"""SubscriptionStore sync from BRIDGES (V2-P2-008)."""

from __future__ import annotations

from typing import Any

from adn_server.application.subscription.bridges_export import export_bridges
from adn_server.application.subscription.store_sync import replace_store_from_bridges
from adn_server.domain import bytes_3, int_id
from adn_server.infrastructure.bootstrap.peer_server import _make_echo_bridges
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _row_fingerprint(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("SYSTEM"),
        int(row.get("TS") or 1),
        int_id(row.get("TGID") or b"\x00\x00\x00"),
        bool(row.get("ACTIVE")),
        str(row.get("TO_TYPE", "ON")),
        row.get("TIMEOUT"),
    )


def _bridges_fingerprints(bridges: dict[str, list[dict[str, Any]]]) -> set[tuple[Any, ...]]:
    fps: set[tuple[Any, ...]] = set()
    for rows in bridges.values():
        for row in rows:
            if isinstance(row, dict):
                fps.add(_row_fingerprint(row))
    return fps


def test_replace_store_from_echo_bridges_round_trip():
    config = {
        "SYSTEMS": {
            "ECHO": {"MODE": "PEER"},
            "MASTER-A": {"MODE": "MASTER", "DEFAULT_UA_TIMER": 10},
            "MASTER-B": {"MODE": "MASTER", "DEFAULT_UA_TIMER": 15},
        }
    }
    bridges = _make_echo_bridges(config)
    store = InMemorySubscriptionStore()
    replace_store_from_bridges(store, bridges)

    assert len(store.snapshot()) == len(_bridges_fingerprints(bridges))

    now = 1_700_000_000.0
    exported = export_bridges(store, now=now)
    assert _bridges_fingerprints(bridges) == _bridges_fingerprints(exported)


def test_replace_store_clears_stale_entries():
    store = InMemorySubscriptionStore()
    bridges_a = {
        "100": [
            {
                "SYSTEM": "SYS-A",
                "TS": 1,
                "TGID": bytes_3(100),
                "ACTIVE": False,
                "TIMEOUT": 600.0,
                "TO_TYPE": "ON",
            }
        ]
    }
    bridges_b = {
        "200": [
            {
                "SYSTEM": "SYS-B",
                "TS": 2,
                "TGID": bytes_3(200),
                "ACTIVE": True,
                "TIMEOUT": 600.0,
                "TO_TYPE": "ON",
            }
        ]
    }
    replace_store_from_bridges(store, bridges_a)
    assert len(store.snapshot()) == 1
    replace_store_from_bridges(store, bridges_b)
    assert len(store.snapshot()) == 1
    (sub,) = store.snapshot()
    assert int(sub.channel.tgid) == 200
