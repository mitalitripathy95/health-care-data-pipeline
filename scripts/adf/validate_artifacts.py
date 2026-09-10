#!/usr/bin/env python3
"""Static repository checks for the Phase 3 Azure Data Factory artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ADF_TERRAFORM = Path("infra/modules/compute/adf.tf")
ADF_TEMPLATES = (
    Path("infra/modules/compute/adf/validate_landing.activities.json.tftpl"),
    Path("infra/modules/compute/adf/ingest_table.activities.json.tftpl"),
)
CONTROL_DDL = Path("database/azure_sql/ddl/002_control_schema.sql")
METADATA_SEED = Path("database/azure_sql/seed/001_ingestion_config.sql")

LINKED_SERVICES = {
    "ls_key_vault",
    "ls_postgresql_clinical",
    "ls_azure_sql_payer",
    "ls_adls_lake",
}
DATASETS = {"ds_postgresql_table", "ds_azure_sql_table", "ds_bronze_parquet"}
PIPELINES = {"pl_validate_landing", "pl_ingest_table", "pl_master_ingestion"}
CONTROL_TABLES = {
    "source_system",
    "ingestion_config",
    "pipeline_run",
    "table_run",
    "watermark_state",
    "ingestion_lock",
    "batch_manifest",
    "dq_result",
    "job_dependency",
    "reprocess_request",
    "reconciliation_result",
    "pipeline_health",
}
CONTROL_PROCEDURES = {
    "usp_begin_pipeline_run",
    "usp_finish_pipeline_run",
    "usp_begin_table_run",
    "usp_publish_table_run",
    "usp_fail_table_run",
    "usp_publish_job_dependency",
}
EXPECTED_FULL_TABLES = {("clinical", "medications"), ("payer", "plans")}
DEPENDENCY_PARAMETERS = {"batch_id", "upstream_job", "downstream_job", "status"}


def _read(root: Path, relative_path: Path, errors: list[str]) -> str:
    path = root / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Missing or unreadable required artifact {relative_path}: {exc}")
        return ""


def _require_names(text: str, names: set[str], kind: str, errors: list[str]) -> None:
    missing = sorted(name for name in names if name not in text)
    if missing:
        errors.append(f"Missing required {kind}: {', '.join(missing)}")


def _metadata_rows(seed: str) -> list[tuple[str, str, str, str, str, str | None]]:
    row_pattern = re.compile(
        r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*"
        r"'(FULL|INCREMENTAL)'\s*,\s*'([^']+)'\s*,\s*(NULL|'[^']+')\s*,",
        re.IGNORECASE,
    )
    rows = []
    for source, schema, table, load_type, primary_key, watermark_token in row_pattern.findall(seed):
        watermark = None if watermark_token.upper() == "NULL" else watermark_token.strip("'")
        rows.append((source, schema, table, load_type.upper(), primary_key, watermark))
    return rows


def _procedure_parameters(ddl: str, procedure_name: str) -> set[str]:
    match = re.search(
        rf"CREATE\s+OR\s+ALTER\s+PROCEDURE\s+control\.{re.escape(procedure_name)}\b(.*?)\bAS\b",
        ddl,
        re.IGNORECASE | re.DOTALL,
    )
    return set() if not match else set(re.findall(r"@(\w+)", match.group(1)))


def _hcl_stored_procedure_parameters(adf: str, procedure_name: str) -> set[str]:
    procedure_at = adf.find(f'storedProcedureName = "control.{procedure_name}"')
    if procedure_at < 0:
        return set()
    block_at = adf.find("storedProcedureParameters = {", procedure_at)
    if block_at < 0:
        return set()
    start = adf.find("{", block_at)
    depth = 0
    end = start
    for end in range(start, len(adf)):
        if adf[end] == "{":
            depth += 1
        elif adf[end] == "}":
            depth -= 1
            if depth == 0:
                break
    block = adf[start + 1 : end]
    return set(re.findall(r"(?m)^\s*([a-zA-Z_]\w*)\s*=", block))


def validate_repository(root: Path) -> list[str]:
    """Return human-readable Phase 3 artifact validation errors for *root*."""
    root = root.resolve()
    errors: list[str] = []
    adf = _read(root, ADF_TERRAFORM, errors)
    templates = {path: _read(root, path, errors) for path in ADF_TEMPLATES}
    ddl = _read(root, CONTROL_DDL, errors)
    seed = _read(root, METADATA_SEED, errors)
    pipeline_text = "\n".join([adf, *templates.values()])

    _require_names(adf, LINKED_SERVICES, "ADF linked services", errors)
    _require_names(adf, DATASETS, "ADF datasets", errors)
    _require_names(adf, PIPELINES, "ADF pipelines", errors)

    if not re.search(r"variable\s+\"enable_adf_schedule_trigger\"[\s\S]*?default\s*=\s*false", adf):
        # The default is declared in variables.tf, so inspect it as part of this
        # repository-level rule.
        variables = _read(root, Path("infra/modules/compute/variables.tf"), errors)
        if not re.search(
            r"variable\s+\"enable_adf_schedule_trigger\"[\s\S]*?default\s*=\s*false",
            variables,
        ):
            errors.append("ADF schedule trigger must be disabled by default.")
    if "use_managed_identity = true" not in adf:
        errors.append("ADLS linked service must use the ADF managed identity.")

    for resource in ("postgresql", "azure_sql"):
        resource_match = re.search(
            rf'resource "azurerm_data_factory_linked_custom_service" "{resource}" \{{(.*?)\n\}}',
            adf,
            re.DOTALL,
        )
        block = "" if resource_match is None else resource_match.group(1)
        if "AzureKeyVaultSecret" not in block or "secretName" not in block:
            errors.append(
                f"ADF {resource} source linked service must use a Key Vault secret reference."
            )

    secret_patterns = (
        r"(?i)AccountKey\s*=",
        r"(?i)(?:password|pwd|client_secret)\s*[:=]\s*[\"'][^\"'@${}]+[\"']",
        r"(?i)connectionString\s*=\s*[\"'][^\"']+(?:Server|Host|Data Source)\s*=",
    )
    for pattern in secret_patterns:
        if re.search(pattern, pipeline_text):
            errors.append(
                "ADF artifacts contain a possible literal credential or connection string."
            )
            break

    if "/batch_id=" not in adf or "/run_id=" not in adf:
        errors.append("Immutable Bronze path must contain batch_id and run_id partitions.")

    rows = _metadata_rows(seed)
    unique_tables = {(schema.lower(), table.lower()) for _, schema, table, *_ in rows}
    if len(rows) != 19 or len(unique_tables) != 19:
        errors.append(
            f"Metadata seed must contain exactly 19 unique source tables; found "
            f"{len(rows)} rows and {len(unique_tables)} unique tables."
        )
    full_tables = {
        (schema.lower(), table.lower())
        for _, schema, table, load_type, *_ in rows
        if load_type == "FULL"
    }
    if full_tables != EXPECTED_FULL_TABLES:
        errors.append(
            "FULL metadata tables must be exactly clinical.medications and payer.plans; found "
            + ", ".join(f"{schema}.{table}" for schema, table in sorted(full_tables))
        )
    missing_watermarks = [
        f"{schema}.{table}"
        for _, schema, table, load_type, _, watermark in rows
        if load_type == "INCREMENTAL" and not watermark
    ]
    if missing_watermarks:
        errors.append(
            "Incremental metadata rows lack watermark columns: " + ", ".join(missing_watermarks)
        )

    for table in sorted(CONTROL_TABLES):
        if not re.search(rf"control\.{re.escape(table)}\b", ddl, re.IGNORECASE):
            errors.append(f"Missing required control table: control.{table}")
    for procedure in sorted(CONTROL_PROCEDURES):
        if not re.search(
            rf"CREATE\s+OR\s+ALTER\s+PROCEDURE\s+control\.{re.escape(procedure)}\b",
            ddl,
            re.IGNORECASE,
        ):
            errors.append(f"Missing required control procedure: control.{procedure}")

    dynamic_type = re.compile(r'"type"\s*:\s*"@if\s*\(', re.IGNORECASE)
    dynamic_reference = re.compile(r'"referenceName"\s*:\s*"@if\s*\(', re.IGNORECASE)
    for path, text in templates.items():
        if dynamic_type.search(text):
            errors.append(
                f"Pipeline artifact {path} dynamically selects a JSON type; use static branches."
            )
        if dynamic_reference.search(text):
            errors.append(
                f"Pipeline artifact {path} dynamically selects referenceName; "
                "use static connector branches."
            )

    ingest = templates.get(ADF_TEMPLATES[1], "")
    validation_at = ingest.find('"name": "Validate immutable landing"')
    publication_at = ingest.find('"name": "Publish table run"')
    if validation_at < 0 or publication_at < 0 or validation_at >= publication_at:
        errors.append("Landing validation must be defined before table-run publication.")
    if "control.usp_fail_table_run" not in ingest:
        errors.append("Table pipeline must wire control.usp_fail_table_run failure handling.")
    backfill_expression = (
        "@and(empty(pipeline().parameters.backfill_start), "
        "empty(pipeline().parameters.backfill_end))"
    )
    if '"advance_watermark"' not in ingest or backfill_expression not in ingest:
        errors.append("Table publication must disable watermark advancement for bounded backfills.")

    success_at = adf.find('name      = "Mark pipeline succeeded"')
    dependency_at = adf.find('name      = "Publish downstream dependency ready"')
    if (
        success_at < 0
        or dependency_at < success_at
        or (
            'activity = "Mark pipeline succeeded", dependencyConditions = ["Succeeded"]'
            not in adf[dependency_at : dependency_at + 800]
        )
    ):
        errors.append(
            "Downstream dependency readiness must be published only after master success."
        )

    sql_parameters = _procedure_parameters(ddl, "usp_publish_job_dependency")
    hcl_parameters = _hcl_stored_procedure_parameters(adf, "usp_publish_job_dependency")
    if sql_parameters != DEPENDENCY_PARAMETERS:
        errors.append(
            "control.usp_publish_job_dependency SQL parameters must be: "
            + ", ".join(sorted(DEPENDENCY_PARAMETERS))
        )
    if hcl_parameters != DEPENDENCY_PARAMETERS:
        errors.append(
            "ADF usp_publish_job_dependency parameter names do not match SQL; found: "
            + ", ".join(sorted(hcl_parameters))
        )

    return errors


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=_default_root())
    args = parser.parse_args(argv)
    errors = validate_repository(args.root)
    if errors:
        print(f"Phase 3 ADF artifact validation failed ({len(errors)} error(s)):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Phase 3 ADF artifact validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
