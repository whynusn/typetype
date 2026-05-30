"""打字会话状态机 — 集中管理会话级别状态和成绩提交资格推导。

职责：
- 持有会话阶段（SessionPhase）、来源模式（SourceMode）、上传资格（UploadStatus）
- 管理分片载文状态（分片列表、当前片索引、重打条件、成绩快照）
- 通过显式转换方法管理状态流转
- 自动推导成绩提交资格（can_submit_score / get_eligibility_reason）

不负责：
- 网络请求（text_id 回查由 TextAdapter 协调）
- Qt 信号（由 TypingAdapter 桥接）
- 打字统计逻辑（由 TypingService 负责）
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
    WENLAI = auto()
    LOCAL_ARTICLE = auto()
    TRAINER = auto()


class UploadStatus(Enum):
    CONFIRMED = auto()
    PENDING = auto()
    INELIGIBLE = auto()
    NA = auto()


class TypingSessionContext:
    """打字会话状态机。"""

    def __init__(self) -> None:
        # 基础会话状态
        self._phase: SessionPhase = SessionPhase.IDLE
        self._source_mode: SourceMode | None = None
        self._upload_status: UploadStatus = UploadStatus.NA
        self._text_id: int | None = None
        self._text_id_resolved: bool = True
        self._slice_index: int = 0
        self._slice_total: int = 0
        self._slice_size: int = 0
        self._slice_text: str = ""

        # 分片载文状态
        self._slices: list[str] = []
        self._slice_stats: list[dict | None] = []
        self._key_stroke_min: float = 0.0
        self._speed_min: int = 0
        self._accuracy_min: int = 0
        self._pass_count_min: int = 1
        self._on_fail_action: str = "retype"
        self._start_slice: int = 1
        self._slice_pass_counts: list[int] = []
        self._slice_metrics: list[dict] = []  # per-slice 指标（每片独立的达标阈值）
        self._current_slice_content: str = ""  # 当前段文本缓存（所有分片模式统一）

        # 失败自动降指标（每指标独立）
        self._auto_decrease_enabled: bool = False
        self._key_stroke_decrease: float = 0.0
        self._speed_decrease: int = 0
        self._accuracy_decrease: int = 0

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
        if self._source_mode == SourceMode.WENLAI:
            return "晴发文文本，成绩不提交排行榜"
        if self._source_mode == SourceMode.LOCAL_ARTICLE:
            return "本地长文，成绩不提交排行榜"
        if self._source_mode == SourceMode.TRAINER:
            return "练单器，成绩不提交排行榜"
        if self._upload_status == UploadStatus.PENDING:
            return "正在确认成绩提交资格..."
        return "成绩不提交排行榜"

    # === 设置接口 ===

    def setup_network_session(self, text_id: int, source_key: str) -> None:
        self._source_mode = SourceMode.NETWORK
        self._text_id = text_id
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_local_session(self, source_key: str, text_id: int | None = None) -> None:
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

    def setup_shuffle_session(self) -> None:
        self._source_mode = SourceMode.SHUFFLE
        self._text_id = None
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_wenlai_session(self) -> None:
        self._source_mode = SourceMode.WENLAI
        self._text_id = None
        self._text_id_resolved = True
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_local_article_session(self) -> None:
        self._source_mode = SourceMode.LOCAL_ARTICLE
        self._text_id = None
        self._text_id_resolved = True
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_trainer_session(self) -> None:
        self._source_mode = SourceMode.TRAINER
        self._text_id = None
        self._text_id_resolved = True
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    # === 分片载文 ===

    def setup_sourced_slice_mode(
        self,
        slice_index: int,
        slice_total: int,
        slice_size: int = 0,
        on_fail_action: str = "none",
        key_stroke_min: float = 0.0,
        speed_min: int = 0,
        accuracy_min: int = 0,
        pass_count_min: int = 1,
        reset_counts: bool = True,
        auto_decrease_enabled: bool = False,
        key_stroke_decrease: float = 0.0,
        speed_decrease: int = 0,
        accuracy_decrease: int = 0,
    ) -> None:
        """设置基于外部来源的分片模式（不分片文本，由适配器提供分段）。

        用于练单器和本地长文：段落后自动推进下一段。
        合格性校验参数与原分片载文模式完全一致。
        reset_counts=False 时保留现有达标次数（自动推进/重打场景）。
        """
        self._source_mode = SourceMode.SLICE
        self._slice_index = slice_index
        self._slice_total = slice_total

        if reset_counts or len(self._slice_pass_counts) != slice_total:
            # 初始载入：用传入参数设置标量指标，并初始化 per-slice 指标
            self._key_stroke_min = key_stroke_min
            self._speed_min = speed_min
            self._accuracy_min = accuracy_min
            self._pass_count_min = pass_count_min
            self._on_fail_action = on_fail_action
            self._auto_decrease_enabled = auto_decrease_enabled
            self._key_stroke_decrease = key_stroke_decrease
            self._speed_decrease = speed_decrease
            self._accuracy_decrease = accuracy_decrease
            self._slice_pass_counts = [0] * slice_total
            self._slice_stats = []
            self._init_slice_metrics(slice_total)
        else:
            # 非初始载入（推进/重打）：从 per-slice 指标恢复当前片的指标
            self.restore_slice_metrics(slice_index)

        self._slice_text = ""
        self._slice_size = slice_size
        self._text_id = None
        self._text_id_resolved = True
        self._phase = SessionPhase.READY
        self._derive_upload_status()

    def setup_slice_mode(
        self,
        text: str,
        slice_size: int,
        start_slice: int,
        key_stroke_min: float,
        speed_min: int,
        accuracy_min: int,
        pass_count_min: int,
        on_fail_action: str,
        auto_decrease_enabled: bool = False,
        key_stroke_decrease: float = 0.0,
        speed_decrease: int = 0,
        accuracy_decrease: int = 0,
    ) -> int:
        if not text or slice_size <= 0:
            return 0

        self._slice_text = text
        self._slice_size = slice_size
        self._slice_total = (len(text) + slice_size - 1) // slice_size
        # 兼容字段保留（不再提前复制所有分片）
        self._slices = []

        if self._slice_total <= 0:
            return 0

        self._key_stroke_min = key_stroke_min
        self._speed_min = speed_min
        self._accuracy_min = accuracy_min
        self._pass_count_min = pass_count_min
        self._on_fail_action = on_fail_action
        self._auto_decrease_enabled = auto_decrease_enabled
        self._key_stroke_decrease = key_stroke_decrease
        self._speed_decrease = speed_decrease
        self._accuracy_decrease = accuracy_decrease
        self._start_slice = max(1, min(start_slice, self._slice_total))
        self._slice_pass_counts = [0] * self._slice_total
        self._slice_stats = []
        self._init_slice_metrics(self._slice_total)
        self._source_mode = SourceMode.SLICE
        self._text_id = None
        self._slice_index = self._start_slice
        self._phase = SessionPhase.READY
        self._derive_upload_status()
        return self._slice_total

    def get_current_slice_text(self) -> str:
        """返回当前片文本。"""
        idx = self._slice_index - 1
        if (
            idx < 0
            or self._slice_size <= 0
            or not self._slice_text
            or self._slice_total <= 0
        ):
            return ""
        start = idx * self._slice_size
        end = start + self._slice_size
        if start >= len(self._slice_text):
            return ""
        return self._slice_text[start:end]

    @property
    def current_slice_content(self) -> str:
        """当前段文本内容（所有分片模式统一缓存）。"""
        return self._current_slice_content

    @current_slice_content.setter
    def current_slice_content(self, value: str) -> None:
        self._current_slice_content = value

    def get_shuffled_slice_text(self) -> str:
        """基于 _current_slice_content 乱序，不依赖 _slice_size。"""
        import random

        text = self._current_slice_content
        if not text:
            return ""
        chars = list(text)
        random.shuffle(chars)
        return "".join(chars)

    def _check_base_metrics(self, stats: dict) -> bool:
        """检查基础指标是否达标（击键、速度、键准、无错字）。"""
        return (
            stats.get("keyStroke", 0) >= self._key_stroke_min
            and stats.get("speed", 0) >= self._speed_min
            and stats.get("keyAccuracy", 0) >= self._accuracy_min
            and stats.get("wrong_char_count", 0) == 0
        )

    def collect_slice_result(self, stats: dict | None) -> None:
        """收集当前片的 SessionStat 快照。"""
        if not stats:
            return

        target_index = self._slice_index - 1
        if target_index < 0:
            return

        # 用 None 填充中间空位，防止手动跳过某片时出现越界
        while len(self._slice_stats) <= target_index:
            self._slice_stats.append(None)

        self._slice_stats[target_index] = stats

        # 统计达标次数（与 should_retype 共享同一套校验逻辑）
        if self._check_base_metrics(stats):
            self._slice_pass_counts[target_index] += 1

    def is_last_slice(self) -> bool:
        """当前片是否为最后一片。"""
        return self._slice_index >= self._slice_total

    def should_retype(self) -> bool:
        """检查当前片是否未达标，需要触发事件。

        纯查询方法（无副作用）：达标次数已在 collect_slice_result 中累计。

        校验逻辑：
        1. 检查击键>=、速度>=、键准>= 且无错字。
        2. 综合校验：四项合格指标（包括达标次数）全部满足，
           返回 False（达标，可推进）；否则返回 True。
        若 on_fail_action 为 'none'，直接返回 False，不再重打。
        """
        result = self.check_slice_result()
        return result != "advance"

    def check_slice_result(self) -> str:
        """检查当前片结果，区分三种状态。

        Returns:
            "fail": 基础指标未达标（应触发降击 + 重打）
            "pass": 基础指标达标，但连达标次数未满（应重打，不降击）
            "advance": 连达标次数已满（应推进下一段）
        """
        if self._on_fail_action == "none":
            return "advance"

        target_index = self._slice_index - 1
        if not (0 <= target_index < len(self._slice_stats)):
            return "fail"

        current = self._slice_stats[target_index]
        if current is None:
            return "fail"

        if not self._check_base_metrics(current):
            return "fail"

        if self._slice_pass_counts[target_index] < self._pass_count_min:
            return "pass"

        return "advance"

    @property
    def on_fail_action(self) -> str:
        return self._on_fail_action

    @property
    def auto_decrease_enabled(self) -> bool:
        return self._auto_decrease_enabled

    @property
    def key_stroke_decrease(self) -> float:
        return self._key_stroke_decrease

    @property
    def speed_decrease(self) -> int:
        return self._speed_decrease

    @property
    def accuracy_decrease(self) -> int:
        return self._accuracy_decrease

    def decrease_metrics_on_fail(self) -> None:
        if not self._auto_decrease_enabled:
            return
        if self._key_stroke_min > self._key_stroke_decrease > 0:
            self._key_stroke_min = round(
                self._key_stroke_min - self._key_stroke_decrease, 2
            )
        if self._speed_min > 0 and self._speed_decrease > 0:
            self._speed_min = max(0, self._speed_min - self._speed_decrease)
        if self._accuracy_min > 0 and self._accuracy_decrease > 0:
            self._accuracy_min = max(0, self._accuracy_min - self._accuracy_decrease)
        self.save_current_slice_metrics()

    def _build_current_metrics_dict(self) -> dict:
        """构建当前标量指标的字典快照。"""
        return {
            "key_stroke_min": self._key_stroke_min,
            "speed_min": self._speed_min,
            "accuracy_min": self._accuracy_min,
            "pass_count_min": self._pass_count_min,
            "on_fail_action": self._on_fail_action,
            "auto_decrease_enabled": self._auto_decrease_enabled,
            "key_stroke_decrease": self._key_stroke_decrease,
            "speed_decrease": self._speed_decrease,
            "accuracy_decrease": self._accuracy_decrease,
        }

    def _apply_metrics_dict(self, m: dict) -> None:
        """从字典恢复标量指标。"""
        self._key_stroke_min = m.get("key_stroke_min", self._key_stroke_min)
        self._speed_min = m.get("speed_min", self._speed_min)
        self._accuracy_min = m.get("accuracy_min", self._accuracy_min)
        self._pass_count_min = m.get("pass_count_min", self._pass_count_min)
        self._on_fail_action = m.get("on_fail_action", self._on_fail_action)
        self._auto_decrease_enabled = m.get(
            "auto_decrease_enabled", self._auto_decrease_enabled
        )
        self._key_stroke_decrease = m.get(
            "key_stroke_decrease", self._key_stroke_decrease
        )
        self._speed_decrease = m.get("speed_decrease", self._speed_decrease)
        self._accuracy_decrease = m.get("accuracy_decrease", self._accuracy_decrease)

    def _init_slice_metrics(self, slice_total: int) -> None:
        """用当前标量指标初始化 per-slice 指标列表。"""
        m = self._build_current_metrics_dict()
        self._slice_metrics = [m.copy() for _ in range(slice_total)]

    def save_current_slice_metrics(self) -> None:
        """将当前标量指标保存到当前片的 per-slice 指标中。"""
        idx = self._slice_index - 1
        if 0 <= idx < len(self._slice_metrics):
            self._slice_metrics[idx] = self._build_current_metrics_dict()

    def restore_slice_metrics(self, idx: int) -> None:
        """从 per-slice 指标恢复指定片的标量指标。"""
        target = idx - 1
        if 0 <= target < len(self._slice_metrics):
            self._apply_metrics_dict(self._slice_metrics[target])

    def get_slice_metrics(self, idx: int) -> dict | None:
        """返回指定片的指标字典，越界返回 None。"""
        target = idx - 1
        if 0 <= target < len(self._slice_metrics):
            return self._slice_metrics[target]
        return None

    def get_slice_status(self) -> str:
        """返回当前片进度摘要。

        优先显示当前片的成绩（打字完成后、推进前）；
        推进到下一片后回退到上一片的成绩。
        """
        if self._source_mode != SourceMode.SLICE:
            return ""
        idx = self._slice_index
        total = self._slice_total

        # 当前片有成绩时优先显示（打字刚结束时）
        prev_index = idx - 1
        if (
            0 <= prev_index < len(self._slice_stats)
            and self._slice_stats[prev_index] is not None
        ):
            current = self._slice_stats[prev_index]
            return (
                f"载文模式: 第 {idx}/{total} 段"
                f"  |  上一段: {current['speed']:.0f}CPM {current['keyAccuracy']:.1f}%"
            )

        # 推进到下一片后，回退到已完成的上片
        if idx > 1:
            prev_index = idx - 2
            if (
                0 <= prev_index < len(self._slice_stats)
                and self._slice_stats[prev_index] is not None
            ):
                current = self._slice_stats[prev_index]
                return (
                    f"载文模式: 第 {idx}/{total} 段"
                    f"  |  上一段: {current['speed']:.0f}CPM {current['keyAccuracy']:.1f}%"
                )

        return f"载文模式: 第 {idx}/{total} 段"

    def get_aggregate_data(self) -> tuple[list[dict], int] | None:
        """返回聚合成绩所需数据 (slice_stats, slice_count)。

        Returns:
            (valid_stats, len(valid_stats)) — 只包含有成绩的片，
            slice_count 为实际完成片数，用于聚合标签的准确显示。
        """
        valid_stats = [s for s in self._slice_stats if s is not None]
        if not valid_stats:
            return None
        return valid_stats, len(valid_stats)

    def get_last_slice_stats(self) -> dict:
        """返回当前片的成绩快照。"""
        target_index = self._slice_index - 1
        if 0 <= target_index < len(self._slice_stats):
            stats = self._slice_stats[target_index]
            return stats if stats is not None else {}
        return {}

    def get_slice_pass_count(self) -> int:
        """返回当前片的累计达标次数。"""
        target_index = self._slice_index - 1
        if 0 <= target_index < len(self._slice_pass_counts):
            return self._slice_pass_counts[target_index]
        return 0

    def exit_slice_mode(self) -> None:
        """退出载文模式，清理分片相关状态。"""
        self._slices = []
        self._slice_text = ""
        self._slice_size = 0
        self._slice_stats = []
        self._slice_pass_counts = []
        self._slice_index = 0
        self._slice_total = 0
        self.reset()

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

    def set_slice_index(self, idx: int) -> None:
        """直接设置当前片索引（用于无尽循环模式）。"""
        self._slice_index = idx
        self._phase = SessionPhase.READY

    def reset_slice_pass_count(self, idx: int) -> None:
        """重置指定段的达标次数（无尽模式循环回绕时使用）。"""
        target = idx - 1
        if 0 <= target < len(self._slice_pass_counts):
            self._slice_pass_counts[target] = 0

    def advance_slice(self) -> None:
        if (
            self._source_mode == SourceMode.SLICE
            and self._slice_index < self._slice_total
        ):
            self._slice_index += 1
            self._phase = SessionPhase.READY

    def back_slice(self) -> None:
        if self._source_mode == SourceMode.SLICE and self._slice_index > 1:
            self._slice_index -= 1
            self._phase = SessionPhase.READY

    # === 订阅 ===

    def subscribe_upload_status(self, callback: Callable[[UploadStatus], None]) -> None:
        self._on_upload_status_changed.append(callback)

    def subscribe_eligibility_reason(self, callback: Callable[[str], None]) -> None:
        self._on_eligibility_reason_changed.append(callback)

    # === 内部 ===

    def _derive_upload_status(self) -> None:
        new_status = self._compute_upload_status()
        if new_status != self._upload_status:
            self._upload_status = new_status
            self._notify_upload_status()
            self._notify_eligibility_reason()

    _INELIGIBLE_MODES = frozenset(
        {
            SourceMode.SLICE,
            SourceMode.SHUFFLE,
            SourceMode.CLIPBOARD,
            SourceMode.WENLAI,
            SourceMode.LOCAL_ARTICLE,
            SourceMode.TRAINER,
        }
    )
    _PENDING_MODES = frozenset({SourceMode.LOCAL, SourceMode.CUSTOM})

    def _compute_upload_status(self) -> UploadStatus:
        if self._source_mode in self._INELIGIBLE_MODES:
            return UploadStatus.NA
        if self._text_id is not None and self._text_id > 0:
            return UploadStatus.CONFIRMED
        if self._text_id_resolved:
            return UploadStatus.INELIGIBLE
        if self._source_mode in self._PENDING_MODES:
            return UploadStatus.PENDING
        return UploadStatus.INELIGIBLE

    def _notify_upload_status(self) -> None:
        for cb in self._on_upload_status_changed:
            cb(self._upload_status)

    def _notify_eligibility_reason(self) -> None:
        for cb in self._on_eligibility_reason_changed:
            cb(self.get_eligibility_reason())
