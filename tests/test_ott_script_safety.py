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

    def test_rejects_urllib_request_import(self) -> None:
        """urllib.request 可 urlopen file:// 读本地文件，必须拒绝。"""
        source = (
            "import urllib.request\n"
            "def fetch_entries():\n"
            "    data = urllib.request.urlopen('file:///etc/passwd').read()\n"
            '    return [{"title": "T", "content": data.decode()}]\n'
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_import" for i in report.issues)

    def test_allows_urllib_parse(self) -> None:
        """urllib.parse 纯 URL 编解码，无 I/O，允许。"""
        source = (
            "from urllib.parse import unquote\n"
            "def fetch_entries():\n"
            "    text = unquote('a%20b')\n"
            '    return [{"title": "T", "content": text}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()

    def test_rejects_object_model_subclasses_escape(self) -> None:
        """对象模型遍历逃逸：attribute 访问而非函数调用，必须被 AST 层拦截。"""
        source = (
            "def fetch_entries():\n"
            "    for c in ().__class__.__bases__[0].__subclasses__():\n"
            "        pass\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_object_model_access" for i in report.issues)

    def test_rejects_globals_attribute(self) -> None:
        """__globals__ 是逃逸链的泄密点，属性访问必须拒绝。"""
        source = (
            "def f():\n"
            "    return 1\n"
            "def fetch_entries():\n"
            "    g = f.__globals__\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert not report.valid
        assert any(i.code == "banned_object_model_access" for i in report.issues)

    def test_allows_realistic_whitelisted_script(self) -> None:
        """白名单库真实用法（httpx + bs4 + Crypto + json + re + datetime）无误报。"""
        source = (
            "import httpx\n"
            "import json\n"
            "import re\n"
            "import datetime\n"
            "import base64\n"
            "from bs4 import BeautifulSoup\n"
            "from Crypto.Cipher import AES\n"
            "from Crypto.Util.Padding import pad\n"
            "def fetch_entries():\n"
            "    resp = httpx.get('https://example.com/data')\n"
            "    soup = BeautifulSoup(resp.text, 'html.parser')\n"
            "    title = soup.find('title').get_text()\n"
            "    cleaned = re.sub(r'\\s+', ' ', title)\n"
            "    key = base64.b64decode('a2V5MTIzNDU2Nzg5MDEyMzQ1Ng==')\n"
            "    cipher = AES.new(key, AES.MODE_CBC)\n"
            "    payload = pad(b'hello', 16)\n"
            "    out = json.dumps(\n"
            "        {'title': cleaned,\n"
            "         'ts': datetime.datetime.now().isoformat()}\n"
            "    )\n"
            '    return [{"title": cleaned, "content": out}]\n'
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()

    def test_allows_super_init_in_class(self) -> None:
        """super().__init__() 是合法类模式：__init__ 属性访问不拦截。"""
        source = (
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "class Sub(Base):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
            "        self.y = 2\n"
            "def fetch_entries():\n"
            "    return []\n"
        )
        report = validate_script_source(source)
        assert report.valid, report.to_dict()
