resource "aws_wafv2_web_acl" "web" {
  count       = var.enable_edge_waf ? 1 : 0
  region      = "us-east-1"
  name        = "${local.name}-edge"
  description = "Common web protections and a per-IP limit on passenger forecast requests"
  scope       = "CLOUDFRONT"
  default_action {
    allow {}
  }

  rule {
    name     = "ForecastRate"
    priority = 0
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit                 = 100
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
        scope_down_statement {
          byte_match_statement {
            field_to_match {
              uri_path {}
            }
            positional_constraint = "EXACTLY"
            search_string         = "/api/forecast"
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SkyCalmForecastRate"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "CommonRules"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SkyCalmCommonRules"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "SkyCalmEdge"
    sampled_requests_enabled   = false
  }
}

resource "aws_lambda_function_url" "forecast" {
  count              = var.enable_edge_waf ? 1 : 0
  function_name      = aws_lambda_function.forecast.function_name
  authorization_type = "AWS_IAM"
}
resource "aws_cloudfront_origin_access_control" "forecast" {
  count                             = var.enable_edge_waf ? 1 : 0
  name                              = "${local.name}-forecast"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_lambda_permission" "edge_url" {
  count                  = var.enable_edge_waf ? 1 : 0
  statement_id           = "AllowSkyCalmDistributionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.forecast.function_name
  principal              = "cloudfront.amazonaws.com"
  function_url_auth_type = "AWS_IAM"
  source_arn             = aws_cloudfront_distribution.web.arn
}
resource "aws_lambda_permission" "edge_invoke" {
  count                    = var.enable_edge_waf ? 1 : 0
  statement_id             = "AllowSkyCalmDistributionInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.forecast.function_name
  principal                = "cloudfront.amazonaws.com"
  invoked_via_function_url = true
  source_arn               = aws_cloudfront_distribution.web.arn
}
data "aws_cloudfront_cache_policy" "disabled" {
  count = var.enable_edge_waf ? 1 : 0
  name  = "Managed-CachingDisabled"
}
resource "aws_cloudfront_origin_request_policy" "forecast" {
  count = var.enable_edge_waf ? 1 : 0
  name  = "${local.name}-forecast-query"
  cookies_config { cookie_behavior = "none" }
  headers_config { header_behavior = "none" }
  query_strings_config {
    query_string_behavior = "whitelist"
    query_strings { items = ["origin", "destination", "departure", "arrival", "run", "q", "wind"] }
  }
}
resource "aws_cloudfront_response_headers_policy" "web" {
  name = "${local.name}-browser"
  security_headers_config {
    content_type_options { override = true }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      override                   = true
    }
  }
}
