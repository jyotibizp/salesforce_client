from __future__ import annotations

import time
import pathlib
import jwt
import requests


def _read_private_key(private_key_path: str) -> str:
    return pathlib.Path(private_key_path).read_text()


def create_jwt_assertion(client_id: str, username: str, audience: str, private_key_path: str) -> str:
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": username,
        "aud": audience,
        "exp": now + 180,
    }
    private_key = _read_private_key(private_key_path)
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token if isinstance(token, str) else token.decode("utf-8")


def get_access_token(login_url: str, assertion: str) -> tuple[str, str]:
    url = f"{login_url}/services/oauth2/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    payload = resp.json()
    return payload["access_token"], payload["instance_url"]


