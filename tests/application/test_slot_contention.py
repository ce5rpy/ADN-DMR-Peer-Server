# ADN DMR Peer Server - slot contention helpers
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from adn_server.application.routing.helpers import (
    group_voice_tg_ingress_collision,
    hbp_ingress_downlink_session_blocks_tx,
    hbp_ingress_new_stream_collision,
    hbp_master_ingress_repeat_allowed,
    hbp_slot_blocks_group_voice,
    hbp_slot_blocks_group_voice_for_peer,
    peer_hotspot_voice_slot_busy,
    register_peer_ua_session,
    slot_has_active_voice,
    slot_in_group_hangtime,
    slot_status_hotspot_owner,
)
from adn_server.domain import HBPF_DATA_SYNC, bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, STREAM_TO

_TG_A = bytes_3(7144)
_TG_B = bytes_3(730444)
_STREAM_A = bytes_4(0x11111111)
_STREAM_B = bytes_4(0x22222222)


def _active_rx_slot(tgid: bytes = _TG_A, stream_id: bytes = _STREAM_A, t: float = 1_000_000.0) -> dict:
    return {
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": tgid,
        "RX_TIME": t,
        "RX_STREAM_ID": stream_id,
        "TX_TIME": 0.0,
    }


def test_active_slot_blocks_other_tg_even_with_zero_hangtime() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    assert slot_has_active_voice(slot, now + 0.1)
    assert hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 0.1, 0.0)


def test_same_stream_allowed_during_active_qso() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    assert not hbp_slot_blocks_group_voice(slot, _TG_A, _STREAM_A, now + 0.1, 0.0)


def test_ingress_same_subscriber_rekey_allowed() -> None:
    """Legacy: same RF source may open a new stream while the prior is still open."""
    now = 1_000_000.0
    rf = bytes_3(3120001)
    slot = _active_rx_slot(stream_id=_STREAM_A, t=now)
    slot["RX_RFS"] = rf
    assert not hbp_ingress_new_stream_collision(
        slot, bytes_4(1001), rf, _STREAM_B, now + 0.1, per_peer=False,
    )


def test_ingress_collides_when_other_hotspot_owns_busy_slot() -> None:
    """MASTER slot is global: second hotspot must not open a new stream on a busy TS."""
    now = 1_000_000.0
    slot = _active_rx_slot()
    slot["RX_RFS"] = bytes_3(730039264)
    slot["RX_PEER"] = bytes_4(730039264)
    assert hbp_ingress_new_stream_collision(
        slot,
        bytes_4(730039265),
        bytes_3(730039265),
        _STREAM_B,
        now + 0.1,
        per_peer=True,
    )


def test_ingress_collides_when_obp_bridge_tx_leg_active() -> None:
    """OBP bridge TX stamp on STATUS[slot] must block a new HBP ingress stream."""
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "TX_RFS": bytes_3(730039256),
        "TX_STREAM_ID": _STREAM_A,
    }
    assert hbp_ingress_new_stream_collision(
        slot,
        bytes_4(730039267),
        bytes_3(730039267),
        _STREAM_B,
        now + 0.1,
        per_peer=True,
    )


def test_ingress_downlink_session_blocks_tx_on_same_tg() -> None:
    peer_slots = {
        1: {"stream_id": _STREAM_A, "tgid": 730500, "time": 1_000_000.0},
    }
    assert hbp_ingress_downlink_session_blocks_tx(1, bytes_3(730500), peer_slots)
    assert not hbp_ingress_downlink_session_blocks_tx(1, bytes_3(730502), peer_slots)


def test_ingress_downlink_session_allows_tx_after_own_ingress() -> None:
    peer_slots = {
        2: {"stream_id": _STREAM_A, "tgid": 730502, "time": 1_000_000.0, "ingress": True},
    }
    assert not hbp_ingress_downlink_session_blocks_tx(2, bytes_3(730502), peer_slots)


def test_master_repeat_denied_for_colliding_stream() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    slot["RX_RFS"] = bytes_3(730039264)
    slot["RX_PEER"] = bytes_4(730039264)
    assert not hbp_master_ingress_repeat_allowed(
        slot,
        bytes_4(730039265),
        bytes_3(730039265),
        _TG_A,
        _STREAM_B,
        now + 0.1,
    )


def test_master_repeat_allowed_for_slot_owner_continuation() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    slot["RX_PEER"] = bytes_4(730039264)
    assert hbp_master_ingress_repeat_allowed(
        slot,
        bytes_4(730039264),
        bytes_3(730039264),
        _TG_A,
        _STREAM_A,
        now + 0.1,
    )


