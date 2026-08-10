# Redis 配置参考

> ⚠️ 本文件为 typetype-server（服务端）侧设计，与本客户端仓库解耦；2026-07-03 起 draft 未更新。客户端开发者请忽略。

> 本文件是 typetype-server 的 Redis 配置参考实现。
> 包含 RedisConfig 配置类、序列化策略、连接池配置、application-redis.yml 等。

---

## 1. application-redis.yml

```yaml
# 🎓 Spring Boot 配置文件分离：
# - application.yml：通用配置
# - application-redis.yml：Redis 相关配置
# - 使用 spring.profiles.active=redis 激活

spring:
  data:
    redis:
      # 🎓 Redis 连接模式：
      # - standalone：单机模式（开发环境）
      # - sentinel：哨兵模式（高可用）
      # - cluster：集群模式（水平扩展）
      # 生产环境建议使用 sentinel 或 cluster
      host: localhost
      port: 6379
      password: ${REDIS_PASSWORD:}  # ⚠️ 生产环境必须设置密码，不要硬编码

      # 🎓 数据库选择：
      # - Redis 默认 16 个数据库（0-15）
      # - 不同业务使用不同数据库做隔离
      # - 但集群模式只支持 db0，所以生产环境建议用 key 前缀替代
      database: 0

      # 🎓 连接超时：
      # - connect-timeout：建立连接的超时时间
      # - timeout：命令执行的超时时间
      # - 生产环境根据网络状况调整，建议 3-5 秒
      timeout: 3000ms
      connect-timeout: 2000ms

      # 🎓 Lettuce 连接池配置（Spring Boot 默认使用 Lettuce）
      # Lettuce 是基于 Netty 的异步驱动，性能优于 Jedis
      lettuce:
        pool:
          # 最大活跃连接数
          # 💡 计算公式：并发请求数 / 平均命令耗时(秒)
          # 例如：100 并发 / 0.01s = 10000，但通常设置 20-50 足够
          max-active: 20

          # 最大空闲连接数
          # 💡 设置与 max-active 相同，避免频繁创建/销毁连接
          max-idle: 20

          # 最小空闲连接数
          # 💡 保持一定数量的空闲连接，减少首次请求延迟
          min-idle: 5

          # 获取连接最大等待时间
          # ⚠️ 设置太短会导致高并发时大量获取连接失败
          max-wait: 2000ms

        # 🎓 关闭超时时间：
        # - 应用关闭时等待连接池中连接关闭的时间
        # - 设置太短会导致连接泄露
        shutdown-timeout: 100ms

      # 🎓 SSL 配置（生产环境建议开启）
      # ssl:
      #   enabled: true
```

---

## 2. RedisConfig 配置类

