"""文本过滤服务。"""

import re

from ...models.dto.text_filter import (
    TextFilterResult,
    TextFilterRule,
    TextFilterRuleKind,
)


class TextFilterService:
    """纯业务文本过滤服务。"""

    ALL_SCOPE = "all"

    def apply(
        self, text: str, scope: str, rules: list[TextFilterRule]
    ) -> TextFilterResult:
        """按 scope 应用文本过滤规则。"""
        result = TextFilterResult(text=text)

        for rule in rules:
            if not self._should_apply(rule, scope):
                continue

            if rule.kind == TextFilterRuleKind.LITERAL_REPLACE:
                self._apply_literal_replace(result, rule)
            elif rule.kind == TextFilterRuleKind.REGEX_REPLACE:
                self._apply_regex_replace(result, rule)
            elif rule.kind == TextFilterRuleKind.LITERAL_BLOCK:
                if rule.pattern and rule.pattern in result.text:
                    result.blocked = True
                    result.matched_rules.append(rule.name)
                    break
            elif rule.kind == TextFilterRuleKind.REGEX_BLOCK:
                if self._regex_matches(rule.pattern, result.text):
                    result.blocked = True
                    result.matched_rules.append(rule.name)
                    break

        return result

    def _should_apply(self, rule: TextFilterRule, scope: str) -> bool:
        return rule.enabled and rule.scope in (scope, self.ALL_SCOPE)

    def _apply_literal_replace(
        self, result: TextFilterResult, rule: TextFilterRule
    ) -> None:
        if not rule.pattern:
            return

        replacement_count = result.text.count(rule.pattern)
        if replacement_count == 0:
            return

        result.text = result.text.replace(rule.pattern, rule.replacement)
        result.replacement_count += replacement_count
        result.matched_rules.append(rule.name)

    def _apply_regex_replace(
        self, result: TextFilterResult, rule: TextFilterRule
    ) -> None:
        if not rule.pattern:
            return

        try:
            updated_text, replacement_count = re.subn(
                rule.pattern, rule.replacement, result.text
            )
        except re.error:
            return

        if replacement_count == 0:
            return

        result.text = updated_text
        result.replacement_count += replacement_count
        result.matched_rules.append(rule.name)

    def _regex_matches(self, pattern: str, text: str) -> bool:
        if not pattern:
            return False

        try:
            return re.search(pattern, text) is not None
        except re.error:
            return False
