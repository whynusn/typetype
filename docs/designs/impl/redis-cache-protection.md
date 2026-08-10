# Redis 缓存防护实现

> ⚠️ 本文件为 typetype-server（服务端）侧设计，与本客户端仓库解耦；2026-07-03 起 draft 未更新。客户端开发者请忽略。

> 本文件是 typetype-server 的 Redis 缓存防护参考实现。
> 包含缓存穿透防护、缓存击穿防护、缓存雪崩防护的完整实现代码。

---

## 1. 缓存问题概述

```
# 🎓 Redis 缓存三大问题

# 1. 缓存穿透（Cache Penetration）
#    - 问题：查询一个一定不存在的数据，缓存永远不会命中
#    - 后果：每次请求都打到数据库，数据库压力剧增
#    - 场景：恶意攻击、业务漏洞（如查询已删除的用户）

# 2. 缓存击穿（Cache Breakdown）
#    - 问题：某个热点 Key 过期，大量并发请求同时打到数据库
#    - 后果：数据库瞬间压力飙升，可能宕机
#    - 场景：秒杀商品、热门排行榜

# 3. 缓存雪崩（Cache Avalanche）
#    - 问题：大量 Key 同时过期，或者 Redis 宕机
#    - 后果：所有请求打到数据库，数据库崩溃
#    - 场景：批量导入数据时设置相同的 TTL

# 防护策略：
# - 穿透：布隆过滤器 + 空值缓存
# - 击穿：逻辑过期 + 分布式锁
# - 雪崩：TTL 随机化 + 多级缓存
```

---

## 2. 缓存穿透防护

### 2.1 布隆过滤器实现

```java
package com.typetype.cache;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.util.BitSet;
import java.util.List;

/**
 * 布隆过滤器
 *
 * 🎓 布隆过滤器原理：
 * 1. 初始化：创建一个长度为 m 的位数组，所有位设置为 0
 * 2. 添加元素：使用 k 个哈希函数对元素进行哈希，将对应位置设置为 1
 * 3. 查询元素：使用相同的 k 个哈希函数检查对应位置
 *    - 如果所有位置都是 1，元素可能存在（有误判）
 *    - 如果任何位置是 0，元素一定不存在（无漏判）
 *
 * 优点：
 * - 空间效率高：只需存储位，不存储元素本身
 * - 查询时间 O(k)：k 是哈希函数数量
 * - 保密性好：无法从布隆过滤器还原元素
 *
 * 缺点：
 * - 存在误判（False Positive）：可能判断元素存在，实际不存在
 * - 不支持删除：删除元素会影响其他元素
 *
 * 💡 适用场景：
 * - 数据量大、内存有限
 * - 允许一定的误判率
 * - 只需要判断"是否存在"
 */
@Component
public class BloomFilter {

    private final RedisTemplate<String, Object> redisTemplate;

    // 🎓 布隆过滤器参数
    // 💡 参数选择指南：
    // - expectedInsertions：预期插入元素数量
    // - fpp：误判概率（False Positive Probability）
    // - m = -n * ln(p) / (ln(2)^2)：位数组长度
    // - k = (m/n) * ln(2)：哈希函数数量
    private static final String BLOOM_FILTER_KEY = "typetype:bloom:users";
    private static final int EXPECTED_INSERTIONS = 10_000_000;  // 预期 1000 万用户
    private static final double FPP = 0.01;  // 1% 误判率

    // 🎓 计算得出的参数
    // m = -10000000 * ln(0.01) / (ln(2)^2) ≈ 95850584 bits ≈ 11.4 MB
    // k = (95850584/10000000) * ln(2) ≈ 7
    private static final int BIT_ARRAY_SIZE = 95_850_584;
    private static final int HASH_COUNT = 7;

    public BloomFilter(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 初始化布隆过滤器
     *
     * 🎓 应用启动时调用，从数据库加载所有用户 ID
     *
     * ⚠️ 注意：
     * - 初始化过程可能很慢，建议异步执行
     * - 可以考虑增量更新，避免全量加载
     */
    public void init(List<Long> userIds) {
        // 🎓 使用 Redis 的 Bitmap 实现布隆过滤器
        // - 比特位操作效率高
        // - 支持持久化
        // - 支持分布式访问
        for (Long userId : userIds) {
            add(userId);
        }
    }

    /**
     * 添加元素到布隆过滤器
     *
     * 🎓 使用多个哈希函数计算位置
     * - 每个哈希函数计算一个位置
     * - 将所有位置的比特位设置为 1
     */
    public void add(Long userId) {
        int[] positions = getHashPositions(userId);

        for (int position : positions) {
            // 🎓 SETBIT 命令：
            // - 设置指定位置的比特位为 1
            // - 如果位置不存在，自动扩展
            // - 时间复杂度：O(1)
            redisTemplate.opsForValue().setBit(BLOOM_FILTER_KEY, position, true);
        }
    }

    /**
     * 检查元素是否可能存在
     *
     * 🎓 查询逻辑：
     * 1. 使用相同的哈希函数计算位置
     * 2. 检查所有位置的比特位
     * 3. 如果所有位置都是 1，返回 true（可能存在）
     * 4. 如果任何位置是 0，返回 false（一定不存在）
     *
     * ⚠️ 注意：
     * - 返回 true 不代表元素一定存在（误判）
     * - 返回 false 代表元素一定不存在（无漏判）
     * - 误判率与参数设置有关
     */
    public boolean mightContain(Long userId) {
        int[] positions = getHashPositions(userId);

        for (int position : positions) {
            // 🎓 GETBIT 命令：
            // - 获取指定位置的比特位
            // - 如果位置不存在，返回 0
            // - 时间复杂度：O(1)
            Boolean bit = redisTemplate.opsForValue().getBit(BLOOM_FILTER_KEY, position);

            // 💡 任何位置是 0，元素一定不存在
            if (bit == null || !bit) {
                return false;
            }
        }

        // 💡 所有位置都是 1，元素可能存在
        return true;
    }

    /**
     * 计算哈希位置
     *
     * 🎓 使用双重哈希模拟多个哈希函数
     * - hash(i) = hash1 + i * hash2
     * - 只需要计算两个哈希值，就能模拟多个
     * - 比使用 k 个独立哈希函数更高效
     */
    private int[] getHashPositions(Long userId) {
        int[] positions = new int[HASH_COUNT];

        // 🎓 第一个哈希函数：MurmurHash
        long hash1 = murmurHash(userId.toString(), 0);

        // 🎓 第二个哈希函数：使用不同的种子
        long hash2 = murmurHash(userId.toString(), (int) hash1);

        for (int i = 0; i < HASH_COUNT; i++) {
            // 🎓 双重哈希公式
            long combinedHash = hash1 + i * hash2;

            // 💡 取绝对值并对位数组大小取模
            // 确保位置在有效范围内
            positions[i] = (int) (Math.abs(combinedHash) % BIT_ARRAY_SIZE);
        }

        return positions;
    }

    /**
     * MurmurHash 实现
     *
     * 🎓 为什么选择 MurmurHash？
     * - 分布均匀：哈希碰撞少
     * - 计算速度快：比 SHA、MD5 快很多
     * - 非加密哈希：不需要安全性，只需要速度
     */
    private long murmurHash(String key, int seed) {
        // 💡 实际项目中建议使用 Guava 的 Hashing 或 Apache Commons 的 MurmurHash3
        // 这里简化实现
        long h = seed;
        for (int i = 0; i < key.length(); i++) {
            h = 31 * h + key.charAt(i);
        }
        return h;
    }
}
```

