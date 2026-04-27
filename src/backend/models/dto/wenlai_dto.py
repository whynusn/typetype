from dataclasses import dataclass
from enum import Enum


class WenlaiDirection(str, Enum):
    NEXT = "next"
    PREV = "prev"


@dataclass(frozen=True)
class WenlaiLoginResult:
    token: str
    user_id: int
    username: str
    display_name: str = ""


@dataclass(frozen=True)
class WenlaiDifficulty:
    id: int
    name: str
    count: int = 0


@dataclass(frozen=True)
class WenlaiCategory:
    code: str
    name: str


@dataclass(frozen=True)
class WenlaiText:
    title: str
    content: str
    mark: str = ""
    book_id: int = 0
    sort_num: int = 0
    end_sort_num: int = 0
    end_chars: str = ""
    start_chars: str = ""
    category: str = ""
    difficulty_level: int = 0
    difficulty_label: str = ""
    difficulty_score: float = 0.0

    @property
    def display_title(self) -> str:
        if self.difficulty_label:
            return f"[{self.difficulty_label}({self.difficulty_score:.2f})]{self.title}"
        return self.title

    @property
    def difficulty_text(self) -> str:
        if self.difficulty_label:
            return f"{self.difficulty_label}({self.difficulty_score:.2f})"
        return ""

    @property
    def progress_text(self) -> str:
        if not self.mark:
            return str(self.sort_num) if self.sort_num > 0 else ""
        if "-" not in self.mark:
            return self.mark
        current, total = self.mark.split("-", 1)
        current = str(self.sort_num) if self.sort_num > 0 else current
        return f"{current}/{total}" if total else current

    @property
    def sender_content(self) -> str:
        """渲染为 TypeSunny 晴发文发文格式。"""
        lines = [
            f"{self.display_title} [字数{len(self.content)}]",
            self.content,
        ]
        if self.mark:
            lines.append(f"-----第{self.mark}段-晴发文")
        else:
            lines.append("-----晴发文")
        return "\n".join(lines)
