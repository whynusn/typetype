"""LeaderboardAdapter 文本列表加载的请求 ID 追踪测试。"""

from unittest.mock import MagicMock

from src.backend.presentation.adapters.leaderboard_adapter import LeaderboardAdapter


class DummyThreadPool:
    def __init__(self):
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter() -> tuple[LeaderboardAdapter, MagicMock, DummyThreadPool]:
    leaderboard_gateway = MagicMock()
    runtime_config = MagicMock()
    adapter = LeaderboardAdapter(
        leaderboard_gateway=leaderboard_gateway,
        runtime_config=runtime_config,
    )
    pool = DummyThreadPool()
    adapter._thread_pool = pool
    return adapter, leaderboard_gateway, pool


class TestLoadTextListRequestId:
    """loadTextList 的 request_id 追踪：过期响应应被丢弃。"""

    def test_stale_response_is_discarded(self):
        """连续两次 loadTextList，第一次的响应不应触发 textListLoaded。"""
        adapter, _, pool = _build_adapter()
        emitted: list[list] = []
        adapter.textListLoaded.connect(emitted.append)

        adapter.loadTextList("source_a")
        adapter.loadTextList("source_b")

        assert len(pool.started_workers) == 2
        worker_a, worker_b = pool.started_workers

        # 模拟 worker_a（过期）先返回
        worker_a.signals.succeeded.emit(
            {"source_key": "source_a", "texts": [{"id": 1, "title": "A"}]}
        )
        assert emitted == []  # 过期响应被丢弃

        # 模拟 worker_b（当前）返回
        worker_b.signals.succeeded.emit(
            {"source_key": "source_b", "texts": [{"id": 2, "title": "B"}]}
        )
        assert len(emitted) == 1
        assert emitted[0] == [{"id": 2, "title": "B"}]

    def test_latest_response_wins_with_three_requests(self):
        """三次请求后，只有最后一次的响应被处理。"""
        adapter, _, pool = _build_adapter()
        emitted: list[list] = []
        adapter.textListLoaded.connect(emitted.append)

        adapter.loadTextList("a")
        adapter.loadTextList("b")
        adapter.loadTextList("c")

        assert len(pool.started_workers) == 3

        # 前两次响应都应被丢弃
        pool.started_workers[0].signals.succeeded.emit(
            {"source_key": "a", "texts": [{"id": 1}]}
        )
        pool.started_workers[1].signals.succeeded.emit(
            {"source_key": "b", "texts": [{"id": 2}]}
        )
        assert emitted == []

        # 第三次响应被处理
        pool.started_workers[2].signals.succeeded.emit(
            {"source_key": "c", "texts": [{"id": 3}]}
        )
        assert emitted == [[{"id": 3}]]

    def test_loading_flag_transitions(self):
        """textListLoading 在请求开始时 True，当前响应到达后 False。"""
        adapter, _, pool = _build_adapter()
        states: list[bool] = []
        adapter.textListLoadingChanged.connect(
            lambda: states.append(adapter.text_list_loading)
        )

        adapter.loadTextList("src")
        assert adapter.text_list_loading is True
        assert states == [True]

        pool.started_workers[0].signals.succeeded.emit(
            {"source_key": "src", "texts": []}
        )
        assert adapter.text_list_loading is False
        assert states == [True, False]

    def test_failed_stale_response_is_discarded(self):
        """过期请求的失败响应也不应触发 textListLoadFailed。"""
        adapter, _, pool = _build_adapter()
        failures: list[str] = []
        adapter.textListLoadFailed.connect(failures.append)

        adapter.loadTextList("a")
        adapter.loadTextList("b")

        # 过期请求失败 — 不应触发信号
        pool.started_workers[0].signals.failed.emit("网络错误")
        assert failures == []

        # 当前请求失败 — 应触发信号（BaseWorker 已加 error_prefix）
        pool.started_workers[1].signals.failed.emit("加载文本列表失败：网络错误")
        assert failures == ["加载文本列表失败：网络错误"]
