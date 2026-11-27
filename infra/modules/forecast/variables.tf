variable "training_image_digest" {
  description = "An approved amd64 training image digest enables the on-demand ML pipeline."
  type        = string
  default     = null
  validation {
    condition     = var.training_image_digest == null ? true : can(regex("^sha256:[a-f0-9]{64}$", var.training_image_digest))
    error_message = "Use an immutable SageMaker container digest."
  }
}
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.74" }
  }
}
variable "account_id" { type = string }
variable "image_digest" { type = string }
variable "lambda_image_digests" { type = object({ python = string }) }
variable "web_directory" { type = string }
variable "archive_directory" { type = string }
variable "enable_edge_waf" {
  type    = bool
  default = false
}
locals {
  lambda_images = { for target, digest in var.lambda_image_digests : target => "${var.account_id}.dkr.ecr.${local.region}.amazonaws.com/skycalm/functions@${digest}" }
  name          = "skycalm-dev"
  region        = "eu-north-1"
  ecr_arn       = "arn:aws:ecr:${local.region}:${var.account_id}:repository/skycalm/grid"
  grid_image    = "${var.account_id}.dkr.ecr.${local.region}.amazonaws.com/skycalm/grid@${var.image_digest}"
}
