locals {
  adf_enabled = var.create_data_factory

  bronze_path_expression = "@concat('bronze/raw/source=', dataset().source_system, '/schema=', dataset().source_schema, '/table=', dataset().source_table, '/batch_id=', dataset().batch_id, '/run_id=', dataset().run_id)"

  adf_activity_policy = {
    timeout                = "0.02:00:00"
    retry                  = 3
    retryIntervalInSeconds = 30
    secureInput            = false
    secureOutput           = false
  }
}

resource "azurerm_data_factory_linked_service_key_vault" "key_vault" {
  count           = local.adf_enabled ? 1 : 0
  name            = "ls_key_vault"
  data_factory_id = azurerm_data_factory.this[0].id
  key_vault_id    = var.key_vault_id
  description     = "Key Vault references only; no source credentials are stored in Terraform configuration."
  annotations     = ["phase-3", "managed-identity", "synthetic-data"]
}

resource "azurerm_data_factory_linked_custom_service" "postgresql" {
  count           = local.adf_enabled ? 1 : 0
  name            = "ls_postgresql_clinical"
  data_factory_id = azurerm_data_factory.this[0].id
  type            = "PostgreSqlV2"
  description     = "Clinical PostgreSQL source. Connection string is resolved from Key Vault at ADF runtime."
  annotations     = ["phase-3", "source", "synthetic-data"]
  type_properties_json = jsonencode({
    connectionString = {
      type = "AzureKeyVaultSecret"
      store = {
        referenceName = azurerm_data_factory_linked_service_key_vault.key_vault[0].name
        type          = "LinkedServiceReference"
      }
      secretName = var.postgres_connection_string_secret_name
    }
  })
}

resource "azurerm_data_factory_linked_custom_service" "azure_sql" {
  count           = local.adf_enabled ? 1 : 0
  name            = "ls_azure_sql_payer"
  data_factory_id = azurerm_data_factory.this[0].id
  type            = "AzureSqlDatabase"
  description     = "Payer source and control database. Connection string is resolved from Key Vault at ADF runtime."
  annotations     = ["phase-3", "source-control", "synthetic-data"]
  type_properties_json = jsonencode({
    connectionString = {
      type = "AzureKeyVaultSecret"
      store = {
        referenceName = azurerm_data_factory_linked_service_key_vault.key_vault[0].name
        type          = "LinkedServiceReference"
      }
      secretName = var.azure_sql_connection_string_secret_name
    }
  })
}

resource "azurerm_data_factory_linked_service_data_lake_storage_gen2" "lake" {
  count                = local.adf_enabled ? 1 : 0
  name                 = "ls_adls_lake"
  data_factory_id      = azurerm_data_factory.this[0].id
  url                  = var.storage_dfs_endpoint
  use_managed_identity = true
  description          = "ADLS Gen2 lake accessed by the Data Factory system-assigned managed identity."
  annotations          = ["phase-3", "managed-identity", "synthetic-data"]
}

resource "azurerm_data_factory_custom_dataset" "postgresql_table" {
  count           = local.adf_enabled ? 1 : 0
  name            = "ds_postgresql_table"
  data_factory_id = azurerm_data_factory.this[0].id
  type            = "PostgreSqlV2Table"
  folder          = "Phase3/Source"
  description     = "Parameterized PostgreSQL source dataset."
  parameters = {
    source_schema = ""
    source_table  = ""
  }
  linked_service {
    name = azurerm_data_factory_linked_custom_service.postgresql[0].name
  }
  type_properties_json = jsonencode({
    schema = { value = "@dataset().source_schema", type = "Expression" }
    table  = { value = "@dataset().source_table", type = "Expression" }
  })
}

resource "azurerm_data_factory_custom_dataset" "azure_sql_table" {
  count           = local.adf_enabled ? 1 : 0
  name            = "ds_azure_sql_table"
  data_factory_id = azurerm_data_factory.this[0].id
  type            = "AzureSqlTable"
  folder          = "Phase3/Source"
  description     = "Parameterized Azure SQL source and control dataset."
  parameters = {
    source_schema = ""
    source_table  = ""
  }
  linked_service {
    name = azurerm_data_factory_linked_custom_service.azure_sql[0].name
  }
  type_properties_json = jsonencode({
    schema = { value = "@dataset().source_schema", type = "Expression" }
    table  = { value = "@dataset().source_table", type = "Expression" }
  })
}

