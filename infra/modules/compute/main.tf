resource "azurerm_data_factory" "this" {
  count               = var.create_data_factory ? 1 : 0
  name                = "${var.name_prefix}-adf-${var.resource_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  identity {
    type = "SystemAssigned"
  }
  tags = var.common_tags
}

resource "azurerm_databricks_workspace" "this" {
  count                         = var.create_databricks ? 1 : 0
  name                          = "${var.name_prefix}-dbw-${var.resource_suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = "trial"
  managed_resource_group_name   = "${var.name_prefix}-dbw-managed-${var.resource_suffix}"
  public_network_access_enabled = true
  tags                          = var.common_tags
}

resource "azurerm_databricks_access_connector" "this" {
  count               = var.create_databricks ? 1 : 0
  name                = "${var.name_prefix}-dac-${var.resource_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  identity {
    type = "SystemAssigned"
  }
  tags = var.common_tags
}

resource "azurerm_user_assigned_identity" "generator" {
  count               = var.create_container_job ? 1 : 0
  name                = "${var.name_prefix}-generator-${var.resource_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.common_tags
}

resource "azurerm_container_app_environment" "this" {
  count               = var.create_container_job ? 1 : 0
  name                = "${var.name_prefix}-cae-${var.resource_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.common_tags
}

resource "azurerm_container_app_job" "generator" {
  count                        = var.create_container_job ? 1 : 0
  name                         = "${var.name_prefix}-generator-job-${var.resource_suffix}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this[0].id
  replica_retry_limit          = 1
  replica_timeout_in_seconds   = 3600

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "synthetic-generator"
      image   = var.container_image
      cpu     = var.data_profile == "tiny" ? 0.25 : 0.5
      memory  = var.data_profile == "tiny" ? "0.5Gi" : "1Gi"
      command = ["/bin/sh", "-c"]
      args    = ["echo 'Replace this command with the packaged synthetic generator entrypoint in Phase 4' && sleep 5"]
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.generator[0].id]
  }

  tags = var.common_tags
}
