"""Validated configuration for the Silver workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from healthcare_bronze.contracts import validate_safe_id

from .tokenization import SecretProvider, validate_key

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SilverConfig:
    batch_id: str = ""
    source_filter: str = "ALL"
    catalog_name: str = "healthcare_demo"
    bronze_schema: str = "bronze"
    restricted_schema: str = "silver_restricted"
    deidentified_schema: str = "silver_deidentified"
    quarantine_schema: str = "quarantine"
    control_jdbc_url: str = ""
    secret_scope: str = "healthcare"
    hmac_key_name: str = "silver-hmac-key"
    token_version: str = "v1"
    transform_version: str = "v1"
    event_watermark: str = ""

    def __post_init__(self) -> None:
        for value in (
            self.catalog_name,
            self.bronze_schema,
            self.restricted_schema,
            self.deidentified_schema,
            self.quarantine_schema,
        ):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"Unsafe catalog/schema identifier: {value}")
        if self.source_filter not in {"ALL", "clinical_provider", "member_claims"}:
            raise ValueError("source_filter must be ALL, clinical_provider, or member_claims")
        if self.batch_id:
            validate_safe_id(self.batch_id, "batch_id")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.hmac_key_name):
            raise ValueError("Unsafe hmac_key_name")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.token_version):
            raise ValueError("Unsafe token_version")
        if self.event_watermark:
            try:
                date.fromisoformat(self.event_watermark[:10])
            except ValueError as exc:
                raise ValueError("event_watermark must be an ISO date or timestamp") from exc

    def watermark_value(self) -> date | datetime | None:
        if not self.event_watermark:
            return None
        value = self.event_watermark
        if "T" in value or " " in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.fromisoformat(value)

    def key_provider(self, dbutils=None) -> SecretProvider:
        if dbutils is None:
            raise ValueError("dbutils is required to resolve the Azure Key Vault-backed HMAC key")

        def provider() -> str:
            return validate_key(dbutils.secrets.get(self.secret_scope, self.hmac_key_name))

        return provider
