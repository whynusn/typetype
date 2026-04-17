# 服务端 API 端点速查

> 后端项目：`typetype-server`（Java Spring Boot）
> 基础 URL：由 `RuntimeConfig.base_url` 配置，默认 `http://127.0.0.1:8080`

## 认证

| 方法 | 端点 | 说明 | Auth |
|------|------|------|------|
| POST | `/api/v1/auth/login` | 登录，返回 JWT | ❌ |
| POST | `/api/v1/auth/register` | 注册 | ❌ |
| POST | `/api/v1/auth/refresh` | 刷新 token | ✅ |
| GET | `/api/v1/auth/validate` | 校验 token | ✅ |

## 文本

| 方法 | 端点 | 说明 | Auth |
|------|------|------|------|
| GET | `/api/v1/texts/catalog` | 获取所有 active 来源 | ❌ |
| GET | `/api/v1/texts/latest/{sourceKey}` | 获取来源最新文本 | ❌ |
| GET | `/api/v1/texts/{textId}/leaderboard` | 按 textId 查排行榜 | ❌ |
| GET | `/api/v1/texts/{textId}/best` | 当前用户最佳成绩 | ✅ |
| GET | `/api/v1/texts/by-source/{sourceKey}` | 列出来源下所有文本摘要 | ❌ |
| POST | `/api/v1/texts/upload` | 上传文本 | ✅ |

## 成绩

| 方法 | 端点 | 说明 | Auth |
|------|------|------|------|
| POST | `/api/v1/scores` | 提交成绩（需 textId > 0） | ✅ |

## 客户端对应关系

| 客户端组件 | 调用的端点 |
|-----------|-----------|
| `RemoteTextProvider` | `/api/v1/texts/latest/{sourceKey}`, `/api/v1/texts/catalog` |
| `ApiClientAuthProvider` | `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`, `/api/v1/auth/validate` |
| `ApiClientScoreSubmitter` | `/api/v1/scores` |
| `LeaderboardFetcher` | `/api/v1/texts/{textId}/leaderboard`, `/api/v1/texts/by-source/{sourceKey}` |
| `TextUploader` | `/api/v1/texts/upload` |

## 认证方式

所有 `Auth=✅` 的端点需要 HTTP Header：
```
Authorization: Bearer <access_token>
```

Token 由 `SecureStorage.get_jwt("current_user")` 获取，通过 `_get_jwt_token` 函数注入各组件。
