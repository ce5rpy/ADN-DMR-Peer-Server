"""Extract peer_id from Homebrew packets (legacy ``adn_proxy.application.packet_commands``)."""

from __future__ import annotations

# Homebrew command prefixes (wire vocabulary; no I/O)
_DMRD = b"DMRD"
_DMRA = b"DMRA"
_MSTC = b"MSTC"
_MSTN = b"MSTN"
_MSTP = b"MSTP"
_RPTA = b"RPTA"
_RPTCL = b"RPTCL"
_RPTK = b"RPTK"
_RPTL = b"RPTL"
_RPTC = b"RPTC"
_RPTO = b"RPTO"
_RPTP = b"RPTP"


def peer_id_from_packet(data: bytes, *, from_master: bool) -> bytes | None:
    """Return 4-byte peer_id from packet payload, or None if not applicable."""
    if len(data) < 8:
        return None
    command = data[:4]
    if from_master:
        if command == _DMRD and len(data) >= 15:
            return data[11:15]
        if command == _RPTA and len(data) >= 10:
            return data[6:10]
        if command == _MSTN and len(data) >= 10:
            return data[6:10]
        if command == _MSTP and len(data) >= 11:
            return data[7:11]
        if command == _MSTC and len(data) >= 9:
            return data[5:9]
        return None
    if command == _DMRD and len(data) >= 15:
        return data[11:15]
    if command in (_DMRA, _RPTL, _RPTK, _RPTO) and len(data) >= 8:
        return data[4:8]
    if command == _RPTC:
        if len(data) >= 5 and data[:5] == _RPTCL:
            return data[5:9] if len(data) >= 9 else None
        return data[4:8] if len(data) >= 8 else None
    if command == _RPTP and len(data) >= 11:
        return data[7:11]
    return None
