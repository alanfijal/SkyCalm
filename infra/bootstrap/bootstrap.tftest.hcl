mock_provider "aws" {}
variables { account_id = "123456789012" }
run "bootstrap_defaults" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_policy && one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled"
    error_message = "Remote state must be private and versioned."
  }
  assert {
    condition     = length(aws_budgets_budget.gross) == 0 && aws_ecr_repository.grid.image_tag_mutability == "IMMUTABLE"
    error_message = "Default bootstrap must leave account-wide budget opt-in and image tags immutable."
  }
}
run "approved_budget" {
  command = plan
  variables {
    enable_budget = true
    budget_email  = "alerts@example.invalid"
  }
  assert {
    condition     = !one(aws_budgets_budget.gross[0].cost_types).include_credit && toset([for n in aws_budgets_budget.gross[0].notification : tonumber(n.threshold)]) == toset([10, 25, 50])
    error_message = "Account-wide budget must alert on gross charges at 10, 25 and 50 dollars."
  }
}
