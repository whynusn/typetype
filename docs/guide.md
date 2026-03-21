# TypeType AI Agent 转化规划指南

> 最后更新：2026-03-21
>
> 本文档详细说明如何将 TypeType 打字练习工具转化为 AI Agent 面试项目。

---

## 相关文档

- [roadmap.md](./roadmap.md) - 项目功能路线图与当前进度
- [spring-boot-backend-design.md](./spring-boot-backend-design.md) - Spring Boot 后端设计方案
- [AGENTS.md](../AGENTS.md) - 项目开发指南

---

## 1. 项目现状分析

### 1.1 当前架构优势

TypeType 项目已具备转化为 AI Agent 项目的**极佳基础**：

#### Clean Architecture（已实现）
```
┌─────────────────────────────────────────────────────────┐
│                    QML 层                              │
│           (通过 appBridge 与后端通信)                    │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              Bridge (QML 通信适配层)                       │
│   仅负责：属性代理、信号转发、Slot 入口                    │
└─────────┬───────────────────────────┬───────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────┐   ┌───────────────────────────────┐
│   Domain Services   │   │      Application Layer       │
│  - TypingService   │   │  - LoadTextUseCase           │
│  - CharStatsService│   │  - TypingUseCase             │
│  - AuthService     │   │                               │
│  - CharStatsService│   │                               │
└─────────────────────┘   └───────────────┬───────────────┘
                                          │
                                          ▼
                              ┌───────────────────────────────┐
                              │      Ports (接口定义)          │
                              │  - TextFetcher                │
                              │  - LocalTextLoader            │
                              │  - ClipboardReader/Writer     │
                              │  - CharStatsRepository        │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │   Integration (实现)          │
                              │  - SaiWenTextFetcher          │
                              │  - QtLocalTextLoader          │
                              │  - SqliteCharStatsRepository  │
                              └───────────────────────────────┘
```

#### 现有"记忆"机制（Agent 核心基础）

| 组件 | 功能 | Agent 价值 |
|------|------|-----------|
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

## 2. 转化可行性分析

### 2.1 高可行性因素

#### ✅ 架构适配性（9/10）
- **Ports & Adapters 模式**：允许无缝添加新服务（AI TextGenerator、TextEvaluator）
- **依赖注入在 main.py 完成**：无需修改现有服务即可注入 Agent 组件
- **协议驱动**：`TextFetcher` 协议可直接扩展为 AI 生成文本来源

#### ✅ 数据基础（8/10）
- **CharStat 模型完善**：已包含错误率、平均耗时、最小/最大耗时、最后出现时间
- **get_weakest_chars() 已实现**：完美适配 Agent 个性化记忆查询
- **SQLite 持久化**：跨会话记忆存储已就绪

#### ✅ UI 集成（7/10）
- **WeakCharsPage 可复用**：已有薄弱字展示页面
- **Bridge 信号机制**：可新增 AI Coach 相关信号
- **QML 组件化**：易于新增 AI Coach 页面

#### ✅ 测试基础（7/10）
- **13 个测试文件**：覆盖核心用例和集成
- **Dummy 对象模式**：便于为 Agent 组件编写测试

### 2.2 技术可行性路线

#### 第 1 步：单 Agent 循环（1-2 天）

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

**依赖添加**：
```bash
uv add langgraph langchain-openai instructor pydantic
# 或本地模型：
uv add langgraph langchain-ollama instructor pydantic
```

**核心 Agent 代码框架**：
```python
# src/backend/agents/ai_typing_coach_agent.py
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import TypedDict

from ..domain.char_stats_service import CharStatsService
from .tools.get_weakest_chars import get_weakest_chars_tool
from .tools.generate_text import generate_text_tool
from .tools.evaluate_text import evaluate_text_tool
from .tools.save_to_backend import save_to_backend_tool


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

#### 第 2 步：Multi-Agent 系统（3-5 天）

**新增 Agent 分工**：
```python
# GeneratorAgent：专注生成个性化文本
# EvaluatorAgent：专注质量评估（LLM-as-Judge）
# SaverAgent：决策存储策略（本地 + Spring Boot）
```

**使用 LangGraph create_supervisor**：
```python
from langgraph.prebuilt import create_supervisor

