"""Pure Silver data-quality rules and metric aggregation.

The module deliberately contains no Spark imports.  It is the contract seam used by
the runtime adapter and by local tests.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from .contracts import (
    QualityIssue,
    authorization_units_issue,
    date_order_issue,
    financial_issue,
    normalize_claim_status,
    positive_issue,
    referential_issue,
)


def _required(row: Mapping[str, Any], fields: Iterable[str]) -> list[QualityIssue]:
    return [
        QualityIssue("REQUIRED_NULL", f"{field} is required", severity="ERROR", field=field)
        for field in fields
        if row.get(field) is None
    ]


def cast_error_issues(cast_errors: Iterable[Mapping[str, Any]]) -> list[QualityIssue]:
    return [
        QualityIssue(
            "CAST_FAILURE",
            f"Cannot cast {error.get('field')} value {error.get('value')!r} to {error.get('type')}",
            severity="ERROR",
            field=str(error.get("field")),
        )
        for error in cast_errors
    ]


def evaluate_row(
    row: Mapping[str, Any],
    table: str,
    required_fields: Iterable[str] = (),
    parent_keys: Mapping[str, set[Any]] | None = None,
    known_late_keys: Mapping[str, set[Any]] | None = None,
    cast_errors: Iterable[Mapping[str, Any]] = (),
) -> list[QualityIssue]:
    """Evaluate common and table-specific quality rules for one conformed row."""
    issues = _required(row, required_fields)
    issues.extend(cast_error_issues(cast_errors))
    for start, end in (
        ("encounter_start", "encounter_end"),
        ("effective_start_date", "effective_end_date"),
        ("service_start", "service_end"),
    ):
        issue = date_order_issue(row, start, end)
        if issue:
            issues.append(issue)
    issue = financial_issue(row)
    if issue:
        issues.append(issue)
    for field in ("quantity", "requested_units", "billed_units"):
        issue = positive_issue(row, field)
        if issue:
            issues.append(issue)
    issue = authorization_units_issue(row)
    if issue:
        issues.append(issue)
    if table in {"claims", "claim_lines"} and row.get("status") is not None:
        if normalize_claim_status(row.get("status")) == "UNKNOWN":
            issues.append(
                QualityIssue(
                    "CLAIM_STATUS",
                    "Claim status is not recognized",
                    severity="WARNING",
                    field="status",
                )
            )
    for field, keys in (parent_keys or {}).items():
        issue = referential_issue(row, field, keys, (known_late_keys or {}).get(field))
        if issue:
            issues.append(issue)
    return issues


def quarantine_record(
    row: Mapping[str, Any],
    issues: Iterable[QualityIssue],
    processed_at: Any = None,
    *,
    source_system: str | None = None,
    source_schema: str | None = None,
    source_table: str | None = None,
) -> dict[str, Any]:
    issues = list(issues)
    return {
        "_silver_record_hash": row.get("_silver_record_hash") or row.get("_record_hash"),
        "_ingest_batch_id": row.get("_ingest_batch_id"),
        "_source_system": source_system or row.get("_source_system"),
        "_source_schema": source_schema or row.get("_source_schema"),
        "_source_table": source_table or row.get("_source_table"),
        "_quarantine_reason": "; ".join(issue.rule_code for issue in issues),
        "_quarantine_severity": max(
            (issue.severity for issue in issues), key=_severity_rank, default="ERROR"
        ),
        "_quarantine_details": "; ".join(issue.reason for issue in issues),
        "_silver_quarantined_at": processed_at or datetime.now(timezone.utc),
        "_raw_record": dict(row),
    }


def _severity_rank(value: str) -> int:
    return {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}.get(value, 2)


def aggregate_quality_metrics(
    *,
    batch_id: str,
    source_system: str,
    source_table: str,
    input_rows: int,
    published_rows: int,
    quarantined_rows: int,
    duplicate_rows: int = 0,
    late_rows: int = 0,
    issues: Iterable[QualityIssue] = (),
    processed_at: Any = None,
) -> list[dict[str, Any]]:
    counts = Counter(issue.rule_code for issue in issues)
    severities = Counter(issue.severity for issue in issues)
    base = {
        "batch_id": batch_id,
        "source_system": source_system,
        "source_table": source_table,
        "input_rows": input_rows,
        "published_rows": published_rows,
        "quarantined_rows": quarantined_rows,
        "duplicate_rows": duplicate_rows,
        "late_rows": late_rows,
        "warning_rows": severities["WARNING"],
        "error_rows": severities["ERROR"],
        "critical_rows": severities["CRITICAL"],
        "processed_at": processed_at or datetime.now(timezone.utc),
    }
    if not counts:
        return [{**base, "rule_code": "NONE", "metric_value": 0}]
    return [
        {**base, "rule_code": code, "metric_value": count} for code, count in sorted(counts.items())
    ]


def aggregate_reconciliation_metrics(
    *,
    batch_id: str,
    source_system: str,
    source_table: str,
    claim_count: int,
    line_count: int,
    payment_count: int,
    header_paid_total: Any,
    line_paid_total: Any,
    payment_paid_total: Any,
    processed_at: Any = None,
) -> list[dict[str, Any]]:
    return [
        {
            "batch_id": batch_id,
            "source_system": source_system,
            "source_table": source_table,
            "claim_count": claim_count,
            "line_count": line_count,
            "payment_count": payment_count,
            "header_paid_total": header_paid_total,
            "line_paid_total": line_paid_total,
            "payment_paid_total": payment_paid_total,
            "header_line_delta": header_paid_total - line_paid_total,
            "header_payment_delta": header_paid_total - payment_paid_total,
            "processed_at": processed_at or datetime.now(timezone.utc),
        }
    ]


def critical_issues(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    return [issue for issue in issues if issue.severity == "CRITICAL"]
