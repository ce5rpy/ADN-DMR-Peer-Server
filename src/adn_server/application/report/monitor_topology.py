"""Monitor topology parity for inject-only proxy (legacy SYSTEM-N / 56400+N).

Hotspot radio IDs often share a user/subscriber prefix, e.g. user ``7300391`` with
HS1 ``730039101``, HS2 ``730039102``, … HS99 ``730039199`` (``user * 100 + n``).
Voice-event peer resolution must not guess when several connected peers match the
same user or 6-digit legacy prefix.
"""

from __future__ import annotations

import copy
from typing import Any

from adn_server.application.proxy.deployment import is_proxy_inject_only, proxy_target_system
from adn_server.domain.value_objects import bytes_4, int_id

DEFAULT_REPORT_BASE_PORT = 56400


def _connected_peers(peers: dict[Any, dict[str, Any]]) -> list[tuple[Any, dict[str, Any]]]:
    return [
        (peer_key, peer)
        for peer_key, peer in peers.items()
        if isinstance(peer, dict) and peer.get("CONNECTION") == "YES"
    ]


def _resolve_slot_map(
    connected: list[tuple[Any, dict[str, Any]]],
    peer_slots: dict[bytes, int] | None,
    *,
    max_slots: int,
) -> dict[Any, int]:
    """Map peer keys to upstream slot indices for monitor ``SYSTEM-N`` rows."""
    slot_map: dict[Any, int] = {}
    if peer_slots:
        for peer_key, _peer in connected:
            if isinstance(peer_key, bytes) and peer_key in peer_slots:
                slot_map[peer_key] = peer_slots[peer_key]
    used = set(slot_map.values())
    for peer_key, _peer in sorted(connected, key=lambda item: int_id(item[0])):
        if peer_key in slot_map:
            continue
        for index in range(max_slots):
            if index not in used:
                slot_map[peer_key] = index
                used.add(index)
                break
    return slot_map


def expand_inject_proxy_systems(
    config: dict[str, Any],
    systems: dict[str, Any],
    peer_slots: dict[bytes, int] | None = None,
) -> dict[str, Any]:
    """Fan inject-only ``SYSTEM`` peers into ``SYSTEM-N`` masters for monitor/report.

    Runtime HBP stays on a single inject target; only the topology snapshot sent to
    adn-monitor matches legacy ``expand_generator`` + adn-proxy upstream ports.
    """
    target = proxy_target_system(config)
    if not target or not is_proxy_inject_only(config, target):
        return systems
    sys_cfg = systems.get(target)
    if not isinstance(sys_cfg, dict) or sys_cfg.get("MODE") != "MASTER":
        return systems
    peers = sys_cfg.get("PEERS", {})
    if not isinstance(peers, dict):
        return systems

    max_slots = int(sys_cfg.get("MAX_PEERS", 1))
    base_port = int(sys_cfg.get("_REPORT_BASE_PORT", DEFAULT_REPORT_BASE_PORT))
    connected = _connected_peers(peers)
    slot_map = _resolve_slot_map(connected, peer_slots, max_slots=max_slots)

    out = {name: cfg for name, cfg in systems.items() if name != target}
    # Legacy ``expand_generator``: emit every virtual master (SYSTEM-0..N-1) so the
    # monitor does not delete unused upstream slots on topology/config update.
    for slot in range(max_slots):
        virtual_name = f"{target}-{slot}"
        virtual = copy.deepcopy(sys_cfg)
        virtual["PORT"] = base_port + slot
        virtual["PEERS"] = {
            peer_key: peers[peer_key]
            for peer_key, mapped in slot_map.items()
            if mapped == slot and peer_key in peers
        }
        out[virtual_name] = virtual
    return out


def _slot_for_voice_peer(
    peer_key: bytes,
    *,
    peers: dict[Any, dict[str, Any]],
    peer_slots: dict[bytes, int] | None,
    max_slots: int,
) -> int | None:
    connected = _connected_peers(peers)
    slot_map = _resolve_slot_map(connected, peer_slots, max_slots=max_slots)
    return slot_map.get(peer_key)


def _peer_key_from_int(peer_key: Any) -> bytes:
    if isinstance(peer_key, bytes):
        return peer_key
    return bytes_4(int_id(peer_key))