supervisor = create_supervisor(
    agents=[generator_agent, evaluator_agent, saver_agent],
    model=ChatOpenAI(model="gpt-4o"),
    prompt="你是 AI Typing Coach 的主管，协调三个专家完成个性化文本生成任务。"
).compile()
```

#### 第 3 步：增强功能（锦上添花）

| 功能 | 实现方式 | 面试加分点 |
|------|---------|-----------|
| **RAG 记忆** | Chroma 向量库 + 用户历史打字记录 | 长期记忆 + 检索增强生成 |
| **可观测性** | LangSmith / LangFuse | Agent 调试与监控 |
| **本地优先** | Ollama + qwen2.5 | 离线可用 + 隐私保护 |
| **Spring Boot 对接** | /ai-import 作为 Agent Tool | 跨语言集成 |

---

## 3. 弊端与风险分析

### 3.1 技术风险

#### ⚠️ Qt 事件循环与 LangGraph 异步冲突（高风险）

**问题**：Qt 使用自己的事件循环，LangGraph/LangChain 异步执行可能阻塞 UI。

**解决方案**：
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

#### ⚠️ API 密钥与成本管理（中风险）

**问题**：OpenAI API 调用成本，用户需配置 API Key。

**解决方案**：
1. 默认使用 Ollama 本地模型（qwen2.5:7b）
2. 可选配置 OpenAI API Key
3. 在 `RuntimeConfig` 中添加：
   ```python
   ai_provider: str = "ollama"  # 或 "openai"
   openai_api_key: str | None = None
   ollama_base_url: str = "http://localhost:11434"
   ```

#### ⚠️ Agent 不可预测性（中风险）

**问题**：LLM 输出不稳定，可能导致生成质量波动。

**解决方案**：
1. **结构化输出**：使用 Instructor 强制 Pydantic 模型输出
2. **重试机制**：最多重试 3 次
3. **质量门控**：LLM-as-Judge 评分 < 80 分重新生成
4. **回退策略**：生成失败时使用预设模板

### 3.2 架构风险

#### ⚠️ 依赖膨胀（低风险）

**问题**：LangGraph + LangChain 依赖包较大（~100MB）。

**影响**：Nuitka 打包体积增加。

**缓解**：
1. 使用 `langchain-core` 而非完整 `langchain`
2. 本地模型（Ollama）减少 API 依赖
3. 可选依赖：`uv add langgraph --optional`

#### ⚠️ 现有代码侵入（低风险）

**问题**：需修改 Bridge、main.py 等核心文件。

**缓解**：
1. **最小侵入**：仅新增信号/槽，不修改现有逻辑
2. **功能开关**：通过环境变量 `TYPETYPE_AI_ENABLED=true` 控制
3. **向后兼容**：未配置 API 时自动降级为传统模式

### 3.3 面试展示风险

#### ⚠️ Demo 稳定性（中风险）

**问题**：现场演示时 LLM 可能超时或输出不佳。

**解决方案**：
1. **预设缓存**：准备 5-10 个预生成的优质文本
2. **离线模式**：Ollama 本地模型不依赖网络
3. **快速重试**：失败后 2 秒内自动重试
4. **可视化过程**：即使最终结果未出，展示 Agent 思考链

---

## 4. 面试价值分析

### 4.1 技术深度展示

| 技术点 | 当前项目 | 改造后面试价值 |
|--------|---------|---------------|
| **Clean Architecture** | ✅ 已实现 | ⭐⭐⭐ 展示架构设计能力 |
| **Tool Use** | ❌ 无 | ⭐⭐⭐⭐ Agent 核心能力 |
| **Memory Integration** | ✅ CharStats | ⭐⭐⭐⭐ 真实用户记忆 |
| **ReAct Loop** | ❌ 无 | ⭐⭐⭐⭐⭐ Agent 循环决策 |
| **Multi-Agent** | ❌ 无 | ⭐⭐⭐⭐⭐ 高级 Agent 模式 |
| **Structured Output** | ❌ 无 | ⭐⭐⭐ LLM 输出控制 |
| **Observability** | ❌ 无 | ⭐⭐⭐ 生产级调试 |

### 4.2 面试官关注点匹配

| 面试官关注 | TypeType 改造后 |
|-----------|----------------|
| "怎么调试 Agent？" | LangSmith/LangFuse 可视化每一步 |
| "怎么处理 LLM 幻觉？" | Instructor 结构化输出 + LLM-as-Judge |
| "怎么保证质量？" | 评估循环 + 重试机制 + 质量门控 |
| "怎么集成到现有系统？" | Clean Architecture + 依赖注入 |
| "怎么处理用户数据？" | CharStatsService 持久化记忆 |

### 4.3 差异化优势

#### 🎯 真实场景（非玩具项目）
- 不是 Jupyter Notebook 演示
- 是真实桌面应用，可直接运行
- 用户输入"量子计算"→ 生成个性化文章 + 弱字适配报告

#### 🎯 全栈展示
- **后端**：Python Agent + SQLite
- **前端**：Qt/QML 桌面 UI
- **未来**：Java Spring Boot（跨语言）
- **部署**：Nuitka 单文件打包

#### 🎯 可量化成果
- 打包成单文件给面试官运行
- 输入主题 → 实时看到 Agent 思考过程
- 生成文本 + 质量评估报告 + 个人弱字适配度

---

## 5. 实施路线图

### Phase 1：单 Agent 循环（Day 1-2）

**目标**：实现 "生成 → 评估 → 决策" 经典 Agent 循环

**任务清单**：
- [ ] 添加依赖：`uv add langgraph langchain-openai instructor pydantic`
- [ ] 创建 `src/backend/agents/` 目录结构
- [ ] 实现 4 个 Tool：
  - [ ] `get_weakest_chars`：复用 CharStatsService
  - [ ] `generate_text`：Instructor 结构化输出
  - [ ] `evaluate_text`：LLM-as-Judge
  - [ ] `save_to_backend`：本地存储
- [ ] 实现 `ai_typing_coach_agent.py`（StateGraph）
- [ ] 新增 `AiCoachWorker`（QRunnable）
- [ ] 修改 `bridge.py` 新增信号/槽
- [ ] 编写测试：`test_ai_coach_agent.py`

**验收标准**：
- 调用 `bridge.requestAiCoachText("科技", 200)` 返回评估报告
- 控制台打印 Agent Chain-of-Thought 日志
- 测试覆盖核心路径

### Phase 2：Multi-Agent 系统（Day 3-5）

**目标**：升级为 Multi-Agent 协作系统

**任务清单**：
- [ ] 拆分为 3 个 Agent：
  - [ ] `GeneratorAgent`：专注文本生成
  - [ ] `EvaluatorAgent`：专注质量评估
  - [ ] `SaverAgent`：决策存储策略
- [ ] 使用 `create_supervisor` 编排
- [ ] 新增 QML 页面：`AiCoachPage.qml`
- [ ] 更新 `Main.qml` 导航
- [ ] 更新 `AGENTS.md` 文档

**验收标准**：
- UI 中可选择主题 + 长度 → 触发 Agent
- 显示 Agent 思考过程（Chain-of-Thought）
- 评估报告 + 保存结果展示

### Phase 3：增强功能（Day 6-7，可选）

**目标**：锦上添花，提升面试竞争力

**任务清单**：
- [ ] RAG 记忆：Chroma 向量库 + 用户历史
- [ ] 可观测性：LangSmith/LangFuse 集成
- [ ] 本地模型：Ollama + qwen2.5 默认配置
- [ ] Spring Boot 预留：/ai-import 接口

---

## 6. 技术栈选择

### 推荐方案

| 组件 | 选择 | 理由 |
|------|------|------|
| **Agent 框架** | LangGraph | 2025-2026 主流，面试最爱 |
| **LLM 提供商** | Ollama（默认） + OpenAI（可选） | 本地优先，降低成本 |
| **结构化输出** | Instructor | Pydantic 模型强制输出 |
| **向量库**（Phase 3） | ChromaDB | 轻量级，易于集成 |
| **可观测性**（Phase 3） | LangSmith | 官方工具，可视化好 |

### 依赖清单

```toml
# pyproject.toml 新增
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

