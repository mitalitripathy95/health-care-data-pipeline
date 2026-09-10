# Healthcare Data Platform — Cloud-First Senior Data Engineering Plan

**Status:** Phases 0–4 complete as code/static validation only; not deployed
**Cloud:** Microsoft Azure trial subscription plus a Snowflake trial account hosted on Azure
**Review date:** 2026-09-05
**Data:** Synthetic data only

---

## 1. Project objective

Build a portfolio-grade healthcare data migration and analytics platform inspired only by publicly understood payer/provider domains. The project will create synthetic clinical, member, provider, enrollment, authorization, claim, and payment data; ingest it from two cloud source databases; process it through a Spark-based medallion architecture; and serve dimensional models and KPI marts in Snowflake.

The implementation will demonstrate:

- cloud-hosted PostgreSQL and SQL Server-compatible source systems;
- deterministic Python generators for every source table;
- metadata-driven Azure Data Factory ingestion;
- immutable, replayable raw data in ADLS Gen2;
- PySpark processing from Bronze to Silver;
- explicit cleansing, conformance, deduplication, survivorship, and claim lifecycle rules;
- restricted and de-identified Silver datasets;
- Spark-built Gold dimensions, facts, bridges, and KPI marts;
- controlled batch loading from Gold exports into Snowflake;
- SCD Type 2 history, late-arriving data, masking, tokenization, governance, audit, and lineage;
- CI/CD, automated testing, monitoring, backfill, disaster/failure scenarios, and Terraform teardown.

This is a fictional portfolio project. It must never use or imply access to Elevance Health proprietary data, code, schemas, credentials, or business rules. It demonstrates **HIPAA-aligned technical controls using synthetic data**; it must not be described as HIPAA compliant.

---

## 2. Confirmed architecture decisions

### 2.1 Cloud-first execution

The full demonstration will run in cloud services. Local tools are used only as the operator workstation for Git, Terraform, Azure CLI, SnowSQL/Snowflake CLI, and deployment commands. Data processing and source databases run in the cloud.

| Capability | Selected service |
|---|---|
| Clinical/provider source | Azure Database for PostgreSQL Flexible Server |
| Member/claims source | Azure SQL Database using the SQL Server engine |
| One-time synthetic-data execution | Azure Container Apps Job using a Python container |
| Container registry | Azure Container Registry Basic |
| Ingestion/orchestration | Azure Data Factory |
| Data lake | ADLS Gen2 |
| Spark/lakehouse | Azure Databricks with Delta Lake and Unity Catalog |
| Secrets | Azure Key Vault |
| Operational metadata | Azure SQL `control` schema |
| Gold serving warehouse | Snowflake account deployed on Azure |
| Monitoring | Azure Monitor, Log Analytics, ADF/Databricks diagnostics, Snowflake audit tables |
| Infrastructure | Terraform |
| CI/CD | GitHub Actions with Azure OIDC and protected environments |

Azure SQL Database is selected instead of a SQL Server VM because it provides SQL Server compatibility at much lower demo cost and operational overhead. Exact SQL Server-specific behavior can be documented but is not necessary for this portfolio flow.

### 2.2 Spark owns Silver and logical Gold construction

Spark will not stop at Silver. Databricks will build:

1. **Bronze raw/source-aligned data** from successful ADF extracts;
2. **Silver conformed data** with quality and privacy rules;
3. **Gold Delta models** containing dimensions, facts, bridges, and precomputed KPI marts;
4. **Gold export snapshots** as batch-scoped Parquet files that Snowflake can load safely.

Snowflake remains the authoritative serving warehouse for BI/analytics. Spark owns scalable construction; Snowflake owns governed serving, concurrency, secure views, and final publication.

### 2.3 Why Gold Delta also needs an export area

Snowflake `COPY INTO` reads normal data files, not Delta transaction logs as dimensional-table merge instructions. Therefore Spark writes Gold tables to Delta for correctness and replay, then publishes only the successful batch to an immutable Parquet export path with a manifest.

```text
Gold Delta table -> validated batch export Parquet -> Snowflake stage -> staging -> MERGE -> published Gold
```

This avoids writing directly from Spark into production Snowflake tables and gives us deterministic replay, file-level reconciliation, and transactional warehouse publication.

---

## 3. End-to-end architecture

```text
                                AZURE
┌──────────────────────────────────────────────────────────────────────────┐
│ Azure Container Apps Job                                                │
│ Python synthetic generators + seeded scenarios                          │
└──────────────┬───────────────────────────────────────┬───────────────────┘
               │                                       │
               ▼                                       ▼
┌────────────────────────────┐          ┌──────────────────────────────┐
│ Azure PostgreSQL           │          │ Azure SQL Database           │
│ clinical + provider        │          │ member + claims              │
└──────────────┬─────────────┘          └──────────────┬───────────────┘
               └──────────────────────┬─────────────────┘
                                      ▼
                           Azure Data Factory
                  metadata, watermark, audit, dependencies
                                      ▼
                          ADLS Gen2 Bronze Raw
             immutable Parquet + manifest + control/audit metadata
                                      ▼
                 Azure Databricks / Spark / Unity Catalog
             Bronze Delta -> Silver restricted/de-identified Delta
                                      ▼
                   Spark Gold Delta dimensional models
           dimensions + facts + bridges + KPI aggregate tables
                                      ▼
                  ADLS Gold Export (immutable Parquet)
                       batch manifest + reconciliation
                                      │
                         Snowflake Azure storage integration
                                      ▼
              Snowflake transient staging -> transactional MERGE
                                      ▼
             Snowflake curated schema + KPI schema + secure views
                                      ▼
                          Power BI / SQL consumers

Cross-cutting: Key Vault, managed identity/service principals, RBAC,
Unity Catalog, masking/tokenization, Terraform, CI/CD, Log Analytics,
budgets, resource monitors, runbooks, replay/backfill, and teardown.
```

### Layer ownership

| Layer | Technology | Purpose | Mutation policy |
|---|---|---|---|
| Bronze raw | ADLS Parquet | Immutable source truth exactly as extracted | Append only |
| Bronze Delta | Databricks Delta | Typed source-aligned history plus ingestion metadata | Idempotent append |
| Silver restricted | Databricks Delta | Cleansed/conformed data retaining synthetic identifiers | MERGE with history/audit |
| Silver de-identified | Databricks Delta | Tokenized and generalized analytical contract | MERGE |
| Gold Delta | Databricks Delta | Spark-built facts, dimensions, bridges, KPIs | SCD/upsert rules |
| Gold export | ADLS Parquet | Immutable load contract for one Gold batch | Append by batch |
| Snowflake staging | Snowflake transient | Batch validation checkpoint | Truncate/reload by batch |
| Snowflake curated | Snowflake permanent | Authoritative BI-serving facts/dimensions/KPIs | Transactional MERGE |

---

## 4. Trial-credit and cost strategy

