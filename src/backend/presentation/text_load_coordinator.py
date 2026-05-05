"""载文协调器 — 管理来源切换、分片导航和结果处理。

从 Bridge 提取的纯逻辑层，不依赖 Qt 信号机制。
Bridge 通过回调将信号发射委托给 QML。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bridge import Bridge

if TYPE_CHECKING:
    from .adapters.local_article_adapter import LocalArticleAdapter
    from .adapters.text_adapter import TextAdapter
    from .adapters.trainer_adapter import TrainerAdapter
    from .adapters.typing_adapter import TypingAdapter
    from .adapters.wenlai_adapter import WenlaiAdapter


class TextLoadCoordinator:
    """载文协调器 — 管理来源切换、分片导航和结果处理。"""

    def __init__(
        self,
        typing_adapter: TypingAdapter,
        text_adapter: TextAdapter,
        wenlai_adapter: WenlaiAdapter | None,
        local_article_adapter: LocalArticleAdapter | None,
        trainer_adapter: TrainerAdapter | None,
    ) -> None:
        self._typing = typing_adapter
        self._text_adapter = text_adapter
        self._wenlai = wenlai_adapter
        self._local_article = local_article_adapter
        self._trainer = trainer_adapter

        # 来源切换状态
        self._pending_standard_source_key: str = ""
        self._pending_wenlai_score_text: str = ""

        # 分片后端状态
        self._source_slice_backend: str | None = None
        self._source_slice_article_id: str = ""
        self._source_slice_segment_size: int = 0
        self._source_slice_trainer_id: str = ""
        self._source_slice_group_size: int = 0

        # 分片参数
        self._pending_slice_params: dict = {
            "key_stroke_min": 0,
            "speed_min": 0,
            "accuracy_min": 0,
            "pass_count_min": 1,
            "on_fail_action": "retype",
            "advance_mode": "sequential",
            "full_shuffle": False,
        }

    # ==========================================
    # 来源清理（幂等，无需判断当前来源）
    # ==========================================

    def clear_text_id(self, bridge: "Bridge") -> None:
        """清空 text_id（分片/乱序/自定义文本不提交成绩）。"""
        self._text_adapter.clear_active()
        bridge.setTextId(0)

    def clear_all_sources(self) -> None:
        """统一清理所有来源状态（幂等）。"""
        self._text_adapter.clear_active()
        if self._wenlai:
            self._wenlai.clear_active()
        if self._local_article:
            self._local_article.clear_active()
        if self._trainer:
            self._trainer.clear_active()

    def reset_session_for_standard_load(self, bridge: "Bridge") -> None:
        """普通载文先清掉特殊来源会话。"""
        self._typing.reset_session_context()
        bridge._text_id = 0
        bridge.textIdChanged.emit()

    # ==========================================
    # 来源切换准备
    # ==========================================

    def prepare_for_wenlai_load(self, bridge: "Bridge") -> None:
        if self._typing.is_slice_mode():
            bridge.exitSliceMode()
        if self._local_article:
            self._local_article.clear_active()
        if self._trainer:
            self._trainer.clear_active()
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)

    def prepare_for_trainer_load(self, bridge: "Bridge") -> None:
        if self._typing.is_slice_mode():
            bridge.exitSliceMode()
        if self._wenlai:
            self._wenlai.clear_active()
        if (
            self._local_article
            and self._local_article.local_article_loading
        ):
            self._local_article.clear_active()
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        self._typing.setup_trainer_session()

    def prepare_for_local_article_load(self, bridge: "Bridge") -> None:
        if self._typing.is_slice_mode():
            bridge.exitSliceMode()
        if self._wenlai:
            self._wenlai.clear_active()
        if self._trainer:
            self._trainer.clear_active()
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)

    # ==========================================
    # 结果处理（由 adapter 信号触发）
    # ==========================================

    def on_standard_text_loaded(
        self, text: str, text_id: int, source_label: str, bridge: "Bridge"
    ) -> None:
        source_key = self._pending_standard_source_key
        if text_id > 0:
            self._typing.setup_network_session(text_id, source_key)
        elif source_key:
            self._typing.setup_local_session(source_key, None)
        bridge.textLoaded.emit(text, text_id, source_label)

    def on_wenlai_text_loaded(self, text: str, title: str, bridge: "Bridge") -> None:
        if self._typing.is_slice_mode():
            bridge.exitSliceMode()
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        self._typing.setup_wenlai_session()
        self._typing.setTextTitle(title)
        bridge.windowTitleChanged.emit()
        pending_score_text = self._pending_wenlai_score_text
        self._pending_wenlai_score_text = ""
        sender_content = ""
        if self._wenlai and self._wenlai.current_text:
            sender_content = self._wenlai.current_text.sender_content
        if sender_content:
            clipboard_text = sender_content
            if pending_score_text:
                clipboard_text = f"{pending_score_text}\n{sender_content}"
            bridge._copy_text_to_clipboard(clipboard_text)
        bridge.wenlaiSegmentLabelChanged.emit()
        bridge.textLoaded.emit(text, -1, title)

    def on_trainer_segment_loaded(self, payload: dict, bridge: "Bridge") -> None:
        title = str(payload.get("title", "") or "")
        index = int(payload.get("index", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        title_label = title
        if index > 0 and total > 0:
            title_label = f"{title} {index}/{total}" if title else f"{index}/{total}"
        self._typing.setTextTitle(title_label)
        bridge.windowTitleChanged.emit()
        content = str(payload.get("content", "") or "")
        self._cache_current_content(content)
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        if index > 0 and total > 0:
            is_initial = self._source_slice_backend != "trainer"
            prev_index = self._typing.slice_index if not is_initial else 0
            self._source_slice_backend = "trainer"
            self._source_slice_trainer_id = str(
                payload.get("trainerId", self._source_slice_trainer_id)
                or self._source_slice_trainer_id
            )
            self._source_slice_group_size = int(
                payload.get("groupSize", self._source_slice_group_size)
                or self._source_slice_group_size
            )
            p = self._pending_slice_params
            self._typing.setup_sourced_slice_mode(
                index,
                total,
                on_fail_action=p["on_fail_action"],
                key_stroke_min=p["key_stroke_min"],
                speed_min=p["speed_min"],
                accuracy_min=p["accuracy_min"],
                pass_count_min=p["pass_count_min"],
                reset_counts=is_initial,
            )
            if not is_initial and index != prev_index:
                self._typing.reset_slice_pass_count(index)
            bridge.sliceModeChanged.emit()
        bridge.trainerSegmentLoaded.emit(payload)
        bridge.textLoaded.emit(content, -1, title_label)

    def on_local_article_segment_loaded(self, payload: dict, bridge: "Bridge") -> None:
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        title = str(payload.get("title", "") or "")
        index = int(payload.get("index", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        title_label = title
        if index > 0 and total > 0:
            title_label = f"{title} {index}/{total}" if title else f"{index}/{total}"
        self._typing.setTextTitle(title_label)
        bridge.windowTitleChanged.emit()
        content = str(payload.get("content", "") or "")
        self._cache_current_content(content)
        if index > 0 and total > 0:
            is_initial = self._source_slice_backend != "local_article"
            prev_index = self._typing.slice_index if not is_initial else 0
            self._source_slice_backend = "local_article"
            p = self._pending_slice_params
            self._typing.setup_sourced_slice_mode(
                index,
                total,
                on_fail_action=p["on_fail_action"],
                key_stroke_min=p["key_stroke_min"],
                speed_min=p["speed_min"],
                accuracy_min=p["accuracy_min"],
                pass_count_min=p["pass_count_min"],
                reset_counts=is_initial,
            )
            if not is_initial and index != prev_index:
                self._typing.reset_slice_pass_count(index)
            bridge.sliceModeChanged.emit()
        bridge.localArticleSegmentLoaded.emit(payload)
        bridge.textLoaded.emit(content, -1, title_label)

    # ==========================================
    # 分片导航
    # ==========================================

    def load_current_slice(self, bridge: "Bridge") -> None:
        idx = self._typing.slice_index
        total = self._typing.slice_total
        if idx <= 0 or idx > total:
            return
        slice_text = self._typing.get_current_slice_text()
        self._cache_current_content(slice_text)
        self._typing.set_slice_index(idx)
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        label = f"载文 {idx}/{total}"
        bridge.sliceStatusChanged.emit(f"载文模式: 第 {idx}/{total} 段")
        bridge.textLoaded.emit(slice_text, -1, label)

    def load_next_slice(self, bridge: "Bridge") -> None:
        if self._pending_slice_params.get("advance_mode") == "random":
            self.load_random_slice(bridge)
            return

        total = self._typing.slice_total
        current = self._typing.slice_index
        next_idx = (current % total) + 1 if total > 0 else 1

        backend = self._source_slice_backend
        if backend == "trainer" and self._source_slice_trainer_id:
            self._trainer.loadTrainerSegment(
                self._source_slice_trainer_id,
                next_idx,
                self._source_slice_group_size,
                full_shuffle=self._pending_slice_params.get("full_shuffle", False),
            )
        elif backend == "local_article":
            self._local_article.loadLocalArticleSegment(
                self._source_slice_article_id,
                next_idx,
                self._source_slice_segment_size,
            )
        else:
            self._typing.reset_slice_pass_count(next_idx)
            self._typing.set_slice_index(next_idx)
            bridge.sliceModeChanged.emit()
            self.load_current_slice(bridge)

    def load_random_slice(self, bridge: "Bridge") -> None:
        total = self._typing.slice_total
        if total <= 1:
            return
        current = self._typing.slice_index
        indices = [i for i in range(1, total + 1) if i != current]
        if not indices:
            return

        import random

        next_idx = random.choice(indices)

        backend = self._source_slice_backend
        if backend == "trainer" and self._source_slice_trainer_id:
            self._trainer.loadTrainerSegment(
                self._source_slice_trainer_id,
                next_idx,
                self._source_slice_group_size,
                full_shuffle=self._pending_slice_params.get("full_shuffle", False),
            )
        elif backend == "local_article":
            self._local_article.loadLocalArticleSegment(
                self._source_slice_article_id,
                next_idx,
                self._source_slice_segment_size,
            )
        else:
            self._typing.reset_slice_pass_count(next_idx)
            self._typing.set_slice_index(next_idx)
            bridge.sliceModeChanged.emit()
            self.load_current_slice(bridge)

    def load_prev_slice(self, bridge: "Bridge") -> None:
        if self._typing.slice_index <= 1:
            return

        backend = self._source_slice_backend
        if backend == "trainer":
            self._trainer.loadPreviousTrainerSegment()
        elif backend == "local_article":
            prev_idx = self._typing.slice_index - 1
            self._local_article.loadLocalArticleSegment(
                self._source_slice_article_id,
                prev_idx,
                self._source_slice_segment_size,
            )
        else:
            prev_idx = self._typing.slice_index - 1
            self._typing.reset_slice_pass_count(prev_idx)
            self._typing.back_slice()
            bridge.sliceModeChanged.emit()
            self.load_current_slice(bridge)

    def handle_slice_retype(self, bridge: "Bridge") -> None:
        backend = self._source_slice_backend
        current = self._typing.slice_index
        action = self._typing.on_fail_action

        if action == "shuffle":
            if backend == "trainer":
                self._trainer.shuffleCurrentTrainerGroup()
            else:
                self.shuffle_current_slice(bridge)
            return

        if action == "retype":
            if backend == "trainer":
                self._trainer.loadCurrentTrainerSegment()
            elif backend == "local_article":
                self._local_article.loadLocalArticleSegment(
                    self._source_slice_article_id,
                    current,
                    self._source_slice_segment_size,
                )
            else:
                self.load_current_slice(bridge)
            return

    def shuffle_current_slice(self, bridge: "Bridge") -> None:
        shuffled = self._typing.get_shuffled_slice_text()
        if not shuffled:
            return
        idx = self._typing.slice_index
        total = self._typing.slice_total
        self._typing.set_slice_index(idx)
        self._typing.prepare_for_text_load()
        self.clear_text_id(bridge)
        bridge.textLoaded.emit(shuffled, -1, f"载文 {idx}/{total}（乱序）")

    def exit_slice_mode(self, bridge: "Bridge") -> None:
        self._source_slice_backend = None
        self._source_slice_trainer_id = ""
        self._source_slice_group_size = 0
        self._typing.exit_slice_mode()
        bridge.sliceModeChanged.emit()
        bridge.sliceStatusChanged.emit("")

    # ==========================================
    # 辅助方法
    # ==========================================

    def _cache_current_content(self, content: str) -> None:
        self._typing.set_current_slice_content(content)

    @property
    def pending_slice_params(self) -> dict:
        return self._pending_slice_params

    @pending_slice_params.setter
    def pending_slice_params(self, value: dict) -> None:
        self._pending_slice_params = value

    @property
    def pending_standard_source_key(self) -> str:
        return self._pending_standard_source_key

    @pending_standard_source_key.setter
    def pending_standard_source_key(self, value: str) -> None:
        self._pending_standard_source_key = value

    @property
    def pending_wenlai_score_text(self) -> str:
        return self._pending_wenlai_score_text

    @pending_wenlai_score_text.setter
    def pending_wenlai_score_text(self, value: str) -> None:
        self._pending_wenlai_score_text = value

    @property
    def source_slice_backend(self) -> str | None:
        return self._source_slice_backend

    @source_slice_backend.setter
    def source_slice_backend(self, value: str | None) -> None:
        self._source_slice_backend = value

    @property
    def source_slice_article_id(self) -> str:
        return self._source_slice_article_id

    @source_slice_article_id.setter
    def source_slice_article_id(self, value: str) -> None:
        self._source_slice_article_id = value

    @property
    def source_slice_segment_size(self) -> int:
        return self._source_slice_segment_size

    @source_slice_segment_size.setter
    def source_slice_segment_size(self, value: int) -> None:
        self._source_slice_segment_size = value

    @property
    def source_slice_trainer_id(self) -> str:
        return self._source_slice_trainer_id

    @source_slice_trainer_id.setter
    def source_slice_trainer_id(self, value: str) -> None:
        self._source_slice_trainer_id = value

    @property
    def source_slice_group_size(self) -> int:
        return self._source_slice_group_size

    @source_slice_group_size.setter
    def source_slice_group_size(self, value: int) -> None:
        self._source_slice_group_size = value
