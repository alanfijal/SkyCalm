"""Limit new classroom identities before Cognito sends verification email or creates a user."""

import os


def handler(event, context):
    allowed = os.environ.get("CLASSROOM_EMAIL", "").strip().casefold()
    email = event.get("request", {}).get("userAttributes", {}).get("email", "")
    if not allowed or not isinstance(email, str) or email.strip().casefold() != allowed:
        raise ValueError("This classroom is invitation only.")
    # Cognito or Google verifies ownership. Do not auto-confirm or auto-verify attributes here.
    return event
