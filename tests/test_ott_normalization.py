"""OTT 通用归一化/脱敏工具测试。"""

from __future__ import annotations

from src.backend.integration.ott_normalization import (
    redact_url,
    safe_int,
    to_jsdelivr_url,
)


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


class TestToJsdelivrUrl:
    def test_maps_github_raw_to_cdn(self) -> None:
        assert (
            to_jsdelivr_url(
                "https://raw.githubusercontent.com/owner/repo/main/scripts/a.py"
            )
            == "https://cdn.jsdelivr.net/gh/owner/repo@main/scripts/a.py"
        )

    def test_maps_nested_path(self) -> None:
        assert (
            to_jsdelivr_url(
                "https://raw.githubusercontent.com/o/r/v1.0/dir/ott-repo.json"
            )
            == "https://cdn.jsdelivr.net/gh/o/r@v1.0/dir/ott-repo.json"
        )

    def test_non_raw_url_returns_none(self) -> None:
        for url in (
            "https://example.com/raw/owner/repo/main/a.py",
            "https://cdn.jsdelivr.net/gh/owner/repo@main/a.py",
            "http://raw.githubusercontent.com/owner/repo/main/a.py",
            "file:///tmp/a.py",
            "",
        ):
            assert to_jsdelivr_url(url) is None, url

    def test_too_few_path_parts_returns_none(self) -> None:
        assert (
            to_jsdelivr_url("https://raw.githubusercontent.com/owner/repo/main") is None
        )