```java
package com.typetype.config;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.impl.LaissezFaireSubTypeValidator;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.time.Duration;

/**
 * Redis 配置类
 *
 * 🎓 设计决策：
 * 1. 使用 JSON 序列化替代 JDK 序列化
 *    - JDK 序列化：体积大、可读性差、存在安全漏洞
 *    - JSON 序列化：体积小、可读性好、跨语言兼容
 *
 * 2. 使用 Lettuce 连接池
 *    - Lettuce 是基于 Netty 的异步驱动
 *    - 支持同步、异步、响应式三种调用方式
 *    - 线程安全，多线程可共享一个连接
 */
@Configuration
@EnableCaching  // 🎓 启用 Spring 缓存注解支持（@Cacheable、@CacheEvict 等）
public class RedisConfig {

    /**
     * 配置 Jackson ObjectMapper
     *
     * 🎓 为什么需要单独配置 ObjectMapper？
     * - 默认的 ObjectMapper 不支持 Java 8 时间类型（LocalDateTime 等）
     * - 需要注册 JavaTimeModule 才能正确序列化/反序列化
     * - 需要启用类型信息，否则反序列化时无法还原具体类型
     */
    private ObjectMapper objectMapper() {
        ObjectMapper om = new ObjectMapper();

        // 🎓 设置可见性：所有字段都可序列化
        // 默认只有 public 字段可见，这会导致 private 字段丢失
        om.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.ANY);

        // 🎓 启用类型信息：
        // - 序列化时在 JSON 中写入类名
        // - 反序列化时根据类名还原具体类型
        // ⚠️ 这会增加 JSON 体积，但能保证类型安全
        // ⚠️ 旧版本使用 DefaultTyping，已废弃，改用 LaissezFaireSubTypeValidator
        om.activateDefaultTyping(
                LaissezFaireSubTypeValidator.instance,
                ObjectMapper.DefaultTyping.NON_FINAL,
                JsonTypeInfo.As.PROPERTY
        );

        // 🎓 注册 Java 8 时间模块
        // 不注册的话，LocalDateTime 会序列化为数组而非字符串
        om.registerModule(new JavaTimeModule());

        return om;
    }

    /**
     * 配置 RedisTemplate
     *
     * 🎓 RedisTemplate 是 Spring Data Redis 的核心类：
     * - 封装了 Redis 的各种操作
     * - 提供类型安全的 API
     * - 支持事务和管道
     *
     * ⚠️ 默认的 RedisTemplate 使用 JDK 序列化，会导致：
     * - Key 前面有 \xac\xed\x00\x05t\x00\x07 这样的乱码
     * - Value 是二进制，无法在 Redis 客户端直接查看
     * - 跨语言调用时无法解析
     */
    @Bean
    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory factory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();

        // 🎓 设置连接工厂
        // RedisConnectionFactory 由 Spring Boot 自动配置（基于 application-redis.yml）
        template.setConnectionFactory(factory);

        // 🎓 Key 序列化器：使用 StringRedisSerializer
        // - 保证 Key 是可读的字符串
        // - 避免出现 \xac\xed\x00\x05t\x00\x07 这样的乱码
        StringRedisSerializer stringSerializer = new StringRedisSerializer();
        template.setKeySerializer(stringSerializer);
        template.setHashKeySerializer(stringSerializer);

        // 🎓 Value 序列化器：使用 GenericJackson2JsonRedisSerializer
        // - 序列化为 JSON 字符串
        // - 支持泛型类型
        // - 可在 Redis 客户端直接查看内容
        GenericJackson2JsonRedisSerializer jsonSerializer =
                new GenericJackson2JsonRedisSerializer(objectMapper());
        template.setValueSerializer(jsonSerializer);
        template.setHashValueSerializer(jsonSerializer);

        // 🎓 调用 afterPropertiesSet 确保配置生效
        // 不调用的话，某些属性可能为 null
        template.afterPropertiesSet();

        return template;
    }

    /**
     * 配置缓存管理器
     *
     * 🎓 Spring Cache 抽象层：
     * - 统一缓存操作接口
     * - 支持多种缓存实现（Redis、EhCache、Caffeine 等）
     * - 通过注解简化缓存代码（@Cacheable、@CacheEvict 等）
     *
     * ⚠️ 缓存管理器和 RedisTemplate 是独立的：
     * - 缓存管理器用于 @Cacheable 注解
     * - RedisTemplate 用于手动操作 Redis
     * - 两者可以共存，但序列化配置要一致
     */
    @Bean
    public CacheManager cacheManager(RedisConnectionFactory factory) {
        // 🎓 默认缓存配置
        RedisCacheConfiguration config = RedisCacheConfiguration.defaultCacheConfig()
                // 默认 TTL：1 小时
                // 💡 设置合理的默认 TTL，避免缓存永久驻留
                .entryTtl(Duration.ofHours(1))

                // Key 序列化：字符串
                .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                                .fromSerializer(new StringRedisSerializer())
                )

                // Value 序列化：JSON
                // 💡 使用与 RedisTemplate 相同的序列化器，保持一致性
                .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                                .fromSerializer(new GenericJackson2JsonRedisSerializer(objectMapper()))
                )

                // 🎓 不缓存 null 值
                // ⚠️ 缓存 null 值可能导致缓存穿透，但这里选择不缓存
                // 如果需要防护缓存穿透，应该在业务层处理
                .disableCachingNullValues();

        // 🎓 构建 RedisCacheManager
        return RedisCacheManager.builder(factory)
                .cacheDefaults(config)
                // 💡 可以为不同的缓存名称设置不同的配置
                // .withCacheConfiguration("leaderboard", config.entryTtl(Duration.ofMinutes(5)))
                .transactionAware()  // 🎓 支持事务，事务回滚时缓存也会回滚
                .build();
    }
}
```

