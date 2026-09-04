# Healthcare Data Platform — Project Plan

## 1. Project objective

Build a portfolio-grade, end-to-end healthcare data platform that demonstrates how a large payer/provider organization could migrate claims, membership, provider, and clinical data into Azure and Snowflake.

The project will:

- generate deterministic, realistic-looking **synthetic data only**;
- use PostgreSQL and SQL Server-compatible databases as independent source systems;
- use Azure Data Factory (ADF) as the metadata-driven ingestion and orchestration control plane;
- retain immutable source extracts in Azure Data Lake Storage Gen2 (ADLS Gen2);
- use Azure Databricks, Spark, Delta Lake, and Unity Catalog for Bronze and Silver processing;
- publish dimensional Gold models to Snowflake;
- demonstrate PII/PHI classification, tokenization, masking, access control, lineage, quality gates, observability, replay, and backfill;
- provision cloud resources with Terraform and deploy artifacts through CI/CD;
- remain small enough to operate using Azure trial credits and Snowflake trial credits.

This is an **Elevance Health-inspired fictional portfolio project**. It is not affiliated with Elevance Health and must not contain Elevance source code, schemas, credentials, business rules, or data. Elevance Health's public description of its health benefits, care delivery/services, Medicare, Medicaid, and whole-health activities informs only the high-level synthetic domains.

## 2. Important design corrections to the initial brief

1. **Use an immutable Landing area before Delta Bronze.** ADF writes source-aligned Parquet extracts to `landing`. Databricks then appends those rows and ingestion metadata to Bronze Delta tables. The original extract remains available for forensic replay.
2. **Use Delta, not plain Parquet, for Bronze and Silver tables.** Delta files are Parquet with a transaction log and provide schema enforcement, ACID writes, time travel, and idempotent `MERGE` behavior. This is a better fit for Unity Catalog and reprocessing.
3. **Do not claim that a portfolio demo is HIPAA compliant.** The project demonstrates HIPAA-aligned technical controls using synthetic data. Actual compliance also requires contracts, policies, risk analysis, operational controls, and eligible service configurations.
4. **Keep Gold in Snowflake.** ADLS/Databricks Gold tables may be added later for ML features, but the authoritative analytics mart in this scope is Snowflake.
5. **Provide local and cloud execution profiles.** Developers should not have to spend cloud credits to test generators, SQL, Spark transformations, or quality rules.

## 3. Target architecture

```text
                         SOURCE SYSTEMS
        ┌─────────────────────────┬──────────────────────────┐
        │ PostgreSQL              │ SQL Server / Azure SQL   │
        │ Clinical + provider     │ Members + claims         │
        └────────────┬────────────┴─────────────┬────────────┘
                     │                          │
                     └──────────┬───────────────┘
                                ▼
                    Azure Data Factory
              metadata, watermark, retries, audit
                                │
                                ▼
                   ADLS Gen2 immutable Landing
                 source/table/load_date/run_id/*.parquet
                                │
                                ▼
             Azure Databricks + Unity Catalog
        Bronze Delta → validation/quarantine → Silver Delta
                                │
                                ▼
                  Snowflake external stage
                 staging tables + COPY INTO
                                │
                                ▼
                   Snowflake Gold warehouse
          dimensions, facts, secure views, masking policies
                                │
                   ┌────────────┴────────────┐
                   ▼                         ▼
                Power BI              SQL / ML consumers

 Cross-cutting: Key Vault, Entra ID, RBAC, Terraform, GitHub Actions,
 Azure Monitor/Log Analytics, pipeline audit tables, cost budgets/alerts.
```

### Execution profiles

| Profile | Purpose | Source databases | Processing | Cost behavior |
|---|---|---|---|---|
| Local | Fast development and CI | Docker PostgreSQL + SQL Server | local PySpark/Delta; local filesystem | No cloud compute |
| Cloud demo | End-to-end portfolio demonstration | Azure Database for PostgreSQL Flexible Server + Azure SQL Database (SQL Server engine) | ADF + ephemeral Databricks job cluster + Snowflake trial | Deploy, run, capture evidence, destroy |
| Production reference | Architecture discussion only | On-prem PostgreSQL/SQL Server through self-hosted IR, VPN/ExpressRoute | private endpoints and hardened workspaces | Not provisioned by default |

