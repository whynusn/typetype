from unittest.mock import MagicMock

import pytest

from src.backend.application.gateways.local_article_gateway import LocalArticleGateway
from src.backend.application.usecases.load_local_article_segment_usecase import (
    LoadLocalArticleSegmentUseCase,
)
from src.backend.models.dto.local_article import LocalArticleCatalogItem


def test_gateway_delegates_to_repository():
    repository = MagicMock()
    repository.list_articles.return_value = [
        LocalArticleCatalogItem(
            article_id="article-1",
            title="标题",
            path="/tmp/article.txt",
            char_count=4,
            modified_timestamp=1.0,
        )
    ]
    gateway = LocalArticleGateway(repository)

    assert gateway.list_articles()[0].title == "标题"
    gateway.save_current_segment("article-1", 2)
    assert (
        gateway.load_current_segment("article-1")
        == repository.load_current_segment.return_value
    )
    assert (
        gateway.load_segment_content("article-1", 4, 2)
        == repository.load_article_segment.return_value
    )
    assert (
        gateway.count_chars("article-1") == repository.count_article_chars.return_value
    )
    repository.save_current_segment.assert_called_once_with("article-1", 2)
    repository.load_article_segment.assert_called_once_with("article-1", 4, 2)
    repository.count_article_chars.assert_called_once_with("article-1")


def test_load_segment_returns_one_based_segment_metadata():
    gateway = MagicMock()
    gateway.get_article.return_value = LocalArticleCatalogItem(
        article_id="article-1",
        title="长文",
        path="/tmp/article.txt",
        char_count=10,
        modified_timestamp=1.0,
    )
    gateway.count_chars.return_value = 10
    gateway.load_segment_content.return_value = "efgh"
    usecase = LoadLocalArticleSegmentUseCase(gateway)

    result = usecase.load_segment("article-1", segment_index=2, segment_size=4)

    assert result.article_id == "article-1"
    assert result.title == "长文"
    assert result.content == "efgh"
    assert result.index == 2
    assert result.total == 3
    gateway.load_segment_content.assert_called_once_with("article-1", 4, 4)
    gateway.save_current_segment.assert_called_once_with("article-1", 2)


def test_load_segment_clamps_index_to_available_range():
    gateway = MagicMock()
    gateway.get_article.return_value = LocalArticleCatalogItem(
        article_id="article-1",
        title="短文",
        path="/tmp/article.txt",
        char_count=3,
        modified_timestamp=1.0,
    )
    gateway.count_chars.return_value = 3
    gateway.load_segment_content.return_value = "c"
    usecase = LoadLocalArticleSegmentUseCase(gateway)

    result = usecase.load_segment("article-1", segment_index=99, segment_size=2)

    assert result.content == "c"
    assert result.index == 2
    assert result.total == 2
    gateway.load_segment_content.assert_called_once_with("article-1", 2, 2)


def test_load_segment_clamps_index_to_lower_bound():
    gateway = MagicMock()
    gateway.get_article.return_value = LocalArticleCatalogItem(
        article_id="article-1",
        title="短文",
        path="/tmp/article.txt",
        char_count=3,
        modified_timestamp=1.0,
    )
    gateway.count_chars.return_value = 3
    gateway.load_segment_content.return_value = "ab"
    usecase = LoadLocalArticleSegmentUseCase(gateway)

    result = usecase.load_segment("article-1", segment_index=0, segment_size=2)

    assert result.content == "ab"
    assert result.index == 1
    assert result.total == 2
    gateway.load_segment_content.assert_called_once_with("article-1", 0, 2)


def test_load_segment_handles_empty_article():
    gateway = MagicMock()
    gateway.get_article.return_value = LocalArticleCatalogItem(
        article_id="article-1",
        title="空文",
        path="/tmp/article.txt",
        char_count=0,
        modified_timestamp=1.0,
    )
    gateway.count_chars.return_value = 0
    gateway.load_segment_content.return_value = ""
    usecase = LoadLocalArticleSegmentUseCase(gateway)

    result = usecase.load_segment("article-1", segment_index=1, segment_size=10)

    assert result.content == ""
    assert result.index == 1
    assert result.total == 1
    gateway.load_segment_content.assert_called_once_with("article-1", 0, 10)
    gateway.save_current_segment.assert_called_once_with("article-1", 1)


def test_load_segment_returns_content_when_progress_save_fails():
    gateway = MagicMock()
    gateway.get_article.return_value = LocalArticleCatalogItem(
        article_id="article-1",
        title="长文",
        path="/tmp/article.txt",
        char_count=4,
        modified_timestamp=1.0,
    )
    gateway.count_chars.return_value = 4
    gateway.load_segment_content.return_value = "ab"
    gateway.save_current_segment.side_effect = OSError("read-only")
    usecase = LoadLocalArticleSegmentUseCase(gateway)

    result = usecase.load_segment("article-1", segment_index=1, segment_size=2)

    assert result.content == "ab"
    assert result.index == 1


def test_load_segment_rejects_invalid_segment_size():
    usecase = LoadLocalArticleSegmentUseCase(MagicMock())

    with pytest.raises(ValueError, match="segment_size"):
        usecase.load_segment("article-1", segment_index=1, segment_size=0)
