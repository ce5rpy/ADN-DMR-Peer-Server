# ADN DMR Peer Server - alias loader
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

"""Load alias dicts (peer_ids, subscriber_ids, talkgroup_ids, etc.). Legacy mk_aliases."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from ...application.ports import AliasLoader

logger = logging.getLogger(__name__)


def try_download(path: Path, file_name: str, url: str, stale_sec: float) -> str:
    """Legacy try_download: download file from url if missing or older than stale_sec. Returns result message."""
    if not url:
        return f"ID ALIAS MAPPER: '{file_name}' URL empty, not downloaded"
    full = path / file_name
    now = time.time()
    file_exists = full.is_file()
    if file_exists:
        file_old = (full.stat().st_mtime + stale_sec) < now
    else:
        file_old = True
    if not file_old and file_exists:
        return f"ID ALIAS MAPPER: '{file_name}' is current, not downloaded"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(url, context=ctx, timeout=30) as response:
            data = response.read()
    except OSError as e:
        return f"ID ALIAS MAPPER: '{file_name}' could not be downloaded due to an IOError: {e}"
    if not data or data == b"{}":
        return f"ID ALIAS MAPPER: '{file_name}' file not written because downloaded data is empty"
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
    except OSError as e:
        return f"ID ALIAS mapper '{file_name}' file could not be written: {e}"
    return f"ID ALIAS MAPPER: '{file_name}' successfully downloaded"


def _blake2bsum(file_path: Path) -> str:
    """Blake2b hex digest of file (legacy blake2bsum)."""
    h = hashlib.blake2b()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


class DefaultAliasLoader(AliasLoader):
    """Load aliases from JSON files and optional downloads. Legacy mk_aliases."""

    def load_aliases(
        self,
        config: dict[str, Any],
    ) -> tuple[
        dict[int, str],
        dict[int, str],
        dict[int, str],
        dict[int, str],
        dict[str, str],
        dict[str, str],
    ]:
        """Build alias dicts. Same order as legacy mk_aliases."""
        aliases = config.get("ALIASES", {})
        path = Path(aliases.get("PATH", "./data/")).resolve()
        stale_sec = float(aliases.get("STALE_TIME", aliases.get("STALE_DAYS", 1) * 86400))
        if aliases.get("TRY_DOWNLOAD"):
            if aliases.get("CHECKSUM_FILE") and aliases.get("CHECKSUM_URL"):
                result = try_download(path, aliases["CHECKSUM_FILE"], aliases.get("CHECKSUM_URL", ""), stale_sec)
                logger.info("(ALIAS) %s", result)
            for key, url_key in [
                ("PEER_FILE", "PEER_URL"),
                ("SUBSCRIBER_FILE", "SUBSCRIBER_URL"),
                ("TGID_FILE", "TGID_URL"),
                ("SERVER_ID_FILE", "SERVER_ID_URL"),
            ]:
                url = aliases.get(url_key)
                if url and aliases.get(key):
                    result = try_download(path, aliases[key], url, stale_sec)
                    logger.info("(ALIAS) %s", result)
        checksums = self._load_checksums(path, aliases.get("CHECKSUM_FILE"))
        peer_file = aliases.get("PEER_FILE", "peer_ids.json")
        sub_file = aliases.get("SUBSCRIBER_FILE", "subscriber_ids.json")
        tgid_file = aliases.get("TGID_FILE", "talkgroup_ids.json")
        server_file = aliases.get("SERVER_ID_FILE", "server_ids.tsv")
        peer_ids = self._load_id_json_verified(path / peer_file, checksums.get("peer_ids"), "peer_ids")
        subscriber_ids = self._load_id_json_verified(path / sub_file, checksums.get("subscriber_ids"), "subscriber_ids")
        talkgroup_ids = self._load_id_json_verified(path / tgid_file, checksums.get("talkgroup_ids"), "talkgroup_ids")
        local_subscriber_ids = self._load_id_json(
            path / aliases.get("LOCAL_SUBSCRIBER_FILE", "subscriber_ids.json")
        )
        server_ids = self._load_server_tsv_verified(path, server_file, checksums.get("server_ids"))
        if server_ids:
            logger.info("(ALIAS) ID ALIAS MAPPER: server_ids dictionary is available")
        return (peer_ids, subscriber_ids, talkgroup_ids, local_subscriber_ids, server_ids, checksums)

    def _load_checksums(self, path: Path, file_name: str | None) -> dict[str, str]:
        """Load checksum JSON (legacy load_json of CHECKSUM_FILE). Keys e.g. peer_ids, subscriber_ids, talkgroup_ids, server_ids."""
        if not file_name:
            return {}
        full = path / file_name
        if not full.is_file():
            return {}
        try:
            with open(full, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("(ALIAS) ID ALIAS MAPPER: Cannot load checksums: %s", e)
            return {}
        return dict(data) if isinstance(data, dict) else {}

    def _load_server_tsv(self, path: Path, file_name: str) -> dict[str, str]:
        """Legacy mk_server_dict: TSV with 'OPB Net ID' -> 'Country'."""
        full = path / file_name
        if not full.is_file():
            return {}
        try:
            with open(full, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, dialect="excel-tab")
                out: dict[str, str] = {}
                for row in reader:
                    net_id = row.get("OPB Net ID", "").strip()
                    country = row.get("Country", "").strip()
                    if net_id:
                        out[net_id] = country
                return out
        except Exception as err:
            logger.warning("(ALIAS) ID ALIAS MAPPER: %s could not be read: %s", file_name, err)
            return {}

    def _load_id_json_verified(
        self, file_path: Path, expected_checksum: str | None, name: str
    ) -> dict[int, str]:
        """Load ID JSON; if expected_checksum given, verify blake2b first (legacy)."""
        if not file_path.is_file():
            return {}
        if expected_checksum:
            try:
                if _blake2bsum(file_path) != expected_checksum:
                    logger.error("(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of %s file. not updating.", name)
                    return {}
            except Exception as e:
                logger.error("(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of %s file: %s", name, e)
                return {}
        return self._load_id_json(file_path)

    def _load_id_json(self, file_path: Path) -> dict[int, str]:
        """Load JSON with 'id' -> 'callsign' structure; return {int(id): callsign}."""
        if not file_path.is_file():
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict) or "count" in data:
            if isinstance(data, dict) and "count" in data:
                del data["count"]
        out: dict[int, str] = {}
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list):
                    for record in val:
                        if isinstance(record, dict) and "id" in record and "callsign" in record:
                            try:
                                out[int(record["id"])] = str(record["callsign"])
                            except (ValueError, TypeError):
                                pass
        return out

    def _load_server_tsv_verified(
        self, path: Path, file_name: str, expected_checksum: str | None
    ) -> dict[str, str]:
        """Load server_ids TSV; if expected_checksum given, verify blake2b first (legacy)."""
        full = path / file_name
        if not full.is_file():
            return {}
        if expected_checksum:
            try:
                if _blake2bsum(full) != expected_checksum:
                    logger.error("(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of server_ids file: not updating.")
                    return {}
            except Exception as e:
                logger.error("(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of server_ids file: %s", e)
                return {}
        return self._load_server_tsv(path, file_name)
