resource "azurerm_postgresql_flexible_server" "clinical" {
  count                         = var.create_postgres ? 1 : 0
  name                          = "${var.name_prefix}-pg-${var.resource_suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "16"
  administrator_login           = var.postgres_admin_login
  administrator_password        = var.postgres_admin_password
  storage_mb                    = var.data_profile == "tiny" ? 32768 : 65536
  sku_name                      = "B_Standard_B1ms"
  backup_retention_days         = 7
  public_network_access_enabled = true
  tags                          = var.common_tags
}

resource "azurerm_postgresql_flexible_server_database" "clinical" {
  count     = var.create_postgres ? 1 : 0
  name      = "clinical"
  server_id = azurerm_postgresql_flexible_server.clinical[0].id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "operator" {
  for_each         = var.create_postgres ? toset(var.allowed_ip_addresses) : []
  name             = "operator-${replace(each.value, ".", "-")}"
  server_id        = azurerm_postgresql_flexible_server.clinical[0].id
  start_ip_address = each.value
  end_ip_address   = each.value
}

resource "azurerm_mssql_server" "payer" {
  count                         = var.create_azure_sql ? 1 : 0
  name                          = "${var.name_prefix}-sql-${var.resource_suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "12.0"
  administrator_login           = var.sql_admin_login
  administrator_login_password  = var.sql_admin_password
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  tags                          = var.common_tags
}

resource "azurerm_mssql_database" "payer" {
  count          = var.create_azure_sql ? 1 : 0
  name           = "payer"
  server_id      = azurerm_mssql_server.payer[0].id
  sku_name       = var.data_profile == "tiny" ? "Basic" : "S0"
  max_size_gb    = var.data_profile == "tiny" ? 2 : 10
  zone_redundant = false
  tags           = var.common_tags
}

resource "azurerm_mssql_firewall_rule" "operator" {
  for_each         = var.create_azure_sql ? { for ip in var.allowed_ip_addresses : replace(ip, ".", "-") => ip } : {}
  name             = "operator-${each.key}"
  server_id        = azurerm_mssql_server.payer[0].id
  start_ip_address = each.value
  end_ip_address   = each.value
}
