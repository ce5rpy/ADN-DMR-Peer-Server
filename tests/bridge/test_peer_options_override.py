"""Peer RPTO OPTIONS override YAML runtime flags (inject-only proxy)."""

from __future__ import annotations

import pytest

from adn_server.application.subscription.router import SubscriptionRouter
from adn_server.domain.value_objects import TgId
from adn_server.domain.voice_routing import VoiceIngress
from tests.harness.deterministic import (
    DeterministicScenario,
    FakeHbpProtocol,
    PacketSpec,
    active_bridge,
)

from adn_server.domain import bytes_3, bytes_4


def _proxy_system_scenario(
    *,
    single_mode_yaml: bool = False,
    use_subscription_router: bool = False,
) -> DeterministicScenario:
    config = DeterministicScenario().config
    config["GLOBAL"]["USE_SUBSCRIPTION_ROUTER"] = use_subscription_router
    sys_cfg = config["SYSTEMS"]["MASTER-A"]
    sys_cfg["SINGLE_MODE"] = single_mode_yaml
    sys_cfg["DEFAULT_UA_TIMER"] = 60
    sys_cfg.pop("OPTIONS", None)
    sys_cfg["TS1_STATIC"] = ""
    sys_cfg["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config, bridges={})
    scenario.bridge._get_protocols = lambda: scenario.protocols  # noqa: SLF001
    proto = scenario.protocols["MASTER-A"]
    assert isinstance(proto, FakeHbpProtocol)
    peer_id = bytes_4(1001)
    proto._peers = {
        peer_id: {
            "CONNECTION": "YES",
            "CALLSIGN": b"CE5RPY",
            "RADIO_ID": peer_id,
            "OPTIONS": b"TS2=730444,52090;SINGLE=1;TIMER=5;",
        }
    }
    return scenario


@pytest.mark.parametrize("use_subscription_router", [False, True])
def test_rpto_single_and_timer_override_yaml(use_subscription_router: bool) -> None:
    scenario = _proxy_system_scenario(
        single_mode_yaml=False,
        use_subscription_router=use_subscription_router,
    )

    scenario.bridge.options_config_for_system(
        "MASTER-A",
        peer_options=b"TS2=730444,52090;SINGLE=1;TIMER=5;",
    )

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["SINGLE_MODE"] is True
    assert scenario.bridge.get_bridges()["730444"][0]["TIMEOUT"] == 300.0
    assert scenario.bridge.get_bridges()["52090"][0]["TIMEOUT"] == 300.0


@pytest.mark.parametrize("use_subscription_router", [False, True])
def test_options_loop_reads_connected_peer_without_yaml_options(
    use_subscription_router: bool,
) -> None:
    scenario = _proxy_system_scenario(
        single_mode_yaml=False,
        use_subscription_router=use_subscription_router,
    )
    bridges = active_bridge(730444, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario.router.set_bridges(bridges)

    scenario.bridge.options_config_loop()

    assert scenario.config["SYSTEMS"]["MASTER-A"]["SINGLE_MODE"] is True


@pytest.mark.parametrize("use_subscription_router", [False, True])
def test_single_mode_deactivates_other_static_tg_after_rpto(
    use_subscription_router: bool,
) -> None:
    scenario = _proxy_system_scenario(
        single_mode_yaml=False,
        use_subscription_router=use_subscription_router,
    )
    bridges = {
        "730444": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": bytes_3(730444),
                "ACTIVE": True,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(730444)],
                "OFF": [],
                "RESET": [],
                "TIMER": 0.0,
            },
            {
                "SYSTEM": "MASTER-B",
                "TS": 2,
                "TGID": bytes_3(730444),
                "ACTIVE": True,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(730444)],
                "OFF": [],
                "RESET": [],
                "TIMER": 0.0,
            },
        ],
        "52090": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": bytes_3(52090),
                "ACTIVE": True,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(52090)],
                "OFF": [],
                "RESET": [],
                "TIMER": 0.0,
            },
            {
                "SYSTEM": "MASTER-B",
                "TS": 2,
                "TGID": bytes_3(52090),
                "ACTIVE": True,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(52090)],
                "OFF": [],
                "RESET": [],
                "TIMER": 0.0,
            },
        ],
    }
    scenario.router.set_bridges(bridges)
    scenario.bridge.options_config_for_system(
        "MASTER-A",
        peer_options=b"TS2=730444,52090;SINGLE=1;TIMER=5;",
    )

    scenario.bridge.apply_in_band_signalling("MASTER-A", 2, bytes_3(730444), pkt_time=3000.0)

    assert scenario.bridge.get_bridges()["730444"][0]["ACTIVE"] is True
    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is False

    if use_subscription_router:
        scenario.bridge._sync_subscription_store()
        legs = SubscriptionRouter(scenario.subscription_store).resolve(
            VoiceIngress(
                source_system="MASTER-B",
                slot=2,
                dst_tgid=TgId(52090),
            )
        )
        assert all(leg.target_system != "MASTER-A" for leg in legs)


