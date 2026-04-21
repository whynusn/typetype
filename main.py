import os
import sys

import darkdetect
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

import RinUI.core.theme as _rinui_theme
from RinUI import RinUIWindow
from src.backend.application.gateways.score_gateway import ScoreGateway
from src.backend.application.gateways.text_source_gateway import TextSourceGateway
from src.backend.application.gateways.leaderboard_gateway import LeaderboardGateway
from src.backend.application.usecases.load_text_usecase import LoadTextUseCase
from src.backend.presentation.bridge import Bridge
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.infrastructure.api_client import ApiClient
from src.backend.integration.api_client_auth_provider import ApiClientAuthProvider
from src.backend.integration.api_client_score_submitter import ApiClientScoreSubmitter
from src.backend.integration.leaderboard_fetcher import LeaderboardFetcher
from src.backend.ports.leaderboard_provider import LeaderboardProvider
from src.backend.integration.text_uploader import TextUploader
from src.backend.domain.services.auth_service import AuthService
from src.backend.domain.services.char_stats_service import CharStatsService
from src.backend.domain.services.typing_service import TypingService
from src.backend.integration.global_key_listener import GlobalKeyListener
from src.backend.integration.remote_text_provider import RemoteTextProvider
from src.backend.integration.qt_async_executor import QtAsyncExecutor
from src.backend.integration.qt_local_text_loader import QtLocalTextLoader
from src.backend.integration.sqlite_char_stats_repository import (
    SqliteCharStatsRepository,
)
from src.backend.integration.system_identifier import SystemIdentifier
from src.backend.presentation.adapters.text_adapter import TextAdapter
from src.backend.presentation.adapters.typing_adapter import TypingAdapter
from src.backend.presentation.adapters.auth_adapter import AuthAdapter
from src.backend.presentation.adapters.char_stats_adapter import CharStatsAdapter
from src.backend.presentation.adapters.leaderboard_adapter import LeaderboardAdapter
from src.backend.presentation.adapters.upload_text_adapter import UploadTextAdapter
from src.backend.security.secure_storage import SecureStorage
from src.backend.utils.logger import (
    install_qt_message_handler,
    is_debug_enabled,
    log_debug,
    log_info,
)


def _check_darkdetect_support() -> bool:
    """RinUI 原始实现不支持 Linux，但 darkdetect 在 Linux (D-Bus/gsettings) 上可用。"""
    try:
        return darkdetect.theme() is not None
    except Exception:
        return False


# 在 ThemeManager 实例化之前修补
_rinui_theme.check_darkdetect_support = _check_darkdetect_support


def _load_common_chars() -> list[str]:
    """加载高频五百中文汉字，用于启动时预热 char_stats 缓存。"""
    try:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "texts",
            "前五百.txt",
        )
        with open(path, encoding="gbk") as f:
            text = f.read()
        # 过滤、去重、转换
        return list(dict.fromkeys(c for c in text if "\u4e00" <= c <= "\u9fff"))
    except Exception:
        return []


def _update_base_url(
    runtime_config: RuntimeConfig,
    text_provider: RemoteTextProvider,
    auth_provider: ApiClientAuthProvider,
    score_submitter: ApiClientScoreSubmitter,
    text_uploader: TextUploader,
    leaderboard_provider: LeaderboardFetcher,
    new_base_url: str,
) -> None:
    """统一更新 base_url 到 RuntimeConfig 及所有依赖对象，并持久化。"""
    runtime_config.update_base_url(new_base_url)
    text_provider.update_base_url(runtime_config.base_url)
    auth_provider.update_base_url(runtime_config.base_url)
    score_submitter.update_base_url(runtime_config.base_url)
    text_uploader.update_base_url(runtime_config.base_url)
    leaderboard_provider.update_base_url(runtime_config.base_url)
    log_info(f"[main] base_url 已更新为: {runtime_config.base_url}")


