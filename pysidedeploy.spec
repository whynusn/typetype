[app]
title = typetype
project_dir = .
input_file = main.py
icon = /home/wangyu/work/TypeType.AppDir/typetype.png
exec_directory = .
project_file = pyproject.toml

[python]

# 这里填写项目依赖的第三方 python 包
# 必填，否则报错 attributeerror
# 根据你的代码，你用到了 httpx，crypto (pycryptodome)
packages = PySide6,httpx,pycryptodome
python_path = /home/wangyu/work/typetype/.venv/bin/python

[qt]

# 你的 qml 文件列表
qml_files = qml/LowerPane.qml,qml/Main.qml,qml/ScoreArea.qml,qml/ToolLine.qml,qml/UpperPane.qml,qml/AppText.qml,qml/HistoryArea.qml

# 排除不需要的 qml 插件
excluded_qml_plugins = QtCharts,QtSensors,QtWebEngine

# 你只需要这些 qt 模块
modules = Core,DBus,Gui,Network,OpenGL,Qml,QmlMeta,QmlModels,QmlWorkerScript,Quick

# 【关键】plugins 列表里必须包含 qml，否则 qtquick/controls 会找不到
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,networkaccess,networkinformation,platforminputcontexts,platforms,platformthemes,qmllint,qmltooling,scenegraph,tls,xcbglintegrations,qml

[nuitka]

# 【强烈建议】先改成 onedir，这样打包更快、更稳定
mode = standalone

# 如果你想完全排除 webengine/pdf 相关的库，可以加这一行（可选）
extra_args = --noinclude-dlls=libQt6WebEngine* --noinclude-dlls=libQt6Pdf* --noinclude-qt-translations

