import os
import time
import jwt
import requests
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization


class Connect:
    """
    OAuth 2.0 JWT Bearer flow for Salesforce.
    - sub = username (NOT user id)
    - aud = token host (login/test/My Domain)
    """

    def __init__(self):
        load_dotenv()
        self.client_id = os.getenv("SALESFORCE_CLIENT_ID")
        self.username = os.getenv("SALESFORCE_USERNAME")  # username, not user id
        self.login_url = os.getenv("SALESFORCE_LOGIN_URL", "https://login.salesforce.com")
        self.private_key_file = os.getenv("SALESFORCE_PRIVATE_KEY")

        if not all([self.client_id, self.username, self.private_key_file]):
            raise ValueError("Missing required environment variables.")

    def _load_private_key(self):
        with open(self.private_key_file, 'rb') as key_file:
            return serialization.load_pem_private_key(key_file.read(), password=None)

    def _create_jwt_assertion(self):
        issued_at = int(time.time())
        expiration = issued_at + 300  # 5 minutes
        payload = {
            'iss': self.client_id,
            'sub': self.username,
            'aud': self.login_url,  # must match the token host
            'exp': expiration,
            'iat': issued_at
        }
        private_key = self._load_private_key()
        return jwt.encode(payload, private_key, algorithm='RS256')

    def get_access_token(self) -> dict:
        """
        Returns the token response JSON, e.g.:
        {
          "access_token": "...",
          "instance_url": "https://MyDomain.my.salesforce.com",
          "id": "https://login.salesforce.com/id/00Dxxxx/005yyyy",
          "token_type": "Bearer",
          ...
        }
        """
        assertion = self._create_jwt_assertion()
        token_url = f"{self.login_url}/services/oauth2/token"
        response = requests.post(token_url, data={
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': assertion
        })
        return response.json()
