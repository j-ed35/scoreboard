"""
NBA Game Summary - Posts current status of all games to Slack

# Dry run (preview)
python summary.py --dry-run

# Post to Slack
python summary.py

"""

import argparse
import logging
import sys

from src.config import config
from src.formatters import SlackMessageBuilder
from src.models import PlayerDailyLeader, TeamDailyLeader
from src.nba_api import NBAApiClient
from src.slack_client import SlackClient

logger = logging.getLogger(__name__)


class GameSummaryService:
    """Service for posting game summaries to Slack"""

    def __init__(self, dry_run: bool = False):
        self.api = NBAApiClient()
        self.formatter = SlackMessageBuilder()
        self.slack = SlackClient(dry_run=dry_run)

    def post_summary(self) -> None:
        """Fetch all active/completed games and post summary to Slack"""
        games = self.api.get_todays_games()
        active_games = [g for g in games if g.is_active]

        if not active_games:
            logger.info("No active or completed games found")
            return

        logger.info(f"Found {len(active_games)} game(s)")

        # Enrich all games with boxscore data
        for game in active_games:
            self.api.enrich_game_with_boxscore(game)

        # Fetch daily leaders
        player_leaders = self._fetch_player_leaders()
        team_leaders = self._fetch_team_leaders()

        # Build the summary message
        message = self._build_summary_message(active_games, player_leaders, team_leaders)

        # Post to Slack
        self.slack.post_message(message)

    def _fetch_player_leaders(self) -> dict[str, list[PlayerDailyLeader]]:
        """Fetch top 3 player leaders for pts, reb, ast, fg3m, fgpct"""
        stats = ["pts", "reb", "ast", "fg3m", "fgpct"]
        leaders = {}

        for stat in stats:
            data = self.api.get_player_daily_leaders(stat)
            if data and "playerstats" in data:
                leaders[stat] = [
                    PlayerDailyLeader.from_api(p, stat)
                    for p in data["playerstats"][:3]
                ]
            else:
                leaders[stat] = []

        return leaders

    def _fetch_team_leaders(self) -> dict[str, list[TeamDailyLeader]]:
        """Fetch top 3 team leaders for pts, ast, fgpct, fg3pct"""
        stats = ["pts", "ast", "fgpct", "fg3pct"]
        leaders = {}

        for stat in stats:
            data = self.api.get_team_daily_leaders(stat)
            if data and "teamstats" in data:
                leaders[stat] = [
                    TeamDailyLeader.from_api(t, stat)
                    for t in data["teamstats"][:3]
                ]
            else:
                leaders[stat] = []

        return leaders

    def _build_summary_message(
        self,
        games: list,
        player_leaders: dict[str, list[PlayerDailyLeader]],
        team_leaders: dict[str, list[TeamDailyLeader]],
    ) -> dict:
        """Build Block Kit message with all game summaries"""
        blocks = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "NBA Scoreboard",
                    "emoji": True,
                },
            }
        )

        for game in games:
            blocks.append({"type": "divider"})
            blocks.append(self._build_game_block(game))

        # Add daily leaders section
        blocks.append({"type": "divider"})
        blocks.append(self._build_leaders_block(player_leaders, team_leaders))

        return {"blocks": blocks}

    def _build_leaders_block(
        self,
        player_leaders: dict[str, list[PlayerDailyLeader]],
        team_leaders: dict[str, list[TeamDailyLeader]],
    ) -> dict:
        """Build the daily leaders section"""
        lines = ["*Tonight's Leaders*", ""]

        # Player leaders
        stat_labels = {
            "pts": "PTS",
            "reb": "REB",
            "ast": "AST",
            "fg3m": "3PM",
            "fgpct": "FG%",
        }

        lines.append("*Players*")
        for stat, label in stat_labels.items():
            leaders = player_leaders.get(stat, [])
            if leaders:
                leader_strs = [
                    f"{p.name} ({p.team_tricode}) {p.format_value()}"
                    for p in leaders[:3]
                ]
                lines.append(f"  {label}: {' | '.join(leader_strs)}")

        lines.append("")

        # Team leaders
        team_stat_labels = {
            "pts": "PTS",
            "ast": "AST",
            "fgpct": "FG%",
            "fg3pct": "3P%",
        }

        lines.append("*Teams*")
        for stat, label in team_stat_labels.items():
            leaders = team_leaders.get(stat, [])
            if leaders:
                leader_strs = [
                    f"{t.tricode} {t.format_value()}"
                    for t in leaders[:3]
                ]
                lines.append(f"  {label}: {' | '.join(leader_strs)}")

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    def _build_game_block(self, game) -> dict:
        """Build a section block for a single game"""
        away = game.away_team
        home = game.home_team

        # Score line with clock
        if game.is_tied:
            score_line = f":_{away.tricode}: Tied at {away.score} :_{home.tricode}:  |  {game.game_time_display}"
        else:
            leader, trailer = game.get_leader_and_trailer()
            if leader == away:
                score_line = f":_{away.tricode}: *{away.score}* @ {home.score} :_{home.tricode}:  |  {game.game_time_display}"
            else:
                score_line = f":_{away.tricode}: {away.score} @ *{home.score}* :_{home.tricode}:  |  {game.game_time_display}"

        lines = [score_line]
        lines.append(f"<https://www.nba.com/game/{game.game_id}/box-score|Box Score>")

        # Away team section
        lines.append(f"*:_{away.tricode}: {away.name}*")
        for player in away.get_top_performers(2):
            lines.append(self.formatter._format_player_line(player))
        if away.stats:
            lines.append(self.formatter._format_team_stats(away.stats))

        # Home team section
        lines.append(f"*:_{home.tricode}: {home.name}*")
        for player in home.get_top_performers(2):
            lines.append(self.formatter._format_player_line(player))
        if home.stats:
            lines.append(self.formatter._format_team_stats(home.stats))

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }


def main():
    parser = argparse.ArgumentParser(
        description="NBA Game Summary - Post all games to Slack"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages instead of posting to Slack",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%I:%M:%S %p",
    )

    errors = config.validate()
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    service = GameSummaryService(dry_run=args.dry_run)
    service.post_summary()


if __name__ == "__main__":
    main()
