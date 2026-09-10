output "data_factory_id" {
  value = try(azurerm_data_factory.this[0].id, null)
}

output "data_factory_principal_id" {
  value = try(azurerm_data_factory.this[0].identity[0].principal_id, null)
}

output "data_factory_name" {
  value = try(azurerm_data_factory.this[0].name, null)
}

output "databricks_workspace_id" {
  value = try(azurerm_databricks_workspace.this[0].id, null)
}

output "databricks_workspace_url" {
  value = try(azurerm_databricks_workspace.this[0].workspace_url, null)
}

output "databricks_access_connector_id" {
  value = try(azurerm_databricks_access_connector.this[0].id, null)
}

output "databricks_access_connector_principal_id" {
  value = try(azurerm_databricks_access_connector.this[0].identity[0].principal_id, null)
}

output "generator_identity_id" {
  value = try(azurerm_user_assigned_identity.generator[0].id, null)
}

output "generator_principal_id" {
  value = try(azurerm_user_assigned_identity.generator[0].principal_id, null)
}

output "container_app_environment_id" {
  value = try(azurerm_container_app_environment.this[0].id, null)
}

output "container_app_job_id" {
  value = try(azurerm_container_app_job.generator[0].id, null)
}
