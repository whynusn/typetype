import os  # 引入 os 模块来处理路径
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import rc_resources  # noqa: F401  # 导入以注册 Qt 资源
from src.backend import text_properties  # noqa: F401  # 在此导入才能在 qml 中使用
from src.backend.backend import Backend
from src.backend.global_key_listener import GlobalKeyListener
from src.backend.system_identifier import SystemIdentifier


def main():
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    system_identifier = SystemIdentifier()
    os_type, display_server = system_identifier.get_system_info()
    print("系统:", os_type, "平台:", display_server)

    # 监听器
    key_listener = None
    if os_type == "Linux" and display_server == "Wayland":
        key_listener = GlobalKeyListener()
        key_listener.start()
        print("因系统平台特殊性，全局监听器已启动")

    # 创建 Backend，并传入监听器
    backend = Backend(key_listener)

    # 暴露 Backend 到 QML（用单例模式）
    engine.rootContext().setContextProperty("backend", backend)

    # 获取当前文件所在路径
    current_path = os.path.dirname(os.path.abspath(__file__))

    # 将 QML 文件所在目录添加到导入路径 (如果你在 QML 里 import 其他自定义模块)
    engine.addImportPath(current_path)

    # 拼接出 Main.qml 的绝对文件路径
    # 注意：通常只需要加载入口文件 (Main.qml)，不需要另外加载 UpperPane 和 LowerPane
    # 因为 Main.qml 内部应该会引用它们。
    main_qml_path = os.path.join(current_path, "src", "qml", "Main.qml")

    print(f"Loading QML from: {main_qml_path}")  # 打印一下方便调试

    # 使用 load 加载文件路径，而不是 loadFromModule
    engine.load(main_qml_path)

    # --------------------

    # 错误处理
    if not engine.rootObjects():
        sys.exit(-1)

    # 清理资源并退出
    exit_code = app.exec()
    if key_listener:
        key_listener.stop()  # 立即生效，无需 wait
    del engine
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
