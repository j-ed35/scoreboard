"""
Simple helper script to send a message to the Slack webhook.
Add your message to the `message` variable and run the script.
"""

import os
import sys

import requests
from dotenv import load_dotenv


def main() -> None:
    """Send a single Slack message to the configured webhook."""
    load_dotenv()
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("Missing SLACK_WEBHOOK_URL in environment or .env file.")
        sys.exit(1)

    message = "<https://www.youtube.com/shorts/-KaR2mmifk0?feature=share|You Like that>"
    if not message:
        print("Please add your message text to the `message` variable before sending.")
        sys.exit(1)

    payload = {"text": message}

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to send Slack message: {exc}")
        sys.exit(1)

    print("Message sent to Slack.")


if __name__ == "__main__":
    main()
