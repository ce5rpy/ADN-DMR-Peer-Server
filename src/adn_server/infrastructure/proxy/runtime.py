# ADN DMR Peer Server - infrastructure proxy runtime
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""Wire integrated hotspot proxy at startup (composition root wiring)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from twisted.internet import reactor
from twisted.internet.interfaces import IDelayedCall

from adn_server.application.ports import ProxyClientSender, ProxyMasterSink
from adn_server.application.proxy import ProxyUseCases
from adn_server.domain.value_objects import int_id
from adn_server.infrastructure.proxy.config import proxy_settings
from adn_server.infrastructure.proxy.hbp_adapters import (
    FanInClientSender,
    HbpMasterPeerRegistry,
    InProcessHbpSink,
)
from adn_server.infrastructure.proxy.ip_blacklist import InMemoryProxyIpBlacklist
from adn_server.infrastructure.proxy.reply_transport import ProxyReplyTransport
from adn_server.infrastructure.proxy.rpto_queue import InMemoryPendingRptoQueue
from adn_server.infrastructure.proxy.self_service_bridge import ProxySelfServiceBridge
from adn_server.infrastructure.proxy.self_service_config import self_service_settings
from adn_server.infrastructure.proxy.session_executor import apply_session_teardown
from adn_server.infrastructure.proxy.slot_store import InMemoryProxySlotStore
from adn_server.infrastructure.proxy.udp_fanin import ProxyFanInProtocol, listen_proxy_fanin


def _proxy_runtime_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    settings = proxy_settings(config)
    target = settings["target_system"]
    max_peers = int(config.get("SYSTEMS", {}).get(target, {}).get("MAX_PEERS", 1))
    return {**settings, "max_peers": max_peers}


@dataclass
class ProxyServiceState:
    """Live proxy handles (for shutdown / reload)."""

    target_system: str
    use_cases: ProxyUseCases
    master_sink: ProxyMasterSink
    client_sender: ProxyClientSender
    fanin: ProxyFanInProtocol
    udp_port: Any
    listen_port: int = 62031
    listen_ip: str = ""
    _timers: dict[bytes, IDelayedCall] = field(default_factory=dict)
    _runtime: dict[str, Any] = field(default_factory=dict)
    self_service: ProxySelfServiceBridge | None = None

    def stop(self) -> Any:
        """Stop timers and UDP listener. Returns Twisted Deferred when a port was bound."""
        if self.self_service is not None:
            self.self_service.stop_loops()
            self.self_service = None
        for call in self._timers.values():
            if call.active():
                call.cancel()
        self._timers.clear()
        if self.udp_port is None:
            return None
        port = self.udp_port
        self.udp_port = None
        return port.stopListening()


def apply_proxy_config_reload(
    state: ProxyServiceState,
    config: dict[str, Any],
    *,
    logger: logging.Logger,
) -> None:
    """Hot-apply PROXY settings on SIGHUP without closing LISTEN_PORT or dropping sessions."""
    incoming = _proxy_runtime_snapshot(config)
    bind_changed = (
        state.listen_port != incoming["listen_port"]
        or state.listen_ip != incoming["listen_ip"]
    )
    target_changed = state.target_system != incoming["target_system"]
    state._runtime.update(incoming)
    state.use_cases.apply_runtime_settings(
        max_peers=incoming["max_peers"],
        black_list=incoming["black_list"],
    )
    ip_bl = state.use_cases._ip_blacklist  # noqa: SLF001
    if isinstance(ip_bl, InMemoryProxyIpBlacklist):
        ip_bl.merge_static_entries(incoming["ip_black_list"])
    state.fanin.debug = bool(incoming["debug"])
    if bind_changed:
        logger.warning(
            "(CONFIG-RELOAD) PROXY bind change ignored at runtime "
            "(still listening on %s:%s); restart adn-server to apply %s:%s",
            state.listen_ip or "*",
            state.listen_port,
            incoming["listen_ip"] or "*",
            incoming["listen_port"],
        )
    if target_changed:
        logger.warning(
            "(CONFIG-RELOAD) PROXY TARGET_SYSTEM change ignored at runtime "
            "(still injecting into %s); restart adn-server to apply %s",
            state.target_system,
            incoming["target_system"],
        )
    logger.debug(
        "(CONFIG-RELOAD) proxy settings applied (%s active session(s), port kept open)",
        len(state.use_cases.list_slots()),
    )


def _build_self_service(
    config: dict[str, Any],
    use_cases: ProxyUseCases,
    master_sink: InProcessHbpSink,
    client_sender: FanInClientSender,
    *,
    logger: logging.Logger,
    mysql_pool: Any | None = None,
    dynamic_tg_uc: Any | None = None,
    purge_peer_dynamic: Callable[[bytes, str], bool] | None = None,
) -> ProxySelfServiceBridge | None:
    ss = self_service_settings(config)
    if not ss["enabled"]:
        return None
    try:
        from adn_server.infrastructure.proxy.persistence import ProxySelfServiceRepository
        if mysql_pool is None:
            from adn_server.infrastructure.persistence.database_config import database_settings
            from adn_server.infrastructure.proxy.persistence import create_pool
            db = database_settings(config)
            mysql_pool = create_pool(
                db["db_server"],
                db["db_username"],
                db["db_password"],
                db["db_name"],
                db["db_port"],
            )
    except ImportError as err:
        raise RuntimeError(
            "(SELF_SERVICE) USE_SELFSERVICE requires mysqlclient "
            "(pip install mysqlclient)"
        ) from err
    store = ProxySelfServiceRepository(mysql_pool)
    bridge = ProxySelfServiceBridge(
        store,
        use_cases,
        master_sink,
        client_sender,
        pbkdf2_salt=ss["pbkdf2_salt"],
        pbkdf2_iterations=ss["pbkdf2_iterations"],
        logger=logger,
        dynamic_tg_uc=dynamic_tg_uc,
        purge_peer_dynamic=purge_peer_dynamic,
    )
    return bridge


