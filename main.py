"""
NBA Quarter-End Updates to Slack
Main entry point for the application

# Run continuously (default)
python main.py

# Single check with dry run
python main.py --once --dry-run

# Continuous with dry run
python main.py --dry-run

"""

import argparse
import signal
import sys
import time
from datetime import datetime

from src.config import config
from src.formatters import SlackMessageBuilder
from src.game_monitor import GameMonitor
from src.nba_api import NBAApiClient
from src.slack_client import SlackClient


class QuarterUpdateService:
    """Main service that orchestrates quarter update monitoring"""

    def __init__(self, dry_run: bool = False):
        self.api = NBAApiClient()
        self.monitor = GameMonitor()
        self.formatter = SlackMessageBuilder()
        self.slack = SlackClient(dry_run=dry_run)
        self.running = True

    def check_games(self) -> None:
        """Check all active games for quarter endings"""
        print(f"\nChecking games at {datetime.now().strftime('%I:%M:%S %p')}")

        games = self.api.get_todays_games()
        active_games = [g for g in games if g.is_active]

        if not active_games:
            print("No active games")
            return

        print(f"Found {len(active_games)} active game(s)")

        for game in active_games:
            self._process_game(game)

    def _process_game(self, game) -> None:
        """Process a single game for quarter updates"""
        away = game.away_team
        home = game.home_team

        print(
            f"\n  :_{away.tricode}: {away.score} @ {home.score} :_{home.tricode}:  |  {game.game_time_display}"
        )

        quarter = self.monitor.detect_quarter_end(game)

        if quarter and self.monitor.should_post_update(game.game_id, quarter):
            print(f"    Quarter {quarter} ended!")

            if self.api.enrich_game_with_boxscore(game):
                message = self.formatter.build_quarter_update(game, quarter)

                if self.slack.post_message(message):
                    self.monitor.mark_quarter_posted(game.game_id, quarter)
                    print(f"    Posted Q{quarter} update")
            else:
                print(f"    Failed to fetch boxscore")
        elif quarter:
            print(f"    Q{quarter} already posted")
        else:
            print(f"    No quarter end detected")

    def run_once(self) -> None:
        """Run a single check cycle"""
        self.check_games()

    def run_continuous(self) -> None:
        """Run continuous monitoring until interrupted"""
        print("=" * 60)
        print("NBA Quarter-End Monitor Started")
        print(f"Polling interval: {config.poll_interval_seconds} seconds")
        print("Press CTRL+C to stop")
        print("=" * 60)

        def signal_handler(sig, frame):
            print("\n" + "=" * 60)
            print("Monitor stopped by user")
            print("=" * 60)
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            self.check_games()
            print(f"\nSleeping for {config.poll_interval_seconds} seconds...")

            for _ in range(config.poll_interval_seconds):
                if not self.running:
                    break
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="NBA Quarter-End Slack Updates")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages instead of posting to Slack",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit instead of continuous monitoring",
    )
    args = parser.parse_args()

    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    service = QuarterUpdateService(dry_run=args.dry_run)

    if args.once:
        service.run_once()
    else:
        service.run_continuous()


if __name__ == "__main__":
    main()
