mock_provider "aws" {}

variables {
  python_image = "123456789012.dkr.ecr.eu-north-1.amazonaws.com/skycalm/functions@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  name         = "skycalm-dev"
  account_id   = "123456789012"
  region       = "eu-north-1"

  weather_bucket     = "classroom-weather"
  runs_table         = "classroom-runs"
  task_arn           = "arn:aws:ecs:eu-north-1:123456789012:task-definition/grid:2"
  cluster_arn        = "arn:aws:ecs:eu-north-1:123456789012:cluster/classroom"
  execution_role_arn = "arn:aws:iam::123456789012:role/execution"
  grid_role_arn      = "arn:aws:iam::123456789012:role/grid"
  security_group     = "sg-0123456789abcdef0"
  subnet             = "subnet-0123456789abcdef0"
}

run "pipeline_controls" {
  command = plan
  module { source = "../../modules/pipeline" }
  assert {
    condition     = alltrue([for f in values(aws_lambda_function.run) : f.package_type == "Image" && f.image_uri == var.python_image && one(f.architectures) == "arm64" && length(one(f.image_config).command) == 1])
    error_message = "All five pipeline consumers must select a handler from the pinned Python image."
  }
  assert {
    condition     = length(aws_sqs_queue.work) == 3 && length(aws_sqs_queue.dead) == 4 && length(aws_cloudwatch_event_target.queue) == 4 && length(aws_lambda_event_source_mapping.consumer) == 3
    error_message = "Admission, route processing and audit require isolated delivery paths."
  }
  assert {
    condition     = alltrue([for key, queue in aws_sqs_queue.work : queue.visibility_timeout_seconds >= 6 * aws_lambda_function.run[key].timeout && queue.sqs_managed_sse_enabled]) && alltrue([for mapping in aws_lambda_event_source_mapping.consumer : contains(mapping.function_response_types, "ReportBatchItemFailures")])
    error_message = "Each consumer requires bounded retries and per-record failure handling."
  }
  assert {
    condition     = aws_sfn_state_machine.grid.type == "STANDARD" && length(aws_cloudwatch_metric_alarm.queue) == 6 && length(aws_cloudwatch_metric_alarm.workflow) == 2 && length(aws_scheduler_schedule.discovery) == 0
    error_message = "Use the durable workflow, alarm on delivery failures, and keep continuous discovery off."
  }
}
run "bounded_discovery" {
  command = plan
  module { source = "../../modules/pipeline" }
  variables { discovery_window = { start = "2027-01-02T06:00:00Z", end = "2027-01-02T08:00:00Z" } }
  assert {
    condition     = length(aws_scheduler_schedule.discovery) == 1 && aws_scheduler_schedule.discovery[0].end_date == var.discovery_window.end
    error_message = "The weather check must stop at the end of the rehearsal."
  }
}
run "reject_continuous_discovery" {
  command = plan
  module { source = "../../modules/pipeline" }
  variables { discovery_window = { start = "2027-01-02T06:00:00Z", end = "2027-01-03T06:00:00Z" } }
  expect_failures = [var.discovery_window]
}