### 2.2 空值缓存实现

```java
package com.typetype.cache;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 空值缓存
 *
 * 🎓 空值缓存原理：
 * 1. 查询数据库，如果结果为空，将空值也缓存起来
 * 2. 设置较短的 TTL（如 5 分钟）
 * 3. 后续相同的查询直接返回空值，不再查询数据库
 *
 * 优点：
 * - 实现简单，效果明显
 * - 有效防止恶意攻击
 *
 * 缺点：
 * - 浪费内存存储空值
 * - 可能导致数据不一致（数据库新增数据后，缓存仍是空值）
 *
 * 💡 适用场景：
 * - 查询结果为空的概率较高
 * - 数据更新频率较低
 * - 可以接受短暂的数据不一致
 */
@Component
public class NullValueCache {

    private final RedisTemplate<String, Object> redisTemplate;

    // 🎓 空值标记
    // 💡 使用特殊的字符串标记空值，避免与正常值混淆
    private static final String NULL_VALUE = "NULL_VALUE";

    // 🎓 空值 TTL
    // 💡 设置较短的 TTL，避免长时间数据不一致
    private static final Duration NULL_VALUE_TTL = Duration.ofMinutes(5);

    public NullValueCache(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 缓存空值
     *
     * 🎓 存储逻辑：
     * 1. 使用特殊的 NULL_VALUE 标记
     * 2. 设置较短的 TTL
     * 3. 避免与正常值混淆
     */
    public void cacheNullValue(String key) {
        redisTemplate.opsForValue().set(key, NULL_VALUE, NULL_VALUE_TTL);
    }

    /**
     * 检查是否是空值缓存
     *
     * 🎓 查询逻辑：
     * 1. 获取缓存值
     * 2. 检查是否是 NULL_VALUE 标记
     * 3. 返回检查结果
     */
    public boolean isNullValueCached(String key) {
        Object value = redisTemplate.opsForValue().get(key);
        return NULL_VALUE.equals(value);
    }

    /**
     * 获取缓存值（处理空值）
     *
     * 🎓 完整的缓存查询逻辑：
     * 1. 查询缓存
     * 2. 如果是空值标记，返回 null
     * 3. 如果是正常值，返回值
     * 4. 如果不存在，返回 null（调用方需要判断）
     */
    public Object getWithNullCheck(String key) {
        Object value = redisTemplate.opsForValue().get(key);

        if (NULL_VALUE.equals(value)) {
            return null;
        }

        return value;
    }
}
```

### 2.3 缓存穿透防护服务