Using Azure SQL Database in the cloud demo avoids paying for a full SQL Server VM while retaining SQL Server compatibility. If exact SQL Server behavior is required, the local Docker profile supplies it.

## 4. Synthetic source model

All identifiers, names, addresses, clinical values, and transactions are fictional. Generation is seeded and repeatable. Referential integrity is generated deliberately rather than repaired afterward.

### Source A — PostgreSQL: clinical and provider operations

| Table | Purpose | Incremental key | Sensitivity |
|---|---|---|---|
| `patients` | Patient demographics and contact attributes | `updated_at, patient_id` | Direct identifiers/PHI |
| `providers` | Synthetic provider and specialty data | `updated_at, provider_id` | Low; fake NPI-like ID |
| `facilities` | Hospitals, clinics, geography | `updated_at, facility_id` | Low |
| `encounters` | Inpatient, outpatient, emergency, virtual visits | `updated_at, encounter_id` | PHI |
| `diagnoses` | Encounter diagnosis records and ICD-like codes | `updated_at, diagnosis_id` | PHI |
| `procedures` | Encounter procedures and synthetic procedure codes | `updated_at, procedure_id` | PHI |
| `observations` | Labs/vitals with units and reference ranges | `updated_at, observation_id` | PHI |
| `medications` | Medication reference catalog | full load | Low |
| `prescriptions` | Patient medication orders | `updated_at, prescription_id` | PHI |

### Source B — SQL Server: health plan and claims administration

| Table | Purpose | Incremental key | Sensitivity |
|---|---|---|---|
| `members` | Subscriber/member identity | `modified_at, member_id` | Direct identifiers/PHI |
| `plans` | Commercial, Medicare-like, Medicaid-like plan products | full load | Low |
| `member_enrollment` | Coverage periods and product enrollment | `modified_at, enrollment_id` | PHI |
| `claims` | Professional/institutional claim headers | `modified_at, claim_id` | PHI/financial |
| `claim_lines` | Procedures, units, billed/allowed/paid amounts | `modified_at, claim_line_id` | PHI/financial |
| `claim_diagnoses` | Claim-to-diagnosis association | `modified_at, claim_diagnosis_id` | PHI |
| `authorizations` | Prior authorization requests and decisions | `modified_at, authorization_id` | PHI |
| `payments` | Claim payment/remittance events | `modified_at, payment_id` | PHI/financial |
| `claim_adjustments` | Reversal, denial correction, void, replacement | `modified_at, adjustment_id` | PHI/financial |

### Cross-source design

- A generated `enterprise_person_id` links `patients` and `members`, but each source also has its own natural identifier.
- Provider and facility references are exported to the claims generator so claims remain referentially plausible across systems.
- Service dates must fall inside enrollment periods.
- Claims are produced from eligible encounters, with controlled lag and occasional late arrival.
- Amount rules enforce `paid_amount <= allowed_amount <= billed_amount`, except deliberately injected bad-data cases.
- No real NPI, SSN, MRN, claim, CPT, or member identifiers will be emitted. Code lists will be public-domain subsets where licensing allows, otherwise clearly marked synthetic lookalikes.

### Data volume profiles

| Profile | Members/patients | Encounters | Claims | Claim lines | Intended use |
|---|---:|---:|---:|---:|---|
| Tiny | 1,000 | 3,000 | 2,000 | 5,000 | unit/integration tests |
| Small | 25,000 | 100,000 | 75,000 | 250,000 | regular cloud demo |
| Medium | 100,000 | 500,000 | 350,000 | 1,200,000 | performance demonstration |

Generators will stream in chunks and bulk-load databases; they must not retain an entire medium dataset in memory.

### Change simulation

A separate deterministic mutation command will create successive batches containing:

- new members, encounters, claims, and lines;
- demographic corrections;
- claim status transitions;
- reversals and replacement claims;
- late-arriving diagnoses and claim lines;
- soft deletes where supported;
- duplicate rows and invalid records when a `--quality-scenarios` option is enabled;
- schema additions in a controlled schema-evolution scenario.

