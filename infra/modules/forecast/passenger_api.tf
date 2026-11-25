locals {
  private_routes = {
    "GET /api/me"             = "flights.read", "GET /api/me/export" = "flights.read", "DELETE /api/me" = "flights.write",
    "PUT /api/me/preferences" = "notifications.write", "PUT /api/me/flights/{slot}" = "flights.write", "DELETE /api/me/flights/{slot}" = "flights.write",
    "GET /api/admin/health"   = "admin", "GET /api/admin/jobs/{job}" = "admin", "POST /api/admin/actions" = "admin"
  }
}
resource "aws_apigatewayv2_authorizer" "passengers" {
  api_id           = aws_apigatewayv2_api.forecast.id
  name             = "passenger-access"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = "https://${aws_cognito_user_pool.passengers.endpoint}"
    audience = [aws_cognito_user_pool_client.passengers.id]
  }
}
resource "aws_apigatewayv2_integration" "passengers" {
  api_id                 = aws_apigatewayv2_api.forecast.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.passenger["api"].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 26000
}
resource "aws_apigatewayv2_route" "passengers" {
  for_each             = local.private_routes
  api_id               = aws_apigatewayv2_api.forecast.id
  route_key            = each.key
  target               = "integrations/${aws_apigatewayv2_integration.passengers.id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.passengers.id
  authorization_scopes = ["skycalm/${each.value}"]
}
resource "aws_lambda_permission" "passengers" {
  for_each      = local.private_routes
  statement_id  = "AllowRoute-${substr(sha256(each.key), 0, 16)}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.passenger["api"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.forecast.execution_arn}/$default/${split(" ", each.key)[0]}${replace(replace(split(" ", each.key)[1], "{slot}", "*"), "{job}", "*")}"
}
