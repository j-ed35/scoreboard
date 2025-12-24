import os
import rumps
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import threading

load_dotenv()

API_KEY = os.getenv("NBA_API_KEY")
BASE_URL = "https://api.nba.com/v0/api/scores/scoreboard/date"
GAME_URL = "https://api.nba.com/v0/api/scores/scoreboard/games"


class NBAScoreboard(rumps.App):
    def __init__(self):
        super(NBAScoreboard, self).__init__("🏀", quit_button=None)
        self.current_date = datetime.now().date()
        self.menu = ["Loading..."]
        self.games_cache = []
        self.update_scores()

    def previous_day(self, _):
        self.current_date -= timedelta(days=1)
        self.update_scores()

    def next_day(self, _):
        self.current_date += timedelta(days=1)
        self.update_scores()

    def go_to_today(self, _):
        self.current_date = datetime.now().date()
        self.update_scores()

    def show_game_leaders(self, sender):
        game_id = sender.game_id

        # Find game info from cache
        game_info = None
        for game in self.games_cache:
            if game["gameId"] == game_id:
                game_info = game
                break

        leaders = self.fetch_game_leaders(game_id)

        if leaders:
            away_leaders = leaders.get("awayLeaders", {})
            home_leaders = leaders.get("homeLeaders", {})

            # Get team names and scores
            away_team = game_info["awayTeam"]["teamTricode"] if game_info else "Away"
            home_team = game_info["homeTeam"]["teamTricode"] if game_info else "Home"
            away_score = game_info["awayTeam"]["score"] if game_info else 0
            home_score = game_info["homeTeam"]["score"] if game_info else 0

            # Build message with team leading scorer
            msg = f"{'=' * 4}\n"
            msg += f"{away_team} {away_score}  @  {home_team} {home_score}\n"
            msg += f"{'=' * 4}\n\n"

            msg += f"🏀 {away_team} Leading Scorer:\n"
            msg += f"   {away_leaders.get('name', 'N/A')}"
            if away_leaders.get("jerseyNum"):
                msg += f" #{away_leaders.get('jerseyNum')}"
            msg += f"\n   {away_leaders.get('points', 0)} PTS  •  "
            msg += f"{away_leaders.get('rebounds', 0)} REB  •  "
            msg += f"{away_leaders.get('assists', 0)} AST"
            if away_leaders.get("blocks", 0) > 0:
                msg += f"  •  {away_leaders.get('blocks', 0)} BLK"
            if away_leaders.get("steals", 0) > 0:
                msg += f"  •  {away_leaders.get('steals', 0)} STL"
            msg += "\n\n"

            msg += f"🏀 {home_team} Leading Scorer:\n"
            msg += f"   {home_leaders.get('name', 'N/A')}"
            if home_leaders.get("jerseyNum"):
                msg += f" #{home_leaders.get('jerseyNum')}"
            msg += f"\n   {home_leaders.get('points', 0)} PTS  •  "
            msg += f"{home_leaders.get('rebounds', 0)} REB  •  "
            msg += f"{home_leaders.get('assists', 0)} AST"
            if home_leaders.get("blocks", 0) > 0:
                msg += f"  •  {home_leaders.get('blocks', 0)} BLK"
            if home_leaders.get("steals", 0) > 0:
                msg += f"  •  {home_leaders.get('steals', 0)} STL"

            rumps.alert(title="Game Leaders", message=msg)
        else:
            rumps.alert(title="Game Leaders", message="Stats not available yet")

    def update_scores(self):
        games = self.fetch_games()
        self.games_cache = games
        self.menu.clear()

        # Date header
        date_str = self.current_date.strftime("%B %d, %Y")
        if self.current_date == datetime.now().date():
            date_str += " (Today)"
        self.menu.add(rumps.MenuItem(f"📅 {date_str}", callback=None))
        self.menu.add(None)

        if not games:
            self.title = "🏀"
            self.menu.add(rumps.MenuItem("No games on this date", callback=None))
        else:
            # Update icon with live game count
            live_count = sum(1 for g in games if g["gameStatus"] == 2)
            self.title = f"🏀 {live_count}" if live_count > 0 else "🏀"

            for game in games:
                away = game["awayTeam"]
                home = game["homeTeam"]
                status = game["gameStatusText"]
                game_id = game["gameId"]

                away_tri = away["teamTricode"]
                home_tri = home["teamTricode"]
                away_score = away["score"]
                home_score = home["score"]

                # Status indicator
                if game["gameStatus"] == 1:
                    indicator = "⏰"
                elif game["gameStatus"] == 2:
                    indicator = "🔴"
                else:
                    indicator = "✓"

                game_str = (
                    f"{indicator} {away_tri} {away_score} @ {home_tri} {home_score}"
                )

                # Make game clickable if it has started
                if game["gameStatus"] >= 2:
                    game_item = rumps.MenuItem(
                        game_str, callback=self.show_game_leaders
                    )
                    game_item.game_id = game_id
                    self.menu.add(game_item)
                else:
                    self.menu.add(rumps.MenuItem(game_str, callback=None))

                self.menu.add(rumps.MenuItem(f"    {status}", callback=None))

        self.menu.add(None)
        # Add keyboard shortcuts
        self.menu.add(
            rumps.MenuItem("← Previous Day", callback=self.previous_day, key="[")
        )
        self.menu.add(rumps.MenuItem("Today", callback=self.go_to_today, key="t"))
        self.menu.add(rumps.MenuItem("→ Next Day", callback=self.next_day, key="]"))
        self.menu.add(None)
        self.menu.add(
            rumps.MenuItem(
                f"Updated: {datetime.now().strftime('%I:%M %p')}", callback=None
            )
        )
        self.menu.add(None)
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application, key="q"))

        # Auto-refresh every 30 seconds only if viewing today
        if self.current_date == datetime.now().date():
            threading.Timer(30.0, self.update_scores).start()

    def fetch_games(self):
        try:
            headers = {"X-NBA-Api-Key": API_KEY}
            params = {
                "leagueId": "00",
                "gameDate": self.current_date.strftime("%Y-%m-%d"),
            }
            response = requests.get(BASE_URL, headers=headers, params=params, timeout=5)

            if response.status_code != 200:
                return []

            data = response.json()
            return data.get("scoreboard", {}).get("games", [])
        except:
            return []

    def fetch_game_leaders(self, game_id):
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
        except:
            return None


if __name__ == "__main__":
    NBAScoreboard().run()
