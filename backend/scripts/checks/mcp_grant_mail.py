"""Preview the MCP grant email, or explicitly send a test without granting access."""

from __future__ import annotations

import argparse
import os

from pydantic import EmailStr, TypeAdapter, ValidationError

from backend.src.core.mailing.mcp_access_granted import send_mcp_access_granted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Send a TEST email over SMTP")
    parser.add_argument("--recipient", default="extern.hamza-hacioglu@allianz.com.tr")
    parser.add_argument("--key-alias", default="ALZ-BRYSL-MAIL-TEST")
    parser.add_argument("--mcp-name", default="mail-preview-only")
    parser.add_argument("--environment", choices=("DEV", "TEST", "STG", "PROD"), default="TEST")
    args = parser.parse_args()
    try:
        recipient = str(TypeAdapter(EmailStr).validate_python(args.recipient))
    except ValidationError:
        parser.error("--recipient must be a valid email address")
    if any("\r" in value or "\n" in value for value in (args.key_alias, args.mcp_name)):
        parser.error("Names must not contain line breaks")
    os.environ["MAIL_PROVIDER"] = "smtp" if args.send else "placeholder"
    status = send_mcp_access_granted(
        recipient_email=recipient, key_alias=args.key_alias, mcp_name=args.mcp_name,
        environment=args.environment, test_message=True,
    )
    print(f"Test notification: {status}; recipient: {recipient}")
    print("No LiteLLM requests were made and no key permissions were changed.")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())