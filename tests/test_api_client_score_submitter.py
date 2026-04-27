"""ApiClientScoreSubmitter 测试。

验证提交 payload 只包含原始字段，符合服务端 V2 纯原始字段契约。
设计原则：客户端只传原始字段，所有派生指标由服务端统一计算。
"""

from src.backend.integration.api_client_score_submitter import ApiClientScoreSubmitter
from src.backend.models.entity.session_stat import SessionStat


class MockApiClient:
    """模拟 ApiClient。"""

    def __init__(self):
        self.request_url = None
        self.request_method = None
        self.request_kwargs = None
        self.last_error = None

    def request(self, method, url, **kwargs):
        self.request_url = url
        self.request_method = method
        self.request_kwargs = kwargs
        return {"code": 200, "message": "success", "data": None}


def test_build_payload_v2_pure_raw_contract():
    """验证提交 payload 只包含原始字段，符合 V2 纯原始字段契约。"""

    # 准备测试数据
    mock_client = MockApiClient()
    submitter = ApiClientScoreSubmitter(
        api_client=mock_client,
        submit_url="http://localhost:8080/api/v1/scores",
        token_provider=lambda: "test-token",
    )

    # 创建 SessionStat（客户端内部事实来源）
    stat = SessionStat(
        text_id=123,
        time=120.5,
        key_stroke_count=1500,
        char_count=300,
        wrong_char_count=5,
        backspace_count=10,
        correction_count=3,
    )

    # 构建 payload
    submitter.submit(stat, text_id=123)

    # 验证请求参数
    assert mock_client.request_method == "POST"
    assert mock_client.request_url == "http://localhost:8080/api/v1/scores"

    payload = mock_client.request_kwargs["json"]

    # 只应该传 6 个原始字段 + textId
    assert len(payload) == 7, f"payload 应该只有 7 个字段，但有: {list(payload.keys())}"

    # 原始字段检查
    assert "textId" in payload
    assert "charCount" in payload
    assert "wrongCharCount" in payload
    assert "backspaceCount" in payload
    assert "correctionCount" in payload
    assert "keyStrokeCount" in payload
    assert "time" in payload

    # 所有派生字段都不应该在 payload 中
    assert "speed" not in payload, "speed 是派生字段，不应传给服务端"
    assert "keyStroke" not in payload, "keyStroke 是派生字段，不应传给服务端"
    assert "codeLength" not in payload, "codeLength 是派生字段，不应传给服务端"
    assert "accuracyRate" not in payload, "accuracyRate 是派生字段，不应传给服务端"
    assert "keyAccuracy" not in payload, "keyAccuracy 是派生字段，不应传给服务端"
    assert "effectiveSpeed" not in payload, "effectiveSpeed 是派生字段，不应传给服务端"
    assert "duration" not in payload, "duration 是兼容字段，不应传给服务端"

    # 原始字段值验证
    assert payload["textId"] == 123
    assert payload["time"] == 120.5
    assert payload["charCount"] == 300
    assert payload["wrongCharCount"] == 5
    assert payload["backspaceCount"] == 10
    assert payload["correctionCount"] == 3
    assert payload["keyStrokeCount"] == 1500


def test_build_payload_raw_fields_only():
    """验证 payload 中只包含原始字段，确保客户端和服务端计算逻辑一致。"""

    # 准备测试数据
    mock_client = MockApiClient()
    submitter = ApiClientScoreSubmitter(
        api_client=mock_client,
        submit_url="http://localhost:8080/api/v1/scores",
        token_provider=lambda: "test-token",
    )

    # 创建 SessionStat（包含各种边缘情况）
    stat = SessionStat(
        text_id=123,
        time=60.0,  # 1 分钟
        key_stroke_count=600,
        char_count=300,
        wrong_char_count=0,
        backspace_count=0,
        correction_count=0,
    )

    # 构建 payload
    submitter.submit(stat, text_id=123)

    payload = mock_client.request_kwargs["json"]

    # 只验证原始字段，不验证派生字段（派生字段由服务端计算）
    assert payload["keyStrokeCount"] == 600
    assert payload["charCount"] == 300
    assert payload["wrongCharCount"] == 0
    assert payload["backspaceCount"] == 0
    assert payload["correctionCount"] == 0
    assert abs(payload["time"] - 60.0) < 0.01
