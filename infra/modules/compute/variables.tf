variable "name_prefix" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "resource_suffix" { type = string }
variable "common_tags" { type = map(string) }
variable "data_profile" { type = string }

variable "storage_dfs_endpoint" {
  type        = string
  description = "ADLS Gen2 DFS endpoint used by ADF managed identity."
}

variable "storage_filesystem_name" {
  type        = string
  description = "ADLS Gen2 filesystem containing Bronze data."
}

variable "key_vault_id" {
  type        = string
  description = "Key Vault resource ID used by the ADF Key Vault linked service."
}

variable "postgres_connection_string_secret_name" {
  type        = string
  description = "Name of the Key Vault secret containing the complete PostgreSQL ADF connection string."
  default     = "adf-postgresql-connection-string"
}

variable "azure_sql_connection_string_secret_name" {
  type        = string
  description = "Name of the Key Vault secret containing the complete Azure SQL ADF connection string."
  default     = "adf-azure-sql-connection-string"
}

variable "enable_adf_schedule_trigger" {
  type        = bool
  description = "Activate the low-cost scheduled ingestion trigger. Keep false until end-to-end deployment testing."
  default     = false
}

variable "adf_schedule_start_time" {
  type        = string
  description = "UTC schedule anchor. Must be supplied deliberately before enabling the trigger."
  default     = "2030-01-01T00:00:00Z"
}

variable "create_data_factory" {
  type    = bool
  default = true
}

variable "create_databricks" {
  type    = bool
  default = true
}

variable "create_container_job" {
  type    = bool
  default = true
}

variable "container_image" {
  type        = string
  description = "Synthetic generator image. Replace with the ACR image in the deployment phase."
  default     = "mcr.microsoft.com/azure-cli:2.64.0"
}