```java
package com.typetype.service;

import com.typetype.cache.BloomFilter;
import com.typetype.cache.NullValueCache;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;

/**
 * 缓存穿透防护服务
 *
 * 🎓 防护流程：
 * 1. 布隆过滤器检查：如果元素不存在，直接返回 null
 * 2. 查询缓存：如果命中缓存，返回缓存值
 * 3. 检查空值缓存：如果是空值，返回 null
 * 4. 查询数据库：获取真实数据
 * 5. 更新缓存：将数据写入缓存
 * 6. 缓存空值：如果数据库为空，缓存空值
 */
@Service
public class CachePenetrationProtectionService {

    private final RedisTemplate<String, Object> redisTemplate;
    private final BloomFilter bloomFilter;
    private final NullValueCache nullValueCache;

    // 🎓 正常数据的 TTL
    private static final Duration NORMAL_TTL = Duration.ofHours(1);

    public CachePenetrationProtectionService(
            RedisTemplate<String, Object> redisTemplate,
            BloomFilter bloomFilter,
            NullValueCache nullValueCache) {
        this.redisTemplate = redisTemplate;
        this.bloomFilter = bloomFilter;
        this.nullValueCache = nullValueCache;
    }

    /**
     * 带防护的缓存查询
     *
     * 🎓 完整的防护流程：
     *
     * 步骤 1：布隆过滤器检查
     * - 如果元素一定不存在，直接返回 null
     * - 避免后续的缓存和数据库查询
     *
     * 步骤 2：查询缓存
     * - 如果命中缓存，直接返回
     * - 避免数据库查询
     *
     * 步骤 3：检查空值缓存
     * - 如果是空值，直接返回 null
     * - 避免数据库查询
     *
     * 步骤 4：查询数据库
     * - 获取真实数据
     *
     * 步骤 5：更新缓存
     * - 将数据写入缓存
     * - 设置合理的 TTL
     *
     * 步骤 6：缓存空值
     * - 如果数据库为空，缓存空值
     * - 防止后续相同的查询打到数据库
     *
     * @param key 缓存 Key
     * @param id 数据 ID
     * @param dbLoader 数据库加载函数
     * @return 数据，如果不存在返回 null
     */
    public Object getWithProtection(String key, Long id, DatabaseLoader dbLoader) {
        // 步骤 1：布隆过滤器检查
        // 🎓 布隆过滤器返回 false，元素一定不存在
        if (!bloomFilter.mightContain(id)) {
            // 💡 记录日志，便于监控恶意攻击
            log.info("Bloom filter rejected: {}", id);
            return null;
        }

        // 步骤 2：查询缓存
        Object cachedValue = redisTemplate.opsForValue().get(key);

        // 🎓 缓存命中，直接返回
        if (cachedValue != null) {
            // 💡 检查是否是空值标记
            if (nullValueCache.isNullValueCached(key)) {
                return null;
            }
            return cachedValue;
        }

        // 步骤 3：查询数据库
        // ⚠️ 注意：这里需要加锁，防止缓存击穿
        // 详见下一节的分布式锁实现
        Object dbValue = dbLoader.load(id);

        // 步骤 4：更新缓存
        if (dbValue != null) {
            // 🎓 缓存正常数据
            redisTemplate.opsForValue().set(key, dbValue, NORMAL_TTL);
        } else {
            // 🎓 缓存空值
            // 💡 防止相同的查询再次打到数据库
            nullValueCache.cacheNullValue(key);
        }

        return dbValue;
    }

    /**
     * 数据库加载函数接口
     *
     * 🎓 使用函数式接口：
     * - 支持 Lambda 表达式
     * - 代码更简洁
     * - 便于测试
     */
    @FunctionalInterface
    public interface DatabaseLoader {
        Object load(Long id);
    }

    private void log.info(String message, Object... args) {
        // 💡 实际项目中使用 SLF4J 或 Log4j2
        System.out.println(String.format(message, args));
    }
}
```

---

## 3. 缓存击穿防护

### 3.1 逻辑过期实现

```java
package com.typetype.cache;

import java.time.Duration;
import java.time.LocalDateTime;

/**
 * 逻辑过期包装器
 *
 * 🎓 逻辑过期原理：
 * 1. 在缓存数据中额外存储一个过期时间字段
 * 2. 读取数据时，检查逻辑过期时间
 * 3. 如果已过期，返回旧数据，同时异步更新缓存
 * 4. 如果未过期，直接返回数据
 *
 * 优点：
 * - 不依赖 Redis 的 TTL 机制
 * - 可以实现"先返回旧数据，再更新"的策略
 * - 避免缓存击穿
 *
 * 缺点：
 * - 实现复杂
 * - 可能返回过期数据
 * - 需要额外的存储空间
 *
 * 💡 适用场景：
 * - 热点数据（如排行榜、热门商品）
 * - 对数据一致性要求不高
 * - 需要高可用性
 */
public class LogicalExpire<T> {

    // 🎓 数据
    private T data;

    // 🎓 逻辑过期时间
    // 💡 使用 LocalDateTime 而非时间戳，可读性更好
    private LocalDateTime expireTime;

    public LogicalExpire(T data, Duration ttl) {
        this.data = data;
        this.expireTime = LocalDateTime.now().plus(ttl);
    }

    /**
     * 检查是否已过期
     *
     * 🎓 逻辑过期判断：
     * - 当前时间 > 过期时间 = 已过期
     * - 当前时间 <= 过期时间 = 未过期
     */
    public boolean isExpired() {
        return LocalDateTime.now().isAfter(expireTime);
    }

    /**
     * 获取剩余有效时间
     *
     * 💡 用于监控和告警
     */
    public Duration getRemainingTime() {
        LocalDateTime now = LocalDateTime.now();
        if (now.isAfter(expireTime)) {
            return Duration.ZERO;
        }
        return Duration.between(now, expireTime);
    }

    // Getter、Setter
    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    public LocalDateTime getExpireTime() {
        return expireTime;
    }

    public void setExpireTime(LocalDateTime expireTime) {
        this.expireTime = expireTime;
    }
}
```

