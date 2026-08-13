# 动态源统一载文机制（Content Snapshot + Freshness）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为动态源（每次随机/周期轮换/低频）实现统一的快照存储 + 新鲜度表现 + 用户 per-source 刷新间隔覆盖，修复「选中载入失配」缺陷。

**Architecture:** 三层：integration 层磁盘快照存储（`EntrySnapshotStore`）+ 刷新策略（`RefreshPolicy`）+ 常驻调度（`RefreshScheduler`）；application 层编排（`SnapshotCatalogService`，快照优先载入、不重抽）；presentation/QML 表现（RegistryAdapter 转发 + RepoEntriesPanel 新鲜度徽章 + ReposManagementPage 间隔设置）。用户覆盖存于 `RuntimeConfig.source_refresh_overrides`（三层优先级链：用户 > manifest > 推断）。

**Tech Stack:** Python 3.11 / PySide6（QObject/Signal/QTimer）/ pytest / ruff / QML（RinUI）。

**Spec:** `docs/designs/dynamic-source-snapshot-freshness.md`（已提交 `949eb3f`、`60c7f73`）

## Global Constraints

- 样式与运行验证：`uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`；测试断言 3 位小数的浮点比较。
- 架构：integration 层**纯存储无网络**；`RuntimeConfig` 是 config.json 唯一序列化者（`set_source_refresh_override` 等入口方法，不直接操作字段）；Bridge/Adapter **不直持 integration 对象**（经 container 注入）；新增源时测试须含 LoadTextUseCase / GlobalExceptionHandler / service 层覆盖。
- 运行时不可用（非 Qt 环境）：`EntrySnapshotStore`/`RefreshPolicy` 纯 Python；`RefreshScheduler` 仅在 Qt 事件循环存在时可用（单测用假 scheduler 或直接调 `_scan_due`，不断言 QTimer 线程）。
- 缓存/快照布局：`registry_cache_dir() = user_data_dir() / "registry_cache"`；快照 `snapshots/{authority_hash}/{entry_id}.json`，`authority_hash = sha256(authority).hexdigest()[:12]`；原子写 tmp+replace。
- 条目字段：entry 含 `_authority`（federation 注入）；快照文件内 `_authority` 冗余存储。
- 命名与拷贝规则：模式字面量 `"static" | "interval" | "on_demand"`；UI 文案中文（qsTr）。

---

### Task 1: RefreshPolicy（integration 层，纯 Python）

**Files:**
- Create: `src/backend/integration/refresh_policy.py`
- Test: `tests/test_refresh_policy.py`

**Interfaces:**
- Produces: `class RefreshPolicy`（dataclass）+ `MODE_STATIC / MODE_INTERVAL / MODE_ON_DEMAND` 常量；`RefreshPolicy(mode, interval_seconds=0)`；`next_refresh_at(captured_at: float) -> float | None`；`to_dict() / from_dict()`；模块函数 `infer_policy(source_type: str) -> RefreshPolicy`（`ott-instance→static`、其余→on_demand）；`source_type_of(entry: dict) -> str | None`。
- Consumes: 无。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_refresh_policy.py
"""RefreshPolicy：模式 → 到期时间、序列化、manifest 推断。"""

from __future__ import annotations

from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_ON_DEMAND,
    MODE_STATIC,
    RefreshPolicy,
    infer_policy,
    source_type_of,
)


def test_static_never_expires() -> None:
    p = RefreshPolicy(MODE_STATIC)
    assert p.next_refresh_at(1000.0) is None


def test_interval_anchors_from_captured_at() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=3600)
    assert p.next_refresh_at(1000.0) == 4600.0


def test_on_demand_expires_immediately() -> None:
    p = RefreshPolicy(MODE_ON_DEMAND)
    assert p.next_refresh_at(1000.0) == 1000.0


def test_interval_requires_positive_seconds() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=0)
    assert p.next_refresh_at(1000.0) == 1000.0  # 立即过期（视作 on_demand）


def test_roundtrip_dict() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=86400)
    assert RefreshPolicy.from_dict(p.to_dict()) == p


def test_infer_instance_is_static() -> None:
    assert infer_policy("ott-instance").mode == MODE_STATIC


def test_infer_rule_script_bridge_is_on_demand() -> None:
    for t in ("ott-rule", "ott-script", "ott-bridge"):
        assert infer_policy(t).mode == MODE_ON_DEMAND


