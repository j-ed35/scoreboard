"""NBA API client for schedule and boxscore data"""

from datetime import datetime
from typing import Optional

import requests

from .config import config
from .models import Game, Player, TeamStats


class NBAApiClient:
    """Client for interacting with NBA API endpoints"""

    def __init__(self):
        self.base_url = config.nba_base_url
        self.schedule_api_key = config.schedule_api_key
        self.stats_api_key = config.stats_api_key

    def get_todays_games(self) -> list[Game]:
        """Fetch today's NBA games from the rolling schedule endpoint"""
        url = f"{self.base_url}/api/schedule/rolling"
        headers = {"X-NBA-Api-Key": self.schedule_api_key}
        params = {"leagueId": "00", "gameDate": "TODAY"}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            rolling_schedule = data.get("rollingSchedule", {})
            game_dates = rolling_schedule.get("gameDates", [])

            today = datetime.now().strftime("%m/%d/%Y")
            for game_date in game_dates:
                if game_date.get("gameDate", "").startswith(today):
                    games_data = game_date.get("games", [])
                    return [Game.from_schedule_api(g) for g in games_data]

            return []
        except requests.RequestException as e:
            print(f"Error fetching today's games: {e}")
            return []

    def get_boxscore(self, game_id: str) -> Optional[dict]:
        """Fetch raw boxscore data for a specific game"""
        url = f"{self.base_url}/api/stats/boxscore"
        headers = {"X-NBA-Api-Key": self.stats_api_key}
        params = {"gameId": game_id, "measureType": "Traditional"}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching boxscore for game {game_id}: {e}")
            return None

    def enrich_game_with_boxscore(self, game: Game) -> bool:
        """Enrich a Game object with player data from boxscore API"""
        boxscore = self.get_boxscore(game.game_id)
        if not boxscore:
            return False

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
