"""动态源健康状态持久化（per-authority，供开源文库源组头展示）。

与 EntrySnapshotStore 分离：快照是「条目内容」的磁盘事实源，本 store
只记录该源的检查/健康状态（last_checked_at / last_success_at /
last_error / consecutive_failures），供 UI 区分「内容多久前更新」与
「最近一次刷新是否成功」。写失败静默，绝不阻塞刷新主流程。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _authority_hash(authority: str) -> str:
    return hashlib.sha256(authority.encode("utf-8")).hexdigest()[:12]


class SourceStatusStore:
    """per-authority 源健康状态存储（JSON 单文件，原子写）。"""

    def __init__(self, cache_dir: Path) -> None:
        self._root = Path(cache_dir) / "source_status"
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 沙箱/只读环境不可写：状态 store 降级为内存 no-op（主流程不阻塞）
            pass

    def _path(self, authority: str) -> Path:
        return self._root / f"{_authority_hash(authority)}.json"

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def get(self, authority: str) -> dict[str, Any]:
        """读取状态；不存在或损坏 → 缺省状态。"""
        try:
            path = self._path(authority)
            if not path.exists():
                return self._empty_status(authority)
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return self._empty_status(authority)
        if not isinstance(data, dict):
            return self._empty_status(authority)
        data.setdefault("authority", authority)
        return data

    def list_all(self) -> dict[str, dict[str, Any]]:
        """返回全部 authority 状态映射（缺省状态不落盘，由 get 兜底）。"""
        result: dict[str, dict[str, Any]] = {}
        try:
            if not self._root.exists():
                return result
            for path in self._root.glob("*.json"):
                if not path.is_file():
                    continue
                try:
                    with path.open(encoding="utf-8") as f:
                        raw = json.load(f)
                except (OSError, json.JSONDecodeError, ValueError, TypeError):
                    continue
                if not isinstance(raw, dict):
                    continue
                authority = str(raw.get("authority", ""))
                if not authority:
                    continue
                result[authority] = self.get(authority)
        except OSError:
            return result
        return result

    @staticmethod
    def _empty_status(authority: str) -> dict[str, Any]:
        return {
            "authority": authority,
            "state": "unknown",
            "message": "",
            "last_checked_at": None,
            "last_success_at": None,
            "last_error_at": None,
            "last_error": "",
            "consecutive_failures": 0,
            "source_label": "",
            "source_type": "",
            "repo_id": "",
            "repo_name": "",
            "repo_url": "",
            "refresh_policy": None,
        }

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def update(
        self,
        authority: str,
        *,
        state: str,
        message: str = "",
        checked_at: float | None = None,
        source_label: str = "",
        source_type: str = "",
        repo_id: str = "",
        repo_name: str = "",
        repo_url: str = "",
        refresh_policy: dict | None = None,
    ) -> None:
        """按 authority 更新健康状态（成功清零连续失败，失败累加）。"""
        if not authority:
            return
        now = float(checked_at if checked_at is not None else time.time())
        current = self.get(authority)
        failures = int(current.get("consecutive_failures", 0) or 0)
        if state == "ok":
            current.update(
                {
                    "state": "ok",
                    "message": "",
                    "last_checked_at": now,
                    "last_success_at": now,
                    "last_error": "",
                    "consecutive_failures": 0,
                }
            )
        else:
            failures += 1
            current.update(
                {
                    "state": "failed",
                    "message": str(message or "") or "刷新失败",
                    "last_checked_at": now,
                    "last_error_at": now,
                    "last_error": str(message or "") or "刷新失败",
                    "consecutive_failures": failures,
                }
            )
        # 元数据只在调用方显式提供时覆盖（避免失败状态丢失展示名）
        if source_label:
            current["source_label"] = source_label
        if source_type:
            current["source_type"] = source_type
        if repo_id:
            current["repo_id"] = repo_id
        if repo_name:
            current["repo_name"] = repo_name
        if repo_url:
            current["repo_url"] = repo_url
        if refresh_policy is not None:
            current["refresh_policy"] = refresh_policy
        current.setdefault("authority", authority)
        try:
            path = self._path(authority)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f"{path.suffix}.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError:
            pass
