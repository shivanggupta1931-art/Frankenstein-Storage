"""Vault key management using scrypt key derivation and in-memory key storage."""

import hashlib
import hmac
import os
import sqlite3

from backend.app.core.errors import AppError

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
VERIFIER_PAYLOAD = b"frankenstein-vault-v1"


class KeyManager:
    def __init__(self):
        self._master_key: bytes | None = None

    def is_unlocked(self) -> bool:
        return self._master_key is not None

    def lock(self) -> None:
        self._master_key = None

    def get_key(self) -> bytes:
        if self._master_key is None:
            raise AppError(403, "VAULT_LOCKED", "Storage vault is locked. Please unlock first.")
        return self._master_key

    def set_key_direct(self, key: bytes) -> None:
        """Helper for isolated unit tests only."""
        if len(key) != 32:
            raise ValueError("Key must be 32 bytes")
        self._master_key = key

    def initialize_or_unlock(self, password: str, conn: sqlite3.Connection) -> bool:
        if not password:
            raise AppError(400, "INVALID_PASSWORD", "Password cannot be empty")

        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings WHERE key IN ('salt', 'verifier')")
        rows = dict(cursor.fetchall())

        salt_hex = rows.get("salt")
        verifier_hex = rows.get("verifier")

        if not salt_hex or not verifier_hex:
            # Vault initial setup
            salt = os.urandom(32)
            derived_key = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
                dklen=KEY_LEN,
            )
            verifier = hmac.new(derived_key, VERIFIER_PAYLOAD, hashlib.sha256).hexdigest()

            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('salt', ?)", (salt.hex(),))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('verifier', ?)", (verifier,))
            self._master_key = derived_key
            return True
        else:
            # Unlock existing vault
            salt = bytes.fromhex(salt_hex)
            candidate_key = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
                dklen=KEY_LEN,
            )
            expected_verifier = hmac.new(candidate_key, VERIFIER_PAYLOAD, hashlib.sha256).hexdigest()

            if not hmac.compare_digest(expected_verifier, verifier_hex):
                raise AppError(401, "INVALID_PASSWORD", "Incorrect password")

            self._master_key = candidate_key
            return True


key_manager = KeyManager()
