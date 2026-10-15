"""离屏交互原语（ADR-015 P1.2）。

用 **Qt 事件注入**驱动界面，而不是直接改属性——交互链路（焦点、按键分发、
输入法提交、onTextChanged、Bridge 往返）都要走到，否则测的是"赋值"，
不是"打字"。

三类注入，语义分明：

- ``type(mode=ime)``：``QInputMethodEvent`` 提交串。中文输入的实际路径
  （拼音上屏），也是最稳的一条。
- ``type(mode=key)``：逐字符 ``QKeyEvent``（``Qt.Key_unknown`` + text）。
  英文/符号路径。
- ``type(mode=set)``：直接写 ``text`` 属性。**只用于构造前置状态**——
  它绕过了交互链路，场景里应显式标注，别拿它冒充打字。

``key`` 走特殊键（Return / Backspace / F2 / …），``click`` 走鼠标事件。

> 实测（PySide6 6.x）：``QTest.keyClicks`` **只绑了 QWidget 重载**，
> 传 QQuickWindow 直接 TypeError——必须自己造事件。
"""

from __future__ import annotations

import time

from PySide6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QEvent,
    QEventLoop,
    QMetaObject,
    QObject,
    QPointF,
    Qt,
)
from PySide6.QtGui import QInputMethodEvent, QKeyEvent, QMouseEvent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication

from .selector import Selector, describe_node, resolve_one

_QT_KEY_PREFIXES = ("Key_",)


def resolve_key(name: str) -> Qt.Key:
    """把场景里的键名解析成 Qt.Key（``Return`` / ``Key_Return`` 皆可）。"""
    if isinstance(name, int):
        return Qt.Key(name)
    for candidate in (name, *(p + name for p in _QT_KEY_PREFIXES)):
        key = getattr(Qt.Key, candidate, None)
        if key is not None:
            return key
    raise ValueError(
        f"未知键名 {name!r}（应为 Qt.Key_* 名，如 Return / F2 / Backspace）"
    )


def resolve_modifiers(names: list[str] | None) -> Qt.KeyboardModifier:
    result = Qt.KeyboardModifier.NoModifier
    for name in names or []:
        for candidate in (name, name + "Modifier"):
            mod = getattr(Qt.KeyboardModifier, candidate, None)
            if mod is not None:
                result |= mod
                break
        else:
            raise ValueError(f"未知修饰键 {name!r}")
    return result


def invoke_callable(obj: QObject, name: str, args: list):
    """调用对象上的方法：Python @Slot 走属性，QML JS 函数走 invokeMethod。

    两条路径是实测逼出来的：

    - Python 侧 QObject（Bridge）的方法就是 Python 方法，``getattr`` 直接调，
      返回值是原生类型，便于断言。
    - QML 定义的 JS 函数**没有 Python 属性**，只出现在 metaObject 上，且参数
      声明为 ``QVariant``——必须走 ``QMetaObject.invokeMethod``。PySide6 里
      ``Q_ARG``/``Q_RETURN_ARG`` 只吃**一个**参数（类型名），且没有 ``QVariant``
      类型对象，只能传字符串 ``"QVariant"``；返回值由 invokeMethod 直接给出。
    """
    py_attr = getattr(obj, name, None)
    if py_attr is not None and callable(py_attr):
        return py_attr(*args)

    def method_name(candidate) -> str:
        raw = candidate.name()
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    meta = obj.metaObject()
    candidates = [
        meta.method(i)
        for i in range(meta.methodCount())
        if method_name(meta.method(i)) == name
    ]
    if not candidates:
        raise AttributeError(f"{meta.className()} 上没有方法 {name}")
    method = next(
        (c for c in candidates if c.parameterCount() == len(args)), candidates[0]
    )
    args = args[: method.parameterCount()]
    generic_args = [Q_ARG("QVariant", value) for value in args]
    return QMetaObject.invokeMethod(
        obj,
        name,
        Qt.ConnectionType.DirectConnection,
        Q_RETURN_ARG("QVariant"),
        *generic_args,
    )