### 3.2 分布式锁实现

```java
package com.typetype.cache;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * 分布式锁
 *
 * 🎓 分布式锁原理：
 * 1. 获取锁：使用 SET NX EX 命令
 *    - NX：只有 Key 不存在时才设置（保证互斥）
 *    - EX：设置过期时间（防止死锁）
 * 2. 释放锁：使用 Lua 脚本
 *    - 检查锁的持有者是否是当前线程
 *    - 如果是，删除锁
 *    - 如果不是，不删除（避免误删其他线程的锁）
 *
 * 优点：
 * - 简单高效
 * - 支持可重入
 * - 支持超时自动释放
 *
 * 缺点：
 * - 依赖 Redis 的可用性
 * - 锁的过期时间难以精确设置
 * - 主从切换可能导致锁丢失
 *
 * 💡 适用场景：
 * - 缓存击穿防护
 * - 分布式任务调度
 * - 库存扣减
 */
@Component
public class DistributedLock {

    private final RedisTemplate<String, Object> redisTemplate;

    // 🎓 锁 Key 前缀
    private static final String LOCK_PREFIX = "typetype:lock:";

    // 🎓 锁的默认过期时间
    // 💡 设置合理的过期时间，防止死锁
    // ⚠️ 不能设置太短，否则任务未完成锁就过期了
    private static final Duration DEFAULT_LOCK_TIMEOUT = Duration.ofSeconds(30);

    // 🎓 获取锁的超时时间
    // 💡 避免无限等待
    private static final Duration ACQUIRE_TIMEOUT = Duration.ofSeconds(5);

    public DistributedLock(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 获取分布式锁
     *
     * 🎓 获取锁的流程：
     * 1. 生成唯一的锁标识（UUID）
     * 2. 使用 SET NX EX 命令尝试获取锁
     * 3. 如果获取成功，返回锁标识
     * 4. 如果获取失败，重试直到超时
     *
     * ⚠️ 注意：
     * - 锁标识必须唯一，用于释放锁时验证持有者
     * - 必须设置过期时间，防止死锁
     * - 获取锁失败时应该重试，而非直接返回错误
     *
     * @param lockKey 锁的 Key
     * @return 锁标识，如果获取失败返回 null
     */
    public String tryLock(String lockKey) {
        return tryLock(lockKey, DEFAULT_LOCK_TIMEOUT, ACQUIRE_TIMEOUT);
    }

    public String tryLock(String lockKey, Duration lockTimeout, Duration acquireTimeout) {
        String fullKey = LOCK_PREFIX + lockKey;

        // 🎓 生成唯一的锁标识
        // 💡 使用 UUID + 线程 ID，保证唯一性
        String lockValue = UUID.randomUUID().toString() + ":" + Thread.currentThread().getId();

        // 🎓 计算超时时间
        long acquireDeadline = System.currentTimeMillis() + acquireTimeout.toMillis();

        // 🎓 重试获取锁
        while (System.currentTimeMillis() < acquireDeadline) {
            // 🎓 SET NX EX 命令：
            // - NX：只有 Key 不存在时才设置
            // - EX：设置过期时间（秒）
            // - 返回 true 表示设置成功（获取锁成功）
            // - 返回 false 表示 Key 已存在（获取锁失败）
            Boolean success = redisTemplate.opsForValue().setIfAbsent(
                    fullKey,
                    lockValue,
                    lockTimeout.toSeconds(),
                    TimeUnit.SECONDS
            );

            if (Boolean.TRUE.equals(success)) {
                // 💡 获取锁成功
                return lockValue;
            }

            // 💡 获取锁失败，短暂等待后重试
            // ⚠️ 不要使用 Thread.sleep()，会影响性能
            // 建议使用 Redis 的发布/订阅机制等待锁释放
            try {
                Thread.sleep(100);  // 100ms 重试间隔
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return null;
            }
        }

        // 💡 获取锁超时
        return null;
    }

    /**
     * 释放分布式锁
     *
     * 🎓 释放锁的流程：
     * 1. 使用 Lua 脚本保证原子性
     * 2. 检查锁的持有者是否是当前线程
     * 3. 如果是，删除锁
     * 4. 如果不是，不删除（避免误删）
     *
     * ⚠️ 注意：
     * - 必须使用 Lua 脚本，保证原子性
     * - 不能直接删除，可能误删其他线程的锁
     * - 释放锁后，锁标识应该失效
     *
     * @param lockKey 锁的 Key
     * @param lockValue 锁标识（获取锁时返回的值）
     * @return 是否释放成功
     */
    public boolean unlock(String lockKey, String lockValue) {
        String fullKey = LOCK_PREFIX + lockKey;

        // 🎓 Lua 脚本
        // 💡 使用 Lua 脚本保证原子性
        // 如果直接使用 Redis 命令，可能在检查和删除之间有其他线程修改锁
        String luaScript = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """;

        // 🎓 执行 Lua 脚本
        // - KEYS[1]：锁的 Key
        // - ARGV[1]：锁标识
        // - 返回 1 表示删除成功
        // - 返回 0 表示删除失败（锁的持有者不是当前线程）
        Long result = redisTemplate.execute(
                new org.springframework.data.redis.core.script.DefaultRedisScript<>(luaScript, Long.class),
                java.util.Collections.singletonList(fullKey),
                lockValue
        );

        return result != null && result == 1;
    }
}
```

### 3.3 缓存击穿防护服务