def test_source_type_of_uses_private_source_key() -> None:
    assert source_type_of({"_source_type": "ott-rule"}) == "ott-rule"
    assert source_type_of({}) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_refresh_policy.py -q`
Expected: FAIL（`ModuleNotFoundError: refresh_policy`）

- [ ] **Step 3: 最小实现**

```python
# src/backend/integration/refresh_policy.py
"""动态源刷新策略（快照到期时间计算）。

模式：
- static    永不过期（不调度）
- interval  按 interval_seconds 周期到期（到期自动刷新）
- on_demand 立即过期（仅手动刷新，防无限刷新循环）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODE_STATIC = "static"
MODE_INTERVAL = "interval"
MODE_ON_DEMAND = "on_demand"

_VALID_MODES = frozenset({MODE_STATIC, MODE_INTERVAL, MODE_ON_DEMAND})


@dataclass
class RefreshPolicy:
    mode: str = MODE_ON_DEMAND
    interval_seconds: int = 0

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            self.mode = MODE_ON_DEMAND
        if not isinstance(self.interval_seconds, int) or self.interval_seconds < 0:
            self.interval_seconds = 0

    def next_refresh_at(self, captured_at: float) -> float | None:
        """static → None（永不过期）；on_demand/interval≤0 → captured_at；否则 captured_at + interval。"""
        if self.mode == MODE_STATIC:
            return None
        if self.interval_seconds > 0:
            return captured_at + self.interval_seconds
        return captured_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            **({"interval_seconds": self.interval_seconds} if self.interval_seconds > 0 else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RefreshPolicy":
        if not isinstance(data, dict):
            return cls()
        raw = data.get("mode", "")
        return cls(
            mode=raw if raw in _VALID_MODES else MODE_ON_DEMAND,
            interval_seconds=data.get("interval_seconds", 0)
            if isinstance(data.get("interval_seconds"), int)
            else 0,
        )


def source_type_of(entry: dict) -> str | None:
    """从 entry 提取源类型（联邦客户端注入的私有字段）。"""
    st = entry.get("_source_type")
    return st if isinstance(st, str) and st else None


def infer_policy(source_type: str | None) -> RefreshPolicy:
    """缺省推断：ott-instance → static；其余（rule/script/bridge）→ on_demand。"""
    if source_type == "ott-instance":
        return RefreshPolicy(MODE_STATIC)
    return RefreshPolicy(MODE_ON_DEMAND)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_refresh_policy.py -q`
Expected: PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check src/backend/integration/refresh_policy.py tests/test_refresh_policy.py && uv run ruff format --check src/backend/integration/refresh_policy.py tests/test_refresh_policy.py`
Commit:
```bash
git add src/backend/integration/refresh_policy.py tests/test_refresh_policy.py
git commit -m "feat: RefreshPolicy 动态源刷新策略（static/interval/on_demand）"
```

---

### Task 2: RuntimeConfig.source_refresh_overrides（用户 per-source 覆盖）

**Files:**
- Modify: `src/backend/config/runtime_config.py`（字段+dataclass+`_from_dict`+`_to_dict`+入口方法）
- Modify: `src/backend/config/runtime_config.py` 迁移（`_needs_v1_migration` 不改；`_fresh_with_builtin` 不改）
- Test: `tests/test_runtime_config.py`（新增类）

**Interfaces:**
- Consumes: Task 1 的 `RefreshPolicy`（from_dict/to_dict）—— 仅复用序列化形状，不 import（避免 config 层依赖 integration 层）；直接手写 `{"mode": ..., "interval_seconds": ...}` 读写。
- Produces: `RuntimeConfig.source_refresh_overrides: dict[str, dict]`（key=authority，value=`{"mode": "static"|"interval"|"on_demand", "interval_seconds": int}`）；`set_source_refresh_override(authority, mode, interval_seconds=0) -> None`（无效 mode 忽略）；`clear_source_refresh_override(authority) -> None`；`get_source_refresh_override(authority) -> dict | None`。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_runtime_config.py` 末尾）

```python
class TestSourceRefreshOverrides:
    def test_default_empty(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        assert cfg.source_refresh_overrides == {}

    def test_set_and_get(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        assert cfg.get_source_refresh_override("auth:1") == {
            "mode": "interval", "interval_seconds": 3600
        }

    def test_invalid_mode_ignored(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "bogus", 10)
        assert cfg.get_source_refresh_override("auth:1") is None

    def test_clear_removes(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 60)
        cfg.clear_source_refresh_override("auth:1")
        assert cfg.get_source_refresh_override("auth:1") is None

    def test_roundtrip_to_dict(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        d = cfg._to_dict()
        assert d["source_refresh_overrides"] == {
            "auth:1": {"mode": "interval", "interval_seconds": 3600}
        }

    def test_load_from_file_roundtrip(self, tmp_path):
        cfg = RuntimeConfig._fresh_with_builtin()
        cfg.set_source_refresh_override("auth:1", "interval", 3600)
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg._to_dict()), encoding="utf-8")
        loaded = RuntimeConfig.load_from_file(str(p))
        assert loaded.get_source_refresh_override("auth:1") == {
            "mode": "interval", "interval_seconds": 3600
        }

    def test_from_dict_tolerates_bad_values(self):
        cfg = RuntimeConfig._fresh_with_builtin()
        d = cfg._to_dict()
        d["source_refresh_overrides"] = {
            "auth:1": {"mode": "interval", "interval_seconds": "not-a-number"},
            "auth:2": "garbage",
        }
        parsed = RuntimeConfig._from_dict(d)
        assert parsed.get_source_refresh_override("auth:1") is None
        assert parsed.get_source_refresh_override("auth:2") is None
```

（文件顶部若缺 `import json`，追加 `import json`。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_runtime_config.py -q -k SourceRefresh`
Expected: FAIL（`AttributeError: 'RuntimeConfig' object has no attribute 'source_refresh_overrides'`）

- [ ] **Step 3: 实现**（在 `runtime_config.py` 中）

在 `SourceReposConfig` 之后新增：

```python
@dataclass
class SourceRefreshOverridesConfig:
    """用户 per-source 刷新间隔覆盖（authority → {mode, interval_seconds}）。

    优先级链：用户覆盖 > manifest 声明（未来） > 客户端推断。
    """

    overrides: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.overrides, dict):
            self.overrides = {}
```

在 `RuntimeConfig` 字段区（`source_repos` 之后）新增：

```python
    source_refresh_overrides: SourceRefreshOverridesConfig = field(
        default_factory=SourceRefreshOverridesConfig
    )
```

在 `_from_dict` 中（`source_repos` 解析之后）新增：

```python
        # 解析用户 per-source 刷新间隔覆盖（容错：非 dict / 非法 mode / 非 int 秒数 → 丢弃该条目）
        overrides: dict[str, dict] = {}
        raw_overrides = data.get("source_refresh_overrides")
        if isinstance(raw_overrides, dict):
            for authority, ov in raw_overrides.items():
                if not isinstance(authority, str) or not isinstance(ov, dict):
                    continue
                mode = ov.get("mode")
                if mode not in ("static", "interval", "on_demand"):
                    continue
                interval = cls._safe_int(ov.get("interval_seconds"), 0)
                overrides[authority] = {
                    "mode": mode,
                    **({"interval_seconds": interval} if interval > 0 else {}),
                }
        source_refresh_overrides = SourceRefreshOverridesConfig(overrides=overrides)
```

在 `_to_dict` 中（`source_repos` 键之后）新增：

```python
            "source_refresh_overrides": dict(self.source_refresh_overrides.overrides),
```

新增入口方法（放在 `set_source_repo_enabled` 附近）：

```python
    def set_source_refresh_override(
        self, authority: str, mode: str, interval_seconds: int = 0
    ) -> None:
        """设置某 authority 的刷新间隔覆盖（用户 per-source 覆盖）。

        无效 mode / 空 authority 忽略；interval_seconds ≤ 0 时不写秒数字段。
        """
        if not isinstance(authority, str) or not authority.strip():
            return
        if mode not in ("static", "interval", "on_demand"):
            return
        entry: dict = {"mode": mode}
        if mode == "interval" and isinstance(interval_seconds, int) and interval_seconds > 0:
            entry["interval_seconds"] = interval_seconds
        self.source_refresh_overrides.overrides[authority] = entry

    def clear_source_refresh_override(self, authority: str) -> None:
        self.source_refresh_overrides.overrides.pop(authority, None)

    def get_source_refresh_override(self, authority: str) -> dict | None:
        ov = self.source_refresh_overrides.overrides.get(authority)
        return dict(ov) if isinstance(ov, dict) else None
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_runtime_config.py -q`
Expected: PASS（含既有用例）

- [ ] **Step 5: ruff + 提交**

Commit:
```bash
git add src/backend/config/runtime_config.py tests/test_runtime_config.py
git commit -m "feat: RuntimeConfig.source_refresh_overrides 用户 per-source 刷新间隔覆盖"
```

---

### Task 3: EntrySnapshotStore（integration 层磁盘快照）

**Files:**
- Create: `src/backend/integration/entry_snapshot_store.py`
- Test: `tests/test_entry_snapshot_store.py`

**Interfaces:**
- Consumes: Task 1 `RefreshPolicy`。
- Produces: `class EntrySnapshotStore`；`__init__(cache_dir: Path, max_per_source: int = 5)`；`save(entry: dict, captured_at: float, policy: RefreshPolicy) -> None`；`get(authority: str, entry_id: str) -> dict | None`（返回带 freshness 元数据的 dict，含 `_authority`）；`list(authority: str) -> list[dict]`（按 `captured_at` 倒序）；`prune(authority: str, max_per_source: int | None = None) -> None`；`due_for_refresh(now: float) -> list[tuple[str, str]]`（仅 interval 到期，on_demand 不入调度）；`clear_cache() -> None`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_entry_snapshot_store.py
"""EntrySnapshotStore：快照落盘/读取/prune/调度到期。"""

from __future__ import annotations

import json
import os
import time

import pytest

from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_STATIC,
    RefreshPolicy,
)


def _entry(authority: str, entry_id: str, content: str = "text") -> dict:
    return {"_authority": authority, "entry_id": entry_id, "content": content}


def test_save_get_roundtrip(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "e1"), captured_at=1000.0, policy=RefreshPolicy(MODE_STATIC))
    got = s.get("auth", "e1")
    assert got is not None
    assert got["entry_id"] == "e1"
    assert got["_authority"] == "auth"
    assert got["captured_at"] == 1000.0


def test_missing_returns_none(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    assert s.get("auth", "nope") is None


def test_list_orders_by_captured_at_desc(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "old"), captured_at=100.0, policy=RefreshPolicy(MODE_STATIC))
    s.save(_entry("auth", "new"), captured_at=200.0, policy=RefreshPolicy(MODE_STATIC))
    ids = [e["entry_id"] for e in s.list("auth")]
    assert ids == ["new", "old"]


def test_prune_keeps_latest_n(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path, max_per_source=2)
    for i in range(4):
        s.save(_entry("auth", f"e{i}"), captured_at=float(i), policy=RefreshPolicy(MODE_STATIC))
    s.prune("auth")
    ids = [e["entry_id"] for e in s.list("auth")]
    assert ids == ["e3", "e2"]


def test_due_for_refresh_only_interval(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "iv"), captured_at=0.0, policy=RefreshPolicy(MODE_INTERVAL, 10))
    s.save(_entry("auth", "od"), captured_at=0.0, policy=RefreshPolicy("on_demand"))
    due = s.due_for_refresh(now=15.0)
    assert ("auth", "iv") in due
    assert ("auth", "od") not in due


def test_corrupt_file_returns_none(tmp_path) -> None:
    s = EntrySnapshotStore(tmp_path)
    s.save(_entry("auth", "e1"), captured_at=0.0, policy=RefreshPolicy(MODE_STATIC))
    from src.backend.integration.entry_snapshot_store import _authority_hash

    p = tmp_path / _authority_hash("auth") / "e1.json"
    p.write_text("{broken", encoding="utf-8")
    assert s.get("auth", "e1") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_entry_snapshot_store.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 最小实现**

```python
# src/backend/integration/entry_snapshot_store.py
"""动态源条目快照磁盘存储（纯存储，无网络）。

