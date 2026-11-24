locals {
  consumers    = toset(["admission", "routes", "audit"])
  dead_letters = setunion(local.consumers, toset(["delivery"]))
}
resource "aws_sqs_queue" "dead" {
  for_each                  = local.dead_letters
  name                      = "${local.prefix}-${each.key}-dlq"
  message_retention_seconds = 604800
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "work" {
  for_each                   = local.consumers
  name                       = "${local.prefix}-${each.key}"
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = 90
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead[each.key].arn, maxReceiveCount = 3 })
}
resource "aws_sqs_queue_redrive_allow_policy" "consumers" {
  for_each             = local.consumers
  queue_url            = aws_sqs_queue.dead[each.key].id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.work[each.key].arn] })
}
