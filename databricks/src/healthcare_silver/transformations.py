"""Pure, deterministic Bronze-to-Silver transformations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from healthcare_bronze.contracts import record_hash

from .contracts import DIRECT_IDENTIFIER_FIELDS, TABLE_KEYS, normalize_claim_status
from .tokenization import hmac_token

PLACEHOLDERS = frozenset({"", "null", "n/a", "na", "none"})
UNKNOWN_ALIASES = frozenset({"unknown"})
NUMERIC_SENTINELS = frozenset({"999999", "-", "--"})
CATEGORICAL_NULL_FIELDS = frozenset(
    {
        "status",
        "line_status",
        "payment_status",
        "encounter_status",
        "enrollment_status",
        "authorization_status",
        "sex",
        "gender",
        "encounter_type",
        "diagnosis_type",
        "plan_type",
        "facility_type",
        "specialty",
        "unit",
    }
)
NUMERIC_SENTINEL_FIELDS = frozenset(
    {
        "quantity",
        "requested_units",
        "approved_units",
        "sequence_number",
        "line_number",
        "billed_amount",
        "allowed_amount",
        "paid_amount",
        "adjustment_amount",
        "observation_value",
    }
)
LINEAGE_FIELDS = (
    "_ingest_batch_id",
    "_ingest_run_id",
    "_ingest_ts",
    "_source_system",
    "_source_schema",
    "_source_table",
    "_source_file",
    "_record_hash",
    "_schema_version",
)


def normalize_value(value: Any, field: str | None = None) -> Any:
    if isinstance(value, str):
        text = value.strip()
        folded = text.casefold()
        if folded in PLACEHOLDERS:
            return None
        # UNKNOWN is not a universal null: an ID represented as "unknown" is a
        # value, while configured categorical fields can safely null it.
        if field in CATEGORICAL_NULL_FIELDS and folded in UNKNOWN_ALIASES:
            return None
        if field in NUMERIC_SENTINEL_FIELDS and folded in NUMERIC_SENTINELS:
            return None
        return text
    return value


def _decimal_spec(type_name: str) -> tuple[int, int] | None:
    if not type_name.startswith("decimal"):
        return None
    body = type_name[type_name.index("(") + 1 : type_name.index(")")]
    precision, scale = (int(part) for part in body.split(",", 1))
    return precision, scale


def cast_value(value: Any, type_name: str) -> Any:
    if value is None:
        return None
    if type_name in {"integer", "long", "short"}:
        return int(value)
    if type_name in {"float", "double"}:
        return float(value)
    if type_name.startswith("decimal"):
        spec = _decimal_spec(type_name)
        if spec is None:
            return Decimal(str(value))
        precision, scale = spec
        try:
            parsed = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError("invalid decimal") from exc
        if not parsed.is_finite():
            raise ValueError("invalid decimal")
        if -parsed.as_tuple().exponent > scale:
            raise ValueError("decimal scale exceeds target scale")
        quantum = Decimal(1).scaleb(-scale)
        quantized = parsed.quantize(quantum, rounding=ROUND_HALF_UP)
        if quantized != parsed:
            # Reject information loss rather than silently rounding amounts.
            raise ValueError("decimal scale exceeds target scale")
        if len(quantized.as_tuple().digits) > precision:
            raise ValueError("decimal precision exceeds target precision")
        return quantized
    if type_name == "boolean":
        if isinstance(value, bool):
            return value
        normalized = str(value).casefold()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise ValueError("invalid boolean")
    if type_name == "date":
        return date.fromisoformat(str(value)[:10])
    if type_name == "timestamp":
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    return value


def cast_row(
    row: Mapping[str, Any], casts: Mapping[str, str] | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    result = {
        str(key).strip().lower(): normalize_value(value, str(key).strip().lower())
        for key, value in row.items()
    }
    errors = []
    for field, type_name in (casts or {}).items():
        try:
            result[field] = cast_value(result.get(field), type_name)
        except (TypeError, ValueError, InvalidOperation, OverflowError):
            raw = result.get(field)
            reason = "TYPE"
            if (
                raw is not None
                and isinstance(raw, float | Decimal)
                and not Decimal(str(raw)).is_finite()
            ):
                reason = "PRECISION"
            result[field] = None
            errors.append(
                {
                    "field": field,
                    "value": str(raw),
                    "type": type_name,
                    "reason": reason,
                }
            )
    return result, errors


STATUS_FIELDS = frozenset(
    {
        "status",
        "line_status",
        "payment_status",
        "enrollment_status",
        "encounter_status",
        "authorization_status",
    }
)
CODE_FIELDS = frozenset(
    {
        "diagnosis_code",
        "procedure_code",
        "observation_code",
        "medication_code",
        "plan_code",
        "region_code",
        "state_code",
    }
)
UNIT_FIELDS = frozenset({"unit"})
SEX_FIELDS = frozenset({"sex", "gender"})


def standardize_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in STATUS_FIELDS:
        synonyms = {
            "IN NETWORK": "IN_NETWORK",
            "OUT OF NETWORK": "OUT_OF_NETWORK",
            "INPROGRESS": "IN_PROGRESS",
            "IN PROGRESS": "IN_PROGRESS",
            "CLOSED": "CLOSED",
            "OPEN": "OPEN",
            "ACTIVE": "ACTIVE",
            "INACTIVE": "INACTIVE",
            "TERMINATED": "TERMINATED",
        }
        return synonyms.get(str(value).strip().upper(), str(value).strip().upper())
    if field in CODE_FIELDS:
        return str(value).strip().upper()
    if field in UNIT_FIELDS:
        synonyms = {"MG": "MG", "ML": "ML", "UNITS": "UNITS", "UNIT": "UNIT"}
        return synonyms.get(str(value).strip().upper(), str(value).strip().upper())
    if field in SEX_FIELDS:
        synonyms = {"M": "M", "MALE": "M", "F": "F", "FEMALE": "F", "U": "U", "UNKNOWN": "U"}
        return synonyms.get(str(value).strip().upper(), "U")
    return value


def standardize_row(
    row: Mapping[str, Any], casts: Mapping[str, str] | None = None
) -> dict[str, Any]:
    result, _ = cast_row(row, casts)
    return {field: standardize_field(field, value) for field, value in result.items()}


def _rank(row: Mapping[str, Any]) -> tuple[str, ...]:
    def value(name: str) -> str:
        return "" if row.get(name) is None else str(row[name])

    return tuple(
        value(name)
        for name in (
            "source_business_version",
            "modified_at",
            "updated_at",
            "_ingest_ts",
            "batch_sequence",
            "_record_hash",
        )
    )


def deterministic_dedupe(
    rows: Iterable[Mapping[str, Any]], business_keys: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(row.get(key) for key in business_keys), []).append(row)
    winners, losers = [], []
    for group in groups.values():
        ordered = sorted(group, key=lambda row: (_rank(row), record_hash(row)), reverse=True)
        winners.append(dict(ordered[0]))
        losers.extend(dict(row) for row in ordered[1:])
    return winners, losers


def survivorship(
    rows: Iterable[Mapping[str, Any]], business_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Merge current and prior rows into one non-null-enriched state per key.

    Rows are expected to be already conformed.  Prior rows participate in the
    same deterministic ordering, but can never remove a newer explicit delete.
    """
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(row.get(key) for key in business_keys), []).append(row)
    output = []
    for group in groups.values():
        ordered = sorted(group, key=lambda row: (_rank(row), record_hash(row)), reverse=True)
        winner = dict(ordered[0])
        if winner.get("is_deleted"):
            winner["_survivorship_action"] = "DELETE"
        else:
            for row in ordered:
                for key, value in row.items():
                    if winner.get(key) is None and value is not None:
                        winner[key] = value
            winner["_survivorship_action"] = "MERGE_NON_NULL"
        winner["_survivorship_source_hashes"] = [
            str(row.get("_record_hash") or record_hash(row)) for row in ordered
        ]
        winner["_survivorship_is_current"] = winner.get("_record_hash") == str(
            ordered[0].get("_record_hash") or record_hash(ordered[0])
        )
        output.append(winner)
    return output


