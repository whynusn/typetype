import os
import platform
import subprocess
from typing import Tuple


class SystemIdentyfier:
    def get_system_info(self) -> Tuple[str, str]:
        """
        返回: (操作系统, 显示服务器类型)
        例如: ('Linux', 'Wayland')
        """

        # 1. 检测操作系统
        os_name = platform.system()
        if os_name == "Linux":
            os_name = "Linux"
        elif os_name == "Windows":
            return ("Windows", "N/A")
        elif os_name == "Darwin":
            return ("macOS", "N/A")

        # 2. 如果是 Linux，检测显示服务器
        display_server = "Unknown"

        # 方法优先级: 环境变量 > 系统命令

        # 检查环境变量
        if "WAYLAND_DISPLAY" in os.environ:
            display_server = "Wayland"
        elif "DISPLAY" in os.environ:
            # 还需要进一步判断是否通过 XWayland
            session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
            if session_type == "wayland":
                display_server = "Wayland (XWayland)"
            else:
                display_server = "X11"

        # 如果环境变量判断不清，使用命令行工具
        if display_server == "Unknown":
            try:
                result = subprocess.run(
                    [
                        "loginctl",
                        "show-session",
                        os.environ.get("XDG_SESSION_ID", ""),
                        "-p",
                        "Type",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    session_type = result.stdout.strip().split("=")[-1].lower()
                    if session_type == "wayland":
                        display_server = "Wayland"
                    elif session_type == "x11":
                        display_server = "X11"
            except Exception:
                pass

        return (os_name, display_server)
