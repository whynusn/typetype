# TypeType Spring Boot 后端设计方案

> 最后更新：2026-03-21
>
> 基于对 typetype 桌面客户端的完整架构分析，设计一套面试级别的 Spring Boot 后端服务。

---

## 相关文档

- [guide.md](./guide.md) - AI Agent 转化规划指南
- [roadmap.md](./roadmap.md) - 项目功能路线图
- [AGENTS.md](../AGENTS.md) - 项目开发指南

---

## 一、当前客户端架构分析

### 1.1 整体架构

typetype 是一个 **PySide6 + QML 的跨平台打字练习工具**，Python 端采用了分层 + Ports & Adapters 架构：

```
QML UI → Presentation (Bridge + Adapters)
           → Application (UseCase + Gateway)
           → Domain / Ports
           → Integration / Infrastructure
```

### 1.2 核心领域对象

| 实体 | 字段 | 位置 |
|---|---|---|
| `SessionStat` | time, key_stroke_count, char_count, wrong_char_count, date + 计算属性(speed, keyStroke, codeLength, accuracy, effectiveSpeed) | `src/backend/models/entity/session_stat.py` |
| `CharStat` | char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen + 计算属性(avg_ms, error_rate) + merge() | `src/backend/models/entity/char_stat.py` |
| `TextSource` (配置) | key, label, type(network/local), url/local_path | `src/backend/config/runtime_config.py` |
| `ScoreSummaryDTO` / `HistoryRecordDTO` | DTO 层，从 ScoreData 映射 | `src/backend/models/dto/score_dto.py` |

### 1.3 关键端口协议

| 协议 | 方法签名 | 位置 |
|---|---|---|
| `TextFetcher` | `fetch_text(url: str) → str \| None` | `application/ports/text_fetcher.py` |
| `LocalTextLoader` | `load_text(path: str) → str \| None` | `application/ports/local_text_loader.py` |
| `ClipboardReader` | `text() → str` | `application/ports/clipboard.py` |
| `ClipboardWriter` | `setText(text: str) → None` | `application/ports/clipboard.py` |

### 1.4 数据流

```
用户点击"载文"
  → QML 调用 appBridge.requestLoadText(sourceKey)
    → Bridge 根据 RuntimeConfig 判断 type=network/local
      → network: 创建 LoadTextWorker → QThreadPool 异步执行
→ LoadTextUseCase.load(source_id)
→ TextFetcher.fetch_text(url)     [当前实现: SaiWenTextFetcher]
→ ApiClient.request("POST", url, json=payload)
→ httpx.Client.request()      [HTTP 请求]
→ local: 同步执行
→ LoadTextUseCase.load(source_id)
          → LocalTextLoader.load_text(path) [当前实现: QtLocalTextLoader]
    → 成功: textLoaded.emit(text) → QML 显示
    → 失败: textLoadFailed.emit(message) → QML 提示

用户打字完成
  → TypingAdapter 结束会话 + typingEnded.emit()
  → TypingUseCase.build_history_record(score_data)
  → historyRecordUpdated.emit(record) → QML 本地维护历史列表
```

### 1.5 依赖注入（main.py）

```python
api_client = ApiClient(timeout=runtime_config.api_timeout)
sai_wen_text_fetcher = SaiWenTextFetcher(api_client=api_client)
local_text_loader = QtLocalTextLoader()
text_gateway = TextGateway(
    runtime_config=runtime_config,
    text_fetchers={"sai_wen": sai_wen_text_fetcher},
    clipboard=clipboard,
    local_text_loader=local_text_loader,
)
load_text_usecase = LoadTextUseCase(gateway=text_gateway)
typing_usecase = TypingUseCase(score_gateway=ScoreGateway(clipboard=clipboard))
bridge = Bridge(
    text_adapter=text_adapter,
    typing_adapter=typing_adapter,
)
```

### 1.6 当前痛点（= Spring Boot 要解决的问题）

1. **文本来源不可控** — 仅依赖第三方极速杯 API
2. **成绩纯本地** — 无持久化、无排行、无历史同步
3. **无用户体系** — 无认证、无个人数据管理

