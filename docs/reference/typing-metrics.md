# 打字指标定义
<!-- 状态: active | 最后验证: 2026-05-14 -->

本文档定义 Typetype 打字练习应用中所有核心统计指标的含义与计算方式。

## 基础数据（原始采集值）

以下数据在打字过程中被直接采集：

| 指标 | 说明 |
|------|------|
| 总按键数 | 打字过程中所有按键被按下的总次数（含正确输入、退格、回改产生的按键） |
| 字数 | 已正确输入的字符数（不含错字） |
| 错字数 | 输入过程中产生错误的字符总数 |
| 退格数 | 退格键（Backspace）被按下的次数 |
| 回改数 | 输入错误后被删除（通过退格或选删）的字数 |
| 用时 | 打字持续时间（秒） |

## 衍生指标（计算值）

### 速度（CPM）
每分钟输入的字符数。

```
速度 = 字数 × 60 / 用时
```

### 击键
每秒的按键次数。

```
击键 = 总按键数 / 用时
```

### 码长
平均每个字需要按多少下键。

```
码长 = 总按键数 / 字数
```

### 准确率
正确字符占总输入字符的比例。

```
准确率 = (字数 − 错字数) / 字数 × 100%
```

### 有效速度
按准确率加权后的速度，反映实际有效输出。

```
有效速度 = 速度 × 准确率 / 100
```

### 键准
反映按键效率的核心指标，衡量按键中有多少是"有效按键"（未用于修正错误的按键）。

#### 错键的定义

跟打器中的"错键"不是指"按错的某个字母键"，而是指所有用于修正错误的按键，分为两类：

| 类别 | 定义 | 计入错键的方式 |
|------|------|----------------|
| 退格 | 退格键（Backspace）被按下的次数 | 每按 1 次退格，计为 1 个错键 |
| 回改 | 输入错误后被删除的字数 | 每回改 1 个字，计为 **平均码长** 个错键 |

关键理解：跟打器并不追踪你具体按错了哪个字母键（比如把"a"按成了"s"），它只追踪你为了修正错误而付出的按键代价——即退格和回改。

#### 计算公式

```
键准 = (总按键数 − 退格数 − 回改数 × 码长) / 总按键数 × 100%
```

- 当总按键数为 0 时，键准定义为 100%。
- 计算结果小于 0 时截断为 0%。

## 对外 API 字段命名（与服务端契约）

### 提交契约（客户端 → 服务端）

以下字段为必传的原始字段（服务端持久化存储）：

| API 字段名 | 类型 | 来源 | 说明 |
|-----------|------|------|------|
| textId | Long | SessionStat.text_id | 服务端文本ID（主键） |
| speed | Decimal | SessionStat.speed | 速度（字/分） |
| keyStroke | Decimal | SessionStat.keyStroke | 击键速度（击/秒） |
| codeLength | Decimal | SessionStat.codeLength | 码长（击/字） |
| charCount | Integer | SessionStat.char_count | 字符数 |
| wrongCharCount | Integer | SessionStat.wrong_char_count | 错误字符数 |
| backspaceCount | Integer | SessionStat.backspace_count | 退格键按下次数 |
| correctionCount | Integer | SessionStat.correction_count | 回改字数 |
| keyAccuracy | Decimal | SessionStat.keyAccuracy | 键准（%） |
| time | Decimal | SessionStat.time | 用时（秒） |

### 返回契约（服务端 → 客户端）

服务端返回字段包含以下三类：

#### 原始字段（直接从数据库读取）

| API 字段名 | 类型 |
|-----------|------|
| speed | Decimal |
| keyStroke | Decimal |
| codeLength | Decimal |
| charCount | Integer |
| wrongCharCount | Integer |
| backspaceCount | Integer |
| correctionCount | Integer |
| keyAccuracy | Decimal |
| time | Decimal |
| createdAt | LocalDateTime |

#### 派生字段（服务端实时计算返回）

| API 字段名 | 计算公式 |
|-----------|----------|
| accuracyRate | `(charCount - wrongCharCount) / charCount * 100` |
| effectiveSpeed | `speed * accuracyRate / 100` |

#### 兼容字段（已废弃，保留用于过渡期）

| API 字段名 | 替代方案 |
|-----------|----------|
| duration | 已统一为 `time` |
| accuracy | 已统一为 `accuracyRate` |

### 契约版本

- **当前版本**: V2
- **发布日期**: 2026-04-26
- **主要变更**: 新增 `backspaceCount`、`correctionCount`、`keyAccuracy`；`duration` 统一为 `time`
