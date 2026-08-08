"""成绩提交 Worker - 异步队列 + 指数退避重试。

为什么需要这个组件：
- 成绩提交是 I/O 密集型操作，阻塞 UI 线程会导致卡顿
- 网络请求可能失败，需要可靠的重试机制
- 内存队列提供快速响应，SQLite 持久化保证不丢失

💡 异步编程模式：
- 生产者-消费者模式：TypingAdapter（生产者）→ Queue → Worker（消费者）
- 内存队列提供低延迟，SQLite 作为故障恢复的持久化层
- 指数退避避免在服务端故障时产生请求风暴

🎓 指数退避（Exponential Backoff）：
- 每次重试间隔翻倍：1s → 2s → 4s → 8s → 16s
- 加入随机抖动（jitter）避免多客户端同时重试导致"惊群效应"
- 最大间隔限制在 60s，避免等待时间过长

🎓 为什么不用 asyncio：
- PySide6 的 QThreadPool + QRunnable 是 Qt 原生的线程池方案
- 与 Qt 事件循环集成更好，不需要 qasync 桥接
- 成绩提交是简单的 HTTP 请求，不需要协程的复杂性
"""

import queue
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..models.entity.session_stat import SessionStat
from ..utils.logger import log_info, log_warning


@dataclass
class SubmitTask:
    """提交任务。"""

    score_data: SessionStat
    text_id: int
    created_at: float = field(default_factory=time.monotonic)
    retry_count: int = 0
    # 💡 持久化记录 ID：用于 SQLite 中 mark_sent/mark_failed
    # None 表示该任务来自内存队列（尚未持久化）
    store_record_id: int | None = None

    @property
    def payload(self) -> dict[str, Any]:
        """构建请求体（与 ApiClientScoreSubmitter._build_payload 一致）。"""
        return {
            "textId": self.text_id,
            "charCount": self.score_data.char_count,
            "wrongCharCount": self.score_data.wrong_char_count,
            "backspaceCount": self.score_data.backspace_count,
            "correctionCount": self.score_data.correction_count,
            "keyStrokeCount": int(self.score_data.key_stroke_count),
            "time": round(self.score_data.time, 2),
        }


