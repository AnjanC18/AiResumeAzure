import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-12345")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    PORT = int(os.environ.get("PORT", 5000))
    UPLOAD_DIR = UPLOAD_DIR
    ALLOWED_EXTENSIONS = {"pdf"}

    # Stage 1: Azure SQL Database configuration
    # Can use full connection string or individual components
    AZURE_SQL_CONNECTION_STRING = os.environ.get("AZURE_SQL_CONNECTION_STRING", "").strip()
    AZURE_SQL_SERVER = os.environ.get("AZURE_SQL_SERVER", "").strip()
    AZURE_SQL_DATABASE = os.environ.get("AZURE_SQL_DATABASE", "").strip()
    AZURE_SQL_USER = os.environ.get("AZURE_SQL_USER", "").strip()
    AZURE_SQL_PASSWORD = os.environ.get("AZURE_SQL_PASSWORD", "").strip()
    AZURE_SQL_DRIVER = os.environ.get("AZURE_SQL_DRIVER", "{ODBC Driver 18 for SQL Server}").strip()
    SQLITE_PATH = os.path.join(BASE_DIR, "resume_screening.db")

    @classmethod
    def use_azure_sql(cls) -> bool:
        return bool(cls.AZURE_SQL_CONNECTION_STRING or (cls.AZURE_SQL_SERVER and cls.AZURE_SQL_DATABASE))

    # Stage 2: Azure Blob Storage configuration
    AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    AZURE_STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
    AZURE_STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER", "resumes").strip()

    @classmethod
    def use_azure_storage(cls) -> bool:
        return bool(cls.AZURE_STORAGE_CONNECTION_STRING or cls.AZURE_STORAGE_ACCOUNT_NAME)

    # Stage 3: Azure Functions configuration
    AZURE_FUNCTION_URL = os.environ.get("AZURE_FUNCTION_URL", "").strip()
    AZURE_FUNCTION_KEY = os.environ.get("AZURE_FUNCTION_KEY", "").strip()

    @classmethod
    def use_azure_functions(cls) -> bool:
        return bool(cls.AZURE_FUNCTION_URL)

    # Stage 4: Azure AI / OpenAI Semantic Matching configuration
    AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY", "").strip()
    AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "text-embedding-3-small").strip()
    AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01").strip()

    @classmethod
    def use_azure_openai(cls) -> bool:
        return bool(cls.AZURE_OPENAI_ENDPOINT and cls.AZURE_OPENAI_KEY)

    @classmethod
    def get_cloud_status(cls) -> dict:
        """Returns the active integration status across all 5 Azure components."""
        return {
            "azure_sql": {
                "active": cls.use_azure_sql(),
                "label": "Azure SQL Database" if cls.use_azure_sql() else "SQLite (Local Fallback)",
                "target": cls.AZURE_SQL_SERVER or "Local File"
            },
            "azure_storage": {
                "active": cls.use_azure_storage(),
                "label": "Azure Blob Storage" if cls.use_azure_storage() else "Local Disk (uploads/)",
                "container": cls.AZURE_STORAGE_CONTAINER if cls.use_azure_storage() else "uploads"
            },
            "azure_functions": {
                "active": cls.use_azure_functions(),
                "label": "Azure Functions (Serverless)" if cls.use_azure_functions() else "In-App Processing",
                "endpoint": cls.AZURE_FUNCTION_URL or "Local Python Pipeline"
            },
            "azure_ai": {
                "active": cls.use_azure_openai(),
                "label": "Azure OpenAI Embeddings" if cls.use_azure_openai() else "Local Semantic Vectorizer",
                "model": cls.AZURE_OPENAI_DEPLOYMENT if cls.use_azure_openai() else "TF-IDF / Cosine Engine"
            },
            "azure_app_service": {
                "active": bool(os.environ.get("WEBSITE_SITE_NAME")),
                "label": "Azure App Service" if os.environ.get("WEBSITE_SITE_NAME") else "Localhost Development",
                "site_name": os.environ.get("WEBSITE_SITE_NAME", "Local")
            }
        }

