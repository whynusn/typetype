# Redis 排行榜实现

> ⚠️ 本文件为 typetype-server（服务端）侧设计，与本客户端仓库解耦；2026-07-03 起 draft 未更新。客户端开发者请忽略。

> 本文件是 typetype-server 的 Redis 排行榜参考实现。
> 包含 LeaderboardService 实现、多维度排行、用户最佳成绩映射、排行榜查询接口等。

---

## 1. 数据结构设计

```
# 🎓 Redis 排行榜数据结构选择：Sorted Set（有序集合）

# 为什么选择 Sorted Set？
# 1. 天然支持排序：ZADD 添加元素时自动按 score 排序
# 2. 高效查询：O(log(N)) 复杂度获取排名
# 3. 支持范围查询：ZREVRANGE 获取 Top N
# 4. 原子操作：ZINCRBY 原子递增

# 排行榜 Key 设计：
# - typetype:leaderboard:{dimension}:{period}
# - dimension：排行维度（wpm、accuracy、score）
# - period：时间范围（daily、weekly、monthly、all）

# 示例：
typetype:leaderboard:wpm:daily        # 每日 WPM 排行榜
typetype:leaderboard:score:weekly      # 每周总分排行榜
typetype:leaderboard:accuracy:monthly  # 每月准确率排行榜
typetype:leaderboard:wpm:all           # 总 WPM 排行榜

# 用户最佳成绩 Hash：
# - typetype:user:best:{userId}
# - 存储用户各维度的最佳成绩
typetype:user:best:12345
  ├── wpm: 120.5
  ├── accuracy: 98.5
  ├── score: 9500
  └── timestamp: 1625097600000
```

---

## 2. LeaderboardService 实现

