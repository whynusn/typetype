# RuntimeConfig 配置速查
<!-- 状态: active | 最后验证: 2026-08-13 -->

> 配置文件位于用户配置目录中的 `config.json`（schema_version=2，ADR-013）。首次启动时由 dataclass 默认值自动生成。macOS 用户配置目录为 `~/Library/Application Support/TypeType/`，Linux 为 `~/.config/typetype/`。

## 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `schema_version` | `int` | `2` | 配置 schema 版本；缺版本（=v1）时一次性幂等迁移并写回 |
| `default_text_source_key` | `str` | `builtin_demo` | 默认本地文本来源 key |
| `typing_history_max_records` | `int` | `2000` | 打字历史最多保留条数 |
| `blocked_content_hashes` | `list[str]` | `[]` | 被撤销的内容 hash 屏蔽集（2.7/7.2 落地，撤销列表自动维护） |
| `text_sources` | `dict[str, TextSourceEntry]` | `{}` | 文本来源配置表（**仅本地文件**） |
| `ott` | `dict` | 见下 | OTT 运行时参数（由旧 `registry` 段收纳） |
| `update` | `dict` | 见下 | OTA 更新检查配置 |
| `source_repos` | `list` | 内置离线源 + 官方默认仓 | OTT Repo 源仓库订阅列表 |
| `wenlai` | `dict` | 见下 | 晴发文服务配置 |
| `ai` | `dict` | 见下 | AI 智能推荐配置 |
| `text_session` | `dict` | 见下 | 载文会话配置 |
| `ui` | `dict` | 见下 | UI 主题与外观配置 |

> **v2 已删除字段**（v1 → v2 迁移时丢弃）：`base_url`、`api_timeout`、`registry` 段（含 `registry.primary_url` / `registry.mirror_url`）、`text_sources` 中的 server/registry 条目与 `loader`/`leaderboard_mode`/`source_type`/`has_ranking` 字段、`font_config.json`（合并进 `ui.reader_font_path` 后文件退役）。

## TextSourceEntry 字段（v2：仅本地文件）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | `str` | ✅ | 来源标识（JSON 对象键名） |
| `label` | `str` | ✅ | 显示名称 |
| `local_path` | `str` | ✅ | 本地文本文件路径 |

> v2 起所有 `text_sources` 条目均为本地文件；OTT 订阅在 `source_repos`，晴发文/AI 走独立配置段。

## 默认来源列表

> 首次启动生成（五组本地文件，`local_path` 指向 `resources/texts/` 打包文本）。

| key | label | 对应资源文件 |
|-----|-------|------------|
| `builtin_demo` | 本地示例 | `resources/texts/builtin_demo.txt` |
| `fst_500` | 前五百 | `resources/texts/前五百.txt` |
| `mid_500` | 中五百 | `resources/texts/中五百.txt` |
| `lst_500` | 后五百 | `resources/texts/后五百.txt` |
| `essential_single_char` | 打词必备单字 | `resources/texts/打词必备单字.txt` |

## ott 子字段（ADR-013 决策 4：由旧 `registry` 段收纳）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ott.cache_ttl_seconds` | `int` | `3600` | rule/script 缓存 TTL（秒） |
| `ott.max_content_bytes` | `int` | `1048576` | 单条目内容上限（1 MB，federation 传入沙箱） |
| `ott.scripts_enabled` | `bool` | 非 Windows 为 `true` | L3 ott-script 沙箱开关（Windows 默认禁用，无 Landlock 沙箱） |

## update 子字段（OTA 更新检查，ADR-014 决策 6）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `update.enabled` | `bool` | `true` | 是否启用更新检查 |
| `update.auto_check` | `bool` | `true` | 启动后后台自动检查（失败静默） |
| `update.check_interval_hours` | `int` | `24` | 自动检查间隔（小时） |
| `update.channel` | `str` | `stable` | 发布通道（stable / beta，预留） |
| `update.mirrors` | `list[str]` | `[]` | 二进制下载镜像前缀列表（默认空 = 使用内置镜像链） |

