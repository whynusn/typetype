import hashlib
import json
import re
import codecs
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..models.dto.local_article import LocalArticleCatalogItem
from ..ports.local_article_repository import LocalArticleRepository


class FileLocalArticleRepository(LocalArticleRepository):
    """基于文件目录的本地长文库仓储。"""

    PROGRESS_FILENAME = ".typetype_progress.json"

    def __init__(
        self,
        article_dir: str | Path,
        progress_filename: str = PROGRESS_FILENAME,
        bundled_source_dir: str | Path | None = None,
    ) -> None:
        self._article_dir = Path(article_dir).expanduser().resolve()
        self._progress_file = self._article_dir / progress_filename
        self._bundled_names: set[str] = set()
        if bundled_source_dir is not None:
            src = Path(bundled_source_dir)
            if src.exists():
                self._bundled_names = {p.name for p in src.glob("*.txt")}

    def list_articles(self) -> list[LocalArticleCatalogItem]:
        articles: list[LocalArticleCatalogItem] = []
        for path in self._article_paths():
            try:
                articles.append(self._build_catalog_item(path))
            except (OSError, UnicodeDecodeError):
                continue
        return articles

    def get_article(self, article_id: str) -> LocalArticleCatalogItem:
        path = self._path_for_article_id(article_id)
        if path is None:
            raise FileNotFoundError(f"unknown article_id: {article_id}")
        return self._build_catalog_item(path)

    def load_article_content(self, article_id: str) -> str:
        path = self._path_for_article_id(article_id)
        if path is None:
            raise FileNotFoundError(f"unknown article_id: {article_id}")
        return self._read_article(path)

    def load_article_segment(self, article_id: str, start: int, length: int) -> str:
        path = self._path_for_article_id(article_id)
        if path is None:
            raise FileNotFoundError(f"unknown article_id: {article_id}")
        if start < 0 or length <= 0:
            return ""
        return self._read_article_segment(path, start, length)

    def count_article_chars(self, article_id: str) -> int:
        path = self._path_for_article_id(article_id)
        if path is None:
            raise FileNotFoundError(f"unknown article_id: {article_id}")
        return self._count_article_chars(path)

    def save_current_segment(self, article_id: str, segment_index: int) -> None:
        self._article_dir.mkdir(parents=True, exist_ok=True)
        progress = self._read_progress()
        progress[article_id] = {"current_segment": segment_index}
        self._progress_file.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_current_segment(self, article_id: str) -> int | None:
        article_progress = self._read_progress().get(article_id)
        if not isinstance(article_progress, dict):
            return None
        segment_index = article_progress.get("current_segment")
        if isinstance(segment_index, int):
            return segment_index
        return None

    def make_article_id(self, relative_path: str | Path) -> str:
        rel_posix = Path(relative_path).as_posix()
        stem = Path(rel_posix).with_suffix("").as_posix()
        slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", stem).strip("-").lower()
        digest = hashlib.sha1(rel_posix.encode("utf-8")).hexdigest()[:12]
        if not slug:
            slug = "article"
        return f"{slug}-{digest}"

    def _article_paths(self) -> list[Path]:
        if not self._article_dir.exists():
            return []
        paths = [
            path
            for path in self._article_dir.rglob("*.txt")
            if path.is_file() and not path.is_symlink()
        ]
        return sorted(
            paths,
            key=lambda path: (
                len(path.relative_to(self._article_dir).parts),
                path.relative_to(self._article_dir).as_posix(),
            ),
        )

    def _build_catalog_item(self, path: Path) -> LocalArticleCatalogItem:
        stat = path.stat()
        return LocalArticleCatalogItem(
            article_id=self.make_article_id(path.relative_to(self._article_dir)),
            title=path.stem,
            path=str(path.resolve()),
            char_count=self._count_article_chars(path),
            modified_timestamp=stat.st_mtime,
            is_bundled=path.name in self._bundled_names,
        )

    def _path_for_article_id(self, article_id: str) -> Path | None:
        for path in self._article_paths():
            if self.make_article_id(path.relative_to(self._article_dir)) == article_id:
                return path
        return None

    def resolve_article_path(self, article_id: str) -> str | None:
        path = self._path_for_article_id(article_id)
        if path is None or not path.exists():
            return None
        return str(path.resolve())

    def _read_article(self, path: Path) -> str:
        return "".join(self._iter_decoded_chunks(path))

    def _count_article_chars(self, path: Path) -> int:
        return sum(len(chunk) for chunk in self._iter_decoded_chunks(path))

    def _read_article_segment(self, path: Path, start: int, length: int) -> str:
        remaining_skip = start
        remaining_take = length
        parts: list[str] = []
        for chunk in self._iter_decoded_chunks(path):
            if remaining_skip >= len(chunk):
                remaining_skip -= len(chunk)
                continue
            if remaining_skip:
                chunk = chunk[remaining_skip:]
                remaining_skip = 0
            if remaining_take <= 0:
                break
            parts.append(chunk[:remaining_take])
            remaining_take -= len(parts[-1])
            if remaining_take <= 0:
                break
        return "".join(parts)

    def _iter_decoded_chunks(self, path: Path) -> Iterator[str]:
        encoding = self._detect_encoding(path)
        yield from self._iter_text_file(path, encoding)

    def _detect_encoding(self, path: Path) -> str:
        decoder = codecs.getincrementaldecoder("utf-8")()
        try:
            with path.open("rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "gb18030"
        return "utf-8"

    def _iter_text_file(self, path: Path, encoding: str) -> Iterator[str]:
        with path.open("r", encoding=encoding) as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    def delete_article(self, article_id: str) -> bool:
        path = self._path_for_article_id(article_id)
        if path is None or not path.exists():
            return False
        path.unlink()
        progress = self._read_progress()
        if article_id in progress:
            del progress[article_id]
            self._progress_file.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return True

    def rename_article(self, article_id: str, new_title: str) -> bool:
        path = self._path_for_article_id(article_id)
        if path is None or not path.exists():
            return False
        new_path = path.parent / f"{new_title}{path.suffix}"
        if new_path.exists() and new_path != path:
            return False
        path.rename(new_path)
        progress = self._read_progress()
        if article_id in progress:
            del progress[article_id]
            new_article_id = self.make_article_id(
                new_path.relative_to(self._article_dir)
            )
            progress[new_article_id] = progress.get(article_id, {})
            self._progress_file.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return True

    def _read_progress(self) -> dict[str, Any]:
        if not self._progress_file.exists():
            return {}
        try:
            data = json.loads(self._progress_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(data, dict):
            return data
        return {}
