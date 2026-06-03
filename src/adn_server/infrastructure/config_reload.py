# ADN DMR Peer Server - hot reload adn-server.yaml
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Reload SYSTEMS / GLOBAL from adn-server.yaml without full process restart."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..domain.errors import ConfigError
from .config_loader import YamlConfigLoader
from .config_normalizer import (
    apply_talker_alias_defaults,
    ensure_system_runtime_config,
    expand_generator,
    normalize_obp_config,
    normalize_peer_config,
)
from .logging_config import reapply_log_level

logger = logging.getLogger(__name__)

_RUNTIME_TOP_KEYS = frozenset({
    "_SUB_MAP",
    "_SUB_IDS",
    "_SUB_PROFILES",
    "_PEER_IDS",
    "_TG_IDS",
    "_LOCAL_SUBSCRIBER_IDS",
    "_SERVER_IDS",
    "CHECKSUMS",
})


@dataclass(frozen=True)
class BindSpec:
    ip: str
    port: int


def bind_spec(sys_cfg: dict[str, Any]) -> BindSpec:
    ip = str(sys_cfg.get("IP") or "0.0.0.0")
    return BindSpec(ip=ip, port=int(sys_cfg.get("PORT", 56400)))


def enabled_systems(systems: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: cfg
        for name, cfg in systems.items()
        if cfg.get("ENABLED", True)
    }


def prepare_incoming_config(
    loader: YamlConfigLoader,
    config_path: str,
    log: logging.Logger,
) -> dict[str, Any]:
    """Load YAML and apply the same normalizers as startup (including GENERATOR expand)."""
    incoming = loader.load(config_path)
    apply_talker_alias_defaults(incoming)
    expand_generator(incoming, log)
    ensure_system_runtime_config(incoming)
    normalize_peer_config(incoming)
    normalize_obp_config(incoming)
    return incoming