布局：registry_cache_dir()/snapshots/{authority_hash}/{entry_id}.json
- 列表展示的物化内容落盘，选中载入直接从快照取（不重新执行规则/脚本）
- 保留最近 N 条（prune），旧快照可回看/可继续打
- on_demand 快照虽立即过期，但不入自动调度（防无限刷新循环）
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .refresh_policy import MODE_INTERVAL, RefreshPolicy


def _authority_hash(authority: str) -> str:
    return hashlib.sha256(authority.encode("utf-8")).hexdigest()[:12]


class EntrySnapshotStore:
    def __init__(self, cache_dir: Path, max_per_source: int = 5) -> None:
        self._root = Path(cache_dir) / "snapshots"
        self._max_per_source = max(1, max_per_source)

    # ------------------------------------------------------------------
    # 内部：路径
    # ------------------------------------------------------------------

    def _dir(self, authority: str) -> Path:
        return self._root / _authority_hash(authority)

    def _path(self, authority: str, entry_id: str) -> Path:
        return self._dir(authority) / f"{entry_id}.json"

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def save(self, entry: dict, captured_at: float, policy: RefreshPolicy) -> None:
        if not isinstance(entry, dict):
            return
        entry_id = entry.get("entry_id")
        authority = entry.get("_authority", "")
        if not entry_id or not authority:
            return
        payload: dict[str, Any] = {
            **entry,
            "captured_at": captured_at,
            "refresh_policy": policy.to_dict(),
            "next_refresh_at": policy.next_refresh_at(captured_at),
        }
        path = self._path(authority, str(entry_id))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f"{path.suffix}.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def get(self, authority: str, entry_id: str) -> dict | None:
        try:
            path = self._path(authority, entry_id)
            if not path.exists():
                return None
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        data.setdefault("_authority", authority)
        return data

    def list(self, authority: str) -> list[dict]:
        directory = self._dir(authority)
        try:
            if not directory.exists():
                return []
            items = []
            for path in directory.iterdir():
                if not path.is_file() or not path.suffix == ".json":
                    continue
                data = self.get(authority, path.stem)
                if data is not None:
                    items.append(data)
        except OSError:
            return []
        items.sort(key=lambda e: e.get("captured_at", 0.0), reverse=True)
        return items

    # ------------------------------------------------------------------
    # prune / 调度
    # ------------------------------------------------------------------

    def prune(self, authority: str, max_per_source: int | None = None) -> None:
        limit = max(1, max_per_source or self._max_per_source)
        items = self.list(authority)
        for stale in items[limit:]:
            try:
                self._path(authority, stale.get("entry_id", "")).unlink(missing_ok=True)
            except OSError:
                pass

    def due_for_refresh(self, now: float) -> list[tuple[str, str]]:
        """返回 (authority, entry_id) 中 interval 模式已到期的快照（on_demand 不返回）。"""
        due: list[tuple[str, str]] = []
        try:
            if not self._root.exists():
                return []
            for authority_dir in self._root.iterdir():
                if not authority_dir.is_dir():
                    continue
                # authority 从哈希目录反查：快照内冗余 _authority 字段
                for path in authority_dir.glob("*.json"):
                    try:
                        with path.open(encoding="utf-8") as f:
                            data = json.load(f)
                    except (OSError, json.JSONDecodeError, ValueError, TypeError):
                        continue
                    if not isinstance(data, dict):
                        continue
                    policy = RefreshPolicy.from_dict(data.get("refresh_policy"))
                    if policy.mode != MODE_INTERVAL:
                        continue
                    nra = data.get("next_refresh_at")
                    if isinstance(nra, (int, float)) and nra <= now:
                        due.append((str(data.get("_authority", "")), str(data.get("entry_id", ""))))
        except OSError:
            return []
        return due

    def clear_cache(self) -> None:
        import shutil

        try:
            if self._root.exists():
                shutil.rmtree(self._root)
                self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_entry_snapshot_store.py -q`
Expected: PASS

- [ ] **Step 5: ruff + 提交**

Commit:
```bash
git add src/backend/integration/entry_snapshot_store.py tests/test_entry_snapshot_store.py
git commit -m "feat: EntrySnapshotStore 条目快照磁盘存储（原子写/prune/到期扫描）"
```

---

### Task 4: SnapshotCatalogService（application 层编排）

**Files:**
- Create: `src/backend/application/services/snapshot_catalog_service.py`
- Test: `tests/test_snapshot_catalog_service.py`

**Interfaces:**
- Consumes: Task 1 `RefreshPolicy`（含 `infer_policy`、`source_type_of`）、Task 2 `RuntimeConfig.get_source_refresh_override`、Task 3 `EntrySnapshotStore`；`OttFederationProvider.list_all_entries()` / `.get_entry(authority, entry_id)`。
- Produces: `class SnapshotCatalogService`；`__init__(federation, store, runtime_config, async_executor=None, max_per_source=5)`；`refresh_and_list_all() -> list[dict]`；`load_entry(authority, entry_id) -> dict | None`；`refresh_source(authority) -> None`（同步物化+快照+prune）；`scheduled_tick() -> None`（用 async_executor 后台刷新 interval 到期源，无 executor 时同步）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_snapshot_catalog_service.py
"""SnapshotCatalogService：物化写快照、快照优先载入（零 fetch）、刷新换新。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.backend.application.services.snapshot_catalog_service import (
    SnapshotCatalogService,
)
from src.backend.integration.entry_snapshot_store import EntrySnapshotStore
from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_ON_DEMAND,
    RefreshPolicy,
)


class _FakeFederation:
    def __init__(self, entries):
        self._entries = entries
        self.get_entry_calls = []
        self.last_fetch = None

    def list_all_entries(self):
        return list(self._entries)

    def get_entry(self, authority, entry_id):
        self.get_entry_calls.append((authority, entry_id))
        return self.last_fetch


def _svc(tmp_path, entries, runtime_config=None, max_per_source=5):
    federation = _FakeFederation(entries)
    store = EntrySnapshotStore(tmp_path)
    return SnapshotCatalogService(federation, store, runtime_config, max_per_source=max_per_source), federation


def _entry(authority="auth", entry_id="e1", content="hello", source_type="ott-rule"):
    return {"_authority": authority, "entry_id": entry_id, "content": content,
            "_source_type": source_type}


def test_refresh_and_list_persists_snapshot(tmp_path) -> None:
    svc, _ = _svc(tmp_path, [_entry()])
    result = svc.refresh_and_list_all()
    assert len(result) == 1
    # 物化结果已落盘：载入从快照取，不重抽
    loaded = svc.load_entry("auth", "e1")
    assert loaded is not None and loaded["content"] == "hello"


def test_load_entry_does_not_refetch_when_snapshot_hits(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [_entry()])
    svc.refresh_and_list_all()
    svc.load_entry("auth", "e1")
    assert federation.get_entry_calls == []  # 零 fetch —— 失配修复回归


def test_load_entry_falls_back_to_federation_on_miss(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [_entry()])
    federation.last_fetch = {"entry_id": "ghost", "content": "fallback"}
    loaded = svc.load_entry("auth", "ghost")
    assert loaded is not None and loaded["content"] == "fallback"
    assert federation.get_entry_calls == [("auth", "ghost")]


def test_refresh_source_materializes_new_snapshot(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [])
    # 首次：无条目
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is None
    # 第二次：federation 有内容 → 换新
    federation._entries = [_entry()]
    svc.refresh_source("auth")
    assert svc.load_entry("auth", "e1") is not None


def test_prune_applies_on_refresh(tmp_path) -> None:
    svc, federation = _svc(tmp_path, [], max_per_source=2)
    for i in range(3):
        federation._entries = [_entry(entry_id=f"e{i}", content=f"c{i}")]
        svc.refresh_source("auth")
    assert svc.load_entry("auth", "e2") is not None
    assert svc.load_entry("auth", "e0") is None


def test_scheduled_tick_refreshes_interval_due(tmp_path) -> None:
    # interval 到期 → 后台/同步刷新；刷新后快照 captured_at 前移
    fed = _FakeFederation([_entry()])
    store = EntrySnapshotStore(tmp_path)
    store.save(_entry(), captured_at=0.0, policy=RefreshPolicy(MODE_INTERVAL, 10))
    svc = SnapshotCatalogService(fed, store, None)
    svc.scheduled_tick(now=15.0)  # 无 async_executor → 同步
    refreshed = store.get("auth", "e1")
    assert refreshed is not None
    assert refreshed["captured_at"] == 15.0
```

