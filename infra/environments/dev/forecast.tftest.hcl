mock_provider "aws" {}
variables {
  account_id   = "123456789012"
  image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
run "compose_environment" {
  command = plan
}
run "forecast_controls" {
  command = plan
  module { source = "../../modules/forecast" }
  variables {
    lambda_zip        = "../../../build/forecast.zip"
    web_directory     = "../../../web/dist"
    archive_directory = "../../../services/forecast/data/replay"
  }
  assert {
    condition     = aws_ecs_task_definition.grid.cpu == "1024" && aws_ecs_task_definition.grid.memory == "2048" && aws_vpc_security_group_egress_rule.https.to_port == 443
    error_message = "The grid task must stay within its compute and outbound HTTPS limits."
  }
  assert {
    condition     = length(aws_apigatewayv2_route.forecast) == 4 && aws_lambda_function.forecast.timeout == 15 && aws_cloudwatch_log_group.api.retention_in_days == 7
    error_message = "Check the public API route count, timeout and log retention."
  }
  assert {
    condition     = length(aws_s3_object.replay) == 70 && length(aws_s3_object.observation_replay) == 5 && length(aws_s3_object.historical_reports) == 5 && aws_dynamodb_table.runs.billing_mode == "PAY_PER_REQUEST" && aws_cloudfront_origin_access_control.web.signing_behavior == "always"
    error_message = "The archive needs its 13 leads and manifest, a pay-per-request index and a signed web origin."
  }
  assert {
    condition     = aws_athena_workgroup.observations.configuration[0].enforce_workgroup_configuration && aws_athena_workgroup.observations.configuration[0].bytes_scanned_cutoff_per_query == 10485760
    error_message = "The weather queries need a workgroup-enforced 10 MiB scan limit."
  }
}
run "reject_mutable_image" {
  command = plan
  variables { image_digest = "latest" }
  expect_failures = [var.image_digest]
}
