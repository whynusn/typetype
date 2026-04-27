import json
from pathlib import Path

import pytest

from src.backend.integration.file_local_article_repository import (
    FileLocalArticleRepository,
)


def test_list_articles_scans_txt_files_with_metadata(tmp_path: Path):
    article_dir = tmp_path / "articles"
    nested_dir = article_dir / "nested"
    nested_dir.mkdir(parents=True)
    first_file = article_dir / "第一篇.txt"
    second_file = nested_dir / "second.txt"
    ignored_file = article_dir / "ignored.md"
    first_file.write_text("甲乙丙", encoding="utf-8")
    second_file.write_text("abcd", encoding="utf-8")
    ignored_file.write_text("nope", encoding="utf-8")
    repository = FileLocalArticleRepository(article_dir)

    catalog = repository.list_articles()

    assert [item.title for item in catalog] == ["第一篇", "second"]
    assert [item.char_count for item in catalog] == [3, 4]
    assert all(Path(item.path).is_absolute() for item in catalog)
    assert all(item.modified_timestamp > 0 for item in catalog)
    assert catalog[0].article_id == repository.make_article_id("第一篇.txt")
    assert catalog[1].article_id == repository.make_article_id("nested/second.txt")


def test_list_articles_rejects_symlinked_txt_outside_article_dir(tmp_path: Path):
    article_dir = tmp_path / "articles"
    outside_dir = tmp_path / "outside"
    article_dir.mkdir()
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    (article_dir / "secret-link.txt").symlink_to(outside_file)
    repository = FileLocalArticleRepository(article_dir)

    assert repository.list_articles() == []


def test_list_articles_skips_unreadable_txt_files(tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    good_file = article_dir / "good.txt"
    broken_file = article_dir / "broken.txt"
    good_file.write_text("可读正文", encoding="utf-8")
    broken_file.write_bytes(b"\xff\xff\xff")
    repository = FileLocalArticleRepository(article_dir)

    catalog = repository.list_articles()

    assert [item.title for item in catalog] == ["good"]
    assert catalog[0].char_count == 4


def test_list_articles_skips_files_that_fail_during_metadata_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    good_file = article_dir / "good.txt"
    broken_file = article_dir / "broken.txt"
    good_file.write_text("正文", encoding="utf-8")
    broken_file.write_text("boom", encoding="utf-8")
    repository = FileLocalArticleRepository(article_dir)
    original_read_article = repository._read_article

    def fail_for_broken(path: Path) -> str:
        if path.name == "broken.txt":
            raise OSError("file disappeared")
        return original_read_article(path)

    monkeypatch.setattr(repository, "_read_article", fail_for_broken)

    catalog = repository.list_articles()

    assert [item.title for item in catalog] == ["good"]


def test_load_article_content_decodes_utf8_then_gb18030(tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    utf8_file = article_dir / "utf8.txt"
    gb_file = article_dir / "gb.txt"
    utf8_file.write_text("UTF-8 正文", encoding="utf-8")
    gb_file.write_bytes("GB 正文".encode("gb18030"))
    repository = FileLocalArticleRepository(article_dir)

    assert (
        repository.load_article_content(repository.make_article_id("utf8.txt"))
        == "UTF-8 正文"
    )
    assert (
        repository.load_article_content(repository.make_article_id("gb.txt"))
        == "GB 正文"
    )


def test_load_article_content_rejects_unknown_article_id(tmp_path: Path):
    repository = FileLocalArticleRepository(tmp_path)

    with pytest.raises(FileNotFoundError, match="unknown article_id"):
        repository.load_article_content("missing")


def test_get_article_metadata_does_not_decode_other_articles(tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    target_file = article_dir / "target.txt"
    broken_file = article_dir / "broken.txt"
    target_file.write_text("正文", encoding="utf-8")
    broken_file.write_bytes(b"\xff\xff\xff")
    repository = FileLocalArticleRepository(article_dir)

    item = repository.get_article(repository.make_article_id("target.txt"))

    assert item.title == "target"
    assert item.char_count == 2


def test_progress_is_persisted_under_article_directory(tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    repository = FileLocalArticleRepository(article_dir)

    repository.save_current_segment("article-1", 3)

    progress_file = article_dir / ".typetype_progress.json"
    assert progress_file.exists()
    assert json.loads(progress_file.read_text(encoding="utf-8")) == {
        "article-1": {"current_segment": 3}
    }
    assert repository.load_current_segment("article-1") == 3
    assert repository.load_current_segment("unknown") is None


def test_corrupt_progress_file_is_ignored(tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    (article_dir / ".typetype_progress.json").write_text("{", encoding="utf-8")
    repository = FileLocalArticleRepository(article_dir)

    assert repository.load_current_segment("article-1") is None