The expected Azure trial credit is often around USD 200, but the amount, eligible services, regions, quotas, and expiration must be checked in the actual subscription before provisioning. Snowflake trial credits are separate from Azure credits.

### Cost rules that are mandatory before deployment

1. Create an Azure budget and alerts at 25%, 50%, 75%, and 90% before Databricks is created.
2. Apply tags: `project`, `owner`, `environment`, `created_at`, `expires_at`, and `managed_by=terraform`.
3. Use one region for all Azure resources and the matching Azure region for Snowflake where available.
4. Use the smallest viable PostgreSQL and Azure SQL SKUs and the smallest storage allocations accepted by the services.
5. Use Databricks **job clusters only**, with autoscaling disabled or tightly bounded for the Tiny/Small demo and auto-termination after each job.
6. Do not create an always-on Databricks interactive cluster.
7. Use an X-Small Snowflake warehouse with 60-second auto-suspend, auto-resume, statement timeout, and a resource monitor.
8. Run Tiny first. Run Small only after the complete Tiny pipeline passes.
9. Do not run Medium under trial credits unless a fresh cost estimate proves sufficient.
10. Destroy billable resources within 1–2 days, then verify deletion in both Azure and Snowflake.

### Recommended demonstration sequence

- **Day 0:** validate quotas, plans, and Terraform; no compute run.
- **Day 1:** deploy, generate Tiny, run full load, validate and fix only configuration issues.
- **Day 2:** run Small, two incremental scenarios, one failure/recovery, one backfill, capture evidence, then destroy.

Terraform destroy does not automatically close or delete every Snowflake account-level object or protect against soft-deleted Azure resources. The teardown checklist includes manual portal/account verification.

---

## 5. Synthetic source systems and Python generation

### 5.1 PostgreSQL clinical/provider source

| Table | Grain | Incremental key | Key relationships | Classification |
|---|---|---|---|---|
| `patients` | One patient | `(updated_at, patient_id)` | enterprise person mapping | Direct identifier/PHI |
| `providers` | One provider | `(updated_at, provider_id)` | facilities, encounters | Synthetic identifier |
| `facilities` | One facility | `(updated_at, facility_id)` | providers, encounters | Low sensitivity |
| `provider_facility_affiliation` | Provider-facility period | `(updated_at, affiliation_id)` | provider, facility | Low sensitivity |
| `encounters` | One care encounter | `(updated_at, encounter_id)` | patient, provider, facility | PHI |
| `diagnoses` | One encounter diagnosis | `(updated_at, diagnosis_id)` | encounter | PHI |
| `procedures` | One encounter procedure | `(updated_at, procedure_id)` | encounter | PHI |
| `observations` | One result/vital | `(updated_at, observation_id)` | encounter, patient | PHI |
| `medications` | One medication reference | Full snapshot | prescriptions | Low sensitivity |
| `prescriptions` | One medication order | `(updated_at, prescription_id)` | patient, encounter, medication | PHI |

### 5.2 Azure SQL member/claims source

| Table | Grain | Incremental key | Key relationships | Classification |
|---|---|---|---|---|
| `members` | One member | `(modified_at, member_id)` | enterprise person mapping | Direct identifier/PHI |
| `plans` | One insurance product | Full snapshot | enrollments | Low sensitivity |
| `member_enrollment` | One coverage segment | `(modified_at, enrollment_id)` | member, plan | PHI |
| `claims` | One claim header/version | `(modified_at, claim_id)` | member, provider, facility | PHI/financial |
| `claim_lines` | One service line/version | `(modified_at, claim_line_id)` | claim | PHI/financial |
| `claim_diagnoses` | One claim-diagnosis relation | `(modified_at, claim_diagnosis_id)` | claim | PHI |
| `authorizations` | One authorization request/version | `(modified_at, authorization_id)` | member/provider | PHI |
| `payments` | One remittance/payment event | `(modified_at, payment_id)` | claim | PHI/financial |
| `claim_adjustments` | One adjustment/reversal event | `(modified_at, adjustment_id)` | claim | PHI/financial |

### 5.3 Generation package

Every table will have generation logic, but shared domain factories prevent copy-pasted scripts. The package will contain:

```text
synthetic_data/
├── config/{tiny,small,medium}.yaml
├── reference/                         # approved public/synthetic code lists
├── generators/
│   ├── identity.py
│   ├── clinical.py
│   ├── provider.py
│   ├── enrollment.py
│   ├── claims.py
│   ├── authorization.py
│   └── payment.py
├── scenarios/
│   ├── initial_load.py
│   ├── incremental_01.py
│   ├── incremental_02.py
│   ├── quality_failures.py
│   └── schema_evolution.py
├── loaders/{postgres.py,azure_sql.py}
├── validation/{relationships.py,financial.py,distribution.py}
└── cli.py
```

CLI contract:

```bash
python -m synthetic_data.cli generate --profile tiny --seed 20260905 --batch-id initial
python -m synthetic_data.cli load --target all --batch-id initial
python -m synthetic_data.cli mutate --scenario incremental_01 --batch-id inc-001
python -m synthetic_data.cli validate --batch-id inc-001
```

The commands execute inside an Azure Container Apps Job in the cloud. The container receives database endpoints through environment references and secrets through Key Vault/managed configuration; credentials never appear in image layers or Git.

### 5.4 Volume profiles

| Profile | Members/patients | Encounters | Claims | Claim lines | Purpose |
|---|---:|---:|---:|---:|---|
| Tiny | 1,000 | 3,000 | 2,000 | 5,000 | End-to-end correctness |
| Small | 25,000 | 100,000 | 75,000 | 250,000 | Cloud portfolio demonstration |
| Medium | 100,000 | 500,000 | 350,000 | 1,200,000 | Optional performance test only |

Generation is deterministic, seeded, chunked, restartable, and memory-safe. A generation manifest records seed, profile, code version, table counts, checksums, and execution timestamp.

### 5.5 Realism and integrity rules

- `enterprise_person_id` links a synthetic patient and member while source natural keys stay independent.
- Enrollment must cover the claim service date unless an intentional DQ scenario is selected.
- Encounter/provider/facility references must be valid for the event date.
- Default financial rule: `0 <= paid_amount <= allowed_amount <= billed_amount`.
- Claim status transitions follow submitted -> pending -> approved/denied -> paid/adjusted/void.
- Claim lines, diagnoses, adjustments, and payments arrive with configurable lag.
- No real SSN, NPI, MRN, member, claim, diagnosis narrative, or address is used.
- Public-domain reference codes are used only where licensing permits; otherwise values are explicitly synthetic.

### 5.6 Change and failure scenarios

1. New members/patients and ordinary new transactions.
2. Demographic correction with identical modification timestamps across many keys.
3. Claim pending-to-paid transition.
4. Claim reversal and replacement.
5. Late-arriving diagnosis and claim line.
6. Soft-deleted/voided source record.
7. Duplicate source event.
8. Broken foreign key and invalid financial equation.
9. Unexpected null in a required field.
10. Nullable schema addition and breaking type-change simulation.

