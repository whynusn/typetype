# 更新日志

本文档记录 typetype 项目所有版本的变更。遵循 [Semantic Versioning](https://semver.org/)。

---

## 格式说明

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added      # 新功能
### Changed    # 现有功能变更
### Deprecated # 即将弃用
### Removed    # 已删除功能
### Fixed      # Bug 修复
### Security   # 安全修复
```

---

## [0.1.0] - 2026-01-15

### Added
- 初版发布：打字练习应用核心功能
- 支持多种文本来源：内置示例、本地文件、远程服务器
- 分片加载模式：支持长文本分片练习
- 薄弱字统计：按错误率、错误次数、加权排序
- 排行榜集成：本地排行榜与远程服务器同步
- 用户认证：支持账号注册、登录、成绩上传
- 键盘监听：全局快捷键支持（依赖平台权限）

### Changed
- 2026-03-21：架构重构，分层明确（Presentation → Application → Domain + Infrastructure）
- 2026-04-13：删除 SessionStat.text_source_key，领域模型去除 UI 路由概念
- 2026-04-16：修复文本加载阻塞问题，所有文本加载统一走后台 Worker
- 2026-04-19：优化跨线程通信，使用 Qt 原生 QueuedConnection 替代 QTimer.singleShot
- 2026-04-27：修复分片载文模式，光标重置和达标次数归零

### Fixed
- 删除字符时位置越界错误（TypingService.clear() 不应清零 char_count）
- ContextMenu 首次展开抖动问题（RinUI 修改 1.2，移除 enter transition 中的 height 动画）
- 分片切换后达标次数累计问题
- 清空 UpperPane 文本时 QTextCursor 位置越界警告
- NavigationView 单实例切换时瞬态状态残留

---

**维护者**: typetype 开发团队  
**最后更新**: 2026-05-14