（注：`refresh_source`/`scheduled_tick` 的 `now` 参数仅测试用，默认取当前时间；上面 `scheduled_tick` 用 `now=15.0` 便于确定性。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_snapshot_catalog_service.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 最小实现**

```python
# src/backend/application/services/snapshot_catalog_service.py
"""动态源快照目录编排层。

- 联邦物化 → 逐条写快照 → prune → 返回带 freshness 的摘要列表
- load_entry：快照命中直接返回（不重新执行规则/脚本），miss 兜底 federation
- 调度：scheduled_tick 只刷新 interval 模式到期源（on_demand 仅手动）
- 用户 per-source 覆盖（config.source_refresh_overrides）> 推断
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..integration.entry_snapshot_store import EntrySnapshotStore
from ..integration.refresh_policy import (
    MODE_INTERVAL,
    RefreshPolicy,
    infer_policy,
    source_type_of,
)

if TYPE_CHECKING:
    from ..config.runtime_config import RuntimeConfig
    from ..integration.ott_federation_provider import OttFederationProvider
    from ..ports.async_executor import AsyncExecutor


class SnapshotCatalogService:
    def __init__(
        self,
        federation: "OttFederationProvider",
        store: EntrySnapshotStore,
        runtime_config: "RuntimeConfig | None",
        async_executor: "AsyncExecutor | None" = None,
        max_per_source: int = 5,
    ) -> None:
        self._federation = federation
        self._store = store
        self._runtime_config = runtime_config
        self._async_executor = async_executor
        self._max_per_source = max_per_source

    # ------------------------------------------------------------------
    # 策略解析（用户覆盖 > 推断）
    # ------------------------------------------------------------------

    def _policy_for(self, entry: dict) -> RefreshPolicy:
        authority = entry.get("_authority", "")
        if self._runtime_config is not None:
            override = self._runtime_config.get_source_refresh_override(authority)
            if isinstance(override, dict):
                return RefreshPolicy.from_dict(override)
        return infer_policy(source_type_of(entry))

    # ------------------------------------------------------------------
    # 列表 / 载入
    # ------------------------------------------------------------------

    def refresh_and_list_all(self) -> list[dict]:
        """物化 → 逐条写快照 → prune → 返回快照（含 freshness 元数据）列表。

        返回**落盘后的快照**（而非原始 federation 条目）——freshness 字段
        （captured_at/refresh_policy/next_refresh_at）只存在于快照内。
        """
        entries = self._federation.list_all_entries() or []
        now = time.time()
        for e in entries:
            if not isinstance(e, dict):
                continue
            e.setdefault("_authority", e.get("authority", ""))
            policy = self._policy_for(e)
            self._store.save(e, captured_at=now, policy=policy)
            self._store.prune(e.get("_authority", ""), self._max_per_source)
        result: list[dict] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            snap = self._store.get(e.get("_authority", ""), e.get("entry_id", ""))
            if snap is not None:
                result.append(self._decorate(snap, now))
        return result

    def load_entry(self, authority: str, entry_id: str) -> dict | None:
        """快照命中直接返回（不重抽）；miss → federation.get_entry 兜底。"""
        snap = self._store.get(authority, entry_id)
        if snap is not None:
            return snap
        return self._federation.get_entry(authority, entry_id)

    def refresh_source(self, authority: str, now: float | None = None) -> None:
        """单源强制刷新（random 换新）：重新物化该 authority 全部条目并落盘。"""
        now = now if now is not None else time.time()
        for e in self._federation.list_all_entries() or []:
            if not isinstance(e, dict):
                continue
            if e.get("_authority") != authority:
                continue
            policy = self._policy_for(e)
            self._store.save(e, captured_at=now, policy=policy)
            self._store.prune(authority, self._max_per_source)

    # ------------------------------------------------------------------
    # 调度
    # ------------------------------------------------------------------

    def scheduled_tick(self, now: float | None = None) -> None:
        """扫描 interval 到期源，后台刷新（async_executor 不可用时同步）。"""
        now = now if now is not None else time.time()
        due = self._store.due_for_refresh(now)
        for authority, _entry_id in due:
            if self._async_executor is not None:
                self._async_executor.submit(
                    lambda a=authority: self.refresh_source(a, now=now)
                )
            else:
                self.refresh_source(authority, now=now)

    # ------------------------------------------------------------------
    # freshness 装饰
    # ------------------------------------------------------------------

    @staticmethod
    def _decorate(entry: dict, now: float) -> dict:
        decorated = dict(entry)
        policy = RefreshPolicy.from_dict(entry.get("refresh_policy"))
        captured = entry.get("captured_at")
        if isinstance(captured, (int, float)):
            decorated["captured_at"] = captured
            decorated["last_fetched_relative"] = _relative_time(now - captured)
            nra = policy.next_refresh_at(float(captured))
            decorated["next_refresh_at"] = nra
            if policy.mode == MODE_INTERVAL:
                decorated["freshness"] = "fresh" if (nra is not None and nra > now) else "stale"
            elif policy.mode == "on_demand":
                decorated["freshness"] = "on_demand"
            else:
                decorated["freshness"] = "fresh"
        return decorated


def _relative_time(seconds: float) -> str:
    """秒差 → 「刚刚 / N 分钟前 / N 小时前 / N 天前」（UI 展示用，中英双语由 qsTr 在 QML 侧）。"""
    seconds = max(0, seconds)
    if seconds < 60:
        return "刚刚"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} 小时前"
    return f"{int(hours // 24)} 天前"
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_snapshot_catalog_service.py -q`
Expected: PASS