def classify_late_arrival(
    row: Mapping[str, Any],
    current_batch_id: str,
    *,
    event_field: str | None = None,
    watermark: Any = None,
) -> bool:
    event = row.get(event_field) if event_field else None
    if watermark is not None and event is not None:
        # A date watermark and a timestamp event are both valid configuration
        # combinations. Compare like with like rather than relying on Python's
        # incompatible date/datetime ordering rules.
        if isinstance(watermark, date) and not isinstance(watermark, datetime):
            if isinstance(event, datetime):
                event = event.date()
            elif isinstance(event, str):
                event = date.fromisoformat(event[:10])
        elif (
            isinstance(watermark, datetime)
            and isinstance(event, date)
            and not isinstance(event, datetime)
        ):
            event = datetime.combine(event, datetime.min.time(), tzinfo=watermark.tzinfo)
        return event < watermark
    # Bronze input is normally batch-filtered, so batch identity alone cannot
    # identify late data. Without an event watermark, retain the conservative
    # answer: no row is late rather than labelling every current-batch row late.
    return False


def normalize_claim_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["original_status"] = row.get("status")
    result["status"] = normalize_claim_status(row.get("status"))
    if "line_status" in row:
        result["line_status"] = normalize_claim_status(row.get("line_status"))
    event = str(row.get("adjustment_type") or row.get("status") or "").strip().upper()
    result["lifecycle_event"] = {
        "ORIGINAL": "ORIGINAL",
        "REPLACEMENT": "REPLACEMENT",
        "REVERSAL": "REVERSAL",
        "VOID": "VOID",
    }.get(event, result["status"])
    result["is_current_state"] = result["lifecycle_event"] not in {"REVERSAL", "VOID"}
    return result


