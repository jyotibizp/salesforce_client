from __future__ import annotations

from dataclasses import dataclass
import os
from typing import List

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # dotenv is optional in some environments
    pass


@dataclass(frozen=True)
class Settings:
    sf_client_id: str
    sf_username: str
    sf_login_url: str
    sf_audience: str
    sf_private_key_path: str
    sf_topic_names: List[str]

    azure_storage_connection_string: str
    azure_blob_container: str

    sqlite_db_dir: str


_settings: Settings | None = None


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def get_settings() -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    topic_names_csv = _env("SF_TOPIC_NAMES", "/event/Delete_Logs__e")
    topic_names = [t.strip() for t in topic_names_csv.split(",") if t.strip()]

    _settings = Settings(
        sf_client_id=_env("SF_CLIENT_ID"),
        sf_username=_env("SF_USERNAME"),
        sf_login_url=_env("SF_LOGIN_URL", "https://login.salesforce.com"),
        sf_audience=_env("SF_AUDIENCE", "https://login.salesforce.com"),
        sf_private_key_path=_env("SF_PRIVATE_KEY_PATH", "certs/private.key"),
        sf_topic_names=topic_names,
        azure_storage_connection_string=_env("AZURE_STORAGE_CONNECTION_STRING"),
        azure_blob_container=_env("AZURE_BLOB_CONTAINER", "events"),
        sqlite_db_dir=_env("SQLITE_DB_DIR", "data"),
    )

    return _settings


