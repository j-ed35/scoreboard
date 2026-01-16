"""NBA API client for schedule and boxscore data"""

import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from time import sleep
from typing import Optional

import requests

from .config import config
from .models import Game, Player, TeamStats

logger = logging.getLogger(__name__)

# Pre-compiled regex for ISO 8601 duration parsing (avoids recompilation per call)
_DURATION_PATTERN = re.compile(r'PT(?:(\d+)M)?(\d+(?:\.\d+)?)?S?')


def parse_iso_duration_to_clock(duration: str) -> str:
    """
    Convert ISO 8601 duration format (PTmmMss.ccS) to MM:SS clock display.

    Examples:
        PT05M32.00S -> 5:32
        PT00M45.50S -> 0:45
        PT12M08.30S -> 12:08

    Args:
        duration: ISO 8601 duration string (e.g., "PT05M32.00S")

    Returns:
        Clock display string (e.g., "5:32")
    """
    if not duration:
        return ""

    # Use pre-compiled pattern for better performance
    match = _DURATION_PATTERN.match(duration)
    if not match:
        return ""

    minutes = int(match.group(1)) if match.group(1) else 0
    seconds = int(float(match.group(2))) if match.group(2) else 0

    return f"{minutes}:{seconds:02d}"


class NBAApiClient:
    """Client for interacting with NBA API endpoints"""

    REQUEST_TIMEOUT = 10
    MAX_RETRIES = 3

    def __init__(self):
        self.base_url = config.nba_base_url
        self.schedule_api_key = config.schedule_api_key
        self.stats_api_key = config.stats_api_key

        # Configure session with connection pooling for better performance
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,  # Number of connection pools to cache
            pool_maxsize=20,      # Max connections per pool
            max_retries=0,        # We handle retries ourselves
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Cache for boxscore data (game_id -> data, timestamp)
        # Helps avoid duplicate API calls within the same polling cycle
        self._boxscore_cache: dict[str, tuple[dict, float]] = {}
        self._cache_ttl = 30  # seconds

    def _request_with_retry(
        self, url: str, headers: dict, params: dict
    ) -> Optional[dict]:
        """Make HTTP request with retry logic and exponential backoff"""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.get(
                    url, headers=headers, params=params, timeout=self.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"Request failed after {self.MAX_RETRIES} attempts: {e}")
                    return None
                wait_time = 2**attempt
                logger.warning(f"Request failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                sleep(wait_time)
        return None

    def get_todays_games(self) -> list[Game]:
        """Fetch today's NBA games from the rolling schedule endpoint

        Returns games from today and yesterday (to handle games that cross midnight).
        Yesterday's games are only included if they are still in progress (status=2),
        to avoid re-posting finals for completed games from the previous day.
        """
        url = f"{self.base_url}/api/schedule/rolling"
        headers = {"X-NBA-Api-Key": self.schedule_api_key}
        params = {"leagueId": "00", "gameDate": "TODAY"}

        data = self._request_with_retry(url, headers, params)
        if not data:
            return []

        rolling_schedule = data.get("rollingSchedule", {})
        game_dates = rolling_schedule.get("gameDates", [])

        # Get date strings for today and yesterday
        now = datetime.now()
        today = now.strftime("%m/%d/%Y")
        yesterday = (now - timedelta(days=1)).strftime("%m/%d/%Y")

        all_games = []
        for game_date in game_dates:
            date_str = game_date.get("gameDate", "")
            games_data = game_date.get("games", [])

            if date_str.startswith(today):
                # Include all of today's games
                all_games.extend([
                    Game.from_schedule_api(g, game_date=today)
                    for g in games_data
                ])
            elif date_str.startswith(yesterday):
                # Only include yesterday's games that are still in progress
                # This handles games that crossed midnight
                for g in games_data:
                    if g.get("gameStatus") == 2:  # In progress
                        all_games.append(Game.from_schedule_api(g, game_date=yesterday))

        return all_games

    def get_yesterdays_games(self) -> list[Game]:
        """Fetch yesterday's completed NBA games

        Returns all games from the previous day that have finished (status=3).
        Useful for daily recaps and morning summaries.

        Note: The rolling schedule API only accepts 'TODAY' as gameDate,
        so we fetch today's rolling window and filter for yesterday's completed games.
        """
        url = f"{self.base_url}/api/schedule/rolling"
        headers = {"X-NBA-Api-Key": self.schedule_api_key}
        params = {"leagueId": "00", "gameDate": "TODAY"}

        data = self._request_with_retry(url, headers, params)
        if not data:
            return []

        rolling_schedule = data.get("rollingSchedule", {})
        game_dates = rolling_schedule.get("gameDates", [])

        # Get yesterday's date string for matching
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%m/%d/%Y")

        all_games = []
        for game_date in game_dates:
            date_str = game_date.get("gameDate", "")
            games_data = game_date.get("games", [])

            # Match yesterday's date and only include finished games
            if date_str.startswith(yesterday):
                all_games.extend([
                    Game.from_schedule_api(g, game_date=yesterday)
                    for g in games_data
                    if g.get("gameStatus") == 3  # Finished games only
                ])

        return all_games

    def get_boxscore(self, game_id: str) -> Optional[dict]:
        """Fetch raw boxscore data for a specific game (with caching)"""
        import time

        # Check cache first
        if game_id in self._boxscore_cache:
            data, timestamp = self._boxscore_cache[game_id]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Using cached boxscore for game {game_id}")
                return data

        # Cache miss or expired, fetch from API
        url = f"{self.base_url}/api/stats/boxscore"
        headers = {"X-NBA-Api-Key": self.stats_api_key}
        params = {"gameId": game_id, "measureType": "Traditional"}

        data = self._request_with_retry(url, headers, params)

        # Cache the result if successful
        if data:
            self._boxscore_cache[game_id] = (data, time.time())

        return data

    def clear_cache(self) -> None:
        """Clear the boxscore cache (useful for testing or forcing refresh)"""
        self._boxscore_cache.clear()

    def enrich_game_with_boxscore(self, game: Game) -> bool:
        """Enrich a Game object with player data from boxscore API"""
        boxscore = self.get_boxscore(game.game_id)
        if not boxscore:
            return False

        # Update game clock and period from boxscore (more recent than schedule API)
        if "period" in boxscore and boxscore["period"] is not None:
            game.period = boxscore["period"]

        if "gameClock" in boxscore and boxscore["gameClock"]:
            game.clock = parse_iso_duration_to_clock(boxscore["gameClock"])

        home_data = boxscore.get("homeTeam", {})
        away_data = boxscore.get("awayTeam", {})

        game.home_team.players = [
            Player.from_api(p) for p in home_data.get("players", [])
        ]
        game.away_team.players = [
            Player.from_api(p) for p in away_data.get("players", [])
        ]

        home_stats_data = home_data.get("statistics", {})
        away_stats_data = away_data.get("statistics", {})

        home_periods = home_stats_data.get("periods", [])
        away_periods = away_stats_data.get("periods", [])

        game.home_team.quarter_scores = [
            p.get("points", 0) for p in home_periods
        ]
        game.away_team.quarter_scores = [
            p.get("points", 0) for p in away_periods
        ]

        game.home_team.stats = TeamStats.from_api(home_stats_data)
        game.away_team.stats = TeamStats.from_api(away_stats_data)

        return True

    def get_player_daily_leaders(self, stat: str) -> Optional[dict]:
        """Fetch daily player leaders for a specific stat category.

        Args:
            stat: One of 'pts', 'reb', 'ast', 'fg3m', 'fgpct', 'blk', 'stl', 'ftm'
        """
        url = f"{self.base_url}/api/stats/player/leaders/daily"
        headers = {"X-NBA-Api-Key": self.stats_api_key}
        params = {"leagueId": "00", "stat": stat}

        return self._request_with_retry(url, headers, params)

    def get_team_daily_leaders(self, stat: str) -> Optional[dict]:
        """Fetch daily team leaders for a specific stat category.

        Args:
            stat: One of 'pts', 'ast', 'fgpct', 'fg3pct'
        """
        url = f"{self.base_url}/api/stats/team/leaders/daily"
        headers = {"X-NBA-Api-Key": self.stats_api_key}
        params = {"leagueId": "00", "stat": stat}

        return self._request_with_retry(url, headers, params)
