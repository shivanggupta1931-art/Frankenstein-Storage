"""AES-256-GCM chunk encryption and decryption."""

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.core.errors import AppError

NONCE_SIZE = 12
TAG_SIZE = 16


def encrypt_chunk(data: bytes, key: bytes) -> bytes:
    """Encrypts chunk data with AES-256-GCM.
    
    Header contains random 12-byte nonce followed by ciphertext and 16-byte auth tag.
    """
    if len(key) != 32:
        raise ValueError("Encryption key must be 32 bytes (256 bits)")
    
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext_and_tag


def decrypt_chunk(chunk_bytes: bytes, key: bytes) -> bytes:
    """Decrypts chunk data with AES-256-GCM.
    
    Extracts 12-byte nonce header and verifies authentication tag.
    """
    if len(key) != 32:
        raise ValueError("Encryption key must be 32 bytes (256 bits)")
    if len(chunk_bytes) < NONCE_SIZE + TAG_SIZE:
        raise AppError(400, "INVALID_CHUNK", "Chunk payload too short to contain nonce and auth tag")

    nonce = chunk_bytes[:NONCE_SIZE]
    ciphertext_and_tag = chunk_bytes[NONCE_SIZE:]
    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(nonce, ciphertext_and_tag, None)
    except InvalidTag:
        raise AppError(400, "CIPHERTEXT_TAMPERED", "Decryption failed: chunk authentication tag mismatch or corrupted ciphertext")
    except Exception as e:
        raise AppError(400, "DECRYPTION_ERROR", f"Failed to decrypt chunk: {e}")
