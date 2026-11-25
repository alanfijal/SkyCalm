resource "aws_ecs_cluster" "grid" {
  name = "${local.name}-grid"
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}
resource "aws_cloudwatch_log_group" "grid" {
  name              = "/ecs/${local.name}-grid"
  retention_in_days = 7
}
resource "aws_ecs_task_definition" "grid" {
  family                   = "${local.name}-grid"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.task["execution"].arn
  task_role_arn            = aws_iam_role.task["grid"].arn
  lifecycle {
    create_before_destroy = true
  }
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name = "grid", image = local.grid_image, essential = true,
    user = "65532:65532", stopTimeout = 30,
    environment = concat([
      { name = "SKYCALM_BUCKET", value = aws_s3_bucket.app["weather"].id },
      { name = "SKYCALM_TABLE", value = aws_dynamodb_table.runs.name }
    ], var.training_image_digest == null ? [] : [{ name = "SKYCALM_MODEL_GROUP", value = "skycalm-turbulence" }]),
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group"  = aws_cloudwatch_log_group.grid.name,
      "awslogs-region" = local.region, "awslogs-stream-prefix" = "grid"
    } }
  }])
}
output "grid_run_request" {
  description = "Input to aws ecs run-task after explicit deployment approval."
  value = {
    cluster = aws_ecs_cluster.grid.arn, taskDefinition = aws_ecs_task_definition.grid.arn,
    count   = 1, launchType = "FARGATE", platformVersion = "1.4.0",
    networkConfiguration = { awsvpcConfiguration = {
      subnets        = [aws_subnet.grid.id], securityGroups = [aws_security_group.grid.id],
      assignPublicIp = "ENABLED"
    } }
  }
}