## 7. 风险缓解清单

### 已识别风险及对策

| 风险 | 严重度 | 发生概率 | 缓解措施 |
|------|--------|---------|---------|
| Qt 事件循环阻塞 | 高 | 中 | QThreadPool + Worker 模式 |
| API 密钥成本 | 中 | 高 | 默认 Ollama 本地模型 |
| Agent 输出不稳定 | 中 | 中 | 结构化输出 + 重试 + 质量门控 |
| 依赖包过大 | 低 | 高 | 可选依赖 + 本地模型 |
| Demo 演示失败 | 中 | 中 | 预设缓存 + 离线模式 |
| 现有代码侵入 | 低 | 低 | 功能开关 + 最小侵入 |

---

## 8. 总结

### 可行性评级：⭐⭐⭐⭐☆（4/5）

TypeType 项目转化为 AI Agent 面试项目**高度可行**，主要优势：

1. **架构基础完美**：Clean Architecture + 依赖注入 = 无缝扩展
2. **记忆机制就绪**：CharStatsService + SQLite = Agent 真实记忆
3. **UI 基础完善**：WeakCharsPage + Bridge 信号 = 快速集成
4. **差异化明显**：真实桌面应用 vs 90% 的 Jupyter Notebook

### 核心建议

1. **立即行动**：今天就添加 LangGraph + 第一个 Tool（get_weakest_chars）
2. **本地优先**：默认使用 Ollama，降低成本和网络依赖
3. **质量门控**：LLM-as-Judge 是核心卖点，务必实现
4. **可视化过程**：即使结果未出，展示 Agent 思考链

