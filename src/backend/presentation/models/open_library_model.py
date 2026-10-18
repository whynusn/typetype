"""开源文库分组列表模型（ADR-016 B2 / open-library review P2）。

把原先 RepoEntriesPanel.qml 里的 JS 分组（rebuild / fillInnerModel /
_expanded 字典 + _innerVersion 版本号）收到 Python：

- **扁平行**：header / entry / history 三种行同在一个 QAbstractListModel，
  QML 用单个 ListView 渲染——只实例化可视区内的行（虚拟化）。原结构是
  「Column + Repeater 全量实例化每组每条」，条目多时首屏成本线性增长。
- **增量更新**：展开/收起、历史切换只对该组的行做 beginRemoveRows /
  beginInsertRows，其余行与 delegate 不动；条目集合 / 筛选 / 搜索变化才整表
  reset。
- **展开状态**：用户显式切换的组持久化（OpenLibraryViewStateStore）；
  没切换过的组走智能默认——只有一个源时展开，多个源时收起。搜索时命中组
  一律展开（用户仍可在搜索态逐组收起，搜索词变化即恢复）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from ...models.dto.catalog_entry import CatalogEntry

KIND_HEADER = "header"
KIND_ENTRY = "entry"
KIND_HISTORY = "history"


class ExpandedStateStore(Protocol):
    def load_expanded(self) -> dict[str, bool]: ...

    def save_expanded(self, expanded: dict[str, bool]) -> None: ...


@dataclass
class _Group:
    key: str
    name: str
    subtitle: str
    repo_id: str
    url: str
    source_type: str
    trust_state: str
    on_demand: bool
    max_entries: int
    entries: list[CatalogEntry] = field(default_factory=list)


@dataclass(frozen=True)
class _Row:
    kind: str
    group: _Group
    entry: CatalogEntry | None = None


_ROLE_NAMES = (
    "kind",
    "groupKey",
    "name",
    "subtitle",
    "repoId",
    "repoUrl",
    "sourceType",
    "trustState",
    "onDemand",
    "count",
    "maxEntries",
    "expanded",
    "entry",
    "entryId",
    "historyCount",
    "historyExpanded",
)
_ROLES = {Qt.ItemDataRole.UserRole + 1 + i: n for i, n in enumerate(_ROLE_NAMES)}
_ROLE_OF = {n: r for r, n in _ROLES.items()}


class OpenLibraryListModel(QAbstractListModel):
    sourceLabelsChanged = Signal()
    countsChanged = Signal()
    searchActiveChanged = Signal()

    def __init__(
        self,
        state_store: ExpandedStateStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = state_store
        self._explicit: dict[str, bool] = (
            state_store.load_expanded() if state_store else {}
        )
        self._entries: list[CatalogEntry] = []
        self._groups: list[_Group] = []
        self._rows: list[_Row] = []
        self._source_filter = ""
        self._search = ""
        self._search_collapsed: set[str] = set()
        self._show_history: set[str] = set()
        self._source_labels: list[str] = []
        self._repo_count = 0

    # ------------------------------------------------------------------
    # QAbstractListModel
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self) -> dict[int, QByteArray]:
        return {r: QByteArray(n.encode()) for r, n in _ROLES.items()}

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        name = _ROLES.get(role)
        if name is None:
            return None
        row = self._rows[index.row()]
        g = row.group
        if name == "kind":
            return row.kind
        if name == "groupKey":
            return g.key
        if name == "name":
            return g.name
        if name == "subtitle":
            # 全部源来自同一个订阅时，组头不重复显示订阅名（降噪）
            return g.subtitle if self._repo_count > 1 else ""
        if name == "repoId":
            return g.repo_id
        if name == "repoUrl":
            return g.url
        if name == "sourceType":
            return g.source_type
        if name == "trustState":
            return g.trust_state
        if name == "onDemand":
            return g.on_demand
        if name == "count":
            return len(g.entries)
        if name == "maxEntries":
            return g.max_entries
        if name == "expanded":
            return self.is_expanded(g.key)
        if name == "entry":
            return dict(row.entry.raw) if row.entry is not None else {}
        if name == "entryId":
            return row.entry.entry_id if row.entry is not None else ""
        if name == "historyCount":
            return max(0, len(g.entries) - 1)
        if name == "historyExpanded":
            return g.key in self._show_history
        return None

    # ------------------------------------------------------------------
    # 输入
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[dict[str, Any]] | None) -> None:
        self._entries = [
            CatalogEntry.from_dict(e) for e in (entries or []) if isinstance(e, dict)
        ]
        labels: list[str] = []
        for e in self._entries:
            if e.source_label and e.source_label not in labels:
                labels.append(e.source_label)
        if self._source_filter and self._source_filter not in labels:
            self._source_filter = ""
        if labels != self._source_labels:
            self._source_labels = labels
            self.sourceLabelsChanged.emit()
        self._rebuild()

    @Slot("QVariantList")
    def setEntries(self, entries: list) -> None:  # noqa: N802 - QML 入口
        self.set_entries(list(entries or []))

    @Slot(str)
    def setSourceFilter(self, label: str) -> None:  # noqa: N802
        label = label or ""
        if label == self._source_filter:
            return
        self._source_filter = label
        self._rebuild()

    @Slot(str)
    def setSearch(self, text: str) -> None:  # noqa: N802
        text = (text or "").strip().lower()
        if text == self._search:
            return
        was_active = bool(self._search)
        self._search = text
        self._search_collapsed.clear()
        if was_active != bool(text):
            self.searchActiveChanged.emit()
        self._rebuild()

    # ------------------------------------------------------------------
    # 展开 / 历史
    # ------------------------------------------------------------------

    def default_expanded(self) -> bool:
        """没被用户切换过的组：只有一个源时展开，多个源时收起。"""
        return len(self._groups) == 1

    def is_expanded(self, key: str) -> bool:
        if self._search:
            return key not in self._search_collapsed
        return self._explicit.get(key, self.default_expanded())

    @Slot(str, result=bool)
    def isExpanded(self, key: str) -> bool:  # noqa: N802
        return self.is_expanded(key)

    @Slot(str)
    def toggleGroup(self, key: str) -> None:  # noqa: N802
        if self._search:
            if key in self._search_collapsed:
                self._search_collapsed.discard(key)
            else:
                self._search_collapsed.add(key)
        else:
            self._explicit[key] = not self.is_expanded(key)
            # 最近切换的放最后：store 截断时丢最老的
            self._explicit[key] = self._explicit.pop(key)
            if self._store is not None:
                try:
                    self._store.save_expanded(self._explicit)
                except OSError:
                    pass  # 视图状态写失败不影响使用
        self._update_group_rows(key)

    @Slot(str)
    def toggleHistory(self, key: str) -> None:  # noqa: N802
        if key in self._show_history:
            self._show_history.discard(key)
        else:
            self._show_history.add(key)
        self._update_group_rows(key)

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    def _get_source_labels(self) -> list[str]:
        return list(self._source_labels)

    sourceLabels = Property(
        "QVariantList", _get_source_labels, notify=sourceLabelsChanged
    )

    def _get_total(self) -> int:
        return len(self._entries)

    totalEntryCount = Property(int, _get_total, notify=countsChanged)

    def _get_visible_entries(self) -> int:
        return sum(len(g.entries) for g in self._groups)

    matchedEntryCount = Property(int, _get_visible_entries, notify=countsChanged)

    def _get_group_count(self) -> int:
        return len(self._groups)

    groupCount = Property(int, _get_group_count, notify=countsChanged)

    def _get_search_active(self) -> bool:
        return bool(self._search)

    searchActive = Property(bool, _get_search_active, notify=searchActiveChanged)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _group_rows(self, g: _Group) -> list[_Row]:
        rows = [_Row(KIND_HEADER, g)]
        if not self.is_expanded(g.key):
            return rows
        show_all = not g.on_demand or g.key in self._show_history
        visible = g.entries if show_all else g.entries[:1]
        rows.extend(_Row(KIND_ENTRY, g, e) for e in visible)
        if g.on_demand and (len(g.entries) > 1 or g.key in self._show_history):
            rows.append(_Row(KIND_HISTORY, g))
        return rows

    def _rebuild(self) -> None:
        groups: list[_Group] = []
        by_key: dict[str, _Group] = {}
        repos: set[str] = set()
        for e in self._entries:
            if self._source_filter and e.source_label != self._source_filter:
                continue
            if self._search and not e.matches(self._search):
                continue
            # 两遍构建：先按首次出现收集组，再整组输出——同组条目在输入中
            # 不连续（随机源多次物化交错）时也不会串组
            g = by_key.get(e.authority)
            if g is None:
                g = _Group(
                    key=e.authority,
                    name=e.source_label or "开源文本",
                    subtitle=e.repo.name or e.repo.url or e.authority,
                    repo_id=e.repo.repo_id,
                    url=e.repo.url,
                    source_type=e.source_type,
                    trust_state=e.repo.trust_state,
                    on_demand=e.on_demand,
                    max_entries=e.repo.max_entries,
                )
                by_key[e.authority] = g
                groups.append(g)
            g.entries.append(e)
            repos.add(e.repo.url or e.repo.repo_id)
        self.beginResetModel()
        self._groups = groups
        self._repo_count = len(repos)
        self._rows = [r for g in groups for r in self._group_rows(g)]
        self.endResetModel()
        self.countsChanged.emit()

    def _update_group_rows(self, key: str) -> None:
        start = next(
            (
                i
                for i, r in enumerate(self._rows)
                if r.kind == KIND_HEADER and r.group.key == key
            ),
            -1,
        )
        if start < 0:
            return
        g = self._rows[start].group
        old_end = start + 1
        while old_end < len(self._rows) and self._rows[old_end].kind != KIND_HEADER:
            old_end += 1
        body = self._group_rows(g)[1:]
        if old_end > start + 1:
            self.beginRemoveRows(QModelIndex(), start + 1, old_end - 1)
            del self._rows[start + 1 : old_end]
            self.endRemoveRows()
        if body:
            self.beginInsertRows(QModelIndex(), start + 1, start + len(body))
            self._rows[start + 1 : start + 1] = body
            self.endInsertRows()
        idx = self.index(start)
        self.dataChanged.emit(
            idx, idx, [_ROLE_OF["expanded"], _ROLE_OF["historyExpanded"]]
        )
