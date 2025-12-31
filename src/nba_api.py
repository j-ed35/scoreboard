"""NBA API client for schedule and boxscore data"""

import logging
import re
from datetime import datetime
from time import sleep
from typing import Optional

import requests

from .config import config
from .models import Game, Player, TeamStats

logger = logging.getLogger(__name__)


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

    # Match pattern: PT followed by optional minutes and seconds
    # PTmmMss.ccS or PTmmMssS or PTssS
    match = re.match(r'PT(?:(\d+)M)?(\d+(?:\.\d+)?)?S?', duration)
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

    def _request_with_retry(
        self, url: str, headers: dict, params: dict
    ) -> Optional[dict]:
        """Make HTTP request with retry logic and exponential backoff"""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(
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
        """Fetch today's NBA games from the rolling schedule endpoint"""
        url = f"{self.base_url}/api/schedule/rolling"
        headers = {"X-NBA-Api-Key": self.schedule_api_key}
        params = {"leagueId": "00", "gameDate": "TODAY"}

        data = self._request_with_retry(url, headers, params)
        if not data:
            return []

        rolling_schedule = data.get("rollingSchedule", {})
        game_dates = rolling_schedule.get("gameDates", [])

        today = datetime.now().strftime("%m/%d/%Y")
        for game_date in game_dates:
            if game_date.get("gameDate", "").startswith(today):
                games_data = game_date.get("games", [])
                return [Game.from_schedule_api(g) for g in games_data]

        return []

    def get_boxscore(self, game_id: str) -> Optional[dict]:
        """Fetch raw boxscore data for a specific game"""
        url = f"{self.base_url}/api/stats/boxscore"
        headers = {"X-NBA-Api-Key": self.stats_api_key}
        params = {"gameId": game_id, "measureType": "Traditional"}

        return self._request_with_retry(url, headers, params)

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
