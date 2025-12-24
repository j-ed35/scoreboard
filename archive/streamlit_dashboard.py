import os
import streamlit as st
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("NBA_API_KEY")
BASE_URL = "https://api.nba.com/v0/api/scores/scoreboard/date"
GAME_URL = "https://api.nba.com/v0/api/scores/scoreboard/games"
BOXSCORE_URL = "https://api.nba.com/v0/api/stats/boxscore"


def fetch_games(game_date):
    """Fetch games for a specific date"""
    try:
        headers = {"X-NBA-Api-Key": API_KEY}
        params = {
            "leagueId": "00",
            "gameDate": game_date.strftime("%Y-%m-%d"),
        }
        response = requests.get(BASE_URL, headers=headers, params=params, timeout=5)

        if response.status_code != 200:
            return []

        data = response.json()
        return data.get("scoreboard", {}).get("games", [])
    except Exception as e:
        st.error(f"Error fetching games: {e}")
        return []


def fetch_game_leaders(game_id):
    """Fetch game leaders for a specific game"""
    try:
        headers = {"X-NBA-Api-Key": API_KEY}
        params = {"leagueId": "00", "gameId": game_id}
        response = requests.get(GAME_URL, headers=headers, params=params, timeout=5)

        if response.status_code != 200:
            return None

        data = response.json()
        games = data.get("scoreboard", {}).get("games", [])
        if games:
            return games[0].get("gameLeaders", {})
        return None
    except Exception as e:
        st.error(f"Error fetching game leaders: {e}")
        return None


def fetch_boxscore(game_id):
    """Fetch detailed boxscore for a specific game"""
    try:
        headers = {"X-NBA-Api-Key": API_KEY}
        params = {"gameId": game_id}
        response = requests.get(BOXSCORE_URL, headers=headers, params=params, timeout=5)

        if response.status_code != 200:
            return None

        data = response.json()
        return data
    except Exception as e:
        st.error(f"Error fetching boxscore: {e}")
        return None


def format_player_stats(player):
    """Format player statistics for display"""
    return {
        "Name": f"{player.get('name', 'N/A')} #{player.get('jerseyNum', '')}",
        "PTS": player.get("points", 0),
        "REB": player.get("rebounds", 0),
        "AST": player.get("assists", 0),
        "STL": player.get("steals", 0),
        "BLK": player.get("blocks", 0),
        "FG": f"{player.get('fieldGoalsMade', 0)}/{player.get('fieldGoalsAttempted', 0)}",
        "3PT": f"{player.get('threePointersMade', 0)}/{player.get('threePointersAttempted', 0)}",
        "FT": f"{player.get('freeThrowsMade', 0)}/{player.get('freeThrowsAttempted', 0)}",
        "MIN": player.get("minutes", "0:00"),
    }


