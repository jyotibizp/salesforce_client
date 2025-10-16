from auth.jwt_token import Connect
from pubsub.subscriber import subscribe_to_topic_with_token_response

# Example topics:
#   CDC:   '/data/AccountChangeEvent', '/data/EventChangeEvent', '/data/ChangeEvents'
#   PE:    '/event/YourEvent__e'
TOPIC = "/data/EventChangeEvent"

def main():
    conn = Connect()
    token_response = conn.get_access_token()

    if "access_token" not in token_response:
        print("Failed to retrieve access token:", token_response)
        return

    subscribe_to_topic_with_token_response(
        token_response,
        TOPIC,
        batch_size=10,
        periodic_fetch_secs=30
    )

if __name__ == "__main__":
    main()
