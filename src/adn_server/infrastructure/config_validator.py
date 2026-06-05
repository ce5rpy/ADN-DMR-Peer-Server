# ADN DMR Peer Server - YAML config validation
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

"""Validate adn-server.yaml types and required combinations before startup."""

from __future__ import annotations

from typing import Any

from ..domain.errors import ConfigError

ACL_KEYS = frozenset(
    {
        "REG_ACL",
        "SUB_ACL",
        "TG1_ACL",
        "TG2_ACL",
        "TGID_ACL",
        "TGID_TS1_ACL",
        "TGID_TS2_ACL",
    }
)

GLOBAL_STRING_KEYS = frozenset(
    {
        "PATH",
        "ANNOUNCEMENT_LANGUAGES",
        "URL_SECURITY",
        "PORT_SECURITY",
        "PASS_SECURITY",
        "USERS_PASS",
        "HASH_ENCRYPT",
        "TALKER_ALIAS_MODE",
        "TALKER_ALIAS_FORMAT",
        "TALKER_ALIAS_TEXT_FORMAT",
        *ACL_KEYS,
    }
)

LOGGER_STRING_KEYS = frozenset({"LOG_FILE", "LOG_HANDLERS", "LOG_LEVEL", "LOG_NAME"})

SYSTEM_STRING_KEYS = frozenset(
    {
        "MODE",
        "IP",
        "PASSPHRASE",
        "MASTER_IP",
        "CALLSIGN",
        "LOCATION",
        "DESCRIPTION",
        "URL",
        "SOFTWARE_ID",
        "PACKAGE_ID",
        "OPTIONS",
        "TARGET_IP",
        "TS1_STATIC",
        "TS2_STATIC",
        "ANNOUNCEMENT_LANGUAGE",
        "OVERRIDE_IDENT_TG",
        *ACL_KEYS,
    }
)


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _expect_str(path: str, value: Any, errors: list[str]) -> None:
    if _is_empty(value):
        return
    if isinstance(value, str):
        return
    errors.append(
        f"{path}: expected string, got {type(value).__name__} ({value!r}). "
        "Use quotes in YAML or re-run scripts/freedmr_cfg_to_yaml.py."
    )


def _expect_bool(path: str, value: Any, errors: list[str]) -> None:
    if _is_empty(value):
        return
    if isinstance(value, bool):
        return
    errors.append(f"{path}: expected boolean (true/false), got {type(value).__name__} ({value!r}).")


def _expect_int(path: str, value: Any, errors: list[str]) -> None:
    if _is_empty(value):
        return
    if isinstance(value, bool):
        errors.append(f"{path}: expected integer, got boolean ({value!r}).")
        return
    if isinstance(value, int):
        return
    errors.append(f"{path}: expected integer, got {type(value).__name__} ({value!r}).")


def _expect_number(path: str, value: Any, errors: list[str]) -> None:
    if _is_empty(value):
        return
    if isinstance(value, bool):
        errors.append(f"{path}: expected number, got boolean ({value!r}).")
        return
    if isinstance(value, (int, float)):
        return
    errors.append(f"{path}: expected number, got {type(value).__name__} ({value!r}).")


def _section_string_keys(section_name: str, section: dict[str, Any], keys: frozenset[str], errors: list[str]) -> None:
    for key in keys:
        if key in section:
            _expect_str(f"{section_name}.{key}", section[key], errors)


def _validate_global(global_cfg: dict[str, Any], errors: list[str]) -> None:
    _section_string_keys("GLOBAL", global_cfg, GLOBAL_STRING_KEYS, errors)
    for key in ("PING_TIME", "MAX_MISSED", "SERVER_ID"):
        if key in global_cfg:
            _expect_int(f"GLOBAL.{key}", global_cfg[key], errors)
    for key in (
        "USE_ACL",
        "GEN_STAT_BRIDGES",
        "ALLOW_NULL_PASSPHRASE",
        "DATA_GATEWAY",
        "VALIDATE_SERVER_IDS",
        "DEBUG_BRIDGES",
        "ENABLE_API",
        "TALKER_ALIAS",
    ):
        if key in global_cfg:
            _expect_bool(f"GLOBAL.{key}", global_cfg[key], errors)

    url = global_cfg.get("URL_SECURITY")
    port = global_cfg.get("PORT_SECURITY")
    password = global_cfg.get("PASS_SECURITY")
    if not _is_empty(url):
        if _is_empty(port):
            errors.append("GLOBAL.PORT_SECURITY: required when GLOBAL.URL_SECURITY is set.")
        if _is_empty(password):
            errors.append("GLOBAL.PASS_SECURITY: required when GLOBAL.URL_SECURITY is set.")


