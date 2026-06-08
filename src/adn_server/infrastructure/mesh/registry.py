"""Registry for built-in mesh codecs (``MESH_PROTOCOL``: auto, dmre_v5, obp_v1)."""

from __future__ import annotations

from adn_server.application.ports import PeerTransport
from adn_server.domain.mesh_routing import MeshEgress, MeshIngress, PeerMeshConfig
from adn_server.infrastructure.mesh.transports import default_peer_transports


class MeshCodecRegistry:
    """Resolve encode/decode codec by name or auto-detect from wire layout."""

    def __init__(self, transports: dict[str, PeerTransport] | None = None) -> None:
        self._transports = dict(transports or default_peer_transports())

    def get(self, name: str) -> PeerTransport | None:
        return self._transports.get(name)

    def decode_auto(self, datagram: bytes, config: PeerMeshConfig) -> MeshIngress | None:
        """Try DMRE first, then DMRD v1 (legacy OPENBRIDGE branch order)."""
        for name in ("dmre_v5", "obp_v1"):
            transport = self._transports.get(name)
            if transport is None:
                continue
            ingress = transport.try_decode(datagram, config)
            if ingress is not None:
                return ingress
        return None

    def encode(
        self,
        mesh_protocol: str,
        egress: MeshEgress,
        config: PeerMeshConfig,
        *,
        session_codec: str | None = None,
    ) -> bytes | None:
        codec = self.resolve_encode_codec(mesh_protocol, config, session_codec=session_codec)
        transport = self._transports.get(codec)
        if transport is None:
            return None
        return transport.encode(egress, config)

    def resolve_encode_codec(
        self,
        mesh_protocol: str,
        config: PeerMeshConfig,
        *,
        session_codec: str | None = None,
    ) -> str:
        if mesh_protocol != "auto":
            return mesh_protocol
        if session_codec:
            return session_codec
        if config.wire_ver is not None and config.wire_ver >= 4:
            return "dmre_v5"
        return "obp_v1"