- [ ] **Step 5: ruff + 提交**

Commit:
```bash
git add src/backend/application/services/snapshot_catalog_service.py tests/test_snapshot_catalog_service.py
git commit -m "feat: SnapshotCatalogService 快照优先载入/物化/prune/调度（修复选中失配）"
```

---

### Task 5: RefreshScheduler（integration 层 Qt 调度）

**Files:**
- Create: `src/backend/integration/refresh_scheduler.py`
- Test: `tests/test_refresh_scheduler.py`

**Interfaces:**
- Consumes: Task 4 `SnapshotCatalogService`（`scheduled_tick`）。
- Produces: `class RefreshScheduler`；`__init__(service, interval_ms=60_000, parent=None)`；`start()`；`stop()`；`tick()`（public，供测试直接调用）；Qt 事件循环存在时用 `QTimer`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_refresh_scheduler.py
"""RefreshScheduler：轻量常驻调度（非 Qt 环境降级同步）。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.backend.integration.refresh_scheduler import RefreshScheduler


def test_tick_forwards_to_service() -> None:
    service = MagicMock()
    scheduler = RefreshScheduler(service)
    scheduler.tick()
    service.scheduled_tick.assert_called_once()


def test_start_stop_without_qt_event_loop(tmp_path) -> None:
    # 无 QApplication 环境：start() 不崩溃（内部 QTimer 单次创建容错），stop() 幂等
    service = MagicMock()
    scheduler = RefreshScheduler(service)
    scheduler.start()
    scheduler.stop()
    scheduler.stop()  # 幂等
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_refresh_scheduler.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 最小实现**

```python
# src/backend/integration/refresh_scheduler.py
"""常驻轻量调度：周期扫描 interval 到期快照，后台刷新。