---

## 6. Metadata-driven ADF ingestion

### 6.1 Control schema

Azure SQL contains:

- `control.source_system`
- `control.ingestion_config`
- `control.pipeline_run`
- `control.table_run`
- `control.watermark_state`
- `control.batch_manifest`
- `control.dq_result`
- `control.job_dependency`
- `control.reprocess_request`
- `control.reconciliation_result`
- `control.pipeline_health`

`ingestion_config` includes source, schema, table, extraction SQL template, load type, primary key, watermark column, destination path, expected schema version, enabled flag, concurrency group, retry policy, and DQ thresholds.

### 6.2 Composite watermark algorithm

A timestamp alone can lose records when several rows share the same timestamp. Incremental extraction uses `(modified_timestamp, primary_key)`.

```sql
WHERE (
       modified_timestamp > @last_timestamp
       OR (modified_timestamp = @last_timestamp AND primary_key > @last_key)
      )
  AND (
       modified_timestamp < @high_timestamp
       OR (modified_timestamp = @high_timestamp AND primary_key <= @high_key)
      )
ORDER BY modified_timestamp, primary_key;
```

Operational sequence:

1. Acquire a table-run lock.
2. Read the last committed low watermark.
3. Capture a fixed source high watermark.
4. Extract only the bounded interval.
5. Write to a run-specific temporary Bronze raw path.
6. Validate file readability, count, schema, and control totals.
7. Publish the immutable batch path and manifest.
8. Commit the high watermark only after manifest success.
9. Release lock and make the batch eligible for Databricks.

### 6.3 ADF pipeline inventory

| Pipeline | Responsibility |
|---|---|
| `pl_master_ingestion` | Creates run, reads enabled metadata, executes table groups |
| `pl_ingest_table` | Full/incremental copy for one configured table |
| `pl_validate_landing` | Count/schema/file validation and manifest publication |
| `pl_trigger_databricks` | Starts Databricks workflow with explicit run/batch parameters |
| `pl_snowflake_publish` | Calls Snowflake load only after Gold export success |
| `pl_backfill_orchestrator` | Validates and executes approved bounded replay |
| `pl_health_monitor` | Checks freshness, failed dependencies, and unreconciled batches |

ADF performs orchestration and copying, not business transformations.

### 6.4 Bronze paths

```text
abfss://bronze@<storage>/raw/source=<source>/schema=<schema>/table=<table>/
  extract_date=YYYY-MM-DD/run_id=<run_id>/batch_id=<batch_id>/*.parquet

abfss://bronze@<storage>/manifests/run_id=<run_id>/batch_id=<batch_id>.json
abfss://bronze@<storage>/delta/<domain>/<table>/
```

Raw extracts are immutable. Bronze Delta preserves source columns and adds:

- `_run_id`
- `_batch_id`
- `_source_system`
- `_source_table`
- `_source_file`
- `_extracted_at`
- `_ingested_at`
- `_record_hash`
- `_schema_version`
- `_is_deleted`

---

## 7. Databricks, Spark, Delta, and Unity Catalog design

### 7.1 Unity Catalog layout

```text
catalog: healthcare_demo
schemas:
  bronze_clinical
  bronze_claims
  silver_restricted
  silver_deidentified
  gold_dimensions
  gold_facts
  gold_marts
  governance
  audit
```

External locations map to Bronze, Silver, Gold, quarantine, exports, checkpoints, and audit containers/prefixes. Grants use groups/roles such as:

- `platform_admin`
- `data_engineer`
- `phi_restricted`
- `analytics_deidentified`
- `auditor_readonly`

### 7.2 Databricks job inventory

A Databricks Asset Bundle defines code, environments, wheel dependencies, workflows, parameters, tasks, permissions, and job-cluster settings.

| Job | Tasks | Output |
|---|---|---|
| `wf_bronze_ingestion` | manifest check -> raw read -> schema validation -> Bronze append -> audit | Bronze Delta |
| `wf_silver_member` | normalize -> dedupe -> survivorship -> tokenization -> DQ -> publish | restricted/de-ID member Silver |
| `wf_silver_provider` | standardize -> affiliation resolution -> DQ -> publish | provider/facility Silver |
| `wf_silver_claims` | claim lifecycle -> financial rules -> line/diagnosis conformance -> DQ | claims Silver |
| `wf_silver_clinical` | encounter/diagnosis/procedure/observation conformance -> DQ | clinical Silver |
| `wf_gold_dimensions` | unknown row -> SCD2 dimensions -> audit | Gold dimensions Delta |
| `wf_gold_facts` | key lookup -> inferred members -> facts/bridges -> reconciliation | Gold facts Delta |
| `wf_gold_kpis` | aggregate from Gold facts -> KPI validation | Gold marts Delta |
| `wf_gold_export` | select changed/full snapshot -> Parquet export -> manifest | Snowflake load package |
| `wf_backfill` | scope resolution -> isolated replay -> compare -> promote | Reprocessed partitions/keys |
| `wf_health_check` | freshness/DQ/reconciliation checks | health table/alerts |

### 7.3 Job-cluster policy

- Jobs compute only; no permanent all-purpose cluster.
- Latest compatible LTS Databricks Runtime is chosen at implementation and pinned in the bundle.
- Photon is enabled only if supported and cost-tested.
- Smallest allowed single-node configuration for Tiny; tightly bounded workers for Small if a single node is insufficient.
- Auto-termination after job completion.
- No local credential files; Azure/Snowflake secrets are runtime references.
- Spark configuration includes UTC session timezone, Delta schema checks, adaptive query execution, and controlled shuffle partitions.
- Cluster policy blocks oversized node types and excessive workers.

Exact runtime/SKU selection is a deployment-time gate because trial availability and regional capacity change.

---

## 8. Bronze-to-Silver Spark rules

### 8.1 Standardization

- Canonical snake_case names.
- Explicit data types; no implicit string-to-number behavior.
- UTC timestamps plus original source timezone where relevant.
- Standard null handling; placeholders such as `UNKNOWN`, empty string, and `999999` mapped by contract.
- Decimal precision fixed for all financial fields.
- Standard member, plan, claim, encounter, provider, diagnosis, procedure, and status values.
- Source lineage retained on every Silver row.

### 8.2 Deterministic deduplication

Rows are ranked using documented keys in this order:

1. business key;
2. source business version where available;
3. modification timestamp;
4. extraction timestamp;
5. batch sequence;
6. deterministic record hash tie-breaker.

Duplicates are not silently discarded. Counts and losing record references are written to sanitized audit tables.

### 8.3 Survivorship rules

#### Member/patient

- Source-specific legal identifiers never cross into de-identified Silver.
- Most recent non-null verified demographic value survives.
- Null never overwrites a valid value unless an explicit source-delete flag is present.
- Address history remains in restricted data; de-identified geography is generalized to state/region or coarse ZIP grouping.
- Conflicting enterprise-person matches are quarantined, not automatically joined.

