def fetch_avro_schema(schema_id: str, token_response: Dict) -> Dict:
    """
    Fetch the Avro schema (COMPACT) for a platform event / CDC schema_id via REST.
    See: /services/data/vXX.X/event/eventSchema/{schemaId}?payloadFormat=COMPACT
    """
    instance_url = token_response["instance_url"]
    access_token = token_response["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Try a few recent API versions (adjust if your org supports newer)
    versions = ["64.0", "61.0", "59.0", "57.0"]
    last_err = None

    for v in versions:
        url = f"{instance_url}/services/data/v{v}/event/eventSchema/{schema_id}?payloadFormat=COMPACT"
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            logging.info("Avro schema GET %s -> %s", url, resp.status_code)
            resp.raise_for_status()
            data = resp.json()

            # Some responses wrap the actual Avro schema under "schema"; normalize both cases.
            schema = data.get("schema", data)
            if not isinstance(schema, dict):
                raise ValueError(f"Unexpected schema shape from {url}: {type(schema)}")
            return schema
        except requests.RequestException as e:
            logging.warning("Schema fetch attempt failed on %s: %s", url, e)
            last_err = e
            continue

    raise RuntimeError(f"Failed to fetch schema for ID {schema_id}: {last_err}")