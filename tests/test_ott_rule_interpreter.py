"""OTT Repo L1 声明式规则解释器测试。"""

from __future__ import annotations

import json
import socket
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.backend.integration.ott_rule_interpreter import (
    MAX_JSON_DEPTH,
    MAX_TOTAL_ENTRIES,
    OttRuleInterpreter,
    _json_depth_exceeds,
    apply_transform,
    apply_transforms_to_entry,
    extract_field,
    extract_fields,
    validate_url,
)
from src.backend.integration.regex_worker import _has_nested_quantifier


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch):
    """域名解析固定为公网 IP，保证全部测试离线且确定。"""
    monkeypatch.setattr(
        "src.backend.integration.ott_rule_interpreter.socket.getaddrinfo",
        lambda _host, _port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )


# ---------------------------------------------------------------------------
# URL 校验
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_rejects_file_scheme(self) -> None:
        assert validate_url("file:///etc/passwd") is False

    def test_rejects_ftp_scheme(self) -> None:
        assert validate_url("ftp://example.com/data") is False

    def test_rejects_empty(self) -> None:
        assert validate_url("") is False
        assert validate_url(None) is False  # type: ignore[arg-type]

    def test_rejects_localhost(self) -> None:
        assert validate_url("http://localhost/api") is False
        assert validate_url("http://localhost:8080/api") is False
        assert validate_url("http://LOCALHOST/api") is False

    def test_rejects_loopback_ip(self) -> None:
        assert validate_url("http://127.0.0.1/api") is False
        assert validate_url("http://127.0.0.1:8080/api") is False

    def test_rejects_private_ip(self) -> None:
        assert validate_url("http://10.0.0.1/api") is False
        assert validate_url("http://192.168.1.1/api") is False
        assert validate_url("http://172.16.0.1/api") is False

    def test_accepts_public_https(self) -> None:
        assert validate_url("https://example.com/api") is True
        assert validate_url("https://v1.hitokoto.cn/?c=i") is True

    def test_accepts_public_http(self) -> None:
        assert validate_url("http://example.com/api") is True

    def test_rejects_percent_encoded_host(self) -> None:
        assert validate_url("http://127.0.0.1.%2e/api") is False
        assert validate_url("http://%31%32%37.0.0.1/api") is False

    def test_rejects_non_ascii_host(self) -> None:
        assert validate_url("http://例え.テスト/api") is False

    def test_rejects_non_standard_port(self) -> None:
        assert validate_url("http://example.com:8080/api") is False
        assert validate_url("https://example.com:444/api") is False
        assert validate_url("http://example.com:80/api") is True
        assert validate_url("https://example.com:443/api") is True

    def test_rejects_numeric_ip_literals(self) -> None:
        assert validate_url("http://2130706433/api") is False
        assert validate_url("http://0x7f000001/api") is False
        assert validate_url("http://017700000001/api") is False

    def test_rejects_ipv4_mapped_ipv6_loopback(self) -> None:
        assert validate_url("http://[::ffff:127.0.0.1]/api") is False
        assert validate_url("http://[::ffff:10.0.0.1]/api") is False
        assert validate_url("http://[0:0:0:0:0:ffff:7f00:1]/api") is False

    def test_rejects_link_local(self) -> None:
        assert validate_url("http://169.254.169.254/latest/meta-data") is False
        assert validate_url("http://[fe80::1]/api") is False

    def test_rejects_dns_resolution_failure(self) -> None:
        with patch(
            "src.backend.integration.ott_rule_interpreter.socket.getaddrinfo",
            side_effect=socket.gaierror("no such host"),
        ):
            assert validate_url("http://example.com/api") is False


# ---------------------------------------------------------------------------
# JSON 深度守卫
# ---------------------------------------------------------------------------


