resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.name}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
resource "aws_cloudfront_cache_policy" "assets" {
  name        = "${local.name}-assets"
  min_ttl     = 0
  default_ttl = 3600
  max_ttl     = 31536000
  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}
# Classroom deployments opt in to the monthly ACL.
#trivy:ignore:AVD-AWS-0011
resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  comment             = "SkyCalm passenger forecast"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  is_ipv6_enabled     = true
  web_acl_id          = var.enable_edge_waf ? aws_wafv2_web_acl.web[0].arn : null
  origin {
    domain_name              = aws_s3_bucket.app["web"].bucket_regional_domain_name
    origin_id                = "private-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }
  dynamic "origin" {
    for_each = aws_lambda_function_url.forecast
    content {
      domain_name              = trimsuffix(trimprefix(origin.value.function_url, "https://"), "/")
      origin_id                = "signed-forecast"
      origin_access_control_id = aws_cloudfront_origin_access_control.forecast[0].id
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }
  dynamic "ordered_cache_behavior" {
    for_each = var.enable_edge_waf ? [1] : []
    content {
      path_pattern               = "/api/*"
      target_origin_id           = "signed-forecast"
      viewer_protocol_policy     = "https-only"
      allowed_methods            = ["GET", "HEAD"]
      cached_methods             = ["GET", "HEAD"]
      cache_policy_id            = data.aws_cloudfront_cache_policy.disabled[0].id
      origin_request_policy_id   = aws_cloudfront_origin_request_policy.forecast[0].id
      response_headers_policy_id = aws_cloudfront_response_headers_policy.web.id
      compress                   = true
    }
  }
  default_cache_behavior {
    target_origin_id           = "private-site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.web.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.passenger_pages.arn
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
  lifecycle {
    precondition {
      condition     = fileexists("${var.web_directory}/index.html")
      error_message = "Build the passenger app with npm run build in web/ first."
    }
  }
}
locals {
  mime_types = {
    html  = "text/html; charset=utf-8", css = "text/css", js = "text/javascript",
    json  = "application/json", jsonl = "application/x-ndjson", geojson = "application/geo+json", svg = "image/svg+xml",
    woff2 = "font/woff2", txt = "text/plain; charset=utf-8", png = "image/png", webmanifest = "application/manifest+json"
  }
  site_files = setsubtract(fileset(var.web_directory, "**"), ["config.json"])
}
resource "aws_s3_object" "site" {
  for_each      = local.site_files
  bucket        = aws_s3_bucket.app["web"].id
  key           = each.key
  source        = "${var.web_directory}/${each.key}"
  source_hash   = filesha256("${var.web_directory}/${each.key}")
  content_type  = lookup(local.mime_types, reverse(split(".", each.key))[0], "application/octet-stream")
  cache_control = startswith(each.key, "assets/") ? "public, max-age=31536000, immutable" : (each.key == "index.html" ? "no-store" : "public, max-age=3600")
}
resource "aws_s3_object" "runtime" {
  bucket        = aws_s3_bucket.app["web"].id
  key           = "config.json"
  content       = jsonencode({ apiOrigin = aws_apigatewayv2_api.forecast.api_endpoint, publicApiOrigin = var.enable_edge_waf ? "" : aws_apigatewayv2_api.forecast.api_endpoint, auth = { domain = "https://${local.login_prefix}.auth.${local.region}.amazoncognito.com", issuer = "https://${aws_cognito_user_pool.passengers.endpoint}", clientId = aws_cognito_user_pool_client.passengers.id, vapidPublicKey = var.passenger_settings.vapid_public } })
  content_type  = "application/json"
  cache_control = "no-store"
}
output "website" { value = "https://${aws_cloudfront_distribution.web.domain_name}" }