def generalized_geography(value: Any, *, granularity: str = "state") -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if granularity == "state":
        return text.upper()[:2] or None
    if granularity == "zip3":
        digits = "".join(char for char in text if char.isdigit())
        return digits[:3] or None
    raise ValueError("granularity must be state or zip3")


def restricted_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return dict(row)


def deidentified_projection(
    row: Mapping[str, Any],
    key: str,
    direct_fields: tuple[str, ...] = DIRECT_IDENTIFIER_FIELDS,
    *,
    token_version: str = "v1",
    table: str | None = None,
) -> dict[str, Any]:
    """Project the restricted row using the registry when a table is supplied."""
    if table is not None:
        from .privacy import project_deidentified

        return project_deidentified(row, key, table, token_version=token_version).projected_row
    result = dict(row)
    for field in direct_fields:
        if field in result:
            result[f"{field}_token"] = hmac_token(
                result[field], key, namespace=f"id:{field}", version=token_version
            )
            result.pop(field, None)
    if "city" in result:
        result.pop("city", None)
    if "state_code" in result:
        result["state_code"] = generalized_geography(result["state_code"], granularity="state")
    if "postal_code" in result:
        result["postal_code"] = generalized_geography(result["postal_code"], granularity="zip3")
    return result


def add_silver_metadata(
    row: Mapping[str, Any],
    *,
    processed_at: Any,
    transform_version: str = "v1",
    late_arriving: bool = False,
) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "_silver_processed_at": processed_at,
            "_silver_transform_version": transform_version,
            "_silver_is_late_arriving": late_arriving,
            "_silver_record_hash": result.get("_record_hash") or record_hash(result),
        }
    )
    return result


def table_business_keys(table: str) -> tuple[str, ...]:
    return TABLE_KEYS.get(table, ())
