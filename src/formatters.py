"""Slack message formatting using Block Kit"""

from .models import Game, Player, Team, TeamStats


class SlackMessageBuilder:
    """Builds Slack Block Kit messages for quarter updates"""

    def build_quarter_update(self, game: Game, quarter: int) -> dict:
        """Build a complete Block Kit message for a quarter update"""
        blocks = []

        blocks.append(self._build_header(game, quarter))
        blocks.append(self._build_quarter_scores(game, quarter))
        blocks.append({"type": "divider"})

        leader, trailer = game.get_leader_and_trailer()

        blocks.append(self._build_team_section(leader))
        blocks.append(self._build_team_section(trailer))

        return {"blocks": blocks}

    def _build_header(self, game: Game, quarter: int) -> dict:
        """Build the header block with score and quarter"""
        quarter_label = self._get_quarter_label(quarter)
        home = game.home_team
        away = game.away_team

        if game.is_tied:
            score_text = f":_{away.tricode}: Tied at {away.score} :_{home.tricode}:"
        else:
            leader, trailer = game.get_leader_and_trailer()
            score_text = f":_{leader.tricode}: {leader.score}-{trailer.score} :_{trailer.tricode}:"

        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{score_text}  {quarter_label}",
                "emoji": True,
            },
        }

    def _build_quarter_scores(self, game: Game, quarter: int) -> dict:
        """Build context block with quarter-by-quarter scores"""
        home = game.home_team
        away = game.away_team

        quarters_played = min(quarter, len(home.quarter_scores), len(away.quarter_scores))

        elements = []

        if quarters_played == 0:
            elements.append(
                {
                    "type": "mrkdwn",
                    "text": f"<https://www.nba.com/game/{game.game_id}/box-score|Box Score>",
                }
            )
        else:
            quarter_parts = []
            for q in range(quarters_played):
                away_pts = away.quarter_scores[q] if q < len(away.quarter_scores) else 0
                home_pts = home.quarter_scores[q] if q < len(home.quarter_scores) else 0
                label = "H" if q == 1 else f"Q{q + 1}"
                quarter_parts.append(f"{label}: {away_pts}-{home_pts}")

            elements.append(
                {"type": "mrkdwn", "text": "  ".join(quarter_parts)}
            )
            elements.append(
                {
                    "type": "mrkdwn",
                    "text": f"<https://www.nba.com/game/{game.game_id}/box-score|Box Score>",
                }
            )

        return {"type": "context", "elements": elements}

    def _build_team_section(self, team: Team) -> dict:
        """Build a section block for a team's top performers and stats"""
        performers = team.get_top_performers(2)

        lines = [f"*:_{team.tricode}: {team.name}*"]
        for player in performers:
            lines.append(self._format_player_line(player))

        if team.stats:
            lines.append(self._format_team_stats(team.stats))

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    def _format_team_stats(self, stats: TeamStats) -> str:
        """Format team statistics block"""
        fg_pct = int(stats.field_goal_pct * 100)
        three_pct = int(stats.three_point_pct * 100)

        line1 = f"  _{stats.field_goals_made}/{stats.field_goals_attempted} {fg_pct}% FG | {stats.three_pointers_made}/{stats.three_pointers_attempted} {three_pct}% 3P | {stats.bench_points} Bench PTS_"
        line2 = f"  _{stats.rebounds} REB | {stats.assists} AST | {stats.steals} STL | {stats.blocks} BLK_"
        line3 = f"  _Lead {stats.biggest_lead} | Run {stats.biggest_run} | Paint {stats.points_in_paint}_"

        return f"{line1}\n{line2}\n{line3}"

    def _format_player_line(self, player: Player) -> str:
        """Format a single player's stat line"""
        stats = player.stats
        parts = [f"{stats.points} PTS"]

        if stats.three_pointers_made > 0:
            parts.append(f"{stats.three_pointers_made} 3PM")

        if stats.is_perfect_shooting:
            parts.append(f"{stats.field_goals_made}-{stats.field_goals_attempted} FG")

        if stats.assists > 2:
            parts.append(f"{stats.assists} AST")

        if stats.rebounds > 1:
            parts.append(f"{stats.rebounds} REB")

        return f"  {player.name} - {' | '.join(parts)}"

    def _get_quarter_label(self, quarter: int) -> str:
        """Get display label for quarter number"""
        labels = {1: "End of Q1", 2: "Halftime", 3: "End of Q3", 4: "Final"}
        return labels.get(quarter, f"Q{quarter}")


def format_player_stat_line(player: Player) -> str:
    """Standalone function for formatting player stats (for testing/compatibility)"""
    builder = SlackMessageBuilder()
    return builder._format_player_line(player)
