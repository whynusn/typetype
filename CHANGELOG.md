# 更新日志

本文档记录 typetype 项目所有版本的变更。遵循 [Semantic Versioning](https://semver.org/)。

**维护规则**：
- 变更记录按**日期倒序**排列（最新的在前）
- 按版本号分组，每个版本号内按**功能类型分类**（Added/Changed/Fixed/Removed）
- 详细的实现细节应记录在此，架构相关内容通过 `@see ARCHITECTURE.md` 指向
- 请勿在 `ARCHITECTURE.md` 中维护版本历史（该文档专注当前架构事实）

---

## [Unreleased] - In Development

> 暂无未发布变更。

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
