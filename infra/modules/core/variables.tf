variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "environment" {
  type = string
}

variable "resource_suffix" {
  type = string
}

variable "tenant_id" {
  type      = string
  sensitive = true
}

variable "common_tags" {
  type = map(string)
}

variable "create_acr" {
  type    = bool
  default = true
}
