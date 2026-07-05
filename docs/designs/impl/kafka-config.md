# Kafka 配置参考

> 本文件是 typetype-server 的 Kafka 配置参考实现。
> 包含 application.yml 配置、Topic 创建、序列化配置等。

---

## 1. application-kafka.yml

```yaml
# 🎓 Spring Boot 配置文件分离：
# - application.yml：通用配置
# - application-kafka.yml：Kafka 相关配置
# - 使用 spring.profiles.active=kafka 激活

spring:
  kafka:
    # 🎓 Bootstrap Servers：
    # - Kafka Broker 地址列表
    # - 只需配置部分 Broker，Kafka 会自动发现集群
    # - 生产环境建议配置 3 个以上，提高可用性
    bootstrap-servers:
      - kafka-broker1:9092
      - kafka-broker2:9092
      - kafka-broker3:9092

    # 🎓 Producer 配置
    producer:
      # Key 序列化器
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      # Value 序列化器（使用 JSON）
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer

      # 🎓 Ack 模式：
      # - 0: 不等待确认（最快，可能丢消息）
      # - 1: Leader 确认（平衡）
      # - all: 所有 ISR 确认（最安全，最慢）
      acks: all

      # 🎓 重试次数：
      # - 网络抖动时自动重试
      # - 配合幂等性使用更安全
      retries: 3

      # 🎓 幂等性：
      # - 开启后，即使重试也不会产生重复消息
      # - 要求 Kafka 0.11+
      properties:
        enable.idempotence: true

      # 🎓 批量发送配置：
      # - batch.size: 批量大小（字节）
      # - linger.ms: 等待时间（毫秒）
      # - 增大这两个值可以提高吞吐量，但会增加延迟
      batch-size: 16384
      linger-ms: 5

      # 🎓 压缩配置：
      # - none: 不压缩
      # - gzip: 压缩率高，CPU 开销大
      # - snappy: 压缩率中等，CPU 开销小
      # - lz4: 压缩率低，CPU 开销最小
      compression-type: snappy

      # 🎓 缓冲区大小：
      # - Producer 内部缓冲区大小
      # - 默认 32MB
      # - 如果发送速度超过网络速度，会使用缓冲区
      buffer-memory: 33554432

    # 🎓 Consumer 配置
    consumer:
      # Key 反序列化器
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      # Value 反序列化器（使用 JSON）
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer

      # 🎓 消费者组 ID：
      # - 同一组的消费者共享消息
      # - 不同组的消费者独立消费所有消息
      # - 命名规范：业务域-功能-group
      group-id: typetype-score-group

      # 🎓 自动提交偏移量：
      # - true: 自动提交（简单，可能丢消息）
      # - false: 手动提交（可靠，推荐）
      enable-auto-commit: false

      # 🎓 偏移量重置策略：
      # - earliest: 从最早的消息开始消费
      # - latest: 从最新的消息开始消费
      # - none: 没有偏移量时抛出异常
      auto-offset-reset: earliest

      # 🎓 会话超时：
      # - Consumer 与 Broker 的心跳超时时间
      # - 超时后认为 Consumer 死亡，触发 Rebalance
      # - 默认 10s，网络差时可以调大
      session-timeout: 30000

      # 🎓 最大拉取记录数：
      # - 单次 poll() 最多返回的记录数
      # - 控制单次处理的消息量，避免内存溢出
      max-poll-records: 500

      # 🎓 JSON 反序列化配置
      properties:
        # 🎓 信任的包路径：
        # - JsonDeserializer 的安全机制
        # - 只允许反序列化指定包下的类
        # - 防止反序列化漏洞
        spring.json.trusted.packages: com.typetype.model

        # 🎓 类型映射：
        # - 将 JSON 类型映射到 Java 类型
        # - 适用于多态类型
        # spring.json.type.mapping: scoreEvent:com.typetype.model.ScoreEvent

    # 🎓 Listener 配置
    listener:
      # 🎓 确认模式：
      # - MANUAL: 手动确认
      # - MANUAL_IMMEDIATE: 立即手动确认
      # - RECORD: 每条消息确认
      # - BATCH: 批量确认
      ack-mode: manual

      # 🎓 并发消费者数：
      # - 设置为 3，表示同时有 3 个消费者线程
      # - 每个线程独立消费 Partition
      # - 不能超过 Partition 数量
      concurrency: 3

      # 🎓 消费类型：
      # - single: 单条消费
      # - batch: 批量消费
      type: single

---
```