## 5. Ingestion control plane

### Operational metadata tables

The cloud demo stores these under an isolated `control` schema in Azure SQL. The production reference would use a dedicated operational metadata database.

- `source_system`: connector and source-level configuration without secrets.
- `ingestion_config`: source schema/table, load type, keys, watermark column, destination, enabled flag, extraction query template, concurrency group, and quality thresholds.
- `pipeline_run`: one record per orchestration run.
- `table_run`: status, timing, low/high watermark, rows read/written/rejected, bytes, retry count, and error details.
- `watermark_state`: last committed composite watermark per source table.
- `batch_manifest`: exact Landing files, checksums, schema hash, and record count.
- `dq_result`: rule outcome, severity, observed value, threshold, and sample quarantine location.
- `reprocess_request`: bounded replay/backfill request and approval/status fields.

### Incremental extraction algorithm

1. Read the last committed `(timestamp, primary_key)` watermark.
2. Query the source for the current high watermark at run start.
3. Extract `old < key <= high`, using a composite predicate to avoid missing rows with identical timestamps.
4. Write to a run-specific temporary Landing path.
5. Validate file readability, schema, checksum, and row count.
6. Atomically publish the batch manifest and mark the Landing batch successful.
7. Advance the watermark only after successful publication.
8. Trigger the downstream workflow with the explicit `run_id` and `batch_id`.

ADF activities will use Lookup → ForEach → Copy → validation/stored-procedure logging. Concurrency and retry policy will be metadata-controlled. Full loads produce dated snapshots; incrementals never overwrite prior extracts.

## 6. Lakehouse design

### ADLS layout

```text
landing/<source>/<schema>/<table>/extract_date=YYYY-MM-DD/run_id=<uuid>/
bronze/<domain>/<table>/
silver_restricted/<domain>/<table>/
silver_deidentified/<domain>/<table>/
quarantine/<layer>/<domain>/<table>/run_id=<uuid>/
checkpoints/<pipeline>/<table>/
audit/<year>/<month>/<day>/
```

### Unity Catalog hierarchy

```text
catalog: healthcare_dev (and healthcare_demo)
schemas:
  bronze_clinical
  bronze_claims
  silver_restricted
  silver_deidentified
  governance
```

Unity Catalog will define storage credentials, external locations, catalogs, schemas, tables, tags, grants, and lineage. Production-like workspace isolation will be documented, but only a minimal single workspace is provisioned for the credit-conscious demo.

### Bronze behavior

- Read only batch files listed in a successful manifest.
- Preserve source columns and add `_run_id`, `_batch_id`, `_source_system`, `_source_file`, `_ingested_at`, `_record_hash`, and `_is_deleted`.
- Append idempotently; a rerun with an existing successful batch does nothing.
- Capture corrupt/unparseable rows in quarantine.
- Detect and log schema drift before accepting it.

### Silver behavior

- Normalize names, types, timestamps (UTC), null semantics, gender/plan/status enumerations, and financial precision.
- Deduplicate deterministically by business key, source version, modification timestamp, and ingestion sequence.
- Apply claim lifecycle/survivorship rules; do not use an undocumented “latest wins” shortcut.
- Validate domain ranges, enrollment-at-service, parent-child relationships, code formats, and financial equations.
- Use Delta `MERGE` for idempotent upserts and explicit delete handling.
- Maintain restricted and de-identified outputs.
- Tokenize stable identifiers with keyed HMAC, not unsalted hashing.
- Generalize/suppress quasi-identifiers in the de-identified output.
- Version schemas and transformation rules.

### Data quality disposition

| Severity | Behavior | Example |
|---|---|---|
| Critical | Fail batch; do not promote | duplicate claim business key after survivorship |
| Error | Quarantine invalid rows; fail if threshold exceeded | claim line without claim header |
| Warning | Promote and alert | unusual daily volume change |
| Info | Record metric | optional-field completeness |