def test_group_voice_tg_collision_rejects_second_hbp_stream() -> None:
    now = 1_000_000.0
    master_status = {
        2: _active_rx_slot(tgid=_TG_A, stream_id=_STREAM_A, t=now),
    }
    master_status[2]["RX_RFS"] = bytes_3(730039264)
    protocols = {"M1": type("P", (), {"STATUS": master_status})()}
    systems = {"M1": {"MODE": "MASTER"}}
    assert group_voice_tg_ingress_collision(
        protocols, systems, _TG_A, _STREAM_B, bytes_3(730039265), now + 0.1,
    )


def test_group_voice_tg_collision_rejects_obp_while_hbp_active() -> None:
    now = 1_000_000.0
    master_status = {1: _active_rx_slot(tgid=bytes_3(730500), stream_id=_STREAM_A, t=now)}
    master_status[1]["RX_RFS"] = bytes_3(730039266)
    obp_status: dict[bytes, dict] = {}
    protocols = {
        "M1": type("P", (), {"STATUS": master_status})(),
        "OBP": type("P", (), {"STATUS": obp_status})(),
    }
    systems = {"M1": {"MODE": "MASTER"}, "OBP": {"MODE": "OPENBRIDGE"}}
    assert group_voice_tg_ingress_collision(
        protocols, systems, bytes_3(730500), _STREAM_B, bytes_3(730039256), now + 0.1,
    )


def test_group_voice_tg_collision_across_hbp_slots() -> None:
    """Active TG on slot 1 must block a new stream on slot 2 (dual-slot OBP peers)."""
    now = 1_000_000.0
    master_status = {
        1: _active_rx_slot(tgid=bytes_3(730500), stream_id=_STREAM_A, t=now),
    }
    master_status[1]["RX_RFS"] = bytes_3(730039266)
    protocols = {"M1": type("P", (), {"STATUS": master_status})()}
    systems = {"M1": {"MODE": "MASTER"}}
    assert group_voice_tg_ingress_collision(
        protocols, systems, bytes_3(730500), _STREAM_B, bytes_3(730039267), now + 0.1,
    )


def test_peer_hotspot_voice_slot_busy_blocks_downlink_during_local_ingress() -> None:
    """Rejected ingress still marks local TX — downlink must not arrive on that slot."""
    now = 1_000_000.0
    hs = bytes_4(730039265)
    slot = _active_rx_slot()
    slot["RX_PEER"] = bytes_4(730039264)
    peer_slots = {
        2: {"stream_id": _STREAM_B, "tgid": 730502, "time": now, "ingress": True},
    }
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_A, _TG_A, slot, peer_slots, None, now + 0.05, 5.0,
    )


def test_per_peer_scope_ignores_other_hotspot_busy_slot() -> None:
    """Inject-only: peer B must not inherit slot contention from peer A."""
    now = 1_000_000.0
    peer_a = bytes_4(352000133)
    peer_b = bytes_4(714002301)
    slot = _active_rx_slot()
    slot["RX_PEER"] = peer_a
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_b, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=True, voice_slot=2,
    ) is False
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_a, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=True, voice_slot=2,
    ) is True


def test_bridge_tx_stamp_same_stream_allows_obp_downlink() -> None:
    """OBP bridge TX stamp (TX_PEER not in PEERS) must not block same-stream downlink."""
    now = 1_000_000.0
    hs = bytes_4(714002301)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": _STREAM_B,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "TX_TGID": _TG_B,
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES"}}
    assert not hbp_slot_blocks_group_voice_for_peer(
        slot, hs, _TG_B, _STREAM_B, now + 0.05, 0.0, per_peer=True, peers=peers,
        voice_slot=2,
    )


def test_per_peer_obp_tx_stamp_blocked_when_other_stream_active() -> None:
    """OBP TX stamp must not override an active per-peer session on another stream."""
    now = 1_000_000.0
    peer = bytes_4(714002301)
    slot = _active_rx_slot()
    slot["RX_PEER"] = peer
    slot["TX_STREAM_ID"] = _STREAM_B
    slot["TX_PEER"] = bytes_4(73010)
    slot["TX_TYPE"] = HBPF_SLT_VHEAD
    slot["TX_TIME"] = now + 0.05
    peers = {peer: {"CONNECTION": "YES"}}
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=True, peers=peers,
        peer_slots={2: {"stream_id": _STREAM_A, "tgid": 7144, "time": now}},
        voice_slot=2,
    ) is True


