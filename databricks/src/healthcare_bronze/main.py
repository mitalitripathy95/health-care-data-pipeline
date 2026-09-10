"""Databricks task entrypoint."""

from __future__ import annotations

import argparse

from .bronze_ingest import run_bronze
from .config import BronzeConfig
from .manifest_reader import publish_bronze_dependencies, read_control_frames


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Promote manifest-approved raw files to Bronze Delta"
    )
    defaults = {
        "batch-id": "",
        "source-filter": "ALL",
        "manifest-path": "",
        "catalog-name": "healthcare_demo",
        "bronze-schema": "bronze",
        "quarantine-schema": "quarantine",
        "control-jdbc-url": "",
        "secret-scope": "healthcare",
        "control-user-key": "control-db-user",
        "control-password-key": "control-db-password",
    }
    for name, default in defaults.items():
        result.add_argument(f"--{name}", default=default)
    return result


def _runtime_dbutils(spark):
    """Return Databricks utilities for a wheel task without importing PySpark locally."""
    injected = globals().get("dbutils")
    if injected is not None:
        return injected

    # Python wheel tasks do not consistently inject dbutils into module globals.
    # This import is intentionally deferred so pure unit tests do not need PySpark.
    from pyspark.dbutils import DBUtils

    return DBUtils(spark)


def should_publish_dependencies(results, config: BronzeConfig) -> bool:
    """Publish only after every selected table succeeded or was already complete."""
    successful_statuses = frozenset({"SUCCEEDED", "SKIPPED_ALREADY_SUCCEEDED"})
    return bool(
        results
        and config.batch_id
        and config.control_jdbc_url
        and config.source_filter == "ALL"
        and all(result.get("status") in successful_statuses for result in results)
    )


def main(argv=None):
    args = parser().parse_args(argv)
    config = BronzeConfig(**vars(args))

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    runtime_dbutils = _runtime_dbutils(spark)
    manifests, dependencies = read_control_frames(spark, config, runtime_dbutils)
    results = run_bronze(spark, config, manifests, dependencies)
    if should_publish_dependencies(results, config):
        publish_bronze_dependencies(spark, config, runtime_dbutils)
    return results


if __name__ == "__main__":
    main()