Pandera/Pytest will validate generator outputs and small dataframes. Spark-native assertion modules will perform scalable checks. Great Expectations may be added only if it reduces rather than duplicates the quality interface.

## 7. Snowflake Gold model

### Loading pattern

1. ADF starts the Gold load only after an explicit Silver batch succeeds.
2. Snowflake uses an Azure storage integration and external stage over approved de-identified Silver paths.
3. `COPY INTO` loads batch-scoped transient staging tables with file metadata.
4. Validation reconciles files, row counts, sums, and schema.
5. A transactional SQL stored procedure merges dimensions and facts.
6. The batch is recorded in `load_audit`; reruns are idempotent.

### Dimensions

- `dim_member` — SCD Type 2 demographic and geography bands; direct identifiers excluded from broad analytics roles.
- `dim_provider` — SCD Type 2 specialty and affiliation.
- `dim_facility` — SCD Type 2 organization/location attributes.
- `dim_plan` — SCD Type 2 product and line of business.
- `dim_diagnosis` — code-system reference.
- `dim_procedure` — synthetic/public code reference.
- `dim_date` — calendar, fiscal, month, quarter, and year attributes.
- Degenerate dimensions: claim number and authorization number retained on facts as tokenized business identifiers.

### Facts and grains

- `fact_claim` — one row per claim version selected as current/analytically valid.
- `fact_claim_line` — one row per claim line; main financial analysis table.
- `fact_encounter` — one row per clinical encounter.
- `fact_observation` — one row per lab/vital observation.
- `fact_authorization` — one row per authorization request.
- `fact_payment` — one row per payment/remittance transaction.
- `bridge_claim_diagnosis` — many-to-many claim/diagnosis relationship.

Every fact declares its grain in SQL comments and documentation. Unknown dimension members use a standard surrogate key. Late-arriving dimensions are inferred and repaired on a later run.

### Initial business marts

- Claims cost and utilization by month, plan, provider specialty, and service category.
- Denial and adjustment trends.
- Authorization turnaround and approval rate.
- Member enrollment and utilization trends.
- Clinical encounter and observation trends using de-identified members.

## 8. Security and governance

- Azure resources use managed identities where supported.
- Secrets reside in Key Vault and are referenced at runtime; secrets never enter Git or Terraform variables committed to the repository.
- Terraform state uses a remote encrypted backend for cloud runs and is treated as sensitive.
- ADLS uses hierarchical namespace, RBAC, ACLs, secure transfer, and public access disabled where the selected Azure account/features permit.
- Databricks uses Unity Catalog grants and groups such as `platform_admin`, `data_engineer`, `phi_restricted`, `analytics_deidentified`, and `auditor`.
- Sensitive columns carry tags such as `DIRECT_IDENTIFIER`, `PHI`, `QUASI_IDENTIFIER`, `FINANCIAL`, and `NON_SENSITIVE`.
- Snowflake uses least-privilege roles, separate ingestion/transform/analytics warehouses, masking policies, row-access policies where justified, access history, query tags, and auto-suspend.
- Logs must not contain raw names, email addresses, phone numbers, identifiers, or full record payloads.
- CI includes secret scanning, dependency scanning, Terraform lint/security checks, SQL linting, and Python tests.
- The repository includes a data classification matrix, data contracts, lineage documentation, retention policy, threat model, and access-control test cases.

## 9. Observability and operations

### Metrics

- ADF: run status, duration, queue time, rows/bytes copied, retries, throughput, watermark lag.
- Landing/Bronze: file count, checksum, source-to-target counts, schema hash, duplicate batch detection.
- Silver: input/output/quarantine counts, DQ pass rate, null rates, duplicates, late arrivals, Delta operation metrics.
- Snowflake: files loaded, rows merged, reconciliation totals, credits, warehouse queue time, query latency, access-denied events.
- End to end: data freshness SLA, pipeline latency, success rate, recovery time, and cost per successful batch.

### Alerting

ADF and Databricks diagnostic logs flow to Log Analytics where supported. Azure Monitor alerts cover failed runs, freshness breach, abnormal volume, repeated retries, and budget thresholds. Snowflake resource monitors cap/alert on credit use. Each actionable alert links to a Markdown runbook.

