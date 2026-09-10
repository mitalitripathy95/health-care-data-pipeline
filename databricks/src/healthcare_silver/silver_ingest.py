"""Spark/Delta adapter for Bronze-to-Silver promotion.

Business rules intentionally live in Spark-independent modules.  The adapter owns
batch boundaries, stable Delta schemas, publication gates, and auditability.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from healthcare_bronze.contracts import validate_safe_id
from healthcare_bronze.schema_registry import get_contract

from .contracts import EVENT_FIELDS, REFERENTIAL_RELATIONSHIPS, TABLE_KEYS
from .quality import (
    aggregate_quality_metrics,
    aggregate_reconciliation_metrics,
    evaluate_row,
    quarantine_record,
)
from .transformations import (
    add_silver_metadata,
    cast_row,
    classify_late_arrival,
    deidentified_projection,
    deterministic_dedupe,
    normalize_claim_row,
    survivorship,
    table_business_keys,
)

AUDIT_COLUMNS = (
    "batch_id string, source_system string, source_schema string, source_table string, "
    "input_rows long, published_rows long, quarantined_rows long, duplicate_rows long, "
    "late_rows long, status string, error_message string, processed_at timestamp"
)
DQ_COLUMNS = (
    "batch_id string, source_system string, source_table string, input_rows long, "
    "published_rows long, quarantined_rows long, duplicate_rows long, late_rows long, "
    "warning_rows long, error_rows long, critical_rows long, rule_code string, "
    "metric_value long, processed_at timestamp"
)
RECON_COLUMNS = (
    "batch_id string, source_system string, source_table string, claim_count long, "
    "line_count long, payment_count long, header_paid_total decimal(18,2), "
    "line_paid_total decimal(18,2), payment_paid_total decimal(18,2), "
    "header_line_delta decimal(18,2), header_payment_delta decimal(18,2), "
    "processed_at timestamp"
)
QUARANTINE_COLUMNS = (
    "_silver_record_hash string, _ingest_batch_id string, _source_system string, "
    "_source_schema string, _source_table string, _quarantine_reason string, "
    "_quarantine_severity string, _quarantine_details string, "
    "_silver_quarantined_at timestamp, _raw_record string"
)

CLINICAL_TABLES = frozenset(
    {
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
    }
)


def _name(config, schema, table):
    return f"{config.catalog_name}.{schema}.{table}"


def _domain(table):
    return (
        ("clinical_provider", "clinical")
        if table in CLINICAL_TABLES
        else ("member_claims", "payer")
    )


def _rows(frame):
    return [row.asDict(recursive=True) for row in frame.collect()]


def _spark_type(type_name):
    from healthcare_bronze.bronze_ingest import _spark_type as bronze_spark_type

    return bronze_spark_type(type_name)


def _table_schema(source_system, source_schema, table, rows, *, deidentified=False):
    """Build a stable schema from the registered contract plus Silver columns."""
    from pyspark.sql.types import BooleanType, StringType, StructField, StructType, TimestampType

    contract = get_contract(source_system, source_schema, table, "v1")
    # Do not leave the source identifier columns in the de-identified physical
    # schema as nullable placeholders.  A nullable column with every value set
    # to NULL is still discoverable through Unity Catalog and is easy to expose
    # accidentally in downstream SQL.  The projection removes these fields,
    # therefore the schema must remove them too and contain only their tokens.
    direct_identifier_fields = {
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
    }
    fields = [
        StructField(name, _spark_type(kind), name not in contract.required_columns)
        for name, kind in contract.columns.items()
        if not (deidentified and name in direct_identifier_fields)
    ]
    known = {field.name for field in fields}
    extras = {
        "original_status": StringType(),
        "lifecycle_event": StringType(),
        "_survivorship_action": StringType(),
        "_survivorship_source_hashes": StringType(),
        "_silver_processed_at": TimestampType(),
        "_silver_transform_version": StringType(),
        "_silver_is_late_arriving": BooleanType(),
        "_silver_record_hash": StringType(),
        "is_current_state": BooleanType(),
    }
    if deidentified:
        for field in (
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
        ):
            extras[f"{field}_token"] = StringType()
    for name, dtype in extras.items():
        if name not in known:
            fields.append(StructField(name, dtype, True))
    # Source lineage is part of the Silver contract.
    for name in (
        "_ingest_batch_id",
        "_ingest_run_id",
        "_ingest_ts",
        "_source_system",
        "_source_schema",
        "_source_table",
        "_source_file",
        "_record_hash",
        "_schema_version",
    ):
        if name not in known:
            fields.append(
                StructField(name, TimestampType() if name == "_ingest_ts" else StringType(), True)
            )
    return StructType(fields)


def _coerce_row(row):
    result = dict(row)
    if isinstance(result.get("_survivorship_source_hashes"), list):
        result["_survivorship_source_hashes"] = json.dumps(
            result["_survivorship_source_hashes"], separators=(",", ":")
        )
    return result


def _replace_batch(spark, rows, target, batch_id, schema, *, batch_column="_ingest_batch_id"):
    validate_safe_id(batch_id, "batch_id")
    frame = spark.createDataFrame([_coerce_row(row) for row in rows], schema=schema)
    if spark.catalog.tableExists(target):
        frame.write.format("delta").mode("overwrite").option(
            "replaceWhere", f"{batch_column} = '{batch_id}'"
        ).option("mergeSchema", "true").saveAsTable(target)
    else:
        frame.write.format("delta").mode("overwrite").option("mergeSchema", "true").saveAsTable(
            target
        )


def _append(spark, target, rows, schema):
    if rows:
        spark.createDataFrame([_coerce_row(row) for row in rows], schema=schema).write.format(
            "delta"
        ).mode("append").saveAsTable(target)


def _replace_diagnostic_batch(spark, target, rows, schema, batch_id, batch_column):
    """Replace one batch of diagnostics so retries cannot duplicate metrics."""
    _replace_batch(spark, rows, target, batch_id, schema, batch_column=batch_column)


def _ensure_tables(spark, config):
    for schema in (config.restricted_schema, config.deidentified_schema, config.quarantine_schema):
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {config.catalog_name}.{schema}")
    audit = _name(config, config.restricted_schema, "_silver_processing_audit")
    quality = _name(config, config.restricted_schema, "_silver_quality_metrics")
    recon = _name(config, config.restricted_schema, "_silver_reconciliation_metrics")
    quarantine = _name(config, config.quarantine_schema, "_silver_quarantine")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {audit} ({AUDIT_COLUMNS}) USING DELTA")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {quality} ({DQ_COLUMNS}) USING DELTA")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {recon} ({RECON_COLUMNS}) USING DELTA")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {quarantine} ({QUARANTINE_COLUMNS}) USING DELTA")


def _audit_row(config, system, schema, table, counts, status, processed_at, error=None):
    return {
        "batch_id": config.batch_id,
        "source_system": system,
        "source_schema": schema,
        "source_table": table,
        **counts,
        "status": status,
        "error_message": error,
        "processed_at": processed_at,
    }


def _reconciliation(config, system, table, rows, processed_at):
    if table not in {"claims", "claim_lines", "payments"}:
        return []
    rows = [row for row in rows if row.get("claim_id") is not None]
    counts = [0, 0, 0]
    totals = [Decimal("0"), Decimal("0"), Decimal("0")]
    index = {"claims": 0, "claim_lines": 1, "payments": 2}[table]
    counts[index] = len(rows)
    totals[index] = sum((Decimal(str(row.get("paid_amount") or 0)) for row in rows), Decimal("0"))
    return aggregate_reconciliation_metrics(
        batch_id=config.batch_id,
        source_system=system,
        source_table=table,
        claim_count=counts[0],
        line_count=counts[1],
        payment_count=counts[2],
        header_paid_total=totals[0],
        line_paid_total=totals[1],
        payment_paid_total=totals[2],
        processed_at=processed_at,
    )


def run_silver(spark, config, table_names=None, key_provider=None):
    """Process one batch, publishing only after the complete quality gate passes."""
    if not config.batch_id:
        raise ValueError("Silver requires an explicit batch_id")
    validate_safe_id(config.batch_id, "batch_id")
    key = (key_provider or config.key_provider(_dbutils(spark)))()
    selected = set(table_names or TABLE_KEYS)
    allowed = {
        "ALL": TABLE_KEYS,
        "clinical_provider": tuple(CLINICAL_TABLES),
        "member_claims": tuple(set(TABLE_KEYS) - CLINICAL_TABLES),
    }[config.source_filter]
    selected &= set(allowed)
    processed_at = datetime.now(timezone.utc)
    _ensure_tables(spark, config)
    staged, quality_rows, recon_rows, quarantine_rows, audits, all_issues = [], [], [], [], [], []
    parent_keys: dict[str, set] = {}
    # Include prior Silver state so a child batch is not rejected when its
    # parent arrived in an earlier batch (or is excluded by source_filter).
    referenced_parents = {
        parent for table in selected for parent in REFERENTIAL_RELATIONSHIPS.get(table, {}).values()
    }
    for parent in referenced_parents:
        psystem, pschema = _domain(parent)
        target = _name(config, config.restricted_schema, f"{psystem}_{pschema}_{parent}")
        if spark.catalog.tableExists(target):
            pkey = table_business_keys(parent)[0]
            parent_keys[parent] = {
                row.get(pkey) for row in _rows(spark.table(target)) if row.get(pkey) is not None
            }
    for table in TABLE_KEYS:
        if table not in selected:
            continue
        system, schema = _domain(table)
        source = _name(config, config.bronze_schema, f"{system}_{schema}_{table}")
        if not spark.catalog.tableExists(source):
            audits.append(
                _audit_row(
                    config,
                    system,
                    schema,
                    table,
                    {
                        "input_rows": 0,
                        "published_rows": 0,
                        "quarantined_rows": 0,
                        "duplicate_rows": 0,
                        "late_rows": 0,
                    },
                    "SKIPPED_MISSING_BRONZE",
                    processed_at,
                    "Bronze table does not exist",
                )
            )
            continue
        from pyspark.sql import functions as F

        raw = _rows(spark.table(source).filter(F.col("_ingest_batch_id") == F.lit(config.batch_id)))
        contract = get_contract(system, schema, table, "v1")
        conformed, row_errors = [], []
        for row in raw:
            value, errors = cast_row(row, contract.columns)
            if table in {"claims", "claim_lines", "claim_adjustments", "payments"}:
                value = normalize_claim_row(value)
            conformed.append(value)
            row_errors.append(errors)
        winners, duplicates = deterministic_dedupe(conformed, table_business_keys(table))
        winners = survivorship(winners, table_business_keys(table))
        # Match errors by deterministic source hash, not list position after dedupe.
        errors_by_hash = {
            str(row.get("_record_hash")): errors
            for row, errors in zip(conformed, row_errors, strict=False)
        }
        published, local_quarantine, local_issues = [], [], []
        for row in winners:
            event_field = EVENT_FIELDS.get(table)
            late = bool(row.get("_silver_is_late_arriving")) or classify_late_arrival(
                row,
                config.batch_id,
                event_field=event_field,
                watermark=config.watermark_value(),
            )
            relationships = REFERENTIAL_RELATIONSHIPS.get(table, {})
            row_parent_keys = {
                field: parent_keys[parent]
                for field, parent in relationships.items()
                if parent in parent_keys
            }
            late_parent_keys = {
                field: parent_keys.get(f"{parent}__late", set())
                for field, parent in relationships.items()
            }
            issues = evaluate_row(
                row,
                table,
                required_fields=contract.required_columns,
                parent_keys=row_parent_keys,
                known_late_keys=late_parent_keys,
                cast_errors=errors_by_hash.get(str(row.get("_record_hash")), ()),
            )
            local_issues.extend(issues)
            if any(issue.severity in {"ERROR", "CRITICAL"} for issue in issues):
                local_quarantine.append(
                    quarantine_record(
                        row,
                        issues,
                        processed_at,
                        source_system=system,
                        source_schema=schema,
                        source_table=table,
                    )
                )
            else:
                published.append(
                    add_silver_metadata(
                        row,
                        processed_at=processed_at,
                        transform_version=config.transform_version,
                        late_arriving=late,
                    )
                )
        staged.append((system, schema, table, published))
        key = table_business_keys(table)[0] if table_business_keys(table) else None
        if key:
            parent_keys[table] = {row.get(key) for row in published if row.get(key) is not None}
            parent_keys[f"{table}__late"] = {
                row.get(key)
                for row in published
                if row.get(key) is not None and row.get("_silver_is_late_arriving")
            }
        all_issues.extend(local_issues)
        quarantine_rows.extend(local_quarantine)
        late_count = sum(1 for row in published if row.get("_silver_is_late_arriving"))
        quality_rows.extend(
            aggregate_quality_metrics(
                batch_id=config.batch_id,
                source_system=system,
                source_table=table,
                input_rows=len(raw),
                published_rows=len(published),
                quarantined_rows=len(local_quarantine),
                duplicate_rows=len(duplicates),
                late_rows=late_count,
                issues=local_issues,
                processed_at=processed_at,
            )
        )
        recon_rows.extend(_reconciliation(config, system, table, published, processed_at))
        audits.append(
            _audit_row(
                config,
                system,
                schema,
                table,
                {
                    "input_rows": len(raw),
                    "published_rows": len(published),
                    "quarantined_rows": len(local_quarantine),
                    "duplicate_rows": len(duplicates),
                    "late_rows": late_count,
                },
                "COMPLETED",
                processed_at,
            )
        )
    audit_schema = spark.table(
        _name(config, config.restricted_schema, "_silver_processing_audit")
    ).schema
    dq_schema = spark.table(
        _name(config, config.restricted_schema, "_silver_quality_metrics")
    ).schema
    recon_schema = spark.table(
        _name(config, config.restricted_schema, "_silver_reconciliation_metrics")
    ).schema
    quarantine_schema = spark.table(
        _name(config, config.quarantine_schema, "_silver_quarantine")
    ).schema
    # Diagnostics and quarantine are durable even when the publication gate blocks.
    if quarantine_rows:
        for record in quarantine_rows:
            record["_raw_record"] = json.dumps(
                record["_raw_record"], default=str, separators=(",", ":")
            )
        _replace_diagnostic_batch(
            spark,
            _name(config, config.quarantine_schema, "_silver_quarantine"),
            quarantine_rows,
            quarantine_schema,
            config.batch_id,
            "_ingest_batch_id",
        )
    else:
        _replace_diagnostic_batch(
            spark,
            _name(config, config.quarantine_schema, "_silver_quarantine"),
            [],
            quarantine_schema,
            config.batch_id,
            "_ingest_batch_id",
        )
    _replace_diagnostic_batch(
        spark,
        _name(config, config.restricted_schema, "_silver_quality_metrics"),
        quality_rows,
        dq_schema,
        config.batch_id,
        "batch_id",
    )
    _replace_diagnostic_batch(
        spark,
        _name(config, config.restricted_schema, "_silver_reconciliation_metrics"),
        recon_rows,
        recon_schema,
        config.batch_id,
        "batch_id",
    )
    if any(issue.severity == "CRITICAL" for issue in all_issues):
        audits = [
            {**audit, "status": "BLOCKED", "error_message": "Critical data-quality issues"}
            for audit in audits
        ]
        _replace_diagnostic_batch(
            spark,
            _name(config, config.restricted_schema, "_silver_processing_audit"),
            audits,
            audit_schema,
            config.batch_id,
            "batch_id",
        )
        raise RuntimeError("Silver publication blocked by critical data-quality issues")

    for system, schema, table, rows in staged:
        target_suffix = f"{system}_{schema}_{table}"
        restricted = _name(config, config.restricted_schema, target_suffix)
        deidentified = _name(config, config.deidentified_schema, target_suffix)
        _replace_batch(
            spark, rows, restricted, config.batch_id, _table_schema(system, schema, table, rows)
        )
        _replace_batch(
            spark,
            [deidentified_projection(row, key, token_version=config.token_version) for row in rows],
            deidentified,
            config.batch_id,
            _table_schema(system, schema, table, rows, deidentified=True),
        )
    _replace_diagnostic_batch(
        spark,
        _name(config, config.restricted_schema, "_silver_processing_audit"),
        audits,
        audit_schema,
        config.batch_id,
        "batch_id",
    )
    return [row for _, _, _, rows in staged for row in rows]


def _dbutils(spark):
    injected = globals().get("dbutils")
    if injected is not None:
        return injected
    from pyspark.dbutils import DBUtils

    return DBUtils(spark)
