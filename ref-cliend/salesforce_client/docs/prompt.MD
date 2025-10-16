I am trying to build python client to subscribe salesforce cdc.

below is my code:

#main.py
import os
import time
import jwt
from auth.jwt_token import Connect
from pubsub.subscriber import subscribe_to_topic
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    token = Connect().get_access_token()
    print(jwt.decode(token, options={"verify_signature": False}))
    time.sleep(5)
    topic_name = os.getenv("SALESFORCE_TOPIC_NAME", "/data/EventChangeEvent")
    if token:
        subscribe_to_topic(token, topic_name)
    else:
        print("Failed to retrieve access token.")

#auth/jwt_token.py

import datetime
import os
import jwt
import requests
from dotenv import load_dotenv

class Connect:
    payload: dict
    private_key: str

    def __init__(self):
        load_dotenv()
        client_id = os.getenv("SALESFORCE_CLIENT_ID")
        self.private_key = os.getenv("SALESFORCE_PRIVATE_KEY")
        self.payload = {
            "sub": os.environ.get("SALESFORCE_USER_ID"),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
            "iss": client_id,
            "aud": "https://login.salesforce.com"  # ✅ Correct audience for Pub/Sub API
        }

    def get_access_token(self):
        jwtToken = jwt.encode(self.payload, self.private_key, algorithm='RS256')

        accessTokenHeaders = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        accessTokenBody = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwtToken
        }

        accessTokenUrl = 'https://login.salesforce.com/services/oauth2/token'
        accessTokenResponse = requests.post(accessTokenUrl, data=accessTokenBody, headers=accessTokenHeaders)

        if accessTokenResponse.status_code == 200:
            return accessTokenResponse.json().get('access_token')
        else:
            # Retry with cleaned private key
            cleaned_key = self.private_key.replace("\\n", "\n")
            jwtToken = jwt.encode(self.payload, cleaned_key, algorithm='RS256')
            accessTokenBody["assertion"] = jwtToken
            accessTokenResponse = requests.post(accessTokenUrl, data=accessTokenBody, headers=accessTokenHeaders)
            if accessTokenResponse.status_code == 200:
                return accessTokenResponse.json().get('access_token')
            else:
                return None

#pubsub/subscriber.py:

import grpc
import os
import time
import logging
from pubsub_api_pb2 import FetchRequest, ReplayPreset
from pubsub_api_pb2_grpc import PubSubStub

# Enable gRPC debug logging
os.environ["GRPC_VERBOSITY"] = "error"
os.environ["GRPC_TRACE"] = "api"

# Optional: configure Python logging
logging.basicConfig(level=logging.DEBUG)

def subscribe_to_topic(access_token, topic_name):
    print(f"🔐 Access Token: {access_token}")
    time.sleep(5)

    if not topic_name.startswith("/event/") and not topic_name.startswith("/data/"):
        print(f"⚠️ Invalid topic name: {topic_name}")
        time.sleep(1)

    channel = grpc.secure_channel('api.pubsub.salesforce.com:443', grpc.ssl_channel_credentials())
    stub = PubSubStub(channel)
    metadata = [('authorization', f'Bearer {access_token}')]

    request = FetchRequest(
        topic_name=topic_name,
        replay_preset=ReplayPreset.LATEST,
        num_requested=10,
        auth_refresh="placeholder"
    )

    print(f"Subscribing to topic: {topic_name}")
    time.sleep(5)
    try:
        response_stream = stub.Subscribe(iter([request]), metadata=metadata)
        with open("deleted_events.log", "a") as log_file:
            print(f"with open")
            time.sleep(2)
            for event in response_stream:
                time.sleep(2)
                if hasattr(event, "event") and hasattr(event.event, "change_type"):
                    if event.event.change_type == "DELETE":
                        print("🗑️ DELETE Event received:")
                        print(event)
                        log_file.write(str(event) + "\n")
                        time.sleep(1)
    except grpc.RpcError as e:
        print(f"❌ gRPC error: {e.code()} - {e.details()}")
        print("🔍 Debug info:", e.debug_error_string())
        time.sleep(2)

#.evn


SALESFORCE_TOPIC_NAME=/data/EventChangeEvent

