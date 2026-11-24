resource "aws_glue_catalog_database" "observations" {
  name = "skycalm_dev_weather"
}
resource "aws_glue_catalog_table" "observations" {
  name          = "observations"
  database_name = aws_glue_catalog_database.observations.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    EXTERNAL                    = "TRUE"
    classification              = "json"
    "projection.enabled"        = "true"
    "projection.day.type"       = "date"
    "projection.day.range"      = "2026-01-01,NOW"
    "projection.day.format"     = "yyyy-MM-dd"
    "storage.location.template" = "s3://${aws_s3_bucket.app["weather"].bucket}/observations/history/day=$${day}/"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.app["weather"].bucket}/observations/history/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }
    dynamic "columns" {
      for_each = {
        id      = "string", kind = "string", source = "string", intensity = "string", observed = "string",
        expires = "string", base_ft = "double", top_ft = "double"
      }
      content {
        name = columns.key
        type = columns.value
      }
    }
  }
}
resource "aws_athena_workgroup" "observations" {
  name = "${local.name}-weather"
  configuration {
    enforce_workgroup_configuration    = true
    bytes_scanned_cutoff_per_query     = 10485760
    publish_cloudwatch_metrics_enabled = false
    result_configuration {
      output_location = "s3://${aws_s3_bucket.app["weather"].bucket}/query-results/"
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}
