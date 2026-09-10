output "log_analytics_workspace_id" { value = azurerm_log_analytics_workspace.this.id }
output "log_analytics_workspace_name" { value = azurerm_log_analytics_workspace.this.name }
output "application_insights_id" { value = azurerm_application_insights.this.id }
output "action_group_id" { value = azurerm_monitor_action_group.budget.id }