非 Qt 事件循环环境（测试/CLI）start() 容错降级为无操作；tick() 恒可调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logger import log_warning

if TYPE_CHECKING:
    from ..application.services.snapshot_catalog_service import SnapshotCatalogService


class RefreshScheduler:
    def __init__(
        self, service: "SnapshotCatalogService", interval_ms: int = 60_000
    ) -> None:
        self._service = service
        self._interval_ms = max(1000, interval_ms)
        self._timer = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            from PySide6.QtCore import QTimer

            self._timer = QTimer()
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self.tick)
            self._timer.start()
        except Exception as e:
            # 无 Qt 事件循环：降级为手动 tick（不崩溃）
            log_warning(f"[RefreshScheduler] Qt 定时器不可用，降级手动刷新: {e}")
            self._timer = None

    def stop(self) -> None:
        self._running = False
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
        except Exception:
            self._timer = None

    def tick(self) -> None:
        """单次到期扫描（测试/手动/定时器共用入口）。"""
        try:
            self._service.scheduled_tick()
        except Exception as e:
            log_warning(f"[RefreshScheduler] tick 失败: {e}")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_refresh_scheduler.py -q`
Expected: PASS

- [ ] **Step 5: ruff + 提交**

Commit:
```bash
git add src/backend/integration/refresh_scheduler.py tests/test_refresh_scheduler.py
git commit -m "feat: RefreshScheduler 常驻轻量到期调度（Qt 降级容错）"
```

---

### Task 6: RegistryAdapter + Bridge 接入 SnapshotCatalogService

**Files:**
- Modify: `src/backend/config/container.py`（装配）
- Modify: `src/backend/presentation/adapters/registry_adapter.py`（loadAllEntries → service；新增 refreshSource slot）
- Modify: `src/backend/presentation/bridge.py`（loadFederatedInlineEntry → service.load_entry；新增 refreshFederatedSource slot；`_registry_adapter` 暴露）
- Test: `tests/test_container_adapters.py`（适配器装配 smoke）

**Interfaces:**
- Consumes: Task 3 `EntrySnapshotStore`、Task 4 `SnapshotCatalogService`、Task 5 `RefreshScheduler`。
- Produces: `RegistryAdapter.loadAllEntries()` 内部改走 `self._catalog.refresh_and_list_all()`；`RegistryAdapter.refreshSource(authority)` slot；`RegistryAdapter.catalog` 只读属性；`Bridge.refreshFederatedSource(authority)` slot；`Bridge.loadFederatedInlineEntry` 走 `catalog.load_entry`。

- [ ] **Step 1: container 装配**（`container.py`）

在 `registry_adapter` 构造（约 433 行）前新增：

```python
    # 动态源快照目录：物化落盘 + 快照优先载入 + 用户 per-source 覆盖 + 常驻调度
    snapshot_store = EntrySnapshotStore(
        cache_dir=registry_cache_dir(), max_per_source=5
    )
    snapshot_service = SnapshotCatalogService(
        federation=federation,
        store=snapshot_store,
        runtime_config=runtime_config,
        async_executor=manifest_async_executor,
    )
    refresh_scheduler = RefreshScheduler(snapshot_service)
    refresh_scheduler.start()
```

并将 `registry_adapter` 构造改为传入 `catalog=snapshot_service`：

```python
    registry_adapter = RegistryAdapter(
        federation=providers.federation,
        manifest_cache=providers.manifest_cache,
        runtime_config=runtime_config,
        catalog=snapshot_service,
    )
```

顶部 import 区（现有 `from ...integration.ott_repo_manifest import RepoManifestCache` 附近）新增：

```python
from ...application.services.snapshot_catalog_service import SnapshotCatalogService
from ...integration.entry_snapshot_store import EntrySnapshotStore
from ...integration.refresh_scheduler import RefreshScheduler
```

注意：`RefreshScheduler` 实例生命周期跟随 container（应用级单例），`start()` 在无 Qt 事件循环的 CLI/测试环境自动降级（Task 5 已容错）。

- [ ] **Step 2: 写失败测试**（追加 `tests/test_container_adapters.py`）

```python
def test_registry_adapter_wired_with_catalog():
    from src.backend.config.container import build_container
    container = build_container()
    registry = container.registry_adapter if hasattr(container, "registry_adapter") else None
    if registry is None:
        # 依 container 实际命名（providers.registry）
        providers = getattr(container, "providers", None)
        registry = getattr(providers, "registry", None)
    assert registry is not None
    assert hasattr(registry, "catalog")
    assert hasattr(registry, "refreshSource")
```

- [ ] **Step 3: 实现（registry_adapter.py）**

- `__init__` 增加 `catalog: SnapshotCatalogService`（关键字参数，向后兼容默认 None）：

```python
    def __init__(
        self,
        federation: "OttFederationProvider",
        manifest_cache: "RepoManifestCache",
        runtime_config: "RuntimeConfig | None" = None,
        catalog: "SnapshotCatalogService | None" = None,
    ) -> None:
        ...
        self._catalog = catalog