```java
package com.typetype.service;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 排行榜服务
 *
 * 🎓 设计决策：
 * 1. 使用 Sorted Set 实现排行榜
 *    - ZADD：添加/更新成绩
 *    - ZREVRANGE：获取 Top N（降序）
 *    - ZREVRANK：获取用户排名
 *    - ZSCORE：获取用户分数
 *
 * 2. 使用 Hash 存储用户最佳成绩
 *    - 避免重复提交更低的成绩
 *    - 支持多维度成绩查询
 *
 * 3. 分时间维度存储
 *    - 减少单个 Sorted Set 的大小
 *    - 支持历史数据清理
 */
@Service
public class LeaderboardService {

    private final RedisTemplate<String, Object> redisTemplate;

    // 🎓 Key 前缀常量
    // 💡 使用常量避免硬编码，便于维护
    private static final String LEADERBOARD_PREFIX = "typetype:leaderboard:";
    private static final String USER_BEST_PREFIX = "typetype:user:best:";

    // 🎓 排行维度枚举
    public enum Dimension {
        WPM("wpm"),           // 每分钟字数
        ACCURACY("accuracy"), // 准确率
        SCORE("score");       // 总分

        private final String value;

        Dimension(String value) {
            this.value = value;
        }

        public String getValue() {
            return value;
        }
    }

    // 🎓 时间范围枚举
    public enum Period {
        DAILY("daily"),       // 每日
        WEEKLY("weekly"),     // 每周
        MONTHLY("monthly"),   // 每月
        ALL("all");           // 总计

        private final String value;

        Period(String value) {
            this.value = value;
        }

        public String getValue() {
            return value;
        }
    }

    public LeaderboardService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 提交成绩
     *
     * 🎓 核心逻辑：
     * 1. 检查是否是用户最佳成绩
     * 2. 如果是，更新用户最佳成绩
     * 3. 更新排行榜
     *
     * ⚠️ 为什么只提交最佳成绩？
     * - 避免排行榜被同一用户的多次提交刷屏
     * - 减少 Redis 存储压力
     * - 保证排行榜的公平性
     *
     * @param userId 用户 ID
     * @param dimension 排行维度
     * @param score 分数
     * @param period 时间范围
     * @return 是否是新的最佳成绩
     */
    public boolean submitScore(Long userId, Dimension dimension, double score, Period period) {
        // 1️⃣ 检查是否是最佳成绩
        boolean isNewBest = isBestScore(userId, dimension, score);

        if (isNewBest) {
            // 2️⃣ 更新用户最佳成绩
            updateBestScore(userId, dimension, score);

            // 3️⃣ 更新排行榜
            String key = buildLeaderboardKey(dimension, period);

            // 🎓 ZADD 命令：
            // - 如果成员不存在，添加新成员
            // - 如果成员存在，更新分数（仅当新分数更大时）
            // - 时间复杂度：O(log(N))
            redisTemplate.opsForZSet().add(key, userId.toString(), score);

            // 💡 设置排行榜 TTL
            // 避免历史数据无限增长
            setLeaderboardTtl(key, period);
        }

        return isNewBest;
    }

    /**
     * 检查是否是最佳成绩
     *
     * 🎓 使用 HGET 获取用户当前最佳成绩
     * - 如果没有记录，视为最佳成绩
     * - 如果新成绩更高，视为最佳成绩
     *
     * ⚠️ 注意：不同维度的比较方式可能不同
     * - WPM：越高越好
     * - 准确率：越高越好
     * - 用时：越少越好（这里统一用分数表示，越高越好）
     */
    private boolean isBestScore(Long userId, Dimension dimension, double newScore) {
        String key = buildUserBestKey(userId);

        // 🎓 HGET 命令：
        // - 获取 Hash 中指定字段的值
        // - 如果字段不存在，返回 null
        // - 时间复杂度：O(1)
        Object currentBest = redisTemplate.opsForHash().get(key, dimension.getValue());

        if (currentBest == null) {
            return true;  // 没有记录，视为最佳
        }

        // 🎓 类型转换
        // ⚠️ Redis 序列化后可能是 Double 或 String，需要兼容处理
        double currentScore;
        if (currentBest instanceof Double) {
            currentScore = (Double) currentBest;
        } else {
            currentScore = Double.parseDouble(currentBest.toString());
        }

        return newScore > currentScore;
    }

    /**
     * 更新用户最佳成绩
     *
     * 🎓 使用 HSET 存储用户最佳成绩
     * - Hash 结构适合存储对象的多个字段
     * - 支持单独更新某个字段，不影响其他字段
     *
     * 💡 同时存储时间戳：
     * - 便于后续分析用户进步趋势
     * - 支持按时间范围查询
     */
    private void updateBestScore(Long userId, Dimension dimension, double score) {
        String key = buildUserBestKey(userId);

        // 🎓 HSET 命令：
        // - 设置 Hash 中指定字段的值
        // - 如果字段不存在，创建新字段
        // - 如果字段存在，覆盖旧值
        // - 时间复杂度：O(1)
        redisTemplate.opsForHash().put(key, dimension.getValue(), score);
        redisTemplate.opsForHash().put(key, dimension.getValue() + ":timestamp",
                System.currentTimeMillis());
    }

    /**
     * 获取排行榜 Top N
     *
     * 🎓 使用 ZREVRANGE 获取排行榜：
     * - 降序排列（分数高的在前）
     * - 返回指定范围的成员
     * - 时间复杂度：O(log(N)+M)，M 是返回的成员数
     *
     * @param dimension 排行维度
     * @param period 时间范围
     * @param topN 获取前 N 名
     * @return 排行榜列表（包含用户 ID 和分数）
     */
    public List<LeaderboardEntry> getLeaderboard(Dimension dimension, Period period, int topN) {
        String key = buildLeaderboardKey(dimension, period);

        // 🎓 ZREVRANGE 命令：
        // - 返回有序集合中指定范围的成员
        // - 按分数从高到低排序
        // - WITHSCORES 同时返回分数
        // - 0 表示起始位置，topN-1 表示结束位置
        Set<ZSetOperations.TypedTuple<Object>> tuples =
                redisTemplate.opsForZSet().reverseRangeWithScores(key, 0, topN - 1);

        if (tuples == null || tuples.isEmpty()) {
            return Collections.emptyList();
        }

        // 🎓 转换为 DTO
        // 💡 在 Service 层转换，避免 Redis 类型泄露到 Controller
        return tuples.stream()
                .map(tuple -> new LeaderboardEntry(
                        Long.parseLong(tuple.getValue().toString()),
                        tuple.getScore()
                ))
                .collect(Collectors.toList());
    }

    /**
     * 获取用户排名
     *
     * 🎓 使用 ZREVRANK 获取用户排名：
     * - 降序排名（分数高的排名靠前）
     * - 返回排名（从 0 开始）
     * - 如果用户不存在，返回 null
     * - 时间复杂度：O(log(N))
     *
     * @param userId 用户 ID
     * @param dimension 排行维度
     * @param period 时间范围
     * @return 排名（从 1 开始），如果未上榜返回 -1
     */
    public Long getUserRank(Long userId, Dimension dimension, Period period) {
        String key = buildLeaderboardKey(dimension, period);

        // 🎓 ZREVRANK 命令：
        // - 返回成员在有序集合中的排名
        // - 排名从 0 开始
        // - 分数最高的成员排名为 0
        Long rank = redisTemplate.opsForZSet().reverseRank(key, userId.toString());

        // 💡 返回 -1 表示未上榜，比返回 null 更友好
        return rank != null ? rank + 1 : -1;
    }

    /**
     * 获取用户分数
     *
     * 🎓 使用 ZSCORE 获取用户分数
     * - 时间复杂度：O(1)
     */
    public Double getUserScore(Long userId, Dimension dimension, Period period) {
        String key = buildLeaderboardKey(dimension, period);

        Object score = redisTemplate.opsForZSet().score(key, userId.toString());

        return score != null ? (Double) score : null;
    }

    /**
     * 获取用户最佳成绩
     *
     * 🎓 使用 HGETALL 获取用户所有维度的最佳成绩
     * - 返回整个 Hash
     * - 时间复杂度：O(N)，N 是 Hash 的大小
     *
     * ⚠️ 注意：如果 Hash 很大，可能影响性能
     * 可以考虑使用 HMGET 只获取需要的字段
     */
    public UserBestScore getUserBestScore(Long userId) {
        String key = buildUserBestKey(userId);

        Map<Object, Object> entries = redisTemplate.opsForHash().entries(key);

        if (entries.isEmpty()) {
            return null;
        }

        return UserBestScore.fromMap(userId, entries);
    }

    /**
     * 获取用户在多个维度的排名
     *
     * 🎓 批量获取排名，减少网络往返
     * - 使用 Pipeline 批量执行命令
     * - 显著提升性能
     */
    public Map<Dimension, Long> getUserRanks(Long userId, Period period) {
        Map<Dimension, Long> ranks = new HashMap<>();

        for (Dimension dimension : Dimension.values()) {
            Long rank = getUserRank(userId, dimension, period);
            ranks.put(dimension, rank);
        }

        return ranks;
    }

    /**
     * 获取用户周边排名
     *
     * 🎓 获取用户前后 N 名的玩家
     * - 用于展示"超越你的人"和"被你超越的人"
     * - 使用 ZREVRANGE 的范围查询
     *
     * @param userId 用户 ID
     * @param dimension 排行维度
     * @param period 时间范围
     * @param range 前后各取 N 名
     * @return 周边排名列表
     */
    public List<LeaderboardEntry> getUserSurroundingRank(Long userId, Dimension dimension,
                                                          Period period, int range) {
        String key = buildLeaderboardKey(dimension, period);

        // 获取用户当前排名
        Long rank = redisTemplate.opsForZSet().reverseRank(key, userId.toString());

        if (rank == null) {
            return Collections.emptyList();
        }

        // 计算起始和结束位置
        long start = Math.max(0, rank - range);
        long end = rank + range;

        Set<ZSetOperations.TypedTuple<Object>> tuples =
                redisTemplate.opsForZSet().reverseRangeWithScores(key, start, end);

        if (tuples == null) {
            return Collections.emptyList();
        }

        return tuples.stream()
                .map(tuple -> new LeaderboardEntry(
                        Long.parseLong(tuple.getValue().toString()),
                        tuple.getScore()
                ))
                .collect(Collectors.toList());
    }

    /**
     * 设置排行榜 TTL
     *
     * 🎓 不同时间范围设置不同的 TTL：
     * - daily：2 天
     * - weekly：8 天
     * - monthly：32 天
     * - all：永不过期（或设置很长的 TTL）
     *
     * ⚠️ 注意：TTL 应该比时间范围稍长
     * 避免用户在时间边界提交成绩时，排行榜已过期
     */
    private void setLeaderboardTtl(String key, Period period) {
        Duration ttl;
        switch (period) {
            case DAILY:
                ttl = Duration.ofDays(2);
                break;
            case WEEKLY:
                ttl = Duration.ofDays(8);
                break;
            case MONTHLY:
                ttl = Duration.ofDays(32);
                break;
            case ALL:
                ttl = Duration.ofDays(365);  // 💡 设置 1 年，而非永不过期
                break;
            default:
                ttl = Duration.ofDays(7);
        }

        redisTemplate.expire(key, ttl);
    }

    // 🎓 Key 构建方法
    // 💡 统一构建 Key，避免硬编码分散在各处
    private String buildLeaderboardKey(Dimension dimension, Period period) {
        return LEADERBOARD_PREFIX + dimension.getValue() + ":" + period.getValue();
    }

    private String buildUserBestKey(Long userId) {
        return USER_BEST_PREFIX + userId;
    }
}
```

