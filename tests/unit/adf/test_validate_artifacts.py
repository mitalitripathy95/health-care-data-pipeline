from __future__ import annotations

import shutil
from pathlib import Path

from scripts.adf.validate_artifacts import validate_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RELEVANT_FILES = (
    "infra/modules/compute/adf.tf",
    "infra/modules/compute/variables.tf",
    "infra/modules/compute/adf/validate_landing.activities.json.tftpl",
    "infra/modules/compute/adf/ingest_table.activities.json.tftpl",
    "database/azure_sql/ddl/002_control_schema.sql",
    "database/azure_sql/seed/001_ingestion_config.sql",
)


def _fixture_repository(tmp_path: Path) -> Path:
    for relative in RELEVANT_FILES:
        source = REPOSITORY_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def test_real_repository_passes() -> None:
    assert validate_repository(REPOSITORY_ROOT) == []


def test_dynamic_reference_name_is_rejected(tmp_path: Path) -> None:
    root = _fixture_repository(tmp_path)
    template = root / "infra/modules/compute/adf/ingest_table.activities.json.tftpl"
    text = template.read_text(encoding="utf-8")
    template.write_text(
        text.replace(
            '"referenceName": "${azure_sql_dataset}"',
            '"referenceName": "@if(true, a, b)"',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_repository(root)

    assert any("dynamically selects referenceName" in error for error in errors)


def test_missing_control_procedure_is_rejected(tmp_path: Path) -> None:
    root = _fixture_repository(tmp_path)
    ddl = root / "database/azure_sql/ddl/002_control_schema.sql"
    ddl.write_text(
        ddl.read_text(encoding="utf-8").replace(
            "control.usp_fail_table_run", "control.usp_removed", 1
        ),
        encoding="utf-8",
    )

    errors = validate_repository(root)

    assert any(
        "Missing required control procedure: control.usp_fail_table_run" in error
        for error in errors
    )


def test_literal_credential_is_rejected(tmp_path: Path) -> None:
    root = _fixture_repository(tmp_path)
    adf = root / "infra/modules/compute/adf.tf"
    adf.write_text(
        adf.read_text(encoding="utf-8") + '\n# invalid fixture\npassword = "do-not-store-this"\n',
        encoding="utf-8",
    )

    errors = validate_repository(root)

    assert any("literal credential" in error for error in errors)
