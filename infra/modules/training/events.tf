resource "aws_iam_role" "announce" {
  name = "skycalm-dev-model-announce"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRole", Principal = { Service = "states.amazonaws.com" },
    Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
  }] })
}
resource "aws_iam_role_policy" "announce" {
  role   = aws_iam_role.announce.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "events:PutEvents", Resource = local.bus_arn }] })
}
resource "aws_sfn_state_machine" "announce" {
  name     = "skycalm-dev-model-approved"
  role_arn = aws_iam_role.announce.arn
  definition = jsonencode({ StartAt = "Publish", TimeoutSeconds = 30, States = { Publish = {
    Type = "Task", Resource = "arn:aws:states:::events:putEvents", End = true,
    Parameters = { Entries = [{ Source = "skycalm.ml", DetailType = "model.approved", EventBusName = var.bus_name,
    Detail = { "packageArn.$" = "$.detail.ModelPackageArn", "version.$" = "$.detail.ModelPackageVersion" } }] },
    Retry = [{ ErrorEquals = ["EventBridge.FailedEntry"], IntervalSeconds = 1, MaxAttempts = 2, BackoffRate = 2 }]
  } } })
}
resource "aws_cloudwatch_event_rule" "approved" {
  name = "skycalm-dev-approved-model"
  event_pattern = jsonencode({ source = ["aws.sagemaker"], "detail-type" = ["SageMaker Model Package State Change"],
  detail = { ModelPackageGroupName = [local.name], ModelApprovalStatus = ["Approved"], ModelPackageStatus = ["Completed"] } })
}
resource "aws_iam_role" "events" {
  name = "skycalm-dev-registry-events"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRole", Principal = { Service = "events.amazonaws.com" },
    Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.approved.arn } }
  }] })
}
resource "aws_iam_role_policy" "events" {
  role   = aws_iam_role.events.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "states:StartExecution", Resource = aws_sfn_state_machine.announce.arn }] })
}
resource "aws_cloudwatch_event_target" "approved" {
  rule     = aws_cloudwatch_event_rule.approved.name
  arn      = aws_sfn_state_machine.announce.arn
  role_arn = aws_iam_role.events.arn
  retry_policy {
    maximum_event_age_in_seconds = 900
    maximum_retry_attempts       = 3
  }
}
