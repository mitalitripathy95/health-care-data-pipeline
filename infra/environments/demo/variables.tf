variable "subscription_id" {
  type        = string
  description = "Azure subscription ID. Supply via ARM_SUBSCRIPTION_ID or *.tfvars; never commit it."
  sensitive   = true
}

variable "tenant_id" {
  type        = string
  description = "Azure tenant ID. Supply via ARM_TENANT_ID or *.tfvars; never commit it."
  sensitive   = true
}

variable "location" {
  type        = string
  description = "Azure region for the short-lived demonstration."
  default     = "eastus"
}

variable "environment" {
  type    = string
  default = "demo"
  validation {
    condition     = can(regex("^[a-z0-9-]{1,12}$", var.environment))
    error_message = "environment must contain only lowercase letters, numbers, and hyphens (max 12 chars)."
  }
}

variable "project_name" {
  type    = string
  default = "healthcare-data-pipeline"
}

variable "resource_suffix" {
  type        = string
  description = "Globally unique, non-sensitive suffix, e.g. abc123."
  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.resource_suffix))
    error_message = "resource_suffix must be 3-12 lowercase alphanumeric characters."
  }
}

variable "data_profile" {
  type    = string
  default = "tiny"
  validation {
    condition     = contains(["tiny", "small"], var.data_profile)
    error_message = "Only tiny and small are permitted for the Azure trial."
  }
}

variable "sql_admin_login" {
  type        = string
  description = "Azure SQL administrator login. Use a non-personal demo identity."
  sensitive   = true
}

variable "sql_admin_password" {
  type        = string
  description = "Azure SQL administrator password; inject from CI or an environment variable."
  sensitive   = true
  validation {
    condition     = length(var.sql_admin_password) >= 16
    error_message = "sql_admin_password must be at least 16 characters."
  }
}

variable "postgres_admin_login" {
  type      = string
  default   = "hcpipeadmin"
  sensitive = true
}

variable "postgres_admin_password" {
  type        = string
  description = "PostgreSQL administrator password; inject from CI or an environment variable."
  sensitive   = true
  validation {
    condition     = length(var.postgres_admin_password) >= 16
    error_message = "postgres_admin_password must be at least 16 characters."
  }
}

variable "alert_email" {
  type        = string
  description = "Optional email for the Azure budget action group."
  default     = null
  nullable    = true
}

variable "monthly_budget_amount" {
  type        = number
  description = "Budget alert amount in the subscription currency."
  default     = 150
  validation {
    condition     = var.monthly_budget_amount > 0 && var.monthly_budget_amount <= 200
    error_message = "The trial budget must be between 0 and 200."
  }
}

variable "budget_start_date" {
  type        = string
  description = "Stable UTC midnight timestamp for the budget, supplied explicitly (for example 2026-09-01T00:00:00Z)."
  default     = "2026-09-01T00:00:00Z"
  validation {
    condition     = can(regex("^20[0-9]{2}-[0-9]{2}-[0-9]{2}T00:00:00Z$", var.budget_start_date))
    error_message = "budget_start_date must be a UTC midnight timestamp."
  }
}

variable "create_acr" {
  type        = bool
  description = "Create the Basic Azure Container Registry used for the generator image."
  default     = true
}

variable "create_data_factory" {
  type        = bool
  description = "Create Azure Data Factory."
  default     = true
}

variable "enable_adf_schedule_trigger" {
  type        = bool
  description = "Enable the daily ADF ingestion trigger. It is intentionally disabled during code build-out."
  default     = false
}

variable "adf_schedule_start_time" {
  type        = string
  description = "UTC anchor used only when the ADF schedule is enabled."
  default     = "2030-01-01T00:00:00Z"
}

variable "postgres_connection_string_secret_name" {
  type        = string
  description = "Key Vault secret name for the complete ADF PostgreSQL connection string."
  default     = "adf-postgresql-connection-string"
}

variable "azure_sql_connection_string_secret_name" {
  type        = string
  description = "Key Vault secret name for the complete ADF Azure SQL connection string."
  default     = "adf-azure-sql-connection-string"
}

variable "create_databricks" {
  type        = bool
  description = "Create the trial Azure Databricks workspace and access connector."
  default     = true
}

variable "create_postgres" {
  type        = bool
  description = "Create the PostgreSQL clinical source."
  default     = true
}

variable "create_azure_sql" {
  type        = bool
  description = "Create the Azure SQL payer source."
  default     = true
}

variable "create_container_job" {
  type        = bool
  description = "Create the one-shot Container Apps synthetic generator job."
  default     = true
}

variable "create_monitoring" {
  type        = bool
  description = "Create Log Analytics, Application Insights, action group, and budget."
  default     = true
}

variable "allowed_ip_addresses" {
  type        = list(string)
  description = "Operator IPv4 addresses allowed through temporary source database firewalls."
  default     = []
  validation {
    condition = alltrue([
      for address in var.allowed_ip_addresses : can(cidrhost("${address}/32", 0))
    ])
    error_message = "allowed_ip_addresses must contain valid IPv4 addresses."
  }
}

variable "container_image" {
  type        = string
  description = "Synthetic generator image. Replace the placeholder with the ACR image in the application phase."
  default     = "mcr.microsoft.com/azure-cli:2.64.0"
}
