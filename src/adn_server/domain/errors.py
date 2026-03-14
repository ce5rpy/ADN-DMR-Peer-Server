# ADN DMR Peer Server - domain errors
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""Domain errors for the ADN DMR Peer Server."""


class DomainError(Exception):
    """Base exception for domain/application."""

    pass


class ConfigError(DomainError):
    """Configuration loading or validation error."""

    pass


class ACLError(DomainError):
    """ACL parse or evaluation error."""

    pass


class AliasError(DomainError):
    """Alias load or resolve error."""

    pass


class ReportProtocolError(DomainError):
    """Report protocol decode or opcode error."""

    pass