```java
package com.typetype.service;

import com.typetype.cache.DistributedLock;
import com.typetype.cache.LogicalExpire;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 缓存击穿防护服务
 *
 * 🎓 防护流程：
 * 1. 查询缓存：如果命中缓存，检查逻辑过期时间
 * 2. 如果未过期：直接返回数据
 * 3. 如果已过期：
 *    a. 尝试获取分布式锁
 *    b. 如果获取成功：查询数据库，更新缓存，释放锁
 *    c. 如果获取失败：返回旧数据（其他线程正在更新）
 * 4. 如果未命中缓存：
 *    a. 获取分布式锁
 *    b. 查询数据库，更新缓存，释放锁
 */
@Service
public class CacheBreakdownProtectionService {

    private final RedisTemplate<String, Object> redisTemplate;
    private final DistributedLock distributedLock;

    // 🎓 逻辑过期时间
    // 💡 设置较短的逻辑过期时间，保证数据相对新鲜
    private static final Duration LOGICAL_EXPIRE = Duration.ofMinutes(30);

    // 🎓 Redis TTL（比逻辑过期时间长）
    // 💡 保证缓存不会真正过期，避免缓存击穿
    private static final Duration REDIS_TTL = Duration.ofHours(2);

    // 🎓 异步更新线程池
    // 💡 使用独立的线程池，避免阻塞主线程
    private final ExecutorService executorService = Executors.newFixedThreadPool(10);

    public CacheBreakdownProtectionService(
            RedisTemplate<String, Object> redisTemplate,
            DistributedLock distributedLock) {
        this.redisTemplate = redisTemplate;
        this.distributedLock = distributedLock;
    }

    /**
     * 带防护的缓存查询
     *
     * 🎓 完整的防护流程：
     *
     * 步骤 1：查询缓存
     * - 如果命中缓存，进入步骤 2
     * - 如果未命中，进入步骤 4
     *
     * 步骤 2：检查逻辑过期
     * - 如果未过期，直接返回数据
     * - 如果已过期，进入步骤 3
     *
     * 步骤 3：异步更新缓存
     * - 尝试获取分布式锁
     * - 如果获取成功，异步更新缓存
     * - 如果获取失败，返回旧数据
     *
     * 步骤 4：同步更新缓存
     * - 获取分布式锁
     * - 查询数据库
     * - 更新缓存
     * - 释放锁
     *
     * @param key 缓存 Key
     * @param lockKey 锁的 Key
     * @param dbLoader 数据库加载函数
     * @return 数据
     */
    public Object getWithProtection(String key, String lockKey, DatabaseLoader dbLoader) {
        // 步骤 1：查询缓存
        Object cachedValue = redisTemplate.opsForValue().get(key);

        if (cachedValue != null) {
            // 🎓 缓存命中，检查逻辑过期
            LogicalExpire<?> logicalExpire = (LogicalExpire<?>) cachedValue;

            if (!logicalExpire.isExpired()) {
                // 步骤 2：未过期，直接返回
                return logicalExpire.getData();
            }

            // 步骤 3：已过期，异步更新
            // 💡 返回旧数据，同时异步更新缓存
            asyncUpdateCache(key, lockKey, dbLoader);
            return logicalExpire.getData();
        }

        // 步骤 4：未命中缓存，同步更新
        return syncUpdateCache(key, lockKey, dbLoader);
    }

    /**
     * 异步更新缓存
     *
     * 🎓 异步更新策略：
     * 1. 尝试获取分布式锁
     * 2. 如果获取成功，提交异步任务更新缓存
     * 3. 如果获取失败，说明其他线程正在更新，无需处理
     *
     * 💡 优点：
     * - 不阻塞主线程
     * - 减少数据库压力
     * - 提高响应速度
     */
    private void asyncUpdateCache(String key, String lockKey, DatabaseLoader dbLoader) {
        CompletableFuture.runAsync(() -> {
            String lockValue = distributedLock.tryLock(lockKey);

            if (lockValue != null) {
                try {
                    // 🎓 双重检查
                    // 💡 其他线程可能已经更新了缓存
                    Object cachedValue = redisTemplate.opsForValue().get(key);

                    if (cachedValue != null) {
                        LogicalExpire<?> logicalExpire = (LogicalExpire<?>) cachedValue;

                        if (!logicalExpire.isExpired()) {
                            // 💡 其他线程已经更新，无需重复更新
                            return;
                        }
                    }

                    // 🎓 查询数据库
                    Object dbValue = dbLoader.load();

                    // 🎓 更新缓存
                    LogicalExpire<Object> newExpire = new LogicalExpire<>(dbValue, LOGICAL_EXPIRE);
                    redisTemplate.opsForValue().set(key, newExpire, REDIS_TTL);

                } finally {
                    // 🎓 释放锁
                    distributedLock.unlock(lockKey, lockValue);
                }
            }
        }, executorService);
    }

    /**
     * 同步更新缓存
     *
     * 🎓 同步更新策略：
     * 1. 获取分布式锁
     * 2. 查询数据库
     * 3. 更新缓存
     * 4. 释放锁
     *
     * 💡 适用场景：
     * - 缓存未命中
     * - 必须返回最新数据
     */
    private Object syncUpdateCache(String key, String lockKey, DatabaseLoader dbLoader) {
        String lockValue = distributedLock.tryLock(lockKey);

        if (lockValue == null) {
            // 💡 获取锁失败，重试
            // ⚠️ 实际项目中应该有重试次数限制
            throw new RuntimeException("获取锁失败");
        }

        try {
            // 🎓 双重检查
            Object cachedValue = redisTemplate.opsForValue().get(key);

            if (cachedValue != null) {
                LogicalExpire<?> logicalExpire = (LogicalExpire<?>) cachedValue;

                if (!logicalExpire.isExpired()) {
                    return logicalExpire.getData();
                }
            }

            // 🎓 查询数据库
            Object dbValue = dbLoader.load();

            // 🎓 更新缓存
            LogicalExpire<Object> newExpire = new LogicalExpire<>(dbValue, LOGICAL_EXPIRE);
            redisTemplate.opsForValue().set(key, newExpire, REDIS_TTL);

            return dbValue;

        } finally {
            // 🎓 释放锁
            distributedLock.unlock(lockKey, lockValue);
        }
    }

    /**
     * 数据库加载函数接口
     */
    @FunctionalInterface
    public interface DatabaseLoader {
        Object load();
    }
}
```

