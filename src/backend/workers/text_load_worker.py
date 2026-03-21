from ..application.usecases.load_text_usecase import LoadTextUseCase
from .base_worker import BaseWorker


class TextLoadWorker(BaseWorker):
    """后台执行文本加载，避免阻塞 UI 线程。"""

    def __init__(self, load_text_usecase: LoadTextUseCase, source_key: str):
        self._load_text_usecase = load_text_usecase
        self._source_key = source_key
        super().__init__(task=self._load_text, error_prefix="加载文本失败")

    def _load_text(self) -> str:
        result = self._load_text_usecase.load(self._source_key)
        if result.success:
            return result.text
        raise Exception(result.error_message)
