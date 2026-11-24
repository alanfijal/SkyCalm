resource "aws_ecr_repository" "grid" {
  name                 = "skycalm/grid"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = false }
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
