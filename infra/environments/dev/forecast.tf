variable "lambda_image_digests" {
  description = "Immutable linux/arm64 manifests from skycalm/functions."
  type        = object({ python = string, push = string })
  validation {
    condition     = alltrue([for d in var.lambda_image_digests : can(regex("^sha256:[a-f0-9]{64}$", d))])
    error_message = "Supply the published Python and Web Push manifest digests."
  }
}
variable "image_digest" {
  description = "Digest of the built linux/amd64 image in the bootstrap ECR repository."
  type        = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Pin the image by its full SHA-256 digest."
  }
}
variable "observation_window" {
  type    = object({ start = string, end = string })
  default = null
}
variable "discovery_window" {
  type    = object({ start = string, end = string })
  default = null
}
variable "passenger_settings" {
  type = object({
    google_ready    = bool
    vapid_public    = string
    classroom_email = string
    login_email     = optional(string)
  })
  default = { google_ready = false, vapid_public = "", classroom_email = "" }
}
module "forecast" {
  passenger_settings   = var.passenger_settings
  source               = "../../modules/forecast"
  account_id           = var.account_id
  image_digest         = var.image_digest
  observation_window   = var.observation_window
  discovery_window     = var.discovery_window
  lambda_image_digests = var.lambda_image_digests
  web_directory        = abspath("${path.root}/../../../web/dist")
  archive_directory    = abspath("${path.root}/../../../services/forecast/data/replay")
}
output "pipeline_operator_policy" { value = module.forecast.pipeline_operator_policy }
output "website" { value = module.forecast.website }
output "api" { value = module.forecast.api }
output "grid_run_request" { value = module.forecast.grid_run_request }

output "observations_function" { value = module.forecast.observations_function }
