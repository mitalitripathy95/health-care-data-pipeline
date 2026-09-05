# ADR 0001: Cloud-first trial scope

- Status: accepted
- Date: 2026-09-05

## Decision

Run the demonstration on Azure using short-lived, Terraform-managed resources. Use Azure Database for PostgreSQL Flexible Server and Azure SQL Database as synthetic source systems, ADF for ingestion, ADLS Gen2 for immutable Bronze/Silver/Gold storage, Databricks/Spark for transformation, and Snowflake for serving.

## Consequences

The design is realistic and auditable, but several paid services must be aggressively right-sized and destroyed after the demonstration. The trial deployment uses a cost-conscious network profile; a private endpoint/VNet topology remains the production reference architecture.