## source_repos 子字段（OTT Repo 控制面）

多 authority 源仓库订阅列表（`SourceReposConfig`）。客户端从每个订阅 URL 拉取 `ott-repo.json` manifest，聚合所有源类型（ott-instance / ott-rule / ott-script）。v2 起 `registry.primary_url`/`mirror_url` 已删除，订阅只走本字段。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_repos[].url` | `str` | — | 订阅 URL（ott-repo.json 地址，必填） |
| `source_repos[].enabled` | `bool` | `true` | 是否启用 |
| `source_repos[].trust_state` | `str` | `"unverified"` | 信任状态：`verified` / `pending` / `unverified` / `failed` |
| `source_repos[].pinned_pubkey` | `str` | `""` | TOFU 固定的公钥（ed25519） |
| `source_repos[].refresh_ttl_seconds` | `int` | `86400` | manifest 刷新 TTL（秒） |
| `source_repos[].etag` | `str` | `""` | HTTP ETag（缓存优化，自动管理） |
| `source_repos[].added_at` | `str` | `""` | 订阅添加时间（ISO 8601） |
| `source_repos[].last_snapshot_hash` | `str` | `""` | 上一版已接受 manifest 的 sha256（TUF-lite 链式快照，3.6 落地，自动管理） |

> 协议细节见 open-typing-texts 仓 `docs/repo-manifest-spec.md`（OTT Repo v1）。

## Wenlai 子字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `wenlai.base_url` | `str` | `https://qingfawen.fcxxz.com` | 晴发文服务地址 |
| `wenlai.length` | `int` | `500` | 载文字数 |
| `wenlai.difficulty_level` | `int` | `0` | 难度等级，0 表示随机 |
| `wenlai.category` | `str` | `""` | 分类，空字符串表示全部 |
| `wenlai.segment_mode` | `str` | `manual` | 换段模式：manual/auto |
| `wenlai.strict_length` | `bool` | `false` | 是否精确字数 |
| `wenlai.username` | `str` | `""` | 晴发文用户名（非敏感信息） |
| `wenlai.display_name` | `str` | `""` | 晴发文显示名 |
| `wenlai.user_id` | `int` | `0` | 晴发文用户 ID |

晴发文 token 不写入 JSON 配置，走系统密钥环中的 `wenlai_user` token key。

## AI 子字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ai.provider` | `str` | `deepseek` | 提供商：openai / deepseek / qwen |
| `ai.base_url` | `str` | `""` | API 地址（空则按 provider 解析默认值） |
| `ai.model` | `str` | `""` | 模型名（空则按 provider 解析默认值） |
| `ai.api_format` | `str` | `openai_chat` | 请求格式：openai_chat / openai_response / anthropic |
| `ai.timeout` | `float` | `30.0` | 请求超时（秒），下限 5 |
| `ai.max_chars` | `int` | `300` | 单次生成最大字符数，下限 50 |

AI API Key 不写入 JSON 配置，走系统密钥环 `ai_api_key`。

## text_session 子字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text_session.small_file_threshold` | `int` | `100000` | 小文件阈值（低于此大小不启用分片优化） |
| `text_session.full_shuffle_threshold` | `int` | `1000000` | 全文乱序阈值 |

## UI 子字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ui.theme.current_theme` | `str` | `"Auto"` | 主题模式（Auto/Light/Dark） |
| `ui.theme_color` | `str` | `"#605ed2"` | 主题色 |
| `ui.backdrop_effect` | `str` | `"none"` | 背景特效 |
| `ui.win10_feat` | `dict` | `{backdrop_light, backdrop_dark}` | Windows 10 背景特效参数 |
| `ui.reader_font_path` | `str` | `""` | 阅读字体文件路径（`font_config.json` 已并入此字段） |
