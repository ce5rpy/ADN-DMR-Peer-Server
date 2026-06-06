"""OBP rate limit regressions."""

from __future__ import annotations

from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_bridge,
    add_openbridge_system,
    patch_bridge_wall_time,
)


def test_obp_rate_limit_uses_start_epoch_not_elapsed() -> None:
    """Regression: OBP must not RATE DROP at normal cadence (packets/START)."""
    bridges = active_bridge(52090, (("OBP-CL", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, bridges=bridges)

    with patch_bridge_wall_time(scenario.clock):
        base = PacketSpec(dst_id=52090, stream_id=0x11223344, slot=1)
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        accepted = 0
        for seq in range(1, 25):
            ok = scenario.inject_obp(
                "OBP-CL",
                DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            )
            if ok is not False:
                accepted += 1
        assert accepted >= 20
