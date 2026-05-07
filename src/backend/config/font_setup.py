"""Qt 字体初始化与 RinUI darkdetect 补丁。"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import darkdetect

import RinUI.core.theme as _rinui_theme

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


def _check_darkdetect_support() -> bool:
    """RinUI 原始实现不支持 Linux，但 darkdetect 在 Linux (D-Bus/gsettings) 上可用。"""
    try:
        return darkdetect.theme() is not None
    except Exception:
        return False


def install_rinui_darkdetect_patch() -> None:
    """修补 RinUI ThemeManager 的 darkdetect 检测，必须在 RinUIWindow 实例化前调用。"""
    _rinui_theme.check_darkdetect_support = _check_darkdetect_support


def find_system_cjk_font() -> str | None:
    """用 fontconfig 找一个支持中文的系统字体。"""
    if sys.platform == "win32" or sys.platform == "darwin":
        return None  # Windows/macOS 直接走 subset 回退
    preferred = [
        "HarmonyOS Sans SC",
        "LXGW WenKai",
        "Noto Sans CJK SC",
        "Source Han Sans CN",
        "WenQuanYi Zen Hei",
    ]
    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "family"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        available = (
            set(result.stdout.strip().split("\n")) if result.returncode == 0 else set()
        )
    except (OSError, subprocess.TimeoutExpired):
        available = set()
    for name in preferred:
        if any(name in f for f in available):
            return name
    # 兜底：任意一个系统 CJK 字体（优于 subset 回退导致乱码）
    return next(iter(available), None)


def setup_app_font(app: QApplication) -> None:
    """注册 UI 字体并设为应用默认字体。

    RinUI 内部组件在 Linux 上读取 Qt.application.font.family，
    设置后所有 RinUI 控件自动使用该字体，无需逐个覆盖。

    subset 字体仅通过 addApplicationFont 加载到 Qt 内部数据库，
    fontconfig 不感知它。当 Qt 偶尔走 fontconfig 路径解析时，
    subset 的 family name 无法被解析，导致中文全部乱码。
    因此 app 字体必须选用 fontconfig 也能识别的系统 CJK 字体。
    """
    from PySide6.QtGui import QFont, QFontDatabase

    ui_font_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "..",
        "resources",
        "fonts",
        "HarmonyOS_Sans_SC_Regular.ttf",
    )
    # subset 字体仍注册到 Qt 数据库，供字体 Dialog 的 FontLoader 使用
    font_id = QFontDatabase.addApplicationFont(ui_font_path)

    cjk_family = find_system_cjk_font()
    if cjk_family:
        app.setFont(QFont(cjk_family))
    elif font_id != -1:
        # 系统无 CJK 字体时才回退到 subset
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0]))
