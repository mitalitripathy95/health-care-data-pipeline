"""Versioned source schema registry. Spark never infers authoritative Bronze schemas."""

from __future__ import annotations

from .contracts import SchemaContract

# Source-aligned types use Spark SQL names. Nullable source fields remain nullable at runtime;
# required_columns contains every NOT NULL source column from Phase 1 DDL.
_TABLES: dict[tuple[str, str, str], tuple[dict[str, str], set[str]]] = {}


def _add(source: str, schema: str, table: str, columns: str, required: str) -> None:
    parsed = dict(item.split(":", 1) for item in columns.split())
    _TABLES[(source, schema, table)] = (parsed, set(required.split()))


_add(
    "clinical_provider",
    "clinical",
    "patients",
    (
        "patient_id:long enterprise_person_id:string first_name:string"
        " last_name:string date_of_birth:date sex:string email:string phone:string"
        " address_line1:string city:string state_code:string postal_code:string"
        " synthetic_national_id:string source_schema_version:string"
        " created_at:timestamp updated_at:timestamp is_deleted:boolean"
    ),
    (
        "patient_id enterprise_person_id first_name last_name date_of_birth sex"
        " source_schema_version created_at updated_at is_deleted"
    ),
)
_add(
    "clinical_provider",
    "clinical",
    "providers",
    (
        "provider_id:long provider_external_id:string provider_name:string"
        " specialty:string npi_like:string updated_at:timestamp is_deleted:boolean"
    ),
    ("provider_id provider_external_id provider_name specialty npi_like updated_at is_deleted"),
)
_add(
    "clinical_provider",
    "clinical",
    "facilities",
    (
        "facility_id:long facility_name:string facility_type:string city:string"
        " state_code:string updated_at:timestamp is_deleted:boolean"
    ),
    "facility_id facility_name facility_type city state_code updated_at is_deleted",
)
_add(
    "clinical_provider",
    "clinical",
    "provider_facility_affiliation",
    (
        "affiliation_id:long provider_id:long facility_id:long"
        " effective_start_date:date effective_end_date:date updated_at:timestamp"
        " is_deleted:boolean"
    ),
    "affiliation_id provider_id facility_id effective_start_date updated_at is_deleted",
)
_add(
    "clinical_provider",
    "clinical",
    "encounters",
    (
        "encounter_id:long patient_id:long provider_id:long facility_id:long"
        " encounter_type:string encounter_start:timestamp encounter_end:timestamp"
        " status:string updated_at:timestamp is_deleted:boolean"
    ),
    (
        "encounter_id patient_id provider_id facility_id encounter_type"
        " encounter_start status updated_at is_deleted"
    ),
)
_add(
    "clinical_provider",
    "clinical",
    "diagnoses",
    (
        "diagnosis_id:long encounter_id:long patient_id:long"
        " diagnosis_code:string diagnosis_type:string sequence_number:short"
        " updated_at:timestamp is_deleted:boolean"
    ),
    (
        "diagnosis_id encounter_id patient_id diagnosis_code diagnosis_type"
        " sequence_number updated_at is_deleted"
    ),
)
_add(
    "clinical_provider",
    "clinical",
    "procedures",
    (
        "procedure_id:long encounter_id:long patient_id:long"
        " procedure_code:string procedure_date:date updated_at:timestamp"
        " is_deleted:boolean"
    ),
    ("procedure_id encounter_id patient_id procedure_code procedure_date updated_at is_deleted"),
)
_add(
    "clinical_provider",
    "clinical",
    "observations",
    (
        "observation_id:long encounter_id:long patient_id:long"
        " observation_code:string observation_value:decimal(12,3) unit:string"
        " observed_at:timestamp updated_at:timestamp is_deleted:boolean"
    ),
    ("observation_id encounter_id patient_id observation_code observed_at updated_at is_deleted"),
)
_add(
    "clinical_provider",
    "clinical",
    "medications",
    (
        "medication_id:long medication_code:string medication_name:string"
        " therapeutic_class:string updated_at:timestamp is_deleted:boolean"
    ),
    ("medication_id medication_code medication_name therapeutic_class updated_at is_deleted"),
)
_add(
    "clinical_provider",
    "clinical",
    "prescriptions",
    (
        "prescription_id:long patient_id:long encounter_id:long"
        " medication_id:long prescribed_date:date status:string quantity:integer"
        " updated_at:timestamp is_deleted:boolean"
    ),
    (
        "prescription_id patient_id medication_id prescribed_date status quantity"
        " updated_at is_deleted"
    ),
)
_add(
    "member_claims",
    "payer",
    "members",
    (
        "member_id:long enterprise_person_id:string first_name:string"
        " last_name:string date_of_birth:date sex:string member_number:string"
        " email:string phone:string modified_at:timestamp is_deleted:boolean"
        " source_schema_version:string"
    ),
    (
        "member_id enterprise_person_id first_name last_name date_of_birth sex"
        " member_number modified_at is_deleted source_schema_version"
    ),
)
_add(
    "member_claims",
    "payer",
    "plans",
    (
        "plan_id:integer plan_code:string plan_name:string plan_type:string"
        " region_code:string modified_at:timestamp is_deleted:boolean"
    ),
    "plan_id plan_code plan_name plan_type region_code modified_at is_deleted",
)
_add(
    "member_claims",
    "payer",
    "member_enrollment",
    (
        "enrollment_id:long member_id:long plan_id:integer"
        " coverage_start_date:date coverage_end_date:date status:string"
        " modified_at:timestamp is_deleted:boolean"
    ),
    "enrollment_id member_id plan_id coverage_start_date status modified_at is_deleted",
)
_add(
    "member_claims",
    "payer",
    "claims",
    (
        "claim_id:long member_id:long provider_id:long facility_id:long"
        " claim_number:string service_start_date:date service_end_date:date"
        " received_date:date status:string billed_amount:decimal(14,2)"
        " allowed_amount:decimal(14,2) paid_amount:decimal(14,2)"
        " modified_at:timestamp is_deleted:boolean source_schema_version:string"
    ),
    (
        "claim_id member_id provider_id facility_id claim_number"
        " service_start_date service_end_date received_date status billed_amount"
        " allowed_amount paid_amount modified_at is_deleted source_schema_version"
    ),
)
_add(
    "member_claims",
    "payer",
    "claim_lines",
    (
        "claim_line_id:long claim_id:long line_number:integer"
        " procedure_code:string service_date:date billed_amount:decimal(14,2)"
        " allowed_amount:decimal(14,2) paid_amount:decimal(14,2)"
        " line_status:string modified_at:timestamp is_deleted:boolean"
    ),
    (
        "claim_line_id claim_id line_number procedure_code service_date"
        " billed_amount allowed_amount paid_amount line_status modified_at"
        " is_deleted"
    ),
)
_add(
    "member_claims",
    "payer",
    "claim_diagnoses",
    (
        "claim_diagnosis_id:long claim_id:long diagnosis_code:string"
        " sequence_number:short modified_at:timestamp is_deleted:boolean"
    ),
    "claim_diagnosis_id claim_id diagnosis_code sequence_number modified_at is_deleted",
)
_add(
    "member_claims",
    "payer",
    "authorizations",
    (
        "authorization_id:long member_id:long provider_id:long"
        " authorization_number:string requested_date:date decision_date:date"
        " status:string requested_units:integer approved_units:integer"
        " modified_at:timestamp is_deleted:boolean"
    ),
    (
        "authorization_id member_id provider_id authorization_number"
        " requested_date status requested_units approved_units modified_at"
        " is_deleted"
    ),
)
_add(
    "member_claims",
    "payer",
    "payments",
    (
        "payment_id:long claim_id:long payment_reference:string payment_date:date"
        " paid_amount:decimal(14,2) payment_status:string modified_at:timestamp"
        " is_deleted:boolean"
    ),
    (
        "payment_id claim_id payment_reference payment_date paid_amount"
        " payment_status modified_at is_deleted"
    ),
)
_add(
    "member_claims",
    "payer",
    "claim_adjustments",
    (
        "adjustment_id:long claim_id:long adjustment_type:string"
        " adjustment_reason:string adjustment_amount:decimal(14,2)"
        " adjustment_date:date modified_at:timestamp is_deleted:boolean"
    ),
    (
        "adjustment_id claim_id adjustment_type adjustment_reason"
        " adjustment_amount adjustment_date modified_at is_deleted"
    ),
)


def get_contract(
    source_system: str, source_schema: str, source_table: str, version: str = "v1"
) -> SchemaContract:
    if version != "v1":
        raise KeyError(f"Unsupported schema version: {version}")
    key = (source_system, source_schema, source_table)
    try:
        columns, required = _TABLES[key]
    except KeyError as exc:
        raise KeyError(f"Unregistered source table: {'.'.join(key)}") from exc
    return SchemaContract(*key, version, columns, frozenset(required))


def registered_tables() -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted(_TABLES))
