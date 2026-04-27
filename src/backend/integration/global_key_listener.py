"""全局键盘监听器（evdev 实现）。

职责：
- 自动发现键盘输入设备（严格/宽松两阶段扫描）
- 支持手动设备选择（QSettings 持久化）
- 将 evdev 按键事件转为 Qt 信号
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QSettings, QSocketNotifier, Signal

from ..ports.key_codes import KeyCodes
from ..utils.logger import log_debug, log_error, log_info


class GlobalKeyListener(QObject):
    keyPressed = Signal(int, str)  # (按键码, 设备名)

    SETTINGS_KEY = "key_listener/device_paths"
    STRICT_SCAN = "strict"
    PERMISSIVE_SCAN = "permissive"

    def __init__(self):
        super().__init__()
        try:
            from evdev import InputDevice, ecodes, list_devices

            self.InputDevice = InputDevice
            self.ecodes = ecodes
            self.list_devices = list_devices
        except ImportError:
            log_error(
                "Error: evdev library not found. This module only works on Linux."
            )
            raise

        self.devices: list[Any] = []
        self.notifiers: list[QSocketNotifier] = []
        self._pressed_shortcut_modifiers: dict[int, set[int]] = {}

    # ==========================================
    # 设备识别
    # ==========================================

    def _is_keyboard_strict(self, device) -> bool:
        """严格模式：标准键盘识别。

        排除条件（可能误杀蓝牙键盘）：
        - EV_REL (鼠标) → 排除
        - EV_ABS (触摸板/手柄/带触摸条的键盘) → 排除
        """
        caps = device.capabilities()

        if self.ecodes.EV_KEY not in caps:
            return False
        if self.ecodes.EV_REL in caps:
            return False
        if self.ecodes.EV_ABS in caps:
            return False

        keys = caps[self.ecodes.EV_KEY]
        return any(k < 256 for k in keys)

    def _is_keyboard_permissive(self, device) -> bool:
        """宽松模式：放宽条件以适应蓝牙键盘、带触摸条的键盘等。

        仅排除：
        - EV_REL (鼠标) — 有鼠标功能的设备不可能是纯键盘
        - 没有任何标准键盘键码的设备
        """
        caps = device.capabilities()

        if self.ecodes.EV_KEY not in caps:
            return False
        # 排除鼠标：有相对位移的设备
        if self.ecodes.EV_REL in caps:
            return False

        keys = caps[self.ecodes.EV_KEY]
        return any(k < 256 for k in keys)

    def _classify_device(self, device) -> str:
        """分类设备类型（用于诊断日志和 UI 展示）。"""
        caps = device.capabilities()

        if self.ecodes.EV_KEY not in caps:
            return "non-keyboard"

        has_rel = self.ecodes.EV_REL in caps
        has_abs = self.ecodes.EV_ABS in caps
        keys = caps.get(self.ecodes.EV_KEY, [])
        has_keyboard_keys = any(k < 256 for k in keys)

        if has_rel and has_keyboard_keys:
            # 部分键盘带鼠标功能（罕见）
            return "keyboard" if not has_abs else "ambiguous"
        if has_rel:
            return "mouse"
        if has_abs and not has_keyboard_keys:
            return "touchpad/gamepad"
        if has_abs and has_keyboard_keys:
            # 带触摸条的键盘（如某些蓝牙键盘）
            return "keyboard"
        if has_keyboard_keys:
            return "keyboard"
        return "unknown"

    def get_all_devices(self) -> list[dict[str, Any]]:
        """获取所有可用输入设备（用于 UI 展示）。

        Returns:
            [{"path": str, "name": str, "type": str, "is_keyboard": bool}, ...]
        """
        devices = []
        for path in self.list_devices():
            try:
                device = self.InputDevice(path)
                device_type = self._classify_device(device)
                devices.append({
                    "path": path,
                    "name": device.name,
                    "type": device_type,
                    "is_keyboard": device_type == "keyboard",
                })
                device.close()
            except Exception as exc:
                log_debug(f"无法读取设备 {path}: {exc}")
        return devices

    # ==========================================
    # 自动发现
    # ==========================================

    def _find_all_keyboards(self) -> list[Any]:
        """自动发现键盘设备（两阶段扫描）。

        1. 严格模式：标准键盘（排除 EV_ABS）
        2. 宽松模式：放宽条件（蓝牙键盘、带触摸条的键盘）
        """
        # 阶段一：严格扫描
        strict_keyboards = self._scan_with(self._is_keyboard_strict)
        if strict_keyboards:
            log_info(
                f"严格模式发现 {len(strict_keyboards)} 个键盘"
            )
            return strict_keyboards

        # 阶段二：宽松扫描（严格模式未找到时回退）
        log_info("严格模式未发现键盘，切换到宽松模式...")
        permissive_keyboards = self._scan_with(self._is_keyboard_permissive)
        if permissive_keyboards:
            log_info(
                f"宽松模式发现 {len(permissive_keyboards)} 个键盘"
            )
            return permissive_keyboards

        return []

    def _scan_with(self, predicate) -> list[Any]:
        """用指定谓词扫描所有输入设备。"""
        found = []
        for path in self.list_devices():
            try:
                device = self.InputDevice(path)
                if predicate(device):
                    found.append(device)
                    log_info(f"发现键盘: {device.name} ({path})")
                else:
                    device.close()
            except Exception as exc:
                log_debug(f"扫描设备 {path} 时出错: {exc}")
        return found

    # ==========================================
    # 手动设备选择
    # ==========================================

    def get_selected_device_paths(self) -> list[str]:
        """从 QSettings 读取手动选择的设备路径。"""
        settings = QSettings()
        count = settings.beginReadArray(self.SETTINGS_KEY)
        paths = []
        for i in range(count):
            settings.setArrayIndex(i)
            path = settings.value("path", "")
            if path:
                paths.append(path)
        settings.endArray()
        return paths

    def set_selected_device_paths(self, paths: list[str]) -> None:
        """保存手动选择的设备路径到 QSettings。"""
        settings = QSettings()
        settings.beginWriteArray(self.SETTINGS_KEY)
        for i, path in enumerate(paths):
            settings.setArrayIndex(i)
            settings.setValue("path", path)
        settings.endArray()
        settings.sync()

    def clear_selected_device_paths(self) -> None:
        """清除手动设备选择（恢复到自动发现）。"""
        settings = QSettings()
        settings.beginWriteArray(self.SETTINGS_KEY)
        settings.remove("")  # 清空整个数组
        settings.endArray()

    def has_selected_devices(self) -> bool:
        """是否已配置手动设备选择。"""
        return bool(self.get_selected_device_paths())

    def get_active_device_paths(self) -> list[str]:
        """返回当前正在监听的设备路径。"""
        return [
            d.path for d in self.devices
            if hasattr(d, "path") and d.path
        ]

    def _open_selected_devices(self, paths: list[str]) -> list[Any]:
        """打开指定路径的 evdev 设备。"""
        devices = []
        for path in paths:
            try:
                device = self.InputDevice(path)
                devices.append(device)
                log_info(f"手动选择设备: {device.name} ({path})")
            except Exception as exc:
                log_error(f"无法打开设备 {path}: {exc}")
        return devices

    # ==========================================
    # 生命周期
    # ==========================================

    def start(self) -> None:
        """启动监听。优先使用手动选择的设备，否则自动发现。"""
        # 1. 尝试手动选择
        selected_paths = self.get_selected_device_paths()
        if selected_paths:
            log_info("检测到手动设备配置，尝试打开...")
            self.devices = self._open_selected_devices(selected_paths)

        # 2. 手动设备打开失败或未配置 → 自动发现
        if not self.devices:
            log_info("自动发现键盘设备...")
            self.devices = self._find_all_keyboards()

        # 3. 仍未找到 → 诊断信息并报错
        if not self.devices:
            all_devices = self.get_all_devices()
            log_info("系统输入设备列表:")
            for d in all_devices:
                log_info(f"  {d['path']}: {d['name']} ({d['type']})")
            raise RuntimeError(
                "未找到可访问的键盘输入设备。\n"
                "可能的原因：\n"
                "1. 当前用户不在 input 组，无法读取 /dev/input/event* — "
                "尝试: sudo usermod -a -G input $USER && 重新登录\n"
                "2. 蓝牙键盘未配对或未连接\n"
                "3. 在设置页中手动选择设备"
            )

        # 4. 注册 socket notifier
        for device in self.devices:
            notifier = QSocketNotifier(device.fd, QSocketNotifier.Read)
            notifier.activated.connect(self.make_handler(device))
            self.notifiers.append(notifier)

    def make_handler(self, dev):
        return lambda: self._handle_events(dev)

    def stop(self) -> None:
        """停止监听。"""
        log_info("正在停止监听器...")
        for notifier in self.notifiers:
            if notifier:
                notifier.setEnabled(False)
                notifier.deleteLater()

        for device in self.devices:
            if device:
                device.close()

        self.notifiers.clear()
        self.devices.clear()
        self._pressed_shortcut_modifiers.clear()
        log_info("监听器已停止")

    def restart_with_selection(self, paths: list[str]) -> None:
        """停止当前监听并使用指定设备重新启动。"""
        self.stop()
        self.set_selected_device_paths(paths)
        self.start()

    def restart_auto_detect(self) -> None:
        """停止当前监听并恢复自动发现。"""
        self.stop()
        self.clear_selected_device_paths()
        self.start()

    # ==========================================
    # 事件处理
    # ==========================================

    def _handle_events(self, device):
        try:
            for event in device.read():
                if event.type != self.ecodes.EV_KEY:
                    continue

                self._update_shortcut_modifier_state(device, event.code, event.value)
                if event.value not in (1, 2):
                    continue

                if self._should_ignore_shortcut_key(device, event.code):
                    continue

                self.keyPressed.emit(event.code, device.name)
        except BlockingIOError:
            pass

    @staticmethod
    def _device_id(device: Any) -> int:
        return getattr(device, "fd", id(device))

    def _update_shortcut_modifier_state(
        self,
        device: Any,
        key_code: int,
        value: int,
    ) -> None:
        if not KeyCodes.is_shortcut_modifier(key_code):
            return

        device_id = self._device_id(device)
        pressed_modifiers = self._pressed_shortcut_modifiers.setdefault(
            device_id,
            set(),
        )
        if value in (1, 2):
            pressed_modifiers.add(key_code)
        elif value == 0:
            pressed_modifiers.discard(key_code)
            if not pressed_modifiers:
                self._pressed_shortcut_modifiers.pop(device_id, None)

    def _should_ignore_shortcut_key(self, device: Any, key_code: int) -> bool:
        if KeyCodes.is_shortcut_modifier(key_code) or KeyCodes.is_backspace(key_code):
            return False

        return bool(self._pressed_shortcut_modifiers.get(self._device_id(device)))
