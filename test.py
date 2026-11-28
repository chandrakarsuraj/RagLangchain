"""Opt-in integration test for the S3-to-PGVector ingestion pipeline."""

import os
import unittest

from config import settings
from worker.ingest import ingest_s3_file


bucket = settings().s3_bucket
document_ids = ingest_s3_file(
    key="climate_change.pdf",
    bucket=bucket,
)

print(document_ids)