```

- `loadAllEntries` 的 `_load` 改为：

```python
        def _load() -> list[dict]:
            if self._catalog is not None:
                return self._catalog.refresh_and_list_all()
            return self._federation.list_all_entries()
```

- 新增 slot + 只读属性：

```python
    @Slot(str)
    def refreshSource(self, authority: str) -> None:
        """单源强制刷新（random 换新）并重发条目列表。"""
        if not authority:
            return
        if self._catalog is None:
            # 无 catalog（未装配）：退化为普通全量加载
            self._set_entries_loading(True)

            def _plain() -> list[dict]:
                return self._federation.list_all_entries()

            from ...workers.base_worker import BaseWorker
            worker = BaseWorker(task=_plain, error_prefix="刷新文本源失败")
            worker.signals.succeeded.connect(self._on_entries_loaded)
            worker.signals.failed.connect(self._on_entries_load_failed)
            self._thread_pool.start(worker)
            return
        self._set_entries_loading(True)

        def _refresh() -> list[dict]:
            self._catalog.refresh_source(authority)
            return self._catalog.refresh_and_list_all()

        from ...workers.base_worker import BaseWorker
        worker = BaseWorker(task=_refresh, error_prefix="刷新文本源失败")
        worker.signals.succeeded.connect(self._on_entries_loaded)
        worker.signals.failed.connect(self._on_entries_load_failed)
        self._thread_pool.start(worker)

    @property
    def catalog(self) -> "SnapshotCatalogService | None":
        return self._catalog
```

- [ ] **Step 4: bridge 接入**

`bridge.py` 中 `loadFederatedInlineEntry` 的 `_load` 改为：

```python
        def _load() -> dict | None:
            if self._registry_adapter is not None and self._registry_adapter.catalog is not None:
                return self._registry_adapter.catalog.load_entry(authority, entryId)
            return federation.get_entry(authority, entryId)
```

新增 slot（放在 `loadFederatedEntries` 附近）：

```python
    @Slot(str)
    def refreshFederatedSource(self, authority: str) -> None:
        """单源强制刷新（random 换新）：物化该源并重发条目列表。"""
        if self._registry_adapter:
            self._registry_adapter.refreshSource(authority)
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest tests/test_container_adapters.py tests/test_ott_bridge_federation.py -q`
Expected: PASS

- [ ] **Step 6: ruff + 提交**

Commit:
```bash
git add src/backend/config/container.py src/backend/presentation/adapters/registry_adapter.py src/backend/presentation/bridge.py tests/test_container_adapters.py
git commit -m "feat: 接入 SnapshotCatalogService（bridge 快照优先载入 + 单源刷新 slot）"
```

---

### Task 7: QML 新鲜度表现（RepoEntriesPanel 卡片）

**Files:**
- Modify: `src/qml/components/RepoEntriesPanel.qml`
- Modify: `src/qml/helpers/TextSourceBehaviors.js`
- Test: `tests/test_qml_pages.py`（若有 QML 加载测试追加）

**Interfaces:**
- Consumes: Task 4 `_decorate` 输出的字段：`freshness`（`"fresh" | "stale" | "on_demand"`）、`last_fetched_relative`、`next_refresh_at`。
- Produces: 卡片右侧新鲜度徽章 + 相对时间副标题 + 单卡片刷新按钮（emit `refreshSourceRequested(authority)`）。

- [ ] **Step 1: JS helper**（追加到 `TextSourceBehaviors.js`）

```javascript
// 相对时间（秒）→ 展示文案（与后端 _relative_time 对应）
function relativeAge(sec) {
    if (typeof sec !== "number" || isNaN(sec)) return ""
    var s = Math.max(0, Math.floor(sec))
    if (s < 60) return qsTr("刚刚")
    var m = Math.floor(s / 60)
    if (m < 60) return qsTr("%1 分钟前").arg(m)
    var h = Math.floor(m / 60)
    if (h < 24) return qsTr("%1 小时前").arg(h)
    return qsTr("%1 天前").arg(Math.floor(h / 24))
}
```

- [ ] **Step 2: 卡片增强**（`RepoEntriesPanel.qml`）

- 新增信号：`signal refreshSourceRequested(string authority)`（组件顶部，靠近 `refreshRequested`）。
- 卡片（`ListView` delegate）右侧追加：

```qml
// 新鲜度徽章（后端 _decorate 输出 freshness）
Rectangle {
    Layout.preferredWidth: 8
    Layout.preferredHeight: 8
    radius: 4
    color: model.entry.freshness === "on_demand" ? Theme.currentTheme.colors.systemCriticalColor
         : model.entry.freshness === "stale" ? Theme.currentTheme.colors.warningColor
         : Theme.currentTheme.colors.primaryColor
    ToolTip.visible: hovered
    ToolTip.text: model.entry.freshness === "on_demand" ? qsTr("每次随机，可抽新")
                : model.entry.freshness === "stale" ? qsTr("已过期，可刷新")
                : qsTr("最新")
}

ToolButton {
    Layout.preferredWidth: 24
    Layout.preferredHeight: 24
    icon.name: "ic_fluent_arrow_sync_20_regular"
    flat: true
    visible: model.entry.freshness !== "fresh"
    enabled: !root.loading
    onClicked: root.refreshSourceRequested(model.entry.authority || model.entry._authority || "")
    ToolTip { text: qsTr("刷新该源"); visible: parent.hovered }
}
```

- 副标题在字数后追加相对时间（复用 JS helper）：

```qml
// 在原 subtitle 拼接处（_syncEntries 或 delegate 展示）追加：
+ (e.last_fetched_relative ? " · " + e.last_fetched_relative : "")
```

- [ ] **Step 3: 手动验证（QML 语法）**

Run: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software uv run python -c "import sys; sys.path.insert(0,'.'); from src.backend.config.app_paths import app_qml_dir; print(app_qml_dir())"`
（存在 QML 加载测试则运行 `uv run pytest tests/test_qml_pages.py -q`。）

- [ ] **Step 4: 提交**

