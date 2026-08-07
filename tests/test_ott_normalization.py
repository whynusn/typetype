"""OTT 通用归一化/脱敏工具测试。"""

from __future__ import annotations

from src.backend.integration.ott_normalization import redact_url, safe_int


class TestSafeInt:
    def test_numeric_string(self) -> None:
        assert safe_int("42", default=0) == 42

    def test_bad_string_returns_default(self) -> None:
        assert safe_int("abc", default=7) == 7

    def test_none_returns_default(self) -> None:
        assert safe_int(None, default=1) == 1

    def test_bool_returns_default(self) -> None:
        assert safe_int(True, default=2) == 2


class TestRedactUrl:
    def test_strips_path_and_query(self) -> None:
        assert (
            redact_url("https://example.com/a/b?token=secret#frag")
            == "https://example.com"
        )

    def test_keeps_scheme_and_host(self) -> None:
        assert redact_url("http://foo.example.org:8080/x") == "http://foo.example.org"

    def test_invalid_url(self) -> None:
        assert redact_url("not a url") == "<invalid-url>"

    def test_empty(self) -> None:
        assert redact_url("") == "<invalid-url>"
