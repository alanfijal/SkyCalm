resource "aws_apigatewayv2_api" "forecast" {
  name          = "${local.name}-forecast"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["https://${aws_cloudfront_distribution.web.domain_name}"]
    allow_methods = ["GET"]
    max_age       = 3600
  }
}
resource "aws_cloudwatch_log_group" "api" {
  name              = "/apigateway/${local.name}-forecast"
  retention_in_days = 7
}
resource "aws_apigatewayv2_stage" "forecast" {
  api_id      = aws_apigatewayv2_api.forecast.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format          = jsonencode({ requestId = "$context.requestId", route = "$context.routeKey", status = "$context.status" })
  }
}
resource "aws_apigatewayv2_integration" "forecast" {
  api_id                 = aws_apigatewayv2_api.forecast.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.forecast.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 16000
}
resource "aws_apigatewayv2_route" "forecast" {
  for_each  = toset(["/api/airports", "/api/runs", "/api/forecast", "/api/observations"])
  api_id    = aws_apigatewayv2_api.forecast.id
  route_key = "GET ${each.key}"
  target    = "integrations/${aws_apigatewayv2_integration.forecast.id}"
}
resource "aws_lambda_permission" "api" {
  for_each      = aws_apigatewayv2_route.forecast
  statement_id  = "AllowGet-${basename(each.key)}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.forecast.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.forecast.execution_arn}/$default/GET${each.key}"
}
output "api" { value = aws_apigatewayv2_api.forecast.api_endpoint }
