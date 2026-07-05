# TypeType 大数据技术栈集成设计
<!-- 状态: draft | 创建: 2026-07-03 |

> 目标：在 typetype-server（Spring Boot）侧引入 Kafka + Flink + Redis，支撑实时排行、异常检测、用户趋势分析。
> 客户端保持轻量，仅调整成绩提交为异步模式。

---

## 目录

- [1. 业务场景分析](#1-业务场景分析)
- [2. 架构总览](#2-架构总览)
- [3. Kafka 设计](#3-kafka-设计)
- [4. Flink 设计](#4-flink-设计)
- [5. Redis 设计](#5-redis-设计)
- [6. 实施路径](#6-实施路径)
- [7. 面试要点](#7-面试要点)

---

## 1. 业务场景分析

### 数据产生场景

| 场景 | 数据量级 | 实时性要求 | 当前实现 | 异步化潜力 |
|:---|:---|:---|:---|:---|
| **打字输入事件** | 每字符 1 事件，高频 | **实时**（UI 反馈 <16ms） | 主线程直接处理 | ❌ 不可异步 |
| **字符统计累积** | 每字符 1 次 accumulate() | 准实时（批量 flush） | 内存累积 → SQLite 批量写 | ✅ 已异步 |
| **成绩提交** | 每局 1 次 POST | 用户可接受 1-3s | 同步 HTTP POST | ✅ **适合异步化** |
| **排行榜加载** | 1 次/查询，50 条/页 | 用户等待 <2s | 同步 HTTP GET | ✅ **可缓存+预加载** |
| **文本目录加载** | 1 次/查询 | 用户等待 | HTTP 请求 | ✅ 可缓存 |
| **薄弱字查询** | Top N | 用户等待 | SQLite 查询 | ✅ 已异步 |
| **分片进度持久化** | 每段完成 1 次写入 | 不阻塞打字 | JSON 文件写入 | ✅ 可异步 |

### 数据流全景

```
==================== TypeType 数据流全景 ====================

  [QML UI 层]
    │
    │  用户交互（打字、点击、快捷键）
    ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Bridge (QML 门面)                                      │
  │  属性代理 · 信号转发 · Slot 入口                         │
  └──────────┬──────────────────────────────┬───────────────┘
             │                              │
    ┌────────▼────────┐           ┌─────────▼─────────┐
    │  TypingAdapter   │           │  TextAdapter       │
    │  (打字统计适配)   │           │  (载文适配)         │
    └────────┬────────┘           └─────────┬─────────┘
             │                              │
  ┌──────────▼──────────┐    ┌──────────────▼──────────────┐
  │  TypingService      │    │  LoadTextUseCase            │
  │  (Domain: 计数/速度) │    │  (Application: 流程编排)     │
  │                     │    │                             │
  │  CharStatsService   │    │  TextSourceGateway          │
  │  (Domain: 单字统计)  │    │  (来源路由 + Port适配)       │
  └──────────┬──────────┘    └──────────────┬──────────────┘
             │                              │
             ▼                              ▼
  ┌──────────────────┐          ┌──────────────────────┐
  │ SQLite (本地)     │          │  typetype-server      │
  │ - char_stats      │          │  (Spring Boot)        │
  │ - session_history │          │                       │
  └──────────────────┘          │  ┌─────────────────┐  │
                                │  │ 新增: Kafka      │  │
                                │  │ 新增: Flink      │  │
                                │  │ 新增: Redis      │  │
                                │  └─────────────────┘  │
                                └──────────────────────┘
```

### 异步化候选（按优先级）

| 优先级 | 场景 | 方案 |
|:---|:---|:---|
| 高 | 成绩提交 | 同步 HTTP → Kafka 异步事件 |
| 高 | 排行榜查询 | DB 直查 → Redis Sorted Set 缓存 |
| 中 | 排行榜更新 | Flink 流处理实时更新 |
| 中 | 异常检测 | Flink ProcessFunction 实时检测 |
| 低 | 用户趋势 | Flink Tumbling Window 日聚合 |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        TypeType 客户端                           │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ 打字引擎  │  │ 载文模块  │  │ 排行榜    │                      │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘                      │
│        │             │             │                             │
│        ▼             ▼             ▼                             │
│  ┌─────────────────────────────────────┐                        │
│  │  HTTP Client (ApiClient)            │                        │
│  └─────────────────┬───────────────────┘                        │
└────────────────────┼────────────────────────────────────────────┘
                     │
                     │ REST / Kafka Producer
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     typetype-server                              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Spring Boot Web Layer                                   │   │
│  │  - AuthController (登录/注册)                              │   │
│  │  - TextController (文本 CRUD)                             │   │
│  │  - ScoreController (成绩提交/查询)                         │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │  Service Layer (新增 Kafka Producer)                      │   │
│  │  - ScoreService → Kafka Producer (成绩事件)               │   │
│  │  - StatsSyncService → Kafka Producer (统计同步)           │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                       │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │  Kafka                                                   │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │   │
│  │  │ score.      │ │ stats.      │ │ leaderboard.│         │   │
│  │  │ submitted   │ │ char-sync   │ │ updated     │         │   │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘         │   │
│  └─────────┼───────────────┼───────────────┼─────────────────┘   │
│            │               │               │                     │
│  ┌─────────▼───────────────▼───────────────▼─────────────────┐   │
│  │  Flink Cluster                                           │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │   │
│  │  │ Job 1:      │ │ Job 2:      │ │ Job 3:      │         │   │
│  │  │ 实时排行榜   │ │ 异常检测    │ │ 用户趋势     │         │   │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘         │   │
│  └─────────┼───────────────┼───────────────┼─────────────────┘   │
│            │               │               │                     │
│  ┌─────────▼───────────────▼───────────────▼─────────────────┐   │
│  │  Redis                                                   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │   │
│  │  │ 排行榜    │ │ 用户画像  │ │ 缓存      │ │ 异常计数  │     │   │
│  │  │ ZSET     │ │ HASH     │ │ STRING   │ │ STRING   │     │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  MySQL / PostgreSQL                                      │   │
│  │  - scores (成绩表)                                        │   │
│  │  - texts (文本表)                                         │   │
│  │  - users (用户表)                                         │   │
│  │  - user_trend_daily (趋势表，新增)                         │   │
│  │  - anomalies (异常记录表，新增)                             │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Kafka 设计

### 3.1 Topic 总览

| Topic | 分区数 | 副本 | 保留策略 | 生产者 | 消费者 |
|:---|:---|:---|:---|:---|:---|
| `typetype.score.submitted` | 12 | 3 | 7 天 | 客户端 ScoreSubmitProducer | 服务端 ScoreIngestionConsumer |
| `typetype.stats.char-sync` | 12 | 3 | 30 天 | 客户端 CharStatsSyncProducer | 服务端 CharStatsMergeConsumer |
| `typetype.score.persisted` | 12 | 3 | 3 天 | 服务端 ScoreIngestionConsumer | 客户端 ScoreConfirmConsumer |
| `typetype.leaderboard.updated` | 6 | 3 | 1 天 | 服务端 ScoreIngestionConsumer | 客户端 LeaderboardCacheInvalidator |

### 3.2 分区策略

| Topic | 分区键 | 保证 |
|:---|:---|:---|
| `score.submitted` | `userId` | 同一用户成绩有序 |
| `stats.char-sync` | `userId` | 同一用户统计有序 |
| `score.persisted` | `userId` | 确认与提交同分区 |
| `leaderboard.updated` | `textId` | 同一文本通知有序 |

### 3.3 消息 Schema

#### `typetype.score.submitted`

```json
{
  "messageId": "uuid-v7",
  "userId": "string",
  "textId": 42,
  "clientTextId": "hash-string",
  "timestamp": "2026-07-03T10:30:00+08:00",
  "payload": {
    "charCount": 150,
    "wrongCharCount": 3,
    "backspaceCount": 5,
    "correctionCount": 2,
    "keyStrokeCount": 180,
    "timeSeconds": 45.2
  },
  "metadata": {
    "clientVersion": "0.1.0",
    "platform": "linux",
    "retryCount": 0
  }
}
```

#### `typetype.stats.char-sync`

```json
{
  "messageId": "uuid-v7",
  "userId": "string",
  "timestamp": "2026-07-03T10:30:00+08:00",
  "chars": [
    {
      "char": "的",
      "totalCount": 1500,
      "errorCount": 30,
      "minTypeMs": 85.2,
      "maxTypeMs": 520.0,
      "avgTypeMs": 120.5
    }
  ]
}
```

#### `typetype.score.persisted`

```json
{
  "messageId": "uuid-v7",
  "userId": "string",
  "originalMessageId": "对应submitted的messageId",
  "status": "persisted",
  "scoreId": 1001,
  "derived": {
    "speed": 199.1,
    "keyStrokeRate": 3.98,
    "codeLength": 1.2,
    "accuracyRate": 98.0,
    "effectiveSpeed": 195.1
  },
  "timestamp": "2026-07-03T10:30:01+08:00"
}
```

### 3.4 幂等性设计

| 层级 | 机制 |
|:---|:---|
| 生产者 | `enable.idempotence=true` + `acks=all` |
| 消息级 | `messageId` (UUID v7) 作为业务幂等键 |
| 消费者 | 成绩：`INSERT ... ON CONFLICT DO NOTHING`；统计：upsert |
| 本地重试 | 客户端 SQLite 重试队列，确认后删除 |

### 3.5 消息大小估算

| Topic | 单条大小 | 日峰值 QPS | 日数据量 |
|:---|:---|:---|:---|
| `score.submitted` | ~500B | 100 | ~4.3MB |
| `stats.char-sync` | ~50KB | 5 | ~21.6MB |
| `score.persisted` | ~300B | 100 | ~2.6MB |
| `leaderboard.updated` | ~200B | 50 | ~0.9MB |

总量级很小，单 broker 足以支撑。

---

## 4. Flink 设计

### 4.1 Job 1: 实时排行榜

#### 拓扑

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐     ┌──────────────┐
│  Kafka      │     │  Source:        │     │  KeyBy:          │     │  SlidingWindow:   │     │  Sink:       │
│  topic:     │────▶│  ScoreEvent     │────▶│  text_id         │────▶│  1min / 10s slide │────▶│  Redis       │
│  scores     │     │  Deserializer   │     │  (rebalance→hash)│     │  TopNBySpeed      │     │  ZADD        │
└─────────────┘     └─────────────────┘     └──────────────────┘     └───────────────────┘     └──────────────┘
```

#### 算子链

| 算子 | 类型 | 说明 |
|:---|:---|:---|
| Source | `KafkaSource<ScoreEvent>` | 从 `scores` topic 消费 |
| Map | `RichMapFunction` | 派生 `speed`, `effectiveSpeed` |
| Filter | `FilterFunction` | 过滤无效成绩（`time < 5s` 或 `charCount < 10`） |
| KeyBy | `KeySelector` | 按 `text_id` 分区 |
| Window | `SlidingEventTimeWindows` | 窗口 60s，滑动 10s |
| Aggregate | `AggregateFunction` | 维护 TopN 有序列表（N=50），按 `effectiveSpeed` 降序 |
| Process | `ProcessWindowFunction` | 附加窗口元信息 |
| Sink | `RedisSortedSetSink` | `ZADD leaderboard:{text_id} {score} {user_id}` |

#### 窗口配置

```
窗口类型:  SlidingEventTimeWindows
窗口大小:  60 秒
滑动步长:  10 秒
时间语义:  EventTime
水位线:    BoundedOutOfOrdernessWatermarks，允许 5s 乱序
迟到数据:  AllowedLateness(30s)
```

---

### 4.2 Job 2: 异常检测

#### 拓扑

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│  Kafka      │     │  Source:         │     │  KeyBy:          │     │  ProcessFunction:        │
│  topic:     │────▶│  ScoreEvent      │────▶│  user_id         │────▶│  AnomalyDetector         │
│  scores     │     │  Deserializer    │     │                  │     │  (状态机检测突变)          │
└─────────────┘     └──────────────────┘     └──────────────────┘     └────────────┬─────────────┘
                                                                                   │
                                                                      ┌────────────┼────────────┐
                                                                      ▼            ▼            ▼
                                                                ┌──────────┐ ┌──────────┐ ┌──────────┐
                                                                │  discard │ │  Kafka   │ │  Redis   │
                                                                │          │ │ anomalies│ │ 计数器    │
                                                                └──────────┘ └──────────┘ └──────────┘
```

#### 异常检测逻辑

```java
// 状态定义
ValueState<Double>  lastSpeed;        // 上一次速度
ValueState<Double>  lastAccuracy;     // 上一次准确率
ListState<Double>   recentSpeeds;     // 最近 10 次速度
ListState<Double>   recentAccuracies; // 最近 10 次准确率

// 检测规则（任一触发即异常）
// 1. 速度突变: |current - avg(recent)| > 2 * stddev 且 > 30 字/分
// 2. 准确率突变: |current - avg(recent)| > 2 * stddev 且 > 15%
// 3. 不可能成绩: speed > 300 字/分 或 accuracy > 99.5% 且 charCount > 100
// 4. 时间异常: time < 3s 且 charCount > 50
```

#### 窗口配置

```
窗口类型:  无固定窗口（KeyedProcessFunction，事件驱动）
状态清理:  状态 TTL 7 天无活动后自动清理
```

---

### 4.3 Job 3: 用户进步趋势

#### 拓扑

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│  Kafka      │     │  Source:         │     │  KeyBy:          │     │  TumblingWindow:         │
│  topic:     │────▶│  ScoreEvent      │────▶│  user_id         │────▶│  1 day                   │
│  scores     │     │  Deserializer    │     │                  │     │  UserProgressAggregator  │
└─────────────┘     └──────────────────┘     └──────────────────┘     └────────────┬─────────────┘
                                                                                   │
                                                                      ┌────────────┼────────────┐
                                                                      ▼            ▼            ▼
                                                                ┌──────────┐ ┌──────────┐ ┌──────────┐
                                                                │  Redis   │ │  MySQL   │ │  Kafka   │
                                                                │  用户    │ │  趋势表  │ │  trends  │
                                                                │  画像    │ │          │ │          │
                                                                └──────────┘ └──────────┘ └──────────┘
```

#### 聚合指标

```
每窗口累积:
  avg_speed, max_speed, avg_accuracy
  total_chars, total_sessions, text_diversity

趋势计算（跨窗口状态）:
  speed_trend_7d     = linearRegression(last7DaysAvgSpeed)  // 斜率
  speed_wow_change   = (this_week - last_week) / last_week  // 周环比

  progress_level:
    speed_trend > 5 且 accuracy_trend > 0  → "accelerating"
    speed_trend > 0                        → "improving"
    speed_trend ≈ 0                        → "plateau"
    speed_trend < 0                        → "declining"
```

#### 窗口配置

```
窗口类型:  TumblingEventTimeWindows
窗口大小:  1 天
水位线:    BoundedOutOfOrdernessWatermarks，允许 1 小时乱序
迟到数据:  AllowedLateness(24h)
```

---

### 4.4 通用配置

#### 状态后端

```
状态后端:  RocksDBStateBackend
  state.backend: rocksdb
  state.backend.incremental: true        # 增量 Checkpoint
  state.backend.rocksdb.block.cache-size: 256mb
  state.backend.rocksdb.writebuffer.size: 128mb

选型理由:
  - Job 2 需要为每个 user_id 维护 ListState
  - Job 3 需要跨窗口的 7 天滑动状态
  - 增量 Checkpoint 减少数据传输量
```

#### Checkpoint 策略

```
checkpoint.interval              = 60s
checkpoint.mode                  = EXACTLY_ONCE
checkpoint.min-pause             = 30s
checkpoint.timeout               = 600s
checkpoint.unaligned.enabled     = true
state.checkpoints.num-retained   = 3
restart-strategy                 = exponential-delay (1s ~ 60s, backoff 2.0)
```

#### 并行度

```
┌──────────────┬──────────┬───────────────────────────────────┐
│  组件         │  并行度   │  说明                             │
├──────────────┼──────────┼───────────────────────────────────┤
│  Kafka Source │  4       │  与 Kafka 分区数对齐               │
│  Map/Filter  │  4       │  与 Source 链化                    │
│  Window Agg  │  4       │  每个实例处理部分 key group         │
│  Redis Sink  │  4       │  连接池 = parallelism × 4         │
│  JDBC Sink   │  2       │  DB 连接瓶颈                      │
├──────────────┴──────────┴───────────────────────────────────┤
│  JobManager: 1 instance, heap 2g                           │
│  TaskManager: 2 instances, heap 4g each, slots=4           │
└────────────────────────────────────────────────────────────┘
```

#### Sink 语义保证

| Sink | 语义 | 机制 |
|:---|:---|:---|
| Kafka Sink | EXACTLY_ONCE | 两阶段提交 + 事务 producer |
| Redis Sink | AT_LEAST_ONCE | 幂等 ZADD/HSET 覆盖写 |
| JDBC Sink | EXACTLY_ONCE | UPSERT 幂等 |

---

## 5. Redis 设计

### 5.1 数据结构清单

| Key 模式 | 类型 | TTL | 说明 |
|:---|:---|:---|:---|
| `lb:text:{textId}:speed` | ZSET | 7d + rand | 综合排行（effectiveSpeed） |
| `lb:text:{textId}:raw_speed` | ZSET | 7d + rand | 纯速度排行 |
| `lb:text:{textId}:accuracy` | ZSET | 7d + rand | 准确率排行 |
| `lb:text:{textId}:keystroke` | ZSET | 7d + rand | 击键频率排行 |
| `lb:text:{textId}:empty` | STRING | 5min | 空值标记（防穿透） |
| `user_best:text:{textId}` | HASH | 7d | 用户最佳成绩映射 |
| `catalog:sources` | STRING | 30min | 来源目录 JSON |
| `catalog:texts:{sourceKey}` | STRING | 10min | 文本列表 JSON |
| `text:content:{textId}` | STRING | 1h | 文本内容 JSON |
| `session:user:{userId}` | HASH | 24h | 用户信息缓存 |
| `session:token:{hash}` | STRING | JWT TTL | Token 校验/黑名单 |
| `queue:score_submit` | LIST | 无 | 成绩提交队列 |
| `lock:lb:text:{textId}` | STRING | 5s | 排行榜回填锁 |
| `anomaly:count:{userId}:{date}` | STRING | 7d | 异常日计数 |
| `user:profile:{userId}` | HASH | 30d | 用户趋势画像 |

### 5.2 排行榜详细设计

#### Score 字段选择

使用 `effectiveSpeed` 作为主排序维度：
- 综合了速度和准确率: `speed * accuracyRate / 100`
- 与现有 API 契约一致
- 避免"刷速度牺牲准确率"的策略性行为

#### 多维度排行

| Key | Score | 用途 |
|:---|:---|:---|
| `lb:text:{textId}:speed` | effectiveSpeed | 综合排行（默认） |
| `lb:text:{textId}:raw_speed` | speed | 纯速度排行 |
| `lb:text:{textId}:accuracy` | accuracyRate | 准确率排行 |
| `lb:text:{textId}:keystroke` | keyStroke | 击键频率排行 |

#### 排行榜更新流程

```
成绩提交成功后:
  1. DB 写入 score 记录
  2. 检查 user_best:text:{textId} 中该用户旧记录
  3. 若新成绩更优:
     a. ZREM 旧 member（若存在）
     b. ZADD lb:text:{textId}:speed {effectiveSpeed} {userId}:{scoreId}
     c. ZADD 其他维度 Sorted Set
     d. HSET user_best:text:{textId} {userId} "{scoreId}:{effectiveSpeed}"
  4. EXPIRE 各 key 7 天 + 随机偏移
```

#### 查询接口

```java
// Spring Boot 服务端
@GetMapping("/api/v1/texts/{textId}/leaderboard")
public Result getLeaderboard(
    @PathVariable Long textId,
    @RequestParam(defaultValue = "speed") String sortBy,
    @RequestParam(defaultValue = "1") int page,
    @RequestParam(defaultValue = "50") int size
) {
    String redisKey = "lb:text:" + textId + ":" + sortBy;
    long start = (page - 1) * size;
    long end = start + size - 1;
    Set<ZSetOperations.TypedTuple<String>> entries = redisTemplate.opsForZSet()
        .reverseRangeWithScores(redisKey, start, end);
    Long total = redisTemplate.opsForZSet().zCard(redisKey);
    // 组装返回...
}
```

### 5.3 缓存防护策略

#### 缓存穿透

```
场景: 查询不存在的 textId 排行榜
方案: 布隆过滤器 + 空值缓存

1. 启动时加载所有有效 textId 到布隆过滤器
2. 查询时: 若布隆过滤器判定不存在 → 直接返回空
3. Redis miss 查 DB → 若 DB 也为空 → 缓存空标记 (TTL 5min)
```

#### 缓存击穿

```
场景: 热门文本排行榜 key 过期瞬间，并发请求穿透
方案: 逻辑过期 + 分布式锁

写入时同时存过期时间戳，读取时:
- 真正 miss → 加锁查 DB 回填
- 逻辑过期 → 异步刷新，返回旧数据不阻塞

分布式锁:
  SET lock:lb:text:{textId} {uuid} NX EX 5
```

#### 缓存雪崩

```
场景: 大量 key 同时过期
方案: 过期时间随机化

baseTTL = 604800 (7天)
randomOffset = random(0, 3600) (0~1小时)
actualTTL = baseTTL + randomOffset
```

### 5.4 命名规范

```
{业务域}:{实体}:{标识}[:{子标识}][:{维度}]

前缀对照:
  lb:          排行榜
  user_best:   用户最佳
  catalog:     文本目录
  text:        文本内容
  session:     用户会话
  queue:       异步队列
  lock:        分布式锁
  anomaly:     异常检测
  user:        用户画像
```

---

## 6. 实施路径

### Phase 1: Kafka + Redis 基础（2 周）

**目标**: 成绩提交异步化 + 排行榜 Redis 缓存

| 任务 | 技术点 |
|:---|:---|
| Docker Compose 搭建 Kafka + Redis | 容器编排、网络配置 |
| Spring Boot 集成 Kafka Producer | `spring-kafka`、序列化、分区策略 |
| 成绩提交改为异步 | REST → Kafka 事件，客户端重试队列 |
| 排行榜 Redis 缓存 | Sorted Set、多维度排行、缓存防护 |
| Flink 集成 Kafka Consumer | 消费成绩事件、写入 Redis |

**面试可聊**: 消息队列选型、分区策略、缓存穿透/击穿/雪崩

### Phase 2: Flink 流处理（2 周）

**目标**: 实时排行榜 + 异常检测

| 任务 | 技术点 |
|:---|:---|
| Flink 集群搭建 | Standalone/YARN 模式、RocksDB 状态后端 |
| Job 1: 实时排行榜 | Sliding Window、AggregateFunction、Redis Sink |
| Job 2: 异常检测 | KeyedProcessFunction、状态机、侧输出流 |
| 监控指标 | Prometheus + Grafana、自定义 Metric |

**面试可聊**: 窗口类型、Watermark、Exactly-Once 语义、状态管理

### Phase 3: 用户趋势 + 优化（1 周）

**目标**: 用户进步趋势分析 + 性能优化

| 任务 | 技术点 |
|:---|:---|
| Job 3: 用户趋势 | Tumbling Window、跨窗口状态、线性回归 |
| 趋势表设计 | MySQL user_trend_daily 表、索引优化 |
| 性能调优 | 并行度、Checkpoint 间隔、RocksDB 参数 |
| 文档完善 | 架构图、API 文档、运维手册 |

**面试可聊**: 流批一体、状态后端选型、Flink 调优

---

## 7. 面试要点

### Kafka

| 问题 | 回答要点 |
|:---|:---|
| 为什么用 Kafka 而不是直接 HTTP？ | 解耦、削峰、异步重试、事件溯源 |
| 分区策略怎么设计？ | 按 userId 保证用户有序，按 textId 保证排行榜有序 |
| 如何保证消息不丢失？ | 生产者 acks=all + 消费者手动提交 offset |
| 如何保证幂等？ | UUID v7 业务幂等键 + DB UPSERT |
| 消息积压怎么办？ | 增加消费者实例、调整分区数、批量消费 |

### Flink

| 问题 | 回答要点 |
|:---|:---|
| 为什么用 Flink 而不是 Spark Streaming？ | 真正的流处理、低延迟、状态管理、Exactly-Once |
| Sliding 和 Tumbling Window 的区别？ | Sliding 有重叠（排行榜需要平滑过渡），Tumbling 无重叠（日聚合） |
| Watermark 是什么？怎么处理乱序？ | 衡量事件时间进度，BoundedOutOfOrderness 允许延迟 |
| 状态后端为什么选 RocksDB？ | 大状态支持、增量 Checkpoint、磁盘友好 |
| Exactly-Once 怎么实现？ | Kafka 两阶段提交 + Checkpoint Barrier 对齐 |

### Redis

| 问题 | 回答要点 |
|:---|:---|
| 为什么用 Sorted Set 做排行榜？ | O(log N) 插入、O(log N + M) 范围查询、天然排序 |
| 缓存穿透/击穿/雪崩怎么防护？ | 布隆过滤器、逻辑过期+分布式锁、TTL 随机化 |
| Redis 和 MySQL 数据一致性？ | Cache-Aside 模式、先更新 DB 再删缓存、异步补偿 |
| Redis 持久化策略？ | RDB 快照 + AOF 追加、混合持久化 |

### 架构设计

| 问题 | 回答要点 |
|:---|:---|
| 为什么不在客户端做大数据处理？ | 客户端资源有限、数据孤岛、无法跨用户分析 |
| 如何保证系统可用性？ | Kafka 解耦 + Redis 降级 + DB 兜底 |
| 数据量增长怎么办？ | Kafka 分区扩展、Flink 并行度调整、Redis Cluster |
| 如何监控系统健康？ | Flink Metrics + Prometheus + Grafana、Kafka Manager |

---

## 附录: 技术选型对比

| 技术 | 替代方案 | 选择理由 |
|:---|:---|:---|
| Kafka | RabbitMQ | 高吞吐、持久化、流处理生态 |
| Flink | Spark Streaming | 真正流处理、低延迟、状态管理 |
| Redis | Memcached | 数据结构丰富（Sorted Set）、持久化 |
| RocksDB | HashTableStateBackend | 大状态支持、增量 Checkpoint |
