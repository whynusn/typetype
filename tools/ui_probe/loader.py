"""离屏环境装配与 QML 组件加载。

复刻 main.py 的最小启动面：QApplication（offscreen）+ RinUIWindow
（engine + ThemeManager + 导入路径）+ 上下文属性（appBridge mock /
resourceBaseUrl / qmlDebug）。与真实 app 的差异只有：无 Bridge 实例
（换 mock）、无事件循环。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

from .fixtures import resolve_fixture_value
from .message_capture import CapturedMessage, MessageCollector
from .mock_bridge import write_mock_bridge
from .bridge_introspect import parse_bridge_file


@dataclass
class LoadResult:
    """单个 QML 目标的加载结果。"""

    target: str
    ok: bool
    load_errors: list[dict] = field(default_factory=list)
    messages: list[CapturedMessage] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)  # 注入的属性名（透明性）

    @property
    def binding_loops(self) -> list[CapturedMessage]:
        return [m for m in self.messages if "Binding loop" in m.message]


class OffscreenHarness:
    """离屏 QML 加载环境（进程内单例语义：一个 app + 一个 engine）。"""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)

        self._owns_app = QApplication.instance() is None
        if self._owns_app:
            # 平台选择走 argv 而非 QT_QPA_PLATFORM 环境变量：用户桌面环境
            # 常预置 wayland/xcb，离屏 harness 必须无视之（环境变量会被
            # 预置值"赢定"，argv 的 -platform 优先级更高）。
            # 未来 P2 CU E2E（xvfb）可用 UI_PROBE_QT_PLATFORM 覆盖。
            platform = os.environ.get("UI_PROBE_QT_PLATFORM", "offscreen")
            self.app = QApplication([sys.argv[0] or "ui-probe", "-platform", platform])
        else:
            self.app = QApplication.instance()

        from RinUI import RinUIWindow

        self._rin_window = RinUIWindow()
        self.engine: QQmlEngine = self._rin_window.engine

        # 复刻 main.py 的导入路径与上下文属性
        self.engine.addImportPath(str(self.repo_root))
        self.engine.addImportPath(str(self.repo_root / "RinUI"))
        self.engine.rootContext().setContextProperty(
            "ThemeManager", self._rin_window.theme_manager
        )
        self.engine.rootContext().setContextProperty("qmlDebug", False)
        self.engine.rootContext().setContextProperty(
            "resourceBaseUrl",
            QUrl.fromLocalFile(str(self.repo_root / "resources") + "/").toString(),
        )

        # mock bridge：由 bridge.py API 面自动生成
        api = parse_bridge_file(self.repo_root / "src/backend/presentation/bridge.py")
        import tempfile

        mock_path = write_mock_bridge(api, Path(tempfile.mkdtemp(prefix="ui-probe-")))
        self._mock_component = QQmlComponent(
            self.engine, QUrl.fromLocalFile(str(mock_path))
        )
        self._mock_bridge = self._mock_component.create()
        if self._mock_bridge is None:
            errors = [self._error_dict(e) for e in self._mock_component.errors()]
            raise RuntimeError(f"mock bridge 加载失败: {errors}")
        self.engine.rootContext().setContextProperty("appBridge", self._mock_bridge)

        self._instances: list[object] = []

    @staticmethod
    def _error_dict(error) -> dict:
        return {
            "message": str(error.description()),
            "line": int(error.line()),
            "column": int(error.column()),
        }

    def load(self, qml_path: Path, fixture_specs: dict | None = None) -> LoadResult:
        """加载单个 QML 文件并实例化，返回结构化结果。

        fixture_specs：独立加载时注入的初始属性（见 fixtures.py）。
        fixture 解析失败记为加载错误——静默降级会掩盖隔离问题。
        """
        try:
            target = str(Path(qml_path).relative_to(self.repo_root))
        except ValueError:
            # 仓库外路径（自检/临时组件）：退回绝对路径，仍可加载
            target = str(Path(qml_path))
        with MessageCollector() as collector:
            component = QQmlComponent(
                self.engine, QUrl.fromLocalFile(str(Path(qml_path).absolute()))
            )
            errors = [self._error_dict(e) for e in component.errors()]
            properties: dict[str, object] = {}
            if not errors and fixture_specs:
                for name, spec in fixture_specs.items():
                    try:
                        properties[name] = resolve_fixture_value(self.engine, spec)
                    except Exception as exc:
                        errors.append(
                            {
                                "message": f"fixture '{name}' 解析失败: {exc}",
                                "line": 0,
                                "column": 0,
                            }
                        )
            instance = None
            if not errors:
                if properties:
                    instance = component.createObject(None, properties)
                else:
                    instance = component.create()
                if instance is None:
                    errors = [self._error_dict(e) for e in component.errors()]
            if instance is not None:
                # 持有引用，避免 GC 早于延迟错误/销毁完成
                self._instances.append(instance)

        return LoadResult(
            target=target,
            ok=not errors,
            load_errors=errors,
            messages=collector.messages,
            fixtures=sorted(fixture_specs or {}),
        )

    def close(self) -> None:
        self._instances.clear()
        self._mock_component = None
        self._mock_bridge = None
        self._rin_window = None
        if self._owns_app:
            # 必须主动销毁 QApplication，不能留着到进程退出：Qt/shiboken
            # 的退出期静态析构会与后台 daemon 线程（如 OTT 跨仓测试的
            # socketserver serve_forever）冲突，实测全量 pytest 跑到
            # 100% 后 SIGABRT——留着 app 就是留着这颗雷。
            self.app = None