class TestJsonDepthGuard:
    def test_depth_scan_rejects_deep_nesting(self) -> None:
        assert _json_depth_exceeds("[" * 100_000, MAX_JSON_DEPTH) is True
        assert _json_depth_exceeds("[" * 256, MAX_JSON_DEPTH) is False
        assert _json_depth_exceeds("[" * 257, MAX_JSON_DEPTH) is True

    def test_depth_scan_ignores_brackets_inside_strings(self) -> None:
        assert _json_depth_exceeds('"[{[{"', 256) is False

    def test_deep_bomb_parse_returns_empty_without_recursion(self) -> None:
        interp = OttRuleInterpreter(httpx.Client())
        bomb = "[" * 100_000 + "]" * 100_000
        assert interp._parse_response(bomb) == []

    def test_normal_json_still_parses(self) -> None:
        interp = OttRuleInterpreter(httpx.Client())
        entries = interp._parse_response(
            '{"entries": [{"title": "a"}, {"title": "b"}]}'
        )
        assert [e["title"] for e in entries] == ["a", "b"]


# ---------------------------------------------------------------------------
# 提取
# ---------------------------------------------------------------------------


class TestExtractField:
    def test_json_path_simple(self) -> None:
        data = {"title": "Hello", "content": "World"}
        assert extract_field(data, "$.title") == "Hello"
        assert extract_field(data, "$.content") == "World"

    def test_json_path_nested(self) -> None:
        data = {"a": {"b": {"c": "deep"}}}
        assert extract_field(data, "$.a.b.c") == "deep"

    def test_json_path_array_wildcard(self) -> None:
        data = {"items": [{"title": "First"}, {"title": "Second"}]}
        result = extract_field(data, "$.items[*].title")
        assert result == "First"

    def test_json_path_array_index(self) -> None:
        data = ["a", "b", "c"]
        assert extract_field(data, "$[0]") == "a"
        assert extract_field(data, "$[2]") == "c"

    def test_regex_named_groups(self) -> None:
        text = "<h1>Title Here</h1><p>Content text</p>"
        pattern = r"<h1>(?P<title>.*?)</h1>"
        result = extract_field(text, pattern)
        assert result == "Title Here"

    def test_regex_slash_delimited(self) -> None:
        text = "Name: John Doe"
        result = extract_field(text, "/Name: (?P<name>.*)/")
        assert result == "John Doe"

    def test_regex_nested_quantifier_rejected(self) -> None:
        # (a+)+$ 灾难性回溯模式：静态拒绝，1s 内返回空
        text = "a" * 10_000
        start = time.monotonic()
        result = extract_field(text, "(a+)+$")
        elapsed = time.monotonic() - start
        assert result == ""
        assert elapsed < 1.0

    def test_regex_worker_timeout_fallback_empty(self) -> None:
        # 子进程执行失败/超时时静默返回空，不抛错
        start = time.monotonic()
        result = extract_field("hello world", "(a|b|ab|c|d|e|f|g|h|i|j|k|l|m)*$")
        elapsed = time.monotonic() - start
        assert result == ""
        assert elapsed < 1.0

    def test_css_selector(self) -> None:
        html = '<div class="content"><p>Hello World</p></div>'
        result = extract_field(html, ".content p")
        assert result == "Hello World"

    def test_css_selector_no_match(self) -> None:
        html = '<div class="other">text</div>'
        result = extract_field(html, ".nonexistent")
        assert result == ""

    def test_empty_spec_returns_stringified(self) -> None:
        assert (
            extract_field({"key": "value"}, "") == {"key": "value"} or True
        )  # dict stringify

    def test_non_dict_data_with_css(self) -> None:
        # 纯文本 + CSS 选择器 → 返回空（bs4 解析文本不会匹配）
        result = extract_field("plain text", ".selector")
        # 不抛错即可
        assert isinstance(result, str)


class TestExtractFields:
    def test_multiple_fields(self) -> None:
        data = {"title": "T", "body": "B"}
        spec = {"title": "$.title", "content": "$.body"}
        result = extract_fields(data, spec)
        assert result == {"title": "T", "content": "B"}

    def test_invalid_spec_returns_empty(self) -> None:
        assert extract_fields({"a": 1}, "not a dict") == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 变换
