"""Wire packets for proxy session teardown (legacy reaper parity)."""

from __future__ import annotations

# Homebrew command prefixes (wire vocabulary; no I/O)
_MSTCL = b"MSTCL"
_RPTCL = b"RPTCL"

CLIENT_TEARDOWN_REPEAT = 3


def master_teardown_packet(peer_id: bytes) -> bytes:
    return _RPTCL + peer_id


def client_teardown_packet() -> bytes:
    return _MSTCL
