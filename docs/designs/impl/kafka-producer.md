# Kafka Producer 实现

> ⚠️ 本文件为 typetype-server（服务端）侧设计，与本客户端仓库解耦；2026-07-03 起 draft 未更新。客户端开发者请忽略。

> 本文件是 typetype-server 的 Kafka Producer 参考实现。
> 设计目标：将用户成绩异步发送到 Kafka，解耦 HTTP 请求与数据处理。

---

## 1. ScoreEventProducer 类

```java
package com.typetype.kafka.producer;

import com.typetype.model.ScoreEvent;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;

/**
 * 成绩事件生产者
 *
 * 🎓 设计模式：Facade 模式
 * - 封装 KafkaTemplate 的复杂性，对外提供简洁的 API
 * - 业务层只需调用 sendScoreEvent()，无需关心 Kafka 底层细节
 *
 * 🎓 为什么用 @Component 而不是 @Service？
 * - 这里是基础设施层组件，不是业务服务层
 * - @Component 更通用，表示"Spring 管理的组件"
 * - 实际上两者功能相同，但语义不同
 */
@Component
public class ScoreEventProducer {

    private static final Logger log = LoggerFactory.getLogger(ScoreEventProducer.class);

    // 🎓 依赖注入：Spring 自动注入 KafkaTemplate
    // KafkaTemplate 是 Spring Kafka 提供的线程安全的生产者模板
    private final KafkaTemplate<String, ScoreEvent> kafkaTemplate;

    // 🎓 构造器注入 vs @Autowired：
    // - 构造器注入更安全（保证依赖不为 null）
    // - 便于单元测试（可以 mock 依赖）
    // - Spring 官方推荐的方式
    public ScoreEventProducer(KafkaTemplate<String, ScoreEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    /**
     * 发送成绩事件到 Kafka
     *
     * @param scoreEvent 成绩事件对象
     * @return CompletableFuture 异步结果
     *
     * 🎓 为什么返回 CompletableFuture？
     * - 异步非阻塞：调用线程不会被阻塞
     * - 可以链式处理：thenApply, thenAccept, exceptionally
     * - 符合响应式编程范式
     *
     * ⚠️ 常见陷阱：不要在生产者端阻塞等待结果
     * - kafkaTemplate.send() 是异步的
     * - 如果调用 .get() 会阻塞当前线程，失去异步意义
     * - 应该用 CompletableFuture 的回调处理结果
     */
    public CompletableFuture<SendResult<String, ScoreEvent>> sendScoreEvent(ScoreEvent scoreEvent) {
        // 🎓 Topic 命名规范：
        // - 使用点分隔：typetype.scores
        // - 体现业务域：typetype 是项目名，scores 是业务实体
        // - 便于 Kafka 管理和权限控制
        String topic = "typetype.scores";

        // 🎓 Partition Key 设计：
        // - 使用 userId 作为 key，保证同一用户的成绩进入同一 Partition
        // - 同一 Partition 内消息有序，便于按用户聚合
        // - Kafka 会对 key 进行 hash 决定 Partition
        String key = scoreEvent.getUserId();

        log.info("发送成绩事件: userId={}, score={}", key, scoreEvent.getScore());

        // 🎓 kafkaTemplate.send() 返回 ListenableFuture
        // Spring Kafka 2.5+ 返回 CompletableFuture
        CompletableFuture<SendResult<String, ScoreEvent>> future =
            kafkaTemplate.send(topic, key, scoreEvent);

        // 🎓 异步回调处理：
        // - 成功：记录日志，可用于监控
        // - 失败：记录错误，触发告警或重试
        future.whenComplete((result, ex) -> {
            if (ex == null) {
                // 成功回调
                RecordMetadata metadata = result.getRecordMetadata();
                log.info("消息发送成功: topic={}, partition={}, offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
            } else {
                // 失败回调
                log.error("消息发送失败: userId={}", key, ex);
                // ⚠️ 这里可以触发告警、写入死信队列等
                // 生产环境应该有完善的错误处理机制
            }
        });

        return future;
    }

    /**
     * 带自定义 Topic 的发送方法
     *
     * 🎓 为什么提供重载方法？
     * - 便于测试：可以发送到不同的 Topic
     * - 灵活性：未来可能有多种事件类型
     */
    public CompletableFuture<SendResult<String, ScoreEvent>> sendScoreEvent(
            String topic, ScoreEvent scoreEvent) {
        String key = scoreEvent.getUserId();
        return kafkaTemplate.send(topic, key, scoreEvent);
    }
}
```

