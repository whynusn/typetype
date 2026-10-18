"""P0 冒烟运行器：离屏加载全部 QML 页面/组件，产出结构化报告。

CLI：
    python -m ui_probe.smoke [--repo-root PATH] [--report PATH] [-v]
    python -m ui_probe.smoke --selfcheck-loop   # 绑定环检测器自检

pytest 入口见 tests/ui_probe/test_qml_smoke.py（以子进程方式调用本 CLI，
避免 Qt/shiboken 初始化污染主测试进程的退出期）。
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from .fixtures import (
    DEFAULT_FIXTURES_RELPATH,
    fixtures_for_target,
    load_fixtures,
    unused_fixture_keys,
)
from .loader import LoadResult, OffscreenHarness
from .report import SmokeReport, build_report


# 已知绑定环：a 依赖 b、b 依赖 a。用于 --selfcheck-loop 验证检测机制。
_LOOP_PROBE_QML = """import QtQuick 2.15
QtObject {
    property int a: b + 1
    property int b: a + 1
}
"""


def _singleton_files(repo_root: Path) -> set[Path]:
    """收集 qmldir 中声明为 singleton 的 QML 文件（不可直接实例化，跳过）。"""
    singletons: set[Path] = set()
    for qmldir in (repo_root / "src/qml").rglob("qmldir"):
        for line in qmldir.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*singleton\s+\S+\s+\S+\s+(\S+)", line)
            if match:
                singletons.add((qmldir.parent / match.group(1)).resolve())
    return singletons


def discover_targets(repo_root: Path) -> list[Path]:
    """发现冒烟目标：src/qml 下全部 .qml，排除 singleton。"""
    repo_root = Path(repo_root)
    skip = _singleton_files(repo_root)
    targets = []
    for path in sorted((repo_root / "src/qml").rglob("*.qml")):
        if path.resolve() in skip:
            continue
        targets.append(path)
    return targets


def run_smoke(
    repo_root: Path,
    verbose: bool = False,
    fixtures_path: Path | None = None,
) -> tuple[SmokeReport, list[LoadResult]]:
    """执行冒烟，返回（报告, 原始结果）。"""
    repo_root = Path(repo_root).resolve()
    targets = discover_targets(repo_root)
    target_rels = {p.relative_to(repo_root).as_posix() for p in targets}

    if fixtures_path is None:
        fixtures_path = repo_root / DEFAULT_FIXTURES_RELPATH
    fixtures = load_fixtures(fixtures_path)

    stale = unused_fixture_keys(fixtures, target_rels)
    if stale:
        print(
            "警告：以下 fixture key 对不上任何冒烟目标（目标被移动/重命名？）："
            + ", ".join(stale),
            file=sys.stderr,
        )

    harness = OffscreenHarness(repo_root)
    results: list[LoadResult] = []
    try:
        for path in targets:
            rel = path.relative_to(repo_root).as_posix()
            specs = fixtures_for_target(fixtures, rel)
            result = harness.load(path, fixture_specs=specs)
            results.append(result)
            if verbose:
                status = "ok" if result.ok else "FAIL"
                fixture_note = (
                    f" [fixtures: {', '.join(result.fixtures)}]"
                    if result.fixtures
                    else ""
                )
                print(f"[{status}] {result.target}{fixture_note}", file=sys.stderr)
                for err in result.load_errors:
                    print(
                        f"    error: {err['message']} (:{err['line']})", file=sys.stderr
                    )
                for msg in result.messages:
                    if msg.severity in ("warning", "critical", "fatal"):
                        print(f"    {msg.severity}: {msg.message}", file=sys.stderr)
    finally:
        harness.close()

    return build_report(repo_root, results), results


def run_selfcheck(repo_root: Path) -> int:
    """绑定环检测器自检：合成已知环，断言 harness 能抓到。

    防检测机制静默失效（消息捕获或判定逻辑改坏时，先失败的是这里，
    而不是放跑所有真环）。返回进程退出码。
    """
    repo_root = Path(repo_root).resolve()
    with tempfile.TemporaryDirectory(prefix="ui-probe-selfcheck-") as tmp:
        probe = Path(tmp) / "loop_probe.qml"
        probe.write_text(_LOOP_PROBE_QML, encoding="utf-8")
        harness = OffscreenHarness(repo_root)
        try:
            result = harness.load(probe)
        finally:
            harness.close()

    if not result.ok:
        print(f"自检组件加载失败: {result.load_errors}", file=sys.stderr)
        return 1
    if not result.binding_loops:
        print(
            "已知绑定环未被检测到——消息捕获或 Binding loop 判定逻辑已失效",
            file=sys.stderr,
        )
        return 1
    print(f"自检通过：{len(result.binding_loops)} 条绑定环告警被捕获")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ui-probe P0 QML 冒烟")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--report", default=None, help="报告输出路径（JSON）")
    parser.add_argument(
        "--fixtures",
        default=None,
        help=f"fixture 文件路径（默认 <repo-root>/{DEFAULT_FIXTURES_RELPATH}）",
    )
    parser.add_argument(
        "--selfcheck-loop",
        action="store_true",
        help="绑定环检测器自检（合成已知环），不执行冒烟",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if args.selfcheck_loop:
        return run_selfcheck(repo_root)

    report, _ = run_smoke(
        repo_root,
        verbose=args.verbose,
        fixtures_path=Path(args.fixtures).resolve() if args.fixtures else None,
    )

    if args.report:
        report.write(Path(args.report))

    summary = report.summary
    print(
        f"ui-probe 冒烟：{summary['total']} 个目标，"
        f"加载失败 {summary['load_failed']}，绑定环 {summary['binding_loops']}，"
        f"警告 {summary['warnings']}"
    )
    for target in report.failed_targets:
        print(f"  FAIL {target['target']}")
        for err in target["load_errors"]:
            print(f"       {err['message']} (:{err['line']}:{err['column']})")
    return 1 if report.failed_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