SALESFORCE_CLIENT_ID="3MVG9JEx.BE6yifNk5USP3ASdT0KN5KGztePUfxsXvV5Wmbl9c.RJG0pt2sWX33CC6Hr7623lUJux3upPcJP8"
SALESFORCE_USER_ID="smsalesforceapi@blueowl.com"
SALESFORCE_PRIVATE_KEY= "-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAqkaNOi4i/bP9iXSE4sOGgUhmcxADtnW4BtFmJUpELMkLTkkU
4/yyXANf0u9cxfYBWwf2QsMWIzTnOGcj/S0hLLVDhTVDRmwy9v26YBQZgix4N3PY
Ya9Pdh2J7qEO7svAh1XWnSBBXfGv6HZ5kHz29viXkzRyloYCQRMdGDsYrDZIHsvr
cCzn8Ek4Q6Us8zIgS+VugBs3+EOeyrVBpGTYKTCNjG+Hpwris/Zayb5H1ouliu/V
cmJ2xVIbtn6mRNjHtHNLQLq1BT+3X87HrtAinMzHqSuHjbIFy/Vl09PHdS8neEJg
m231orw6S6eQx/Gxwbdupy7pqDgO9k4KzEokCwIDAQABAoIBAEsUOrdZmoIlN/jA
0MswDYG5y7qWaByuwUr4T8LHgVIB/6MwJC72wCpELp9SfaSn+ScLVrFPVdaGQCGl
kL/Ug1k0P6Zfut81XC995wzwL+Mu+n7w7Ir+AtqA4c2/ZFc0rhq+ZZf4nfnvVHH6
s1VbVIXHTQZSTOhEBIBvDhgeDp33xJYGdKeVa7GsPG6sDOfg+rJRJCFG6dYJYleJ
hCBf9SN+BtlOMLPourq/AMNcT49IjVOiKjFfcQPp/i0+bdKghXyBtS2S0hlUVowP
PwrLL4qikDSYYPWTWuX7YXQ2jGvYQ+fsLL3XbQsgxc7mDXlnUgYocT/vyzUUXRyY
km2byMECgYEA4ibE9KGsFZhYRfBHUQkQzMp9mI46tv5NWwnr0zt1F7ez9cWjGCVt
zB1PJokw8R0lfgMhv+Yi3ttnrNLZgYBwJowNfNO52YLxRGjWKKFBwJG7CfY68me9
mgK5VxJpRxdaBD5tZx7kZRgH+FHELTwTFR8HS77Xe3VTw+xsZni3GuECgYEAwL/X
vURK4F3XibN5ZY7rHNDhsCF1Y1Wf5z0bbwNm9qOVSfSpWok6hEt1uwxamos5hGFs
WkfMOjeeUL1i52ZrhD3aQuk1DtG93tZ+5+jQ0GSmrkhnjgRikf3/I5GssM3pRH+z
2oGYKlR9Bahi3gcOdvQm2BJi3cDKfm4o6aom6GsCgYEAzdOZSEjotRLdrHG+hrto
her5mmJAgBI9V1FVSAACVx7D9Dj3cl+GadJ3GkyctaXgXKr/CYesTwaDemDAw0Oh
TwQCtoyAxr2NVsTPvVTe4iQAhlWLWtoeT1CRXPUNyj0vmVM0ATm1h2jywAezM7RM
bdm6qy67Mcsb/OJt2mmdxSECgYEAtz2qe+RQyrxsDBzza/lSyzJJXIhycN0WB1+w
lPlHCXK6mnReDBQp7VtPsWMtP37cT13PBIT9QttdRqTFQfe8fxvOQ44xQsVjHFYO
j6pl2bfWPhnXWMwSaXhu9gGniu42tUgyU6igYJ2xvY83bpyGw8+YnhHcq7R8zXUs
r/dyxcECgYAW/V6WOjpP4D2ATgxOWQ6mPcJ89+Gz9s/ZgQCPkFffMU+xvELqdJlX
i22oxqXXLZ5bwT3C9glq9sat+xF3qAxr/URcqrHkHLST37fdQ//BokMUgfAv6lxV
Zb6lt0AIUSMbNQXD/UJVwoaJvsSZQwcZBL+eIFMFmpTONb6cD3Y24A==
-----END RSA PRIVATE KEY-----"
