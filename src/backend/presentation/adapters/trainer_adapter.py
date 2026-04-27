from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from ...application.gateways.trainer_gateway import TrainerGateway
from ...application.usecases.load_trainer_segment_usecase import (
    LoadTrainerSegmentUseCase,
)
from ...models.dto.trainer import TrainerCatalogItem, TrainerSegment
from ...workers.trainer_worker import TrainerWorker


class TrainerAdapter(QObject):
    """练单器 Qt 适配层。"""

    trainersLoaded = Signal(list)
    trainersLoadFailed = Signal(str)
    trainerSegmentLoaded = Signal(dict)
    trainerSegmentLoadFailed = Signal(str)
    trainerLoadingChanged = Signal()

    def __init__(
        self,
        gateway: TrainerGateway,
        load_segment_usecase: LoadTrainerSegmentUseCase,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._load_segment_usecase = load_segment_usecase
        self._thread_pool = QThreadPool.globalInstance()
        self._trainer_loading = False
        self._request_generation = 0
        self._active_worker = None

    @property
    def trainer_loading(self) -> bool:
        return self._trainer_loading

    def clear_active(self) -> None:
        """失效当前仍在后台运行的练单器请求。"""
        self._next_request_generation()
        self._active_worker = None
        self._set_loading(False)

    def _set_loading(self, loading: bool) -> None:
        if self._trainer_loading != loading:
            self._trainer_loading = loading
            self.trainerLoadingChanged.emit()

    def _next_request_generation(self) -> int:
        self._request_generation += 1
        return self._request_generation

    @staticmethod
    def _catalog_item_to_dict(item: TrainerCatalogItem) -> dict:
        return {
            "trainerId": item.trainer_id,
            "title": item.title,
            "path": item.path,
            "entryCount": item.entry_count,
            "modifiedTimestamp": item.modified_timestamp,
        }

    @staticmethod
    def _segment_to_dict(segment: TrainerSegment) -> dict:
        return {
            "trainerId": segment.trainer_id,
            "title": segment.title,
            "content": segment.content,
            "items": list(segment.items),
            "index": segment.index,
            "total": segment.total,
            "mode": segment.mode,
            "groupSize": segment.group_size,
        }

    def _list_trainers(self) -> list[dict]:
        return [
            self._catalog_item_to_dict(item) for item in self._gateway.list_trainers()
        ]

    def _load_segment(
        self,
        trainer_id: str,
        segment_index: int,
        group_size: int,
        full_shuffle: bool = False,
    ) -> dict:
        segment = self._load_segment_usecase.load_segment(
            trainer_id,
            segment_index=segment_index,
            group_size=group_size,
            full_shuffle=full_shuffle,
        )
        return self._segment_to_dict(segment)

    def _run_catalog_worker(self) -> None:
        if self._trainer_loading:
            return
        self._set_loading(True)
        request_generation = self._next_request_generation()
        worker = TrainerWorker(
            task=self._list_trainers,
            error_prefix="加载练单器词库列表失败",
        )
        worker.signals.succeeded.connect(
            lambda trainers, gen=request_generation: self._on_trainers_loaded(
                gen,
                trainers,
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=request_generation: self._on_trainers_load_failed(
                gen,
                message,
            )
        )
        worker.signals.finished.connect(
            lambda gen=request_generation: self._on_worker_finished(gen)
        )
        self._active_worker = worker
        self._thread_pool.start(worker)

    def _run_segment_worker(
        self,
        task: Callable[[], dict],
        error_prefix: str,
    ) -> None:
        if self._trainer_loading:
            return
        self._set_loading(True)
        request_generation = self._next_request_generation()
        worker = TrainerWorker(task=task, error_prefix=error_prefix)
        worker.signals.succeeded.connect(
            lambda payload, gen=request_generation: self._on_segment_loaded(
                gen,
                payload,
            )
        )
        worker.signals.failed.connect(
            lambda message, gen=request_generation: self._on_segment_load_failed(
                gen,
                message,
            )
        )
        worker.signals.finished.connect(
            lambda gen=request_generation: self._on_worker_finished(gen)
        )
        self._active_worker = worker
        self._thread_pool.start(worker)

    def _on_trainers_loaded(
        self,
        request_generation: int,
        trainers: list[dict],
    ) -> None:
        if request_generation != self._request_generation:
            return
        self.trainersLoaded.emit(trainers)

    def _on_trainers_load_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._request_generation:
            return
        self.trainersLoadFailed.emit(message)

    def _on_segment_loaded(self, request_generation: int, payload: dict) -> None:
        if request_generation != self._request_generation:
            return
        self.trainerSegmentLoaded.emit(payload)

    def _on_segment_load_failed(self, request_generation: int, message: str) -> None:
        if request_generation != self._request_generation:
            return
        self.trainerSegmentLoadFailed.emit(message)

    def _on_worker_finished(self, request_generation: int) -> None:
        if request_generation != self._request_generation:
            return
        self._active_worker = None
        self._set_loading(False)

    @Slot()
    def loadTrainers(self) -> None:
        self._run_catalog_worker()

    @Slot(str, int, int)
    def loadTrainerSegment(
        self,
        trainer_id: str,
        segment_index: int,
        group_size: int,
        full_shuffle: bool = False,
    ) -> None:
        self._run_segment_worker(
            task=lambda: self._load_segment(
                trainer_id, segment_index, group_size, full_shuffle
            ),
            error_prefix="加载练单器段落失败",
        )

    @Slot()
    def loadCurrentTrainerSegment(self) -> None:
        self._run_segment_worker(
            task=lambda: self._segment_to_dict(
                self._load_segment_usecase.current_segment()
            ),
            error_prefix="加载练单器当前段落失败",
        )

    @Slot()
    def loadNextTrainerSegment(self) -> None:
        self._run_segment_worker(
            task=lambda: self._segment_to_dict(
                self._load_segment_usecase.next_segment()
            ),
            error_prefix="加载练单器下一段失败",
        )

    @Slot()
    def loadPreviousTrainerSegment(self) -> None:
        self._run_segment_worker(
            task=lambda: self._segment_to_dict(
                self._load_segment_usecase.previous_segment()
            ),
            error_prefix="加载练单器上一段失败",
        )

    @Slot()
    def shuffleCurrentTrainerGroup(self) -> None:
        self._run_segment_worker(
            task=lambda: self._segment_to_dict(
                self._load_segment_usecase.shuffle_current_group()
            ),
            error_prefix="练单器当前组乱序失败",
        )
