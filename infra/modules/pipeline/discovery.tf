resource "aws_iam_role" "clock" {
  count              = var.discovery_window == null ? 0 : 1
  name               = "${local.prefix}-clock"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" }, Condition = { StringEquals = { "aws:SourceAccount" = var.account_id, "aws:SourceArn" = "arn:aws:scheduler:${var.region}:${var.account_id}:schedule-group/default" } } }] })
}
resource "aws_iam_role_policy" "clock" {
  count  = length(aws_iam_role.clock)
  name   = "check-noaa"
  role   = aws_iam_role.clock[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.run["discover"].arn }] })
}
resource "aws_scheduler_schedule" "discovery" {
  count               = length(aws_iam_role.clock)
  name                = "${local.prefix}-discovery"
  schedule_expression = "rate(15 minutes)"
  start_date          = var.discovery_window.start
  end_date            = var.discovery_window.end
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.run["discover"].arn
    role_arn = aws_iam_role.clock[0].arn
    retry_policy {
      maximum_event_age_in_seconds = 120
      maximum_retry_attempts       = 0
    }
  }
}
resource "aws_lambda_function_event_invoke_config" "discovery" {
  function_name                = aws_lambda_function.run["discover"].function_name
  maximum_event_age_in_seconds = 120
  maximum_retry_attempts       = 0
}