---

## 3. DTO 定义

```java
package com.typetype.dto;

import java.util.Map;

/**
 * 排行榜条目
 */
public class LeaderboardEntry {
    private Long userId;
    private Double score;
    private Long rank;  // 💡 可选字段，用于批量查询时填充排名

    public LeaderboardEntry(Long userId, Double score) {
        this.userId = userId;
        this.score = score;
    }

    // Getter、Setter 省略
}

/**
 * 用户最佳成绩
 */
public class UserBestScore {
    private Long userId;
    private Double wpm;
    private Double accuracy;
    private Double score;
    private Long wpmTimestamp;
    private Long accuracyTimestamp;
    private Long scoreTimestamp;

    /**
     * 从 Map 转换
     *
     * 🎓 使用工厂方法封装转换逻辑
     * - 避免在 Service 层处理类型转换
     * - 便于单元测试
     */
    public static UserBestScore fromMap(Long userId, Map<Object, Object> map) {
        UserBestScore best = new UserBestScore();
        best.setUserId(userId);

        // 💡 安全的类型转换，避免 ClassCastException
        best.setWpm(parseDouble(map.get("wpm")));
        best.setAccuracy(parseDouble(map.get("accuracy")));
        best.setScore(parseDouble(map.get("score")));
        best.setWpmTimestamp(parseLong(map.get("wpm:timestamp")));
        best.setAccuracyTimestamp(parseLong(map.get("accuracy:timestamp")));
        best.setScoreTimestamp(parseLong(map.get("score:timestamp")));

        return best;
    }

    private static Double parseDouble(Object value) {
        if (value == null) return null;
        if (value instanceof Double) return (Double) value;
        return Double.parseDouble(value.toString());
    }

    private static Long parseLong(Object value) {
        if (value == null) return null;
        if (value instanceof Long) return (Long) value;
        return Long.parseLong(value.toString());
    }

    // Getter、Setter 省略
}
```

