locals {
  name_prefix = "hcpipe-${var.environment}"
  common_tags = {
    project             = var.project_name
    environment         = var.environment
    owner               = "portfolio"
    managed_by          = "terraform"
    cost_center         = "trial"
    data_classification = "synthetic"
  }
}

module "core" {
  source          = "../../modules/core"
  name_prefix     = local.name_prefix
  location        = var.location
  environment     = var.environment
  resource_suffix = var.resource_suffix
  tenant_id       = var.tenant_id
  common_tags     = local.common_tags
  create_acr      = var.create_acr
}

module "data" {
  source                  = "../../modules/data"
  name_prefix             = local.name_prefix
  location                = var.location
  resource_group_name     = module.core.resource_group_name
  resource_suffix         = var.resource_suffix
  common_tags             = local.common_tags
  data_profile            = var.data_profile
  create_postgres         = var.create_postgres
  create_azure_sql        = var.create_azure_sql
  postgres_admin_login    = var.postgres_admin_login
  postgres_admin_password = var.postgres_admin_password
  sql_admin_login         = var.sql_admin_login
  sql_admin_password      = var.sql_admin_password
  allowed_ip_addresses    = var.allowed_ip_addresses
}

module "compute" {
  source                                  = "../../modules/compute"
  name_prefix                             = local.name_prefix
  location                                = var.location
  resource_group_name                     = module.core.resource_group_name
  resource_suffix                         = var.resource_suffix
  common_tags                             = local.common_tags
  data_profile                            = var.data_profile
  storage_dfs_endpoint                    = module.core.storage_dfs_endpoint
  storage_filesystem_name                 = module.core.storage_filesystem_name
  key_vault_id                            = module.core.key_vault_id
  postgres_connection_string_secret_name  = var.postgres_connection_string_secret_name
  azure_sql_connection_string_secret_name = var.azure_sql_connection_string_secret_name
  enable_adf_schedule_trigger             = var.enable_adf_schedule_trigger
  adf_schedule_start_time                 = var.adf_schedule_start_time
  create_data_factory                     = var.create_data_factory
  create_databricks                       = var.create_databricks
  create_container_job                    = var.create_container_job
  container_image                         = var.container_image
}

module "monitoring" {
  count                 = var.create_monitoring ? 1 : 0
  source                = "../../modules/monitoring"
  name_prefix           = local.name_prefix
  location              = var.location
  resource_group_name   = module.core.resource_group_name
  resource_group_id     = module.core.resource_group_id
  common_tags           = local.common_tags
  alert_email           = var.alert_email
  monthly_budget_amount = var.monthly_budget_amount
  budget_start_date     = var.budget_start_date
}

resource "azurerm_role_assignment" "adf_storage" {
  count                = var.create_data_factory && module.compute.data_factory_principal_id != null ? 1 : 0
  scope                = module.core.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.data_factory_principal_id
}

resource "azurerm_role_assignment" "adf_key_vault" {
  count                = var.create_data_factory && module.compute.data_factory_principal_id != null ? 1 : 0
  scope                = module.core.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.compute.data_factory_principal_id
}

resource "azurerm_role_assignment" "generator_storage" {
  count                = var.create_container_job && module.compute.generator_principal_id != null ? 1 : 0
  scope                = module.core.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.generator_principal_id
}

resource "azurerm_role_assignment" "generator_key_vault" {
  count                = var.create_container_job && module.compute.generator_principal_id != null ? 1 : 0
  scope                = module.core.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.compute.generator_principal_id
}

resource "azurerm_role_assignment" "databricks_storage" {
  count                = var.create_databricks && module.compute.databricks_access_connector_principal_id != null ? 1 : 0
  scope                = module.core.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.compute.databricks_access_connector_principal_id
}

resource "azurerm_role_assignment" "databricks_key_vault" {
  count                = var.create_databricks && module.compute.databricks_access_connector_principal_id != null ? 1 : 0
  scope                = module.core.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.compute.databricks_access_connector_principal_id
}