def test_ua_bridge_creation_pushes_routing_snapshot() -> None:
    """Monitor UA chip needs an immediate routing_table push, not only the 52s rule_timer loop."""
    scenario = _proxy_system_scenario()
    scenario.config["REPORTS"]["REPORT"] = True
    sent: list[tuple[dict, bool]] = []

    class _Rec:
        def send_bridge(self, bridges, *, incremental: bool = False) -> None:
            sent.append((bridges, incremental))

        def send_bridge_event(self, _event: str) -> None:
            pass

    scenario.bridge._reporting = _Rec()  # noqa: SLF001

    base = PacketSpec(dst_id=7304, stream_id=0x22222222, slot=2, peer_id=1001)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))

    assert sent
    assert sent[-1][1] is True
    assert "7304" in sent[-1][0]


def test_ua_bridge_uses_transmitting_peer_timer_minutes() -> None:
    """First TX to unknown TG uses peer OPTIONS TIMER (minutes), not YAML DEFAULT_UA_TIMER."""
    scenario = _proxy_system_scenario()
    assert scenario.config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] == 60

    base = PacketSpec(dst_id=7304, stream_id=0x11111111, slot=2, peer_id=1001)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))

    bridges = scenario.bridge.get_bridges()
    assert "7304" in bridges
    legs = [e for e in bridges["7304"] if e["SYSTEM"] == "MASTER-A" and e["TS"] == 2]
    assert len(legs) == 1
    assert legs[0]["ACTIVE"] is True
    assert legs[0]["TIMEOUT"] == 300.0


def test_peer_timer_does_not_override_other_peer_static_tg_timeout() -> None:
    """Each hotspot TIMER applies only to that peer's static TGs (no max() across peers)."""
    config = DeterministicScenario().config
    config["GLOBAL"]["USE_SUBSCRIPTION_ROUTER"] = False
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 60
    scenario = DeterministicScenario(config=config, bridges={})
    scenario.bridge._get_protocols = lambda: scenario.protocols  # noqa: SLF001
    proto = scenario.protocols["MASTER-A"]
    assert isinstance(proto, FakeHbpProtocol)
    proto._peers = {
        bytes_4(1001): {
            "CONNECTION": "YES",
            "CALLSIGN": b"CA1ROG",
            "RADIO_ID": bytes_4(1001),
            "OPTIONS": b'TS2=730444;TIMER=300;',
        },
        bytes_4(1002): {
            "CONNECTION": "YES",
            "CALLSIGN": b"CE5RPY",
            "RADIO_ID": bytes_4(1002),
            "OPTIONS": b"TS2=214091;SINGLE=1;TIMER=5;",
        },
    }

    scenario.bridge.options_config_for_system("MASTER-A")

    bridges = scenario.bridge.get_bridges()
    assert bridges["730444"][0]["TIMEOUT"] == 300.0 * 60.0
    assert bridges["214091"][0]["TIMEOUT"] == 5.0 * 60.0

    scenario.bridge.options_config_for_system(
        "MASTER-A",
        peer_options=b"TS2=214091;SINGLE=1;TIMER=5;",
    )
    bridges = scenario.bridge.get_bridges()
    assert bridges["730444"][0]["TIMEOUT"] == 300.0 * 60.0
    assert bridges["214091"][0]["TIMEOUT"] == 5.0 * 60.0


def test_make_static_tg_preserves_single_mode_deactivation_on_options_refresh() -> None:
    """OPTIONS loop (make_static_tg) must not re-activate TGs turned off by SINGLE VTERM."""
    scenario = _proxy_system_scenario(single_mode_yaml=True)
    bridges = {
        "730444": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": bytes_3(730444),
                "ACTIVE": False,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(730444)],
                "OFF": [],
                "RESET": [],
                "TIMER": 9_999_999.0,
            }
        ],
        "7305": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": bytes_3(7305),
                "ACTIVE": True,
                "TIMEOUT": 300.0,
                "TO_TYPE": "OFF",
                "ON": [bytes_3(7305)],
                "OFF": [],
                "RESET": [],
                "TIMER": 9_999_998.0,
            }
        ],
    }
    scenario.router.set_bridges(bridges)

    scenario.bridge.make_static_tg(730444, 2, 5.0, "MASTER-A")
    scenario.bridge.make_static_tg(7305, 2, 5.0, "MASTER-A")

    assert scenario.bridge.get_bridges()["730444"][0]["ACTIVE"] is False
    assert scenario.bridge.get_bridges()["7305"][0]["ACTIVE"] is True
