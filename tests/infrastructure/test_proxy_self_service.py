# ADN DMR Peer Server - tests infrastructure proxy self service
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

"""Integrated proxy self-service DB hooks (legacy adn-proxy parity)."""

from __future__ import annotations

from typing import Any

from twisted.internet.defer import Deferred

from adn_server.application.proxy import ProxyUseCases
from adn_server.domain import bytes_4
from adn_server.domain.proxy import ClientEndpoint
from adn_server.infrastructure.hbp_constants import RPTC, RPTO
from adn_server.infrastructure.proxy.null_self_service import NullProxySelfServiceStore
from adn_server.infrastructure.proxy.rpto_queue import InMemoryPendingRptoQueue
from adn_server.infrastructure.proxy.self_service_bridge import ProxySelfServiceBridge
from adn_server.infrastructure.proxy.self_service_config import self_service_settings
from adn_server.infrastructure.proxy.slot_store import InMemoryProxySlotStore


class _RecordingSink:
    def __init__(self) -> None:
        self.injected: list[tuple[bytes, tuple[str, int]]] = []

    def inject(self, data: bytes, client_addr: tuple[str, int]) -> None:
        self.injected.append((data, client_addr))


class _RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, ClientEndpoint]] = []

    def send_to_client(self, data: bytes, client: ClientEndpoint) -> None:
        self.sent.append((data, client))


class _FakeStore(NullProxySelfServiceStore):
    def __init__(self) -> None:
        self.actions: list[tuple[str, bytes]] = []
        self.options_by_peer: dict[bytes, str] = {}
        self.pending_modified: list[tuple[bytes, str]] = []
        self.reconcile_calls: list[list[bytes]] = []

    def ins_conf(
        self,
        int_id: int,
        peer_id_bytes: bytes,
        callsign: str,
        host: str,
        mode: str,
    ) -> None:
        self.actions.append(("ins_conf", peer_id_bytes))

    def updt_tbl(
        self,
        action: str,
        peer_id_bytes: bytes,
        *,
        psswd: str | None = None,
    ) -> None:
        self.actions.append((action, peer_id_bytes))

    def slct_opt(self, peer_id_bytes: bytes):
        from twisted.internet.defer import succeed

        opt = self.options_by_peer.get(peer_id_bytes)
        if not opt:
            return succeed([])
        return succeed([(opt,)])

    def slct_db(self):
        from twisted.internet.defer import succeed

        return succeed([(pid, opt) for pid, opt in self.pending_modified])

    def updt_lstseen(self, dmrid_list: list[tuple[bytes, ...]]) -> None:
        self.actions.append(("updt_lstseen", b""))

    def reconcile_logged_in(self, connected_peer_ids: list[bytes]) -> Any:
        from twisted.internet.defer import succeed

        self.reconcile_calls.append(list(connected_peer_ids))
        return succeed(None)


def _bridge() -> tuple[ProxySelfServiceBridge, _RecordingSink, _FakeStore, _RecordingSender]:
    store = _FakeStore()
    sink = _RecordingSink()
    sender = _RecordingSender()
    use_cases = ProxyUseCases(InMemoryProxySlotStore(), InMemoryPendingRptoQueue(), max_peers=4)
    peer = bytes_4(7300444)
    use_cases.attach_client(peer, "192.168.1.10", 62031)
    bridge = ProxySelfServiceBridge(
        store,
        use_cases,
        sink,
        sender,
        pbkdf2_salt="ADN",
        pbkdf2_iterations=2000,
    )
    return bridge, sink, store, sender


def _run_deferred(d: Deferred) -> None:
    results: list[object] = []
    d.addBoth(lambda x: results.append(x) or x)
    assert results, "deferred did not fire synchronously"


def test_self_service_settings_reads_database_and_self_service_keys() -> None:
    cfg = {
        "DATABASE": {
            "DB_SERVER": "localhost",
            "DB_USERNAME": "hbmon",
            "DB_PASSWORD": "secret",
            "DB_NAME": "hbmon",
            "DB_PORT": 3306,
        },
        "SELF_SERVICE": {
            "USE_SELFSERVICE": True,
            "PBKDF2_SALT": "ADN",
            "PBKDF2_ITERATIONS": 2000,
        },
    }
    ss = self_service_settings(cfg)
    assert ss["enabled"] is True
    assert ss["db_name"] == "hbmon"
    assert ss["pbkdf2_iterations"] == 2000


def test_rptc_schedules_fallback_when_no_pass() -> None:
    """RPTC without prior PASS schedules a fallback timer to fetch DB options."""
    bridge, _sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;"
    packet = RPTC + peer + b"CE1ILI  " + b"\x00" * 85 + b"4"
    bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert ("ins_conf", peer) in store.actions
    assert peer in bridge._opt_timers


def test_rptc_fallback_fetches_db_options() -> None:
    """When the fallback timer fires (no RPTO), DB options are fetched and injected."""
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;SINGLE=1;"
    packet = RPTC + peer + b"CE1ILI  " + b"\x00" * 85 + b"4"
    bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    # Simulate the timer firing
    bridge._rptc_fallback_fire(peer)
    assert peer in bridge._mysql_option_peers
    assert sink.injected
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;SINGLE=1;"


def test_rpto_cancels_rptc_fallback() -> None:
    """RPTO with content cancels the RPTC fallback timer."""
    bridge, _sink, _store, _sender = _bridge()
    peer = bytes_4(7300444)
    packet = RPTC + peer + b"CE1ILI  " + b"\x00" * 85 + b"4"
    bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert peer in bridge._opt_timers
    bridge.before_inject(
        RPTO + peer + b"TS2=730;SINGLE=0;",
        ("192.168.1.10", 62031),
        peer,
    )
    assert peer not in bridge._opt_timers


