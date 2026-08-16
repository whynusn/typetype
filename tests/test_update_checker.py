"""update_checker 模块测试（纯 mock，无真实网络）。

网络经注入的 fetch_json / fetch_bytes 函数或 MagicMock 客户端模拟，
不发起任何真实请求。验签测试生成独立 Ed25519 keypair，与内置
UPDATE_PUBKEY 占位符解耦。
"""

import hashlib
import json
from unittest.mock import MagicMock

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.backend.integration.update_checker import (
    GITHUB_API_URL,
    VERSION_MANIFEST_PATHS,
    UpdateChecker,
    _direct_download_url,
    _version_gt,
)
from src.backend.version import APP_VERSION

ASSET_NAME = "typetype-linux-amd64.tar.gz"
DIRECT_URL = (
    "https://github.com/whynusn/typetype/releases/download/v0.5.0/"
    "typetype-linux-amd64.tar.gz"
)


def _make_keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    pubkey = private_key.public_key().public_bytes_raw().hex()
    return private_key, pubkey


def _make_manifest(
    version: str,
    assets: list[dict],
    private_key: Ed25519PrivateKey,
) -> dict:
    """用私钥对剔除 signature 键的 canonical JSON 签名，返回完整 manifest。"""
    manifest = {"version": version, "assets": assets}
    canonical = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    manifest["signature"] = private_key.sign(canonical).hex()
    return manifest


# ---- 版本比较 ----


def test_version_gt():
    assert _version_gt("1.0.0", "0.9.9")
    assert not _version_gt("0.4.5", "0.4.5")
    assert _version_gt("0.5.0", "0.4.5")
    assert not _version_gt("0.4.5", "0.5.0")
    # 容忍 v 前缀
    assert _version_gt("v0.5.0", "0.4.5")
    # prerelease 边界：release > prerelease
    assert _version_gt("1.0.0", "1.0.0-rc.1")
    assert not _version_gt("1.0.0-rc.1", "1.0.0")
    # prerelease 内部比较
    assert _version_gt("1.0.0-rc.2", "1.0.0-rc.1")
    assert not _version_gt("1.0.0-alpha", "1.0.0-alpha.1")
    assert _version_gt("1.0.0-rc.1", "1.0.0-beta.2")
    assert not _version_gt("1.0.0-beta", "1.0.0-rc.1")


# ---- GitHub API 主路径 ----


def test_api_newer_version_returns_update():
    release = {
        "tag_name": "v0.5.0",
        "body": "修复若干问题\n新增功能",
        "assets": [
            {
                "name": ASSET_NAME,
                "browser_download_url": DIRECT_URL,
                "size": 1234,
            }
        ],
    }

    def fetch_json(url):
        return release if url == GITHUB_API_URL else None

    checker = UpdateChecker(fetch_json=fetch_json)
    info = checker.check_for_update()
    assert info is not None
    assert info.version == "0.5.0"
    assert info.source == "github_api"
    assert info.release_notes == "修复若干问题\n新增功能"
    assert info.assets[0]["name"] == ASSET_NAME
    assert info.assets[0]["url"] == DIRECT_URL
    assert info.assets[0]["sha256"] == ""


def test_api_same_version_returns_none():
    release = {"tag_name": f"v{APP_VERSION}", "assets": []}

    def fetch_json(url):
        return release if url == GITHUB_API_URL else None

    checker = UpdateChecker(fetch_json=fetch_json)
    assert checker.check_for_update() is None


# ---- version.json 降级链 ----


def test_api_failure_falls_back_to_manifest():
    private_key, pubkey = _make_keypair()
    manifest = _make_manifest(
        "0.6.0",
        [{"name": ASSET_NAME, "url": DIRECT_URL, "sha256": "aa" * 32}],
        private_key,
    )
    calls = []

    def fetch_json(url):
        calls.append(url)
        if url == GITHUB_API_URL:
            raise httpx.ConnectError("network down")
        if url == VERSION_MANIFEST_PATHS[0]:
            return manifest
        return None

    checker = UpdateChecker(fetch_json=fetch_json, update_pubkey=pubkey)
    info = checker.check_for_update()
    assert info is not None
    assert info.source == "manifest"
    assert info.version == "0.6.0"
    assert calls[0] == GITHUB_API_URL
    assert calls[1] == VERSION_MANIFEST_PATHS[0]


