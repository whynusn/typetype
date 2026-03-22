"""
SaiWenTextFetcher 模块测试
"""

from src.backend.infrastructure.api_client import ApiClient
from src.backend.integration.sai_wen_text_fetcher import SaiWenTextFetcher


class DummyApiClient(ApiClient):
    """模拟 ApiClient 返回值。"""

    def __init__(self, response_data):
        self.response_data = response_data
        self.last_url = None
        self.last_payload = None
        self._last_error = None

    def request(self, method, url, *, params=None, json=None, data=None, headers=None):
        self.last_url = url
        self.last_payload = json
        return self.response_data


class TestSaiWenTextFetcher:
    """测试 SaiWenTextFetcher 解析逻辑"""

    def test_msg_is_string(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        api_client = DummyApiClient({"msg": "hello"})
        service = SaiWenTextFetcher(api_client=api_client)

        assert service.fetch_text("https://example.com") == "hello"
        assert api_client.last_url == "https://example.com"
        assert api_client.last_payload == {0: "ENCODED"}

    def test_msg_is_dict_with_content(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenTextFetcher(
            api_client=DummyApiClient({"msg": {"content": "abc"}})
        )
        assert service.fetch_text("https://example.com") == "abc"

    def test_msg_is_dict_with_zero_key(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenTextFetcher(
            api_client=DummyApiClient({"msg": {"0": "zero-content"}})
        )
        assert service.fetch_text("https://example.com") == "zero-content"

    def test_msg_is_other_type(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenTextFetcher(api_client=DummyApiClient({"msg": 123}))
        assert service.fetch_text("https://example.com") == "123"

    def test_msg_is_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenTextFetcher(api_client=DummyApiClient({"msg": None}))
        assert service.fetch_text("https://example.com") == ""

    def test_request_exception_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenTextFetcher(api_client=DummyApiClient(None))
        assert service.fetch_text("https://example.com") is None

    def test_request_error_raises_last_error(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.integration.sai_wen_text_fetcher.crypt.encrypt",
            lambda _: "XENCODED",
        )

        api_client = DummyApiClient(None)
        api_client._last_error = RuntimeError("network timeout")
        service = SaiWenTextFetcher(api_client=api_client)

        try:
            service.fetch_text("https://example.com")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert str(e) == "network timeout"
