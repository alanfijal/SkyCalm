terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.74" }
  }
}
variable "account_id" { type = string }
variable "image_digest" { type = string }
variable "lambda_image_digests" { type = object({ python = string, push = string }) }
variable "web_directory" { type = string }
variable "archive_directory" { type = string }
locals {
  lambda_images = { for target, digest in var.lambda_image_digests : target => "${var.account_id}.dkr.ecr.${local.region}.amazonaws.com/skycalm/functions@${digest}" }
  name          = "skycalm-dev"
  region        = "eu-north-1"
  ecr_arn       = "arn:aws:ecr:${local.region}:${var.account_id}:repository/skycalm/grid"
  grid_image    = "${var.account_id}.dkr.ecr.${local.region}.amazonaws.com/skycalm/grid@${var.image_digest}"
}
