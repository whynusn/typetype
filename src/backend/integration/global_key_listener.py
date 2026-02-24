from PySide6.QtCore import QObject, QSocketNotifier, Signal


class GlobalKeyListener(QObject):  # 继承 QObject 而非 QThread
    keyPressed = Signal(int, str)  # 发送 (按键码, 设备名)

    def __init__(self):
        super().__init__()

        # 只有当这个类被实例化时，才会执行这里的 import
        try:
            from evdev import InputDevice, ecodes, list_devices

            # 将导入的对象绑定到 self 上，这样其他方法就可以通过 self 访问了
            self.InputDevice = InputDevice
            self.ecodes = ecodes
            self.list_devices = list_devices
        except ImportError:
            # 如果在 Linux 下但没装库，或者意外在 Windows 下被实例化了，给出提示
            print("Error: evdev library not found. This module only works on Linux.")
            raise

        self.devices = []  # 存储所有设备
        self.notifiers = []  # 存储所有 notifier

    def _is_keyboard(self, device):
        """识别设备是否为键盘"""
        caps = device.capabilities()

        # 1. 必须支持按键
        if self.ecodes.EV_KEY not in caps:
            return False

        # 2. 排除鼠标：如果有相对位移 (REL_X, REL_Y)，通常是鼠标
        if self.ecodes.EV_REL in caps:
            return False

        # 3. 排除触摸板/手柄：如果有绝对坐标 (ABS_X, ABS_Y)，通常不是纯键盘
        # 注意：极少数带触摸条的键盘可能会触发这个，视情况而定可注释掉这行
        if self.ecodes.EV_ABS in caps:
            return False

        # 4. (进阶) 确认它有真正的键盘按键，而不是只有几个怪按钮
        # 我们检查它是否包含标准键盘区的按键 (例如 KEY_A 到 KEY_Z, 或者 ESC)
        # 键盘的标准键码通常小于 256 (0x100)
        keys = caps[self.ecodes.EV_KEY]
        # 只要有一个典型的键盘键，我们就认为它是键盘
        # 比如 KEY_ESC (1), KEY_1 (2), KEY_Q (16) 等
        # 这里简单判断：如果有小于 256 的键码，且不是单纯只有鼠标键
        has_keyboard_keys = any(k < 256 for k in keys)

        return has_keyboard_keys

    def _find_all_keyboards(self):
        """添加所有键盘设备"""
        keyboards = []
        paths = self.list_devices()
        for path in paths:
            device = self.InputDevice(path)
            # 判断是否为键盘
            if self._is_keyboard(device):
                keyboards.append(device)
                print(f"发现键盘: {device.name} ({path})")
        return keyboards

    def make_handler(self, dev):
        """这个槽函数用来即时返回对应device的事件处理函数, 专门用来抵抗lambda函数的惰性"""
        return lambda: self._handle_events(dev)

    def start(self):
        """启动所有键盘的监听"""
        self.devices = self._find_all_keyboards()

        for device in self.devices:
            notifier = QSocketNotifier(device.fd, QSocketNotifier.Read)
            notifier.activated.connect(
                self.make_handler(device)
            )  # 不直接把lambda作为槽函数是因为lambda函数是惰性的，并不能立即得到对应的device的函数引用, 在调用时总是指向同一个device对象（也就是最后一个）
            self.notifiers.append(notifier)

    def stop(self):
        """立即停止，无需等待"""
        print("正在停止监听器...")
        for notifier in self.notifiers:
            if notifier:
                notifier.setEnabled(False)  # 禁用通知
                notifier.deleteLater()  # 延迟删除
                notifier = None

        for device in self.devices:
            if device:
                device.close()
                device = None
        print("监听器已停止")

    def _handle_events(self, device):
        """统一处理所有设备的按键事件"""
        try:
            for event in device.read():
                if event.type == self.ecodes.EV_KEY and event.value in (1, 2):
                    # 发送信号时附带设备名，方便区分
                    self.keyPressed.emit(event.code, device.name)
        except BlockingIOError:
            # 资源暂时不可用是正常现象，直接忽略
            pass
