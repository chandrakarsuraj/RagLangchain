from functools import cache
from typing import Any

import boto3
from botocore.client import BaseClient

from config import settings


@cache
def client(service: str) -> BaseClient:
    """Return a cached boto3 client for the requested AWS service."""
    aws_settings = settings()
    client_options: dict[str, Any] = {}

    if aws_settings.aws_region:
        client_options["region_name"] = aws_settings.aws_region

    access_key_id = aws_settings.aws_access_key_id
    secret_access_key = aws_settings.aws_secret_access_key
    if bool(access_key_id) != bool(secret_access_key):
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be configured together."
        )
    if access_key_id and secret_access_key:
        client_options["aws_access_key_id"] = access_key_id
        client_options["aws_secret_access_key"] = secret_access_key

    # When explicit credentials are not configured, boto3 uses its normal
    # credential chain (environment, profiles, instance/task roles, etc.).
    return boto3.client(service, **client_options)
