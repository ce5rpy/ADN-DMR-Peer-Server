# ADN DMR Peer Server - user passwords loader keeps cache on bad reload

from __future__ import annotations

import json
from pathlib import Path

from adn_server.infrastructure.security.user_passwords_loader import UserPasswordsLoader


def test_load_keeps_cached_passwords_when_file_becomes_invalid(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pw_file = data_dir / "user_passwords.json"
    pw_file.write_text(
        json.dumps({"passwords": {"7300391": "enc"}}),
        encoding="utf-8",
    )
    loader = UserPasswordsLoader(str(tmp_path))
    config = {
        "ALIASES": {"PATH": "data/"},
        "GLOBAL": {"USERS_PASS": "user_passwords.json", "CONFIG_PATH": "config"},
    }
    loader._passwords = {"7300391": "secret"}
    pw_file.write_text("not json", encoding="utf-8")
    result = loader.load(config)
    assert result == {"7300391": "secret"}
