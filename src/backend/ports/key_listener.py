"""全局键盘监听器协议。

定义全局键盘事件的抽象接口，供集成层实现。
主要用于 Wayland 平台下 evdev 监听退格/击键事件。
"""

from __future__ import annotations

from typing import Any, Protocol


class KeyListener(Protocol):
    """全局键盘监听器协议。

    实现类：
    - integration.global_key_listener.GlobalKeyListener: Wayland evdev 实现
    """

    def start(self) -> None:
        """启动监听。"""
        ...

    def stop(self) -> None:
        """停止监听。"""
        ...

    def get_all_devices(self) -> list[dict[str, Any]]:
        """获取所有可用输入设备（用于 UI 展示）。

        Returns:
            [{"path": str, "name": str, "type": str, "is_keyboard": bool}, ...]
        """
        ...

    def get_selected_device_paths(self) -> list[str]:
        """读取手动选择的设备路径。"""
        ...

    def set_selected_device_paths(self, paths: list[str]) -> None:
        """保存手动选择的设备路径。"""
        ...

    def has_selected_devices(self) -> bool:
        """是否已配置手动设备选择。"""
        ...

    def get_active_device_paths(self) -> list[str]:
        """返回当前正在监听的设备路径列表。"""
        ...

    def restart_with_selection(self, paths: list[str]) -> None:
        """停止当前监听并使用指定设备重新启动。"""
        ...

    def restart_auto_detect(self) -> None:
        """停止当前监听并恢复自动发现。"""
        ...