#### Provider/facility

- Active affiliation for the event/service date is selected.
- A later row cannot retroactively replace an affiliation outside its effective period.
- Specialty changes are preserved for downstream SCD2 history.

#### Claim lifecycle

- A claim version is identified by claim business ID, source version, and adjustment chain.
- Original, replacement, reversal, void, denied, approved, and paid states remain auditable.
- Reversal negates the applicable prior financial effect.
- Replacement supersedes the referenced claim for current-state analytics but does not erase history.
- Paid totals derive from payment events where present; header paid amount is reconciled, not trusted blindly.
- Late claim lines or diagnoses reopen only affected business keys/partitions.

#### Clinical

- Corrected results supersede prior result versions for current views while preserving version history.
- Impossible dates, units, ranges, or encounter relationships are quarantined.
- Observations are not silently converted unless a versioned unit-conversion mapping exists.

### 8.4 Data quality disposition

| Severity | Result |
|---|---|
| Critical | Fail domain batch and block Gold |
| Error | Quarantine rows; fail batch if configured threshold is exceeded |
| Warning | Publish, record metric, and alert |
| Info | Metric only |

Example gates include primary-key uniqueness, parent-child relationships, enrollment-at-service, valid date ordering, accepted statuses, financial equations, claim header/line reconciliation, valid effective-date ranges, and direct-identifier absence in de-identified tables.

---

## 9. PHI/PII tokenization, masking, and access design

### 9.1 Classification metadata

Every column is registered as one of:

- `DIRECT_IDENTIFIER`
- `PHI`
- `QUASI_IDENTIFIER`
- `FINANCIAL_SENSITIVE`
- `NON_SENSITIVE`

The classification registry drives transformations, tests, Unity Catalog tags, documentation, and Snowflake policies.

### 9.2 Tokenization

Stable analytical identifiers use keyed HMAC-SHA-256:

```text
token = HMAC_SHA256(secret_key, source_system || canonical_identifier)
```

Properties:

- deterministic for joins;
- resistant to rainbow-table attacks unlike an unsalted hash;
- key stored outside code in Key Vault/secret scope;
- environment-specific key to prevent cross-environment correlation;
- token version stored so future key rotation can be controlled.

Raw identifiers are retained only in restricted Silver where the demonstration needs to prove the control. Broad Gold outputs contain tokens, not raw member/patient IDs.

### 9.3 De-identification rules

- Remove name, email, phone, street address, and synthetic national identifiers.
- Convert date of birth to age band; suppress or top-code very old ages where appropriate.
- Generalize ZIP/postal location to coarse geography.
- Retain service dates because this is synthetic data, but document date shifting as the production pattern.
- Suppress rare combinations below a configured demonstration threshold in selected KPI outputs.
- Scan schemas and sample values to prove direct identifiers are absent.

### 9.4 Defense in depth

- TLS in transit and platform encryption at rest.
- Key Vault-managed secrets.
- Managed identity where supported.
- ADLS RBAC plus ACLs.
- Unity Catalog tags, grants, lineage, and restricted schemas.
- Snowflake role hierarchy, dynamic masking policies, row-access policies where justified, access history, and query tags.
- Logs contain run IDs and hashes, never names or full payloads.

---

## 10. Spark-built Gold dimensional model

### 10.1 Dimensions

| Table | SCD type | Important attributes |
|---|---|---|
| `dim_member` | Type 2 | member token, age band, gender category, geography band, effective dates |
| `dim_provider` | Type 2 | provider token, specialty, status, affiliation attributes |
| `dim_facility` | Type 2 | facility token, type, region, status |
| `dim_plan` | Type 2 | plan, line of business, product type, funding type |
| `dim_diagnosis` | Type 1/reference | diagnosis code/category/description class |
| `dim_procedure` | Type 1/reference | procedure code/category/service group |
| `dim_date` | Static | day/week/month/quarter/year/fiscal attributes |
| `dim_claim_status` | Type 1/reference | normalized claim lifecycle state |

Each SCD2 row contains surrogate key, business key/token, attribute hash, `effective_from`, `effective_to`, `is_current`, `created_batch_id`, and `updated_batch_id`. Effective periods cannot overlap.

### 10.2 Facts and declared grains

| Table | Grain | Measures/examples |
|---|---|---|
| `fact_claim` | One analytically valid claim version | billed, allowed, paid, member liability, denial flag |
| `fact_claim_line` | One valid claim line version | units, billed, allowed, paid |
| `fact_encounter` | One encounter | length of stay, visit count, readmission indicators |
| `fact_observation` | One observation version | numeric result, abnormal flag |
| `fact_authorization` | One authorization request version | requested/decision timestamps, turnaround hours, approval flag |
| `fact_payment` | One payment/remittance event | payment and adjustment amount |
| `bridge_claim_diagnosis` | One claim-diagnosis relationship | sequence and primary-diagnosis flag |

Unknown dimension members use a standard surrogate key. Late-arriving dimensions create inferred rows which are repaired in a later batch without changing fact grain.

### 10.3 Gold build order

1. Validate required Silver domain batches.
2. Build/update reference dimensions and `dim_date`.
3. Apply SCD2 changes to member/provider/facility/plan.
4. Create inferred dimensions for unresolved but valid late keys.
5. Resolve surrogate keys as of each fact event date.
6. Build claim, claim-line, authorization, payment, encounter, and observation facts.
7. Build bridges.
8. Reconcile counts and financial totals to Silver.
9. Build KPI aggregate tables.
10. Commit Gold batch status.
11. Export only committed Gold data to batch-scoped Parquet.

---

## 11. KPI marts built by Spark and served in Snowflake

KPI definitions are versioned contracts with owner, grain, numerator, denominator, exclusions, refresh frequency, and quality threshold.

| KPI table | Grain | Example measures/formulas |
|---|---|---|
| `kpi_claims_monthly` | month, plan, region | claim count, billed, allowed, paid, paid-to-allowed ratio |
| `kpi_denial_rate` | month, plan, provider specialty, denial category | denied claims / adjudicated claims |
| `kpi_adjustment_rate` | month, plan | adjusted or reversed claims / finalized claims |
| `kpi_pmpm_cost` | month, plan, region | total allowed amount / enrolled member months |
| `kpi_utilization` | month, service category, 1,000-member basis | services / member months * 1000 |
| `kpi_authorization` | month, service category | approval rate, median and p90 turnaround hours |
| `kpi_readmission` | discharge month, facility/region | qualifying 30-day readmissions / eligible discharges |
| `kpi_data_freshness` | pipeline/domain | source-to-Gold lag, last success, SLA status |
| `kpi_data_quality` | batch/domain/rule | pass rate, quarantined count, threshold status |
| `kpi_financial_reconciliation` | batch/source | source, Silver, Gold, Snowflake counts and amount differences |

