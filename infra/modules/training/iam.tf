locals {
  sm_trust = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRole", Principal = { Service = "sagemaker.amazonaws.com" },
    Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
  }] })
  jobs = ["${local.sm}:processing-job/pipelines-*", "${local.sm}:training-job/pipelines-*"]
}
resource "aws_iam_role" "sagemaker" {
  name               = "skycalm-dev-training-jobs"
  assume_role_policy = local.sm_trust
}
resource "aws_iam_role_policy" "jobs" {
  role = aws_iam_role.sagemaker.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = local.storage },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = local.storage,
    Condition = { StringLike = { "s3:prefix" = ["archive/ti1-cape-v1/*", "archive/observations/*", "ml/runs/*"] } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = [for prefix in ["archive/ti1-cape-v1", "archive/observations", "ml/runs"] : "${local.storage}/${prefix}/*"] },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:AbortMultipartUpload"], Resource = "${local.storage}/ml/runs/*" },
    { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = "arn:aws:ecr:${local.region}:${var.account_id}:repository/skycalm/grid" },
    { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents"],
    Resource = [for kind in ["ProcessingJobs", "TrainingJobs"] : "arn:aws:logs:${local.region}:${var.account_id}:log-group:/aws/sagemaker/${kind}:*"] }
  ] })
}
resource "aws_iam_role" "pipeline" {
  name               = "skycalm-dev-training-pipeline"
  assume_role_policy = local.sm_trust
}
resource "aws_iam_role_policy" "pipeline" {
  role = aws_iam_role.pipeline.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sagemaker:CreateProcessingJob", "sagemaker:DescribeProcessingJob", "sagemaker:StopProcessingJob",
    "sagemaker:CreateTrainingJob", "sagemaker:DescribeTrainingJob", "sagemaker:StopTrainingJob", "sagemaker:AddTags", "sagemaker:ListTags"], Resource = local.jobs },
    { Effect = "Allow", Action = ["sagemaker:CreateModelPackage", "sagemaker:DescribeModelPackage", "sagemaker:AddTags"], Resource = [local.group_arn, local.model_arn] },
    # RegisterModel calls CreateModelPackageGroup even when Terraform already created the group.
    { Effect = "Allow", Action = ["sagemaker:CreateModelPackageGroup", "sagemaker:DescribeModelPackageGroup"], Resource = local.group_arn },
    { Effect = "Allow", Action = "iam:PassRole", Resource = aws_iam_role.sagemaker.arn, Condition = { StringEquals = { "iam:PassedToService" = "sagemaker.amazonaws.com" } } },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${local.storage}/ml/runs/*" },
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = local.storage },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:DescribeImages"], Resource = "arn:aws:ecr:${local.region}:${var.account_id}:repository/skycalm/grid" }
  ] })
}
resource "aws_iam_role_policy" "grid" {
  name = "read-approved-model"
  role = var.grid_role
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "sagemaker:ListModelPackages", Resource = "*" },
    { Effect = "Allow", Action = "sagemaker:DescribeModelPackage", Resource = local.model_arn },
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${local.storage}/ml/runs/*/output/model.tar.gz" }
  ] })
}
resource "aws_iam_role_policy" "briefings" {
  name = "read-prepared-briefings"
  role = var.forecast_role
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${local.storage}/ml/briefings/*" },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = local.storage,
    Condition = { StringLike = { "s3:prefix" = ["ml/briefings/*"] } } }
  ] })
}
