"""全局键盘监听器协议。

定义全局键盘事件的抽象接口，供集成层实现。
主要用于 Wayland 平台下 evdev 监听退格/击键事件。
"""

from typing import Protocol


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
