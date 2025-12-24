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
    slack_webhook_url: Optional[str]
    nba_base_url: str = "https://api.nba.com/v0"
    poll_interval_seconds: int = 120

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            schedule_api_key=os.getenv("SCHEDULE_API_KEY", ""),
            stats_api_key=os.getenv("STATS_API_KEY", ""),
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
        return errors


config = Config.from_env()
