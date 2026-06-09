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

from .application import (
    BridgeUseCases,
    IdentUseCases,
    ReportingUseCases,
    ReportSender,
    VoiceUseCases,
)
from .application.runtime_context import (
    ConfigProxy,
    RuntimeContext,
    RuntimeContextHolder,
    prepare_reload_config,
    swap_runtime_config,
)
from .domain import bytes_3
from .domain.errors import ConfigError
from .infrastructure import YamlConfigLoader, reopen_file_handlers, setup_logging
from .infrastructure.bridge_router_impl import InMemoryBridgeRouter
from .infrastructure.config_normalizer import (
    apply_talker_alias_defaults as _apply_talker_alias_defaults,
)
from .infrastructure.config_normalizer import (
    ensure_system_runtime_config as _ensure_system_runtime_config,
)
from .infrastructure.config_normalizer import (
    expand_generator as _expand_generator,
)
from .infrastructure.config_normalizer import (
    normalize_obp_config as _normalize_obp_config,
)
from .infrastructure.config_normalizer import (
    normalize_peer_config as _normalize_peer_config,
)
from .infrastructure.config_reload import BindSpec, reload_server_config
from .application.proxy.deployment import is_proxy_inject_only, normalize_proxy_target, proxy_target_system
from .infrastructure.proxy import apply_proxy_config_reload, start_proxy_service
from .domain.dmr.bptc import encode_emblc
from .infrastructure.persistence import PickleSubMapStore
from .infrastructure.persistence.alias_loader import DefaultAliasLoader
from .infrastructure.persistence.keys_store import JsonKeysStore
from .infrastructure.security.password_download import DefaultSecurityDownloader, StubSecurityDownloader
from .infrastructure.security.user_passwords_loader import UserPasswordsLoader
from .infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from .application.report.queue import BoundedReportQueue, QueuedReportSender
from .infrastructure.twisted_adapters.report.mqtt_config import mqtt_settings_from_config
from .infrastructure.twisted_adapters.report.mqtt_publisher import (
    create_report_mqtt_publisher,
    reconcile_mqtt_publisher,
)
from .infrastructure.twisted_adapters.report.worker import start_report_queue_worker
from .infrastructure.twisted_adapters.report_server import ReportServerFactory
from .infrastructure.twisted_adapters.udp_hbp import HBPProtocolFactory
from .infrastructure.voice import DefaultVoiceProvider, StubVoiceProvider
from .infrastructure.voice.recording import RecordingHandler


class ReportSenderAdapter(ReportSender):
    """Adapt ReportServerFactory to ReportSender port."""

    def __init__(self, factory: ReportServerFactory) -> None:
        self._factory = factory

    def set_systems(self, systems) -> None:
        self._factory.set_systems(systems)

    def set_bridges(self, bridges) -> None:
        self._factory.set_bridges(bridges)

    def send_config(self, systems, *, incremental: bool = False) -> None:
        self._factory.set_systems(systems)
        self._factory.send_config(incremental=incremental)

    def send_bridge(self, bridges, *, incremental: bool = False) -> None:
        self._factory.set_bridges(bridges)
        self._factory.send_bridge(incremental=incremental)

    def send_bridge_event(self, event: str) -> None:
        self._factory.send_bridge_event(event)

    def set_peer_slot_map(self, provider) -> None:
        self._factory.set_peer_slot_map(provider)


def _wire_proxy_report_slots(
    report_factory: ReportServerFactory,
    proxy_state: Any,
) -> None:
    """Bind proxy upstream slot indices into monitor topology expansion."""
    if proxy_state is None:
        report_factory.set_peer_slot_map(None)
        return

    def _slot_map() -> dict[bytes, int]:
        return {
            slot.peer_id: slot.report_slot
            for slot in proxy_state.use_cases.list_slots()
            if slot.report_slot is not None
        }

    report_factory.set_peer_slot_map(_slot_map)


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
    """Errback for LoopingCalls (legacy loopingErrHandle). Stops reactor to avoid memory leaks."""
    try:
        tb = failure.getTraceback() if hasattr(failure, "getTraceback") else str(failure)
    except Exception:
        tb = repr(failure)
    logger.error(
        "(GLOBAL) STOPPING REACTOR TO AVOID MEMORY LEAK: Unhandled error in timed loop.\n%s",
        tb,
    )
    from twisted.internet import reactor as _reactor
    _reactor.stop()


