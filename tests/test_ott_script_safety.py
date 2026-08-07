"""OTT Repo ott-script AST 安全检查测试。"""

from __future__ import annotations

from src.backend.integration.ott_script_safety import validate_script_source


class TestScriptSafety:
    def test_allows_simple_fetch_script(self) -> None:
        source = (
            "import httpx\n"
            "import json\n"
            "def fetch_entries():\n"
            '    return [{"title": "T", "content": "Hello"}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()

    def test_allows_pycryptodome(self) -> None:
        source = (
            "from Crypto.Cipher import AES\n"
            "import base64\n"
            "def fetch_entries():\n"
            '    return [{"title": "T", "content": "encrypted"}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()

    def test_rejects_eval(self) -> None:
        source = 'def fetch_entries():\n    return eval("[1,2,3]")\n'
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_call" for i in report.issues)

    def test_rejects_exec(self) -> None:
        source = 'def fetch_entries():\n    exec("x = 1")\n    return []\n'
        report = validate_script_source(source)
        assert not report.valid

    def test_rejects_os_system(self) -> None:
        source = (
            "import os\n"
            "def fetch_entries():\n"
            "    os.system('rm -rf /')\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_call" for i in report.issues)

    def test_rejects_subprocess_import(self) -> None:
        source = (
            "import subprocess\n"
            "def fetch_entries():\n"
            "    subprocess.run(['ls'])\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_import" for i in report.issues)

    def test_rejects_importlib_dynamic_import(self) -> None:
        source = (
            "import importlib\n"
            "def fetch_entries():\n"
            "    mod = importlib.import_module('subprocess')\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_dynamic_import" for i in report.issues)

    def test_rejects_dunder_import(self) -> None:
        source = "def fetch_entries():\n    __import__('subprocess')\n    return []\n"
        report = validate_script_source(source)
        assert not report.valid

    def test_allows_json_and_re(self) -> None:
        source = (
            "import json\n"
            "import re\n"
            "def fetch_entries():\n"
            "    data = json.loads('{\"a\": 1}')\n"
            '    return [{"title": "T", "content": str(data)}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()

    def test_rejects_syntax_error(self) -> None:
        source = "def fetch_entries(\n"  # 语法错误
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "invalid_python" for i in report.issues)

    def test_allows_beautifulsoup(self) -> None:
        source = (
            "from bs4 import BeautifulSoup\n"
            "def fetch_entries():\n"
            "    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')\n"
            '    return [{"title": "T", "content": soup.get_text()}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()
