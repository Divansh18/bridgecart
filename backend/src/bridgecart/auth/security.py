"""Password and opaque credential primitives; no raw value is logged."""

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM)
    return "scrypt$32768$8$1$" + base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, payload = encoded.split("$", 4)
        if algorithm != "scrypt" or (n, r, p) != ("32768", "8", "1"):
            return False
        raw = base64.urlsafe_b64decode(payload)
        if len(raw) != 80:
            return False
        expected = hashlib.scrypt(
            password.encode(), salt=raw[:16], n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM
        )
        return hmac.compare_digest(expected, raw[16:])
    except (ValueError, TypeError):
        return False


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(48)


def token_hash(kind: str, token: str) -> str:
    return hashlib.sha256((kind + ":" + token).encode()).hexdigest()
