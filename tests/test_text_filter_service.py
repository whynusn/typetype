"""文本过滤服务测试。"""

from src.backend.domain.services.text_filter_service import TextFilterService
from src.backend.models.dto.text_filter import TextFilterRule, TextFilterRuleKind


def test_applies_exact_and_all_scope_replacements_and_counts_matches() -> None:
    """应应用当前 scope 与 all scope 的替换规则并统计替换次数。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="wenlai-literal",
            scope="wenlai",
            kind=TextFilterRuleKind.LITERAL_REPLACE,
            pattern="foo",
            replacement="bar",
        ),
        TextFilterRule(
            name="all-regex",
            scope="all",
            kind=TextFilterRuleKind.REGEX_REPLACE,
            pattern=r"\d+",
            replacement="#",
        ),
        TextFilterRule(
            name="clipboard-only",
            scope="clipboard",
            kind=TextFilterRuleKind.LITERAL_REPLACE,
            pattern="bar",
            replacement="baz",
        ),
    ]

    result = service.apply("foo 123 foo", "wenlai", rules)

    assert result.text == "bar # bar"
    assert result.blocked is False
    assert result.matched_rules == ["wenlai-literal", "all-regex"]
    assert result.replacement_count == 3


def test_ignores_disabled_rules() -> None:
    """禁用规则不应参与替换或命中统计。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="disabled",
            scope="all",
            kind=TextFilterRuleKind.LITERAL_REPLACE,
            pattern="foo",
            replacement="bar",
            enabled=False,
        )
    ]

    result = service.apply("foo", "trainer", rules)

    assert result.text == "foo"
    assert result.blocked is False
    assert result.matched_rules == []
    assert result.replacement_count == 0


def test_literal_block_marks_blocked_and_stops_later_mutation() -> None:
    """阻断规则命中后应标记 blocked，后续规则不再修改文本。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="block-secret",
            scope="local_article",
            kind=TextFilterRuleKind.LITERAL_BLOCK,
            pattern="secret",
        ),
        TextFilterRule(
            name="later-replace",
            scope="all",
            kind=TextFilterRuleKind.LITERAL_REPLACE,
            pattern="secret",
            replacement="public",
        ),
    ]

    result = service.apply("contains secret", "local_article", rules)

    assert result.text == "contains secret"
    assert result.blocked is True
    assert result.matched_rules == ["block-secret"]
    assert result.replacement_count == 0


def test_regex_block_marks_blocked() -> None:
    """正则阻断规则命中后应标记 blocked。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="block-digits",
            scope="clipboard",
            kind=TextFilterRuleKind.REGEX_BLOCK,
            pattern=r"\d{3}",
        )
    ]

    result = service.apply("abc123", "clipboard", rules)

    assert result.text == "abc123"
    assert result.blocked is True
    assert result.matched_rules == ["block-digits"]
    assert result.replacement_count == 0


def test_invalid_regex_rules_are_ignored() -> None:
    """无效正则规则应被忽略而不是抛出异常。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="bad-replace",
            scope="all",
            kind=TextFilterRuleKind.REGEX_REPLACE,
            pattern="[",
            replacement="x",
        ),
        TextFilterRule(
            name="bad-block",
            scope="all",
            kind=TextFilterRuleKind.REGEX_BLOCK,
            pattern="(",
        ),
        TextFilterRule(
            name="good",
            scope="all",
            kind=TextFilterRuleKind.LITERAL_REPLACE,
            pattern="foo",
            replacement="bar",
        ),
    ]

    result = service.apply("foo [", "wenlai", rules)

    assert result.text == "bar ["
    assert result.blocked is False
    assert result.matched_rules == ["good"]
    assert result.replacement_count == 1


def test_empty_regex_patterns_are_ignored() -> None:
    """空正则 pattern 不应替换边界或阻断所有文本。"""
    service = TextFilterService()
    rules = [
        TextFilterRule(
            name="empty-replace",
            scope="all",
            kind=TextFilterRuleKind.REGEX_REPLACE,
            pattern="",
            replacement="x",
        ),
        TextFilterRule(
            name="empty-block",
            scope="all",
            kind=TextFilterRuleKind.REGEX_BLOCK,
            pattern="",
        ),
    ]

    result = service.apply("abc", "wenlai", rules)

    assert result.text == "abc"
    assert result.blocked is False
    assert result.matched_rules == []
    assert result.replacement_count == 0