class ScoreSubmitQueue:
    """成绩提交异步队列。

    核心职责：
    - 接收提交请求，放入内存队列
    - 后台线程从队列取任务并执行 HTTP POST
    - 失败时指数退避重试
    - 超过最大重试次数后持久化到 SQLite

    用法：
        queue = ScoreSubmitQueue(
            submit_fn=api_client_score_submitter._do_submit,
            retry_store=score_retry_store,
        )
        queue.start()

        # 异步提交（非阻塞）
        queue.enqueue(score_data, text_id)

        # 关闭时等待队列清空
        queue.stop()
    """

    # 💡 设计决策：队列大小限制
    # 桌面应用场景下，用户不太可能连续提交超过 100 条成绩
    # 限制队列大小可以防止内存泄漏
    MAX_QUEUE_SIZE = 100

    # 指数退避参数
    INITIAL_BACKOFF = 1.0  # 初始退避时间（秒）
    MAX_BACKOFF = 60.0  # 最大退避时间（秒）
    BACKOFF_MULTIPLIER = 2.0  # 退避倍数
    JITTER_RANGE = 0.5  # 抖动范围（0~1）
    MAX_RETRIES = 5  # 最大重试次数

    def __init__(
        self,
        submit_fn: Callable[[dict[str, Any]], bool],
        retry_store: Any | None = None,
    ):
        """
        Args:
            submit_fn: 实际的提交函数，接收 payload dict，返回是否成功
            retry_store: SQLite 持久化存储（可选）
        """
        self._submit_fn = submit_fn
        self._retry_store = retry_store
        self._queue: queue.Queue[SubmitTask] = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._running = False
        self._worker_thread: threading.Thread | None = None
        self._stats = {"submitted": 0, "failed": 0, "retried": 0}

    def start(self) -> None:
        """启动后台工作线程。"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="ScoreSubmitWorker",
            daemon=True,  # 🎓 daemon 线程在主进程退出时自动终止
        )
        self._worker_thread.start()
        log_info("[ScoreSubmitQueue] 后台工作线程已启动")

        # 启动时加载 SQLite 中的待处理记录
        self._load_from_retry_store()

    def stop(self, timeout: float = 5.0) -> None:
        """停止工作线程，等待队列清空。"""
        self._running = False
        # 💡 入队一个哨兵，立即唤醒阻塞在 queue.get() 的线程，
        # 避免关闭时平均等待 ~0.5s（原 get(timeout=1.0) 的均值）
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        log_info(
            f"[ScoreSubmitQueue] 已停止，统计: "
            f"submitted={self._stats['submitted']} "
            f"failed={self._stats['failed']} "
            f"retried={self._stats['retried']}"
        )

    def enqueue(self, score_data: SessionStat, text_id: int) -> bool:
        """异步提交成绩（非阻塞）。

        Args:
            score_data: 会话统计数据
            text_id: 服务端文本 ID

        Returns:
            True 如果成功入队，False 如果队列已满
        """
        task = SubmitTask(score_data=score_data, text_id=text_id)
        try:
            self._queue.put_nowait(task)
            log_info(
                f"[ScoreSubmitQueue] 成绩入队: textId={text_id} "
                f"queue_size={self._queue.qsize()}"
            )
            return True
        except queue.Full:
            # ⚠️ 队列满了，直接持久化到 SQLite
            log_warning(
                f"[ScoreSubmitQueue] 队列已满，持久化到 SQLite: textId={text_id}"
            )
            self._persist_to_retry_store(task)
            return False

    def _worker_loop(self) -> None:
        """后台工作线程主循环。

        🎓 这是典型的生产者-消费者模式：
        - 生产者：enqueue() 方法（主线程调用）
        - 消费者：这个循环（后台线程执行）
        - 缓冲区：self._queue（线程安全队列）
        """
        while self._running:
            try:
                # 🎓 get() 会阻塞直到有数据或超时
                # 超时是为了定期检查 self._running 标志
                # stop() 会推入一个 None 哨兵立即唤醒此处
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # 💡 哨兵：stop() 推入的 None，检测到后立即结束循环
            if task is None:
                self._queue.task_done()
                continue

            # 计算退避时间（如果需要重试）
            if task.retry_count > 0:
                backoff = self._calculate_backoff(task.retry_count)
                log_info(
                    f"[ScoreSubmitQueue] 重试等待: textId={task.text_id} "
                    f"retry={task.retry_count} backoff={backoff:.1f}s"
                )
                # 💡 分段 sleep 以便快速响应停止信号
                self._interruptible_sleep(backoff)

            # 执行提交
            success = self._try_submit(task)

            if success:
                self._stats["submitted"] += 1
                # 如果之前持久化过，标记为已发送
                self._mark_sent_in_store(task)
            elif task.retry_count < self.MAX_RETRIES:
                # 可以重试，放回队列
                task.retry_count += 1
                self._stats["retried"] += 1
                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    # 队列满，持久化到 SQLite
                    self._persist_to_retry_store(task)
            else:
                # ⚠️ 超过最大重试次数，持久化到 SQLite
                self._stats["failed"] += 1
                log_warning(
                    f"[ScoreSubmitQueue] 超过最大重试次数: textId={task.text_id} "
                    f"retry={task.retry_count}"
                )
                self._persist_to_retry_store(task)

            self._queue.task_done()

    def _try_submit(self, task: SubmitTask) -> bool:
        """尝试提交成绩。"""
        try:
            return self._submit_fn(task.payload)
        except Exception as e:
            log_warning(f"[ScoreSubmitQueue] 提交异常: textId={task.text_id} error={e}")
            return False

    def _calculate_backoff(self, retry_count: int) -> float:
        """计算指数退避时间（带抖动）。

        🎓 指数退避公式：
        backoff = min(initial * multiplier^retry_count, max_backoff)

        🎓 抖动（Jitter）的作用：
        如果多个客户端同时失败，没有抖动的话会同时重试，
        导致服务端瞬间收到大量请求（惊群效应）。
        抖动让重试时间随机化，分散请求。
        """
        # 指数退避
        backoff = min(
            self.INITIAL_BACKOFF * (self.BACKOFF_MULTIPLIER**retry_count),
            self.MAX_BACKOFF,
        )
        # 加入随机抖动
        jitter = backoff * self.JITTER_RANGE * random.random()
        return backoff + jitter

    def _interruptible_sleep(self, duration: float) -> None:
        """可中断的 sleep（响应停止信号）。"""
        end_time = time.monotonic() + duration
        while self._running and time.monotonic() < end_time:
            time.sleep(0.1)

    def _persist_to_retry_store(self, task: SubmitTask) -> None:
        """持久化到 SQLite 重试队列。

        ⚠️ 如果 task 已有 store_record_id（从 SQLite 恢复的任务），
        只更新重试次数，不重复插入。
        """
        if self._retry_store is None:
            log_warning(
                f"[ScoreSubmitQueue] 无 SQLite 存储，成绩丢失: textId={task.text_id}"
            )
            return

        try:
            if task.store_record_id is not None:
                # 已有持久化记录，标记失败并更新重试计数
                # 下次启动时会重新加载
                self._retry_store.mark_failed(task.store_record_id)
            else:
                # 新任务，插入到 SQLite
                record_id = self._retry_store.enqueue(task.payload)
                task.store_record_id = record_id
        except Exception as e:
            log_warning(f"[ScoreSubmitQueue] SQLite 持久化失败: {e}")

    def _mark_sent_in_store(self, task: SubmitTask) -> None:
        """标记 SQLite 中的记录为已发送并删除。

        🎓 只有从 SQLite 恢复的任务才有 store_record_id，
        内存队列中首次提交的任务不会触发此方法。
        """
        if self._retry_store is None or task.store_record_id is None:
            return
        try:
            self._retry_store.mark_sent(task.store_record_id)
        except Exception as e:
            log_warning(f"[ScoreSubmitQueue] SQLite 标记发送失败: {e}")

    def _load_from_retry_store(self) -> None:
        """启动时从 SQLite 加载待处理记录。

        🎓 每条记录携带 store_record_id，
        提交成功后通过该 ID 从 SQLite 删除。
        """
        if self._retry_store is None:
            return

        try:
            pending = self._retry_store.get_pending(limit=self.MAX_QUEUE_SIZE)
            for record in pending:
                # 💡 将 SQLite 记录转换为 SubmitTask
                # 注意：SessionStat 无法从 payload 完整还原，
                # 所以直接使用 payload dict 提交
                task = _PayloadTask(
                    payload=record.payload,
                    text_id=record.text_id,
                    store_record_id=record.id,
                )
                task.retry_count = record.retry_count
                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    break
            if pending:
                log_info(
                    f"[ScoreSubmitQueue] 从 SQLite 加载 {len(pending)} 条待处理记录"
                )
        except Exception as e:
            log_warning(f"[ScoreSubmitQueue] 加载 SQLite 记录失败: {e}")

    @property
    def stats(self) -> dict[str, int]:
        """返回队列统计。"""
        return {**self._stats, "queue_size": self._queue.qsize()}


@dataclass
class _PayloadTask(SubmitTask):
    """从 SQLite 加载的任务（只有 payload，没有完整的 SessionStat）。

    ⚠️ 这是一个妥协：SQLite 中只存了 payload dict，
    无法还原完整的 SessionStat 对象。
    但 submit_fn 只需要 payload，所以可以正常工作。
    """

    _payload: dict[str, Any] = field(default_factory=dict)
    _text_id: int = 0

    def __init__(
        self,
        payload: dict[str, Any],
        text_id: int,
        store_record_id: int | None = None,
    ):
        # ⚠️ 跳过父类 __init__，直接设置字段
        object.__setattr__(self, "_payload", payload)
        object.__setattr__(self, "_text_id", text_id)
        object.__setattr__(self, "score_data", SessionStat())
        object.__setattr__(self, "text_id", text_id)
        object.__setattr__(self, "created_at", time.monotonic())
        object.__setattr__(self, "retry_count", 0)
        object.__setattr__(self, "store_record_id", store_record_id)

    @property
    def payload(self) -> dict[str, Any]:
        return self._payload


class ScoreSubmitWorker:
    """成绩提交 Worker（兼容旧接口）。

    💡 设计决策：
    - 保留这个类以兼容 TypingAdapter 中的旧代码
    - 内部委托给 ScoreSubmitQueue 处理
    - 新代码应该直接使用 ScoreSubmitQueue
    """

    def __init__(
        self,
        score_submitter: Any,
        score_data: SessionStat,
        text_id: int,
    ):
        self._score_submitter = score_submitter
        self._score_data = score_data
        self._text_id = text_id
        # 兼容旧接口：创建一个 signals 对象
        self.signals = _WorkerSignals()

    def run(self) -> None:
        """执行提交（兼容旧接口）。"""
        try:
            result = self._score_submitter.submit(
                self._score_data,
                text_id=self._text_id,
            )
            if result:
                self.signals.succeeded.emit(True)
            else:
                self.signals.failed.emit("提交成绩失败")
        except Exception as e:
            self.signals.failed.emit(f"提交成绩失败：{e}")
        finally:
            self.signals.finished.emit()


class _WorkerSignals:
    """兼容旧接口的信号对象。"""

    class _Signal:
        def __init__(self):
            self._callbacks: list = []

        def connect(self, callback: Any) -> None:
            self._callbacks.append(callback)

        def emit(self, *args: Any) -> None:
            for cb in self._callbacks:
                try:
                    cb(*args)
                except Exception:
                    pass

    def __init__(self):
        self.succeeded = self._Signal()
        self.failed = self._Signal()
        self.finished = self._Signal()
