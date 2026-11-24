variable "observation_window" {
  description = "Optional UTC demonstration window for half-hourly AWC capture (maximum two hours)."
  type        = object({ start = string, end = string })
  default     = null
  validation {
    condition = var.observation_window == null ? true : try(
      endswith(var.observation_window.start, "Z") && endswith(var.observation_window.end, "Z") &&
      timecmp(var.observation_window.end, var.observation_window.start) > 0 &&
      timecmp(var.observation_window.end, timeadd(var.observation_window.start, "2h")) <= 0, false
    )
    error_message = "Supply UTC start and end times no more than two hours apart."
  }
}
resource "aws_iam_role" "observation_schedule" {
  count = var.observation_window == null ? 0 : 1
  name  = "${local.name}-observation-clock"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = { StringEquals = { "aws:SourceAccount" = var.account_id,
    "aws:SourceArn" = "arn:aws:scheduler:${local.region}:${var.account_id}:schedule-group/default" } }
  }] })
}
resource "aws_iam_role_policy" "observation_schedule" {
  count = length(aws_iam_role.observation_schedule)
  name  = "invoke-weather-capture"
  role  = aws_iam_role.observation_schedule[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.observations.arn
  }] })
}
resource "aws_scheduler_schedule" "observations" {
  count               = var.observation_window == null ? 0 : 1
  name                = "${local.name}-observation-window"
  schedule_expression = "rate(30 minutes)"
  start_date          = var.observation_window.start
  end_date            = var.observation_window.end
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.observations.arn
    role_arn = aws_iam_role.observation_schedule[0].arn
    retry_policy {
      maximum_event_age_in_seconds = 120
      maximum_retry_attempts       = 0
    }
  }
}
