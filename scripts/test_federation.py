#!/usr/bin/env python3
"""test_federation.py - 本地测试 OTT 联邦管线。

验证 manifest 拉取 → 联邦聚合 → entry 产出的完整流程。

用法：
    uv run python scripts/test_federation.py
    uv run python scripts/test_federation.py --manifest-url http://127.0.0.1:18888/ott-repo.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="OTT 联邦管线测试")
    parser.add_argument(
        "--manifest-url",
        default="http://127.0.0.1:18888/ott-repo.json",
        help="manifest URL",
    )
    args = parser.parse_args()

    print(f"拉取 manifest: {args.manifest_url}")
    try:
        resp = httpx.get(args.manifest_url, timeout=10.0)
        resp.raise_for_status()
        manifest = resp.json()
    except Exception as e:
        print(f"失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"protocol: {manifest.get('protocol')}")
    print(f"type: {manifest.get('type')}")
    print(f"repo_id: {manifest.get('repo_id')}")
    print(f"sources: {len(manifest.get('sources', []))}")

    for i, source in enumerate(manifest.get("sources", [])):
        stype = source.get("type")
        print(f"\n  [{i}] type={stype}")
        if stype == "ott-instance":
            print(f"      authority={source.get('authority')}")
            print(f"      endpoints={len(source.get('endpoints', []))}")
        elif stype == "ott-rule":
            print(f"      rule_id={source.get('rule_id')}")
            print(
                f"      extract={list(source.get('rule', {}).get('extract', {}).keys())}"
            )
        elif stype == "ott-script":
            print(f"      url={source.get('url')}")

    # 尝试走联邦聚合
    print("\n--- 联邦聚合测试 ---")
    try:
        from src.backend.config.runtime_config import (
            RegistryConfig,
            RuntimeConfig,
            SourceRepoEntry,
            SourceReposConfig,
        )
        from src.backend.integration.ott_federation_provider import (
            OttFederationProvider,
        )
        from src.backend.integration.ott_repo_manifest import RepoManifestCache
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = RuntimeConfig.__new__(RuntimeConfig)
            config.registry = RegistryConfig()
            config.source_repos = SourceReposConfig(
                repos=[SourceRepoEntry(url=args.manifest_url, enabled=True)]
            )

            http_client = httpx.Client(timeout=10.0, trust_env=False)
            cache_dir = tmp_path / "manifest_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            manifest_cache = RepoManifestCache(
                cache_dir=cache_dir,
                http_client=http_client,
                async_executor=None,
            )

            provider = OttFederationProvider(
                runtime_config=config,
                manifest_cache=manifest_cache,
            )

            # 用 mock 的方式测试各类 client
            from unittest.mock import patch

            # Mock instance entries
            instance_entries = [
                {
                    "entry_id": "test-static-1",
                    "title": "测试静态文本",
                    "content": "这是测试内容",
                    "char_count": 6,
                    "content_mode": "inline",
                    "current_revision_id": "v1",
                    "authority": "test-static",
                    "source_key": "test-static",
                    "source_label": "测试静态",
                }
            ]

            # Mock rule entries
            rule_entries = [
                {
                    "entry_id": "test-rule-1",
                    "title": "Hitokoto 测试",
                    "content": "山重水复疑无路，柳暗花明又一村。",
                    "char_count": 16,
                    "content_mode": "inline",
                    "current_revision_id": "v1",
                    "authority": "rule:hitokoto",
                    "source_key": "rule:hitokoto",
                    "source_label": "一言",
                }
            ]

            # Mock script entries
            script_entries = [
                {
                    "entry_id": "test-script-1",
                    "title": "脚本测试",
                    "content": "脚本生成的文本内容",
                    "char_count": 10,
                    "content_mode": "inline",
                    "current_revision_id": "v1",
                    "authority": "script",
                    "source_key": "script",
                    "source_label": "脚本源",
                }
            ]

            from src.backend.integration.ott_federation_provider import (
                _InstanceClient,
                _RuleClient,
                _ScriptClient,
            )

            with patch.object(
                _InstanceClient, "list_entries", return_value=instance_entries
            ):
                with patch.object(
                    _RuleClient, "list_entries", return_value=rule_entries
                ):
                    with patch.object(
                        _ScriptClient, "list_entries", return_value=script_entries
                    ):
                        all_entries = provider.list_all_entries()

            print(f"聚合条目数: {len(all_entries)}")
            for e in all_entries:
                print(
                    f"  [{e.get('authority')}] {e.get('title')!r} ({e.get('char_count', 0)} 字)"
                )

            http_client.close()
            print("\n✓ 联邦聚合测试通过")

    except Exception as e:
        print(f"联邦测试失败: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