def merge_system_config(old_cfg: dict[str, Any], new_cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply new system settings while keeping live runtime state (PEERS, STATS, options/static TGs)."""
    merged = copy.deepcopy(new_cfg)
    mode = merged.get("MODE")
    if mode == "MASTER":
        merged["PEERS"] = old_cfg.get("PEERS", {})
        for key in (
            "OPTIONS",
            "TS1_STATIC",
            "TS2_STATIC",
            "DEFAULT_UA_TIMER",
            "_options_static_apply_fp",
            "_default_options",
        ):
            if key in old_cfg:
                merged[key] = old_cfg[key]
    elif mode == "PEER":
        stats = old_cfg.get("STATS")
        if isinstance(stats, dict):
            merged["STATS"] = stats
    return merged


def merge_top_level_config(config: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Update GLOBAL / REPORTS / ALIASES / LOGGER in the live config dict."""
    kill_flag = config.get("GLOBAL", {}).get("_KILL_SERVER")
    for key in ("GLOBAL", "REPORTS", "ALIASES", "LOGGER"):
        if key not in incoming:
            continue
        config[key] = copy.deepcopy(incoming[key])
    if kill_flag is not None:
        config.setdefault("GLOBAL", {})["_KILL_SERVER"] = kill_flag
    for rk in _RUNTIME_TOP_KEYS:
        if rk in config:
            continue
        if rk in incoming:
            config[rk] = incoming[rk]


@dataclass
class ReloadResult:
    added: list[str]
    removed: list[str]
    updated: list[str]
    rebound: list[str]


def reload_server_config(
    config: dict[str, Any],
    config_path: str,
    loader: YamlConfigLoader,
    protocols: dict[str, Any],
    transports: dict[str, Any],
    *,
    create_protocol: Callable[[str], Any],
    listen_udp: Callable[[str, BindSpec, Any], Any],
    stop_listener: Callable[[Any], None],
    on_systems_changed: Callable[[], None] | None = None,
    on_system_removed: Callable[[str, Any], None] | None = None,
    log: logging.Logger | None = None,
) -> ReloadResult:
    """
    Re-read adn-server.yaml, diff SYSTEMS, start/stop UDP listeners.

    Preserves PEERS / STATS and protocol STATUS for systems that stay up with the
    same bind address. Runs on the Twisted reactor thread.
    """
    log = log or logger
    try:
        incoming = prepare_incoming_config(loader, config_path, log)
    except ConfigError as e:
        log.error("(CONFIG-RELOAD) failed to load config: %s", e)
        raise
    except Exception as e:
        log.error("(CONFIG-RELOAD) failed to prepare config: %s", e)
        raise

    merge_top_level_config(config, incoming)
    if "LOGGER" in incoming:
        level_name = reapply_log_level(config.get("LOGGER", {}))
        log.info("(CONFIG-RELOAD) LOG_LEVEL applied: %s", level_name)

    old_systems = dict(config.get("SYSTEMS", {}))
    new_systems = incoming.get("SYSTEMS", {})
    old_enabled = set(enabled_systems(old_systems))
    new_enabled = set(enabled_systems(new_systems))

    added: list[str] = []
    removed: list[str] = []
    updated: list[str] = []
    rebound: list[str] = []

    for name in sorted(old_enabled - new_enabled):
        port = transports.pop(name, None)
        proto = protocols.pop(name, None)
        if proto is not None and on_system_removed:
            on_system_removed(name, proto)
        if proto is not None:
            try:
                proto.dereg()
            except Exception as e:
                log.warning("(CONFIG-RELOAD) dereg %s: %s", name, e)
        if port is not None:
            stop_listener(port)
        config.get("SYSTEMS", {}).pop(name, None)
        removed.append(name)
        log.info("(CONFIG-RELOAD) removed system %s", name)

    for name in sorted(new_enabled - old_enabled):
        sys_cfg = copy.deepcopy(new_systems[name])
        config.setdefault("SYSTEMS", {})[name] = sys_cfg
        proto = create_protocol(name)
        bind = bind_spec(sys_cfg)
        transports[name] = listen_udp(name, bind, proto)
        protocols[name] = proto
        added.append(name)
        log.info("(CONFIG-RELOAD) added system %s on %s:%s", name, bind.ip, bind.port)

    for name in sorted(old_enabled & new_enabled):
        old_cfg = old_systems[name]
        new_cfg = new_systems[name]
        old_bind = bind_spec(old_cfg)
        new_bind = bind_spec(new_cfg)
        merged = merge_system_config(old_cfg, new_cfg)
        config["SYSTEMS"][name] = merged
        proto = protocols.get(name)
        if proto is None:
            proto = create_protocol(name)
            transports[name] = listen_udp(name, new_bind, proto)
            protocols[name] = proto
            added.append(name)
            log.info("(CONFIG-RELOAD) started missing listener %s on %s:%s", name, new_bind.ip, new_bind.port)
            continue
        if hasattr(proto, "apply_system_config"):
            proto.apply_system_config(config)
        if old_bind != new_bind:
            port = transports.get(name)
            if port is not None:
                stop_listener(port)
            transports[name] = listen_udp(name, new_bind, proto)
            rebound.append(name)
            log.info(
                "(CONFIG-RELOAD) rebound %s %s:%s -> %s:%s",
                name, old_bind.ip, old_bind.port, new_bind.ip, new_bind.port,
            )
        else:
            updated.append(name)
            log.debug("(CONFIG-RELOAD) updated system %s (bind unchanged)", name)

    for name in sorted(set(old_systems) - old_enabled):
        if name not in new_systems:
            config.get("SYSTEMS", {}).pop(name, None)

    if on_systems_changed and (added or removed or updated or rebound):
        on_systems_changed()

    log.info(
        "(CONFIG-RELOAD) complete: +%s -%s updated=%s rebound=%s",
        len(added), len(removed), len(updated), len(rebound),
    )
    return ReloadResult(added=added, removed=removed, updated=updated, rebound=rebound)