def test_manifest_valid_signature_accepted():
    private_key, pubkey = _make_keypair()
    manifest = _make_manifest(
        "0.9.0",
        [{"name": ASSET_NAME, "url": DIRECT_URL, "sha256": "bb" * 32}],
        private_key,
    )
    checker = UpdateChecker(
        fetch_json=lambda url: None if url == GITHUB_API_URL else manifest,
        update_pubkey=pubkey,
    )
    info = checker.check_for_update()
    assert info is not None
    assert info.source == "manifest"
    assert info.version == "0.9.0"
    assert info.assets[0]["sha256"] == "bb" * 32
    assert info.release_notes == ""


def test_manifest_signature_with_ed25519_prefix_accepted():
    private_key, pubkey = _make_keypair()
    manifest = _make_manifest("0.9.1", [], private_key)
    manifest["signature"] = "ed25519:" + manifest["signature"]
    checker = UpdateChecker(
        fetch_json=lambda url: None if url == GITHUB_API_URL else manifest,
        update_pubkey=pubkey,
    )
    info = checker.check_for_update()
    assert info is not None
    assert info.source == "manifest"


def test_manifest_bad_signature_rejected():
    private_key, _ = _make_keypair()
    _, wrong_pubkey = _make_keypair()
    manifest = _make_manifest("0.6.0", [], private_key)
    checker = UpdateChecker(
        fetch_json=lambda url: None if url == GITHUB_API_URL else manifest,
        update_pubkey=wrong_pubkey,
    )
    assert checker.check_for_update() is None


def test_manifest_without_signature_rejected():
    manifest = {"version": "0.6.0", "assets": []}
    checker = UpdateChecker(
        fetch_json=lambda url: None if url == GITHUB_API_URL else manifest,
        update_pubkey="",
    )
    assert checker.check_for_update() is None


# ---- 下载 ----


def test_download_ok(tmp_path):
    content = b"hello update archive"
    expected = hashlib.sha256(content).hexdigest()
    checker = UpdateChecker(fetch_bytes=lambda url: content)
    dest = tmp_path / "update.tar.gz"
    assert checker.download("https://x/update.tar.gz", expected, dest) is True
    assert dest.read_bytes() == content
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_sha256_mismatch_deletes_file(tmp_path):
    content = b"corrupted data"
    wrong = hashlib.sha256(b"something else").hexdigest()
    checker = UpdateChecker(fetch_bytes=lambda url: content)
    dest = tmp_path / "update.tar.gz"
    assert checker.download("https://x/update.tar.gz", wrong, dest) is False
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_missing_sha256_rejected(tmp_path):
    checker = UpdateChecker()
    dest = tmp_path / "update.tar.gz"
    assert checker.download("https://x/update.tar.gz", "", dest) is False
    assert not dest.exists()


def test_download_ok_streaming_client(tmp_path):
    content = b"streamed payload"
    expected = hashlib.sha256(content).hexdigest()
    mock_response = MagicMock()
    mock_response.iter_bytes.return_value = iter([content])
    mock_client = MagicMock()
    mock_client.stream.return_value.__enter__.return_value = mock_response

    checker = UpdateChecker(client=mock_client)
    dest = tmp_path / "u.tar.gz"
    assert checker.download("https://x/u.tar.gz", expected, dest) is True
    assert dest.read_bytes() == content
    mock_client.stream.assert_called_once_with("GET", "https://x/u.tar.gz")


def test_download_streaming_http_error_cleans_up(tmp_path):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock(status_code=403)
    )
    mock_client = MagicMock()
    mock_client.stream.return_value.__enter__.return_value = mock_response

    checker = UpdateChecker(client=mock_client)
    dest = tmp_path / "u.tar.gz"
    assert checker.download("https://x/u.tar.gz", "aa" * 32, dest) is False
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


# ---- 下载候选 ----


def test_build_download_candidates():
    checker = UpdateChecker()
    mirrors = ["https://ghproxy.com/", "https://mirror.ghproxy.com"]
    candidates = checker.build_download_candidates("v0.5.0", ASSET_NAME, mirrors)
    assert candidates[0] == DIRECT_URL
    assert candidates[1] == "https://ghproxy.com/" + DIRECT_URL
    assert candidates[2] == "https://mirror.ghproxy.com/" + DIRECT_URL
    # 去重
    dup = checker.build_download_candidates(
        "v0.5.0", ASSET_NAME, ["https://ghproxy.com/", "https://ghproxy.com/"]
    )
    assert dup == [DIRECT_URL, "https://ghproxy.com/" + DIRECT_URL]


def test_build_download_candidates_uses_default_mirrors():
    checker = UpdateChecker()
    candidates = checker.build_download_candidates("v0.5.0", ASSET_NAME, None)
    assert candidates[0] == DIRECT_URL
    assert len(candidates) > 1


def test_direct_download_url_adds_v_prefix():
    assert _direct_download_url("0.5.0", ASSET_NAME) == DIRECT_URL
