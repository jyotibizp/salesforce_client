### Flow summary

- Get the delete log from salesforce by subscribing platform events
- Dump this log somewhere in Azure data hub
- ADF to pick these logs for batch processing and push the log to delete_tracker table
- Enable stream on delete_tracker
- Create task to process this stream
- Create stored procedure to get called by task
- Once data reach to delete_tracker, stream also gets data, task on stream calls procedure and data in actual table get delete
