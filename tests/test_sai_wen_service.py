"""
sai_wen_service 模块测试
"""

from src.backend.core.api_client import ApiClient
from src.backend.services.sai_wen_service import SaiWenService


class DummyApiClient(ApiClient):
    """模拟 ApiClient 返回值。"""

    def __init__(self, response_data):
        self.response_data = response_data
        self.last_url = None
        self.last_payload = None

    def post_json(self, url, payload):
        self.last_url = url
        self.last_payload = payload
        return self.response_data


class TestSaiWenService:
    """测试 SaiWenService 解析逻辑"""

    def test_msg_is_string(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        api_client = DummyApiClient({"msg": "hello"})
        service = SaiWenService(api_client=api_client)

        assert service.fetch_text("https://example.com") == "hello"
        assert api_client.last_url == "https://example.com"
        assert api_client.last_payload == {0: "ENCODED"}

    def test_msg_is_dict_with_content(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenService(api_client=DummyApiClient({"msg": {"content": "abc"}}))
        assert service.fetch_text("https://example.com") == "abc"

    def test_msg_is_dict_with_zero_key(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenService(api_client=DummyApiClient({"msg": {"0": "zero-content"}}))
        assert service.fetch_text("https://example.com") == "zero-content"

    def test_msg_is_other_type(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenService(api_client=DummyApiClient({"msg": 123}))
        assert service.fetch_text("https://example.com") == "123"

    def test_msg_is_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenService(api_client=DummyApiClient({"msg": None}))
        assert service.fetch_text("https://example.com") == ""

    def test_request_exception_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.time.time", lambda: 1234567890
        )
        monkeypatch.setattr(
            "src.backend.services.sai_wen_service.crypt.encrypt",
            lambda _: "XENCODED",
        )

        service = SaiWenService(api_client=DummyApiClient(None))
        assert service.fetch_text("https://example.com") is None
