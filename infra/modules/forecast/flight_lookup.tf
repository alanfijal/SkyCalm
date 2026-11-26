variable "enable_flight_lookup" {
  description = "Enable the signed-in flight schedule lookup after provisioning its standard SecureString."
  type        = bool
  default     = false
}

locals {
  flight_parameter = "/${local.name}/providers/aerodatabox"
}

resource "aws_dynamodb_table" "flight_lookup" {
  count        = var.enable_flight_lookup ? 1 : 0
  name         = "${local.name}-flight-lookup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

resource "aws_iam_role_policy" "flight_lookup" {
  count = var.enable_flight_lookup ? 1 : 0
  name  = "read-flight-schedules"
  role  = aws_iam_role.passenger["api"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan", "dynamodb:DeleteItem"], Resource = aws_dynamodb_table.flight_lookup[0].arn },
    { Effect = "Allow", Action = "ssm:GetParameter", Resource = "arn:aws:ssm:${local.region}:${var.account_id}:parameter${local.flight_parameter}" }
  ] })
}

resource "aws_cloudwatch_event_rule" "expire_flight_cache" {
  count               = var.enable_flight_lookup ? 1 : 0
  name                = "${local.name}-expire-flight-cache"
  schedule_expression = "rate(1 day)"
}
resource "aws_cloudwatch_event_target" "expire_flight_cache" {
  count = var.enable_flight_lookup ? 1 : 0
  rule  = aws_cloudwatch_event_rule.expire_flight_cache[0].name
  arn   = aws_lambda_function.passenger["api"].arn
  input = jsonencode({ task = "expire-flight-cache" })
}
resource "aws_lambda_permission" "expire_flight_cache" {
  count         = var.enable_flight_lookup ? 1 : 0
  statement_id  = "AllowScheduleCacheExpiry"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.passenger["api"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.expire_flight_cache[0].arn
}