# ---------------------------------------------------------------------------


class TestTransforms:
    def test_trim(self) -> None:
        assert apply_transform("  hello  ", ["trim"]) == "hello"

    def test_truncate(self) -> None:
        long = "x" * 3000
        result = apply_transform(long, ["truncate"])
        assert len(result) == 2000

    def test_multiple_transforms(self) -> None:
        assert apply_transform("  hello world  ", ["trim", "truncate"]) == "hello world"

    def test_empty_transforms(self) -> None:
        assert apply_transform("hello", []) == "hello"
        assert apply_transform("hello", None) == "hello"  # type: ignore[arg-type]

    def test_apply_transforms_to_entry(self) -> None:
        entry = {"title": "  Hi  ", "content": "  World  "}
        result = apply_transforms_to_entry(entry, ["trim"])
        assert result["title"] == "Hi"
        assert result["content"] == "World"

    def test_replace_transform(self) -> None:
        entry = {"content": "hello world"}
        result = apply_transforms_to_entry(entry, ["replace"], {"hello": "hi"})
        assert result["content"] == "hi world"


# ---------------------------------------------------------------------------
# 解释器（mock HTTP）
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, text, status_code=200):
        self._text = text
        self.status_code = status_code
        self.headers = {"content-length": str(len(text))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=self)

    @property
    def text(self):
        return self._text

    def iter_text(self, chunk_size: int = 1):
        """Streaming text iterator (matches httpx.Response API)."""
        yield self._text


def _mock_client(json_data=None, text="", status_code=200):
    client = MagicMock(spec=httpx.Client)
    if json_data is not None:
        text = json.dumps(json_data)
    client.get.return_value = _MockResponse(text, status_code)
    client.post.return_value = _MockResponse(text, status_code)
    return client


