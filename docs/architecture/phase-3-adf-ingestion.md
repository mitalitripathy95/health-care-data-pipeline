# Phase 3 — Azure Data Factory Bronze ingestion

## Status and scope

Phase 3 is complete as repository code only. It has not been deployed or runtime-tested
in Azure. Deployment remains intentionally deferred until the final end-to-end phase.

This phase provides metadata-driven ingestion from the two Azure-hosted synthetic source
systems into immutable Parquet objects in ADLS Gen2:

| Source | ADF linked service | Source schema | Load behavior |
|---|---|---|---|
| PostgreSQL Flexible Server | `ls_postgresql_clinical` | `clinical` | Full and composite-watermark incremental |
| Azure SQL Database | `ls_azure_sql_payer` | `payer`, `control` | Full and composite-watermark incremental/control |
| ADLS Gen2 | `ls_adls_lake` | `bronze/raw` | Managed-identity Parquet sink |

The implementation consists of Terraform ADF resources in
`infra/modules/compute/adf.tf`, activity templates under `infra/modules/compute/adf/`,
the Azure SQL control schema in `database/azure_sql/ddl/002_control_schema.sql`, and the
19-table metadata seed in `database/azure_sql/seed/001_ingestion_config.sql`.

## Resource inventory

### Linked services and security

- `ls_key_vault` resolves source secrets at ADF runtime.
- `ls_postgresql_clinical` uses the Key Vault secret
  `adf-postgresql-connection-string` by default.
- `ls_azure_sql_payer` uses the Key Vault secret
  `adf-azure-sql-connection-string` by default.
- `ls_adls_lake` authenticates with the ADF system-assigned managed identity.

No source password or storage key is embedded in the ADF artifacts. Azure RBAC grants
the factory identity access to Key Vault and the lake through the infrastructure modules.
Only synthetic healthcare data is permitted.

### Parameterized datasets

- `ds_postgresql_table` selects a PostgreSQL schema and table.
- `ds_azure_sql_table` selects an Azure SQL schema and table and supports control queries.
- `ds_bronze_parquet` writes Snappy-compressed Parquet to a run-scoped path.

ADF connector types and dataset references are selected through static branches. Dynamic
expressions are not used for JSON `type` or `referenceName`, avoiding unsupported ADF
resource shapes.

### Pipelines and trigger

- `pl_master_ingestion` starts the pipeline audit, reads enabled metadata, runs table
  ingestion, closes the master run, and publishes Phase 4 readiness.
- `pl_ingest_table` locks and ingests one table, validates the landing, and transactionally
  publishes its manifest and watermark.
- `pl_validate_landing` checks source/landed row equality, file presence when rows exist,
  and the immutable path contract.
- `tr_daily_ingestion` is provisionable but disabled by default to control Azure trial
  cost. The first execution should be manual.

Master concurrency is one. Tiny-profile table execution is sequential; larger profiles
allow bounded parallelism. Activities use a two-hour timeout, three retries, and a
30-second retry interval.

## Metadata-driven orchestration

The `control.source_system` and `control.ingestion_config` tables define enabled sources,
connector engine, source object, key columns, extraction SQL, load type, expected schema,
and concurrency group. The seed contains 10 clinical PostgreSQL tables and 9 payer Azure
SQL tables. Only `clinical.medications` and `payer.plans` use full snapshots; the other
17 tables are incremental.

The master pipeline creates a `control.pipeline_run`, reads enabled metadata, and invokes
the child pipeline once per table. A successful master run publishes this exact dependency:

```text
batch_id=<requested batch>
upstream_job=adf_ingestion
downstream_job=databricks_bronze
status=READY
```

No Databricks job is invoked in Phase 3. `control.job_dependency` is the durable handoff
contract for Phase 4.

## Incremental and full extraction

### Composite watermark

Incremental tables use the ordered tuple `(watermark timestamp, primary key)`. The lower
bound is the last committed tuple. Before copying, the pipeline captures a high tuple and
then extracts a bounded interval:

```text
(row_ts > low_ts OR (row_ts = low_ts AND row_key > low_key))
AND
(row_ts < high_ts OR (row_ts = high_ts AND row_key <= high_key))
```

The bounded high watermark prevents rows arriving during a copy from creating an
unrepeatable interval. The primary-key tie-breaker prevents loss when multiple records
share the same timestamp. If no tuple exists above the lower bound, the pipeline records
an empty successful interval without running a copy.

### Full snapshots

Full tables copy their complete source state into a new run-scoped path. They do not use
or advance an incremental watermark. Because every run writes to a unique location, a
historical snapshot is never overwritten.

### Backfills

`backfill_start` and `backfill_end` parameters override the effective interval bounds.
The publication procedure receives `advance_watermark=false` for a bounded backfill, so
historical reprocessing cannot move the production incremental watermark. Backfills must
use a unique batch ID and remain auditable as `BACKFILL` invocations.

## Immutable Bronze contract

The sink path is:

```text
bronze/raw/source=<source>/schema=<schema>/table=<table>/batch_id=<batch>/run_id=<table-run>/
```

The table pipeline uses its own ADF RunId as `table_run_id`; the parent master RunId is
stored as `pipeline_run_id`. A retry cannot overwrite a previously published run because
its run path is immutable. A batch already marked successful is rejected by the control
procedure.

## Audit, locking, validation, and publication

The Azure SQL `control` schema includes source configuration, pipeline/table runs,
watermarks, locks, manifests, data-quality results, dependencies, reprocess requests,
reconciliation results, and health observations.

For each table the flow is:

1. Acquire an expiring row-level ingestion lock and create a `RUNNING` table run.
2. Read the committed low watermark.
3. Determine a bounded high watermark or select full-snapshot mode.
4. Copy to the immutable run path, or explicitly represent an empty interval.
5. Run `pl_validate_landing` before publication.
6. In one Azure SQL transaction, mark the table successful, insert its manifest, optionally
   advance the watermark, and release the lock.

Validation requires source and landed row counts to match. A non-empty extraction must
produce at least one file, and the path must contain the expected `batch_id` and `run_id`.
Any watermark-read, extraction, validation, or publication failure calls
`control.usp_fail_table_run`, records the error, and releases the lock. Failed runs never
advance a watermark and never publish downstream readiness.

## Idempotency and partial failure recovery

Control procedures reject duplicate successful or simultaneously running batch IDs.
Locks prevent concurrent ingestion of the same configured table. Publication is
transactional, so manifest and watermark state cannot diverge during a successful commit.

After a partial failure, retain the failed run for audit and rerun the master with a new
batch ID. Already written failed-run files remain isolated by `run_id` and are not treated
as published manifests. The new run starts from the last successfully committed
watermark.

## Checksum limitation

The Phase 3 manifest checksum is a deterministic SHA-256 over batch/path/count metadata;
it is not a byte-level checksum of every Parquet object. Row-count/path checks protect the
ADF landing contract. Content-level schema and quality checks are added by the Spark
Bronze and Silver phases.

## Trial cost controls

- The schedule trigger is disabled by default.
- Tiny-profile ingestion is sequential and intentionally low concurrency.
- No self-hosted integration runtime or always-on ADF compute is provisioned.
- Sources, ADF, and storage should run only for the final 1–2 day demonstration.
- Budget alerts must exist before testing, and all resources must be destroyed afterward.
