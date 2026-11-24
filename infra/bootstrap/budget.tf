variable "enable_budget" {
  description = "Create the account-wide budget only after owner approval."
  type        = bool
  default     = false
}
variable "budget_email" {
  type      = string
  sensitive = true
  default   = ""
}
resource "aws_budgets_budget" "gross" {
  count        = var.enable_budget ? 1 : 0
  name         = "skycalm-account-gross"
  budget_type  = "COST"
  limit_amount = "50"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_types {
    include_credit   = false
    include_refund   = false
    include_discount = true
    include_tax      = true
    use_amortized    = false
    use_blended      = false
  }
  dynamic "notification" {
    for_each = toset(["10", "25", "50"])
    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = "ACTUAL"
      threshold_type             = "ABSOLUTE_VALUE"
      threshold                  = tonumber(notification.value)
      subscriber_email_addresses = [var.budget_email]
    }
  }
  lifecycle {
    precondition {
      condition     = can(regex("^[^@ ]+@[^@ ]+[.][^@ ]+$", var.budget_email))
      error_message = "Supply the approved subscriber email locally."
    }
  }
}
