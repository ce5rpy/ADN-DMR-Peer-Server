# ADN DMR Peer Server - HBP protocol constants
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink (const.py). GPLv3.

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
