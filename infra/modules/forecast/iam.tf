locals {
  weather_arn = aws_s3_bucket.app["weather"].arn
  # S3 returns 404 for missing runs only when the caller can list this bucket.
  find_weather = { Effect = "Allow", Action = "s3:ListBucket", Resource = local.weather_arn }
  head_key     = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["latest#ti1-cape-v1"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  ecs_trust = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = {
      StringEquals = { "aws:SourceAccount" = var.account_id },
      ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${local.region}:${var.account_id}:*" }
    }
  }] })
}
resource "aws_iam_role" "task" {
  for_each           = toset(["execution", "grid"])
  name               = "${local.name}-${each.key}"
  assume_role_policy = local.ecs_trust
}
resource "aws_iam_role_policy" "pull_and_log" {
  name = "pull-grid-and-write-logs"
  role = aws_iam_role.task["execution"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = local.ecr_arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.grid.arn}:*" }
  ] })
}
resource "aws_iam_role_policy" "publish" {
  name = "publish-completed-runs"
  role = aws_iam_role.task["grid"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    local.find_weather,
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${local.weather_arn}/runs/ti1-cape-v1/*" },
    { Effect = "Allow", Action = "dynamodb:UpdateItem", Resource = aws_dynamodb_table.runs.arn, Condition = local.head_key }
  ] })
}
resource "aws_iam_role" "forecast" {
  name = "${local.name}-forecast"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "forecast" {
  name = "read-weather-and-write-logs"
  role = aws_iam_role.forecast.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    local.find_weather,
    { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/runs/ti1-cape-v1/*", "${local.weather_arn}/archive/ti1-cape-v1/*"] },
    { Effect = "Allow", Action = "dynamodb:GetItem", Resource = aws_dynamodb_table.runs.arn, Condition = local.head_key },
    { Effect = "Allow", Action = "dynamodb:GetItem", Resource = aws_dynamodb_table.runs.arn, Condition = local.observation_key },
    { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/observations/snapshots/*", "${local.weather_arn}/archive/observations/*"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.forecast.arn}:*" }
  ] })
}