---

## 2. KafkaAdminConfig - Topic 创建

```java
package com.typetype.kafka.config;

import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

import java.util.HashMap;
import java.util.Map;

/**
 * Kafka Admin 配置类
 *
 * 🎓 KafkaAdmin 的作用：
 * - 自动创建 Topic
 * - 管理 Topic 配置
 * - 支持 Topic 配置变更
 *
 * 🎓 为什么用代码创建 Topic？
 * - 版本控制：Topic 配置可以和代码一起管理
 * - 自动化：应用启动时自动创建
 * - 一致性：保证 Topic 配置在所有环境一致
 */
@Configuration
public class KafkaAdminConfig {

    /**
     * 创建 KafkaAdmin Bean
     *
     * 🎓 KafkaAdmin 的职责：
     * - 连接到 Kafka Broker
     * - 执行 Admin 操作（创建 Topic、修改配置等）
     * - 应用启动时自动执行
     */
    @Bean
    public KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        // 🎓 Broker 地址：与 Producer/Consumer 相同
        configs.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        return new KafkaAdmin(configs);
    }

    /**
     * 创建成绩 Topic
     *
     * @return NewTopic 对象
     *
     * 🎓 Topic 设计原则：
     * - 分区数：根据吞吐量需求设置
     *   - 分区数 = max(预期吞吐量 / 单分区吞吐量, 消费者数量)
     *   - 示例：预期 1000 msg/s，单分区 100 msg/s，消费者 3 个
     *   - 分区数 = max(10, 3) = 10
     * - 副本数：根据可靠性需求设置
     *   - 副本数 = min(Broker 数量, 3)
     *   - 示例：3 个 Broker，副本数 = 3
     */
    @Bean
    public NewTopic scoreTopic() {
        return new NewTopic(
            "typetype.scores",  // Topic 名称
            10,                 // 分区数
            (short) 3           // 副本数
        );
        // 🎓 可以链式调用配置更多属性
        // .configs(Map.of(
        //     "retention.ms", "604800000",  // 保留 7 天
        //     "cleanup.policy", "delete"     // 删除策略
        // ))
    }

    /**
     * 创建排行榜 Topic
     *
     * 🎓 不同 Topic 可以有不同的配置：
     * - 分区数：根据消费者数量设置
     * - 副本数：根据可靠性需求设置
     * - 保留时间：根据业务需求设置
     */
    @Bean
    public NewTopic leaderboardTopic() {
        return new NewTopic(
            "typetype.leaderboard",
            5,                  // 分区数较少，因为消费者较少
            (short) 3
        );
    }

    /**
     * 创建死信队列 Topic
     *
     * 🎓 死信队列（DLQ）Topic 命名规范：
     * - 原 Topic 名称 + .DLT
     * - 便于识别和关联
     * - 配置与原 Topic 相似，但保留时间更长
     */
    @Bean
    public NewTopic scoreDltTopic() {
        return new NewTopic(
            "typetype.scores.DLT",
            3,                  // 分区数较少，错误消息不会太多
            (short) 3
        );
    }

    /**
     * 创建用户统计 Topic
     *
     * 🎓 事件溯源（Event Sourcing）：
     * - 所有用户操作都记录为事件
     * - 可以重放事件重建状态
     * - 便于审计和调试
     */
    @Bean
    public NewTopic userStatsTopic() {
        return new NewTopic(
            "typetype.user.stats",
            10,
            (short) 3
        );
    }

    /**
     * 使用 TopicBuilder 创建 Topic（推荐方式）
     *
     * 🎓 TopicBuilder 是 Spring Kafka 2.6+ 提供的 Builder 模式
     * - 更流畅的 API
     * - 支持更多配置选项
     * - 代码更清晰
     */
    @Bean
    public NewTopic scoreTopicV2() {
        return org.springframework.kafka.config.TopicBuilder.name("typetype.scores.v2")
            .partitions(10)
            .replicas(3)
            // 🎓 配置 Topic 属性
            .config("retention.ms", "604800000")  // 保留 7 天
            .config("cleanup.policy", "delete")    // 删除策略
            .config("max.message.bytes", "1048576") // 最大消息大小 1MB
            // 🎓 压缩配置
            .config("compression.type", "snappy")
            .build();
    }
}
```

