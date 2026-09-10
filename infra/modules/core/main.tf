resource "azurerm_resource_group" "this" {
  name     = "${var.name_prefix}-rg-${var.resource_suffix}"
  location = var.location
  tags     = var.common_tags
}

resource "random_string" "storage" {
  length  = 8
  special = false
  upper   = false
}

resource "azurerm_storage_account" "lake" {
  name                            = substr("hcpipe${var.environment}${var.resource_suffix}${random_string.storage.result}", 0, 24)
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false
  tags                            = var.common_tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 7 }
    container_delete_retention_policy { days = 7 }
  }
}

resource "azurerm_storage_data_lake_gen2_filesystem" "lake" {
  name               = "lake"
  storage_account_id = azurerm_storage_account.lake.id
  properties         = { purpose = "bronze-silver-gold" }
}

resource "azurerm_storage_data_lake_gen2_path" "layers" {
  for_each           = toset(["bronze", "silver", "gold", "control"])
  path               = each.value
  filesystem_name    = azurerm_storage_data_lake_gen2_filesystem.lake.name
  storage_account_id = azurerm_storage_account.lake.id
  resource           = "directory"
}

resource "azurerm_key_vault" "this" {
  name                          = substr("${var.name_prefix}-kv-${var.resource_suffix}", 0, 24)
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = false
  soft_delete_retention_days    = 7
  public_network_access_enabled = true
  rbac_authorization_enabled    = true
  tags                          = var.common_tags
}

resource "azurerm_container_registry" "this" {
  count               = var.create_acr ? 1 : 0
  name                = substr("hcpipe${var.environment}${var.resource_suffix}acr", 0, 50)
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.common_tags
}
