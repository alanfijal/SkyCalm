module "training" {
  count         = var.training_image_digest == null ? 0 : 1
  source        = "../training"
  account_id    = var.account_id
  bucket        = aws_s3_bucket.app["weather"].id
  image_digest  = var.training_image_digest
  bus_name      = module.pipeline.bus_name
  grid_role     = aws_iam_role.task["grid"].id
  forecast_role = aws_iam_role.forecast.id
}
