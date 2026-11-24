locals {
  bucket_purposes = toset(["weather", "web"])
}
resource "aws_s3_bucket" "app" {
  for_each = local.bucket_purposes
  bucket   = "${local.name}-${each.key}-${var.account_id}-${local.region}"
}
resource "aws_s3_bucket_public_access_block" "app" {
  for_each                = local.bucket_purposes
  bucket                  = aws_s3_bucket.app[each.key].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "app" {
  for_each = local.bucket_purposes
  bucket   = aws_s3_bucket.app[each.key].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
# The buckets hold public weather and site assets. SSE-S3 avoids a per-key charge.
#trivy:ignore:AVD-AWS-0132
resource "aws_s3_bucket_server_side_encryption_configuration" "app" {
  for_each = local.bucket_purposes
  bucket   = aws_s3_bucket.app[each.key].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "app" {
  for_each = local.bucket_purposes
  bucket   = aws_s3_bucket.app[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.app[each.key].arn, "${aws_s3_bucket.app[each.key].arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }], each.key == "web" ? [{
    Effect    = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject",
    Resource  = "${aws_s3_bucket.app[each.key].arn}/*",
    Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.web.arn } }
  }] : []) })
  depends_on = [aws_s3_bucket_public_access_block.app]
}
resource "aws_s3_bucket_lifecycle_configuration" "weather" {
  bucket = aws_s3_bucket.app["weather"].id
  rule {
    id     = "expire-working-runs"
    status = "Enabled"
    filter { prefix = "runs/" }
    expiration { days = 7 }
  }
  rule {
    id     = "unfinished-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
  dynamic "rule" {
    for_each = { "observations/raw/" = 7, "observations/snapshots/" = 7, "query-results/" = 1 }
    content {
      id     = "expire-${replace(trimsuffix(rule.key, "/"), "/", "-")}"
      status = "Enabled"
      filter { prefix = rule.key }
      expiration { days = rule.value }
    }
  }
  rule {
    id     = "expire-recent-observation-history"
    status = "Enabled"
    filter {
      and {
        prefix = "observations/history/"
        tags   = { Retention = "working" }
      }
    }
    expiration { days = 30 }
  }
}
resource "aws_s3_object" "replay" {
  for_each     = fileset(var.archive_directory, "gfs-*/**")
  bucket       = aws_s3_bucket.app["weather"].id
  key          = "archive/ti1-cape-v1/${each.key}"
  source       = "${var.archive_directory}/${each.key}"
  source_hash  = filesha256("${var.archive_directory}/${each.key}")
  content_type = endswith(each.key, ".json") ? "application/json" : "application/octet-stream"
}
resource "aws_dynamodb_table" "runs" {
  name         = "${local.name}-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
}
