"""OpenLibraryListModel / CatalogEntry / OpenLibraryViewStateStore 单测。

覆盖 2026-10-18 review P2：分组下沉到 Python、扁平行虚拟化、展开状态
持久化 + 智能默认、增量更新（切换不 reset）。
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QCoreApplication

from src.backend.integration.open_library_view_state_store import (
    OpenLibraryViewStateStore,
)
from src.backend.models.dto.catalog_entry import CatalogEntry
from src.backend.presentation.models.open_library_model import OpenLibraryListModel


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def _e(authority, entry_id, *, label=None, stype="ott-instance", repo="r1", title=""):
    return {
        "entry_id": entry_id,
        "_authority": authority,
        "_source_label": label or authority,
        "_source_type": stype,
        "_repo_url": f"https://example.com/{repo}",
        "_repo_name": repo,
        "title": title or entry_id,
    }


def _shape(m: OpenLibraryListModel) -> list[str]:
    out = []
    for r in m._rows:
        if r.kind == "header":
            out.append(f"H:{r.group.key}")
        elif r.kind == "entry":
            out.append(f"E:{r.entry.entry_id}")
        else:
            out.append(f"Y:{r.group.key}")
    return out


class _MemStore:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.saves = 0

    def load_expanded(self):
        return dict(self.data)

    def save_expanded(self, expanded):
        self.saves += 1
        self.data = dict(expanded)


# ---------------------------------------------------------------- CatalogEntry


def test_catalog_entry_field_fallbacks():
    e = CatalogEntry.from_dict(
        {
            "entry_id": "x",
            "authority": "plain",
            "source_label": "旧标签",
            "preview": "摘要",
            "charCount": 12,
            "_repo_max_entries": 5,
            "tags": ["a", 1, "b"],
        }
    )
    assert e.authority == "plain"
    assert e.source_label == "旧标签"
    assert e.preview == "摘要"
    assert e.char_count == 12
    assert e.repo.max_entries == 5
    assert e.tags == ("a", "b")
    assert e.raw["entry_id"] == "x"


def test_catalog_entry_prefers_injected_fields_and_inline_content():
    e = CatalogEntry.from_dict(
        {
            "entry_id": "x",
            "_authority": "inj",
            "authority": "plain",
            "_source_label": "注入",
            "source_label": "旧",
            "content": "全文",
            "preview": "摘要",
            "_source_type": "ott-rule",
        }
    )
    assert (e.authority, e.source_label, e.preview) == ("inj", "注入", "全文")
    assert e.on_demand is True
    assert e.matches("全文") and e.matches("注入") and not e.matches("没有")


# ---------------------------------------------------------------- 分组 / 默认展开


def test_single_source_expanded_by_default():
    m = OpenLibraryListModel()
    m.set_entries([_e("a", "1"), _e("a", "2")])
    assert _shape(m) == ["H:a", "E:1", "E:2"]


def test_multiple_sources_collapsed_by_default_and_not_cross_grouped():
    m = OpenLibraryListModel()
    # 同组条目不连续：不得串组
    m.set_entries([_e("a", "1"), _e("b", "2"), _e("a", "3")])
    assert _shape(m) == ["H:a", "H:b"]
    m.toggleGroup("a")
    assert _shape(m) == ["H:a", "E:1", "E:3", "H:b"]


def test_toggle_is_incremental_not_reset():
    m = OpenLibraryListModel()
    m.set_entries([_e("a", "1"), _e("b", "2")])
    events = []
    m.modelReset.connect(lambda: events.append("reset"))
    m.rowsInserted.connect(lambda *_: events.append("insert"))
    m.rowsRemoved.connect(lambda *_: events.append("remove"))
    m.toggleGroup("b")
    m.toggleGroup("b")
    assert events == ["insert", "remove"]


def test_unknown_group_toggle_is_noop():
    m = OpenLibraryListModel()
    m.set_entries([_e("a", "1")])
    m.toggleGroup("missing")
    assert _shape(m) == ["H:a", "E:1"]


# ---------------------------------------------------------------- 持久化


def test_explicit_toggle_is_persisted_and_restored():
    store = _MemStore()
    m = OpenLibraryListModel(store)
    m.set_entries([_e("a", "1")])
    m.toggleGroup("a")  # 默认展开 → 收起
    assert store.data == {"a": False}
    m2 = OpenLibraryListModel(store)
    m2.set_entries([_e("a", "1")])
    assert _shape(m2) == ["H:a"]


def test_search_toggle_is_not_persisted():
    store = _MemStore()
    m = OpenLibraryListModel(store)
    m.set_entries([_e("a", "1"), _e("b", "2")])
    m.setSearch("1")
    m.toggleGroup("a")
    assert store.saves == 0


def test_view_state_store_roundtrip_and_corruption(tmp_path):
    path = tmp_path / "state.json"
    store = OpenLibraryViewStateStore(path)
    assert store.load_expanded() == {}
    store.save_expanded({"a": True, "b": False})
    assert store.load_expanded() == {"a": True, "b": False}
    path.write_text("{not json", encoding="utf-8")
    assert store.load_expanded() == {}
    path.write_text(json.dumps({"expanded": {"a": "yes", "b": True}}), encoding="utf-8")
    assert store.load_expanded() == {"b": True}


# ---------------------------------------------------------------- 搜索 / 筛选


def test_search_auto_expands_hits_and_restores_after_clear():
    m = OpenLibraryListModel()
    m.set_entries(
        [_e("a", "1", title="唐诗"), _e("a", "2"), _e("b", "3", title="唐诗二")]
    )
    assert _shape(m) == ["H:a", "H:b"]
    m.setSearch("唐诗")
    assert _shape(m) == ["H:a", "E:1", "H:b", "E:3"]
    m.toggleGroup("a")  # 搜索态手动收起
    assert _shape(m) == ["H:a", "H:b", "E:3"]
    m.setSearch("")
    assert _shape(m) == ["H:a", "H:b"]


def test_source_filter_and_labels():
    m = OpenLibraryListModel()
    m.set_entries([_e("a", "1", label="甲"), _e("b", "2", label="乙")])
    assert m.sourceLabels == ["甲", "乙"]
    m.setSourceFilter("乙")
    assert _shape(m) == ["H:b", "E:2"]  # 筛选后只剩一个源 → 默认展开
    # 条目里不再有被筛选的源：筛选自动失效
    m.set_entries([_e("a", "1", label="甲")])
    assert _shape(m) == ["H:a", "E:1"]


# ---------------------------------------------------------------- 随机源历史


def test_on_demand_shows_latest_with_history_row():
    m = OpenLibraryListModel()
    m.set_entries([_e("r", str(i), stype="ott-rule") for i in range(3)])
    assert _shape(m) == ["H:r", "E:0", "Y:r"]
    hist = m.index(2)
    role = {v.data().decode(): k for k, v in m.roleNames().items()}
    assert m.data(hist, role["historyCount"]) == 2
    assert m.data(hist, role["historyExpanded"]) is False
    m.toggleHistory("r")
    assert _shape(m) == ["H:r", "E:0", "E:1", "E:2", "Y:r"]
    assert m.data(m.index(4), role["historyExpanded"]) is True


def test_single_on_demand_entry_has_no_history_row():
    m = OpenLibraryListModel()
    m.set_entries([_e("r", "0", stype="ott-script")])
    assert _shape(m) == ["H:r", "E:0"]


# ---------------------------------------------------------------- 组头降噪


def test_subtitle_only_when_multiple_repos():
    m = OpenLibraryListModel()
    role = {v.data().decode(): k for k, v in m.roleNames().items()}
    m.set_entries([_e("a", "1"), _e("b", "2")])
    assert m.data(m.index(0), role["subtitle"]) == ""
    m.set_entries([_e("a", "1"), _e("b", "2", repo="r2")])
    assert m.data(m.index(0), role["subtitle"]) == "r1"


def test_entry_role_returns_raw_dict():
    m = OpenLibraryListModel()
    role = {v.data().decode(): k for k, v in m.roleNames().items()}
    raw = _e("a", "1")
    m.set_entries([raw])
    assert m.data(m.index(1), role["entry"]) == raw
    assert m.data(m.index(0), role["entry"]) == {}
