import os
import sys

from PySide6.QtCore import QUrl
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
from src.backend.config.font_setup import install_rinui_darkdetect_patch, setup_app_font
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.presentation.bridge import Bridge
from src.backend.utils.logger import (
    install_qt_message_handler,
    is_debug_enabled,
    log_debug,
    log_info,
)

# 在 ThemeManager 实例化之前修补 RinUI darkdetect 检测
install_rinui_darkdetect_patch()


def main():
    install_qt_message_handler()
    ensure_app_initialized()

    app = QApplication(sys.argv)
    setup_app_font(app)

    runtime_config = RuntimeConfig.load_from_file()

    # 构建对象图
    infra = create_infra(runtime_config)
    repos = create_repos()
    providers = create_providers(runtime_config, infra)
    clipboard = QApplication.clipboard()
    gateways = create_gateways(runtime_config, providers, infra, repos, clipboard)
    use_cases = create_use_cases(gateways, repos, clipboard)
    services = create_services(infra, runtime_config)
    adapters = create_adapters(services, gateways, use_cases, infra, runtime_config)

    # URL 更新回调：列表迭代替代逐个调用
    url_dependent = [
        providers.text,
        services.auth_provider,
        services.score_submitter,
        services.text_uploader,
        services.leaderboard_fetcher,
    ]

    def update_base_url(new_url: str) -> None:
        runtime_config.update_base_url(new_url)
        for obj in url_dependent:
            obj.update_base_url(runtime_config.base_url)
        log_info(f"[main] base_url 已更新为: {runtime_config.base_url}")

    bridge = Bridge(
        typing_adapter=adapters.typing,
        text_adapter=adapters.text,
        auth_adapter=adapters.auth,
        char_stats_adapter=adapters.char_stats,
        upload_text_adapter=adapters.upload_text,
        leaderboard_adapter=adapters.leaderboard,
        wenlai_adapter=adapters.wenlai,
        local_article_adapter=adapters.local_article,
        ziti_adapter=adapters.ziti,
        trainer_adapter=adapters.trainer,
        font_adapter=adapters.font,
        typing_totals_gateway=gateways.typing_totals,
        key_listener=adapters.key_listener,
        base_url_update_callback=update_base_url,
    )
    bridge.initializeLoginState()
    bridge.loadCatalog()

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

    # 事件循环 + 清理
    exit_code = app.exec()
    services.char_stats.flush()
    infra.api_client.close()
    if adapters.key_listener:
        adapters.key_listener.stop()
    del engine
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
