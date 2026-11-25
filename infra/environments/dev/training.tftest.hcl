mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/skycalm-test" }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = { arn = "arn:aws:states:eu-north-1:123456789012:stateMachine:skycalm-test" }
  }
  mock_resource "aws_cloudwatch_event_rule" {
    defaults = { arn = "arn:aws:events:eu-north-1:123456789012:rule/skycalm-test" }
  }
}
run "bounded_training_pipeline" {
  command = apply
  module { source = "../../modules/training" }
  variables {
    account_id    = "123456789012"
    bucket        = "example-weather"
    image_digest  = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    bus_name      = "example-bus"
    grid_role     = "example-grid"
    forecast_role = "example-forecast"
  }
  assert {
    condition = alltrue([for step in slice(jsondecode(aws_sagemaker_pipeline.classifier.pipeline_definition).Steps, 0, 3) :
    step.Arguments.StoppingCondition.MaxRuntimeInSeconds == 300]) && local.prepare.Arguments.NetworkConfig.EnableNetworkIsolation && local.train.Arguments.EnableNetworkIsolation
    error_message = "Preparation, training and evaluation must each stop within five minutes with network isolation."
  }
  assert {
    condition     = local.gate.Arguments.IfSteps[0].Arguments.ModelApprovalStatus == "Approved" && local.gate.Arguments.ElseSteps[0].Arguments.ModelApprovalStatus == "PendingManualApproval" && aws_sagemaker_model_package_group.classifier.model_package_group_name == "skycalm-turbulence"
    error_message = "The evaluation gate must keep unsupported candidates pending."
  }
}
