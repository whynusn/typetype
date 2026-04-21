# RuntimeConfig 配置速查

> 配置文件查找顺序：`~/.config/typetype/config.json` → `config/config.json` → `config/config.example.json`

## 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `base_url` | `str` | `http://127.0.0.1:8080` | 服务端地址 |
| `default_text_source_key` | `str` | `builtin_demo` | 默认文本来源 key |
| `api_timeout` | `float` | `20.0` | API 请求超时（秒） |
| `text_sources` | `dict[str, TextSourceEntry]` | `{}` | 文本来源配置表 |

## TextSourceEntry 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | `str` | ❌ | 显示名称（默认取 key 值） |
| `local_path` | `str` | ❌ | 本地文件路径（有则走本地加载，无则走远程 API） |
| `has_ranking` | `bool` | ❌ | 是否参与排行榜（默认 false） |

## 判断规则

```
有 local_path → 本地来源 → text_id=None → 不提交成绩
无 local_path → 远程来源 → text_id 由服务端返回 → 可提交成绩
```

## 默认来源列表

| key | label | 类型 | 排行榜 |
|-----|-------|------|--------|
| `builtin_demo` | 本地示例 | 本地 | ❌ |
| `jisubei` | 极速杯 | 远程 | ✅ |
| `fst_500` | 前五百 | 本地 | ✅ |
| `mid_500` | 中五百 | 本地 | ✅ |
| `lst_500` | 后五百 | 本地 | ✅ |
| `essential_single_char` | 打词必备单字 | 本地 | ❌ |

## 运行时动态属性

通过 `RuntimeConfig` 实例可获取的派生属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `default_text_source_key` | `str` | 默认来源 key |
| `login_api_url` | `str` | 登录接口 URL |
| `validate_api_url` | `str` | token 校验接口 URL（默认 `/api/v1/users/me`） |
| `refresh_api_url` | `str` | token 刷新接口 URL |
| `register_api_url` | `str` | 注册接口 URL |
