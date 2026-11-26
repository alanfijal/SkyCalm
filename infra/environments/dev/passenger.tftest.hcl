mock_provider "aws" {}
variables {
  lambda_image_digests = { python = "sha256:1111111111111111111111111111111111111111111111111111111111111111", push = "sha256:2222222222222222222222222222222222222222222222222222222222222222" }
  account_id           = "123456789012"
  image_digest         = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

  web_directory      = "../../../web/dist"
  archive_directory  = "../../../services/forecast/data/replay"
  passenger_settings = { google_ready = true, vapid_public = "classroom-public-key", classroom_email = "team@example.edu", login_email = "presenter@example.com" }
}
run "passenger_controls" {
  command = plan
  module { source = "../../modules/forecast" }
  assert {
    condition = alltrue([for f in concat(
      [aws_lambda_function.forecast, aws_lambda_function.observations, aws_lambda_function.passenger_admission],
      values(aws_lambda_function.passenger)
      ) : f.package_type == "Image" && one(f.architectures) == "arm64" && length(one(f.image_config).command) == 1]) && (
      aws_lambda_function.passenger["push"].image_uri != aws_lambda_function.passenger["worker"].image_uri &&
      aws_lambda_function.passenger["worker"].environment[0].variables["PUSH_FUNCTION"] == aws_lambda_function.passenger["push"].function_name
    )
    error_message = "The passenger functions must launch the right ARM64 runtime and target the image-based push sender."
  }
  assert {
    condition = (
      aws_lambda_function.passenger_admission.environment[0].variables["CLASSROOM_EMAIL"] == "presenter@example.com" &&
      aws_lambda_function.passenger["api"].environment[0].variables["CLASSROOM_EMAIL"] == "presenter@example.com" &&
      aws_lambda_function.passenger["api"].environment[0].variables["SES_RECIPIENT"] == "team@example.edu" &&
      aws_sesv2_email_identity.classroom[0].email_identity == "team@example.edu"
    )
    error_message = "The sign-in invite and the verified email destination must be independently configurable."
  }
  assert {
    condition     = aws_cognito_user_pool_client.passengers.allowed_oauth_flows == toset(["code"]) && !aws_cognito_user_pool_client.passengers.generate_secret && aws_cognito_user_pool_client.passengers.refresh_token_rotation[0].feature == "ENABLED"
    error_message = "A public PKCE client requires code flow and rotating refresh tokens."
  }
  assert {
    condition     = aws_apigatewayv2_route.shared_forecast.route_key == "POST /api/shared" && aws_apigatewayv2_route.shared_forecast.authorization_type == "NONE" && length(aws_apigatewayv2_route.passengers) == 14 && alltrue([for r in aws_apigatewayv2_route.passengers : r.authorization_type == "JWT" && length(r.authorization_scopes) == 1])
    error_message = "Every private route must require its access scope."
  }
  assert {
    condition     = aws_dynamodb_table.passengers.ttl[0].enabled && aws_sqs_queue.passenger_work.visibility_timeout_seconds >= 6 * aws_lambda_function.passenger["worker"].timeout && length(aws_cloudformation_stack.google) == 1 && length(aws_sesv2_email_identity.classroom) == 1
    error_message = "Check retention, queue retry timing and the classroom providers."
  }
}

run "enable_dated_flight_search" {
  command = plan
  module { source = "../../modules/forecast" }
  variables { enable_flight_lookup = true }
  assert {
    condition = (
      aws_dynamodb_table.flight_lookup[0].billing_mode == "PAY_PER_REQUEST" &&
      aws_dynamodb_table.flight_lookup[0].ttl[0].attribute_name == "expiresAt" &&
      aws_apigatewayv2_route.passengers["POST /api/me/flight-lookup"].authorization_scopes == toset(["skycalm/flights.read"]) &&
      aws_apigatewayv2_route.passengers["POST /api/me/flight-lookup"].authorization_type == "JWT" &&
      aws_lambda_function.passenger["api"].environment[0].variables["FLIGHT_LOOKUP_TABLE"] == aws_dynamodb_table.flight_lookup[0].name &&
      !contains(keys(aws_lambda_function.passenger["worker"].environment[0].variables), "FLIGHT_LOOKUP_PARAMETER") &&
      aws_cloudwatch_event_rule.expire_flight_cache[0].schedule_expression == "rate(1 day)"
    )
    error_message = "Dated flight searches require passenger identity, an expiring on-demand cache, and a bounded daily cleanup."
  }
}
