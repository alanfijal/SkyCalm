resource "aws_cloudwatch_event_bus" "forecast" { name = local.prefix }
locals {
  types    = { available = "forecast.run.available", ready = "forecast.tiles.ready", probe = "forecast.delivery.test" }
  bindings = { admit = { rule = "available", queue = "admission" }, route = { rule = "ready", queue = "routes" }, record = { rule = "ready", queue = "audit" }, test = { rule = "probe", queue = "routes" } }
}
resource "aws_cloudwatch_event_rule" "forecast" {
  for_each       = local.types
  name           = "${local.prefix}-${each.key}"
  event_bus_name = aws_cloudwatch_event_bus.forecast.name
  event_pattern  = jsonencode({ source = ["skycalm.forecast"], "detail-type" = [each.value] })
}
resource "aws_sqs_queue_policy" "work" {
  for_each  = local.consumers
  queue_url = aws_sqs_queue.work[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.work[each.key].arn,
  Condition = { ArnEquals = { "aws:SourceArn" = [for b in values(local.bindings) : aws_cloudwatch_event_rule.forecast[b.rule].arn if b.queue == each.key] } } }] })
}
resource "aws_sqs_queue_policy" "delivery" {
  queue_url = aws_sqs_queue.dead["delivery"].id
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.dead["delivery"].arn, Condition = { ArnEquals = { "aws:SourceArn" = [for r in aws_cloudwatch_event_rule.forecast : r.arn] } } }] })
}
resource "aws_cloudwatch_event_target" "queue" {
  for_each       = local.bindings
  event_bus_name = aws_cloudwatch_event_bus.forecast.name
  rule           = aws_cloudwatch_event_rule.forecast[each.value.rule].name
  arn            = aws_sqs_queue.work[each.value.queue].arn
  target_id      = each.key
  retry_policy {
    maximum_event_age_in_seconds = 300
    maximum_retry_attempts       = 3
  }
  dead_letter_config { arn = aws_sqs_queue.dead["delivery"].arn }
  depends_on = [aws_sqs_queue_policy.work, aws_sqs_queue_policy.delivery]
}
