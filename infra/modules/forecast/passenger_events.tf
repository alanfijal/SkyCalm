resource "aws_dynamodb_table" "passengers" {
  name             = local.passenger_name
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  range_key        = "sk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
  dynamic "attribute" {
    for_each = { pk = "S", sk = "S", watch = "S", departureEpoch = "N" }
    content {
      name = attribute.key
      type = attribute.value
    }
  }
  global_secondary_index {
    name = "departures"
    key_schema {
      attribute_name = "watch"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "departureEpoch"
      key_type       = "RANGE"
    }
    projection_type    = "INCLUDE"
    non_key_attributes = ["slot", "revision"]
  }
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}
resource "aws_scheduler_schedule_group" "passengers" { name = local.passenger_name }
resource "aws_sqs_queue" "passenger_dead" {
  name                      = "${local.passenger_name}-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 86400
}
resource "aws_sqs_queue" "passenger_work" {
  name                       = local.passenger_name
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = 360
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 86400
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.passenger_dead.arn, maxReceiveCount = 3 })
}
resource "aws_sqs_queue_redrive_allow_policy" "passengers" {
  queue_url            = aws_sqs_queue.passenger_dead.url
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.passenger_work.arn] })
}
resource "aws_cloudwatch_event_rule" "passengers" {
  name           = local.passenger_name
  event_bus_name = module.pipeline.bus_name
  event_pattern  = jsonencode({ source = ["skycalm.forecast"], "detail-type" = ["forecast.tiles.ready", "passenger.notice.ready", "passenger.change.test"] })
}
resource "aws_sqs_queue_policy" "passengers" {
  for_each  = { work = aws_sqs_queue.passenger_work.url, dead = aws_sqs_queue.passenger_dead.url }
  queue_url = each.value
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage",
    Resource = each.key == "work" ? aws_sqs_queue.passenger_work.arn : aws_sqs_queue.passenger_dead.arn,
  Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.passengers.arn } } }] })
}
resource "aws_cloudwatch_event_target" "passengers" {
  event_bus_name = module.pipeline.bus_name
  rule           = aws_cloudwatch_event_rule.passengers.name
  arn            = aws_sqs_queue.passenger_work.arn
  target_id      = "passenger-forecasts"
  retry_policy {
    maximum_event_age_in_seconds = 300
    maximum_retry_attempts       = 3
  }
  dead_letter_config { arn = aws_sqs_queue.passenger_dead.arn }
  depends_on = [aws_sqs_queue_policy.passengers]
}
resource "aws_lambda_event_source_mapping" "passenger_work" {
  event_source_arn        = aws_sqs_queue.passenger_work.arn
  function_name           = aws_lambda_function.passenger["worker"].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  depends_on              = [aws_iam_role_policy.passenger]
}
resource "aws_lambda_event_source_mapping" "passenger_stream" {
  event_source_arn               = aws_dynamodb_table.passengers.stream_arn
  function_name                  = aws_lambda_function.passenger["stream"].arn
  starting_position              = "TRIM_HORIZON"
  batch_size                     = 10
  function_response_types        = ["ReportBatchItemFailures"]
  maximum_retry_attempts         = 5
  maximum_record_age_in_seconds  = 3600
  bisect_batch_on_function_error = true
  destination_config {
    on_failure { destination_arn = aws_sqs_queue.passenger_dead.arn }
  }
  depends_on = [aws_iam_role_policy.passenger]
}
resource "aws_cloudwatch_metric_alarm" "passenger_dead" {
  alarm_name          = "${local.passenger_name}-dlq"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.passenger_dead.name }
  statistic           = "Maximum"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  period              = 60
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
}
