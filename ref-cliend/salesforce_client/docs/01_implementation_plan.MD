## 🔄 Implementation Flow

1. **Environment Setup**
   - Load credentials from `.env` file:
     - `SALESFORCE_CLIENT_ID`
     - `SALESFORCE_USER_ID`
     - `SALESFORCE_PRIVATE_KEY`

2. **JWT Token Generation**
   - Create a JWT with claims (`iss`, `sub`, `aud`, `exp`)
   - Sign it using the RSA private key

3. **Access Token Retrieval**
   - Send the JWT to Salesforce’s token endpoint
   - Receive an OAuth access token

4. **Stub Files Setup**
   - Use precompiled files (`pubsub_api_pb2.py`, `pubsub_api_pb2_grpc.py`) from the `python/` folder  
     **OR**
   - Generate them using:
     ```bash
     python -m grpc_tools.protoc --proto_path=../ pub-sub-api/python/pubsub_api.proto --python_out=. --grpc_python_out=.
     ```

5. **gRPC Client Initialization**
   - Create a secure gRPC channel to `api.pubsub.salesforce.com:443`
   - Attach the access token in the request metadata

6. **Subscribe to Topic**
   - Send a `FetchRequest` for the desired topic (e.g., `/data/EventChangeEvent`)
   - Receive and process event messages

---

https://developer.salesforce.com/docs/platform/pub-sub-api/guide/qs-generate-stub.html

| Package      | Why It's Needed                     |
|--------------|-------------------------------------|
| `grpcio`     | Required to make gRPC calls         |
| `protobuf`   | Required to handle protocol buffers |
| `requests`   | Used for HTTP requests (OAuth token)|
| `PyJWT`      | Used to generate JWT tokens         |
| `python-dotenv` | Loads environment variables from `.env` |

 writing a script to call GetTopic or decode your access token to verify scopes