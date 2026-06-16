# ADN DMR Peer Server - tests application peer single downlink
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""Per-peer SINGLE=1 downlink exclusivity (inject-only multi-hotspot)."""

from __future__ import annotations


from adn_server.domain import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, bytes_3, bytes_4, int_id

from adn_server.application.routing.helpers import (
    clear_peer_ua_sessions,
    tg4000_reset_on_vhead,
    clear_peer_rx_status_slots,
    peer_receives_group_tgid,
    peer_should_receive_group_voice,
    peer_single_blocks_group_voice,
    peer_single_blocks_uplink,
    register_peer_ua_multi_tg,
    register_peer_ua_session,
    seed_peer_ua_session_from_status,
)


def _sys_cfg() -> dict:
    return {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}


def _peer_id() -> bytes:
    return bytes_4(730039101)


def test_static_tg_on_opposite_slot_receives_group_voice() -> None:
    """Hotspot lists TG on TS1 but network voice arrives on TS2 (legacy REPEAT parity)."""
    peer = {"OPTIONS": b"TS1=730170;"}
    assert peer_receives_group_tgid(peer, 2, 730170)
    assert peer_should_receive_group_voice(peer, 2, 730170, connected_count=8)


def test_single_blocks_other_static_tg_while_session_on_static() -> None:
    """Indigo on 7305 blocks RX on 730 even when both are in OPTIONS."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)

    assert peer_should_receive_group_voice(
        peer, 2, 7305, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 60
    )
    assert not peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 60
    )


def test_single_session_survives_on_sys_cfg_store() -> None:
    """Session lives on ``sys_cfg['_PEER_UA_SESSIONS']``, not only the peer dict."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    peer.pop("_UA_SESSION", None)

    assert not peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 60
    )


def test_single_uses_peer_options_timer_not_yaml_default() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 60}
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    still_locked = now + 5 * 60 - 1
    expired = now + 5 * 60 + 1

    assert not peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=still_locked
    )
    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=expired
    )


def test_single_allows_other_tg_after_timer_expires() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    expired = now + 5 * 60 + 1

    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=expired
    )


def test_single_zero_allows_multiple_static_tgs() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)

    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 60
    )


def test_tg4000_reset_only_on_voice_header() -> None:
    assert tg4000_reset_on_vhead(4000, HBPF_DATA_SYNC, HBPF_SLT_VHEAD)
    assert not tg4000_reset_on_vhead(4000, HBPF_DATA_SYNC, 2)
    assert not tg4000_reset_on_vhead(730, HBPF_DATA_SYNC, HBPF_SLT_VHEAD)


def test_tg4000_clears_single_session() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    clear_peer_ua_sessions(peer, sys_cfg, peer_id, slot=2)

    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_seed_session_from_status_after_options() -> None:
    """TX on 7305 before RPTO SINGLE=1 — OPTIONS must seed the lock."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;", "CONNECTED": 999_000.0}
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    status = {"RX_PEER": peer_id, "RX_TGID": bytes_3(7305), "RX_TIME": 999_500.0}
    now = 1_000_000.0
    seed_peer_ua_session_from_status(
        peer, peer_id, 2, status, sys_cfg, now=now,
    )
    assert not peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_seed_ignores_stale_status_from_before_reconnect() -> None:
    """OPTIONS after reconnect must not restore indigo from pre-login STATUS."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;", "CONNECTED": 2_000_000.0}
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    status = {"RX_PEER": peer_id, "RX_TGID": bytes_3(7305), "RX_TIME": 1_000_000.0}
    now = 2_000_100.0
    seed_peer_ua_session_from_status(
        peer, peer_id, 2, status, sys_cfg, now=now,
    )
    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_disconnect_clears_session_on_peer_and_sys_cfg() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    clear_peer_ua_sessions(peer, sys_cfg, peer_id)
    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_disconnect_clears_stale_rx_status() -> None:
    peer_id = _peer_id()
    status = {
        2: {"RX_PEER": peer_id, "RX_TGID": bytes_3(7305), "RX_TIME": 1_000_000.0},
    }
    clear_peer_rx_status_slots(status, peer_id)
    assert status[2]["RX_PEER"] == b"\x00"
    assert int_id(status[2]["RX_TGID"]) == 0


def test_single_never_blocks_uplink_tx_switches_indigo() -> None:
    """SINGLE=1 blocks RX on other TGs, not local TX; new TX replaces the session."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    assert not peer_single_blocks_uplink(peer, peer_id, 2, 730, sys_cfg, now=now + 10)
    assert peer_single_blocks_group_voice(peer, 2, 730, sys_cfg, peer_id=peer_id, now=now + 10)
    register_peer_ua_session(peer, peer_id, 2, 730, sys_cfg, now=now + 120)
    assert not peer_single_blocks_group_voice(peer, 2, 730, sys_cfg, peer_id=peer_id, now=now + 121)
    assert peer_single_blocks_group_voice(peer, 2, 7305, sys_cfg, peer_id=peer_id, now=now + 121)


