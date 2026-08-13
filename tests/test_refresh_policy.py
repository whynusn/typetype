"""RefreshPolicy：模式 → 到期时间、序列化、manifest 推断。"""

from __future__ import annotations

from src.backend.integration.refresh_policy import (
    MODE_INTERVAL,
    MODE_ON_DEMAND,
    MODE_STATIC,
    RefreshPolicy,
    infer_policy,
    source_type_of,
)


def test_static_never_expires() -> None:
    p = RefreshPolicy(MODE_STATIC)
    assert p.next_refresh_at(1000.0) is None


def test_interval_anchors_from_captured_at() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=3600)
    assert p.next_refresh_at(1000.0) == 4600.0


def test_on_demand_expires_immediately() -> None:
    p = RefreshPolicy(MODE_ON_DEMAND)
    assert p.next_refresh_at(1000.0) == 1000.0


def test_interval_requires_positive_seconds() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=0)
    assert p.next_refresh_at(1000.0) == 1000.0  # 立即过期（视作 on_demand）


def test_roundtrip_dict() -> None:
    p = RefreshPolicy(MODE_INTERVAL, interval_seconds=86400)
    assert RefreshPolicy.from_dict(p.to_dict()) == p


def test_infer_instance_is_static() -> None:
    assert infer_policy("ott-instance").mode == MODE_STATIC


def test_infer_rule_script_bridge_is_on_demand() -> None:
    for t in ("ott-rule", "ott-script", "ott-bridge"):
        assert infer_policy(t).mode == MODE_ON_DEMAND


def test_source_type_of_uses_private_source_key() -> None:
    assert source_type_of({"_source_type": "ott-rule"}) == "ott-rule"
    assert source_type_of({}) is None
