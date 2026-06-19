"""pyproject.toml version and CLI --version."""

from __future__ import annotations

import re
import subprocess
import sys

from adn_server import __version__, read_version, repo_root


def test_read_version_matches_pyproject():
    text = (repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "project.version missing in pyproject.toml"
    assert read_version() == m.group(1)
    assert __version__ == read_version()


def test_adn_server_cli_version():
    proc = subprocess.run(
        [sys.executable, "-m", "adn_server.main", "--version"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root()),
    )
    assert proc.stdout.strip() == f"adn-server {read_version()}"
