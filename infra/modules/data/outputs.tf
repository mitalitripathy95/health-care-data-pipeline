output "postgres_fqdn" { value = try(azurerm_postgresql_flexible_server.clinical[0].fqdn, null) }
output "postgres_server_id" { value = try(azurerm_postgresql_flexible_server.clinical[0].id, null) }
output "postgres_database_name" { value = try(azurerm_postgresql_flexible_server_database.clinical[0].name, null) }
output "azure_sql_fqdn" { value = try(azurerm_mssql_server.payer[0].fully_qualified_domain_name, null) }
output "azure_sql_server_id" { value = try(azurerm_mssql_server.payer[0].id, null) }
output "azure_sql_database_name" { value = try(azurerm_mssql_database.payer[0].name, null) }
