import os
import sys

import darkdetect
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

import RinUI.core.theme as _rinui_theme
from RinUI import RinUIWindow
from src.backend.application.usecases.score_usecase import ScoreUseCase
from src.backend.application.usecases.text_usecase import TextUseCase
from src.backend.bridge import Bridge
from src.backend.config.runtime_config import RuntimeConfig
from src.backend.core.api_client import ApiClient
from src.backend.domain.auth_service import AuthService
from src.backend.domain.char_stats_service import CharStatsService
from src.backend.domain.text_load_service import TextLoadService
from src.backend.domain.typing_service import TypingService
from src.backend.integration.global_key_listener import GlobalKeyListener
from src.backend.integration.local_text_loader import QtLocalTextLoader
from src.backend.integration.sai_wen_service import SaiWenService
from src.backend.integration.sqlite_char_stats_repository import (
    SqliteCharStatsRepository,
)
from src.backend.integration.system_identifier import SystemIdentifier
from src.backend.utils.logger import is_debug_enabled, log_debug, log_info


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


def main():
    app = QGuiApplication(sys.argv)

    # 注册 UI 字体并设为应用默认字体。
    # RinUI 内部组件（Button、ComboBox 等）在 Linux 上读取 Qt.application.font.family，
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
    runtime_config = RuntimeConfig()

    api_client = ApiClient(timeout=runtime_config.api_timeout)
    sai_wen_service = SaiWenService(api_client=api_client)
    local_text_loader = QtLocalTextLoader()
    text_usecase = TextUseCase(
        text_fetcher=sai_wen_service,
        clipboard=clipboard,
        local_text_loader=local_text_loader,
    )
    score_usecase = ScoreUseCase(clipboard=clipboard)

    char_stats_repo = SqliteCharStatsRepository(db_path="data/char_stats.db")
    char_stats_service = CharStatsService(repository=char_stats_repo)
    common_chars = _load_common_chars()
    if common_chars:
        char_stats_service.warm_chars(common_chars)

    typing_service = TypingService(
        score_usecase=score_usecase, char_stats_service=char_stats_service
    )
    text_load_service = TextLoadService(
        text_usecase=text_usecase,
        runtime_config=runtime_config,
    )
    auth_service = AuthService(
        api_client=api_client,
        login_url=runtime_config.login_api_url,
        validate_url=runtime_config.validate_api_url,
        refresh_url=runtime_config.refresh_api_url,
    )
    system_identifier = SystemIdentifier()
    os_type, display_server = system_identifier.get_system_info()
    log_info(f"系统: {os_type} 平台: {display_server}")

    key_listener = None
    if os_type == "Linux" and display_server == "Wayland":
        key_listener = GlobalKeyListener()
        key_listener.start()
        log_info("因系统平台特殊性，全局监听器已启动")

    bridge = Bridge(
        typing_service=typing_service,
        text_load_service=text_load_service,
        auth_service=auth_service,
        runtime_config=runtime_config,
        key_listener=key_listener,
        char_stats_service=char_stats_service,
    )

    bridge.initializeLoginState()

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
