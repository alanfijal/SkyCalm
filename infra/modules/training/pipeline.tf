resource "aws_sagemaker_model_package_group" "classifier" {
  model_package_group_name        = local.name
  model_package_group_description = "Batch turbulence candidates evaluated against the physical grid."
}

locals {
  tags = [{ Key = "Project", Value = "SkyCalm" }, { Key = "Environment", Value = "dev" }]
  run  = { Get = "Execution.PipelineExecutionId" }
  paths = { for key in ["dataset", "training", "evaluation", "evaluation/evaluation.json"] : key =>
    { "Std:Join" = { On = "/", Values = ["${local.base}/ml/runs", local.run, key] } }
  }
  processing = {
    RoleArn             = aws_iam_role.sagemaker.arn, StoppingCondition = { MaxRuntimeInSeconds = 300 },
    ProcessingResources = { ClusterConfig = { InstanceCount = 1, InstanceType = "ml.m5.large", VolumeSizeInGB = 5 } },
    NetworkConfig       = { EnableNetworkIsolation = true }, Tags = local.tags
  }
  inputs = {
    grids        = { location = "${local.base}/archive/ti1-cape-v1/", path = "grids" }
    observations = { location = "${local.base}/archive/observations/", path = "observations" }
  }
  training_data = { Get = "Steps.SkyCalmPrepare.ProcessingOutputConfig.Outputs['dataset'].S3Output.S3Uri" }
  model_data    = { Get = "Steps.SkyCalmTrain.ModelArtifacts.S3ModelArtifacts" }
  prepare = {
    Name = "SkyCalmPrepare", Type = "Processing",
    Arguments = merge(local.processing, {
      AppSpecification = { ImageUri = local.image, ContainerArguments = ["prepare"] }
      ProcessingInputs = [for key, input in local.inputs : {
        InputName = key, S3Input = { S3Uri = input.location, LocalPath = "/opt/ml/processing/${input.path}", S3DataType = "S3Prefix", S3InputMode = "File" }
      }]
      ProcessingOutputConfig = { Outputs = [{
        OutputName = "dataset", S3Output = { S3Uri = local.paths.dataset, LocalPath = "/opt/ml/processing/dataset", S3UploadMode = "EndOfJob" }
      }] }
    })
  }
  train = {
    Name = "SkyCalmTrain", Type = "Training", Arguments = {
      AlgorithmSpecification = { TrainingImage = local.image, TrainingInputMode = "File" }
      RoleArn                = aws_iam_role.sagemaker.arn, Tags = local.tags, EnableNetworkIsolation = true,
      HyperParameters        = { rounds = "40" },
      InputDataConfig        = [{ ChannelName = "training", DataSource = { S3DataSource = { S3DataType = "S3Prefix", S3Uri = local.training_data, S3DataDistributionType = "FullyReplicated" } } }]
      OutputDataConfig       = { S3OutputPath = local.paths.training }
      ResourceConfig         = { InstanceCount = 1, InstanceType = "ml.m5.large", VolumeSizeInGB = 5 }
      StoppingCondition      = { MaxRuntimeInSeconds = 300 }
    }
  }
  evaluate = {
    Name = "SkyCalmEvaluate", Type = "Processing", PropertyFiles = [{ PropertyFileName = "Metrics", OutputName = "metrics", FilePath = "evaluation.json" }]
    Arguments = merge(local.processing, {
      AppSpecification = { ImageUri = local.image, ContainerArguments = ["evaluate"] }
      ProcessingInputs = [
        { InputName = "dataset", S3Input = { S3Uri = local.training_data, LocalPath = "/opt/ml/processing/dataset", S3DataType = "S3Prefix", S3InputMode = "File" } },
        { InputName = "model", S3Input = { S3Uri = local.model_data, LocalPath = "/opt/ml/processing/model", S3DataType = "S3Prefix", S3InputMode = "File" } }
      ]
      ProcessingOutputConfig = { Outputs = [{
        OutputName = "metrics", S3Output = { S3Uri = local.paths.evaluation, LocalPath = "/opt/ml/processing/metrics", S3UploadMode = "EndOfJob" }
      }] }
    })
  }
  register = { for status in ["Approved", "PendingManualApproval"] : status => {
    Name = "Register${status}", Type = "RegisterModel", Arguments = {
      ModelPackageGroupName = aws_sagemaker_model_package_group.classifier.model_package_group_name,
      ModelApprovalStatus   = status,
      InferenceSpecification = { Containers = [{ Image = local.image, ModelDataUrl = local.model_data }],
      SupportedContentTypes = ["application/json"], SupportedResponseMIMETypes = ["application/json"] }
      ModelMetrics = { ModelQuality = { Statistics = { ContentType = "application/json", S3Uri = local.paths["evaluation/evaluation.json"] } } }
    }
  } }
  gate = {
    Name = "CompareAgainstBaseline", Type = "Condition", Arguments = {
      Conditions = [{ Type = "Equals", LeftValue = { "Std:JsonGet" = { PropertyFile = { Get = "Steps.SkyCalmEvaluate.PropertyFiles.Metrics" }, Path = "approval.status" } }, RightValue = "Approved" }],
      IfSteps    = [local.register.Approved], ElseSteps = [local.register.PendingManualApproval]
    }
  }
}
resource "aws_sagemaker_pipeline" "classifier" {
  pipeline_name         = local.name
  pipeline_display_name = "SkyCalm-Turbulence-Evaluation"
  role_arn              = aws_iam_role.pipeline.arn
  pipeline_definition   = jsonencode({ Version = "2020-12-01", Parameters = [], Steps = [local.prepare, local.train, local.evaluate, local.gate] })
}
