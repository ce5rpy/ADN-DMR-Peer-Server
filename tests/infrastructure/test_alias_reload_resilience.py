# ADN DMR Peer Server - alias reload resilience when selfcare download fails

from __future__ import annotations

import json
from pathlib import Path

from adn_server.infrastructure.persistence.alias_loader import DefaultAliasLoader, try_download


def _write_subscriber_file(path: Path, file_name: str, rid: int, callsign: str) -> None:
    data = {"subscribers": [{"id": rid, "callsign": callsign}]}
    (path / file_name).write_text(json.dumps(data), encoding="utf-8")


def test_try_download_failure_does_not_erase_existing_file(tmp_path: Path) -> None:
    file_name = "subscriber_ids.json"
    full = tmp_path / file_name
    full.write_bytes(b'{"subscribers":[{"id":7300391,"callsign":"CE5RPY"}]}')
    # stale_sec=0 forces download attempt; bad URL simulates selfcare down
    result = try_download(tmp_path, file_name, "http://127.0.0.1:1/nope.json", stale_sec=0)
    assert "could not be downloaded" in result or "IOError" in result
    assert full.read_bytes().startswith(b"{")


def test_merge_reload_keeps_previous_sub_ids_on_empty_reload() -> None:
    loader = DefaultAliasLoader()
    config = {
        "_SUB_IDS": {7300391: "CE5RPY"},
        "_PEER_IDS": {730039101: "CE5RPY"},
        "ALIASES": {"PATH": "."},
    }
    DefaultAliasLoader.merge_reload_into_config(
        config,
        loader,
        {},
        {},
        {},
        {},
        {},
        {},
    )
    assert config["_SUB_IDS"] == {7300391: "CE5RPY"}
    assert config["_PEER_IDS"] == {730039101: "CE5RPY"}


def test_load_id_dict_with_backup_uses_bak_on_checksum_mismatch(tmp_path: Path) -> None:
    loader = DefaultAliasLoader()
    file_name = "subscriber_ids.json"
    _write_subscriber_file(tmp_path, file_name, 1111111, "BAD")
    _write_subscriber_file(tmp_path, f"{file_name}.bak", 7300391, "GOOD")
    loaded = loader._load_id_dict_with_backup(
        tmp_path,
        file_name,
        "deadbeef",
        "subscriber_ids",
    )
    assert loaded.get(7300391) == "GOOD"