KPI outputs include `metric_version`, `as_of_timestamp`, and `batch_id`. Snowflake exposes secure views for approved BI roles. Because all data is synthetic, these metrics are demonstrations and not clinical or actuarial advice.

---

## 12. Gold export and Snowflake loading plan

### 12.1 Export contract

```text
abfss://gold@<storage>/export/table=<table>/load_date=YYYY-MM-DD/batch_id=<batch_id>/*.parquet
abfss://gold@<storage>/export/manifests/batch_id=<batch_id>.json
```

Manifest fields:

- table and schema version;
- batch/run ID;
- export mode: `delta_changes` or `full_snapshot`;
- exact file list and checksums;
- row count;
- distinct business-key count;
- min/max event dates;
- financial control totals;
- Spark code version and Delta source version.

### 12.2 Snowflake objects

Databases/schemas:

```text
HEALTHCARE_DEMO.RAW_STAGE
HEALTHCARE_DEMO.CURATED
HEALTHCARE_DEMO.KPI
HEALTHCARE_DEMO.AUDIT
HEALTHCARE_DEMO.SECURE_SHARE
```

Other objects:

- Azure storage integration;
- external stage over only the Gold export prefix;
- Parquet file format;
- transient staging tables;
- permanent dimensions/facts/KPIs;
- load audit and reconciliation tables;
- masking/row-access policies;
- secure views;
- X-Small loading/BI warehouses;
- resource monitor.

### 12.3 Controlled load sequence

1. ADF receives successful Gold export status and `batch_id`.
2. ADF calls a Snowflake procedure/task with the explicit manifest path.
3. Snowflake validates that the batch was not already committed.
4. `COPY INTO` loads exact manifest files into batch-scoped transient staging.
5. Validate file count, row count, schema, nullability, uniqueness, and financial controls.
6. Begin a Snowflake transaction.
7. MERGE SCD2 dimensions in dependency order.
8. MERGE facts/bridges using stable business/version keys.
9. MERGE KPI aggregate tables by their declared grain and metric version.
10. Write `AUDIT.LOAD_AUDIT` and reconciliation records.
11. Commit and mark the batch published.
12. On failure, roll back; prior curated data remains queryable.

A rerun of an already successful `batch_id` is a no-op unless an approved replay version is supplied.

### 12.4 Why not use the Spark Snowflake connector for final writes

The connector is useful, but direct writes make it easier to create partially published business truth and harder to replay exact files. The selected default is Parquet export plus Snowflake `COPY INTO`, staging validation, and transactional MERGE. The connector may be used only for small control calls or test comparisons, not direct final-table publication.

---

## 13. Backfill and reprocessing design

### 13.1 Request contract

```yaml
request_id: bf-20260905-001
domain: claims
start_business_date: 2025-01-01
end_business_date: 2025-01-31
business_key_range: null
reason: "Demonstrate corrected claim survivorship rule"
requested_by: operator
code_version: git-sha
contract_version: v1
mode: dry-run | execute
```

### 13.2 Backfill algorithm

1. Validate request, authorization, date range, and affected domains.
2. Resolve exact immutable Bronze manifests.
3. Estimate rows/files/compute and require approval if above threshold.
4. Block overlap with conflicting live loads or serialize by domain/partition.
5. Process into an isolated replay namespace using a new replay batch ID.
6. Run all Silver, privacy, Gold, and KPI quality checks.
7. Compare replay outputs against currently published data.
8. Promote only affected business keys/partitions with idempotent MERGE.
9. Export a new Snowflake load package and publish transactionally.
10. Record old/new code versions, counts, totals, approver, and reason.
11. Do not move the normal incremental source watermark backward.

Backfill modes include full-domain rebuild, date-partition replay, business-key replay, and KPI-only rebuild.

---

## 14. Monitoring, health checks, and operational runbooks

### Metrics by layer

- **ADF:** status, duration, retries, queue time, rows/bytes, throughput, watermark lag.
- **Bronze:** source count, file count, checksum, schema hash, duplicate batch, corrupt records.
- **Silver:** input/output/quarantine counts, duplicates, survivorship counts, rule failures, Delta MERGE metrics.
- **Gold Spark:** dimension inserts/updates, inferred keys, fact counts, orphan keys, KPI output counts, reconciliation deltas.
- **Snowflake:** copied files, loaded/merged rows, failed files, credits, queue time, query latency, access failures.
- **End to end:** freshness, latency, success rate, recovery time, cost per batch.

### Health job checks

- latest success and freshness per source/domain/table;
- watermarks that stopped advancing;
- incomplete Bronze paths without a manifest;
- failed/long-running Databricks tasks;
- DQ failure and quarantine thresholds;
- Gold batches not exported;
- exports not committed in Snowflake;
- source-to-Snowflake financial/count differences;
- Azure budget and Snowflake resource-monitor state.

### Runbooks to deliver

1. Source unavailable.
2. ADF partial copy.
3. Watermark mismatch.
4. Schema drift.
5. Databricks task/cluster failure.
6. Critical DQ failure.
7. Tokenization-key rotation.
8. Snowflake COPY/MERGE failure.
9. Late-arriving data replay.
10. Historical backfill.
11. Cost threshold breach.
12. Emergency stop and complete teardown.

Alerts must contain sanitized run identifiers, failure stage, owning runbook, and next action—not record payloads.

---

## 15. Failure behavior matrix

| Scenario | Required behavior |
|---|---|
| Source connection failure | Retry with backoff; watermark unchanged; downstream blocked |
| Partial raw write | No success manifest; batch ignored; temporary files cleaned later |
| Duplicate ADF trigger | Run/batch idempotency prevents duplicate publication |
| Identical timestamps | Composite timestamp/key watermark prevents loss |
| Source changes during extraction | Fixed high watermark creates a bounded batch |
| Compatible nullable column | Detect and accept only under configured contract policy |
| Breaking type/removal | Fail and require new contract version |
| Bronze/Silver Spark failure | Inputs preserved; exact batch can rerun |
| Critical DQ failure | Quarantine evidence and block Gold |
| Token secret unavailable | Fail closed; do not output unprotected IDs |
| Claim reversal/replacement | Preserve audit history and recompute affected keys/KPIs |
| Late dimension | Create inferred member, then repair deterministically |
| Gold export failure | Snowflake is not triggered |
| Snowflake COPY failure | Curated schema unchanged; reload missing/failed files |
| Snowflake MERGE failure | Transaction rollback; previous Gold remains active |
| Cost alarm | Stop/disable jobs and execute emergency teardown runbook |

---

## 16. Infrastructure as Code

### Terraform stack order

