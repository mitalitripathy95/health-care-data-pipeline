# Phase 1 — Source systems and synthetic data

## Objective

Phase 1 establishes realistic, deterministic source-system contracts before any Azure
resources are deployed. All records are synthetic and safe for local development.

## Source ownership

| Source | Engine/schema | Responsibility |
|---|---|---|
| Clinical/provider | PostgreSQL `clinical` | Patient identity, providers, facilities, encounters, diagnoses, procedures, observations, medications, prescriptions |
| Member/claims | Azure SQL `payer` | Members, plans, enrollment, claims, claim lines/diagnoses, authorizations, payments, claim adjustments |
| Pipeline control | Azure SQL `control` | Source configuration, pipeline/table runs, watermarks, manifests, DQ, dependencies, reprocessing, reconciliation, health |

DDL is under `database/`. The source contract and sensitivity metadata are under
`docs/contracts/`. Source tables use primary/foreign keys, uniqueness and date-ordering
checks, soft-delete flags, and source schema version columns where appropriate.

## Local interchange format

The generator writes one sorted-key JSONL file per table:

```text
data/generated/<batch_id>/
  clinical_provider/<table>.jsonl
  member_claims/<table>.jsonl
  manifest.json
```

The manifest records profile, seed, row counts, columns, relative paths, and SHA-256
checksums. This makes generated batches auditable and allows validation before loading
to a database or ADLS landing area.

## Determinism and restartability

IDs are derived from SHA-256 of the seed/table identity and are not based on Python's
process-randomized `hash()` function. Re-running the same profile and seed produces the
same table bytes. A batch ID is an explicit output boundary; an existing batch must be
removed or given a new ID before regeneration.

## Incremental extraction contract

The committed source watermark is a tuple, compared lexicographically:

- PostgreSQL: `(updated_at, primary_key)`
- Azure SQL: `(modified_at, primary_key)`

Rows are selected only when their tuple is strictly greater than the committed low
watermark. A higher primary key at the same timestamp is therefore included. Timestamp
values must be timezone-aware in the helper contract.

## Quality scenarios

`src/synthetic_data/scenarios/mutate.py` provides reproducible fixtures for broken foreign
keys, invalid financial amounts, duplicate events, and two changed-record timestamps.
The financial invariant is:

```text
0 <= paid_amount <= allowed_amount <= billed_amount
```

The incremental fixtures deliberately assign the same timestamp to two changed claims,
demonstrating why timestamp-only extraction is unsafe. They are changed-record fixtures,
not a complete new-record/change-data-capture simulation; that will be expanded with the
ingestion implementation in a later phase.

## Next phase boundary

Phase 1 does not connect to databases or Azure. Later phases will load the same contracts
into PostgreSQL/Azure SQL, ingest to ADLS Bronze, transform Bronze-to-Silver and
Silver-to-Gold with Spark, and publish modeled data to Snowflake.
