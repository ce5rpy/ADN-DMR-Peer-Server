# ADN DMR Peer Server - security downloads (legacy security_downloader)
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

"""Central security server: download encryption key and user passwords. Legacy init_security_downloads, periodic_password_download."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import tempfile
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ...application.ports import SecurityDownloader

logger = logging.getLogger(__name__)

DOWNLOAD_INTERVAL_PASSWORDS = 300

_last_passwords_download = 0.0
_last_passwords_size = 0
_last_passwords_content: bytes | None = None


def _resolve_hostname(hostname: str, timeout: int = 10) -> str | None:
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(hostname)
        socket.setdefaulttimeout(old_timeout)
        logger.debug("(SECURITY) Resolved %s to %s", hostname, ip)
        return ip
    except socket.gaierror as e:
        logger.error("(SECURITY) DNS resolution failed for %s: %s", hostname, e)
        return None
    except Exception as e:
        logger.error("(SECURITY) Unexpected error resolving %s: %s", hostname, e)
        return None


def _build_download_url(config: dict[str, Any], filename: str) -> tuple[str | None, str | None]:
    g = config.get("GLOBAL", {})
    url_security = (g.get("URL_SECURITY") or "").strip()
    port_security = (g.get("PORT_SECURITY") or "").strip()
    pass_security = (g.get("PASS_SECURITY") or "").strip()
    if not url_security or not port_security or not pass_security:
        return None, None
    try:
        socket.inet_aton(url_security)
        host = url_security
    except OSError:
        host = _resolve_hostname(url_security)
        if not host:
            logger.error("(SECURITY) Could not resolve hostname: %s", url_security)
            return None, None
    url = f"http://{host}:{port_security}/descargar?pass={quote(pass_security, safe='')}&file={filename}"
    return url, url_security


def _download_file_safely(
    url: str, dest_path: str, timeout: int = 60
) -> bool:
    try:
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            logger.debug("(SECURITY) Attempting download from: %s", url)
            req = Request(url)
            req.add_header("User-Agent", "ADN-Systems-DMR/1.0")
            with urlopen(req, timeout=timeout) as response:
                content = response.read()
            if len(content) == 0:
                logger.warning("(SECURITY) Downloaded file is empty, keeping existing: %s", dest_path)
                os.unlink(temp_path)
                return False
            with open(temp_path, "wb") as f:
                f.write(content)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(temp_path, dest_path)
            logger.info("(SECURITY) Successfully downloaded: %s (%d bytes)", dest_path, len(content))
            return True
        except HTTPError as e:
            logger.error("(SECURITY) HTTP error downloading %s: %s (Code: %d)", dest_path, e, e.code)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False
        except URLError as e:
            logger.error("(SECURITY) URL error downloading %s: %s", dest_path, e.reason)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False
        except socket.timeout:
            logger.error("(SECURITY) Timeout downloading %s", dest_path)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False
    except Exception as e:
        logger.error("(SECURITY) Unexpected error downloading %s: %s", dest_path, e)
        return False


def _download_encryption_key(config: dict[str, Any], config_dir: str) -> bool:
    g = config.get("GLOBAL", {})
    hash_encrypt = (g.get("HASH_ENCRYPT") or "encryption_key.secret").strip()
    dest_path = os.path.join(config_dir, hash_encrypt)
    url, _ = _build_download_url(config, hash_encrypt)
    if not url:
        logger.debug("(SECURITY) Security server not configured, skipping encryption key download")
        return False
    logger.info("(SECURITY) Downloading encryption key from central server...")
    return _download_file_safely(url, dest_path)


def _download_user_passwords(
    config: dict[str, Any], data_dir: str, force: bool = False
) -> bool:
    global _last_passwords_download, _last_passwords_size, _last_passwords_content
    now = time.time()
    if not force and (now - _last_passwords_download) < DOWNLOAD_INTERVAL_PASSWORDS:
        return False
    g = config.get("GLOBAL", {})
    users_pass = (g.get("USERS_PASS") or "user_passwords.json").strip()
    dest_path = os.path.join(data_dir, users_pass)
    url, _ = _build_download_url(config, users_pass)
    if not url:
        logger.debug("(SECURITY) Security server not configured, skipping passwords download")
        return False
    try:
        logger.debug("(SECURITY) Downloading passwords from: %s", url)
        req = Request(url)
        req.add_header("User-Agent", "ADN-Systems-DMR/1.0")
        with urlopen(req, timeout=60) as response:
            new_content = response.read()
        new_size = len(new_content)
        if new_size == 0:
            logger.warning("(SECURITY) Downloaded passwords file is empty, keeping existing")
            _last_passwords_download = now
            return False
        if _last_passwords_content is not None and new_content == _last_passwords_content:
            logger.debug("(SECURITY) Passwords file unchanged, no update needed")
            _last_passwords_download = now
            return False
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        with open(temp_path, "wb") as f:
            f.write(new_content)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.move(temp_path, dest_path)
        _last_passwords_content = new_content
        _last_passwords_size = new_size
        _last_passwords_download = now
        logger.info("(SECURITY) Successfully updated passwords file: %s (%d bytes)", dest_path, new_size)
        return True
    except HTTPError as e:
        logger.error("(SECURITY) HTTP error downloading passwords: %s (Code: %d)", e, e.code)
        _last_passwords_download = now
        return False
    except URLError as e:
        logger.error("(SECURITY) URL error downloading passwords: %s", e.reason)
        _last_passwords_download = now
        return False
    except socket.timeout:
        logger.error("(SECURITY) Timeout downloading passwords")
        _last_passwords_download = now
        return False
    except Exception as e:
        logger.error("(SECURITY) Unexpected error downloading passwords: %s", e)
        _last_passwords_download = now
        return False


class DefaultSecurityDownloader(SecurityDownloader):
    """Legacy security_downloader: init_security_downloads + periodic_password_download."""

    def __init__(self, project_root: str) -> None:
        self._project_root = project_root

    def _config_dir(self, config: dict[str, Any]) -> str:
        return os.path.join(self._project_root, (config.get("GLOBAL", {}).get("CONFIG_PATH") or "config"))

    def _data_dir(self, config: dict[str, Any]) -> str:
        path = (config.get("ALIASES", {}).get("PATH") or "data").rstrip("/")
        return os.path.join(self._project_root, path)

    def init_downloads(self, config: dict[str, Any]) -> None:
        """One-time init: resolve hostname, download encryption key and passwords (force)."""
        url_security = (config.get("GLOBAL", {}).get("URL_SECURITY") or "").strip()
        if not url_security:
            logger.info("(SECURITY) Central security server not configured")
            return
        port_security = (config.get("GLOBAL", {}).get("PORT_SECURITY") or "").strip()
        logger.info("(SECURITY) Initializing centralized security downloads...")
        logger.info("(SECURITY) Security server: %s:%s", url_security, port_security)
        try:
            socket.inet_aton(url_security)
            logger.info("(SECURITY) Using IP address: %s", url_security)
        except OSError:
            resolved = _resolve_hostname(url_security)
            if resolved:
                logger.info("(SECURITY) Resolved hostname %s to IP: %s", url_security, resolved)
            else:
                logger.error("(SECURITY) Failed to resolve hostname: %s", url_security)
                return
        config_dir = self._config_dir(config)
        data_dir = self._data_dir(config)
        _download_encryption_key(config, config_dir)
        _download_user_passwords(config, data_dir, force=True)

    def periodic_download(self, config: dict[str, Any]) -> None:
        """Periodic password file download (every 5 min)."""
        data_dir = self._data_dir(config)
        _download_user_passwords(config, data_dir)


class StubSecurityDownloader(SecurityDownloader):
    """Stub: init and periodic_download do nothing."""

    def init_downloads(self, config: dict[str, Any]) -> None:
        pass

    def periodic_download(self, config: dict[str, Any]) -> None:
        pass
