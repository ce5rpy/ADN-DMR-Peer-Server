"""No-op self-service store when ``SELF_SERVICE.USE_SELFSERVICE`` is false."""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import ProxySelfServiceStore


class NullProxySelfServiceStore(ProxySelfServiceStore):
    """Disabled self-service: all methods are no-ops."""

    def test_db(self) -> Any:
        from twisted.internet.defer import succeed

        return succeed(True)

    def ins_conf(
        self,
        int_id: int,
        peer_id_bytes: bytes,
        callsign: str,
        host: str,
        mode: str,
    ) -> None:
        pass

    def updt_tbl(
        self,
        action: str,
        peer_id_bytes: bytes,
        *,
        psswd: str | None = None,
    ) -> None:
        pass

    def slct_opt(self, peer_id_bytes: bytes) -> Any:
        from twisted.internet.defer import succeed

        return succeed([])

    def slct_db(self) -> Any:
        from twisted.internet.defer import succeed

        return succeed([])

    def updt_lstseen(self, dmrid_list: list[tuple[bytes, ...]]) -> None:
        pass

    def clean_tbl(self) -> Any:
        from twisted.internet.defer import succeed

        return succeed(None)
