from healthcare_bronze.config import BronzeConfig
from healthcare_bronze.main import parser, should_publish_dependencies


def test_cli_exposes_bundle_parameters():
    args = parser().parse_args(
        [
            "--batch-id",
            "b1",
            "--source-filter",
            "member_claims",
            "--manifest-path",
            "abfss://control",
            "--catalog-name",
            "catalog",
        ]
    )
    assert args.batch_id == "b1"
    assert args.source_filter == "member_claims"
    assert args.catalog_name == "catalog"


def test_dependency_publication_requires_all_results_to_succeed():
    config = BronzeConfig(batch_id="b1", control_jdbc_url="jdbc:sqlserver://control")
    assert should_publish_dependencies(
        [{"status": "SUCCEEDED"}, {"status": "SKIPPED_ALREADY_SUCCEEDED"}], config
    )
    assert not should_publish_dependencies([{"status": "SUCCEEDED"}, {"status": "FAILED"}], config)
    assert not should_publish_dependencies([], config)