### 面试价值预期

- **技术深度**：从 "入门级 LLM 使用" 升级到 "Production-grade Agent"
- **差异化**：真实桌面应用 + 个性化记忆 + 可量化成果
- **全栈能力**：Python Agent + Qt UI + SQLite + 未来 Java Spring Boot

**改造周期**：2 周内可完成核心功能，拥有可演示的 AI Typing Coach Agent。

---

## 附录

### A. 相关文件清单

**需修改文件**：
- `src/backend/presentation/bridge.py`（新增信号/槽）
- `main.py`（新增依赖注入）
- `pyproject.toml`（新增依赖）
- `AGENTS.md`（更新文档）

**新增文件**：
- `src/backend/agents/`（Agent 目录）
- `src/qml/pages/AiCoachPage.qml`（UI 页面）
- `tests/test_ai_coach_agent.py`（测试）

**可复用文件**：
- `src/backend/domain/services/char_stats_service.py`（记忆源）
- `src/backend/application/ports/char_stats_repository.py`（协议）
- `src/qml/pages/WeakCharsPage.qml`（UI 参考）

### B. 参考资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Instructor 结构化输出](https://python.useinstructor.com/)
- [Ollama 本地模型](https://ollama.com/)
- [Clean Architecture 原则](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

### C. 快速开始命令

```bash
# 1. 拉取最新代码
git pull

# 2. 添加 AI 依赖
uv add langgraph langchain-ollama instructor pydantic

# 3. 安装 Ollama（本地模型）
# macOS/Linux: curl -fsSL https://ollama.com/install.sh | sh
# Windows: 下载 https://ollama.com/download/windows

# 4. 拉取模型
ollama pull qwen2.5:7b

# 5. 运行项目
uv run python main.py
```

---

**文档版本**：v1.0  
**创建日期**：2026-03-21  
**适用项目版本**：TypeType v0.2.6+
