#!/usr/bin/env python3
# ADN DMR Parrot (playback) - launcher script
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS & Mike Zingman, N4IRR
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# GPLv3. Derived from playback.py / ADN DMR Server / HBlink.

"""
Run the ADN DMR Parrot (playback) from the project root.

  python adn-parrot.py
  python adn-parrot.py -c adn-parrot.yaml
  python adn-parrot.py --logging DEBUG

Config default: adn-parrot.yaml in this directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from adn_server.parrot_main import main

if __name__ == "__main__":
    main()
