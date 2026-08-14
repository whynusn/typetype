"""动态源条目快照磁盘存储（纯存储，无网络）。

布局：registry_cache_dir()/snapshots/{authority_hash}/{entry_id}.json
- 列表展示的物化内容落盘，选中载入直接从快照取（不重新执行规则/脚本）
- 保留最近 N 条（prune），旧快照可回看/可继续打
- on_demand 快照虽立即过期，但不入自动调度（防无限刷新循环）
"""

from __future__ import annotations

import hashlib
import json
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

    def save(
        self,
        entry: dict,
        captured_at: float,
        policy: RefreshPolicy,
        fingerprint: str | None = None,
    ) -> None:
        """写快照；fingerprint 为内容指纹（非 None 时写入 snap_fingerprint）。

        snap_fingerprint 供后台 revalidate 做「内容未变」判定：指纹相同
        则跳过 save 保留原 captured_at（freshness 不被虚刷）。旧快照无该
        字段 → 首次 revalidate 会视为已变并补写指纹（一次性）。
        """
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
        if fingerprint is not None:
            payload["snap_fingerprint"] = fingerprint
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

    def list_all(self) -> list[dict]:
        """遍历所有 authority 目录返回全部快照（按 captured_at 倒序）。

        供「进入开源文库先渲染已存快照」使用：零网络，纯磁盘读。
        """
        items: list[dict] = []
        try:
            if not self._root.exists():
                return []
            for authority_dir in self._root.iterdir():
                if not authority_dir.is_dir():
                    continue
                for path in authority_dir.glob("*.json"):
                    if not path.is_file():
                        continue
                    # authority 从快照内冗余字段反查（哈希目录不可逆推原值）
                    try:
                        with path.open(encoding="utf-8") as f:
                            raw = json.load(f)
                    except (OSError, json.JSONDecodeError, ValueError, TypeError):
                        continue
                    if not isinstance(raw, dict):
                        continue
                    authority = str(raw.get("_authority", ""))
                    if not authority:
                        continue
                    data = self.get(authority, str(raw.get("entry_id", "")))
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

    def prune_stale(
        self, authority: str, live_ids: set[str], max_per_source: int | None = None
    ) -> None:
        """只清理不再活跃的旧快照（保留最近 N 条；live_ids 中的条目永不删除）。"""
        limit = max(1, max_per_source or self._max_per_source)
        stale = [e for e in self.list(authority) if e.get("entry_id") not in live_ids]
        for item in stale[limit:]:
            try:
                self._path(authority, item.get("entry_id", "")).unlink(missing_ok=True)
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
                        due.append(
                            (
                                str(data.get("_authority", "")),
                                str(data.get("entry_id", "")),
                            )
                        )
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

    def clear_authority(self, authority: str) -> None:
        """删除某 authority 的全部快照目录（删除订阅时清理残留）。"""
        import shutil

        try:
            directory = self._dir(authority)
            if directory.exists():
                shutil.rmtree(directory)
        except OSError:
            pass
