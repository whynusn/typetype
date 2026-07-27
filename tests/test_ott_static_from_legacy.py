"""验证旧 registry/CI 系统的静态内容能在新 OTT Core v1 管线中直接使用。"""

from __future__ import annotations

import json
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestLegacyStaticContent:
    """旧 content/*.json → 新 OTT Static Profile entries.json。"""

    def test_static_entries_file_is_valid_ott_format(self) -> None:
        """entries.json 符合 OTT Core v1 Static Profile 格式。"""
        path = FIXTURES / "ott-static" / "entries.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert len(data["entries"]) >= 2

        for entry in data["entries"]:
            assert "entry_id" in entry
            assert "title" in entry
            assert "content" in entry
            assert "content_mode" in entry
            assert entry["content_mode"] == "inline"

    def test_ott_client_can_parse_static_entries(self) -> None:
        """OttClient.list_entries 能解析该 entries.json（摘要无 content，符合规范）。"""
        from src.backend.integration.ott_client import OttClient

        path = FIXTURES / "ott-static" / "entries.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        # 模拟 fetch_json：返回 raw entries 数据
        def fetch_json(cache_key, url, mirror_url, max_bytes):
            return raw

        client = OttClient(
            primary_url="https://example.com/ott/",
            mirror_url="",
            authority="test-static",
            fetch_json=fetch_json,
            fetch_text=lambda *a, **k: None,
            max_content_bytes=1_048_576,
        )
        entries = client.list_entries()
        assert entries is not None
        assert len(entries) == 2
        assert entries[0]["title"] == "经典中文短句练习"
        assert entries[0]["authority"] == "test-static"
        # 摘要字段存在
        assert "entry_id" in entries[0]
        assert "content_mode" in entries[0]
        assert "char_count" in entries[0]


class TestLegacyScriptAsRule:
    """旧 fetch_daily.py（Hitokoto）→ 新 ott-rule。"""

    def test_hitokoto_rule_file_is_valid(self) -> None:
        """hitokoto.json 是有效的 ott-rule 定义。"""
        path = FIXTURES / "rule-samples" / "hitokoto.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["type"] == "ott-rule"
        assert data["rule_id"] == "hitokoto"
        assert data["rule"]["request"]["url"] == "https://v1.hitokoto.cn/?c=i"
        assert "$.hitokoto" in data["rule"]["extract"].values()

    def test_hitokoto_rule_produces_entries(self) -> None:
        """解释器执行 hitokoto rule 能抓到条目（mock HTTP）。"""
        from src.backend.integration.ott_rule_interpreter import OttRuleInterpreter
        from unittest.mock import MagicMock
        import httpx

        path = FIXTURES / "rule-samples" / "hitokoto.json"
        rule = json.loads(path.read_text(encoding="utf-8"))

        # mock Hitokoto 响应
        hitokoto_data = {
            "hitokoto": "山重水复疑无路，柳暗花明又一村。",
            "from": "陆游《游山西村》",
            "from_who": "陆游",
        }
        mock_client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = json.dumps(hitokoto_data)
        resp.headers = {"content-length": "100"}
        resp.raise_for_status = MagicMock()
        mock_client.get.return_value = resp

        interp = OttRuleInterpreter(mock_client)
        entries = interp.list_entries(rule["rule"], rule["rule_id"], max_pages=1)
        assert len(entries) == 1
        assert entries[0]["content"] == "山重水复疑无路，柳暗花明又一村。"
        assert entries[0]["title"] == "陆游《游山西村》"
        assert entries[0]["authority"] == "rule:hitokoto"
