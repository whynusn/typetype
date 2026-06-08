# 服务端 API 端点速查
<!-- 状态: active | 最后验证: 2026-05-14 -->

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

## 成绩提交契约（V2）

### POST /api/v1/scores

客户端只发送原始采集字段，所有派生指标由服务端统一根据原始字段实时计算。

**请求体字段（必传）：**

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| textId | Long | SessionStat.text_id | 服务端文本ID（主键） |
| charCount | Integer | SessionStat.char_count | 已正确输入字符数 |
| wrongCharCount | Integer | SessionStat.wrong_char_count | 错误字符数 |
| backspaceCount | Integer | SessionStat.backspace_count | 退格键按下次数 |
| correctionCount | Integer | SessionStat.correction_count | 回改字数 |
| keyStrokeCount | Integer | SessionStat.key_stroke_count | 总按键数（原始值） |
| time | Decimal | SessionStat.time | 用时（秒） |

**服务端返回字段：**

#### 原始字段（直接从数据库读取）

| 字段 | 类型 |
|------|------|
| textId | Long |
| charCount | Integer |
| wrongCharCount | Integer |
| backspaceCount | Integer |
| correctionCount | Integer |
| keyStrokeCount | Integer |
| time | Decimal |
| createdAt | LocalDateTime |

#### 派生字段（服务端实时计算返回）

| 字段 | 计算公式 |
|------|----------|
| speed | `charCount × 60 / time` |
| keyStroke | `keyStrokeCount / time` |
| codeLength | `keyStrokeCount / charCount` |
| keyAccuracy | `(keyStrokeCount - backspaceCount - correctionCount × codeLength) / keyStrokeCount × 100%` |
| accuracyRate | `(charCount - wrongCharCount) / charCount × 100` |
| effectiveSpeed | `speed × accuracyRate / 100` |

#### 兼容字段（已废弃，保留用于过渡期）

| 字段 | 替代方案 |
|------|----------|
| duration | 已统一为 `time` |
| accuracy | 已统一为 `accuracyRate` |

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
