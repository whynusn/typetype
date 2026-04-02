from dataclasses import dataclass


@dataclass
class TextSourceDTO:
    id: int
    source_key: str
    label: str
    category: str
    is_active: bool
