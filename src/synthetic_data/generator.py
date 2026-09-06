"""Deterministic synthetic source-system data generator."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TABLES = {
    "clinical_provider": [
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
    "member_claims": [
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
}
ALL_TABLES = [*TABLES["clinical_provider"], *TABLES["member_claims"]]
COUNTS = {
    "tiny": {"patients": 1_000, "encounters": 3_000, "claims": 2_000, "claim_lines": 5_000},
    "small": {"patients": 25_000, "encounters": 100_000, "claims": 75_000, "claim_lines": 250_000},
    "medium": {
        "patients": 100_000,
        "encounters": 500_000,
        "claims": 350_000,
        "claim_lines": 1_200_000,
    },
}
BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def stable_id(seed: int, table: str, number: int) -> int:
    table_hash = int(hashlib.sha256(table.encode()).hexdigest()[:8], 16)
    return seed * 10_000_000 + table_hash * 10_000 + number


def _iso(number: int, lag: int = 0) -> str:
    return (BASE + timedelta(minutes=number + lag)).isoformat()


def _day(number: int) -> str:
    return (BASE.date() + timedelta(days=number % 365)).isoformat()


def _common(table: str, number: int) -> dict[str, Any]:
    return {
        "updated_at" if table in TABLES["clinical_provider"] else "modified_at": _iso(number),
        "is_deleted": False,
    }


def _row(table: str, i: int, seed: int, refs: dict[str, list[int]]) -> dict[str, Any]:
    k = stable_id(seed, table, i)
    common = _common(table, i)
    if table == "patients":
        return {
            "patient_id": k,
            "enterprise_person_id": (
                f"00000000-0000-4000-8000-{stable_id(seed, 'patients', i) % 10**12:012d}"
            ),
            "first_name": f"Synthetic{i:06d}",
            "last_name": f"Person{i:06d}",
            "date_of_birth": f"{1960 + i % 45:04d}-{i % 12 + 1:02d}-{i % 27 + 1:02d}",
            "sex": "FMXU"[i % 4],
            "email": f"person{i}@example.invalid",
            "phone": f"+1-555-{i % 10000:04d}",
            "synthetic_national_id": f"SYN-NID-{i:012d}",
            "source_schema_version": "v1",
            "created_at": _iso(i),
            **common,
        }
    if table == "members":
        enterprise_id = stable_id(seed, "patients", i) % 10**12
        return {
            "member_id": k,
            "enterprise_person_id": f"00000000-0000-4000-8000-{enterprise_id:012d}",
            "first_name": f"Synthetic{i:06d}",
            "last_name": f"Person{i:06d}",
            "date_of_birth": f"{1960 + i % 45:04d}-{i % 12 + 1:02d}-{i % 27 + 1:02d}",
            "sex": "FMXU"[i % 4],
            "member_number": f"SM{i:09d}",
            "email": f"person{i}@example.invalid",
            "phone": f"+1-555-{i % 10000:04d}",
            "source_schema_version": "v1",
            **common,
        }
    if table == "providers":
        return {
            "provider_id": k,
            "provider_external_id": f"PROV-{i:08d}",
            "provider_name": f"Synthetic Provider {i}",
            "specialty": ["primary_care", "cardiology", "oncology", "pediatrics"][i % 4],
            "npi_like": f"9{i:09d}",
            **common,
        }
    if table == "facilities":
        return {
            "facility_id": k,
            "facility_name": f"Synthetic Facility {i}",
            "facility_type": ["hospital", "clinic", "laboratory"][i % 3],
            "city": ["Phoenix", "Dallas", "Boston", "Denver"][i % 4],
            "state_code": ["AZ", "TX", "MA", "CO"][i % 4],
            **common,
        }
    if table == "plans":
        return {
            "plan_id": i + 1,
            "plan_code": f"PLAN-{i + 1:03d}",
            "plan_name": f"Synthetic Plan {i + 1}",
            "plan_type": ["HMO", "PPO", "EPO"][i % 3],
            "region_code": ["WEST", "SOUTH", "EAST"][i % 3],
            **common,
        }
    if table == "provider_facility_affiliation":
        return {
            "affiliation_id": k,
            "provider_id": refs["provider"][i % len(refs["provider"])],
            "facility_id": refs["facility"][i % len(refs["facility"])],
            "effective_start_date": "2025-01-01",
            "effective_end_date": None,
            **common,
        }
    if table == "encounters":
        return {
            "encounter_id": k,
            "patient_id": refs["patient"][i % len(refs["patient"])],
            "provider_id": refs["provider"][i % len(refs["provider"])],
            "facility_id": refs["facility"][i % len(refs["facility"])],
            "encounter_type": ["office", "inpatient", "emergency"][i % 3],
            "encounter_start": _iso(i, 100),
            "encounter_end": _iso(i, 160),
            "status": "completed",
            **common,
        }
    if table in {"diagnoses", "procedures", "observations"}:
        encounter = refs["encounter"][i % len(refs["encounter"])]
        patient = refs["patient"][i % len(refs["patient"])]
        if table == "diagnoses":
            return {
                "diagnosis_id": k,
                "encounter_id": encounter,
                "patient_id": patient,
                "diagnosis_code": ["SYN-A01", "SYN-B02", "SYN-C03"][i % 3],
                "diagnosis_type": "principal",
                "sequence_number": 1,
                **common,
            }
        if table == "procedures":
            return {
                "procedure_id": k,
                "encounter_id": encounter,
                "patient_id": patient,
                "procedure_code": f"PROC-{i % 20:03d}",
                "procedure_date": _day(i),
                **common,
            }
        return {
            "observation_id": k,
            "encounter_id": encounter,
            "patient_id": patient,
            "observation_code": ["SYN-BP", "SYN-TEMP", "SYN-HR"][i % 3],
            "observation_value": round(60 + (i % 80) * 0.7, 3),
            "unit": "unit",
            "observed_at": _iso(i, 120),
            **common,
        }
    if table == "medications":
        return {
            "medication_id": k,
            "medication_code": f"MED-{i:04d}",
            "medication_name": f"Synthetic Medication {i}",
            "therapeutic_class": "synthetic",
            **common,
        }
    if table == "prescriptions":
        return {
            "prescription_id": k,
            "patient_id": refs["patient"][i % len(refs["patient"])],
            "encounter_id": refs["encounter"][i % len(refs["encounter"])],
            "medication_id": refs["medication"][i % len(refs["medication"])],
            "prescribed_date": _day(i),
            "status": "active",
            "quantity": 30,
            **common,
        }
    if table == "member_enrollment":
        return {
            "enrollment_id": k,
            "member_id": refs["member"][i % len(refs["member"])],
            "plan_id": refs["plan"][i % len(refs["plan"])],
            "coverage_start_date": "2025-01-01",
            "coverage_end_date": "2025-12-31",
            "status": "active",
            **common,
        }
    if table == "claims":
        billed = 100 + (i % 100) * 10
        allowed = round(billed * 0.8, 2)
        paid = round(allowed * (0.9 if i % 10 else 0), 2)
        return {
            "claim_id": k,
            "member_id": refs["member"][i % len(refs["member"])],
            "provider_id": refs["provider"][i % len(refs["provider"])],
            "facility_id": refs["facility"][i % len(refs["facility"])],
            "claim_number": f"CLM-{i:010d}",
            "service_start_date": _day(i),
            "service_end_date": _day(i),
            "received_date": _day(i + 2),
            "status": "paid" if paid else "denied",
            "billed_amount": billed,
            "allowed_amount": allowed,
            "paid_amount": paid,
            "source_schema_version": "v1",
            **common,
        }
    if table == "claim_lines":
        claim_index = i % len(refs["claim"])
        billed = round(50 + (i % 50) * 3.0, 2)
        allowed = round(billed * 0.8, 2)
        return {
            "claim_line_id": k,
            "claim_id": refs["claim"][claim_index],
            "line_number": i // len(refs["claim"]) + 1,
            "procedure_code": f"PROC-{i % 20:03d}",
            "service_date": _day(i),
            "billed_amount": billed,
            "allowed_amount": allowed,
            "paid_amount": round(allowed * 0.9, 2),
            "line_status": "paid",
            **common,
        }
    if table == "claim_diagnoses":
        return {
            "claim_diagnosis_id": k,
            "claim_id": refs["claim"][i % len(refs["claim"])],
            "diagnosis_code": ["SYN-A01", "SYN-B02"][i % 2],
            "sequence_number": 1,
            **common,
        }
    if table == "authorizations":
        return {
            "authorization_id": k,
            "member_id": refs["member"][i % len(refs["member"])],
            "provider_id": refs["provider"][i % len(refs["provider"])],
            "authorization_number": f"AUTH-{i:010d}",
            "requested_date": _day(i),
            "decision_date": _day(i + 1),
            "status": "approved",
            "requested_units": 10,
            "approved_units": 10,
            **common,
        }
    if table == "payments":
        return {
            "payment_id": k,
            "claim_id": refs["claim"][i % len(refs["claim"])],
            "payment_reference": f"PAY-{i:010d}",
            "payment_date": _day(i + 5),
            "paid_amount": round(10 + (i % 20), 2),
            "payment_status": "posted",
            **common,
        }
    if table == "claim_adjustments":
        return {
            "adjustment_id": k,
            "claim_id": refs["claim"][i % len(refs["claim"])],
            "adjustment_type": "recoupment",
            "adjustment_reason": "synthetic correction",
            "adjustment_amount": round(i % 25, 2),
            "adjustment_date": _day(i + 6),
            **common,
        }
    raise KeyError(table)


def _counts(profile: str) -> dict[str, int]:
    if profile not in COUNTS:
        raise ValueError(f"unknown profile: {profile}; expected one of {', '.join(COUNTS)}")
    counts = {table: 0 for table in ALL_TABLES}
    counts.update(COUNTS[profile])
    counts["members"] = counts["patients"]
    counts.update(
        {
            "providers": max(10, counts["patients"] // 20),
            "facilities": max(5, counts["patients"] // 100),
            "provider_facility_affiliation": max(10, counts["patients"] // 20),
            "diagnoses": counts["encounters"],
            "procedures": counts["encounters"],
            "observations": counts["encounters"],
            "medications": max(20, counts["patients"] // 10),
            "prescriptions": counts["encounters"],
            "plans": 3,
            "member_enrollment": counts["patients"],
            "claim_diagnoses": counts["claims"],
            "authorizations": counts["claims"] // 2,
            "payments": counts["claims"] // 2,
            "claim_adjustments": counts["claims"] // 10,
        }
    )
    return counts


def generate(
    profile: str = "tiny",
    seed: int = 20260905,
    batch_id: str = "initial",
    output_dir: str | Path = "data/generated",
) -> dict[str, Any]:
    counts = _counts(profile)
    out = Path(output_dir) / batch_id
    out.mkdir(parents=True, exist_ok=True)
    refs = {
        "patient": [stable_id(seed, "patients", i) for i in range(counts["patients"])],
        "member": [stable_id(seed, "members", i) for i in range(counts["members"])],
        "provider": [stable_id(seed, "providers", i) for i in range(counts["providers"])],
        "facility": [stable_id(seed, "facilities", i) for i in range(counts["facilities"])],
        "encounter": [stable_id(seed, "encounters", i) for i in range(counts["encounters"])],
        "medication": [stable_id(seed, "medications", i) for i in range(counts["medications"])],
        "claim": [stable_id(seed, "claims", i) for i in range(counts["claims"])],
        "plan": list(range(1, counts["plans"] + 1)),
    }
    metadata: dict[str, Any] = {}
    for table in ALL_TABLES:
        domain = "clinical_provider" if table in TABLES["clinical_provider"] else "member_claims"
        table_dir = out / domain
        table_dir.mkdir(exist_ok=True)
        file_path = table_dir / f"{table}.jsonl"
        digest = hashlib.sha256()
        columns: list[str] = []
        row_count = 0
        with file_path.open("w", encoding="utf-8", newline="\n") as handle:
            for i in range(counts[table]):
                row = _row(table, i, seed, refs)
                columns = columns or list(row)
                line = json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
                handle.write(line)
                digest.update(line.encode())
                row_count += 1
        metadata[f"{domain}.{table}"] = {
            "path": str(file_path.relative_to(out)),
            "row_count": row_count,
            "sha256": digest.hexdigest(),
            "columns": sorted(columns),
        }
    manifest = {
        "batch_id": batch_id,
        "profile": profile,
        "seed": seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "tables": ALL_TABLES,
        "format": "jsonl",
        "table_metadata": metadata,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
