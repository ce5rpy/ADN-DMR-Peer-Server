# ADN DMR Peer Server - parrot (playback) entrypoint
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Derived from ADN DMR Server / FreeDMR  / HBlink. Original license:
###############################################################################
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
ADN DMR Parrot (playback) entrypoint.

Exact port of legacy playback.py: record group voice, play back with new stream ID.
Uses the same YAML config as adn-server (only MASTER/PEER systems, no OPENBRIDGE).

  python adn-parrot.py
  python adn-parrot.py -c adn-parrot.yaml
  python adn-parrot.py --logging DEBUG
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from twisted.internet import reactor, task

from .infrastructure import YamlConfigLoader, reopen_file_handlers, setup_logging
from .infrastructure.config_normalizer import (
    ensure_system_runtime_config,
    normalize_peer_config,
    normalize_obp_config,
)
from .infrastructure.bridge_router_impl import InMemoryBridgeRouter
from .infrastructure.twisted_adapters.report_server import ReportServerFactory
from .infrastructure.twisted_adapters.udp_hbp import HBPProtocolFactory
from .application.playback_use_cases import PlaybackUseCases
from .domain.errors import ConfigError


def _looping_errback(logger_obj: logging.Logger, failure):
    logger_obj.error("(GLOBAL) Unhandled error in timed loop: %s", failure.getTraceback())


def main() -> None:
    parser = argparse.ArgumentParser(description="ADN DMR Parrot (playback)")
    parser.add_argument("-c", "--config", dest="CONFIG_FILE", default=None, help="Path to YAML config")
    parser.add_argument("--logging", dest="LOG_LEVEL", default=None, help="Override log level")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root.endswith("/adn_server"):
        project_root = str(Path(project_root).parent.parent)
    config_path = args.CONFIG_FILE or os.path.join(project_root, "adn-parrot.yaml")

    loader = YamlConfigLoader(project_root)
    try:
        config = loader.load(config_path)
    except ConfigError as exc:
        print(f"(CONFIG) {exc}", file=sys.stderr)
        sys.exit(1)

    if args.LOG_LEVEL:
        config.setdefault("LOGGER", {})["LOG_LEVEL"] = args.LOG_LEVEL
    logger = setup_logging(config.get("LOGGER", {}))
    logger.info("\n\nCopyright (c) 2026 Rodrigo Pérez, CE5RPY ce5rpy@qmd.cl")
    logger.info("\n\nCopyright (c) 2026 Joaquin Madrid Belando, EA5GVK ea5gvk@gmail.com")
    logger.info("\nCopyright (c) 2024-2026 Esteban Mackay, HP3ICC setcom40@gmail.com")
    logger.info("\nCopyright (c) 2020-2023 Simon Adlem, G7RZU g7rzu@gb7fr.org.uk")
    logger.info("\nCopyright (c) 2016-2019 Cortney T. Buffington, N0MJS n0mjs@me.com")
    logger.info("\nCopyright (c) 2013, 2014, 2015, 2016, 2018, 2019\n\tThe Regents of the K0USY Group. All rights reserved.")
    logger.debug("\n\n(GLOBAL) Logging system started, anything from here on gets logged")

    ensure_system_runtime_config(config)
    normalize_peer_config(config)
    normalize_obp_config(config)

    g = config.setdefault("GLOBAL", {})
    sid = g.get("SERVER_ID", 0)
    g["SERVER_ID"] = (int(sid) & 0xFFFFFFFF).to_bytes(4, "big") if not isinstance(sid, bytes) else sid

    protocols: dict[str, Any] = {}
    router = InMemoryBridgeRouter()
    report_factory = ReportServerFactory(config)
    systems_cfg = config.get("SYSTEMS", {})
    report_factory.set_systems(systems_cfg)

    if config.get("REPORTS", {}).get("REPORT", False):
        port = config["REPORTS"].get("REPORT_PORT", 4321)
        reactor.listenTCP(port, report_factory)
        logger.info("(REPORT) Report server listening on TCP %s", port)

    def reporting_loop():
        report_factory.set_systems(config.get("SYSTEMS", {}))
        report_factory.send_config()

    report_interval = config.get("REPORTS", {}).get("REPORT_INTERVAL", 60)
    task.LoopingCall(reporting_loop).start(report_interval).addErrback(_looping_errback, logger)

    playback_instances: dict[str, PlaybackUseCases] = {}

    def sig_handler(sig, frame):
        logger.info("SHUTDOWN: PARROT IS TERMINATING WITH SIGNAL %s", sig)
        if reactor.running:
            reactor.stop()

    def sigusr2_reopen_logs(_sig, _frame):
        """Logrotate: reopen file log handlers (does not reload config)."""
        n = reopen_file_handlers()
        logger.info("(LOGGER) Reopened %s file log handler(s) after SIGUSR2", n)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGUSR2, sigusr2_reopen_logs)

    logger.info("ADN Parrot -- SYSTEM STARTING...")
    for system_name, sys_cfg in systems_cfg.items():
        if not sys_cfg.get("ENABLED", True):
            continue
        if sys_cfg.get("MODE") == "OPENBRIDGE":
            logger.critical(
                "%s FATAL: Instance is mode 'OPENBRIDGE', which would be tragic for playback. "
                "playback only works with MMDVM-based systems",
                system_name,
            )
            sys.exit(
                "playback cannot function with OPENBRIDGE systems. System {} is configured as OPENBRIDGE".format(
                    system_name
                )
            )

        pb = PlaybackUseCases(system_name, get_protocol=lambda sn=system_name: protocols.get(sn))
        playback_instances[system_name] = pb

        protocol = HBPProtocolFactory(
            system_name,
            config,
            report_factory,
            router=router,
            dmrd_received=pb.dmrd_received,
        )
        protocols[system_name] = protocol
        ip = sys_cfg.get("IP", "")
        udp_port = sys_cfg.get("PORT", 56400)
        reactor.listenUDP(udp_port, protocol, interface=ip or "0.0.0.0")
        logger.debug("%s instance created: %s, %s", sys_cfg.get("MODE", "?"), system_name, protocol)

    reactor.run()


if __name__ == "__main__":
    main()
