# 更新日志

本文档记录 typetype 项目所有版本的变更。遵循 [Semantic Versioning](https://semver.org/)。

**维护规则**：
- 变更记录按**日期倒序**排列（最新的在前）
- 按版本号分组，每个版本号内按**功能类型分类**（Added/Changed/Fixed/Removed）
- 详细的实现细节应记录在此，架构相关内容通过 `@see ARCHITECTURE.md` 指向
- 请勿在 `ARCHITECTURE.md` 中维护版本历史（该文档专注当前架构事实）

---

## [Unreleased] - In Development

### Added

- **内置默认文本源（ADR-011 Phase 4）**：首启自动注入 `file://` 内置 OTT Repo（经典中文短句 / 拼音声调练习 / 唐诗精选），完全离线可用，不自动订阅任何远程源；静态 profile 补齐 `sources.json` 与 `entries/{id}.json`，摘要不再内嵌全文，entry_id 符合 schema pattern，逐条标注 rights/license/origin；官方默认仓移除 ott-script/ott-rule 示例
- **OTT DSL 组合安全加固（ADR-011 Phase 1.5）**：整数纳入单值字节上限（`bit_length` 估算），超大位移直接拒绝，字面量/结果超限检查前置到求值器内部；新增组合矩阵 + 固定种子模糊测试，随机表达式只可能成功或抛 `DslError`
- **default_enabled 消费（ADR-011 Phase 3.4）**：联邦聚合按 manifest 声明的 `default_enabled` 启用/禁用 ott-instance 源，未声明时默认启用
- **manifest 条件请求与镜像 failover（ADR-011 Phase 3.1/3.2）**：拉取携带 `If-None-Match`，304 刷新缓存 mtime 不换内容；主地址失败时按已缓存 manifest 的 http(s) mirrors 依次回退，ETag 持久化到订阅
- **联邦客户端复用与结果缓存（ADR-011 Phase 3.9）**：rule/script 共用单个 `httpx.Client`，按订阅+manifest mtime 签名复用客户端实例；rule/script 条目结果按 `cache_ttl_seconds` 缓存，避免每次查询全量重抓
- **requires 协商（ADR-011 Phase 3.3）**：manifest 声明 `ott_core` 版本约束与 `client_features`，不满足整仓标记不兼容并跳过，订阅列表显示 `incompatible_reason`，不再静默部分启用
- **ott-bridge 决策落地（ADR-011 Phase 3.5）**：明确暂不实现 L2 provider；联邦跳过桥接源并在订阅面板显示"桥接源暂不支持"，ARCHITECTURE 同步为未落地
- **本地内容屏蔽清单（ADR-011 Phase 7.2）**：`blocked_content_hashes` 配置持久化，联邦按 `content_hash` 屏蔽条目详情，takedown 可即时生效；新增 OTT Repo 治理操作手册（贡献协议/收稿红线/takedown 流程）
- **L3 签名门槛（ADR-011 Phase 2.3）**：ott-script 仅允许 `trust_state=verified` 的仓库执行，未签名/未确认/签名失败仓库跳过；新增适配器签名方案设计文档（Phase 2.0，canonical JSON/裸 Ed25519/TOFU/撤销）
- **OTT Repo 控制面（ADR-010）**：去中心化文本源订阅生态。多 authority 联邦聚合（`OttFederationConfig`）、订阅管理 UI（`ReposManagementPanel`）、声明式规则源（L1 `OttRuleInterpreter`）、ott-script 脚本源（L3 子进程沙箱）、旧 `registry.primary_url` 自动迁移
- **打词率（word typing rate）指标**：统计会话中 CJK 字符被作为词组输入的比例。
  算法将间隔 ≤ 300ms 的连续 CJK 字符视为词组输入，打词率 = 词组字符数 / 总 CJK 字符数 × 100。
  - ：记录每个字符的提交时间戳
  - ：打词率计算核心逻辑
  - ：领域模型字段
  -  和 ：成绩展示和历史记录
  - 新测试文件 （10 个用例覆盖边界条件）
  - 对应 Issue #2: 用户反馈 "统计里能加上打词率"

### Fixed

- **内置源 Windows 无法加载**：`file://` URI 转本地路径兼容 Windows 盘符（`/D:/...` → `D:\...`），manifest 占位符展开使用正斜杠盘符形式，修复 CI Windows 上内置源 0 条目的问题
- **ott-script 沙箱逃逸（严重）**：原进程内 `exec()` + 模块注入可被 `json.__builtins__['open']` 单行逃逸。重写为独立 Python 子进程（`ott_script_runner.py`），资源限制（256MB 内存 / 30s CPU / RLIMIT_NPROC=0）+ AST 白名单 import + 别名解析 + `__builtins__` 检测
- **规则解释器 ReDoS 与 fetch 大小绕过**：正则匹配输入截断至 50KB 防灾难性回溯；`_fetch()` 改为 streaming 截断（不依赖 `content-length` 头，堵住 chunked 传输绕过）
- **用户配置写入路径污染**：`RuntimeConfig._save_to_file()` 尊重显式加载的 `_config_path`，避免测试或临时配置写入真实 `~/.config/typetype/config.json`
- **启动默认载文报错**：首次进入跟打页时优先使用本地可用来源自动载文，避免默认远程来源（如 `old`）在服务端不可用时每次启动弹出“无法获取网络文本”
- **启动默认网络载文误报失败**：远程文本解析兼容 `content`/`text`/`textContent`/`articleContent` 与顶层响应格式，避免 `/api/v1/texts/latest/{sourceKey}` 返回 200 时仍显示“无法获取网络文本”
- **个人中心趋势图横轴**：图表内部类目改用唯一索引，横轴标签按 `ChartView.plotArea` 中心点独立渲染，避免 Qt Charts 因重复空白类目导致刻度重叠、缺失或柱状数据错位
- **个人中心趋势粒度**：`按小时` 改为小时刻度，`按周` 改为 ISO 周刻度，`按月` 改为后端按月聚合，避免前端把日数据误折叠导致月图为空
- ** 重复项修复**：移除条目列表中多余的"用时"重复项

- **文本排行页崩溃**：`TextLeaderboardPage.qml` 缺少 `DataCell` 类型引用导致页面无法打开；排行榜布局改为响应式（宽屏左右分栏、窄屏上下堆叠），列宽不再截断内容
- **开源文库加载状态**：开源文库列表不再错误复用 `typetype-server` 的 `textListLoading`，改为独立的 `catalogLoading` 属性

### Changed

- **个人中心趋势图**：趋势图改用 PySide6 Qt Charts 成品 `ChartView`/`BarSeries` 组件渲染，并沿用 RinUI 主题色与时间范围切换
- **统一载文中心**：极速杯、本地文库、开源文库、练单器、自定义 5 个载文入口合并为单一 `TextLoadHubPage.qml`，顶部 Segmented 切换来源，左侧列表/输入区与右侧切片设置/预览区统一；删除 `JisuBeiPage.qml`、`LocalArticlesPage.qml`、`TextLibraryPage.qml`、`CustomLoadTextPage.qml`、`TrainerPage.qml`
- **顶部来源切换**：`SelectorBar` 替换为 RinUI `Segmented`/`SegmentedItem`，带背景容器与间距，视觉层次更清晰；无边框、紧贴下方组件的问题已解决
- **个人中心重构**：登录后展示用户信息卡片、6 项统计卡片（今日字数/总字数/平均速度/最高速度/平均键准/总场次）、最近 30 天打字趋势迷你柱状图、最近 50 条成绩列表（右键复制成绩）
- **全应用内部通知统一**：抽取 `AppNotification.qml` + `AppNotificationManager.qml`，替换 `HistoryArea`、`TextInfoCard`、`DailyLeaderboard`、`UploadTextPage` 中各页面硬编码的 `copyToast`/`InfoBar`
- **自定义载文去重**：统一载文中心内的自定义面板隐藏与顶部来源切换功能重叠的"从文本库选择"，仅保留纯文本输入 + 切片设置

### Added

- **打字历史记录持久化**：新增 `TypingHistoryStore` 端口、`JsonTypingHistoryStore` 实现、`TypingHistoryGateway` 业务网关；每次跟打完成自动持久化到 `~/.local/share/typetype/typing_history.json`，最多 5000 条；Bridge 暴露 `typingHistoryCount`/`typingHistoryAverageSpeed`/`typingHistoryMaxSpeed`/`typingHistoryAverageKeyAccuracy`/`typingHistoryTotalChars`/`typingHistoryRecords`/`typingHistoryDailyTrend`
- **Bridge `catalogLoading` 属性**：开源文库目录加载的独立状态信号

---

## [0.2.0] - 2026-06-04

### Changed

- **Bridge 架构重构**：分片载文业务逻辑下沉到 `TypingSessionContext`，Bridge 瘦身为薄适配层（属性代理/信号转发/Slot 入口）；删除 200+ 行业务逻辑代码
- **NavigationView 单实例重构**：移除 StackView 及 push/pop 动画，改用 `pageInstances` 字典缓存实例，通过 `visible` + `active` 属性切换页面；所有 QML 页面信号守卫迁移为 `page.active`
- **Bridge 类型合规**：`UploadTextAdapter` 和 `Bridge` 类型注解从 `integration.*` 改为 `ports.*`（消除 Presentation→Integration 违规）
- **Bridge 代码清理**：提取 `_clear_text_id()` 方法消除 4 处重复

### Added

- **TypingSessionContext 会话状态机**：集中管理会话阶段、来源模式、上传资格推导、分片载文
- **配置文件自动初始化**：启动时检查 `config.json` 不存在则从 example 复制
- **服务地址运行时配置**：SettingsPage 输入框 → Bridge.setBaseUrl() → 闭包传播到所有依赖对象 + 持久化
- **回改/退格统计指标**：`SessionStat` 新增 `backspace_count`/`correction_count`，Wayland 通过 evdev 检测
- **macOS 兼容**：新增 Quartz CGEventTap 全局键盘监听；配置和数据库写入用户可写目录
- **分片载文修复**：光标重置防越界、`_color_text` 边界检查、片段切换时达标次数归零
- **文档体系重构**：ARCHITECTURE.md 精简（去掉重复目录树，从 683→170 行）；AGENTS.md 精简（去掉重复导航卡，从 497→200 行）；7 个 ADR 覆盖核心架构决策；tutorials/ 和 guides/ 目录有实际内容

### Fixed

- **本地文本加载两阶段异步**：Worker 只读文件，HTTP 回查移至 daemon thread（消除主线程阻塞）
- **FluentPage OpacityMask 移除**：GPU 离屏渲染阻塞页面切换
- **ContextMenu height 动画修复**：`enter` transition 改为 `Behavior on height`（修复首次打开缩回 6px）
- **FluentPage anchors → x/y**：消除 ColumnLayout 与 anchors 冲突警告
- **TextAdapter 统一走 Worker**：所有文本加载后台执行，不再主线程同步 I/O

---

## [0.1.0] - 2026-04-13

### Changed

- 架构重构：只有服务端文本才能提交成绩；客户端移除 hash 计算；删除无感上传回调链路；source_key 不再进入成绩提交链路

### Added

- 新增 TextUploader Port、text_id 生成逻辑、无感上传链路；移除配置中 text_id 字段

---

## [0.0.1] - 2026-04-06

### Changed

- 基于当前源码重写：补充对象装配、QML 页面结构、真实数据流与边界判断
- 2026-04-03: 重写文本加载闭口后的边界规则

### Added

- 2026-03-21: 首次创建架构文档

---

**最后更新**: 2026-06-04  
**相关文档**: [@see docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 当前架构事实源
