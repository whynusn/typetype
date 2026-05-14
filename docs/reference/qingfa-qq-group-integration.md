# 晴发文 QQ 群接入调研
<!-- 状态: active | 最后验证: 2026-05-14 -->

## TypeSunny 现有做法

TypeSunny 的 QQ 群发送能力主要在 `Utils/QQHelper.cs`：

- 通过 Windows `UIAutomationClient` 查找主窗口标题为 `QQ` 的窗口。
- 枚举会话列表，提取群名，缓存群名和 UI 元素。
- 发送时先切到目标群，再把内容写入剪贴板，聚焦 QQ 输入区。
- 新版 QQ 输入区可能是 `Document` 控件，旧版 QQ 可能是 `Edit` 控件，两套路径都做了兼容。
- 找到发送按钮后调用 UIAutomation `InvokePattern`，必要时降级到键盘回车。
- 发文和成绩的组合逻辑在 `MainWindow.xaml.cs`：
  - 有选群：调用 `QQHelper.SendQQMessage` 或 `SendQQMessageD`。
  - 未选群：复制到剪贴板。
  - 晴发文自动下一段时，成绩和下一段发文会合并发送或合并复制。

这条路线强依赖 Windows 桌面 QQ 和 Windows UIAutomation，不能直接复用到 macOS/Linux。

## typetype 可行路径

### 第一阶段：先对齐 TypeSunny 的剪贴板行为

当前已适合先做：

- 晴发文载文完成后复制发文文本。
- 打完后复制成绩。
- 自动下一段时复制“成绩 + 下一段发文”。

这不依赖 QQ 客户端，跨平台稳定，也给后续 QQ 自动发送提供统一消息内容。

### 第二阶段：Windows QQ 自动发送

如果要复刻 TypeSunny，建议新增独立端口：

- `ports/qq_sender.py`
  - `list_groups() -> list[str]`
  - `send_message(group_name: str, content: str) -> None`
  - `send_messages(group_name: str, first: str, second: str) -> None`
- `integration/windows_qq_sender.py`
  - 用 Python UI Automation 库接入 Windows QQ。
  - 可选库：`uiautomation` 或 `pywinauto`。
  - 复刻 TypeSunny 的目标群查找、输入框兼容、发送按钮调用。
- `presentation/adapters/qq_adapter.py`
  - 后台 Worker 枚举群、发送消息，失败回传 UI。

Windows 外的平台默认禁用 QQ 自动发送，只保留复制到剪贴板。

### 第三阶段：macOS 方案需要单独设计

macOS QQ 没有 TypeSunny 那套 UIAutomation。可选方案：

- AppleScript/辅助功能权限驱动 QQ 窗口。
- 只复制到剪贴板，由用户手动粘贴。
- 接入 QQ 机器人/频道开放平台，但这通常不是“本机 QQ 群窗口发送”，需要机器人账号、服务端回调和平台审核。

## 建议

先不要把 QQ 自动发送混进晴发文载文主链路。先把消息格式和复制行为稳定下来，再加一个可选的 `QQSender` 端口。这样 Windows 可以复刻 TypeSunny，macOS/Linux 不会因为 QQ 自动化不可用影响基础跟打。
