"""Slack webhook client for posting messages"""

from typing import Optional

import requests

from .config import config


class SlackClient:
    """Client for posting messages to Slack via webhook"""

    def __init__(self, webhook_url: Optional[str] = None, dry_run: bool = False):
        self.webhook_url = webhook_url or config.slack_webhook_url
        self.dry_run = dry_run

    def post_message(self, payload: dict) -> bool:
        """
        Post a message payload to Slack.
        Returns True on success, False on failure.
        """
        if not self.webhook_url:
            print("No Slack webhook URL configured")
            return False

        if self.dry_run:
            print("[DRY RUN] Would post to Slack:")
            self._print_preview(payload)
            return True

        try:
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            print("Posted to Slack successfully")
            return True
        except requests.RequestException as e:
            print(f"Error posting to Slack: {e}")
            return False

    def _print_preview(self, payload: dict) -> None:
        """Print a preview of the message for dry run mode"""
        blocks = payload.get("blocks", [])
        print("-" * 50)
        for block in blocks:
            block_type = block.get("type")
            if block_type == "header":
                text = block.get("text", {}).get("text", "")
                print(f"HEADER: {text}")
            elif block_type == "section":
                text = block.get("text", {}).get("text", "")
                print(text)
            elif block_type == "context":
                elements = block.get("elements", [])
                for el in elements:
                    print(f"  {el.get('text', '')}")
            elif block_type == "divider":
                print("-" * 30)
        print("-" * 50)
