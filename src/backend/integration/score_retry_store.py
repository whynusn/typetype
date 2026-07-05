"""SQLite 重试队列持久化。

为什么需要这个组件：
- 成绩提交可能因为网络抖动、服务端过载等原因失败
- 内存队列在进程退出后丢失，需要持久化到本地存储
- SQLite 是 Python 内置的，无需额外依赖，适合桌面应用场景

💡 持久化队列设计：
- 使用 SQLite 的 WAL 模式提高并发性能
- 每条记录包含：payload（JSON）、重试次数、最大重试次数、下次重试时间、状态
- 状态流转：pending → sending → sent（确认后删除）
- 发送成功的记录直接删除，不保留历史（节省磁盘空间）

🎓 为什么不用消息队列（如 Redis）：
- 桌面应用的并发量很低，SQLite 完全够用
- 零外部依赖，不需要用户安装额外服务
- SQLite 文件可以随应用数据目录迁移
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logger import log_info, log_warning


@dataclass
class PendingScore:
    """待提交的成绩记录。"""

    id: int
    payload: dict[str, Any]
    retry_count: int
    max_retries: int
    next_retry_at: str | None
    created_at: str

    @property
    def text_id(self) -> int:
        return self.payload.get("textId", 0)


class ScoreRetryStore:
    """基于 SQLite 的成绩重试队列。

    用法：
        store = ScoreRetryStore(db_path="/path/to/retry.db")
        store.init_db()

        # 入队
        store.enqueue({"textId": 1, "speed": 120.5})

        # 获取待处理记录
        pending = store.get_pending(limit=10)

        # 标记发送成功（删除记录）
        store.mark_sent(record_id=1)
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS score_retry_queue (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        payload       TEXT NOT NULL,
        retry_count   INTEGER NOT NULL DEFAULT 0,
        max_retries   INTEGER NOT NULL DEFAULT 5,
        next_retry_at TEXT,
        status        TEXT NOT NULL DEFAULT 'pending',
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    );
    """

    # 🎓 SQLite 索引加速查询：按状态和重试次数排序
    CREATE_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_score_retry_status
    ON score_retry_queue(status, retry_count);
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def init_db(self) -> None:
        """初始化数据库，创建表和索引。"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            # 🎓 WAL 模式：允许读写并发，提高性能
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(self.CREATE_TABLE_SQL)
            conn.execute(self.CREATE_INDEX_SQL)

    def enqueue(self, payload: dict[str, Any], max_retries: int = 5) -> int:
        """将成绩数据入队。

        Args:
            payload: 成绩数据字典（会被 JSON 序列化）
            max_retries: 最大重试次数

        Returns:
            新记录的 ID
        """
        now = datetime.now().isoformat()
        serialized = json.dumps(payload, ensure_ascii=False)

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO score_retry_queue "
                "(payload, max_retries, status, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (serialized, max_retries, now, now),
            )
            record_id = cursor.lastrowid

        log_info(
            f"[ScoreRetryStore] 成绩入队: id={record_id} textId={payload.get('textId', '?')}"
        )
        return record_id  # type: ignore[return-value]

    def get_pending(self, limit: int = 10) -> list[PendingScore]:
        """获取待处理的成绩记录。

        按创建时间排序，优先处理最早入队的记录。
        过滤 next_retry_at：只返回已到达重试时间的记录。

        Args:
            limit: 最多返回的记录数

        Returns:
            待处理记录列表
        """
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, payload, retry_count, max_retries, next_retry_at, created_at "
                "FROM score_retry_queue "
                "WHERE status = 'pending' "
                "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
                "ORDER BY created_at ASC "
                "LIMIT ?",
                (now, limit),
            ).fetchall()

        return [
            PendingScore(
                id=row["id"],
                payload=json.loads(row["payload"]),
                retry_count=row["retry_count"],
                max_retries=row["max_retries"],
                next_retry_at=row["next_retry_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def mark_sending(self, record_id: int) -> None:
        """标记记录为发送中（防止重复发送）。"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE score_retry_queue SET status = 'sending', updated_at = ? WHERE id = ?",
                (now, record_id),
            )

    def mark_sent(self, record_id: int) -> None:
        """标记发送成功并删除记录。

        💡 设计决策：
        - 直接删除而非标记 sent：节省磁盘空间
        - 如果需要审计日志，可以改为 UPDATE status='sent' 并定期清理
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM score_retry_queue WHERE id = ?",
                (record_id,),
            )
        log_info(f"[ScoreRetryStore] 成绩提交成功，已删除: id={record_id}")

    def mark_failed(
        self,
        record_id: int,
        next_retry_at: str | None = None,
    ) -> bool:
        """标记发送失败，增加重试次数。

        Args:
            record_id: 记录 ID
            next_retry_at: 下次重试时间（ISO 格式），由调用方根据指数退避计算

        Returns:
            True 如果还可以重试，False 如果已超过最大重试次数
        """
        now = datetime.now().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT retry_count, max_retries FROM score_retry_queue WHERE id = ?",
                (record_id,),
            ).fetchone()

            if row is None:
                return False

            new_count = row[0] + 1
            max_retries = row[1]
            if new_count >= max_retries:
                # ⚠️ 超过最大重试次数，标记为 dead
                # 这条记录不会再被捞起，但保留在数据库中供排查
                conn.execute(
                    "UPDATE score_retry_queue "
                    "SET status = 'dead', retry_count = ?, updated_at = ? "
                    "WHERE id = ?",
                    (new_count, now, record_id),
                )
                log_warning(
                    f"[ScoreRetryStore] 超过最大重试次数，标记为 dead: id={record_id} retry={new_count}"
                )
                return False

            # 重置为 pending，增加重试计数，设置下次重试时间
            conn.execute(
                "UPDATE score_retry_queue "
                "SET status = 'pending', retry_count = ?, "
                "next_retry_at = ?, updated_at = ? "
                "WHERE id = ?",
                (new_count, next_retry_at, now, record_id),
            )
            return True

    def get_stats(self) -> dict[str, int]:
        """获取队列统计。"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM score_retry_queue GROUP BY status"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def cleanup_dead(self, older_than_days: int = 30) -> int:
        """清理超过指定天数的 dead 记录。

        Args:
            older_than_days: 超过多少天的 dead 记录会被清理

        Returns:
            清理的记录数
        """
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM score_retry_queue "
                "WHERE status = 'dead' "
                "AND created_at < datetime('now', ?)",
                (f"-{older_than_days} days",),
            )
            count = cursor.rowcount
        if count > 0:
            log_info(f"[ScoreRetryStore] 清理 {count} 条 dead 记录")
        return count