### Health monitor

A scheduled health job checks:

- latest successful batch per table;
- watermarks that stopped advancing;
- orphaned/incomplete Landing batches;
- failed or long-running Databricks jobs;
- quarantined-row thresholds;
- unreconciled Snowflake loads;
- source-to-Gold freshness and financial totals.

It writes a compact `pipeline_health` table and produces a portfolio dashboard/export without exposing record-level data.

## 10. Failure, replay, and backfill scenarios

| Scenario | Required behavior |
|---|---|
| Source connection failure | Retry with backoff; do not advance watermark; downstream stays blocked |
| Partial Landing write | Keep under temporary/incomplete path; no successful manifest; safe cleanup |
| Duplicate ADF invocation | Existing batch/run id makes processing idempotent |
| Same timestamp on many rows | Composite timestamp + primary-key watermark prevents loss |
| Source update during extract | Fixed high watermark bounds the batch |
| Schema-compatible new nullable column | Record drift; accept only under configured evolution policy |
| Breaking schema/type change | Quarantine/fail and require contract version update |
| Bronze/Silver Spark failure | Preserve inputs; rerun exact batch after correction |
| DQ critical failure | Stop promotion and write sanitized evidence to audit tables |
| Late-arriving claim/diagnosis | Reprocess affected business keys/partitions and update facts idempotently |
| Claim reversal/replacement | Preserve audit history; derive current analytical state via explicit rules |
| Snowflake COPY failure | Do not merge staging into Gold; rerun only missing/failed files |
| Gold merge failure | Transaction rollback; prior Gold remains available |
| Credential rotation | Key Vault/secret scope update without code change |
| Accidental expensive compute | Cluster policies, auto-termination, budgets, resource monitors, and destroy workflow |

### Backfill interface

A backfill is requested with:

```text
source/table OR domain
start/end business date
optional business-key range
reason and requested_by
code/data-contract version
mode: dry-run | execute
```

The orchestrator resolves immutable Landing manifests, estimates scope, prevents overlap with conflicting live loads, processes into batch-scoped temporary outputs, validates reconciliations, and promotes only after success. Watermarks for normal incremental ingestion are not moved backward.

## 11. Infrastructure as code and CI/CD

### Terraform stacks/modules

- `bootstrap`: resource group, remote state storage, budget/action group.
- `azure_core`: ADLS, Key Vault, Log Analytics, ADF, optional source databases.
- `databricks`: workspace integration, cluster policy, jobs, Unity Catalog objects where account permissions permit.
- `snowflake`: databases, schemas, roles, warehouses, resource monitors, storage integration, file formats, and stages.
- `monitoring`: diagnostics, queries, alerts, and workbooks.

Environments use separate variable files and state. `dev` is the implementation default; `demo` is an ephemeral full deployment. Production is documentation and validated Terraform structure, not a costly standing environment.

### CI stages

1. Format/lint: Ruff, Black, SQLFluff, Terraform fmt/validate/tflint, YAML checks.
2. Security: secret scan, Checkov/tfsec-equivalent checks, dependency audit.
3. Unit tests: generators, tokenization, watermark predicates, transforms, DQ rules, SCD logic.
4. Integration tests: Docker source databases and local Spark/Delta.
5. Contract tests: source-to-Bronze and Silver-to-Gold schemas.
6. Terraform plan on pull requests; apply only through a protected manual demo workflow.
7. Deploy ADF/Databricks/Snowflake artifacts, run smoke pipeline, publish test evidence.
8. Manual or scheduled teardown workflow for all billable demo resources.

## 12. Proposed repository structure

