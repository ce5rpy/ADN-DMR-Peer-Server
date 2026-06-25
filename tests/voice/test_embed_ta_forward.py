"""Talker Alias embedded LC alternation on voice bursts."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_bridge
from tests.harness.scenarios import talker_alias_config


def test_talker_alias_embed_state_prepared_on_bridge_vhead() -> None:
    bridges = active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), bridges=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0xABABABAB)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))

    ts_st = scenario.protocols["MASTER-B"].STATUS.get(2, {})
    assert "TX_TA_EMB" in ts_st
    assert ts_st.get("TX_TA_ON") is False
    assert ts_st.get("TX_TA_PHASE") == 0


def test_talker_alias_embed_cleared_on_vterm() -> None:
    bridges = active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), bridges=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0xCDCDCDCD)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_term_spec(base, seq=99),
    )

    ts_st = scenario.protocols["MASTER-B"].STATUS.get(2, {})
    assert "TX_TA_EMB" not in ts_st
    assert "TX_TA_ON" not in ts_st
