resource "aws_iam_role" "passenger" {
  for_each           = local.passenger_functions
  name               = "${local.passenger_name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role" "reminders" {
  name = "${local.passenger_name}-reminders"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole",
  Condition = { StringEquals = { "aws:SourceAccount" = var.account_id }, ArnEquals = { "aws:SourceArn" = aws_scheduler_schedule_group.passengers.arn } } }] })
}
resource "aws_iam_role_policy" "reminders" {
  role   = aws_iam_role.reminders.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sqs:SendMessage", Resource = [aws_sqs_queue.passenger_work.arn, aws_sqs_queue.passenger_dead.arn] }] })
}
locals {
  passenger_db = aws_dynamodb_table.passengers.arn
  bus_arn      = "arn:aws:events:${local.region}:${var.account_id}:event-bus/${module.pipeline.bus_name}"
  read_flights = { Effect = "Allow", Action = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"], Resource = local.passenger_db }
  private_permissions = {
    api = concat([local.read_flights,
      { Effect = "Allow", Action = "dynamodb:DeleteItem", Resource = local.passenger_db },
      { Effect = "Allow", Action = "cognito-idp:AdminDeleteUser", Resource = aws_cognito_user_pool.passengers.arn },
      { Effect = "Allow", Action = "events:PutEvents", Resource = local.bus_arn, Condition = { StringEquals = { "events:source" = "skycalm.forecast", "events:detail-type" = ["forecast.run.available", "passenger.change.test"] } } },
      { Effect = "Allow", Action = "dynamodb:GetItem", Resource = [aws_dynamodb_table.runs.arn, module.pipeline.table_arn] },
      { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/runs/ti1-cape-v1/*/manifest.json", "${local.weather_arn}/observations/snapshots/*"] },
      { Effect = "Allow", Action = "s3:ListBucket", Resource = local.weather_arn, Condition = { StringLike = { "s3:prefix" = "observations/snapshots/????-??-??" } } },
    { Effect = "Allow", Action = "sqs:GetQueueAttributes", Resource = concat(module.pipeline.queue_arns, [aws_sqs_queue.passenger_work.arn, aws_sqs_queue.passenger_dead.arn]) }]),
    worker = concat([local.read_flights,
      { Effect = "Allow", Action = "dynamodb:GetItem", Resource = aws_dynamodb_table.runs.arn },
      { Effect = "Allow", Action = "dynamodb:Query", Resource = "${local.passenger_db}/index/departures" },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:SendMessage"], Resource = aws_sqs_queue.passenger_work.arn },
      { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.weather_arn}/runs/*", "${local.weather_arn}/pipeline/jobs/replay-*/*"] },
      ], var.passenger_settings.classroom_email == "" ? [] : [{ Effect = "Allow", Action = "ses:SendEmail", Resource = aws_sesv2_email_identity.classroom[0].arn,
    Condition = { StringEquals = { "ses:FromAddress" = var.passenger_settings.classroom_email }, "ForAllValues:StringEquals" = { "ses:Recipients" = [var.passenger_settings.classroom_email] }, Null = { "ses:Recipients" = "false" } } }]),
    stream = [
      { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.passenger_work.arn },
      { Effect = "Allow", Action = ["dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:DescribeStream", "dynamodb:ListStreams"], Resource = aws_dynamodb_table.passengers.stream_arn },
      { Effect = "Allow", Action = "dynamodb:GetItem", Resource = local.passenger_db },
      { Effect = "Allow", Action = "events:PutEvents", Resource = local.bus_arn, Condition = { StringEquals = { "events:source" = "skycalm.forecast", "events:detail-type" = "passenger.notice.ready" } } },
      { Effect = "Allow", Action = ["scheduler:CreateSchedule", "scheduler:GetSchedule", "scheduler:DeleteSchedule"], Resource = "arn:aws:scheduler:${local.region}:${var.account_id}:schedule/${aws_scheduler_schedule_group.passengers.name}/f-*" },
      { Effect = "Allow", Action = "iam:PassRole", Resource = aws_iam_role.reminders.arn, Condition = { StringEquals = { "iam:PassedToService" = "scheduler.amazonaws.com" } } },
    { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.passenger_dead.arn }],
  }
}
resource "aws_iam_role_policy" "passenger" {
  for_each = local.passenger_functions
  role     = aws_iam_role.passenger[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat(local.private_permissions[each.key], [{
    Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.passenger[each.key].arn}:*"
  }]) })
}
