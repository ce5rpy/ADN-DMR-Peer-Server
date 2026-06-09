"""Integrated proxy self-service DB hooks (legacy adn-proxy parity)."""

from __future__ import annotations

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


def test_self_service_settings_reads_monitor_keys() -> None:
    cfg = {
        "SELF_SERVICE": {
            "USE_SELFSERVICE": True,
            "DB_SERVER": "localhost",
            "DB_USERNAME": "hbmon",
            "DB_PASSWORD": "secret",
            "DB_NAME": "hbmon",
            "DB_PORT": 3306,
            "PBKDF2_SALT": "ADN",
            "PBKDF2_ITERATIONS": 2000,
        }
    }
    ss = self_service_settings(cfg)
    assert ss["enabled"] is True
    assert ss["db_name"] == "hbmon"
    assert ss["pbkdf2_iterations"] == 2000


def test_rptc_ins_conf_and_login_opt_injects_rpto() -> None:
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.options_by_peer[peer] = "TS2=730444;"
    packet = RPTC + peer + b"CE1ILI  " + b"\x00" * 85 + b"4"
    bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert ("ins_conf", peer) in store.actions
    _run_deferred(bridge._login_opt(peer))
    assert sink.injected
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;"


def test_rpto_pass_stores_password_and_skips_inject() -> None:
    bridge, sink, store, sender = _bridge()
    peer = bytes_4(7300444)
    packet = RPTO + peer + b"PASS=secret123"
    skip = bridge.before_inject(packet, ("192.168.1.10", 62031), peer)
    assert skip is True
    assert sink.injected == []
    assert ("psswd", peer) in store.actions
    assert sender.sent and sender.sent[0][0][:6] == b"RPTACK"


def test_send_opts_pushes_modified_rows_to_master() -> None:
    bridge, sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    store.pending_modified = [(peer, "TS2=730444;")]
    _run_deferred(bridge.send_opts())
    assert ("rst_mod", peer) in store.actions
    assert sink.injected[0][0] == RPTO + peer + b"TS2=730444;"


def test_session_expired_logs_out() -> None:
    bridge, _sink, store, _sender = _bridge()
    peer = bytes_4(7300444)
    bridge.on_session_expired(peer)
    assert ("log_out", peer) in store.actions


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
SELF_SERVICE:
  USE_SELFSERVICE: true
  DB_SERVER: localhost
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
