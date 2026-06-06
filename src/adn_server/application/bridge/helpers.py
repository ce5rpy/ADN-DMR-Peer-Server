# ADN DMR Peer Server - bridge helpers (V2-P0-004)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Shared bridge routing helpers (no Twisted)."""

from __future__ import annotations

from typing import Any

from ...domain import bytes_3, int_id

# Embedded LC codeword sits at bits 116:148 inside the 48-bit EMB field (108:156).
# Legacy bridge_master.py replaces dmrbits[116:148] on bursts B–E (dtype_vseq 1–4).
EMB_LC_SLICE = slice(116, 148)


def obp_target_bcsq_quenches_stream(
    systems_cfg: dict[str, Any], target_name: str, dst_id_b: bytes, stream_id: bytes
) -> bool:
    """True if target OBP config has _bcsq[tgid]==stream_id (bytes key or same int TG)."""
    m = systems_cfg.get(target_name, {}).get("_bcsq")
    if not isinstance(m, dict) or not m:
        return False
    tid = dst_id_b[:3] if isinstance(dst_id_b, bytes) and len(dst_id_b) >= 3 else bytes_3(int_id(dst_id_b))
    if m.get(tid) == stream_id:
        return True
    for k, v in m.items():
        if v != stream_id:
            continue
        try:
            if isinstance(k, bytes) and len(k) >= 3 and int_id(k) == int_id(tid):
                return True
        except Exception:
            continue
    return False


def is_special_tg(bridge_key: str) -> bool:
    """True if bridge is special TGID 9990-9999 (excluded from infinite timer)."""
    if bridge_key and bridge_key[0:1] == "#":
        return False
    try:
        return 9990 <= int(bridge_key) <= 9999
    except ValueError:
        return False
