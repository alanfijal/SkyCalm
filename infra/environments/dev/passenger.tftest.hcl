mock_provider "aws" {}
variables {
  account_id         = "123456789012"
  image_digest       = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  lambda_zip         = "../../../build/forecast.zip"
  web_directory      = "../../../web/dist"
  archive_directory  = "../../../services/forecast/data/replay"
  passenger_settings = { google_ready = true, vapid_public = "classroom-public-key", classroom_email = "team@example.edu" }
}
run "passenger_controls" {
  command = plan
  module { source = "../../modules/forecast" }
  assert {
    condition     = aws_cognito_user_pool_client.passengers.allowed_oauth_flows == toset(["code"]) && !aws_cognito_user_pool_client.passengers.generate_secret && aws_cognito_user_pool_client.passengers.refresh_token_rotation[0].feature == "ENABLED"
    error_message = "A public PKCE client requires code flow and rotating refresh tokens."
  }
  assert {
    condition     = length(aws_apigatewayv2_route.passengers) == 9 && alltrue([for r in aws_apigatewayv2_route.passengers : r.authorization_type == "JWT" && length(r.authorization_scopes) == 1])
    error_message = "Every private route must require its access scope."
  }
  assert {
    condition     = aws_dynamodb_table.passengers.ttl[0].enabled && aws_sqs_queue.passenger_work.visibility_timeout_seconds >= 6 * aws_lambda_function.passenger["worker"].timeout && length(aws_cloudformation_stack.google) == 1 && length(aws_sesv2_email_identity.classroom) == 1
    error_message = "Check retention, queue retry timing and the classroom providers."
  }
}