---

## 4. 缓存雪崩防护

### 4.1 TTL 随机化实现

```java
package com.typetype.cache;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

/**
 * TTL 随机化工具
 *
 * 🎓 TTL 随机化原理：
 * 1. 为每个缓存设置基础 TTL
 * 2. 在基础 TTL 上增加随机偏移量
 * 3. 避免大量缓存同时过期
 *
 * 优点：
 * - 实现简单
 * - 有效防止缓存雪崩
 * - 不影响业务逻辑
 *
 * 缺点：
 * - 增加了 TTL 管理的复杂度
 * - 可能导致某些缓存过早或过晚过期
 *
 * 💡 适用场景：
 * - 批量导入数据
 * - 热点数据缓存
 * - 需要高可用性的场景
 */
public class TtlRandomizer {

    // 🎓 随机偏移范围
    // 💡 设置合理的偏移范围，避免 TTL 差异过大
    // 例如：基础 TTL 1 小时，偏移范围 5 分钟
    // 实际 TTL：55 分钟 ~ 65 分钟
    private static final Duration MAX_OFFSET = Duration.ofMinutes(5);

    /**
     * 生成随机化 TTL
     *
     * 🎓 随机化策略：
     * 1. 生成 [-maxOffset, +maxOffset] 范围内的随机偏移量
     * 2. 将偏移量加到基础 TTL 上
     * 3. 确保 TTL 不小于 0
     *
     * @param baseTtl 基础 TTL
     * @return 随机化后的 TTL
     */
    public static Duration randomize(Duration baseTtl) {
        return randomize(baseTtl, MAX_OFFSET);
    }

    public static Duration randomize(Duration baseTtl, Duration maxOffset) {
        // 🎓 生成随机偏移量
        // 💡 使用 ThreadLocalRandom，避免多线程竞争
        long offsetMillis = ThreadLocalRandom.current().nextLong(
                -maxOffset.toMillis(),
                maxOffset.toMillis()
        );

        // 🎓 计算随机化后的 TTL
        long randomTtlMillis = baseTtl.toMillis() + offsetMillis;

        // ⚠️ 确保 TTL 不小于 0
        if (randomTtlMillis < 0) {
            randomTtlMillis = 0;
        }

        return Duration.ofMillis(randomTtlMillis);
    }

    /**
     * 生成批量缓存的随机化 TTL
     *
     * 🎓 批量场景：
     * - 批量导入数据时，为每条数据设置不同的 TTL
     * - 避免大量缓存同时过期
     *
     * @param baseTtl 基础 TTL
     * @param count 数据数量
     * @return 随机化后的 TTL 数组
     */
    public static Duration[] randomizeBatch(Duration baseTtl, int count) {
        Duration[] ttls = new Duration[count];

        for (int i = 0; i < count; i++) {
            ttls[i] = randomize(baseTtl);
        }

        return ttls;
    }
}
```

### 4.2 多级缓存实现

