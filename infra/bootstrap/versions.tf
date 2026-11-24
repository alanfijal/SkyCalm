terraform {
  required_version = "= 1.17.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.74.0"
    }
  }
}
provider "aws" {
  region              = "eu-north-1"
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "SkyCalm", Environment = "bootstrap", Owner = var.owner } }
}
variable "account_id" {
  description = "Expected AWS account. The provider rejects other identities."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Supply the 12-digit AWS account ID."
  }
}
variable "owner" {
  type    = string
  default = "esade"
}
