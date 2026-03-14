#!/usr/bin/env python3
# ADN DMR Peer Server - launcher script (like monitor/monitor.py)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# GPLv3. Derived from ADN DMR Server / HBlink.

"""
Run the ADN DMR Peer Server from the project root.

  python adn-server.py
  python adn-server.py -c adn-server.yaml
  python adn-server.py --logging DEBUG

Config default: adn-server.yaml in this directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from adn_server.main import main

if __name__ == "__main__":
    main()
