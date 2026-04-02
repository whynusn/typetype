from dataclasses import dataclass


@dataclass
class Text:
    id: int
    source_id: int
    title: str
    content: str
    char_count: int
    difficulty: int = 0
