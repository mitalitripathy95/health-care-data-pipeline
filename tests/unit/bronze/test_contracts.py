from __future__ import annotations

from dataclasses import replace

import pytest
from healthcare_bronze.config import BronzeConfig
from healthcare_bronze.contracts import (
    Dependency,
    DriftKind,
    Manifest,
    SchemaContract,
    classify_schema_drift,
    eligible_manifests,
    idempotency_key,
    record_hash,
)
from healthcare_bronze.schema_registry import get_contract, registered_tables


def manifest(**changes):
    base = Manifest(
        batch_id="batch-001",
        table_run_id="run-001",
        source_system="clinical_provider",
        source_schema="clinical",
        source_table="patients",
        bronze_path=(
            "bronze/raw/source=clinical_provider/schema=clinical/table=patients/"
            "batch_id=batch-001/run_id=run-001/"
        ),
        source_row_count=2,
        landed_row_count=2,
        schema_version="v1",
        status="PUBLISHED",
        published_at="2026-09-07T00:00:00Z",
    )
    return replace(base, **changes)


def ready_dependency(**changes):
    base = Dependency("batch-001", "adf_ingestion", "databricks_bronze", "READY")
    return replace(base, **changes)


def test_only_reconciled_published_manifest_with_ready_dependency_is_eligible():
    assert eligible_manifests([manifest()], [ready_dependency()], "batch-001") == [manifest()]
    assert not eligible_manifests([manifest(status="STAGED")], [ready_dependency()])
    assert not eligible_manifests([manifest(published_at=None)], [ready_dependency()])
    assert not eligible_manifests([manifest(landed_row_count=1)], [ready_dependency()])
    assert not eligible_manifests([manifest()], [ready_dependency(status="COMPLETED")])


def test_manifest_path_must_match_manifest_identity():
    bad = manifest(bronze_path=manifest().bronze_path.replace("patients", "providers"))
    with pytest.raises(ValueError, match="does not match manifest identity"):
        eligible_manifests([bad], [ready_dependency()])


def test_registry_contains_all_nineteen_phase_one_tables():
    assert len(registered_tables()) == 19
    assert get_contract("clinical_provider", "clinical", "patients").version == "v1"
    with pytest.raises(KeyError, match="Unsupported schema version"):
        get_contract("clinical_provider", "clinical", "patients", "v2")


def test_schema_drift_policy():
    contract = SchemaContract("s", "x", "t", "v1", {"id": "integer"}, frozenset({"id"}))
    assert classify_schema_drift(contract, {"id": ("integer", False)}).kind is DriftKind.EXACT
    additive = classify_schema_drift(contract, {"id": ("integer", False), "note": ("string", True)})
    assert additive.allowed and additive.kind is DriftKind.ADDITIVE
    assert not classify_schema_drift(
        contract, {"id": ("integer", False), "note": ("string", False)}
    ).allowed
    assert not classify_schema_drift(contract, {}).allowed
    assert not classify_schema_drift(contract, {"id": ("string", False)}).allowed
    widening = classify_schema_drift(contract, {"id": ("long", False)})
    assert widening.allowed and widening.kind is DriftKind.WIDENING


def test_hashes_are_deterministic_and_identity_sensitive():
    assert record_hash({"b": 2, "a": 1}) == record_hash({"a": 1, "b": 2})
    assert idempotency_key(manifest()) == idempotency_key(manifest(table_run_id="retry-run"))
    assert idempotency_key(manifest()) != idempotency_key(manifest(batch_id="backfill-002"))


def test_runtime_configuration_rejects_unsafe_values():
    config = BronzeConfig(manifest_path="abfss://control", source_filter="ALL")
    assert config.catalog_name == "healthcare_demo"
    with pytest.raises(ValueError, match="source_filter"):
        BronzeConfig(manifest_path="x", source_filter="patients")
    with pytest.raises(ValueError, match="Either manifest_path"):
        BronzeConfig()
    with pytest.raises(ValueError, match="Unsafe"):
        BronzeConfig(manifest_path="x", catalog_name="bad-name")
