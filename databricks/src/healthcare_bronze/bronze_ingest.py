"""Spark/Delta runtime adapter; PySpark is imported only inside runtime functions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .contracts import (
    Dependency,
    Manifest,
    classify_schema_drift,
    eligible_manifests,
    idempotency_key,
    validate_safe_id,
)
from .schema_registry import get_contract

AUDIT_COLUMNS = (
    "batch_id string, idempotency_key string, source_system string, source_schema string, "
    "source_table string, table_run_id string, input_rows long, output_rows long, "
    "quarantined_rows long, file_count long, schema_version string, drift_kind string, "
    "status string, error_message string, processed_at timestamp"
)
REGISTRY_COLUMNS = (
    "idempotency_key string, batch_id string, source_system string, source_schema string, "
    "source_table string, table_run_id string, status string, processed_at timestamp"
)
QUARANTINE_COLUMNS = (
    "_corrupt_record string, _ingest_batch_id string, _ingest_run_id string, "
    "_source_system string, _source_schema string, _source_table string, "
    "_source_file string, _quarantine_reason string"
)
SUPPORTED_FORMATS = frozenset({"PARQUET", "JSON", "CSV"})


def _rows(frame):
    return [row.asDict(recursive=True) for row in frame.collect()]


def _manifest(row):
    return Manifest(**{key: row.get(key) for key in Manifest.__dataclass_fields__})


def _dependency(row):
    return Dependency(**{key: row.get(key) for key in Dependency.__dataclass_fields__})


def normalize_target_format(value: str) -> str:
    normalized = str(value).upper()
    if normalized not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported target_format {value!r}; expected one of {sorted(SUPPORTED_FORMATS)}"
        )
    return normalized


def batch_replace_predicate(batch_id: str) -> str:
    return f"_ingest_batch_id = '{validate_safe_id(batch_id, 'batch_id')}'"


def _spark_type(type_name):
    from pyspark.sql.types import (
        BooleanType,
        DateType,
        DecimalType,
        DoubleType,
        FloatType,
        IntegerType,
        LongType,
        ShortType,
        StringType,
        TimestampType,
    )

    primitive = {
        "boolean": BooleanType,
        "date": DateType,
        "double": DoubleType,
        "float": FloatType,
        "integer": IntegerType,
        "long": LongType,
        "short": ShortType,
        "string": StringType,
        "timestamp": TimestampType,
    }
    if type_name.startswith("decimal("):
        precision, scale = type_name.removeprefix("decimal(").removesuffix(")").split(",")
        return DecimalType(int(precision), int(scale))
    try:
        return primitive[type_name]()
    except KeyError as exc:
        raise ValueError(f"Unsupported registered Spark type: {type_name}") from exc


def _authoritative_schema(contract, actual_fields, widened_columns=(), include_corrupt=False):
    from pyspark.sql.types import StringType, StructField, StructType

    widened_columns = frozenset(widened_columns)
    fields = [
        StructField(
            name,
            actual_fields[name][0] if name in widened_columns else _spark_type(type_name),
            name not in contract.required_columns,
        )
        for name, type_name in contract.columns.items()
    ]
    for name in sorted(actual_fields.keys() - contract.columns.keys()):
        data_type, nullable = actual_fields[name]
        fields.append(StructField(name, data_type, nullable))
    if include_corrupt:
        fields.append(StructField("_corrupt_record", StringType(), True))
    return StructType(fields)


def _merge_registry(spark, registry, row):
    schema = spark.table(registry).schema
    view = f"bronze_registry_{uuid4().hex}"
    spark.createDataFrame([row], schema=schema).createOrReplaceTempView(view)
    try:
        spark.sql(
            f"""MERGE INTO {registry} target USING {view} source
            ON target.idempotency_key = source.idempotency_key
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *"""
        )
    finally:
        spark.catalog.dropTempView(view)


def _registry_row(item, key, status, timestamp):
    return {
        "idempotency_key": key,
        "batch_id": item.batch_id,
        "source_system": item.source_system,
        "source_schema": item.source_schema,
        "source_table": item.source_table,
        "table_run_id": item.table_run_id,
        "status": status,
        "processed_at": timestamp,
    }


def _audit_result(item, key, timestamp, **changes):
    result = {
        "batch_id": item.batch_id,
        "idempotency_key": key,
        "source_system": item.source_system,
        "source_schema": item.source_schema,
        "source_table": item.source_table,
        "table_run_id": item.table_run_id,
        "input_rows": 0,
        "output_rows": 0,
        "quarantined_rows": 0,
        "file_count": 0,
        "schema_version": item.schema_version,
        "drift_kind": "INCOMPATIBLE",
        "status": "FAILED",
        "error_message": None,
        "processed_at": timestamp,
    }
    result.update(changes)
    return result


def _append_audit(spark, audit_table, result):
    schema = spark.table(audit_table).schema
    spark.createDataFrame([result], schema=schema).write.mode("append").saveAsTable(audit_table)


def run_bronze(spark, config, manifest_frame, dependency_frame):
    """Promote eligible manifests and return one auditable result per selected table."""
    from pyspark.sql import functions as F

    manifests = [_manifest(row) for row in _rows(manifest_frame)]
    dependencies = [_dependency(row) for row in _rows(dependency_frame)]
    selected = eligible_manifests(manifests, dependencies, config.batch_id)
    if config.source_filter != "ALL":
        selected = [item for item in selected if item.source_system == config.source_filter]

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {config.catalog_name}.{config.bronze_schema}")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {config.catalog_name}.{config.quarantine_schema}")
    registry = f"{config.catalog_name}.{config.bronze_schema}._bronze_batch_registry"
    audit = f"{config.catalog_name}.{config.bronze_schema}._bronze_processing_audit"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {registry} ({REGISTRY_COLUMNS}) USING DELTA")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {audit} ({AUDIT_COLUMNS}) USING DELTA")
    completed = {
        row.idempotency_key
        for row in spark.table(registry)
        .filter("status = 'SUCCEEDED'")
        .select("idempotency_key")
        .collect()
    }

    results = []
    for item in selected:
        key = idempotency_key(item)
        if key in completed:
            result = _audit_result(
                item,
                key,
                datetime.now(timezone.utc),
                drift_kind="NOT_EVALUATED",
                status="SKIPPED_ALREADY_SUCCEEDED",
            )
            _append_audit(spark, audit, result)
            results.append(result)
            continue

        timestamp = datetime.now(timezone.utc)
        _merge_registry(spark, registry, _registry_row(item, key, "RUNNING", timestamp))
        raw = None
        try:
            contract = get_contract(
                item.source_system, item.source_schema, item.source_table, item.schema_version
            )
            target_format = normalize_target_format(item.target_format)
            inference_reader = spark.read.format(target_format.lower())
            if target_format == "CSV":
                inference_reader = inference_reader.option("header", "true").option(
                    "inferSchema", "true"
                )
            inferred = inference_reader.load(item.bronze_path)
            actual_fields = {
                field.name: (field.dataType, field.nullable) for field in inferred.schema.fields
            }
            drift_input = {
                name: (data_type.simpleString(), nullable)
                for name, (data_type, nullable) in actual_fields.items()
            }
            drift = classify_schema_drift(contract, drift_input)
            if not drift.allowed:
                raise ValueError("; ".join(drift.errors))

            has_corrupt = target_format in {"JSON", "CSV"}
            schema = _authoritative_schema(
                contract,
                actual_fields,
                widened_columns=drift.widened_columns,
                include_corrupt=has_corrupt,
            )
            reader = spark.read.format(target_format.lower()).schema(schema)
            if target_format == "CSV":
                reader = reader.option("header", "true")
            if has_corrupt:
                reader = reader.option("mode", "PERMISSIVE").option(
                    "columnNameOfCorruptRecord", "_corrupt_record"
                )
            raw = reader.load(item.bronze_path).cache()
            file_count = len(raw.inputFiles())
            input_rows = raw.count()
            quarantine_rows = (
                raw.filter(F.col("_corrupt_record").isNotNull()).count() if has_corrupt else 0
            )
            good = (
                raw.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")
                if has_corrupt
                else raw
            )
            source_cols = sorted(good.columns)
            canonical = F.to_json(
                F.struct(*[F.col(f"`{column}`") for column in source_cols]),
                options={"ignoreNullFields": "false"},
            )
            enriched = (
                good.withColumn("_ingest_batch_id", F.lit(item.batch_id))
                .withColumn("_ingest_run_id", F.lit(item.table_run_id))
                .withColumn("_ingest_ts", F.lit(timestamp))
                .withColumn("_source_system", F.lit(item.source_system))
                .withColumn("_source_schema", F.lit(item.source_schema))
                .withColumn("_source_table", F.lit(item.source_table))
                .withColumn("_source_file", F.input_file_name())
                .withColumn("_record_hash", F.sha2(canonical, 256))
                .withColumn("_schema_version", F.lit(item.schema_version))
            )
            target = (
                f"{config.catalog_name}.{config.bronze_schema}."
                f"{item.source_system}_{item.source_schema}_{item.source_table}"
            )
            (
                enriched.write.format("delta")
                .mode("overwrite")
                .option("replaceWhere", batch_replace_predicate(item.batch_id))
                .option("mergeSchema", "true" if drift.added_columns else "false")
                .saveAsTable(target)
            )
            if has_corrupt:
                qtarget = (
                    f"{config.catalog_name}.{config.quarantine_schema}."
                    f"{item.source_system}_{item.source_schema}_{item.source_table}"
                )
                spark.sql(
                    f"CREATE TABLE IF NOT EXISTS {qtarget} ({QUARANTINE_COLUMNS}) USING DELTA"
                )
                quarantine = (
                    raw.filter(F.col("_corrupt_record").isNotNull())
                    .select("_corrupt_record")
                    .withColumn("_ingest_batch_id", F.lit(item.batch_id))
                    .withColumn("_ingest_run_id", F.lit(item.table_run_id))
                    .withColumn("_source_system", F.lit(item.source_system))
                    .withColumn("_source_schema", F.lit(item.source_schema))
                    .withColumn("_source_table", F.lit(item.source_table))
                    .withColumn("_source_file", F.input_file_name())
                    .withColumn("_quarantine_reason", F.lit("CORRUPT_RECORD"))
                )
                (
                    quarantine.write.format("delta")
                    .mode("overwrite")
                    .option("replaceWhere", batch_replace_predicate(item.batch_id))
                    .saveAsTable(qtarget)
                )
            result = _audit_result(
                item,
                key,
                timestamp,
                input_rows=input_rows,
                output_rows=input_rows - quarantine_rows,
                quarantined_rows=quarantine_rows,
                file_count=file_count,
                drift_kind=drift.kind.value,
                status="SUCCEEDED",
            )
            _merge_registry(spark, registry, _registry_row(item, key, "SUCCEEDED", timestamp))
        except Exception as exc:
            result = _audit_result(item, key, timestamp, error_message=str(exc)[:2000])
            _merge_registry(spark, registry, _registry_row(item, key, "FAILED", timestamp))
        finally:
            if raw is not None:
                raw.unpersist()

        _append_audit(spark, audit, result)
        results.append(result)
        if result["status"] == "FAILED":
            raise RuntimeError(
                f"Bronze promotion failed for {item.source_table}: {result['error_message']}"
            )
    return results
