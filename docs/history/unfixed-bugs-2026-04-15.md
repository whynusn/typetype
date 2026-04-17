# TypeType 未修复 Bug 详细记录

**日期**: 2026-04-15
**最后更新**: 2026-04-16（代码状态校验）
**状态**: 3 个问题均未修复，已尝试多种方案均被用户确认无效

---

## 问题 1: ToolLine 按钮完全不显示

**现象**: TypingPage 顶部的 ToolLine 组件（载文、剪贴板载文、重打、排行榜按钮）全部不可见。

**已尝试的修复**（均无效）:
1. ~~RinUI Button.qml 中移除 `font: text.font` 绑定~~（commit 168d00a 已执行，仍无效）
2. 将 ToolLine.qml 根组件从 QtQuick.Controls `Pane` 改为 RinUI `Frame`
3. 移除自定义 `background`，改用 Frame 自带属性（padding, radius, color, borderColor）
4. 清除 `/home/wangyu/.cache/main.py/qmlcache/` 目录
5. 清除 Python `__pycache__`

**当前代码状态**（2026-04-16 校验）:
- `Button.qml`: `font: text.font` 绑定已移除（commit 168d00a）
- `ToolLine.qml`: 根组件已恢复为 QtQuick.Controls `Pane`（padding: 8），内部使用 `Row`（非 RowLayout）

**可能的真正根因**: RinUI 组件的类型加载顺序导致 Button 组件解析失败；或 Pane 的尺寸策略与 RinUI 主题冲突。

**关键文件**: `src/qml/typing/ToolLine.qml`, `RinUI/components/BasicInput/Button.qml`

---

## 问题 2: 文本排行页面 ComboBox 为空

**现象**: TextLeaderboardPage 左侧的文本来源 ComboBox 没有任何选项。

**已尝试的修复**（均无效）:
1. `StackView.onActivated` 中用 `Qt.callLater` 延迟调用 `loadCatalog()`
2. 将 `onCatalogLoaded` 的 Connections 从 `enabled: StackView.status === StackView.Active` 改为无守卫
3. LeaderboardAdapter 添加 catalog 缓存机制

**当前代码状态**:
- TextLeaderboardPage.qml: `StackView.onActivated` 中 `Qt.callLater(appBridge.loadCatalog)`
- catalog Connections 无 StackView.status 守卫
- leaderboardAdapter 的 loadCatalog 有缓存逻辑

**可能的真正根因**: `Qt.callLater` 后 StackView.status 的 binding re-evaluation 仍可能未完成；或者 Bridge 的 `catalogLoaded` 信号根本没有发出（leaderboard_adapter 的 loadCatalog 可能因为 Port/Gateway 问题静默失败）。

**关键文件**: `src/qml/pages/TextLeaderboardPage.qml`, `src/backend/presentation/adapters/leaderboard_adapter.py`, `src/backend/presentation/bridge.py`

---

## 问题 3: 排行榜日期列不显示

**现象**: 排行榜列表中"日期"列全部显示为 "-"。

**已尝试的修复**（无效）:
1. 在 `leaderboard_fetcher.py` 中添加 `_normalize_leaderboard_dates()` 将 Jackson 可能序列化的数组格式 `[yyyy,MM,dd,HH,mm,ss]` 转为 ISO 字符串

**服务端信息**:
- Spring Boot 3.2.5, Jackson 2.15.4
- `jackson-module-jsr310` 在 classpath 上
- LeaderboardVO 的 `createdAt` 字段为 `LocalDateTime`
- SQL 中 `s.created_at AS createdAt`
- MyBatis `map-underscore-to-camel-case: true`

**可能的真正根因**: 可能不是序列化格式问题，而是服务端的 `createdAt` 字段实际为 null，或者 JSON 字段名不匹配。

**关键文件**: `src/backend/integration/leaderboard_fetcher.py`, `src/qml/pages/TextLeaderboardPage.qml` (formatDate 函数), 服务端 `LeaderboardVO.java`, `ScoreMapper.java`

---

## 架构修复（已完成）

以下修复已由 subagent 完成，代码正确：
- 创建 `LeaderboardProvider` Port 协议
- `LeaderboardGateway` 依赖 Port 而非具体实现
- `main.py` 注入逻辑更新
- 28 个新测试全部通过

---

## 调试建议

下次排查时应该：
1. 在运行的客户端中添加 `console.log` 输出，确认关键信号是否发出和接收
2. 检查服务端 API 实际返回的 JSON 格式（特别是 leaderboard 的 createdAt 字段）
3. 考虑使用 codebuddy (glm5.1) 从全新视角分析问题

## codebuddy 信息

- 路径: `/home/wangyu/.local/share/fnm/node-versions/v20.19.5/installation/bin/codebuddy`
- 包: `@tencent-ai/codebuddy-code`
- 支持 `-p --print` 非交互模式
- 需要进一步探索其 headless/ACP 调用方式