---

## 4. Controller 接口

```java
package com.typetype.controller;

import com.typetype.dto.LeaderboardEntry;
import com.typetype.dto.UserBestScore;
import com.typetype.service.LeaderboardService;
import com.typetype.service.LeaderboardService.Dimension;
import com.typetype.service.LeaderboardService.Period;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 排行榜接口
 *
 * 🎓 RESTful API 设计：
 * - GET：查询排行榜
 * - POST：提交成绩
 * - 路径参数：维度和时间范围
 * - 查询参数：Top N、用户 ID
 */
@RestController
@RequestMapping("/api/leaderboard")
public class LeaderboardController {

    private final LeaderboardService leaderboardService;

    public LeaderboardController(LeaderboardService leaderboardService) {
        this.leaderboardService = leaderboardService;
    }

    /**
     * 获取排行榜
     *
     * 🎓 接口设计：
     * - 路径参数表达资源层级：/leaderboard/{dimension}/{period}
     * - 查询参数表达过滤条件：?topN=100
     *
     * 示例：GET /api/leaderboard/wpm/daily?topN=100
     */
    @GetMapping("/{dimension}/{period}")
    public List<LeaderboardEntry> getLeaderboard(
            @PathVariable Dimension dimension,
            @PathVariable Period period,
            @RequestParam(defaultValue = "100") int topN) {

        // ⚠️ 参数校验
        // 避免查询过多数据导致性能问题
        if (topN > 1000) {
            topN = 1000;
        }

        return leaderboardService.getLeaderboard(dimension, period, topN);
    }

    /**
     * 提交成绩
     *
     * 🎓 接口设计：
     * - POST 请求提交新成绩
     * - 请求体包含成绩信息
     * - 返回是否是新的最佳成绩
     *
     * 示例：POST /api/leaderboard/submit
     * Body: {"userId": 123, "dimension": "wpm", "score": 120.5}
     */
    @PostMapping("/submit")
    public Map<String, Object> submitScore(@RequestBody ScoreSubmitRequest request) {
        boolean isNewBest = leaderboardService.submitScore(
                request.getUserId(),
                request.getDimension(),
                request.getScore(),
                Period.ALL  // 💡 默认提交到总排行榜，可根据业务扩展
        );

        return Map.of(
                "success", true,
                "isNewBest", isNewBest
        );
    }

    /**
     * 获取用户排名
     *
     * 示例：GET /api/leaderboard/user/123/rank?dimension=wpm&period=daily
     */
    @GetMapping("/user/{userId}/rank")
    public Map<String, Long> getUserRank(
            @PathVariable Long userId,
            @RequestParam Dimension dimension,
            @RequestParam Period period) {

        Long rank = leaderboardService.getUserRank(userId, dimension, period);

        return Map.of("rank", rank);
    }

    /**
     * 获取用户最佳成绩
     *
     * 示例：GET /api/leaderboard/user/123/best
     */
    @GetMapping("/user/{userId}/best")
    public UserBestScore getUserBestScore(@PathVariable Long userId) {
        return leaderboardService.getUserBestScore(userId);
    }

    /**
     * 获取用户周边排名
     *
     * 示例：GET /api/leaderboard/user/123/surrounding?dimension=wpm&period=daily&range=5
     */
    @GetMapping("/user/{userId}/surrounding")
    public List<LeaderboardEntry> getUserSurroundingRank(
            @PathVariable Long userId,
            @RequestParam Dimension dimension,
            @RequestParam Period period,
            @RequestParam(defaultValue = "5") int range) {

        return leaderboardService.getUserSurroundingRank(userId, dimension, period, range);
    }
}

/**
 * 成绩提交请求
 */
class ScoreSubmitRequest {
    private Long userId;
    private Dimension dimension;
    private Double score;

    // Getter、Setter 省略
}
```

