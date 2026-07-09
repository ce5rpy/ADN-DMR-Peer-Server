# ADN DMR Peer Server - tests infrastructure security downloader
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
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

"""SecurityDownloader stub and password_crypto round-trip."""

from __future__ import annotations

import pytest

from adn_server.infrastructure.security.password_crypto import decrypt_password
from adn_server.infrastructure.security.password_download import StubSecurityDownloader

pytest.importorskip("cryptography")
from cryptography.fernet import Fernet  # noqa: E402


def test_password_crypto_roundtrip(tmp_path) -> None:
    key_path = tmp_path / "encryption_key.secret"
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    plaintext = "peer-secret-42"
    encrypted = Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")
    assert decrypt_password(encrypted, str(key_path)) == plaintext


def test_stub_security_downloader_is_noop() -> None:
    stub = StubSecurityDownloader()
    config = {"GLOBAL": {"URL_SECURITY": "", "PORT_SECURITY": "", "PASS_SECURITY": ""}}
    stub.init_downloads(config)
    stub.periodic_download(config)
