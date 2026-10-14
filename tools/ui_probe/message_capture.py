"""捕获 Qt/QML 运行时消息（加载失败、绑定环、qWarning 等）。

QML 的「Failed to load component」「Binding loop detected」等都以
Qt 消息形式出现；安装本捕获器后按目标归集，成为报告的结构化部分。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QtMsgType, qInstallMessageHandler


_SEVERITY = {
    QtMsgType.QtDebugMsg: "debug",
    QtMsgType.QtInfoMsg: "info",
    QtMsgType.QtWarningMsg: "warning",
    QtMsgType.QtCriticalMsg: "critical",
    QtMsgType.QtFatalMsg: "fatal",
}


@dataclass
class CapturedMessage:
    severity: str
    category: str
    message: str
    file: str
    line: int


class MessageCollector:
    """qInstallMessageHandler 捕获器；install/uninstall 成对使用。"""

    def __init__(self) -> None:
        self.messages: list[CapturedMessage] = []
        self._previous = None
        self._installed = False

    def _handler(self, mode, context, message) -> None:
        self.messages.append(
            CapturedMessage(
                severity=_SEVERITY.get(mode, str(mode)),
                category=str(getattr(context, "category", "")),
                message=str(message),
                file=str(getattr(context, "file", "")),
                line=int(getattr(context, "line", 0) or 0),
            )
        )

    def install(self) -> None:
        if self._installed:
            return
        # 记住前一个 handler：真实 app 装了自己的日志 handler，
        # 卸载时若传 None 会把它丢掉（后续消息不再进项目日志）
        self._previous = qInstallMessageHandler(self._handler)
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        qInstallMessageHandler(self._previous)
        self._previous = None
        self._installed = False

    def __enter__(self) -> "MessageCollector":
        self.install()
        return self

    def __exit__(self, *exc) -> None:
        self.uninstall()
