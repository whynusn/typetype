# TypeType 功能路线图

> 最后更新：2026-03-21
>
> 本文档记录 TypeType 客户端当前完成状态与后续功能规划。

---

## 一、已完成

| 阶段 | 内容 | 状态 |
|------|------|------|
| CharStat 实体 | `src/backend/models/entity/char_stat.py` — 字符级统计 (char, char_count, error_char_count, total_ms, min_ms, max_ms, last_seen) | ✅ |
| SessionStat 实体 | `src/backend/models/entity/session_stat.py` — 会话级统计 | ✅ |
| TypingService 集成 | `handleCommittedText` 合并循环：char_stats 累积 + prefix_sum 更新 + 着色，单次遍历完成 | ✅ |
| Bridge 合并 | 原 Backend 合并到 Bridge，key_listener 由 Bridge 持有，QML 统一走 appBridge | ✅ |
| 目录结构 | 领域实体统一到 `models/`，删除 `typing/` 目录 | ✅ |
| SQLite 持久化 | `SqliteCharStatsRepository` + `CharStatsRepository` 协议 | ✅ |
| CharStatsService | 内存缓存 + 异步持久化 + 薄弱字查询 | ✅ |
| WeakCharsPage | QML 薄弱字展示页面，显示 top 10 薄弱字符 | ✅ |
| 异步 Worker | `CharStatFlushWorker` + `WeakCharsQueryWorker` 异步执行 | ✅ |

### CharStat 实体设计

```python
@dataclass
class CharStat:
    char: str               # 字符（主键）
    char_count: int         # 字符上屏次数
    error_char_count: int   # 错误字符次数
    total_ms: float         # 累计耗时（毫秒）
    min_ms: float           # 最快按键
    max_ms: float           # 最慢按键
    last_seen: str          # 最近一次出现时间

    def accumulate(keystroke_ms, is_error) -> None
    def merge(other: CharStat) -> None
    @property avg_ms -> float
    @property error_rate -> float
```

### 同步特性

- `char_count` 系字段取 max（本地全量值直接覆盖远端）
- `min_ms` / `max_ms` 取极值
- `last_seen` 取最新
- 聚合数据天然无冲突 —— 不存在"本地说 100 次、远端说 200 次"的矛盾

---

## 二、本地持久化

```
Phase 2: 本地 SQLite 持久化
```

### 2.1 本地表结构

```sql
CREATE TABLE char_stats (
    char              TEXT PRIMARY KEY,
    char_count        INTEGER NOT NULL DEFAULT 0,
    error_char_count  INTEGER NOT NULL DEFAULT 0,
    total_ms          REAL NOT NULL DEFAULT 0.0,
    min_ms            REAL NOT NULL DEFAULT 0.0,
    max_ms            REAL NOT NULL DEFAULT 0.0,
    last_seen         TEXT NOT NULL DEFAULT '',

    last_synced_at    TEXT,             -- 上次同步成功时间
    is_dirty          INTEGER DEFAULT 1 -- 1=有变更未同步
);
```

### 2.2 Port 层

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class CharStatsRepository(Protocol):
    """字符统计持久化协议。"""

    def init_db(self) -> None:
        """初始化数据库（创建表结构）。"""
        ...

    def get(self, char: str) -> CharStat | None:
        """获取单个字符的统计。"""
        ...

    def get_batch(self, chars: list[str]) -> list[CharStat]:
        """批量获取字符统计。"""
        ...

    def get_weakest_chars(self, n: int) -> list[CharStat]:
        """获取最薄弱的 n 个字符统计"""
        ...

    def save(self, stat: CharStat) -> None:
        """保存单个字符的统计（插入或更新）。"""
        ...

    def save_batch(self, stats: list[CharStat]) -> None:
        """批量保存字符统计。"""
        ...

    def get_all(self) -> list[CharStat]:
        """获取全部字符统计。"""
        ...

    def get_all_dirty(self) -> list[CharStat]:
        """获取所有待同步的字符统计（is_dirty=1）。"""
        ...

    def mark_synced(self, chars: list[str], synced_at: str) -> None:
        """标记字符为已同步。"""
        ...
```

### 2.3 Integration 实现

```python
class SqliteCharStatsRepository(CharStatsRepository):
    """本地 SQLite 实现"""

class NoopCharStatsRepository(CharStatsRepository):
    """占位实现，无持久化时不影响打字功能"""
```

---

## 三、CharStatsService

```
Phase 3: ✅ CharStatsService — 管理内存缓存 + 持久化调度（已完成）
```

```python
class CharStatsService:
    """字符统计领域服务。

    按需加载（lazy loading）：首次遇到字符时才从数据库读取，
    避免启动时全量加载到内存。
    """

    def __init__(self, repository: CharStatsRepository):
        self._repo = repository
        self._cache: dict[str, CharStat] = {}
        self._dirty: set[str] = set()
        self._repo.init_db()

    def accumulate(self, char: str, keystroke_ms: float, is_error: bool) -> None:
        """累积一次字符结果（从 TypingService 调用）"""
        if char not in self._cache:
            existing = self._repo.get(char)
            self._cache[char] = existing if existing else CharStat(char)
        self._cache[char].accumulate(keystroke_ms, is_error)
        self._dirty.add(char)

    def warm_chars(self, chars: list[str]) -> None:
        """预热缓存（启动时加载高频字）"""

    def flush(self) -> None:
        """同步持久化缓存到本地"""

    def flush_async(self) -> None:
        """异步持久化缓存到本地（打完文章后调用）"""

    def get_weakest_chars(self, n: int = 10) -> list[CharStat]:
        """获取最弱的 n 个字符（按 error_rate 排序）"""
        return self._repo.get_weakest_chars(n)

    def get_all(self) -> dict[str, CharStat]:
        """获取全部统计"""
        return dict(self._cache)