def main():
    install_qt_message_handler()
    app = QGuiApplication(sys.argv)

    # 注册 UI 字体并设为应用默认字体。
    # RinUI 内部组件在 Linux 上读取 Qt.application.font.family，
    # 设置后所有 RinUI 控件自动使用 HarmonyOS 字体，无需逐个覆盖。
    _ui_font_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "resources",
        "fonts",
        "HarmonyOS_Sans_SC_Regular-subset.ttf",
    )
    _font_id = QFontDatabase.addApplicationFont(_ui_font_path)
    if _font_id != -1:
        _families = QFontDatabase.applicationFontFamilies(_font_id)
        if _families:
            app.setFont(QFont(_families[0]))

    clipboard = QGuiApplication.clipboard()
    runtime_config = RuntimeConfig.load_from_file()

    # Infrastructure 层
    api_client = ApiClient(timeout=runtime_config.api_timeout)
    local_text_loader = QtLocalTextLoader()

    # JWT token 提供函数
    def _get_jwt_token() -> str:
        return SecureStorage.get_jwt("current_user") or ""

    text_provider = RemoteTextProvider(
        base_url=runtime_config.base_url,
        api_client=api_client,
        token_provider=_get_jwt_token,
    )

    # Gateways
    score_gateway = ScoreGateway(clipboard=clipboard)
    text_gateway = TextSourceGateway(
        runtime_config=runtime_config,
        text_provider=text_provider,
        local_text_loader=local_text_loader,
    )

    # UseCases
    load_text_usecase = LoadTextUseCase(
        text_gateway=text_gateway,
        clipboard_reader=clipboard,
    )

    # Domain Services
    async_executor = QtAsyncExecutor()
    char_stats_repo = SqliteCharStatsRepository(db_path="data/char_stats.db")
    char_stats_service = CharStatsService(
        repository=char_stats_repo,
        async_executor=async_executor,
    )
    common_chars = _load_common_chars()
    if common_chars:
        char_stats_service.warm_chars(common_chars)

    typing_service = TypingService(char_stats_service=char_stats_service)

    auth_provider = ApiClientAuthProvider(
        api_client=api_client,
        login_url=runtime_config.login_api_url,
        validate_url=runtime_config.validate_api_url,
        refresh_url=runtime_config.refresh_api_url,
        register_url=runtime_config.register_api_url,
    )
    auth_service = AuthService(auth_provider=auth_provider)

    # Score submitter
    score_submit_url = f"{runtime_config.base_url}/api/v1/scores"
    score_submitter = ApiClientScoreSubmitter(
        api_client=api_client,
        submit_url=score_submit_url,
        token_provider=_get_jwt_token,
    )

    # Text uploader
    text_upload_url = f"{runtime_config.base_url}/api/v1/texts/upload"
    text_uploader = TextUploader(
        api_client=api_client,
        upload_url=text_upload_url,
        token_provider=_get_jwt_token,
    )

    # Adapters
    typing_adapter = TypingAdapter(
        typing_service=typing_service,
        score_gateway=score_gateway,
        score_submitter=score_submitter,
    )
    text_adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=load_text_usecase,
        local_text_loader=local_text_loader,
    )
    auth_adapter = AuthAdapter(auth_service=auth_service)
    char_stats_adapter = CharStatsAdapter(char_stats_service=char_stats_service)

    # Leaderboard
    leaderboard_provider: LeaderboardProvider = LeaderboardFetcher(
        api_client=api_client,
        base_url=runtime_config.base_url,
        token_provider=_get_jwt_token,
    )
    leaderboard_gateway = LeaderboardGateway(leaderboard_provider=leaderboard_provider)
    leaderboard_adapter = LeaderboardAdapter(
        leaderboard_gateway=leaderboard_gateway,
        runtime_config=runtime_config,
    )

    # Upload text adapter
    upload_text_adapter = UploadTextAdapter(
        text_uploader=text_uploader,
    )

    # Platform detection
    system_identifier = SystemIdentifier()
    os_type, display_server = system_identifier.get_system_info()
    log_info(f"系统: {os_type} 平台: {display_server}")

    key_listener = None
    if os_type == "Linux" and display_server == "Wayland":
        key_listener = GlobalKeyListener()
        key_listener.start()
        log_info("因系统平台特殊性，全局监听器已启动")

    # Bridge
    bridge = Bridge(
        typing_adapter=typing_adapter,
        text_adapter=text_adapter,
        auth_adapter=auth_adapter,
        char_stats_adapter=char_stats_adapter,
        upload_text_adapter=upload_text_adapter,
        leaderboard_adapter=leaderboard_adapter,
        key_listener=key_listener,
        base_url_update_callback=lambda new_url: _update_base_url(
            runtime_config=runtime_config,
            text_provider=text_provider,
            auth_provider=auth_provider,
            score_submitter=score_submitter,
            text_uploader=text_uploader,
            leaderboard_provider=leaderboard_provider,
            new_base_url=new_url,
        ),
    )

    bridge.initializeLoginState()

    # 预加载文本来源目录，避免首次切换页面时的网络延迟
    bridge.loadCatalog()

    # 使用 RinUIWindow 接管 engine 和 QML 加载
    rin_window = RinUIWindow()
    engine = rin_window.engine

    engine.rootContext().setContextProperty("appBridge", bridge)

    # 获取当前文件所在路径
    current_path = os.path.dirname(os.path.abspath(__file__))

    # 将 QML 文件所在目录添加到导入路径 (如果你在 QML 里 import 其他自定义模块)
    engine.addImportPath(current_path)
    resource_base_url = QUrl.fromLocalFile(
        os.path.join(current_path, "resources") + "/"
    )
    engine.rootContext().setContextProperty(
        "resourceBaseUrl", resource_base_url.toString()
    )
    engine.rootContext().setContextProperty("qmlDebug", is_debug_enabled())

    # 拼接出 Main.qml 的绝对文件路径
    main_qml_path = os.path.join(current_path, "src", "qml", "Main.qml")
    log_debug(f"Loading QML from: {main_qml_path}")

    # 通过 RinUIWindow.load() 加载 QML（内部会注入 ThemeManager、设置 import path 等）
    rin_window.load(main_qml_path)

    # --------------------

    # 清理资源并退出
    exit_code = app.exec()
    char_stats_service.flush()
    api_client.close()
    if key_listener:
        key_listener.stop()  # 立即生效，无需 wait
    del engine
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
