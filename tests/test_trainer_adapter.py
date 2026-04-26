from unittest.mock import MagicMock

from src.backend.models.dto.trainer import TrainerCatalogItem, TrainerSegment
from src.backend.presentation.adapters.trainer_adapter import TrainerAdapter


class DummyThreadPool:
    def __init__(self) -> None:
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter() -> tuple[TrainerAdapter, MagicMock, MagicMock, DummyThreadPool]:
    gateway = MagicMock()
    usecase = MagicMock()
    adapter = TrainerAdapter(gateway=gateway, load_segment_usecase=usecase)
    pool = DummyThreadPool()
    adapter._thread_pool = pool
    return adapter, gateway, usecase, pool


def test_load_trainers_enqueues_worker_and_emits_catalog_payload() -> None:
    adapter, gateway, _, pool = _build_adapter()
    gateway.list_trainers.return_value = [
        TrainerCatalogItem(
            trainer_id="1.前500",
            title="前500",
            path="/tmp/1.前500.txt",
            entry_count=500,
            modified_timestamp=1710000000.0,
        )
    ]
    loaded: list[list[dict]] = []
    states: list[bool] = []
    adapter.trainersLoaded.connect(loaded.append)
    adapter.trainerLoadingChanged.connect(
        lambda: states.append(adapter.trainer_loading)
    )

    adapter.loadTrainers()

    assert len(pool.started_workers) == 1
    assert adapter.trainer_loading is True
    pool.started_workers[0].run()

    assert loaded == [
        [
            {
                "trainerId": "1.前500",
                "title": "前500",
                "path": "/tmp/1.前500.txt",
                "entryCount": 500,
                "modifiedTimestamp": 1710000000.0,
            }
        ]
    ]
    assert adapter.trainer_loading is False
    assert states == [True, False]


def test_load_trainer_segment_enqueues_worker_and_emits_segment_payload() -> None:
    adapter, _, usecase, pool = _build_adapter()
    usecase.load_segment.return_value = TrainerSegment(
        trainer_id="1.前500",
        title="前500",
        content="的一",
        items=("的", "一"),
        index=1,
        total=250,
        mode="fixed",
        group_size=2,
    )
    loaded: list[dict] = []
    adapter.trainerSegmentLoaded.connect(loaded.append)

    adapter.loadTrainerSegment("1.前500", 1, 2)

    assert len(pool.started_workers) == 1
    pool.started_workers[0].run()

    usecase.load_segment.assert_called_once_with(
        "1.前500",
        segment_index=1,
        group_size=2,
    )
    assert loaded == [
        {
            "trainerId": "1.前500",
            "title": "前500",
            "content": "的一",
            "items": ["的", "一"],
            "index": 1,
            "total": 250,
            "mode": "fixed",
            "groupSize": 2,
        }
    ]


def test_next_previous_and_shuffle_emit_segment_payloads() -> None:
    adapter, _, usecase, pool = _build_adapter()
    usecase.next_segment.return_value = TrainerSegment(
        trainer_id="words",
        title="词库",
        content="三四",
        items=("三", "四"),
        index=2,
        total=3,
        mode="fixed",
        group_size=2,
    )
    loaded: list[dict] = []
    adapter.trainerSegmentLoaded.connect(loaded.append)

    adapter.loadNextTrainerSegment()
    pool.started_workers[0].run()

    assert usecase.next_segment.call_count == 1
    assert loaded[-1]["content"] == "三四"


def test_trainer_failures_clear_loading_and_emit_failure_signal() -> None:
    adapter, gateway, _, pool = _build_adapter()
    gateway.list_trainers.side_effect = RuntimeError("boom")
    failures: list[str] = []
    adapter.trainersLoadFailed.connect(failures.append)

    adapter.loadTrainers()
    pool.started_workers[0].run()

    assert adapter.trainer_loading is False
    assert failures == ["加载练单器词库列表失败：boom"]


def test_clear_active_invalidates_pending_segment_worker() -> None:
    adapter, _, usecase, pool = _build_adapter()
    usecase.load_segment.return_value = TrainerSegment(
        trainer_id="words",
        title="词库",
        content="旧段",
        items=("旧", "段"),
        index=1,
        total=2,
        mode="fixed",
        group_size=2,
    )
    loaded: list[dict] = []
    adapter.trainerSegmentLoaded.connect(loaded.append)

    adapter.loadTrainerSegment("words", 1, 2)
    adapter.clear_active()
    pool.started_workers[0].run()

    assert adapter.trainer_loading is False
    assert loaded == []
