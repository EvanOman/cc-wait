"""Background daemon that monitors rate limits and auto-continues sessions."""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from cc_wait.oauth import UsageStatus, fetch_usage_status
from cc_wait.tmux import (
    capture_pane_content,
    detect_rate_limit,
    get_claude_panes,
    is_tmux_available,
    send_continue,
)

POLL_INTERVAL = int(os.environ.get("CC_WAIT_POLL_INTERVAL", "60"))
DEBUG = os.environ.get("CC_WAIT_DEBUG", "").lower() in ("1", "true", "yes")
DEBUG_LOG_PATH = Path.home() / ".claude" / "cc-wait-daemon.log"


def log(msg: str, *, debug_only: bool = False, to_file: bool = False) -> None:
    """Log a message with timestamp."""
    if debug_only and not DEBUG:
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, file=sys.stderr, flush=True)

    # Also write to debug log file if requested
    if to_file or DEBUG:
        _write_debug_log(line)


def _write_debug_log(msg: str) -> None:
    """Append message to debug log file."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass  # Don't crash on log failures


def debug_log(msg: str) -> None:
    """Write detailed debug info to log file only (not stderr)."""
    _write_debug_log(msg)


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
                        f"Rate limit hit (100%). Reset at {reset_str} ({format_duration(remaining)})",
                        to_file=True,
                    )
                else:
                    log("Rate limit hit (100%).", to_file=True)

                # Log Claude sessions that might need continuing
                panes = get_claude_panes()
                debug_log("=" * 60)
                debug_log("RATE LIMIT HIT - Capturing initial session state")
                debug_log("=" * 60)
                if panes:
                    log(f"Found {len(panes)} Claude session(s) to monitor", to_file=True)
                    for pane in panes:
                        debug_log(f"  - {pane.pane_id} ({pane.session_name}): {pane.command}")
                else:
                    log("No Claude sessions found in tmux", to_file=True)

            # Check if we've passed the reset time
            reset = status.next_reset
            if reset and datetime.now(UTC) >= reset:
                log("Reset time reached, but API still shows limited. Waiting...", debug_only=True)

        else:
            if self.waiting_for_reset:
                # Rate limit just cleared - check which sessions are blocked and continue them
                log("Rate limit reset! Checking for blocked sessions...", to_file=True)
                self._continue_blocked_sessions()
                self.waiting_for_reset = False
                self.continued_panes.clear()

    def _continue_blocked_sessions(self) -> None:
        """Send continue sequence only to Claude panes that are actually blocked.

        Captures each pane's content, checks for rate limit indicators,
        and only sends continue to panes showing the rate limit message.
        Logs everything for debugging.
        """
        panes = get_claude_panes()

        if not panes:
            log("No Claude sessions found", to_file=True)
            return

        debug_log("=" * 60)
        debug_log(f"RATE LIMIT RESET - Checking {len(panes)} Claude session(s)")
        debug_log("=" * 60)

        blocked_panes = []
        for pane in panes:
            if pane.pane_id in self.continued_panes:
                debug_log(f"[{pane.pane_id}] Already continued, skipping")
                continue

            # Capture pane content for analysis
            content = capture_pane_content(pane.pane_id, lines=50)

            debug_log(f"\n[{pane.pane_id}] Session: {pane.session_name}")
            debug_log(f"[{pane.pane_id}] Command: {pane.command}")
            debug_log(f"[{pane.pane_id}] Content length: {len(content)} chars")
            debug_log(f"[{pane.pane_id}] --- BEGIN CONTENT ---")
            # Log last 30 lines for context
            content_lines = content.strip().split("\n")
            for line in content_lines[-30:]:
                debug_log(f"[{pane.pane_id}]   {line[:200]}")  # Truncate long lines
            debug_log(f"[{pane.pane_id}] --- END CONTENT ---")

            # Check for rate limit indicators
            rate_info = detect_rate_limit(content)

            if rate_info:
                debug_log(f"[{pane.pane_id}] DETECTED RATE LIMIT: {rate_info}")
                blocked_panes.append(pane)
            else:
                # Fallback: check ONLY the last 15 lines for rate limit indicators
                # This avoids false positives from code/explanations earlier in history
                last_lines = "\n".join(content_lines[-15:]).lower()

                # Must have "claude" + "usage limit" together (not just generic text)
                has_claude_usage_limit = "claude" in last_lines and "usage limit" in last_lines
                has_limit_reset = "limit will reset" in last_lines
                # Check for the numbered menu that Claude shows
                has_menu = "1." in last_lines and ("wait" in last_lines or "upgrade" in last_lines)

                debug_log(f"[{pane.pane_id}] Detection results:")
                debug_log(f"[{pane.pane_id}]   detect_rate_limit(): None")
                debug_log(f"[{pane.pane_id}]   Checking last 15 lines only...")
                debug_log(
                    f"[{pane.pane_id}]   'claude' + 'usage limit' in last 15 lines: {has_claude_usage_limit}"
                )
                debug_log(
                    f"[{pane.pane_id}]   'limit will reset' in last 15 lines: {has_limit_reset}"
                )
                debug_log(f"[{pane.pane_id}]   menu format (1. + wait/upgrade): {has_menu}")

                # Require BOTH the Claude usage limit text AND the menu format
                if has_claude_usage_limit and has_limit_reset and has_menu:
                    debug_log(
                        f"[{pane.pane_id}] FALLBACK DETECTED: has all indicators in recent lines"
                    )
                    blocked_panes.append(pane)
                else:
                    debug_log(f"[{pane.pane_id}] NOT BLOCKED - skipping")

        debug_log(f"\nSummary: {len(blocked_panes)}/{len(panes)} panes detected as blocked")

        if not blocked_panes:
            log("No blocked sessions detected", to_file=True)
            return

        log(f"Sending continue to {len(blocked_panes)} blocked session(s)...", to_file=True)

        for pane in blocked_panes:
            if send_continue(pane.pane_id):
                log(
                    f"  → {pane.pane_id} ({pane.session_name}): sent '1' + 'continue'", to_file=True
                )
                self.continued_panes.add(pane.pane_id)
            else:
                log(f"  ✗ {pane.pane_id} ({pane.session_name}): failed to send", to_file=True)


def run_daemon(poll_interval: int = POLL_INTERVAL) -> None:
    """Run the rate limit daemon."""
    daemon = RateLimitDaemon(poll_interval=poll_interval)
    daemon.run()
