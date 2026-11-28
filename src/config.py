from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    tavily_api_key: str | None = None
    langsmith_api_key: str | None = None
    langchain_tracing_v2: str | None = None
    langchain_endpoint: str | None = None
    langchain_project: str | None = None

    qdrant_api_key: str | None = None
    qdrant_cluster_endpoint: str | None = None

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None
    s3_bucket: str | None = None

    s3_upload_prefix: str = "uploads"
    ingest_worker_url: str | None = None
    ingest_worker_api_key: str | None = None

    langgraph_api_url: str = "http://127.0.0.1:2024"
    langgraph_api_key: str | None = None
    langgraph_assistant_id: str = "rag_agent"
    vector_collection_name: str = "raglangchain"

    pinecone_api_key: str | None = None
    pinecone_index_name: str | None = None
    pinecone_index_host: str | None = None
    pinecone_cloud: str | None = None
    pinecone_region: str | None = None
    pinecone_ready_timeout: str | None = None

    database_url: str | None = None

    max_upload_bytes: int = 10485760
    min_relevance : float=0.25
    hitl_enable : bool = True
    memory_turns:int =6
    chat_model: str = "gpt-4.1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024


    firebase_api_key :str = ""
    firebase_auth_domain: str = ""
    firebase_project_id: str = ""

    
def settings()-> Settings:
    return Settings()
