resource "aws_ecr_repository" "grid" {
  name                 = "skycalm/grid"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "untagged" {
  repository = aws_ecr_repository.grid.name
  policy = jsonencode({ rules = [{
    rulePriority = 1,
    description  = "Expire untagged images after one week",
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 },
    action       = { type = "expire" }
  }] })
}
output "grid_repository" { value = aws_ecr_repository.grid.repository_url }

resource "aws_ecr_repository" "functions" {
  name                 = "skycalm/functions"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository_policy" "functions" {
  repository = aws_ecr_repository.functions.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "SkyCalmLambdaPull", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" },
    Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
    Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:lambda:eu-north-1:${var.account_id}:function:skycalm-dev-*" } }
  }] })
}

resource "aws_ecr_lifecycle_policy" "functions" {
  repository = aws_ecr_repository.functions.name
  # Active and rollback releases keep immutable tags. Age alone cannot identify an idle live function.
  policy = aws_ecr_lifecycle_policy.untagged.policy
}
output "functions_repository" { value = aws_ecr_repository.functions.repository_url }
