"""
NBA Game Summary - Posts current status of all games to Slack

# Dry run (preview)
python summary.py --dry-run

# Post to Slack
python summary.py

"""

import argparse
import sys

from src.config import config
from src.formatters import SlackMessageBuilder
from src.nba_api import NBAApiClient
from src.slack_client import SlackClient


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
            print("No active or completed games found")
            return

        print(f"Found {len(active_games)} game(s)")

        # Enrich all games with boxscore data
        for game in active_games:
            self.api.enrich_game_with_boxscore(game)

        # Build the summary message
        message = self._build_summary_message(active_games)

        # Post to Slack
        self.slack.post_message(message)

    def _build_summary_message(self, games: list) -> dict:
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

        return {"blocks": blocks}

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
    args = parser.parse_args()

    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    service = GameSummaryService(dry_run=args.dry_run)
    service.post_summary()


if __name__ == "__main__":
    main()
