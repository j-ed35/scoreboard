"""Data models for NBA game tracking"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlayerStats:
    """Player statistics for a game"""

    points: int = 0
    rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    three_pointers_made: int = 0
    three_pointers_attempted: int = 0
    field_goals_made: int = 0
    field_goals_attempted: int = 0

    @property
    def is_perfect_shooting(self) -> bool:
        """Check if player is shooting 100% from the field"""
        return (
            self.field_goals_made > 0
            and self.field_goals_made == self.field_goals_attempted
        )


@dataclass
class Player:
    """NBA player with game statistics"""

    name: str
    stats: PlayerStats
    played: bool = False

    @classmethod
    def from_api(cls, data: dict) -> "Player":
        """Create Player from NBA API response"""
        stats_data = data.get("statistics", {})
        return cls(
            name=data.get("name", "Unknown"),
            played=data.get("played") == "1",
            stats=PlayerStats(
                points=stats_data.get("points", 0),
                rebounds=stats_data.get("reboundsTotal", 0),
                assists=stats_data.get("assists", 0),
                steals=stats_data.get("steals", 0),
                blocks=stats_data.get("blocks", 0),
                three_pointers_made=stats_data.get("threePointersMade", 0),
                three_pointers_attempted=stats_data.get("threePointersAttempted", 0),
                field_goals_made=stats_data.get("fieldGoalsMade", 0),
                field_goals_attempted=stats_data.get("fieldGoalsAttempted", 0),
            ),
        )


@dataclass
class TeamStats:
    """Team statistics for a game"""

    field_goals_made: int = 0
    field_goals_attempted: int = 0
    field_goal_pct: float = 0.0
    three_pointers_made: int = 0
    three_pointers_attempted: int = 0
    three_point_pct: float = 0.0
    rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    bench_points: int = 0
    biggest_lead: int = 0
    biggest_run: int = 0
    points_in_paint: int = 0
    fast_break_points: int = 0
    points_second_chance: int = 0
    points_from_turnovers: int = 0
    lead_changes: int = 0
    times_tied: int = 0

    @classmethod
    def from_api(cls, data: dict) -> "TeamStats":
        """Create TeamStats from boxscore API response"""
        return cls(
            field_goals_made=data.get("fieldGoalsMade", 0),
            field_goals_attempted=data.get("fieldGoalsAttempted", 0),
            field_goal_pct=data.get("fieldGoalsPercentage", 0.0),
            three_pointers_made=data.get("threePointersMade", 0),
            three_pointers_attempted=data.get("threePointersAttempted", 0),
            three_point_pct=data.get("threePointersPercentage", 0.0),
            rebounds=data.get("reboundsPersonal", 0),
            assists=data.get("assists", 0),
            steals=data.get("steals", 0),
            blocks=data.get("blocks", 0),
            turnovers=data.get("turnoversTotal", 0),
            bench_points=data.get("benchPoints", 0),
            biggest_lead=data.get("biggestLead", 0),
            biggest_run=data.get("biggestScoringRun", 0),
            points_in_paint=data.get("pointsInThePaint", 0),
            fast_break_points=data.get("pointsFastBreak", 0),
            points_second_chance=data.get("pointsSecondChance", 0),
            points_from_turnovers=data.get("pointsFromTurnovers", 0),
            lead_changes=data.get("leadChanges", 0),
            times_tied=data.get("timesTied", 0),
        )


@dataclass
class Team:
    """NBA team with game data"""

    name: str
    tricode: str
    score: int = 0
    players: list[Player] = field(default_factory=list)
    quarter_scores: list[int] = field(default_factory=list)
    stats: Optional[TeamStats] = None

    @classmethod
    def from_schedule_api(cls, data: dict) -> "Team":
        """Create Team from schedule API response"""
        return cls(
            name=data.get("teamName", "Unknown"),
            tricode=data.get("teamTricode", "???"),
            score=data.get("score", 0),
        )

    def get_top_performers(self, count: int = 2) -> list[Player]:
        """Get top performers by points, with PTS+REB+AST as tiebreaker"""
        active = [p for p in self.players if p.played]
        return sorted(
            active,
            key=lambda p: (
                p.stats.points,
                p.stats.points + p.stats.rebounds + p.stats.assists,
            ),
            reverse=True,
        )[:count]


@dataclass
class Game:
    """NBA game with current state"""

    game_id: str
    home_team: Team
    away_team: Team
    status: int  # 1=not started, 2=in progress, 3=finished
    status_text: str
    period: int = 0
    clock: str = ""

    @classmethod
    def from_schedule_api(cls, data: dict) -> "Game":
        """Create Game from schedule API response"""
        return cls(
            game_id=data.get("gameId", ""),
            home_team=Team.from_schedule_api(data.get("homeTeam", {})),
            away_team=Team.from_schedule_api(data.get("visitorTeam", {})),
            status=data.get("gameStatus", 1),
            status_text=data.get("gameStatusText", "").strip(),
            period=data.get("period", 0),
            clock=data.get("clock", "").strip(),
        )

    @property
    def is_active(self) -> bool:
        """Check if game is in progress or recently finished"""
        return self.status in [2, 3]

    @property
    def is_tied(self) -> bool:
        """Check if game is currently tied"""
        return self.home_team.score == self.away_team.score

    def get_leader_and_trailer(self) -> tuple[Team, Team]:
        """Return (leading_team, trailing_team), away team first if tied"""
        if self.away_team.score > self.home_team.score:
            return self.away_team, self.home_team
        elif self.home_team.score > self.away_team.score:
            return self.home_team, self.away_team
        else:
            return self.away_team, self.home_team

    @property
    def game_time_display(self) -> str:
        """Get formatted game time display (e.g., 'Q2 5:32' or 'Halftime')"""
        if self.status == 1:
            return "Not Started"
        if self.status == 3:
            return "Final"
        if self.status_text:
            if "Half" in self.status_text:
                return "Halftime"
            if "End" in self.status_text:
                return self.status_text
        if self.clock:
            return f"Q{self.period} {self.clock}"
        return f"Q{self.period}"


QUARTER_LABELS = {1: "End of Q1", 2: "Halftime", 3: "End of Q3", 4: "Final"}


def get_quarter_label(quarter: int) -> str:
    """Get human-readable quarter label"""
    return QUARTER_LABELS.get(quarter, f"Q{quarter}")


@dataclass
class QuarterUpdate:
    """Represents a quarter-end update to be posted"""

    game: Game
    quarter: int
    quarter_scores: list[tuple[int, int]] = field(default_factory=list)

    @property
    def quarter_label(self) -> str:
        """Get human-readable quarter label"""
        return get_quarter_label(self.quarter)


@dataclass
class PlayerDailyLeader:
    """A player's daily leader entry"""

    name: str
    team_tricode: str
    value: float
    stat_type: str

    @classmethod
    def from_api(cls, data: dict, stat_type: str) -> "PlayerDailyLeader":
        """Create PlayerDailyLeader from API response"""
        # API uses UPPERCASE field names
        name = data.get("PLAYER_NAME", "Unknown")
        tricode = data.get("TEAM_ABBREVIATION", "???")

        # Get the stat value - API uses UPPERCASE field names
        stat_key = stat_type.upper()
        if stat_type == "fgpct":
            stat_key = "FG_PCT"
        elif stat_type == "fg3m":
            stat_key = "FG3M"
        value = data.get(stat_key, 0) or 0

        return cls(name=name, team_tricode=tricode, value=value, stat_type=stat_type)

    def format_value(self) -> str:
        """Format the stat value for display"""
        if self.stat_type == "fgpct":
            return f"{self.value * 100:.1f}%"
        elif isinstance(self.value, float) and self.value != int(self.value):
            return f"{self.value:.1f}"
        return str(int(self.value))


@dataclass
class TeamDailyLeader:
    """A team's daily leader entry"""

    name: str
    tricode: str
    value: float
    stat_type: str

    @classmethod
    def from_api(cls, data: dict, stat_type: str) -> "TeamDailyLeader":
        """Create TeamDailyLeader from API response"""
        # API uses UPPERCASE field names
        name = data.get("TEAM_NAME", "Unknown")
        tricode = data.get("TEAM_ABBREVIATION", "???")

        # Get the stat value - API uses UPPERCASE field names
        stat_key = stat_type.upper()
        if stat_type == "fgpct":
            stat_key = "FG_PCT"
        elif stat_type == "fg3pct":
            stat_key = "FG3_PCT"
        value = data.get(stat_key, 0) or 0

        return cls(name=name, tricode=tricode, value=value, stat_type=stat_type)

    def format_value(self) -> str:
        """Format the stat value for display"""
        if self.stat_type in ("fgpct", "fg3pct"):
            return f"{self.value * 100:.1f}%"
        elif isinstance(self.value, float) and self.value != int(self.value):
            return f"{self.value:.1f}"
        return str(int(self.value))
