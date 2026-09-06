from pathlib import Path

import pytest

from synthetic_data.generator import generate
from synthetic_data.loaders.local import LocalFileLoader
from synthetic_data.scenarios.mutate import mutate
from synthetic_data.validation.checks import (
    validate_batch,
    validate_financial,
)
from synthetic_data.watermark import (
    is_after,
    max_watermark,
    parse_timestamp,
    select_after,
)


def test_tiny_generation_is_complete_and_valid(tmp_path):
    manifest = generate("tiny", 7, "initial", tmp_path)
    assert set(manifest["tables"]) == {
        "patients",
        "providers",
        "facilities",
        "provider_facility_affiliation",
        "encounters",
        "diagnoses",
        "procedures",
        "observations",
        "medications",
        "prescriptions",
        "members",
        "plans",
        "member_enrollment",
        "claims",
        "claim_lines",
        "claim_diagnoses",
        "authorizations",
        "payments",
        "claim_adjustments",
    }
    assert manifest["counts"]["patients"] == 1000
    assert validate_batch(tmp_path, "initial")["passed"]


def test_same_seed_produces_same_bytes(tmp_path):
    generate("tiny", 99, "a", tmp_path)
    generate("tiny", 99, "b", tmp_path)
    a = (Path(tmp_path) / "a" / "clinical_provider" / "patients.jsonl").read_bytes()
    b = (Path(tmp_path) / "b" / "clinical_provider" / "patients.jsonl").read_bytes()
    assert a == b


def test_quality_scenario_is_detected(tmp_path):
    generate("tiny", 7, "initial", tmp_path)
    mutate(tmp_path, "initial", "broken_foreign_key", "bad")
    result = validate_batch(tmp_path, "bad")
    assert not result["passed"] and result["relationship_errors"]


def test_invalid_financial_scenario_is_detected(tmp_path):
    generate("tiny", 7, "initial", tmp_path)
    mutate(tmp_path, "initial", "invalid_financial", "bad")
    assert validate_financial(Path(tmp_path), "bad")


def test_duplicate_event_scenario_is_detected(tmp_path):
    generate("tiny", 7, "initial", tmp_path)
    mutate(tmp_path, "initial", "duplicate_event", "bad")
    result = validate_batch(tmp_path, "bad")
    assert not result["passed"] and result["key_errors"]


def test_manifest_detects_tampering(tmp_path):
    generate("tiny", 7, "initial", tmp_path)
    path = Path(tmp_path) / "initial" / "clinical_provider" / "patients.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = validate_batch(tmp_path, "initial")
    assert not result["passed"] and result["manifest_errors"]


def test_local_loader_returns_manifest_counts(tmp_path):
    manifest = generate("tiny", 7, "initial", tmp_path)
    counts = LocalFileLoader().load_batch(Path(tmp_path) / "initial", ["claims"])
    assert counts == {"member_claims.claims": manifest["counts"]["claims"]}


def test_incremental_scenarios_have_progressing_watermarks(tmp_path):
    generate("tiny", 7, "initial", tmp_path)
    mutate(tmp_path, "initial", "incremental_01", "inc-001")
    mutate(tmp_path, "initial", "incremental_02", "inc-002")
    for batch_id, expected in (
        ("inc-001", "2025-02-01T00:00:00+00:00"),
        ("inc-002", "2025-03-01T00:00:00+00:00"),
    ):
        claims = Path(tmp_path) / batch_id / "member_claims" / "claims.jsonl"
        assert expected in claims.read_text(encoding="utf-8")


def test_composite_watermark_includes_same_timestamp_with_higher_key():
    timestamp = "2025-02-01T00:00:00+00:00"
    assert is_after(timestamp, 11, timestamp, 10)
    assert not is_after(timestamp, 9, timestamp, 10)
    assert not is_after("2025-01-31T23:59:59+00:00", 99, timestamp, 10)


def test_select_after_uses_timestamp_and_primary_key_together():
    rows = [
        {"claim_id": 9, "modified_at": "2025-01-31T23:59:59+00:00"},
        {"claim_id": 10, "modified_at": "2025-02-01T00:00:00+00:00"},
        {"claim_id": 11, "modified_at": "2025-02-01T00:00:00+00:00"},
        {"claim_id": 12, "modified_at": "2025-02-02T00:00:00+00:00"},
    ]
    selected = select_after(
        rows,
        timestamp_column="modified_at",
        primary_key_column="claim_id",
        low_watermark=("2025-02-01T00:00:00+00:00", 10),
    )
    assert [row["claim_id"] for row in selected] == [11, 12]


def test_max_watermark_returns_greatest_composite_value():
    rows = [
        {"claim_id": 12, "modified_at": "2025-02-01T00:00:00+00:00"},
        {"claim_id": 11, "modified_at": "2025-02-01T00:00:00+00:00"},
        {"claim_id": 10, "modified_at": "2025-03-01T00:00:00+00:00"},
    ]
    assert max_watermark(rows, "modified_at", "claim_id") == (
        parse_timestamp("2025-03-01T00:00:00+00:00"),
        10,
    )


def test_watermark_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        parse_timestamp("2025-02-01T00:00:00")
