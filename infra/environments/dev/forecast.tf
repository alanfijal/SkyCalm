variable "image_digest" {
  description = "Digest of the built linux/amd64 image in the bootstrap ECR repository."
  type        = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Pin the image by its full SHA-256 digest."
  }
}
module "forecast" {
  source            = "../../modules/forecast"
  account_id        = var.account_id
  image_digest      = var.image_digest
  lambda_zip        = abspath("${path.root}/../../../build/forecast.zip")
  web_directory     = abspath("${path.root}/../../../web/dist")
  archive_directory = abspath("${path.root}/../../../services/forecast/data/replay")
}
output "website" { value = module.forecast.website }
output "api" { value = module.forecast.api }
output "grid_run_request" { value = module.forecast.grid_run_request }
