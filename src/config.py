"""Configuration management for NBA Quarter Updates"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration loaded from environment variables"""

    schedule_api_key: str
    stats_api_key: str
    slack_bot_token: Optional[str]
    slack_channel_id: Optional[str]
    slack_webhook_url: Optional[str]  # Legacy, kept for backwards compatibility
    nba_base_url: str = "https://api.nba.com/v0"
    poll_interval_seconds: int = 120

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            schedule_api_key=os.getenv("SCHEDULE_API_KEY", ""),
            stats_api_key=os.getenv("STATS_API_KEY", ""),
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN"),
            slack_channel_id=os.getenv("SLACK_CHANNEL_ID_GAME_MONITOR"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            nba_base_url=os.getenv("NBA_BASE_URL", "https://api.nba.com/v0"),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "120")),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors"""
        errors = []
        if not self.schedule_api_key:
            errors.append("SCHEDULE_API_KEY is required")
        if not self.stats_api_key:
            errors.append("STATS_API_KEY is required")
        if not self.slack_bot_token:
            errors.append("SLACK_BOT_TOKEN is required")
        if not self.slack_channel_id:
            errors.append("SLACK_CHANNEL_ID_GAME_MONITOR is required")
        return errors


config = Config.from_env()
