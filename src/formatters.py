"""Slack message formatting using Block Kit"""

from typing import TYPE_CHECKING

from .models import Game, Player, Team, TeamStats, get_quarter_label

if TYPE_CHECKING:
    from .game_monitor import CloseGameAlert, PerformanceAlert

# Triple-double threshold
TRIPLE_DOUBLE_THRESHOLD = 10


def has_triple_double(player: Player) -> bool:
    """Check if player has a triple-double"""
    stats = player.stats
    categories = [
        stats.points >= TRIPLE_DOUBLE_THRESHOLD,
        stats.rebounds >= TRIPLE_DOUBLE_THRESHOLD,
        stats.assists >= TRIPLE_DOUBLE_THRESHOLD,
        stats.steals >= TRIPLE_DOUBLE_THRESHOLD,
        stats.blocks >= TRIPLE_DOUBLE_THRESHOLD,
    ]
    return sum(categories) >= 3


class SlackMessageBuilder:
    """Builds Slack Block Kit messages for game updates"""

    # -------------------------------------------------------------------------
    # Game Start Message (Parent Thread)
    # -------------------------------------------------------------------------

    def build_game_start(self, game: Game) -> dict:
        """Build game start notification (serves as parent thread message)"""
        away = game.away_team
        home = game.home_team

        header_text = f":_{away.tricode}: {away.name} @ {home.name} :_{home.tricode}:"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_text,
                    "emoji": True,
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Box Score",
                            "emoji": False,
                        },
                        "url": f"https://www.nba.com/game/{game.game_id}/box-score",
                        "action_id": f"box_score_{game.game_id}",
                    }
                ],
            },
        ]

        return {"blocks": blocks}

    # -------------------------------------------------------------------------
    # Quarter Updates (Halftime / Final - broadcast to channel)
    # -------------------------------------------------------------------------

    def build_quarter_update(self, game: Game, quarter: int) -> dict:
        """Build a complete Block Kit message for a quarter update"""
        blocks = []

        blocks.append(self._build_header(game, quarter))
        blocks.append(self._build_quarter_scores(game, quarter))

        # Add lead changes and times tied
        away = game.away_team
        if away.stats:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"{away.stats.lead_changes} Lead Changes | Tied {away.stats.times_tied}x",
                    }
                ],
            })

        blocks.append({"type": "divider"})

        leader, trailer = game.get_leader_and_trailer()

        blocks.append(self._build_team_section(leader))
        blocks.append(self._build_team_section(trailer))

        return {"blocks": blocks}

    def build_halftime_update(self, game: Game) -> dict:
        """Build halftime update message"""
        return self.build_quarter_update(game, quarter=2)

    def build_final_update(self, game: Game) -> dict:
        """Build final score message"""
        return self.build_quarter_update(game, quarter=game.period)

    # -------------------------------------------------------------------------
    # Close Game Alert (threaded)
    # -------------------------------------------------------------------------

    def build_close_game_alert(self, alert: "CloseGameAlert") -> dict:
        """Build close game alert message"""
        game = alert.game
        away = game.away_team
        home = game.home_team

        # Determine period label
        if alert.period > 4:
            ot_num = alert.period - 4
            period_label = f"OT{ot_num}" if ot_num > 1 else "OT"
        else:
            period_label = f"Q{alert.period}"

        if alert.point_diff == 0:
            score_text = f"TIED {away.score}-{home.score}"
        else:
            leader, trailer = game.get_leader_and_trailer()
            score_text = f"{leader.tricode} leads {leader.score}-{trailer.score}"

        clock_text = f"{period_label} {alert.clock}" if alert.clock else period_label

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Close Game Alert*\n{score_text} | {clock_text}",
                },
            },
        ]

        return {"blocks": blocks}

    # -------------------------------------------------------------------------
    # Performance Alerts (threaded)
    # -------------------------------------------------------------------------

    def build_performance_alert(self, alert: "PerformanceAlert") -> dict:
        """Build notable performance alert message"""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*:_{alert.team_tricode}:* {alert.description}",
                },
            },
        ]

        return {"blocks": blocks}

    # -------------------------------------------------------------------------
    # End of Night Summary
    # -------------------------------------------------------------------------

    def build_end_of_night_summary(
        self,
        games: list[Game],
        player_leaders: dict,
        team_leaders: dict,
    ) -> dict:
        """Build end of night summary with all final scores and leaders"""
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "End of Night Summary",
                "emoji": True,
            },
        })

        # All final scores
        for game in games:
            blocks.append({"type": "divider"})
            blocks.append(self._build_summary_game_block(game))

        # Daily leaders
        blocks.append({"type": "divider"})
        blocks.append(self._build_leaders_block(player_leaders, team_leaders))

        return {"blocks": blocks}

    def _build_summary_game_block(self, game: Game) -> dict:
        """Build a condensed game block for end of night summary"""
        away = game.away_team
        home = game.home_team

        # Determine game result
        if game.is_tied:
            score_line = f":_{away.tricode}: Tied {away.score} :_{home.tricode}:"
        else:
            leader, trailer = game.get_leader_and_trailer()
            if leader == away:
                score_line = f":_{away.tricode}: *{away.score}* @ {home.score} :_{home.tricode}:"
            else:
                score_line = f":_{away.tricode}: {away.score} @ *{home.score}* :_{home.tricode}:"

        # Add OT indicator if applicable
        status = "Final"
        if game.period > 4:
            ot_num = game.period - 4
            ot_label = f"OT{ot_num}" if ot_num > 1 else "OT"
            status = f"Final ({ot_label})"

        lines = [f"{score_line}  |  {status}"]

        # Top performers (1 per team for summary)
        for team in [away, home]:
            top = team.get_top_performers(1)
            if top:
                player = top[0]
                stats = player.stats
                lines.append(
                    f"  :_{team.tricode}: {player.name} - {stats.points} PTS / {stats.rebounds} REB / {stats.assists} AST"
                )

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    def _build_leaders_block(self, player_leaders: dict, team_leaders: dict) -> dict:
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
                leader_strs = [f"{t.tricode} {t.format_value()}" for t in leaders[:3]]
                lines.append(f"  {label}: {' | '.join(leader_strs)}")

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _build_header(self, game: Game, quarter: int) -> dict:
        """Build the header block with score and quarter"""
        quarter_label = get_quarter_label(quarter)
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
        """Build context block with quarter-by-quarter scores (no box score link)"""
        home = game.home_team
        away = game.away_team

        quarters_played = min(
            quarter, len(home.quarter_scores), len(away.quarter_scores)
        )

        if quarters_played == 0:
            # No quarter data yet
            return {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "Game in progress"}],
            }

        quarter_parts = []
        for q in range(quarters_played):
            away_pts = away.quarter_scores[q] if q < len(away.quarter_scores) else 0
            home_pts = home.quarter_scores[q] if q < len(home.quarter_scores) else 0
            # Label: Q1, H (halftime), Q3, Q4, OT, 2OT, etc.
            if q == 1:
                label = "H"
            elif q >= 4:
                ot_num = q - 3
                label = f"OT{ot_num}" if ot_num > 1 else "OT"
            else:
                label = f"Q{q + 1}"
            quarter_parts.append(f"{label}: {away_pts}-{home_pts}")

        return {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "  ".join(quarter_parts)}],
        }

    def _build_team_section(self, team: Team) -> dict:
        """Build a section block for a team's top performers and stats"""
        # Get top 2 performers by points
        top_scorers = team.get_top_performers(2)

        # Find any triple-double players not in top scorers
        triple_double_players = []
        for player in team.players:
            if player.played and has_triple_double(player):
                if player not in top_scorers:
                    triple_double_players.append(player)

        lines = [f"*:_{team.tricode}: {team.name}*"]

        # Add top scorers first
        for player in top_scorers:
            td_marker = " (TD)" if has_triple_double(player) else ""
            lines.append(self._format_player_line(player) + td_marker)

        # Add any additional triple-double players
        for player in triple_double_players:
            lines.append(self._format_player_line(player) + " (TD)")

        if team.stats:
            lines.append(self._format_team_stats(team.stats))

        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }

    @staticmethod
    def _format_player_line(player: Player) -> str:
        """Format a single player's stat line

        Example: Keyonte George - 15 PTS (6-11 FG) | 2 3PM (2-5 3P) | 3 REB | 3 STL | 2 BLK
        """
        stats = player.stats
        parts = []

        # Points with FG splits
        pts_str = f"{stats.points} PTS ({stats.field_goals_made}-{stats.field_goals_attempted} FG)"
        parts.append(pts_str)

        # 3-pointers with splits (only if made any)
        if stats.three_pointers_made > 0:
            parts.append(
                f"{stats.three_pointers_made} 3PM ({stats.three_pointers_made}-{stats.three_pointers_attempted} 3P)"
            )

        # Assists (if > 2)
        if stats.assists > 2:
            parts.append(f"{stats.assists} AST")

        # Rebounds (if > 1)
        if stats.rebounds > 1:
            parts.append(f"{stats.rebounds} REB")

        # Steals (if > 2)
        if stats.steals > 2:
            parts.append(f"{stats.steals} STL")

        # Blocks (if > 2)
        if stats.blocks > 2:
            parts.append(f"{stats.blocks} BLK")

        return f"{player.name} - {' | '.join(parts)}"

    @staticmethod
    def _format_team_stats(stats: TeamStats) -> str:
        """Format team statistics block"""
        fg_pct = int(stats.field_goal_pct * 100)
        three_pct = int(stats.three_point_pct * 100)

        line1 = f"{stats.field_goals_made}/{stats.field_goals_attempted} {fg_pct}% FG | {stats.three_pointers_made}/{stats.three_pointers_attempted} {three_pct}% 3P"
        line2 = f"{stats.rebounds} REB | {stats.assists} AST | {stats.steals} STL | {stats.blocks} BLK"
        line3 = f"Bench: {stats.bench_points} | Paint: {stats.points_in_paint} | 2ndPTS: {stats.points_second_chance} | PTSTO: {stats.points_from_turnovers}"

        return f"{line1}\n{line2}\n{line3}"


def format_player_stat_line(player: Player) -> str:
    """Standalone function for formatting player stats (for testing/compatibility)"""
    return SlackMessageBuilder._format_player_line(player)