def test_lab_witness_many_static_tgs_blocks_second_tg_on_slot() -> None:
    """Full-table lab witness (>6 static TGs) still obeys one-QSO-per-RF-slot."""
    now = 1_000_000.0
    witness_id = bytes_4(730039257)
    tg_list = ",".join(str(730500 + i) for i in range(13))
    witness = {"OPTIONS": f"TS2={tg_list};SINGLE=1;".encode()}
    peer_slots = {
        2: {"stream_id": _STREAM_A, "tgid": 730500, "time": now - 1.0},
    }
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}
    assert peer_hotspot_voice_slot_busy(
        witness_id,
        2,
        _STREAM_B,
        _TG_B,
        slot,
        peer_slots,
        None,
        now,
        5.0,
        peer=witness,
        sys_cfg={"GROUP_HANGTIME": 5.0},
    )


def test_same_stream_vterm_not_blocked_by_peer_slot_busy() -> None:
    """VTERM for the active stream must reach the hotspot to clear peer_voice_slots."""
    from adn_server.application.routing.downlink import (
        DownlinkContext,
        peer_slot_blocks_downlink,
        touch_peer_voice_slot,
    )

    sys_cfg = {"GROUP_HANGTIME": 5.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    hs = bytes_4(714002301)
    peer = {"OPTIONS": b"TS2=7141,71442;SINGLE=1;"}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={hs: peer},
        status={1: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}, 2: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}},
        connected_count=2,
    )
    now = 1_000_000.0
    stream = bytes_4(0x11111111)
    touch_peer_voice_slot(ctx, hs, 2, stream, bytes_3(7141), pkt_time=now)
    vterm = b"".join([
        b"DMRD", b"\x00", bytes_3(100), bytes_3(7141), b"\x00\x00\x00\x00",
        bytes([0x80 | (HBPF_DATA_SYNC << 4) | HBPF_SLT_VTERM]),
        stream,
    ] + [b"\x00"] * 33)
    assert not peer_slot_blocks_downlink(ctx, hs, peer, vterm, pkt_time=now + 0.5)


def test_peer_slot_session_blocks_other_tg_after_burst_gap() -> None:
    """Per-peer session must survive DMR inter-burst gaps (> STREAM_TO)."""
    now = 1_000_000.0
    hs = bytes_4(714002301)
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}
    peer_slots = {
        2: {"stream_id": _STREAM_A, "tgid": 7141, "time": now - STREAM_TO - 2.0},
    }
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, _TG_B, slot, peer_slots, None, now, 5.0,
    )
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, hs, _TG_B, _STREAM_B, now, 5.0, per_peer=True,
        peer_slots=peer_slots, voice_slot=2,
    )


def test_obp_tx_stamp_does_not_override_peer_hangtime() -> None:
    """GROUP_HANGTIME from hotspot TX must block OBP downlink even with matching TX stamp."""
    now = 1_000_000.0
    hs = bytes_4(730039101)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": _STREAM_B,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "TX_TGID": bytes_3(7305),
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES"}}
    hang = (7306, now - 1.0)
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, bytes_3(7305), slot, None, hang, now + 2.0, 10.0, peers=peers,
    )
    assert peer_hotspot_voice_slot_busy(
        hs, 2, bytes_4(0x99999999), bytes_3(7305), slot, None, hang, now + 2.0, 10.0, peers=peers,
    )
    assert not peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, bytes_3(7306), slot, None, hang, now + 2.0, 10.0, peers=peers,
    )


def test_downlink_track_preserves_ingress_tx_flag() -> None:
    """Delivered downlink DMRD must not clear ingress while hotspot is still TX."""
    from adn_server.application.routing.downlink import (
        DownlinkContext,
        peer_slot_blocks_downlink,
        touch_peer_voice_slot,
        track_peer_group_dmrd,
    )

    sys_cfg = {"GROUP_HANGTIME": 5.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"SYSTEMS": {"MASTER-A": sys_cfg}}
    peer_id = bytes_4(730039264)
    peer = {"OPTIONS": b"TS2=730502;SINGLE=1;"}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={peer_id: peer},
        status={1: {}, 2: {}},
        connected_count=2,
    )
    now = 1_000_000.0
    stream_a = bytes_4(0x11111111)
    stream_b = bytes_4(0x22222222)
    touch_peer_voice_slot(
        ctx, peer_id, 2, stream_a, bytes_3(730502), pkt_time=now, ingress=True,
    )
    foreign_vhead = b"".join([
        b"DMRD", b"\x00", bytes_3(730039265), bytes_3(730502), b"\x00\x00\x00\x00",
        bytes([0x80 | (HBPF_DATA_SYNC << 4) | HBPF_SLT_VHEAD]), stream_b,
    ] + [b"\x00"] * 33)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, foreign_vhead, pkt_time=now + 2.1)
    track_peer_group_dmrd(ctx, peer_id, foreign_vhead, peer, pkt_time=now + 2)
    assert ctx.peer_voice_slots[peer_id][2].get("ingress") is True


