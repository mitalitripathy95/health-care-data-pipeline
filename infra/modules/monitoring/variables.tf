variable "name_prefix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_id" {
  type = string
}

variable "common_tags" {
  type = map(string)
}

variable "alert_email" {
  type     = string
  default  = null
  nullable = true
}

variable "monthly_budget_amount" {
  type = number
}

variable "budget_start_date" {
  type        = string
  description = "Stable UTC start date for the budget, e.g. 2026-09-01T00:00:00Z."
  validation {
    condition     = can(regex("^20[0-9]{2}-[0-9]{2}-[0-9]{2}T00:00:00Z$", var.budget_start_date))
    error_message = "budget_start_date must be a UTC midnight timestamp."
  }
}
