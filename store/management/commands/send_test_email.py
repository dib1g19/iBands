from environs import Env
import requests

env = Env()
env.read_env()

# Use environment override for Mailgun API base URL, default to EU region
MAILGUN_API_URL = env("MAILGUN_API_URL", "https://api.eu.mailgun.net/v3")


def send_simple_message():
    api_key = env("MAILGUN_API_KEY")
    domain = env("MAILGUN_SENDER_DOMAIN")
    sender = env("DEFAULT_FROM_EMAIL")
    recipient = env("TEST_RECEIVER_EMAIL")

    # Debug output
    print(f"DEBUG — Mailgun API Key: {api_key}")
    print(f"DEBUG — Mailgun Domain: {domain}")
    print(f"DEBUG — From Address: {sender}")
    print(f"DEBUG — Test Recipient: {recipient}")

    # Validate environment
    if not api_key or not domain or not sender or not recipient:
        raise RuntimeError(
            "Make sure MAILGUN_API_KEY, MAILGUN_SENDER_DOMAIN, DEFAULT_FROM_EMAIL "
            "and TEST_RECEIVER_EMAIL are set in your .env"
        )

    # Build request
    url = f"{MAILGUN_API_URL}/{domain}/messages"
    print(f"DEBUG — Request URL: {url}")

    response = requests.post(
        url,
        auth=("api", api_key),
        data={
            "from": sender,
            "to": recipient,
            "subject": "Mailgun Test from Django Environment",
            "text": "If you’re seeing this, your MAILGUN setup is working!",
        },
    )
    response.raise_for_status()
    print("✅ Sent! Response:", response.json())


if __name__ == "__main__":
    send_simple_message()
