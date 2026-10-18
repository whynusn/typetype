"""捕获 Qt/QML 运行时消息（加载失败、绑定环、qWarning 等）。

QML 的「Failed to load component」「Binding loop detected」等都以
Qt 消息形式出现；安装本捕获器后按目标归集，成为报告的结构化部分。

> **真机模式的盲区（实测，务必记住）**：真实客户端在 ``bootstrap()`` 第一行
> 就调 ``install_qt_message_handler()``，把 ``qInstallMessageHandler`` 换成了
> 它自己的 handler——**先装再 bootstrap 等于全程失聪**，app_run 会报
> "0 警告"的假阴性（真机上其实有 QML 警告）。两条措施补全覆盖：
>
> 1. bootstrap 期间挂 **logging sink**：app 的 handler 把 Qt 消息转成
>    ``[Qt:category] message`` 记进 ``src.backend.utils.logger``，挂在这个
>    **具名 logger** 上即可精确捞到 Qt 消息，不掺入业务日志。
> 2. bootstrap 之后 ``reinstall()`` 把 Qt handler 抢回来，并**转发**给 app 的
>    handler（保证 app.log 照旧记录，不破坏被验对象的行为）。
>
> 两个通道时段不重叠，因此不会重复计数。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

# app 把 Qt 消息路由进的具名 logger（src/backend/utils/logger.py）
_QT_BRIDGE_LOGGER = "src.backend.utils.logger"

# QML 警告形如 `file:///a/b.qml:375:5: QML Connections: ...`
_LOCATION = re.compile(r"(file:///[^\s:]+):(\d+):(\d+):")

_SEVERITY = {
    QtMsgType.QtDebugMsg: "debug",
    QtMsgType.QtInfoMsg: "info",
    QtMsgType.QtWarningMsg: "warning",
    QtMsgType.QtCriticalMsg: "critical",
    QtMsgType.QtFatalMsg: "fatal",
}

# logging 级别 → 报告口径（与 Qt 严重度对齐：ERROR 对应 critical）
_LOG_SEVERITY = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warning",
    "ERROR": "critical",
    "CRITICAL": "critical",
}


@dataclass
class CapturedMessage:
    severity: str
    category: str
    message: str
    file: str
    line: int


# 离屏平台缺系统字体别名时 Qt 的性能提示（macOS offscreen 必现），与被测 QML 无关
_BENIGN_PREFIXES = (
    "Populating font family aliases took",
    # Windows offscreen 平台走 freetype 字体库，PySide6 wheel 不带 lib/fonts
    "QFontDatabase: Cannot find font directory",
)


# ---- 退出期兜底 ----
#
# 有些 Qt 消息在**进程退出期**才发出（典型：QThread 销毁时仍在运行 →
# qFatal → SIGABRT）。那时 Qt message handler 已被卸载/失效，handler 捕获
# 不到，只能从子进程 stderr 里捞。实测这条抓到了真实缺陷（RinUI 主题监听
# 线程没停，客户端每次正常退出都崩）。

_CONSOLE_QT = re.compile(
    r"^\d{2}:\d{2}:\d{2}\s+\[(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s+"
    r"\[Qt:(?P<category>[^\]]*)\]\s+(?P<message>.*)$"
)

# 未经 app handler 转写、Qt 直接打到 stderr 的致命噪声
_RAW_FATAL = (
    "QThread: Destroyed while thread",
    "QObject: Cannot create children for a parent that is in a different thread",
)

_LOG_SEVERITY_EXIT = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warning",
    "ERROR": "critical",
    "CRITICAL": "critical",
}


def parse_exit_messages(stderr: str) -> list[CapturedMessage]:
    """从子进程 stderr 里还原退出期的 Qt 消息。"""
    found: list[CapturedMessage] = []
    for line in (stderr or "").splitlines():
        match = _CONSOLE_QT.match(line.strip())
        if match:
            found.append(
                CapturedMessage(
                    severity=_LOG_SEVERITY_EXIT.get(match.group("level"), "warning"),
                    category=match.group("category"),
                    message=match.group("message"),
                    file="<exit>",
                    line=0,
                )
            )
            continue
        if any(token in line for token in _RAW_FATAL):
            found.append(
                CapturedMessage(
                    severity="critical",
                    category="qt",
                    message=line.strip(),
                    file="<exit>",
                    line=0,
                )
            )
    return found


class MessageCollector:
    """Qt 消息捕获器。install/uninstall 成对使用。"""

    def __init__(self) -> None:
        self.messages: list[CapturedMessage] = []
        self._previous = None
        self._forward = False
        self._installed = False
        self._sink: logging.Handler | None = None

    # ---------- 采集 ----------

    def _record(self, severity: str, category: str, message: str, file: str, line: int):
        if message.startswith(_BENIGN_PREFIXES):
            return
        self.messages.append(
            CapturedMessage(
                severity=severity,
                category=category,
                message=message,
                file=file,
                line=line,
            )
        )

    def _handler(self, mode, context, message) -> None:
        self._record(
            _SEVERITY.get(mode, str(mode)),
            str(getattr(context, "category", "")),
            str(message),
            str(getattr(context, "file", "")),
            int(getattr(context, "line", 0) or 0),
        )
        if self._forward and callable(self._previous):
            self._previous(mode, context, message)

    def _from_log_record(self, record: logging.LogRecord) -> None:
        """从 app 的 logging 记录还原 Qt 消息（bootstrap 期的唯一通道）。"""
        try:
            message = record.getMessage()
        except Exception:
            return
        category = ""
        if message.startswith("[Qt:"):
            head, _, message = message.partition("] ")
            category = head.removeprefix("[Qt:") or ""
        file, line = "", 0
        match = _LOCATION.search(message)
        if match:
            file, line = match.group(1).removeprefix("file://"), int(match.group(2))
        self._record(
            _LOG_SEVERITY.get(record.levelname, record.levelname.lower()),
            category,
            message,
            file,
            line,
        )

    # ---------- 安装 ----------

    def install(self, forward: bool = True) -> None:
        self._previous = qInstallMessageHandler(self._handler)
        self._forward = forward and callable(self._previous)
        self._installed = True

    def reinstall(self, forward: bool = True) -> None:
        """重新夺回 Qt handler（被验 app 装了自己的 handler 时用）。

        典型顺序：install() → bootstrap()（app 顶掉我们）→ reinstall()。
        """
        previous = qInstallMessageHandler(self._handler)
        if forward and callable(previous):
            self._previous = previous
            self._forward = True
        self._installed = True

    def attach_log_sink(self) -> None:
        """挂 logging sink，捞 app handler 转写出来的 Qt 消息。"""
        if self._sink is not None:
            return

        class _Sink(logging.Handler):
            def __init__(self, collector: MessageCollector) -> None:
                super().__init__()
                self._collector = collector

            def emit(self, record: logging.LogRecord) -> None:
                self._collector._from_log_record(record)

        self._sink = _Sink(self)
        logging.getLogger(_QT_BRIDGE_LOGGER).addHandler(self._sink)

    def detach_log_sink(self) -> None:
        if self._sink is None:
            return
        logging.getLogger(_QT_BRIDGE_LOGGER).removeHandler(self._sink)
        self._sink = None

    def uninstall(self) -> None:
        self.detach_log_sink()
        if self._installed:
            qInstallMessageHandler(self._previous)
            self._previous = None
            self._forward = False
            self._installed = False

    def __enter__(self) -> "MessageCollector":
        self.install()
        return self

    def __exit__(self, *exc) -> None:
        self.uninstall()
