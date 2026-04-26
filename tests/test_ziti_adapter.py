from unittest.mock import MagicMock

from src.backend.models.dto.ziti import ZitiScheme, ZitiSchemeData
from src.backend.presentation.adapters.ziti_adapter import ZitiAdapter


class DummyThreadPool:
    def __init__(self) -> None:
        self.started_workers = []

    def start(self, worker) -> None:
        self.started_workers.append(worker)


def _build_adapter() -> tuple[ZitiAdapter, MagicMock, DummyThreadPool]:
    gateway = MagicMock()
    adapter = ZitiAdapter(gateway=gateway)
    pool = DummyThreadPool()
    adapter._thread_pool = pool
    return adapter, gateway, pool


def test_load_ziti_schemes_enqueues_worker_and_emits_payload() -> None:
    adapter, gateway, pool = _build_adapter()
    gateway.list_schemes.return_value = [ZitiScheme(name="小鹤", entry_count=2)]
    loaded: list[list[dict]] = []
    adapter.schemesLoaded.connect(loaded.append)

    adapter.loadSchemes()
    pool.started_workers[0].run()

    assert loaded == [[{"name": "小鹤", "entryCount": 2}]]


def test_load_ziti_scheme_sets_current_hints_and_emits_state() -> None:
    adapter, gateway, pool = _build_adapter()
    gateway.load_scheme.return_value = ZitiSchemeData(
        scheme=ZitiScheme(name="小鹤", entry_count=2),
        hints={"一": "yi", "二": "er"},
    )
    loaded: list[tuple[str, int]] = []
    adapter.schemeLoaded.connect(lambda name, count: loaded.append((name, count)))
    changes: list[tuple[bool, str, int]] = []
    adapter.zitiStateChanged.connect(
        lambda: changes.append(
            (adapter.enabled, adapter.current_scheme, adapter.loaded_count)
        )
    )

    adapter.loadScheme("小鹤")
    pool.started_workers[0].run()

    assert loaded == [("小鹤", 2)]
    assert changes[-1] == (False, "小鹤", 2)
    assert adapter.get_hint("一") == "yi"
    assert adapter.get_hint("三") == ""


def test_set_ziti_enabled_emits_state_change() -> None:
    adapter, _, _ = _build_adapter()
    changes: list[bool] = []
    adapter.zitiStateChanged.connect(lambda: changes.append(adapter.enabled))

    adapter.setEnabled(True)

    assert adapter.enabled is True
    assert changes == [True]
