from PySide6.QtCore import Property, QObject, Signal


class Backend(QObject):  # Python 端的 Backend
    # 定义一个属性，QML 可以绑定它
    keyPressed = Signal(int, str)  # 转发信号给 QML
    specialPlatformConfirmed = Signal(bool)  # False为normal, True为special(wayland)

    def __init__(self, key_listener=None):
        super().__init__()
        self._isSpecialPlatform = False

        if key_listener:
            self._isSpecialPlatform = True
            # 连接：监听器信号 → Backend 信号
            key_listener.keyPressed.connect(self.on_key_received)

        self.specialPlatformConfirmed.emit(self._isSpecialPlatform)
        print("[Backend] 检测到平台特殊性:", self._isSpecialPlatform)

    @Property(bool, notify=specialPlatformConfirmed)
    def isSpecialPlatform(self):
        return self._isSpecialPlatform

    def on_key_received(self, keyCode, deviceName):
        """接收按键并处理（可以在这里加逻辑）"""
        print(f"[Backend] 收到按键: {keyCode} from {deviceName}")
        # 转发给 QML
        self.keyPressed.emit(keyCode, deviceName)
