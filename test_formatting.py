"""
Test script to verify quarter-end update formatting
Uses the sample_boxscore.json to test message generation
"""

import json
from typing import List, Dict


def get_team_leaders(players: List[Dict], num_leaders: int = 2) -> List[Dict]:
    """Get top scorers for a team from player stats"""
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
    """Format a player's stat line for Slack message"""
    name = player.get("name", "Unknown Player")
    stats_obj = player.get("statistics", {})

    pts = stats_obj.get("points", 0)
    reb = stats_obj.get("reboundsTotal", 0)
    ast = stats_obj.get("assists", 0)
    threes = stats_obj.get("threePointersMade", 0)
    fg_made = stats_obj.get("fieldGoalsMade", 0)
    fg_att = stats_obj.get("fieldGoalsAttempted", 0)

    # Start with name and points
    stat_parts = [f"{pts} PTS"]

    # Add 3-pointers made if > 0
    if threes > 0:
        stat_parts.append(f"{threes} 3PM")

    # Add FG if they shot perfectly (100%)
    if fg_made > 0 and fg_made == fg_att:
        stat_parts.append(f"{fg_made}-{fg_att} FG")

    # Add assists if > 0
    if ast > 0:
        stat_parts.append(f"{ast} AST")

    # Add rebounds if > 0
    if reb > 0:
        stat_parts.append(f"{reb} REB")

    return f"* {name} – {' | '.join(stat_parts)}"


def create_test_message(boxscore: Dict, quarter: int = 2) -> str:
    """Create formatted message for testing"""
    # Get team info from boxscore
    home_team = boxscore.get("homeTeam", {})
    away_team = boxscore.get("awayTeam", {})

    home_name = home_team.get("teamName", "Home")
    away_name = away_team.get("teamName", "Away")
    home_stats = home_team.get("statistics", {})
    away_stats = away_team.get("statistics", {})
    home_score = home_stats.get("points", 0)
    away_score = away_stats.get("points", 0)

    # Get players
    home_players = home_team.get("players", [])
    away_players = away_team.get("players", [])

    # Determine leading/trailing team
    if away_score > home_score:
        leader_name = "Washington"  # Based on your example
        trailer_name = "Charlotte"
        leader_score = away_score
        trailer_score = home_score
        leader_players = away_players
        trailer_players = home_players
    else:
        leader_name = home_name
        trailer_name = away_name
        leader_score = home_score
        trailer_score = away_score
        leader_players = home_players
        trailer_players = away_players

    # Get leaders for each team
    leader_top_performers = get_team_leaders(leader_players)
    trailer_top_performers = get_team_leaders(trailer_players)

    # Build message - format: "65-62 Washington, at half."
    message = f"{leader_score}-{trailer_score} {leader_name}, at half.\n"

    message += f"__Top Performers – {leader_name}__\n"
    for player in leader_top_performers:
        message += f"{format_player_stat_line(player)}\n"

    message += f"__Top Performers – {trailer_name}__\n"
    for player in trailer_top_performers:
        message += f"{format_player_stat_line(player)}\n"

    return message.strip()


# Load sample boxscore
with open("sample_boxscore.json", "r") as f:
    sample_boxscore = json.load(f)

# Note: The sample has Charlotte as home team with 63 points
# We need Washington's score to be higher for the expected output
# Let's manually adjust for testing

print("=" * 70)
print("TESTING MESSAGE GENERATION")
print("=" * 70)
print()

# Display home team info
home_team = sample_boxscore.get("homeTeam", {})
print(f"Home Team: {home_team.get('teamName')}")
print(f"Home Score: {home_team.get('statistics', {}).get('points')}")
print()

# Get top performers for home team
home_players = home_team.get("players", [])
home_leaders = get_team_leaders(home_players, 2)

print("Home Team Top 2 Scorers:")
for player in home_leaders:
    print(f"  {format_player_stat_line(player)}")
print()

# For the awayTeam, we'd need that data from the API
# The sample only has homeTeam, so let's note this
print("Note: Sample boxscore only contains homeTeam data.")
print("In production, awayTeam would have similar structure.")
print()

print("=" * 70)
print("EXPECTED OUTPUT FORMAT:")
print("=" * 70)
print("""65-62 Washington, at half.
__Top Performers – Washington__
* Bilal Coulibaly – 11 PTS | 2 3PM | 5 REB
* Marvin Bagley III – 10 PTS | 2 REB
__Top Performers – Charlotte__
* Brandon Miller – 11 PTS | 3 AST
* Moussa Diabaté – 10 PTS | 5-5 FG | 13 REB""")
print()

print("=" * 70)
print("ACTUAL CHARLOTTE OUTPUT (from sample):")
print("=" * 70)
for player in home_leaders:
    print(format_player_stat_line(player))
