from healthcare_pipeline.config import RuntimeConfig


def test_runtime_config_uses_safe_non_secret_defaults(monkeypatch):
    monkeypatch.delenv("PIPELINE_ENV", raising=False)
    monkeypatch.delenv("AZURE_LOCATION", raising=False)
    monkeypatch.delenv("DATA_PROFILE", raising=False)

    assert RuntimeConfig.from_environment() == RuntimeConfig("local", "eastus", "tiny")
