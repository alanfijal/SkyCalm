locals {
  push_zip = abspath("${dirname(var.lambda_zip)}/push.zip")
  passenger_functions = {
    api    = { handler = "services.passengers.api.handler", timeout = 25, memory = 256 },
    worker = { handler = "services.passengers.worker.worker", timeout = 55, memory = 512 },
    stream = { handler = "services.passengers.worker.stream", timeout = 40, memory = 256 },
    push   = { handler = "index.handler", timeout = 12, memory = 128 }
  }
  health_queues = merge(module.pipeline.queue_urls, { passengers = aws_sqs_queue.passenger_work.url, "passengers-dlq" = aws_sqs_queue.passenger_dead.url })
}
resource "aws_cloudwatch_log_group" "passenger" {
  for_each          = local.passenger_functions
  name              = "/aws/lambda/${local.passenger_name}-${each.key}"
  retention_in_days = 7
}
resource "aws_lambda_function" "passenger" {
  for_each         = local.passenger_functions
  function_name    = "${local.passenger_name}-${each.key}"
  role             = aws_iam_role.passenger[each.key].arn
  handler          = each.value.handler
  timeout          = each.value.timeout
  memory_size      = each.value.memory
  architectures    = ["arm64"]
  runtime          = each.key == "push" ? "nodejs24.x" : "python3.12"
  filename         = each.key == "push" ? local.push_zip : var.lambda_zip
  source_code_hash = try(filebase64sha256(each.key == "push" ? local.push_zip : var.lambda_zip), null)
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.passenger[each.key].name
  }
  environment {
    variables = each.key == "push" ? tomap({ VAPID_SECRET = aws_secretsmanager_secret.passenger["vapid"].arn, VAPID_SUBJECT = var.passenger_settings.classroom_email == "" ? local.callback : "mailto:${var.passenger_settings.classroom_email}" }) : merge({
      PASSENGERS     = aws_dynamodb_table.passengers.name, PIPELINE_BUS = module.pipeline.bus_name, PIPELINE_TABLE = module.pipeline.table_name,
      SKYCALM_BUCKET = aws_s3_bucket.app["weather"].id, SKYCALM_TABLE = aws_dynamodb_table.runs.name,
      USER_POOL      = aws_cognito_user_pool.passengers.id, SES_FROM = var.passenger_settings.classroom_email, SES_RECIPIENT = var.passenger_settings.classroom_email,
      WORK_QUEUE     = aws_sqs_queue.passenger_work.url, WORK_ARN = aws_sqs_queue.passenger_work.arn, DEAD_ARN = aws_sqs_queue.passenger_dead.arn,
      SCHEDULE_GROUP = aws_scheduler_schedule_group.passengers.name, SCHEDULER_ROLE = aws_iam_role.reminders.arn,
      PUSH_FUNCTION  = "${local.passenger_name}-push", HEALTH_QUEUES = jsonencode(local.health_queues)
    }, each.key == "api" ? { CLASSROOM_EMAIL = local.passenger_login_email } : {})
  }
  lifecycle {
    precondition {
      condition     = fileexists(each.key == "push" ? local.push_zip : var.lambda_zip)
      error_message = "Build the passenger push and forecast Lambda packages first."
    }
  }
}
