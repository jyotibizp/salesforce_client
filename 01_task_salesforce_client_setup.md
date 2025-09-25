## ✅ **Salesforce Pub/Sub  API Client in Azure Function**

1. **Azure Function Setup**

   * Use a **Timer Trigger** (e.g. every 30 mins) to poll Salesforce.
   * Keep code modular — auth, event handling, DB, and blob upload in separate helpers.

2. **Salesforce Auth with Private Key**

   * Use **JWT Bearer Token flow** with `client_id`, `username`, and private key from `.crt` or `.key`.
   * Use **.env**.

3. **Subscribe to Platform Events via Pub/Sub API**

   * Connect over **gRPC**, subscribe to desired `/event/XYZ__e` topics.
   * Always resume using the last saved replay_id to avoid missing events.

4. **Manage Replay IDs**

   * Track and persist last successful `replay_id` per topic (in SQLite).
   * Handle replay errors like `REPLAY_ID_NOT_AVAILABLE`.

5. **Batch Event Collection**
   * Collect all events in memory for a run.

6. **Save Events to SQLite DB**

   * Save events in a file like `delete_logs_<timestamp>.db`.
   * Store raw JSON, topic, replay_id, etc. in a simple schema.

7. **Upload to Azure Blob**

   * Push the SQLite file to blob storage (`events/delete_logs_<timestamp>.db`).
   * Delete local file after successful upload.

8. **Error Handling, Logging & Config**

   * Add retries, log failures, and use config/env vars for all dynamic stuff.
   * Store secrets in Key Vault and track cert expiry.

