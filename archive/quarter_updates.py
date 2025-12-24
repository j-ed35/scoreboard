"""
NBA Quarter-End Updates to Slack
Monitors games in progress and posts scoring updates after each quarter
Uses schedule API for detection + boxscore API for detailed stats
"""

import os
import requests
import time
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
SCHEDULE_API_KEY = os.getenv("SCHEDULE_API_KEY")
STATS_API_KEY = os.getenv("STATS_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
NBA_BASE_URL = "https://api.nba.com/v0"

# Polling configuration
POLL_INTERVAL_SECONDS = 10  # Check every 10 seconds

# Track which quarters have been posted for each game
# Format: {game_id: set(quarter_numbers)}
posted_quarters = {}


def get_todays_games() -> List[Dict]:
    """Fetch today's NBA games using the rolling schedule endpoint"""
    url = f"{NBA_BASE_URL}/api/schedule/rolling"
    headers = {"X-NBA-Api-Key": SCHEDULE_API_KEY}
    params = {
        "leagueId": "00",  # NBA
        "gameDate": "TODAY",
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract games from today's date
        rolling_schedule = data.get("rollingSchedule", {})
        game_dates = rolling_schedule.get("gameDates", [])

        # Date format in API is "MM/DD/YYYY HH:MM:SS"
        today = datetime.now().strftime("%m/%d/%Y")
        for game_date in game_dates:
            if game_date.get("gameDate", "").startswith(today):
                return game_date.get("games", [])

        return []
    except Exception as e:
        print(f"Error fetching today's games: {e}")
        return []


def get_boxscore(game_id: str) -> Optional[Dict]:
    """Fetch boxscore data for a specific game"""
    url = f"{NBA_BASE_URL}/api/stats/boxscore"
    headers = {"X-NBA-Api-Key": STATS_API_KEY}
    params = {"gameId": game_id, "measureType": "Traditional"}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching boxscore for game {game_id}: {e}")
        return None


def get_team_leaders(players: List[Dict], num_leaders: int = 2) -> List[Dict]:
    """
    Get top scorers for a team from player stats
    Sorts by PTS, then by (PTS + REB + AST) for tiebreaker
    Players must have played (played='1')
    """
    # Filter to players who actually played
    active_players = [p for p in players if p.get("played") == "1"]

    # Sort by points (primary), then by PTS+REB+AST (tiebreaker)
    sorted_players = sorted(
        active_players,
        key=lambda p: (
            p.get("statistics", {}).get("points", 0),
            p.get("statistics", {}).get("points", 0)
            + p.get("statistics", {}).get("reboundsTotal", 0)
            + p.get("statistics", {}).get("assists", 0),
        ),
        reverse=True,
    )

    return sorted_players[:num_leaders]


def format_player_stat_line(player: Dict) -> str:
    """Format a player's stat line for Slack message

    Format: Name – PTS | 3PM (if >0) | FG (if perfect) | AST (if >2) | REB (if >1)
    """
    name = player.get("name", "Unknown Player")
    stats_obj = player.get("statistics", {})

    pts = stats_obj.get("points", 0)
    reb = stats_obj.get("reboundsTotal", 0)
    ast = stats_obj.get("assists", 0)
    threes = stats_obj.get("threePointersMade", 0)
    fg_made = stats_obj.get("fieldGoalsMade", 0)
    fg_att = stats_obj.get("fieldGoalsAttempted", 0)

    # Start with points (always shown)
    stat_parts = [f"{pts} PTS"]

    # Add 3-pointers made if > 0
    if threes > 0:
        stat_parts.append(f"{threes} 3PM")

    # Add FG if they shot perfectly (100%)
    if fg_made > 0 and fg_made == fg_att:
        stat_parts.append(f"{fg_made}-{fg_att} FG")

    # Add assists if > 2 (based on your examples)
    if ast > 2:
        stat_parts.append(f"{ast} AST")

    # Add rebounds if > 1 (based on your examples)
    if reb > 1:
        stat_parts.append(f"{reb} REB")

    return f"* {name} – {' | '.join(stat_parts)}"


def detect_quarter_end(game: Dict) -> Optional[int]:
    """
    Detect if a quarter just ended based on gameStatusText
    Returns quarter number (1-4) if quarter ended, None otherwise
    """
    game_status_text = game.get("gameStatusText", "").strip()
    game_status = game.get("gameStatus", 1)

    # gameStatus: 1 = not started, 2 = in progress, 3 = finished

    # Check for halftime (end of Q2)
    if "Halftime" in game_status_text or "Half" in game_status_text:
        return 2

    # Check for end of Q1, Q3 based on "End Q" pattern
    if "End Q1" in game_status_text:
        return 1
    if "End Q3" in game_status_text:
        return 3

    # Check for final (end of Q4)
    if game_status == 3:  # Game finished
        return 4

    return None


def create_quarter_message(game: Dict, boxscore: Dict, quarter: int) -> str:
    """Create formatted Slack message for quarter end"""
    # Get team info from schedule game data (has current scores)
    home_team = game.get("homeTeam", {})
    away_team = game.get("visitorTeam", {})

    home_name = home_team.get("teamName", "Home")
    home_code = home_team.get("teamTricode", "HOME")
    away_name = away_team.get("teamName", "Away")
    away_code = away_team.get("teamTricode", "AWAY")
    home_score = home_team.get("score", 0)
    away_score = away_team.get("score", 0)

    # Get players from boxscore for detailed stats
    home_players = boxscore.get("homeTeam", {}).get("players", [])
    away_players = boxscore.get("awayTeam", {}).get("players", [])

    # Determine leading/trailing team
    if home_score > away_score:
        leader_name = home_name
        leader_code = home_code
        trailer_name = away_name
        trailer_code = away_code
        leader_score = home_score
        trailer_score = away_score
        leader_players = home_players
        trailer_players = away_players
    elif away_score > home_score:
        leader_name = away_name
        leader_code = away_code
        trailer_name = home_name
        trailer_code = home_code
        leader_score = away_score
        trailer_score = home_score
        leader_players = away_players
        trailer_players = home_players
    else:
        # Tied - use away as "leader" for consistent format
        leader_name = away_name
        leader_code = away_code
        trailer_name = home_name
        trailer_code = home_code
        leader_score = away_score
        trailer_score = home_score
        leader_players = away_players
        trailer_players = home_players

    # Quarter name
    quarter_name = {2: "half"}.get(quarter, f"end of Q{quarter}")

    # Get leaders for each team
    leader_top_performers = get_team_leaders(leader_players)
    trailer_top_performers = get_team_leaders(trailer_players)

    # Build message - format: "65-62 Washington, at half."
    message = f"{leader_score}-{trailer_score} :_{leader_code}:, at {quarter_name}.\n"

    message += f"*Top Performers* – :_{leader_code}:\n"
    for player in leader_top_performers:
        message += f"{format_player_stat_line(player)}\n"

    message += f"*Top Performers* – :_{trailer_code}:\n"
    for player in trailer_top_performers:
        message += f"{format_player_stat_line(player)}\n"

    return message.strip()


def post_to_slack(message: str) -> bool:
    """Post message to Slack webhook"""
    if not SLACK_WEBHOOK_URL:
        print("No Slack webhook URL configured")
        return False

    payload = {"text": message}

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print(f"Posted to Slack successfully")
        return True
    except Exception as e:
        print(f"Error posting to Slack: {e}")
        return False


def check_and_post_quarter_updates():
    """Main function to check games and post quarter updates"""
    print(f"\nChecking for games at {datetime.now().strftime('%I:%M:%S %p')}")

    # Get today's games
    games = get_todays_games()

    # Only process active games (gameStatus == 2 or recently finished == 3)
    active_games = [g for g in games if g.get("gameStatus") in [2, 3]]

    if not active_games:
        print("No active games")
        return

    print(f"Found {len(active_games)} active game(s)")

    for game in active_games:
        game_id = game.get("gameId")
        home_team = game.get("homeTeam", {}).get("teamName", "Home")
        home_code = game.get("homeTeam", {}).get("teamTricode", "HOME")
        away_team = game.get("visitorTeam", {}).get("teamName", "Away")
        away_code = game.get("visitorTeam", {}).get("teamTricode", "AWAY")
        game_status = game.get("gameStatus", 1)
        game_status_text = game.get("gameStatusText", "").strip()
        period = game.get("period", 0)

        print(f"\n  _{away_code} @ _{home_code}")
        print(f"    Status: {game_status_text} (Period {period})")

        # Initialize tracking for this game if needed
        if game_id not in posted_quarters:
            posted_quarters[game_id] = set()

        # Check if a quarter just ended
        quarter_ended = detect_quarter_end(game)

        if quarter_ended and quarter_ended not in posted_quarters[game_id]:
            print(f"    → Quarter {quarter_ended} ended!")

            # Get boxscore for detailed stats
            boxscore = get_boxscore(game_id)
            if boxscore:
                # Create and post message
                message = create_quarter_message(game, boxscore, quarter_ended)
                print(
                    f"\n--- Message Preview ---\n{message}\n-----------------------\n"
                )

                if post_to_slack(message):
                    posted_quarters[game_id].add(quarter_ended)
                    print(f"    ✓ Posted Q{quarter_ended} update")
        else:
            if quarter_ended:
                print(f"    ✓ Q{quarter_ended} already posted")
            else:
                print(f"    → No quarter end detected")


def run_continuous_monitoring():
    """
    Main loop: continuously monitor games and post quarter updates
    Runs until interrupted with CTRL+C
    """
    print("=" * 60)
    print("NBA Quarter-End Monitor Started")
    print(f"Polling interval: {POLL_INTERVAL_SECONDS} seconds")
    print("Press CTRL+C to stop")
    print("=" * 60)

    try:
        while True:
            check_and_post_quarter_updates()

            # Sleep until next check
            print(f"\n→ Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Monitor stopped by user")
        print("=" * 60)


if __name__ == "__main__":
    run_continuous_monitoring()
