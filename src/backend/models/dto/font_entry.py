from dataclasses import dataclass


@dataclass(frozen=True)
class FontEntry:
    name: str
    file_path: str
    file_name: str
    is_bundled: bool