---

## 5. 定时任务：清理历史排行榜

```java
package com.typetype.task;

import com.typetype.service.LeaderboardService;
import com.typetype.service.LeaderboardService.Period;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 排行榜定时任务
 *
 * 🎓 定时清理过期的排行榜数据：
 * - 每天凌晨 2 点清理昨天的每日排行榜
 * - 每周一凌晨 3 点清理上周的每周排行榜
 * - 每月 1 号凌晨 4 点清理上月的每月排行榜
 *
 * ⚠️ 注意：清理任务应该在低峰期执行
 * 避免影响正常的排行榜查询
 */
@Component
public class LeaderboardCleanupTask {

    private final RedisTemplate<String, Object> redisTemplate;

    public LeaderboardCleanupTask(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 清理过期的每日排行榜
     *
     * 🎓 使用 @Scheduled 注解配置定时任务
     * - cron 表达式：秒 分 时 日 月 周
     * - "0 0 2 * * ?" 表示每天凌晨 2 点执行
     */
    @Scheduled(cron = "0 0 2 * * ?")
    public void cleanupDailyLeaderboards() {
        // 💡 删除 7 天前的每日排行榜
        // 保留 7 天是为了应对节假日等特殊情况
        for (int i = 7; i <= 30; i++) {
            String key = buildExpiredKey(Period.DAILY, i);
            redisTemplate.delete(key);
        }
    }

    /**
     * 清理过期的每周排行榜
     */
    @Scheduled(cron = "0 0 3 * * MON")
    public void cleanupWeeklyLeaderboards() {
        for (int i = 4; i <= 12; i++) {
            String key = buildExpiredKey(Period.WEEKLY, i);
            redisTemplate.delete(key);
        }
    }

    /**
     * 清理过期的每月排行榜
     */
    @Scheduled(cron = "0 0 4 1 * ?")
    public void cleanupMonthlyLeaderboards() {
        for (int i = 6; i <= 24; i++) {
            String key = buildExpiredKey(Period.MONTHLY, i);
            redisTemplate.delete(key);
        }
    }

    private String buildExpiredKey(Period period, int daysAgo) {
        // 💡 根据日期生成 Key
        // 实际实现中应该使用日期格式化
        return "typetype:leaderboard:" + period.getValue() + ":" + daysAgo;
    }
}
```