def test_downlink_vterm_does_not_reset_transmit_hangtime() -> None:
    """Delivered OBP VTERM must not replace ingress GROUP_HANGTIME ownership."""
    from adn_server.application.routing.downlink import (
        DownlinkContext,
        end_peer_voice_slot,
        peer_slot_blocks_downlink,
        touch_peer_voice_slot,
    )

    sys_cfg = {"GROUP_HANGTIME": 10.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={},
        status={1: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}, 2: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}},
        connected_count=1,
    )
    peer_id = bytes_4(730039101)
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    ctx.peers[peer_id] = peer
    now = 3_000_000.0
    touch_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7306), pkt_time=now)
    end_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7306), pkt_time=now + 1)
    assert ctx.peer_voice_hangtime[peer_id][2] == (7306, now + 1)
    end_peer_voice_slot(
        ctx, peer_id, 2, bytes_4(0x2222), bytes_3(7305), pkt_time=now + 2, apply_hangtime=False,
    )
    assert ctx.peer_voice_hangtime[peer_id][2] == (7306, now + 1)
    foreign = b"".join([
        b"DMRD", b"\x00", bytes_3(100), bytes_3(7305), b"\x00\x00\x00\x00",
        bytes([0x80 | (HBPF_DATA_SYNC << 4) | HBPF_SLT_VHEAD]), bytes_4(0x3333),
    ] + [b"\x00"] * 33)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, foreign, pkt_time=now + 3)


def test_obp_tx_stamp_does_not_bypass_fresh_chile_downlink_session() -> None:
    """OBP TX stamp for Panama VTERM must not flash over active Chile listen (714002301 lab)."""
    now = 1_000_000.0
    hs = bytes_4(714002301)
    chile_stream = bytes_4(0x11111111)
    panama_stream = bytes_4(0x22222222)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": panama_stream,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES", "OPTIONS": b"TS2=7141,71442;"}}
    peer_slots = {
        2: {"stream_id": chile_stream, "tgid": 7141, "time": now - 0.1},
    }
    assert peer_hotspot_voice_slot_busy(
        hs, 2, panama_stream, bytes_3(71442), slot, peer_slots, None, now, 10.0, peers=peers,
    )


def test_obp_bridge_tx_blocked_when_other_stream_session_active() -> None:
    """Active per-peer session on another stream blocks OBP bridged downlink (one QSO per slot)."""
    now = 1_000_000.0
    hs = bytes_4(0x2B83833D)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": _STREAM_B,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES"}}
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, _TG_B, slot,
        {2: {"stream_id": _STREAM_A, "tgid": 7305, "time": now - 5.0}},
        None, now, 5.0, peers=peers,
    )


def test_bridge_tx_peer_does_not_clear_hotspot_contention() -> None:
    """Bridge TX_PEER=73010 must not disable per-hotspot slot busy checks."""
    now = 1_000_000.0
    hs = bytes_4(714002301)
    slot = _active_rx_slot(stream_id=_STREAM_A)
    slot["TX_PEER"] = bytes_4(73010)
    slot["TX_STREAM_ID"] = _STREAM_A
    slot["TX_TYPE"] = HBPF_SLT_VHEAD
    slot["TX_TIME"] = now
    peers = {hs: {"CONNECTION": "YES"}}
    assert slot_status_hotspot_owner(slot, peers) is None
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, _TG_B, slot,
        {2: {"stream_id": _STREAM_A, "tgid": 7144, "time": now}},
        None, now + 0.05, 5.0,
    )


def test_peer_hotspot_hangtime_blocks_other_tg() -> None:
    now = 1_000_000.0
    hs = bytes_4(714002301)
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}
    assert peer_hotspot_voice_slot_busy(
        hs, 2, _STREAM_B, _TG_B, slot, None, (7144, now), now + 2.0, 5.0,
    )


