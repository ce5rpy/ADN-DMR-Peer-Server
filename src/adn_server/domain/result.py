# ADN DMR Peer Server - result type
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

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
