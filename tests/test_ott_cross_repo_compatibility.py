import json
import shutil
import socket as _socket
import sys
import tempfile as _tempfile
import threading
import time as _time
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from src.backend.config.runtime_config import RegistryConfig
from src.backend.integration.ott_repo_manifest import validate_repo_manifest
from src.backend.integration.ott_text_provider import OttTextProvider

OTT_ROOT = Path(__file__).resolve().parents[1].parent / "open-typing-texts"
EXPECTED = OTT_ROOT / "tests" / "fixtures" / "ott" / "expected-normalized-entries.json"
EXPECTED_SEGMENTED = (
    OTT_ROOT / "tests" / "fixtures" / "ott" / "expected-segmented-entry.json"
)
STATIC_PROFILE = OTT_ROOT / "tests" / "fixtures" / "ott" / "static-profile"


def _mock_response(json_data, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.content = json.dumps(json_data).encode("utf-8") if json_data else b""
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def _mock_text_response(text: str, status_code=200):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.content = text.encode("utf-8")
    response.text = text
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    return response


@pytest.mark.skipif(not EXPECTED.exists(), reason="OTT compatibility pack unavailable")
def test_typetype_consumes_ott_expected_entry_summaries(tmp_path):
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(
        {"entries": expected["summaries"], "total": 2, "page": 1, "pages": 1}
    )
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://ott.example.com"),
        tmp_path / "cache",
        http_client=client,
    )

    result = provider.fetch_all_entries()

    assert result[0]["entry_id"] == expected["summaries"][0]["entry_id"]
    assert (
        result[1]["current_revision_id"]
        == expected["summaries"][1]["current_revision_id"]
    )


@pytest.mark.skipif(not EXPECTED.exists(), reason="OTT compatibility pack unavailable")
def test_typetype_consumes_ott_expected_entry_detail(tmp_path):
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    detail = expected["details"][0]
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = _mock_response(detail)
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://ott.example.com"),
        tmp_path / "cache",
        http_client=client,
    )

    result = provider.fetch_text_by_entry_id(detail["entry_id"])

    assert result is not None
    assert result.entry_id == detail["entry_id"]
    assert result.revision_id == detail["current_revision_id"]
    assert result.content == detail["content"]


@pytest.mark.skipif(
    not EXPECTED_SEGMENTED.exists(),
    reason="OTT segmented compatibility fixture unavailable",
)
def test_typetype_consumes_ott_segmented_compatibility_fixture(tmp_path):
    expected = json.loads(EXPECTED_SEGMENTED.read_text(encoding="utf-8"))
    summary = expected["summary"]
    segment = expected["segment"]
    source = expected["source"]
    content = source["content_char"] * segment["char_count"]
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        _mock_response({"entries": [summary], "total": 1, "page": 1, "pages": 1}),
        _mock_response(
            {
                "entry_id": summary["entry_id"],
                "revision_id": summary["current_revision_id"],
                **segment,
                "content": content,
            }
        ),
    ]
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://ott.example.com"),
        tmp_path / "cache",
        http_client=client,
    )

    entries = provider.fetch_all_entries()
    fetched_segment = provider.fetch_ott_segment(
        summary["entry_id"],
        summary["current_revision_id"],
        segment["index"],
        summary["segment_size_hint"],
    )

    assert entries[0]["content_mode"] == "segmented"
    assert fetched_segment is not None
    assert fetched_segment["start_char"] == segment["start_char"]
    assert fetched_segment["content_hash"] == segment["content_hash"]


@pytest.mark.skipif(
    not EXPECTED_SEGMENTED.exists(),
    reason="OTT segmented compatibility fixture unavailable",
)
def test_ott_revision_change_changes_progress_identity():
    from src.backend.presentation.bridge import _compute_progress_key

    expected = json.loads(EXPECTED_SEGMENTED.read_text(encoding="utf-8"))
    entry_id = expected["summary"]["entry_id"]
    authority = "ott.example.com"
    current = _compute_progress_key(
        "ott",
        f"{authority}:{entry_id}@{expected['summary']['current_revision_id']}",
    )
    revised = _compute_progress_key(
        "ott",
        f"{authority}:{entry_id}@rev_long_fixture_v2",
    )

    assert current != revised


