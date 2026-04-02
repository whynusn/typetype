from ..application.usecases.load_text_usecase import LoadTextUseCase
from ..models.config.text_source_config import TextSourceEntry
from .base_worker import BaseWorker


class TextLoadWorker(BaseWorker):
    def __init__(self, load_text_usecase: LoadTextUseCase, source: TextSourceEntry):
        self._load_text_usecase = load_text_usecase
        self._source = source
        super().__init__(task=self._load_text, error_prefix="加载文本失败")

    def _load_text(self) -> str:
        result = self._load_text_usecase.load_from_source(self._source)
        if result.success:
            return result.text
        raise Exception(result.error_message)
