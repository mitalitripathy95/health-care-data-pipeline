"""Spark adapter for enriched manifests and Phase 3 control metadata."""

from __future__ import annotations

MANIFEST_QUERY = """(
SELECT bm.batch_id, CONVERT(varchar(36), bm.table_run_id) AS table_run_id,
       ss.source_name AS source_system, ic.source_schema, ic.source_table,
       bm.bronze_path, bm.source_row_count, bm.landed_row_count,
       ic.expected_schema_version AS schema_version, bm.status,
       CONVERT(varchar(33), bm.published_at, 127) AS published_at,
       ic.target_format
FROM control.batch_manifest bm
JOIN control.table_run tr ON tr.table_run_id = bm.table_run_id
JOIN control.ingestion_config ic ON ic.ingestion_config_id = tr.ingestion_config_id
JOIN control.source_system ss ON ss.source_system_id = ic.source_system_id
) bronze_manifests"""
DEPENDENCY_QUERY = """(
SELECT batch_id, upstream_job, downstream_job, status
FROM control.job_dependency
WHERE upstream_job='adf_ingestion' AND downstream_job='databricks_bronze'
) bronze_dependencies"""


def _jdbc_properties(config, dbutils):
    if dbutils is None:
        raise ValueError("dbutils is required for Key Vault-backed JDBC credentials")
    return {
        "user": dbutils.secrets.get(config.secret_scope, config.control_user_key),
        "password": dbutils.secrets.get(config.secret_scope, config.control_password_key),
        "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
    }


def read_control_frames(spark, config, dbutils=None):
    if config.manifest_path:
        base = spark.read.format("delta").load(config.manifest_path)
        return base.filter("record_type = 'MANIFEST'"), base.filter("record_type = 'DEPENDENCY'")
    props = _jdbc_properties(config, dbutils)
    return (
        spark.read.jdbc(config.control_jdbc_url, MANIFEST_QUERY, properties=props),
        spark.read.jdbc(config.control_jdbc_url, DEPENDENCY_QUERY, properties=props),
    )


def publish_bronze_dependencies(spark, config, dbutils=None) -> None:
    """Atomically advance the Phase 3/4 dependency gates through Azure SQL."""
    props = _jdbc_properties(config, dbutils)
    java_import = spark.sparkContext._gateway.jvm.java.sql.DriverManager
    connection = java_import.getConnection(
        config.control_jdbc_url, props["user"], props["password"]
    )
    connection.setAutoCommit(False)
    statement = None
    try:
        statement = connection.prepareCall("{call control.usp_publish_job_dependency(?,?,?,?)}")
        transitions = (
            ("adf_ingestion", "databricks_bronze", "COMPLETED"),
            ("databricks_bronze", "databricks_silver", "READY"),
        )
        for upstream, downstream, status in transitions:
            statement.setString(1, config.batch_id)
            statement.setString(2, upstream)
            statement.setString(3, downstream)
            statement.setString(4, status)
            statement.execute()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if statement is not None:
            statement.close()
        connection.close()