def test_rptc_after_pass_reinjects_rpto() -> None:
    """RPTC after PASS= re-fetches OPTIONS once ins_conf has run (logged_in in DB)."""
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;"
    bridge.before_inject(
        RPTO + peer + b"PASS=secret123",
        ("192.168.1.10", 62031),
        peer,
    )
    assert len(sink.injected) == 1
    packet = RPTC + peer + b"CE1ILI  " + b"\x00" * 85 + b"4"
    bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert ("ins_conf", peer) in store.actions
    assert len(sink.injected) == 2
    assert sink.injected[-1][0] == RPTO + peer + b"TS2=730444;"


def test_rpto_pass_stores_password_and_skips_inject() -> None:
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    packet = RPTO + peer + b"PASS=secret123"
    skip = bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert skip is True
    assert sink.injected == []
    assert ("psswd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"


def test_rpto_pass_fetches_options_immediately() -> None:
    """PASS= triggers MySQL slct_opt + RPTO inject without waiting for RPTC/10s timer."""
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;SINGLE=1;"
    skip = bridge.before_inject(
        RPTO + peer + b"PASS=secret123",
        ("192.168.1.10", 62031),
        peer,
    )
    assert skip is True
    assert ("psswd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"
    assert sink.injected
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;SINGLE=1;"


def test_rpto_empty_fetches_options_from_db() -> None:
    """Empty RPTO payload: BD is the authority (like PASS). Password cleared."""
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;SINGLE=1;"
    skip = bridge.before_inject(
        RPTO + peer,
        ("192.168.1.10", 62031),
        peer,
    )
    assert skip is True
    assert ("clear_psswd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"
    assert sink.injected
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;SINGLE=1;"


def test_rpto_empty_no_db_options_skips_inject() -> None:
    """Empty RPTO + empty BD: no inject; server YAML defaults apply."""
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    skip = bridge.before_inject(
        RPTO + peer,
        ("192.168.1.10", 62031),
        peer,
    )
    assert skip is True
    assert ("clear_psswd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"
    assert sink.injected == []


def test_rpto_with_content_clears_password_and_passes_through() -> None:
    """OPTIONS with content (no PASS): hotspot is authority; password cleared
    so only IP auto-login works; user cannot login by password (NULL hash)."""
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    skip = bridge.before_inject(
        RPTO + peer + b"TS2=730;SINGLE=0;",
        ("192.168.1.10", 62031),
        peer,
    )
    assert skip is False
    assert ("clear_psswd", peer) in store.actions
    assert ("opt_rcvd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"
    assert sink.injected == []
    assert peer not in bridge._mysql_option_peers


def test_send_opts_skips_without_pass() -> None:
    """Peer that sent OPTIONS with content (not in _mysql_option_peers) is skipped by send_opts."""
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.pending_modified = [(peer, "TS2=730444;")]
    _run_deferred(bridge.send_opts())
    assert ("rst_mod", peer) not in store.actions
    assert sink.injected == []


def test_send_opts_pushes_modified_rows_after_pass() -> None:
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    bridge.before_inject(
        RPTO + peer + b"PASS=secret123",
        ("192.168.1.10", 62031),
        peer,
    )
    store.pending_modified = [(peer, "TS2=730444;")]
    _run_deferred(bridge.send_opts())
    assert ("rst_mod", peer) in store.actions
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;"


def test_session_expired_logs_out() -> None:
    bridge, _sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    bridge.on_session_expired(peer)
    assert ("log_out", peer) in store.actions


def test_lst_seen_reconciles_connected_peers() -> None:
    """lst_seen calls reconcile_logged_in with the connected peer IDs."""
    bridge, _sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    bridge.lst_seen()
    assert store.reconcile_calls == [[peer]]


def test_lst_seen_reconciles_empty_when_no_peers() -> None:
    """lst_seen with no slots calls reconcile_logged_in([]) — startup clean slate."""
    from adn_server.application.proxy import ProxyUseCases
    from adn_server.infrastructure.proxy.rpto_queue import InMemoryPendingRptoQueue
    from adn_server.infrastructure.proxy.slot_store import InMemoryProxySlotStore

    store = _FakeStore()
    sink = _RecordingSink()
    sender = _RecordingSender()
    use_cases = ProxyUseCases(
        InMemoryProxySlotStore(), InMemoryPendingRptoQueue(), max_peers=4
    )
    bridge = ProxySelfServiceBridge(
        store, use_cases, sink, sender, pbkdf2_salt="ADN", pbkdf2_iterations=2000
    )
    bridge.lst_seen()
    assert store.reconcile_calls == [[]]


def test_yaml_loader_preserves_self_service_block(tmp_path) -> None:
    """SELF_SERVICE from adn-server.yaml must reach runtime (not stripped at load)."""
    from adn_server.infrastructure.config_loader import YamlConfigLoader

    cfg_path = tmp_path / "adn-server.yaml"
    cfg_path.write_text(
        """
GLOBAL: {}
PROXY:
  LISTEN_PORT: 62031
  TARGET_SYSTEM: SYSTEM
DATABASE:
  DB_SERVER: localhost
  DB_USERNAME: hbmon
  DB_PASSWORD: secret
  DB_NAME: hbmon
  DB_PORT: 3306
SELF_SERVICE:
  USE_SELFSERVICE: true
SYSTEMS:
  SYSTEM:
    MODE: MASTER
    ENABLED: true
""",
        encoding="utf-8",
    )
    config = YamlConfigLoader(tmp_path).load(str(cfg_path))
    assert config["SELF_SERVICE"]["USE_SELFSERVICE"] is True
    assert self_service_settings(config)["enabled"] is True
