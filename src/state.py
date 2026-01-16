"""Persistent state management for game tracking"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default state file location
DEFAULT_STATE_FILE = Path(__file__).parent.parent / ".game_state.json"


@dataclass
class GameState:
    """State for a single game"""

    game_id: str
    thread_ts: Optional[str] = None  # Parent message timestamp for threading
    posted_quarters: list[int] = field(default_factory=list)
    game_started_posted: bool = False
    halftime_posted: bool = False
    final_posted: bool = False
    close_game_alerts: list[str] = field(default_factory=list)  # Timestamps of close game alerts
    performance_alerts: list[str] = field(default_factory=list)  # "player_name:alert_type" posted

    def has_posted_quarter(self, quarter: int) -> bool:
        return quarter in self.posted_quarters

    def mark_quarter_posted(self, quarter: int) -> None:
        if quarter not in self.posted_quarters:
            self.posted_quarters.append(quarter)

    def has_posted_performance_alert(self, player_name: str, alert_type: str) -> bool:
        key = f"{player_name}:{alert_type}"
        return key in self.performance_alerts

    def mark_performance_alert_posted(self, player_name: str, alert_type: str) -> None:
        key = f"{player_name}:{alert_type}"
        if key not in self.performance_alerts:
            self.performance_alerts.append(key)


@dataclass
class DailyState:
    """State for a single day's games"""

    date: str  # YYYY-MM-DD format
    games: dict[str, GameState] = field(default_factory=dict)
    end_of_night_posted: bool = False

    def get_game(self, game_id: str) -> GameState:
        """Get or create game state"""
        if game_id not in self.games:
            self.games[game_id] = GameState(game_id=game_id)
        return self.games[game_id]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "date": self.date,
            "end_of_night_posted": self.end_of_night_posted,
            "games": {
                game_id: asdict(game_state)
                for game_id, game_state in self.games.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyState":
        """Create from dictionary"""
        state = cls(
            date=data["date"],
            end_of_night_posted=data.get("end_of_night_posted", False),
        )
        for game_id, game_data in data.get("games", {}).items():
            state.games[game_id] = GameState(
                game_id=game_data["game_id"],
                thread_ts=game_data.get("thread_ts"),
                posted_quarters=game_data.get("posted_quarters", []),
                game_started_posted=game_data.get("game_started_posted", False),
                halftime_posted=game_data.get("halftime_posted", False),
                final_posted=game_data.get("final_posted", False),
                close_game_alerts=game_data.get("close_game_alerts", []),
                performance_alerts=game_data.get("performance_alerts", []),
            )
        return state


class StateManager:
    """Manages persistent state for game tracking"""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._state: Optional[DailyState] = None
        self._dirty = False  # Track if state needs saving
        self._load()

    def _get_today(self) -> str:
        """Get today's date string"""
        return datetime.now().strftime("%Y-%m-%d")

    def _load(self) -> None:
        """Load state from file"""
        today = self._get_today()

        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)

                # Check if state is for today
                if data.get("date") == today:
                    self._state = DailyState.from_dict(data)
                    logger.info(f"Loaded state for {today} with {len(self._state.games)} games")
                else:
                    # State is from a different day, start fresh
                    logger.info(f"State file is from {data.get('date')}, starting fresh for {today}")
                    self._state = DailyState(date=today)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Could not load state file: {e}, starting fresh")
                self._state = DailyState(date=today)
        else:
            self._state = DailyState(date=today)

    def _save(self) -> None:
        """Save state to file (only if dirty)"""
        if self._state and self._dirty:
            try:
                with open(self.state_file, "w") as f:
                    json.dump(self._state.to_dict(), f, indent=2)
                self._dirty = False
                logger.debug("State saved to disk")
            except IOError as e:
                logger.error(f"Could not save state file: {e}")

    def get_game(self, game_id: str) -> GameState:
        """Get game state, creating if necessary"""
        # Ensure we're using today's state
        today = self._get_today()
        if self._state is None or self._state.date != today:
            self._state = DailyState(date=today)

        return self._state.get_game(game_id)

    def save_game(self, game_state: GameState) -> None:
        """Save a game's state (marks dirty but doesn't write immediately)"""
        if self._state:
            self._state.games[game_state.game_id] = game_state
            self._dirty = True
            self._save()

    def is_end_of_night_posted(self) -> bool:
        """Check if end of night summary was posted"""
        return self._state.end_of_night_posted if self._state else False

    def mark_end_of_night_posted(self) -> None:
        """Mark end of night summary as posted"""
        if self._state:
            self._state.end_of_night_posted = True
            self._dirty = True
            self._save()

    def flush(self) -> None:
        """Force write state to disk if dirty"""
        self._save()

    def get_all_game_states(self) -> dict[str, GameState]:
        """Get all game states for today"""
        if self._state:
            return self._state.games
        return {}

    def reset(self) -> None:
        """Reset all state (useful for testing)"""
        self._state = DailyState(date=self._get_today())
        if self.state_file.exists():
            os.remove(self.state_file)
