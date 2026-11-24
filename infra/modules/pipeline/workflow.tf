resource "aws_sfn_state_machine" "grid" {
  name     = local.prefix
  role_arn = aws_iam_role.workflow.arn
  type     = "STANDARD"
  definition = templatefile("${path.module}/workflow.asl.json.tftpl", {
    worker         = aws_lambda_function.run["workflow"].arn
    bus            = aws_cloudwatch_event_bus.forecast.name
    cluster        = var.cluster_arn
    task           = var.task_arn
    security_group = var.security_group
    subnet         = var.subnet
  })
  depends_on = [aws_iam_role_policy.workflow]
}
