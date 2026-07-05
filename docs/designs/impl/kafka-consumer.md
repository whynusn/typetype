# Kafka Consumer 实现

> 本文件是 typetype-server 的 Kafka Consumer 参考实现。
> 设计目标：消费成绩事件，进行实时聚合和存储。

---

## 1. ScoreIngestionConsumer 类

```java
package com.typetype.kafka.consumer;

import com.typetype.model.ScoreEvent;
import com.typetype.service.ScoreAggregationService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

/**
 * 成绩事件消费者
 *
 * 🎓 设计模式：消费者模式（Consumer Pattern）
 * - 被动消费：从 Topic 拉取消息
 * - 业务处理：聚合、存储、分析
 * - 确认机制：处理完成后手动 ACK
 *
 * 🎓 @Component vs @Service：
 * - 这里是基础设施层组件
 * - 负责消息消费，不是业务逻辑
 * - 实际的业务逻辑委托给 ScoreAggregationService
 */
@Component
public class ScoreIngestionConsumer {

    private static final Logger log = LoggerFactory.getLogger(ScoreIngestionConsumer.class);

    private final ScoreAggregationService aggregationService;

    public ScoreIngestionConsumer(ScoreAggregationService aggregationService) {
        this.aggregationService = aggregationService;
    }

    /**
     * 消费成绩事件
     *
     * @param record Kafka 消息记录
     * @param acknowledgment 手动确认对象
     *
     * 🎓 @KafkaListener 的作用：
     * - 声明这是一个 Kafka 消费者方法
     * - 自动订阅指定的 Topic
     * - 支持批量消费、并发消费等配置
     *
     * 🎓 为什么用手动确认（Manual Ack）？
     * - 自动确认：消息拉取后立即确认，可能丢失
     * - 手动确认：处理完成后才确认，更可靠
     * - 生产环境推荐手动确认
     *
     * ⚠️ 常见陷阱：忘记调用 acknowledgment.acknowledge()
     * - 消息会被重复消费
     * - 可能导致数据不一致
     */
    @KafkaListener(
        topics = "typetype.scores",           // 订阅的 Topic
        groupId = "score-ingestion-group",    // 消费者组 ID
        containerFactory = "kafkaListenerContainerFactory"  // 容器工厂
    )
    public void consumeScoreEvent(
            ConsumerRecord<String, ScoreEvent> record,
            Acknowledgment acknowledgment) {

        String userId = record.key();
        ScoreEvent scoreEvent = record.value();

        log.info("收到成绩事件: topic={}, partition={}, offset={}, userId={}",
            record.topic(),
            record.partition(),
            record.offset(),
            userId);

        try {
            // 🎓 业务处理：委托给 Service 层
            // 保持 Consumer 类职责单一，只负责消息接收和确认
            aggregationService.aggregateScore(scoreEvent);

            // 🎓 手动确认：消息处理成功
            // 必须在业务逻辑执行成功后才调用
            acknowledgment.acknowledge();

            log.info("成绩事件处理成功: userId={}", userId);

        } catch (Exception e) {
            // 🎓 异常处理：
            // - 记录错误日志
            // - 不调用 acknowledge()，消息会被重新消费
            // - 可以配置重试次数和死信队列
            log.error("成绩事件处理失败: userId={}", userId, e);

            // ⚠️ 这里可以选择：
            // 1. 抛出异常，让框架重试
            // 2. 发送到死信队列
            // 3. 记录到数据库，人工处理
            throw new RuntimeException("消息处理失败", e);
        }
    }

    /**
     * 批量消费示例
     *
     * 🎓 批量消费的优势：
     * - 减少网络开销：一次拉取多条消息
     * - 提高吞吐量：批量处理更高效
     * - 适合高吞吐场景
     *
     * @param records 消息列表
     * @param acknowledgment 手动确认
     */
    @KafkaListener(
        topics = "typetype.scores",
        groupId = "score-batch-processing-group",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consumeScoreEventsBatch(
            java.util.List<ConsumerRecord<String, ScoreEvent>> records,
            Acknowledgment acknowledgment) {

        log.info("批量消费 {} 条消息", records.size());

        try {
            for (ConsumerRecord<String, ScoreEvent> record : records) {
                ScoreEvent scoreEvent = record.value();
                aggregationService.aggregateScore(scoreEvent);
            }

            // 🎓 批量确认：所有消息处理完成后一次性确认
            acknowledgment.acknowledge();

            log.info("批量处理完成: {} 条消息", records.size());

        } catch (Exception e) {
            log.error("批量处理失败", e);
            // ⚠️ 批量消费的异常处理更复杂
            // 需要考虑部分成功、部分失败的情况
            throw new RuntimeException("批量处理失败", e);
        }
    }
}
```

