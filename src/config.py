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
    nba_base_url: str = "https://api.nba.com/v0"
    poll_interval_active: int = 45  # Polling interval when games are in progress
    poll_interval_idle: int = 300   # Polling interval when no active games (5 min)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            schedule_api_key=os.getenv("SCHEDULE_API_KEY", ""),
            stats_api_key=os.getenv("STATS_API_KEY", ""),
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN"),
            slack_channel_id=os.getenv("SLACK_CHANNEL_ID_GAME_MONITOR"),
            nba_base_url=os.getenv("NBA_BASE_URL", "https://api.nba.com/v0"),
            poll_interval_active=int(os.getenv("POLL_INTERVAL_ACTIVE", "45")),
            poll_interval_idle=int(os.getenv("POLL_INTERVAL_IDLE", "300")),
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
