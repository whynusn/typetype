"""场景 DSL v0：声明式交互验收（ADR-015 P1.2 / 决策 6）。

场景是 **YAML 文件**，也是文档——可评审、可 diff、AI 可直接读写。只引用语义
（role / text / objectName / path / 上下文对象名），不 import 任何 typetype
或 RinUI 类型。

两种模式：

- ``component``：离屏加载单个 QML（mock bridge）。快、隔离，测组件自身行为。
- ``app``：启动**真实客户端**（真 Bridge / 真配置 / 真数据 / 真 worker）。
  慢，但能抓到只有真机才显形的缺陷——实测两个缺陷都是这么抓到的。

YAML 形态::

    schema: ui-probe/scenario@1
    name: typing-basic
    description: 载文 → 打字 → 统计更新
    mode: app
    wait_ms: 1500
    steps:
      - name: 上屏区有范文
        action: assert
        find: {role: static-text, text: "你好"}
        expect: {text_contains: "你好"}
      - name: 打完一段
        action: type
        find: {role: text-input}
        text: "你好，世界。"
        mode: ime
      - name: 进度满格
        action: assert
        find: {context: appBridge}
        expect: {prop_equals: {charNum: "6/6"}}

CLI::

    python -m ui_probe.scenario --scenario tools/ui_probe/scenarios/typing_basic.yaml
    python -m ui_probe.scenario --all --out scenario_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from PySide6.QtQuick import QQuickItem

from .env import enter_sandbox
from .interact import Driver, invoke_callable
from .loader import OffscreenHarness
from .message_capture import MessageCollector, parse_exit_messages
from .selector import Selector, node_text, read_prop, resolve_all
from .snapshot import SnapshotOptions, snapshot_node

SCENARIO_SCHEMA = "ui-probe/scenario@1"

_ACTIONS = {"wait", "assert", "click", "type", "key", "call", "set", "snapshot", "pump"}
_EXPECT_KEYS = {
    "exists",
    "count",
    "count_gte",
    "text_contains",
    "text_equals",
    "prop_equals",
    "prop_contains",
    "prop_true",
    "prop_false",
    "prop_gt",
    "prop_lt",
    "visible",
    "enabled",
    "min_width",
    "min_height",
    "no_new_messages",
}


@dataclass
class StepResult:
    name: str
    action: str
    status: str = "pass"
    detail: dict = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }


class ScenarioError(Exception):
    """场景执行失败（断言不成立或动作无法完成）。"""


# ------------------------------------------------------------------
# 断言求值
# ------------------------------------------------------------------


def evaluate_expect(
    runner: "ScenarioRunner", selector: Selector, expect: dict, root
) -> dict:
    """求值一组断言，返回 actual 快照（供报告展示实际值）。"""
    unknown = set(expect) - _EXPECT_KEYS
    if unknown:
        raise ScenarioError(
            f"断言含未知字段 {sorted(unknown)}（可用：{sorted(_EXPECT_KEYS)}）"
        )

    driver = runner.driver
    actual: dict = {}
    failures: list[str] = []

    if "no_new_messages" in expect:
        new = runner.new_messages()
        actual["new_messages"] = new
        if expect["no_new_messages"] and new:
            failures.append(f"新增 {len(new)} 条 Qt/QML 消息：{new[:3]}")

    if expect.get("exists", True) is False:
        hits = resolve_all(root, selector) if not selector.context else []
        actual["count"] = len(hits)
        if hits:
            failures.append(f"期望不存在，实际命中 {len(hits)} 个")
        return {"actual": actual, "failures": failures}

    try:
        obj, info = driver.locate(selector)
    except LookupError as exc:
        if "count" in expect or "count_gte" in expect:
            raise ScenarioError(str(exc)) from exc
        raise ScenarioError(f"断言定位失败：{exc}") from exc
    actual["node"] = info

    if "count" in expect or "count_gte" in expect:
        hits = resolve_all(root, selector)
        actual["count"] = len(hits)
        if "count" in expect and len(hits) != expect["count"]:
            failures.append(f"count 期望 {expect['count']}，实际 {len(hits)}")
        if "count_gte" in expect and len(hits) < expect["count_gte"]:
            failures.append(f"count_gte 期望 ≥{expect['count_gte']}，实际 {len(hits)}")

    if "text_contains" in expect:
        text = node_text(obj)
        actual["text"] = text
        if expect["text_contains"] not in text:
            failures.append(f"文本不包含 {expect['text_contains']!r}，实际 {text!r}")
    if "text_equals" in expect:
        text = node_text(obj)
        actual["text"] = text
        if text != expect["text_equals"]:
            failures.append(f"文本期望 {expect['text_equals']!r}，实际 {text!r}")

    for name, value in (expect.get("prop_equals") or {}).items():
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if got != value:
            failures.append(f"属性 {name} 期望 {value!r}，实际 {got!r}")
    for name, value in (expect.get("prop_contains") or {}).items():
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if not isinstance(got, str) or value not in got:
            failures.append(f"属性 {name} 期望包含 {value!r}，实际 {got!r}")
    for name in expect.get("prop_true") or []:
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if got is not True:
            failures.append(f"属性 {name} 期望 true，实际 {got!r}")
    for name in expect.get("prop_false") or []:
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if got is not False:
            failures.append(f"属性 {name} 期望 false，实际 {got!r}")
    for name, bound in (expect.get("prop_gt") or {}).items():
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if not isinstance(got, (int, float)) or got <= bound:
            failures.append(f"属性 {name} 期望 >{bound}，实际 {got!r}")
    for name, bound in (expect.get("prop_lt") or {}).items():
        got = read_prop(obj, name)
        actual.setdefault("props", {})[name] = got
        if not isinstance(got, (int, float)) or got >= bound:
            failures.append(f"属性 {name} 期望 <{bound}，实际 {got!r}")

    if "visible" in expect:
        got = read_prop(obj, "visible")
        actual["visible"] = got
        if bool(got) != bool(expect["visible"]):
            failures.append(f"visible 期望 {expect['visible']}，实际 {got!r}")
    if "enabled" in expect:
        got = read_prop(obj, "enabled")
        actual["enabled"] = got
        if bool(got) != bool(expect["enabled"]):
            failures.append(f"enabled 期望 {expect['enabled']}，实际 {got!r}")
    for key, prop in (("min_width", "width"), ("min_height", "height")):
        if key in expect:
            got = read_prop(obj, prop)
            actual[prop] = got
            if not isinstance(got, (int, float)) or got < expect[key]:
                failures.append(f"{prop} 期望 ≥{expect[key]}，实际 {got!r}")

    return {"actual": actual, "failures": failures}


# ------------------------------------------------------------------
# 执行引擎
# ------------------------------------------------------------------


class ScenarioRunner:
    """按模式装配环境，逐步执行动作。"""

    def __init__(self, spec: dict, repo_root: Path) -> None:
        self.spec = spec
        self.repo_root = repo_root
        self.collector = MessageCollector()
        self._seen_messages = 0
        self.driver: Driver | None = None
        self.root = None
        self._sandbox_home: Path | None = None

    # -- 消息窗口（供 no_new_messages 断言使用） --

    def new_messages(self) -> list[dict]:
        items = [
            {
                "severity": m.severity,
                "message": m.message[:200],
                "file": m.file,
                "line": m.line,
            }
            for m in self.collector.messages[self._seen_messages :]
        ]
        self._seen_messages = len(self.collector.messages)
        return items

    # -- 隔离信息（报告透明性 + 回归门禁的输入）--

    def isolation_info(self) -> dict:
        """真机模式跑在哪个 HOME 里。

        桌面会话常预置 XDG_CONFIG_HOME/XDG_DATA_HOME，**只改 HOME 隔离不住**
        ——配置和打字历史会直接写进用户真实目录。所以真机模式一律走
        `enter_sandbox()`，这里把结果写进报告，由测试断言它确是一次性目录。
        """
        return {
            "isolated": bool(self._sandbox_home),
            "home": str(self._sandbox_home) if self._sandbox_home else None,
        }

    # -- 环境装配 --

    def setup(self) -> None:
        mode = self.spec.get("mode", "component")
        wait_ms = int(self.spec.get("wait_ms", 800))
        # 覆盖窗口一：install（Qt handler）
        self.collector.install()
        if mode == "app":
            self.collector.attach_log_sink()  # bootstrap 期 app 会顶掉 Qt handler
            if str(self.repo_root) not in sys.path:
                sys.path.insert(0, str(self.repo_root))
            # 必须在 import main 之前：bootstrap 期间就会解析配置/数据目录，
            # 只改 HOME 挡不住预置的 XDG_*——那样会真写用户的打字历史。
            self._sandbox_home = enter_sandbox()
            from main import bootstrap  # noqa: PLC0415

            self._runtime = bootstrap(argv=[sys.argv[0], "-platform", "offscreen"])
            self.collector.detach_log_sink()
            self.collector.reinstall()  # 覆盖窗口二：夺回 Qt handler
            window = self._runtime.window.root_window
            self.root = window.contentItem()
            self.driver = Driver(
                self._runtime.app,
                self.root,
                window=window,
                context_getter=lambda n: {"appBridge": self._runtime.bridge}.get(n),
            )
        else:
            self._harness = OffscreenHarness(self.repo_root)
            result = self._harness.load(
                self.repo_root / self.spec["target"],
                fixture_specs=self.spec.get("fixtures"),
            )
            if not result.ok:
                raise ScenarioError(
                    f"组件加载失败：{self.spec.get('target')} —— "
                    f"{[e['message'] for e in result.load_errors]}"
                )
            self.root = self._harness._instances[-1]
            # 离屏无窗口：根节点是内容尺寸，不设视口尺寸则布局不解算，
            # 子节点宽度为 0，点击/几何断言全部失真（与 snapshot 同一坑）。
            if isinstance(self.root, QQuickItem):
                self.root.setWidth(int(self.spec.get("root_width", 1280)))
                self.root.setHeight(int(self.spec.get("root_height", 800)))
            context = self._harness.engine.rootContext()
            self.driver = Driver(
                self._harness.app,
                self.root,
                window=None,
                context_getter=lambda n: context.contextProperty(n),
            )
        self.driver.pump(wait_ms)

    def teardown(self) -> None:
        if getattr(self, "_runtime", None) is not None:
            from main import shutdown  # noqa: PLC0415

            shutdown(self._runtime)
        if getattr(self, "_harness", None) is not None:
            self._harness.close()
        self.collector.uninstall()

    # -- 步骤 --

    def run_step(self, step: dict) -> StepResult:
        action = step.get("action")
        if action not in _ACTIONS:
            raise ScenarioError(f"未知动作 {action!r}（可用：{sorted(_ACTIONS)}）")
        name = step.get("name") or action
        started = time.monotonic()
        result = StepResult(name=name, action=action)
        driver, root = self.driver, self.root

        try:
            if action in ("wait", "pump"):
                driver.pump(int(step.get("ms", 100)))
            elif action == "assert":
                selector = Selector.from_dict(step.get("find"))
                outcome = evaluate_expect(
                    self, selector, step.get("expect") or {}, root
                )
                result.detail = outcome["actual"]
                if outcome["failures"]:
                    result.status = "fail"
                    result.detail["failures"] = outcome["failures"]
            elif action == "click":
                result.detail["node"] = driver.click(Selector.from_dict(step["find"]))
            elif action == "type":
                selector = Selector.from_dict(step["find"])
                text = step.get("text", "")
                result.detail["node"] = driver.type_text(
                    selector, text, mode=step.get("mode", "ime")
                )
                result.detail["text"] = text
                result.detail["mode"] = step.get("mode", "ime")
                if step.get("expect"):
                    outcome = evaluate_expect(self, selector, step["expect"], root)
                    result.detail.update(outcome["actual"])
                    if outcome["failures"]:
                        result.status = "fail"
                        result.detail["failures"] = outcome["failures"]
            elif action == "key":
                result.detail["pressed"] = driver.press_key(
                    step["key"], step.get("modifiers")
                )
            elif action == "call":
                selector = Selector.from_dict(step["find"])
                value = invoke_callable(
                    driver.find(selector), step["method"], list(step.get("args") or [])
                )
                result.detail["returned"] = (
                    value if isinstance(value, (str, int, float, bool)) else str(value)
                )
                if step.get("expect"):
                    outcome = evaluate_expect(self, selector, step["expect"], root)
                    result.detail.update(outcome["actual"])
                    if outcome["failures"]:
                        result.status = "fail"
                        result.detail["failures"] = outcome["failures"]
            elif action == "set":
                selector = Selector.from_dict(step["find"])
                for prop, value in (step.get("props") or {}).items():
                    driver.set_prop(selector, prop, value)
                result.detail["props"] = step.get("props") or {}
            elif action == "snapshot":
                selector = step.get("find")
                target = driver.find(Selector.from_dict(selector)) if selector else root
                tree = snapshot_node(
                    target,
                    "0",
                    0,
                    SnapshotOptions(max_nodes=int(step.get("max_nodes", 500))),
                )
                result.detail["tree"] = tree
        except Exception as exc:  # 任一动作异常即该步失败，不中断后续步骤
            result.status = "fail"
            result.detail["error"] = f"{type(exc).__name__}: {exc}"

        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result

    def run(self) -> dict:
        started = time.monotonic()
        steps: list[StepResult] = []
        setup_error = None
        try:
            self.setup()
        except Exception as exc:
            setup_error = f"{type(exc).__name__}: {exc}"
        if setup_error is None:
            # 基线对齐：装配期自身的消息不记账，no_new_messages 判的是
            # "这一步有没有引入新噪声"（装配期噪声由 summary 兜住）
            self.new_messages()
            for raw in self.spec.get("steps", []):
                steps.append(self.run_step(raw))
        try:
            self.teardown()
        except Exception:
            pass

        messages = [
            {
                "severity": m.severity,
                "category": m.category,
                "message": m.message,
                "file": m.file,
                "line": m.line,
            }
            for m in self.collector.messages
        ]
        return {
            "schema": SCENARIO_SCHEMA,
            "name": self.spec.get("name", "unnamed"),
            "description": self.spec.get("description", ""),
            "mode": self.spec.get("mode", "component"),
            "target": self.spec.get("target", ""),
            "setup_error": setup_error,
            # 透明性：真机模式必须跑在一次性 HOME 里，否则一会就写脏用户数据
            "isolation": self.isolation_info(),
            "steps": [s.to_dict() for s in steps],
            "messages": messages,
            "summary": {
                "duration_ms": int((time.monotonic() - started) * 1000),
                "steps": len(steps),
                "passed": sum(1 for s in steps if s.status == "pass"),
                "failed": sum(1 for s in steps if s.status == "fail"),
                "errors": sum(
                    1 for m in messages if m["severity"] in ("critical", "fatal")
                ),
                "warnings": sum(1 for m in messages if m["severity"] == "warning"),
                "binding_loops": sum(
                    1 for m in messages if "Binding loop" in m["message"]
                ),
            },
        }


def run_scenario_file(path: Path, repo_root: Path) -> dict:
    # `{{today}}` 占位符替换为运行当天日期（ISO），避免场景里硬编码日期过期
    raw = (
        Path(path)
        .read_text(encoding="utf-8")
        .replace("{{today}}", date.today().isoformat())
    )
    spec = yaml.safe_load(raw)
    if spec.get("schema") not in (None, SCENARIO_SCHEMA):
        raise ScenarioError(
            f"{path}: 场景 schema 应为 {SCENARIO_SCHEMA}，实际 {spec.get('schema')!r}"
        )
    return ScenarioRunner(spec, repo_root).run()


def discover_scenarios(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "tools/ui_probe/scenarios").glob("*.yaml"))


def run_scenario_isolated(path: Path, repo_root: Path, timeout: int = 180) -> dict:
    """在**独立子进程**里跑单个场景，报告经 JSON 回传。

    为什么必须隔离（与冒烟同一坑）：Qt 在一个进程里起第二个真实客户端
    （第二个 Bridge / RinUIWindow / worker）状态会串，且退出期静态析构与
    后台线程冲突会 SIGABRT。场景彼此独立，就该彼此隔离。
    """
    import os
    import shutil
    import subprocess
    import tempfile

    from .env import create_isolated_home, isolated_env

    tmpdir = tempfile.mkdtemp(prefix="ui-probe-scn-", dir=str(Path.home()))
    # 每个场景一份独立 HOME：app 模式会写配置与打字历史，共用会让场景互相
    # 污染（前一个场景的成绩变成后一个场景的初始状态）。这里由父进程创建并
    # 在收尾时删除——子进程的 enter_sandbox() 认 UI_PROBE_HOME，不会自己再建。
    scenario_home = create_isolated_home(Path(tmpdir))
    out = Path(tmpdir) / "report.json"
    try:
        # 必须连 HOME/XDG_* 一起给：只设 UI_PROBE_HOME 的话，子进程的
        # enter_sandbox() 复用该目录却不套覆盖，桌面会话预置的 XDG_DATA_HOME
        # 会指回用户真实目录，打字历史直接写进真实数据。
        env = isolated_env(scenario_home)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(repo_root / "tools"), env.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ui_probe.scenario",
                "--repo-root",
                str(repo_root),
                "--scenario",
                str(path),
                "--out",
                str(out),
                # 关键：子进程必须 --in-process，否则它会再去起子进程
                # （实测：漏了这个参数就是无限递归，进程树挂死）
                "--in-process",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(repo_root),
            env=env,
        )
        if out.exists():
            payload = json.loads(out.read_text(encoding="utf-8"))
            report = payload["scenarios"][0]
            # 退出期兜底：Qt 在进程销毁阶段发的消息（handler 那时已失效）
            # 只能从 stderr 捞——实测靠这条抓到了"每次退出必崩"的真实缺陷。
            late = parse_exit_messages(proc.stderr)
            if late:
                report["messages"] = report.get("messages", []) + [
                    {
                        "severity": m.severity,
                        "category": m.category,
                        "message": m.message,
                        "file": m.file,
                        "line": m.line,
                    }
                    for m in late
                ]
                summary = report["summary"]
                summary["errors"] += sum(
                    1 for m in late if m.severity in ("critical", "fatal")
                )
                summary["warnings"] += sum(1 for m in late if m.severity == "warning")
                summary["exit_phase_messages"] = len(late)
            return report
        return {
            "schema": SCENARIO_SCHEMA,
            "name": Path(path).stem,
            "mode": "unknown",
            "target": "",
            "setup_error": f"子进程无报告产出（exit={proc.returncode}）：{proc.stderr[-1500:]}",
            "steps": [],
            "messages": [],
            "summary": {
                "steps": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "warnings": 0,
                "binding_loops": 0,
                "duration_ms": 0,
            },
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


_SELFCHECK_YAML = """\
schema: ui-probe/scenario@1
name: selfcheck-should-fail
description: 自检场景——断言必然不成立，用来验证"失败能被报出来"
mode: component
target: src/qml/typing/LowerPane.qml
wait_ms: 100
steps:
  - name: 必然失败的断言
    action: assert
    find: {objectName: typingInput}
    expect:
      text_equals: "这个文本绝对不存在"
  - name: 必然定位不到的节点
    action: assert
    find: {objectName: 不存在的节点}
    expect:
      exists: true
