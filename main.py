import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlEngine
from PySide6.QtWidgets import QApplication
from RinUI import RinUIWindow

from src.backend.config.container import (
    create_adapters,
    create_gateways,
    create_infra,
    create_providers,
    create_repos,
    create_services,
    create_use_cases,
    ensure_app_initialized,
)
from src.backend.config.font_setup import (
    ensure_utf8_stdio,
    install_rinui_darkdetect_patch,
    setup_app_font,
    setup_quick_controls_style,
)
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.presentation.bridge import Bridge
from src.backend.utils.logger import (
    install_qt_message_handler,
    is_debug_enabled,
    log_debug,
)

ensure_utf8_stdio()

# 在 ThemeManager 实例化之前修补 RinUI darkdetect 检测
install_rinui_darkdetect_patch()


@dataclass
class AppRuntime:
    """启动后的运行时句柄。

    供自动化验收（tools/ui_probe）使用：拿到 engine/window/bridge 后做
    真实运行时的快照与交互，而不被事件循环阻塞。
    """

    app: QApplication
    window: RinUIWindow
    engine: QQmlEngine
    bridge: "Bridge"
    services: object
    providers: object
    adapters: object


def bootstrap(argv: list[str] | None = None) -> AppRuntime:
    """构建对象图并加载主窗口（不进入事件循环）。

    argv 可传 ``["-platform", "offscreen"]`` 之类参数供离屏自动化使用。
    """
    install_qt_message_handler()
    ensure_app_initialized()

    app = QApplication.instance() or QApplication(
        argv if argv is not None else sys.argv
    )
    setup_app_font(app)
    setup_quick_controls_style()

    runtime_config = RuntimeConfig.load_from_file()

    # 构建对象图
    infra = create_infra(runtime_config)
    repos = create_repos()
    providers = create_providers(runtime_config, infra)
    clipboard = QApplication.clipboard()
    gateways = create_gateways(runtime_config, providers, infra, repos, clipboard)
    use_cases = create_use_cases(gateways, repos, providers, clipboard)
    services = create_services(infra, runtime_config)
    adapters = create_adapters(
        services, gateways, use_cases, providers, infra, runtime_config
    )

    from src.backend.config.app_paths import (
        open_library_view_state_path,
        slice_metrics_prefs_path,
        text_slice_progress_path,
    )
    from src.backend.integration.slice_metrics_prefs_store import SliceMetricsPrefsStore
    from src.backend.integration.text_slice_progress_store import TextSliceProgressStore

    from src.backend.integration.open_library_view_state_store import (
        OpenLibraryViewStateStore,
    )

    slice_metrics_store = SliceMetricsPrefsStore(slice_metrics_prefs_path())
    open_library_view_state_store = OpenLibraryViewStateStore(
        open_library_view_state_path()
    )
    text_slice_progress_store = TextSliceProgressStore(text_slice_progress_path())

    bridge = Bridge(
        typing_adapter=adapters.typing,
        text_adapter=adapters.text,
        char_stats_adapter=adapters.char_stats,
        upload_text_adapter=adapters.upload_text,
        registry_adapter=adapters.registry,
        wenlai_adapter=adapters.wenlai,
        ai_text_adapter=adapters.ai_text,
        local_article_adapter=adapters.local_article,
        ziti_adapter=adapters.ziti,
        trainer_adapter=adapters.trainer,
        font_adapter=adapters.font,
        typing_totals_gateway=gateways.typing_totals,
        typing_history_gateway=gateways.typing_history,
        key_listener=adapters.key_listener,
        slice_metrics_prefs_store=slice_metrics_store,
        text_slice_progress_store=text_slice_progress_store,
        ott_segment_provider_cls=adapters.ott_segment_provider_cls,
        update_adapter=adapters.update,
        open_library_view_state_store=open_library_view_state_store,
    )

    # ADR-014：QApplication 就绪后按配置触发一次后台自动更新检查（失败静默）。
    # update_adapter 未装配（并行 lane 未完成）时无操作。
    if runtime_config.update.enabled and runtime_config.update.auto_check:
        bridge.trigger_auto_update_check()

    # QML 引擎
    rin_window = RinUIWindow()
    engine = rin_window.engine
    current_path = os.path.dirname(os.path.abspath(__file__))

    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.addImportPath(current_path)
    resource_base_url = QUrl.fromLocalFile(
        os.path.join(current_path, "resources") + "/"
    )
    engine.rootContext().setContextProperty(
        "resourceBaseUrl", resource_base_url.toString()
    )
    engine.rootContext().setContextProperty("qmlDebug", is_debug_enabled())

    main_qml_path = os.path.join(current_path, "src", "qml", "Main.qml")
    log_debug(f"Loading QML from: {main_qml_path}")
    rin_window.load(main_qml_path)

    return AppRuntime(
        app=app,
        window=rin_window,
        engine=engine,
        bridge=bridge,
        services=services,
        providers=providers,
        adapters=adapters,
    )


def shutdown(runtime: AppRuntime) -> None:
    """事件循环结束后的清理（worker flush / 连接池关闭 / 键盘监听停止 / 主题线程停止）。

    主题监听线程必须在**这里**显式停：它跑的是轮询循环，若在退出期仍活着，
    Qt 销毁 QThread 时会直接 qFatal 导致进程 SIGABRT（实测每次必现）。
    """
    runtime.services.char_stats.flush()
    runtime.providers.federation.close()
    if runtime.adapters.key_listener:
        runtime.adapters.key_listener.stop()
    theme_manager = getattr(runtime.window, "theme_manager", None)
    if theme_manager is not None:
        theme_manager.clean_up()


def main():
    runtime = bootstrap()
    exit_code = runtime.app.exec()
    shutdown(runtime)
    os._exit(exit_code)


if __name__ == "__main__":
    main()
