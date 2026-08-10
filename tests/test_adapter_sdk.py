"""OTT 适配器包 SDK（scripts/adapter.py）测试。

覆盖：new 脚手架 schema 有效、未签名校验失败、new+sign+validate CLI 往返、
载荷篡改 checksum 失败、adapter.json 字段篡改签名失败。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "open-typing-texts"
    / "schemas"
    / "ott-adapter-v1.schema.json"
)
ADAPTER_SCRIPT = ROOT / "scripts" / "adapter.py"

pytestmark = pytest.mark.skipif(
    not SCHEMA_PATH.exists(),
    reason="open-typing-texts 仓未克隆到兄弟目录，跳过适配器 schema 测试",
)


def _load_sdk() -> Any:
    """scripts/ 非包目录，按文件路径加载 adapter 模块。"""
    spec = importlib.util.spec_from_file_location("adapter_sdk", ADAPTER_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sdk = _load_sdk()


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _gen_keypair() -> tuple[str, str]:
    """生成 ed25519 密钥对，返回裸 hex (pubkey, secret_key)。"""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    secret = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    return pub, secret


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ADAPTER_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _step_map(steps: list[tuple[str, bool, str]]) -> dict[str, bool]:
    return {name: ok for name, ok, _ in steps}


def test_new_scaffolds_schema_valid_package(tmp_path: Path) -> None:
    pkg = sdk.scaffold(tmp_path, "hello", "script", repo_id="demo.repo")
    adapter = json.loads((pkg / "adapter.json").read_text(encoding="utf-8"))
    jsonschema.validate(adapter, _schema())  # 不抛错即 schema 有效
    assert (pkg / "code" / "script.py").exists()
    assert (pkg / "fixtures" / "responses").is_dir()
    assert (pkg / "README.md").exists()
    # 未签名占位：pubkey 为全零
    assert adapter["signature"]["pubkey"].endswith("0" * 64)


def test_validate_unsigned_scaffold_fails_signature(tmp_path: Path) -> None:
    pkg = sdk.scaffold(tmp_path, "demo", "script", repo_id="demo.repo")
    steps = sdk.validate_package(pkg)
    by_name = _step_map(steps)
    assert by_name["schema"] is True
    assert by_name["checksum"] is True
    assert by_name["signature"] is False  # 未签名 → 签名步骤明确失败
    msg = next(m for n, ok, m in steps if n == "signature")
    assert "未签名" in msg


def test_roundtrip_new_sign_validate_via_cli(tmp_path: Path) -> None:
    name = "roundtrip"
    pub, secret = _gen_keypair()

    r1 = _run_cli(
        "new",
        name,
        "--type",
        "rule",
        "--repo-id",
        "demo.repo",
        "--api-level",
        "2",
        cwd=tmp_path,
    )
    assert r1.returncode == 0, r1.stderr

    r2 = _run_cli("sign", name, "--pubkey", pub, "--secret-key", secret, cwd=tmp_path)
    assert r2.returncode == 0, r2.stderr

    r3 = _run_cli("validate", name, cwd=tmp_path)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "校验全部通过" in r3.stdout


def test_tampered_content_fails_checksum(tmp_path: Path) -> None:
    pkg = sdk.scaffold(tmp_path, "demo", "script", repo_id="demo.repo")
    content_path = pkg / "code" / "script.py"
    content_path.write_text(
        content_path.read_text(encoding="utf-8") + "\n# 篡改\n", encoding="utf-8"
    )
    steps = sdk.validate_package(pkg)
    by_name = _step_map(steps)
    assert by_name["checksum"] is False
    assert by_name["signature"] is False  # 载荷变化同时破坏签名


def test_tampered_adapter_field_fails_signature(tmp_path: Path) -> None:
    pkg = sdk.scaffold(tmp_path, "demo", "script", repo_id="demo.repo")
    pub, secret = _gen_keypair()
    sdk.sign_package(pkg, pub, secret)

    adapter_path = pkg / "adapter.json"
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    adapter["name"] = "hacked"
    adapter_path.write_text(json.dumps(adapter, ensure_ascii=False), encoding="utf-8")

    steps = sdk.validate_package(pkg)
    by_name = _step_map(steps)
    assert by_name["signature"] is False
    assert by_name["checksum"] is True  # 只改 name，content 载荷未动
