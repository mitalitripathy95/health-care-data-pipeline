"""Validation checks for generated source batches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .distribution import validate_distribution


def read_table(root: Path, domain: str, table: str) -> list[dict[str, Any]]:
    path = root / domain / f"{table}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# This is intentionally explicit and mirrors the source DDL.  Cross-source provider and
# facility keys are validated as referential contracts even though Azure SQL does not own them.
FOREIGN_KEYS = [
    (
        "clinical_provider",
        "provider_facility_affiliation",
        "provider_id",
        "clinical_provider",
        "providers",
        "provider_id",
    ),
    (
        "clinical_provider",
        "provider_facility_affiliation",
        "facility_id",
        "clinical_provider",
        "facilities",
        "facility_id",
    ),
    (
        "clinical_provider",
        "encounters",
        "patient_id",
        "clinical_provider",
        "patients",
        "patient_id",
    ),
    (
        "clinical_provider",
        "encounters",
        "provider_id",
        "clinical_provider",
        "providers",
        "provider_id",
    ),
    (
        "clinical_provider",
        "encounters",
        "facility_id",
        "clinical_provider",
        "facilities",
        "facility_id",
    ),
    (
        "clinical_provider",
        "diagnoses",
        "encounter_id",
        "clinical_provider",
        "encounters",
        "encounter_id",
    ),
    ("clinical_provider", "diagnoses", "patient_id", "clinical_provider", "patients", "patient_id"),
    (
        "clinical_provider",
        "procedures",
        "encounter_id",
        "clinical_provider",
        "encounters",
        "encounter_id",
    ),
    (
        "clinical_provider",
        "procedures",
        "patient_id",
        "clinical_provider",
        "patients",
        "patient_id",
    ),
    (
        "clinical_provider",
        "observations",
        "encounter_id",
        "clinical_provider",
        "encounters",
        "encounter_id",
    ),
    (
        "clinical_provider",
        "observations",
        "patient_id",
        "clinical_provider",
        "patients",
        "patient_id",
    ),
    (
        "clinical_provider",
        "prescriptions",
        "patient_id",
        "clinical_provider",
        "patients",
        "patient_id",
    ),
    (
        "clinical_provider",
        "prescriptions",
        "encounter_id",
        "clinical_provider",
        "encounters",
        "encounter_id",
    ),
    (
        "clinical_provider",
        "prescriptions",
        "medication_id",
        "clinical_provider",
        "medications",
        "medication_id",
    ),
    ("member_claims", "member_enrollment", "member_id", "member_claims", "members", "member_id"),
    ("member_claims", "member_enrollment", "plan_id", "member_claims", "plans", "plan_id"),
    ("member_claims", "claims", "member_id", "member_claims", "members", "member_id"),
    ("member_claims", "claim_lines", "claim_id", "member_claims", "claims", "claim_id"),
    ("member_claims", "claim_diagnoses", "claim_id", "member_claims", "claims", "claim_id"),
    ("member_claims", "authorizations", "member_id", "member_claims", "members", "member_id"),
    ("member_claims", "payments", "claim_id", "member_claims", "claims", "claim_id"),
    ("member_claims", "claim_adjustments", "claim_id", "member_claims", "claims", "claim_id"),
]
PRIMARY_KEYS = {
    "patients": "patient_id",
    "providers": "provider_id",
    "facilities": "facility_id",
    "provider_facility_affiliation": "affiliation_id",
    "encounters": "encounter_id",
    "diagnoses": "diagnosis_id",
    "procedures": "procedure_id",
    "observations": "observation_id",
    "medications": "medication_id",
    "prescriptions": "prescription_id",
    "members": "member_id",
    "plans": "plan_id",
    "member_enrollment": "enrollment_id",
    "claims": "claim_id",
    "claim_lines": "claim_line_id",
    "claim_diagnoses": "claim_diagnosis_id",
    "authorizations": "authorization_id",
    "payments": "payment_id",
    "claim_adjustments": "adjustment_id",
}


def validate_relationships(root: str | Path, batch_id: str) -> list[str]:
    root = Path(root) / batch_id
    cache: dict[tuple[str, str, str], set[Any]] = {}
    errors: list[str] = []
    for domain, table, column, parent_domain, parent_table, parent_column in FOREIGN_KEYS:
        cache_key = (parent_domain, parent_table, parent_column)
        cache.setdefault(
            cache_key,
            {row.get(parent_column) for row in read_table(root, parent_domain, parent_table)},
        )
        for row in read_table(root, domain, table):
            if row.get(column) not in cache[cache_key]:
                errors.append(
                    f"{domain}.{table}.{column}={row.get(column)} missing from "
                    f"{parent_domain}.{parent_table}"
                )
    return errors


def validate_keys(root: str | Path, batch_id: str) -> list[str]:
    batch = Path(root) / batch_id
    errors: list[str] = []
    for domain, tables in (
        (
            "clinical_provider",
            [
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
            ],
        ),
        (
            "member_claims",
            [
                "members",
                "plans",
                "member_enrollment",
                "claims",
                "claim_lines",
                "claim_diagnoses",
                "authorizations",
                "payments",
                "claim_adjustments",
            ],
        ),
    ):
        for table in tables:
            key_column = PRIMARY_KEYS[table]
            seen: set[Any] = set()
            for row in read_table(batch, domain, table):
                value = row.get(key_column)
                if value in seen:
                    errors.append(f"{domain}.{table}.{key_column} duplicate: {value}")
                seen.add(value)
    return errors


def validate_financial(root: str | Path, batch_id: str) -> list[str]:
    errors: list[str] = []
    for table in ("claims", "claim_lines"):
        for row in read_table(Path(root) / batch_id, "member_claims", table):
            billed, allowed, paid = row["billed_amount"], row["allowed_amount"], row["paid_amount"]
            if not (0 <= paid <= allowed <= billed):
                errors.append(
                    f"{table}:{row.get('claim_id', row.get('claim_line_id'))}: "
                    "financial ordering invalid"
                )
    return errors


def validate_manifest(root: str | Path, batch_id: str) -> list[str]:
    batch = Path(root) / batch_id
    manifest_path = batch / "manifest.json"
    if not manifest_path.exists():
        return ["manifest.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for table_name, metadata in manifest.get("table_metadata", {}).items():
        path = batch / metadata["path"]
        if not path.exists():
            errors.append(f"{table_name}: file is missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != metadata.get("sha256"):
            errors.append(f"{table_name}: sha256 mismatch")
        actual = len(path.read_text(encoding="utf-8").splitlines())
        if actual != metadata.get("row_count"):
            errors.append(f"{table_name}: row count mismatch")
    return errors


def validate_batch(root: str | Path, batch_id: str) -> dict[str, Any]:
    relationship_errors = validate_relationships(root, batch_id)
    financial_errors = validate_financial(root, batch_id)
    key_errors = validate_keys(root, batch_id)
    manifest_errors = validate_manifest(root, batch_id)
    distribution_errors = validate_distribution(root, batch_id)
    return {
        "batch_id": batch_id,
        "passed": not (
            relationship_errors
            or financial_errors
            or key_errors
            or manifest_errors
            or distribution_errors
        ),
        "relationship_errors": relationship_errors,
        "financial_errors": financial_errors,
        "key_errors": key_errors,
        "manifest_errors": manifest_errors,
        "distribution_errors": distribution_errors,
    }
