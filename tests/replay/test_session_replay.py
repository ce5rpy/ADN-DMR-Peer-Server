"""JSONL session replay tests (V2-P0-007)."""

from __future__ import annotations

import pytest

from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_bridge, minimal_config
from tests.harness.session_replay import (
    FIXTURES_DIR,
    IngressEvent,
    SessionCapture,
    SessionExpect,
    SessionMeta,
    SessionReplayer,
    bridges_to_json,
    capture_enabled,
    load_session,
    replay_session,
)

_HBP_FIXTURE = FIXTURES_DIR / "hbp_group_voice_short.jsonl"


def test_load_session_parses_meta_and_ingress() -> None:
    session = load_session(_HBP_FIXTURE)
    assert session.meta.name == "hbp_group_voice_short"
    assert session.meta.apply_startup_bridges is True
    assert len(session.events) == 2
    assert session.meta.expect.forwards["MASTER-B"] == 2


@pytest.mark.behavior
def test_replay_hbp_group_voice_short_matches_golden() -> None:
    """Golden JSONL session: VHEAD + burst on MASTER-A forwards twice to MASTER-B."""
    replay_session(_HBP_FIXTURE)


@pytest.mark.behavior
def test_replay_matches_inline_harness() -> None:
    """Replay output equals hand-written DeterministicScenario inject sequence."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    bridges = active_bridge(52090, (("MASTER-A", 2), ("MASTER-B", 2)))

    inline = DeterministicScenario(config=config, bridges=bridges)
    inline.bridge.apply_startup_bridges()
    base = PacketSpec(dst_id=52090, stream_id=0x80808080, slot=2)
    inline.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    inline.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    replayed = SessionReplayer.from_path(_HBP_FIXTURE).run()
    assert len(replayed.capture.packets) == len(inline.capture.packets)
    assert replayed.capture.for_system("MASTER-B") == inline.capture.for_system("MASTER-B")


@pytest.mark.behavior
def test_capture_roundtrip(tmp_path) -> None:
    """SessionCapture writes JSONL that SessionReplayer can load."""
    bridges = bridges_to_json(active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2))))
    meta = SessionMeta(
        name="roundtrip",
        bridges=bridges,
        apply_startup_bridges=False,
        expect=SessionExpect(forwards={"MASTER-B": 1}, dst_id=91),
    )
    cap = SessionCapture(meta=meta)
    cap.add_ingress(
        IngressEvent(
            channel="hbp",
            system="MASTER-A",
            dt=0,
            packet="voice_head",
            base={"dst_id": 91, "stream_id": 0x01020304, "slot": 2},
        )
    )
    out = tmp_path / "roundtrip.jsonl"
    cap.write(out)

    scenario = SessionReplayer.from_path(out).run()
    SessionReplayer(load_session(out)).assert_expectations(scenario)


@pytest.mark.behavior
@pytest.mark.skipif(not capture_enabled(), reason="set CAPTURE=1 to write fixture under _capture/")
def test_capture_startup_voice_session() -> None:
    """Dev tap: CAPTURE=1 records a session JSONL under fixtures/sessions/_capture/."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    bridges = bridges_to_json(active_bridge(52090, (("MASTER-A", 2), ("MASTER-B", 2))))
    base = {"dst_id": 52090, "stream_id": 0x80808080, "slot": 2, "peer_id": 1001, "rf_src": 3120001}
    cap = SessionCapture(
        meta=SessionMeta(
            name="capture_startup_voice",
            config=config,
            bridges=bridges,
            apply_startup_bridges=True,
            expect=SessionExpect(forwards={"MASTER-B": 2}, dst_id=52090),
        )
    )
    cap.add_ingress(IngressEvent("hbp", "MASTER-A", 0, packet="voice_head", base=base))
    cap.add_ingress(
        IngressEvent("hbp", "MASTER-A", 0.06, packet="voice_burst", base=base, seq=1, dtype_vseq=1)
    )
    path = SessionCapture.capture_path("capture_startup_voice")
    cap.write(path)
    replay_session(path)
