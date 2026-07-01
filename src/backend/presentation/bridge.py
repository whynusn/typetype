"""QML 通信适配层。

仅负责：
- 属性代理（QML 属性绑定透传到各个 Adapter）
- 信号转发（Adapter 信号 -> Bridge 信号 -> QML）
- Slot 入口（QML 调用 -> Bridge 调用 -> Adapter）
- 全局键盘监听器持有与转发（Wayland 平台特殊处理）
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQuick import QQuickTextDocument

from ..config.app_paths import user_config_dir
from ..ports.key_codes import KeyCodes
from ..utils.logger import log_info


if TYPE_CHECKING:
    from ..ports.key_listener import KeyListener
    from ..application.gateways.typing_totals_gateway import TypingTotalsGateway
    from ..integration.slice_metrics_prefs_store import SliceMetricsPrefsStore
    from ..integration.text_slice_progress_store import TextSliceProgressStore
    from .adapters.auth_adapter import AuthAdapter
    from .adapters.char_stats_adapter import CharStatsAdapter
    from .adapters.leaderboard_adapter import LeaderboardAdapter
    from .adapters.local_article_adapter import LocalArticleAdapter
    from .adapters.text_adapter import TextAdapter
    from .adapters.trainer_adapter import TrainerAdapter
    from .adapters.typing_adapter import TypingAdapter
    from .adapters.upload_text_adapter import UploadTextAdapter
    from .adapters.wenlai_adapter import WenlaiAdapter
    from .adapters.font_adapter import FontAdapter
    from .adapters.ziti_adapter import ZitiAdapter

from .text_load_coordinator import TextLoadCoordinator


def _compute_progress_key(key_type: str, identifier: str) -> str:
    """统一的进度 key 生成。key_type: "local_article" / "trainer" / "custom_text"。"""
    if key_type == "local_article":
        return f"__local_article__:{identifier}"
    if key_type == "trainer":
        return f"__trainer__:{identifier}"
    return (
        f"__custom_text__:{hashlib.sha256(identifier.encode('utf-8')).hexdigest()[:16]}"
    )


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
    textFileLoaded = Signal(str)  # 文件导入：预览内容
    textFilePathLoaded = Signal(str)  # 文件导入：文件路径（用于上传）
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
    textTitleChanged = Signal()
    typingTotalsChanged = Signal()
    textIdLookupFailed = Signal()  # 本地 text_id 回查失败
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
    localArticleDeleted = Signal(bool, str)
    localArticleRenamed = Signal(bool, str)
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
    # 字体信号
    fontsLoaded = Signal(list)
    fontsLoadFailed = Signal(str)
    fontAdded = Signal(bool, str)
    fontRemoved = Signal(bool, str)
    readerFontPathChanged = Signal()
    readerFontUrlChanged = Signal(str)

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
        font_adapter: FontAdapter | None = None,
        typing_totals_gateway: TypingTotalsGateway | None = None,
        key_listener: KeyListener | None = None,
        base_url_update_callback: Callable[[str], None] | None = None,
        slice_metrics_prefs_store: "SliceMetricsPrefsStore | None" = None,
        text_slice_progress_store: "TextSliceProgressStore | None" = None,
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
        self._font_adapter = font_adapter
        self._typing_totals_gateway = typing_totals_gateway
        self._key_listener = key_listener
        self._base_url_update_callback = base_url_update_callback
        self._slice_metrics_prefs_store = slice_metrics_prefs_store
        self._text_slice_progress_store = text_slice_progress_store
        self._is_special_platform = key_listener is not None
        self._lower_pane_focused = False
        self._text_id = 0
        self._pending_history_segment_label = ""
        self._pending_history_score_text = ""
        self._pending_restored_progress: dict | None = None
        self._pending_restore_key: str = ""
        self._current_shuffle_seed: int | None = None
        self._progress_key_text: str = ""  # 全文乱序前的原文，用于进度存储 key
        self._progress_key_override: str = ""  # 显式覆盖进度 key（如本地文库全文乱序）
        self._cached_devices: list[dict] | None = None
        self._reader_font_path = self._load_reader_font_path()

        # 载文协调器
        self._coordinator = TextLoadCoordinator(
            typing_adapter=typing_adapter,
            text_adapter=text_adapter,
            wenlai_adapter=wenlai_adapter,
            local_article_adapter=local_article_adapter,
            trainer_adapter=trainer_adapter,
        )

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
        self._connect_font_signals()
        self._connect_key_listener()

        self.specialPlatformConfirmed.emit(self._is_special_platform)
        log_info(f"[Bridge] 检测到平台特殊性: {self._is_special_platform}")

    def _clear_text_id(self) -> None:
        """清空 text_id（分片/乱序/自定义文本不提交成绩）。"""
        self._coordinator.clear_text_id(self)

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
        self._coordinator.reset_session_for_standard_load(self)

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
        elif self._wenlai_adapter and self._wenlai_adapter.is_active:
            self._pending_history_segment_label = self.wenlaiSegmentLabel
        else:
            text_id = self._text_id
            self._pending_history_segment_label = (
                str(text_id) if text_id and text_id > 0 else "1"
            )
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
        # 普通模式：使用文本ID作为段号（如果有）
        text_id = self._text_id
        if text_id and text_id > 0:
            return f"第{text_id}段"
        # 回退
        return "第1段"

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
        self._text_adapter.localTextIdLookupFailed.connect(self.textIdLookupFailed.emit)

    def _on_standard_text_loaded(
        self, text: str, text_id: int, source_label: str
    ) -> None:
        self._coordinator.on_standard_text_loaded(text, text_id, source_label, self)

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
            self._on_local_article_segment_load_failed
        )
        self._local_article_adapter.localArticleLoadingChanged.connect(
            self.localArticleLoadingChanged.emit
        )
        self._local_article_adapter.localArticleDeleted.connect(
            self.localArticleDeleted.emit
        )
        self._local_article_adapter.localArticleRenamed.connect(
            self.localArticleRenamed.emit
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
            self._on_trainer_segment_load_failed
        )
        self._trainer_adapter.trainerLoadingChanged.connect(
            self.trainerLoadingChanged.emit
        )

    def _connect_font_signals(self) -> None:
        if not self._font_adapter:
            return
        self._font_adapter.fontsLoaded.connect(self.fontsLoaded.emit)
        self._font_adapter.fontsLoadFailed.connect(self.fontsLoadFailed.emit)
        self._font_adapter.fontAdded.connect(self.fontAdded.emit)
        self._font_adapter.fontRemoved.connect(self.fontRemoved.emit)

    def _on_trainer_segment_loaded(self, payload: dict) -> None:
        self._coordinator.on_trainer_segment_loaded(payload, self)
        self._restore_pending_progress()
        self._update_progress_current_slice()

    def _on_trainer_segment_load_failed(self, message: str) -> None:
        self._pending_restored_progress = None
        self.trainerSegmentLoadFailed.emit(message)

    def _on_local_article_segment_loaded(self, payload: dict) -> None:
        self._coordinator.on_local_article_segment_loaded(payload, self)
        self._restore_pending_progress()
        self._update_progress_current_slice()

    def _on_local_article_segment_load_failed(self, message: str) -> None:
        self._pending_restored_progress = None
        self.localArticleSegmentLoadFailed.emit(message)

    def _restore_pending_progress(self) -> None:
        """source-based 路径恢复历史进度（达标次数 + per-slice 指标）。

        不删除存储中的进度条目——由 collectSliceResult 在用户完成一段后自然覆盖。
        这样即使用户继续进度后未完成一段就关闭应用，进度也不会丢失。
        """
        if not self._pending_restored_progress:
            return
        ctx = self._typing_adapter._session_context
        if not ctx:
            self._pending_restored_progress = None
            return
        rp = self._pending_restored_progress
        saved_counts = rp.get("slice_pass_counts")
        if saved_counts:
            for i, count in enumerate(saved_counts):
                if i < len(ctx._slice_pass_counts):
                    ctx._slice_pass_counts[i] = count
        # 恢复 per-slice 指标
        saved_slice_metrics = rp.get("slice_metrics")
        if saved_slice_metrics:
            # 保存端截断到 slice_index（性能优化），恢复端逐条覆盖 + 默认值填充
            for i, m in enumerate(saved_slice_metrics):
                if i < len(ctx._slice_metrics):
                    ctx._slice_metrics[i] = m.copy() if isinstance(m, dict) else m
            ctx.restore_slice_metrics(ctx.slice_index)
        # 恢复成绩快照（用于 get_slice_status / check_slice_result 显示历史成绩）
        saved_slice_stats = rp.get("slice_stats")
        if saved_slice_stats and ctx._slice_stats is not None:
            # 初始化 _slice_stats 到正确大小，用 None 填充，再用保存值覆盖
            while len(ctx._slice_stats) < ctx.slice_total:
                ctx._slice_stats.append(None)
            for i, s in enumerate(saved_slice_stats):
                if i < ctx.slice_total:
                    ctx._slice_stats[i] = s
        self._pending_restore_key = ""
        self._pending_restored_progress = None

    def _on_wenlai_config_changed(self) -> None:
        self.wenlaiConfigChanged.emit()
        self.wenlaiSegmentLabelChanged.emit()
        self.windowTitleChanged.emit()

    def _on_wenlai_load_failed(self, message: str) -> None:
        self._coordinator.pending_wenlai_score_text = ""
        self.wenlaiLoadFailed.emit(message)

    def _on_wenlai_text_loaded(self, text: str, title: str) -> None:
        self._coordinator.on_wenlai_text_loaded(text, title, self)

    def _connect_key_listener(self) -> None:
        if self._key_listener:
            self._key_listener.keyPressed.connect(self.on_key_received)

    def on_key_received(self, keyCode: int, deviceName: str) -> None:
        if not self._lower_pane_focused or KeyCodes.is_modifier(keyCode):
            return

        # 导航键（方向键/Home/End/PgUp/PgDn/Insert/Delete）不产生文本，
        # 不应影响码长（key_stroke_count）和击键统计
        if KeyCodes.is_navigation(keyCode):
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

    @Property(str, notify=textTitleChanged)
    def textTitle(self) -> str:
        return self._typing_adapter.text_title

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

    @Property(float, notify=charNumChanged)
    def typingProgress(self) -> float:
        return self._typing_adapter.typing_progress

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
        self.textTitleChanged.emit()

    @Slot(int)
    def setTextId(self, text_id: int) -> None:
        """设置当前文本ID（用于成绩提交）。"""
        self._text_id = text_id
        self._typing_adapter.setTextId(text_id if text_id > 0 else None)
        self.textIdChanged.emit()

    @Slot(str, str)
    @Slot(str, str, str)
    @Slot(str, str, str, int)
    def loadFullText(
        self, text: str, source_key: str = "", title: str = "", text_id: int = 0
    ) -> None:
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
        if text_id > 0:
            self._text_id = text_id
            self._typing_adapter.setTextId(text_id)
            self.textIdChanged.emit()
        # 设置会话状态机
        self._typing_adapter.setup_custom_session(source_key or "custom")
        display_title = title if title else "自定义文本"
        self._typing_adapter.setTextTitle(display_title)
        self.windowTitleChanged.emit()
        sender = TextLoadCoordinator._build_local_sender_content(
            display_title, text, index=text_id if text_id > 0 else 0,
        )
        if sender:
            self._copy_text_to_clipboard(sender)
        self.textLoaded.emit(text, text_id if text_id > 0 else -1, display_title)
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
        self._coordinator.pending_standard_source_key = source_key
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
        self._coordinator.pending_standard_source_key = ""
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

    @Slot(str, str, str, bool, bool)
    def uploadTextFromFile(
        self, title: str, filePath: str, sourceKey: str, toLocal: bool, toCloud: bool
    ) -> None:
        """从文件路径上传文本。

        本地上传：直接复制文件（不经过内存）
        云端上传：multipart/form-data 分块传输
        """
        if not self._upload_text_adapter:
            self.uploadResult.emit(False, "上传功能未初始化", 0)
            return
        self._upload_text_adapter.upload_from_file(
            title, filePath, sourceKey, toLocal, toCloud
        )

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

    @Slot(str)
    def deleteLocalArticle(self, article_id: str) -> None:
        """删除本地长文。"""
        if self._local_article_adapter:
            self._local_article_adapter.deleteArticle(article_id)

    @Slot(str, str)
    def renameLocalArticle(self, article_id: str, new_title: str) -> None:
        """重命名本地长文。"""
        if self._local_article_adapter:
            self._local_article_adapter.renameArticle(article_id, new_title)

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

        # 入口页已通过 prepareSliceProgressRestore 设置了待恢复进度，使用保存的分片索引
        if self._pending_restored_progress:
            saved_slice = self._pending_restored_progress.get("current_slice", 1)
            saved_total = self._pending_restored_progress.get("total_slices", 0)
            if 1 <= saved_slice <= saved_total:
                segmentIndex = saved_slice

        if self._typing_adapter.is_slice_mode():
            self.exitSliceMode()
        self._clear_wenlai_active()
        self._clear_trainer_active()
        self._typing_adapter.prepare_for_text_load()
        self._clear_text_id()

        # 全文乱序：通过 TextSessionUseCase.shuffle_all_virtual 统一处理
        full_shuffle = self._coordinator.pending_slice_params.pop("full_shuffle", False)

        file_path = self._local_article_adapter.resolve_article_path(articleId)
        if file_path:
            from pathlib import Path

            stat = Path(file_path).stat()
            version = f"{stat.st_size}:{stat.st_mtime}"
            title = self._local_article_adapter.get_article_title(articleId)
            from src.backend.models.dto.text_session import TextKind

            result = self._text_adapter.startFileTextSession(
                file_path=file_path,
                kind=TextKind.LOCAL_ARTICLE,
                identifier=articleId,
                title=title,
                version=version,
                slice_size=segmentSize,
                start_slice=segmentIndex,
            )
            if result is None:
                return

            # 全文乱序：通过 UseCase 统一处理（小文本全量 shuffle，大文本 Feistel）
            # 保留 _pending_restored_progress 以便后续 _restore_pending_progress 使用
            saved_progress = self._pending_restored_progress
            if full_shuffle:
                import random

                saved_seed = None
                if saved_progress:
                    saved_seed = saved_progress.get("shuffle_seed")
                if saved_seed is None:
                    saved_seed = random.randint(0, 2**31 - 1)
                usecase = self._text_adapter.text_session_usecase
                if usecase:
                    shuffled_usecase = usecase.shuffle_all_virtual(saved_seed)
                    self._text_adapter._text_session_usecase = shuffled_usecase
                    result = shuffled_usecase.get_segment(segmentIndex, segmentSize)
                self._current_shuffle_seed = saved_seed
                if saved_progress:
                    saved_progress["shuffle_seed"] = saved_seed
                self._progress_key_override = _compute_progress_key(
                    "local_article", articleId
                )

            # 设置分片模式（自动推进、重打、指标等依赖此状态）
            p = self._coordinator.pending_slice_params
            title_label = title
            if result.total > 1:
                title_label = (
                    f"{title} {result.index}/{result.total}"
                    if title
                    else f"{result.index}/{result.total}"
                )
            self._typing_adapter.setTextTitle(title_label)
            self.windowTitleChanged.emit()
            self._coordinator._cache_current_content(result.content)
            self._coordinator.source_slice_backend = "local_article"
            self._coordinator.source_slice_article_id = articleId
            self._coordinator.source_slice_segment_size = segmentSize
            self._coordinator._visited_slices.clear()
            self._typing_adapter.setup_sourced_slice_mode(
                result.index,
                result.total,
                slice_size=segmentSize,
                on_fail_action=p["on_fail_action"],
                key_stroke_min=p["key_stroke_min"],
                speed_min=p["speed_min"],
                accuracy_min=p["accuracy_min"],
                pass_count_min=p["pass_count_min"],
                reset_counts=True,
                auto_decrease_enabled=p.get("auto_decrease_enabled", False),
                key_stroke_decrease=p.get("key_stroke_decrease", 0.0),
                speed_decrease=p.get("speed_decrease", 0),
                accuracy_decrease=p.get("accuracy_decrease", 0),
            )
            # 恢复进度（达标次数 + per-slice 指标）
            self._pending_restored_progress = saved_progress
            self._restore_pending_progress()
            self._update_progress_current_slice()
            self.sliceModeChanged.emit()
            self.textLoaded.emit(result.content, -1, title_label)
        else:
            self._typing_adapter.setup_local_article_session()
            self._coordinator.source_slice_backend = None
            self._coordinator.source_slice_article_id = articleId
            self._coordinator._visited_slices.clear()
            self._coordinator.source_slice_segment_size = segmentSize
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

        # 入口页已通过 prepareSliceProgressRestore 设置了待恢复进度，使用保存的分片索引
        if self._pending_restored_progress:
            saved_slice = self._pending_restored_progress.get("current_slice", 1)
            saved_total = self._pending_restored_progress.get("total_slices", 0)
            if 1 <= saved_slice <= saved_total:
                segmentIndex = saved_slice

        self._prepare_for_trainer_load()
        self._coordinator.source_slice_trainer_id = trainerId
        self._coordinator.source_slice_group_size = groupSize
        self._coordinator._visited_slices.clear()

        # 全文乱序 seed 管理：恢复进度时用保存的 seed，否则生成新 seed
        full_shuffle = self._coordinator.pending_slice_params.get("full_shuffle", False)
        seed = None
        if full_shuffle:
            import random

            saved_seed = None
            if self._pending_restored_progress:
                saved_seed = self._pending_restored_progress.get("shuffle_seed")
            if saved_seed is not None:
                seed = saved_seed
            else:
                seed = random.randint(0, 2**31 - 1)
            self._current_shuffle_seed = seed

        self._trainer_adapter.loadTrainerSegment(
            trainerId,
            segmentIndex,
            groupSize,
            full_shuffle=full_shuffle,
            seed=seed,
        )

    @Slot()
    def loadCurrentTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        if self._coordinator.source_slice_backend != "trainer":
            self._prepare_for_trainer_load()
        self._trainer_adapter.loadCurrentTrainerSegment()

    @Slot()
    def loadNextTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        if self._coordinator.source_slice_backend != "trainer":
            self._prepare_for_trainer_load()
        self._trainer_adapter.loadNextTrainerSegment()

    @Slot()
    def loadPreviousTrainerSegment(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        if self._coordinator.source_slice_backend != "trainer":
            self._prepare_for_trainer_load()
        self._trainer_adapter.loadPreviousTrainerSegment()

    @Slot()
    def shuffleCurrentTrainerGroup(self) -> None:
        if not self._trainer_adapter or self._trainer_adapter.trainer_loading:
            return
        if self._coordinator.source_slice_backend != "trainer":
            self._prepare_for_trainer_load()
        self._trainer_adapter.shuffleCurrentTrainerGroup()

    def _prepare_for_trainer_load(self) -> None:
        self._coordinator.prepare_for_trainer_load(self)

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

    @Slot(str, str, str, str, str, int, int)
    def startFileTextSession(
        self,
        file_path: str,
        kind: str,
        identifier: str,
        title: str,
        version: str,
        slice_size: int,
        start_slice: int = 1,
    ) -> None:
        """统一文件型载文入口：通过 FileSegmentProvider 创建会话并加载第一段。"""
        from src.backend.models.dto.text_session import TextKind

        if not file_path or slice_size <= 0:
            return

        self._typing_adapter.prepare_for_text_load()
        self._coordinator.clear_text_id(self)
        result = self._text_adapter.startFileTextSession(
            file_path=file_path,
            kind=TextKind(kind),
            identifier=identifier,
            title=title,
            version=version,
            slice_size=slice_size,
            start_slice=start_slice,
        )
        if result is not None:
            label = title
            if result.total > 1:
                label = (
                    f"{title} {result.index}/{result.total}"
                    if title
                    else f"{result.index}/{result.total}"
                )
            self.textLoaded.emit(result.content, -1, label)

    @Slot(str, int, int, float, int, int, int, str, bool, float, int, int, str)
    @Slot(str, int, int, float, int, int, int, str, bool, float, int, int, str, str)
    def setupSliceMode(
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
        restored_progress: str = "",
        title: str = "",
    ) -> None:
        """初始化载文模式：分片文本并加载第 start_slice 片。"""
        if not text or slice_size <= 0:
            return

        # 仅使用入口页显式传入的已恢复进度（不自动从存储恢复）
        progress_dict = None
        if restored_progress:
            try:
                progress_dict = json.loads(restored_progress)
            except (json.JSONDecodeError, TypeError):
                progress_dict = None

        # 保存乱序前的原文用于进度存储 key（全文乱序后 _slice_text 是乱序文本）
        self._progress_key_text = text

        # 全文乱序：恢复进度时用保存的 seed 复现同一排列，否则生成新 seed
        if self._coordinator.pending_slice_params.get("full_shuffle"):
            import random

            seed = (progress_dict or {}).get("shuffle_seed")
            if seed is None:
                seed = random.randint(0, 2**31 - 1)
            rng = random.Random(seed)
            chars = list(text)
            rng.shuffle(chars)
            text = "".join(chars)
            self._current_shuffle_seed = seed
            if progress_dict is not None:
                progress_dict["shuffle_seed"] = seed

        self._apply_slice_setup(
            text,
            slice_size,
            start_slice,
            key_stroke_min,
            speed_min,
            accuracy_min,
            pass_count_min,
            on_fail_action,
            auto_decrease_enabled,
            key_stroke_decrease,
            speed_decrease,
            accuracy_decrease,
            progress_dict,
            title,
        )

    def _apply_slice_setup(
        self,
        text: str,
        slice_size: int,
        start_slice: int,
        key_stroke_min: float,
        speed_min: int,
        accuracy_min: int,
        pass_count_min: int,
        on_fail_action: str,
        auto_decrease_enabled: bool,
        key_stroke_decrease: float,
        speed_decrease: int,
        accuracy_decrease: int,
        restored_progress: dict | None,
        title: str = "",
    ) -> None:
        """实际执行分片设置（被 setupSliceMode 调用）。"""
        effective_start_slice = start_slice
        if restored_progress:
            saved_slice = restored_progress.get("current_slice", 1)
            saved_total = restored_progress.get("total_slices", 0)
            if saved_slice > 1 and saved_slice <= saved_total:
                effective_start_slice = saved_slice

        # 保存进度时的指标（可能含降击值），用于恢复 per-slice 数据
        saved_metrics = (
            restored_progress.get("metrics", {}) if restored_progress else {}
        )
        saved_slice_metrics = (
            restored_progress.get("slice_metrics") if restored_progress else None
        )

        # 用原始用户指标初始化 per-slice 列表（确保未访问片段保持原始值）
        total = self._typing_adapter.setup_slice_mode(
            text=text,
            slice_size=slice_size,
            start_slice=effective_start_slice,
            key_stroke_min=key_stroke_min,
            speed_min=speed_min,
            accuracy_min=accuracy_min,
            pass_count_min=pass_count_min,
            on_fail_action=on_fail_action,
            auto_decrease_enabled=auto_decrease_enabled,
            key_stroke_decrease=key_stroke_decrease,
            speed_decrease=speed_decrease,
            accuracy_decrease=accuracy_decrease,
        )

        # 文本型分片模式必须优先清空数据源型后端标记
        self._coordinator.source_slice_backend = None
        self._coordinator.source_slice_article_id = ""
        self._coordinator.source_slice_segment_size = 0
        self._coordinator.source_slice_trainer_id = ""
        self._coordinator.source_slice_group_size = 0
        self._coordinator._source_slice_title = title
        if title:
            self._typing_adapter.setTextTitle(title)
            self.windowTitleChanged.emit()

        if total <= 0:
            return

        # 恢复历史达标次数和指标配置
        if restored_progress:
            ctx = self._typing_adapter._session_context
            if not ctx:
                return
            if restored_progress.get("slice_pass_counts"):
                saved_counts = restored_progress["slice_pass_counts"]
                for i, count in enumerate(saved_counts):
                    if i < len(ctx._slice_pass_counts):
                        ctx._slice_pass_counts[i] = count
            # 恢复保存时的标量指标（含降击值）
            if saved_metrics:
                ctx._apply_metrics_dict(saved_metrics)
            # 恢复 per-slice 指标（已访问片段的降击历史）
            if saved_slice_metrics:
                # 保存端截断到 slice_index（性能优化），恢复端逐条覆盖 + 默认值填充
                for i, m in enumerate(saved_slice_metrics):
                    if i < len(ctx._slice_metrics):
                        ctx._slice_metrics[i] = m.copy() if isinstance(m, dict) else m
                ctx.restore_slice_metrics(ctx.slice_index)
            # 恢复成绩快照（用于 get_slice_status / check_slice_result 显示历史成绩）
            saved_slice_stats = restored_progress.get("slice_stats")
            if saved_slice_stats and ctx._slice_stats is not None:
                while len(ctx._slice_stats) < ctx.slice_total:
                    ctx._slice_stats.append(None)
                for i, s in enumerate(saved_slice_stats):
                    if i < ctx.slice_total:
                        ctx._slice_stats[i] = s

        # 同步参数到 pending_slice_params，使 loadNextSlice 使用相同的自动推进逻辑
        self._coordinator.pending_slice_params.update(
            {
                "key_stroke_min": key_stroke_min,
                "speed_min": speed_min,
                "accuracy_min": accuracy_min,
                "pass_count_min": pass_count_min,
                "on_fail_action": on_fail_action,
                "auto_decrease_enabled": auto_decrease_enabled,
                "key_stroke_decrease": key_stroke_decrease,
                "speed_decrease": speed_decrease,
                "accuracy_decrease": accuracy_decrease,
            }
        )
        self._clear_wenlai_active()
        self._clear_local_article_active()
        self._clear_trainer_active()
        self._coordinator._visited_slices.clear()
        self.sliceModeChanged.emit()
        self._load_current_slice()

    def _load_current_slice(self) -> None:
        self._coordinator.load_current_slice(self)

    @Slot()
    def collectSliceResult(self) -> None:
        """收集当前片的 SessionStat 快照。"""
        stats = self._typing_adapter.get_last_slice_stats()
        log_info(
            f"[collectSliceResult] stats={stats is not None} "
            f"store={self._text_slice_progress_store is not None} "
            f"slice_mode={self._typing_adapter.is_slice_mode()} "
            f"backend={self._coordinator.source_slice_backend}"
        )
        if not stats:
            return
        self._typing_adapter.collect_slice_result(stats)
        self.sliceStatusChanged.emit(self._typing_adapter.get_slice_status())
        self.sliceModeChanged.emit()

        if self._text_slice_progress_store and self._typing_adapter.is_slice_mode():
            from datetime import datetime

            ctx = self._typing_adapter._session_context
            if ctx:
                # source-based 路径（本地文库、练单器）始终使用后端标识作为进度 key，
                # 不受全文乱序影响。_progress_key_override 用于全文乱序本地文库路径
                # （source_slice_backend 为 None 但需要使用 local_article 前缀 key）。
                if self._progress_key_override:
                    text = self._progress_key_override
                elif self._coordinator.source_slice_backend == "local_article":
                    text = _compute_progress_key(
                        "local_article", self._coordinator.source_slice_article_id
                    )
                elif self._coordinator.source_slice_backend == "trainer":
                    text = _compute_progress_key(
                        "trainer", self._coordinator.source_slice_trainer_id
                    )
                else:
                    # text-based 路径：使用乱序前原文（如有）生成稳定的 key
                    raw = self._progress_key_text or ctx._slice_text
                    text = _compute_progress_key("custom_text", raw)
                if not text:
                    return
                title = self._typing_adapter.text_title
                # 保存下一片索引（用户正在打的片），而非刚完成的片
                next_slice = (
                    (ctx.slice_index % ctx.slice_total) + 1
                    if ctx.slice_total > 0
                    else ctx.slice_index
                )
                progress = {
                    "last_accessed": datetime.now().isoformat(),
                    "total_slices": ctx.slice_total,
                    "current_slice": next_slice,
                    "slice_size": ctx._slice_size if hasattr(ctx, "_slice_size") else 0,
                    "slice_pass_counts": list(ctx._slice_pass_counts),
                    "slice_stats": list(ctx._slice_stats),
                    "metrics": {
                        "key_stroke_min": ctx._key_stroke_min,
                        "speed_min": ctx._speed_min,
                        "accuracy_min": ctx._accuracy_min,
                        "pass_count_min": ctx._pass_count_min,
                        "on_fail_action": ctx.on_fail_action,
                        "auto_decrease_enabled": ctx.auto_decrease_enabled,
                        "key_stroke_decrease": ctx._key_stroke_decrease,
                        "speed_decrease": ctx._speed_decrease,
                        "accuracy_decrease": ctx._accuracy_decrease,
                    },
                    "advance_mode": self._coordinator.pending_slice_params.get(
                        "advance_mode", "sequential"
                    ),
                    "slice_metrics": [
                        m.copy() for m in ctx._slice_metrics[: ctx.slice_index]
                    ],
                    "shuffle_seed": self._current_shuffle_seed,
                }
                log_info(
                    f"[collectSliceResult] saving key={text[:40]}... title={title}"
                )
                self._text_slice_progress_store.save_progress(text, title, progress)

    @Slot(result=bool)
    def isLastSlice(self) -> bool:
        return self._typing_adapter.is_last_slice()

    def _save_current_slice_if_needed(self) -> None:
        """段落切换前，若当前段有未保存的成绩则先保存。"""
        if self._typing_adapter.get_last_slice_stats():
            self.collectSliceResult()

    def _update_progress_current_slice(self) -> None:
        """片切换后，更新已保存进度的 current_slice 为当前正在打的片。"""
        if (
            not self._text_slice_progress_store
            or not self._typing_adapter.is_slice_mode()
        ):
            return
        ctx = self._typing_adapter._session_context
        if not ctx:
            return
        if self._progress_key_override:
            key = self._progress_key_override
        elif self._coordinator.source_slice_backend == "local_article":
            key = _compute_progress_key(
                "local_article", self._coordinator.source_slice_article_id
            )
        elif self._coordinator.source_slice_backend == "trainer":
            key = _compute_progress_key(
                "trainer", self._coordinator.source_slice_trainer_id
            )
        else:
            raw = self._progress_key_text or ctx._slice_text
            key = _compute_progress_key("custom_text", raw)
        entry, hash_key = self._find_progress(key)
        if entry and hash_key:
            entry["current_slice"] = ctx.slice_index
            self._text_slice_progress_store.save_progress(
                key, entry.get("text_title", ""), entry
            )

    @Slot()
    def loadNextSlice(self) -> None:
        """载入下一片（无尽模式：最后一片后回到第一片）。"""
        self._save_current_slice_if_needed()
        self._coordinator.load_next_slice(self)
        self._update_progress_current_slice()

    @Slot()
    def loadRandomSlice(self) -> None:
        """手动载入一个随机片段（避开当前片）。"""
        if self._typing_adapter.is_slice_mode():
            self._save_current_slice_if_needed()
            self._coordinator.load_random_slice(self)
            self._update_progress_current_slice()

    def _load_random_slice(self) -> None:
        self._save_current_slice_if_needed()
        self._coordinator.load_random_slice(self)
        self._update_progress_current_slice()

    @Slot()
    def loadPrevSlice(self) -> None:
        """载入上一片。"""
        self._save_current_slice_if_needed()
        self._coordinator.load_prev_slice(self)
        self._update_progress_current_slice()

    @Slot(result=bool)
    def shouldRetype(self) -> bool:
        """检查当前片成绩是否触发重打条件。"""
        return self._typing_adapter.should_retype()

    @Slot()
    def handleSliceRetype(self) -> None:
        """根据 on_fail_action 自动处理重打（含降击）。"""
        if self._typing_adapter.auto_decrease_enabled:
            self._typing_adapter.decrease_metrics_on_fail()
            self.sliceModeChanged.emit()
        self._coordinator.handle_slice_retype(self)

    @Slot()
    def handleSliceRetypeNoDecrease(self) -> None:
        """重打当前片，不触发降击（连达标未满场景）。"""
        self._coordinator.handle_slice_retype(self)

    @Slot(result=str)
    def checkSliceResult(self) -> str:
        """检查当前片结果：'fail'（未达标）/ 'pass'（达标但连达标未满）/ 'advance'（可推进）。"""
        return self._typing_adapter.check_slice_result()

    @Slot(result=str)
    def getOnFailAction(self) -> str:
        """返回当前未达标处理动作（供 QML 查询）。"""
        return self._typing_adapter.on_fail_action

    def _find_progress(
        self, progressKey: str, title: str = ""
    ) -> tuple[dict | None, str]:
        """查找进度条目，返回 (entry, hash_key)。

        hash_key 是 JSON 文件中的 SHA-256 hex key，可直接用于 delete_by_hash_key。
        优先按 progressKey 直接查找，找不到时按标题前缀回退扫描（兼容旧格式 key）。
        多条匹配时取 last_accessed 最新的条目。
        """
        if not self._text_slice_progress_store:
            return None, ""
        store = self._text_slice_progress_store
        data = store.load()
        hash_key = hashlib.sha256(progressKey.encode("utf-8")).hexdigest()
        entry = data.get(hash_key)
        if isinstance(entry, dict):
            log_info(
                f"[_find_progress] hash HIT: key={progressKey[:40]} "
                f"title={entry.get('text_title')} seed={entry.get('shuffle_seed')}"
            )
            return entry, hash_key
        # 回退：按标题前缀扫描（兼容旧格式 key），取最新条目
        if title:
            best: dict | None = None
            best_key = ""
            for key, item in data.items():
                if isinstance(item, dict) and item.get("text_title", "").startswith(
                    title
                ):
                    if best is None or item.get("last_accessed", "") > best.get(
                        "last_accessed", ""
                    ):
                        best = item
                        best_key = key
            if best is not None:
                log_info(
                    f"[_find_progress] title SCAN: key={progressKey[:40]} "
                    f"found={best.get('text_title')} seed={best.get('shuffle_seed')} "
                    f"last_accessed={best.get('last_accessed')}"
                )
                return best, best_key
        log_info(f"[_find_progress] MISS: key={progressKey[:40]} title={title}")
        return None, ""

    @Slot(str, str, result=bool)
    def hasSliceProgress(self, progressKey: str, title: str = "") -> bool:
        """同步查询指定 key 是否有保存的分片进度。title 用于旧格式回退查找。"""
        entry, _ = self._find_progress(progressKey, title)
        return entry is not None

    @Slot(str, str, result=str)
    def getSliceProgressInfo(self, progressKey: str, title: str = "") -> str:
        """返回 JSON 格式的进度详情，供入口页弹窗展示。无进度时返回空字符串。"""
        progress, _ = self._find_progress(progressKey, title)
        if not progress:
            return ""
        metrics = progress.get("metrics", {})
        saved_slice_idx = progress.get("current_slice", 1) - 1
        pass_counts = progress.get("slice_pass_counts", [])
        info = {
            "saved_slice": progress.get("current_slice", 1),
            "saved_total": progress.get("total_slices", 0),
            "saved_title": progress.get("text_title", ""),
            "slice_size": progress.get("slice_size", 0),
            "advance_mode": progress.get(
                "advance_mode",
                self._coordinator.pending_slice_params.get(
                    "advance_mode", "sequential"
                ),
            ),
            "last_accessed": progress.get("last_accessed", ""),
            "current_pass_count": pass_counts[saved_slice_idx]
            if 0 <= saved_slice_idx < len(pass_counts)
            else 0,
            "saved_pass_count_min": metrics.get("pass_count_min", 1),
            "saved_ks": metrics.get("key_stroke_min", 0),
            "saved_spd": metrics.get("speed_min", 0),
            "saved_acc": metrics.get("accuracy_min", 0),
            "saved_onfail": metrics.get("on_fail_action", "retype"),
        }
        return json.dumps(info, ensure_ascii=False)

    @Slot(str, str, result=str)
    def getProgressKey(self, keyType: str, identifier: str) -> str:
        """统一的进度 key 生成入口（供 QML 调用）。"""
        return _compute_progress_key(keyType, identifier)

    @Slot(result=str)
    def getRestoredSliceSettings(self) -> str:
        """返回已恢复进度的完整设置 JSON，供 _startWithCriteria 使用。

        包含 slice_size, advance_mode, full_shuffle, 以及各项达标指标。
        无待恢复进度时返回空 JSON 对象 "{}"。
        """
        if not self._pending_restored_progress:
            return "{}"
        p = self._pending_restored_progress
        metrics = p.get("metrics", {})
        settings = {
            "slice_size": p.get("slice_size", 0),
            "advance_mode": p.get("advance_mode", "sequential"),
            "full_shuffle": p.get("shuffle_seed") is not None,
            "condition_on": bool(
                metrics.get("key_stroke_min", 0)
                or metrics.get("speed_min", 0)
                or metrics.get("accuracy_min", 0)
                or metrics.get("on_fail_action", "none") != "none"
            ),
            "key_stroke_min": metrics.get("key_stroke_min", 0),
            "speed_min": metrics.get("speed_min", 0),
            "accuracy_min": metrics.get("accuracy_min", 0),
            "pass_count_min": metrics.get("pass_count_min", 1),
            "on_fail_action": metrics.get("on_fail_action", "none"),
            "auto_decrease_enabled": metrics.get("auto_decrease_enabled", False),
            "key_stroke_decrease": metrics.get("key_stroke_decrease", 0.0),
            "speed_decrease": metrics.get("speed_decrease", 0),
            "accuracy_decrease": metrics.get("accuracy_decrease", 0),
        }
        return json.dumps(settings, ensure_ascii=False)

    @Slot()
    def clearPendingRestore(self) -> None:
        """清除待恢复进度状态（非恢复流程开始时调用，防止旧数据残留）。"""
        self._pending_restored_progress = None
        self._pending_restore_key = ""

    @Slot(str, bool, str, result=str)
    def applySliceProgressRestore(
        self, progressKey: str, restore: bool, title: str = ""
    ) -> str:
        """处理入口页弹窗结果。

        restore=True 时返回保存的进度 JSON（供 setupSliceMode 使用），
        不删除进度——由 collectSliceResult 在用户完成一段后自然覆盖。
        restore=False 时删除进度并返回空字符串（用户主动放弃进度）。
        """
        progress, actual_key = self._find_progress(progressKey, title)
        log_info(
            f"[applySliceProgressRestore] key={progressKey[:40]} restore={restore} "
            f"found={progress is not None} "
            f"title={progress.get('text_title') if progress else None} "
            f"seed={progress.get('shuffle_seed') if progress else None}"
        )
        if restore:
            if progress:
                return json.dumps(progress, ensure_ascii=False)
            return ""
        else:
            if actual_key and self._text_slice_progress_store:
                self._text_slice_progress_store.delete_by_hash_key(actual_key)
            return ""

    @Slot(str, str)
    def prepareSliceProgressRestore(self, progressKey: str, title: str = "") -> None:
        """从存储读取进度并设置 _pending_restored_progress，供 loader 恢复。"""
        progress, actual_key = self._find_progress(progressKey, title)
        log_info(
            f"[prepareSliceProgressRestore] key={progressKey[:40]} "
            f"found={progress is not None} "
            f"title={progress.get('text_title') if progress else None} "
            f"seed={progress.get('shuffle_seed') if progress else None} "
            f"slice={progress.get('current_slice') if progress else None}/{progress.get('total_slices') if progress else None}"
        )
        if progress:
            self._pending_restored_progress = progress
            self._pending_restore_key = actual_key
            # 同时覆盖 pending_slice_params 中的指标为保存的值
            p = self._coordinator.pending_slice_params
            saved_metrics = progress.get("metrics", {})
            if saved_metrics:
                p["key_stroke_min"] = saved_metrics.get(
                    "key_stroke_min", p["key_stroke_min"]
                )
                p["speed_min"] = saved_metrics.get("speed_min", p["speed_min"])
                p["accuracy_min"] = saved_metrics.get("accuracy_min", p["accuracy_min"])
                p["pass_count_min"] = saved_metrics.get(
                    "pass_count_min", p["pass_count_min"]
                )
                p["on_fail_action"] = saved_metrics.get(
                    "on_fail_action", p["on_fail_action"]
                )
                p["auto_decrease_enabled"] = saved_metrics.get(
                    "auto_decrease_enabled", p.get("auto_decrease_enabled", False)
                )
                p["key_stroke_decrease"] = saved_metrics.get(
                    "key_stroke_decrease", p.get("key_stroke_decrease", 0.0)
                )
                p["speed_decrease"] = saved_metrics.get(
                    "speed_decrease", p.get("speed_decrease", 0)
                )
                p["accuracy_decrease"] = saved_metrics.get(
                    "accuracy_decrease", p.get("accuracy_decrease", 0)
                )
            # 恢复 advance_mode 和 full_shuffle
            saved_advance = progress.get("advance_mode")
            if saved_advance:
                p["advance_mode"] = saved_advance
            if progress.get("shuffle_seed") is not None:
                p["full_shuffle"] = True

    def _reload_current_slice(self) -> None:
        self._coordinator.load_current_slice(self)

    def _cache_current_content(self, content: str) -> None:
        self._typing_adapter.set_current_slice_content(content)

    @Slot()
    def shuffleCurrentSlice(self) -> None:
        """乱序当前片并加载。"""
        self._coordinator.shuffle_current_slice(self)

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
        self._progress_key_text = ""
        self._progress_key_override = ""
        self._current_shuffle_seed = None
        self._coordinator.exit_slice_mode(self)

    @Slot(float, int, int, int, str, str, bool, bool, float, int, int)
    def setSliceCriteria(
        self,
        keyStrokeMin: float,
        speedMin: int,
        accuracyMin: int,
        passCountMin: int,
        onFailAction: str,
        advanceMode: str = "sequential",
        fullShuffle: bool = False,
        autoDecreaseEnabled: bool = False,
        keyStrokeDecrease: float = 0.0,
        speedDecrease: int = 0,
        accuracyDecrease: int = 0,
    ) -> None:
        """设置自动推进与乱序参数。"""
        self._coordinator.pending_slice_params = {
            "key_stroke_min": keyStrokeMin,
            "speed_min": speedMin,
            "accuracy_min": accuracyMin,
            "pass_count_min": passCountMin,
            "on_fail_action": onFailAction,
            "advance_mode": advanceMode,
            "full_shuffle": fullShuffle,
            "auto_decrease_enabled": autoDecreaseEnabled,
            "key_stroke_decrease": keyStrokeDecrease,
            "speed_decrease": speedDecrease,
            "accuracy_decrease": accuracyDecrease,
        }

    @Slot(result="QVariantMap")
    def loadSliceMetricsPrefs(self) -> dict:
        if self._slice_metrics_prefs_store:
            return self._slice_metrics_prefs_store.load()
        return {}

    @Slot(float, int, int, int, str, bool, float, int, int)
    def saveSliceMetricsPrefs(
        self,
        keyStrokeMin: float,
        speedMin: int,
        accuracyMin: int,
        passCountMin: int,
        onFailAction: str,
        autoDecreaseEnabled: bool,
        keyStrokeDecrease: float,
        speedDecrease: int,
        accuracyDecrease: int,
    ) -> None:
        if self._slice_metrics_prefs_store:
            self._slice_metrics_prefs_store.save(
                {
                    "key_stroke_min": keyStrokeMin,
                    "speed_min": speedMin,
                    "accuracy_min": accuracyMin,
                    "pass_count_min": passCountMin,
                    "on_fail_action": onFailAction,
                    "auto_decrease_enabled": autoDecreaseEnabled,
                    "key_stroke_decrease": keyStrokeDecrease,
                    "speed_decrease": speedDecrease,
                    "accuracy_decrease": accuracyDecrease,
                }
            )

    @Slot(str, result="QVariantMap")
    def getTextSliceProgress(self, text: str) -> dict:
        if self._text_slice_progress_store:
            result = self._text_slice_progress_store.get_progress(text)
            return result if result else {}
        return {}

    @Slot(str, str, "QVariantMap")
    def saveTextSliceProgress(self, text: str, title: str, progress: dict) -> None:
        if self._text_slice_progress_store:
            self._text_slice_progress_store.save_progress(text, title, progress)

    @Slot(result=str)
    def getSliceStatus(self) -> str:
        """返回当前片进度摘要。"""
        return self._typing_adapter.get_slice_status()

    @Slot(result=str)
    def getSliceCriteria(self) -> str:
        """返回当前达标条件文字（含降击后更新）。"""
        if self._typing_adapter.is_slice_mode():
            ctx = self._typing_adapter._session_context
            if ctx:
                ks = ctx._key_stroke_min
                spd = ctx._speed_min
                acc = ctx._accuracy_min
                pc = ctx._pass_count_min
                return f"击键≥{ks:.2f}  速度≥{spd}  键准≥{acc}%  达标≥{pc}次"
        return ""

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
        self._coordinator.pending_wenlai_score_text = (
            self._build_current_score_plain_text()
        )
        self._copy_text_to_clipboard(self._coordinator.pending_wenlai_score_text)
        self.loadNextWenlaiSegment()

    @Slot()
    def loadPrevWenlaiSegment(self) -> None:
        if not self._wenlai_adapter or self._wenlai_adapter.text_loading:
            return
        self._prepare_for_wenlai_load()
        self._wenlai_adapter.loadPrevSegment()

    def _prepare_for_wenlai_load(self) -> None:
        self._coordinator.prepare_for_wenlai_load(self)

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
    # 字体管理
    # ==========================================

    @Property(str, notify=readerFontPathChanged)
    def readerFontPath(self) -> str:
        """当前阅读字体的文件路径，供 QML FontLoader 使用。"""
        return self._reader_font_path

    @Slot(str)
    def setReaderFontPath(self, file_path: str) -> None:
        if self._reader_font_path == file_path:
            return
        self._reader_font_path = file_path
        self._save_reader_font_path(file_path)
        self.readerFontPathChanged.emit()
        from PySide6.QtCore import QUrl

        font_url = QUrl.fromLocalFile(file_path).toString() if file_path else ""
        self.readerFontUrlChanged.emit(font_url)

    @Slot()
    def loadFonts(self) -> None:
        if self._font_adapter:
            self._font_adapter.loadFonts()

    @Slot(str)
    def addFont(self, file_path: str) -> None:
        if self._font_adapter:
            self._font_adapter.addFont(file_path)

    @Slot(str)
    def removeFont(self, name: str) -> None:
        if not self._font_adapter:
            return

        # 原子操作：若删除的是当前字体，先切换到其它可用字体再删除
        entries = self._font_adapter.list_fonts()
        target = next((e for e in entries if e.name == name), None)
        if target and target.file_path == self._reader_font_path:
            fallback = next(
                (e for e in entries if e.file_path != target.file_path), None
            )
            if fallback:
                self.setReaderFontPath(fallback.file_path)

        self._font_adapter.removeFont(name)

    @Slot()
    def openFontFileDialog(self) -> None:
        """打开系统文件对话框选择字体文件。"""
        from PySide6.QtWidgets import QFileDialog

        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("字体文件 (*.ttf *.otf)")
        dialog.setWindowTitle("选择字体文件")
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                self.addFont(files[0])

    @Slot()
    def openTextFileDialog(self) -> None:
        """打开系统文件对话框导入文本文件。只读取前 20 行用于预览，上传时直接传输文件。"""
        from PySide6.QtWidgets import QFileDialog

        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("文本文件 (*.txt)")
        dialog.setWindowTitle("导入文本文件")
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                file_path = files[0]
                try:
                    # 只读取前 20 行 / 前 4096 字节用于预览（防止单行大文件炸内存）
                    preview_lines = []
                    byte_count = 0
                    max_preview_bytes = 4096
                    with open(file_path, encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if i >= 20:
                                preview_lines.append("... [仅显示前 20 行预览]")
                                break
                            line_bytes = len(line.encode("utf-8"))
                            if byte_count + line_bytes > max_preview_bytes:
                                preview_lines.append(
                                    "... [预览截断，上传时传输完整文件]"
                                )
                                break
                            preview_lines.append(line.rstrip("\n\r"))
                            byte_count += line_bytes

                    preview = "\n".join(preview_lines)
                    self.textFileLoaded.emit(preview)
                    self.textFilePathLoaded.emit(file_path)
                except OSError:
                    self.textFileLoaded.emit("")
                    self.textFilePathLoaded.emit("")

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

    # ==========================================
    # 字体配置持久化
    # ==========================================

    @staticmethod
    def _font_config_path() -> str:
        import os

        return os.path.join(str(user_config_dir()), "font_config.json")

    def _load_reader_font_path(self) -> str:
        import json
        import os

        path = self._font_config_path()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("reader_font_path", "")
            except (json.JSONDecodeError, OSError):
                pass
        return ""

    def _save_reader_font_path(self, file_path: str) -> None:
        import json
        import os

        path = self._font_config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {"reader_font_path": file_path}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