1. `bootstrap` — state resource group, storage account/container, optional state lock conventions.
2. `azure_core` — project resource group, tags, budget, action group, Log Analytics, Key Vault, ADLS, ACR.
3. `sources` — PostgreSQL, Azure SQL, databases, firewall/network settings, private DNS only if selected.
4. `data_factory` — ADF, managed identity permissions, linked-service shells, diagnostics.
5. `databricks_workspace` — workspace, access connector/identity, storage permissions.
6. `databricks_data` — Unity Catalog/external locations/grants where account permissions allow.
7. `container_jobs` — Container Apps environment/job for synthetic generation.
8. `monitoring` — diagnostic settings, alerts, saved queries, workbook assets.
9. `snowflake` — roles, warehouses, resource monitor, database/schemas, stage/integration, policies.

Terraform will create infrastructure and stable platform objects. Database DDL, ADF JSON, Databricks bundle code, and versioned Snowflake SQL migrations remain deployable artifacts rather than unreadable giant inline Terraform strings.

### Network profile for the trial demo

The default demo prioritizes affordability while still enforcing TLS, firewall allow-lists, managed identities, secrets, and public-access restrictions where practical. A full private-endpoint/VNet-injected architecture is documented as the production reference but is not automatically deployed because private networking can add cost and complexity and may exceed trial quotas.

The README must clearly distinguish the cost-conscious demo network from a regulated production network.

### Terraform safety

- remote encrypted state;
- secrets excluded from state wherever possible;
- `.tfvars` containing secrets ignored;
- deletion protection disabled only for ephemeral demo resources;
- unique suffixes generated once and stored in state;
- pre-destroy export of run evidence;
- `prevent_destroy` only on bootstrap state until all child stacks are removed.

---

## 17. Dependencies and packaging

### Python project

Use `pyproject.toml` and a lockfile. Dependency groups:

- runtime generation: Faker, NumPy, database drivers, YAML/config validation;
- Spark: PySpark-compatible project code and Delta APIs supplied/pinned with the Databricks runtime;
- data contracts: Pydantic/Pandera where useful;
- tests: Pytest, Hypothesis, coverage;
- quality: Ruff, formatter, mypy/type checks;
- security: dependency audit and secret scanning.

Exact versions are pinned during implementation after selecting the Databricks LTS runtime so local package constraints do not conflict with runtime-provided Spark libraries.

### Infrastructure/deployment tools

- Terraform and locked providers for AzureRM, AzureAD where needed, Databricks, and Snowflake;
- Azure CLI;
- Databricks CLI with Asset Bundles;
- Snowflake CLI or SnowSQL;
- Docker/Buildx;
- SQLFluff for SQL formatting/linting;
- Checkov or equivalent IaC scanning;
- GitHub Actions pinned to commit SHAs or trusted major versions according to repository policy.

---

## 18. CI/CD plan

### Branch and environments

- feature branch -> pull request validation;
- `main` -> package/deploy artifacts only after approval;
- GitHub `demo` environment -> protected cloud apply and data run;
- GitHub `destroy` environment -> protected teardown but easy to invoke in an emergency.

### Authentication

GitHub Actions uses OpenID Connect federation to Azure; no long-lived Azure client secret is stored. Snowflake automation uses the strongest practical trial-supported key-pair/OAuth pattern, with sensitive material in GitHub environment secrets and rotation documentation.

### Pull request pipeline

1. Validate repository structure and generated docs.
2. Python format, lint, and type checks.
3. Unit/property tests for generators, watermark logic, tokenization, survivorship, SCD2, and KPIs.
4. SQL lint and static tests.
5. Terraform fmt/validate/tflint and security scan.
6. Validate ADF JSON/templates.
7. Validate Databricks Asset Bundle.
8. Build container and run vulnerability scan without pushing production tags.
9. Produce Terraform plans for approved stacks without applying.

### Deployment pipeline

1. Manual approval and cost/quota preflight.
2. Apply bootstrap/core/source infrastructure.
3. Build and push synthetic generator image to ACR.
4. Apply Container Apps Job and data platform stacks.
5. Deploy source DDL/control tables.
6. Deploy ADF artifacts.
7. Deploy Databricks bundle/jobs.
8. Apply Snowflake migrations/policies.
9. Run smoke tests.
10. Run Tiny end to end.
11. Publish test and reconciliation evidence.
12. Require separate approval before Small.

### Teardown pipeline

1. Disable ADF triggers and Databricks schedules.
2. Suspend Snowflake warehouses.
3. Export sanitized evidence and manifests needed for the portfolio.
4. Destroy dependent Snowflake objects if desired.
5. Destroy Databricks data objects/workspace dependencies.
6. Destroy Container Apps, sources, ADF, ADLS, monitoring, and core resource group.
7. Destroy ACR last among application resources.
8. Keep or destroy Terraform bootstrap state based on final decision.
9. Verify Azure portal has no billable project resources.
10. Verify Snowflake warehouses are suspended and resource monitor is active/account cleaned.

---

## 19. Repository structure to build

```text
.
├── README.md
├── PROJECT_PLAN.md
├── Makefile
├── pyproject.toml
├── uv.lock or equivalent lockfile
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/
│   ├── pr-checks.yml
│   ├── terraform-plan.yml
│   ├── deploy-demo.yml
│   ├── run-pipeline.yml
│   └── destroy-demo.yml
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── contracts/
│   ├── data-dictionary/
│   ├── kpis/
│   ├── lineage/
│   ├── runbooks/
│   ├── security/
│   └── cost/
├── infra/
│   ├── bootstrap/
│   ├── modules/{core,sources,adf,databricks,container_jobs,monitoring,snowflake}/
│   └── environments/demo/
├── synthetic_data/{config,reference,generators,scenarios,loaders,validation}/
├── databases/
│   ├── postgres/{ddl,indexes,tests}/
│   ├── azure_sql/{ddl,indexes,control,tests}/
│   └── migrations/
├── orchestration/adf/{linked_services,datasets,pipelines,triggers}/
├── databricks/
│   ├── databricks.yml
│   ├── resources/
│   ├── src/{bronze,silver,gold,quality,privacy,audit,common}/
│   └── tests/
├── snowflake/
│   ├── migrations/
│   ├── procedures/
│   ├── policies/
│   ├── tests/
│   └── secure_views/
├── monitoring/{azure,snowflake,queries,dashboards}/
├── scripts/{preflight,deploy,smoke,run_scenario,backfill,destroy}/
└── tests/{unit,integration,contracts,e2e,security,resilience}/
```

Core interfaces:

```text
generate_dataset(config, seed, batch_id) -> generation_manifest
apply_change_scenario(scenario, batch_id) -> generation_manifest
extract_table(table_config, watermark_window) -> raw_batch_manifest
promote_bronze(raw_batch_manifest) -> bronze_result
build_silver(domain, batch_ids) -> quality_and_promotion_result
build_gold(gold_batch_id, silver_versions) -> gold_result
export_gold(gold_batch_id) -> snowflake_load_manifest
publish_snowflake(load_manifest) -> reconciliation_result
execute_backfill(request) -> backfill_result
```

---

## 20. Detailed implementation roadmap and approval gates

