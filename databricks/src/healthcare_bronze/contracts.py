"""Pure domain seam for manifest eligibility, schema drift, and deterministic identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SAFE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}"
_SAFE_ID = re.compile(rf"^{SAFE_ID_PATTERN}$")
_PATH = re.compile(
    r"^(?:abfss://[^/]+@[^/]+/)?bronze/raw/"
    r"source=(?P<source>[a-z0-9_]+)/schema=(?P<schema>[a-z0-9_]+)/"
    rf"table=(?P<table>[a-z0-9_]+)/batch_id=(?P<batch>{SAFE_ID_PATTERN})/"
    rf"run_id=(?P<run>{SAFE_ID_PATTERN})/?$"
)
_ALLOWED_WIDENINGS = {
    ("byte", "short"),
    ("byte", "integer"),
    ("byte", "long"),
    ("short", "integer"),
    ("short", "long"),
    ("integer", "long"),
    ("float", "double"),
    ("date", "timestamp"),
}


class SchemaValidationError(ValueError):
    """Raised when an input cannot safely satisfy its registered source contract."""


class DriftKind(StrEnum):
    EXACT = "EXACT"
    ADDITIVE = "ADDITIVE_NULLABLE"
    WIDENING = "TYPE_WIDENING"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class Manifest:
    batch_id: str
    table_run_id: str
    source_system: str
    source_schema: str
    source_table: str
    bronze_path: str
    source_row_count: int
    landed_row_count: int
    schema_version: str
    status: str
    published_at: str | None
    target_format: str = "PARQUET"


@dataclass(frozen=True)
class Dependency:
    batch_id: str
    upstream_job: str
    downstream_job: str
    status: str


@dataclass(frozen=True)
class SchemaContract:
    source_system: str
    source_schema: str
    source_table: str
    version: str
    columns: Mapping[str, str]
    required_columns: frozenset[str]


@dataclass(frozen=True)
class DriftDecision:
    kind: DriftKind
    added_columns: tuple[str, ...] = ()
    widened_columns: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.errors


def validate_raw_path(manifest: Manifest) -> None:
    validate_safe_id(manifest.batch_id, "batch_id")
    validate_safe_id(manifest.table_run_id, "table_run_id")
    match = _PATH.fullmatch(manifest.bronze_path)
    if not match:
        raise ValueError(
            f"Raw path violates the immutable Phase 3 contract: {manifest.bronze_path}"
        )
    expected = (
        manifest.source_system,
        manifest.source_schema,
        manifest.source_table,
        manifest.batch_id,
        manifest.table_run_id,
    )
    actual = tuple(match.group(k) for k in ("source", "schema", "table", "batch", "run"))
    if actual != expected:
        raise ValueError(f"Raw path identity {actual} does not match manifest identity {expected}")


def validate_safe_id(value: str, field_name: str) -> str:
    """Validate an identity before it reaches a path or SQL predicate."""
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"Unsafe {field_name}: {value!r}")
    return value


def eligible_manifests(
    manifests: Iterable[Manifest], dependencies: Iterable[Dependency], batch_id: str = ""
) -> list[Manifest]:
    if batch_id:
        validate_safe_id(batch_id, "batch_id")
    manifests = list(manifests)
    dependencies = list(dependencies)
    for manifest in manifests:
        validate_safe_id(manifest.batch_id, "batch_id")
        validate_safe_id(manifest.table_run_id, "table_run_id")
    for dependency in dependencies:
        validate_safe_id(dependency.batch_id, "dependency batch_id")
    ready = {
        d.batch_id
        for d in dependencies
        if d.upstream_job == "adf_ingestion"
        and d.downstream_job == "databricks_bronze"
        and d.status == "READY"
    }
    result: list[Manifest] = []
    for manifest in manifests:
        if batch_id and manifest.batch_id != batch_id:
            continue
        if manifest.batch_id not in ready:
            continue
        if manifest.status != "PUBLISHED" or not manifest.published_at:
            continue
        if manifest.source_row_count != manifest.landed_row_count:
            continue
        validate_raw_path(manifest)
        result.append(manifest)
    return sorted(
        result,
        key=lambda item: (item.batch_id, item.source_system, item.source_schema, item.source_table),
    )


def classify_schema_drift(
    contract: SchemaContract,
    actual_columns: Mapping[str, tuple[str, bool]],
) -> DriftDecision:
    missing = sorted(contract.required_columns - actual_columns.keys())
    errors = [f"missing required column: {name}" for name in missing]
    added = sorted(actual_columns.keys() - contract.columns.keys())
    non_nullable_added = [name for name in added if not actual_columns[name][1]]
    errors.extend(f"new column must be nullable: {name}" for name in non_nullable_added)
    widened: list[str] = []
    for name in sorted(contract.columns.keys() & actual_columns.keys()):
        expected = normalize_type(contract.columns[name])
        actual = normalize_type(actual_columns[name][0])
        if actual == expected:
            continue
        if (expected, actual) in _ALLOWED_WIDENINGS:
            widened.append(name)
        else:
            errors.append(f"incompatible type for {name}: expected {expected}, found {actual}")
    if errors:
        return DriftDecision(DriftKind.INCOMPATIBLE, tuple(added), tuple(widened), tuple(errors))
    if widened:
        return DriftDecision(DriftKind.WIDENING, tuple(added), tuple(widened))
    if added:
        return DriftDecision(DriftKind.ADDITIVE, tuple(added))
    return DriftDecision(DriftKind.EXACT)


def normalize_type(value: str) -> str:
    value = value.lower().replace(" ", "")
    aliases = {
        "int": "integer",
        "bigint": "long",
        "datetime": "timestamp",
        "datetime2": "timestamp",
        "bool": "boolean",
        "bit": "boolean",
    }
    if (
        value.startswith("varchar")
        or value.startswith("nvarchar")
        or value in {"uuid", "uniqueidentifier", "char", "string"}
    ):
        return "string"
    if value.startswith("decimal") or value.startswith("numeric"):
        return value
    return aliases.get(value, value)


def idempotency_key(manifest: Manifest) -> str:
    value = "|".join(
        (manifest.batch_id, manifest.source_system, manifest.source_schema, manifest.source_table)
    )
    return hashlib.sha256(value.encode()).hexdigest()


def record_hash(record: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        record, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
