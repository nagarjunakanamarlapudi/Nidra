"""Symmetric encryption for secrets at rest (e.g. Plaid access tokens).

The Fernet key is derived from APP_SECRET_KEY so no extra key management is
needed for a single-user deploy.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _key(app_secret_key: str) -> bytes:
    digest = hashlib.sha256(app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, app_secret_key: str) -> str:
    return Fernet(_key(app_secret_key)).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, app_secret_key: str) -> str:
    return Fernet(_key(app_secret_key)).decrypt(token.encode()).decode()
