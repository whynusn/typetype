# 服务端 API 端点速查

> 后端项目：`typetype-server`（Java Spring Boot）
> 基础 URL：由 `RuntimeConfig.base_url` 配置，默认 `http://127.0.0.1:8080`

## 认证（AuthController: `/api/v1/auth`）

| 方法 | 端点 | 客户端调用 | Auth |
|------|------|-----------|------|
| POST | `/api/v1/auth/login` | ✅ `ApiClientAuthProvider` | ❌ |
| POST | `/api/v1/auth/register` | ✅ `ApiClientAuthProvider` | ❌ |
| POST | `/api/v1/auth/refresh` | ✅ `ApiClientAuthProvider` | ✅ |
| POST | `/api/v1/auth/logout` | ❌ | ✅ |

## 用户（UserController: `/api/v1/users`）

| 方法 | 端点 | 客户端调用 | Auth |
|------|------|-----------|------|
| GET | `/api/v1/users/me` | ✅ `ApiClientAuthProvider`（token 校验） | ✅ |
| GET | `/api/v1/users/{id}` | ❌ | ✅ |

## 文本（TextController: `/api/v1/texts`）

| 方法 | 端点 | 客户端调用 | Auth |
|------|------|-----------|------|
| GET | `/api/v1/texts/catalog` | ✅ `RemoteTextProvider` / `LeaderboardFetcher` | ❌ |
| GET | `/api/v1/texts/latest/{sourceKey}` | ✅ `RemoteTextProvider` / `LeaderboardFetcher` | ❌ |
| GET | `/api/v1/texts/{id}` | ✅ `LeaderboardFetcher` | ❌ |
| GET | `/api/v1/texts/source/{sourceKey}` | ❌ | ❌ |
| GET | `/api/v1/texts/by-source/{sourceKey}` | ✅ `LeaderboardFetcher` | ❌ |
| GET | `/api/v1/texts/by-client-text-id/{clientTextId}` | ✅ `RemoteTextProvider` | ❌ |
| POST | `/api/v1/texts/upload` | ✅ `TextUploader` | ✅ |

## 成绩（ScoreController: `/api/v1`）

| 方法 | 端点 | 客户端调用 | Auth |
|------|------|-----------|------|
| POST | `/api/v1/scores` | ✅ `ApiClientScoreSubmitter` | ✅ |
| GET | `/api/v1/scores/history` | ❌ | ✅ |
| GET | `/api/v1/texts/{textId}/scores` | ❌ | ❌ |
| GET | `/api/v1/texts/{textId}/leaderboard` | ✅ `LeaderboardFetcher` | ❌ |
| GET | `/api/v1/texts/{textId}/best` | ❌ | ✅ |

## 排行榜（特殊端点）

| 方法 | 端点 | 客户端调用 | Auth |
|------|------|-----------|------|
| GET | `/api/v1/texts/{textId}/leaderboard` | ✅ `LeaderboardFetcher` | ❌ |

## 认证方式

所有 `Auth=✅` 的端点需要 HTTP Header：
```
Authorization: Bearer ***
```

Token 由 `SecureStorage.get_jwt("current_user")` 获取，通过 `_get_jwt_token` 函数注入各组件。

## 客户端组件 → 端点映射

| 客户端组件 | 调用的端点 |
|-----------|-----------|
| `ApiClientAuthProvider` | `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`, `/api/v1/users/me` |
| `ApiClientScoreSubmitter` | `/api/v1/scores` |
| `RemoteTextProvider` | `/api/v1/texts/catalog`, `/api/v1/texts/latest/{sourceKey}`, `/api/v1/texts/by-client-text-id/{clientTextId}` |
| `LeaderboardFetcher` | `/api/v1/texts/catalog`, `/api/v1/texts/latest/{sourceKey}`, `/api/v1/texts/{id}`, `/api/v1/texts/by-source/{sourceKey}`, `/api/v1/texts/{textId}/leaderboard` |
| `TextUploader` | `/api/v1/texts/upload` |
