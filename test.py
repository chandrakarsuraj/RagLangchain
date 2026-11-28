"""Run the S3-to-PGVector ingestion pipeline for a sample PDF."""

import logging

from config import settings
from worker.ingest import ingest_s3_file

logger = logging.getLogger(__name__)


def main() -> None:
    bucket = settings().s3_bucket
    if not bucket:
        raise RuntimeError("Configure S3_BUCKET in the environment or .env file.")

    document_ids = ingest_s3_file(
        key="climate_change.pdf",
        bucket=bucket,
    )
    logger.info(
        "Ingestion returned %d stored chunk ID(s): %s",
        len(document_ids),
        document_ids,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
