"""Silver contracts, classifications, and deterministic domain rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

CANONICAL_CLAIM_STATUSES = frozenset(
    {
        "SUBMITTED",
        "PENDING",
        "APPROVED",
        "DENIED",
        "PAID",
        "ADJUSTED",
        "REVERSED",
        "VOID",
        "UNKNOWN",
    }
)
STATUS_MAP = {
    "SUBMIT": "SUBMITTED",
    "SUBMITTED": "SUBMITTED",
    "RECEIVED": "SUBMITTED",
    "PEND": "PENDING",
    "PENDING": "PENDING",
    "APPROVE": "APPROVED",
    "APPROVED": "APPROVED",
    "DENY": "DENIED",
    "DENIED": "DENIED",
    "PAY": "PAID",
    "PAID": "PAID",
    "ADJUST": "ADJUSTED",
    "ADJUSTED": "ADJUSTED",
    "REVERSE": "REVERSED",
    "REVERSED": "REVERSED",
    "VOID": "VOID",
    "CANCELLED": "VOID",
    "CANCELED": "VOID",
}
TABLE_KEYS = {
    "patients": ("patient_id",),
    "providers": ("provider_id",),
    "facilities": ("facility_id",),
    "provider_facility_affiliation": ("affiliation_id",),
    "encounters": ("encounter_id",),
    "diagnoses": ("diagnosis_id",),
    "procedures": ("procedure_id",),
    "observations": ("observation_id",),
    "medications": ("medication_id",),
    "prescriptions": ("prescription_id",),
    "members": ("member_id",),
    "plans": ("plan_id",),
    "member_enrollment": ("enrollment_id",),
    "claims": ("claim_id",),
    "claim_lines": ("claim_line_id",),
    "claim_diagnoses": ("claim_diagnosis_id",),
    "authorizations": ("authorization_id",),
    "payments": ("payment_id",),
    "claim_adjustments": ("adjustment_id",),
}
# Child-column to parent-table relationships used by the runtime quality gate.
# The mapping is intentionally explicit: a missing parent is either an invalid
# reference or a late reference when the parent key is present in this batch.
REFERENTIAL_RELATIONSHIPS = {
    "provider_facility_affiliation": {"provider_id": "providers", "facility_id": "facilities"},
    "encounters": {
        "patient_id": "patients",
        "provider_id": "providers",
        "facility_id": "facilities",
    },
    "diagnoses": {"encounter_id": "encounters", "patient_id": "patients"},
    "procedures": {"encounter_id": "encounters", "patient_id": "patients"},
    "observations": {"encounter_id": "encounters", "patient_id": "patients"},
    "prescriptions": {
        "patient_id": "patients",
        "encounter_id": "encounters",
        "medication_id": "medications",
    },
    "member_enrollment": {"member_id": "members", "plan_id": "plans"},
    "claims": {"member_id": "members", "provider_id": "providers", "facility_id": "facilities"},
    "claim_lines": {"claim_id": "claims"},
    "claim_diagnoses": {"claim_id": "claims"},
    "authorizations": {"member_id": "members", "provider_id": "providers"},
    "payments": {"claim_id": "claims"},
    "claim_adjustments": {"claim_id": "claims"},
}
EVENT_FIELDS = {
    "claims": "service_start_date",
    "claim_lines": "service_date",
    "encounters": "encounter_start",
    "procedures": "procedure_date",
    "observations": "observed_at",
    "prescriptions": "prescribed_date",
    "member_enrollment": "coverage_start_date",
    "provider_facility_affiliation": "effective_start_date",
    "authorizations": "requested_date",
    "payments": "payment_date",
    "claim_adjustments": "adjustment_date",
}
DIRECT_IDENTIFIER_FIELDS = (
    "patient_id",
    "member_id",
    "member_number",
    "enterprise_person_id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address_line1",
    "address_line2",
    "synthetic_national_id",
    "provider_id",
    "facility_id",
    "claim_id",
    "claim_line_id",
    "payment_id",
    "authorization_id",
    "encounter_id",
)
SENSITIVE_FIELDS = frozenset(
    DIRECT_IDENTIFIER_FIELDS
    + (
        "date_of_birth",
        "service_date",
        "diagnosis_code",
        "procedure_code",
        "billed_amount",
        "allowed_amount",
        "paid_amount",
    )
)


@dataclass(frozen=True)
class QualityIssue:
    rule_code: str
    reason: str
    severity: str = "ERROR"
    classification: str = "INVALID"
    field: str | None = None


def normalize_claim_status(value: Any) -> str:
    return STATUS_MAP.get(str(value or "").strip().upper(), "UNKNOWN")


def _decimal(row: dict[str, Any], field: str) -> Decimal | None:
    value = row.get(field)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def financial_issue(row: dict[str, Any]) -> QualityIssue | None:
    values = [_decimal(row, field) for field in ("billed_amount", "allowed_amount", "paid_amount")]
    if any(value is None for value in values) and any(
        row.get(field) is not None for field in ("billed_amount", "allowed_amount", "paid_amount")
    ):
        return QualityIssue(
            "FINANCIAL_TYPE", "Financial amount is not numeric", field="financial_amount"
        )
    if any(value is None for value in values):
        return None
    billed, allowed, paid = values
    if min(billed, allowed, paid) < 0 or not paid <= allowed <= billed:
        return QualityIssue(
            "FINANCIAL_ORDER",
            "Expected 0 <= paid_amount <= allowed_amount <= billed_amount",
            field="financial_amount",
        )
    return None


def positive_issue(row: dict[str, Any], field: str) -> QualityIssue | None:
    value = _decimal(row, field)
    if row.get(field) is not None and value is None:
        return QualityIssue("VALUE_TYPE", f"{field} is not numeric", field=field)
    if value is not None and value <= 0:
        return QualityIssue("POSITIVE_VALUE", f"{field} must be greater than zero", field=field)
    return None


def authorization_units_issue(row: dict[str, Any]) -> QualityIssue | None:
    requested, approved = _decimal(row, "requested_units"), _decimal(row, "approved_units")
    if requested is None or approved is None:
        return None
    if requested <= 0 or approved < 0 or approved > requested:
        return QualityIssue(
            "AUTHORIZATION_UNITS",
            "Expected 0 <= approved_units <= requested_units and requested_units > 0",
            field="approved_units",
        )
    return None


def referential_issue(
    row: dict[str, Any],
    field: str,
    parent_keys: set[Any] | None,
    known_late_keys: set[Any] | None = None,
) -> QualityIssue | None:
    value = row.get(field)
    if value is None or parent_keys is None or value in parent_keys:
        return None
    late = known_late_keys is not None and value in known_late_keys
    return QualityIssue(
        "LATE_REFERENCE" if late else "REFERENTIAL_INTEGRITY",
        f"{field} does not exist in its parent",
        classification="LATE_REFERENCE" if late else "INVALID",
        field=field,
    )


def date_order_issue(row: dict[str, Any], start: str, end: str) -> QualityIssue | None:
    if row.get(start) is not None and row.get(end) is not None and row[end] < row[start]:
        return QualityIssue(
            "DATE_ORDER", f"{end} must be greater than or equal to {start}", field=end
        )
    return None


def claim_reconciliation_issue(
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    payments: list[dict[str, Any]] | None = None,
) -> QualityIssue | None:
    line_paid = sum((_decimal(line, "paid_amount") or Decimal("0") for line in lines), Decimal("0"))
    payment_paid = sum(
        (_decimal(payment, "paid_amount") or Decimal("0") for payment in (payments or [])),
        Decimal("0"),
    )
    expected = payment_paid if payments else line_paid
    actual = _decimal(header, "paid_amount")
    if actual is not None and actual != expected:
        return QualityIssue(
            "CLAIM_PAID_RECONCILIATION",
            f"Claim paid amount {actual} does not reconcile to {expected}",
            severity="ERROR",
            field="paid_amount",
        )
    return None
