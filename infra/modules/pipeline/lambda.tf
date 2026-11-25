resource "aws_dynamodb_table" "jobs" {
  name         = local.prefix
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}
locals {
  functions = {
    admission = { handler = "handlers.admission", timeout = 12 },
    workflow  = { handler = "handlers.workflow", timeout = 20 },
    routes    = { handler = "handlers.routes", timeout = 15 },
    audit     = { handler = "handlers.audit", timeout = 12 },
    discover  = { handler = "discovery.handler", timeout = 90 }
  }
}
resource "aws_cloudwatch_log_group" "function" {
  for_each          = local.functions
  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = 7
}
resource "aws_lambda_function" "run" {
  for_each      = local.functions
  function_name = "${local.prefix}-${each.key}-img"
  role          = aws_iam_role.function[each.key].arn
  package_type  = "Image"
  image_uri     = var.python_image
  image_config { command = ["services.pipeline.${each.value.handler}"] }
  lifecycle { create_before_destroy = true }
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = each.value.timeout
  environment {
    variables = { PIPELINE_TABLE = aws_dynamodb_table.jobs.name, PIPELINE_BUS = aws_cloudwatch_event_bus.forecast.name, STATE_MACHINE = local.machine_arn, SKYCALM_BUCKET = var.weather_bucket, SKYCALM_TABLE = var.runs_table }
  }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.function[each.key].name
  }
}
resource "aws_lambda_event_source_mapping" "consumer" {
  for_each                = local.consumers
  event_source_arn        = aws_sqs_queue.work[each.key].arn
  function_name           = aws_lambda_function.run[each.key].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  depends_on              = [aws_iam_role_policy.function]
}
