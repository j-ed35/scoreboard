"""
Debug script to test NBA API connections and view game data
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import json

load_dotenv()

SCHEDULE_API_KEY = os.getenv("SCHEDULE_API_KEY")
STATS_API_KEY = os.getenv("STATS_API_KEY")
NBA_BASE_URL = "https://api.nba.com/v0"


def test_schedule_api():
    """Test the schedule API to see today's games"""
    print("=" * 60)
    print("TESTING SCHEDULE API")
    print("=" * 60)

    url = f"{NBA_BASE_URL}/api/schedule/rolling"
    headers = {"X-NBA-Api-Key": SCHEDULE_API_KEY}
    params = {"leagueId": "00", "gameDate": "TODAY"}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        print(f"\nSchedule API Response Status: {response.status_code}")

        # Find today's games - the data is nested under rollingSchedule
        rolling_schedule = data.get("rollingSchedule", {})
        game_dates = rolling_schedule.get("gameDates", [])

        today = datetime.now().strftime("%m/%d/%Y")
        print(f"Looking for games on: {today}")
        print(f"Number of game dates returned: {len(game_dates)}")

        for game_date in game_dates:
            date_str = game_date.get("gameDate", "")
            print(f"\nFound game date: {date_str}")

            # Date format is "MM/DD/YYYY HH:MM:SS", so we need to compare just the date part
            if date_str.startswith(today):
                games = game_date.get("games", [])
                print(f"Number of games today: {len(games)}\n")

                for i, game in enumerate(games, 1):
                    game_id = game.get("gameId")
                    home = game.get("homeTeam", {})
                    visitor = game.get("visitorTeam", {})
                    game_time = game.get("gameDateTimeUTC", "")
                    status = game.get("gameStatusText", "")

                    home_score = home.get("score", 0)
                    visitor_score = visitor.get("score", 0)

                    print(f"{i}. {visitor.get('teamCity')} {visitor.get('teamName')} @ {home.get('teamCity')} {home.get('teamName')}")
                    print(f"   Game ID: {game_id}")
                    print(f"   Score: {visitor_score} - {home_score}")
                    print(f"   Time: {game_time}")
                    print(f"   Status: {status}")
                    print()

                return games

        print("No games found for today")
        return []

    except Exception as e:
        print(f"Error testing schedule API: {e}")
        return []


def test_boxscore_api(game_id):
    """Test the boxscore API for a specific game"""
    print("=" * 60)
    print(f"TESTING BOXSCORE API - Game {game_id}")
    print("=" * 60)

    url = f"{NBA_BASE_URL}/api/stats/boxscore"
    headers = {"X-NBA-Api-Key": STATS_API_KEY}
    params = {"gameId": game_id, "measureType": "Traditional"}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        print(f"\nBoxscore API Response Status: {response.status_code}")

        # Game info
        game = data.get("game", {})
        print(f"\nGame Status: {game.get('gameStatus')}")
        print(f"Period: {game.get('period')}")
        print(f"Game Clock: {game.get('gameClock')}")

        # Team scores
        home_team = game.get("homeTeam", {})
        away_team = game.get("awayTeam", {})

        print(f"\n{away_team.get('teamName')}: {away_team.get('score')}")
        print(f"{home_team.get('teamName')}: {home_team.get('score')}")

        # Player stats preview
        player_stats = data.get("playerStats", [])
        print(f"\nTotal players with stats: {len(player_stats)}")

        if player_stats:
            print("\nSample player stat (first player):")
            sample = player_stats[0]
            print(f"  Name: {sample.get('first_name')} {sample.get('last_name')}")
            print(f"  Team ID: {sample.get('team_id')}")
            print(
                f"  Stats: {sample.get('pts')} PTS, {sample.get('reb')} REB, {sample.get('ast')} AST"
            )

            # Show top scorers
            sorted_by_pts = sorted(
                player_stats, key=lambda p: p.get("pts", 0), reverse=True
            )
            print("\nTop 5 Scorers:")
            for i, player in enumerate(sorted_by_pts[:5], 1):
                name = f"{player.get('first_name')} {player.get('last_name')}"
                pts = player.get("pts", 0)
                reb = player.get("reb", 0)
                ast = player.get("ast", 0)
                print(f"  {i}. {name}: {pts} PTS, {reb} REB, {ast} AST")

        return data

    except Exception as e:
        print(f"Error testing boxscore API: {e}")
        import traceback

        traceback.print_exc()
        return None


def save_sample_data(games, boxscore):
    """Save sample data to files for reference"""
    with open("sample_schedule.json", "w") as f:
        json.dump(games, f, indent=2)
    print("\nSaved sample schedule to: sample_schedule.json")

    if boxscore:
        with open("sample_boxscore.json", "w") as f:
            json.dump(boxscore, f, indent=2)
        print("Saved sample boxscore to: sample_boxscore.json")


if __name__ == "__main__":
    # Test schedule API
    games = test_schedule_api()

    # Test boxscore API with first game if available
    boxscore = None
    if games:
        first_game_id = games[0].get("gameId")
        boxscore = test_boxscore_api(first_game_id)

    # Save sample data
    save_sample_data(games, boxscore)

    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)
