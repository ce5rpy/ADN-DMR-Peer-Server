# ADN DMR Peer Server - i18n voice key mapping
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server i8n_voice_map.py (Simon Adlem, G7RZU). GPLv3.

"""Map logical keys (e.g. 'A') to AMBE file names (e.g. 'alpha') per language."""

VOICE_MAP: dict[str, dict[str, str]] = {
    "en_GB": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
    },
    "en_GB_2": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
    },
    "cy_GB": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
        "allstar-link-mode": "alpha",
    },
    "en_US": {
        "to": "2", "adn": "silence", "this-is": "silence", "allstar-link-mode": "alpha",
    },
    "es_ES": {
        "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
        "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
        "A": "alfa", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
        "allstar-link-mode": "alfa",
    },
    "fr_FR": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
        "allstar-link-mode": "alpha",
    },
    "pt_PT": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "linkedto": "linked-to",
        "allstar-link-mode": "alpha",
    },
    "el_GR": {
        "A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo",
        "F": "foxtrot", "G": "golf", "H": "hotel", "I": "india", "J": "juliet",
        "K": "kilo", "L": "lima", "M": "mike", "N": "november", "O": "oscar",
        "P": "papa", "Q": "quebec", "R": "romeo", "S": "sierra", "T": "tango",
        "U": "uniform", "V": "victor", "W": "whiskey", "X": "x-ray", "Y": "yankee",
        "Z": "zulu", "to": "silence", "notlinked": "not-linked", "allstar-link-mode": "alpha",
    },
    "de_DE": {"to": "silence", "allstar-link-mode": "A"},
    "dk_DK": {"to": "silence", "adn": "silence", "this-is": "silence", "allstar-link-mode": "A"},
    "it_IT": {"to": "silence", "adn": "silence", "this-is": "silence", "allstar-link-mode": "A"},
    "no_NO": {"to": "silence", "adn": "silence", "this-is": "silence", "allstar-link-mode": "A"},
    "pl_PL": {"to": "silence", "adn": "silence", "this-is": "silence", "allstar-link-mode": "A"},
    "se_SE": {"to": "silence", "adn": "silence", "this-is": "silence", "allstar-link-mode": "A"},
    "CW": {"to": "silence", "adn": "silence", "this-is": "silence", "linkedto": "silence", "allstar-link-mode": "T"},
    "th_TH": {"to": "silence", "allstar-link-mode": "A"},
}
