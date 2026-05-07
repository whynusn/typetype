"""依赖装配工厂。

提供 dataclass 包和工厂函数，将 main.py 中的手动依赖创建逻辑集中管理。
main.py 是唯一调用方；此模块不应被其他模块导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .app_paths import (
    char_stats_db_path,
    ensure_user_fonts_seeded,
    ensure_user_texts_seeded,
    ensure_user_trainer_seeded,
    ensure_user_ziti_seeded,
    load_common_chars,
    typing_totals_path,
    user_fonts_dir,
    user_texts_dir,
    user_trainer_dir,
    user_ziti_dir,
)
from .runtime_config import RuntimeConfig
from ..utils.logger import log_info

if TYPE_CHECKING:
    from ..application.gateways.local_article_gateway import LocalArticleGateway
    from ..application.gateways.score_gateway import ScoreGateway
    from ..application.gateways.text_source_gateway import TextSourceGateway
    from ..application.gateways.trainer_gateway import TrainerGateway
    from ..application.gateways.typing_totals_gateway import TypingTotalsGateway
    from ..application.gateways.wenlai_gateway import WenlaiGateway
    from ..application.gateways.ziti_gateway import ZitiGateway
    from ..application.usecases.load_local_article_segment_usecase import (
        LoadLocalArticleSegmentUseCase,
    )
    from ..application.usecases.load_text_usecase import LoadTextUseCase
    from ..application.usecases.load_trainer_segment_usecase import (
        LoadTrainerSegmentUseCase,
    )
    from ..application.usecases.load_wenlai_text_usecase import LoadWenlaiTextUseCase
    from ..domain.services.auth_service import AuthService
    from ..domain.services.char_stats_service import CharStatsService
    from ..domain.services.typing_service import TypingService
    from ..infrastructure.api_client import ApiClient
    from ..integration.api_client_auth_provider import ApiClientAuthProvider
    from ..integration.api_client_score_submitter import ApiClientScoreSubmitter
    from ..integration.file_local_article_repository import FileLocalArticleRepository
    from ..integration.file_trainer_repository import FileTrainerRepository
    from ..integration.file_ziti_repository import FileZitiRepository
    from ..integration.leaderboard_fetcher import LeaderboardFetcher
    from ..integration.qt_local_text_loader import QtLocalTextLoader
    from ..integration.remote_text_provider import RemoteTextProvider
    from ..integration.secure_token_store import SecureTokenStore
    from ..integration.text_uploader import TextUploader
    from ..integration.wenlai_provider import WenlaiProvider
    from ..ports.key_listener import KeyListener
    from ..presentation.adapters.auth_adapter import AuthAdapter
    from ..presentation.adapters.char_stats_adapter import CharStatsAdapter
    from ..presentation.adapters.font_adapter import FontAdapter
    from ..presentation.adapters.leaderboard_adapter import LeaderboardAdapter
    from ..presentation.adapters.local_article_adapter import LocalArticleAdapter
    from ..presentation.adapters.text_adapter import TextAdapter
    from ..presentation.adapters.trainer_adapter import TrainerAdapter
    from ..presentation.adapters.typing_adapter import TypingAdapter
    from ..presentation.adapters.upload_text_adapter import UploadTextAdapter
    from ..presentation.adapters.wenlai_adapter import WenlaiAdapter
    from ..presentation.adapters.ziti_adapter import ZitiAdapter


# ---------------------------------------------------------------------------
# Dataclass bundles
# ---------------------------------------------------------------------------


@dataclass
class Infra:
    api_client: ApiClient
    wenlai_api_client: ApiClient
    local_text_loader: QtLocalTextLoader
    token_store: SecureTokenStore


@dataclass
class Repos:
    local_article: FileLocalArticleRepository
    ziti: FileZitiRepository
    trainer: FileTrainerRepository


@dataclass
class Providers:
    text: RemoteTextProvider
    wenlai: WenlaiProvider


@dataclass
class Gateways:
    score: ScoreGateway
    text_source: TextSourceGateway
    wenlai: WenlaiGateway
    local_article: LocalArticleGateway
    ziti: ZitiGateway
    trainer: TrainerGateway
    typing_totals: TypingTotalsGateway


@dataclass
class UseCases:
    load_text: LoadTextUseCase
    load_wenlai_text: LoadWenlaiTextUseCase
    load_local_article_segment: LoadLocalArticleSegmentUseCase
    load_trainer_segment: LoadTrainerSegmentUseCase


@dataclass
class Services:
    char_stats: CharStatsService
    typing: TypingService
    auth: AuthService
    auth_provider: ApiClientAuthProvider  # URL 更新链路需要
    score_submitter: ApiClientScoreSubmitter
    text_uploader: TextUploader
    leaderboard_fetcher: LeaderboardFetcher  # URL 更新链路需要


@dataclass
class Adapters:
    typing: TypingAdapter
    text: TextAdapter
    auth: AuthAdapter
    char_stats: CharStatsAdapter
    wenlai: WenlaiAdapter
    local_article: LocalArticleAdapter
    ziti: ZitiAdapter
    trainer: TrainerAdapter
    font: FontAdapter
    leaderboard: LeaderboardAdapter
    upload_text: UploadTextAdapter
    key_listener: KeyListener | None


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def create_infra(runtime_config: RuntimeConfig) -> Infra:
    from ..infrastructure.api_client import ApiClient
    from ..integration.qt_local_text_loader import QtLocalTextLoader
    from ..integration.secure_token_store import SecureTokenStore
    from ..application.gateways.wenlai_gateway import WenlaiGateway

    api_client = ApiClient(timeout=runtime_config.api_timeout)
    wenlai_api_client = ApiClient(timeout=runtime_config.api_timeout)
    local_text_loader = QtLocalTextLoader()
    token_store = SecureTokenStore()
    # 预读 token 到缓存
    token_store.get_token("current_user")
    token_store.get_token(WenlaiGateway.TOKEN_KEY)
    return Infra(
        api_client=api_client,
        wenlai_api_client=wenlai_api_client,
        local_text_loader=local_text_loader,
        token_store=token_store,
    )


def create_repos() -> Repos:
    from ..integration.file_local_article_repository import FileLocalArticleRepository
    from ..integration.file_ziti_repository import FileZitiRepository
    from ..integration.file_trainer_repository import FileTrainerRepository

    bundled_texts_dir = _PROJECT_ROOT / "resources" / "texts"
    return Repos(
        local_article=FileLocalArticleRepository(
            user_texts_dir(), bundled_source_dir=bundled_texts_dir
        ),
        ziti=FileZitiRepository(user_ziti_dir()),
        trainer=FileTrainerRepository(user_trainer_dir()),
    )


def create_providers(runtime_config: RuntimeConfig, infra: Infra) -> Providers:
    from ..integration.remote_text_provider import RemoteTextProvider
    from ..integration.wenlai_provider import WenlaiProvider
    from ..application.gateways.wenlai_gateway import WenlaiGateway

    def _get_jwt_token() -> str:
        return infra.token_store.get_token("current_user") or ""

    def _get_wenlai_token() -> str:
        return infra.token_store.get_token(WenlaiGateway.TOKEN_KEY) or ""

    return Providers(
        text=RemoteTextProvider(
            base_url=runtime_config.base_url,
            api_client=infra.api_client,
            token_provider=_get_jwt_token,
        ),
        wenlai=WenlaiProvider(
            api_client=infra.wenlai_api_client,
            base_url=runtime_config.wenlai.base_url,
            token_provider=_get_wenlai_token,
        ),
    )


def create_gateways(
    runtime_config: RuntimeConfig,
    providers: Providers,
    infra: Infra,
    repos: Repos,
    clipboard: Any,
) -> Gateways:
    from ..application.gateways.score_gateway import ScoreGateway
    from ..application.gateways.text_source_gateway import TextSourceGateway
    from ..application.gateways.wenlai_gateway import WenlaiGateway
    from ..application.gateways.local_article_gateway import LocalArticleGateway
    from ..application.gateways.ziti_gateway import ZitiGateway
    from ..application.gateways.trainer_gateway import TrainerGateway
    from ..application.gateways.typing_totals_gateway import TypingTotalsGateway
    from ..integration.json_typing_totals_store import JsonTypingTotalsStore

    return Gateways(
        score=ScoreGateway(clipboard=clipboard),
        text_source=TextSourceGateway(
            runtime_config=runtime_config,
            text_provider=providers.text,
            local_text_loader=infra.local_text_loader,
        ),
        wenlai=WenlaiGateway(
            runtime_config=runtime_config,
            provider=providers.wenlai,
            token_store=infra.token_store,
        ),
        local_article=LocalArticleGateway(repository=repos.local_article),
        ziti=ZitiGateway(repository=repos.ziti),
        trainer=TrainerGateway(repository=repos.trainer),
        typing_totals=TypingTotalsGateway(
            store=JsonTypingTotalsStore(typing_totals_path())
        ),
    )


def create_use_cases(gateways: Gateways, repos: Repos, clipboard: Any) -> UseCases:
    from ..application.usecases.load_text_usecase import LoadTextUseCase
    from ..application.usecases.load_wenlai_text_usecase import LoadWenlaiTextUseCase
    from ..application.usecases.load_local_article_segment_usecase import (
        LoadLocalArticleSegmentUseCase,
    )
    from ..application.usecases.load_trainer_segment_usecase import (
        LoadTrainerSegmentUseCase,
    )
    from ..domain.services.trainer_service import TrainerService

    trainer_service = TrainerService(repository=repos.trainer)
    return UseCases(
        load_text=LoadTextUseCase(
            text_gateway=gateways.text_source,
            clipboard_reader=clipboard,
        ),
        load_wenlai_text=LoadWenlaiTextUseCase(gateway=gateways.wenlai),
        load_local_article_segment=LoadLocalArticleSegmentUseCase(
            gateway=gateways.local_article,
        ),
        load_trainer_segment=LoadTrainerSegmentUseCase(service=trainer_service),
    )


def create_services(infra: Infra, runtime_config: RuntimeConfig) -> Services:
    from ..domain.services.char_stats_service import CharStatsService
    from ..domain.services.typing_service import TypingService
    from ..domain.services.auth_service import AuthService
    from ..integration.api_client_auth_provider import ApiClientAuthProvider
    from ..integration.api_client_score_submitter import ApiClientScoreSubmitter
    from ..integration.text_uploader import TextUploader
    from ..integration.leaderboard_fetcher import LeaderboardFetcher
    from ..integration.qt_async_executor import QtAsyncExecutor
    from ..integration.sqlite_char_stats_repository import SqliteCharStatsRepository

    # CharStats
    async_executor = QtAsyncExecutor()
    char_stats_repo = SqliteCharStatsRepository(db_path=str(char_stats_db_path()))
    char_stats_service = CharStatsService(
        repository=char_stats_repo,
        async_executor=async_executor,
    )
    common_chars = load_common_chars()
    if common_chars:
        char_stats_service.warm_chars(common_chars)

    typing_service = TypingService(char_stats_service=char_stats_service)

    # Auth
    auth_provider = ApiClientAuthProvider(
        api_client=infra.api_client,
        login_url=f"{runtime_config.base_url}/api/v1/auth/login",
        validate_url=f"{runtime_config.base_url}/api/v1/users/me",
        refresh_url=f"{runtime_config.base_url}/api/v1/auth/refresh",
        register_url=f"{runtime_config.base_url}/api/v1/auth/register",
    )
    auth_service = AuthService(auth_provider=auth_provider)

    # Score submitter
    score_submitter = ApiClientScoreSubmitter(
        api_client=infra.api_client,
        submit_url=f"{runtime_config.base_url}/api/v1/scores",
        token_provider=lambda: infra.token_store.get_token("current_user") or "",
    )

    # Text uploader
    text_uploader = TextUploader(
        api_client=infra.api_client,
        upload_url=f"{runtime_config.base_url}/api/v1/texts/upload",
        token_provider=lambda: infra.token_store.get_token("current_user") or "",
    )

    # Leaderboard fetcher
    leaderboard_fetcher = LeaderboardFetcher(
        api_client=infra.api_client,
        base_url=runtime_config.base_url,
        token_provider=lambda: infra.token_store.get_token("current_user") or "",
    )

    return Services(
        char_stats=char_stats_service,
        typing=typing_service,
        auth=auth_service,
        auth_provider=auth_provider,
        score_submitter=score_submitter,
        text_uploader=text_uploader,
        leaderboard_fetcher=leaderboard_fetcher,
    )


def create_adapters(
    services: Services,
    gateways: Gateways,
    use_cases: UseCases,
    infra: Infra,
    runtime_config: RuntimeConfig,
) -> Adapters:
    from ..application.session_context import TypingSessionContext
    from ..integration.file_font_repository import FileFontRepository
    from ..integration.system_identifier import SystemIdentifier
    from ..integration.key_listener_factory import create_key_listener
    from ..integration.global_key_listener import GlobalKeyListener
    from ..integration.mac_key_listener import MacKeyListener
    from ..presentation.adapters.typing_adapter import TypingAdapter
    from ..presentation.adapters.text_adapter import TextAdapter
    from ..presentation.adapters.auth_adapter import AuthAdapter
    from ..presentation.adapters.char_stats_adapter import CharStatsAdapter
    from ..presentation.adapters.wenlai_adapter import WenlaiAdapter
    from ..presentation.adapters.local_article_adapter import LocalArticleAdapter
    from ..presentation.adapters.ziti_adapter import ZitiAdapter
    from ..presentation.adapters.trainer_adapter import TrainerAdapter
    from ..presentation.adapters.font_adapter import FontAdapter
    from ..presentation.adapters.leaderboard_adapter import LeaderboardAdapter
    from ..presentation.adapters.upload_text_adapter import UploadTextAdapter
    from ..application.gateways.font_gateway import FontGateway
    from ..application.gateways.leaderboard_gateway import LeaderboardGateway

    # Session context
    session_context = TypingSessionContext()

    # Adapters
    typing_adapter = TypingAdapter(
        typing_service=services.typing,
        score_gateway=gateways.score,
        score_submitter=services.score_submitter,
        session_context=session_context,
    )
    text_adapter = TextAdapter(
        runtime_config=runtime_config,
        load_text_usecase=use_cases.load_text,
        local_text_loader=infra.local_text_loader,
    )
    auth_adapter = AuthAdapter(auth_service=services.auth)
    char_stats_adapter = CharStatsAdapter(char_stats_service=services.char_stats)
    wenlai_adapter = WenlaiAdapter(
        gateway=gateways.wenlai,
        load_usecase=use_cases.load_wenlai_text,
    )
    local_article_adapter = LocalArticleAdapter(
        gateway=gateways.local_article,
        load_segment_usecase=use_cases.load_local_article_segment,
    )
    ziti_adapter = ZitiAdapter(gateway=gateways.ziti)
    trainer_adapter = TrainerAdapter(
        gateway=gateways.trainer,
        load_segment_usecase=use_cases.load_trainer_segment,
    )

    # Font management
    bundled_fonts_dir = str(_PROJECT_ROOT / "resources" / "fonts")
    font_repository = FileFontRepository(
        user_dir=str(user_fonts_dir()),
        bundled_dir=bundled_fonts_dir,
    )
    font_gateway = FontGateway(repository=font_repository)
    font_adapter = FontAdapter(gateway=font_gateway)

    # Leaderboard
    leaderboard_gateway = LeaderboardGateway(
        leaderboard_provider=services.leaderboard_fetcher,
    )
    leaderboard_adapter = LeaderboardAdapter(
        leaderboard_gateway=leaderboard_gateway,
        runtime_config=runtime_config,
    )

    # Upload text
    upload_text_adapter = UploadTextAdapter(text_uploader=services.text_uploader)

    # Platform detection + key listener
    system_identifier = SystemIdentifier()
    os_type, display_server = system_identifier.get_system_info()
    log_info(f"系统: {os_type} 平台: {display_server}")

    key_listener = create_key_listener(
        os_type=os_type,
        display_server=display_server,
        linux_listener_factory=GlobalKeyListener,
        macos_listener_factory=MacKeyListener,
    )
    if key_listener:
        log_info("因系统平台特殊性，全局监听器已启动")

    return Adapters(
        typing=typing_adapter,
        text=text_adapter,
        auth=auth_adapter,
        char_stats=char_stats_adapter,
        wenlai=wenlai_adapter,
        local_article=local_article_adapter,
        ziti=ziti_adapter,
        trainer=trainer_adapter,
        font=font_adapter,
        leaderboard=leaderboard_adapter,
        upload_text=upload_text_adapter,
        key_listener=key_listener,
    )


def ensure_app_initialized() -> None:
    """确保用户可写配置文件和种子数据存在。"""
    config_path = RuntimeConfig.ensure_user_config_exists()
    log_info(f"[main] 用户配置文件: {config_path}")
    for label, seeder in [
        ("本地文库文本", ensure_user_texts_seeded),
        ("字提示方案", ensure_user_ziti_seeded),
        ("练单器词库", ensure_user_trainer_seeded),
        ("字体文件", ensure_user_fonts_seeded),
    ]:
        copied = seeder()
        if copied:
            log_info(f"[main] 已初始化{label}: {copied} 个文件")
