"""Game monitoring and quarter detection logic"""

from typing import Optional

from .models import Game


class GameMonitor:
    """Tracks game state and detects quarter endings"""

    def __init__(self):
        self.posted_quarters: dict[str, set[int]] = {}

    def detect_quarter_end(self, game: Game) -> Optional[int]:
        """
        Detect if a quarter just ended based on gameStatusText.
        Returns quarter number (1-4) if quarter ended, None otherwise.
        """
        status_text = game.status_text

        if "Halftime" in status_text or "Half" in status_text:
            return 2

        if "End of Q1" in status_text:
            return 1
        if "End of Q3" in status_text:
            return 3

        if game.status == 3:
            return 4

        return None

    def should_post_update(self, game_id: str, quarter: int) -> bool:
        """Check if we should post an update for this quarter"""
        if game_id not in self.posted_quarters:
            return True
        return quarter not in self.posted_quarters[game_id]

    def mark_quarter_posted(self, game_id: str, quarter: int) -> None:
        """Mark a quarter as posted for a game"""
        if game_id not in self.posted_quarters:
            self.posted_quarters[game_id] = set()
        self.posted_quarters[game_id].add(quarter)

    def get_posted_quarters(self, game_id: str) -> set[int]:
        """Get set of quarters already posted for a game"""
        return self.posted_quarters.get(game_id, set())

    def reset_game(self, game_id: str) -> None:
        """Reset tracking for a game (useful for testing)"""
        if game_id in self.posted_quarters:
            del self.posted_quarters[game_id]