def main() -> None:
    from . import __version__

    parser = argparse.ArgumentParser(description="ADN DMR Peer Server")
    parser.add_argument("-c", "--config", dest="CONFIG_FILE", default=None, help="Path to adn-server.yaml")
    parser.add_argument("--logging", dest="LOG_LEVEL", default=None, help="Override log level")
    parser.add_argument("--version", action="version", version=f"adn-server {__version__}")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root.endswith("/adn_server"):
        project_root = str(Path(project_root).parent.parent)
    config_path = args.CONFIG_FILE or os.path.join(project_root, "adn-server.yaml")

    loader = YamlConfigLoader(project_root)
    try:
        config = loader.load(config_path)
    except ConfigError as exc:
        print(f"(CONFIG) {exc}", file=sys.stderr)
        sys.exit(1)
    _apply_talker_alias_defaults(config)

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
    subscriber_ids[900999] = "D-APRS"
    subscriber_ids[4294967295] = "SC"
    config["_SUB_IDS"] = subscriber_ids
    config["_SUB_PROFILES"] = alias_loader.load_subscriber_profiles(config)
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
    normalize_proxy_target(config)
    _ensure_system_runtime_config(config)
    _normalize_peer_config(config)
    _normalize_obp_config(config)

    runtime_holder = RuntimeContextHolder(RuntimeContext(config=config, config_path=config_path))
    config = ConfigProxy(runtime_holder)

    # BRIDGES
    bridge_router = InMemoryBridgeRouter()
    systems_cfg = config.get("SYSTEMS", {})
    if "ECHO" in systems_cfg and systems_cfg["ECHO"].get("MODE") in ("PEER", "MASTER"):
        bridge_router.set_bridges(_make_echo_bridges(config))
    else:
        bridge_router.set_bridges({})

    # Protocol registry for send_to_system (legacy: systems[name].send_system(packet))
    protocols: dict[str, Any] = {}
    udp_ports: dict[str, Any] = {}
    report_mqtt = create_report_mqtt_publisher(config)
    report_factory = ReportServerFactory(config, mqtt=report_mqtt)

    def send_to_system(system_name: str, packet: bytes, **kwargs: Any) -> None:
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "send_system"):
            p.send_system(packet, **kwargs)

    def send_dmra_to_system(
        system_name: str,
        packets: list[bytes],
        exclude_peer: bytes | None = None,
    ) -> int:
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "send_dmra_system"):
            return int(p.send_dmra_system(packets, exclude_peer=exclude_peer) or 0)
        return 0

    def get_dmra_blocks(system_name: str, stream_id: bytes) -> dict[int, bytes] | None:
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "get_dmra_blocks"):
            return p.get_dmra_blocks(stream_id)
        return None

    def send_bcsq(system_name: str, tgid: bytes, stream_id: bytes) -> None:
        """Legacy: bridge calls send_bcsq (e.g. loop control first OBP). OBP protocol only."""
        p = protocols.get(system_name)
        if p is not None and hasattr(p, "_obp_send_bcsq"):
            p._obp_send_bcsq(tgid, stream_id)

    report_inner = ReportSenderAdapter(report_factory)
    report_queue = BoundedReportQueue()
    report_sender = QueuedReportSender(report_queue, report_inner)
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
        reporting=reporting_use_cases,
        on_bridge_deactivated=lambda sys: reactor.callInThread(voice_use_cases.disconnected_voice, sys),
        send_bcsq=send_bcsq,
        send_dmra_to_system=send_dmra_to_system,
        get_dmra_blocks=get_dmra_blocks,
        call_later=reactor.callLater,
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
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
        start_report_queue_worker(
            report_queue,
            report_inner,
            on_errback=lambda e: _looping_errback(e, logger),
        )
        if report_mqtt is not None:
            report_factory.start_mqtt()
            reactor.addSystemEventTrigger("during", "shutdown", report_mqtt.stop)

    # Reporting loop (REPORT_INTERVAL) — same logs as legacy after send_config/send_bridge
    def reporting_loop():
        logger.debug("(REPORT) Periodic reporting loop started")
        reporting_use_cases.send_config(config.get("SYSTEMS", {}))
        reporting_use_cases.send_bridge(bridge_router.get_bridges())
        # Legacy: peer count and SUB_MAP count
        systems_with_peers = sum(1 for s in config.get("SYSTEMS", {}) if config.get("SYSTEMS", {}).get(s, {}).get("PEERS"))
        logger.info("(REPORT) %s systems have at least one peer", systems_with_peers)
        logger.info("(REPORT) Subscriber Map has %s entries", len(config.get("_SUB_MAP", {})))

    report_interval = config.get("REPORTS", {}).get("REPORT_INTERVAL", 60)
    task.LoopingCall(reporting_loop).start(report_interval).addErrback(_looping_errback, logger)

    # LoopingCalls (legacy intervals). rule_timer / stat_trimmer mutate BRIDGES on reactor
    # (V2-P0-006: no deferToThread — avoids races with dmrd_received on the same dict).
    def _rule_timer_on_reactor() -> None:
        bridge_use_cases.rule_timer_loop()
        reporting_use_cases.send_bridge(bridge_router.get_bridges(), incremental=True)

    task.LoopingCall(_rule_timer_on_reactor).start(52).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.stream_trimmer_loop).start(5).addErrback(_looping_errback, logger)
    task.LoopingCall(bridge_use_cases.bridge_reset_loop).start(6).addErrback(_looping_errback, logger)
    if config.get("GLOBAL", {}).get("GEN_STAT_BRIDGES", False):

        def _stat_trimmer_on_reactor() -> None:
            bridge_use_cases.stat_trimmer_loop()
            reporting_use_cases.send_bridge(bridge_router.get_bridges(), incremental=True)

        task.LoopingCall(_stat_trimmer_on_reactor).start(303).addErrback(_looping_errback, logger)

    # KA Reporting (legacy kaReporting, 60s)
    task.LoopingCall(lambda: threads.deferToThread(reporting_use_cases.ka_reporting_loop)).start(60).addErrback(_looping_errback, logger)

    # bridgeDebug (legacy 66s) — remove invalid bridges, fix >1 active dial per MASTER
    if config.get("GLOBAL", {}).get("DEBUG_BRIDGES"):
        task.LoopingCall(
            lambda: (
                bridge_use_cases.bridge_debug_loop(),
                reporting_use_cases.send_bridge(bridge_router.get_bridges(), incremental=True),
            )
        ).start(66).addErrback(_looping_errback, logger)

    # Alias reload (STALE_DAYS -> seconds)
    alias_interval = (aliases_cfg.get("STALE_DAYS") or 1) * 86400

    def alias_reload_loop():
        logger.debug("(ALIAS) starting alias thread")
        try:
            peer_ids, subscriber_ids, talkgroup_ids, local_subscriber_ids, server_ids, checksums = (
                alias_loader.load_aliases(config)
            )
            config["_SUB_IDS"] = subscriber_ids
            config["_SUB_PROFILES"] = alias_loader.load_subscriber_profiles(config)
            config["_PEER_IDS"] = peer_ids
            config["_TG_IDS"] = talkgroup_ids
            config["_LOCAL_SUBSCRIBER_IDS"] = local_subscriber_ids
            config["_SERVER_IDS"] = server_ids
            config["CHECKSUMS"] = checksums
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
        for _sys_name in protocols:
            logger.info("(GLOBAL) SHUTDOWN: DE-REGISTER SYSTEM: %s", _sys_name)
            try:
                protocols[_sys_name].dereg()
            except Exception:
                pass
        config["GLOBAL"]["_KILL_SERVER"] = True
        if reactor.running:
            reactor.stop()

    def sigusr2_reopen_logs(_sig, _frame):
        """Logrotate: reopen file log handlers (does not reload config)."""
        n = reopen_file_handlers()
        logger.info("(LOGGER) Reopened %s file log handler(s) after SIGUSR2", n)

    def _create_hbp_protocol(system_name: str) -> Any:
        return HBPProtocolFactory(
            system_name,
            config,
            report_sender,
            router=bridge_router,
            dmrd_received=bridge_use_cases.dmrd_received,
            get_user_password_callback=user_passwords_loader.get_user_password,
            on_play_file_request=voice_use_cases.play_file_on_request,
            on_handle_recording=recording_handler.handle_recording,
            on_in_band_signalling=bridge_use_cases.apply_in_band_signalling,
            on_options_received=bridge_use_cases.options_config_for_system,
            on_deactivate_dynamic_bridges=bridge_use_cases.deactivate_all_dynamic_bridges,
            on_obp_bcsq_received=bridge_use_cases.on_obp_bcsq_received,
            on_talker_alias_repeat_prepare=bridge_use_cases.prepare_talker_alias_local_repeat,
            on_talker_alias_repeat_burst=bridge_use_cases.rewrite_repeat_voice_burst,
            on_talker_alias_stream_end=bridge_use_cases.clear_talker_alias_stream,
            on_dmra_fragment_stored=bridge_use_cases.on_dmra_fragment_stored,
        )

    def _listen_system(_name: str, bind: BindSpec, protocol: Any) -> Any:
        port = reactor.listenUDP(bind.port, protocol, interface=bind.ip or "0.0.0.0")
        logger.info("(GLOBAL) UDP %s listening on %s:%s", _name, bind.ip or "*", bind.port)
        return port

    def _stop_udp_port(port: Any) -> Any:
        if port is not None:
            return port.stopListening()
        return None

    # UDP / proxy listeners (proxy_state declared before reload handler uses nonlocal)
    proxy_state = None

    def _should_bind_udp(system_name: str, sys_cfg: dict[str, Any]) -> bool:
        return not is_proxy_inject_only(config, system_name)

    def _on_config_systems_changed() -> None:
        reporting_use_cases.send_config(config.get("SYSTEMS", {}))
        reporting_use_cases.send_bridge(bridge_router.get_bridges())
        user_passwords_loader.load(config)

    def _apply_reload_success(result: Any, *, new_config: dict[str, Any], mqtt_before: Any) -> None:
        nonlocal report_mqtt, proxy_state
        swap_runtime_config(runtime_holder, new_config, config_path=config_path)
        normalize_proxy_target(config)
        report_factory.set_config(config)
        mqtt_after = mqtt_settings_from_config(config)
        report_mqtt = reconcile_mqtt_publisher(
            report_factory,
            report_mqtt,
            mqtt_before,
            mqtt_after,
            report_enabled=config.get("REPORTS", {}).get("REPORT", True),
        )
        if proxy_state is not None:
            apply_proxy_config_reload(proxy_state, config, logger=logger)
            _wire_proxy_report_slots(report_factory, proxy_state)
        elif proxy_target_system(config):
            proxy_state = start_proxy_service(config, protocols, logger=logger)
            _wire_proxy_report_slots(report_factory, proxy_state)
        else:
            _wire_proxy_report_slots(report_factory, None)
        if result.added or result.removed or result.updated or result.rebound:
            _on_config_systems_changed()

    def _do_config_reload() -> None:
        nonlocal report_mqtt, proxy_state
        mqtt_before = mqtt_settings_from_config(config)
        new_config = prepare_reload_config(runtime_holder)

        def _on_reload_done(result: Any) -> None:
            _apply_reload_success(result, new_config=new_config, mqtt_before=mqtt_before)

        def _on_reload_failed(failure: Any) -> None:
            logger.error("(CONFIG-RELOAD) aborted: %s", failure.value)

        reload_server_config(
            new_config,
            config_path,
            loader,
            protocols,
            udp_ports,
            create_protocol=_create_hbp_protocol,
            listen_udp=lambda n, b, p: _listen_system(n, b, p),
            stop_listener=_stop_udp_port,
            on_systems_changed=None,
            on_system_removed=bridge_use_cases.flush_monitor_events_for_system,
            should_bind_udp=_should_bind_udp,
            log=logger,
        ).addCallbacks(_on_reload_done, _on_reload_failed)

    def sighup_reload_config(_sig, _frame):
        """Reload adn-server.yaml (SYSTEMS, GLOBAL); keeps active streams on unchanged listeners."""
        logger.info("(CONFIG-RELOAD) SIGHUP received, scheduling reload")
        reactor.callLater(0, _do_config_reload)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGUSR2, sigusr2_reopen_logs)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, sighup_reload_config)
        logger.info("(CONFIG-RELOAD) SIGHUP handler active (systemctl reload / kill -HUP)")
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
        protocol = _create_hbp_protocol(system_name)
        protocols[system_name] = protocol
        if not _should_bind_udp(system_name, sys_cfg):
            logger.info("(PROXY) %s inject-only (no UDP bind)", system_name)
            continue
        bind = BindSpec(ip=str(sys_cfg.get("IP") or "0.0.0.0"), port=int(sys_cfg.get("PORT", 56400)))
        udp_ports[system_name] = _listen_system(system_name, bind, protocol)
        logger.debug(
            "(GLOBAL) %s instance created: %s, %s",
            sys_cfg.get("MODE", "?"),
            system_name,
            protocol,
        )

    if proxy_target_system(config):
        try:
            proxy_state = start_proxy_service(config, protocols, logger=logger)
        except Exception as exc:
            logger.error("(PROXY) failed to start integrated proxy: %s", exc)
            raise

        def _stop_proxy(_: Any = None) -> None:
            if proxy_state is not None:
                proxy_state.stop()

        reactor.addSystemEventTrigger("before", "shutdown", _stop_proxy)
        _wire_proxy_report_slots(report_factory, proxy_state)

    logger.info("(GLOBAL) ADN DMR Peer Server started. Use adn-dmr-server as reference.")
    reactor.suggestThreadPoolSize(100)
    reactor.run()


if __name__ == "__main__":
    main()
