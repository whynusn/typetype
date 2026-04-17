# JWT 定时刷新设计文档

> 创建日期：2026-04-13
> 状态：已批准

---

## 一、目标

根据服务端返回的 JWT `expiresIn` 字段，在 access_token 过期前自动刷新，对用户零感知。断网场景下静默重试，不误踢用户。

## 二、现状分析

- 服务端 `TokenVO` 已返回 `expiresIn`（当前 900 秒 = 15 分钟）
- 客户端 `AuthResult` 未解析 `expiresIn`
- 客户端 `AuthService.refresh_token()` 已存在且可用
- 当前只在启动时 `validate_token()` 失败才触发刷新
- 无定时刷新机制

## 三、设计方案

### 3.1 状态机

```
NOT_LOGGED_IN → login() → ACTIVE (定时刷新中)
ACTIVE → 定时器触发 → REFRESHING → 成功 → ACTIVE（重置定时器）
REFRESHING → 网络异常 → RETRYING（60s后重试，最多10次）
REFRESHING → HTTP 401 → 重试1次 → 失败 → EXPIRED（通知UI重登）
RETRYING → 重试成功 → ACTIVE
EXPIRED → tokenExpired 信号 → UI 提示重新登录
```

### 3.2 数据流

```
登录/刷新成功
  → 服务端返回 { accessToken, refreshToken, expiresIn: 900 }
  → ApiClientAuthProvider 解析 expiresIn
  → AuthResult 新增 expires_in 字段
  → AuthService 保存 token + 记录时间戳
  → AuthAdapter 读取 refresh_interval → 启动 QTimer
    → interval = max(expires_in - 120, 60)
  → 定时器触发 → AuthService.refresh_token()
    → 成功：重置 QTimer（新 expiresIn）
    → 网络异常：60s 后重试，最多 10 次
    → 401：再试 1 次，仍失败则 tokenExpired
```

### 3.3 断网容错

| 场景 | 行为 |
|------|------|
| 刷新成功 | 重置定时器，回到 ACTIVE |
| 网络断开 | 不弹登录，60s 后重试，最多 10 次 |
| HTTP 401 | 重试 1 次刷新，仍失败则 EXPIRED |
| 其他 HTTP 错误 | 当作临时故障，60s 后重试 |
| 重试 10 次全失败 | 静默停止，等下次用户操作时触发 |
| 应用从后台恢复 | 检查 token 剩余时间，不足则立即刷新 |

## 四、修改文件清单

| 文件 | 改动 |
|------|------|
| `src/backend/models/dto/auth_dto.py` | AuthResult 新增 `expires_in: int = 0` |
| `src/backend/integration/api_client_auth_provider.py` | `_parse_auth_response` 解析 `expiresIn` |
| `src/backend/domain/services/auth_service.py` | 保存 expires_in；新增 `token_remaining_seconds`、`refresh_interval_seconds` |
| `src/backend/presentation/adapters/auth_adapter.py` | 新增 QTimer + 重试逻辑 + 生命周期监听 |
| `src/backend/presentation/bridge.py` | 新增 `tokenExpired` 信号透传 |
| `tests/test_auth_service.py` | 测试 refresh interval 计算、token 过期 |

## 五、架构约束

- **Domain（AuthService）** 不持有 QTimer，只暴露属性和方法
- **Presentation（AuthAdapter）** 持有 QTimer，管理 Qt 资源
- 新增 `tokenExpired` 信号从 AuthAdapter → Bridge → QML
- 遵循现有依赖规则：Adapter → Application/Domain，不穿透到 Integration

## 六、关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| REFRESH_AHEAD_SECONDS | 120 | 提前 2 分钟刷新 |
| RETRY_INTERVAL_MS | 60000 | 重试间隔 60 秒 |
| MAX_RETRY | 10 | 最大重试次数 |

## 七、不做的事

- 不修改后端代码（后端已返回 expiresIn）
- 不改变现有登录/登出流程
- 不引入新依赖（用已有的 QTimer）
- 不做 Redis token 黑名单（已有设计文档中提及但当前不落地）
