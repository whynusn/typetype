"""OTT Repo ott-script 沙箱执行测试。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.backend.integration import ott_script_runner as runner
from src.backend.integration.ott_script_client import (
    ScriptCache,
    ScriptSandbox,
    execute_script,
)
from src.backend.integration.ott_script_runner import landlock_available


class FakeTokenStore:
    """测试用内存 token store（模拟 SecureTokenStore 的按名存取）。"""

    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        self._tokens = dict(tokens or {})

    def get_token(self, key: str) -> str | None:
        return self._tokens.get(key)

    def save_token(self, key: str, token: str) -> None:
        self._tokens[key] = token

    def delete_token(self, key: str) -> None:
        self._tokens.pop(key, None)


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
        """authority 按脚本 URL 指纹命名空间化（与联邦层一致）。"""
        from src.backend.integration.ott_normalization import _script_authority

        source = 'def fetch_entries():\n    return [{"title": "T", "content": "C"}]\n'
        sandbox = ScriptSandbox()
        entries = sandbox.execute(source, "test://script")
        assert entries[0]["authority"] == _script_authority("test://script")

    def test_authority_namespaced_by_url(self) -> None:
        """不同 URL 的脚本 authority 不同；source_key 保持稳定分组键。"""
        from src.backend.integration.ott_normalization import _script_authority

        source = 'def fetch_entries():\n    return [{"title": "T", "content": "C"}]\n'
        sandbox = ScriptSandbox()
        a = sandbox.execute(source, "https://example.com/a.py")
        b = sandbox.execute(source, "https://example.com/b.py")
        assert a[0]["authority"] == _script_authority("https://example.com/a.py")
        assert b[0]["authority"] == _script_authority("https://example.com/b.py")
        assert a[0]["authority"] != b[0]["authority"]
        assert a[0]["source_key"] == "script"

    @pytest.mark.skipif(
        not landlock_available(), reason="需要 Linux 内核 5.13+ Landlock"
    )
    def test_object_model_escape_cannot_read_arbitrary_files(self) -> None:
        # 对象模型逃逸：绕过受限 builtins 拿到真实 open，尝试读取白名单外
        # （家目录）的文件 —— 被 Landlock 拒绝。注意目标不能放在 /tmp 下：
        # 沙箱脚本目录在 /tmp，路径规则是层级性的，/tmp 整树被放行。
        secret = Path.home() / ".cache" / f"typetype-escape-{os.getpid()}.tmp"
        secret.parent.mkdir(parents=True, exist_ok=True)
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


# ── 双沙箱守卫（Landlock + seccomp 均不可用 → 拒绝执行）────────────────


class TestSandboxGuard:
    """双沙箱不可用时拒绝执行 L3 脚本；单侧可用照常执行。"""

    def test_refuses_when_both_sandboxes_unavailable(self, tmp_path) -> None:
        script = tmp_path / "s.py"
        script.write_text(
            "def fetch_entries():\n    return [{'content': 'x'}]\n",
            encoding="utf-8",
        )
        with (
            patch.object(runner, "landlock_available", return_value=False),
            patch.object(runner, "seccomp_available", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="拒绝执行"):
                runner.run_script(str(script))

    def test_executes_when_only_landlock_available(self, tmp_path) -> None:
        script = tmp_path / "s.py"
        script.write_text(
            "def fetch_entries():\n    return [{'content': 'landlock'}]\n",
            encoding="utf-8",
        )
        with (
            patch.object(runner, "landlock_available", return_value=True),
            patch.object(runner, "seccomp_available", return_value=False),
        ):
            entries = runner.run_script(str(script))
        assert entries == [{"content": "landlock"}]

    def test_executes_when_only_seccomp_available(self, tmp_path) -> None:
        script = tmp_path / "s.py"
        script.write_text(
            "def fetch_entries():\n    return [{'content': 'seccomp'}]\n",
            encoding="utf-8",
        )
        with (
            patch.object(runner, "landlock_available", return_value=False),
            patch.object(runner, "seccomp_available", return_value=True),
        ):
            entries = runner.run_script(str(script))
        assert entries == [{"content": "seccomp"}]


# ── API level 门槛（ADR-011 Phase 2.6）────────────────────────────────


class TestScriptApiLevel:
    def test_skips_when_api_level_above_client(self) -> None:
        source = "def fetch_entries():\n    return []\n"
        with patch(
            "src.backend.integration.ott_script_client.subprocess.Popen"
        ) as mock_popen:
            sandbox = ScriptSandbox()
            entries = sandbox.execute(source, "test://script", min_api_level=999)
        assert entries == []
        mock_popen.assert_not_called()

    def test_skips_when_api_level_invalid(self) -> None:
        source = "def fetch_entries():\n    return []\n"
        with patch(
            "src.backend.integration.ott_script_client.subprocess.Popen"
        ) as mock_popen:
            sandbox = ScriptSandbox()
            entries = sandbox.execute(source, "test://script", min_api_level="abc")
        assert entries == []
        mock_popen.assert_not_called()

    def test_executes_when_api_level_at_or_below_client(self) -> None:
        from src.backend.integration.ott_script_client import CLIENT_API_LEVEL

        source = 'def fetch_entries():\n    return [{"content": "ok"}]\n'
        entries = ScriptSandbox().execute(
            source, "test://script", min_api_level=CLIENT_API_LEVEL
        )
        assert entries[0]["content"] == "ok"


class TestScriptNetworkAllowlist:
    def test_allowlist_passed_in_config_json(self) -> None:
        source = "def fetch_entries():\n    return []\n"
        with patch(
            "src.backend.integration.ott_script_client.subprocess.Popen"
        ) as mock_popen:
            proc = MagicMock()
            proc.communicate.return_value = ("[]", "")
            proc.returncode = 0
            mock_popen.return_value = proc
            sandbox = ScriptSandbox()
            entries = sandbox.execute(
                source, "test://script", network_allowlist=["api.example.com"]
            )
        assert entries == []
        input_arg = (
            proc.communicate.call_args.kwargs.get("input")
            or proc.communicate.call_args.args[0]
        )
        payload = json.loads(input_arg)
        assert payload["network_allowlist"] == ["api.example.com"]

    def test_empty_allowlist_in_config_when_absent(self) -> None:
        source = "def fetch_entries():\n    return []\n"
        with patch(
            "src.backend.integration.ott_script_client.subprocess.Popen"
        ) as mock_popen:
            proc = MagicMock()
            proc.communicate.return_value = ("[]", "")
            proc.returncode = 0
            mock_popen.return_value = proc
            entries = ScriptSandbox().execute(source, "test://script")
        assert entries == []
        input_arg = (
            proc.communicate.call_args.kwargs.get("input")
            or proc.communicate.call_args.args[0]
        )
        payload = json.loads(input_arg)
        assert payload["network_allowlist"] == []


# ── 网络白名单门控（runner 层，ADR-011 Phase 2.2）─────────────────────


class TestNetworkGate:
    def test_denies_everything_with_empty_allowlist(self) -> None:
        gate = runner._NetworkGate([])
        assert not gate.allows("https://example.com")
        assert not gate.allows("http://1.2.3.4")

    def test_denies_everything_with_none_allowlist(self) -> None:
        gate = runner._NetworkGate(None)
        assert not gate.allows("https://example.com")

    def test_allows_exact_host_and_subdomain(self) -> None:
        gate = runner._NetworkGate(["example.com"])
        assert gate.allows("https://example.com/path")
        assert gate.allows("https://api.example.com/x")
        assert not gate.allows("https://notexample.com")
        assert not gate.allows("https://evil-example.com")

    def test_accepts_full_url_entry(self) -> None:
        gate = runner._NetworkGate(["https://example.com/ott"])
        assert gate.allows("https://api.example.com/x")

    def test_rejects_non_http_scheme(self) -> None:
        gate = runner._NetworkGate(["example.com"])
        assert not gate.allows("ftp://example.com")
        assert not gate.allows("file:///etc/passwd")

    def test_check_raises_on_denied(self) -> None:
        gate = runner._NetworkGate(["example.com"])
        gate.check("https://example.com")  # 不抛
        with pytest.raises(runner._NetworkDeniedError):
            gate.check("https://other.com")

    def test_normalizes_case_and_scheme_entries(self) -> None:
        gate = runner._NetworkGate(["HTTP://EXAMPLE.COM", "https://api.other.org"])
        assert gate.allows("https://example.com")
        assert gate.allows("https://api.other.org")

    def test_rejects_tld_only_allowlist(self) -> None:
        """TLD-only 白名单（com）拒绝一切 —— 防 *.com 近乎完全网络访问。"""
        gate = runner._NetworkGate(["com"])
        assert not gate._entries
        assert not gate.allows("https://example.com")
        assert not gate.allows("https://api.example.com")

    def test_rejects_ip_literal_allowlist(self) -> None:
        """IP 字面量/CIDR 白名单拒绝 —— 白名单只接受域名形式。"""
        for bad in ["127.0.0.1", "0.0.0.0/0", "10.0.0.0/8", "::1", "::ffff:10.0.0.1"]:
            gate = runner._NetworkGate([bad])
            assert not gate._entries, f"{bad!r} 不应入白名单"
        gate = runner._NetworkGate(["0.0.0.0/0"])
        assert not gate.allows("https://example.com")

    def test_keeps_valid_domain_allowlist(self) -> None:
        gate = runner._NetworkGate(["example.com", "a.b.example.org"])
        assert gate.allows("https://example.com")
        assert gate.allows("https://x.a.b.example.org")
        assert not gate.allows("https://evil.com")


class TestDnsPin:
    def test_is_private_ip(self) -> None:
        assert runner._is_private_ip("127.0.0.1")
        assert runner._is_private_ip("10.0.0.1")
        assert runner._is_private_ip("192.168.1.1")
        assert runner._is_private_ip("169.254.1.1")
        assert runner._is_private_ip("::1")
        assert runner._is_private_ip("not-an-ip")
        assert not runner._is_private_ip("8.8.8.8")

    def test_is_private_ip_filters_ipv4_mapped(self) -> None:
        """IPv4-mapped IPv6（::ffff:10.0.0.1）必须判为内网 —— 防 DNS pin 绕过 SSRF。"""
        assert runner._is_private_ip("::ffff:10.0.0.1")
        assert runner._is_private_ip("::ffff:127.0.0.1")
        assert runner._is_private_ip("::ffff:192.168.1.1")
        assert runner._is_private_ip("::ffff:169.254.1.1")
        assert not runner._is_private_ip("::ffff:8.8.8.8")

    def test_pinned_getaddrinfo_filters_loopback(self) -> None:
        import socket

        pinned = runner._make_pinned_getaddrinfo(socket.getaddrinfo)
        results = pinned("localhost", 80)
        assert all(not runner._is_private_ip(r[4][0]) for r in results)


@pytest.mark.skipif(
    not runner.landlock_available() and not runner.seccomp_available(),
    reason="双沙箱均不可用，runner 拒绝执行 L3 脚本",
)
class TestRunnerNetworkGate:
    def test_runner_blocks_network_without_allowlist(self, tmp_path) -> None:
        script = tmp_path / "net_deny.py"
        script.write_text(
            "import httpx\n"
            "def fetch_entries():\n"
            "    try:\n"
            "        httpx.get('https://example.com')\n"
            "        return [{'content': 'unexpected'}]\n"
            "    except Exception:\n"
            "        return [{'content': 'denied'}]\n"
        )
        proc = subprocess.run(
            [sys.executable, str(Path(runner.__file__)), str(script)],
            input=json.dumps({"secrets": {}, "network_allowlist": []}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entries = json.loads(proc.stdout)
        assert entries[0]["content"] == "denied"

    def test_runner_rejects_allowlisted_loopback_via_dns_pin(self, tmp_path) -> None:
        script = tmp_path / "net_pin.py"
        script.write_text(
            "import httpx\n"
            "def fetch_entries():\n"
            "    try:\n"
            "        httpx.get('http://localhost:1')\n"
            "        return [{'content': 'unexpected'}]\n"
            "    except Exception:\n"
            "        return [{'content': 'pinned'}]\n"
        )
        proc = subprocess.run(
            [sys.executable, str(Path(runner.__file__)), str(script)],
            input=json.dumps({"secrets": {}, "network_allowlist": ["localhost"]}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entries = json.loads(proc.stdout)
        assert entries[0]["content"] == "pinned"

    def test_runner_rejects_http_client_import(self, tmp_path) -> None:
        """http 模块已移出白名单：脚本 import http.client 必须被拒绝。"""
        script = tmp_path / "http_client_import.py"
        script.write_text(
            "def fetch_entries():\n"
            "    try:\n"
            "        import http.client\n"
            "        return [{'content': 'imported'}]\n"
            "    except ImportError:\n"
            "        return [{'content': 'blocked'}]\n"
        )
        proc = subprocess.run(
            [sys.executable, str(Path(runner.__file__)), str(script)],
            input=json.dumps({"secrets": {}, "network_allowlist": []}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entries = json.loads(proc.stdout)
        assert entries[0]["content"] == "blocked"

    def test_runner_blocks_non_allowlisted_host(self, tmp_path) -> None:
        """非空白名单下，白名单外 host 的请求仍被 gate 拒绝。"""
        script = tmp_path / "net_deny_allow.py"
        script.write_text(
            "import httpx\n"
            "def fetch_entries():\n"
            "    try:\n"
            "        httpx.get('https://evil.com')\n"
            "        return [{'content': 'unexpected'}]\n"
            "    except Exception:\n"
            "        return [{'content': 'denied'}]\n"
        )
        proc = subprocess.run(
            [sys.executable, str(Path(runner.__file__)), str(script)],
            input=json.dumps({"secrets": {}, "network_allowlist": ["api.example.com"]}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entries = json.loads(proc.stdout)
        assert entries[0]["content"] == "denied"


# ── Landlock /etc 缩小 ─────────────────────────────────────────────────


class TestLandlockNarrowing:
    """_apply_landlock 的 /etc 只按文件授予（mock syscall，不依赖真实内核）。"""

    def test_etc_granted_per_file_with_read_only(self) -> None:
        open_calls: list[tuple[str, int]] = []
        add_calls: list[tuple[int, int]] = []
        fd_map: dict[int, str] = {}
        fd_counter = iter(range(100, 200))

        def fake_open(path, flags):
            open_calls.append((path, flags))
            fd = next(fd_counter)
            fd_map[fd] = path
            return fd

        def fake_add_rule(ruleset_fd, access, parent_fd):
            add_calls.append((access, parent_fd))

        with (
            patch.object(runner, "_landlock_create", return_value=7),
            patch.object(runner, "_landlock_add_rule", side_effect=fake_add_rule),
            patch.object(runner, "_landlock_set_no_new_privs"),
            patch.object(runner, "_landlock_restrict_self"),
            patch.object(runner.os, "open", side_effect=fake_open),
            patch.object(runner.os, "close"),
        ):
            runner._apply_landlock("/tmp/ott-script-test-dir")

        # /etc 不再整目录打开，只按文件打开
        assert not any(path == "/etc" for path, _ in open_calls)
        opened_files = [
            path for path, flags in open_calls if not (flags & os.O_DIRECTORY)
        ]
        assert opened_files == ["/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"]

        # 文件规则只授 READ_FILE，且全部落在 _ETC_DNS_FILES 上
        file_rules = [
            (fd_map[fd], access)
            for access, fd in add_calls
            if access == runner._LANDLOCK_FS_READ_FILE
        ]
        assert file_rules == [
            ("/etc/resolv.conf", runner._LANDLOCK_FS_READ_FILE),
            ("/etc/hosts", runner._LANDLOCK_FS_READ_FILE),
            ("/etc/nsswitch.conf", runner._LANDLOCK_FS_READ_FILE),
        ]

    def test_skips_missing_etc_file_and_continues(self) -> None:
        open_calls: list[tuple[str, int]] = []
        add_calls: list[tuple[int, int]] = []
        fd_map: dict[int, str] = {}
        fd_counter = iter(range(200, 300))

        def fake_open(path, flags):
            if path == "/etc/resolv.conf":
                raise OSError(2, "No such file or directory")
            open_calls.append((path, flags))
            fd = next(fd_counter)
            fd_map[fd] = path
            return fd

        def fake_add_rule(ruleset_fd, access, parent_fd):
            add_calls.append((access, parent_fd))

        with (
            patch.object(runner, "_landlock_create", return_value=7),
            patch.object(runner, "_landlock_add_rule", side_effect=fake_add_rule),
            patch.object(runner, "_landlock_set_no_new_privs"),
            patch.object(runner, "_landlock_restrict_self") as mock_restrict,
            patch.object(runner.os, "open", side_effect=fake_open),
            patch.object(runner.os, "close"),
        ):
            runner._apply_landlock("/tmp/ott-script-test-dir")

        assert "/etc/resolv.conf" not in [p for p, _ in open_calls]
        file_rules = [
            (fd_map[fd], access)
            for access, fd in add_calls
            if access == runner._LANDLOCK_FS_READ_FILE
        ]
        assert file_rules == [
            ("/etc/hosts", runner._LANDLOCK_FS_READ_FILE),
            ("/etc/nsswitch.conf", runner._LANDLOCK_FS_READ_FILE),
        ]
        # 缺失文件不中断整体 Landlock 限制
        mock_restrict.assert_called_once_with(7)


# ── seccomp 系统调用过滤 ──────────────────────────────────────────────


class TestSeccomp:
    def test_available_returns_bool(self) -> None:
        """探测返回 bool 且不抛异常（Linux 上真实子进程探测，其他平台 False）。"""
        assert isinstance(runner.seccomp_available(), bool)

    def test_filter_denies_escapes_and_allows_default(self) -> None:
        """BPF 程序结构：arch 检查 → 逐条 deny 配对 KILL → 末尾默认 ALLOW。"""
        deny = runner._DENY_ESCAPES["x86_64"]
        prog = runner._build_seccomp_filter(runner._AUDIT_ARCH_X86_64, deny)

        assert prog[0] == (runner._BPF_LD_W_ABS, 0, 0, 4)  # seccomp_data.arch
        assert prog[1] == (runner._BPF_JMP_JEQ_K, 1, 0, runner._AUDIT_ARCH_X86_64)
        assert prog[2] == (runner._BPF_RET_K, 0, 0, runner._SECCOMP_RET_ALLOW)
        assert prog[3] == (runner._BPF_LD_W_ABS, 0, 0, 0)  # seccomp_data.nr

        # 每个 deny 条目都有 JEQ + RET KILL 对（prog[4:] 排除开头的 arch JEQ）
        deny_nrs = {ins[3] for ins in prog[4:] if ins[0] == runner._BPF_JMP_JEQ_K}
        assert deny_nrs == set(deny)
        kill_rets = [
            ins
            for ins in prog
            if ins[0] == runner._BPF_RET_K
            and ins[3] == runner._SECCOMP_RET_KILL_PROCESS
        ]
        assert len(kill_rets) == len(deny)
        # 默认放行，脚本合法网络/文件 IO 不误杀
        assert prog[-1] == (runner._BPF_RET_K, 0, 0, runner._SECCOMP_RET_ALLOW)

    @pytest.mark.skipif(
        not runner.seccomp_available(), reason="需要内核 seccomp filter 支持"
    )
    def test_denied_syscall_is_killed(self) -> None:
        """deny 表内的 syscall（ptrace）在应用过滤器后被 SIGSYS 击杀。"""
        repo_root = Path(__file__).resolve().parents[1]
        code = (
            "import ctypes, sys\n"
            f"sys.path.insert(0, {str(repo_root)!r})\n"
            "from src.backend.integration import ott_script_runner as r\n"
            "r._apply_seccomp()\n"
            "libc = ctypes.CDLL(None, use_errno=True)\n"
            "libc.ptrace.restype = ctypes.c_long\n"
            "libc.ptrace(0, 0, None, None)  # PTRACE_TRACEME → 命中 deny 表\n"
            "print('PTRACE_CALLED')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert proc.returncode != 0
        assert "PTRACE_CALLED" not in proc.stdout

    @pytest.mark.skipif(
        not runner.seccomp_available(), reason="需要内核 seccomp filter 支持"
    )
    def test_normal_script_runs_under_seccomp(self, tmp_path) -> None:
        """正常脚本（白名单 stdlib + 简单计算）在 seccomp 过滤下不误杀。"""
        script = tmp_path / "sane.py"
        script.write_text(
            "def fetch_entries():\n"
            "    import json, random, time\n"
            "    time.sleep(0.01)\n"
            "    return [{'title': 'T', 'content': str(random.randint(0, 100))}]\n",
            encoding="utf-8",
        )
        runner_path = Path(runner.__file__).resolve()
        proc = subprocess.run(
            [sys.executable, str(runner_path), str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entries = json.loads(proc.stdout)
        assert len(entries) == 1
        assert entries[0]["content"].isdigit()


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


# ── 凭据注入（ADR-011 Phase 5.4）───────────────────────────────────────


class TestScriptSandboxSecrets:
    def test_get_secret_reads_fd_once_and_closes(self) -> None:
        """子进程侧：从 fd 读一次，值匹配，fd 关闭，再次读取报错。"""
        r, w = os.pipe()
        try:
            os.write(w, b"api-token-123")
            os.close(w)
            helper = runner._SandboxSecrets({"k": r})
            assert helper.get_secret("k") == "api-token-123"
            with pytest.raises(RuntimeError):
                helper.get_secret("k")
            with pytest.raises(OSError):
                os.fstat(r)  # fd 已关闭
        finally:
            try:
                os.close(r)
            except OSError:
                pass

    def test_get_secret_rejects_undeclared_name(self) -> None:
        helper = runner._SandboxSecrets({})
        with pytest.raises(RuntimeError):
            helper.get_secret("undeclared")

    def test_execute_injects_declared_secret(self) -> None:
        """父进程 → 一次性 fd → 子进程 sandbox.get_secret 取值（全链路）。"""
        source = (
            "def fetch_entries():\n"
            '    v = sandbox.get_secret("k")\n'
            '    return [{"title": "T", "content": v}]\n'
        )
        store = FakeTokenStore({"k": "top-secret-value"})
        sandbox = ScriptSandbox(token_store=store)
        entries = sandbox.execute(source, "test://script", secret_names=["k"])
        assert len(entries) == 1
        assert entries[0]["content"] == "top-secret-value"

    def test_execute_injects_multiple_secrets(self) -> None:
        source = (
            "def fetch_entries():\n"
            '    return [{"title": "T", '
            '"content": sandbox.get_secret("a") + "|" + sandbox.get_secret("b")}]\n'
        )
        store = FakeTokenStore({"a": "A", "b": "B"})
        sandbox = ScriptSandbox(token_store=store)
        entries = sandbox.execute(source, "test://script", secret_names=["a", "b"])
        assert entries[0]["content"] == "A|B"

    def test_execute_fails_when_secret_missing(self) -> None:
        """凭据缺失 → 整体失败（返回 []，不静默继续）。"""
        source = (
            'def fetch_entries():\n    return [{"content": sandbox.get_secret("k")}]\n'
        )
        sandbox = ScriptSandbox(token_store=FakeTokenStore({}))
        assert sandbox.execute(source, "test://script", secret_names=["k"]) == []

    def test_no_helper_without_declared_secrets(self) -> None:
        """未声明凭据时脚本 globals 不注入 sandbox 助手。"""
        source = (
            'def fetch_entries():\n    return [{"content": sandbox.get_secret("k")}]\n'
        )
        sandbox = ScriptSandbox()
        assert sandbox.execute(source, "test://script") == []

    def test_secret_not_written_to_sandbox_filesystem(self, tmp_path) -> None:
        """凭据值不落入沙箱脚本目录（Landlock 白名单内可写区）。"""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        source = (
            'def fetch_entries():\n    return [{"content": sandbox.get_secret("k")}]\n'
        )
        with (
            patch(
                "src.backend.integration.ott_script_client.tempfile.mkdtemp",
                return_value=str(sandbox_dir),
            ),
            patch("src.backend.integration.ott_script_client.shutil.rmtree"),
        ):
            sandbox = ScriptSandbox(token_store=FakeTokenStore({"k": "fs-secret"}))
            entries = sandbox.execute(source, "test://script", secret_names=["k"])
        assert entries[0]["content"] == "fs-secret"
        for f in sandbox_dir.iterdir():
            assert "fs-secret" not in f.read_text(encoding="utf-8")

    def test_secret_passed_via_fd_not_env(self) -> None:
        """凭据经 pass_fds 传递；不构造含凭据的 env，stdin 只带 fd 映射。"""
        source = "def fetch_entries():\n    return []\n"
        with patch(
            "src.backend.integration.ott_script_client.subprocess.Popen"
        ) as mock_popen:
            proc = MagicMock()
            proc.communicate.return_value = ("[]", "")
            proc.returncode = 0
            mock_popen.return_value = proc
            sandbox = ScriptSandbox(token_store=FakeTokenStore({"k": "env-secret"}))
            entries = sandbox.execute(source, "test://script", secret_names=["k"])
        assert entries == []
        call_kwargs = mock_popen.call_args.kwargs
        # 环境变量不参与传递：不构造 env、父进程环境无凭据
        assert call_kwargs.get("env") is None
        assert all(v != "env-secret" for v in os.environ.values())
        # 读端 fd 经 pass_fds 继承，stdin JSON 仅含 fd 映射（不含值）
        assert call_kwargs["pass_fds"]
        input_arg = (
            proc.communicate.call_args.kwargs.get("input")
            or proc.communicate.call_args.args[0]
        )
        payload = json.loads(input_arg)
        assert "env-secret" not in input_arg
        assert payload["secrets"]["k"]["fd"] == call_kwargs["pass_fds"][0]