---

## 3. 序列化/反序列化配置

```java
package com.typetype.kafka.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

/**
 * 序列化/反序列化配置
 *
 * 🎓 为什么需要单独配置？
 * - 默认的 ObjectMapper 可能不满足需求
 * - 需要注册自定义模块（如 Java 8 时间模块）
 * - 需要配置序列化选项
 */
@Configuration
public class KafkaSerializationConfig {

    /**
     * 配置 ObjectMapper
     *
     * 🎓 ObjectMapper 是 Jackson 的核心类：
     * - 负责 Java 对象与 JSON 的转换
     * - 支持自定义序列化/反序列化
     * - 线程安全，可以共享
     */
    @Bean
    public ObjectMapper objectMapper() {
        ObjectMapper mapper = new ObjectMapper();

        // 🎓 注册 Java 8 时间模块：
        // - 支持 Instant, LocalDateTime, LocalDate 等
        // - 默认 Jackson 不支持 Java 8 时间类型
        mapper.registerModule(new JavaTimeModule());

        // 🎓 禁用日期时间戳序列化：
        // - 默认：将日期序列化为时间戳（数字）
        // - 禁用后：序列化为 ISO-8601 格式（字符串）
        // - 例如：2024-01-01T12:00:00Z
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        return mapper;
    }

    /**
     * 配置 JsonSerializer
     *
     * 🎓 JsonSerializer 的作用：
     * - 将 Java 对象序列化为 JSON byte[]
     * - 使用 ObjectMapper 进行转换
     * - 支持自定义配置
     */
    @Bean
    public JsonSerializer<Object> jsonSerializer() {
        JsonSerializer<Object> serializer = new JsonSerializer<>();
        // 🎓 使用自定义的 ObjectMapper
        serializer.setObjectMapper(objectMapper());
        return serializer;
    }

    /**
     * 配置 JsonDeserializer
     *
     * 🎓 JsonDeserializer 的作用：
     * - 将 JSON byte[] 反序列化为 Java 对象
     * - 使用 ObjectMapper 进行转换
     * - 支持类型映射和信任包配置
     */
    @Bean
    public JsonDeserializer<Object> jsonDeserializer() {
        JsonDeserializer<Object> deserializer = new JsonDeserializer<>();
        // 🎓 使用自定义的 ObjectMapper
        deserializer.setObjectMapper(objectMapper());
        // 🎓 信任的包路径：
        // - 安全机制，防止反序列化漏洞
        // - 只允许反序列化指定包下的类
        deserializer.addTrustedPackages("com.typetype.model");
        return deserializer;
    }
}
```

---

## 4. application.yml 完整配置

