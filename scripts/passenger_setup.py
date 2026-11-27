"""Validate private provider files locally or explicitly provision an approved deployment."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ACCOUNT = "028718095604"
REGION = "eu-north-1"
CALLBACK = f"https://skycalm-dev-{ACCOUNT}.auth.{REGION}.amazoncognito.com/oauth2/idpresponse"


def private_file(path):
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise SystemExit(f"Restrict permissions on {path.name} to the owner first.")
    return json.loads(path.read_bytes())


def write_private(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
        json.dump(data, out)
        out.write("\n")


def read_google(path):
    web = private_file(path).get("web", {})
    if not (
        web.get("client_id", "").endswith(".apps.googleusercontent.com")
        and isinstance(web.get("client_secret"), str)
        and web["client_secret"]
        and CALLBACK in web.get("redirect_uris", [])
        and web.get("auth_uri") == "https://accounts.google.com/o/oauth2/auth"
        and web.get("token_uri") == "https://oauth2.googleapis.com/token"
    ):
        raise SystemExit("The private Google web client or Cognito redirect did not match.")
    return {k: web[k] for k in ("client_id", "client_secret")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-dir", type=Path, required=True)
    p.add_argument(
        "--classroom-email", required=True, help="Verified SES mailbox for classroom alerts"
    )
    p.add_argument(
        "--login-email", help="Invited sign-in address if different from the SES mailbox"
    )
    p.add_argument("--profile", default="coldchain-console")
    p.add_argument("--provision-approved-secrets", action="store_true")
    a = p.parse_args()
    directory = a.private_dir.resolve()
    if directory.stat().st_mode & 0o077:
        raise SystemExit("The private directory must have mode 700.")
    google = read_google(directory / "google-oauth.json")
    config = {
        "passenger_settings": {
            "google_ready": True,
            "classroom_email": a.classroom_email,
        }
    }
    if a.login_email:
        config["passenger_settings"]["login_email"] = a.login_email.strip()
    vars_path = directory / "passengers.tfvars.json"
    if not vars_path.exists():
        write_private(vars_path, config)
    else:
        existing = private_file(vars_path)
        existing.get("passenger_settings", {}).pop("vapid_public", None)
        if existing != config:
            raise SystemExit("Existing local settings differ. Review the private configuration.")
    if not a.provision_approved_secrets:
        print("Validated Google redirect and classroom email configuration.")
        return
    cli = ["aws", "--profile", a.profile, "--region", REGION, "--no-cli-pager"]
    if (
        subprocess.check_output(
            [*cli, "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            text=True,
        ).strip()
        != ACCOUNT
    ):
        raise SystemExit("AWS account mismatch.")
    with TemporaryDirectory(dir=directory) as temp:
        secret = "skycalm-dev/passengers/google"
        versions = json.loads(
            subprocess.check_output(
                [
                    *cli,
                    "secretsmanager",
                    "list-secret-version-ids",
                    "--secret-id",
                    secret,
                    "--output",
                    "json",
                ]
            )
        )
        if versions.get("Versions"):
            existing = json.loads(
                subprocess.check_output(
                    [
                        *cli,
                        "secretsmanager",
                        "get-secret-value",
                        "--secret-id",
                        secret,
                        "--query",
                        "SecretString",
                        "--output",
                        "text",
                    ]
                )
            )
            if existing != google:
                raise SystemExit("Existing secret differs. Review rotation separately.")
            return
        path = Path(temp) / "google"
        write_private(path, google)
        subprocess.run(
            [
                *cli,
                "secretsmanager",
                "put-secret-value",
                "--secret-id",
                secret,
                "--secret-string",
                "file://" + str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print("Google provider credentials are provisioned.")


if __name__ == "__main__":
    main()
