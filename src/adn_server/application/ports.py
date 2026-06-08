# ADN DMR Peer Server - application ports
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

"""Abstract ports (interfaces) for infrastructure adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol


class ConfigLoader(ABC):
    """Load and validate config (YAML at project root). Returns same semantic structure as legacy INI."""

    @abstractmethod
    def load(self, path: str | None = None) -> dict[str, Any]:
        """Load config; path None = default (project root adn-server.yaml)."""
        ...

    @abstractmethod
    def reload_voice_config(self, config: dict[str, Any], voice_path: str | None = None) -> None:
        """Hot-reload adn-voice.yaml into config["VOICE"]."""
        ...


class AliasLoader(ABC):
    """Load and refresh alias dicts (peer_ids, subscriber_ids, talkgroup_ids, server_ids, checksums)."""

    @abstractmethod
    def load_aliases(self, config: dict[str, Any]) -> tuple[
        dict[int, str],  # peer_ids
        dict[int, str],  # subscriber_ids
        dict[int, str],  # talkgroup_ids
        dict[int, str],  # local_subscriber_ids
        dict[str, str],  # server_ids
        dict[str, str],  # checksums
    ]:
        """Build alias dicts from config (downloads + files). Same as legacy mk_aliases."""
        ...


class SubMapStore(ABC):
    """Persist and load SUB_MAP (bytes_3(peer) -> (callsign, slot, time))."""

    @abstractmethod
    def load(self, path: str) -> dict[bytes, tuple[str, int, float]]:
        """Load SUB_MAP from pickle file."""
        ...

    @abstractmethod
    def save(self, path: str, sub_map: dict[bytes, tuple[str, int, float]]) -> None:
        """Save SUB_MAP to pickle file."""
        ...


class KeysStore(ABC):
    """Load/save keys JSON (e.g. system API key)."""

    @abstractmethod
    def load(self, path: str) -> dict[str, Any]:
        """Load keys from JSON."""
        ...

    @abstractmethod
    def save(self, path: str, keys: dict[str, Any]) -> None:
        """Save keys to JSON."""
        ...


class ReportWireEncoder(ABC):
    """Outbound port: encode one report protocol variant into zero or more TCP frames."""

    @abstractmethod
    def hello_frames(self, systems: dict[str, Any]) -> tuple[bytes, ...]:
        """HELLO (0xFF) frame(s) for this variant."""
        ...

    @abstractmethod
    def config_frames(self, systems: dict[str, Any], *, full_snapshot: bool) -> tuple[bytes, ...]:
        """CONFIG_SND / TOPOLOGY_SND / delta frames (empty if nothing to send)."""
        ...

    @abstractmethod
    def bridge_frames(self, bridges: dict[str, Any], *, full_snapshot: bool) -> tuple[bytes, ...]:
        """BRIDGE_SND / ROUTING_TABLE_SND / delta frames."""
        ...

    @abstractmethod
    def bridge_event_frames(self, event: str) -> tuple[bytes, ...]:
        """BRDG_EVENT / VOICE_EVENT_SND frames."""
        ...


class ReportSender(ABC):
    """Send config and bridge state to report TCP clients (CONFIG_SND, BRIDGE_SND, BRDG_EVENT)."""

    @abstractmethod
    def send_config(self, systems: dict[str, Any], *, incremental: bool = False) -> None:
        """Send CONFIG_SND (pickle systems) or topology / delta JSON."""
        ...

    @abstractmethod
    def send_bridge(self, bridges: dict[str, Any], *, incremental: bool = False) -> None:
        """Send BRIDGE_SND (pickle bridges) or routing_table / delta JSON."""
        ...

    @abstractmethod
    def send_bridge_event(self, event: str) -> None:
        """Send BRDG_EVENT (opcode + event string)."""
        ...


class BridgeRouter(ABC):
    """Query and update BRIDGES (conference bridge state). Used by rule_timer, make_single_bridge, etc."""

    @abstractmethod
    def get_bridges(self) -> dict[str, list[dict[str, Any]]]:
        """Return current BRIDGES dict (key = TGID or #reflector)."""
        ...

    @abstractmethod
    def set_bridges(self, bridges: dict[str, list[dict[str, Any]]]) -> None:
        """Replace BRIDGES (e.g. after rule_timer or make_single_bridge)."""
        ...

    @abstractmethod
    def rebuild_source_index(self) -> None:
        """Rebuild index of ACTIVE source rows by (system, TS, dst_tgid)."""
        ...

    @abstractmethod
    def bridge_tables_with_active_source(self, system: str, ts: int, dst_tgid: int) -> list[str]:
        """Return bridge table names with matching ACTIVE source (legacy full-scan parity)."""
        ...

    @abstractmethod
    def acl_check(self, id_bytes_or_int: bytes | int, acl: tuple[bool, list[tuple[int, int]]]) -> bool:
        """Check ID against ACL; return True if permitted."""
        ...


class VoiceProvider(ABC):
    """AMBE voice packets, file announcements, TTS. Used for announcements and playback."""

    @abstractmethod
    def get_ambe_words(self, languages: str, audio_path: str) -> dict[str, dict[str, Any]]:
        """Load AMBE words by language (readAMBE.readfiles)."""
        ...

    @abstractmethod
    def pkt_gen(self, rf_src: bytes, dst_id: bytes, peer: bytes, slot: int, phrase: list[Any]) -> Any:
        """Generate HBP voice packets for a phrase (generator). Legacy mk_voice.pkt_gen."""
        ...

    @abstractmethod
    def ensure_tts_ambe(self, config: dict[str, Any], item: dict[str, Any], audio_path: str) -> str | None:
        """TTS to AMBE file; return path or None. Legacy tts_engine.ensure_tts_ambe."""
        ...

    def read_single_file(self, audio_path: str, lang: str, file_number: str) -> list:
        """Read one AMBE file (e.g. ondemand/{file_number}.ambe). Legacy readSingleFile for playFileOnRequest."""
        return []


class SecurityDownloader(ABC):
    """Periodic security downloads (passwords, encryption). Legacy security_downloader."""

    @abstractmethod
    def init_downloads(self, config: dict[str, Any]) -> None:
        """One-time init (e.g. create dirs)."""
        ...

    @abstractmethod
    def periodic_download(self, config: dict[str, Any]) -> None:
        """Periodic password/encryption download."""
        ...


class DmrEmbeddedLcEncoder(Protocol):
    """Encode a 9-byte DMR embedded LC into burst B–E BPTC fragments (vseq 1–4)."""

    def __call__(self, lc: bytes) -> dict[int, Any]:
        ...


class TalkerAliasEmblcEncoder(Protocol):
    """Encode Talker Alias into embedded-LC burst dicts for DMRD overlay."""

    def encode_text(
        self,
        text: str,
        *,
        text_formats: Sequence[str] | None = None,
    ) -> tuple[list[dict[int, Any]], int]:
        ...

    def encode_blocks(self, blocks: dict[int, bytes]) -> tuple[list[dict[int, Any]], int]:
        ...
