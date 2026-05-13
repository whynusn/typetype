# 更新日志

本文档记录 typetype 项目所有版本的变更。遵循 [Semantic Versioning](https://semver.org/)。

**维护规则**：
- 变更记录按**日期倒序**排列（最新的在前）
- 按版本号分组，每个版本号内按**功能类型分类**（Added/Changed/Fixed/Removed）
- 详细的实现细节应记录在此，架构相关内容通过 `@see ARCHITECTURE.md` 指向
- 请勿在 `ARCHITECTURE.md` 中维护版本历史（该文档专注当前架构事实）

---

## [Unreleased] - In Development

### Changed
- 2026-04-27: 分片载文模式修复：① 清空 UpperPane 文本前先重置光标位置，修复 `QTextCursor::setPosition` 越界警告；② `_color_text` 边界检查加强（`begin_pos + n > doc_len`）；③ 片段切换时重置目标片段达标次数（同一片段重打保留、离开后回来归零），修复第二轮达标次数跨轮累计导致一次达标即自动推进
- 2026-04-26: macOS 兼容：新增 Quartz CGEventTap 全局键盘监听与平台 listener 工厂；配置、字符统计数据库、本地上传文本改为写入用户可写目录，避免打包应用写安装目录
- 2026-04-25: 架构合规修复：① UploadTextAdapter 类型注解从 `integration.TextUploader` 改为 `ports.TextUploader`（消除 Presentation→Integration 违规）；② 新增 `ports/key_listener.py` Protocol，Bridge 类型注解从 `integration.GlobalKeyListener` 改为 `ports.KeyListener`（消除 Bridge→Integration 违规）；③ Bridge 提取 `_clear_text_id()` 方法消除 4 处重复
- 2026-04-24: NavigationView 重构为单实例页面管理：移除 StackView 及 push/pop 动画，改用 `pageInstances` 字典缓存实例，通过 `visible` + `active` 属性切换页面；所有 QML 页面 `Connections.enabled` 守卫从 `StackView.status === StackView.Active` 迁移为 `page.active`；`StackView.onActivating`/`onActivated` 生命周期统一替换为 `onActiveChanged`；`safePop()` 在单实例模式下为空操作（无历史栈）

### Added
- 2026-04-23: Bridge 架构重构：分片载文业务逻辑下沉到 TypingSessionContext，Bridge 瘦身为薄适配层（属性代理/信号转发/Slot 入口）；删除 200+ 行业务逻辑代码
- 2026-04-22: 新增 `TypingSessionContext` 会话状态机：集中管理会话阶段、来源模式、上传资格推导；`TypingAdapter` 新增 setup_* 代理方法；Bridge 新增 uploadStatus/eligibilityReason 属性
- 2026-04-22: 新增配置文件初始化：`main.py` 启动时在 `RuntimeConfig.load_from_file()` 之前执行 `_ensure_config_exists()`，检查 `config/config.json` 是否存在，若不存在则从 `config/config.example.json` 复制创建，确保用户配置持久化到 `config.json` 而非修改 example 文件
- 2026-04-21: 新增服务地址运行时配置链路：SettingsPage 输入框 + 应用按钮 → Bridge.setBaseUrl() → 回调上抛 main._update_base_url() → 统一更新 RuntimeConfig + 5 个 Integration 对象（RemoteTextProvider/ApiClientAuthProvider/ApiClientScoreSubmitter/TextUploader/LeaderboardFetcher）+ 持久化到 config.json；TextAdapter 新增 get_base_url() 代理只读属性
- 2026-04-20: 新增回改/退格统计指标：SessionStat +backspace_count/correction_count，Wayland 通过 evdev KEY_BACKSPACE 检测退格，非 Wayland 通过 QML Keys.onPressed 检测退格，回改通过 textChanged growLength<0 检测
- 2026-04-17: 目录树补全：models/dto（+auth_dto/fetched_text/score_dto）、models/entity（+char_stat/session_stat）、security/（+crypt/secure_storage）、utils/（+logger）

### Fixed
- 2026-04-19: FluentPage `container` 的 anchors 替换为 x/y 属性绑定（消除 ColumnLayout 与 anchors 冲突警告）
- 2026-04-19: 本地文本加载拆分两阶段：`_load_from_local()` 只读文件立即返回（text_id=None），TextAdapter 后台 daemon thread 异步回查服务端 text_id（`lookup_text_id`），通过 `localTextIdResolved` 信号 → Bridge.setTextId() 更新排行榜。修复 `QTimer.singleShot` lambda 静默失败问题，改用 Qt 原生 QueuedConnection 跨线程信号
- 2026-04-16: TextAdapter 移除 `_load_sync`，所有文本加载统一走 Worker（本地来源内含同步 HTTP 回查 `_lookup_server_text_id`，不能在主线程执行）；FluentPage 移除 `layer.effect: OpacityMask`（GPU 离屏渲染阻塞页面切换）；RinUI ContextMenu 的 `height` 动画从 `enter` transition 改为 `Behavior on height`（修复首次打开缩回问题）
- 2026-04-15: 补全文档遗漏：新增 LeaderboardProvider/AsyncExecutor 端口、LeaderboardGateway/Adapter/Worker、TextListWorker、WeakCharsQueryWorker、UploadTextAdapter、text_id 工具等

---

## [0.1.0] - 2026-04-13

### Changed
- 架构重构：只有服务端文本才能提交成绩；客户端移除 hash 计算；删除无感上传回调链路；source_key 不再进入成绩提交链路

### Added
- 2026-04-11: 新增 TextUploader Port、text_id 生成逻辑、无感上传链路；移除配置中 text_id 字段

---

## [0.0.1] - 2026-04-06

### Changed
- 基于当前源码重写：补充对象装配、QML 页面结构、真实数据流与边界判断
- 2026-04-03: 重写文本加载闭口后的边界规则

### Added
- 2026-03-21: 首次创建架构文档

---

**维护者**: typetype 开发团队  
**最后更新**: 2026-05-14  
**相关文档**: [@see ARCHITECTURE.md](./ARCHITECTURE.md) — 当前架构事实源
