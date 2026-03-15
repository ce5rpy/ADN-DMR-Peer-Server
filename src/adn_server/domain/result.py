# ADN DMR Peer Server - result type
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

"""Result type for functional error handling (Success/Fail)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


@dataclass(frozen=True, slots=True)
class Success(Generic[T]):
    """Successful result wrapping a value."""

    value: T


@dataclass(frozen=True, slots=True)
class Fail(Generic[E]):
    """Failed result wrapping an error."""

    error: E


Result = Success[T] | Fail[E]


def is_fail(r: Result[T, E]) -> bool:
    """Return True if result is Fail."""
    return isinstance(r, Fail)


def is_ok(r: Result[T, E]) -> bool:
    """Return True if result is Success."""
    return isinstance(r, Success)


def unwrap_or(r: Result[T, E], default: T) -> T:
    """Return value if Success, else default."""
    return r.value if isinstance(r, Success) else default
