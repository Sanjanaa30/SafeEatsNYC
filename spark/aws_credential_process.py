"""Supply refreshable aws-login credentials to the Java AWS SDK."""

from __future__ import annotations

import json
import os
from datetime import timezone

import boto3


def credential_document() -> dict[str, str | int]:
    """Return the standard credential_process JSON document."""

    profile = os.getenv("SAFEEATS_SOURCE_AWS_PROFILE", "safeeats-dev")
    source_config = os.getenv(
        "SAFEEATS_SOURCE_AWS_CONFIG_FILE",
        "/home/airflow/.aws/config",
    )
    source_credentials = os.getenv(
        "SAFEEATS_SOURCE_AWS_SHARED_CREDENTIALS_FILE",
        "/home/airflow/.aws/credentials",
    )

    os.environ["AWS_PROFILE"] = profile
    os.environ["AWS_CONFIG_FILE"] = source_config
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = source_credentials

    credentials = boto3.Session(profile_name=profile).get_credentials()
    if credentials is None:
        raise RuntimeError(f"AWS profile {profile!r} did not provide credentials.")
    frozen = credentials.get_frozen_credentials()
    document: dict[str, str | int] = {
        "Version": 1,
        "AccessKeyId": frozen.access_key,
        "SecretAccessKey": frozen.secret_key,
    }
    if frozen.token:
        document["SessionToken"] = frozen.token

    expiry = getattr(credentials, "_expiry_time", None)
    if expiry is not None:
        document["Expiration"] = expiry.astimezone(timezone.utc).isoformat()
    return document


def main() -> None:
    """Print only the JSON format expected by AWS credential_process."""

    print(json.dumps(credential_document(), separators=(",", ":")))


if __name__ == "__main__":
    main()
