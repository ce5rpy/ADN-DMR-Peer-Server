# ADN DMR Peer Server - logging setup
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

"""Configure logging (same format/handlers as legacy log.config_logging)."""

from __future__ import annotations

import logging
import sys
from functools import partial, partialmethod
from typing import Any


def setup_logging(log_config: dict[str, Any]) -> logging.Logger:
    """Configure logging from CONFIG['LOGGER']. Returns root logger."""
    level = getattr(logging, (log_config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    log_file = log_config.get("LOG_FILE", "/dev/null")
    handlers_cfg = log_config.get("LOG_HANDLERS", "console-timed").strip().split(",")
    log_name = log_config.get("LOG_NAME", "ADN")

    logging.TRACE = 5
    logging.addLevelName(logging.TRACE, "TRACE")
    logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
    logging.trace = partial(logging.log, logging.TRACE)

    handlers: list[logging.Handler] = []
    if "console-timed" in handlers_cfg or "console" in handlers_cfg:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s %(asctime)s %(message)s"))
        handlers.append(h)
    if ("file-timed" in handlers_cfg or "file" in handlers_cfg) and log_file and log_file != "/dev/null":
        try:
            h = logging.FileHandler(log_file, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(levelname)s %(asctime)s %(message)s"))
            handlers.append(h)
        except OSError as e:
            # Fallback: warn to stderr if file cannot be opened (e.g. permission, missing dir)
            sys.stderr.write("(LOGGER) Could not open log file %s: %s\n" % (log_file, e))

    # force=True (Python 3.8+) so our handlers replace any already set by other libs (e.g. Twisted)
    logging.basicConfig(level=level, handlers=handlers or [logging.NullHandler()], force=True)
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    return logger
