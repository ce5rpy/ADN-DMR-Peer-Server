# ADN DMR Peer Server - password encryption (legacy password_crypto)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server. GPLv3.

"""Fernet-based encrypt/decrypt for stored passwords. Legacy password_crypto."""

from __future__ import annotations

import os
from typing import Optional

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None  # type: ignore[misc, assignment]


def get_or_create_key(key_path: str) -> bytes:
    """Load encryption key from file or create and save one."""
    if Fernet is None:
        raise RuntimeError("cryptography package required for password_crypto")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key)
    return key


def get_fernet(key_path: str = "config/encryption_key.secret") -> "Fernet":
    """Return Fernet instance using key at key_path."""
    if Fernet is None:
        raise RuntimeError("cryptography package required for password_crypto")
    key = get_or_create_key(key_path)
    return Fernet(key)


def decrypt_password(encrypted_password: Optional[str], key_path: str = "config/encryption_key.secret") -> Optional[str]:
    """Decrypt a stored password; return as-is if empty or on failure."""
    if not encrypted_password:
        return encrypted_password
    try:
        fernet = get_fernet(key_path)
        decrypted = fernet.decrypt(encrypted_password.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception:
        return encrypted_password


def encrypt_password(password: Optional[str], key_path: str = "config/encryption_key.secret") -> Optional[str]:
    """Encrypt a password for storage."""
    if not password:
        return password
    fernet = get_fernet(key_path)
    encrypted = fernet.encrypt(password.encode("utf-8"))
    return encrypted.decode("utf-8")


def is_encrypted(value: Optional[str], key_path: str = "config/encryption_key.secret") -> bool:
    """Return True if value looks like Fernet-encrypted data."""
    if not value:
        return False
    try:
        fernet = get_fernet(key_path)
        fernet.decrypt(value.encode("utf-8"))
        return True
    except Exception:
        return False
