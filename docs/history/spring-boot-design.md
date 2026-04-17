# TypeType Spring Boot 后端设计方案

> 最后更新：2026-04-17
>
> 基于对 typetype 桌面客户端的完整架构分析，设计一套面试级别的 Spring Boot 后端服务。
>
> 注意：本文重点是后端方案，客户端架构请以 [ARCHITECTURE.md](./ARCHITECTURE.md) 和源码为准。

---

## 目录

- [客户端现状分析](#客户端现状分析)
- [后端整体架构](#后端整体架构)
- [数据库设计](#数据库设计)
- [API 设计](#api-设计)
- [核心亮点设计](#核心亮点设计)
- [项目结构](#项目结构)
- [Python 客户端改造](#python-客户端改造)
- [面试话术建议](#面试话术建议)

---

## 客户端现状分析

### 整体架构

typetype 是一个 **PySide6 + QML 的跨平台打字练习工具**，Python 端采用了分层 + Ports & Adapters 架构：

```
QML UI → Presentation (Bridge + Adapters)
           → Application (UseCase + Gateway)
           → Domain / Ports
           → Integration / Infrastructure
```

### 当前痛点（截至 2026-04-17）

1. **文本来源部分可控** — 已支持多来源（网络 + 本地文件 + 剪贴板），但远程来源仍依赖第三方 API
2. **成绩已可提交云端** — `ApiClientScoreSubmitter` 已实现，排行榜基础可用，但服务端稳定性和功能完善仍需迭代
3. **认证基础已建立** — `AuthService` + JWT token 校验/刷新已实现，但无用户管理、个人中心等上层功能

Spring Boot 后端的目标：**替换第三方 API 为自托管文本服务，提供更完整的用户/排行/统计体验。**

---

## 后端整体架构

```
┌──────────────────────────────────────────────────────────────┐
│               typetype Client (PySide6)                      │
│  RuntimeConfig 增加 springboot 来源                           │
│  新增 SpringBootTextProvider 实现 TextProvider 协议           │
│  复用 ApiClient (httpx)                                      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (JSON)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Spring Boot Backend (分层架构)                    │
│                                                              │
│  ┌── Controller ──┐  ┌── Service ──┐  ┌── Repository ──┐   │
│  │ TextController   │→│ TextService  │→│ TextRepository  │   │
│  │ ScoreController  │→│ ScoreService │→│ ScoreRepository │   │
│  │ UserController   │→│ UserService  │→│ UserRepository  │   │
│  │ AuthController   │→│ AuthService  │→│                 │   │
│  └──────────────────┘  └─────────────┘  └────────────────┘   │
│                              ↓                                │
│  ┌── Infrastructure ─────────────────────────────────────┐   │
│  │ Redis (缓存 + 排行榜)  │  MySQL/PostgreSQL (持久化)     │   │
│  │ Spring Security + JWT  │  MyBatis-Plus / JPA           │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 技术选型

| 层面 | 选型 | 选型依据 |
|------|------|----------|
| **认证** | Spring Security + JWT (双 token) | access_token 15min + refresh_token 7d，token rotation 防重放 |
| **缓存** | Redis | 排行榜用 ZSET；随机文本用 SET 预加载 ID 池；热门文本缓存 |
| **ORM** | MyBatis-Plus (推荐面试) | 国内面试 MyBatis 加分，能聊 SQL 优化 |
| **参数校验** | `@Valid` + `javax.validation` | 全局异常处理器 `@RestControllerAdvice` 捕获 |
| **接口文档** | SpringDoc (OpenAPI 3) | 前后端对接效率，体现协作意识 |
| **日志** | SLF4J + Logback，MDC 链路追踪 | 每个请求带 traceId，面试聊日志排查能力 |
| **限流** | Guava RateLimiter 或 Redis + Lua | 防刷成绩接口，面试聊分布式限流 |
| **数据库版本** | Flyway | 数据库 migration 版本管理 |

---

## 数据库设计

### ER 关系

```
t_user (1) ──── (N) t_score (N) ──── (1) t_text (N) ──── (1) t_text_source
```

### DDL 设计

```sql
-- 用户表
CREATE TABLE t_user (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    username    VARCHAR(32) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL,          -- BCrypt 加密
    nickname    VARCHAR(64),
    avatar_url  VARCHAR(512),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username)
);

-- 文本来源表
CREATE TABLE t_text_source (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    source_key  VARCHAR(64) UNIQUE NOT NULL,    -- 如 'cet4', 'essay_classic'
    label       VARCHAR(128) NOT NULL,
    category    VARCHAR(32) NOT NULL,           -- 'vocabulary', 'article', 'custom'
    is_active   TINYINT(1) DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 文本表
CREATE TABLE t_text (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    source_id   BIGINT NOT NULL,
    title       VARCHAR(255),
    content     TEXT NOT NULL,
    char_count  INT NOT NULL,                   -- 冗余字段，避免每次 LENGTH()
    difficulty  TINYINT DEFAULT 0,              -- 0-5 难度分级
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES t_text_source(id),
    INDEX idx_source_difficulty (source_id, difficulty)
);

-- 成绩表
CREATE TABLE t_score (
    id                BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id           BIGINT NOT NULL,
    text_id           BIGINT,                   -- 可选，关联练习的文本
    speed             DECIMAL(8,2) NOT NULL,     -- 字/分
    effective_speed   DECIMAL(8,2) NOT NULL,
    key_stroke        DECIMAL(8,2) NOT NULL,     -- 击/秒
    code_length       DECIMAL(8,4) NOT NULL,     -- 击/字
    accuracy_rate     DECIMAL(5,2) NOT NULL,     -- 准确率 %
    char_count        INT NOT NULL,
    wrong_char_count  INT NOT NULL,
    duration          DECIMAL(10,2) NOT NULL,    -- 秒
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES t_user(id),
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_speed (speed DESC),
    INDEX idx_created_at (created_at)
);
```

### 索引设计说明

| 索引 | 服务场景 | 说明 |
|------|----------|------|
| `idx_username` | 登录查询 | 用户名唯一索引，登录快速定位 |
| `idx_source_difficulty` | 随机选文 | 复合索引：按来源 + 难度筛选文本 |
| `idx_user_created` | 个人历史记录 | 覆盖"我的记录"查询，DESC 支持最近优先 |
| `idx_speed` | 排行榜 | 全局速度排行快速查询 |
| `idx_created_at` | 时间范围查询 | 支持日/周/月维度的统计聚合 |

---

## API 设计

### 接口列表

```yaml
# === 认证 ===
POST   /api/v1/auth/register        # 注册
POST   /api/v1/auth/login           # 登录 → 返回 JWT access_token + refresh_token
POST   /api/v1/auth/refresh         # 刷新 token

# === 文本 ===
GET    /api/v1/texts/random          # 随机获取一篇练习文本
       ?sourceKey=cet4               #   按来源筛选
       &difficulty=3                 #   按难度筛选（可选）
GET    /api/v1/text-sources          # 获取所有可用文本来源

# === 成绩 ===
POST   /api/v1/scores                # 提交成绩
GET    /api/v1/scores/me             # 我的历史记录（分页）
       ?page=1&size=20
       &sortBy=createdAt             # 支持 speed/createdAt 排序
GET    /api/v1/scores/ranking        # 排行榜
       ?type=daily|weekly|all_time
       &page=1&size=50

# === 用户 ===
GET    /api/v1/users/me              # 获取当前用户信息
PUT    /api/v1/users/me              # 更新个人信息
GET    /api/v1/users/me/stats        # 个人统计概览
```

### 统一响应格式

```json
// 成功
{
  "code": 200,
  "message": "success",
  "data": { ... },
  "timestamp": 1709625600000
}

// 分页
{
  "code": 200,
  "data": {
    "records": [...],
    "total": 1234,
    "page": 1,
    "size": 20,
    "pages": 62
  }
}

// 错误
{
  "code": 40001,
  "message": "用户名已存在",
  "timestamp": 1709625600000
}
```

### 业务错误码

```
10xxx → 系统错误
  10001  内部异常
  10002  参数校验失败

20xxx → 认证错误
  20001  token 过期
  20002  token 无效
  20003  密码错误
  20004  用户名不存在

30xxx → 文本业务
  30001  来源不存在
  30002  无可用文本

40xxx → 成绩业务
  40001  成绩数据异常
  40002  提交过于频繁
```

---

## 核心亮点设计

### 排行榜（Redis ZSET）

```java
// 提交成绩时更新排行榜
public void updateRanking(Long userId, double speed) {
    String dailyKey = "ranking:daily:" + LocalDate.now();
    String weeklyKey = "ranking:weekly:" + getWeekKey();
    String allTimeKey = "ranking:all_time";

    // ZADD 只保留最高分 (GT flag: only update if new score > old)
    redisTemplate.opsForZSet().add(dailyKey, userId.toString(), speed);
    redisTemplate.expire(dailyKey, Duration.ofDays(2));

    redisTemplate.opsForZSet().add(weeklyKey, userId.toString(), speed);
    redisTemplate.expire(weeklyKey, Duration.ofDays(8));

    redisTemplate.opsForZSet().add(allTimeKey, userId.toString(), speed);
}

// 查询排行榜 Top N
public List<RankingVO> getTopN(String type, int n) {
    String key = "ranking:" + type + ":" + getKeySuffix(type);
    Set<ZSetOperations.TypedTuple<String>> tuples =
        redisTemplate.opsForZSet().reverseRangeWithScores(key, 0, n - 1);
    // 批量查 userInfo (pipeline)，拼装返回
}
```

**面试谈资**：为什么用 ZSET 不用 SQL `ORDER BY`？→ O(logN) 写入 + O(logN+M) 范围查询 vs 全表排序。

### 随机文本（避免慢查询）

```java
// 方案：预热 ID 池 + SRANDMEMBER
@Scheduled(fixedRate = 300_000) // 5min 刷新
public void refreshTextIdPool() {
    for (TextSource source : sourceRepo.findAllActive()) {
        List<Long> ids = textRepo.findIdsBySourceId(source.getId());
        String key = "text:ids:" + source.getSourceKey();
        redisTemplate.delete(key);
        redisTemplate.opsForSet().add(
            key,
            ids.stream().map(String::valueOf).toArray(String[]::new)
        );
    }
}

public Text getRandomText(String sourceKey) {
    String key = "text:ids:" + sourceKey;
    String idStr = redisTemplate.opsForSet().randomMember(key);
    // 查缓存或 DB
}
```

**面试谈资**：为什么不用 `ORDER BY RAND() LIMIT 1`？→ 全表扫描 + filesort，大数据量下性能灾难。

### 成绩防作弊

```java
@PostMapping("/scores")
public Result<ScoreVO> submitScore(@Valid @RequestBody ScoreSubmitDTO dto) {
    // 1. 基本合理性校验
    if (dto.getSpeed() > 300) throw new BusinessException(40001, "成绩数据异常");
    if (dto.getAccuracyRate() > 100 || dto.getAccuracyRate() < 0) throw ...;
    if (dto.getDuration() < 1) throw ...;

    // 2. 交叉校验：speed ≈ charCount * 60 / duration
    double expectedSpeed = dto.getCharCount() * 60.0 / dto.getDuration();
    if (Math.abs(expectedSpeed - dto.getSpeed()) > 1.0) throw ...;

    // 3. 频率限制：同一用户 5s 内只能提交一次
    String lockKey = "score:submit:" + currentUserId;
    if (!redisTemplate.opsForValue()
            .setIfAbsent(lockKey, "1", Duration.ofSeconds(5))) {
        throw new BusinessException(40002, "提交过于频繁");
    }

    // 4. 持久化 + 更新排行榜
}
```

### 个人统计概览（SQL）

```sql
-- 总览统计
SELECT
    COUNT(*) as total_practices,
    AVG(speed) as avg_speed,
    MAX(speed) as max_speed,
    AVG(accuracy_rate) as avg_accuracy,
    SUM(duration) as total_duration
FROM t_score
WHERE user_id = #{userId};

-- 近 30 天进步曲线（按天聚合）
SELECT
    DATE(created_at) as date,
    AVG(speed) as avg_speed,
    MAX(speed) as max_speed
FROM t_score
WHERE user_id = #{userId}
  AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at)
ORDER BY date;
```

---

## 项目分包结构

```
typetype-server/
├── src/main/java/com/typetype/
│   ├── TypetypeApplication.java
│   ├── common/
│   │   ├── result/              # Result<T>, PageResult<T>, ResultCode
│   │   ├── exception/           # BusinessException, GlobalExceptionHandler
│   │   └── config/              # RedisConfig, SecurityConfig, CorsConfig
│   ├── auth/
│   │   ├── controller/          # AuthController
│   │   ├── service/             # AuthService, JwtService
│   │   ├── dto/                 # LoginDTO, RegisterDTO, TokenVO
│   │   └── filter/              # JwtAuthenticationFilter
│   ├── text/
│   │   ├── controller/          # TextController
│   │   ├── service/             # TextService
│   │   ├── repository/          # TextRepository, TextSourceRepository
│   │   ├── entity/              # Text, TextSource
│   │   └── dto/                 # TextVO, TextSourceVO
│   ├── score/
│   │   ├── controller/          # ScoreController
│   │   ├── service/             # ScoreService, RankingService
│   │   ├── repository/          # ScoreRepository
│   │   ├── entity/              # Score
│   │   └── dto/                 # ScoreSubmitDTO, ScoreVO, RankingVO
│   └── user/
│       ├── controller/          # UserController
│       ├── service/             # UserService, UserStatsService
│       ├── repository/          # UserRepository
│       ├── entity/              # User
│       └── dto/                 # UserVO, UserStatsVO
├── src/main/resources/
│   ├── application.yml
│   ├── application-dev.yml
│   └── db/migration/            # Flyway 数据库版本管理
└── src/test/
```

---

## Python 客户端改造要点

改动可以控制得比较小，但建议严格沿用当前客户端的边界：

- QML / Adapter 不直接对接 Spring Boot 细节
- 仍然通过 `TextProvider` Port 隔离外部文本服务
- 仍然复用 `LoadTextUseCase -> TextSourceGateway` 这条应用层入口
- 具体是否“替换现有远程来源”还是“支持多个远程来源共存”，由 `TextSourceGateway` 演进来承接，不要把路由逻辑放回 QML / Adapter

### 1. 新增 SpringBootTextProvider

```python
# src/backend/integration/springboot_text_provider.py
from src.backend.ports.text_provider import TextProvider


class SpringBootTextProvider(TextProvider):
    """Spring Boot 文本服务，实现 TextProvider 协议。"""

    def __init__(self, api_client: ApiClient, base_url: str):
        self._api_client = api_client
        self._base_url = base_url

    def get_catalog(self) -> list[TextCatalogItem]:
        url = f"{self._base_url}/api/v1/text-sources"
        data = self._api_client.request("GET", url)
        # 解析为 TextCatalogItem 列表
        ...

    def fetch_text_by_key(self, source_key: str) -> str | None:
        url = f"{self._base_url}/api/v1/texts/random"
        data = self._api_client.request(
            "GET",
            url,
            params={"sourceKey": source_key},
        )
        if data is None:
            return None
        return data.get("data", {}).get("content")
```

### 2. `main.py` 最小改动注入方案

如果目标是**把当前远程文本服务整体切到 Spring Boot**，最小改动是直接替换 `RemoteTextProvider` 的注入位置，而不是在 `TextAdapter` / QML 增加判断：

```python
# main.py
springboot_provider = SpringBootTextProvider(
    api_client=api_client,
    base_url=os.environ.get("TYPETYPE_TEXT_API_BASE_URL", "http://localhost:8080"),
)
text_gateway = TextSourceGateway(
    runtime_config=runtime_config,
    text_provider=springboot_provider,
    local_text_loader=local_text_loader,
)
load_text_usecase = LoadTextUseCase(
    text_gateway=text_gateway,
    clipboard_reader=clipboard,
)
```

### 3. 如果要支持多个远程提供方共存

当前客户端代码里 `TextSourceGateway` 只依赖一个 `TextProvider`。  
如果后续要同时保留“旧远程来源 + Spring Boot 来源”，建议：

1. 先扩展 Application 层边界（例如让 Gateway 能识别 provider key）
2. 保持 QML / Adapter 无感
3. 让来源路由仍由 Application 层负责

不要直接在 QML 里拼 URL，也不要让 `TextAdapter` 承担业务路由。

### 4. RuntimeConfig 新增来源

```json
"springboot_random": {
    "label": "服务器随机",
    "has_ranking": true
}
```

如果需要更细粒度配置，可以进一步扩展 `RuntimeConfig`，但建议优先复用当前的 `base_url` / `api_timeout` 能力，保持配置面简洁。

### 5. 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `TYPETYPE_TEXT_API_BASE_URL` | 文本 API 地址 | `http://localhost:8080` |
| `TYPETYPE_SCORE_API_BASE_URL` | 成绩 API 地址 | `http://localhost:8080` |
| `TYPETYPE_API_TIMEOUT` | API 超时时间 (秒) | `20.0` |

---

## 面试话术建议

被问到"为什么做这个后端"时，按这个逻辑链回答：

1. 桌面端已有完整的打字 + 计分流程，但**文本依赖第三方**、**成绩纯本地**
2. Spring Boot 后端解决三个问题：**自主文本管理**、**成绩云端持久化 + 排行**、**用户体系**
3. 客户端采用六边形架构，通过 `TextProvider` 协议解耦，切换后端只需换注入 —— 体现**面向接口编程**
4. 后端用 Redis ZSET 做排行榜、预热 ID 池做随机文本、JWT 双 token 做认证 —— 每个选型都有**性能或安全层面的理由**
5. 成绩提交做交叉校验 + 频率限制 —— 体现**安全防御意识**

### 面试核心考点覆盖

| 考点 | 本项目覆盖 |
|------|------------|
| 分层架构 | Controller → Service → Repository，DTO/VO 分离 |
| 数据库建模 | ER 关系、字段类型选择、冗余字段取舍 |
| 索引设计 | 复合索引、覆盖索引、排序索引 |
| RESTful API | 资源命名、HTTP 方法语义、统一响应格式、错误码 |
| 认证鉴权 | JWT 双 token、Spring Security Filter Chain |
| 缓存设计 | Redis ZSET 排行榜、SET 随机文本池、缓存过期策略 |
| 并发控制 | Redis SETNX 频率限制、分布式锁 |
| 数据一致性 | 成绩交叉校验、幂等提交 |
| 安全防御 | 防作弊校验、BCrypt 密码加密、Token Rotation |
| SQL 优化 | 避免 `ORDER BY RAND()`、避免 `LENGTH()` 全表扫描 |

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-06 | 重命名为 SPRING_BOOT.md，整理结构 |
| 2026-03-21 | 添加文档链接，更新格式 |
| 2026-03-15 | 初始版本，完整后端设计方案 |