```text
.
├── README.md
├── PROJECT_PLAN.md
├── Makefile
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── architecture/
│   ├── data-dictionary/
│   ├── contracts/
│   ├── runbooks/
│   ├── security/
│   └── decisions/
├── infra/
│   ├── bootstrap/
│   ├── modules/
│   └── environments/{local,dev,demo}/
├── synthetic_data/
│   ├── generators/
│   ├── scenarios/
│   ├── loaders/
│   └── config/
├── databases/
│   ├── postgres/{ddl,seeds}/
│   └── sqlserver/{ddl,seeds}/
├── orchestration/adf/
├── databricks/
│   ├── src/{bronze,silver,quality,governance,common}/
│   ├── resources/
│   └── tests/
├── snowflake/
│   ├── migrations/
│   ├── models/{staging,dimensions,facts,marts}/
│   ├── policies/
│   └── tests/
├── monitoring/{azure,snowflake,queries,dashboards}/
├── scripts/
└── tests/{unit,integration,contracts,e2e}/
```

The main deep modules and seams will be:

- `generate_dataset(config, seed) -> manifests`
- `apply_change_scenario(scenario, batch_id) -> manifests`
- `ingest_batch(table_config, watermark_window) -> batch_manifest`
- `promote_bronze(batch_manifest) -> promotion_result`
- `build_silver(domain, batch_ids) -> quality_and_promotion_result`
- `load_gold(silver_batch) -> reconciliation_result`

Cloud, Docker, and in-memory adapters will sit behind those interfaces where behavior genuinely varies.

## 13. Step-by-step delivery roadmap

### Phase 0 — Foundation and decisions

**Deliver:** README, architecture diagram, naming/tagging standard, ADRs, threat model, cost guardrails, Python project, Makefile, pre-commit, CI skeleton.

**Exit:** local quality pipeline passes; no cloud resource exists yet.

### Phase 1 — Source systems and synthetic data

**Deliver:** Docker databases, DDL, deterministic generators, bulk loaders, all three volume profiles, change scenarios, data dictionary, and source DQ tests.

**Exit:** one command creates databases and loads a valid tiny/small dataset; mutation batches are repeatable; referential/financial constraints pass.

### Phase 2 — Terraform Azure foundation

**Deliver:** remote state bootstrap, resource group, ADLS, Key Vault, Log Analytics, ADF, budgets, optional PostgreSQL/Azure SQL sources, teardown command.

**Exit:** `terraform plan` is clean, smoke tests can access storage through intended identities, and estimated/demo cost is documented.

### Phase 3 — Metadata-driven ADF Landing ingestion

**Deliver:** control schema, linked services, datasets, parameterized master/child pipelines, full/incremental extraction, composite watermarks, manifests, retry/failure paths.

**Exit:** at least one full-load table and two incremental high-volume tables ingest from each source; reruns do not duplicate; failed loads do not advance state.

### Phase 4 — Databricks Bronze + Unity Catalog

**Deliver:** workspace/UC configuration, storage credentials/external locations, job cluster policy, Landing-to-Bronze Spark jobs, schema drift handling, quarantine, audit metrics.

**Exit:** exact batch replay is deterministic and duplicate execution is a no-op.

### Phase 5 — Silver domain pipelines and privacy

**Deliver:** claims, member, provider, and clinical transformations; standardized models; survivorship; HMAC tokenization; restricted/de-identified outputs; DQ gates; data contracts.

**Exit:** critical injected defects block promotion, recoverable defects quarantine correctly, and tests prove raw identifiers are absent from de-identified outputs and logs.

### Phase 6 — Snowflake Gold warehouse

**Deliver:** Terraform Snowflake objects, external stage, staging/COPY, SCD2 dimensions, facts, bridge, marts, masking policies, row access where useful, reconciliation and SQL tests.

**Exit:** a rerun is idempotent; point-in-time dimension joins work; financial totals reconcile from source through Gold.

### Phase 7 — End-to-end orchestration and backfill

**Deliver:** ADF-triggered Databricks and Snowflake steps, dependency gates, backfill request workflow, dry-run scope estimate, concurrent-run protection, replay tests.

**Exit:** scheduled incremental, failed-batch recovery, and bounded historical backfill all pass documented demonstrations.

### Phase 8 — Observability and operations

**Deliver:** health monitor, Log Analytics queries, Azure alerts, Snowflake resource monitor, operational dashboard/export, alert-linked runbooks, SLO definitions.

**Exit:** test failures produce actionable sanitized alerts and every major scenario has a runbook.

### Phase 9 — Portfolio packaging