```

集成点：`TypingService.typingEnded` → 触发 `CharStatsService.flush_async()`

---

## 四、远端同步（Spring Boot）

```
Phase 4: 远端同步（与 spring-boot-backend-design.md 配合）
```

### 4.1 API 设计

```yaml
POST   /api/v1/sync/char-stats    # 批量上传本地变更
GET    /api/v1/sync/char-stats    # 拉取远端变更（since 参数）
```

### 4.2 MySQL 表结构

```sql
CREATE TABLE user_char_stats (
    user_id         VARCHAR(64),
    char            VARCHAR(4),
    char_count      INT,
    error_char_count INT,
    total_ms        DOUBLE,
    min_ms          DOUBLE,
    max_ms          DOUBLE,
    last_seen       DATETIME,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, char)
);
```

### 4.3 同步策略（混合方案）

```
启动时：pull 远端数据到本地
打完文章：push dirty 数据
关闭应用：push dirty 数据兜底
```

### 4.4 Port 层

```python
class SyncRepository(ABC):
    @abstractmethod
    def push_char_stats(self, stats: list[CharStat]) -> None: ...

    @abstractmethod
    def pull_char_stats(self, since: datetime) -> list[CharStat]: ...
```

### 4.5 边界情况

| 场景 | 处理方式 |
|------|----------|
| 首次登录新设备 | pull 全量远端数据到本地 |
| 离线打字一周后上线 | 批量 push 积压的 dirty 数据 |
| 多设备同时打字 | 本地值即最新全量，直接覆盖远端 |
| 同步中途断网 | 下次重试，is_dirty = 1 的数据会再次上传 |
| 用户注销 | 清本地数据，下次登录触发 pull |

---

## 五、UI 功能

```
Phase 5: ✅ QML UI — 薄弱字看板（已完成）
```

### 5.1 薄弱字看板（WeakCharsPage）

- ✅ 显示 `error_rate` 最高的前 10 个字符
- ✅ 每个字符展示：输入次数、错误率、平均耗时
- ✅ 颜色编码：红色 (>20%) / 黄色 (>10%) / 绿色 (≤10%)
- ✅ 通过 Bridge 的 `weakestCharsLoaded` 信号获取数据

### 5.2 推荐练习（待开发）

- 根据薄弱字生成随机练习文本
- 权重算法：`weight = error_rate * log(char_count + 1)`（兼顾错误率和练习量）

### 5.3 进度追踪（待开发）

- 展示单字符的 `error_rate` 变化曲线（随时间/随 session）

---

## 六、AI Agent 改造（新增）

```
Phase 6: AI Typing Coach Agent — 面试杀手锏（规划中）
```

详见 [guide.md](./guide.md) - AI Agent 转化规划指南

### 快速概览

| 阶段 | 目标 | 工作量 |
|------|------|--------|
| Phase 1 | 单 Agent 循环（生成→评估→决策） | 1-2 天 |
| Phase 2 | Multi-Agent 系统 | 3-5 天 |
| Phase 3 | RAG + 可观测性 | 2-3 天 |

### 核心优势

- **完美匹配**：`CharStatsService.get_weakest_chars()` 正是 Agent 的记忆源
- **低阻力**：Ports & Adapters 架构允许无缝添加新服务
- **UI 基础**：WeakCharsPage 可复用/扩展

---

## 七、后续探索

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 混淆对统计 | 记录哪些字符经常互换（如 "的"↔"得"） | 中 |
| 跨词频分层 | 按 pinyin / 部首 / 词频分组统计 | 低 |
| 智能推荐 | 根据薄弱点动态调整练习难度 | 低 |
| 社交功能 | 好友对比、对战模式 | 待定 |

---

## 八、目录结构

```
src/backend/
├── application/
│   ├── gateways/      # TextGateway, ScoreGateway
│   ├── ports/         # 协议定义
│   └── usecases/      # LoadTextUseCase, TypingUseCase
├── config/            # RuntimeConfig
├── domain/
│   └── services/      # TypingService, AuthService, CharStatsService
├── infrastructure/    # ApiClient, NetworkErrors
├── integration/       # SaiWenTextFetcher, CatalogService, SqliteCharStatsRepository
├── models/
│   ├── entity/        # CharStat, SessionStat
│   ├── dto/           # ScoreSummaryDTO, HistoryRecordDTO
│   └── text_source.py # TextSource, TextSourceConfig
├── presentation/
│   ├── adapters/      # TypingAdapter, TextAdapter
│   └── bridge.py      # Bridge
├── security/          # Crypt, SecureStorage
├── utils/             # Logger
└── workers/           # BaseWorker, TextLoadWorker, SessionStatWorker
```