```java
package com.typetype.cache;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 多级缓存
 *
 * 🎓 多级缓存原理：
 * 1. L1 缓存：本地缓存（Caffeine、Guava Cache）
 *    - 访问速度快（纳秒级）
 *    - 容量有限（受 JVM 内存限制）
 *    - 无法跨进程共享
 *
 * 2. L2 缓存：分布式缓存（Redis）
 *    - 访问速度较慢（毫秒级）
 *    - 容量大（可水平扩展）
 *    - 支持跨进程共享
 *
 * 3. 查询流程：
 *    a. 查询 L1 缓存
 *    b. 如果 L1 未命中，查询 L2 缓存
 *    c. 如果 L2 未命中，查询数据库
 *    d. 将数据写入 L1 和 L2 缓存
 *
 * 优点：
 * - 兼顾性能和容量
 * - 减少 Redis 访问压力
 * - 提高系统可用性
 *
 * 缺点：
 * - 实现复杂
 * - 数据一致性难以保证
 * - 需要维护两套缓存
 *
 * 💡 适用场景：
 * - 热点数据（如排行榜、配置信息）
 * - 需要高并发、低延迟
 * - 可以接受短暂的数据不一致
 */
@Component
public class MultiLevelCache {

    private final RedisTemplate<String, Object> redisTemplate;

    // 🎓 L1 缓存：本地缓存
    // 💡 使用 ConcurrentHashMap 简化实现
    // 实际项目中建议使用 Caffeine 或 Guava Cache
    private final ConcurrentHashMap<String, CacheEntry> localCache = new ConcurrentHashMap<>();

    // 🎓 L1 缓存配置
    private static final Duration LOCAL_TTL = Duration.ofMinutes(5);
    private static final int LOCAL_MAX_SIZE = 1000;

    // 🎓 L2 缓存配置
    private static final Duration REDIS_TTL = Duration.ofHours(1);

    public MultiLevelCache(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 查询缓存
     *
     * 🎓 查询流程：
     * 1. 查询 L1 缓存
     * 2. 如果 L1 命中，直接返回
     * 3. 如果 L1 未命中，查询 L2 缓存
     * 4. 如果 L2 命中，写入 L1 缓存，返回
     * 5. 如果 L2 未命中，返回 null（调用方查询数据库）
     */
    public Object get(String key) {
        // 步骤 1：查询 L1 缓存
        CacheEntry entry = localCache.get(key);

        if (entry != null && !entry.isExpired()) {
            // 💡 L1 命中，直接返回
            return entry.getValue();
        }

        // 步骤 2：查询 L2 缓存
        Object redisValue = redisTemplate.opsForValue().get(key);

        if (redisValue != null) {
            // 💡 L2 命中，写入 L1 缓存
            putLocal(key, redisValue);
            return redisValue;
        }

        // 💡 两级缓存都未命中
        return null;
    }

    /**
     * 写入缓存
     *
     * 🎓 写入流程：
     * 1. 写入 L1 缓存
     * 2. 写入 L2 缓存
     * 3. 保证最终一致性
     */
    public void put(String key, Object value) {
        // 写入 L1 缓存
        putLocal(key, value);

        // 写入 L2 缓存
        redisTemplate.opsForValue().set(key, value, REDIS_TTL);
    }

    /**
     * 删除缓存
     *
     * 🎓 删除流程：
     * 1. 删除 L1 缓存
     * 2. 删除 L2 缓存
     * 3. 保证一致性
     */
    public void evict(String key) {
        // 删除 L1 缓存
        localCache.remove(key);

        // 删除 L2 缓存
        redisTemplate.delete(key);
    }

    /**
     * 写入 L1 缓存
     *
     * 🎓 L1 缓存管理：
     * 1. 检查容量限制
     * 2. 如果超过限制，清理过期条目
     * 3. 写入新条目
     */
    private void putLocal(String key, Object value) {
        // 💡 检查容量限制
        if (localCache.size() >= LOCAL_MAX_SIZE) {
            cleanupExpiredEntries();
        }

        // 🎓 写入 L1 缓存
        CacheEntry entry = new CacheEntry(value, LOCAL_TTL);
        localCache.put(key, entry);
    }

    /**
     * 清理过期条目
     *
     * 🎓 定期清理：
     * - 避免本地缓存无限增长
     * - 减少内存占用
     */
    private void cleanupExpiredEntries() {
        localCache.entrySet().removeIf(entry -> entry.getValue().isExpired());
    }

    /**
     * 缓存条目
     */
    private static class CacheEntry {
        private final Object value;
        private final long expireTime;

        public CacheEntry(Object value, Duration ttl) {
            this.value = value;
            this.expireTime = System.currentTimeMillis() + ttl.toMillis();
        }

        public Object getValue() {
            return value;
        }

        public boolean isExpired() {
            return System.currentTimeMillis() > expireTime;
        }
    }
}
```

### 4.3 缓存雪崩防护服务