def generate_game_report(game_id, game_info):
    """Generate a detailed game report with boxscore data"""
    st.subheader("Game Report")

    # Display game header
    away_team = game_info["awayTeam"]["teamTricode"]
    home_team = game_info["homeTeam"]["teamTricode"]
    away_score = game_info["awayTeam"]["score"]
    home_score = game_info["homeTeam"]["score"]

    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        st.metric(label=away_team, value=away_score)
    with col2:
        st.markdown("<h3 style='text-align: center;'>@</h3>", unsafe_allow_html=True)
    with col3:
        st.metric(label=home_team, value=home_score)

    st.markdown(f"**Status:** {game_info['gameStatusText']}")
    st.markdown("---")

    # Fetch game leaders
    with st.spinner("Fetching game leaders..."):
        leaders = fetch_game_leaders(game_id)

    if leaders:
        st.subheader("Game Leaders")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**{away_team} Leading Scorer**")
            away_leader = leaders.get("awayLeaders", {})
            if away_leader:
                st.markdown(f"**{away_leader.get('name', 'N/A')}** #{away_leader.get('jerseyNum', '')}")
                st.write(f"**{away_leader.get('points', 0)}** PTS | "
                        f"{away_leader.get('rebounds', 0)} REB | "
                        f"{away_leader.get('assists', 0)} AST")
                if away_leader.get("blocks", 0) > 0 or away_leader.get("steals", 0) > 0:
                    st.write(f"{away_leader.get('steals', 0)} STL | "
                            f"{away_leader.get('blocks', 0)} BLK")

        with col2:
            st.markdown(f"**{home_team} Leading Scorer**")
            home_leader = leaders.get("homeLeaders", {})
            if home_leader:
                st.markdown(f"**{home_leader.get('name', 'N/A')}** #{home_leader.get('jerseyNum', '')}")
                st.write(f"**{home_leader.get('points', 0)}** PTS | "
                        f"{home_leader.get('rebounds', 0)} REB | "
                        f"{home_leader.get('assists', 0)} AST")
                if home_leader.get("blocks", 0) > 0 or home_leader.get("steals", 0) > 0:
                    st.write(f"{home_leader.get('steals', 0)} STL | "
                            f"{home_leader.get('blocks', 0)} BLK")

        st.markdown("---")

    # Fetch detailed boxscore
    with st.spinner("Fetching detailed boxscore..."):
        boxscore = fetch_boxscore(game_id)

    if boxscore:
        st.subheader("Detailed Box Score")

        # Extract team stats and player stats
        game_data = boxscore.get("game", {})

        # Away team stats
        st.markdown(f"### {away_team} Box Score")
        away_players = game_data.get("awayTeam", {}).get("players", [])
        if away_players:
            away_stats = [format_player_stats(p) for p in away_players if p.get("played", "1") == "1"]
            if away_stats:
                st.dataframe(away_stats, use_container_width=True)
            else:
                st.info("No player stats available yet")
        else:
            st.info("No player stats available yet")

        st.markdown("---")

        # Home team stats
        st.markdown(f"### {home_team} Box Score")
        home_players = game_data.get("homeTeam", {}).get("players", [])
        if home_players:
            home_stats = [format_player_stats(p) for p in home_players if p.get("played", "1") == "1"]
            if home_stats:
                st.dataframe(home_stats, use_container_width=True)
            else:
                st.info("No player stats available yet")
        else:
            st.info("No player stats available yet")

        # Team totals
        st.markdown("---")
        st.subheader("Team Statistics")

        col1, col2 = st.columns(2)

        away_team_stats = game_data.get("awayTeam", {}).get("statistics", {})
        home_team_stats = game_data.get("homeTeam", {}).get("statistics", {})

        with col1:
            st.markdown(f"**{away_team}**")
            if away_team_stats:
                st.write(f"FG: {away_team_stats.get('fieldGoalsMade', 0)}/{away_team_stats.get('fieldGoalsAttempted', 0)} "
                        f"({away_team_stats.get('fieldGoalsPercentage', 0):.1f}%)")
                st.write(f"3PT: {away_team_stats.get('threePointersMade', 0)}/{away_team_stats.get('threePointersAttempted', 0)} "
                        f"({away_team_stats.get('threePointersPercentage', 0):.1f}%)")
                st.write(f"FT: {away_team_stats.get('freeThrowsMade', 0)}/{away_team_stats.get('freeThrowsAttempted', 0)} "
                        f"({away_team_stats.get('freeThrowsPercentage', 0):.1f}%)")
                st.write(f"Rebounds: {away_team_stats.get('reboundsTotal', 0)}")
                st.write(f"Assists: {away_team_stats.get('assists', 0)}")
                st.write(f"Turnovers: {away_team_stats.get('turnovers', 0)}")

        with col2:
            st.markdown(f"**{home_team}**")
            if home_team_stats:
                st.write(f"FG: {home_team_stats.get('fieldGoalsMade', 0)}/{home_team_stats.get('fieldGoalsAttempted', 0)} "
                        f"({home_team_stats.get('fieldGoalsPercentage', 0):.1f}%)")
                st.write(f"3PT: {home_team_stats.get('threePointersMade', 0)}/{home_team_stats.get('threePointersAttempted', 0)} "
                        f"({home_team_stats.get('threePointersPercentage', 0):.1f}%)")
                st.write(f"FT: {home_team_stats.get('freeThrowsMade', 0)}/{home_team_stats.get('freeThrowsAttempted', 0)} "
                        f"({home_team_stats.get('freeThrowsPercentage', 0):.1f}%)")
                st.write(f"Rebounds: {home_team_stats.get('reboundsTotal', 0)}")
                st.write(f"Assists: {home_team_stats.get('assists', 0)}")
                st.write(f"Turnovers: {home_team_stats.get('turnovers', 0)}")
    else:
        st.warning("Detailed boxscore not available for this game")


