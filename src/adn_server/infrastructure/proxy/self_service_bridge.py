"""Self-service hooks on integrated proxy (legacy adn-proxy DB + RPTO parity)."""

from __future__ import annotations

import logging
import struct
from hashlib import pbkdf2_hmac
from typing import Any

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.interfaces import IDelayedCall
from twisted.internet.task import LoopingCall

from adn_server.application.ports import (
    ProxyClientSender,
    ProxyMasterSink,
    ProxySelfServiceStore,
)
from adn_server.application.proxy import ProxyUseCases
from adn_server.domain.proxy import ClientEndpoint
from adn_server.domain.value_objects import int_id
from adn_server.infrastructure.hbp_constants import RPTACK, RPTC, RPTCL, RPTO


def _peer_id_from_db(value: Any) -> bytes | None:
    if isinstance(value, bytes) and len(value) == 4:
        return value
    if isinstance(value, int) and 0 <= value <= 0xFFFFFFFF:
        return struct.pack(">I", value)
    return None


class ProxySelfServiceBridge:
    """Mirror legacy proxy ``Clients`` writes and RPTO push loops on core fan-in."""

    def __init__(
        self,
        store: ProxySelfServiceStore,
        use_cases: ProxyUseCases,
        master_sink: ProxyMasterSink,
        client_sender: ProxyClientSender,
        *,
        pbkdf2_salt: str = "ADN",
        pbkdf2_iterations: int = 2000,
        logger: logging.Logger | None = None,
    ) -> None:
        self._store = store
        self._use_cases = use_cases
        self._master_sink = master_sink
        self._client_sender = client_sender
        self._pbkdf2_salt = pbkdf2_salt
        self._pbkdf2_iterations = pbkdf2_iterations
        self._log = logger or logging.getLogger(__name__)
        self._opt_timers: dict[bytes, IDelayedCall] = {}
        self._loop_calls: list[LoopingCall] = []

    def start_loops(self) -> None:
        """Legacy timers: send_opts 10s, lst_seen 120s, clean_tbl 3600s."""
        for interval, fn in (
            (10.0, self.send_opts),
            (120.0, self.lst_seen),
            (3600.0, self._clean_tbl),
        ):
            call = LoopingCall(fn)
            call.start(interval, now=False)
            self._loop_calls.append(call)
        self._log.info(
            "(SELF_SERVICE) DB options at login, send_opts every 10s, "
            "clean_tbl every 1h, lst_seen every 2min"
        )

    def stop_loops(self) -> None:
        for call in self._loop_calls:
            if call.running:
                call.stop()
        self._loop_calls.clear()
        for timer in self._opt_timers.values():
            if timer.active():
                timer.cancel()
        self._opt_timers.clear()

    def before_inject(
        self,
        data: bytes,
        addr: tuple[str, int],
        peer_id: bytes,
    ) -> bool:
        """Handle RPTC/RPTO DB side effects. Return True to skip master inject."""
        if len(data) < 4:
            return False
        command = data[:4]
        host, port = addr
        if command == RPTO:
            return self._handle_rpto(data, peer_id, host, port)
        if command == RPTC and len(data) >= 5 and data[:5] != RPTCL:
            self._handle_rptc(data, peer_id, host)
        return False

    def on_session_expired(self, peer_id: bytes) -> None:
        self._cancel_opt_timer(peer_id)
        self._store.updt_tbl("log_out", peer_id)

    def _handle_rptc(self, data: bytes, peer_id: bytes, host: str) -> None:
        if self._use_cases.resolve_client(peer_id) is None:
            return
        mode = data[97:98].decode("utf-8", errors="replace") if len(data) >= 98 else "4"
        callsign = data[8:16].rstrip().decode("utf-8", errors="replace")
        self._store.ins_conf(int_id(peer_id), peer_id, callsign, host, mode)
        self._cancel_opt_timer(peer_id)
        self._opt_timers[peer_id] = reactor.callLater(10, self._login_opt, peer_id)

    def _handle_rpto(
        self,
        data: bytes,
        peer_id: bytes,
        host: str,
        port: int,
    ) -> bool:
        if self._use_cases.resolve_client(peer_id) is None:
            return False
        if data[8:].upper().startswith(b"PASS=") and len(data) >= 13:
            psswd_raw = data[13:]
            if len(psswd_raw) >= 6:
                dk = pbkdf2_hmac(
                    "sha256",
                    psswd_raw,
                    self._pbkdf2_salt.encode("utf-8"),
                    self._pbkdf2_iterations,
                ).hex()
                self._store.updt_tbl("psswd", peer_id, psswd=dk)
                self._client_sender.send_to_client(
                    RPTACK + peer_id,
                    ClientEndpoint(host=host, port=port),
                )
                self._log.info("(SELF_SERVICE) Password stored for: %s", int_id(peer_id))
            return True
        self._store.updt_tbl("opt_rcvd", peer_id)
        self._cancel_opt_timer(peer_id)
        self._log.info("(SELF_SERVICE) Options received from: %s", int_id(peer_id))
        return False

    def _cancel_opt_timer(self, peer_id: bytes) -> None:
        timer = self._opt_timers.pop(peer_id, None)
        if timer is not None and timer.active():
            timer.cancel()

    def _inject_rpto(self, peer_id: bytes, options: str | bytes) -> None:
        client = self._use_cases.resolve_client(peer_id)
        if client is None:
            return
        body = options.encode("utf-8") if isinstance(options, str) else options
        packet = RPTO + peer_id + body
        self._master_sink.inject(packet, (client.host, client.port))
        self._log.info(
            "(SELF_SERVICE) Options sent for: %s, opt: %s",
            int_id(peer_id),
            options if isinstance(options, str) else options.decode("utf-8", errors="replace"),
        )

    @inlineCallbacks
    def _login_opt(self, peer_id: bytes) -> None:
        self._opt_timers.pop(peer_id, None)
        if self._use_cases.resolve_client(peer_id) is None:
            return
        try:
            rows = yield self._store.slct_opt(peer_id)
            if not rows or not rows[0]:
                return
            options = rows[0][0]
            if not options:
                return
            self._inject_rpto(peer_id, options)
            self._log.info("(SELF_SERVICE) Options sent at login for: %s", int_id(peer_id))
        except Exception as err:
            self._log.warning("(SELF_SERVICE) login_opt error: %s", err)

    @inlineCallbacks
    def send_opts(self) -> None:
        try:
            results = yield self._store.slct_db()
            for row in results:
                if len(row) < 2:
                    continue
                pid = _peer_id_from_db(row[0])
                options = row[1]
                if pid is None or not options:
                    continue
                if self._use_cases.resolve_client(pid) is None:
                    continue
                self._store.updt_tbl("rst_mod", pid)
                self._inject_rpto(pid, options)
                self._log.info("(SELF_SERVICE) Options update sent for: %s", int_id(pid))
        except Exception as err:
            self._log.warning("(SELF_SERVICE) send_opts error: %s", err)

    def lst_seen(self) -> None:
        dmrid_list = [(slot.peer_id,) for slot in self._use_cases.list_slots()]
        if dmrid_list:
            self._store.updt_lstseen(dmrid_list)

    def _clean_tbl(self) -> None:
        self._store.clean_tbl()
