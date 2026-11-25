resource "aws_cloudwatch_log_group" "forecast" {
  name              = "/aws/lambda/${local.name}-forecast"
  retention_in_days = 7
}
resource "aws_lambda_function" "forecast" {
  function_name = "${local.name}-forecast-img"
  role          = aws_iam_role.forecast.arn
  package_type  = "Image"
  image_uri     = local.lambda_images.python
  image_config { command = ["services.forecast.handler.handler"] }
  lifecycle { create_before_destroy = true }
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 15
  environment {
    variables = {
      SKYCALM_BRIEFINGS = var.training_image_digest == null ? "disabled" : "enabled"
      SKYCALM_BUCKET    = aws_s3_bucket.app["weather"].id
      SKYCALM_TABLE     = aws_dynamodb_table.runs.name
    }
  }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.forecast.name
  }
}
