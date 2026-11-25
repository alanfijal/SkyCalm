output "bus_name" { value = aws_cloudwatch_event_bus.forecast.name }
output "table_name" { value = aws_dynamodb_table.jobs.name }
output "table_arn" { value = aws_dynamodb_table.jobs.arn }
output "queue_urls" {
  value = merge({ for k, q in aws_sqs_queue.work : k => q.url }, { for k, q in aws_sqs_queue.dead : "${k}-dlq" => q.url })
}
output "queue_arns" { value = concat([for q in aws_sqs_queue.work : q.arn], [for q in aws_sqs_queue.dead : q.arn]) }
