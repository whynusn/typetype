from ..application.usecases.text_usecase import TextUseCase
from .base_worker import BaseWorker


class LoadTextWorker(BaseWorker):
    """后台执行网络载文，避免阻塞 UI 线程。"""

    def __init__(self, text_usecase: TextUseCase, url: str):
        self._text_usecase = text_usecase
        self._url = url
        super().__init__(task=self._load_text, error_prefix="加载文本失败")

    def _load_text(self) -> str | None:
        return self._text_usecase.load_text_from_network(self._url)
