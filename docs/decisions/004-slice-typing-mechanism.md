# ADR-004: 载文分片机制（Slice Typing）

<!-- 状态: accepted | 最后验证: 2026-06-04 -->

## 背景

长文本一次性载入会导致：
- 大量文本一次性显示在 QML TextArea 中，内存占用高
- 用户打字体验差（一屏显示过多文本）
- 无法做"分段达标"的跟打模式

## 选项

### A. 全文载入，QML 分页显示

后端传入全文，QML 通过 ScrollArea 分页显示。

**优点**：实现简单。
**缺点**：全文在内存中；无法服务端聚合成绩；长文首屏加载慢。

### B. 后端分片，逐段传入

后端将文本按字符数切分为多个片段，每次只传入当前段。分片状态（当前索引、达标次数）在服务端/后端状态机中管理。

**优点**：
- 内存中只持当前段
- 支持分段达标、达标自动推进
- 支持历史进度恢复

**缺点**：需要实现分片状态机；段切换时 UI 需平滑过渡。

### C. 混合模式

短文本全文载入，长文本分片。

**优点**：短文本无分片开销。
**缺点**：两套逻辑维护成本高；用户可能混淆两种模式。

## 决策

**选择 B**。所有载文统一走分片管线。

核心设计：
- `TypingSessionContext` 管理分片状态：`current_slice`、`total_slices`、`pass_count`、`slices_met`
- 共享组件 `SliceCriteriaPanel`：击键、速度、准确率、达标次数、失败动作配置
- `TextLoadCoordinator`（Presentation 层）管理来源切换状态、分片参数、UI 协调
- 所有 4 个载文入口（CustomLoadTextPage、LocalArticlesPage、TrainerPage、JisuBeiPage）使用相同的分片参数和 UI 模式

## 影响

- **正向**：统一了所有载文入口的分片逻辑
- **正向**：短文本也走分片（N=1），逻辑统一
- **变更**：`SliceCriteriaPanel` 和 `TextLoadPanel` 作为共享组件
- **注意**：分片达标次数在片段切换时必须归零；同一片段重打时保留

## 参考

- 详细设计：[`docs/history/2026-04-21-slice-typing-design.md`](../history/2026-04-21-slice-typing-design.md)
- 初版草案：[`docs/history/2026-04-21-slice-typing-design-v1.md`](../history/2026-04-21-slice-typing-design-v1.md)
