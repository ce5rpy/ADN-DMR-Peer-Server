# ADN DMR Peer Server - application ports
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""Abstract ports (interfaces) for infrastructure adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ConfigLoader(ABC):
    """Load and validate config (YAML at project root). Returns same semantic structure as legacy INI."""

    @abstractmethod
    def load(self, path: str | None = None) -> dict[str, Any]:
        """Load config; path None = default (project root adn-server.yaml)."""
        ...

    @abstractmethod
    def reload_voice_config(self, config: dict[str, Any]) -> None:
        """Reload voice/announcement config from main config file (optional second arg: path)."""
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


class ReportSender(ABC):
    """Send config and bridge state to report TCP clients (CONFIG_SND, BRIDGE_SND, BRDG_EVENT)."""

    @abstractmethod
    def send_config(self, systems: dict[str, Any]) -> None:
        """Send CONFIG_SND (pickle systems)."""
        ...

    @abstractmethod
    def send_bridge(self, bridges: dict[str, Any]) -> None:
        """Send BRIDGE_SND (pickle bridges)."""
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
    def ensure_tts_ambe(self, text: str, lang: str, out_path: str, config: dict[str, Any]) -> str | None:
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
