"""Talker Alias bridge/repeat injection."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_bridge
from tests.harness.scenarios import talker_alias_config

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.talker_alias import DMRA_BLOCK_COUNT, DMRA_OPCODE


def test_talker_alias_inject_dmra_on_bridge_vhead() -> None:
    """Bridge forward sends DMRA blocks once per target stream on VHEAD."""
    bridges = active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), bridges=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0x90909090)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))

    assert len(scenario.dmra_capture) == 1
    dmra = scenario.dmra_capture[0]
    assert dmra.target_system == "MASTER-B"
    assert 1 <= len(dmra.packets) <= DMRA_BLOCK_COUNT
    assert all(p[:4] == DMRA_OPCODE for p in dmra.packets)
    payload = b"".join(p[8:15] for p in dmra.packets)
    assert b"CE5RPY" in payload


def test_talker_alias_vhead_sent_once_per_target_stream() -> None:
    bridges = active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), bridges=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0x91919191)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert len(scenario.dmra_capture) == 1


def test_talker_alias_local_repeat_excludes_source_peer() -> None:
    scenario = DeterministicScenario(
        config=talker_alias_config(),
        bridges=active_bridge(91, (("MASTER-A", 2),)),
    )
    stream_id = bytes_4(0x92929292)
    peer = bytes_4(1001)
    rf_src = bytes_3(3120001)

    scenario.bridge.send_talker_alias_local_repeat("MASTER-A", peer, rf_src, stream_id)

    assert len(scenario.dmra_capture) == 1
    assert scenario.dmra_capture[0].exclude_peer == peer