def _connected_peer_keys(peers: dict[Any, Any]) -> list[bytes]:
    keys: list[bytes] = []
    for peer_key, peer in peers.items():
        if not isinstance(peer, dict) or peer.get("CONNECTION") != "YES":
            continue
        keys.append(_peer_key_from_int(peer_key))
    return keys


def _unique_peer_match(matches: list[bytes]) -> bytes | None:
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def _peers_for_voice_candidate(val: int, connected: list[bytes]) -> list[bytes]:
    """Match a BRDG_EVENT peer/subscriber field to connected hotspot radio ids."""
    exact = bytes_4(val)
    if exact in connected:
        return [exact]
    val_str = str(val)
    matches: list[bytes] = []
    for peer_key in connected:
        peer_int = int_id(peer_key)
        peer_str = str(peer_int)
        if peer_str == val_str:
            matches.append(peer_key)
            continue
        # user 7300391 → radios 730039101..730039199 (user * 100 + hs)
        if peer_int // 100 == val:
            matches.append(peer_key)
            continue
        if len(val_str) >= 5 and len(peer_str) >= 7 and peer_str.startswith(val_str):
            matches.append(peer_key)
            continue
        if len(val_str) >= 7 and peer_str.startswith(val_str) and len(peer_str) == len(val_str) + 2:
            matches.append(peer_key)
            continue
        # legacy 6-digit dst (bridge.py hotspot match) — ambiguous when user has >1 HS
        if len(val_str) >= 6 and len(peer_str) >= 6 and peer_str[:6] == val_str[:6]:
            matches.append(peer_key)
    return matches


def _peer_key_from_voice_csv(parts: list[str], peers: dict[Any, Any]) -> bytes | None:
    """Resolve hotspot radio id from legacy BRDG_EVENT CSV (peer_id, then rf_src).

    Prefer exact radio ids. Fuzzy user/6-digit matching applies only when a single
    connected peer matches (e.g. one HS online for user 7300391).
    """
    connected = _connected_peer_keys(peers)
    if not connected:
        return None
    field_values: list[tuple[int, int]] = []
    for idx in (5, 6):
        if len(parts) <= idx:
            continue
        raw = parts[idx].strip()
        if not raw:
            continue
        try:
            field_values.append((idx, int(raw)))
        except ValueError:
            continue
    for _idx, val in field_values:
        key = bytes_4(val)
        if key in connected:
            return key
    for _idx, val in field_values:
        matched = _peers_for_voice_candidate(val, connected)
        resolved = _unique_peer_match(matched)
        if resolved is not None:
            return resolved
    return None


def remap_inject_proxy_voice_event(
    event: str,
    config: dict[str, Any],
    systems: dict[str, Any],
    peer_slots: dict[bytes, int] | None = None,
) -> str:
    """Map inject-only ``SYSTEM`` voice events to ``SYSTEM-N`` for monitor ``rts_update``.

    Topology expansion removes the runtime inject target from CONFIG/TOPOLOGY; voice
    events must use the same virtual master name or dashboard hotspot chips stay idle.
    """
    target = proxy_target_system(config)
    if not target or not is_proxy_inject_only(config, target):
        return event
    parts = event.split(",")
    if len(parts) < 6 or parts[3].strip() != target:
        return event
    sys_cfg = systems.get(target, {})
    if not isinstance(sys_cfg, dict):
        return event
    peers = sys_cfg.get("PEERS", {})
    if not isinstance(peers, dict):
        return event
    peer_key = _peer_key_from_voice_csv(parts, peers)
    if peer_key is None:
        return event
    max_slots = int(sys_cfg.get("MAX_PEERS", 1))
    slot = _slot_for_voice_peer(
        peer_key, peers=peers, peer_slots=peer_slots, max_slots=max_slots
    )
    if slot is None:
        return event
    parts[3] = f"{target}-{slot}"
    # RX legs: field 5 is the RF source peer — normalize to full hotspot radio id.
    # TX legs: keep legacy field 5 (echo 9990, OBP server id) so the hotspot chip
    # shows TX/green while receiving; rewriting to the hotspot id would mark RX/red.
    if len(parts) > 5 and len(parts) > 2 and parts[2].strip() == "RX":
        resolved_peer = int_id(peer_key)
        try:
            reported_peer = int(parts[5].strip())
        except ValueError:
            reported_peer = None
        if reported_peer != resolved_peer:
            parts[5] = str(resolved_peer)
    return ",".join(parts)
