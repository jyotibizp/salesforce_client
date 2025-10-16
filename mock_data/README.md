# Mock Data for Platform Events

This directory contains mock event data for testing the Azure Function without connecting to Salesforce.

## Usage

Set `MOCK_MODE=true` in your `local.settings.json` to enable mock mode:

```json
{
  "Values": {
    "MOCK_MODE": "true",
    "MOCK_DATA_DIR": "mock_data"
  }
}
```

When mock mode is enabled, the function will load events from JSON files instead of subscribing to Salesforce Pub/Sub API.

## File Format

Each JSON file should be named after the event (e.g., `ActivityContent_Delete__e.json`) and contain an array of mock events:

```json
[
  {
    "topic": "/event/ActivityContent_Delete__e",
    "replay_id": "AQEBAQ==",
    "event_id": "mock-event-001",
    "schema_id": "mock-schema-id",
    "payload": {
      "ObjectName": "ActivityContent",
      "RecordId": "0XX3t000000ABC001",
      "DeletedBy": "0053t000000XYZ101",
      "DeletedDate": "2025-10-16T10:15:30.000Z",
      "OwnerId": "0053t000000XYZ101"
    },
    "latest_replay_id": "AQEBAQ=="
  }
]
```

## Available Mock Topics

- `ActivityContent_Delete__e.json` - 3 mock events
- `Investment_Delete__e.json` - 2 mock events

Add more JSON files as needed for other topics.

