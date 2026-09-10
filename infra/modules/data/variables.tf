variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "common_tags" {
  type = map(string)
}

variable "data_profile" {
  type = string
}

variable "create_postgres" {
  type    = bool
  default = true
}

variable "create_azure_sql" {
  type    = bool
  default = true
}

variable "postgres_admin_login" {
  type      = string
  sensitive = true
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
}

variable "sql_admin_login" {
  type      = string
  sensitive = true
}

variable "sql_admin_password" {
  type      = string
  sensitive = true
}

variable "resource_suffix" {
  type = string
}

variable "allowed_ip_addresses" {
  type    = list(string)
  default = []
}
