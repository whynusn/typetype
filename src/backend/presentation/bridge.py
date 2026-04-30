"""QML 通信适配层。

仅负责：
- 属性代理（QML 属性绑定透传到各个 Adapter）
- 信号转发（Adapter 信号 -> Bridge 信号 -> QML）
- Slot 入口（QML 调用 -> Bridge 调用 -> Adapter）
- 全局键盘监听器持有与转发（Wayland 平台特殊处理）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQuick import QQuickTextDocument

from ..ports.key_codes import KeyCodes
from ..utils.logger import log_info


if TYPE_CHECKING:
    from ..ports.key_listener import KeyListener
    from ..application.gateways.typing_totals_gateway import TypingTotalsGateway
    from .adapters.auth_adapter import AuthAdapter
    from .adapters.char_stats_adapter import CharStatsAdapter
    from .adapters.leaderboard_adapter import LeaderboardAdapter
    from .adapters.local_article_adapter import LocalArticleAdapter
    from .adapters.text_adapter import TextAdapter
    from .adapters.trainer_adapter import TrainerAdapter
    from .adapters.typing_adapter import TypingAdapter
    from .adapters.upload_text_adapter import UploadTextAdapter
    from .adapters.wenlai_adapter import WenlaiAdapter
    from .adapters.ziti_adapter import ZitiAdapter


class Bridge(QObject):
    """QML 通信适配层。"""

    # 信号定义
    typeSpeedChanged = Signal()
    keyStrokeChanged = Signal()
    codeLengthChanged = Signal()
    charNumChanged = Signal()
    totalTimeChanged = Signal()
    readOnlyChanged = Signal()
    historyRecordUpdated = Signal(dict)
    typingEnded = Signal()
    textLoaded = Signal(str, int, str)  # (text_content, text_id, source_label)
    textLoadFailed = Signal(str)
    textLoadingChanged = Signal()
    loggedinChanged = Signal()
    userInfoChanged = Signal()
    loginResult = Signal(bool, str)
    registerResult = Signal(bool, str)
    loginStateInitialized = Signal(bool)
    cursorPosChanged = Signal(int)
    specialPlatformConfirmed = Signal(bool)
    backspaceChanged = Signal()
    correctionChanged = Signal()
    keyAccuracyChanged = Signal()
    typingPausedChanged = Signal()
    weakestCharsLoaded = Signal(list)
    leaderboardLoaded = Signal(dict)
    leaderboardLoadFailed = Signal(str)
    leaderboardLoadingChanged = Signal()
    catalogLoaded = Signal(list)
    catalogLoadFailed = Signal(str)
    textListLoaded = Signal(list)
    textListLoadFailed = Signal(str)
    textListLoadingChanged = Signal()
    uploadResult = Signal(bool, str, int)  # (success, message, server_text_id)
    tokenExpired = Signal()
    textIdChanged = Signal()
    # 载文模式信号
    sliceModeChanged = Signal()
    sliceStatusChanged = Signal(str)
    textContentLoaded = Signal(int, str, str)  # (text_id, content, title)
    # 会话状态机信号
    uploadStatusChanged = Signal(int)
    eligibilityReasonChanged = Signal(str)
    baseUrlChanged = Signal()
    windowTitleChanged = Signal()
    typingTotalsChanged = Signal()
    # 晴发文信号
    wenlaiLoadFailed = Signal(str)
    wenlaiLoadingChanged = Signal()
    wenlaiLoginResult = Signal(bool, str)
    wenlaiLoginStateChanged = Signal()
    wenlaiConfigChanged = Signal()
    wenlaiSegmentLabelChanged = Signal()
    wenlaiDifficultiesLoaded = Signal(list)
    wenlaiCategoriesLoaded = Signal(list)
    # 本地长文信号
    localArticlesLoaded = Signal(list)
    localArticlesLoadFailed = Signal(str)
    localArticleSegmentLoaded = Signal(dict)
    localArticleSegmentLoadFailed = Signal(str)
    localArticleLoadingChanged = Signal()
    # 字提示信号
    zitiSchemesLoaded = Signal(list)
    zitiSchemesLoadFailed = Signal(str)
    zitiSchemeLoaded = Signal(str, int)
    zitiSchemeLoadFailed = Signal(str)
    zitiStateChanged = Signal()
    # 练单器信号
    trainersLoaded = Signal(list)
    trainersLoadFailed = Signal(str)
    trainerSegmentLoaded = Signal(dict)
    trainerSegmentLoadFailed = Signal(str)
    trainerLoadingChanged = Signal()

    def __init__(
        self,
        typing_adapter: TypingAdapter,
        text_adapter: TextAdapter,
        auth_adapter: AuthAdapter,
        char_stats_adapter: CharStatsAdapter,
        upload_text_adapter: UploadTextAdapter | None = None,
        leaderboard_adapter: LeaderboardAdapter | None = None,
        wenlai_adapter: WenlaiAdapter | None = None,
        local_article_adapter: LocalArticleAdapter | None = None,
        ziti_adapter: ZitiAdapter | None = None,
        trainer_adapter: TrainerAdapter | None = None,
        typing_totals_gateway: TypingTotalsGateway | None = None,
        key_listener: KeyListener | None = None,
        base_url_update_callback: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self._typing_adapter = typing_adapter
        self._text_adapter = text_adapter
        self._auth_adapter = auth_adapter
        self._char_stats_adapter = char_stats_adapter
        self._upload_text_adapter = upload_text_adapter
        self._leaderboard_adapter = leaderboard_adapter
        self._wenlai_adapter = wenlai_adapter
        self._local_article_adapter = local_article_adapter
        self._ziti_adapter = ziti_adapter
        self._trainer_adapter = trainer_adapter
        self._typing_totals_gateway = typing_totals_gateway
        self._key_listener = key_listener
        self._base_url_update_callback = base_url_update_callback
        self._is_special_platform = key_listener is not None
        self._lower_pane_focused = False
        self._text_id = 0
        self._pending_wenlai_score_text = ""
        self._pending_history_segment_label = ""
        self._pending_history_score_text = ""
        self._pending_standard_source_key = ""
        self._source_slice_backend: str | None = None
        self._source_slice_article_id: str = ""
        self._source_slice_segment_size: int = 0
        self._source_slice_trainer_id: str = ""
        self._source_slice_group_size: int = 0
        self._pending_slice_params: dict = {
            "key_stroke_min": 0,
            "speed_min": 0,
            "accuracy_min": 0,
            "pass_count_min": 1,
            "on_fail_action": "retype",
            "advance_mode": "sequential",
            "full_shuffle": False,
        }
        self._cached_devices: list[dict] | None = None

        self._connect_typing_signals()
        self._connect_text_load_signals()
        self._connect_auth_signals()
        self._connect_char_stats_signals()
        self._connect_upload_signals()
        self._connect_leaderboard_signals()
        self._connect_wenlai_signals()
        self._connect_local_article_signals()
        self._connect_ziti_signals()
        self._connect_trainer_signals()
        self._connect_key_listener()

        self.specialPlatformConfirmed.emit(self._is_special_platform)
        log_info(f"[Bridge] 检测到平台特殊性: {self._is_special_platform}")

    def _clear_text_id(self) -> None:
        """清空 text_id（分片/乱序/自定义文本不提交成绩）。"""
        self._text_adapter.clear_active()
        self.setTextId(0)

    def _clear_wenlai_active(self) -> None:
        """退出晴发文当前文本状态（切到其他来源时调用）。"""
        if self._wenlai_adapter:
            self._wenlai_adapter.clear_active()

    def _clear_local_article_active(self) -> None:
        """失效本地长文进行中的异步结果（切到其他来源时调用）。"""
        if self._local_article_adapter:
            self._local_article_adapter.clear_active()

    def _clear_trainer_active(self) -> None:
        """失效练单器进行中的异步结果（切到其他来源时调用）。"""
        if self._trainer_adapter:
            self._trainer_adapter.clear_active()

    def _reset_session_for_standard_load(self) -> None:
        """普通载文先清掉特殊来源会话，后续 textId 回填再确认资格。"""
        self._typing_adapter.reset_session_context()
        self._text_id = 0
        self.textIdChanged.emit()

    def _connect_typing_signals(self) -> None:
        self._typing_adapter.typeSpeedChanged.connect(self.typeSpeedChanged.emit)
        self._typing_adapter.keyStrokeChanged.connect(self.keyStrokeChanged.emit)
        self._typing_adapter.codeLengthChanged.connect(self.codeLengthChanged.emit)
        self._typing_adapter.charNumChanged.connect(self._on_char_num_changed)
        self._typing_adapter.totalTimeChanged.connect(self.totalTimeChanged.emit)
        self._typing_adapter.readOnlyChanged.connect(self.readOnlyChanged.emit)
        self._typing_adapter.typingEnded.connect(self._on_typing_ended)
        self._typing_adapter.historyRecordUpdated.connect(self._on_history_record)
        self._typing_adapter.backspaceChanged.connect(self.backspaceChanged.emit)
        self._typing_adapter.correctionChanged.connect(self.correctionChanged.emit)
        self._typing_adapter.keyAccuracyChanged.connect(self.keyAccuracyChanged.emit)
        self._typing_adapter.pauseChanged.connect(self._on_typing_pause_changed)
        # 会话状态机信号
        self._typing_adapter.uploadStatusChanged.connect(self.uploadStatusChanged.emit)
        self._typing_adapter.eligibilityReasonChanged.connect(
            self.eligibilityReasonChanged.emit
        )

    def _on_char_num_changed(self) -> None:
        self.charNumChanged.emit()
        self.windowTitleChanged.emit()

    def _on_history_record(self, record: dict) -> None:
        record = dict(record)
        if self._pending_history_segment_label or self._pending_history_score_text:
            if self._pending_history_segment_label:
                record["segmentNo"] = self._pending_history_segment_label
            if self._pending_history_score_text:
                record["scoreText"] = self._pending_history_score_text
        self._pending_history_segment_label = ""
        self._pending_history_score_text = ""
        if self._typing_totals_gateway:
            char_count = self._safe_record_char_count(record)
            self._typing_totals_gateway.record_session(char_count)
            self.typingTotalsChanged.emit()
        self.historyRecordUpdated.emit(record)

    def _on_typing_ended(self) -> None:
        if self._typing_adapter.is_slice_mode():
            idx = self._typing_adapter.slice_index
            total = self._typing_adapter.slice_total
            self._pending_history_segment_label = f"{idx}/{total}"
        else:
            self._pending_history_segment_label = self.wenlaiSegmentLabel
        self._pending_history_score_text = self._build_current_score_plain_text()
        self.typingEnded.emit()

    def _on_typing_pause_changed(self) -> None:
        self.typingPausedChanged.emit()
        self.windowTitleChanged.emit()

    def _build_current_score_plain_text(self) -> str:
        """构建当前会话的可复制成绩。"""
        score_text = self._typing_adapter.get_score_plain_text()
        segment_prefix = self._current_score_segment_prefix()
        if not score_text or not segment_prefix:
            return score_text
        if score_text.startswith(f"{segment_prefix} "):
            return score_text
        return f"{segment_prefix} {score_text}"

    def _current_score_segment_prefix(self) -> str:
        """返回当前段号的文本前缀（用于 scoreText）。"""
        # 晴发文：使用服务端返回的段号
        if self._wenlai_adapter and self._wenlai_adapter.is_active:
            current_text = self._wenlai_adapter.current_text
            if current_text:
                if current_text.mark:
                    return f"段{current_text.mark}"
                if current_text.sort_num > 0:
                    return f"第{current_text.sort_num}段"
                progress = current_text.progress_text
                return f"段{progress}" if progress else ""
        # 分片载文/练单器/本地文库：使用本地段号
        if self._typing_adapter.is_slice_mode():
            idx = self._typing_adapter.slice_index
            total = self._typing_adapter.slice_total
            if idx > 0 and total > 0:
                return f"第{idx}/{total}段"
        return ""

    @staticmethod
    def _safe_record_char_count(record: dict) -> int:
        try:
            return max(int(record.get("charNum", 0) or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _connect_text_load_signals(self) -> None:
        self._text_adapter.textLoaded.connect(self._on_standard_text_loaded)
        self._text_adapter.textLoadFailed.connect(self._on_standard_text_load_failed)
        self._text_adapter.textLoadingChanged.connect(self.textLoadingChanged.emit)
        self._text_adapter.localTextIdResolved.connect(self._on_local_text_id_resolved)

    def _on_standard_text_loaded(
        self, text: str, text_id: int, source_label: str
    ) -> None:
        source_key = self._pending_standard_source_key
        if text_id > 0:
            self._typing_adapter.setup_network_session(text_id, source_key)
        elif source_key:
            self._typing_adapter.setup_local_session(source_key, None)
        self.textLoaded.emit(text, text_id, source_label)

    def _on_standard_text_load_failed(self, message: str) -> None:
        self.textLoadFailed.emit(message)

    def _on_local_text_id_resolved(self, text_id: int, lookup_generation: int) -> None:
        """本地文本异步回查到 text_id 后自动设置。"""
        if (
            text_id
            and text_id > 0
            and lookup_generation == self._text_adapter.current_lookup_generation
            and self._typing_adapter.can_accept_resolved_text_id()
        ):
            self.setTextId(text_id)

    def _connect_auth_signals(self) -> None:
        self._auth_adapter.loggedinChanged.connect(self.loggedinChanged.emit)
        self._auth_adapter.userInfoChanged.connect(self.userInfoChanged.emit)
        self._auth_adapter.loginResult.connect(self.loginResult.emit)
        self._auth_adapter.registerResult.connect(self.registerResult.emit)
        self._auth_adapter.tokenExpired.connect(self.tokenExpired.emit)
        self._auth_adapter.loginStateInitialized.connect(
            self.loginStateInitialized.emit
        )

    def _connect_char_stats_signals(self) -> None:
        self._char_stats_adapter.weakestCharsLoaded.connect(
            self.weakestCharsLoaded.emit
        )

    def _connect_upload_signals(self) -> None:
        if self._upload_text_adapter:
            self._upload_text_adapter.uploadFinished.connect(self.uploadResult.emit)

    def _connect_leaderboard_signals(self) -> None:
        if self._leaderboard_adapter:
            self._leaderboard_adapter.leaderboardLoaded.connect(
                self.leaderboardLoaded.emit
            )
            self._leaderboard_adapter.leaderboardLoadFailed.connect(
                self.leaderboardLoadFailed.emit
            )
            self._leaderboard_adapter.leaderboardLoadingChanged.connect(
                self.leaderboardLoadingChanged.emit
            )
            self._leaderboard_adapter.textListLoaded.connect(self.textListLoaded.emit)
            self._leaderboard_adapter.textListLoadFailed.connect(
                self.textListLoadFailed.emit
            )
            self._leaderboard_adapter.textListLoadingChanged.connect(
                self.textListLoadingChanged.emit
            )
            self._leaderboard_adapter.catalogLoaded.connect(self.catalogLoaded.emit)
            self._leaderboard_adapter.catalogLoadFailed.connect(
                self.catalogLoadFailed.emit
            )

    def _connect_wenlai_signals(self) -> None:
        if not self._wenlai_adapter:
            return
        self._wenlai_adapter.textLoaded.connect(self._on_wenlai_text_loaded)
        self._wenlai_adapter.loadFailed.connect(self._on_wenlai_load_failed)
        self._wenlai_adapter.loadingChanged.connect(self.wenlaiLoadingChanged.emit)
        self._wenlai_adapter.loginResult.connect(self.wenlaiLoginResult.emit)
        self._wenlai_adapter.loginStateChanged.connect(
            self.wenlaiLoginStateChanged.emit
        )
        self._wenlai_adapter.configChanged.connect(self._on_wenlai_config_changed)
        self._wenlai_adapter.difficultiesLoaded.connect(
            self.wenlaiDifficultiesLoaded.emit
        )
        self._wenlai_adapter.categoriesLoaded.connect(self.wenlaiCategoriesLoaded.emit)

    def _connect_local_article_signals(self) -> None:
        if not self._local_article_adapter:
            return
        self._local_article_adapter.localArticlesLoaded.connect(
            self.localArticlesLoaded.emit
        )
        self._local_article_adapter.localArticlesLoadFailed.connect(
            self.localArticlesLoadFailed.emit
        )
        self._local_article_adapter.localArticleSegmentLoaded.connect(
            self._on_local_article_segment_loaded
        )
        self._local_article_adapter.localArticleSegmentLoadFailed.connect(
            self.localArticleSegmentLoadFailed.emit
        )
        self._local_article_adapter.localArticleLoadingChanged.connect(
            self.localArticleLoadingChanged.emit
        )

    def _connect_ziti_signals(self) -> None:
        if not self._ziti_adapter:
            return
        self._ziti_adapter.schemesLoaded.connect(self.zitiSchemesLoaded.emit)
        self._ziti_adapter.schemesLoadFailed.connect(self.zitiSchemesLoadFailed.emit)
        self._ziti_adapter.schemeLoaded.connect(self.zitiSchemeLoaded.emit)
        self._ziti_adapter.schemeLoadFailed.connect(self.zitiSchemeLoadFailed.emit)
        self._ziti_adapter.zitiStateChanged.connect(self.zitiStateChanged.emit)

    def _connect_trainer_signals(self) -> None:
        if not self._trainer_adapter:
            return
        self._trainer_adapter.trainersLoaded.connect(self.trainersLoaded.emit)
        self._trainer_adapter.trainersLoadFailed.connect(self.trainersLoadFailed.emit)
        self._trainer_adapter.trainerSegmentLoaded.connect(
            self._on_trainer_segment_loaded
        )
        self._trainer_adapter.trainerSegmentLoadFailed.connect(
            self.trainerSegmentLoadFailed.emit
        )
        self._trainer_adapter.trainerLoadingChanged.connect(
            self.trainerLoadingChanged.emit
        )

    def _on_trainer_segment_loaded(self, payload: dict) -> None:
        title = str(payload.get("title", "") or "")
        index = int(payload.get("index", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        title_label = title
        if index > 0 and total > 0:
            title_label = f"{title} {index}/{total}" if title else f"{index}/{total}"
        self._typing_adapter.setTextTitle(title_label)
        self.windowTitleChanged.emit()
        content = str(payload.get("content", "") or "")
        self._cache_current_content(content)
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        # 启用分片载文模式，实现自动推进下一段
        if index > 0 and total > 0:
            is_initial = self._source_slice_backend != "trainer"
            prev_index = self._typing_adapter.slice_index if not is_initial else 0
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
            self._typing_adapter.setup_sourced_slice_mode(
                index,
                total,
                on_fail_action=p["on_fail_action"],
                key_stroke_min=p["key_stroke_min"],
                speed_min=p["speed_min"],
                accuracy_min=p["accuracy_min"],
                pass_count_min=p["pass_count_min"],
                reset_counts=is_initial,
            )
            # 片段切换时重置目标片段的达标次数（同一片段重打则保留）
            if not is_initial and index != prev_index:
                self._typing_adapter.reset_slice_pass_count(index)
            self.sliceModeChanged.emit()
        self.trainerSegmentLoaded.emit(payload)
        self.textLoaded.emit(content, -1, title_label)

    def _on_local_article_segment_loaded(self, payload: dict) -> None:
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        title = str(payload.get("title", "") or "")
        index = int(payload.get("index", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        title_label = title
        if index > 0 and total > 0:
            title_label = f"{title} {index}/{total}" if title else f"{index}/{total}"
        self._typing_adapter.setTextTitle(title_label)
        self.windowTitleChanged.emit()
        content = str(payload.get("content", "") or "")
        self._cache_current_content(content)
        # 启用分片载文模式，实现自动推进下一段
        if index > 0 and total > 0:
            is_initial = self._source_slice_backend != "local_article"
            prev_index = self._typing_adapter.slice_index if not is_initial else 0
            self._source_slice_backend = "local_article"
            p = self._pending_slice_params
            self._typing_adapter.setup_sourced_slice_mode(
                index,
                total,
                on_fail_action=p["on_fail_action"],
                key_stroke_min=p["key_stroke_min"],
                speed_min=p["speed_min"],
                accuracy_min=p["accuracy_min"],
                pass_count_min=p["pass_count_min"],
                reset_counts=is_initial,
            )
            # 片段切换时重置目标片段的达标次数（同一片段重打则保留）
            if not is_initial and index != prev_index:
                self._typing_adapter.reset_slice_pass_count(index)
            self.sliceModeChanged.emit()
        self.localArticleSegmentLoaded.emit(payload)
        self.textLoaded.emit(content, -1, title_label)

    def _on_wenlai_config_changed(self) -> None:
        self.wenlaiConfigChanged.emit()
        self.wenlaiSegmentLabelChanged.emit()
        self.windowTitleChanged.emit()

    def _on_wenlai_load_failed(self, message: str) -> None:
        self._pending_wenlai_score_text = ""
        self.wenlaiLoadFailed.emit(message)

    def _on_wenlai_text_loaded(self, text: str, title: str) -> None:
        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        self._typing_adapter.setup_wenlai_session()
        self._typing_adapter.setTextTitle(title)
        self.windowTitleChanged.emit()
        pending_score_text = self._pending_wenlai_score_text
        self._pending_wenlai_score_text = ""
        sender_content = ""
        if self._wenlai_adapter and self._wenlai_adapter.current_text:
            sender_content = self._wenlai_adapter.current_text.sender_content
        if sender_content:
            clipboard_text = sender_content
            if pending_score_text:
                clipboard_text = f"{pending_score_text}\n{sender_content}"
            self._copy_text_to_clipboard(clipboard_text)
        self.wenlaiSegmentLabelChanged.emit()
        self.textLoaded.emit(text, -1, title)

    def _connect_key_listener(self) -> None:
        if self._key_listener:
            self._key_listener.keyPressed.connect(self.on_key_received)

    def on_key_received(self, keyCode: int, deviceName: str) -> None:
        if not self._lower_pane_focused or KeyCodes.is_modifier(keyCode):
            return

        if (
            not self._typing_adapter.is_started
            and not self._typing_adapter.text_read_only
            and not KeyCodes.is_backspace(keyCode)
        ):
            self._typing_adapter.handleStartStatus(True)

        if KeyCodes.is_backspace(keyCode):
            self._typing_adapter.handleBackspace()
        self._typing_adapter.handlePressed()

    # 属性代理

    @Property(bool, notify=readOnlyChanged)
    def textReadOnly(self) -> bool:
        return self._typing_adapter.text_read_only

    @Property(bool, notify=textLoadingChanged)
    def textLoading(self) -> bool:
        return self._text_adapter.text_loading

    @Property(str, constant=True)
    def defaultTextSourceKey(self) -> str:
        return self._text_adapter.get_default_source_key()

    @Property(str, constant=True)
    def defaultTextTitle(self) -> str:
        return self._text_adapter.get_default_source_label()

    @Property(list, constant=True)
    def textSourceOptions(self) -> list:
        return self._text_adapter.get_source_options()

    @Property(list, constant=True)
    def rankingSourceOptions(self) -> list:
        return self._text_adapter.get_ranking_source_options()

    @Property(list, constant=True)
    def uploadTextSourceOptions(self) -> list:
        return self._text_adapter.get_upload_source_options()

    @Property(float, notify=totalTimeChanged)
    def totalTime(self) -> float:
        return self._typing_adapter.total_time

    @Property(float, notify=typeSpeedChanged)
    def typeSpeed(self) -> float:
        return self._typing_adapter.type_speed

    @Property(float, notify=keyStrokeChanged)
    def keyStroke(self) -> float:
        return self._typing_adapter.key_stroke

    @Property(float, notify=codeLengthChanged)
    def codeLength(self) -> float:
        return self._typing_adapter.code_length

    @Property(int, notify=charNumChanged)
    def wrongNum(self) -> int:
        return self._typing_adapter.wrong_num

    @Property(int, notify=backspaceChanged)
    def backspace(self) -> int:
        return self._typing_adapter.backspace_count

    @Property(int, notify=correctionChanged)
    def correction(self) -> int:
        return self._typing_adapter.correction_count

    @Property(float, notify=keyAccuracyChanged)
    def keyAccuracy(self) -> float:
        return self._typing_adapter.key_accuracy

    @Property(str, notify=charNumChanged)
    def charNum(self) -> str:
        return self._typing_adapter.char_num

    @Property(bool, notify=typingPausedChanged)
    def typingPaused(self) -> bool:
        return self._typing_adapter.is_paused

    @Property(bool, notify=loggedinChanged)
    def loggedin(self) -> bool:
        return self._auth_adapter.loggedin

    @Property(str, notify=userInfoChanged)
    def userNickname(self) -> str:
        return self._auth_adapter.user_nickname

    @Property(str, notify=userInfoChanged)
    def currentUser(self) -> str:
        return self._auth_adapter.current_user

    @Property(bool, notify=specialPlatformConfirmed)
    def isSpecialPlatform(self) -> bool:
        return self._is_special_platform

    @Property(bool, notify=leaderboardLoadingChanged)
    def leaderboardLoading(self) -> bool:
        if self._leaderboard_adapter:
            return self._leaderboard_adapter.loading
        return False

    @Property(bool, notify=textListLoadingChanged)
    def textListLoading(self) -> bool:
        if self._leaderboard_adapter:
            return self._leaderboard_adapter.text_list_loading
        return False

    @Property(int, notify=textIdChanged)
    def textId(self) -> int:
        return self._text_id

    @Property(int, notify=uploadStatusChanged)
    def uploadStatus(self) -> int:
        """当前上传资格状态（0=CONFIRMED, 1=PENDING, 2=INELIGIBLE, 3=NA）。"""
        return self._typing_adapter.upload_status

    @Property(str, notify=eligibilityReasonChanged)
    def eligibilityReason(self) -> str:
        """当前资格原因消息。"""
        return self._typing_adapter.eligibility_reason

    @Property(str, notify=baseUrlChanged)
    def baseUrl(self) -> str:
        """当前 API 服务地址。"""
        return self._text_adapter.get_base_url()

    @Property(str, notify=windowTitleChanged)
    def windowTitle(self) -> str:
        return self._build_window_title()

    @Property(int, notify=typingTotalsChanged)
    def todayTypedChars(self) -> int:
        if self._typing_totals_gateway:
            return self._typing_totals_gateway.today_chars
        return 0

    @Property(int, notify=typingTotalsChanged)
    def totalTypedChars(self) -> int:
        if self._typing_totals_gateway:
            return self._typing_totals_gateway.total_chars
        return 0

    def _build_window_title(self) -> str:
        char_num = self._typing_adapter.char_num
        current_text = (
            self._wenlai_adapter.current_text if self._wenlai_adapter else None
        )
        if self._wenlai_adapter and self._wenlai_adapter.is_active and current_text:
            parts = ["TypeType"]
            if self._typing_adapter.is_paused:
                parts.append("暂停")
            if current_text.difficulty_text:
                parts.append(current_text.difficulty_text)
            parts.append(char_num)
            if current_text.title:
                parts.append(current_text.title)
            return " ".join(parts)

        text_title = self._typing_adapter.text_title
        parts = ["TypeType"]
        if self._typing_adapter.is_paused:
            parts.append("暂停")
        if char_num != "0/0":
            parts.append(char_num)
        if text_title:
            parts.append(text_title)
        return " ".join(parts)

    @Property(bool, notify=wenlaiLoadingChanged)
    def wenlaiLoading(self) -> bool:
        return self._wenlai_adapter.text_loading if self._wenlai_adapter else False

    @Property(bool, notify=wenlaiLoginStateChanged)
    def wenlaiLoggedIn(self) -> bool:
        return self._wenlai_adapter.logged_in if self._wenlai_adapter else False

    @Property(str, notify=wenlaiLoginStateChanged)
    def wenlaiCurrentUser(self) -> str:
        return self._wenlai_adapter.current_user if self._wenlai_adapter else ""

    @Property(bool, notify=wenlaiConfigChanged)
    def isWenlaiActive(self) -> bool:
        return self._wenlai_adapter.is_active if self._wenlai_adapter else False

    @Property(str, notify=wenlaiConfigChanged)
    def wenlaiSegmentMode(self) -> str:
        return self._wenlai_adapter.segment_mode if self._wenlai_adapter else "manual"

    @Property(str, notify=wenlaiSegmentLabelChanged)
    def wenlaiSegmentLabel(self) -> str:
        current_text = (
            self._wenlai_adapter.current_text if self._wenlai_adapter else None
        )
        if (
            not self._wenlai_adapter
            or not self._wenlai_adapter.is_active
            or not current_text
        ):
            return ""
        return current_text.progress_text

    @Property(str, notify=wenlaiConfigChanged)
    def wenlaiBaseUrl(self) -> str:
        return self._wenlai_adapter.base_url if self._wenlai_adapter else ""

    @Property(int, notify=wenlaiConfigChanged)
    def wenlaiLength(self) -> int:
        return self._wenlai_adapter.length if self._wenlai_adapter else 0

    @Property(int, notify=wenlaiConfigChanged)
    def wenlaiDifficultyLevel(self) -> int:
        return self._wenlai_adapter.difficulty_level if self._wenlai_adapter else 0

    @Property(str, notify=wenlaiConfigChanged)
    def wenlaiCategory(self) -> str:
        return self._wenlai_adapter.category if self._wenlai_adapter else ""

    @Property(bool, notify=wenlaiConfigChanged)
    def wenlaiStrictLength(self) -> bool:
        return self._wenlai_adapter.strict_length if self._wenlai_adapter else False

    @Property(bool, notify=localArticleLoadingChanged)
    def localArticleLoading(self) -> bool:
        if self._local_article_adapter:
            return self._local_article_adapter.local_article_loading
        return False

    @Property(bool, notify=trainerLoadingChanged)
    def trainerLoading(self) -> bool:
        if self._trainer_adapter:
            return self._trainer_adapter.trainer_loading
        return False

    @Property(bool, notify=zitiStateChanged)
    def zitiEnabled(self) -> bool:
        return self._ziti_adapter.enabled if self._ziti_adapter else False

    @Property(str, notify=zitiStateChanged)
    def zitiCurrentScheme(self) -> str:
        return self._ziti_adapter.current_scheme if self._ziti_adapter else ""

    @Property(int, notify=zitiStateChanged)
    def zitiLoadedCount(self) -> int:
        return self._ziti_adapter.loaded_count if self._ziti_adapter else 0

    # Slot 入口

    @Slot(str)
    def handlePinyin(self, s: str) -> None:
        pass

    @Slot()
    def handlePressed(self) -> None:
        self._typing_adapter.handlePressed()

    @Slot(result=bool)
    def toggleTypingPause(self) -> bool:
        return self._typing_adapter.toggleTypingPause()

    @Slot(result=bool)
    def pauseTypingFromWindowDeactivate(self) -> bool:
        return self._typing_adapter.pauseTyping()

    @Slot()
    def accumulateCorrection(self) -> None:
        self._typing_adapter.handleCorrection()

    @Slot()
    def accumulateBackspace(self) -> None:
        self._typing_adapter.handleBackspace()

    @Slot(bool)
    def setLowerPaneFocused(self, focused: bool) -> None:
        self._lower_pane_focused = focused

    @Slot(str, int)
    def handleCommittedText(self, s: str, growLength: int) -> None:
        self._typing_adapter.handleCommittedText(s, growLength)

    @Slot(QQuickTextDocument)
    @Slot(QQuickTextDocument, str)
    def handleLoadedText(self, quickDoc: QQuickTextDocument, text: str = "") -> None:
        self._typing_adapter.handleLoadedText(quickDoc, text)

    @Slot(str)
    def setTextTitle(self, title: str) -> None:
        """设置当前文本标题（用于上传）。"""
        self._typing_adapter.setTextTitle(title)
        self.windowTitleChanged.emit()

    @Slot(int)
    def setTextId(self, text_id: int) -> None:
        """设置当前文本ID（用于成绩提交）。"""
        self._text_id = text_id
        self._typing_adapter.setTextId(text_id if text_id > 0 else None)
        self.textIdChanged.emit()

    @Slot(str, str)
    @Slot(str, str, str)
    def loadFullText(self, text: str, source_key: str = "") -> None:
        """全文载入（不分片），走正常文本加载路径。

        与 setupSliceMode 的区别：不进入 slice_mode，排行榜/成绩正常工作。
        复用 textLoaded 信号链：QML applyLoadedText → handleLoadedText。
        异步回查服务端 text_id 使排行榜可用。
        """
        if not text:
            return
        # 确保退出之前可能的分片模式
        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        # 设置会话状态机
        self._typing_adapter.setup_custom_session(source_key or "custom")
        self.textLoaded.emit(text, -1, "自定义文本")
        # 异步回查服务端 text_id（复用 TextAdapter 的 localTextIdResolved 信号链）
        lookup_key = source_key if source_key else "custom"
        self._text_adapter.lookup_text_id(lookup_key, text)

    @Slot(str)
    def requestLoadText(self, source_key: str) -> None:
        if self._typing_adapter.is_slice_mode():
            return
        self._clear_wenlai_active()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._reset_session_for_standard_load()
        self._pending_standard_source_key = source_key
        self._text_adapter.requestLoadText(source_key)

    @Slot()
    def loadTextFromClipboard(self) -> None:
        # 确保退出之前可能的分片模式
        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_wenlai_active()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._pending_standard_source_key = ""
        self._text_adapter.loadTextFromClipboard()
        # 设置会话状态机
        self._typing_adapter.setup_clipboard_session()

    @Slot(str, str, str, bool, bool)
    def uploadText(
        self, title: str, content: str, sourceKey: str, toLocal: bool, toCloud: bool
    ) -> None:
        """上传文本，支持同时上传到本地和云端。"""
        if not self._upload_text_adapter:
            self.uploadResult.emit(False, "上传功能未初始化", 0)
            return
        self._upload_text_adapter.upload(title, content, sourceKey, toLocal, toCloud)

    @Slot(bool)
    def handleStartStatus(self, status: bool) -> None:
        self._typing_adapter.handleStartStatus(status)

    @Slot(result=bool)
    def isStart(self) -> bool:
        return self._typing_adapter.is_started

    @Slot(result=bool)
    def isReadOnly(self) -> bool:
        return self._typing_adapter.text_read_only

    @Slot(result=int)
    def getCursorPos(self) -> int:
        return self._typing_adapter.cursor_position

    @Slot(int)
    def setCursorPos(self, newPos: int):
        self._typing_adapter.setCursorPosition(newPos)
        self.cursorPosChanged.emit(newPos)

    @Slot(result=str)
    def getScoreMessage(self) -> str:
        return self._typing_adapter.get_score_message()

    @Slot(result=str)
    def getScorePlainText(self) -> str:
        return self._build_current_score_plain_text()

    @Slot()
    def copyScoreMessage(self) -> None:
        self._copy_text_to_clipboard(self._build_current_score_plain_text())

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        self._auth_adapter.login(username, password)

    @Slot(str, str, str)
    def register(self, username: str, password: str, nickname: str = "") -> None:
        self._auth_adapter.register(username, password, nickname)

    @Slot()
    def logout(self) -> None:
        self._auth_adapter.logout()

    def initializeLoginState(self) -> None:
        self._auth_adapter.initialize_login_state()

    @Slot()
    def checkTokenStatus(self) -> None:
        """应用从后台恢复时检查 token 状态。"""
        self._auth_adapter.check_token_status()

    @Slot()
    @Slot(int)
    @Slot(int, str)
    @Slot(int, str, "QVariantMap")
    def loadWeakChars(self, n=10, sortMode="error_rate", weights=None):
        self._char_stats_adapter.loadWeakChars(
            n=n,
            sort_mode=sortMode,
            weights=weights if weights else None,
        )

    @Slot(str)
    def loadLeaderboard(self, source_key: str) -> None:
        """加载指定来源的排行榜。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadLeaderboard(source_key)

    @Slot(int)
    def loadLeaderboardByTextId(self, text_id: int) -> None:
        """按 text_id 直接加载排行榜。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadLeaderboardByTextId(text_id)

    @Slot(str)
    def loadTextList(self, source_key: str) -> None:
        """加载来源下的文本列表。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadTextList(source_key)

    @Slot(int)
    def getTextContentById(self, text_id: int) -> None:
        """按文本 ID 异步获取完整内容。结果通过 textContentLoaded 信号返回。"""
        if not self._leaderboard_adapter:
            return
        self._leaderboard_adapter.get_text_content_by_id(
            text_id,
            lambda data, requested_id=text_id: self._on_text_content_loaded(
                requested_id, data
            ),
        )

    def _on_text_content_loaded(self, text_id: int, data: dict) -> None:
        content = data.get("content", "")
        title = data.get("title", "")
        self.textContentLoaded.emit(text_id, content or "", title or "")

    @Slot(str, result=str)
    def getLocalTextContent(self, source_key: str) -> str:
        """同步读取本地文本内容，供载文 Dialog 离线预览。"""
        return self._text_adapter.get_local_text_content(source_key)

    @Slot()
    def loadCatalog(self) -> None:
        """从服务端加载文本来源目录。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.loadCatalog()

    @Slot()
    def refreshCatalog(self) -> None:
        """清除缓存并重新从服务端加载文本来源目录。"""
        if self._leaderboard_adapter:
            self._leaderboard_adapter.refreshCatalog()

    @Slot()
    def loadLocalArticles(self) -> None:
        """加载本地长文目录。"""
        if self._local_article_adapter:
            self._local_article_adapter.loadLocalArticles()

    @Slot(str, int, int)
    def loadLocalArticleSegment(
        self,
        articleId: str,
        segmentIndex: int,
        segmentSize: int,
    ) -> None:
        """加载本地长文片段。"""
        if not self._local_article_adapter:
            return

        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_wenlai_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()

        # 全文乱序：先打乱全文，再使用文本分片
        if self._pending_slice_params.get("full_shuffle"):
            full_text = self._local_article_adapter.get_full_article_content(articleId)
            if full_text:
                import random

                chars = list(full_text)
                random.shuffle(chars)
                shuffled = "".join(chars)
                p = self._pending_slice_params
                self.setupSliceMode(
                    shuffled,
                    segmentSize,
                    segmentIndex,
                    p["key_stroke_min"],
                    p["speed_min"],
                    p["accuracy_min"],
                    p["pass_count_min"],
                    p["on_fail_action"],
                )
                return

        self._typing_adapter.setup_local_article_session()
        self._source_slice_backend = None
        self._source_slice_article_id = articleId
        self._source_slice_segment_size = segmentSize
        self._local_article_adapter.loadLocalArticleSegment(
            articleId,
            segmentIndex,
            segmentSize,
        )

    @Slot()
    def loadTrainers(self) -> None:
        """加载练单器词库目录。"""
        if self._trainer_adapter:
            self._trainer_adapter.loadTrainers()

    @Slot(str, int, int)
    def loadTrainerSegment(
        self,
        trainerId: str,
        segmentIndex: int,
        groupSize: int,
    ) -> None:
        """加载练单器指定分组。"""
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        self._prepare_for_trainer_load()
        self._source_slice_trainer_id = trainerId
        self._source_slice_group_size = groupSize
        self._trainer_adapter.loadTrainerSegment(
            trainerId,
            segmentIndex,
            groupSize,
            full_shuffle=self._pending_slice_params.get("full_shuffle", False),
        )

    @Slot()
    def loadCurrentTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        self._prepare_for_trainer_load()
        self._trainer_adapter.loadCurrentTrainerSegment()

    @Slot()
    def loadNextTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        self._prepare_for_trainer_load()
        self._trainer_adapter.loadNextTrainerSegment()

    @Slot()
    def loadPreviousTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        self._prepare_for_trainer_load()
        self._trainer_adapter.loadPreviousTrainerSegment()

    @Slot()
    def shuffleCurrentTrainerGroup(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        self._prepare_for_trainer_load()
        self._trainer_adapter.shuffleCurrentTrainerGroup()

    def _prepare_for_trainer_load(self) -> None:
        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_wenlai_active()
        if (
            self._local_article_adapter
            and self._local_article_adapter.local_article_loading
        ):
            self._clear_local_article_active()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        self._typing_adapter.setup_trainer_session()

    @Slot()
    def loadZitiSchemes(self) -> None:
        if self._ziti_adapter:
            self._ziti_adapter.loadSchemes()

    @Slot(str)
    def loadZitiScheme(self, name: str) -> None:
        if self._ziti_adapter:
            self._ziti_adapter.loadScheme(name)

    @Slot(bool)
    def setZitiEnabled(self, enabled: bool) -> None:
        if self._ziti_adapter:
            self._ziti_adapter.setEnabled(enabled)

    @Slot(str, result=str)
    def getZitiHint(self, char: str) -> str:
        if not self._ziti_adapter:
            return ""
        return self._ziti_adapter.get_hint(char)

    @Slot()
    def requestShuffle(self) -> None:
        """乱序当前文本。

        将当前文本的所有字符随机打乱，重置打字状态。
        乱序后的文本不参与排行榜（text_id 清空）。

        分片模式下保持分片状态不变，仅乱序当前片内容。
        """
        if self._typing_adapter.is_slice_mode():
            self.shuffleCurrentSlice()
            return

        result = self._typing_adapter.shuffle_and_prepare()
        if not result:
            return

        shuffled, title = result
        self._clear_wenlai_active()
        self._clear_local_article_active()
        self._clear_trainer_active()
        # 清空 text_id：乱序内容与服务端不匹配，不提交成绩
        self._clear_text_id()
        # 设置会话状态机
        self._typing_adapter.setup_shuffle_session()
        # 发射 textLoaded 信号，QML 侧 applyLoadedText + handleLoadedText 重置打字状态
        self.textLoaded.emit(shuffled, -1, title)

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        """复制文本到剪贴板。"""
        self._copy_text_to_clipboard(text)

    def _copy_text_to_clipboard(self, text: str) -> None:
        if not text:
            return
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    # ==========================================
    # 载文模式
    # ==========================================

    @Property(bool, notify=sliceModeChanged)
    def sliceMode(self) -> bool:
        return self._typing_adapter.is_slice_mode()

    @Property(int, notify=sliceModeChanged)
    def totalSliceCount(self) -> int:
        return self._typing_adapter.slice_total

    @Property(int, notify=sliceModeChanged)
    def sliceIndex(self) -> int:
        return self._typing_adapter.slice_index

    @Property(int, notify=sliceModeChanged)
    def slicePassCount(self) -> int:
        return self._typing_adapter.get_slice_pass_count()

    @Slot(str, int, int, int, int, int, int, str)
    def setupSliceMode(
        self,
        text: str,
        slice_size: int,
        start_slice: int,
        key_stroke_min: int,
        speed_min: int,
        accuracy_min: int,
        pass_count_min: int,
        on_fail_action: str,
    ) -> None:
        """初始化载文模式：分片文本并加载第 start_slice 片。"""
        if not text or slice_size <= 0:
            return

        # 全文乱序：先打乱全文字符，再进入分片
        if self._pending_slice_params.get("full_shuffle"):
            import random

            chars = list(text)
            random.shuffle(chars)
            text = "".join(chars)

        total = self._typing_adapter.setup_slice_mode(
            text=text,
            slice_size=slice_size,
            start_slice=start_slice,
            key_stroke_min=key_stroke_min,
            speed_min=speed_min,
            accuracy_min=accuracy_min,
            pass_count_min=pass_count_min,
            on_fail_action=on_fail_action,
        )

        # 文本型分片模式必须优先清空数据源型后端标记，避免后续重打误走
        # trainer/local_article 分支（会表现为段号不变但内容被外部源替换/乱序）。
        self._source_slice_backend = None
        self._source_slice_article_id = ""
        self._source_slice_segment_size = 0
        self._source_slice_trainer_id = ""
        self._source_slice_group_size = 0

        if total <= 0:
            return

        # 同步参数到 _pending_slice_params，使 loadNextSlice 使用相同的自动推进逻辑
        self._pending_slice_params.update(
            {
                "key_stroke_min": key_stroke_min,
                "speed_min": speed_min,
                "accuracy_min": accuracy_min,
                "pass_count_min": pass_count_min,
                "on_fail_action": on_fail_action,
            }
        )
        self._clear_wenlai_active()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self.sliceModeChanged.emit()
        self._load_current_slice()

    def _load_current_slice(self) -> None:
        """加载当前片到打字区。

        完全复用全文载文的流程：prepare_for_text_load → textLoaded 信号 →
        QML applyLoadedText → handleLoadedText，与 requestShuffle / requestLoadText
        走完全相同的路径。

        注意：不在此处重置达标次数。达标次数的重置由调用方在片段切换时
        负责（同一片段重打应保留累计达标次数）。
        """
        idx = self._typing_adapter.slice_index
        total = self._typing_adapter.slice_total

        if idx <= 0 or idx > total:
            return

        slice_text = self._typing_adapter.get_current_slice_text()
        self._cache_current_content(slice_text)

        # 设置片索引（注入到 historyRecordUpdated 的 record 中）
        self._typing_adapter.set_slice_index(idx)

        # 复用全文载文的 prepare 流程
        self._typing_adapter.prepare_for_text_load()

        # 清空 text_id（分片不提交成绩）
        self._clear_text_id()

        # 发射 textLoaded，QML 侧完成 applyLoadedText + handleLoadedText
        label = f"载文 {idx}/{total}"
        self.sliceStatusChanged.emit(f"载文模式: 第 {idx}/{total} 段")
        self.textLoaded.emit(slice_text, -1, label)

    @Slot()
    def collectSliceResult(self) -> None:
        """收集当前片的 SessionStat 快照。"""
        stats = self._typing_adapter.get_last_slice_stats()
        if not stats:
            return
        self._typing_adapter.collect_slice_result(stats)
        self.sliceStatusChanged.emit(self._typing_adapter.get_slice_status())
        self.sliceModeChanged.emit()  # 更新 slicePassCount 等绑定

    @Slot(result=bool)
    def isLastSlice(self) -> bool:
        return self._typing_adapter.is_last_slice()

    @Slot()
    def loadNextSlice(self) -> None:
        """载入下一片（无尽模式：最后一片后回到第一片）。"""
        if self._pending_slice_params.get("advance_mode") == "random":
            self._load_random_slice()
            return

        total = self._typing_adapter.slice_total
        current = self._typing_adapter.slice_index
        # Circular mode: wrap around
        next_idx = (current % total) + 1 if total > 0 else 1

        backend = self._source_slice_backend
        if backend == "trainer" and self._source_slice_trainer_id:
            self._trainer_adapter.loadTrainerSegment(
                self._source_slice_trainer_id,
                next_idx,
                self._source_slice_group_size,
                full_shuffle=self._pending_slice_params.get("full_shuffle", False),
            )
        elif backend == "local_article":
            self._local_article_adapter.loadLocalArticleSegment(
                self._source_slice_article_id,
                next_idx,
                self._source_slice_segment_size,
            )
        else:
            # 片段切换时重置目标片段的达标次数
            self._typing_adapter.reset_slice_pass_count(next_idx)
            self._typing_adapter.set_slice_index(next_idx)
            self.sliceModeChanged.emit()
            self._load_current_slice()

    @Slot()
    def loadRandomSlice(self) -> None:
        """手动载入一个随机片段（避开当前片）。"""
        if self._typing_adapter.is_slice_mode():
            self._load_random_slice()

    def _load_random_slice(self) -> None:
        """随机载入一片（避开当前片）。"""
        total = self._typing_adapter.slice_total
        if total <= 1:
            return
        current = self._typing_adapter.slice_index
        indices = [i for i in range(1, total + 1) if i != current]
        if not indices:
            return

        import random

        next_idx = random.choice(indices)

        backend = self._source_slice_backend
        if backend == "trainer" and self._source_slice_trainer_id:
            self._trainer_adapter.loadTrainerSegment(
                self._source_slice_trainer_id,
                next_idx,
                self._source_slice_group_size,
                full_shuffle=self._pending_slice_params.get("full_shuffle", False),
            )
        elif backend == "local_article":
            self._local_article_adapter.loadLocalArticleSegment(
                self._source_slice_article_id,
                next_idx,
                self._source_slice_segment_size,
            )
        else:
            # 片段切换时重置目标片段的达标次数
            self._typing_adapter.reset_slice_pass_count(next_idx)
            self._typing_adapter.set_slice_index(next_idx)
            self.sliceModeChanged.emit()
            self._load_current_slice()

    @Slot()
    def loadPrevSlice(self) -> None:
        """载入上一片。"""
        if self._typing_adapter.slice_index <= 1:
            return

        backend = self._source_slice_backend
        if backend == "trainer":
            self._trainer_adapter.loadPreviousTrainerSegment()
        elif backend == "local_article":
            prev_idx = self._typing_adapter.slice_index - 1
            self._local_article_adapter.loadLocalArticleSegment(
                self._source_slice_article_id,
                prev_idx,
                self._source_slice_segment_size,
            )
        else:
            prev_idx = self._typing_adapter.slice_index - 1
            # 片段切换时重置目标片段的达标次数
            self._typing_adapter.reset_slice_pass_count(prev_idx)
            self._typing_adapter.back_slice()
            self.sliceModeChanged.emit()
            self._load_current_slice()

    @Slot(result=bool)
    def shouldRetype(self) -> bool:
        """检查当前片成绩是否触发重打条件。"""
        return self._typing_adapter.should_retype()

    @Slot()
    def handleSliceRetype(self) -> None:
        """根据 on_fail_action 自动处理重打。

        统一路径：
        - shuffle → _shuffle_current_slice（local_article/trainer 各有特化）
        - retype  → 重新从对应后端加载当前段
        - none    → 不处理
        """
        backend = self._source_slice_backend
        current = self._typing_adapter.slice_index
        action = self._typing_adapter.on_fail_action

        if action == "shuffle":
            if backend == "trainer":
                self._trainer_adapter.shuffleCurrentTrainerGroup()
            else:
                self.shuffleCurrentSlice()
            return

        if action == "retype":
            if backend == "trainer":
                self._trainer_adapter.loadCurrentTrainerSegment()
            elif backend == "local_article":
                self._local_article_adapter.loadLocalArticleSegment(
                    self._source_slice_article_id,
                    current,
                    self._source_slice_segment_size,
                )
            else:
                self._reload_current_slice()
            return

        # action == "none" → 不重打

    @Slot(result=str)
    def getOnFailAction(self) -> str:
        """返回当前未达标处理动作（供 QML 查询）。"""
        return self._typing_adapter.on_fail_action

    def _reload_current_slice(self) -> None:
        """重打当前片（原样重新加载）。"""
        self._load_current_slice()

    def _cache_current_content(self, content: str) -> None:
        """将当前段文本写入 session context，供 get_shuffled_slice_text() 统一使用。"""
        self._typing_adapter.set_current_slice_content(content)

    @Slot()
    def shuffleCurrentSlice(self) -> None:
        """乱序当前片并加载。"""
        shuffled = self._typing_adapter.get_shuffled_slice_text()
        if not shuffled:
            return

        idx = self._typing_adapter.slice_index
        total = self._typing_adapter.slice_total
        self._typing_adapter.set_slice_index(idx)
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()
        self.textLoaded.emit(shuffled, -1, f"载文 {idx}/{total}（乱序）")

    @Slot(result=str)
    def buildAggregateScore(self) -> str:
        """计算所有片的聚合成绩，返回 HTML 消息。"""
        data = self._typing_adapter.get_aggregate_data()
        if not data:
            return ""
        slice_stats, slice_count = data
        return self._typing_adapter.build_aggregate_score(slice_stats, slice_count)

    @Slot()
    def copyAggregateScore(self) -> None:
        """复制聚合成绩到剪贴板。"""
        data = self._typing_adapter.get_aggregate_data()
        if not data:
            return
        slice_stats, slice_count = data
        text = self._typing_adapter.copy_aggregate_score(slice_stats, slice_count)
        if text:
            self.copyToClipboard(text)

    @Slot()
    def exitSliceMode(self) -> None:
        """退出载文模式，清理状态。"""
        self._source_slice_backend = None
        self._source_slice_trainer_id = ""
        self._source_slice_group_size = 0
        self._typing_adapter.exit_slice_mode()
        self.sliceModeChanged.emit()
        self.sliceStatusChanged.emit("")

    @Slot(int, int, int, int, str, str, bool)
    def setSliceCriteria(
        self,
        keyStrokeMin: int,
        speedMin: int,
        accuracyMin: int,
        passCountMin: int,
        onFailAction: str,
        advanceMode: str = "sequential",
        fullShuffle: bool = False,
    ) -> None:
        """设置自动推进与乱序参数。"""
        self._pending_slice_params = {
            "key_stroke_min": keyStrokeMin,
            "speed_min": speedMin,
            "accuracy_min": accuracyMin,
            "pass_count_min": passCountMin,
            "on_fail_action": onFailAction,
            "advance_mode": advanceMode,
            "full_shuffle": fullShuffle,
        }

    @Slot(result=str)
    def getSliceStatus(self) -> str:
        """返回当前片进度摘要。"""
        return self._typing_adapter.get_slice_status()

    @Slot(result="QVariantMap")
    def getLastSliceStats(self) -> dict:
        """返回最后一片的成绩快照。"""
        return self._typing_adapter.get_last_slice_stats()

    @Slot(str)
    def setBaseUrl(self, new_base_url: str) -> None:
        """更新 API 服务地址，持久化到配置文件，并同步更新所有依赖对象。"""
        if self._base_url_update_callback:
            self._base_url_update_callback(new_base_url)
        self.baseUrlChanged.emit()

    @Slot(str, str)
    def loginWenlai(self, username: str, password: str) -> None:
        if self._wenlai_adapter:
            self._wenlai_adapter.login(username, password)

    @Slot()
    def logoutWenlai(self) -> None:
        if self._wenlai_adapter:
            self._wenlai_adapter.logout()

    @Slot()
    def loadRandomWenlaiText(self) -> None:
        if not self._wenlai_adapter or self._wenlai_adapter.text_loading:
            return
        self._prepare_for_wenlai_load()
        self._wenlai_adapter.loadRandomText()

    @Slot()
    def loadNextWenlaiSegment(self) -> None:
        if not self._wenlai_adapter or self._wenlai_adapter.text_loading:
            return
        self._prepare_for_wenlai_load()
        self._wenlai_adapter.loadNextSegment()

    @Slot()
    def loadNextWenlaiSegmentWithScore(self) -> None:
        if not self._wenlai_adapter or self._wenlai_adapter.text_loading:
            return
        self._pending_wenlai_score_text = self._build_current_score_plain_text()
        self._copy_text_to_clipboard(self._pending_wenlai_score_text)
        self.loadNextWenlaiSegment()

    @Slot()
    def loadPrevWenlaiSegment(self) -> None:
        if not self._wenlai_adapter or self._wenlai_adapter.text_loading:
            return
        self._prepare_for_wenlai_load()
        self._wenlai_adapter.loadPrevSegment()

    def _prepare_for_wenlai_load(self) -> None:
        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()

    @Slot()
    def refreshWenlaiDifficulties(self) -> None:
        if self._wenlai_adapter:
            self._wenlai_adapter.refreshDifficulties()

    @Slot()
    def refreshWenlaiCategories(self) -> None:
        if self._wenlai_adapter:
            self._wenlai_adapter.refreshCategories()

    @Slot(str, int, int, str, str, bool)
    def updateWenlaiConfig(
        self,
        base_url: str,
        length: int,
        difficulty_level: int,
        category: str,
        segment_mode: str,
        strict_length: bool,
    ) -> None:
        if self._wenlai_adapter:
            self._wenlai_adapter.updateConfig(
                base_url,
                length,
                difficulty_level,
                category,
                segment_mode,
                strict_length,
            )

    # ==========================================
    # 键盘设备选择
    # ==========================================

    keyboardDevicesChanged = Signal()

    @Slot(result="QVariantList")
    def listAvailableInputDevices(self) -> list[dict]:
        """返回设备列表（使用缓存，不触发设备扫描）。"""
        if not self._key_listener:
            return []
        if self._cached_devices is None:
            # 首次访问时执行一次扫描
            self._cached_devices = self._key_listener.get_all_devices()
        return self._apply_device_markers(list(self._cached_devices))

    @Slot()
    def refreshInputDevices(self) -> None:
        """强制重新扫描所有输入设备（用户主动触发，可能阻塞）。"""
        if not self._key_listener:
            return
        self._cached_devices = self._key_listener.get_all_devices()
        self.keyboardDevicesChanged.emit()

    def _apply_device_markers(self, devices: list[dict]) -> list[dict]:
        """给设备列表添加 selected/active 标记（纯内存操作，不触 I/O）。"""
        if not self._key_listener:
            return devices
        selected_paths = self._key_listener.get_selected_device_paths()
        active_paths = self._key_listener.get_active_device_paths()
        has_manual = self._key_listener.has_selected_devices()
        for d in devices:
            d["active"] = d["path"] in active_paths
            if has_manual:
                d["selected"] = d["path"] in selected_paths
            else:
                # 自动发现模式：活动设备显示为已勾选
                d["selected"] = d["active"]
        return devices

    @Property(bool, notify=keyboardDevicesChanged)
    def hasManualKeyboardDevices(self) -> bool:
        """是否已配置手动设备选择。"""
        if not self._key_listener:
            return False
        return self._key_listener.has_selected_devices()

    @Slot("QVariantList")
    def setKeyboardDevices(self, paths: list) -> None:
        """设置手动选择的设备路径并重启监听器。"""
        if not self._key_listener:
            return
        str_paths = [str(p) for p in paths]
        self._key_listener.restart_with_selection(str_paths)
        self.keyboardDevicesChanged.emit()

    @Slot()
    def resetKeyboardAutoDetect(self) -> None:
        """恢复自动发现模式。"""
        if not self._key_listener:
            return
        self._key_listener.restart_auto_detect()
        self.keyboardDevicesChanged.emit()