### 1.7 网络错误体系

```python
NetworkError (基类)
├── NetworkTimeoutError     # 请求超时
├── NetworkHttpStatusError  # HTTP 状态码错误 (含 status_code)
├── NetworkDecodeError      # 响应解析错误
└── NetworkRequestError     # 请求发送错误
```

客户端 `LoadTextUseCase` 已对网络异常做了分类映射和用户友好提示。

---

## 二、Spring Boot 后端架构设计

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     typetype Client (PySide6)                │
│  RuntimeConfig 增加 springboot 来源                           │
│  新增 SpringBootTextService (实现 TextFetcher)                │
│  复用 ApiClient (httpx)                                      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (JSON)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Spring Boot Backend (分层架构)                    │
│                                                              │
│  ┌─── Controller ──┐  ┌── Service ──┐  ┌── Repository ──┐   │
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

### 2.2 技术选型

| 层面 | 选型 | 选型依据 |
|---|---|---|
| **认证** | Spring Security + JWT (双 token) | access_token 15min + refresh_token 7d，refresh 时做 token rotation 防重放 |
| **缓存** | Redis | 排行榜用 ZSET (`ZREVRANGE`)；随机文本用 `SRANDMEMBER` 预加载 ID 池；热门文本缓存 |
| **ORM** | MyBatis-Plus (推荐面试) 或 Spring Data JPA | 国内面试 MyBatis 加分，能聊 SQL 优化 |
| **参数校验** | `@Valid` + `javax.validation` | 全局异常处理器 `@RestControllerAdvice` 捕获 |
| **接口文档** | SpringDoc (OpenAPI 3) | 前后端对接效率，面试体现协作意识 |
| **日志** | SLF4J + Logback，MDC 链路追踪 | 每个请求带 traceId，面试聊日志排查能力 |
| **限流** | Guava RateLimiter 或 Redis + Lua | 防刷成绩接口，面试聊分布式限流 |
| **数据库版本** | Flyway | 数据库 migration 版本管理 |

---

## 三、数据库设计

### 3.1 ER 模型

```
t_user (1) ──── (N) t_score (N) ──── (1) t_text (N) ──── (1) t_text_source
```

### 3.2 DDL

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

### 3.3 索引设计说明

| 索引 | 服务场景 | 说明 |
|---|---|---|
| `idx_username` | 登录查询 | 用户名唯一索引，登录时快速定位 |
| `idx_source_difficulty` | 随机选文 | 复合索引：按来源 + 难度筛选文本 |
| `idx_user_created` | 个人历史记录 | 覆盖"我的记录"查询，DESC 支持最近优先 |
| `idx_speed` | 排行榜 | 全局速度排行快速查询 |
| `idx_created_at` | 时间范围查询 | 支持日/周/月维度的统计聚合 |

### 3.4 扩展考虑

- `t_score` 量大后可按 `created_at` 做**按月分区**，或按 `user_id` 做分表
- `t_text.char_count` 冗余存储，避免 `LENGTH(content)` 全表扫描

---

## 四、API 设计

### 4.1 接口列表

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

### 4.2 统一响应格式

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

### 4.3 业务错误码

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

### 4.4 关键接口详细设计

#### POST /api/v1/auth/login

```json
// Request
{
  "username": "typist_wang",
  "password": "your_password"
}

// Response 200
{
  "code": 200,
  "data": {
    "accessToken": "eyJhbGciOi...",
    "refreshToken": "eyJhbGciOi...",
    "expiresIn": 900,
    "user": {
      "id": 1,
      "username": "typist_wang",
      "nickname": "王同学"
    }
  }
}
```

#### GET /api/v1/texts/random?sourceKey=cet4

```json
// Response 200
{
  "code": 200,
  "data": {
    "id": 42,
    "title": "CET-4 Vocabulary Practice #42",
    "content": "这是一段练习文本内容...",
    "charCount": 200,
    "sourceKey": "cet4",
    "difficulty": 3
  }
}
```

#### POST /api/v1/scores

