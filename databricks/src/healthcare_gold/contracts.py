"""Gold dimensional contracts and stable physical schemas.

The contracts are deliberately Spark-independent so they can be validated in
unit tests without a Databricks runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

UNKNOWN_SK = -1
UNKNOWN_BATCH = "UNKNOWN"


@dataclass(frozen=True)
class GoldTable:
    name: str
    kind: str
    columns: dict[str, str]
    business_key: tuple[str, ...] = ()
    scd_type: int | None = None
    foreign_keys: dict[str, str] = None

    def __post_init__(self) -> None:
        if self.kind not in {"DIMENSION", "FACT", "BRIDGE", "DIAGNOSTIC"}:
            raise ValueError(f"Unsupported Gold table kind: {self.kind}")
        if self.kind == "DIMENSION" and self.scd_type not in {1, 2}:
            raise ValueError(f"{self.name} must define SCD 1 or SCD 2")
        if self.kind != "DIMENSION" and self.scd_type is not None:
            raise ValueError(f"SCD applies only to dimensions: {self.name}")
        object.__setattr__(self, "foreign_keys", dict(self.foreign_keys or {}))


COMMON_DIMENSION_COLUMNS = {
    "surrogate_key": "long",
    "_gold_batch_id": "string",
    "_is_inferred": "boolean",
    "effective_from": "timestamp",
    "effective_to": "timestamp",
    "is_current": "boolean",
    "_source_system": "string",
    "_source_schema": "string",
    "_source_table": "string",
    "_silver_record_hash": "string",
    "_record_hash": "string",
    "_gold_processed_at": "timestamp",
}


def _dimension(extra: dict[str, str], scd_type: int, business_key: tuple[str, ...]) -> GoldTable:
    return GoldTable(
        name="",
        kind="DIMENSION",
        columns={**COMMON_DIMENSION_COLUMNS, **extra},
        business_key=business_key,
        scd_type=scd_type,
    )


GOLD_TABLES: dict[str, GoldTable] = {
    "dim_patient": _dimension(
        {
            "patient_id": "long",
            "enterprise_person_id": "string",
            "first_name": "string",
            "last_name": "string",
            "date_of_birth": "date",
            "sex": "string",
            "email": "string",
            "phone": "string",
            "address_line1": "string",
            "city": "string",
            "state_code": "string",
            "postal_code": "string",
            "synthetic_national_id": "string",
        },
        2,
        ("patient_id",),
    ),
    "dim_member": _dimension(
        {
            "member_id": "long",
            "enterprise_person_id": "string",
            "first_name": "string",
            "last_name": "string",
            "date_of_birth": "date",
            "sex": "string",
            "member_number": "string",
            "email": "string",
            "phone": "string",
        },
        2,
        ("member_id",),
    ),
    "dim_provider": _dimension(
        {
            "provider_id": "long",
            "provider_external_id": "string",
            "provider_name": "string",
            "specialty": "string",
            "npi_like": "string",
        },
        2,
        ("provider_id",),
    ),
    "dim_facility": _dimension(
        {
            "facility_id": "long",
            "facility_name": "string",
            "facility_type": "string",
            "city": "string",
            "state_code": "string",
        },
        1,
        ("facility_id",),
    ),
    "dim_plan": _dimension(
        {
            "plan_id": "integer",
            "plan_code": "string",
            "plan_name": "string",
            "plan_type": "string",
            "region_code": "string",
        },
        1,
        ("plan_id",),
    ),
    "dim_date": _dimension(
        {
            "date_key": "integer",
            "date": "date",
            "year": "integer",
            "quarter": "integer",
            "month": "integer",
            "month_name": "string",
            "week_of_year": "integer",
            "day_of_month": "integer",
            "day_of_week": "integer",
            "day_name": "string",
            "is_weekend": "boolean",
        },
        1,
        ("date_key",),
    ),
    "dim_diagnosis": _dimension(
        {
            "diagnosis_code": "string",
            "diagnosis_type": "string",
        },
        1,
        ("diagnosis_code",),
    ),
    "dim_procedure": _dimension(
        {
            "procedure_code": "string",
            "procedure_description": "string",
        },
        1,
        ("procedure_code",),
    ),
    "dim_medication": _dimension(
        {
            "medication_id": "long",
            "medication_code": "string",
            "medication_name": "string",
            "therapeutic_class": "string",
        },
        1,
        ("medication_id",),
    ),
}


_COMMON_FACT_COLUMNS = {
    "surrogate_key": "long",
    "_gold_batch_id": "string",
    "_source_system": "string",
    "_source_schema": "string",
    "_source_table": "string",
    "_silver_record_hash": "string",
    "_record_hash": "string",
    "_gold_processed_at": "timestamp",
    "effective_from": "timestamp",
    "effective_to": "timestamp",
    "is_current": "boolean",
}


def _fact(name: str, extra: dict[str, str], foreign_keys: dict[str, str], event: str) -> GoldTable:
    return GoldTable(
        name=name,
        kind="FACT",
        columns={**_COMMON_FACT_COLUMNS, **extra, "date_key": "integer"},
        business_key=(event,),
        foreign_keys=foreign_keys,
    )


for _name, _event in (
    ("fact_encounter", "encounter_start"),
    ("fact_claim", "service_start_date"),
    ("fact_claim_line", "service_date"),
    ("fact_payment", "payment_date"),
    ("fact_authorization", "requested_date"),
    ("fact_observation", "observed_at"),
    ("fact_prescription", "prescribed_date"),
):
    GOLD_TABLES[_name] = _fact(
        _name,
        {"_event_field": "string"},
        {},
        _event,
    )

GOLD_TABLES["fact_encounter"].foreign_keys.update(
    {"patient_sk": "dim_patient", "provider_sk": "dim_provider", "facility_sk": "dim_facility"}
)
GOLD_TABLES["fact_claim"].foreign_keys.update(
    {"member_sk": "dim_member", "provider_sk": "dim_provider", "facility_sk": "dim_facility"}
)
GOLD_TABLES["fact_claim_line"].foreign_keys.update({"claim_sk": "fact_claim"})
GOLD_TABLES["fact_payment"].foreign_keys.update({"claim_sk": "fact_claim"})
GOLD_TABLES["fact_observation"].foreign_keys.update(
    {"encounter_sk": "fact_encounter", "patient_sk": "dim_patient"}
)
GOLD_TABLES["fact_prescription"].foreign_keys.update(
    {
        "patient_sk": "dim_patient",
        "encounter_sk": "fact_encounter",
        "medication_sk": "dim_medication",
    }
)
GOLD_TABLES["fact_authorization"].foreign_keys.update(
    {"member_sk": "dim_member", "provider_sk": "dim_provider"}
)

GOLD_TABLES["bridge_claim_diagnosis"] = GoldTable(
    "bridge_claim_diagnosis",
    "BRIDGE",
    {
        "bridge_key": "long",
        "claim_sk": "long",
        "diagnosis_sk": "long",
        "sequence_number": "integer",
        "_gold_batch_id": "string",
        "effective_from": "timestamp",
        "effective_to": "timestamp",
        "is_current": "boolean",
    },
    foreign_keys={"claim_sk": "fact_claim", "diagnosis_sk": "dim_diagnosis"},
)
GOLD_TABLES["bridge_provider_facility"] = GoldTable(
    "bridge_provider_facility",
    "BRIDGE",
    {
        "bridge_key": "long",
        "affiliation_id": "long",
        "provider_sk": "long",
        "facility_sk": "long",
        "effective_start_date": "date",
        "effective_end_date": "date",
        "_gold_batch_id": "string",
        "effective_from": "timestamp",
        "effective_to": "timestamp",
        "is_current": "boolean",
    },
    foreign_keys={"provider_sk": "dim_provider", "facility_sk": "dim_facility"},
)
GOLD_TABLES["bridge_member_enrollment"] = GoldTable(
    "bridge_member_enrollment",
    "BRIDGE",
    {
        "bridge_key": "long",
        "enrollment_id": "long",
        "member_sk": "long",
        "plan_sk": "long",
        "status": "string",
        "coverage_start_date": "date",
        "coverage_end_date": "date",
        "_gold_batch_id": "string",
        "effective_from": "timestamp",
        "effective_to": "timestamp",
        "is_current": "boolean",
    },
    foreign_keys={"member_sk": "dim_member", "plan_sk": "dim_plan"},
)

GOLD_TABLES["_gold_processing_audit"] = GoldTable(
    "_gold_processing_audit",
    "DIAGNOSTIC",
    {
        "batch_id": "string",
        "gold_table": "string",
        "input_rows": "long",
        "output_rows": "long",
        "inferred_rows": "long",
        "unknown_rows": "long",
        "unresolved_foreign_keys": "long",
        "status": "string",
        "error_message": "string",
        "processed_at": "timestamp",
    },
)
GOLD_TABLES["_gold_reconciliation_metrics"] = GoldTable(
    "_gold_reconciliation_metrics",
    "DIAGNOSTIC",
    {
        "batch_id": "string",
        "gold_table": "string",
        "foreign_key": "string",
        "expected_rows": "long",
        "resolved_rows": "long",
        "unknown_rows": "long",
        "status": "string",
        "processed_at": "timestamp",
    },
)

DIMENSION_TABLES = tuple(
    name for name, table in GOLD_TABLES.items() if table.kind == "DIMENSION"
)
FACT_TABLES = tuple(name for name, table in GOLD_TABLES.items() if table.kind == "FACT")
BRIDGE_TABLES = tuple(name for name, table in GOLD_TABLES.items() if table.kind == "BRIDGE")

DIMENSION_BY_SOURCE = {
    "patients": "dim_patient",
    "members": "dim_member",
    "providers": "dim_provider",
    "facilities": "dim_facility",
    "plans": "dim_plan",
    "diagnoses": "dim_diagnosis",
    "procedures": "dim_procedure",
    "medications": "dim_medication",
}

TRACKED_ATTRIBUTES = {
    "dim_patient": (
        "enterprise_person_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "sex",
        "email",
        "phone",
        "address_line1",
        "city",
        "state_code",
        "postal_code",
        "synthetic_national_id",
    ),
    "dim_member": (
        "enterprise_person_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "sex",
        "member_number",
        "email",
        "phone",
    ),
    "dim_provider": ("provider_external_id", "provider_name", "specialty", "npi_like"),
}

FOREIGN_KEY_SOURCES = {
    "encounters": {
        "patient_sk": ("patients", "patient_id"),
        "provider_sk": ("providers", "provider_id"),
        "facility_sk": ("facilities", "facility_id"),
    },
    "claims": {
        "member_sk": ("members", "member_id"),
        "provider_sk": ("providers", "provider_id"),
        "facility_sk": ("facilities", "facility_id"),
    },
    "claim_lines": {"claim_sk": ("claims", "claim_id")},
    "observations": {
        "encounter_sk": ("encounters", "encounter_id"),
        "patient_sk": ("patients", "patient_id"),
    },
    "prescriptions": {
        "patient_sk": ("patients", "patient_id"),
        "encounter_sk": ("encounters", "encounter_id"),
        "medication_sk": ("medications", "medication_id"),
    },
    "authorizations": {
        "member_sk": ("members", "member_id"),
        "provider_sk": ("providers", "provider_id"),
    },
    "payments": {"claim_sk": ("claims", "claim_id")},
}

SPECIALTY_DIMENSION_SOURCES = {
    "fact_encounter": {
        "patient_sk": ("patients", "patient_id"),
        "provider_sk": ("providers", "provider_id"),
        "facility_sk": ("facilities", "facility_id"),
    },
    "fact_claim": {
        "member_sk": ("members", "member_id"),
        "provider_sk": ("providers", "provider_id"),
        "facility_sk": ("facilities", "facility_id"),
    },
    "fact_claim_line": {"claim_sk": ("claims", "claim_id")},
    "fact_payment": {"claim_sk": ("claims", "claim_id")},
    "fact_observation": {
        "encounter_sk": ("encounters", "encounter_id"),
        "patient_sk": ("patients", "patient_id"),
    },
    "fact_prescription": {
        "patient_sk": ("patients", "patient_id"),
        "encounter_sk": ("encounters", "encounter_id"),
        "medication_sk": ("medications", "medication_id"),
    },
    "fact_authorization": {
        "member_sk": ("members", "member_id"),
        "provider_sk": ("providers", "provider_id"),
    },
}
