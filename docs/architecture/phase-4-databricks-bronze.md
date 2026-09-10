# Phase 4 — Databricks Bronze Delta architecture

## Status and scope

Phase 4 is implemented as repository code and credential-free static validation only. It
has not been deployed to Azure Databricks and no Spark or Delta runtime acceptance test
has been executed. Deployment remains deferred until the final end-to-end phase.

This phase promotes only Phase 3 manifest-approved, immutable ADLS raw files into typed,
source-aligned Delta tables. It does not clean business data, apply survivorship, or
perform de-identification; those are Phase 5 Silver responsibilities. All project data is
synthetic. Real PHI must never be used.

## Data flow and control gate

```text
ADF immutable raw Parquet
  -> control.batch_manifest status=PUBLISHED
  -> control.job_dependency adf_ingestion -> databricks_bronze status=READY
  -> wf_bronze_ingestion
  -> schema/drift validation
  -> Bronze Delta or quarantine
  -> Bronze audit and idempotency registry
  -> dependency transitions in one Azure SQL transaction
       adf_ingestion -> databricks_bronze = COMPLETED
       databricks_bronze -> databricks_silver = READY
```

A manifest is eligible only when it is published, has a publication timestamp, reconciles
`source_row_count = landed_row_count`, has the matching READY dependency, and its path
identity exactly matches source, schema, table, batch, and table-run identity. The path
contract is:

```text
bronze/raw/source=<source>/schema=<schema>/table=<table>/batch_id=<batch>/run_id=<run>/
```

No directory listing is used to discover work. An unpublished or partially written raw
path is never promoted.

## Raw Bronze and Delta Bronze

Phase 3 raw Bronze is immutable source truth as extracted by ADF. Phase 4 Bronze Delta is
a typed, queryable, source-aligned representation with operational metadata. Target names
are deterministic:

```text
<catalog>.<bronze_schema>.<source_system>_<source_schema>_<source_table>
```

The code creates the configured Bronze and quarantine schemas and Delta tables, but the
catalog, Unity Catalog metastore attachment, external locations/storage credentials, and
workspace bindings are account-level prerequisites. They are intentionally not automated
inside the Asset Bundle. Terraform provisions the Azure Databricks workspace and access
connector; it does not duplicate account-level Unity Catalog administration.

Each accepted record keeps all source columns and receives:

- `_ingest_batch_id`
- `_ingest_run_id`
- `_ingest_ts`
- `_source_system`
- `_source_schema`
- `_source_table`
- `_source_file`
- `_record_hash`
- `_schema_version`

`_record_hash` is a SHA-256 over a canonical JSON structure of source columns and is for
repeatable record comparison, not reversible tokenization.

## Schema registry and drift policy

`healthcare_bronze.schema_registry` contains explicit version `v1` contracts for all 19
Phase 1 source tables. The job inspects the physical source schema, compares it to the
registered contract, then reads with an authoritative Spark schema rather than relying on
inference for production values.

Allowed changes:

- an exact registered schema;
- new nullable columns;
- explicitly supported safe type widening.

Rejected changes:

- a missing required column;
- a new non-nullable column;
- narrowing or incompatible type changes;
- an unknown source table or schema version.

Nullable additive columns are retained and Delta schema merge is enabled only for that
approved case. Breaking drift fails the table safely and is recorded in the audit table.

## Corrupt-record quarantine

Parquet is the active Phase 3 landing format. JSON and CSV readers are also supported for
controlled future inputs. They use Spark permissive parsing with `_corrupt_record`.
Unreadable rows are excluded from the Bronze target and appended to the corresponding
quarantine table with `_quarantine_reason=CORRUPT_RECORD` and batch identity. A corrupt
row does not silently become a trusted Bronze record. Input, output, and quarantined row
counts are reconciled in the audit record.

## Audit, idempotency, retries, and backfills

Two Delta control tables live in the Bronze schema:

- `_bronze_batch_registry` tracks `RUNNING`, `SUCCEEDED`, and `FAILED` table-batch keys;
- `_bronze_processing_audit` records counts, files, schema version, drift decision,
  status, error text, and processing time.

The idempotency key is:

```text
sha256(batch_id|source_system|source_schema|source_table)
```

An exact successful rerun is reported as `SKIPPED_ALREADY_SUCCEEDED`. A failed attempt can
be retried deterministically: its batch partition is replaced using `replaceWhere`, so a
partial retry does not append duplicate Bronze rows. A backfill uses a new batch ID and
therefore remains independently auditable. Raw input is cached only for the current table
and unpersisted in `finally`.

An empty eligible-manifest set returns no results. A zero-row manifest is supported only
when Phase 1/ADF lands a readable, schema-bearing empty Parquet dataset; this behavior is
pending Azure Databricks runtime acceptance testing. Dependencies are published only for
an explicit batch ID, after non-empty successful processing, and when the Azure SQL JDBC
control path is configured. Both downstream dependency changes execute in one transaction
and roll back together on failure.

## Secrets and access

Azure SQL JDBC credentials are read from a Databricks secret scope backed by Azure Key
Vault. Defaults refer to `control-db-user` and `control-db-password`; secret values are not
stored in bundle YAML, source code, Terraform variables, logs, or notebooks. The job
identity requires only the catalog/schema/table privileges, ADLS external-location access,
secret-scope read access, and control procedure/database access needed for this workflow.

## Asset Bundle and cost controls

The bundle `healthcare-data-pipeline` builds the `healthcare-bronze` wheel and defines
`wf_bronze_ingestion`. Its demonstration target uses an ephemeral single-node job cluster,
a pinned LTS runtime variable, standard (non-Photon) runtime engine, 15-minute
auto-termination, bounded retries, a two-hour timeout, no schedule, and
`max_concurrent_runs: 1`. Regional node availability and the selected LTS identifier must
be confirmed immediately before the final deployment.
