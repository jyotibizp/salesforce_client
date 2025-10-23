# Batch Mode Platform Event Subscriber - Debug & Fix

## Problem
TimerPoller Azure Function (runs every 30 min) wasn't receiving events, even though:
- No errors were showing
- Events were created in Salesforce
- Continuous mode subscriber (ref-cliend) worked fine

## Root Cause
**First-time run used wrong replay preset**

When no replay_id exists (first run), the code used `ReplayPreset.LATEST`:
- LATEST means "start from now onwards" 
- In batch mode, function runs once and exits
- Any events published BEFORE the function runs are missed
- If no events arrive at the exact moment of subscription, nothing is fetched

## The Fix
Changed first-time run to use `ReplayPreset.EARLIEST`:
- EARLIEST fetches all available events from the retention window
- Subsequent runs continue using CUSTOM with saved replay_id
- This matches expected batch polling behavior

### Files Changed
1. `src/app/salesforce/pubsub_client.py` (line 103)
   - Changed: `replay_preset=pb2.ReplayPreset.LATEST`
   - To: `replay_preset=pb2.ReplayPreset.EARLIEST`

2. Added better logging in both files to track replay_id flow

## How It Works Now

### First Run (no replay_id in DB)
1. Fetches with `EARLIEST` preset
2. Gets all available events from retention window
3. Saves latest replay_id to cursor.db

### Subsequent Runs (replay_id exists)
1. Fetches with `CUSTOM` preset + saved replay_id
2. Gets events after the last processed event
3. Updates replay_id in cursor.db

## Testing

### Quick Test
1. Delete `data/cursor.db` to simulate first run
2. Trigger the TimerPoller function
3. Check logs for:
   ```
   No replay_id found for topic /event/Delete_Logs__e - will fetch from EARLIEST
   Subscribing to /event/Delete_Logs__e from EARLIEST (first run)
   Received batch with X events from /event/Delete_Logs__e
   Saved replay_id for topic /event/Delete_Logs__e
   ```

### Verify Replay Logic
1. Let function run and save replay_id
2. Create new test events in Salesforce
3. Trigger function again
4. Should see: `Found existing replay_id for topic... (length: X bytes)`
5. Should only fetch NEW events created after first run

## Replay Presets Explained
- **EARLIEST**: Start from oldest available event in retention window
- **LATEST**: Start from newest (now onwards)
- **CUSTOM**: Start from specific replay_id (resume point)

## What Was Already Correct
- Replay ID storage/retrieval (bytes type handled correctly)
- Event parsing and Avro decoding
- Batch mode exit logic (break after one batch)
- Cursor store database schema

The issue was purely the wrong replay preset on first run.

