from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from scripts.databricks.validate_bundle import BundleValidationError, validate_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _copy_bundle(tmp_path: Path) -> Path:
    shutil.copytree(PROJECT_ROOT / "databricks", tmp_path / "databricks")
    return tmp_path / "databricks"


def test_repository_bundle_is_trial_safe_and_complete():
    report = validate_bundle(PROJECT_ROOT)
    assert report.bundle_name == "healthcare-data-pipeline"
    assert report.job_name == "wf_bronze_ingestion"
    assert report.single_node is True


def test_validator_rejects_enabled_schedule(tmp_path):
    bundle_dir = _copy_bundle(tmp_path)
    jobs_path = bundle_dir / "resources" / "jobs.yml"
    jobs = yaml.safe_load(jobs_path.read_text(encoding="utf-8"))
    jobs["resources"]["jobs"]["wf_bronze_ingestion"]["schedule"] = {
        "quartz_cron_expression": "0 0 * * * ?",
        "timezone_id": "UTC",
        "pause_status": "UNPAUSED",
    }
    jobs_path.write_text(yaml.safe_dump(jobs), encoding="utf-8")
    with pytest.raises(BundleValidationError, match="schedule"):
        validate_bundle(tmp_path)


def test_validator_rejects_wheel_path_outside_bundle_artifact_directory(tmp_path):
    bundle_dir = _copy_bundle(tmp_path)
    jobs_path = bundle_dir / "resources" / "jobs.yml"
    jobs = yaml.safe_load(jobs_path.read_text(encoding="utf-8"))
    task = jobs["resources"]["jobs"]["wf_bronze_ingestion"]["tasks"][0]
    task["libraries"] = [{"whl": "../dist/*.whl"}]
    jobs_path.write_text(yaml.safe_dump(jobs), encoding="utf-8")
    with pytest.raises(BundleValidationError, match="bundle artifact path"):
        validate_bundle(tmp_path)


def test_validator_rejects_plaintext_credentials(tmp_path):
    bundle_dir = _copy_bundle(tmp_path)
    with (bundle_dir / "pyproject.toml").open("a", encoding="utf-8") as handle:
        handle.write("\npassword = 'secret'\n")
    with pytest.raises(BundleValidationError, match="plaintext secret"):
        validate_bundle(tmp_path)
