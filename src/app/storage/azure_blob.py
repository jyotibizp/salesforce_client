from __future__ import annotations

import os
import shutil
from azure.storage.blob import BlobServiceClient


def upload_file(connection_string: str, container: str, local_path: str, blob_path: str) -> None:
    # Check if running in local environment
    environment = os.getenv("ENVIRONMENT", "").lower()

    if environment == "local":
        # Use local filesystem storage instead of Azure Blob
        local_storage_dir = os.path.join("local_storage", container)
        os.makedirs(local_storage_dir, exist_ok=True)

        # Create the full destination path
        dest_path = os.path.join(local_storage_dir, blob_path)
        dest_dir = os.path.dirname(dest_path)
        os.makedirs(dest_dir, exist_ok=True)

        # Copy the file to local storage
        shutil.copy2(local_path, dest_path)
        print(f"File saved to local storage: {dest_path}")
    else:
        # Use Azure Blob Storage for non-local environments
        service = BlobServiceClient.from_connection_string(connection_string)
        blob_client = service.get_blob_client(container=container, blob=blob_path)
        with open(local_path, "rb") as fh:
            blob_client.upload_blob(fh, overwrite=True)


