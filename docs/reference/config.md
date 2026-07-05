# RuntimeConfig 配置速查
<!-- 状态: active | 最后验证: 2026-07-04 -->

> 配置文件查找顺序：用户配置目录中的 `config.json` → `config/config.json` → `config/config.example.json`。macOS 用户配置目录为 `~/Library/Application Support/TypeType/`，Linux 为 `~/.config/typetype/`。

## 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `base_url` | `str` | `http://127.0.0.1:8080` | 服务端地址 |
| `default_text_source_key` | `str` | `builtin_demo` | 默认文本来源 key |
| `api_timeout` | `float` | `20.0` | API 请求超时（秒），启动期常量 |
| `text_sources` | `dict[str, TextSourceEntry]` | `{}` | 文本来源配置表 |
| `wenlai` | `dict` | 见下 | 晴发文服务配置 |
| `ui` | `dict` | 见下 | UI 主题与外观配置 |

## TextSourceEntry 字段

> 设计：`loader`（数据从哪来）+ `leaderboard_mode`（成绩怎么处理）二维正交。详见 `text_source_config.py` 模块文档。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | `str` | ✅ | 来源标识（JSON 对象键名） |
| `label` | `str` | ✅ | 显示名称 |
| `loader` | `str` | ❌ | `local_file` / `remote_api` / `registry`（决定 Gateway 路由） |
| `leaderboard_mode` | `str` | ❌ | `none` / `server_resolved` / `local_lookup`（决定 text_id 决策） |
| `local_path` | `str` | ❌ | 仅 loader=local_file 时需要 |

## Loader 枚举

| 值 | 加载方式 | Gateway 路由 |
|----|---------|-------------|
| `local_file` | 读本地文件 | `LocalTextLoader` / `FileSegmentProvider` |
| `remote_api` | 调用服务端 API | `RemoteTextProvider` |
| `registry` | CDN 注册表（GitHub Actions 生成） | `RegistryTextProvider` |

## LeaderboardMode 枚举

| 值 | text_id 决策 | 适用场景 |
|----|------------|---------|
| `none` | 不提交，不参与排行榜 | 本地练习文本、剪贴板 |
| `server_resolved` | 服务端直接返回 text_id | 极速杯等远程源、注册表源 |
| `local_lookup` | 本地内容 hash 回查服务端 text_id | "前五百"等固定本地内容 |

## 默认来源列表

| key | label | loader | leaderboard_mode |
|-----|-------|--------|-----------------|
| `builtin_demo` | 本地示例 | local_file | none |
| `jisubei` | 极速杯 | remote_api | server_resolved |
| `fst_500` | 前五百 | local_file | local_lookup |
| `mid_500` | 中五百 | local_file | local_lookup |
| `lst_500` | 后五百 | local_file | local_lookup |
| `essential_single_char` | 打词必备单字 | local_file | none |

## 运行时动态属性

通过 `RuntimeConfig` 实例可获取的派生属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `default_text_source_key` | `str` | 默认来源 key |
| `login_api_url` | `str` | 登录接口 URL |
| `validate_api_url` | `str` | token 校验接口 URL（默认 `/api/v1/users/me`） |
| `refresh_api_url` | `str` | token 刷新接口 URL |
| `register_api_url` | `str` | 注册接口 URL |

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

## UI 子字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ui.theme.current_theme` | `str` | `"Auto"` | 主题模式（Auto/Light/Dark） |
| `ui.theme_color` | `str` | `"#605ed2"` | 主题色 |
| `ui.backdrop_effect` | `str` | `"none"` | 背景特效 |
| `ui.win10_feat` | `dict` | `{backdrop_light, backdrop_dark}` | Windows 10 背景特效参数 |
| `ui.reader_font_path` | `str` | `""` | 阅读字体文件路径（`font_config.json` 已并入此字段） |