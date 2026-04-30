# TypeType AI Typing Coach Agent 改造规划

> 最后更新：2026-04-06
>
> 本文档详细说明如何将 TypeType 打字练习工具转化为 AI Agent 面试项目。
>
> 注意：本文是规划文档，不是当前客户端架构的事实来源。若其中出现架构术语冲突，请以 [ARCHITECTURE.md](./ARCHITECTURE.md) 和当前源码为准。

---

## 目录

- [项目现状分析](#项目现状分析)
- [转化可行性分析](#转化可行性分析)
- [实施步骤](#实施步骤)
- [技术栈选择](#技术栈选择)
- [风险分析与缓解](#风险分析与缓解)
- [面试价值](#面试价值)
- [相关文档](#相关文档)

---

## 项目现状分析

### 当前架构优势

TypeType 项目已具备转化为 AI Agent 项目的**极佳基础**：

#### Clean Architecture（已实现）

```
┌─────────────────────────────────────────────────────────┐
│                    QML 层                               │
│           (通过 appBridge 与后端通信)                   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                  Presentation Layer                     │
│                 (Bridge + Adapters)                     │
│  Bridge: appBridge，属性代理/信号转发/Slot 入口         │
│  Adapters: TypingAdapter, TextAdapter, ...             │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                     Application Layer                   │
│        UseCases: LoadTextUseCase                        │
│        Gateways: TextSourceGateway, ScoreGateway        │
└─────────┬───────────────────────────┬───────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────────┐   ┌───────────────────────────┐
│      Domain Services    │   │          Ports            │
│ (纯业务逻辑，无 Qt 依赖)│   │   (接口协议 / 抽象依赖)   │
│ Typing/Auth/CharStats   │   │ TextProvider, Clipboard...│
└─────────┬───────────────┘   └───────────┬───────────────┘
          │                               │
          └──────────────┬────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Integration / Infrastructure           │
│ RemoteTextProvider, SqliteRepo, ApiClient, QtLocalTextLoader │
└─────────────────────────────────────────────────────────┘
```

#### 现有"记忆"机制（Agent 核心基础）

| 组件 | 功能 | Agent 价值 |
|:--- |:--- |:---|
| **CharStatsService** | 字符维度统计（缓存、异步持久化） | 用户弱字记忆源 |
| **CharStat** 模型 | 包含 `avg_ms`, `error_rate`, `char_count` 等 | 个性化数据基础 |
| **SqliteCharStatsRepository** | SQLite 持久化 | 跨会话记忆存储 |
| **WeakCharsPage.qml** | 显示薄弱字的 UI 页面 | Agent 结果展示层 |

#### 关键方法（已实现）

```python
# CharStatsService 中已有的 Agent 可用方法：
def get_weakest_chars(self, n: int = 10) -> list[CharStat]:
    """获取最薄弱的 n 个字符统计 - Agent 记忆查询接口"""
    return self._repo.get_weakest_chars(n)

def accumulate(self, char: str, keystroke_ms: float, is_error: bool) -> None:
    """累积打字结果 - Agent 可调用的记忆更新接口"""
```

---

## 转化可行性分析

### 高可行性因素

| 维度 | 评分 | 说明 |
|:--- |:--- |:---|
| 架构适配性 | 9/10 | Ports & Adapters 模式，允许无缝添加新服务，依赖注入在 main.py 完成 |
| 数据基础 | 8/10 | CharStat 模型完善，`get_weakest_chars()` 已实现，SQLite 持久化就绪 |
| UI 集成 | 7/10 | WeakCharsPage 可复用，Bridge 信号机制易于扩展 |
| 测试基础 | 7/10 | 现有 13 个测试文件，Dummy 对象模式便于编写测试 |

### 技术可行性结论

项目已具备良好基础，改造**高度可行**。六边形架构使得新增 Agent 能力对现有代码侵入极小。

---

## 实施步骤

### Phase 1：单 Agent 循环（1-2 天）

**目标**：实现 "查询 → 生成 → 评估 → 决策" 经典 Agent 循环

**新增文件结构**：
```
src/backend/agents/
├── __init__.py
├── ai_typing_coach_agent.py    # 主 Agent（LangGraph）
├── tools/
│   ├── __init__.py
│   ├── get_weakest_chars.py    # 复用 CharStatsService
│   ├── generate_text.py        # LLM 结构化输出
│   ├── evaluate_text.py        # LLM-as-Judge
│   └── save_to_backend.py      # 本地存储 + Spring Boot
└── models/
    ├── __init__.py
    └── text_quality_assessment.py  # Pydantic 模型
```

**核心 Agent 代码框架**：
```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import TypedDict


class AgentState(TypedDict):
    """Agent 状态定义"""
    weak_chars: list[str]
    generated_text: str | None
    assessment: dict | None
    should_save: bool
    iteration_count: int


def plan_next_step(state: AgentState) -> AgentState:
    """规划下一步：查询弱字 → 生成 → 评估 → 决策"""
    if not state.get("weak_chars"):
        state["weak_chars"] = get_weakest_chars_tool(n=5)
    return state


def generate_text(state: AgentState) -> AgentState:
    """生成个性化文本"""
    state["generated_text"] = generate_text_tool(
        weak_chars=state["weak_chars"],
        topic="科技",
        length=200
    )
    state["iteration_count"] = state.get("iteration_count", 0) + 1
    return state


def evaluate_text(state: AgentState) -> AgentState:
    """LLM-as-Judge 评估"""
    state["assessment"] = evaluate_text_tool(state["generated_text"])
    return state


def decide_to_save(state: AgentState) -> str:
    """决策：保存还是重新生成"""
    if state["assessment"]["quality_score"] >= 80:
        return "save"
    if state["iteration_count"] >= 3:
        return "save"  # 最多重试 3 次
    return "regenerate"


def save_text(state: AgentState) -> AgentState:
    """保存通过评估的文本"""
    save_to_backend_tool(state["generated_text"], state["assessment"])
    state["should_save"] = True
    return state


# 构建 StateGraph
graph = StateGraph(AgentState)
graph.add_node("planner", plan_next_step)
graph.add_node("generator", generate_text)
graph.add_node("evaluator", evaluate_text)
graph.add_node("saver", save_text)

graph.set_entry_point("planner")
graph.add_edge("planner", "generator")
graph.add_edge("generator", "evaluator")
graph.add_conditional_edges(
    "evaluator",
    decide_to_save,
    {
        "save": "saver",
        "regenerate": "generator"
    }
)
graph.add_edge("saver", END)

# 编译 Agent
ai_coach_agent = graph.compile()
```

**Bridge 新增信号/槽**：
```python
# src/backend/presentation/bridge.py 新增
aiCoachResultReady = Signal(str, dict)  # text, assessment
aiCoachLoadingChanged = Signal()
aiCoachError = Signal(str)

@Slot(str, int)
def requestAiCoachText(self, topic: str, length: int) -> None:
    """QML 调用：请求 AI 生成个性化文本"""
    worker = AiCoachWorker(
        agent=ai_coach_agent,
        char_stats_service=self._char_stats_service,
        topic=topic,
        length=length
    )
    worker.signals.result.connect(self._on_ai_coach_result)
    worker.signals.error.connect(self._on_ai_coach_error)
    QThreadPool.globalInstance().start(worker)
    self.aiCoachLoadingChanged.emit()
```

**验收标准**：
- 调用 `bridge.requestAiCoachText("科技", 200)` 返回评估报告
- 控制台打印 Agent Chain-of-Thought 日志
- 测试覆盖核心路径

### Phase 2：Multi-Agent 系统（3-5 天）

**目标**：升级为多 Agent 分工协作系统

**新增分工**：
- `GeneratorAgent`：专注生成个性化文本
- `EvaluatorAgent`：专注质量评估（LLM-as-Judge）
- `SaverAgent`：决策存储策略（本地 + Spring Boot）

**使用 LangGraph `create_supervisor` 编排**：
```python
from langgraph.prebuilt import create_supervisor

supervisor = create_supervisor(
    agents=[generator_agent, evaluator_agent, saver_agent],
    model=ChatOpenAI(model="gpt-4o"),
    prompt="你是 AI Typing Coach 的主管，协调三个专家完成个性化文本生成任务。"
).compile()
```

**新增 QML 页面**：
- 创建 `AiCoachPage.qml`
- 更新 `Main.qml` 导航

**验收标准**：
- UI 中可选择主题 + 长度 → 触发 Agent
- 显示 Agent 思考过程（Chain-of-Thought）
- 评估报告 + 保存结果展示

### Phase 3：增强功能（锦上添花，2-3 天）

| 功能 | 实现方式 | 面试加分点 |
|:--- |:--- |:---|
| **RAG 记忆** | Chroma 向量库 + 用户历史打字记录 | 长期记忆 + 检索增强生成 |
| **可观测性** | LangSmith / LangFuse | Agent 调试与监控 |
| **本地优先** | Ollama + qwen2.5 | 离线可用 + 隐私保护 |
| **Spring Boot 对接** | `/ai-import` 作为 Agent Tool | 跨语言集成 |

---

## 技术栈选择

### 推荐方案

| 组件 | 选择 | 理由 |
|:--- |:--- |:---|
| **Agent 框架** | LangGraph | 2025-2026 主流，面试认可度高 |
| **LLM 提供商** | Ollama（默认） + OpenAI（可选） | 本地优先，降低成本 |
| **结构化输出** | Instructor | Pydantic 模型强制输出 |
| **向量库**（Phase 3） | ChromaDB | 轻量级，易于集成 |
| **可观测性**（Phase 3） | LangSmith | 官方工具，可视化好 |

### 依赖配置（pyproject.toml）

```toml
[project.optional-dependencies]
ai = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",  # 可选
    "langchain-ollama>=0.2.0",  # 默认
    "instructor>=1.5.0",
    "pydantic>=2.0.0",
]
ai-full = [
    "typetype[ai]",
    "chromadb>=0.5.0",  # Phase 3 RAG
    "langsmith>=0.2.0",  # Phase 3 可观测性
]
```

---

## 风险分析与缓解

### 已识别风险及对策

| 风险 | 严重度 | 概率 | 缓解措施 |
|:--- |:--- |:--- |:---|
| Qt 事件循环与 LangGraph 异步冲突 | 高 | 中 | 使用 `QThreadPool + AiCoachWorker`，独立线程运行 |
| API 密钥与成本管理 | 中 | 高 | 默认 Ollama 本地模型，可选 OpenAI |
| Agent 输出不稳定 | 中 | 中 | Instructor 结构化输出 + 重试 + 质量门控 |
| 依赖包过大 | 低 | 高 | 可选依赖，不开启不增加体积 |
| Demo 演示失败 | 中 | 中 | 预设缓存 + 离线模式 + 快速重试 |
| 现有代码侵入 | 低 | 低 | 功能开关 + 最小侵入，不影响现有逻辑 |

### Qt 异步解决方案

```python
# 使用 QThreadPool + Worker 模式
class AiCoachWorker(QRunnable):
    def run(self):
        # 在独立线程中运行 Agent
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(agent.ainvoke(state))
        self.signals.result.emit(result)
```

---

## 面试价值

### 技术深度展示

| 技术点 | 改造后面试价值 | 星级 |
|:--- |:--- |:---|
| Clean Architecture | 展示架构设计能力 | ⭐⭐⭐ |
| Tool Use | Agent 核心能力 | ⭐⭐⭐⭐ |
| Memory Integration | 真实用户记忆 | ⭐⭐⭐⭐ |
| ReAct Loop | Agent 循环决策 | ⭐⭐⭐⭐⭐ |
| Multi-Agent | 高级 Agent 模式 | ⭐⭐⭐⭐⭐ |
| Structured Output | LLM 输出控制 | ⭐⭐⭐ |
| Observability | 生产级调试 | ⭐⭐⭐ |

### 面试官关注点匹配

| 面试官问题 | 本项目回答方式 |
|:--- |:---|
| 怎么调试 Agent？ | LangSmith/LangFuse 可视化每一步 |
| 怎么处理 LLM 幻觉？ | Instructor 结构化输出 + LLM-as-Judge |
| 怎么保证质量？ | 评估循环 + 重试机制 + 质量门控 |
| 怎么集成到现有系统？ | Clean Architecture + 依赖注入 |
| 怎么处理用户数据？ | CharStatsService 持久化记忆 |

### 差异化优势

- 🎯 **真实场景**：不是 Jupyter Notebook 玩具项目，是可运行的真实桌面应用
- 🎯 **全栈展示**：Python Agent + Qt/QML 桌面 UI + SQLite + 可选 Java Spring Boot
- 🎯 **可量化成果**：打包成单文件给面试官运行，输入主题 → 实时生成个性化文章

---

## 快速开始命令

```bash
# 1. 添加 AI 依赖
uv add --optional ai langgraph langchain-ollama instructor pydantic

# 2. 安装 Ollama（本地模型）
# macOS/Linux: curl -fsSL https://ollama.com/install.sh | sh
# Windows: 下载 https://ollama.com/download/windows

# 3. 拉取模型
ollama pull qwen2.5:7b

# 4. 运行项目
uv run python main.py
```

---

## 相关文档

- [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) - 当前客户端架构
- [spring-boot-design.md](./spring-boot-design.md) - Spring Boot 后端设计

---

## 版本历史

| 日期 | 变更 |
|:--- |:---|
| 2026-04-06 | 重命名为 AI_AGENT_PLAN.md，整理结构 |
| 2026-03-21 | 初始版本，完整改造方案 |
