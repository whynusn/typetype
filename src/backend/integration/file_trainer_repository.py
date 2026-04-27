import json
import re
from pathlib import Path
from typing import Any

from ..models.dto.trainer import TrainerCatalogItem, TrainerLexicon
from ..ports.trainer_repository import TrainerRepository


class FileTrainerRepository(TrainerRepository):
    """基于 TypeSunny 练单器 txt 目录的词库仓储。"""

    PROGRESS_FILENAME = ".typetype_trainer_progress.json"

    def __init__(
        self,
        trainer_dir: str | Path,
        progress_filename: str = PROGRESS_FILENAME,
    ) -> None:
        self._trainer_dir = Path(trainer_dir).expanduser().resolve()
        self._progress_file = self._trainer_dir / progress_filename

    def list_trainers(self) -> list[TrainerCatalogItem]:
        trainers: list[TrainerCatalogItem] = []
        for path in self._trainer_paths():
            try:
                lines = self._non_empty_lines(self._read_text(path))
                stat = path.stat()
            except (OSError, UnicodeDecodeError):
                continue
            trainers.append(
                TrainerCatalogItem(
                    trainer_id=path.stem,
                    title=self._display_name(path.stem),
                    path=str(path.resolve()),
                    entry_count=len(lines),
                    modified_timestamp=stat.st_mtime,
                )
            )
        return trainers

    def load_lexicon(self, trainer_id: str, group_size: int) -> TrainerLexicon:
        if group_size <= 0:
            raise ValueError("group_size must be greater than 0")

        path = self._path_for_trainer(trainer_id)
        if path is None:
            raise FileNotFoundError(f"unknown trainer: {trainer_id}")

        lines = self._non_empty_lines(self._read_text(path))
        groups, mode = self._build_groups(lines, group_size)
        return TrainerLexicon(
            trainer_id=path.stem,
            title=self._display_name(path.stem),
            mode=mode,
            groups=groups,
            group_size=group_size,
        )

    def save_current_segment(self, trainer_id: str, segment_index: int) -> None:
        self._trainer_dir.mkdir(parents=True, exist_ok=True)
        progress = self._read_progress()
        progress[trainer_id] = {"current_segment": segment_index}
        self._progress_file.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_current_segment(self, trainer_id: str) -> int | None:
        trainer_progress = self._read_progress().get(trainer_id)
        if not isinstance(trainer_progress, dict):
            return None
        segment_index = trainer_progress.get("current_segment")
        if isinstance(segment_index, int):
            return segment_index
        return None

    def _trainer_paths(self) -> list[Path]:
        if not self._trainer_dir.exists():
            return []
        paths = [
            path
            for path in self._trainer_dir.glob("*.txt")
            if path.is_file() and not path.is_symlink()
        ]
        return sorted(paths, key=lambda path: self._natural_key(path.name))

    def _path_for_trainer(self, trainer_id: str) -> Path | None:
        for path in self._trainer_paths():
            if path.stem == trainer_id:
                return path
        return None

    def _read_text(self, path: Path) -> str:
        content = path.read_bytes()
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content.decode("gb18030")

    def _non_empty_lines(self, text: str) -> list[str]:
        normalized = text.strip().replace("\r", "")
        return [line for line in normalized.split("\n") if line.strip()]

    def _build_groups(
        self,
        lines: list[str],
        group_size: int,
    ) -> tuple[tuple[tuple[str, ...], ...], str]:
        if not lines:
            return ((), "fixed")

        max_line_len = max(len(line) for line in lines)
        first_line = lines[0].lstrip()
        if first_line and not re.match(r"[A-Za-z]", first_line[0]) and max_line_len > 4:
            return tuple(tuple(line.strip()) for line in lines), "variable"

        groups = [
            tuple(lines[index : index + group_size])
            for index in range(0, len(lines), group_size)
        ]
        return tuple(groups), "fixed"

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

    def _display_name(self, stem: str) -> str:
        return re.sub(r"^\d+\.\s*", "", stem)

    def _natural_key(self, name: str) -> tuple[tuple[int, int | str], ...]:
        parts = re.split(r"(\d+)", name.lower())
        key: list[tuple[int, int | str]] = []
        for part in parts:
            if part.isdigit():
                key.append((0, int(part)))
            else:
                key.append((1, part))
        return tuple(key)
