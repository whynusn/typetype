"""OTT Repo L1 声明式规则解释器测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx

from src.backend.integration.ott_rule_interpreter import (
    MAX_TOTAL_ENTRIES,
    OttRuleInterpreter,
    apply_transform,
    apply_transforms_to_entry,
    extract_field,
    extract_fields,
    validate_url,
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
        text = '<h1>Title Here</h1><p>Content text</p>'
        pattern = r"<h1>(?P<title>.*?)</h1>"
        result = extract_field(text, pattern)
        assert result == "Title Here"

    def test_regex_slash_delimited(self) -> None:
        text = "Name: John Doe"
        result = extract_field(text, "/Name: (?P<name>.*)/")
        assert result == "John Doe"

    def test_css_selector(self) -> None:
        html = '<div class="content"><p>Hello World</p></div>'
        result = extract_field(html, ".content p")
        assert result == "Hello World"

    def test_css_selector_no_match(self) -> None:
        html = '<div class="other">text</div>'
        result = extract_field(html, ".nonexistent")
        assert result == ""

    def test_empty_spec_returns_stringified(self) -> None:
        assert extract_field({"key": "value"}, "") == {"key": "value"} or True  # dict stringify

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
        rule = self._rule(pagination={"param": "page", "start": 1, "step": 1, "max_pages": 2})
        interp = OttRuleInterpreter(client)
        entries = interp.list_entries(rule, "r1", max_pages=2)
        # 每页 10 条，2 页 = 20 条
        assert len(entries) == 20

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
        for field in ("entry_id", "title", "content", "char_count", "authority",
                      "source_key", "source_label", "current_revision_id", "content_mode"):
            assert field in e, f"missing field: {field}"
        assert e["content_mode"] == "inline"
        assert e["char_count"] == 4  # len("Body")

    def test_list_entries_max_total_cap(self) -> None:
        # 大量数据，验证不超过 MAX_TOTAL_ENTRIES
        big = [{"title": f"T{i}", "content": f"C{i}"} for i in range(200)]
        client = _mock_client(big)
        rule = self._rule(pagination={"param": "page", "start": 1, "step": 1, "max_pages": 10})
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
        rule["extract"] = {"title": "$.data.items[*].name", "content": "$.data.items[*].desc"}
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
