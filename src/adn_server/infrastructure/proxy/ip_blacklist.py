"""In-memory IP blacklist for proxy fan-in."""

from __future__ import annotations

from adn_server.application.ports import ProxyIpBlacklist


class InMemoryProxyIpBlacklist(ProxyIpBlacklist):
    def __init__(self, initial: dict[str, float] | None = None) -> None:
        self._entries: dict[str, float] = dict(initial or {})

    def block_until(self, host: str, expire_at: float) -> None:
        self._entries[host] = expire_at

    def is_blocked(self, host: str, now: float) -> bool:
        expire = self._entries.get(host)
        return expire is not None and now < expire

    def merge_static_entries(self, entries: dict[str, float]) -> None:
        """Apply config IP_BLACK_LIST entries (runtime PRBL blocks are kept)."""
        self._entries.update(entries)
