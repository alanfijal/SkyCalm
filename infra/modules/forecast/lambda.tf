resource "aws_cloudwatch_log_group" "forecast" {
  name              = "/aws/lambda/${local.name}-forecast"
  retention_in_days = 7
}
resource "aws_lambda_function" "forecast" {
  function_name    = "${local.name}-forecast"
  role             = aws_iam_role.forecast.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "services.forecast.handler.handler"
  memory_size      = 512
  timeout          = 15
  filename         = var.lambda_zip
  source_code_hash = try(filebase64sha256(var.lambda_zip), null)
  environment {
    variables = {
      SKYCALM_BUCKET = aws_s3_bucket.app["weather"].id
      SKYCALM_TABLE  = aws_dynamodb_table.runs.name
    }
  }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.forecast.name
  }
  lifecycle {
    precondition {
      condition     = fileexists(var.lambda_zip)
      error_message = "Build the Lambda zip with python scripts/package_lambda.py first."
    }
  }
}
