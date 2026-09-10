"""Databricks Silver wheel entry point."""

from __future__ import annotations

import argparse

from .config import SilverConfig
from .silver_ingest import run_silver


def parser():
    p = argparse.ArgumentParser(
        description="Conform Bronze data into restricted and de-identified Silver"
    )
    defaults = {
        "batch-id": "",
        "source-filter": "ALL",
        "catalog-name": "healthcare_demo",
        "bronze-schema": "bronze",
        "restricted-schema": "silver_restricted",
        "deidentified-schema": "silver_deidentified",
        "quarantine-schema": "quarantine",
        "control-jdbc-url": "",
        "secret-scope": "healthcare",
        "hmac-key-name": "silver-hmac-key",
        "token-version": "v1",
        "transform-version": "v1",
        "event-watermark": "",
    }
    for name, default in defaults.items():
        p.add_argument(f"--{name}", default=default)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    config = SilverConfig(**vars(args))
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    return run_silver(spark, config)


if __name__ == "__main__":
    main()