---

## 2. Consumer 配置

```java
package com.typetype.kafka.config;

import com.typetype.model.ScoreEvent;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

import java.util.HashMap;
import java.util.Map;

/**
 * Kafka Consumer 配置类
 *
 * 🎓 配置类的作用：
 * - 集中管理所有 Kafka 配置
 * - 便于维护和修改
 * - 支持多环境配置
 */
@Configuration
public class KafkaConsumerConfig {

    /**
     * 创建 ConsumerFactory
     *
     * 🎓 ConsumerFactory 的职责：
     * - 创建 KafkaConsumer 实例
     * - 配置反序列化器
     * - 管理消费者生命周期
     */
    @Bean
    public ConsumerFactory<String, ScoreEvent> consumerFactory() {
        Map<String, Object> config = new HashMap<>();

        // 🎓 Broker 地址：与 Producer 相同
        config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");

        // 🎓 Key 反序列化器：
        // - 与 Producer 的 Key 序列化器对应
        // - StringDeserializer 将 byte[] 转为 String
        config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);

        // 🎓 Value 反序列化器：
        // - 使用 ErrorHandlingDeserializer 包装
        // - 反序列化失败时不会抛出异常，而是发送到错误 Topic
        config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, ErrorHandlingDeserializer.class);
        config.put(ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS, JsonDeserializer.class.getName());

        // 🎓 JsonDeserializer 配置：
        // - trusted.packages：允许反序列化的包路径
        // - 不配置的话，反序列化会失败（安全机制）
        config.put(JsonDeserializer.TRUSTED_PACKAGES, "com.typetype.model");

        // 🎓 消费者组 ID：
        // - 同一组的消费者共享消息
        // - 不同组的消费者独立消费所有消息
        // - 命名规范：业务域-功能-group
        config.put(ConsumerConfig.GROUP_ID_CONFIG, "score-ingestion-group");

        // 🎓 自动提交偏移量：
        // - enable.auto.commit=true：自动提交（简单，可能丢消息）
        // - enable.auto.commit=false：手动提交（可靠，推荐）
        config.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

        // 🎓 偏移量重置策略：
        // - earliest：从最早的消息开始消费
        // - latest：从最新的消息开始消费
        // - none：没有偏移量时抛出异常
        config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        // 🎓 会话超时：
        // - Consumer 与 Broker 的心跳超时时间
        // - 超时后认为 Consumer 死亡，触发 Rebalance
        // - 默认 10s，网络差时可以调大
        config.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 30000);

        // 🎓 最大拉取记录数：
        // - 单次 poll() 最多返回的记录数
        // - 控制单次处理的消息量，避免内存溢出
        config.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 500);

        return new DefaultKafkaConsumerFactory<>(config);
    }

    /**
     * 创建单条消费的监听容器工厂
     *
     * 🎓 ConcurrentKafkaListenerContainerFactory 的作用：
     * - 创建 KafkaListenerContainer 实例
     * - 配置并发数、确认模式等
     * - 支持多个 @KafkaListener 方法
     */
    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, ScoreEvent>
            kafkaListenerContainerFactory() {

        ConcurrentKafkaListenerContainerFactory<String, ScoreEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory());

        // 🎓 并发消费者数：
        // - 设置为 3，表示同时有 3 个消费者线程
        // - 每个线程独立消费 Partition
        // - 不能超过 Partition 数量（否则多余的消费者会闲置）
        factory.setConcurrency(3);

        // 🎓 手动确认模式：
        // - MANUAL：需要手动调用 acknowledgment.acknowledge()
        // - MANUAL_IMMEDIATE：立即提交偏移量
        // - 生产环境推荐 MANUAL
        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL);

        // 🎓 错误处理：
        // - 默认行为：抛出异常，停止消费
        // - 可以配置 ErrorHandler，实现重试、死信队列等
        // factory.setErrorHandler(new DefaultErrorHandler());

        return factory;
    }

    /**
     * 创建批量消费的监听容器工厂
     *
     * 🎓 批量消费 vs 单条消费：
     * - 批量：一次 poll 多条消息，批量处理
     * - 单条：一次 poll 一条消息，逐条处理
     * - 批量吞吐量更高，但错误处理更复杂
     */
    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, ScoreEvent>
            batchKafkaListenerContainerFactory() {

        ConcurrentKafkaListenerContainerFactory<String, ScoreEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory());
        factory.setConcurrency(3);

        // 🎓 开启批量消费模式
        factory.setBatchListener(true);

        // 🎓 批量确认模式
        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL);

        return factory;
    }
}
```

