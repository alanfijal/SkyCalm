locals {
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
  for_each      = local.passenger_functions
  function_name = "${local.passenger_name}-${each.key}-img"
  role          = aws_iam_role.passenger[each.key].arn
  timeout       = each.value.timeout
  memory_size   = each.value.memory
  package_type  = "Image"
  image_uri     = each.key == "push" ? local.lambda_images.push : local.lambda_images.python
  image_config { command = [each.value.handler] }
  lifecycle { create_before_destroy = true }
  architectures = ["arm64"]
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
      PUSH_FUNCTION  = "${local.passenger_name}-push-img", HEALTH_QUEUES = jsonencode(local.health_queues)
    }, each.key == "api" ? { CLASSROOM_EMAIL = local.passenger_login_email, PUBLIC_SITE = local.callback, PUBLIC_API = aws_apigatewayv2_api.forecast.api_endpoint } : {}, each.key == "worker" ? { INBOX_URL = "${local.callback}flights?view=inbox" } : {}, each.key == "api" && var.enable_flight_lookup ? { FLIGHT_LOOKUP_TABLE = aws_dynamodb_table.flight_lookup[0].name, FLIGHT_LOOKUP_PARAMETER = local.flight_parameter } : {})
  }
}
