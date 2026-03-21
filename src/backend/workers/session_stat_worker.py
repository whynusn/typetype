from ..application.ports.ranking_repository import RankingRepository
from ..models.entity.session_stat import SessionStat
from .base_worker import BaseWorker


class SessionStatWorker(BaseWorker):
    """异步上传成绩到排行榜。"""

    def __init__(
        self,
        session_stat: SessionStat,
        ranking_repository: RankingRepository,
    ):
        self._session_stat = session_stat
        self._ranking_repository = ranking_repository
        super().__init__(task=self._submit_score, error_prefix="提交成绩失败")

    def _submit_score(self) -> bool:
        success = self._ranking_repository.submit_score(self._session_stat)
        if not success:
            raise Exception("提交成绩失败")
        return success