**Deliver:** polished README, screenshots, architecture/data-flow diagrams, sample dashboard, cost report, demo script, trade-off narrative, lineage evidence, and teardown proof.

**Exit:** a reviewer can understand the system, run the local path, and reproduce a controlled cloud demo without proprietary data.

## 14. Test strategy

- **Unit:** pure generator rules, watermark boundaries, token stability, normalization, survivorship, financial rules, and SCD2 state transitions.
- **Property-based:** dates, amounts, uniqueness, enrollment coverage, and idempotency over generated cases.
- **Database integration:** DDL, bulk loading, extraction predicates, same-timestamp records, updates, and deletes against both engines.
- **Spark integration:** small Delta tables, MERGE behavior, schema drift, quarantine, and batch replay.
- **Snowflake SQL:** uniqueness, not-null, accepted values, relationships, SCD non-overlap, fact grain, and reconciliation.
- **Contract:** versioned schemas and compatibility rules between each layer.
- **Security:** denied access by role, masking output, no secrets in state/logs/artifacts, no direct identifiers in de-identified tables.
- **Resilience:** partial writes, retries, duplicate trigger, source outage, Spark failure, Snowflake failure, and restart.
- **Performance:** small/medium generation throughput, copy throughput, Spark shuffle/partition behavior, Snowflake query timing and credits.
- **End to end:** initial full load, two incremental batches, late arrival, reversal, critical DQ failure/recovery, and historical backfill.

## 15. Cost-control plan

- Put every resource in a dedicated resource group with mandatory owner/project/expiry tags.
- Configure Azure budget alerts before provisioning compute.
- Default to local Docker for daily development.
- Use the smallest viable burstable/serverless source databases and stop/delete them when not needed.
- Use Databricks job clusters with auto-termination and restrictive cluster policies; never leave an all-purpose cluster running.
- Keep datasets modest in cloud; medium scale can be demonstrated selectively.
- Apply ADLS lifecycle policies only after confirming replay requirements.
- Configure Snowflake X-Small warehouses, 60-second auto-suspend, statement timeouts, and resource monitors.
- Provide `make cloud-down` and a GitHub manual teardown workflow.
- Document that Azure and Snowflake offers, free quotas, regional availability, and prices change; check the calculators immediately before deployment.

## 16. Key decisions still requiring confirmation before cloud deployment

These do not block Phase 0 or Phase 1:

1. Azure subscription/trial status, tenant permissions, and allowed region.
2. Whether the subscription can create Azure Databricks and Unity Catalog resources.
3. Snowflake trial account availability and Azure region pairing.
4. Whether Azure SQL Database is acceptable as the cloud SQL Server-compatible source (recommended) or an exact SQL Server instance is mandatory.
5. Whether Power BI should be a working deliverable or documented consumption endpoint.

## 17. Recommended first implementation increment

Start with **Phase 0 and Phase 1 only**. This creates a valuable, testable vertical foundation with no cloud spend:

1. scaffold Python, Docker, tests, linting, and Make targets;
2. define source DDL and data contracts;
3. implement deterministic Tiny generation first;
4. bulk-load PostgreSQL and SQL Server;
5. implement one mutation batch and validate composite-watermark extraction;
6. scale the same generator to Small and Medium profiles;
7. only then provision Azure resources.

This order prevents expensive cloud debugging of basic schema and data-generation problems.

## 18. Reference links reviewed for planning

- Elevance Health public company overview: <https://www.elevancehealth.com/who-we-are>
- Azure free account/purchase options: <https://azure.microsoft.com/en-us/free/>
- Azure Data Factory pricing: <https://azure.microsoft.com/en-us/pricing/details/data-factory/data-pipeline/>
- Azure Database for PostgreSQL pricing: <https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/>
- Unity Catalog on Azure Databricks: <https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/>
- ADF incremental copy/watermark pattern: <https://learn.microsoft.com/en-us/azure/data-factory/tutorial-incremental-copy-overview>
- Snowflake loading from Azure: <https://docs.snowflake.com/en/user-guide/data-load-azure>

Review date: 2026-09-05. Product features, free offers, and pricing must be revalidated at deployment time.
