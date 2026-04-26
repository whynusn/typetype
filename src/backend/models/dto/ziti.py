from dataclasses import dataclass


@dataclass(frozen=True)
class ZitiScheme:
    name: str
    entry_count: int


@dataclass(frozen=True)
class ZitiSchemeData:
    scheme: ZitiScheme
    hints: dict[str, str]