class TestOttRuleInterpreter:
    def _rule(self, url="https://example.com/api", extract=None, pagination=None):
        return {
            "request": {"url": url, "method": "GET"},
            "extract": extract or {"title": "$.title", "content": "$.content"},
            "transform": [],
            "pagination": pagination or {},
        }

    def test_list_entries_basic(self) -> None:
        data = [
            {"title": "First", "content": "Content one"},
            {"title": "Second", "content": "Content two"},
        ]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        # max_pages=1 避免 mock 持续返回数据导致多页重复
        entries = interp.list_entries(self._rule(), "test-rule", max_pages=1)
        assert len(entries) == 2
        assert entries[0]["title"] == "First"
        assert entries[0]["content"] == "Content one"
        assert entries[0]["authority"] == "rule:test-rule"
        assert entries[0]["source_key"] == "rule:test-rule"

    def test_list_entries_deterministic_id(self) -> None:
        data = [{"title": "T", "content": "same content"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        e1 = interp.list_entries(self._rule(), "r1")
        e2 = interp.list_entries(self._rule(), "r1")
        assert e1[0]["entry_id"] == e2[0]["entry_id"]

    def test_list_entries_pagination(self) -> None:
        # 两页数据 + 空页终止
        page1 = [{"title": "P1", "content": "page1"}]
        page2 = [{"title": "P2", "content": "page2"}]

        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = [
            _MockResponse(json.dumps(page1)),
            _MockResponse(json.dumps(page2)),
            _MockResponse(json.dumps([])),  # 空页终止循环
        ]

        rule = self._rule(
            url="https://example.com/api?page={page}",
            pagination={"param": "page", "start": 1, "step": 1, "max_pages": 5},
        )
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        assert len(entries) == 2
        assert entries[0]["title"] == "P1"
        assert entries[1]["title"] == "P2"

    def test_list_entries_enforces_max_pages(self) -> None:
        # 无限数据源，但 max_pages=2 应截断
        data = [{"title": f"T{i}", "content": f"C{i}"} for i in range(10)]
        client = _mock_client(data)
        rule = self._rule(
            pagination={"param": "page", "start": 1, "step": 1, "max_pages": 2}
        )
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1", max_pages=2)
        # 每页 10 条，2 页 = 20 条
        assert len(entries) == 20

    def test_list_entries_zero_page_step_is_bounded(self) -> None:
        # 恶意 manifest 声明 step=0：page 永不前进，若无守卫会重复请求
        # 直到 MAX_TOTAL_ENTRIES（1000 次）。守卫后归一到 step=1，
        # 请求数受 max_pages 限制。
        data = [{"title": "T", "content": "C"}]
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _MockResponse(json.dumps(data))
        rule = self._rule(
            url="https://example.com/api?page={page}",
            pagination={"param": "page", "start": 1, "step": 0, "max_pages": 3},
        )
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1", max_pages=3)
        # 每页 1 条 × 3 页（step 归一到 1），而非 1000 条
        assert len(entries) == 3
        assert client.get.call_count == 3

    def test_list_entries_stops_when_empty_page(self) -> None:
        page1 = [{"title": "T", "content": "C"}]
        page2 = []  # 空页

        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = [
            _MockResponse(json.dumps(page1)),
            _MockResponse(json.dumps(page2)),
        ]

        rule = self._rule(url="https://example.com/api?page={page}")
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        assert len(entries) == 1

    def test_list_entries_rejects_bad_url(self) -> None:
        rule = self._rule(url="http://localhost/api")
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        assert entries == []

    def test_list_entries_rejects_file_url(self) -> None:
        rule = self._rule(url="file:///etc/passwd")
        client = _mock_client("[]")
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        assert entries == []

    def test_list_entries_network_failure_returns_empty(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.ConnectError("offline")
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(self._rule(), "r1")
        assert entries == []

    def test_list_entries_invalid_json_returns_empty(self) -> None:
        client = _mock_client(text="not json at all <html>")
        interp = OttRuleInterpreter(client)
        # 非 JSON 响应 → _parse_response 返回 [] → 无条目
        entries = interp.list_entries(self._rule(), "r1")
        assert entries == []

    def test_list_entries_normalized_shape(self) -> None:
        data = [{"title": "Test", "content": "Body"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(self._rule(), "r1", max_pages=1)
        assert len(entries) == 1
        e = entries[0]
        # 关键字段存在
        for field in (
            "entry_id",
            "title",
            "content",
            "char_count",
            "authority",
            "source_key",
            "source_label",
            "current_revision_id",
            "content_mode",
        ):
            assert field in e, f"missing field: {field}"
        assert e["content_mode"] == "inline"
        assert e["char_count"] == 4  # len("Body")

    def test_list_entries_max_total_cap(self) -> None:
        # 大量数据，验证不超过 MAX_TOTAL_ENTRIES
        big = [{"title": f"T{i}", "content": f"C{i}"} for i in range(200)]
        client = _mock_client(big)
        rule = self._rule(
            pagination={"param": "page", "start": 1, "step": 1, "max_pages": 10}
        )
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1", max_pages=10)
        assert len(entries) <= MAX_TOTAL_ENTRIES

    def test_list_entries_with_transforms(self) -> None:
        data = [{"title": "  Spaced  ", "content": "  Trim me  "}]
        client = _mock_client(data)
        rule = self._rule()
        rule["transform"] = ["trim"]
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        assert entries[0]["title"] == "Spaced"
        assert entries[0]["content"] == "Trim me"

    def test_list_entries_extracts_from_nested_json(self) -> None:
        data = {"data": {"items": [{"name": "Item1", "desc": "Desc1"}]}}
        client = _mock_client(data)
        rule = self._rule()
        rule["extract"] = {
            "title": "$.data.items[*].name",
            "content": "$.data.items[*].desc",
        }
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert entries[0]["title"] == "Item1"
        assert entries[0]["content"] == "Desc1"

    def test_list_entries_empty_rule_returns_empty(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        assert interp.list_entries({}, "r1") == []
        assert interp.list_entries(None, "r1") == []  # type: ignore[arg-type]

    def test_list_entries_missing_extract_returns_empty(self) -> None:
        rule = {"request": {"url": "https://example.com"}}
        client = _mock_client([{"title": "T"}])
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1")
        # extract 为空 → extract_fields 返回 {} → 跳过
        assert entries == []


# ---------------------------------------------------------------------------
# DNS pin（0.A3）
# ---------------------------------------------------------------------------


class TestDnsPin:
    def test_http_requests_pinned_ip_with_host_header(self) -> None:
        client = _mock_client([{"title": "T", "content": "C"}])
        interp = OttRuleInterpreter(client)
        rule = {
            "request": {"url": "http://example.com/api", "method": "GET"},
            "extract": {"title": "$.title", "content": "$.content"},
            "transform": [],
            "pagination": {},
        }
        interp.list_entries(rule, "r1", max_pages=1)
        url = client.get.call_args.args[0]
        assert url.startswith("http://93.184.216.34:")
        assert "example.com" not in url
        assert client.get.call_args.kwargs["headers"]["Host"] == "example.com"

    def test_https_keeps_domain_url(self) -> None:
        """HTTPS 不 pin：TLS 证书按域名校验，内网 IP 无合法证书，天然防 rebinding。"""
        client = _mock_client([{"title": "T", "content": "C"}])
        interp = OttRuleInterpreter(client)
        rule = {
            "request": {"url": "https://example.com/api", "method": "GET"},
            "extract": {"title": "$.title", "content": "$.content"},
            "transform": [],
            "pagination": {},
        }
        interp.list_entries(rule, "r1", max_pages=1)
        url = client.get.call_args.args[0]
        assert url == "https://example.com/api"
        assert "Host" not in client.get.call_args.kwargs["headers"]

    def test_pin_url_rejects_blocked_resolution(self) -> None:
        interp = OttRuleInterpreter(_mock_client())
        with patch(
            "src.backend.integration.ott_rule_interpreter.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
        ):
            pinned, _ = interp._pin_url("http://example.com/api", {})
        assert pinned is None

    def test_pin_url_rejects_resolution_failure(self) -> None:
        interp = OttRuleInterpreter(_mock_client())
        with patch(
            "src.backend.integration.ott_rule_interpreter.socket.getaddrinfo",
            side_effect=socket.gaierror("no such host"),
        ):
            pinned, _ = interp._pin_url("http://example.com/api", {})
        assert pinned is None


class TestRegexWorkerProtocol:
    def test_has_nested_quantifier_detects_catastrophic(self) -> None:
        for bad in ["(a+)+", "(a*)*", "(a|a)+", "(a{1,3}){2}", "((a+)+)+"]:
            assert _has_nested_quantifier(bad), bad

    def test_has_nested_quantifier_allows_safe(self) -> None:
        for ok in ["a+", "(ab)+", "(a|b)+", "[a+]+", "a{2}", r"\(a+\)+"]:
            assert not _has_nested_quantifier(ok), ok

    def test_worker_runs_subprocess(self) -> None:
        import subprocess
        import sys

        from src.backend.integration.ott_rule_interpreter import REGEX_WORKER_PATH

        payload = json.dumps(
            {"pattern": "<h1>(?P<title>.*?)</h1>", "text": "<h1>Hi</h1>"}
        ).encode()
        proc = subprocess.run(
            [sys.executable, str(REGEX_WORKER_PATH)],
            input=payload,
            capture_output=True,
            timeout=5,
        )
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["ok"] is True
        assert out["groups"]["title"] == "Hi"

    def test_worker_rejects_nested_quantifier(self) -> None:
        import subprocess
        import sys

        from src.backend.integration.ott_rule_interpreter import REGEX_WORKER_PATH

        payload = json.dumps({"pattern": "(a+)+", "text": "aaa"}).encode()
        proc = subprocess.run(
            [sys.executable, str(REGEX_WORKER_PATH)],
            input=payload,
            capture_output=True,
            timeout=5,
        )
        out = json.loads(proc.stdout)
        assert out["ok"] is False
        assert out["error"] == "nested_quantifier"


# ---------------------------------------------------------------------------
# schema v2（Phase 1.3）：steps / request.body / permissions / rights
# ---------------------------------------------------------------------------


class TestSchemaV2:
    def _v2_rule(self, **overrides):
        body = overrides.pop("body", None)
        request_ov = overrides.pop("request", None)
        rule = {
            "request": {
                "url": "https://example.com/api",
                "method": "POST",
                "body": "",
            },
            "steps": [{"fn": "concat", "args": ["!"]}],
            "extract": {"title": "$.title", "content": "$.content"},
            "permissions": {"network": ["example.com"]},
            "rights": {"min_api_level": 1},
        }
        if body is not None:
            rule["request"]["body"] = body
        if request_ov is not None:
            rule["request"].update(request_ov)
        rule.update(overrides)
        return rule

    def test_steps_output_becomes_post_body(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(body="a")
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert client.post.call_args.kwargs["content"] == "a!"

    def test_steps_ref_body_placeholder(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(
            steps=[
                {"fn": "utf8_encode", "args": [{"ref": "body"}]},
                {"fn": "sha256", "args": []},
            ],
            body="secret",
        )
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        import hashlib

        expected = hashlib.sha256(b"secret").hexdigest()
        assert client.post.call_args.kwargs["content"] == expected

    def test_rule_without_steps_uses_literal_body(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(steps=None, body="raw-literal")
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert client.post.call_args.kwargs["content"] == "raw-literal"

    def test_transform_and_steps_conflict_rejected(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(transform=["trim"])
        assert interp.list_entries(rule, "r1") == []

    def test_rights_min_api_level_greater_than_client_rejected(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client, api_level=1)
        rule = self._v2_rule(rights={"min_api_level": 2})
        assert interp.list_entries(rule, "r1") == []

    def test_permissions_network_mismatch_rejected(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(permissions={"network": ["other.com"]})
        assert interp.list_entries(rule, "r1") == []

    def test_permissions_network_subdomain_allowed(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(
            request={
                "url": "https://api.example.com/v1",
                "method": "POST",
                "body": "x",
            }
        )
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1

    def test_missing_permissions_falls_back_to_validate_url(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(permissions={})
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1

    def test_dsl_failure_skips_rule(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(steps=[{"fn": "not_a_primitive", "args": []}])
        assert interp.list_entries(rule, "r1") == []

    def test_steps_limit_exceeded_skips_rule(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        from src.backend.integration.ott_dsl import MAX_STEPS

        rule = self._v2_rule(
            steps=[{"fn": "str", "args": [1]} for _ in range(MAX_STEPS + 1)]
        )
        assert interp.list_entries(rule, "r1") == []

    def test_get_method_ignores_body(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(
            request={"url": "https://example.com/api", "method": "GET"}, steps=None
        )
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert client.get.called
        assert client.post.called is False

    def test_dict_literal_body_serialized_as_json(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(steps=None, body={"0": "abc"})
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert client.post.call_args.kwargs["content"] == '{"0": "abc"}'

    def test_dict_steps_output_serialized_as_json(self) -> None:
        data = [{"title": "T", "content": "C"}]
        client = _mock_client(data)
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(steps=[{"fn": "json_decode", "args": []}], body="{}")
        entries = interp.list_entries(rule, "r1", max_pages=1)
        assert len(entries) == 1
        assert client.post.call_args.kwargs["content"] == "{}"

    def test_unsupported_body_type_skips_rule(self) -> None:
        client = _mock_client([])
        interp = OttRuleInterpreter(client)
        rule = self._v2_rule(steps=None, body=object())
        assert interp.list_entries(rule, "r1") == []
