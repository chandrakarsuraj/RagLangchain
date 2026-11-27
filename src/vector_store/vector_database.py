"""PostgreSQL pgvector store setup for LangChain."""

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from config import settings
from database import get_sqlalchemy_database_url


def get_vector_store(collection_name: str = "raglangchain") -> PGVector:
    """Create a synchronous LangChain PGVector store for a collection.

    PGVector creates its collection tables on first use. The database must have
    the pgvector extension available, and the configured database user needs
    permission to create it if it is not already enabled.
    """
    config = settings()
    missing_settings = [
        name
        for name, value in (
            ("DATABASE_URL", config.database_url),
            ("OPENAI_API_KEY", config.openai_api_key),
        )
        if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "Configure the following environment variables before using pgvector: "
            + ", ".join(missing_settings)
        )

    normalized_collection_name = collection_name.strip()
    if not normalized_collection_name:
        raise ValueError("collection_name must be a non-empty string.")

    embeddings = OpenAIEmbeddings(
        model=config.embedding_model,
        dimensions=config.embedding_dim,
        api_key=config.openai_api_key,
    )

    return PGVector(
        embeddings=embeddings,
        collection_name=normalized_collection_name,
        connection=get_sqlalchemy_database_url(config.database_url),
        embedding_length=config.embedding_dim,
        use_jsonb=True,
        create_extension=True,
    )
