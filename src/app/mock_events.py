"""Mock event loader for testing without Salesforce connectivity"""

import json
import logging
import os
import base64
from typing import Dict, List


def load_mock_events_for_topic(mock_data_dir: str, topic_name: str) -> List[Dict]:
    """
    Load mock events from JSON file for a given topic.
    
    Args:
        mock_data_dir: Directory containing mock data files
        topic_name: Full topic name (e.g., "/event/ActivityContent_Delete__e")
        
    Returns:
        List of mock event dictionaries
    """
    # Extract event name from topic path (e.g., "/event/ActivityContent_Delete__e" -> "ActivityContent_Delete__e")
    event_name = topic_name.split("/")[-1]
    file_path = os.path.join(mock_data_dir, f"{event_name}.json")
    
    if not os.path.exists(file_path):
        logging.info("No mock data file found for %s at %s", topic_name, file_path)
        return []
    
    try:
        with open(file_path, "r") as f:
            mock_events = json.load(f)
        
        # Convert replay_id from base64 string to bytes
        for event in mock_events:
            if isinstance(event.get("replay_id"), str):
                event["replay_id"] = base64.b64decode(event["replay_id"])
            if isinstance(event.get("latest_replay_id"), str):
                event["latest_replay_id"] = base64.b64decode(event["latest_replay_id"])
        
        logging.info("Loaded %d mock events for %s from %s", len(mock_events), topic_name, file_path)
        return mock_events
        
    except Exception as e:
        logging.error("Error loading mock data from %s: %s", file_path, e)
        return []


def get_mock_events(mock_data_dir: str, topic_names: List[str]) -> Dict[str, List[Dict]]:
    """
    Load mock events for multiple topics.
    
    Args:
        mock_data_dir: Directory containing mock data files
        topic_names: List of topic names to load
        
    Returns:
        Dictionary mapping topic names to list of mock events
    """
    mock_data = {}
    
    for topic in topic_names:
        events = load_mock_events_for_topic(mock_data_dir, topic)
        if events:
            mock_data[topic] = events
    
    return mock_data