---

## 3. ScoreAggregationService

```java
package com.typetype.service;

import com.typetype.model.ScoreEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * 成绩聚合服务
 *
 * 🎓 领域服务（Domain Service）：
 * - 包含业务逻辑
 * - 不属于任何实体
 * - 协调多个实体或外部服务
 *
 * 🎓 为什么用 @Service？
 * - 语义明确：这是业务服务层
 * - Spring 会自动扫描和管理
 */
@Service
public class ScoreAggregationService {

    private static final Logger log = LoggerFactory.getLogger(ScoreAggregationService.class);

    private final RedisTemplate<String, Object> redisTemplate;

    public ScoreAggregationService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * 聚合成绩
     *
     * @param scoreEvent 成绩事件
     *
     * 🎓 业务逻辑：
     * 1. 更新用户总分
     * 2. 更新排行榜
     * 3. 记录统计信息
     *
     * ⚠️ 常见陷阱：幂等性设计
     * - 消息可能重复消费
     * - 使用 offset 或事件 ID 去重
     * - 或者设计为幂等操作（如 SET 覆盖）
     */
    public void aggregateScore(ScoreEvent scoreEvent) {
        String userId = scoreEvent.getUserId();
        int score = scoreEvent.getScore();

        // 🎓 1. 更新用户总分（Redis INCRBY 是原子操作）
        String userScoreKey = "user:score:" + userId;
        redisTemplate.opsForValue().increment(userScoreKey, score);

        // 🎓 2. 更新排行榜（Redis Sorted Set）
        // ZINCRBY 是原子操作，适合并发场景
        String leaderboardKey = "leaderboard:global";
        redisTemplate.opsForZSet().incrementScore(leaderboardKey, userId, score);

        // 🎓 3. 记录最近成绩（Redis List）
        // 保留最近 100 条成绩，用于统计
        String recentScoresKey = "user:recent_scores:" + userId;
        redisTemplate.opsForList().leftPush(recentScoresKey, scoreEvent);
        redisTemplate.opsForList().trim(recentScoresKey, 0, 99);

        // 🎓 4. 设置过期时间（避免数据无限增长）
        // 用户数据保留 30 天
        redisTemplate.expire(userScoreKey, 30, TimeUnit.DAYS);
        redisTemplate.expire(recentScoresKey, 30, TimeUnit.DAYS);

        log.info("成绩聚合完成: userId={}, score={}, totalScore={}",
            userId, score, redisTemplate.opsForValue().get(userScoreKey));
    }
}
```

---

## 4. 错误处理和重试