```json
// Request (需要 Authorization: Bearer <token>)
{
  "textId": 42,
  "speed": 123.45,
  "effectiveSpeed": 120.18,
  "keyStroke": 6.7,
  "codeLength": 2.15,
  "accuracyRate": 97.35,
  "charCount": 200,
  "wrongCharCount": 5,
  "duration": 97.56
}

// Response 201
{
  "code": 200,
  "data": {
    "id": 1001,
    "rank": 42,
    "personalBest": false
  }
}
```

#### GET /api/v1/users/me/stats

```json
// Response 200
{
  "code": 200,
  "data": {
    "totalPractices": 156,
    "avgSpeed": 98.7,
    "maxSpeed": 145.2,
    "avgAccuracy": 96.3,
    "totalDuration": 18720.5,
    "recentTrend": [
      { "date": "2026-03-01", "avgSpeed": 95.2, "maxSpeed": 110.0 },
      { "date": "2026-03-02", "avgSpeed": 97.8, "maxSpeed": 125.3 },
      { "date": "2026-03-03", "avgSpeed": 101.5, "maxSpeed": 132.1 }
    ]
  }
}
```

---

## 五、核心亮点设计

### 5.1 排行榜（Redis ZSET）

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

### 5.2 随机文本（避免慢查询）

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

### 5.3 成绩防作弊

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

### 5.4 个人统计概览

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

## 六、项目分包结构

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

## 七、Python 客户端改造要点

改动极小，这是现有六边形架构的红利。

### 7.1 新增 SpringBootTextService

```python
# src/backend/services/springboot_text_service.py
class SpringBootTextService:
    """Spring Boot 文本服务，实现 TextFetcher 协议。"""

    def __init__(self, api_client: ApiClient, base_url: str):
        self._api_client = api_client
        self._base_url = base_url

    def fetch_text(self, source_id: str) -> str | None:
        url = f"{self._base_url}/api/v1/texts/random"
        data = self._api_client.request("GET", url, params={"sourceKey": source_id})
        if data is None:
            last_error = self._api_client.last_error
            if last_error:
                raise last_error
            return None
        return data.get("data", {}).get("content")
```

### 7.2 main.py 注入切换

```python
springboot_service = SpringBootTextService(
    api_client=api_client,
    base_url=os.environ.get("TYPETYPE_TEXT_API_BASE_URL", "http://localhost:8080"),
)
text_gateway = TextGateway(
    runtime_config=runtime_config,
    text_fetchers={"springboot": springboot_service},
    clipboard=clipboard,
    local_text_loader=local_text_loader,
)
load_text_usecase = LoadTextUseCase(gateway=text_gateway)
```

### 7.3 RuntimeConfig 新增来源

```python
"springboot_random": {
    "label": "服务器随机",
    "type": "network",
    "url": "http://localhost:8080/api/v1/texts/random",
}
```

### 7.4 环境变量配置

| 变量名 | 说明 | 默认值 |
|---|---|---|
| `TYPETYPE_TEXT_API_BASE_URL` | 文本 API 地址 | `http://localhost:8080` |
| `TYPETYPE_SCORE_API_BASE_URL` | 成绩 API 地址 | `http://localhost:8080` |
| `TYPETYPE_API_TIMEOUT` | API 超时时间 (秒) | `20.0` |

---

## 八、面试话术建议

被问到"为什么做这个后端"时，按这个逻辑链回答：

1. 桌面端已有完整的打字 + 计分流程，但**文本依赖第三方**、**成绩纯本地**
2. Spring Boot 后端解决三个问题：**自主文本管理**、**成绩云端持久化 + 排行**、**用户体系**
3. 客户端采用六边形架构，通过 `TextFetcher` 协议解耦，切换后端只需换注入 —— 体现**面向接口编程**
4. 后端用 Redis ZSET 做排行榜、预热 ID 池做随机文本、JWT 双 token 做认证 —— 每个选型都有**性能或安全层面的理由**
5. 成绩提交做交叉校验 + 频率限制 —— 体现**安全防御意识**

### 面试核心考点覆盖

| 考点 | 本项目覆盖 |
|---|---|
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
| 2026-03-21 | 添加文档链接，更新格式 |
| 2026-03-15 | 初始版本，完整后端设计方案 |
