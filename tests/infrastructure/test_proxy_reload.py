"""Proxy hot-reload keeps LISTEN_PORT and active sessions."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from adn_server.application.proxy import ProxyUseCases
from adn_server.infrastructure.config_reload import merge_top_level_config
from adn_server.domain.proxy import ClientEndpoint, ClientSlot
from adn_server.infrastructure.proxy.ip_blacklist import InMemoryProxyIpBlacklist
from adn_server.infrastructure.proxy.rpto_queue import InMemoryPendingRptoQueue
from adn_server.infrastructure.proxy.runtime import ProxyServiceState, apply_proxy_config_reload
from adn_server.infrastructure.proxy.slot_store import InMemoryProxySlotStore
from adn_server.infrastructure.proxy.udp_fanin import ProxyFanInProtocol


def _minimal_proxy_state() -> ProxyServiceState:
    use_cases = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=10,
        black_list=(),
        ip_blacklist=InMemoryProxyIpBlacklist(),
    )
    peer = b"\x00\x07\x06\xf5"  # 730039101
    use_cases._slots.bind(  # noqa: SLF001
        ClientSlot(
            peer_id=peer,
            client=ClientEndpoint(host="10.0.0.1", port=62031),
            report_slot=0,
        )
    )
    fanin = ProxyFanInProtocol(use_cases, master_sink=None)  # type: ignore[arg-type]
    return ProxyServiceState(
        target_system="SYSTEM",
        use_cases=use_cases,
        master_sink=None,  # type: ignore[arg-type]
        client_sender=None,  # type: ignore[arg-type]
        fanin=fanin,
        udp_port=object(),
        listen_port=62031,
        listen_ip="",
        _runtime={
            "listen_port": 62031,
            "listen_ip": "",
            "target_system": "SYSTEM",
            "timeout": 30.0,
            "debug": False,
            "client_info": True,
            "black_list": (),
            "ip_black_list": {},
            "max_peers": 10,
        },
    )


def test_apply_proxy_config_reload_keeps_sessions_and_updates_timeout() -> None:
    state = _minimal_proxy_state()
    config = {
        "PROXY": {
            "LISTEN_PORT": 62031,
            "TARGET_SYSTEM": "SYSTEM",
            "TIMEOUT": 45,
            "DEBUG": True,
        },
        "SYSTEMS": {"SYSTEM": {"MAX_PEERS": 20}},
    }
    log = logging.getLogger("test.proxy.reload")

    apply_proxy_config_reload(state, config, logger=log)

    assert len(state.use_cases.list_slots()) == 1
    assert state.udp_port is not None
    assert state._runtime["timeout"] == 45.0
    assert state.fanin.debug is True
    assert state.use_cases._max_peers == 20  # noqa: SLF001


def test_hot_reload_never_closes_udp_listener() -> None:
    """Regression: SIGHUP must not stopListening() on PROXY (EADDRINUSE / dropped sessions)."""
    state = _minimal_proxy_state()
    stop_mock = MagicMock(return_value=None)
    state.udp_port = MagicMock()
    state.udp_port.stopListening = stop_mock

    apply_proxy_config_reload(
        state,
        {
            "PROXY": {"LISTEN_PORT": 62031, "TARGET_SYSTEM": "SYSTEM", "TIMEOUT": 60},
            "SYSTEMS": {"SYSTEM": {"MAX_PEERS": 20}},
        },
        logger=logging.getLogger("test.proxy.reload"),
    )

    stop_mock.assert_not_called()
    assert len(state.use_cases.list_slots()) == 1


def test_merge_top_level_config_updates_proxy_section() -> None:
    live = {"GLOBAL": {}, "PROXY": {"TIMEOUT": 30, "LISTEN_PORT": 62031}}
    merge_top_level_config(live, {"PROXY": {"TIMEOUT": 45, "LISTEN_PORT": 62031}})
    assert live["PROXY"]["TIMEOUT"] == 45


def test_proxy_use_cases_apply_runtime_settings() -> None:
    uc = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=5,
        black_list=(1001,),
    )
    uc.apply_runtime_settings(max_peers=12, black_list=(2002, 3003))
    assert uc._max_peers == 12  # noqa: SLF001
    assert uc._black_list == frozenset({2002, 3003})  # noqa: SLF001
