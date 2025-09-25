from __future__ import annotations

from typing import Dict, Iterable, List, Optional
import requests


API_VERSION = "v60.0"


def topic_to_sobject_name(topic: str) -> str:
    # '/event/Delete_Logs__e' -> 'Delete_Logs__e'
    return topic.split("/")[-1]


def build_soql(sobject_name: str, since_iso: Optional[str]) -> str:
    base = f"SELECT Id, CreatedDate FROM {sobject_name}"
    if since_iso:
        base += f" WHERE CreatedDate > {since_iso}"
    return base + " ORDER BY CreatedDate ASC LIMIT 2000"


def fetch_events(instance_url: str, access_token: str, sobject_name: str, since_iso: Optional[str]) -> List[Dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    soql = build_soql(sobject_name, since_iso)
    url = f"{instance_url}/services/data/{API_VERSION}/query"
    params = {"q": soql}
    all_records: List[Dict] = []
    while True:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        all_records.extend(data.get("records", []))
        next_url = data.get("nextRecordsUrl")
        if not next_url:
            break
        url = f"{instance_url}{next_url}"
        params = None
    return all_records


