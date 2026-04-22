"""打字会话状态机 — 集中管理会话级别状态和成绩提交资格推导。

职责：
- 持有会话阶段（SessionPhase）、来源模式（SourceMode）、上传资格（UploadStatus）
- 通过显式转换方法管理状态流转
- 自动推导成绩提交资格（can_submit_score / get_eligibility_reason）

不负责：
- 网络请求（text_id 回查由 TextAdapter 协调）
- Qt 信号（由 TypingAdapter 桥接）
- 打字统计逻辑（由 TypingService 负责）
- 切片数据和切片加载逻辑（由 Bridge 管理）
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class SessionPhase(Enum):
    IDLE = auto()
    READY = auto()
    TYPING = auto()
    COMPLETED = auto()
    CLOSED = auto()


class SourceMode(Enum):
    NETWORK = auto()
    LOCAL = auto()
    CUSTOM = auto()
    CLIPBOARD = auto()
    SLICE = auto()
    SHUFFLE = auto()


class UploadStatus(Enum):
    CONFIRMED = auto()
    PENDING = auto()
    INELIGIBLE = auto()
    NA = auto()


class TypingSessionContext:
    """打字会话状态机。"""

    def __init__(self) -> None:
        self._phase: SessionPhase = SessionPhase.IDLE
        self._source_mode: SourceMode | None = None
        self._upload_status: UploadStatus = UploadStatus.NA
        self._text_id: int | None = None
        self._text_id_resolved: bool = True  # True = 已确定（有值或已查询失败）
        self._slice_index: int = 0
        self._slice_total: int = 0

        self._on_upload_status_changed: list[Callable[[UploadStatus], None]] = []
        self._on_eligibility_reason_changed: list[Callable[[str], None]] = []

    # === 查询接口 ===

    @property
    def phase(self) -> SessionPhase:
        return self._phase

    @property
    def source_mode(self) -> SourceMode | None:
        return self._source_mode

    @property
    def upload_status(self) -> UploadStatus:
        return self._upload_status

    @property
    def text_id(self) -> int | None:
        return self._text_id

    @property
    def slice_index(self) -> int:
        return self._slice_index

    @property
    def slice_total(self) -> int:
        return self._slice_total

    def can_submit_score(self) -> bool:
        return self._upload_status == UploadStatus.CONFIRMED

    def get_eligibility_reason(self) -> str:
        if self._source_mode in (SourceMode.SLICE, SourceMode.SHUFFLE):
            return "分片/乱序模式，成绩不提交排行榜"
        if self._source_mode == SourceMode.CLIPBOARD:
            return "剪贴板文本，成绩不提交排行榜"
        if self._upload_status == UploadStatus.CONFIRMED:
            return "成绩将提交排行榜"
        if self._upload_status == UploadStatus.PENDING:
            return "正在确认成绩提交资格..."
        return "成绩不提交排行榜"

    # === 设置接口 ===

    def setup_network_session(self, text_id: int, source_key: str) -> None:
        self._source_mode = SourceMode.NETWORK
        self._text_id = text_id
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_local_session(
        self, source_key: str, text_id: int | None = None
    ) -> None:
        self._source_mode = SourceMode.LOCAL
        self._text_id = text_id
        self._text_id_resolved = text_id is not None
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_custom_session(self, source_key: str) -> None:
        self._source_mode = SourceMode.CUSTOM
        self._text_id = None
        self._text_id_resolved = False
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_clipboard_session(self) -> None:
        self._source_mode = SourceMode.CLIPBOARD
        self._text_id = None
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_slice_session(self, total: int) -> None:
        self._source_mode = SourceMode.SLICE
        self._text_id = None
        self._slice_index = 1
        self._slice_total = total
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_shuffle_session(self) -> None:
        self._source_mode = SourceMode.SHUFFLE
        self._text_id = None
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    # === 阶段转换 ===

    def start_typing(self) -> None:
        if self._phase == SessionPhase.READY:
            self._phase = SessionPhase.TYPING

    def complete_typing(self) -> None:
        if self._phase == SessionPhase.TYPING:
            self._phase = SessionPhase.COMPLETED
            self._derive_upload_status()

    def reset(self) -> None:
        self._phase = SessionPhase.IDLE
        self._source_mode = None
        self._upload_status = UploadStatus.NA
        self._text_id = None
        self._text_id_resolved = True
        self._slice_index = 0
        self._slice_total = 0

    # === 回调 ===

    def set_text_id(self, text_id: int | None) -> None:
        self._text_id = text_id
        self._text_id_resolved = True
        self._derive_upload_status()

    def advance_slice(self) -> None:
        if self._source_mode == SourceMode.SLICE and self._slice_index < self._slice_total:
            self._slice_index += 1
            self._phase = SessionPhase.READY

    # === 订阅 ===

    def subscribe_upload_status(
        self, callback: Callable[[UploadStatus], None]
    ) -> None:
        self._on_upload_status_changed.append(callback)

    def subscribe_eligibility_reason(
        self, callback: Callable[[str], None]
    ) -> None:
        self._on_eligibility_reason_changed.append(callback)

    # === 内部 ===

    def _derive_upload_status(self) -> None:
        new_status = self._compute_upload_status()
        if new_status != self._upload_status:
            self._upload_status = new_status
            self._notify_upload_status()
            self._notify_eligibility_reason()

    def _compute_upload_status(self) -> UploadStatus:
        if self._source_mode in (
            SourceMode.SLICE,
            SourceMode.SHUFFLE,
            SourceMode.CLIPBOARD,
        ):
            return UploadStatus.NA

        if self._text_id is not None and self._text_id > 0:
            return UploadStatus.CONFIRMED

        if self._text_id_resolved:
            return UploadStatus.INELIGIBLE

        if self._source_mode in (SourceMode.LOCAL, SourceMode.CUSTOM):
            return UploadStatus.PENDING

        return UploadStatus.INELIGIBLE

    def _notify_upload_status(self) -> None:
        for cb in self._on_upload_status_changed:
            cb(self._upload_status)

    def _notify_eligibility_reason(self) -> None:
        for cb in self._on_eligibility_reason_changed:
            cb(self.get_eligibility_reason())
