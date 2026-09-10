"""Validated runtime configuration for the Bronze workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import validate_safe_id

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SOURCE_FILTERS = frozenset({"ALL", "clinical_provider", "member_claims"})


@dataclass(frozen=True)
class BronzeConfig:
    batch_id: str = ""
    source_filter: str = "ALL"
    manifest_path: str = ""
    catalog_name: str = "healthcare_demo"
    bronze_schema: str = "bronze"
    quarantine_schema: str = "quarantine"
    control_jdbc_url: str = ""
    secret_scope: str = "healthcare"
    control_user_key: str = "control-db-user"
    control_password_key: str = "control-db-password"

    def __post_init__(self) -> None:
        for value in (self.catalog_name, self.bronze_schema, self.quarantine_schema):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"Unsafe catalog/schema identifier: {value}")
        if self.source_filter not in _SOURCE_FILTERS:
            raise ValueError("source_filter must be ALL, clinical_provider, or member_claims")
        if self.batch_id:
            validate_safe_id(self.batch_id, "batch_id")
        if not self.manifest_path and not self.control_jdbc_url:
            raise ValueError("Either manifest_path or control_jdbc_url is required")
