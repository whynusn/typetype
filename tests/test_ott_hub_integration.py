"""OTT Source Hub manifest 跨仓集成测试。

验证 hub 仓库（ott-source-hub）的 manifest 可被 typetype 完整解析：
1. 通过 ott-repo.schema.json 权威校验（vendored 于 tests/fixtures/hub/）
2. 联邦层按四种源类型（instance/rule/bridge/script）构建客户端
3. L1/L1.5/L2 源条目可聚合；L3 在 trust=verified 时执行

hub manifest 由 CI 的 manifest-validate.yml 保证与协议仓 schema 同步；
本测试防止客户端侧解析漂移。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import jsonschema
import pytest

from src.backend.config.runtime_config import (
    OttConfig,
    RuntimeConfig,
    SourceRepoEntry,
    SourceReposConfig,
)
from src.backend.integration.ott_federation_provider import (
    _BridgeClient,
    OttFederationProvider,
)
from src.backend.integration.ott_normalization import (
    _bridge_authority,
    _script_authority,
)
from src.backend.integration.ott_repo_manifest import (
    RepoManifestCache,
    validate_repo_manifest,
)

HUB_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hub" / "ott-repo.json"

pytestmark = pytest.mark.skipif(
    not HUB_FIXTURE.exists(),
    reason="hub manifest fixture 缺失（tests/fixtures/hub/ott-repo.json）",
)


def _load_hub_manifest() -> dict:
    return json.loads(HUB_FIXTURE.read_text(encoding="utf-8"))


def _mock_http(json_data):
    client = MagicMock(spec=httpx.Client)
    text = json.dumps(json_data)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = text
    response.headers = {"content-length": str(len(text))}
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data
    client.get.return_value = response
    client.post.return_value = response
    return client


def _federation_with_hub(tmp_path, trust_state="verified", script_data=None):
    """创建一个订阅 hub 的 OttFederationProvider（manifest 预写缓存跳过网络）。"""
    config = MagicMock(spec=RuntimeConfig)
    config.ott = OttConfig(cache_ttl_seconds=3600, max_content_bytes=1_048_576)
    repo_entry = SourceRepoEntry(
        url="https://raw.githubusercontent.com/whynusn/ott-source-hub/main/ott-repo.json",
        enabled=True,
        trust_state=trust_state,
    )
    config.source_repos = SourceReposConfig(repos=[repo_entry])

    cache_dir = tmp_path / "repo_manifest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_cache = RepoManifestCache(
        cache_dir=cache_dir,
        http_client=_mock_http(_load_hub_manifest()),
        async_executor=None,
    )
    provider = OttFederationProvider(
        runtime_config=config,
        manifest_cache=manifest_cache,
    )
    # 共享 http client：rule/bridge 用它；script 沙箱可注入 mock
    provider._shared_client = _mock_http(
        {
            "title": "桥接标题",
            "content": "来自桥的动态文本",
        }
    )
    return provider


def test_hub_manifest_passes_repo_schema() -> None:
    """hub manifest 必须通过 typetype 的 validate_repo_manifest（含签名/结构校验）。"""
    manifest = _load_hub_manifest()
    result = validate_repo_manifest(manifest)
    assert result is not None, "hub manifest 未通过 validate_repo_manifest"
    assert result["version"] == "1.1"
    types = {s["type"] for s in result["sources"]}
    assert types == {"ott-rule", "ott-bridge", "ott-script"}


def test_hub_manifest_valid_against_vendored_schema() -> None:
    """hub manifest 通过协议仓权威 schema（与 hub CI 同源校验）。"""
    # 兄弟仓 open-typing-texts 与 typetype 同处 work/ 下
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "open-typing-texts"
        / "schemas"
        / "ott-repo.schema.json"
    )
    if not schema_path.exists():
        pytest.skip("open-typing-texts 兄弟仓未克隆，跳过 schema 校验")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(_load_hub_manifest(), schema)


def test_hub_all_four_sources_build_clients(tmp_path) -> None:
    """hub 的 rule（hitokoto/jisubei）+ bridge（jinrishici）+ script（zenquotes）全部构建客户端。"""
    provider = _federation_with_hub(tmp_path)
    clients = provider._build_clients()
    authorities = set(clients.keys())

    # L1/L1.5 rule 源
    assert "rule:io.github.whynusn.ott-source-hub:hitokoto" in authorities
    assert "rule:io.github.whynusn.ott-source-hub:jisubei" in authorities
    # L2 bridge 源
    bridge_auth = _bridge_authority("https://v1.jinrishici.com/all.json")
    assert bridge_auth in authorities
    assert isinstance(clients[bridge_auth], _BridgeClient)
    # L3 script 源（trust=verified 才构建）
    script_auth = _script_authority(
        "https://raw.githubusercontent.com/whynusn/ott-source-hub/main/adapters/zenquotes/code/script.py"
    )
    assert script_auth in authorities


def test_hub_bridge_source_aggregates_entries(tmp_path) -> None:
    """L2 桥接源条目进入联邦聚合列表，content_mode=inline。"""
    provider = _federation_with_hub(tmp_path)
    entries = provider.list_all_entries()
    bridge_entries = [
        e
        for e in entries
        if e["_authority"] == _bridge_authority("https://v1.jinrishici.com/all.json")
    ]
    assert len(bridge_entries) >= 1
    assert bridge_entries[0]["content"] == "来自桥的动态文本"
    assert bridge_entries[0]["content_mode"] == "inline"


def test_hub_script_source_requires_verified_trust(tmp_path) -> None:
    """L3 脚本源：trust_state=verified 时构建；否则跳过（签名准入门槛）。"""
    provider_verified = _federation_with_hub(tmp_path, trust_state="verified")
    verified_clients = provider_verified._build_clients()
    script_auth = _script_authority(
        "https://raw.githubusercontent.com/whynusn/ott-source-hub/main/adapters/zenquotes/code/script.py"
    )
    assert script_auth in verified_clients

    provider_pending = _federation_with_hub(tmp_path, trust_state="pending")
    pending_clients = provider_pending._build_clients()
    assert script_auth not in pending_clients