```yaml
# 🎓 Spring Boot 主配置文件
# 包含通用配置和 Profile 激活

spring:
  application:
    name: typetype-server

  # 🎓 Profile 激活：
  # - 可以激活多个 Profile
  # - kafka Profile 激活 Kafka 相关配置
  profiles:
    active:
      - kafka
      - redis

  # 🎓 Jackson 配置（全局）：
  # - 与 Kafka 序列化配置保持一致
  jackson:
    date-format: yyyy-MM-dd HH:mm:ss
    time-zone: UTC
    default-property-inclusion: non_null

# 🎓 日志配置
logging:
  level:
    # 🎓 Kafka 日志级别：
    # - INFO：正常运行
    # - DEBUG：调试问题
    # - WARN：警告信息
    org.apache.kafka: INFO
    org.springframework.kafka: INFO

  # 🎓 日志格式：
  # - 包含时间戳、线程、级别、类名、消息
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n"

# 🎓 自定义配置（可选）：
# - 可以在 application.yml 中定义自定义配置
# - 使用 @ConfigurationProperties 读取
typetype:
  kafka:
    # 成绩 Topic 名称
    score-topic: typetype.scores
    # 排行榜 Topic 名称
    leaderboard-topic: typetype.leaderboard
    # 死信队列 Topic 名称
    dlt-topic: typetype.scores.DLT
    # 消费者组 ID
    consumer-group: typetype-score-group
    # 并发消费者数
    concurrency: 3
```

---

## 5. 自定义配置类

```java
package com.typetype.kafka.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 自定义 Kafka 配置类
 *
 * 🎓 @ConfigurationProperties 的作用：
 * - 将 application.yml 中的配置映射到 Java 对象
 * - 支持类型安全的配置访问
 * - 支持配置校验
 *
 * 🎓 prefix 配置：
 * - 指定配置的前缀
 * - 例如：typetype.kafka.score-topic
 */
@Configuration
@ConfigurationProperties(prefix = "typetype.kafka")
public class TypetypeKafkaProperties {

    // 🎓 成绩 Topic 名称
    private String scoreTopic = "typetype.scores";

    // 🎓 排行榜 Topic 名称
    private String leaderboardTopic = "typetype.leaderboard";

    // 🎓 死信队列 Topic 名称
    private String dltTopic = "typetype.scores.DLT";

    // 🎓 消费者组 ID
    private String consumerGroup = "typetype-score-group";

    // 🎓 并发消费者数
    private int concurrency = 3;

    // 🎓 Getter 和 Setter
    // Spring Boot 会自动注入配置值

    public String getScoreTopic() {
        return scoreTopic;
    }

    public void setScoreTopic(String scoreTopic) {
        this.scoreTopic = scoreTopic;
    }

    public String getLeaderboardTopic() {
        return leaderboardTopic;
    }

    public void setLeaderboardTopic(String leaderboardTopic) {
        this.leaderboardTopic = leaderboardTopic;
    }

    public String getDltTopic() {
        return dltTopic;
    }

    public void setDltTopic(String dltTopic) {
        this.dltTopic = dltTopic;
    }

    public String getConsumerGroup() {
        return consumerGroup;
    }

    public void setConsumerGroup(String consumerGroup) {
        this.consumerGroup = consumerGroup;
    }

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }
}
```

---

## 6. 使用自定义配置

```java
package com.typetype.kafka.producer;

import com.typetype.kafka.config.TypetypeKafkaProperties;
import com.typetype.model.ScoreEvent;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * 使用自定义配置的 Producer
 *
 * 🎓 为什么使用自定义配置？
 * - 集中管理配置，便于维护
 * - 类型安全，避免硬编码
 * - 支持多环境配置
 */
@Component
public class ConfigurableScoreEventProducer {

    private final KafkaTemplate<String, ScoreEvent> kafkaTemplate;
    private final TypetypeKafkaProperties properties;

    public ConfigurableScoreEventProducer(
            KafkaTemplate<String, ScoreEvent> kafkaTemplate,
            TypetypeKafkaProperties properties) {
        this.kafkaTemplate = kafkaTemplate;
        this.properties = properties;
    }

    /**
     * 发送成绩事件
     *
     * 🎓 使用配置的 Topic 名称
     * - 从 TypetypeKafkaProperties 读取
     * - 支持动态配置，无需修改代码
     */
    public void sendScoreEvent(ScoreEvent scoreEvent) {
        // 🎓 使用配置的 Topic 名称
        String topic = properties.getScoreTopic();
        String key = scoreEvent.getUserId();

        kafkaTemplate.send(topic, key, scoreEvent);
    }
}
```