We will implement one phase at a time. At the end of every phase, the user receives exact commands, expected output, validation SQL, troubleshooting notes, and a commit checkpoint. We do not proceed if the exit criteria fail.

### Phase 0 — Workstation and repository foundation

**Build**

1. Validate Azure CLI, Terraform, Docker, Python, Databricks CLI, and Snowflake CLI.
2. Scaffold Python package, lock dependencies, Make targets, pre-commit, tests, and GitHub workflows.
3. Add naming/tagging standards, architecture decision records, `.env.example`, and secret rules.
4. Add cost preflight and emergency-stop scripts.
5. Configure GitHub environments and document OIDC setup.

**Exit criteria**

- All lint/unit/static checks pass.
- No credential is committed.
- Terraform validates without cloud apply.
- Cost and teardown checklists are approved.

### Phase 1 — Source schemas and complete synthetic data

**Build**

1. Write PostgreSQL and Azure SQL DDL, indexes, constraints, and migration ordering.
2. Write source contracts and sensitivity metadata for every column.
3. Implement all generators and shared domain factories.
4. Implement Tiny/Small/Medium profiles.
5. Implement cloud-safe chunked bulk loaders.
6. Implement all incremental and bad-data scenarios.
7. Add unit/property/referential/financial/distribution tests.
8. Build and scan the generator container.

**Exit criteria**

- Every listed table is generated and loadable.
- Same seed produces the same keys, counts, and checksums.
- Tiny fits all integrity constraints.
- Bad-data scenarios fail only expected tests.

### Phase 2 — Terraform bootstrap, budgets, and cloud sources

**Build**

1. Create remote state and project resource group.
2. Create budget/action group before compute.
3. Provision Key Vault, ADLS, ACR, Log Analytics.
4. Provision PostgreSQL and Azure SQL using approved smallest SKUs.
5. Configure firewall/TLS/identities and diagnostics.
6. Provision Container Apps Job.
7. Deploy DDL and run generator initial load in Azure.

**Exit criteria**

- Source tables/counts validate from cloud queries.
- Secrets are resolved at runtime.
- Budget alerts exist.
- `terraform destroy` plan is reviewed before continuing.

### Phase 3 — ADF Bronze raw ingestion

**Implementation status:** Complete as code and statically validated. Azure deployment,
source connectivity, ingestion execution, and runtime acceptance tests are deferred to the
final end-to-end deployment phase.

**Build**

1. [Implemented as code] Deploy control schema and seed ingestion metadata for all tables.
2. [Implemented as code] Create Key Vault-backed linked services and parameterized datasets.
3. [Implemented as code] Implement master/child/validation pipelines.
4. [Implemented as code] Implement full snapshots and composite-watermark incrementals.
5. [Implemented as code] Implement manifests, locks, retries, and audit logging.
6. [Deferred Azure test] Ingest Tiny initial data to immutable Bronze raw.
7. [Deferred Azure tests] Test duplicate trigger, identical timestamp, and partial failure.

**Exit criteria**

- [Pending Azure runtime test] All source counts reconcile to successful manifests.
- [Pending Azure runtime test] Failed runs do not advance watermarks.
- [Pending Azure runtime test] Duplicate execution does not duplicate a published batch.

### Phase 4 — Databricks Bronze Delta and Unity Catalog

**Implemented as repository code**

1. Phase 2 Terraform provisions the Azure Databricks workspace and access connector.
2. A tested Python wheel reads Azure SQL control metadata or a controlled Delta manifest,
   enforces immutable raw-path identities, and gates processing on published/reconciled
   manifests and READY dependencies.
3. Explicit versioned contracts cover all 19 Phase 1 source tables, with policies for
   exact schemas, nullable additive columns, safe widening, and rejected breaking drift.
4. Parquet plus controlled JSON/CSV readers, corrupt-record quarantine, source-aligned
   Delta targets, nine operational metadata columns, and Delta registry/audit tables are
   implemented.
5. Batch/table idempotency, successful-rerun skips, deterministic batch-partition retries,
   and independently auditable backfills are implemented.
6. Successful explicit-batch processing transactionally publishes Azure SQL dependency
   transitions from Bronze completion to Silver readiness.
7. The Databricks Asset Bundle defines the wheel workflow, bounded retries, restricted job
   permissions, no active schedule, one concurrent run, and an ephemeral non-Photon
   single-node job cluster with 15-minute auto-termination.
8. Credential-free bundle validation, pure unit tests, architecture documentation, and a
   future deployment/runtime acceptance runbook are implemented.

**Deferred until final cloud deployment/testing**

1. Deploy the Databricks Asset Bundle and run the workflow in Azure.
2. Attach/accept the account-level Unity Catalog metastore and configure the catalog,
   schemas, storage credential, external locations, workspace bindings, and grants.
3. Verify the selected Databricks Runtime and Azure VM node type are available regionally.
4. Run all Tiny published manifests through Spark and validate physical Delta writes,
   quarantine, schema evolution, audit metrics, reruns, retries, and backfills.
5. Perform native workspace-backed bundle validation with a compatible Databricks CLI and
   authenticated cloud configuration.

**Exit criteria**

- [Pending Azure runtime test] Bronze tables contain source rows plus metadata.
- [Pending Azure runtime test] Exact rerun is a no-op.
- [Pending Azure runtime test] Corrupt/breaking schemas fail safely.

### Phase 5 — Silver Spark transformations and privacy

**Build**

1. Implement member/patient conformance and enterprise linking.
2. Implement provider/facility conformance.
3. Implement claim/header/line/diagnosis lifecycle and survivorship.
4. Implement authorization/payment/adjustment logic.
5. Implement clinical conformance.
6. Implement HMAC tokenization and de-identification.
7. Implement DQ severity gates, quarantines, contracts, and tests.
8. Publish restricted and de-identified Silver Delta.

**Exit criteria**

- Injected critical defects block publication.
- Allowed defects quarantine with correct counts.
- De-identified schemas/logs contain no direct identifiers.
- Claim financial and lifecycle tests pass.

### Phase 6 — Spark Gold facts, dimensions, and KPIs

**Build**

1. Create `dim_date` and reference dimensions.
2. Implement reusable SCD2 engine and effective-period tests.
3. Build member/provider/facility/plan dimensions.
4. Build claim, line, encounter, observation, authorization, and payment facts.
5. Build claim-diagnosis bridge and inferred-dimension handling.
6. Build all KPI aggregate tables and metric contracts.
7. Add Silver-to-Gold count/financial reconciliation.
8. Publish batch-scoped Parquet exports and manifests.

**Exit criteria**

- Every fact has declared/tested grain.
- SCD2 periods do not overlap.
- Late dimension repair works.
- KPIs reproduce independently calculated test expectations.
- Gold rerun is idempotent.

### Phase 7 — Snowflake serving layer

**Build**

