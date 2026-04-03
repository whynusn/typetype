from ..application.usecases.load_text_usecase import LoadTextUseCase
from .base_worker import BaseWorker


class TextLoadWorker(BaseWorker):
    """文本加载 Worker - 在后台线程执行网络请求。"""

    def __init__(self, load_text_usecase: LoadTextUseCase, source_key: str):
        self._load_text_usecase = load_text_usecase
        self._source_key = source_key
        super().__init__(task=self._load_text, error_prefix="加载文本失败")

    def _load_text(self) -> str:
        """在后台线程中加载文本。"""
        result = self._load_text_usecase.load(self._source_key)
        if result.success:
            return result.text
        raise Exception(result.error_message)
