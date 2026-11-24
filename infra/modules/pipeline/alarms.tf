locals {
  queue_alarms = merge(
    { for k, q in aws_sqs_queue.dead : "${k}-dlq" => { queue = q.name, metric = "ApproximateNumberOfMessagesVisible", threshold = 1 } },
    { for k in ["admission", "routes"] : "${k}-age" => { queue = aws_sqs_queue.work[k].name, metric = "ApproximateAgeOfOldestMessage", threshold = 120 } }
  )
}
resource "aws_cloudwatch_metric_alarm" "queue" {
  for_each            = local.queue_alarms
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = "AWS/SQS"
  metric_name         = each.value.metric
  dimensions          = { QueueName = each.value.queue }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = each.value.threshold
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
}
resource "aws_cloudwatch_metric_alarm" "workflow" {
  for_each            = toset(["ExecutionsFailed", "ExecutionsTimedOut"])
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = "AWS/States"
  metric_name         = each.key
  dimensions          = { StateMachineArn = aws_sfn_state_machine.grid.arn }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
}
