"""ui-probe — Qt/QML 前端验收 harness（AI-agent 亲和）。

寄居于 typetype 仓（ADR-015），核心按通用设计：

- ``bridge_introspect`` 解析 bridge.py 的 QML 可见 API 面
- ``mock_bridge`` 由 API 面自动生成 mock bridge QML（离屏加载的替身）
- ``message_capture`` 捕获 Qt/QML 消息（加载失败、绑定环、qWarning）
- ``loader`` 离屏环境装配 + 组件加载
- ``report`` 结构化报告（JSON，AI agent 的唯一消费接口）
- ``smoke`` P0 冒烟运行器（CLI + pytest 入口）
"""

__version__ = "0.1.0"