resource "azurerm_data_factory_dataset_parquet" "bronze" {
  count               = local.adf_enabled ? 1 : 0
  name                = "ds_bronze_parquet"
  data_factory_id     = azurerm_data_factory.this[0].id
  linked_service_name = azurerm_data_factory_linked_service_data_lake_storage_gen2.lake[0].name
  folder              = "Phase3/Bronze"
  description         = "Immutable, run-scoped Bronze Parquet dataset."
  compression_codec   = "snappy"
  parameters = {
    source_system = ""
    source_schema = ""
    source_table  = ""
    batch_id      = ""
    run_id        = ""
  }
  azure_blob_fs_location {
    file_system                 = var.storage_filesystem_name
    path                        = local.bronze_path_expression
    dynamic_path_enabled        = true
    dynamic_file_system_enabled = false
  }
}

resource "azurerm_data_factory_pipeline" "validate_landing" {
  count           = local.adf_enabled ? 1 : 0
  name            = "pl_validate_landing"
  data_factory_id = azurerm_data_factory.this[0].id
  folder          = "Phase3/Ingestion"
  description     = "Fails a table run when Copy did not land the expected row count or path contract."
  annotations     = ["phase-3", "validation"]

  parameters = {
    source_row_count = "0"
    landed_row_count = "0"
    file_count       = "0"
    bronze_path      = ""
  }

  activities_json = templatefile("${path.module}/adf/validate_landing.activities.json.tftpl", {})
}

resource "azurerm_data_factory_pipeline" "ingest_table" {
  count           = local.adf_enabled ? 1 : 0
  name            = "pl_ingest_table"
  data_factory_id = azurerm_data_factory.this[0].id
  folder          = "Phase3/Ingestion"
  description     = "Retry-safe bounded extraction of one configured source table into immutable Bronze."
  annotations     = ["phase-3", "metadata-driven", "composite-watermark"]
  concurrency     = var.data_profile == "tiny" ? 2 : 4

  parameters = {
    ingestion_config_id = "0"
    source_system       = ""
    source_engine       = ""
    source_schema       = ""
    source_table        = ""
    primary_key_column  = ""
    watermark_column    = ""
    load_type           = "INCREMENTAL"
    extraction_sql      = ""
    batch_id            = ""
    pipeline_run_id     = ""
    backfill_start      = ""
    backfill_end        = ""
  }

  variables = {
    source_row_count   = "0"
    landed_row_count   = "0"
    file_count         = "0"
    low_watermark_ts   = "1900-01-01T00:00:00.000"
    low_watermark_key  = "0"
    high_watermark_ts  = ""
    high_watermark_key = ""
    bronze_path        = ""
  }

  activities_json = templatefile("${path.module}/adf/ingest_table.activities.json.tftpl", {
    activity_policy          = jsonencode(local.adf_activity_policy)
    azure_sql_linked_service = azurerm_data_factory_linked_custom_service.azure_sql[0].name
    azure_sql_dataset        = azurerm_data_factory_custom_dataset.azure_sql_table[0].name
    postgresql_dataset       = azurerm_data_factory_custom_dataset.postgresql_table[0].name
    bronze_dataset           = azurerm_data_factory_dataset_parquet.bronze[0].name
    validation_pipeline      = azurerm_data_factory_pipeline.validate_landing[0].name
  })
}

