# Salesforce Pub/Sub gRPC Client

A Python client for subscribing to Salesforce Change Data Capture (CDC) and Platform Events using the Pub/Sub API with JWT-based OAuth authentication.

## 🔧 Setup

1. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate
   ```

2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

3. Configure environment variables in a `.env` file:
   ```
   SALESFORCE_CLIENT_ID=your_consumer_key
   SALESFORCE_USER_ID=your_salesforce_username
   SALESFORCE_PRIVATE_KEY=your_rsa_private_key
   ```

## 🚀 Run the Client

```powershell
python main.py
```

This will authenticate using JWT and subscribe to the specified CDC or Platform Event topic.

## 📁 Project Structure

```
salesforce_client/
├── auth/
│   └── jwt_token.py
├── pubsub/
│   ├── pubsub_pb2.py
│   ├── pubsub_pb2_grpc.py
│   └── subscriber.py
├── .env
├── requirements.txt
└── main.py
```

---
