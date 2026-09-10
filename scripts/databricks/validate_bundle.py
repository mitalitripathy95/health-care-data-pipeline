#!/usr/bin/env python3
"""Static, credential-free validation for the Databricks Asset Bundle."""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FILES = (
    "databricks.yml",
    "resources/jobs.yml",
    "resources/permissions.yml",
    "pyproject.toml",
    "src/healthcare_bronze/main.py",
    "src/healthcare_silver/main.py",
)
REQUIRED_VARIABLES = {
    "workspace_host",
    "catalog_name",
    "bronze_schema",
    "restricted_schema",
    "deidentified_schema",
    "quarantine_schema",
    "manifest_path",
    "control_jdbc_url",
    "secret_scope",
    "hmac_key_name",
    "token_version",
    "transform_version",
    "event_watermark",
    "node_type_id",
    "spark_version",
}
REQUIRED_PARAMETERS = {
    "batch_id",
    "source_filter",
    "manifest_path",
    "catalog_name",
    "bronze_schema",
    "quarantine_schema",
    "control_jdbc_url",
    "secret_scope",
}
SILVER_PARAMETERS = {
    "batch_id",
    "source_filter",
    "catalog_name",
    "bronze_schema",
    "restricted_schema",
    "deidentified_schema",
    "quarantine_schema",
    "control_jdbc_url",
    "secret_scope",
    "hmac_key_name",
    "token_version",
    "transform_version",
    "event_watermark",
}
EXPECTED_WHEEL_PATH = "./dist/*.whl"
SECRET_PATTERN = re.compile(
    r"(?im)^\s*(password|client_secret|access_token|private_key|hmac_key)\s*[:=]\s*[\"']?(?!\$\{|\{\{|$)([^\s#]+)"
)


class BundleValidationError(ValueError):
    """Raised when the bundle violates a required Phase 4 safety contract."""


@dataclass(frozen=True)
class BundleReport:
    bundle_name: str
    job_name: str
    single_node: bool


def _read_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise BundleValidationError(f"YAML root must be an object: {path}")
    return document


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleValidationError(message)


def _scan_plaintext_secrets(paths: Iterable[Path]) -> None:
    for path in paths:
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".whl"}:
            continue
        if path.is_file() and SECRET_PATTERN.search(
            path.read_text(encoding="utf-8", errors="ignore")
        ):
            raise BundleValidationError(f"Possible plaintext secret in {path}")


