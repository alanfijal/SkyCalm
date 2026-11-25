terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.74" }
  }
}
variable "name" { type = string }
variable "region" { type = string }
variable "account_id" { type = string }
variable "python_image" { type = string }
variable "weather_bucket" { type = string }
variable "runs_table" { type = string }
variable "task_arn" { type = string }
variable "cluster_arn" { type = string }
variable "subnet" { type = string }
variable "security_group" { type = string }
variable "execution_role_arn" { type = string }
variable "grid_role_arn" { type = string }
variable "discovery_window" {
  type    = object({ start = string, end = string })
  default = null
  validation {
    condition     = var.discovery_window == null ? true : try(endswith(var.discovery_window.start, "Z") && endswith(var.discovery_window.end, "Z") && timecmp(var.discovery_window.end, var.discovery_window.start) > 0 && timecmp(var.discovery_window.end, timeadd(var.discovery_window.start, "2h")) <= 0, false)
    error_message = "Use a bounded discovery window of up to two hours in UTC."
  }
}
locals {
  prefix        = "${var.name}-pipeline"
  machine_arn   = "arn:aws:states:${var.region}:${var.account_id}:stateMachine:${local.prefix}"
  execution_arn = "arn:aws:states:${var.region}:${var.account_id}:execution:${local.prefix}:*"
  weather_arn   = "arn:aws:s3:::${var.weather_bucket}"
  runs_arn      = "arn:aws:dynamodb:${var.region}:${var.account_id}:table/${var.runs_table}"
}