```bash
git add src/qml/components/RepoEntriesPanel.qml src/qml/helpers/TextSourceBehaviors.js
git commit -m "feat: RepoEntriesPanel 新鲜度徽章/相对时间/单源刷新"
```

---

### Task 8: ReposManagementPage 刷新间隔设置（用户 per-source 覆盖 UI）

**Files:**
- Modify: `src/qml/pages/ReposManagementPage.qml`
- Modify: `src/qml/pages/ReposManagementPanel.qml`（若存在来源列表区域，否则在 ReposManagementPage 内实现）
- Test: `tests/test_qml_pages.py`

**Interfaces:**
- Consumes: Task 2 `RuntimeConfig.set_source_refresh_override`（经 Bridge slot 暴露）。
- Produces: Bridge slot `setSourceRefreshOverride(authority, mode, intervalSeconds)`、`clearSourceRefreshOverride(authority)`、`getSourceRefreshOverrides()`；QML 下拉（手动/随机、每小时、每天、每周、每月、不刷新、自定义秒数）。

- [ ] **Step 1: bridge slots**（`bridge.py`，新增 3 个 slot）

```python
    @Slot(str, str, int)
    def setSourceRefreshOverride(self, authority: str, mode: str, interval_seconds: int) -> None:
        """用户 per-source 刷新间隔覆盖。"""
        if self._registry_adapter is None or self._registry_adapter.catalog is None:
            return
        rc = getattr(self._registry_adapter, "_runtime_config", None)
        if rc is not None:
            rc.set_source_refresh_override(authority, mode, interval_seconds)

    @Slot(str)
    def clearSourceRefreshOverride(self, authority: str) -> None:
        if self._registry_adapter is None or self._registry_adapter.catalog is None:
            return
        rc = getattr(self._registry_adapter, "_runtime_config", None)
        if rc is not None:
            rc.clear_source_refresh_override(authority)

    @Slot(result="QVariantMap")
    def getSourceRefreshOverrides(self) -> dict:
        if self._registry_adapter is None or self._registry_adapter.catalog is None:
            return {}
        rc = getattr(self._registry_adapter, "_runtime_config", None)
        return dict(rc.source_refresh_overrides.overrides) if rc is not None else {}
```

- [ ] **Step 2: QML 下拉**（`ReposManagementPage.qml` 订阅摘要的源列表行，追加刷新间隔设置）

```qml
// 每个源行（authority）追加：
QQC.ComboBox {
    Layout.preferredWidth: 120
    model: [qsTr("默认"), qsTr("随机/手动"), qsTr("每小时"), qsTr("每天"), qsTr("每周"), qsTr("每月"), qsTr("不刷新")]
    currentIndex: root._intervalIndexFor(authority)
    onActivated: function(index) {
        var map = {0: "", 1: "on_demand", 2: "interval:3600", 3: "interval:86400",
                   4: "interval:604800", 5: "interval:2592000", 6: "static"}
        var v = map[index]
        if (v === "") appBridge.clearSourceRefreshOverride(authority)
        else if (v.indexOf("interval:") === 0) appBridge.setSourceRefreshOverride(authority, "interval", parseInt(v.split(":")[1]))
        else appBridge.setSourceRefreshOverride(authority, v, 0)
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add src/qml/pages/ReposManagementPage.qml src/backend/presentation/bridge.py
git commit -m "feat: 订阅管理页 per-source 刷新间隔设置（用户覆盖）"
```

---

### Task 9: 回归 + 文档收口

**Files:**
- Modify: `docs/ARCHITECTURE.md`（新增「动态源快照目录」节，注明组件与布局）
- Modify: `AGENTS.md`（§8 新增陷阱：「动态源快照必须物化落盘，载入不得重抽」）
- Modify: `CHANGELOG.md`（追加条目）
- Test: 全量

- [ ] **Step 1: 全量回归**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS（含新增 ~30 用例）

- [ ] **Step 2: 文档**

`docs/ARCHITECTURE.md` 新增：

```markdown
### 动态源快照目录（Content Snapshot + Freshness）

- `EntrySnapshotStore`（integration）：`registry_cache_dir()/snapshots/{authority_hash}/{entry_id}.json`，列表物化内容落盘，原子写，保留最近 N 条
- `RefreshPolicy`：static / interval / on_demand 三模式；用户覆盖（`config.source_refresh_overrides`）> manifest 声明（未来）> 推断（instance→static、rule/script/bridge→on_demand）
- `SnapshotCatalogService`（application）：物化→写快照→prune；`load_entry` 快照优先（不重抽）；`scheduled_tick` 仅刷新 interval 到期源
- `RefreshScheduler`：QTimer 60s tick，Qt 环境可用，非 Qt 降级手动
```

`AGENTS.md` §8 新增：

```markdown
### ⚠️ 动态源条目必须物化落盘，选中载入不得重新执行规则/脚本

**问题**：rule/script 源每次执行返回随机内容，`get_entry(authority, entry_id)` 重抽会与列表 entry_id 失配（实测 `get_entry('2b96d8...') → None`）。

**正确做法**：联邦列表物化结果写 `EntrySnapshotStore`（磁盘快照），`load_entry` 快照命中直接返回；刷新只是换新（保留最近 N 条）。on_demand 源（每次随机）不得进入自动调度（防无限刷新循环），仅手动「抽新」。新增刷新策略 → 扩展 `RefreshPolicy` 模式；用户 per-source 覆盖走 `RuntimeConfig.set_source_refresh_override`。

**历史**：2026-08-13 设计（docs/designs/dynamic-source-snapshot-freshness.md）与实现。
```

`CHANGELOG.md` 追加：

```markdown
- **开源文库动态源快照机制**：联邦条目物化落盘（EntrySnapshotStore），选中载入从快照取（修复随机源选中失配）；RepoEntriesPanel 卡片新增新鲜度徽章/相对时间/单源刷新；订阅管理页支持 per-source 刷新间隔设置（用户覆盖 source_refresh_overrides）；常驻 RefreshScheduler 只自动刷新 interval 到期源
```

- [ ] **Step 3: 提交**

```bash
git add docs/ARCHITECTURE.md AGENTS.md CHANGELOG.md
git commit -m "docs: 动态源快照机制架构/陷阱/CHANGELOG 收口"
```
