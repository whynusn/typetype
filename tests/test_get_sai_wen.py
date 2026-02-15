"""
get_sai_wen 模块测试
"""

from src.backend import get_sai_wen


class FakeResponse:
    """模拟 httpx 响应对象"""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeClient:
    """模拟 httpx.Client 上下文"""

    def __init__(self, response_data):
        self.response_data = response_data
        self.last_post_args = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.last_post_args = (url, json)
        return FakeResponse(self.response_data)


def _patch_common(monkeypatch, response_data):
    """统一 patch 加密和时间及 HTTP 客户端"""

    monkeypatch.setattr(get_sai_wen.time, "time", lambda: 1234567890)
    monkeypatch.setattr(get_sai_wen.crypt, "encrypt", lambda _: "XENCODED")
    monkeypatch.setattr(get_sai_wen.httpx, "Client", lambda timeout: FakeClient(response_data))


class TestGetSaiWen:
    """测试 get_sai_wen 解析逻辑"""

    def test_msg_is_string(self, monkeypatch):
        _patch_common(monkeypatch, {"msg": "hello"})
        assert get_sai_wen.get_sai_wen("https://example.com") == "hello"

    def test_msg_is_dict_with_content(self, monkeypatch):
        _patch_common(monkeypatch, {"msg": {"content": "abc"}})
        assert get_sai_wen.get_sai_wen("https://example.com") == "abc"

    def test_msg_is_dict_with_zero_key(self, monkeypatch):
        _patch_common(monkeypatch, {"msg": {"0": "zero-content"}})
        assert get_sai_wen.get_sai_wen("https://example.com") == "zero-content"

    def test_msg_is_other_type(self, monkeypatch):
        _patch_common(monkeypatch, {"msg": 123})
        assert get_sai_wen.get_sai_wen("https://example.com") == "123"

    def test_msg_is_none(self, monkeypatch):
        _patch_common(monkeypatch, {"msg": None})
        assert get_sai_wen.get_sai_wen("https://example.com") == ""

    def test_request_exception_returns_none(self, monkeypatch):
        monkeypatch.setattr(get_sai_wen.time, "time", lambda: 1234567890)
        monkeypatch.setattr(get_sai_wen.crypt, "encrypt", lambda _: "XENCODED")

        class ErrorClient:
            def __init__(self, timeout):
                self.timeout = timeout

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, json):
                raise RuntimeError("network error")

        monkeypatch.setattr(get_sai_wen.httpx, "Client", ErrorClient)

        assert get_sai_wen.get_sai_wen("https://example.com") is None
