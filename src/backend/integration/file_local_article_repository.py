import hashlib
import json
import re
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
    ) -> None:
        self._article_dir = Path(article_dir).expanduser().resolve()
        self._progress_file = self._article_dir / progress_filename

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
            char_count=len(self._read_article(path)),
            modified_timestamp=stat.st_mtime,
        )

    def _path_for_article_id(self, article_id: str) -> Path | None:
        for path in self._article_paths():
            if self.make_article_id(path.relative_to(self._article_dir)) == article_id:
                return path
        return None

    def _read_article(self, path: Path) -> str:
        content = path.read_bytes()
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("gb18030")

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