---

## 7. 多环境配置

### application-dev.yml（开发环境）

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      retries: 0  # 开发环境不需要重试
    consumer:
      auto-offset-reset: latest  # 开发环境从最新消息开始

logging:
  level:
    org.apache.kafka: DEBUG  # 开发环境开启 DEBUG 日志
```

### application-prod.yml（生产环境）

```yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-broker1:9092
      - kafka-broker2:9092
      - kafka-broker3:9092
    producer:
      retries: 3
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      auto-offset-reset: earliest
      session-timeout: 30000

logging:
  level:
    org.apache.kafka: WARN  # 生产环境只记录警告
```

---

## 8. 面试要点

### Q: Kafka 配置的最佳实践？

1. **分离配置**：不同环境使用不同配置文件
2. **类型安全**：使用 @ConfigurationProperties
3. **默认值**：提供合理的默认值
4. **文档化**：配置项添加注释说明

### Q: 如何选择分区数？

- **公式**：分区数 = max(预期吞吐量 / 单分区吞吐量, 消费者数量)
- **示例**：
  - 预期吞吐量：1000 msg/s
  - 单分区吞吐量：100 msg/s
  - 消费者数量：3
  - 分区数 = max(10, 3) = 10

### Q: 如何选择副本数？

- **原则**：副本数 <= Broker 数量
- **推荐**：生产环境至少 3 副本
- **权衡**：副本数越多，可靠性越高，但写入延迟也越高

### Q: 序列化方案选择？

- **JSON**：通用性好，可读性强，性能中等
- **Avro**：性能好，支持 Schema 演进，需要 Schema Registry
- **Protobuf**：性能最好，跨语言支持好，需要 .proto 文件

### Q: 如何处理序列化异常？

1. **使用 ErrorHandlingDeserializer**：反序列化失败时不会抛出异常
2. **配置信任包**：防止反序列化漏洞
3. **记录错误日志**：便于排查问题
4. **发送到死信队列**：人工处理

---

## 9. 常见陷阱

### 陷阱 1：配置不一致

```yaml
# ❌ 错误：Producer 和 Consumer 配置不一致
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.IntegerDeserializer

# ✅ 正确：保持序列化/反序列化一致
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

### 陷阱 2：没有配置信任包

```yaml
# ❌ 错误：没有配置信任包，反序列化会失败
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer

# ✅ 正确：配置信任包
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.typetype.model
```

### 陷阱 3：分区数设置不合理

```java
// ❌ 错误：分区数太少，限制并发
new NewTopic("topic", 1, (short) 3);

// ❌ 错误：分区数太多，增加开销
new NewTopic("topic", 1000, (short) 3);

// ✅ 正确：根据需求设置合理的分区数
new NewTopic("topic", 10, (short) 3);
```

### 陷阱 4：没有配置保留时间

```java
// ❌ 错误：没有配置保留时间，数据会无限增长
new NewTopic("topic", 10, (short) 3);

// ✅ 正确：配置合理的保留时间
NewTopic topic = TopicBuilder.name("topic")
    .partitions(10)
    .replicas(3)
    .config("retention.ms", "604800000")  // 保留 7 天
    .build();
```

---

## 10. 生产环境建议

### 配置管理

- **集中管理**：使用配置中心（如 Nacos, Consul）
- **版本控制**：配置文件纳入版本控制
- **环境隔离**：不同环境使用不同配置
- **敏感信息**：使用环境变量或加密存储

### 监控配置

- **配置热更新**：支持动态修改配置
- **配置校验**：启动时校验配置合法性
- **配置审计**：记录配置变更历史

### 性能调优

- **批量配置**：调整 batch.size 和 linger.ms
- **压缩配置**：根据网络带宽选择压缩算法
- **缓冲区配置**：根据发送速度调整 buffer.memory
- **并发配置**：根据 Partition 数量调整 concurrency
