from ...models.dto.local_article import LocalArticleCatalogItem
from ...ports.local_article_repository import LocalArticleRepository


class LocalArticleGateway:
    """本地长文库应用层网关。"""

    def __init__(self, repository: LocalArticleRepository) -> None:
        self._repository = repository

    def list_articles(self) -> list[LocalArticleCatalogItem]:
        return self._repository.list_articles()

    def get_article(self, article_id: str) -> LocalArticleCatalogItem:
        return self._repository.get_article(article_id)

    def load_content(self, article_id: str) -> str:
        return self._repository.load_article_content(article_id)

    def load_segment_content(self, article_id: str, start: int, length: int) -> str:
        return self._repository.load_article_segment(article_id, start, length)

    def count_chars(self, article_id: str) -> int:
        return self._repository.count_article_chars(article_id)

    def save_current_segment(self, article_id: str, segment_index: int) -> None:
        self._repository.save_current_segment(article_id, segment_index)

    def load_current_segment(self, article_id: str) -> int | None:
        return self._repository.load_current_segment(article_id)

    def resolve_article_path(self, article_id: str) -> str | None:
        return self._repository.resolve_article_path(article_id)

    def delete_article(self, article_id: str) -> bool:
        return self._repository.delete_article(article_id)

    def rename_article(self, article_id: str, new_title: str) -> bool:
        return self._repository.rename_article(article_id, new_title)
