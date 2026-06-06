"""Voice announcement anti-collision."""

from __future__ import annotations

from tests.harness.voice_helpers import make_voice_uc, voice_master_scenario

from adn_server.domain import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3


def test_build_targets_skips_busy_qso_slot() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_announcement_targets(91, "91", "ANN-TEST")

    assert targets == []
    assert busy == 1


def test_build_targets_includes_idle_slot() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VTERM
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_announcement_targets(91, "91", "ANN-TEST")

    assert busy == 0
    assert len(targets) == 1
    assert targets[0]["name"] == "MASTER-A"
    assert targets[0]["ts"] == 2


def test_broadcast_aborts_when_qso_starts_mid_transmission() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VTERM
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)
    targets = [{"sys_obj": master, "name": "MASTER-A", "slot": master.STATUS[2], "ts": 2}]
    pkts = {1: [b"\x00" * 55], 2: [b"\x00" * 55]}
    source = bytes_3(5000)
    dst = bytes_3(91)

    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    uc._announcement_send_broadcast(targets, pkts, 0, source, dst, 91, 0, "ANN-TEST", None)

    assert uc._announcement_running[0] is False
    assert master.sent == []