def test_single_still_blocks_non_static_dynamic() -> None:
    """Dynamic UA not in OPTIONS stays exclusive to the session owner."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    assert not peer_should_receive_group_voice(
        peer, 2, 730444, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_cross_peer_static_tx_does_not_reach_locked_peer() -> None:
    """730039101 indigo 7305 must not hear 730 when 730039210 keys up on 730."""
    peer_a = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    peer_b = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    id_a = bytes_4(730039101)
    id_b = bytes_4(730039210)
    now = 1_000_000.0
    register_peer_ua_session(peer_a, id_a, 2, 7305, sys_cfg, now=now)
    register_peer_ua_session(peer_b, id_b, 2, 730, sys_cfg, now=now + 5)
    assert not peer_should_receive_group_voice(
        peer_a, 2, 730, peer_id=id_a, connected_count=3, sys_cfg=sys_cfg, now=now + 10
    )


def test_active_routing_table_does_not_fan_out_without_static_tg() -> None:
    """Regression: ACTIVE BRIDGES leg must not deliver to peers missing TG in OPTIONS."""
    peer_without = {"OPTIONS": b"TS2=91;"}
    peer_with = {"OPTIONS": b"TS2=7305;"}
    bridges = {
        "7305": [
            {
                "SYSTEM": "SYSTEM",
                "TS": 2,
                "ACTIVE": True,
                "TO_TYPE": "ON",
            }
        ]
    }
    assert not peer_should_receive_group_voice(
        peer_without,
        2,
        7305,
        system="SYSTEM",
        bridges=bridges,
        connected_count=8,
        sys_cfg=_sys_cfg(),
    )
    assert peer_should_receive_group_voice(
        peer_with,
        2,
        7305,
        system="SYSTEM",
        bridges=bridges,
        connected_count=8,
        sys_cfg=_sys_cfg(),
    )


def test_dynamic_ua_delivers_only_to_session_owner() -> None:
    """UA TG not in static OPTIONS — only the activating SINGLE peer receives it."""
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    other = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    other_id = bytes_4(730039210)
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 730444, sys_cfg, now=now)
    assert peer_should_receive_group_voice(
        peer, 2, 730444, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )
    assert not peer_should_receive_group_voice(
        other, 2, 730444, peer_id=other_id, connected_count=8, sys_cfg=sys_cfg, now=now + 10
    )


def test_peer_without_static_tgs_receives_nothing_until_dynamic() -> None:
    """No OPTIONS static list → no downlink; dynamic UA session is the only path."""
    peer = {"OPTIONS": b"Type=HBlink;SINGLE=1;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    assert not peer_should_receive_group_voice(
        peer, 2, 7305, peer_id=peer_id, connected_count=1, sys_cfg=sys_cfg, now=now + 10
    )
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    assert peer_should_receive_group_voice(
        peer, 2, 7305, peer_id=peer_id, connected_count=1, sys_cfg=sys_cfg, now=now + 10
    )


def test_single_zero_dynamic_heard_when_both_peers_keyed() -> None:
    """SINGLE=0: HS1 and HS2 both keyed 7304 → each hears the other's TX on 7304."""
    peer_a = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    peer_b = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    sys_cfg = _sys_cfg()
    id_a = bytes_4(730039101)
    id_b = bytes_4(730039210)
    now = 1_000_000.0
    register_peer_ua_session(peer_a, id_a, 2, 7304, sys_cfg, now=now)
    register_peer_ua_session(peer_b, id_b, 2, 7304, sys_cfg, now=now + 5)

    assert peer_should_receive_group_voice(
        peer_a, 2, 7304, peer_id=id_a, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )
    assert peer_should_receive_group_voice(
        peer_b, 2, 7304, peer_id=id_b, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )


def test_single_zero_dynamic_not_heard_without_local_key() -> None:
    """SINGLE=0: dynamic 7304 only reaches peers that keyed it (not the other HS)."""
    peer_a = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    peer_b = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    sys_cfg = _sys_cfg()
    id_a = bytes_4(730039101)
    id_b = bytes_4(730039210)
    now = 1_000_000.0
    register_peer_ua_session(peer_a, id_a, 2, 7304, sys_cfg, now=now)

    assert peer_should_receive_group_voice(
        peer_a, 2, 7304, peer_id=id_a, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )
    assert not peer_should_receive_group_voice(
        peer_b, 2, 7304, peer_id=id_b, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )


def test_single_zero_tg4000_clears_multi_dynamic() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_multi_tg(peer, peer_id, 2, 7304, sys_cfg)
    clear_peer_ua_sessions(peer, sys_cfg, peer_id, slot=2)
    assert not peer_should_receive_group_voice(
        peer, 2, 7304, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )


def test_new_tx_replaces_single_session_tg() -> None:
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    sys_cfg = _sys_cfg()
    peer_id = _peer_id()
    now = 1_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7305, sys_cfg, now=now)
    register_peer_ua_session(peer, peer_id, 2, 730, sys_cfg, now=now + 120)

    assert peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 121
    )
    assert not peer_should_receive_group_voice(
        peer, 2, 7305, peer_id=peer_id, connected_count=8, sys_cfg=sys_cfg, now=now + 121
    )