def test_single0_ingress_tx_blocks_other_static_tg_on_slot() -> None:
    """SINGLE=0: local TX on one TG blocks any other downlink on the same RF slot."""
    now = 1_000_000.0
    hs = bytes_4(730039253)
    peer = {"OPTIONS": b"TS2=730507,730508;SINGLE=0;"}
    sys_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}
    peer_slots = {
        2: {
            "stream_id": bytes_4(0x11111111),
            "tgid": 730507,
            "time": now,
            "ingress": True,
        },
    }
    assert peer_hotspot_voice_slot_busy(
        hs,
        2,
        bytes_4(0x22222222),
        bytes_3(730508),
        slot,
        peer_slots,
        None,
        now + 0.1,
        0.0,
        peer=peer,
        sys_cfg=sys_cfg,
    )


def test_lab_witness_nine_static_tgs_blocks_second_tg_on_slot() -> None:
    """Lab witness with >6 static TGs is hard-locked to one QSO per RF slot."""
    now = 1_000_000.0
    hs = bytes_4(730039257)
    peer = {
        "OPTIONS": b"TS2=730500,730501,730502,730503,730504,730505,730506,730507,730508;",
    }
    sys_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}
    slot = {
        "RX_PEER": bytes_4(730039253),
        "RX_TGID": bytes_3(730507),
        "RX_STREAM_ID": bytes_4(0x11111111),
        "RX_TIME": now,
        "RX_TYPE": HBPF_SLT_VHEAD,
    }
    peer_slots = {
        2: {"stream_id": bytes_4(0x11111111), "tgid": 730507, "time": now, "ingress": False},
    }
    assert peer_hotspot_voice_slot_busy(
        hs,
        2,
        bytes_4(0x22222222),
        bytes_3(730508),
        slot,
        peer_slots,
        None,
        now + 0.1,
        0.0,
        peer=peer,
        sys_cfg=sys_cfg,
    )


def test_ingress_tx_blocks_same_stream_obp_echo() -> None:
    """OBP loopback with same stream_id must not downlink while hotspot is still TX."""
    now = 1_000_000.0
    hs = bytes_4(730039264)
    stream = bytes_4(0x22222222)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": stream,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES", "OPTIONS": b"TS2=730502;SINGLE=1;"}}
    peer_slots = {
        2: {
            "stream_id": stream,
            "tgid": 730502,
            "time": now,
            "ingress": True,
        },
    }
    assert peer_hotspot_voice_slot_busy(
        hs, 2, stream, bytes_3(730502), slot, peer_slots, None, now, 5.0, peers=peers,
    )


def test_ingress_tx_blocks_same_tg_foreign_stream_despite_bridge_stamp() -> None:
    """Local RF TX must block downlink even when OBP bridge TX stamp matches incoming."""
    now = 1_000_000.0
    hs = bytes_4(730039101)
    slot = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": bytes_4(0x22222222),
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    peers = {hs: {"CONNECTION": "YES", "OPTIONS": b"TS2=730,7305;"}}
    peer_slots = {
        2: {
            "stream_id": bytes_4(0x11111111),
            "tgid": 7306,
            "time": now,
            "ingress": True,
        },
    }
    assert peer_hotspot_voice_slot_busy(
        hs, 2, bytes_4(0x22222222), bytes_3(7306), slot, peer_slots, None, now, 5.0, peers=peers,
    )


def test_single1_listen_blocks_other_static_tg_during_downlink() -> None:
    """Lab J39JQ: SINGLE=1 listening on 730502 must not RX 730500 on same slot."""
    now = 1_000_000.0
    hs = bytes_4(730039270)
    peer = {"OPTIONS": b"TS2=730500,730508;SINGLE=1;TIMER=5;"}
    sys_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}
    slot = {
        "RX_PEER": bytes_4(730039269),
        "RX_TGID": bytes_3(730500),
        "RX_STREAM_ID": bytes_4(0x11111111),
        "RX_TIME": now,
        "RX_TYPE": HBPF_SLT_VHEAD,
    }
    peer_slots = {
        2: {"stream_id": bytes_4(0x22222222), "tgid": 730502, "time": now, "ingress": False},
    }
    assert peer_hotspot_voice_slot_busy(
        hs,
        2,
        bytes_4(0x11111111),
        bytes_3(730500),
        slot,
        peer_slots,
        None,
        now + 0.1,
        5.0,
        peer=peer,
        sys_cfg=sys_cfg,
    )


