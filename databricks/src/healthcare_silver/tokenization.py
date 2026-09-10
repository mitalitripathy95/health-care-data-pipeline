"""Runtime-only HMAC tokenization. Keys are never logged or persisted."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from typing import Any

SecretProvider = Callable[[], str]
_TOKEN = re.compile(r"^tok_(?P<version>[A-Za-z0-9_.-]+)_[0-9a-f]{64}$")


def canonicalize(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    return text or None


def validate_key(key: Any) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("HMAC key must be a non-empty string")
    return key


def hmac_token(value: Any, key: str, *, namespace: str = "id", version: str = "v1") -> str | None:
    canonical = canonicalize(value)
    if canonical is None:
        return None
    validate_key(key)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", version):
        raise ValueError("Unsafe token version")
    message = f"{namespace}:{canonical}".encode()
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"tok_{version}_{digest}"


def tokenize_row(
    row: dict[str, Any],
    key: str,
    fields: tuple[str, ...],
    *,
    namespace: str = "id",
    version: str = "v1",
) -> dict[str, Any]:
    result = dict(row)
    for field in fields:
        if field in result:
            result[f"{field}_token"] = hmac_token(
                result[field], key, namespace=f"{namespace}:{field}", version=version
            )
            result.pop(field, None)
    return result


def is_token(value: Any) -> bool:
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value))


def runtime_key_from_dbutils(dbutils, scope: str, key_name: str) -> str:
    if dbutils is None:
        raise ValueError("Databricks dbutils is required")
    return validate_key(dbutils.secrets.get(scope, key_name))