---

## 2. ScoreEvent 模型

```java
package com.typetype.model;

import java.time.Instant;

/**
 * 成绩事件模型
 *
 * 🎓 领域驱动设计（DDD）：
 * - 这是一个值对象（Value Object）
 * - 不可变（immutable），所有字段 final
 * - 通过构造器创建，没有 setter
 *
 * 🎓 序列化考虑：
 * - Jackson 默认使用 getter 序列化
 * - 没有 setter 也能反序列化（使用 @JsonCreator）
 * - 不可变对象更安全，适合并发场景
 */
public class ScoreEvent {

    // 🎓 业务标识符：用于 Partition 路由
    private final String userId;

    // 🎓 业务数据：打字成绩
    private final int score;
    private final double accuracy;
    private final int wpm; // words per minute

    // 🎓 元数据：用于追踪和调试
    private final String textId; // 打字文本 ID
    private final Instant timestamp; // 事件时间戳
    private final String source; // 来源标识（客户端版本等）

    // 🎓 @JsonCreator 告诉 Jackson 如何反序列化
    // 参数名必须与 JSON 字段名匹配（或用 @JsonProperty）
    public ScoreEvent(
            String userId,
            int score,
            double accuracy,
            int wpm,
            String textId,
            Instant timestamp,
            String source) {
        this.userId = userId;
        this.score = score;
        this.accuracy = accuracy;
        this.wpm = wpm;
        this.textId = textId;
        this.timestamp = timestamp;
        this.source = source;
    }

    // 🎓 只有 getter，没有 setter → 不可变对象
    public String getUserId() { return userId; }
    public int getScore() { return score; }
    public double getAccuracy() { return accuracy; }
    public int getWpm() { return wpm; }
    public String getTextId() { return textId; }
    public Instant getTimestamp() { return timestamp; }
    public String getSource() { return source; }

    @Override
    public String toString() {
        return String.format("ScoreEvent{userId='%s', score=%d, wpm=%d, accuracy=%.2f}",
            userId, score, wpm, accuracy);
    }
}
```

---

## 3. Producer 配置

```java
package com.typetype.kafka.config;

import com.typetype.model.ScoreEvent;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

import java.util.HashMap;
import java.util.Map;

/**
 * Kafka Producer 配置类
 *
 * 🎓 @Configuration 的作用：
 * - 声明这是一个配置类，等价于 XML 配置文件
 * - @Bean 方法的返回值会被 Spring 管理
 * - 可以被 @ComponentScan 扫描到
 */
@Configuration
public class KafkaProducerConfig {

    /**
     * 创建 ProducerFactory
     *
     * 🎓 ProducerFactory 的职责：
     * - 创建 KafkaProducer 实例
     * - 管理 Producer 的生命周期
     * - 配置序列化器
     *
     * ⚠️ 为什么不用 @Value 注入配置？
     * - 这里用 Map 显式配置，便于理解
     * - 生产环境应该用 application.yml + @ConfigurationProperties
     */
    @Bean
    public ProducerFactory<String, ScoreEvent> producerFactory() {
        Map<String, Object> config = new HashMap<>();

        // 🎓 Kafka Broker 地址：
        // - 多个地址用逗号分隔：broker1:9092,broker2:9092
        // - 只需配置部分 Broker，Kafka 会自动发现集群
        config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");

        // 🎓 Key 序列化器：
        // - Key 用于 Partition 路由
        // - StringSerializer 将 String 转为 byte[]
        config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        // 🎓 Value 序列化器：
        // - JsonSerializer 将对象转为 JSON byte[]
        // - 默认使用 Jackson，需要 jackson-databind 依赖
        config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

        // 🎓 Ack 模式（可靠性保证）：
        // - acks=0: 不等待确认（最快，可能丢消息）
        // - acks=1: Leader 确认（平衡）
        // - acks=all: 所有 ISR 确认（最安全，最慢）
        config.put(ProducerConfig.ACKS_CONFIG, "all");

        // 🎓 重试次数：
        // - 网络抖动时自动重试
        // - 配合 enable.idempotence=true 使用更安全
        config.put(ProducerConfig.RETRIES_CONFIG, 3);

        // 🎓 幂等性：
        // - 开启后，即使重试也不会产生重复消息
        // - 要求 Kafka 0.11+
        // - 会略微降低吞吐量
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(config);
    }

    /**
     * 创建 KafkaTemplate
     *
     * 🎓 KafkaTemplate 的角色：
     * - Spring 对 KafkaProducer 的封装
     * - 提供 send() 方法，返回 ListenableFuture
     * - 线程安全，可以被多个线程共享
     */
    @Bean
    public KafkaTemplate<String, ScoreEvent> kafkaTemplate() {
        return new KafkaTemplate<>(producerFactory());
    }
}
```