---

## 3. 自定义缓存配置（按业务场景）

```java
package com.typetype.config;

import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.lang.reflect.Method;
import java.util.StringJoiner;

/**
 * 自定义缓存 Key 生成器
 *
 * 🎓 为什么需要自定义 Key 生成器？
 * - 默认的 KeyGenerator 使用方法参数的 hashCode
 * - 不同对象可能有相同的 hashCode（碰撞）
 * - 无法表达业务含义，调试困难
 */
@Configuration
public class CacheKeyConfig {

    /**
     * 排行榜缓存 Key 生成器
     *
     * 🎓 Key 设计原则：
     * 1. 有业务含义：便于在 Redis 客户端查找
     * 2. 唯一性：不同参数生成不同 Key
     * 3. 简洁性：避免 Key 过长浪费内存
     *
     * 生成格式：类名:方法名:参数1:参数2:...
     */
    @Bean("leaderboardKeyGenerator")
    public KeyGenerator leaderboardKeyGenerator() {
        return (Object target, Method method, Object... params) -> {
            StringJoiner joiner = new StringJoiner(":");

            // 添加类名（简化版，只取类名不含包名）
            joiner.add(target.getClass().getSimpleName());

            // 添加方法名
            joiner.add(method.getName());

            // 添加所有参数
            for (Object param : params) {
                if (param != null) {
                    joiner.add(param.toString());
                }
            }

            return joiner.toString();
        };
    }
}
```

---

## 4. Redis 连接健康检查

```java
package com.typetype.config;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Component;

/**
 * Redis 健康检查
 *
 * 🎓 Spring Boot Actuator 健康检查：
 * - 自动检测 Redis 连接状态
 * - 可通过 /actuator/health 端点查看
 * - 支持自定义检查逻辑
 */
@Component
public class RedisHealthIndicator implements HealthIndicator {

    private final RedisConnectionFactory connectionFactory;

    public RedisHealthIndicator(RedisConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public Health health() {
        try {
            // 🎓 通过 PING 命令检测连接
            // 如果连接正常，会返回 PONG
            connectionConnectionFactory.getConnection().ping();

            return Health.up()
                    .withDetail("redis", "Available")
                    .build();
        } catch (Exception e) {
            // ⚠️ 连接失败时返回 DOWN 状态
            // 生产环境应该配置告警
            return Health.down()
                    .withDetail("redis", "Not Available")
                    .withException(e)
                    .build();
        }
    }
}
```

---

## 5. 配置要点总结

| 配置项 | 推荐值 | 说明 |
|:--- |:--- |:--- |
| max-active | 20-50 | 根据并发量调整 |
| max-idle | 与 max-active 相同 | 避免频繁创建/销毁连接 |
| min-idle | 5-10 | 保持空闲连接，减少首次延迟 |
| timeout | 3000ms | 命令执行超时 |
| connect-timeout | 2000ms | 连接建立超时 |
| TTL（缓存） | 根据业务场景 | 排行榜 5 分钟，用户信息 1 小时 |

---

## 6. 常见问题

### Q: 为什么 Key 前面有乱码？

**原因**：使用了默认的 JDK 序列化器。

**解决**：在 RedisConfig 中设置 `StringRedisSerializer` 作为 Key 序列化器。

### Q: 为什么 Value 在 Redis 客户端是二进制？

**原因**：使用了 JDK 序列化器或未正确配置 JSON 序列化器。

**解决**：使用 `GenericJackson2JsonRedisSerializer` 作为 Value 序列化器。

### Q: 为什么 LocalDateTime 序列化后是数组？

**原因**：未注册 `JavaTimeModule`。

**解决**：在 ObjectMapper 中注册 `om.registerModule(new JavaTimeModule())`。