class Driver:
    """在活动对象树上执行交互。component / app 双模式共用。"""

    def __init__(
        self,
        app: QApplication,
        root: QObject,
        window: QQuickWindow | None = None,
        context_getter=None,
    ) -> None:
        self.app = app
        self.root = root
        self.window = window
        self._context_getter = context_getter

    # ---------- 基础 ----------

    def pump(self, ms: int = 100) -> None:
        """跑一段事件循环：定时器/异步 worker/延迟绑定都靠它落地。"""
        deadline = time.monotonic() + ms / 1000.0
        while time.monotonic() < deadline:
            self.app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            time.sleep(0.005)

    def find(self, selector: Selector) -> QObject:
        """定位节点：context 选择器取上下文对象，否则在对象树里找。"""
        if selector.context:
            obj = (
                self._context_getter(selector.context) if self._context_getter else None
            )
            if obj is None:
                raise LookupError(f"上下文对象不存在：{selector.context}")
            return obj
        obj, _ = resolve_one(self.root, selector)
        return obj

    def locate(self, selector: Selector) -> tuple[QObject, dict]:
        obj = self.find(selector)
        _, path = (
            resolve_one(self.root, selector) if not selector.context else (obj, "")
        )
        return obj, describe_node(obj, path if path else "context")

    # ---------- 交互 ----------

    def click(self, selector: Selector) -> dict:
        obj, info = self.locate(selector)
        target: QObject = self.window if self.window is not None else obj
        if isinstance(obj, QQuickItem):
            obj.forceActiveFocus()
            local = QPointF(obj.width() / 2, obj.height() / 2)
            scene = obj.mapToScene(local)
            for qtype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                event = QMouseEvent(
                    qtype,
                    scene,
                    scene,
                    scene,
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                QApplication.sendEvent(target, event)
        self.pump(50)
        return info

    def type_text(self, selector: Selector, text: str, mode: str = "ime") -> dict:
        """注入文本。ime=输入法提交 / key=按键事件 / set=直接赋值。"""
        obj, info = self.locate(selector)
        if mode == "set":
            obj.setProperty("text", text)
            self.pump(30)
            return info

        if isinstance(obj, QQuickItem):
            obj.forceActiveFocus()
            self.pump(20)
        target: QObject = self.window if self.window is not None else obj

        if mode == "ime":
            event = QInputMethodEvent()
            event.setCommitString(text)
            QApplication.sendEvent(target, event)
        elif mode == "key":
            for ch in text:
                for qtype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                    event = QKeyEvent(
                        qtype,
                        Qt.Key.Key_unknown,
                        Qt.KeyboardModifier.NoModifier,
                        ch,
                    )
                    QApplication.sendEvent(target, event)
        else:
            raise ValueError(f"未知 type 模式 {mode!r}（可用：ime / key / set）")
        self.pump(50)
        return info

    def press_key(self, key: str, modifiers: list[str] | None = None) -> dict:
        """按一个特殊键（Return / Backspace / F2 / …）。"""
        qt_key = resolve_key(key)
        mods = resolve_modifiers(modifiers)
        target: QObject = self.window if self.window is not None else self.root
        for qtype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            event = QKeyEvent(qtype, qt_key, mods)
            QApplication.sendEvent(target, event)
        self.pump(50)
        return {"key": key, "modifiers": modifiers or []}

    def call(self, selector: Selector, method: str, args: list | None = None) -> object:
        obj = self.find(selector)
        result = invoke_callable(obj, method, list(args or []))
        self.pump(50)
        return result

    def set_prop(self, selector: Selector, name: str, value) -> None:
        obj = self.find(selector)
        if not obj.setProperty(name, value):
            raise AttributeError(f"属性 {name} 写入失败（{describe_node(obj, '')}）")
        self.pump(30)
