"""Game monitoring and alert detection logic"""

import logging
from dataclasses import dataclass
from typing import Optional

from .models import Game, Player

logger = logging.getLogger(__name__)

# Alert thresholds
CLOSE_GAME_THRESHOLD = 5  # Point differential for close game
CLOSE_GAME_QUARTER = 4  # Only alert in Q4 or OT
HIGH_SCORE_THRESHOLD = 40  # Points for high scorer alert
TRIPLE_DOUBLE_THRESHOLD = 10  # Minimum for each category


@dataclass(slots=True)
class PerformanceAlert:
    """Notable player performance alert"""

    player: Player
    team_tricode: str
    alert_type: (
        str  # "triple_double_watch", "triple_double", "high_scorer", "near_record"
    )
    description: str


@dataclass(slots=True)
class CloseGameAlert:
    """Close game alert"""

    game: Game
    point_diff: int
    period: int
    clock: str


class GameMonitor:
    """Monitors games for notable events and alerts"""

    def detect_quarter_end(self, game: Game) -> Optional[int]:
        """
        Detect if a quarter/period just ended based on gameStatusText.
        Returns period number if ended, None otherwise.
        Supports overtime (period > 4).
        """
        status_text = game.status_text

        # Check for halftime
        if "Halftime" in status_text or "Half" in status_text:
            return 2

        # Check for quarter ends
        if "End of Q1" in status_text:
            return 1
        if "End of Q3" in status_text:
            return 3

        # Check for overtime ends
        if "End of OT" in status_text:
            # Could be "End of OT", "End of OT1", "End of 2OT", etc.
            return game.period  # Use the actual period from game data

        # Check for final (regular or overtime)
        if game.status == 3:
            return game.period if game.period >= 4 else 4

        return None

    def is_halftime(self, game: Game) -> bool:
        """Check if game is at halftime.

        Uses multiple detection methods for reliability:
        1. Period-based: Q2 finished (period=2, no clock or 0:00)
        2. Status text: Contains "Halftime" or "Half"

        The schedule API's gameStatusText can lag behind actual game state,
        so period-based detection from boxscore data is more reliable.
        """
        # Primary: Period-based detection (more reliable from boxscore data)
        # Period 2 with no clock or 0:00 means Q2 just ended
        if game.period == 2:
            clock = game.clock.strip() if game.clock else ""
            if clock in ("", "0:00", "0:0"):
                logger.debug(
                    f"Halftime detected via period/clock: period={game.period}, "
                    f"clock='{game.clock}', status_text='{game.status_text}'"
                )
                return True

        # Fallback: Check status_text from schedule API
        status_text = game.status_text
        if "Halftime" in status_text or "Half" in status_text:
            logger.debug(
                f"Halftime detected via status_text: period={game.period}, "
                f"clock='{game.clock}', status_text='{game.status_text}'"
            )
            return True

        return False

    def is_final(self, game: Game) -> bool:
        """Check if game is final (not heading to overtime)

        Handles edge cases:
        - status == 3 is the primary indicator
        - "End of Q4" with tied score means overtime (NOT final)
        - "Final" in status text confirms it's truly over
        """
        # Primary check: status == 3 means game is over
        if game.status == 3:
            return True

        # Fallback for games that show "End of Q4" or similar
        status_text = game.status_text

        # Explicitly final status text
        if "Final" in status_text:
            return True

        # "End of Q4" requires additional checks
        if "End of Q4" in status_text:
            # If game is tied, it's going to overtime (not final)
            if game.is_tied:
                return False
            # If not tied, Q4 ended means it's final
            return True

        return False

    def is_overtime(self, game: Game) -> bool:
        """Check if game is in overtime"""
        return game.period > 4

    def detect_close_game(self, game: Game) -> Optional[CloseGameAlert]:
        """
        Detect if a game is close in the 4th quarter or overtime.
        Returns CloseGameAlert if conditions met, None otherwise.
        """
        # Only check active games in Q4 or OT
        if game.status != 2:  # Not in progress
            return None

        if game.period < CLOSE_GAME_QUARTER:
            return None

        # Calculate point differential
        point_diff = abs(game.home_team.score - game.away_team.score)

        if point_diff <= CLOSE_GAME_THRESHOLD:
            return CloseGameAlert(
                game=game,
                point_diff=point_diff,
                period=game.period,
                clock=game.clock,
            )

        return None

    def detect_performance_alerts(self, game: Game) -> list[PerformanceAlert]:
        """
        Detect notable individual performances.
        Returns list of PerformanceAlert objects.
        """
        alerts = []

        for team in [game.home_team, game.away_team]:
            for player in team.players:
                if not player.played:
                    continue

                stats = player.stats

                # Check for triple-double
                triple_double_cats = sum(
                    [
                        1 if stats.points >= TRIPLE_DOUBLE_THRESHOLD else 0,
                        1 if stats.rebounds >= TRIPLE_DOUBLE_THRESHOLD else 0,
                        1 if stats.assists >= TRIPLE_DOUBLE_THRESHOLD else 0,
                        1 if stats.steals >= TRIPLE_DOUBLE_THRESHOLD else 0,
                        1 if stats.blocks >= TRIPLE_DOUBLE_THRESHOLD else 0,
                    ]
                )

                if triple_double_cats >= 3:
                    # Full triple-double achieved
                    alerts.append(
                        PerformanceAlert(
                            player=player,
                            team_tricode=team.tricode,
                            alert_type="triple_double",
                            description=self._format_triple_double(
                                player, achieved=True
                            ),
                        )
                    )
                elif triple_double_cats == 2:
                    # Check if close to triple-double (2 categories at 10+, 1 at 7+)
                    close_cats = sum(
                        [
                            1 if 7 <= stats.points < TRIPLE_DOUBLE_THRESHOLD else 0,
                            1 if 7 <= stats.rebounds < TRIPLE_DOUBLE_THRESHOLD else 0,
                            1 if 7 <= stats.assists < TRIPLE_DOUBLE_THRESHOLD else 0,
                            1 if 7 <= stats.steals < TRIPLE_DOUBLE_THRESHOLD else 0,
                            1 if 7 <= stats.blocks < TRIPLE_DOUBLE_THRESHOLD else 0,
                        ]
                    )
                    if close_cats >= 1:
                        alerts.append(
                            PerformanceAlert(
                                player=player,
                                team_tricode=team.tricode,
                                alert_type="triple_double_watch",
                                description=self._format_triple_double(
                                    player, achieved=False
                                ),
                            )
                        )

                # Check for high scorer (40+ points)
                if stats.points >= HIGH_SCORE_THRESHOLD:
                    alerts.append(
                        PerformanceAlert(
                            player=player,
                            team_tricode=team.tricode,
                            alert_type="high_scorer",
                            description=f"{player.name} has {stats.points} points!",
                        )
                    )

        return alerts

    def _format_triple_double(self, player: Player, achieved: bool) -> str:
        """Format triple-double alert description"""
        stats = player.stats
        stat_parts = []

        if stats.points >= 7:
            stat_parts.append(f"{stats.points} PTS")
        if stats.rebounds >= 7:
            stat_parts.append(f"{stats.rebounds} REB")
        if stats.assists >= 7:
            stat_parts.append(f"{stats.assists} AST")
        if stats.steals >= 7:
            stat_parts.append(f"{stats.steals} STL")
        if stats.blocks >= 7:
            stat_parts.append(f"{stats.blocks} BLK")

        stat_line = " / ".join(stat_parts)

        if achieved:
            return f"TRIPLE-DOUBLE: {player.name} - {stat_line}"
        else:
            return f"Triple-Double Watch: {player.name} - {stat_line}"

    def get_period_label(self, period: int) -> str:
        """Get human-readable period label"""
        if period <= 4:
            return {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}.get(period, f"Q{period}")
        else:
            ot_num = period - 4
            return f"OT{ot_num}" if ot_num > 1 else "OT"

    def get_quarter_end_label(self, period: int) -> str:
        """Get human-readable quarter end label"""
        if period == 1:
            return "End of Q1"
        elif period == 2:
            return "Halftime"
        elif period == 3:
            return "End of Q3"
        elif period == 4:
            return "Final"
        else:
            ot_num = period - 4
            ot_label = f"OT{ot_num}" if ot_num > 1 else "OT"
            return f"Final ({ot_label})"
