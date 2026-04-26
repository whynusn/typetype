from ...models.dto.local_article import LocalArticleSegment
from ..gateways.local_article_gateway import LocalArticleGateway


class LoadLocalArticleSegmentUseCase:
    """加载本地长文的指定分段。"""

    def __init__(self, gateway: LocalArticleGateway) -> None:
        self._gateway = gateway

    def load_segment(
        self,
        article_id: str,
        *,
        segment_index: int,
        segment_size: int,
    ) -> LocalArticleSegment:
        if segment_size <= 0:
            raise ValueError("segment_size must be greater than 0")

        article = self._gateway.get_article(article_id)
        content = self._gateway.load_content(article_id)
        total = max(1, (len(content) + segment_size - 1) // segment_size)
        index = min(max(segment_index, 1), total)
        start = (index - 1) * segment_size
        end = start + segment_size
        try:
            self._gateway.save_current_segment(article_id, index)
        except OSError:
            pass

        return LocalArticleSegment(
            article_id=article_id,
            title=article.title,
            content=content[start:end],
            index=index,
            total=total,
        )