def main():
    st.set_page_config(
        page_title="NBA Scoreboard Dashboard",
        page_icon="🏀",
        layout="wide",
    )

    st.title("🏀 NBA Scoreboard Dashboard")

    # Date selector
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        selected_date = st.date_input(
            "Select Date",
            value=datetime.now().date(),
            max_value=datetime.now().date() + timedelta(days=7),
        )

    # Auto-refresh toggle
    col1, col2 = st.columns([3, 1])
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)

    # Fetch games
    with st.spinner("Loading games..."):
        games = fetch_games(selected_date)

    if not games:
        st.info(f"No games scheduled for {selected_date.strftime('%B %d, %Y')}")
        return

    # Display game count
    live_count = sum(1 for g in games if g["gameStatus"] == 2)
    total_games = len(games)

    st.markdown(f"**{total_games} games** | **{live_count} live** 🔴")
    st.markdown("---")

    # Display games in a grid
    for idx, game in enumerate(games):
        away_team = game["awayTeam"]
        home_team = game["homeTeam"]
        status = game["gameStatusText"]
        game_id = game["gameId"]

        away_tri = away_team["teamTricode"]
        home_tri = home_team["teamTricode"]
        away_score = away_team["score"]
        home_score = home_team["score"]

        # Status indicator
        if game["gameStatus"] == 1:
            indicator = "⏰ Scheduled"
            status_color = "#FFA500"
        elif game["gameStatus"] == 2:
            indicator = "🔴 LIVE"
            status_color = "#FF0000"
        else:
            indicator = "✓ Final"
            status_color = "#00FF00"

        # Create game card
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 1, 2, 2])

            with col1:
                st.markdown(f"### {away_tri}")
                st.markdown(f"<h1 style='text-align: center;'>{away_score}</h1>", unsafe_allow_html=True)

            with col2:
                st.markdown("<h3 style='text-align: center;'>@</h3>", unsafe_allow_html=True)

            with col3:
                st.markdown(f"### {home_tri}")
                st.markdown(f"<h1 style='text-align: center;'>{home_score}</h1>", unsafe_allow_html=True)

            with col4:
                st.markdown(f"<p style='color: {status_color};'><b>{indicator}</b></p>", unsafe_allow_html=True)
                st.markdown(f"*{status}*")

                # Game report button (only if game has started)
                if game["gameStatus"] >= 2:
                    if st.button("📊 Game Report", key=f"report_{game_id}"):
                        st.session_state[f"show_report_{game_id}"] = True

            # Display game report if button was clicked
            if st.session_state.get(f"show_report_{game_id}", False):
                with st.expander("Game Report", expanded=True):
                    generate_game_report(game_id, game)
                    if st.button("Close Report", key=f"close_{game_id}"):
                        st.session_state[f"show_report_{game_id}"] = False
                        st.rerun()

            st.markdown("---")

    # Display last updated time
    st.caption(f"Last updated: {datetime.now().strftime('%I:%M:%S %p')}")

    # Auto-refresh
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()


if __name__ == "__main__":
    main()
