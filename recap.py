"""
NBA Daily Recap - Posts recap of yesterday's completed games to Slack

# Dry run (preview)
python recap.py --dry-run

# Post to Slack
python recap.py

# Post recap with yesterday's daily leaders
python recap.py --with-leaders

"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from src.config import config
from src.formatters import SlackMessageBuilder
from src.models import PlayerDailyLeader, TeamDailyLeader
from src.nba_api import NBAApiClient
from src.slack_client import SlackClient

logger = logging.getLogger(__name__)


class DailyRecapService:
    """Service for posting daily game recaps to Slack"""

    def __init__(self, dry_run: bool = False, include_leaders: bool = True):
        self.api = NBAApiClient()
        self.formatter = SlackMessageBuilder()
        self.slack = SlackClient(dry_run=dry_run)
        self.include_leaders = include_leaders

    def post_recap(self) -> None:
        """Fetch yesterday's completed games and post recap to Slack"""
        games = self.api.get_yesterdays_games()

        if not games:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
            logger.info(f"No completed games found for {yesterday}")
            return

        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
        logger.info(f"Found {len(games)} completed game(s) from {yesterday_str}")

        # Enrich all games with boxscore data in parallel
        with ThreadPoolExecutor(max_workers=min(len(games), 10)) as executor:
            futures = {
                executor.submit(self.api.enrich_game_with_boxscore, game): game
                for game in games
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    game = futures[future]
                    logger.warning(f"Failed to enrich game {game.game_id}: {e}")

        # Fetch daily leaders if requested
        player_leaders = {}
        team_leaders = {}
        if self.include_leaders:
            player_leaders = self._fetch_player_leaders()
            team_leaders = self._fetch_team_leaders()

        # Build and post the recap message
        message = self._build_recap_message(games, player_leaders, team_leaders)
        self.slack.post_message(message)

    def _fetch_player_leaders(self) -> dict[str, list[PlayerDailyLeader]]:
        """Fetch yesterday's player leaders concurrently"""
        stats = ["pts", "reb", "ast", "fg3m", "fgpct"]
        leaders = {}

        with ThreadPoolExecutor(max_workers=len(stats)) as executor:
            futures = {
                executor.submit(self.api.get_player_daily_leaders, stat): stat
                for stat in stats
            }
            for future in as_completed(futures):
                stat = futures[future]
                try:
                    data = future.result()
                    if data and "playerstats" in data:
                        leaders[stat] = [
                            PlayerDailyLeader.from_api(p, stat)
                            for p in data["playerstats"][:3]
                        ]
                    else:
                        leaders[stat] = []
                except Exception as e:
                    logger.warning(f"Failed to fetch {stat} leaders: {e}")
                    leaders[stat] = []

        return leaders

    def _fetch_team_leaders(self) -> dict[str, list[TeamDailyLeader]]:
        """Fetch yesterday's team leaders concurrently"""
        stats = ["pts", "ast", "fgpct", "fg3pct"]
        leaders = {}

        with ThreadPoolExecutor(max_workers=len(stats)) as executor:
            futures = {
                executor.submit(self.api.get_team_daily_leaders, stat): stat
                for stat in stats
            }
            for future in as_completed(futures):
                stat = futures[future]
                try:
                    data = future.result()
                    if data and "teamstats" in data:
                        leaders[stat] = [
                            TeamDailyLeader.from_api(t, stat)
                            for t in data["teamstats"][:3]
                        ]
                    else:
                        leaders[stat] = []
                except Exception as e:
                    logger.warning(f"Failed to fetch {stat} team leaders: {e}")
                    leaders[stat] = []

        return leaders

    def _build_recap_message(
        self,
        games: list,
        player_leaders: dict[str, list[PlayerDailyLeader]],
        team_leaders: dict[str, list[TeamDailyLeader]],
    ) -> dict:
        """Build Block Kit message with yesterday's game recaps"""
        blocks = []

        # Header with date
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"NBA Recap - {yesterday}",
                "emoji": True,
            },
        })

        # Summary stats context
        total_points = sum(g.home_team.score + g.away_team.score for g in games)
        avg_points = total_points / len(games) if games else 0
        ot_games = sum(1 for g in games if g.period > 4)

        summary_parts = [f"{len(games)} Games"]
        if ot_games > 0:
            summary_parts.append(f"{ot_games} OT")
        summary_parts.append(f"Avg Score: {avg_points:.1f}")

        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": " | ".join(summary_parts),
            }],
        })

        # Sort games by total score (most exciting first)
        games_sorted = sorted(
            games,
            key=lambda g: (
                g.period > 4,  # OT games first
                g.home_team.score + g.away_team.score  # Then by total points
            ),
            reverse=True
        )

        # Game recaps
        for game in games_sorted:
            blocks.append({"type": "divider"})
            blocks.append(self._build_game_recap_block(game))

        # Daily leaders section (if included)
        if self.include_leaders and (player_leaders or team_leaders):
            blocks.append({"type": "divider"})
            blocks.append(self._build_leaders_block(player_leaders, team_leaders))

        return {"blocks": blocks}

    def _build_game_recap_block(self, game) -> dict:
        """Build a detailed recap block for a single game"""
        away = game.away_team
        home = game.home_team

        # Determine winner and format score line
        if game.is_tied:
            # This shouldn't happen for finished games, but handle it
            score_line = f":_{away.tricode}: {away.name} {away.score}, :_{home.tricode}: {home.name} {home.score} - TIED"
            result_emoji = ""
        else:
            winner, loser = game.get_leader_and_trailer()
            is_away_winner = winner == away

            # Add OT indicator
            if game.period > 4:
                ot_num = game.period - 4
                ot_label = f"{ot_num}OT" if ot_num > 1 else "OT"
                result_emoji = f" ({ot_label})"
            else:
                result_emoji = ""

            # Format: Winner tricode WINS score-score (OT if applicable)
            score_line = f":_{winner.tricode}: *{winner.name}* defeats :_{loser.tricode}: {loser.name}, *{winner.score}-{loser.score}*{result_emoji}"

        lines = [score_line]

        # Add game highlights if available
        if away.stats and home.stats:
            highlights = []

            # Close game indicator
            point_diff = abs(home.score - away.score)
            if point_diff <= 5:
                highlights.append(f"Close game ({point_diff} pt margin)")

            # High scoring game
            total_score = home.score + away.score
            if total_score >= 250:
                highlights.append(f"High scoring ({total_score} total pts)")

            # Lead changes
            if away.stats.lead_changes >= 15:
                highlights.append(f"{away.stats.lead_changes} lead changes")

            if highlights:
                lines.append("_" + " • ".join(highlights) + "_")

        lines.append("")  # Blank line

        # Away team top performers
        lines.append(f"*:_{away.tricode}: {away.name}*")
        top_away = away.get_top_performers(2)
        if top_away:
            for player in top_away:
                lines.append(self._format_player_recap_line(player))
        else:
            lines.append("_No player stats available_")

        lines.append("")  # Blank line

        # Home team top performers
        lines.append(f"*:_{home.tricode}: {home.name}*")
        top_home = home.get_top_performers(2)
        if top_home:
            for player in top_home:
                lines.append(self._format_player_recap_line(player))
        else:
            lines.append("_No player stats available_")

        # Team stats comparison (condensed for recap)
        if away.stats and home.stats:
            lines.append("")
            lines.append(self._format_team_comparison(away, home))

        # Box score link
        lines.append("")
        lines.append(f"<https://www.nba.com/game/{game.game_id}/box-score|Full Box Score>")

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    def _format_player_recap_line(self, player) -> str:
        """Format a player stat line for recap (slightly more condensed)"""
        stats = player.stats
        parts = []

        # Always show PTS/REB/AST for recap
        parts.append(f"{stats.points} PTS")
        if stats.rebounds > 0:
            parts.append(f"{stats.rebounds} REB")
        if stats.assists > 0:
            parts.append(f"{stats.assists} AST")

        # Show shooting splits
        fg_pct = (stats.field_goals_made / stats.field_goals_attempted * 100) if stats.field_goals_attempted > 0 else 0
        parts.append(f"{stats.field_goals_made}-{stats.field_goals_attempted} FG ({fg_pct:.0f}%)")

        # Show 3PT if made any
        if stats.three_pointers_made > 0:
            parts.append(f"{stats.three_pointers_made}-{stats.three_pointers_attempted} 3P")

        return f"  • {player.name}: {' | '.join(parts)}"

    def _format_team_comparison(self, away, home) -> str:
        """Format a condensed team stats comparison"""
        away_fg_pct = int(away.stats.field_goal_pct * 100)
        home_fg_pct = int(home.stats.field_goal_pct * 100)

        away_3p_pct = int(away.stats.three_point_pct * 100)
        home_3p_pct = int(home.stats.three_point_pct * 100)

        lines = []
        lines.append(f"*Team Stats:* {away.tricode} vs {home.tricode}")
        lines.append(f"  FG%: {away_fg_pct}% vs {home_fg_pct}%  •  3P%: {away_3p_pct}% vs {home_3p_pct}%")
        lines.append(f"  REB: {away.stats.rebounds} vs {home.stats.rebounds}  •  AST: {away.stats.assists} vs {home.stats.assists}")
        lines.append(f"  TO: {away.stats.turnovers} vs {home.stats.turnovers}  •  Bench: {away.stats.bench_points} vs {home.stats.bench_points}")

        return "\n".join(lines)

    def _build_leaders_block(
        self,
        player_leaders: dict[str, list[PlayerDailyLeader]],
        team_leaders: dict[str, list[TeamDailyLeader]],
    ) -> dict:
        """Build the daily leaders section"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d")
        lines = [f"*{yesterday} League Leaders*", ""]

        # Player leaders
        if player_leaders:
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
        if team_leaders:
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


def main():
    parser = argparse.ArgumentParser(
        description="NBA Daily Recap - Post yesterday's completed games to Slack"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages instead of posting to Slack",
    )
    parser.add_argument(
        "--with-leaders",
        action="store_true",
        default=True,
        help="Include daily statistical leaders (default: True)",
    )
    parser.add_argument(
        "--no-leaders",
        action="store_true",
        help="Exclude daily statistical leaders",
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

    # Handle --no-leaders flag
    include_leaders = args.with_leaders and not args.no_leaders

    service = DailyRecapService(dry_run=args.dry_run, include_leaders=include_leaders)
    service.post_recap()


if __name__ == "__main__":
    main()