"""


def run_selfcheck(repo_root: Path) -> dict:
    """检测器自检：合成一个必然失败的场景，验证引擎**会**报失败。

    没有自检，"引擎静默把所有步骤判为 pass" 这种失效是看不见的——
    门禁会一路绿灯直到真出事（与绑定环检测器自检同一个道理）。
    """
    spec = yaml.safe_load(_SELFCHECK_YAML)
    report = ScenarioRunner(spec, repo_root).run()
    failed_steps = [s for s in report["steps"] if s["status"] == "fail"]
    return {
        "ok": len(failed_steps) == 2 and report["summary"]["failed"] == 2,
        "expected_failures": 2,
        "actual_failures": report["summary"]["failed"],
        "detail": [f"{s['name']}: {s['status']}" for s in report["steps"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ui-probe 场景验收（声明式交互）")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument(
        "--scenario", action="append", default=[], help="场景文件（可多次）"
    )
    parser.add_argument("--all", action="store_true", help="跑全部场景")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--pretty", action="store_true", help="缩进输出")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="不隔离子进程（调试单个场景用；多场景同进程会串状态）",
    )
    parser.add_argument(
        "--selfcheck",
        action="store_true",
        help="自检：跑一个必然失败的场景，验证失败能被报出来",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if args.selfcheck:
        result = run_selfcheck(repo_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    paths = (
        discover_scenarios(repo_root) if args.all else [Path(p) for p in args.scenario]
    )
    if not paths:
        print("未指定场景（--scenario 或 --all）", file=sys.stderr)
        return 2

    if args.in_process:
        reports = [run_scenario_file(p, repo_root) for p in paths]
    else:
        reports = [run_scenario_isolated(p, repo_root) for p in paths]
    payload = {
        "schema": SCENARIO_SCHEMA,
        "repo_root": str(repo_root),
        "scenarios": reports,
        "summary": {
            "total": len(reports),
            "passed": sum(
                1
                for r in reports
                if r["summary"]["failed"] == 0 and not r["setup_error"]
            ),
            "failed": sum(
                1 for r in reports if r["summary"]["failed"] or r["setup_error"]
            ),
        },
    }
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        for r in reports:
            s = r["summary"]
            flag = "PASS" if s["failed"] == 0 and not r["setup_error"] else "FAIL"
            print(
                f"[{flag}] {r['name']}（{r['mode']}）：步骤 {s['passed']}/{s['steps']}，"
                f"错误 {s['errors']}，警告 {s['warnings']}，绑定环 {s['binding_loops']}"
            )
        print(f"-> {args.out}")
    else:
        print(text)
    return 1 if payload["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
