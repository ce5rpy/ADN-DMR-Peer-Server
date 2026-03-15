# ADN DMR Peer Server - HBP protocol constants
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

"""Homebrew protocol opcodes and frame types (legacy const.py)."""

# DMR
DMR = b"DMR"
DMRD = b"DMRD"
DMRE = b"DMRE"
DMRF = b"DMRF"
DMRA = b"DMRA"

# Master/peer
RPTL = b"RPTL"
RPTPING = b"RPTPING"
RPTACK = b"RPTACK"
RPTCL = b"RPTCL"
RPTK = b"RPTK"
RPTC = b"RPTC"
RPTP = b"RPTP"
RPTA = b"RPTA"
RPTO = b"RPTO"
MSTCL = b"MSTCL"
MSTNAK = b"MSTNAK"
MSTPONG = b"MSTPONG"
MSTN = b"MSTN"   # peer receives MSTNAK as MSTN (4-char command)
MSTP = b"MSTP"   # peer receives MSTPONG as MSTP
MSTC = b"MSTC"   # peer receives MSTCL as MSTC

# OpenBridge
EOBP = b"EOBP"
BC = b"BC"
BCKA = b"BCKA"
BCSQ = b"BCSQ"
BCST = b"BCST"
BCVE = b"BCVE"

# Proxy
PRIN = b"PRIN"
PRBL = b"PRBL"

# Frame types (bits)
HBPF_VOICE = 0x0
HBPF_VOICE_SYNC = 0x1
HBPF_DATA_SYNC = 0x2
HBPF_SLT_VHEAD = 0x1
HBPF_SLT_VTERM = 0x2

VER = 5
PROTO_VER = 5

# Legacy const.py: stream timeout (seconds) for contention
STREAM_TO = 0.36
