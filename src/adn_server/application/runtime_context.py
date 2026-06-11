# ADN DMR Peer Server - runtime context holder
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Runtime config container and atomic pointer swap on SIGHUP reload."""

from __future__ import annotations

import copy
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeContext:
    """Live server configuration and related metadata."""

    config: dict[str, Any]
    config_path: str = ""
    subscription_store: Any = None


class RuntimeContextHolder:
    """Thread-local holder for the active RuntimeContext (swap on SIGHUP reload)."""

    def __init__(self, initial: RuntimeContext) -> None:
        self._ctx = initial

    def get(self) -> RuntimeContext:
        return self._ctx

    def swap(self, ctx: RuntimeContext) -> RuntimeContext:
        """Replace the active context; returns the previous context."""
        previous = self._ctx
        self._ctx = ctx
        return previous


class ConfigProxy(MutableMapping[str, Any]):
    """Dict-like view that always reads/writes the holder's current config dict."""

    def __init__(self, holder: RuntimeContextHolder) -> None:
        self._holder = holder

    def _cfg(self) -> dict[str, Any]:
        return self._holder.get().config

    def __getitem__(self, key: str) -> Any:
        return self._cfg()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._cfg()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._cfg()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._cfg())

    def __len__(self) -> int:
        return len(self._cfg())

    def __contains__(self, key: object) -> bool:
        return key in self._cfg()

    def get(self, key: str, default: Any = None) -> Any:
        return self._cfg().get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._cfg().setdefault(key, default)

    def pop(self, key: str, *default: Any) -> Any:
        return self._cfg().pop(key, *default)

    def keys(self) -> Any:
        return self._cfg().keys()

    def values(self) -> Any:
        return self._cfg().values()

    def items(self) -> Any:
        return self._cfg().items()

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._cfg().update(*args, **kwargs)


def prepare_reload_config(holder: RuntimeContextHolder) -> dict[str, Any]:
    """
    Build a working copy for SIGHUP reload.

    The live ``_SUB_MAP`` object is shared so subscriber state is not duplicated.
    On failure the holder is unchanged; on success call ``swap`` with the merged dict.
    """
    live = holder.get().config
    sub_map = live.get("_SUB_MAP")
    new_config = copy.deepcopy(live)
    if sub_map is not None:
        new_config["_SUB_MAP"] = sub_map
    return new_config


def swap_runtime_config(
    holder: RuntimeContextHolder,
    new_config: dict[str, Any],
    *,
    config_path: str | None = None,
) -> RuntimeContext:
    """Atomically install a reloaded config dict."""
    previous = holder.get()
    path = config_path if config_path is not None else previous.config_path
    return holder.swap(
        RuntimeContext(
            config=new_config,
            config_path=path,
            subscription_store=previous.subscription_store,
        )
    )
