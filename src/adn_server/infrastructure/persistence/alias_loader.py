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
import shutil
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
        peer_ids = self._load_id_dict_with_backup(
            path, peer_file, checksums.get("peer_ids"), "peer_ids",
        )
        subscriber_ids = self._load_id_dict_with_backup(
            path, sub_file, checksums.get("subscriber_ids"), "subscriber_ids",
        )
        talkgroup_ids = self._load_id_dict_with_backup(
            path, tgid_file, checksums.get("talkgroup_ids"), "talkgroup_ids",
        )
        local_subscriber_ids = self._load_id_json(
            path / aliases.get("LOCAL_SUBSCRIBER_FILE", "subscriber_ids.json")
        )
        server_ids = self._load_server_tsv_with_backup(
            path, server_file, checksums.get("server_ids"),
        )
        return (peer_ids, subscriber_ids, talkgroup_ids, local_subscriber_ids, server_ids, checksums)

    @staticmethod
    def merge_reload_into_config(
        config: dict[str, Any],
        alias_loader: AliasLoader,
        peer_ids: dict[int, str],
        subscriber_ids: dict[int, str],
        talkgroup_ids: dict[int, str],
        local_subscriber_ids: dict[int, str],
        server_ids: dict[str, str],
        checksums: dict[str, str],
    ) -> None:
        """Apply alias reload without wiping in-memory tables on partial download failure."""
        def _keep(key: str, new_val: dict, label: str) -> None:
            if new_val:
                config[key] = new_val
            elif config.get(key):
                logger.warning(
                    "(ALIAS) reload kept previous %s (%d entries)",
                    label,
                    len(config[key]),
                )

        _keep("_PEER_IDS", peer_ids, "peer_ids")
        if subscriber_ids:
            sub = dict(subscriber_ids)
            sub[900999] = "D-APRS"
            sub[4294967295] = "SC"
            config["_SUB_IDS"] = sub
            if isinstance(alias_loader, DefaultAliasLoader):
                config["_SUB_PROFILES"] = alias_loader.load_subscriber_profiles(config)
        elif config.get("_SUB_IDS"):
            logger.warning(
                "(ALIAS) reload kept previous subscriber_ids (%d entries)",
                len(config["_SUB_IDS"]),
            )
        _keep("_TG_IDS", talkgroup_ids, "talkgroup_ids")
        _keep("_LOCAL_SUBSCRIBER_IDS", local_subscriber_ids, "local_subscriber_ids")
        _keep("_SERVER_IDS", server_ids, "server_ids")
        if checksums:
            config["CHECKSUMS"] = checksums

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

    def _load_id_dict_with_backup(
        self,
        path: Path,
        file_name: str,
        expected_checksum: str | None,
        name: str,
    ) -> dict[int, str]:
        """Legacy mk_aliases peer/subscriber/tgid load with .bak fallback."""
        full = path / file_name
        bak = path / f"{file_name}.bak"
        result: dict[int, str] = {}
        loaded_from_primary = False

        def _load_verified(target: Path) -> dict[int, str]:
            if not target.is_file():
                return {}
            if expected_checksum:
                if _blake2bsum(target) != expected_checksum:
                    raise ValueError("bad checksum")
            loaded = self._load_id_json(target)
            if not loaded:
                raise ValueError("empty or invalid dictionary data")
            return loaded

        try:
            result = _load_verified(full)
            loaded_from_primary = True
        except Exception as e:
            logger.error(
                "(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of %s file. not updating.: %s",
                name,
                e,
            )
            if bak.is_file():
                try:
                    result = self._load_id_json(bak)
                except Exception as f:
                    logger.error(
                        "(ALIAS) ID ALIAS MAPPER: Tried backup %s file, but couldn't load that either: %s",
                        name,
                        f,
                    )
        if result:
            logger.info("(ALIAS) ID ALIAS MAPPER: %s dictionary is available", name)
        if loaded_from_primary and full.is_file():
            try:
                shutil.copy(full, bak)
            except OSError as g:
                logger.info(
                    "(ALIAS) ID ALIAS MAPPER: couldn't make backup copy of %s file %s",
                    name,
                    g,
                )
        return result

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

    def _load_server_tsv_with_backup(
        self,
        path: Path,
        file_name: str,
        expected_checksum: str | None,
    ) -> dict[str, str]:
        """Legacy mk_aliases server_ids load with .bak fallback."""
        full = path / file_name
        bak = path / f"{file_name}.bak"
        result: dict[str, str] = {}
        loaded_from_primary = False

        try:
            if expected_checksum and full.is_file():
                if _blake2bsum(full) != expected_checksum:
                    raise ValueError("bad checksum")
            result = self._load_server_tsv(path, file_name)
            if full.is_file() and not result:
                raise ValueError("empty server_ids")
            loaded_from_primary = bool(result)
        except Exception as e:
            logger.error(
                "(ALIAS) ID ALIAS MAPPER: problem with blake2bsum of server_ids file: %s",
                e,
            )
            if bak.is_file():
                try:
                    result = self._load_server_tsv(path, f"{file_name}.bak")
                except Exception as f:
                    logger.error(
                        "(ALIAS) ID ALIAS MAPPER: Tried backup server_ids file, but couldn't load that either: %s",
                        f,
                    )
        if result:
            logger.info("(ALIAS) ID ALIAS MAPPER: server_ids dictionary is available")
        if loaded_from_primary and full.is_file():
            try:
                shutil.copy(full, bak)
            except OSError as g:
                logger.info(
                    "(ALIAS) ID ALIAS MAPPER: couldn't make backup copy of server_ids file %s",
                    g,
                )
        return result

    def load_subscriber_profiles(self, config: dict[str, Any]) -> dict[int, dict[str, str]]:
        """Load {id: {callsign, fname, surname, talker_alias?}} from subscriber JSON files."""
        aliases = config.get("ALIASES", {})
        path = Path(aliases.get("PATH", "./data/")).resolve()
        sub_file = aliases.get("SUBSCRIBER_FILE", "subscriber_ids.json")
        local_file = aliases.get("LOCAL_SUBSCRIBER_FILE", "subscriber_ids.json")
        profiles: dict[int, dict[str, str]] = {}
        for file_name in (sub_file, local_file):
            self._merge_subscriber_profiles(path / file_name, profiles)
        return profiles

    def _merge_subscriber_profiles(self, file_path: Path, out: dict[int, dict[str, str]]) -> None:
        if not file_path.is_file():
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        if "count" in data:
            data = {k: v for k, v in data.items() if k != "count"}
        for _key, val in data.items():
            if not isinstance(val, list):
                continue
            for record in val:
                if not isinstance(record, dict) or "id" not in record:
                    continue
                try:
                    rid = int(record["id"])
                except (ValueError, TypeError):
                    continue
                entry: dict[str, str] = {}
                if record.get("callsign"):
                    entry["callsign"] = str(record["callsign"])
                if record.get("fname"):
                    entry["fname"] = str(record["fname"])
                if record.get("surname"):
                    entry["surname"] = str(record["surname"])
                if record.get("talker_alias"):
                    entry["talker_alias"] = str(record["talker_alias"])
                if entry:
                    prev = out.get(rid, {})
                    prev.update(entry)
                    out[rid] = prev