def validate_bundle(
    project_root: Path | str = ".", files: tuple[str, ...] | None = None
) -> BundleReport:
    """Validate bundle shape and Azure-trial controls without contacting Databricks."""
    root = Path(project_root).resolve()
    bundle_root = root / "databricks"
    required = files or REQUIRED_FILES
    paths = [bundle_root / relative for relative in required]
    missing = [str(path) for path in paths if not path.is_file()]
    _require(not missing, f"Missing Databricks bundle files: {', '.join(missing)}")
    _scan_plaintext_secrets(path for path in bundle_root.rglob("*") if path.is_file())

    bundle = _read_yaml(bundle_root / "databricks.yml")
    jobs_doc = _read_yaml(bundle_root / "resources" / "jobs.yml")
    permissions_doc = _read_yaml(bundle_root / "resources" / "permissions.yml")

    bundle_name = bundle.get("bundle", {}).get("name")
    _require(bundle_name == "healthcare-data-pipeline", "Unexpected bundle name")
    _require(
        REQUIRED_VARIABLES <= set(bundle.get("variables", {})), "Missing required bundle variables"
    )
    artifacts = bundle.get("artifacts", {})
    _require(
        any(item.get("type") == "whl" for item in artifacts.values()), "Wheel artifact is required"
    )

    jobs = jobs_doc.get("resources", {}).get("jobs", {})
    _require("wf_bronze_ingestion" in jobs, "wf_bronze_ingestion job is required")
    _require("wf_silver_transformation" in jobs, "wf_silver_transformation job is required")
    job = jobs["wf_bronze_ingestion"]
    _require(job.get("name") == "wf_bronze_ingestion", "Unexpected workflow name")
    _require(job.get("max_concurrent_runs") == 1, "max_concurrent_runs must equal 1")
    schedule = job.get("schedule")
    _require(
        not schedule or schedule.get("pause_status") == "PAUSED",
        "Job schedule must be absent or paused",
    )
    parameters = {item.get("name") for item in job.get("parameters", [])}
    _require(REQUIRED_PARAMETERS <= parameters, "Missing required job parameters")

    clusters = job.get("job_clusters", [])
    _require(len(clusters) == 1, "Exactly one ephemeral job cluster is required")
    cluster = clusters[0].get("new_cluster", {})
    _require(cluster.get("num_workers") in (0, 1), "Trial-safe compute requires zero or one worker")
    _require(
        1 <= int(cluster.get("autotermination_minutes", 0)) <= 30,
        "Auto-termination must be 1-30 minutes",
    )
    _require(
        cluster.get("runtime_engine") == "STANDARD",
        "Photon must remain disabled for the trial workload",
    )
    single_node = cluster.get("num_workers") == 0
    if single_node:
        _require(
            cluster.get("spark_conf", {}).get("spark.databricks.cluster.profile") == "singleNode",
            "Zero-worker compute must use the singleNode profile",
        )

    tasks = job.get("tasks", [])
    _require(len(tasks) == 1, "Bronze workflow must contain exactly one task")
    task = tasks[0]
    wheel_task = task.get("python_wheel_task", {})
    _require(wheel_task.get("package_name") == "healthcare_bronze", "Unexpected wheel package")
    _require(wheel_task.get("entry_point") == "healthcare-bronze", "Unexpected wheel entry point")
    wheel_paths = [library.get("whl") for library in task.get("libraries", []) if "whl" in library]
    _require(
        wheel_paths == [EXPECTED_WHEEL_PATH],
        f"Wheel library must use bundle artifact path {EXPECTED_WHEEL_PATH}",
    )
    _require(
        task.get("job_cluster_key") == clusters[0].get("job_cluster_key"),
        "Task must use the ephemeral job cluster",
    )

    permissions = (
        permissions_doc.get("resources", {})
        .get("jobs", {})
        .get("wf_bronze_ingestion", {})
        .get("permissions", [])
    )
    _require(bool(permissions), "Least-privilege job permissions are required")
    _require(
        all(item.get("level") != "CAN_MANAGE" for item in permissions),
        "Do not grant broad CAN_MANAGE permission",
    )

    silver = jobs["wf_silver_transformation"]
    _require(silver.get("name") == "wf_silver_transformation", "Unexpected Silver workflow name")
    _require(silver.get("max_concurrent_runs") == 1, "Silver max_concurrent_runs must equal 1")
    _require(
        not silver.get("schedule") or silver["schedule"].get("pause_status") == "PAUSED",
        "Silver job schedule must be absent or paused",
    )
    silver_parameters = {item.get("name") for item in silver.get("parameters", [])}
    _require(SILVER_PARAMETERS <= silver_parameters, "Missing required Silver job parameters")
    silver_clusters = silver.get("job_clusters", [])
    _require(len(silver_clusters) == 1, "Exactly one ephemeral Silver job cluster is required")
    silver_cluster = silver_clusters[0].get("new_cluster", {})
    _require(silver_cluster.get("num_workers") == 0, "Silver must use single-node compute")
    _require(silver_cluster.get("runtime_engine") == "STANDARD", "Photon must remain disabled")
    _require(
        1 <= int(silver_cluster.get("autotermination_minutes", 0)) <= 30,
        "Silver auto-termination must be 1-30 minutes",
    )
    _require(
        silver_cluster.get("spark_conf", {}).get("spark.databricks.cluster.profile")
        == "singleNode",
        "Silver zero-worker compute must use the singleNode profile",
    )
    silver_tasks = silver.get("tasks", [])
    _require(len(silver_tasks) == 1, "Silver workflow must contain exactly one task")
    silver_task = silver_tasks[0]
    silver_wheel = silver_task.get("python_wheel_task", {})
    _require(
        silver_wheel.get("package_name") == "healthcare_bronze",
        "Unexpected Silver wheel package",
    )
    _require(
        silver_wheel.get("entry_point") == "healthcare-silver",
        "Unexpected Silver wheel entry point",
    )
    _require(
        [item.get("whl") for item in silver_task.get("libraries", []) if "whl" in item]
        == [EXPECTED_WHEEL_PATH],
        f"Silver wheel library must use bundle artifact path {EXPECTED_WHEEL_PATH}",
    )
    silver_permission = (
        permissions_doc.get("resources", {})
        .get("jobs", {})
        .get("wf_silver_transformation", {})
        .get("permissions", [])
    )
    _require(bool(silver_permission), "Least-privilege Silver job permissions are required")
    _require(
        all(item.get("level") != "CAN_MANAGE" for item in silver_permission),
        "Do not grant broad CAN_MANAGE permission",
    )

    pyproject = (bundle_root / "pyproject.toml").read_text(encoding="utf-8")
    _require(
        'healthcare-bronze = "healthcare_bronze.main:main"' in pyproject,
        "Wheel entry point is missing",
    )
    _require(
        'healthcare-silver = "healthcare_silver.main:main"' in pyproject,
        "Silver wheel entry point is missing",
    )
    return BundleReport(bundle_name=bundle_name, job_name=job["name"], single_node=single_node)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()
    report = validate_bundle(args.project_root)
    print(f"Validated {report.bundle_name}: {report.job_name} (single_node={report.single_node})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
