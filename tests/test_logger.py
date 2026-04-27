import importlib
import logging
import logging.handlers

import src.backend.utils.logger as logger_module
from PySide6.QtCore import QtMsgType, qDebug, qInstallMessageHandler, qWarning


def test_logger_import_survives_file_handler_creation_failure(
    monkeypatch, tmp_path
) -> None:
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()

    class FailingRotatingFileHandler(logging.Handler):
        def __init__(self, *args, **kwargs):
            raise OSError("read-only file system")

    with monkeypatch.context() as context:
        context.setenv("HOME", str(isolated_home))
        context.setattr(
            logging.handlers,
            "RotatingFileHandler",
            FailingRotatingFileHandler,
        )
        reloaded_logger = importlib.reload(logger_module)

        root_logger = logging.getLogger()
        assert any(
            isinstance(handler, logging.StreamHandler)
            for handler in root_logger.handlers
        )

        reloaded_logger.log_warning("logger fallback should stay usable")

    importlib.reload(logger_module)


def test_install_qt_message_handler_routes_qt_logs_to_python_logger(
    monkeypatch,
) -> None:
    messages: list[tuple[int, str]] = []
    previous_handler = qInstallMessageHandler(None)
    previous_installed = logger_module._qt_message_handler_installed

    class DummyLogger:
        def log(self, level: int, message: str) -> None:
            messages.append((level, message))

    try:
        monkeypatch.setattr(logger_module, "_logger", DummyLogger())
        logger_module._qt_message_handler_installed = False

        assert logger_module.install_qt_message_handler() is True

        qDebug("qml debug message")
        qWarning("qml warning message")
    finally:
        qInstallMessageHandler(previous_handler)
        logger_module._qt_message_handler_installed = previous_installed

    assert (logging.DEBUG, "[Qt:default] qml debug message") in messages
    assert (logging.WARNING, "[Qt:default] qml warning message") in messages


def test_qt_message_handler_suppresses_macos_keymapper_mismatch_noise(
    monkeypatch,
) -> None:
    messages: list[tuple[int, str]] = []

    class DummyLogger:
        def log(self, level: int, message: str) -> None:
            messages.append((level, message))

    class Context:
        category = "qt.qpa.keymapper"

    monkeypatch.setattr(logger_module, "_logger", DummyLogger())

    logger_module._qt_message_handler(
        QtMsgType.QtWarningMsg,
        Context(),
        "Mismatch between Cocoa 'r' and Carbon '\\x0' for virtual key 15",
    )

    assert messages == []
