"""OTT Repo ott-script 沙箱执行测试。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from src.backend.integration.ott_script_client import (
    ScriptCache,
    ScriptSandbox,
    execute_script,
)
from src.backend.integration.ott_script_runner import landlock_available


# ── 沙箱执行 ────────────────────────────────────────────────────────────


class TestScriptSandbox:
    def test_executes_fetch_entries(self) -> None:
        source = (
            "def fetch_entries():\n"
            '    return [{"title": "Hello", '
            '"content": "World"}]\n'
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "World"
        assert entries[0]["title"] == "Hello"
        assert entries[0]["content_mode"] == "inline"

    def test_normalizes_string_entries(self) -> None:
        source = 'def fetch_entries():\n    return ["简单文本"]\n'
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "简单文本"

    def test_skips_non_dict_non_string_entries(self) -> None:
        source = 'def fetch_entries():\n    return [123, None, {"content": "valid"}]\n'
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
        source = "def fetch_entries():\n    raise RuntimeError('boom')\n"
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_returns_empty_on_non_list_result(self) -> None:
        source = 'def fetch_entries():\n    return "not a list"\n'
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_rejects_urllib_request_at_runtime(self) -> None:
        """防御纵深：即使绕过 AST 检查，runner 受限 __import__ 也拒绝 urllib.request。"""
        source = (
            "import urllib.request\n"
            "def fetch_entries():\n"
            "    data = urllib.request.urlopen('file:///etc/passwd').read()\n"
            '    return [{"title": "T", "content": data.decode()}]\n'
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries == []

    def test_allows_urllib_parse_at_runtime(self) -> None:
        source = (
            "from urllib.parse import unquote\n"
            "def fetch_entries():\n"
            '    return [{"title": "T", "content": unquote("a%20b")}]\n'
        )
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert len(entries) == 1
        assert entries[0]["content"] == "a b"

    def test_entry_has_required_fields(self) -> None:
        source = 'def fetch_entries():\n    return [{"title": "T", "content": "C"}]\n'
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        e = entries[0]
        for field in (
            "entry_id",
            "title",
            "content",
            "char_count",
            "authority",
            "source_key",
            "content_mode",
        ):
            assert field in e, f"missing: {field}"

    def test_entry_id_is_deterministic(self) -> None:
        source = (
            'def fetch_entries():\n    return [{"title": "T", "content": "same"}]\n'
        )
        sandbox = ScriptSandbox()
        e1 = sandbox.execute(source, "test://script")
        e2 = sandbox.execute(source, "test://script")
        assert e1[0]["entry_id"] == e2[0]["entry_id"]

    def test_authority_is_script(self) -> None:
        source = 'def fetch_entries():\n    return [{"title": "T", "content": "C"}]\n'
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries[0]["authority"] == "script"

    @pytest.mark.skipif(
        not landlock_available(), reason="需要 Linux 内核 5.13+ Landlock"
    )
    def test_object_model_escape_cannot_read_arbitrary_files(self) -> None:
        # 对象模型逃逸：绕过受限 builtins 拿到真实 open，尝试读取白名单外
        # （家目录）的文件 —— 被 Landlock 拒绝。注意目标不能放在 /tmp 下：
        # 沙箱脚本目录在 /tmp，路径规则是层级性的，/tmp 整树被放行。
        secret = Path.home() / ".cache" / f"typetype-escape-{os.getpid()}.tmp"
        secret.write_text("SECRET")
        try:
            target = repr(str(secret))
            source = (
                "def fetch_entries():\n"
                "    for c in ().__class__.__bases__[0].__subclasses__():\n"
                "        try:\n"
                "            g = c.__init__.__globals__\n"
                "        except AttributeError:\n"
                "            continue\n"
                "        if 'open' in g:\n"
                "            try:\n"
                "                g['open'](" + target + ").read()\n"
                "                return [{'title': 'escape', 'content': 'READ_OK'}]\n"
                "            except OSError:\n"
                "                return [{'title': 'escape', 'content': 'READ_BLOCKED'}]\n"
                "    return [{'title': 'escape', 'content': 'NO_CLASS'}]\n"
            )
            sandbox = ScriptSandbox()
            entries = sandbox.execute(source, "test://script")
            assert entries[0]["content"] == "READ_BLOCKED"
        finally:
            secret.unlink(missing_ok=True)


class TestExecuteScript:
    def test_convenience_function(self) -> None:
        source = (
            'def fetch_entries():\n    return [{"title": "T", "content": "Hello"}]\n'
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


class TestScriptDisabled:
    def test_cache_disabled_returns_none_without_fetch(self, tmp_path) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        cache = ScriptCache(tmp_path / "scripts", mock_http, enabled=False)
        assert cache.get_script("https://example.com/s.py") is None
        mock_http.get.assert_not_called()

    def test_sandbox_disabled_returns_empty(self) -> None:
        sandbox = ScriptSandbox(enabled=False)
        source = 'def fetch_entries():\n    return [{"content": "x"}]\n'
        assert sandbox.execute(source, "test://script") == []
