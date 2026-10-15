"""P1.3 真机门禁：真实 typetype 客户端（真 Bridge/真配置/真数据）离屏启动验收。

与 mock 冒烟互补——mock 保真度覆盖不到的真实问题在此暴露：真实数据形状、
真实异步链路、真实布局。子进程隔离（Qt 不进主测试进程），并用临时 HOME +
XDG_* 隔离用户数据（夹具与 env 构造见 `conftest.py` / `tools/ui_probe/env.py`）。
"""


def test_real_client_boots_without_qml_errors(app_run_report):
    """真实客户端启动不得有 QML 错误/警告/绑定环。"""
    summary = app_run_report["summary"]
    noisy = [
        m
        for m in app_run_report["messages"]
        if m["severity"] in ("warning", "critical", "fatal")
    ]
    assert not noisy, "真实客户端产生 QML 告警:\n" + "\n".join(
        f"  [{m['severity']}] {m['message']}" for m in noisy
    )
    assert summary["binding_loops"] == 0


def test_real_client_window_renders_content(app_run_report):
    """窗口必须真的长出界面：空窗口/空树说明主 QML 没起来。"""
    window = app_run_report["window"]
    assert window["title"], "窗口标题为空——主窗口未正确初始化"
    assert window["width"] > 0 and window["height"] > 0

    def count(node) -> int:
        return 1 + sum(count(c) for c in node.get("children", []))

    nodes = count(app_run_report["tree"])
    assert nodes > 200, f"真实窗口仅 {nodes} 个节点，疑似渲染失败或快照遍历回归"
