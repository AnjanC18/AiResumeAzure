import os
import logging
from typing import Optional, Tuple, BinaryIO
from config import Config

logger = logging.getLogger(__name__)

# Try importing Azure Storage Blob
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions
    from azure.identity import DefaultAzureCredential
    AZURE_STORAGE_AVAILABLE = True
except ImportError:
    AZURE_STORAGE_AVAILABLE = False


class StorageService:
    """
    Unified Storage Service supporting:
    1. Azure Blob Storage (Cloud Production)
    2. Local Filesystem (Local Development Fallback)
    """

    def __init__(self):
        self.blob_service_client = None
        self.container_client = None
        self.container_name = Config.AZURE_STORAGE_CONTAINER
        self.use_blob = False

        if Config.use_azure_storage() and AZURE_STORAGE_AVAILABLE:
            self._init_azure_storage()

    def _init_azure_storage(self):
        try:
            if Config.AZURE_STORAGE_CONNECTION_STRING:
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    Config.AZURE_STORAGE_CONNECTION_STRING
                )
            elif Config.AZURE_STORAGE_ACCOUNT_NAME:
                account_url = f"https://{Config.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
                credential = DefaultAzureCredential()
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)

            if self.blob_service_client:
                self.container_client = self.blob_service_client.get_container_client(self.container_name)
                # Create container if it doesn't exist
                try:
                    self.container_client.create_container()
                except Exception:
                    pass  # Container already exists or permissions handled
                self.use_blob = True
                logger.info(f"Connected to Azure Blob Storage container: {self.container_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure Blob Storage ({e}). Falling back to local filesystem.")
            self.use_blob = False

    def save_resume(self, file_storage, filename: str) -> Tuple[str, Optional[str], str]:
        """
        Saves a resume either to Azure Blob Storage or local uploads/.
        Returns (filename, blob_url_or_none, storage_type: 'azure_blob' | 'local')
        """
        local_path = os.path.join(Config.UPLOAD_DIR, filename)
        
        # Always keep a local copy for immediate fast parsing if needed
        file_storage.seek(0)
        file_storage.save(local_path)

        if self.use_blob and self.container_client:
            try:
                blob_client = self.container_client.get_blob_client(filename)
                with open(local_path, "rb") as data:
                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=ContentSettings(content_type="application/pdf")
                    )
                blob_url = blob_client.url
                logger.info(f"Uploaded {filename} to Azure Blob: {blob_url}")
                return filename, blob_url, "azure_blob"
            except Exception as e:
                logger.error(f"Error uploading to Azure Blob Storage: {e}")
                return filename, None, "local"

        return filename, None, "local"

    def get_resume_bytes(self, filename: str) -> Optional[bytes]:
        """Reads resume bytes from Azure Blob Storage or local filesystem."""
        if self.use_blob and self.container_client:
            try:
                blob_client = self.container_client.get_blob_client(filename)
                return blob_client.download_blob().readall()
            except Exception as e:
                logger.warning(f"Could not read from Azure Blob ({e}), trying local fallback.")

        local_path = os.path.join(Config.UPLOAD_DIR, filename)
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return f.read()
        return None

    def delete_resume(self, filename: str) -> bool:
        """Deletes resume from both Azure Blob and local disk."""
        deleted = False
        if self.use_blob and self.container_client:
            try:
                blob_client = self.container_client.get_blob_client(filename)
                blob_client.delete_blob()
                deleted = True
            except Exception as e:
                logger.warning(f"Could not delete blob {filename}: {e}")

        local_path = os.path.join(Config.UPLOAD_DIR, filename)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                deleted = True
            except OSError:
                pass

        return deleted

    def get_resume_view_url(self, filename: str, blob_url: Optional[str] = None) -> str:
        """Returns direct link or local route for viewing resume."""
        if blob_url:
            return blob_url
        return f"/uploads/{filename}"


# Global singleton instance
storage_service = StorageService()

