locals {
  observation_key = {
    "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["observations#awc"] }
    Null                        = { "dynamodb:LeadingKeys" = "false" }
  }
  observation_archive = "${var.archive_directory}/../observations"
}
resource "aws_cloudwatch_log_group" "observations" {
  name              = "/aws/lambda/${local.name}-observations"
  retention_in_days = 7
}
resource "aws_iam_role" "observations" {
  name               = "${local.name}-observations"
  assume_role_policy = aws_iam_role.forecast.assume_role_policy
}
resource "aws_iam_role_policy" "observations" {
  name = "write-observation-snapshots"
  role = aws_iam_role.observations.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:PutObject", Resource = [for prefix in ["raw", "history", "snapshots"] : "${local.weather_arn}/observations/${prefix}/*"] },
    { Effect = "Allow", Action = "s3:PutObjectTagging", Resource = "${local.weather_arn}/observations/history/*" },
    { Effect = "Allow", Action = "dynamodb:UpdateItem", Resource = aws_dynamodb_table.runs.arn, Condition = local.observation_key },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.observations.arn}:*" }
  ] })
}
resource "aws_lambda_function" "observations" {
  function_name    = "${local.name}-observations"
  role             = aws_iam_role.observations.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "services.observations.handler.handler"
  memory_size      = 256
  timeout          = 90
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)
  environment { variables = { SKYCALM_BUCKET = aws_s3_bucket.app["weather"].id, SKYCALM_TABLE = aws_dynamodb_table.runs.name } }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.observations.name
  }
}
resource "aws_lambda_function_event_invoke_config" "observations" {
  function_name                = aws_lambda_function.observations.function_name
  maximum_event_age_in_seconds = 300
  maximum_retry_attempts       = 0
}
resource "aws_s3_object" "observation_replay" {
  for_each     = fileset(local.observation_archive, "gfs-*.json")
  bucket       = aws_s3_bucket.app["weather"].id
  key          = "archive/observations/${each.key}"
  source       = "${local.observation_archive}/${each.key}"
  source_hash  = filesha256("${local.observation_archive}/${each.key}")
  content_type = "application/json"
}
resource "aws_s3_object" "historical_reports" {
  for_each         = fileset("${var.archive_directory}/../observation-history", "day=*/*.json.gz")
  bucket           = aws_s3_bucket.app["weather"].id
  key              = "observations/history/${each.key}"
  source           = "${var.archive_directory}/../observation-history/${each.key}"
  source_hash      = filesha256("${var.archive_directory}/../observation-history/${each.key}")
  content_type     = "application/x-ndjson"
  content_encoding = "gzip"
}