```java
package com.typetype.kafka.error;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

/**
 * 自定义错误处理器
 *
 * 🎓 错误处理策略：
 * 1. 重试：可恢复的错误（网络抖动、临时故障）
 * 2. 死信队列：不可恢复的错误（数据格式错误、业务异常）
 * 3. 告警：通知运维人员
 *
 * 🎓 CommonErrorHandler 是 Spring Kafka 2.8+ 的接口
 * 替代了旧的 ErrorHandler 和 BatchErrorHandler
 */
@Component
public class KafkaErrorHandler implements CommonErrorHandler {

    private static final Logger log = LoggerFactory.getLogger(KafkaErrorHandler.class);

    // 🎓 最大重试次数
    private static final int MAX_RETRIES = 3;

    /**
     * 处理单条消息错误
     *
     * @param thrownException 异常
     * @param record 消息记录
     * @param consumer 消费者对象
     * @param container 监听容器
     *
     * @return true 表示已处理，false 表示继续抛出异常
     */
    @Override
    public boolean handleOne(
            Exception thrownException,
            ConsumerRecord<?, ?> record,
            Consumer<?, ?> consumer,
            MessageListenerContainer container) {

        log.error("消息处理失败: topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            thrownException);

        // 🎓 判断是否应该重试
        if (shouldRetry(thrownException)) {
            log.info("将重试消息: offset={}", record.offset());
            // 返回 false，让框架重试
            return false;
        }

        // 🎓 发送到死信队列
        sendToDeadLetterQueue(record, thrownException);

        // 🎓 返回 true，表示已处理，继续消费下一条
        return true;
    }

    /**
     * 判断是否应该重试
     *
     * 🎓 可重试的异常类型：
     * - 网络异常（ConnectException, TimeoutException）
     * - 临时服务不可用（ServiceUnavailableException）
     * - 数据库连接异常
     *
     * 🎓 不可重试的异常类型：
     * - 数据格式异常（JsonParseException）
     * - 业务逻辑异常（IllegalArgumentException）
     * - 权限异常（AccessDeniedException）
     */
    private boolean shouldRetry(Exception exception) {
        // 示例：检查异常类型
        if (exception instanceof org.apache.kafka.common.errors.TimeoutException) {
            return true; // 网络超时，可以重试
        }
        if (exception instanceof com.fasterxml.jackson.core.JsonParseException) {
            return false; // JSON 格式错误，不能重试
        }
        // 默认重试
        return true;
    }

    /**
     * 发送到死信队列
     *
     * 🎓 死信队列（Dead Letter Queue, DLQ）：
     * - 存放处理失败的消息
     * - 便于后续人工处理或重试
     * - Topic 命名：原 Topic + .DLT
     */
    private void sendToDeadLetterQueue(ConsumerRecord<?, ?> record, Exception exception) {
        String dltTopic = record.topic() + ".DLT";

        log.info("发送到死信队列: topic={}, originalOffset={}",
            dltTopic, record.offset());

        // TODO: 实际实现需要注入 KafkaTemplate
        // kafkaTemplate.send(dltTopic, record.key(), record.value());
    }
}
```

---

## 5. 使用示例：完整的消费流程

```java
package com.typetype.kafka;

import com.typetype.model.ScoreEvent;
import com.typetype.service.ScoreAggregationService;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

/**
 * 完整的消费流程示例
 *
 * 🎓 消费流程：
 * 1. 从 Topic 拉取消息
 * 2. 反序列化为对象
 * 3. 业务处理
 * 4. 确认消息
 * 5. 异常处理
 */
@Component
public class ScoreConsumerExample {

    private static final Logger log = LoggerFactory.getLogger(ScoreConsumerExample.class);

    private final ScoreAggregationService aggregationService;

    public ScoreConsumerExample(ScoreAggregationService aggregationService) {
        this.aggregationService = aggregationService;
    }

    @KafkaListener(
        topics = "typetype.scores",
        groupId = "score-processing-group"
    )
    public void processScore(
            ConsumerRecord<String, ScoreEvent> record,
            Acknowledgment acknowledgment) {

        String userId = record.key();
        ScoreEvent event = record.value();

        log.info("开始处理: userId={}, offset={}", userId, record.offset());

        try {
            // 🎓 1. 数据验证
            validateScoreEvent(event);

            // 🎓 2. 业务处理
            aggregationService.aggregateScore(event);

            // 🎓 3. 确认消息
            acknowledgment.acknowledge();

            log.info("处理完成: userId={}", userId);

        } catch (IllegalArgumentException e) {
            // 🎓 数据验证失败：发送到死信队列
            log.error("数据验证失败: userId={}", userId, e);
            sendToDeadLetterQueue(record, e);
            acknowledgment.acknowledge(); // 确认消息，避免重复消费

        } catch (Exception e) {
            // 🎓 业务处理失败：重试
            log.error("业务处理失败: userId={}", userId, e);
            throw e; // 抛出异常，触发重试
        }
    }

    /**
     * 验证成绩事件
     *
     * 🎓 数据验证的重要性：
     * - 防止脏数据进入系统
     * - 尽早发现数据问题
     * - 保护下游服务
     */
    private void validateScoreEvent(ScoreEvent event) {
        if (event.getUserId() == null || event.getUserId().isEmpty()) {
            throw new IllegalArgumentException("userId 不能为空");
        }
        if (event.getScore() < 0) {
            throw new IllegalArgumentException("score 不能为负数");
        }
        if (event.getWpm() < 0 || event.getWpm() > 300) {
            throw new IllegalArgumentException("wpm 不在合理范围内");
        }
    }

    private void sendToDeadLetterQueue(ConsumerRecord<String, ScoreEvent> record, Exception e) {
        // TODO: 实现死信队列发送
        log.info("发送到死信队列: offset={}", record.offset());
    }
}
```