---

## 4. 使用示例

```java
package com.typetype.controller;

import com.typetype.kafka.producer.ScoreEventProducer;
import com.typetype.model.ScoreEvent;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
public class ScoreController {

    private final ScoreEventProducer scoreEventProducer;

    public ScoreController(ScoreEventProducer scoreEventProducer) {
        this.scoreEventProducer = scoreEventProducer;
    }

    /**
     * 提交成绩
     *
     * 🎓 为什么用 ResponseEntity？
     * - 可以控制 HTTP 状态码
     * - 可以返回自定义响应体
     * - RESTful API 最佳实践
     */
    @PostMapping("/api/scores")
    public ResponseEntity<String> submitScore(@RequestBody ScoreEvent scoreEvent) {
        // 🎓 异步发送，不阻塞 HTTP 请求
        // 客户端立即得到响应，后台异步处理
        scoreEventProducer.sendScoreEvent(scoreEvent);

        // 🎓 202 Accepted 表示请求已接受，但尚未处理完成
        // 适合异步处理场景
        return ResponseEntity.accepted().body("Score submitted");
    }
}
```

---

## 5. 面试要点

### Q: Kafka Producer 发送消息的流程？

1. **序列化**：将 Key/Value 转为 byte[]
2. **分区**：根据 Key 的 hash 决定 Partition
3. **批量发送**：linger.ms 时间内积累消息批量发送
4. **压缩**：可选压缩（gzip, snappy, lz4）
5. **发送到 Broker**：网络传输
6. **等待确认**：根据 acks 配置等待 Broker 确认

### Q: 如何保证消息不丢失？

1. **acks=all**：等待所有 ISR 副本确认
2. **retries > 0**：失败自动重试
3. **enable.idempotence=true**：防止重试产生重复
4. **min.insync.replicas=2**：至少 2 个副本同步

### Q: 如何保证消息有序？

1. **同一 Partition 内有序**：通过 Partition Key 保证
2. **全局有序**：只用一个 Partition（不推荐，影响性能）
3. **业务有序**：按 userId 路由，保证同一用户的成绩有序

### Q: KafkaTemplate 是线程安全的吗？

- **是**：KafkaTemplate 内部使用 Producer 实例池
- **可以共享**：一个 KafkaTemplate 实例可以被多个线程使用
- **推荐**：在 Spring 中注入单例即可

---

## 6. 常见陷阱

### 陷阱 1：阻塞等待结果

```java
// ❌ 错误：阻塞当前线程
SendResult<String, ScoreEvent> result = kafkaTemplate.send(...).get();

// ✅ 正确：异步回调
kafkaTemplate.send(...).whenComplete((result, ex) -> {
    // 处理结果
});
```

### 陷阱 2：没有处理异常

```java
// ❌ 错误：忽略异常
kafkaTemplate.send(...);

// ✅ 正确：处理异常
kafkaTemplate.send(...).exceptionally(ex -> {
    log.error("发送失败", ex);
    // 告警、重试、写死信队列
    return null;
});
```

### 陷阱 3：Key 设计不合理

```java
// ❌ 错误：使用随机 Key，消息分散到不同 Partition
String key = UUID.randomUUID().toString();

// ✅ 正确：使用业务 Key，保证相关消息进入同一 Partition
String key = scoreEvent.getUserId();
```

### 陷阱 4：没有配置重试

```java
// ❌ 错误：网络抖动时直接失败
config.put(ProducerConfig.RETRIES_CONFIG, 0);

// ✅ 正确：配置重试次数
config.put(ProducerConfig.RETRIES_CONFIG, 3);
```

---

## 7. 生产环境建议

### 监控指标

- **发送成功率**：成功数 / 总数
- **发送延迟**：从发送到确认的时间
- **队列积压**：Producer 内部队列大小
- **错误率**：失败次数 / 总次数

### 告警规则

- 发送失败率 > 1%
- 发送延迟 > 100ms
- 队列积压 > 10000

### 性能调优

- **batch.size**：批量大小，默认 16384
- **linger.ms**：等待时间，默认 0
- **compression.type**：压缩类型，默认 none
- **buffer.memory**：缓冲区大小，默认 33554432
