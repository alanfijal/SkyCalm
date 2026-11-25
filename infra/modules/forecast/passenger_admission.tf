resource "aws_iam_role" "passenger_admission" {
  name               = "${local.passenger_name}-admission"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_cloudwatch_log_group" "passenger_admission" {
  name              = "/aws/lambda/${local.passenger_name}-admission"
  retention_in_days = 7
}
resource "aws_iam_role_policy" "passenger_admission" {
  role   = aws_iam_role.passenger_admission.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.passenger_admission.arn}:*" }] })
}
resource "aws_lambda_function" "passenger_admission" {
  function_name = "${local.passenger_name}-admission-img"
  role          = aws_iam_role.passenger_admission.arn
  package_type  = "Image"
  image_uri     = local.lambda_images.python
  image_config { command = ["services.passengers.admission.handler"] }
  lifecycle { create_before_destroy = true }
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 3
  environment { variables = { CLASSROOM_EMAIL = local.passenger_login_email } }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.passenger_admission.name
  }
}
resource "aws_lambda_permission" "passenger_admission" {
  lifecycle { create_before_destroy = true }
  statement_id   = "ClassroomSignup"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.passenger_admission.function_name
  principal      = "cognito-idp.amazonaws.com"
  source_account = var.account_id
  source_arn     = aws_cognito_user_pool.passengers.arn
}