---

## 6. 面试要点

### Q: Kafka Consumer 消费消息的流程？

1. **订阅 Topic**：Consumer 订阅一个或多个 Topic
2. **加入消费者组**：向 Coordinator 注册
3. **分配 Partition**：Coordinator 分配 Partition 给 Consumer
4. **拉取消息**：Consumer 从 Partition 拉取消息
5. **处理消息**：业务逻辑处理
6. **提交偏移量**：记录消费到的位置
7. **心跳保持**：定期发送心跳，证明存活

### Q: 什么是 Rebalance？

- **定义**：Consumer Group 中的 Consumer 数量变化时，重新分配 Partition
- **触发条件**：
  - Consumer 加入或离开
  - Topic 的 Partition 数量变化
  - Consumer 心跳超时
- **影响**：Rebalance 期间会暂停消费
- **优化**：减少 Rebalance 频率，调整 session.timeout.ms

### Q: 如何保证消息不丢失？

1. **手动提交偏移量**：处理成功后才提交
2. **幂等性处理**：重复消费不会产生副作用
3. **事务支持**：使用 Kafka 事务
4. **确认机制**：等待 Broker 确认

### Q: 如何保证消息顺序？

1. **单 Partition**：一个 Partition 只能被一个 Consumer 消费
2. **Partition Key**：相同 Key 的消息进入同一 Partition
3. **业务保证**：使用版本号或时间戳排序

### Q: 如何处理重复消费？

1. **幂等性设计**：相同操作多次执行结果相同
2. **去重表**：记录已处理的消息 ID
3. **唯一约束**：数据库唯一索引防止重复插入
4. **乐观锁**：使用版本号控制更新

---

## 7. 常见陷阱

### 陷阱 1：忘记手动确认

```java
// ❌ 错误：忘记调用 acknowledge()
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record) {
    // 处理消息
    // 忘记调用 acknowledgment.acknowledge()
}

// ✅ 正确：处理完成后手动确认
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record, Acknowledgment ack) {
    // 处理消息
    ack.acknowledge();
}
```

### 陷阱 2：阻塞消费线程

```java
// ❌ 错误：在消费线程中执行耗时操作
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record) {
    // 调用外部 API，可能阻塞
    externalService.call();
}

// ✅ 正确：异步处理，快速返回
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record) {
    // 发送到内部队列，异步处理
    internalQueue.offer(record);
}
```

### 陷阱 3：没有处理反序列化异常

```java
// ❌ 错误：反序列化失败会导致消费停止
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record) {
    // 直接反序列化，可能失败
    ScoreEvent event = objectMapper.readValue(record.value(), ScoreEvent.class);
}

// ✅ 正确：使用 ErrorHandlingDeserializer
// 在配置中添加：
// props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, ErrorHandlingDeserializer.class);
// props.put(ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS, JsonDeserializer.class.getName());
```

### 陷阱 4：没有配置消费者组

```java
// ❌ 错误：没有配置 groupId
@KafkaListener(topics = "test")
public void consume(ConsumerRecord<String, String> record) {
    // 每次启动都会从头消费
}

// ✅ 正确：配置 groupId
@KafkaListener(topics = "test", groupId = "my-group")
public void consume(ConsumerRecord<String, String> record) {
    // 从上次提交的位置继续消费
}
```

---

## 8. 生产环境建议

### 监控指标

- **消费延迟**：当前偏移量与最新偏移量的差值
- **消费速率**：每秒处理的消息数
- **处理时间**：单条消息的处理时间
- **错误率**：处理失败的消息比例

### 告警规则

- 消费延迟 > 10000 条
- 消费速率下降 > 50%
- 错误率 > 1%
- 处理时间 > 1s

### 性能调优

- **并发数**：设置为 Partition 数量
- **批量大小**：调整 max.poll.records
- **拉取间隔**：调整 fetch.max.wait.ms
- **缓冲区大小**：调整 fetch.min.bytes
