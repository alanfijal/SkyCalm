terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.74" }
  }
}
variable "account_id" { type = string }
variable "bucket" { type = string }
variable "image_digest" { type = string }
variable "bus_name" { type = string }
variable "grid_role" { type = string }
variable "forecast_role" { type = string }
locals {
  name      = "skycalm-turbulence"
  region    = "eu-north-1"
  sm        = "arn:aws:sagemaker:${local.region}:${var.account_id}"
  storage   = "arn:aws:s3:::${var.bucket}"
  base      = "s3://${var.bucket}"
  image     = "${var.account_id}.dkr.ecr.${local.region}.amazonaws.com/skycalm/grid@${var.image_digest}"
  group_arn = "${local.sm}:model-package-group/${local.name}"
  model_arn = "${local.sm}:model-package/${local.name}/*"
  bus_arn   = "arn:aws:events:${local.region}:${var.account_id}:event-bus/${var.bus_name}"
}
