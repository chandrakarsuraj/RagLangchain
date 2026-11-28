"""Load documents stored in Amazon S3."""

import logging
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from aws import client
from config import settings
from loader.loader import load_file
from vector_store.vector_database import get_embedding, get_vector_store


logger = logging.getLogger(__name__)
_SUPPORTED_SUFFIXES = {".pdf", ".txt"}


def load_s3_file(key: str, bucket: str | None = None) -> list[Document]:
    """Download an S3 object temporarily and load it as LangChain documents.

    Args:
        key: The object's key in S3, such as ``manuals/guide.pdf``.
        bucket: S3 bucket name. Defaults to the configured ``S3_BUCKET``.

    Returns:
        Documents returned by ``loader.load_file``, with each document's
        ``source`` metadata set to the object's ``s3://`` URI.

    Raises:
        ValueError: If the bucket/key is missing or the file type is unsupported.
        botocore.exceptions.ClientError: If S3 cannot retrieve the object.
    """
    if not key or not key.strip():
        raise ValueError("S3 object key must be provided.")

    bucket_name = bucket or settings().s3_bucket
    if not bucket_name:
        raise ValueError("Provide a bucket or configure the S3_BUCKET setting.")

    suffix = PurePosixPath(key).suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(
            f"Unsupported S3 document type {suffix!r}. Supported types: {supported}"
        )

    s3_uri = f"s3://{bucket_name}/{key}"
    logger.info("Downloading S3 object %s", s3_uri)
    with TemporaryDirectory(prefix="raglangchain-s3-") as temp_dir:
        local_path = Path(temp_dir) / f"document{suffix}"
        client("s3").download_file(bucket_name, key, str(local_path))
        logger.info(
            "Downloaded %s (%d bytes)", s3_uri, local_path.stat().st_size
        )
        documents = load_file(local_path)

    for document in documents:
        document.metadata["source"] = s3_uri

    logger.info("Loaded %d document(s) from %s", len(documents), s3_uri)
    return documents


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """Split loaded documents into overlapping chunks for indexing."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")
    if not documents:
        logger.warning("No documents were provided for chunking")
        return []

    logger.info(
        "Chunking %d document(s) with chunk_size=%d and chunk_overlap=%d",
        len(documents),
        chunk_size,
        chunk_overlap,
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(documents)
    logger.info("Created %d chunk(s)", len(chunks))
    return chunks


def create_embeddings(documents: list[Document]) -> list[list[float]]:
    """Create embeddings for documents using the configured embedding model."""
    if not documents:
        logger.warning("No documents were provided for embedding")
        return []

    logger.info("Creating embeddings for %d chunk(s)", len(documents))
    embedding_model = get_embedding()
    embeddings = embedding_model.embed_documents(
        [document.page_content for document in documents]
    )
    logger.info("Created %d embedding(s)", len(embeddings))
    return embeddings


def store_documents(
    documents: list[Document],
    embeddings: list[list[float]],
    collection_name: str = "raglangchain",
) -> list[str]:
    """Store document text, metadata, and precomputed embeddings in PGVector."""
    if len(documents) != len(embeddings):
        raise ValueError(
            "The number of embeddings must match the number of documents."
        )
    if not documents:
        logger.warning("No documents were provided for vector-store insertion")
        return []

    logger.info(
        "Storing %d document chunk(s) in collection %r",
        len(documents),
        collection_name,
    )
    vector_store = get_vector_store(collection_name)
    document_ids = vector_store.add_embeddings(
        texts=[document.page_content for document in documents],
        embeddings=embeddings,
        metadatas=[document.metadata for document in documents],
    )
    logger.info(
        "Stored %d chunk(s) in collection %r",
        len(document_ids),
        collection_name,
    )
    return document_ids


def ingest_s3_file(
    key: str,
    bucket: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    collection_name: str = "raglangchain",
) -> list[str]:
    """Ingest an S3 PDF or text file into the configured vector database.

    Downloads and loads the object, splits its documents into chunks, creates
    embeddings, and stores the chunks in the requested PGVector collection.
    Returns the vector-store IDs for the stored chunks.
    """
    s3_uri = f"s3://{bucket}/{key}"
    logger.info("Starting ingestion for %s", s3_uri)
    try:
        documents = load_s3_file(key=key, bucket=bucket)
        chunks = chunk_documents(
            documents,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        embeddings = create_embeddings(chunks)
        document_ids = store_documents(
            chunks,
            embeddings,
            collection_name=collection_name,
        )
    except Exception:
        logger.exception("Ingestion failed for %s", s3_uri)
        raise

    logger.info(
        "Ingestion complete for %s: %d document(s), %d chunk(s), %d stored ID(s)",
        s3_uri,
        len(documents),
        len(chunks),
        len(document_ids),
    )
    return document_ids
