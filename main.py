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
import logging
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.config import config
from src.formatters import SlackMessageBuilder
from src.game_monitor import GameMonitor
from src.models import PlayerDailyLeader, TeamDailyLeader
from src.nba_api import NBAApiClient
from src.slack_client import SlackClient
from src.state import StateManager

logger = logging.getLogger(__name__)

# Cooldown for close game alerts (don't spam every poll)
CLOSE_GAME_ALERT_COOLDOWN_POLLS = 4  # ~3 minutes with 45s polling


class QuarterUpdateService:
    """Main service that orchestrates quarter update monitoring"""

    def __init__(self, dry_run: bool = False):
        self.api = NBAApiClient()
        self.monitor = GameMonitor()
        self.formatter = SlackMessageBuilder()
        self.slack = SlackClient(dry_run=dry_run)
        self.state = StateManager()
        self.stop_event = threading.Event()
        self.close_game_cooldowns: dict[str, int] = {}  # game_id -> polls remaining

    def check_games(self) -> bool:
        """Check all games for updates and alerts.

        Returns:
            True if there are active (in-progress) games, False otherwise.
        """
        logger.info(f"Checking games at {datetime.now().strftime('%I:%M:%S %p')}")

        games = self.api.get_todays_games()

        if not games:
            logger.info("No games today")
            return False

        # Separate games by status with improved detection
        # Use GameMonitor.is_final() for robust status detection
        not_started = [g for g in games if g.status == 1]
        finished = [g for g in games if self.monitor.is_final(g)]
        # In-progress includes status==2 AND games that haven't reached final yet
        in_progress = [g for g in games if g.status == 2 or (g.status != 1 and not self.monitor.is_final(g))]

        logger.info(
            f"Games: {len(not_started)} not started, {len(in_progress)} in progress, {len(finished)} finished"
        )

        # Process games that just started (status changed from 1 to 2)
        for game in in_progress:
            self._handle_game_start(game)

        # Enrich active games with boxscore data (in parallel)
        # Skip finished games that already have final posted to save API calls
        games_to_enrich = in_progress + [
            g for g in finished if not self.state.get_game(g.game_id).final_posted
        ]
        if games_to_enrich:
            self._enrich_games_parallel(games_to_enrich)

        # Process in-progress games for alerts
        for game in in_progress:
            self._process_in_progress_game(game)

        # Process finished games
        for game in finished:
            self._process_finished_game(game)

        # Decrement close game cooldowns
        self._update_cooldowns()

        # Check for end of night summary
        self._check_end_of_night(games)

        # Return True if there are active games (for dynamic polling)
        return len(in_progress) > 0

    def _enrich_games_parallel(self, games: list) -> None:
        """Enrich multiple games with boxscore data in parallel"""
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

    def _handle_game_start(self, game) -> None:
        """Post game start message if not already posted"""
        game_state = self.state.get_game(game.game_id)

        if not game_state.game_started_posted:
            logger.info(f"Game starting: {game.away_team.tricode} @ {game.home_team.tricode}")

            message = self.formatter.build_game_start(game)
            thread_ts = self.slack.post_message(message)

            if thread_ts:
                game_state.game_started_posted = True
                game_state.thread_ts = thread_ts
                self.state.save_game(game_state)
                logger.info(f"Posted game start, thread_ts: {thread_ts}")

    def _process_in_progress_game(self, game) -> None:
        """Process an in-progress game for quarter updates and alerts"""
        game_state = self.state.get_game(game.game_id)
        away = game.away_team
        home = game.home_team

        logger.info(
            f"  {away.tricode} {away.score} @ {home.score} {home.tricode} | {game.game_time_display}"
        )

        # Check for halftime
        if self.monitor.is_halftime(game) and not game_state.halftime_posted:
            self._post_halftime(game, game_state)

        # Check for close game alert
        close_alert = self.monitor.detect_close_game(game)
        if close_alert and self._should_post_close_game_alert(game.game_id):
            self._post_close_game_alert(close_alert, game_state)

        # Check for performance alerts
        performance_alerts = self.monitor.detect_performance_alerts(game)
        for alert in performance_alerts:
            if not game_state.has_posted_performance_alert(alert.player.name, alert.alert_type):
                self._post_performance_alert(alert, game_state)

    def _process_finished_game(self, game) -> None:
        """Process a finished game for final update"""
        game_state = self.state.get_game(game.game_id)

        # Only process if final hasn't been posted yet
        if not game_state.final_posted:
            self._post_final(game, game_state)

    def _post_halftime(self, game, game_state) -> None:
        """Post halftime update"""
        logger.info(f"Posting halftime: {game.away_team.tricode} @ {game.home_team.tricode}")

        message = self.formatter.build_halftime_update(game)

        # Post to thread and broadcast to channel
        if game_state.thread_ts:
            self.slack.post_thread_reply(
                message,
                thread_ts=game_state.thread_ts,
                also_send_to_channel=True,
            )
        else:
            # No thread exists, post as new message
            self.slack.post_message(message)

        game_state.halftime_posted = True
        game_state.mark_quarter_posted(2)
        self.state.save_game(game_state)

    def _post_final(self, game, game_state) -> None:
        """Post final score update"""
        logger.info(f"Posting final: {game.away_team.tricode} @ {game.home_team.tricode}")

        message = self.formatter.build_final_update(game)

        # Post to thread and broadcast to channel
        if game_state.thread_ts:
            self.slack.post_thread_reply(
                message,
                thread_ts=game_state.thread_ts,
                also_send_to_channel=True,
            )
        else:
            # No thread exists, post as new message
            self.slack.post_message(message)

        game_state.final_posted = True
        game_state.mark_quarter_posted(game.period)
        self.state.save_game(game_state)

    def _should_post_close_game_alert(self, game_id: str) -> bool:
        """Check if we should post a close game alert (respecting cooldown)"""
        return self.close_game_cooldowns.get(game_id, 0) <= 0

    def _post_close_game_alert(self, alert, game_state) -> None:
        """Post close game alert to thread"""
        game = alert.game
        logger.info(f"Close game alert: {game.away_team.tricode} @ {game.home_team.tricode}")

        message = self.formatter.build_close_game_alert(alert)

        if game_state.thread_ts:
            ts = self.slack.post_thread_reply(message, thread_ts=game_state.thread_ts)
            if ts:
                game_state.close_game_alerts.append(ts)
                self.state.save_game(game_state)

        # Set cooldown
        self.close_game_cooldowns[game.game_id] = CLOSE_GAME_ALERT_COOLDOWN_POLLS

    def _post_performance_alert(self, alert, game_state) -> None:
        """Post performance alert to thread"""
        logger.info(f"Performance alert: {alert.description}")

        message = self.formatter.build_performance_alert(alert)

        if game_state.thread_ts:
            ts = self.slack.post_thread_reply(message, thread_ts=game_state.thread_ts)
            if ts:
                game_state.mark_performance_alert_posted(alert.player.name, alert.alert_type)
                self.state.save_game(game_state)

    def _update_cooldowns(self) -> None:
        """Decrement all cooldowns"""
        for game_id in list(self.close_game_cooldowns.keys()):
            self.close_game_cooldowns[game_id] -= 1
            if self.close_game_cooldowns[game_id] <= 0:
                del self.close_game_cooldowns[game_id]

    def _check_end_of_night(self, games: list) -> None:
        """Check if all games are finished and post end of night summary"""
        if self.state.is_end_of_night_posted():
            return

        # Check if there are any games and all are finished
        if not games:
            return

        all_finished = all(g.status == 3 for g in games)
        if not all_finished:
            return

        logger.info("All games finished, posting end of night summary")
        self._post_end_of_night_summary(games)

    def _post_end_of_night_summary(self, games: list) -> None:
        """Post the end of night summary with all final scores and leaders"""
        # Fetch daily leaders
        player_leaders = self._fetch_player_leaders()
        team_leaders = self._fetch_team_leaders()

        message = self.formatter.build_end_of_night_summary(
            games, player_leaders, team_leaders
        )

        if self.slack.post_message(message):
            self.state.mark_end_of_night_posted()
            logger.info("Posted end of night summary")

    def _fetch_player_leaders(self) -> dict[str, list[PlayerDailyLeader]]:
        """Fetch player leaders concurrently"""
        stats = ["pts", "reb", "ast", "fg3m", "fgpct"]
        leaders = {}

        with ThreadPoolExecutor(max_workers=len(stats)) as executor:
            futures = {
                executor.submit(self.api.get_player_daily_leaders, stat): stat
                for stat in stats
            }
            for future in as_completed(futures):
                stat = futures[future]
                data = future.result()
                if data and "playerstats" in data:
                    leaders[stat] = [
                        PlayerDailyLeader.from_api(p, stat)
                        for p in data["playerstats"][:3]
                    ]
                else:
                    leaders[stat] = []

        return leaders

    def _fetch_team_leaders(self) -> dict[str, list[TeamDailyLeader]]:
        """Fetch team leaders concurrently"""
        stats = ["pts", "ast", "fgpct", "fg3pct"]
        leaders = {}

        with ThreadPoolExecutor(max_workers=len(stats)) as executor:
            futures = {
                executor.submit(self.api.get_team_daily_leaders, stat): stat
                for stat in stats
            }
            for future in as_completed(futures):
                stat = futures[future]
                data = future.result()
                if data and "teamstats" in data:
                    leaders[stat] = [
                        TeamDailyLeader.from_api(t, stat)
                        for t in data["teamstats"][:3]
                    ]
                else:
                    leaders[stat] = []

        return leaders

    def run_once(self) -> None:
        """Run a single check cycle"""
        self.check_games()

    def run_continuous(self) -> None:
        """Run continuous monitoring until interrupted"""
        logger.info("=" * 60)
        logger.info("NBA Game Monitor Started")
        logger.info(f"Polling interval: {config.poll_interval_active}s (active) / {config.poll_interval_idle}s (idle)")
        logger.info("Press CTRL+C to stop")
        logger.info("=" * 60)

        def signal_handler(sig, frame):
            logger.info("=" * 60)
            logger.info("Monitor stopped by user")
            logger.info("=" * 60)
            self.stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)

        while not self.stop_event.is_set():
            has_active_games = False
            try:
                has_active_games = self.check_games()
            except Exception as e:
                logger.error(f"Error during check: {e}", exc_info=True)

            # Use dynamic polling: faster when games active, slower when idle
            interval = config.poll_interval_active if has_active_games else config.poll_interval_idle
            logger.debug(f"Sleeping for {interval} seconds ({'active' if has_active_games else 'idle'} mode)...")
            self.stop_event.wait(interval)


def main():
    parser = argparse.ArgumentParser(description="NBA Game Monitor - Slack Updates")
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

    service = QuarterUpdateService(dry_run=args.dry_run)

    if args.once:
        service.run_once()
    else:
        service.run_continuous()


if __name__ == "__main__":
    main()
