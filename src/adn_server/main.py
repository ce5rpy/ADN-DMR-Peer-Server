# ADN DMR Peer Server - entrypoint
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Derived from ADN DMR Server / FreeDMR  / HBlink. Original license:
###############################################################################
# Copyright (C) 2026 Joaquin Madrid Belando, EA5GVK <ea5gvk@gmail.com>
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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

"""
ADN DMR Peer Server entrypoint.

Run: python -m adn_server.main [-c adn-server.yaml] [--logging LEVEL]
Config default: adn-server.yaml at project root.
"""

from __future__ import annotations

import argparse
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
from .infrastructure.config_normalizer import (
    expand_generator as _expand_generator,
    ensure_system_runtime_config as _ensure_system_runtime_config,
    normalize_peer_config as _normalize_peer_config,
    normalize_obp_config as _normalize_obp_config,
)
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


def _make_echo_bridges(config: dict) -> dict:
    """Initial BRIDGES for ECHO system (legacy make_bridges 9990 + MASTER expansion).

    Works regardless of whether ECHO is PEER or MASTER:
    - ECHO entry is always ACTIVE with TO_TYPE NONE (the parrot endpoint).
    - Every other MASTER gets ACTIVE False / TO_TYPE ON so in-band signalling
      activates them on first voice terminator (legacy behavior).
    """
    now = time.time()
    timeout_sec = 2 * 60
    tgid_b = bytes_3(9990)
    bridges: dict = {
        "9990": [
            {
                "SYSTEM": "ECHO",
                "TS": 2,
                "TGID": tgid_b,
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
    systems_cfg = config.get("SYSTEMS", {})
    for _system, sys_cfg in systems_cfg.items():
        if _system == "ECHO":
            continue
        if sys_cfg.get("MODE") != "MASTER":
            continue
        _tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
        bridges["9990"].append({"SYSTEM": _system, "TS": 1, "TGID": tgid_b, "ACTIVE": False, "TIMEOUT": _tmout * 60, "TO_TYPE": "ON", "OFF": [], "ON": [tgid_b], "RESET": [], "TIMER": now})
        bridges["9990"].append({"SYSTEM": _system, "TS": 2, "TGID": tgid_b, "ACTIVE": False, "TIMEOUT": _tmout * 60, "TO_TYPE": "ON", "OFF": [], "ON": [tgid_b], "RESET": [], "TIMER": now})
    return bridges


def _looping_errback(logger: logging.Logger, failure):
    """Errback for LoopingCalls (legacy loopingErrHandle)."""
    logger.error("(GLOBAL) Unhandled error in timed loop: %s", failure.getTraceback())


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

    # Voice config lives in a separate file for hot-reload without restart
    voice_config_path = os.path.join(os.path.dirname(os.path.abspath(config_path)), "adn-voice.yaml")
    voice_data = loader.load_voice_config(voice_config_path)
    if voice_data:
        config.setdefault("VOICE", {}).update(voice_data)

    if args.LOG_LEVEL:
        config.setdefault("LOGGER", {})["LOG_LEVEL"] = args.LOG_LEVEL
    logger = setup_logging(config.get("LOGGER", {}))
    logger.info("\n\nCopyright (c) 2026 Rodrigo Pérez, CE5RPY ce5rpy@qmd.cl")
    logger.info("\n\nCopyright (c) 2026 Joaquin Madrid Belando, EA5GVK ea5gvk@gmail.com")
    logger.info("\nCopyright (c) 2024-2026 Esteban Mackay, HP3ICC setcom40@gmail.com")
    logger.info("\nCopyright (c) 2020 Simon Adlem, G7RZU g7rzu@gb7fr.org.uk")
    logger.info("\nCopyright (c) 2016-2019 Cortney T. Buffington, N0MJS n0mjs@me.com")
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
    if "ECHO" in systems_cfg and systems_cfg["ECHO"].get("MODE") in ("PEER", "MASTER"):
        bridge_router.set_bridges(_make_echo_bridges(config))
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

    # Voice: AMBE words + pkt_gen (legacy readAMBE + mk_voice). Use Default when Audio dir exists.
    # ANNOUNCEMENT_LANGUAGES is only for voice ident; announcements/TTS use per-item LANGUAGE.
    audio_path = os.path.join(project_root, config.get("VOICE", {}).get("AUDIO_PATH", "Audio"))
    if config.get("VOICE") and not os.path.isdir(audio_path):
        os.makedirs(audio_path, exist_ok=True)
    if os.path.isdir(audio_path):
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
    voice_use_cases.check_voice_config_reload(voice_config_path)
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

    # Voice config reload (15s): re-read adn-voice.yaml, start/stop announcement LoopingCalls on change
    def voice_reload_loop():
        try:
            loader.reload_voice_config(config, voice_config_path)
            voice_use_cases.check_voice_config_reload(voice_config_path)
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
            on_obp_bcsq_received=bridge_use_cases.on_obp_bcsq_received,
        )
        protocols[system_name] = protocol
        reactor.listenUDP(udp_port, protocol, interface=ip or "0.0.0.0")
        logger.debug("(GLOBAL) %s instance created: %s, %s", sys_cfg.get("MODE", "?"), system_name, protocol)
        logger.info("(GLOBAL) UDP %s listening on %s:%s", system_name, ip or "*", udp_port)

    logger.info("(GLOBAL) ADN DMR Peer Server started. Use adn-dmr-server as reference.")
    reactor.run()


if __name__ == "__main__":
    main()
