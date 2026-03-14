# ADN DMR Peer Server - entrypoint
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""
ADN DMR Peer Server entrypoint.

Run: python -m adn_server.main [-c adn-server.yaml] [--logging LEVEL]
Config default: adn-server.yaml at project root.
"""

from __future__ import annotations

import argparse
import copy
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

# Ensure package is on path when run as __main__
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from twisted.internet import reactor, task, threads

from .domain import bytes_3
from .infrastructure import YamlConfigLoader, setup_logging
from .infrastructure.persistence import PickleSubMapStore
from .infrastructure.persistence.keys_store import JsonKeysStore
from .infrastructure.persistence.alias_loader import DefaultAliasLoader
from .infrastructure.twisted_adapters.report_server import ReportServerFactory
from .infrastructure.twisted_adapters.udp_hbp import HBPProtocolFactory
from .infrastructure.bridge_router_impl import InMemoryBridgeRouter
from .infrastructure.voice import DefaultVoiceProvider, StubVoiceProvider
from .infrastructure.security.password_download import DefaultSecurityDownloader, StubSecurityDownloader
from .infrastructure.security.user_passwords_loader import UserPasswordsLoader
from .infrastructure.voice.recording import RecordingHandler
from .application import (
    BridgeUseCases,
    IdentUseCases,
    VoiceUseCases,
    ReportingUseCases,
    ReportSender,
    VoiceProvider,
    SecurityDownloader,
)


class ReportSenderAdapter(ReportSender):
    """Adapt ReportServerFactory to ReportSender port."""

    def __init__(self, factory: ReportServerFactory) -> None:
        self._factory = factory

    def send_config(self, systems) -> None:
        self._factory.set_systems(systems)
        self._factory.send_config()

    def send_bridge(self, bridges) -> None:
        self._factory.set_bridges(bridges)
        self._factory.send_bridge()

    def send_bridge_event(self, event: str) -> None:
        self._factory.send_bridge_event(event)


def _make_echo_bridges() -> dict:
    """Initial BRIDGES for ECHO peer (legacy make_bridges 9990)."""
    now = time.time()
    timeout_sec = 2 * 60
    return {
        "9990": [
            {
                "SYSTEM": "ECHO",
                "TS": 2,
                "TGID": bytes_3(9990),
                "ACTIVE": True,
                "TIMEOUT": timeout_sec,
                "TO_TYPE": "NONE",
                "ON": [],
                "OFF": [],
                "RESET": [],
                "TIMER": now + timeout_sec,
            }
        ]
    }


def _looping_errback(logger: logging.Logger, failure):
    """Errback for LoopingCalls (legacy loopingErrHandle)."""
    logger.error("(GLOBAL) Unhandled error in timed loop: %s", failure.getTraceback())


def _expand_generator(config: dict, logger: logging.Logger) -> None:
    """Replace MASTER systems with GENERATOR > 1 by SYSTEM-0, SYSTEM-1, ... (legacy generator)."""
    systems = config.get("SYSTEMS", {})
    to_remove: list[str] = []
    new_systems: dict = {}
    for system_name, sys_cfg in list(systems.items()):
        if not sys_cfg.get("ENABLED", True):
            continue
        if sys_cfg.get("MODE") != "MASTER":
            continue
        generator = int(sys_cfg.get("GENERATOR", 1))
        if generator <= 1:
            continue
        for count in range(generator):
            new_name = f"{system_name}-{count}"
            new_cfg = copy.deepcopy(sys_cfg)
            base_port = int(new_cfg.get("PORT", 56400))
            new_cfg["PORT"] = base_port + count
            new_cfg["_default_options"] = "SINGLE={};DEFAULT_UA_TIMER={};VOICE={};LANG={}".format(
                int(new_cfg.get("SINGLE_MODE", False)),
                new_cfg.get("DEFAULT_UA_TIMER", 60),
                int(new_cfg.get("VOICE_IDENT", False)),
                new_cfg.get("ANNOUNCEMENT_LANGUAGE", "en_GB"),
            )
            new_systems[new_name] = new_cfg
            logger.debug("(GLOBAL) Generator - generated system %s", new_name)
        to_remove.append(system_name)
    for name in to_remove:
        systems.pop(name, None)
    for name, cfg in new_systems.items():
        systems[name] = cfg


def _ensure_system_runtime_config(config: dict) -> None:
    """Ensure MASTER has PEERS and PEER has STATS (legacy config.py runtime state)."""
    for name, sys_cfg in config.get("SYSTEMS", {}).items():
        if sys_cfg.get("MODE") == "MASTER":
            sys_cfg.setdefault("PEERS", {})
        elif sys_cfg.get("MODE") == "PEER":
            sys_cfg.setdefault("STATS", {
                "CONNECTION": "NO",
                "CONNECTED": None,
                "PINGS_SENT": 0,
                "PINGS_ACKD": 0,
                "NUM_OUTSTANDING": 0,
                "PING_OUTSTANDING": False,
                "LAST_PING_TX_TIME": 0,
                "LAST_PING_ACK_TIME": 0,
            })


def _normalize_peer_config(config: dict) -> None:
    """Convert PEER systems from YAML to legacy format: MASTER_SOCKADDR, RADIO_ID/CALLSIGN/OPTIONS as bytes (config.py)."""
    import socket
    for name, sys_cfg in config.get("SYSTEMS", {}).items():
        if sys_cfg.get("MODE") != "PEER":
            continue
        master_ip_str = str(sys_cfg.get("MASTER_IP", "127.0.0.1"))
        master_port = int(sys_cfg.get("MASTER_PORT", 56400))
        try:
            resolved_ip = socket.gethostbyname(master_ip_str)
        except OSError:
            resolved_ip = master_ip_str
        sys_cfg["_MASTER_IP"] = master_ip_str
        sys_cfg["MASTER_IP"] = resolved_ip
        sys_cfg["MASTER_PORT"] = master_port
        sys_cfg["MASTER_SOCKADDR"] = (resolved_ip, master_port)
        radio_id = int(sys_cfg.get("RADIO_ID", 0))
        sys_cfg["RADIO_ID"] = (radio_id & 0xFFFFFFFF).to_bytes(4, "big")
        for field, length in [
            ("CALLSIGN", 8), ("RX_FREQ", 9), ("TX_FREQ", 9), ("TX_POWER", 2), ("COLORCODE", 2),
            ("LATITUDE", 8), ("LONGITUDE", 9), ("HEIGHT", 3), ("LOCATION", 20), ("DESCRIPTION", 19),
            ("SLOTS", 1), ("URL", 124), ("SOFTWARE_ID", 40), ("PACKAGE_ID", 40),
        ]:
            val = sys_cfg.get(field, "")
            if isinstance(val, (int, float)):
                val = str(val)
            b = val.encode("utf-8") if isinstance(val, str) else val
            if field == "CALLSIGN":
                sys_cfg[field] = b.ljust(length)[:length]
            elif field in ("RX_FREQ", "TX_FREQ", "LATITUDE", "LONGITUDE", "LOCATION", "DESCRIPTION", "URL", "SOFTWARE_ID", "PACKAGE_ID"):
                sys_cfg[field] = b.ljust(length)[:length]
            else:
                sys_cfg[field] = b.rjust(length, b"0")[:length] if length <= 3 else b.ljust(length)[:length]
        opt = sys_cfg.get("OPTIONS", "")
        sys_cfg["OPTIONS"] = opt.encode("utf-8") if isinstance(opt, str) else (opt or b"")
        passphrase = sys_cfg.get("PASSPHRASE", "")
        sys_cfg["PASSPHRASE"] = passphrase.encode("utf-8") if isinstance(passphrase, str) else (passphrase or b"")
        sys_cfg.setdefault("LOOSE", False)
        stats = sys_cfg.get("STATS", {})
        stats["DNS_TIME"] = time.time()


def _normalize_obp_config(config: dict) -> None:
    """Normalize OPENBRIDGE systems and GLOBAL SERVER_ID (legacy config.py)."""
    import socket
    g = config.setdefault("GLOBAL", {})
    sid = g.get("SERVER_ID", 0)
    g["SERVER_ID"] = (int(sid) & 0xFFFFFFFF).to_bytes(4, "big") if not isinstance(sid, bytes) else sid
    for name, sys_cfg in config.get("SYSTEMS", {}).items():
        if sys_cfg.get("MODE") != "OPENBRIDGE":
            continue
        net_id = int(sys_cfg.get("NETWORK_ID", 0))
        sys_cfg["NETWORK_ID"] = (net_id & 0xFFFFFFFF).to_bytes(4, "big")
        target_ip = str(sys_cfg.get("TARGET_IP", ""))
        target_port = int(sys_cfg.get("TARGET_PORT", 62044))
        if target_ip:
            try:
                resolved = socket.gethostbyname(target_ip)
                sys_cfg["TARGET_IP"] = resolved
                sys_cfg["TARGET_SOCK"] = (resolved, target_port)
            except OSError:
                sys_cfg["TARGET_IP"] = None
                sys_cfg["TARGET_SOCK"] = (None, target_port)
        else:
            sys_cfg["TARGET_IP"] = None
            sys_cfg["TARGET_SOCK"] = (None, target_port)
        # Legacy config.py 359: VER from PROTO_VER (OPENBRIDGE uses VER for send_system and receive check)
        ver = int(sys_cfg.get("PROTO_VER", sys_cfg.get("VER", 5)))
        if ver in (0, 2, 3) or ver > 5:
            ver = 5
        sys_cfg["VER"] = ver
        # Legacy config.py OPENBRIDGE: PASSPHRASE padded to 20 bytes with nulls (BLAKE2b/HMAC key)
        p = sys_cfg.get("PASSPHRASE") or b""
        if isinstance(p, str):
            p = p.strip().encode("utf-8")
        else:
            p = p or b""
        sys_cfg["PASSPHRASE"] = (p + b"\x00" * 20)[:20]
        sys_cfg.setdefault("RELAX_CHECKS", True)
        sys_cfg.setdefault("ENHANCED_OBP", True)
        if "TG1_ACL" not in sys_cfg and "TGID_ACL" in sys_cfg:
            sys_cfg["TG1_ACL"] = sys_cfg["TGID_ACL"]


def main() -> None:
    parser = argparse.ArgumentParser(description="ADN DMR Peer Server")
    parser.add_argument("-c", "--config", dest="CONFIG_FILE", default=None, help="Path to adn-server.yaml")
    parser.add_argument("--logging", dest="LOG_LEVEL", default=None, help="Override log level")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root.endswith("/adn_server"):
        project_root = str(Path(project_root).parent.parent)
    config_path = args.CONFIG_FILE or os.path.join(project_root, "adn-server.yaml")

    loader = YamlConfigLoader(project_root)
    config = loader.load(config_path)

    if args.LOG_LEVEL:
        config.setdefault("LOGGER", {})["LOG_LEVEL"] = args.LOG_LEVEL
    logger = setup_logging(config.get("LOGGER", {}))
    logger.info("\n\nCopyright (c) 2026 Rodrigo Pérez, CE5RPY ce5rpy@qmd.cl")
    logger.info("\n\nCopyright (c) 2026 Joaquin Madrid Belando, EA5GVK ea5gvk@gmail.com")
    logger.info("\nCopyright (c) 2024-2026 Esteban Mackay, HP3ICC setcom40@gmail.com")
    logger.info("\nCopyright (c) 2020-2023 Simon G7RZU simon@gb7fr.org.uk")
    logger.info("\nCopyright (c) 2013, 2014, 2015, 2016, 2018, 2019\n\tThe Regents of the K0USY Group. All rights reserved.")
    logger.debug("\n\n(GLOBAL) Logging system started, anything from here on gets logged")

    # Aliases
    alias_loader = DefaultAliasLoader()
    peer_ids, subscriber_ids, talkgroup_ids, local_subscriber_ids, server_ids, checksums = (
        alias_loader.load_aliases(config)
    )
    config["_SUB_IDS"] = subscriber_ids
    config["_PEER_IDS"] = peer_ids
    config["_TG_IDS"] = talkgroup_ids
    config["_LOCAL_SUBSCRIBER_IDS"] = local_subscriber_ids
    config["_SERVER_IDS"] = server_ids
    config["CHECKSUMS"] = checksums

    # SUB_MAP (shared mutable; used by SubMapTrimmer and shutdown)
    aliases_cfg = config.get("ALIASES", {})
    data_path = (aliases_cfg.get("PATH") or ".").rstrip("/")
    sub_map_file = aliases_cfg.get("SUB_MAP_FILE") or "sub_map.pkl"
    sub_map_path = os.path.join(project_root, data_path, sub_map_file)
    sub_map_store = PickleSubMapStore()
    sub_map = sub_map_store.load(sub_map_path)
    config["_SUB_MAP"] = sub_map

    # Generator: expand MASTER systems with GENERATOR > 1 into SYSTEM-0, SYSTEM-1, ... (legacy)
    _expand_generator(config, logger)
    _ensure_system_runtime_config(config)
    _normalize_peer_config(config)
    _normalize_obp_config(config)

    # BRIDGES
    bridge_router = InMemoryBridgeRouter()
    systems_cfg = config.get("SYSTEMS", {})
    if "ECHO" in systems_cfg and systems_cfg.get("ECHO", {}).get("MODE") == "PEER":
        bridge_router.set_bridges(_make_echo_bridges())
    else:
        bridge_router.set_bridges({})

    # Protocol registry for send_to_system (legacy: systems[name].send_system(packet))
    protocols: dict[str, Any] = {}
    report_factory = ReportServerFactory(config)

    def send_to_system(system_name: str, packet: bytes, **kwargs: Any) -> None:
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "send_system"):
            p.send_system(packet, **kwargs)

    def send_bcsq(system_name: str, tgid: bytes, stream_id: bytes) -> None:
        """Legacy: bridge calls send_bcsq (e.g. loop control first OBP). OBP protocol only."""
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "_obp_send_bcsq"):
            p._obp_send_bcsq(tgid, stream_id)

    report_sender = ReportSenderAdapter(report_factory)
    report_factory.set_systems(systems_cfg)
    report_factory.set_bridges(bridge_router.get_bridges())
    reporting_use_cases = ReportingUseCases(report_sender, config)
    if config.get("GLOBAL", {}).get("URL_SECURITY", "").strip():
        security = DefaultSecurityDownloader(project_root)
    else:
        security = StubSecurityDownloader()
    security.init_downloads(config)

    user_passwords_loader = UserPasswordsLoader(project_root)
    user_passwords_loader.load(config)

    recording_handler = RecordingHandler(config, project_root)

    # Voice: AMBE words + pkt_gen (legacy readAMBE + mk_voice). Use Default when languages + audio path set.
    audio_path = os.path.join(project_root, config.get("VOICE", {}).get("AUDIO_PATH", "Audio"))
    ann_lang = (config.get("VOICE", {}).get("ANNOUNCEMENT_LANGUAGES") or "").strip()
    if ann_lang and os.path.isdir(audio_path):
        voice_provider = DefaultVoiceProvider()
    else:
        voice_provider = StubVoiceProvider()
    def _start_voice_loop(fn, interval: float, now: bool):
        lc = task.LoopingCall(fn)
        d = lc.start(interval, now=now)
        d.addErrback(_looping_errback, logger)
        return lc

    voice_use_cases = VoiceUseCases(
        voice_provider,
        config,
        get_protocols=lambda: protocols,
        call_from_reactor=reactor.callFromThread,
        audio_path=audio_path,
        get_bridges=bridge_router.get_bridges,
        call_later=reactor.callLater,
        start_looping_call=_start_voice_loop,
        defer_to_thread=threads.deferToThread,
    )
    voice_use_cases.check_voice_config_reload(config_path)
    ident_use_cases = IdentUseCases(
        config,
        voice_use_cases,
        audio_path,
        get_protocols=lambda: protocols,
        call_from_reactor=reactor.callFromThread,
    )

    bridge_use_cases = BridgeUseCases(
        bridge_router,
        config,
        send_to_system=send_to_system,
        get_protocols=lambda: protocols,
        report_factory=report_factory,
        on_bridge_deactivated=lambda sys: reactor.callInThread(voice_use_cases.disconnected_voice, sys),
        send_bcsq=send_bcsq,
    )
    bridge_use_cases.apply_startup_bridges()
    report_factory.set_bridges(bridge_router.get_bridges())
    report_factory.set_systems(config.get("SYSTEMS", {}))

    # Report server (same order as legacy: log then listen)
    if config.get("REPORTS", {}).get("REPORT", True):
        logger.info("(REPORT) HBlink TCP reporting server configured")
        port = config["REPORTS"].get("REPORT_PORT", 4321)
        reactor.listenTCP(port, report_factory)
        logger.info("(REPORT) Report server listening on TCP %s", port)

    # Reporting loop (REPORT_INTERVAL) — same logs as legacy after send_config/send_bridge
    def reporting_loop():
        logger.debug("(REPORT) Periodic reporting loop started")
        report_factory.set_systems(config.get("SYSTEMS", {}))
        report_factory.set_bridges(bridge_router.get_bridges())
        report_factory.send_config()
        report_factory.send_bridge()
        # Legacy: peer count and SUB_MAP count
        systems_with_peers = sum(1 for s in config.get("SYSTEMS", {}) if config.get("SYSTEMS", {}).get(s, {}).get("PEERS"))
        logger.info("(REPORT) %s systems have at least one peer", systems_with_peers)
        logger.info("(REPORT) Subscriber Map has %s entries", len(config.get("_SUB_MAP", {})))

    report_interval = config.get("REPORTS", {}).get("REPORT_INTERVAL", 60)
    task.LoopingCall(reporting_loop).start(report_interval).addErrback(_looping_errback, logger)

    # LoopingCalls (legacy intervals)
    def _rule_timer_in_thread():
        bridge_use_cases.rule_timer_loop()
        reactor.callFromThread(report_factory.set_bridges, bridge_router.get_bridges())
        reactor.callFromThread(report_factory.send_bridge)
    task.LoopingCall(lambda: threads.deferToThread(_rule_timer_in_thread)).start(52).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.stream_trimmer_loop).start(5).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.bridge_reset_loop).start(6).addErrback(_looping_errback, logger)
    if config.get("GLOBAL", {}).get("GEN_STAT_BRIDGES", False):
        def _stat_trimmer_in_thread():
            bridge_use_cases.stat_trimmer_loop()
            reactor.callFromThread(report_factory.set_bridges, bridge_router.get_bridges())
            reactor.callFromThread(report_factory.send_bridge)
        task.LoopingCall(lambda: threads.deferToThread(_stat_trimmer_in_thread)).start(303).addErrback(_looping_errback, logger)

    # KA Reporting (legacy kaReporting, 60s)
    task.LoopingCall(lambda: threads.deferToThread(reporting_use_cases.ka_reporting_loop)).start(60).addErrback(_looping_errback, logger)

    # bridgeDebug (legacy 66s) — remove invalid bridges, fix >1 active dial per MASTER
    task.LoopingCall(
        lambda: (bridge_use_cases.bridge_debug_loop(), report_factory.set_bridges(bridge_router.get_bridges()), report_factory.send_bridge())
    ).start(66).addErrback(_looping_errback, logger)

    # Alias reload (STALE_DAYS -> seconds)
    alias_interval = (aliases_cfg.get("STALE_DAYS") or 1) * 86400

    def alias_reload_loop():
        logger.debug("(ALIAS) starting alias thread")
        try:
            p, s, t, l, sv, ch = alias_loader.load_aliases(config)
            config["_SUB_IDS"] = s
            config["_PEER_IDS"] = p
            config["_TG_IDS"] = t
            config["_LOCAL_SUBSCRIBER_IDS"] = l
            config["_SERVER_IDS"] = sv
            config["CHECKSUMS"] = ch
        except Exception as e:
            logger.warning("(ALIAS) alias reload failed: %s", e)

    task.LoopingCall(alias_reload_loop).start(alias_interval).addErrback(_looping_errback, logger)

    # SubMapTrimmer (3600s) + save
    def sub_map_trimmer_loop():
        logger.debug("(SUBSCRIBER) Subscriber Map trimmer loop started")
        now = time.time()
        to_remove = [k for k, v in sub_map.items() if v[2] < (now - 86400)]
        for k in to_remove:
            sub_map.pop(k, None)
        if aliases_cfg.get("SUB_MAP_FILE"):
            try:
                sub_map_store.save(sub_map_path, sub_map)
                logger.info("(SUBSCRIBER) Writing SUB_MAP to disk")
            except Exception as e:
                logger.warning("(SUBSCRIBER) Cannot write SUB_MAP to file: %s", e)

    task.LoopingCall(sub_map_trimmer_loop).start(3600).addErrback(_looping_errback, logger)

    # Kill switch + shutdown (legacy kill_server every 5s; SIGTERM/SIGINT trigger _KILL_SERVER)
    config.setdefault("GLOBAL", {})["_KILL_SERVER"] = False
    keys_store = JsonKeysStore()
    keys_path = os.path.join(project_root, data_path, aliases_cfg.get("KEYS_FILE") or "keys.json")
    keys = keys_store.load(keys_path) if keys_path else {}

    def kill_server_loop():
        try:
            if config.get("GLOBAL", {}).get("_KILL_SERVER"):
                logger.info("(GLOBAL) SHUTDOWN: CONFBRIDGE IS TERMINATING - killserver called")
                if reactor.running:
                    reactor.stop()
                if aliases_cfg.get("SUB_MAP_FILE"):
                    sub_map_store.save(sub_map_path, sub_map)
                try:
                    keys_store.save(keys_path, keys)
                    logger.info("(KEYS) saved system keys to keystore")
                except Exception as e:
                    logger.error("(GLOBAL) Cannot save key file: %s", e)
        except KeyError:
            pass

    task.LoopingCall(kill_server_loop).start(5).addErrback(_looping_errback, logger)

    def shutdown_handler():
        """On reactor shutdown: save SUB_MAP and keys."""
        if aliases_cfg.get("SUB_MAP_FILE"):
            try:
                sub_map_store.save(sub_map_path, config["_SUB_MAP"])
                logger.info("(SUBSCRIBER) Writing SUB_MAP to disk (shutdown)")
            except Exception as e:
                logger.warning("(SUBSCRIBER) Cannot write SUB_MAP on shutdown: %s", e)
        try:
            keys_store.save(keys_path, keys)
            logger.info("(KEYS) saved system keys to keystore (shutdown)")
        except Exception as e:
            logger.error("(GLOBAL) Cannot save key file on shutdown: %s", e)

    def sig_handler(sig, frame):
        logger.info("(GLOBAL) SHUTDOWN: CONFBRIDGE IS TERMINATING WITH SIGNAL %s", sig)
        config["GLOBAL"]["_KILL_SERVER"] = True
        if reactor.running:
            reactor.stop()

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    reactor.addSystemEventTrigger("before", "shutdown", shutdown_handler)

    # Voice/announcement config reload (15s): re-read main YAML, start/stop announcement LoopingCalls on change
    def voice_reload_loop():
        try:
            loader.reload_voice_config(config, config_path)
            voice_use_cases.check_voice_config_reload(config_path)
        except Exception as e:
            logger.debug("(VOICE-RELOAD) %s", e)

    task.LoopingCall(voice_reload_loop).start(15).addErrback(_looping_errback, logger)
    logger.info("(VOICE-RELOAD) config file watch active (every 15 seconds)")

    def security_loop():
        security.periodic_download(config)

    task.LoopingCall(security_loop).start(300).addErrback(_looping_errback, logger)
    logger.info("(SECURITY) Periodic password download task started (every 5 minutes)")

    # Ident (3600s): run ident in thread for MASTERs with VOICE_IDENT
    def ident_loop():
        logger.debug("(IDENT) starting ident thread")
        reactor.callInThread(ident_use_cases.run_ident)

    task.LoopingCall(ident_loop).start(3600).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.options_config_loop).start(26).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.log_connected_systems_and_tgs).start(60).addErrback(_looping_errback, logger)
    task.LoopingCall(lambda: logger.debug("(ROUTER) KeepAlive reporting loop started")).start(60).addErrback(_looping_errback, logger)

    # UDP listeners per system (same order as legacy: SYSTEM STARTING then instance created per system)
    logger.info("(GLOBAL) ADN DMR Peer Server -- SYSTEM STARTING...")
    for system_name, sys_cfg in systems_cfg.items():
        if not sys_cfg.get("ENABLED", True):
            continue
        ip = sys_cfg.get("IP", "")
        udp_port = sys_cfg.get("PORT", 56400)
        protocol = HBPProtocolFactory(
            system_name,
            config,
            report_factory,
            router=bridge_router,
            dmrd_received=bridge_use_cases.dmrd_received,
            get_user_password_callback=user_passwords_loader.get_user_password,
            on_play_file_request=voice_use_cases.play_file_on_request,
            on_handle_recording=recording_handler.handle_recording,
            on_in_band_signalling=bridge_use_cases.apply_in_band_signalling,
            on_options_received=bridge_use_cases.options_config_for_system,
            on_deactivate_dynamic_bridges=bridge_use_cases.deactivate_all_dynamic_bridges,
        )
        protocols[system_name] = protocol
        reactor.listenUDP(udp_port, protocol, interface=ip or "0.0.0.0")
        logger.debug("(GLOBAL) %s instance created: %s, %s", sys_cfg.get("MODE", "?"), system_name, protocol)
        logger.info("(GLOBAL) UDP %s listening on %s:%s", system_name, ip or "*", udp_port)

    logger.info("(GLOBAL) ADN DMR Peer Server started. Use adn-dmr-server as reference.")
    reactor.run()


if __name__ == "__main__":
    main()
