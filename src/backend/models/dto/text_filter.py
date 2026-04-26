"""文本过滤传输对象。"""

from dataclasses import dataclass, field
from enum import StrEnum


class TextFilterRuleKind(StrEnum):
    """文本过滤规则类型。"""

    LITERAL_REPLACE = "literal_replace"
    REGEX_REPLACE = "regex_replace"
    LITERAL_BLOCK = "literal_block"
    REGEX_BLOCK = "regex_block"


@dataclass
class TextFilterRule:
    """文本过滤规则。"""

    name: str
    scope: str
    kind: TextFilterRuleKind
    pattern: str
    replacement: str = ""
    enabled: bool = True


@dataclass
class TextFilterResult:
    """文本过滤结果。"""

    text: str
    blocked: bool = False
    matched_rules: list[str] = field(default_factory=list)
    replacement_count: int = 0