def start_proxy_service(
    config: dict[str, Any],
    protocols: dict[str, Any],
    *,
    logger: logging.Logger,
    mysql_pool: Any | None = None,
    dynamic_tg_uc: Any | None = None,
    purge_peer_dynamic: Callable[[bytes, str], bool] | None = None,
) -> ProxyServiceState:
    """Start LISTEN_PORT fan-in and inject into ``PROXY.TARGET_SYSTEM`` MASTER."""
    runtime = _proxy_runtime_snapshot(config)
    target = runtime["target_system"]
    target_proto = protocols.get(target)
    if target_proto is None:
        raise RuntimeError(f"(PROXY) TARGET_SYSTEM {target!r} has no HBP protocol instance")

    ip_blacklist = InMemoryProxyIpBlacklist(runtime["ip_black_list"])
    use_cases = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=runtime["max_peers"],
        black_list=runtime["black_list"],
        ip_blacklist=ip_blacklist,
    )
    master_sink = InProcessHbpSink(target_proto)
    peer_registry = HbpMasterPeerRegistry(target_proto)
    fanin = ProxyFanInProtocol(
        use_cases,
        master_sink,
        debug=runtime["debug"],
        logger=logger,
    )
    self_service_bridge: ProxySelfServiceBridge | None = None
    state = ProxyServiceState(
        target_system=target,
        use_cases=use_cases,
        master_sink=master_sink,
        client_sender=FanInClientSender(None),
        fanin=fanin,
        udp_port=None,
        listen_port=runtime["listen_port"],
        listen_ip=runtime["listen_ip"],
        _runtime=dict(runtime),
    )

    def _on_client_attached(peer_id: bytes, host: str, port: int, new_session: bool) -> None:
        rt = state._runtime
        if (
            new_session
            and rt["client_info"]
            and peer_id != b"\xff\xff\xff\xff"
        ):
            logger.info(
                "(PROXY) New client: ID:%s IP:%s Port:%s",
                str(int_id(peer_id)).rjust(9),
                host.rjust(15),
                port,
            )
        existing = state._timers.get(peer_id)
        if existing is not None and existing.active():
            existing.reset(rt["timeout"])
            return
        if existing is not None:
            existing.cancel()
        state._timers[peer_id] = reactor.callLater(rt["timeout"], _reap_session, peer_id)

    def _reap_session(peer_id: bytes) -> None:
        rt = state._runtime
        state._timers.pop(peer_id, None)
        teardown = use_cases.expire_session(peer_id)
        if teardown is None:
            return
        if rt["debug"]:
            logger.debug(
                "(PROXY) session timeout peer=%s client=%s:%s",
                int_id(peer_id),
                teardown.client.host,
                teardown.client.port,
            )
        if rt["client_info"] and peer_id != b"\xff\xff\xff\xff":
            logger.info(
                "(PROXY) Client: ID:%s IP:%s Port:%s Removed.",
                str(int_id(peer_id)).rjust(9),
                teardown.client.host.rjust(15),
                teardown.client.port,
            )
        if state.self_service is not None:
            state.self_service.on_session_expired(peer_id)
        apply_session_teardown(
            teardown,
            master_sink=master_sink,
            client_sender=state.client_sender,
            peer_registry=peer_registry,
        )

    def _handle_prbl(data: bytes, addr: tuple[str, int]) -> None:
        expire = use_cases.block_ip_from_prbl(data, addr[0])
        if state._runtime["client_info"]:
            logger.info("(PROXY) Add to blacklist: host %s expire %s", addr[0], expire)

    fanin._on_attached = _on_client_attached  # noqa: SLF001
    fanin_proto, udp_port = listen_proxy_fanin(
        reactor,
        runtime["listen_ip"],
        runtime["listen_port"],
        use_cases,
        master_sink,
        debug=runtime["debug"],
        logger=logger,
        protocol=fanin,
        config=config,
    )
    state.udp_port = udp_port
    state.client_sender = FanInClientSender(fanin_proto.transport)
    target_proto.transport = ProxyReplyTransport(fanin_proto.transport, prbl_handler=_handle_prbl)

    ss_settings = self_service_settings(config)
    if ss_settings["enabled"]:
        self_service_bridge = _build_self_service(
            config,
            use_cases,
            master_sink,
            state.client_sender,
            logger=logger,
            mysql_pool=mysql_pool,
            dynamic_tg_uc=dynamic_tg_uc,
            purge_peer_dynamic=purge_peer_dynamic,
        )
        if self_service_bridge is not None:
            fanin._self_service = self_service_bridge  # noqa: SLF001

    logger.info(
        "(PROXY) Hotspot fan-in on %s:%s → inject %s (MAX_PEERS=%s, TIMEOUT=%ss)",
        runtime["listen_ip"] or "*",
        runtime["listen_port"],
        target,
        runtime["max_peers"],
        runtime["timeout"],
    )
    if self_service_bridge is not None:
        store = self_service_bridge._store  # noqa: SLF001

        def _on_db_ok(ok: bool) -> None:
            if not ok:
                logger.error("(SELF_SERVICE) Database connection failed — self-service disabled")
                return
            self_service_bridge.start_loops()
            state.self_service = self_service_bridge
            logger.info("(SELF_SERVICE) Enabled (shared Clients table with adn-monitor)")

        store.test_db().addCallback(_on_db_ok)
    return state