def test_single1_ua_blocks_same_tg_foreign_tx() -> None:
    """SINGLE=1 UA on 730502: block HP3ICC downlink on same TG while slot is busy."""
    now = 1_000_000.0
    listener = bytes_4(730039270)
    tx_peer = bytes_4(730039269)
    peer = {"OPTIONS": b"TS2=730500,730508;SINGLE=1;TIMER=5;"}
    sys_cfg = {"SINGLE_MODE": False, "DEFAULT_UA_TIMER": 10}
    register_peer_ua_session(peer, listener, 2, 730502, sys_cfg, now=now)
    slot = {
        "RX_PEER": tx_peer,
        "RX_TGID": bytes_3(730502),
        "RX_STREAM_ID": bytes_4(0x11111111),
        "RX_TIME": now,
        "RX_TYPE": HBPF_SLT_VHEAD,
    }
    assert peer_hotspot_voice_slot_busy(
        listener,
        2,
        bytes_4(0x22222222),
        bytes_3(730502),
        slot,
        None,
        None,
        now + 0.1,
        5.0,
        peer=peer,
        sys_cfg=sys_cfg,
    )


def test_global_scope_still_blocks_any_peer_on_busy_slot() -> None:
    now = 1_000_000.0
    peer_b = bytes_4(714002301)
    slot = _active_rx_slot()
    slot["RX_PEER"] = bytes_4(352000133)
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_b, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=False,
    ) is True

    now = 1_000_000.0
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM, "RX_TIME": 0.0, "TX_TIME": 0.0}
    assert not hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now, 5.0)


def test_group_hangtime_blocks_other_tg_after_vterm() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": _TG_A,
        "RX_TIME": now,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
    }
    assert slot_in_group_hangtime(slot, _TG_B, now + 2.0, 5.0)
    assert not slot_in_group_hangtime(slot, _TG_A, now + 2.0, 5.0)
    assert not slot_in_group_hangtime(slot, _TG_B, now + 6.0, 5.0)


def test_group_hangtime_zero_allows_other_tg_after_vterm() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": _TG_A,
        "RX_TIME": now,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
    }
    assert not slot_in_group_hangtime(slot, _TG_B, now + 1.0, 0.0)
    assert not hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 1.0, 0.0)


def test_active_tx_leg_blocks_other_stream() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
        "TX_STREAM_ID": _STREAM_A,
    }
    assert slot_has_active_voice(slot, now + 0.05)
    assert hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 0.05, 0.0)


def test_stream_timeout_ends_active_busy() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot(t=now - STREAM_TO - 0.01)
    assert not slot_has_active_voice(slot, now)


def test_foreign_vterm_dropped_while_listening_other_tg() -> None:
    """VTERM for a stream never delivered must not reach the hotspot."""
    from adn_server.application.routing.downlink import (
        DownlinkContext,
        peer_slot_blocks_downlink,
        touch_peer_voice_slot,
    )

    sys_cfg = {"GROUP_HANGTIME": 5.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    hs = bytes_4(714002301)
    peer = {"OPTIONS": b"TS2=7141,71442;"}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={hs: peer},
        status={1: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}, 2: {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM}},
        connected_count=2,
    )
    now = 1_000_000.0
    chile_stream = bytes_4(0x11111111)
    panama_stream = bytes_4(0x22222222)
    touch_peer_voice_slot(ctx, hs, 2, chile_stream, bytes_3(7141), pkt_time=now)
    panama_vterm = b"".join([
        b"DMRD", b"\x00", bytes_3(100), bytes_3(71442), b"\x00\x00\x00\x00",
        bytes([0x80 | (HBPF_DATA_SYNC << 4) | HBPF_SLT_VTERM]),
        panama_stream,
    ] + [b"\x00"] * 33)
    assert peer_slot_blocks_downlink(ctx, hs, peer, panama_vterm, pkt_time=now + 0.5)


def test_global_slot_blocks_foreign_vterm_during_active_rx() -> None:
    """Bridge TX stamp must not let foreign VTERM through during active RX."""
    now = 1_000_000.0
    chile_stream = bytes_4(0x11111111)
    panama_stream = bytes_4(0x22222222)
    slot = {
        "RX_PEER": bytes_4(714002301),
        "RX_STREAM_ID": chile_stream,
        "RX_TYPE": HBPF_SLT_VHEAD,
        "RX_TIME": now,
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": panama_stream,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
    }
    assert hbp_slot_blocks_group_voice(
        slot, bytes_3(71442), panama_stream, now + 0.1, 0.0, is_vterm=True,
    )
    assert not hbp_slot_blocks_group_voice(slot, _TG_A, chile_stream, now + 0.1, 0.0)
