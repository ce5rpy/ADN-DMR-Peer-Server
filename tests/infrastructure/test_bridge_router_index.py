"""BRIDGES source index parity with legacy full scan."""

from __future__ import annotations

from adn_server.domain import bytes_3, int_id
from adn_server.infrastructure.bridge_router_impl import InMemoryBridgeRouter


def _legacy_scan_tables(
    bridges: dict,
    system_name: str,
    bridge_match_slot: int,
    dst_id_b: bytes,
    dst_int: int,
) -> list[str]:
    result: list[str] = []

    def row_is_active_source(row: dict) -> bool:
        return bool(
            row.get("SYSTEM") == system_name
            and row.get("TS") == bridge_match_slot
            and row.get("ACTIVE")
            and (
                row.get("TGID") == dst_id_b
                or int_id(row.get("TGID") or b"\x00\x00\x00") == dst_int
            )
        )

    for bridge_name, rows in bridges.items():
        if any(row_is_active_source(r) for r in rows):
            result.append(bridge_name)
    return result


def test_index_matches_legacy_scan_static_tg() -> None:
    router = InMemoryBridgeRouter()
    tgid = bytes_3(91)
    router.set_bridges(
        {
            "91": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": tgid, "ACTIVE": True},
                {"SYSTEM": "MASTER-B", "TS": 2, "TGID": tgid, "ACTIVE": True},
            ]
        }
    )
    dst_b = tgid
    dst_int = 91
    legacy = _legacy_scan_tables(router.get_bridges(), "MASTER-A", 2, dst_b, dst_int)
    indexed = router.bridge_tables_with_active_source("MASTER-A", 2, dst_int)
    assert indexed == legacy == ["91"]


def test_index_matches_legacy_scan_multiple_tables() -> None:
    router = InMemoryBridgeRouter()
    tgid = bytes_3(310)
    router.set_bridges(
        {
            "91": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": bytes_3(91), "ACTIVE": True},
                {"SYSTEM": "MASTER-B", "TS": 2, "TGID": bytes_3(91), "ACTIVE": True},
            ],
            "#310": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": tgid, "ACTIVE": True},
                {"SYSTEM": "OBP-1", "TS": 1, "TGID": tgid, "ACTIVE": True},
            ],
        }
    )
    legacy = _legacy_scan_tables(router.get_bridges(), "MASTER-A", 2, tgid, 310)
    indexed = router.bridge_tables_with_active_source("MASTER-A", 2, 310)
    assert indexed == legacy == ["#310"]


def test_index_empty_when_no_active_source() -> None:
    router = InMemoryBridgeRouter()
    router.set_bridges(
        {
            "91": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": bytes_3(91), "ACTIVE": False},
                {"SYSTEM": "MASTER-B", "TS": 2, "TGID": bytes_3(91), "ACTIVE": True},
            ]
        }
    )
    assert router.bridge_tables_with_active_source("MASTER-A", 2, 91) == []


def test_index_updates_after_in_place_mutation() -> None:
    router = InMemoryBridgeRouter()
    bridges = router.get_bridges()
    bridges["91"] = [
        {"SYSTEM": "MASTER-A", "TS": 2, "TGID": bytes_3(91), "ACTIVE": False},
        {"SYSTEM": "MASTER-B", "TS": 2, "TGID": bytes_3(91), "ACTIVE": True},
    ]
    assert router.bridge_tables_with_active_source("MASTER-A", 2, 91) == []
    bridges["91"][0]["ACTIVE"] = True
    legacy = _legacy_scan_tables(bridges, "MASTER-A", 2, bytes_3(91), 91)
    assert router.bridge_tables_with_active_source("MASTER-A", 2, 91) == legacy == ["91"]


def test_index_many_bridge_tables() -> None:
    """Regression: index order and membership match legacy scan with many tables."""
    router = InMemoryBridgeRouter()
    tgid = bytes_3(500)
    bridges: dict[str, list] = {}
    for i in range(120):
        bridges[str(1000 + i)] = [
            {"SYSTEM": "MASTER-X", "TS": 1, "TGID": bytes_3(1000 + i), "ACTIVE": True},
        ]
    bridges["500"] = [
        {"SYSTEM": "MASTER-A", "TS": 2, "TGID": tgid, "ACTIVE": True},
        {"SYSTEM": "MASTER-B", "TS": 2, "TGID": tgid, "ACTIVE": True},
    ]
    router.set_bridges(bridges)
    legacy = _legacy_scan_tables(router.get_bridges(), "MASTER-A", 2, tgid, 500)
    indexed = router.bridge_tables_with_active_source("MASTER-A", 2, 500)
    assert indexed == legacy == ["500"]
