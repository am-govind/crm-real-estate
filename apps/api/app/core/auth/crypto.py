import base64
import hashlib
import json
import secrets
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().session_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_json(data: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(token.encode()))


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