def _validate_reports(reports_cfg: dict[str, Any], errors: list[str]) -> None:
    if "REPORT" in reports_cfg:
        _expect_bool("REPORTS.REPORT", reports_cfg["REPORT"], errors)
    for key in ("REPORT_INTERVAL", "REPORT_PORT"):
        if key in reports_cfg:
            _expect_int(f"REPORTS.{key}", reports_cfg[key], errors)
    if "REPORT_CLIENTS" in reports_cfg and not _is_empty(reports_cfg["REPORT_CLIENTS"]):
        clients = reports_cfg["REPORT_CLIENTS"]
        if not isinstance(clients, (str, list)):
            errors.append(
                f"REPORTS.REPORT_CLIENTS: expected string or list, got {type(clients).__name__} ({clients!r})."
            )


def _validate_logger(logger_cfg: dict[str, Any], errors: list[str]) -> None:
    _section_string_keys("LOGGER", logger_cfg, LOGGER_STRING_KEYS, errors)


def _validate_system(name: str, sys_cfg: dict[str, Any], errors: list[str]) -> None:
    prefix = f"SYSTEMS.{name}"
    _section_string_keys(prefix, sys_cfg, SYSTEM_STRING_KEYS, errors)
    mode = sys_cfg.get("MODE")
    if mode is not None and not _is_empty(mode) and not isinstance(mode, str):
        errors.append(f"{prefix}.MODE: expected string, got {type(mode).__name__} ({mode!r}).")
    for key in ("ENABLED", "REPEAT", "USE_ACL", "SINGLE_MODE", "VOICE_IDENT", "ALLOW_UNREG_ID", "PROXY_CONTROL", "EXPORT_AMBE", "LOOSE", "RELAX_CHECKS", "ENHANCED_OBP", "BOTH_SLOTS"):
        if key in sys_cfg:
            _expect_bool(f"{prefix}.{key}", sys_cfg[key], errors)
    for key in (
        "PORT",
        "MASTER_PORT",
        "MAX_PEERS",
        "GROUP_HANGTIME",
        "DEFAULT_UA_TIMER",
        "DEFAULT_REFLECTOR",
        "GENERATOR",
        "NETWORK_ID",
        "TARGET_PORT",
        "PROTO_VER",
        "RADIO_ID",
        "RX_FREQ",
        "TX_FREQ",
        "TX_POWER",
        "COLORCODE",
        "SLOTS",
        "HEIGHT",
    ):
        if key in sys_cfg:
            _expect_int(f"{prefix}.{key}", sys_cfg[key], errors)
    for key in ("LATITUDE", "LONGITUDE"):
        if key in sys_cfg:
            _expect_number(f"{prefix}.{key}", sys_cfg[key], errors)


def validate_config(config: dict[str, Any], *, config_path: str | None = None) -> None:
    """Validate config structure and scalar types. Raises ConfigError with all issues found."""
    errors: list[str] = []
    if not isinstance(config, dict):
        raise ConfigError("Configuration root must be a mapping.")

    _validate_global(config.get("GLOBAL", {}), errors)
    _validate_reports(config.get("REPORTS", {}), errors)
    _validate_logger(config.get("LOGGER", {}), errors)

    systems = config.get("SYSTEMS", {})
    if systems is not None and not isinstance(systems, dict):
        errors.append(f"SYSTEMS: expected mapping, got {type(systems).__name__}.")
    elif isinstance(systems, dict):
        for name, sys_cfg in systems.items():
            if not isinstance(sys_cfg, dict):
                errors.append(f"SYSTEMS.{name}: expected mapping, got {type(sys_cfg).__name__}.")
                continue
            _validate_system(name, sys_cfg, errors)

    if errors:
        header = f"Configuration error in {config_path}:" if config_path else "Configuration error:"
        raise ConfigError("\n".join([header, *[f"  - {err}" for err in errors]]))
