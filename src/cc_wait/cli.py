"""CLI entry point for cc-wait."""

from __future__ import annotations

import argparse
import sys

from cc_wait.daemon import POLL_INTERVAL, run_daemon
from cc_wait.oauth import fetch_usage_status
from cc_wait.tmux import find_rate_limited_panes, get_claude_panes, is_tmux_available


def format_bar(percent: float, width: int = 10) -> str:
    """Format a percentage as a progress bar."""
    filled = int(percent / 100 * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"


def cmd_status(args: argparse.Namespace) -> int:
    """Show current rate limit status."""
    status = fetch_usage_status()

    if status is None:
        print("Error: Could not fetch usage status.")
        print("Make sure you're logged into Claude Code (check ~/.claude/.credentials.json)")
        return 1

    # 5-hour window
    five = status.five_hour
    bar = format_bar(five.utilization)
    resets = format_duration(five.resets_in_seconds) if five.resets_in_seconds else "N/A"
    limited = " ⚠️ LIMITED" if five.is_limited else ""
    print(f"5-hour:  {five.utilization:5.1f}% {bar}  resets in {resets}{limited}")

    # 7-day window
    seven = status.seven_day
    bar = format_bar(seven.utilization)
    resets = format_duration(seven.resets_in_seconds) if seven.resets_in_seconds else "N/A"
    limited = " ⚠️ LIMITED" if seven.is_limited else ""
    print(f"7-day:   {seven.utilization:5.1f}% {bar}  resets in {resets}{limited}")

    # Opus (if available)
    if status.seven_day_opus:
        opus = status.seven_day_opus
        bar = format_bar(opus.utilization)
        resets = format_duration(opus.resets_in_seconds) if opus.resets_in_seconds else "N/A"
        limited = " ⚠️ LIMITED" if opus.is_limited else ""
        print(f"Opus:    {opus.utilization:5.1f}% {bar}  resets in {resets}{limited}")

    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    """Detect rate-limited Claude sessions in tmux."""
    if not is_tmux_available():
        print("Error: tmux not available or no sessions running.")
        return 1

    print("Scanning tmux panes for Claude sessions...")
    print()

    all_panes = get_claude_panes()
    if not all_panes:
        print("No Claude sessions found in tmux.")
        return 0

    print(f"Found {len(all_panes)} Claude session(s):")

    limited_panes = find_rate_limited_panes()
    limited_ids = {p.pane_id for p in limited_panes}

    for pane in all_panes:
        if pane.pane_id in limited_ids:
            print(f"  ⚠️  {pane.pane_id} ({pane.session_name}): RATE LIMITED")
        else:
            print(f"  ✓  {pane.pane_id} ({pane.session_name}): OK")

    print()
    print(f"Rate limited: {len(limited_panes)}")

    if limited_panes:
        print()
        print("To manually continue these sessions:")
        for pane in limited_panes:
            print(f"  tmux send-keys -t {pane.pane_id} 'continue' Enter")

    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run the rate limit monitor daemon."""
    poll_interval = args.interval if hasattr(args, "interval") else POLL_INTERVAL
    run_daemon(poll_interval=poll_interval)
    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="cc-wait",
        description="Automatically continue Claude Code sessions after rate limits reset.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status command
    subparsers.add_parser("status", help="Show current rate limit status")

    # detect command
    subparsers.add_parser("detect", help="Detect rate-limited Claude sessions in tmux")

    # daemon command
    daemon_parser = subparsers.add_parser("daemon", help="Run the rate limit monitor daemon")
    daemon_parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=POLL_INTERVAL,
        help=f"Poll interval in seconds (default: {POLL_INTERVAL})",
    )

    args = parser.parse_args()

    if args.command == "status":
        return cmd_status(args)
    elif args.command == "detect":
        return cmd_detect(args)
    elif args.command == "daemon":
        return cmd_daemon(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
