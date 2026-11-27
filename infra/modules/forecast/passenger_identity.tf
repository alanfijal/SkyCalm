variable "passenger_settings" {
  type = object({
    google_ready    = bool
    classroom_email = string
    login_email     = optional(string)
  })
  default = { google_ready = false, classroom_email = "" }
}
locals {
  passenger_login_email = trimspace(var.passenger_settings.login_email != null ? var.passenger_settings.login_email : var.passenger_settings.classroom_email)
  passenger_name        = "${local.name}-passengers"
  login_prefix          = "${local.name}-${var.account_id}"
  callback              = "https://${aws_cloudfront_distribution.web.domain_name}/"
  passenger_scopes      = { "flights.read" = "Read your private flights and inbox", "flights.write" = "Manage your flights and account", "notifications.write" = "Manage your alert preferences", admin = "Operate classroom replays" }
}
resource "aws_secretsmanager_secret" "passenger" {
  for_each                = toset(["google"])
  name                    = "${local.name}/passengers/${each.key}"
  recovery_window_in_days = 7
  description             = "SkyCalm passenger provider configuration provisioned outside Terraform"
}
resource "aws_cognito_user_pool" "passengers" {
  name                     = local.passenger_name
  user_pool_tier           = "ESSENTIALS"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  lambda_config { pre_sign_up = aws_lambda_function.passenger_admission.arn }
  username_configuration { case_sensitive = false }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 2
  }
  email_configuration { email_sending_account = "COGNITO_DEFAULT" }
}
resource "aws_cognito_user_pool_domain" "passengers" {
  domain                = local.login_prefix
  user_pool_id          = aws_cognito_user_pool.passengers.id
  managed_login_version = 2
}
resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.passengers.id
}
resource "aws_cognito_resource_server" "passengers" {
  user_pool_id = aws_cognito_user_pool.passengers.id
  identifier   = "skycalm"
  name         = "SkyCalm passenger API"
  dynamic "scope" {
    for_each = local.passenger_scopes
    content {
      scope_name        = scope.key
      scope_description = scope.value
    }
  }
}
# CloudFormation resolves the provider credentials directly from Secrets Manager.
resource "aws_cloudformation_stack" "google" {
  count = var.passenger_settings.google_ready ? 1 : 0
  name  = "${local.name}-google-login"
  template_body = jsonencode({
    AWSTemplateFormatVersion = "2010-09-09"
    Resources = { Google = { Type = "AWS::Cognito::UserPoolIdentityProvider", Properties = {
      UserPoolId = aws_cognito_user_pool.passengers.id, ProviderName = "Google", ProviderType = "Google",
      ProviderDetails = { authorize_scopes = "openid email profile",
        client_id = "{{resolve:secretsmanager:${aws_secretsmanager_secret.passenger["google"].name}:SecretString:client_id}}",
      client_secret = "{{resolve:secretsmanager:${aws_secretsmanager_secret.passenger["google"].name}:SecretString:client_secret}}" },
      AttributeMapping = { email = "email", email_verified = "email_verified" }
    } } }
  })
}
resource "aws_cognito_user_pool_client" "passengers" {
  name                                 = "${local.name}-web"
  user_pool_id                         = aws_cognito_user_pool.passengers.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = concat(["openid", "email", "aws.cognito.signin.user.admin"], sort(tolist(aws_cognito_resource_server.passengers.scope_identifiers)))
  supported_identity_providers         = var.passenger_settings.google_ready ? ["COGNITO", "Google"] : ["COGNITO"]
  callback_urls                        = [local.callback]
  logout_urls                          = [local.callback]
  explicit_auth_flows                  = ["ALLOW_USER_SRP_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 15
  id_token_validity                    = 15
  refresh_token_validity               = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = 5
  }
  depends_on = [aws_cloudformation_stack.google]
}
resource "aws_cognito_managed_login_branding" "passengers" {
  user_pool_id                = aws_cognito_user_pool.passengers.id
  client_id                   = aws_cognito_user_pool_client.passengers.id
  use_cognito_provided_values = true
}
resource "aws_sesv2_email_identity" "classroom" {
  count          = var.passenger_settings.classroom_email != "" ? 1 : 0
  email_identity = var.passenger_settings.classroom_email
}
