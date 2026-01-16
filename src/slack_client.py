"""Slack client for posting messages via chat.postMessage API"""

import logging
from typing import Optional

import requests

from .config import config

logger = logging.getLogger(__name__)

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
SLACK_UPDATE_MESSAGE_URL = "https://slack.com/api/chat.update"


class SlackClient:
    """Client for posting messages to Slack via chat.postMessage API"""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        channel_id: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.bot_token = bot_token or config.slack_bot_token
        self.channel_id = channel_id or config.slack_channel_id
        self.dry_run = dry_run

        # Configure session with connection pooling for Slack API
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=0,  # We handle retries if needed
        )
        self.session.mount("https://", adapter)

    def post_message(
        self,
        payload: dict,
        thread_ts: Optional[str] = None,
        reply_broadcast: bool = False,
    ) -> Optional[str]:
        """
        Post a message payload to Slack using chat.postMessage API.

        Args:
            payload: Message payload with 'blocks' and/or 'text'
            thread_ts: Thread timestamp to reply to (for threaded messages)
            reply_broadcast: If True, also post reply to channel (threaded + channel)

        Returns:
            Message timestamp (ts) on success for threading, None on failure.
        """
        if not self.bot_token:
            logger.warning("No Slack bot token configured")
            return None

        if not self.channel_id:
            logger.warning("No Slack channel ID configured")
            return None

        if self.dry_run:
            thread_info = f" [thread: {thread_ts}]" if thread_ts else ""
            broadcast_info = " [broadcast]" if reply_broadcast else ""
            logger.info(f"[DRY RUN] Would post to Slack{thread_info}{broadcast_info}:")
            self._print_preview(payload)
            # Return a fake timestamp for dry run testing
            return "dry_run_ts"

        # Build the API request payload
        api_payload = {
            "channel": self.channel_id,
            **payload,
        }

        # Add threading parameters if specified
        if thread_ts:
            api_payload["thread_ts"] = thread_ts
            if reply_broadcast:
                api_payload["reply_broadcast"] = True

        # Ensure there's a fallback text for notifications
        if "text" not in api_payload and "blocks" in api_payload:
            api_payload["text"] = self._extract_fallback_text(api_payload["blocks"])

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                SLACK_POST_MESSAGE_URL,
                json=api_payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            if not data.get("ok"):
                error = data.get("error", "Unknown error")
                logger.error(f"Slack API error: {error}")
                return None

            message_ts = data.get("ts")
            thread_info = f" (thread: {thread_ts})" if thread_ts else ""
            logger.info(f"Posted to Slack successfully{thread_info}")
            return message_ts
        except requests.RequestException as e:
            logger.error(f"Error posting to Slack: {e}")
            return None

    def post_thread_reply(
        self,
        payload: dict,
        thread_ts: str,
        also_send_to_channel: bool = False,
    ) -> Optional[str]:
        """
        Post a threaded reply to an existing message.

        Args:
            payload: Message payload with 'blocks' and/or 'text'
            thread_ts: Parent message timestamp to reply to
            also_send_to_channel: If True, also post to the main channel

        Returns:
            Message timestamp on success, None on failure.
        """
        return self.post_message(
            payload,
            thread_ts=thread_ts,
            reply_broadcast=also_send_to_channel,
        )

    def update_message(self, ts: str, payload: dict) -> bool:
        """
        Update an existing message.

        Args:
            ts: Timestamp of the message to update
            payload: New message payload with 'blocks' and/or 'text'

        Returns:
            True on success, False on failure.
        """
        if not self.bot_token or not self.channel_id:
            logger.warning("No Slack bot token or channel configured")
            return False

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update message {ts}:")
            self._print_preview(payload)
            return True

        api_payload = {
            "channel": self.channel_id,
            "ts": ts,
            **payload,
        }

        if "text" not in api_payload and "blocks" in api_payload:
            api_payload["text"] = self._extract_fallback_text(api_payload["blocks"])

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                SLACK_UPDATE_MESSAGE_URL,
                json=api_payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            if not data.get("ok"):
                error = data.get("error", "Unknown error")
                logger.error(f"Slack API error updating message: {error}")
                return False

            logger.info(f"Updated Slack message {ts}")
            return True
        except requests.RequestException as e:
            logger.error(f"Error updating Slack message: {e}")
            return False

    def _extract_fallback_text(self, blocks: list) -> str:
        """Extract fallback text from blocks for notification preview"""
        for block in blocks:
            if block.get("type") == "header":
                text = block.get("text", {}).get("text", "")
                if text:
                    return text
            elif block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                if text:
                    # Return first line of section as fallback
                    return text.split("\n")[0]
        return "NBA Update"

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
