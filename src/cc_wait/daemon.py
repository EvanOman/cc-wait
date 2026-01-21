"""Background daemon that monitors rate limits and auto-continues sessions."""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime

from cc_wait.oauth import UsageStatus, fetch_usage_status
from cc_wait.tmux import get_claude_panes, is_tmux_available, send_continue

POLL_INTERVAL = int(os.environ.get("CC_WAIT_POLL_INTERVAL", "60"))
DEBUG = os.environ.get("CC_WAIT_DEBUG", "").lower() in ("1", "true", "yes")


def log(msg: str, *, debug_only: bool = False) -> None:
    """Log a message with timestamp."""
    if debug_only and not DEBUG:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", file=sys.stderr, flush=True)


def format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"


class RateLimitDaemon:
    """Daemon that monitors rate limits and auto-continues sessions."""

    def __init__(self, poll_interval: int = POLL_INTERVAL):
        self.poll_interval = poll_interval
        self.waiting_for_reset = False
        self.last_status: UsageStatus | None = None
        self.continued_panes: set[str] = set()  # Track panes we've already continued

    def run(self) -> None:
        """Main daemon loop."""
        log("cc-wait daemon started")
        log(f"Poll interval: {self.poll_interval}s", debug_only=True)

        if not is_tmux_available():
            log("Warning: tmux not available. Auto-continue will not work.")

        while True:
            try:
                self._check_and_handle()
            except KeyboardInterrupt:
                log("Daemon stopped")
                break
            except Exception as e:
                log(f"Error: {e}", debug_only=True)

            time.sleep(self.poll_interval)

    def _check_and_handle(self) -> None:
        """Check usage and handle rate limits."""
        status = fetch_usage_status()

        if status is None:
            log("Failed to fetch usage status", debug_only=True)
            return

        self.last_status = status

        if status.is_limited:
            if not self.waiting_for_reset:
                # Just hit the limit
                self.waiting_for_reset = True
                self.continued_panes.clear()

                reset = status.next_reset
                if reset:
                    reset_str = reset.strftime("%H:%M")
                    remaining = status.five_hour.resets_in_seconds or 0
                    log(
                        f"Rate limit hit (100%). Reset at {reset_str} ({format_duration(remaining)})"
                    )
                else:
                    log("Rate limit hit (100%).")

                # Log how many Claude sessions we'll continue when limit resets
                panes = get_claude_panes()
                if panes:
                    log(f"Will send 'continue' to {len(panes)} Claude session(s) when limit resets")
                else:
                    log("No Claude sessions found in tmux")

            # Check if we've passed the reset time
            reset = status.next_reset
            if reset and datetime.now(UTC) >= reset:
                log("Reset time reached, but API still shows limited. Waiting...", debug_only=True)

        else:
            if self.waiting_for_reset:
                # Rate limit just cleared - continue ALL Claude sessions
                log("Rate limit reset! Continuing all Claude sessions...")
                self._continue_all_sessions()
                self.waiting_for_reset = False
                self.continued_panes.clear()

    def _continue_all_sessions(self) -> None:
        """Send 'continue' to ALL Claude panes.

        We don't try to detect which panes are blocked - just send continue to all.
        This is more robust than regex-based terminal parsing.
        Sending 'continue' to a non-blocked pane is harmless.
        """
        panes = get_claude_panes()

        if not panes:
            log("No Claude sessions found")
            return

        for pane in panes:
            if pane.pane_id in self.continued_panes:
                continue

            if send_continue(pane.pane_id):
                log(f"Sent 'continue' to {pane.pane_id} ({pane.session_name})")
                self.continued_panes.add(pane.pane_id)
            else:
                log(f"Failed to send 'continue' to {pane.pane_id}")


def run_daemon(poll_interval: int = POLL_INTERVAL) -> None:
    """Run the rate limit daemon."""
    daemon = RateLimitDaemon(poll_interval=poll_interval)
    daemon.run()
