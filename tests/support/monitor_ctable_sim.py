"""Minimal adn-monitor CTABLE semantics for report contract tests.

Mirrors the behaviour that broke production (``update_hblink_table_impl`` in
adn-monitor): masters missing from CONFIG are deleted; peers on ``SYSTEM-N`` are
only visible when that master already exists in CTABLE (update does not create
new master rows).
"""

from __future__ import annotations

import copy
from typing import Any

from adn_server.domain.value_objects import bytes_4, int_id


def empty_ctable() -> dict[str, Any]:
    return {"MASTERS": {}, "PEERS": {}, "OPENBRIDGES": {}}


def build_ctable_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Monitor ``build_hblink_table`` path (empty CTABLE on first connect)."""
    ctable = empty_ctable()
    for name, data in config.items():
        if not data.get("ENABLED", True):
            continue
        mode = data.get("MODE")
        if mode == "MASTER":
            ctable["MASTERS"][name] = {"PEERS": {}}
            for peer_key, peer_conf in data.get("PEERS", {}).items():
                if peer_conf.get("CONNECTION") == "YES":
                    _add_peer(ctable["MASTERS"][name]["PEERS"], peer_key)
        elif mode == "OPENBRIDGE":
            ctable["OPENBRIDGES"][name] = {"STREAMS": {}}
    return ctable


def update_ctable_from_config(config: dict[str, Any], ctable: dict[str, Any]) -> None:
    """Monitor ``update_hblink_table`` path (CTABLE already populated)."""
    for key in ("MASTERS", "PEERS", "OPENBRIDGES"):
        for name in list(ctable.get(key, {})):
            if name not in config:
                del ctable[key][name]
    for name, data in config.items():
        if data.get("MODE") != "MASTER":
            continue
        # Peers attach only to masters that already exist — no master creation here.
        masters_peers = ctable["MASTERS"].get(name, {}).get("PEERS", {})
        for peer_key, peer_conf in data.get("PEERS", {}).items():
            if peer_conf.get("CONNECTION") != "YES":
                continue
            pid = int_id(peer_key)
            if pid not in masters_peers:
                _add_peer(masters_peers, peer_key)
        for peer_id in list(masters_peers):
            if bytes_4(peer_id) not in data.get("PEERS", {}):
                del masters_peers[peer_id]


def apply_config_to_ctable(config: dict[str, Any], ctable: dict[str, Any]) -> None:
    """Legacy ``_apply_config_to_state`` (v1 CONFIG_SND / topology): build when empty, else update."""
    if ctable["MASTERS"]:
        update_ctable_from_config(config, ctable)
    else:
        built = build_ctable_from_config(config)
        ctable["MASTERS"] = built["MASTERS"]
        ctable["PEERS"] = built["PEERS"]
        ctable["OPENBRIDGES"] = built["OPENBRIDGES"]


def apply_slim_dashboard_state(config: dict[str, Any], ctable: dict[str, Any]) -> None:
    """D-25 ``dashboard_state``: full snapshot — prune absent rows, then rebuild."""
    for key in ("MASTERS", "PEERS", "OPENBRIDGES"):
        section = ctable.setdefault(key, {})
        for name in list(section):
            if name not in config:
                del section[name]
    built = build_ctable_from_config(config)
    for key in ("MASTERS", "PEERS", "OPENBRIDGES"):
        ctable[key] = built[key]


def count_masters(ctable: dict[str, Any]) -> int:
    return len(ctable.get("MASTERS", {}))


def count_master_peers(ctable: dict[str, Any]) -> int:
    total = 0
    for master in ctable.get("MASTERS", {}).values():
        total += len(master.get("PEERS", {}))
    return total


def ctable_with_virtual_masters(
    *,
    target: str = "SYSTEM",
    max_slots: int,
    extra: tuple[str, ...] = ("ECHO", "D-APRS-0", "OBP-CL"),
) -> dict[str, Any]:
    """CTABLE like a healthy monitor before the sparse-topology regression."""
    ctable = empty_ctable()
    for slot in range(max_slots):
        ctable["MASTERS"][f"{target}-{slot}"] = {"PEERS": {}}
    for name in extra:
        if name == "OBP-CL":
            ctable["OPENBRIDGES"][name] = {"STREAMS": {}}
        else:
            ctable["MASTERS"][name] = {"PEERS": {}}
    return ctable


def sparse_expand_buggy(
    config: dict[str, Any],
    systems: dict[str, Any],
    peer_slots: dict[bytes, int] | None,
) -> dict[str, Any]:
    """Old broken behaviour: only ``SYSTEM-N`` slots that carry peers."""
    import copy as _copy

    from adn_server.application.proxy.deployment import is_proxy_inject_only, proxy_target_system
    from adn_server.application.report.monitor_topology import (
        _connected_peers,
        _resolve_slot_map,
    )

    target = proxy_target_system(config)
    if not target or not is_proxy_inject_only(config, target):
        return systems
    sys_cfg = systems.get(target)
    if not isinstance(sys_cfg, dict) or sys_cfg.get("MODE") != "MASTER":
        return systems
    peers = sys_cfg.get("PEERS", {})
    max_slots = int(sys_cfg.get("MAX_PEERS", 1))
    base_port = int(sys_cfg.get("_REPORT_BASE_PORT", 56400))
    connected = _connected_peers(peers)
    slot_map = _resolve_slot_map(connected, peer_slots, max_slots=max_slots)
    out = {name: cfg for name, cfg in systems.items() if name != target}
    for slot in sorted({s for s in slot_map.values()}):
        virtual_name = f"{target}-{slot}"
        virtual = _copy.deepcopy(sys_cfg)
        virtual["PORT"] = base_port + slot
        virtual["PEERS"] = {
            peer_key: peers[peer_key]
            for peer_key, mapped in slot_map.items()
            if mapped == slot and peer_key in peers
        }
        out[virtual_name] = virtual
    return out


def config_from_systems(systems: dict[str, Any]) -> dict[str, Any]:
    """CONFIG dict shape after monitor ``dashboard_state_to_config`` (masters with live peers)."""
    config: dict[str, Any] = {}
    for name, data in systems.items():
        if not isinstance(data, dict) or not data.get("ENABLED", True):
            continue
        mode = data.get("MODE")
        entry: dict[str, Any] = {"ENABLED": True, "MODE": mode}
        if mode == "MASTER":
            peers = {
                peer_key: peer_conf
                for peer_key, peer_conf in data.get("PEERS", {}).items()
                if isinstance(peer_conf, dict) and peer_conf.get("CONNECTION") == "YES"
            }
            if not peers:
                continue
            entry["PEERS"] = peers
        elif mode == "OPENBRIDGE":
            entry["NETWORK_ID"] = data.get("NETWORK_ID", 0)
        else:
            continue
        config[name] = entry
    return config


def deep_copy_ctable(ctable: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(ctable)


def _add_peer(peers: dict[int, dict[str, str]], peer_key: Any) -> None:
    peers[int_id(peer_key)] = {"CONNECTION": "YES"}