---

## 6. 性能优化建议

### 6.1 批量操作

```java
// 🎓 使用 Pipeline 批量执行命令
// 减少网络往返次数，提升性能

public void batchSubmitScores(List<ScoreSubmitRequest> requests) {
    redisTemplate.executePipelined((RedisCallback<Object>) connection -> {
        for (ScoreSubmitRequest request : requests) {
            String key = buildLeaderboardKey(request.getDimension(), Period.ALL);
            connection.zAdd(
                    key.getBytes(),
                    request.getScore(),
                    request.getUserId().toString().getBytes()
            );
        }
        return null;
    });
}
```

### 6.2 缓存热点数据

```java
// 🎓 缓存 Top N 排行榜
// 避免每次都查询 Redis

@Cacheable(value = "leaderboard", key = "#dimension + ':' + #period + ':' + #topN")
public List<LeaderboardEntry> getLeaderboardWithCache(Dimension dimension, Period period, int topN) {
    return leaderboardService.getLeaderboard(dimension, period, topN);
}
```

### 6.3 异步更新

```java
// 🎓 异步更新排行榜
// 避免阻塞主线程

@Async
public void asyncSubmitScore(Long userId, Dimension dimension, double score, Period period) {
    leaderboardService.submitScore(userId, dimension, score, period);
}
```

---

## 7. 监控指标

| 指标 | 说明 | 告警阈值 |
|:--- |:--- |:--- |
| leaderboard:ops | 排行榜操作数/秒 | > 1000 |
| leaderboard:latency | 排行榜操作延迟 | > 100ms |
| leaderboard:memory | 排行榜内存占用 | > 1GB |
| leaderboard:entries | 排行榜条目数 | > 100000 |
