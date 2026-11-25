module "pipeline" {
  source             = "../pipeline"
  name               = local.name
  region             = local.region
  account_id         = var.account_id
  python_image       = local.lambda_images.python
  weather_bucket     = aws_s3_bucket.app["weather"].id
  runs_table         = aws_dynamodb_table.runs.name
  task_arn           = aws_ecs_task_definition.grid.arn
  cluster_arn        = aws_ecs_cluster.grid.arn
  subnet             = aws_subnet.grid.id
  security_group     = aws_security_group.grid.id
  execution_role_arn = aws_iam_role.task["execution"].arn
  grid_role_arn      = aws_iam_role.task["grid"].arn
  discovery_window   = var.discovery_window
}

resource "aws_iam_role_policy" "grid_replay" {
  name = "write-isolated-replay-grids"
  role = aws_iam_role.task["grid"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${local.weather_arn}/pipeline/jobs/replay-*/*"
  }] })
}
variable "discovery_window" {
  type    = object({ start = string, end = string })
  default = null
}
output "pipeline_operator_policy" { value = module.pipeline.operator_policy }
