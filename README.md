# NBA Quarter-End Updates to Slack

Automatically monitors NBA games in progress and posts scoring updates to Slack after each quarter ends. **Now runs continuously throughout the night without manual intervention!**

## Setup

1. **Install dependencies** (if not already installed):
   ```bash
   pip install requests python-dotenv
   ```

2. **Configure environment variables**:
   Create a `.env` file with:
   ```
   SCHEDULE_API_KEY=your_schedule_api_key
   STATS_API_KEY=your_stats_api_key
   SLACK_WEBHOOK_URL=your_slack_webhook_url
   ```

3. **Test the connection**:
   ```bash
   python debug_api.py
   ```
   This will show you today's games and test the boxscore API.

## Usage

### Run Continuously (Recommended for Live Games)
```bash
python quarter_end_updates.py
```

The script will:
- ✅ Poll for game updates every 2 minutes automatically
- ✅ Track which quarters have been posted (no duplicates)
- ✅ Run all night until you stop it with CTRL+C
- ✅ Display status updates in the console

**No need for cron jobs, loops, or manual re-runs!**

### Adjust Polling Interval (Optional)
Edit the `POLL_INTERVAL_SECONDS` variable in the script:
```python
POLL_INTERVAL_SECONDS = 120  # Check every 2 minutes (default)
```

## How It Works

1. **Fetches today's games** using the Schedule API (with `SCHEDULE_API_KEY`)
2. **Gets boxscore data** for each game using the Stats API (with `STATS_API_KEY`)
3. **Detects quarter endings** by checking game status and period
4. **Tracks posted quarters** to prevent duplicate messages
5. **Posts to Slack** with:
   - Final score at end of quarter
   - Top 2 performers for each team
   - Stats: PTS, REB, AST, and notable stats (3PM, STL, BLK)
6. **Sleeps and repeats** until stopped

## Message Format

```
The Pistons lead the Trail Blazers, 61-51, at the end of 1Q.

Pistons Top Performers
Cade Cunningham – 12 PTS | 4 REB | 4 AST
Duncan Robinson – 9 PTS | 3 AST | 2 3PM

Trail Blazers Top Performers
Shaedon Sharpe – 16 PTS | 2 REB | 3 STL
Deni Avdija – 12 PTS | 5 REB | 2 AST
```

## API Keys

**Important**: This script uses TWO different API keys:
- `SCHEDULE_API_KEY` - For fetching game schedules
- `STATS_API_KEY` - For fetching boxscore/player stats

Both must be configured in your `.env` file.

## Notes

- The script maintains an in-memory tracker to prevent duplicate posts
- Each game+quarter combination is posted exactly once
- The tracker persists for the entire run (resets when script restarts)
- Handles ties by using PTS + REB + AST as tiebreaker for top performers
- Automatically formats quarter names (1Q, 2Q, 3Q, Final)
- Safe to stop anytime with CTRL+C