@pytest.mark.skipif(
    not STATIC_PROFILE.exists(),
    reason="OTT Static Profile fixture unavailable",
)
def test_typetype_reads_exported_ott_static_profile_fixture(tmp_path):
    def response_for_url(url: str):
        if url.endswith("/ott/v1/entries") or "/ott/v1/entries?" in url:
            return _mock_response(None, 404)
        if url.endswith("/ott/v1/entries/ent_static_fixture"):
            return _mock_response(None, 404)
        if url.endswith(
            "/ott/v1/entries/ent_static_fixture/revisions/rev_static_fixture/segments/1"
        ):
            return _mock_response(None, 404)
        if url.endswith("/entries.json"):
            return _mock_response(
                json.loads((STATIC_PROFILE / "entries.json").read_text("utf-8"))
            )
        if url.endswith("/entries/ent_static_fixture.json"):
            return _mock_response(
                json.loads(
                    (STATIC_PROFILE / "entries" / "ent_static_fixture.json").read_text(
                        "utf-8"
                    )
                )
            )
        if url.endswith("/segments/rev_static_fixture/1.txt"):
            return _mock_text_response(
                (
                    STATIC_PROFILE / "segments" / "rev_static_fixture" / "1.txt"
                ).read_text("utf-8")
            )
        raise AssertionError(f"unexpected URL: {url}")

    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = response_for_url
    provider = OttTextProvider(
        RegistryConfig(primary_url="https://ott.example.com"),
        tmp_path / "cache",
        http_client=client,
    )

    entries = provider.fetch_all_entries()
    detail = provider.fetch_text_by_entry_id("ent_static_fixture")
    segment = provider.fetch_ott_segment(
        "ent_static_fixture",
        "rev_static_fixture",
        1,
        source_segment_size=entries[0]["segment_size_hint"],
    )

    assert entries[0]["entry_id"] == "ent_static_fixture"
    assert detail is not None
    assert detail.content_mode == "segmented"
    assert segment is not None
    assert segment["content"] == "abcd\n"


# ── Repo Control Plane e2e ──────────────────────────────────────────────────

sys_path_original = list(sys.path)
_OTT_ADAPTER_DIR = str(OTT_ROOT)
if _OTT_ADAPTER_DIR not in sys.path:
    sys.path.insert(0, _OTT_ADAPTER_DIR)


def _start_real_adapter_server() -> tuple[int, Path]:
    """Start a real adapter server on a random port, return (port, data_dir)."""
    import importlib

    start_server = getattr(
        importlib.import_module("ott_adapter.server"), "start_server"
    )
    data_dir = Path(_tempfile.mkdtemp(prefix="ott_cross_repo_"))
    (data_dir / "content").mkdir()
    (data_dir / "scripts").mkdir()
    sock = _socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    thread = threading.Thread(
        target=start_server, args=(port, str(data_dir)), daemon=True
    )
    thread.start()
    _time.sleep(0.5)
    return port, data_dir


def _fetch_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        assert r.status == 200
        return json.loads(r.read())


def _write_adapter_content(data_dir: Path, source_key: str, entries: list[dict]):
    payload = {
        "source_key": source_key,
        "title": source_key,
        "content": entries[-1]["content"] if entries else "",
        "entries": entries,
    }
    (data_dir / "content" / f"{source_key}.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _rebuild_adapter_index(data_dir: Path):
    import importlib

    getattr(importlib.import_module("ott_adapter.scheduler"), "rebuild_index")(data_dir)


@pytest.mark.skipif(
    not OTT_ROOT.exists(),
    reason="open-typing-texts repo not found adjacent to typetype",
)
def test_adapter_manifest_passes_typetype_validator():
    """Adapter /ott-repo.json must pass validate_repo_manifest()."""
    port, data_dir = _start_real_adapter_server()
    try:
        manifest = _fetch_json(port, "/ott-repo.json")
        normalized = validate_repo_manifest(manifest)
        assert normalized is not None, f"validate_repo_manifest rejected: {manifest}"
        assert normalized["protocol"] == "ott-repo"
        assert normalized["repo_id"] == "local"
        assert normalized["mirrors"]
        assert normalized["sources"]
        src = normalized["sources"][0]
        assert src["authority"] == "local"
        assert src["endpoints"]
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.mark.skipif(
    not OTT_ROOT.exists(),
    reason="open-typing-texts repo not found adjacent to typetype",
)
def test_adapter_manifest_reflects_content_count():
    """Adapter /ott-repo.json description must reflect actual content count."""
    port, data_dir = _start_real_adapter_server()
    try:
        manifest_empty = _fetch_json(port, "/ott-repo.json")
        assert "个文本源" not in manifest_empty["description"]

        _write_adapter_content(
            data_dir,
            "cross_a",
            [{"title": "a", "content": "hello", "fetched_at": "2024-01-01"}],
        )
        _write_adapter_content(
            data_dir,
            "cross_b",
            [{"title": "b", "content": "world", "fetched_at": "2024-01-01"}],
        )
        _rebuild_adapter_index(data_dir)
        manifest_two = _fetch_json(port, "/ott-repo.json")
        assert "2 个文本源" in manifest_two["description"]
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.mark.skipif(
    not OTT_ROOT.exists(),
    reason="open-typing-texts repo not found adjacent to typetype",
)
def test_adapter_manifest_endpoints_use_correct_profiles():
    """Service + Static endpoints must be present with correct profiles."""
    port, data_dir = _start_real_adapter_server()
    try:
        manifest = _fetch_json(port, "/ott-repo.json")
        src = manifest["sources"][0]
        profiles = {ep["profile"] for ep in src["endpoints"]}
        assert "service" in profiles
        assert "static" in profiles
        for ep in src["endpoints"]:
            assert ep["url"]
            assert isinstance(ep.get("priority", 1), int)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
