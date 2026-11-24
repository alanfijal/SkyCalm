locals {
  lambda_trust = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }] })
  job_keys     = { "ForAllValues:StringLike" = { "dynamodb:LeadingKeys" = ["job#*"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  lease_keys   = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["active"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  head_keys    = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["latest#ti1-cape-v1"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  job_update   = { Effect = "Allow", Action = "dynamodb:UpdateItem", Resource = aws_dynamodb_table.jobs.arn, Condition = local.job_keys }
  get_tiles    = { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/runs/ti1-cape-v1/*", "${local.weather_arn}/pipeline/jobs/replay-*/*"] }
  allow_events = { Effect = "Allow", Action = "events:PutEvents", Resource = aws_cloudwatch_event_bus.forecast.arn, Condition = { StringEquals = { "events:source" = "skycalm.forecast", "events:detail-type" = "forecast.run.available" } } }
  actions = {
    admission = [
      { Effect = "Allow", Action = "states:StartExecution", Resource = local.machine_arn },
      { Effect = "Allow", Action = "states:DescribeExecution", Resource = local.execution_arn }
    ],
    workflow = [
      local.job_update,
      { Effect = "Allow", Action = ["dynamodb:UpdateItem", "dynamodb:DeleteItem"], Resource = aws_dynamodb_table.jobs.arn, Condition = local.lease_keys },
      { Effect = "Allow", Action = "dynamodb:UpdateItem", Resource = local.runs_arn, Condition = local.head_keys },
      { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/runs/ti1-cape-v1/*/manifest.json", "${local.weather_arn}/pipeline/jobs/replay-*/manifest.json"] }
    ],
    routes   = [local.get_tiles, local.job_update],
    audit    = [local.job_update, { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.weather_arn}/pipeline/receipts/*" }],
    discover = [local.allow_events, { Effect = "Allow", Action = "dynamodb:GetItem", Resource = local.runs_arn, Condition = local.head_keys }]
  }
}
resource "aws_iam_role" "function" {
  for_each           = local.functions
  name               = "${local.prefix}-${each.key}"
  assume_role_policy = local.lambda_trust
}
resource "aws_iam_role_policy" "function" {
  for_each = local.functions
  name     = "run-${each.key}"
  role     = aws_iam_role.function[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat(
    [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.function[each.key].arn}:*" }],
    local.actions[each.key],
    contains(local.consumers, each.key) ? [{ Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.work[each.key].arn }] : []
  ) })
}
resource "aws_iam_role" "workflow" {
  name               = "${local.prefix}-states"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "states.amazonaws.com" }, Condition = { StringEquals = { "aws:SourceAccount" = var.account_id }, ArnEquals = { "aws:SourceArn" = local.machine_arn } } }] })
}
resource "aws_iam_role_policy" "workflow" {
  name = "run-one-grid"
  role = aws_iam_role.workflow.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.run["workflow"].arn },
    { Effect = "Allow", Action = "ecs:RunTask", Resource = var.task_arn, Condition = { ArnEquals = { "ecs:cluster" = var.cluster_arn } } },
    { Effect = "Allow", Action = ["ecs:DescribeTasks", "ecs:StopTask"], Resource = "arn:aws:ecs:${var.region}:${var.account_id}:task/${var.name}-grid/*" },
    { Effect = "Allow", Action = "iam:PassRole", Resource = [var.grid_role_arn, var.execution_role_arn], Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } },
    { Effect = "Allow", Action = ["events:PutTargets", "events:PutRule", "events:DescribeRule"], Resource = "arn:aws:events:${var.region}:${var.account_id}:rule/StepFunctionsGetEventsForECSTaskRule" },
    { Effect = "Allow", Action = "events:PutEvents", Resource = aws_cloudwatch_event_bus.forecast.arn, Condition = { StringEquals = { "events:source" = "skycalm.forecast", "events:detail-type" = "forecast.tiles.ready" } } }
  ] })
}
resource "aws_iam_policy" "operator" {
  name        = "${local.prefix}-operator"
  description = "Invoke classroom actions and inspect SkyCalm health with temporary AWS credentials."
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "events:PutEvents", Resource = aws_cloudwatch_event_bus.forecast.arn, Condition = { StringEquals = { "events:source" = "skycalm.forecast", "events:detail-type" = ["forecast.run.available", "forecast.delivery.test"] } } },
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.run["discover"].arn },
    { Effect = "Allow", Action = ["states:DescribeExecution", "states:RedriveExecution"], Resource = local.execution_arn },
    { Effect = "Allow", Action = "dynamodb:GetItem", Resource = aws_dynamodb_table.jobs.arn, Condition = { "ForAllValues:StringLike" = { "dynamodb:LeadingKeys" = ["job#*", "active"] }, Null = { "dynamodb:LeadingKeys" = "false" } } },
    { Effect = "Allow", Action = "dynamodb:GetItem", Resource = local.runs_arn, Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["latest#ti1-cape-v1", "observations#awc"] }, Null = { "dynamodb:LeadingKeys" = "false" } } },
    { Effect = "Allow", Action = "sqs:GetQueueAttributes", Resource = concat([for q in aws_sqs_queue.work : q.arn], [for q in aws_sqs_queue.dead : q.arn]) },
    { Effect = "Allow", Action = "cloudwatch:DescribeAlarms", Resource = "arn:aws:cloudwatch:${var.region}:${var.account_id}:alarm:${local.prefix}-*" }
  ] })
}
output "operator_policy" { value = aws_iam_policy.operator.arn }
