"""OTT Repo ott-script 沙箱执行测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from src.backend.integration.ott_script_client import (
    ScriptCache,
    ScriptSandbox,
    execute_script,
)


# ── 沙箱执行 ────────────────────────────────────────────────────────────


class TestScriptSandbox:
    def test_executes_fetch_entries(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"Hello\", "\
            "\"content\": \"World\"}]\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "World"
        assert entries[0]["title"] == "Hello"
        assert entries[0]["content_mode"] == "inline"

    def test_normalizes_string_entries(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [\"简单文本\"]\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "简单文本"

    def test_skips_non_dict_non_string_entries(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [123, None, {\"content\": \"valid\"}]\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "valid"

    def test_returns_empty_when_no_fetch_entries(self) -> None:
        source = "x = 1\n"
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_returns_empty_on_exception(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    raise RuntimeError('boom')\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_returns_empty_on_non_list_result(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return \"not a list\"\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_entry_has_required_fields(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"T\", \"content\": \"C\"}]\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        e = entries[0]
        for field in ("entry_id", "title", "content", "char_count",
                      "authority", "source_key", "content_mode"):
            assert field in e, f"missing: {field}"

    def test_entry_id_is_deterministic(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"T\", \"content\": \"same\"}]\n"
        )
        sandbox = ScriptSandbox()
        e1 = sandbox.execute(source, "test://script")
        e2 = sandbox.execute(source, "test://script")
        assert e1[0]["entry_id"] == e2[0]["entry_id"]

    def test_authority_is_script(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"T\", \"content\": \"C\"}]\n"
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries[0]["authority"] == "script"


class TestExecuteScript:
    def test_convenience_function(self) -> None:
        source = (
            "def fetch_entries():\n"
            "    return [{\"title\": \"T\", \"content\": \"Hello\"}]\n"
        )
        entries = execute_script(source, "test://script")
        assert len(entries) == 1


# ── 缓存 ────────────────────────────────────────────────────────────────


class TestScriptCache:
    def test_cache_fetches_and_writes(self, tmp_path) -> None:
        source = "def fetch_entries():\n    return []\n"
        mock_http = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = source
        resp.headers = {"content-length": str(len(source))}
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        cache = ScriptCache(tmp_path / "scripts", mock_http)
        result = cache.get_script("https://example.com/script.py")
        assert result == source

    def test_cache_rejects_unsafe_script(self, tmp_path) -> None:
        dangerous = (
            "import os\n"
            "def fetch_entries():\n"
            "    os.system('echo pwned')\n"
            "    return []\n"
        )
        mock_http = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = dangerous
        resp.headers = {"content-length": str(len(dangerous))}
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        cache = ScriptCache(tmp_path / "scripts", mock_http)
        result = cache.get_script("https://example.com/bad.py")
        assert result is None  # 安全检查失败，不缓存

    def test_cache_falls_back_to_stale(self, tmp_path) -> None:
        # 先写一个有效缓存
        safe_source = "def fetch_entries():\n    return []\n"
        cache_dir = tmp_path / "scripts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        from src.backend.integration.ott_script_client import script_cache_key
        cache_file = cache_dir / f"{script_cache_key('https://example.com/s.py')}.py"
        cache_file.write_text(safe_source, encoding="utf-8")

        # 网络失败
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.get.side_effect = httpx.ConnectError("offline")

        cache = ScriptCache(cache_dir, mock_http)
        result = cache.get_script("https://example.com/s.py", ttl_seconds=0)
        # 网络失败但缓存存在 → 返回缓存
        assert result == safe_source