1. Provision Snowflake roles, warehouses, monitor, DB/schemas, stage, and file format.
2. Deploy staging and curated DDL.
3. Implement manifest-driven `COPY INTO`.
4. Implement transactional SCD/fact/KPI MERGE procedures.
5. Implement load audit and reconciliation.
6. Apply masking/row policies and secure views.
7. Add Snowflake SQL and role-access tests.

**Exit criteria**

- Tiny Gold publishes transactionally.
- Spark and Snowflake counts/totals match.
- A failed merge leaves curated tables unchanged.
- BI role sees only approved masked/de-identified fields.

### Phase 8 — End-to-end incrementals, backfill, and resilience

**Build and demonstrate**

1. Initial full load.
2. Incremental batch with new records and same-timestamp updates.
3. Claim status transition plus reversal/replacement.
4. Late-arriving line/diagnosis and inferred-dimension repair.
5. Critical DQ failure, correction, and successful rerun.
6. Dry-run and execute bounded historical backfill.
7. Duplicate trigger/idempotency test.
8. Snowflake publication failure and recovery.

**Exit criteria**

- All scenarios have captured audit evidence.
- Normal watermarks remain correct after backfill.
- No partial layer is exposed as successful.

### Phase 9 — Monitoring, CI/CD, and operational hardening

**Build**

1. Deploy diagnostics, alerts, saved queries, and health job.
2. Implement freshness, DQ, reconciliation, and cost dashboard/export.
3. Complete PR, deploy, run, and destroy workflows.
4. Execute secret, dependency, IaC, container, access-control, and resilience tests.
5. Validate every alert links to a usable runbook.

**Exit criteria**

- Forced failures generate actionable sanitized alerts.
- CI blocks known bad code/infrastructure.
- Deployment is reproducible from a clean checkout.

### Phase 10 — Small demonstration, evidence, and destruction

**Run**

1. Confirm remaining Azure/Snowflake credit.
2. Run Small initial and incremental workloads.
3. Record timings, counts, Spark metrics, Snowflake query results, KPIs, and costs.
4. Capture sanitized screenshots/diagrams/lineage.
5. Suspend all compute.
6. Run ordered Terraform/Snowflake teardown.
7. Verify no billable resources remain.
8. Publish final README, demo script, trade-offs, cost report, and teardown proof.

**Exit criteria**

- Portfolio artifacts are complete.
- Azure project resources are gone or intentionally retained at zero/minimal cost.
- Snowflake compute is suspended/account objects cleaned as planned.

---

## 21. Test strategy

- **Unit:** generator rules, token stability, normalization, claim survivorship, SCD2 transitions, KPI formulas.
- **Property-based:** uniqueness, dates, enrollment coverage, amounts, effective periods, idempotency.
- **Database integration:** DDL, indexes, bulk loading, watermark predicates, same-timestamp rows, updates/deletes.
- **ADF contract:** linked-service parameters, metadata rows, success/failure state transitions.
- **Spark integration:** Delta append/MERGE, schema drift, quarantine, replay, SCD2, late data.
- **Snowflake SQL:** not-null, uniqueness, relationships, fact grain, SCD overlap, policy output, reconciliation.
- **Security:** denied role access, masking output, no raw IDs in de-ID/Gold, no secrets in logs/state/artifacts.
- **Resilience:** partial copy, duplicate trigger, source outage, Spark failure, DQ failure, Snowflake failure/restart.
- **Performance/cost:** generation throughput, ADF throughput, Spark shuffle/files, Snowflake credits/query latency.
- **End to end:** full, two incrementals, reversal, late arrival, failure/recovery, backfill, teardown.

---

## 22. Operator workflow we will provide during implementation

For each phase, instructions will use the same structure:

1. **Purpose** — what is being built and why.
2. **Files created/changed** — exact repository paths.
3. **Settings** — each portal/CLI/Terraform value and safe default.
4. **Commands** — copy/paste commands in execution order.
5. **Expected output** — what success looks like.
6. **Validation** — SQL, API, Spark, or CLI checks.
7. **Failure handling** — common error, diagnosis, and recovery.
8. **Cost impact** — resources started and how to stop them.
9. **Checkpoint** — tests and Git commit before the next phase.
10. **Teardown** — phase-specific rollback if necessary.

The user should not need to invent code, job settings, dependency versions, DDL, pipeline parameters, or backfill logic. We will create those artifacts and provide the exact execution steps. Credentials and subscription-specific identifiers remain user-supplied through documented secure inputs.

---

## 23. Deployment prerequisites to verify before Phase 2

These do not block repository and source-code implementation, but they block cloud deployment:

1. Azure trial is active and available credit is confirmed.
2. Selected Azure region allows PostgreSQL, Azure SQL, Container Apps, ACR, ADF, and Databricks under current quota.
3. The tenant allows an Azure Databricks workspace and required Unity Catalog/account operations.
4. The operator has Owner or sufficient Contributor plus User Access Administrator permissions for identity/RBAC steps.
5. GitHub repository/environment administration is available for OIDC.
6. Snowflake trial account exists on Azure, preferably in the same/nearby region.
7. Snowflake role can create storage integration, warehouses, databases, roles, and policies.
8. A unique naming suffix and operator IP/network approach are selected.

If Unity Catalog cannot be provisioned in the trial/account, implementation pauses at that gate rather than silently replacing it with an ungoverned design. A documented fallback may be approved separately.

---

## 24. Final definition of done

The project is complete only when:

- all source tables are generated by deterministic Python code in Azure;
- ADF ingests full and incremental data with correct composite watermarks;
- Bronze is immutable and replayable;
- Spark builds cleansed Silver using tested survivorship and DQ rules;
- direct identifiers are tokenized/removed from de-identified outputs;
- Spark creates facts, dimensions, bridges, and KPI marts;
- Snowflake loads exact Gold exports through staging and transactional MERGE;
- counts and financial totals reconcile from source to Snowflake;
- masking/access tests pass;
- incremental, reversal, late-arrival, failure/recovery, and backfill scenarios pass;
- CI/CD can validate, deploy, run, and destroy the platform;
- monitoring and runbooks are actionable;
- sanitized portfolio evidence is captured;
- all billable demo resources are destroyed or explicitly verified suspended.

---

## 25. Reference documentation

- Azure free account: <https://azure.microsoft.com/en-us/free/>
- Azure Data Factory pricing: <https://azure.microsoft.com/en-us/pricing/details/data-factory/data-pipeline/>
- Azure PostgreSQL pricing: <https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/>
- Azure Databricks Unity Catalog: <https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/>
- ADF incremental watermark pattern: <https://learn.microsoft.com/en-us/azure/data-factory/tutorial-incremental-copy-overview>
- Snowflake loading from Azure: <https://docs.snowflake.com/en/user-guide/data-load-azure>
- Elevance Health public overview: <https://www.elevancehealth.com/who-we-are>

Cloud prices, free offers, quotas, runtime versions, provider versions, and regional availability change. They will be revalidated and pinned immediately before deployment.
