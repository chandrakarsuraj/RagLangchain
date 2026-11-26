import os
from dotenv import load_dotenv


load_dotenv()

class Settings:

    OPEN_API_KEY = os.getenv("OPEN_API_KEY")
    QDRANT_URL = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_COLLECTION = "rag-project"



settings = Settings()