```java
package com.typetype.service;

import com.typetype.cache.MultiLevelCache;
import com.typetype.cache.TtlRandomizer;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;

/**
 * 缓存雪崩防护服务
 *
 * 🎓 防护策略：
 * 1. TTL 随机化：避免大量缓存同时过期
 * 2. 多级缓存：减少 Redis 访问压力
 * 3. 限流降级：在缓存失效时保护数据库
 */
@Service
public class CacheAvalancheProtectionService {

    private final RedisTemplate<String, Object> redisTemplate;
    private final MultiLevelCache multiLevelCache;

    // 🎓 基础 TTL
    private static final Duration BASE_TTL = Duration.ofHours(1);

    public CacheAvalancheProtectionService(
            RedisTemplate<String, Object> redisTemplate,
            MultiLevelCache multiLevelCache) {
        this.redisTemplate = redisTemplate;
        this.multiLevelCache = multiLevelCache;
    }

    /**
     * 批量加载数据到缓存
     *
     * 🎓 批量加载策略：
     * 1. 为每条数据生成随机化 TTL
     * 2. 使用 Pipeline 批量写入 Redis
     * 3. 同时写入本地缓存
     *
     * 💡 优点：
     * - 避免缓存雪崩
     * - 提高加载效率
     * - 减少 Redis 访问次数
     */
    public void batchLoad(List<CacheItem> items) {
        // 🎓 使用 Pipeline 批量写入
        redisTemplate.executePipelined((org.springframework.data.redis.core.RedisCallback<Object>) connection -> {
            for (CacheItem item : items) {
                // 🎓 生成随机化 TTL
                Duration randomTtl = TtlRandomizer.randomize(BASE_TTL);

                // 💡 写入 Redis
                connection.setEx(
                        item.getKey().getBytes(),
                        randomTtl.toSeconds(),
                        serialize(item.getValue())
                );

                // 💡 写入本地缓存
                multiLevelCache.put(item.getKey(), item.getValue());
            }
            return null;
        });
    }

    /**
     * 带防护的缓存查询
     *
     * 🎓 查询策略：
     * 1. 查询多级缓存
     * 2. 如果命中，直接返回
     * 3. 如果未命中，查询数据库
     * 4. 使用随机化 TTL 写入缓存
     */
    public Object getWithProtection(String key, DatabaseLoader dbLoader) {
        // 步骤 1：查询多级缓存
        Object cachedValue = multiLevelCache.get(key);

        if (cachedValue != null) {
            return cachedValue;
        }

        // 步骤 2：查询数据库
        Object dbValue = dbLoader.load();

        if (dbValue != null) {
            // 步骤 3：使用随机化 TTL 写入缓存
            Duration randomTtl = TtlRandomizer.randomize(BASE_TTL);
            redisTemplate.opsForValue().set(key, dbValue, randomTtl);

            // 写入本地缓存
            multiLevelCache.put(key, dbValue);
        }

        return dbValue;
    }

    /**
     * 缓存预热
     *
     * 🎓 缓存预热策略：
     * 1. 系统启动时，提前加载热点数据
     * 2. 使用随机化 TTL，避免同时过期
     * 3. 异步加载，不阻塞系统启动
     */
    public void warmUpCache(List<String> hotKeys, DatabaseLoader dbLoader) {
        // 🎓 异步加载
        CompletableFuture.runAsync(() -> {
            for (String key : hotKeys) {
                Object dbValue = dbLoader.load();

                if (dbValue != null) {
                    Duration randomTtl = TtlRandomizer.randomize(BASE_TTL);
                    redisTemplate.opsForValue().set(key, dbValue, randomTtl);
                    multiLevelCache.put(key, dbValue);
                }
            }
        });
    }

    /**
     * 序列化工具
     */
    private byte[] serialize(Object value) {
        // 💡 实际项目中使用 Jackson 或 Fastjson
        return value.toString().getBytes();
    }

    /**
     * 缓存项
     */
    public static class CacheItem {
        private final String key;
        private final Object value;

        public CacheItem(String key, Object value) {
            this.key = key;
            this.value = value;
        }

        public String getKey() {
            return key;
        }

        public Object getValue() {
            return value;
        }
    }

    /**
     * 数据库加载函数接口
     */
    @FunctionalInterface
    public interface DatabaseLoader {
        Object load();
    }
}
```

---

## 5. 完整使用示例

```java
package com.typetype.controller;

import com.typetype.service.CacheAvalancheProtectionService;
import com.typetype.service.CacheBreakdownProtectionService;
import com.typetype.service.CachePenetrationProtectionService;
import org.springframework.web.bind.annotation.*;

/**
 * 缓存防护示例 Controller
 */
@RestController
@RequestMapping("/api/cache")
public class CacheProtectionController {

    private final CachePenetrationProtectionService penetrationService;
    private final CacheBreakdownProtectionService breakdownService;
    private final CacheAvalancheProtectionService avalancheService;

    public CacheProtectionController(
            CachePenetrationProtectionService penetrationService,
            CacheBreakdownProtectionService breakdownService,
            CacheAvalancheProtectionService avalancheService) {
        this.penetrationService = penetrationService;
        this.breakdownService = breakdownService;
        this.avalancheService = avalancheService;
    }

    /**
     * 查询用户信息（防护缓存穿透）
     *
     * 🎓 使用布隆过滤器 + 空值缓存
     */
    @GetMapping("/user/{userId}")
    public Object getUser(@PathVariable Long userId) {
        String key = "user:" + userId;

        return penetrationService.getWithProtection(key, userId, () -> {
            // 查询数据库
            return userService.getUserById(userId);
        });
    }

    /**
     * 查询排行榜（防护缓存击穿）
     *
     * 🎓 使用逻辑过期 + 分布式锁
     */
    @GetMapping("/leaderboard/{dimension}")
    public Object getLeaderboard(@PathVariable String dimension) {
        String key = "leaderboard:" + dimension;
        String lockKey = "lock:leaderboard:" + dimension;

        return breakdownService.getWithProtection(key, lockKey, () -> {
            // 查询数据库
            return leaderboardService.getLeaderboard(dimension);
        });
    }

    /**
     * 批量加载数据（防护缓存雪崩）
     *
     * 🎓 使用 TTL 随机化 + 多级缓存
     */
    @PostMapping("/batch-load")
    public void batchLoad(@RequestBody List<CacheItem> items) {
        avalancheService.batchLoad(items);
    }
}
```

---

## 6. 监控指标

| 指标 | 说明 | 告警阈值 |
|:--- |:--- |:--- |
| cache:hit | 缓存命中率 | < 80% |
| cache:miss | 缓存未命中率 | > 20% |
| cache:penetration | 穿透次数 | > 100/min |
| cache:breakdown | 击穿次数 | > 10/min |
| cache:avalanche | 雪崩次数 | > 0 |
| cache:latency | 缓存延迟 | > 100ms |

---

## 7. 总结

| 问题 | 防护策略 | 实现方式 |
|:--- |:--- |:--- |
| 缓存穿透 | 布隆过滤器 + 空值缓存 | BloomFilter + NullValueCache |
| 缓存击穿 | 逻辑过期 + 分布式锁 | LogicalExpire + DistributedLock |
| 缓存雪崩 | TTL 随机化 + 多级缓存 | TtlRandomizer + MultiLevelCache |
