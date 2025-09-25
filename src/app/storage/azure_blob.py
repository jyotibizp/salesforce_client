from __future__ import annotations

import os
from azure.storage.blob import BlobServiceClient


def upload_file(connection_string: str, container: str, local_path: str, blob_path: str) -> None:
    service = BlobServiceClient.from_connection_string(connection_string)
    blob_client = service.get_blob_client(container=container, blob=blob_path)
    with open(local_path, "rb") as fh:
        blob_client.upload_blob(fh, overwrite=True)


