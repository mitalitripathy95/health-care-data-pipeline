resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name_prefix}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  # Azure Monitor enforces a minimum retention of 30 days. The workspace is
  # still inexpensive for this short-lived synthetic demonstration.
  retention_in_days = 30
  tags              = var.common_tags
}

resource "azurerm_application_insights" "this" {
  name                = "${var.name_prefix}-appi"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "other"
  retention_in_days   = 30
  tags                = var.common_tags
}

resource "azurerm_monitor_action_group" "budget" {
  name                = "${var.name_prefix}-ag"
  resource_group_name = var.resource_group_name
  short_name          = "hcpipe"
  dynamic "email_receiver" {
    for_each = var.alert_email == null ? [] : [var.alert_email]
    content {
      name          = "budget-owner"
      email_address = email_receiver.value
    }
  }
  tags = var.common_tags
}

resource "azurerm_consumption_budget_resource_group" "this" {
  name              = "${var.name_prefix}-budget"
  resource_group_id = var.resource_group_id
  amount            = var.monthly_budget_amount
  time_grain        = "Monthly"
  time_period {
    start_date = var.budget_start_date
    end_date   = "2035-01-01T00:00:00Z"
  }
  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.budget.id]
  }
  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_groups = [azurerm_monitor_action_group.budget.id]
  }
}
