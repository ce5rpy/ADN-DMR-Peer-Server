"""In-band voice signalling on VTERM."""

from __future__ import annotations

import copy

from tests.harness.deterministic import DeterministicScenario, active_bridge
from tests.harness.voice_helpers import reflector_bridge_entry

from adn_server.domain import bytes_3


def _user_bridge(active: bool = True) -> dict:
    return active_bridge(52090, (("MASTER-A", 2),))


def test_reflector_bridge_ignored_when_vterm_not_on_tg9() -> None:
    bridges = _user_bridge()
    bridges.update(reflector_bridge_entry())
    scenario = DeterministicScenario(bridges=bridges)
    leg = scenario.bridge.get_bridges()["#310"][0]
    timer_before = leg["TIMER"]

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(52090), pkt_time=2000.0)

    assert scenario.bridge.get_bridges()["#310"][0]["TIMER"] == timer_before
    assert scenario.bridge.get_bridges()["#310"][0]["ACTIVE"] is True


def test_reflector_bridge_processes_vterm_on_tg9() -> None:
    bridges = _user_bridge()
    bridges.update(reflector_bridge_entry())
    scenario = DeterministicScenario(bridges=bridges)

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(9), pkt_time=2000.0)

    leg = scenario.bridge.get_bridges()["#310"][0]
    assert leg["ACTIVE"] is True
    assert leg["TIMER"] == 2000.0 + leg["TIMEOUT"]


def test_single_mode_deactivates_on_non_source_tg() -> None:
    bridges = _user_bridge()
    scenario = DeterministicScenario(bridges=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = True
    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is True

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(91), pkt_time=3000.0)

    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is False


def test_non_single_mode_keeps_bridge_on_arbitrary_vterm_tg() -> None:
    bridges = _user_bridge()
    scenario = DeterministicScenario(bridges=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = False

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(91), pkt_time=3000.0)

    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is True


def test_non_single_mode_deactivates_on_tg4000() -> None:
    bridges = copy.deepcopy(_user_bridge())
    scenario = DeterministicScenario(bridges=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = False

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(4000), pkt_time=3000.0)

    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is False