resource "azurerm_data_factory_pipeline" "master_ingestion" {
  count           = local.adf_enabled ? 1 : 0
  name            = "pl_master_ingestion"
  data_factory_id = azurerm_data_factory.this[0].id
  folder          = "Phase3/Ingestion"
  description     = "Reads enabled metadata and orchestrates bounded table ingestion, completion, and downstream readiness."
  annotations     = ["phase-3", "metadata-driven", "orchestration"]
  concurrency     = 1

  parameters = {
    batch_id       = ""
    source_filter  = "ALL"
    backfill_start = ""
    backfill_end   = ""
  }

  activities_json = jsonencode([
    {
      name   = "Begin pipeline run"
      type   = "SqlServerStoredProcedure"
      policy = local.adf_activity_policy
      linkedServiceName = {
        referenceName = azurerm_data_factory_linked_custom_service.azure_sql[0].name
        type          = "LinkedServiceReference"
      }
      typeProperties = {
        storedProcedureName = "control.usp_begin_pipeline_run"
        storedProcedureParameters = {
          pipeline_run_id = { value = { type = "Expression", value = "@pipeline().RunId" }, type = "Guid" }
          batch_id        = { value = { type = "Expression", value = "@if(empty(pipeline().parameters.batch_id), concat('scheduled-', formatDateTime(utcNow(), 'yyyyMMdd-HHmmss')), pipeline().parameters.batch_id)" }, type = "String" }
          pipeline_name   = { value = "pl_master_ingestion", type = "String" }
          invocation_type = { value = "@if(or(not(empty(pipeline().parameters.backfill_start)), not(empty(pipeline().parameters.backfill_end))), 'BACKFILL', 'MANUAL')", type = "String" }
        }
      }
    },
    {
      name   = "Read enabled ingestion metadata"
      type   = "Lookup"
      policy = local.adf_activity_policy
      dependsOn = [
        { activity = "Begin pipeline run", dependencyConditions = ["Succeeded"] }
      ]
      typeProperties = {
        source = {
          type = "AzureSqlSource"
          sqlReaderQuery = {
            type  = "Expression"
            value = "@concat('SELECT c.ingestion_config_id, s.source_name AS source_system, s.engine AS source_engine, c.source_schema, c.source_table, c.primary_key_column, c.watermark_column, c.load_type, c.extraction_sql_template AS extraction_sql FROM control.ingestion_config c JOIN control.source_system s ON s.source_system_id=c.source_system_id WHERE c.enabled=1 AND s.enabled=1', if(equals(pipeline().parameters.source_filter, 'ALL'), '', concat(' AND s.source_name=''', pipeline().parameters.source_filter, '''')), ' ORDER BY c.concurrency_group, c.ingestion_config_id')"
          }
        }
        dataset = {
          referenceName = azurerm_data_factory_custom_dataset.azure_sql_table[0].name
          type          = "DatasetReference"
          parameters    = { source_schema = "control", source_table = "ingestion_config" }
        }
        firstRowOnly = false
      }
    },
    {
      name      = "Ingest configured tables"
      type      = "ForEach"
      dependsOn = [{ activity = "Read enabled ingestion metadata", dependencyConditions = ["Succeeded"] }]
      typeProperties = {
        isSequential = var.data_profile == "tiny"
        batchCount   = var.data_profile == "tiny" ? 1 : 4
        items        = { type = "Expression", value = "@activity('Read enabled ingestion metadata').output.value" }
        activities = [{
          name = "Execute table ingestion"
          type = "ExecutePipeline"
          typeProperties = {
            pipeline = {
              referenceName = azurerm_data_factory_pipeline.ingest_table[0].name
              type          = "PipelineReference"
            }
            waitOnCompletion = true
            parameters = {
              ingestion_config_id = "@string(item().ingestion_config_id)"
              source_system       = "@item().source_system"
              source_engine       = "@item().source_engine"
              source_schema       = "@item().source_schema"
              source_table        = "@item().source_table"
              primary_key_column  = "@item().primary_key_column"
              watermark_column    = "@item().watermark_column"
              load_type           = "@item().load_type"
              extraction_sql      = "@item().extraction_sql"
              batch_id            = "@if(empty(pipeline().parameters.batch_id), concat('scheduled-', formatDateTime(utcNow(), 'yyyyMMdd-HHmmss')), pipeline().parameters.batch_id)"
              pipeline_run_id     = "@pipeline().RunId"
              backfill_start      = "@pipeline().parameters.backfill_start"
              backfill_end        = "@pipeline().parameters.backfill_end"
            }
          }
        }]
      }
    },
    {
      name      = "Mark pipeline succeeded"
      type      = "SqlServerStoredProcedure"
      dependsOn = [{ activity = "Ingest configured tables", dependencyConditions = ["Succeeded"] }]
      policy    = local.adf_activity_policy
      linkedServiceName = {
        referenceName = azurerm_data_factory_linked_custom_service.azure_sql[0].name
        type          = "LinkedServiceReference"
      }
      typeProperties = {
        storedProcedureName = "control.usp_finish_pipeline_run"
        storedProcedureParameters = {
          pipeline_run_id = { value = { type = "Expression", value = "@pipeline().RunId" }, type = "Guid" }
          status          = { value = "SUCCEEDED", type = "String" }
          error_message   = { value = "", type = "String" }
        }
      }
    },
    {
      name      = "Publish downstream dependency ready"
      type      = "SqlServerStoredProcedure"
      dependsOn = [{ activity = "Mark pipeline succeeded", dependencyConditions = ["Succeeded"] }]
      policy    = local.adf_activity_policy
      linkedServiceName = {
        referenceName = azurerm_data_factory_linked_custom_service.azure_sql[0].name
        type          = "LinkedServiceReference"
      }
      typeProperties = {
        storedProcedureName = "control.usp_publish_job_dependency"
        storedProcedureParameters = {
          batch_id       = { value = { type = "Expression", value = "@if(empty(pipeline().parameters.batch_id), concat('scheduled-', formatDateTime(utcNow(), 'yyyyMMdd-HHmmss')), pipeline().parameters.batch_id)" }, type = "String" }
          upstream_job   = { value = "adf_ingestion", type = "String" }
          downstream_job = { value = "databricks_bronze", type = "String" }
          status         = { value = "READY", type = "String" }
        }
      }
    },
    {
      name = "Mark pipeline failed"
      type = "SqlServerStoredProcedure"
      dependsOn = [
        { activity = "Begin pipeline run", dependencyConditions = ["Failed"] },
        { activity = "Read enabled ingestion metadata", dependencyConditions = ["Failed"] },
        { activity = "Ingest configured tables", dependencyConditions = ["Failed"] },
        { activity = "Mark pipeline succeeded", dependencyConditions = ["Failed"] },
        { activity = "Publish downstream dependency ready", dependencyConditions = ["Failed"] }
      ]
      policy = local.adf_activity_policy
      linkedServiceName = {
        referenceName = azurerm_data_factory_linked_custom_service.azure_sql[0].name
        type          = "LinkedServiceReference"
      }
      typeProperties = {
        storedProcedureName = "control.usp_finish_pipeline_run"
        storedProcedureParameters = {
          pipeline_run_id = { value = { type = "Expression", value = "@pipeline().RunId" }, type = "Guid" }
          status          = { value = "FAILED", type = "String" }
          error_message   = { value = { type = "Expression", value = "@coalesce(activity('Ingest configured tables').error.message, activity('Read enabled ingestion metadata').error.message, 'Pipeline execution failed. Inspect ADF activity output.')" }, type = "String" }
        }
      }
    },
    {
      name      = "Raise pipeline failure"
      type      = "Fail"
      dependsOn = [{ activity = "Mark pipeline failed", dependencyConditions = ["Succeeded"] }]
      typeProperties = {
        errorCode = "MASTER_INGESTION_FAILED"
        message   = "One or more table runs, metadata reads, or control publications failed."
      }
    }
  ])
}

resource "azurerm_data_factory_trigger_schedule" "daily_ingestion" {
  count           = local.adf_enabled ? 1 : 0
  name            = "tr_daily_ingestion"
  data_factory_id = azurerm_data_factory.this[0].id
  pipeline_name   = azurerm_data_factory_pipeline.master_ingestion[0].name
  frequency       = "Day"
  interval        = 1
  start_time      = var.adf_schedule_start_time
  time_zone       = "UTC"
  activated       = var.enable_adf_schedule_trigger
  description     = "Optional daily trigger. Disabled by default for Azure trial cost control."
  annotations     = ["phase-3", "disabled-by-default"]

  pipeline_parameters = {
    batch_id       = ""
    source_filter  = "ALL"
    backfill_start = ""
    backfill_end   = ""
  }
}
