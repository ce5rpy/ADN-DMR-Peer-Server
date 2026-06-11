"""In-band voice signalling on VTERM."""

from __future__ import annotations

import copy

from tests.harness.deterministic import DeterministicScenario, active_routing_table
from tests.harness.voice_helpers import reflector_routing_entry

from adn_server.domain import bytes_3


def _user_routing_table(active: bool = True) -> dict:
    return active_routing_table(52090, (("MASTER-A", 2),))


def test_reflector_bridge_ignored_when_vterm_not_on_tg9() -> None:
    bridges = _user_routing_table()
    bridges.update(reflector_routing_entry())
    scenario = DeterministicScenario(routing_table=bridges)
    leg = scenario.routing.routing_table_for_report()["#310"][0]
    timer_before = leg["TIMER"]

    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(52090), pkt_time=2000.0)

    assert scenario.routing.routing_table_for_report()["#310"][0]["TIMER"] == timer_before
    assert scenario.routing.routing_table_for_report()["#310"][0]["ACTIVE"] is True


def test_reflector_bridge_processes_vterm_on_tg9() -> None:
    bridges = _user_routing_table()
    bridges.update(reflector_routing_entry())
    scenario = DeterministicScenario(routing_table=bridges)

    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(9), pkt_time=2000.0)

    leg = scenario.routing.routing_table_for_report()["#310"][0]
    assert leg["ACTIVE"] is True
    assert leg["TIMER"] == 2000.0 + leg["TIMEOUT"]


def test_single_mode_deactivates_on_non_source_tg() -> None:
    bridges = _user_routing_table()
    scenario = DeterministicScenario(routing_table=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = True
    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is True

    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(91), pkt_time=3000.0)

    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is False


def test_non_single_mode_keeps_bridge_on_arbitrary_vterm_tg() -> None:
    bridges = _user_routing_table()
    scenario = DeterministicScenario(routing_table=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = False

    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(91), pkt_time=3000.0)

    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is True


def test_non_single_mode_deactivates_on_tg4000() -> None:
    bridges = copy.deepcopy(_user_routing_table())
    scenario = DeterministicScenario(routing_table=bridges)
    scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] = False

    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(4000), pkt_time=3000.0)

    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is False


def test_in_band_signalling_pushes_routing_snapshot() -> None:
    """Monitor UA chips need routing refresh after VTERM in-band mutates BRIDGES."""
    scenario = DeterministicScenario(routing_table=_user_routing_table())
    scenario.config["REPORTS"]["REPORT"] = True
    sent: list[bool] = []

    class _Rec:
        def send_routing_table(self, bridges, *, incremental: bool = False) -> None:
            sent.append(incremental)

        def send_routing_event(self, _event: str) -> None:
            pass

    scenario.routing._reporting = _Rec()  # noqa: SLF001
    scenario.routing.apply_in_band_signalling("MASTER-A", 2, bytes_3(52090), pkt_time=2000.0)

    assert sent == [True]
