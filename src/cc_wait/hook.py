"""
Claude Code Stop hook that waits until rate limits reset and then continues.

When Claude hits rate limits, this hook:
1. Detects the reset time from messages like "Your limit will reset at 7pm"
2. Calculates the wait duration until that time
3. Sleeps until the reset window
4. Returns a signal to continue the conversation
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEBUG = os.environ.get("CC_WAIT_DEBUG", "").lower() in ("1", "true", "yes")
DEBUG_LOG = Path.home() / ".claude" / "wait_hook_debug.log"


def log_debug(msg: str) -> None:
    """Log debug message to file if DEBUG is enabled."""
    if DEBUG:
        timestamp = datetime.now().isoformat()
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{timestamp}] {msg}\n")


def parse_reset_time(text: str) -> datetime | None:
    """
    Parse reset time from Claude Code messages.

    Examples:
    - "Your limit will reset at 7pm (Asia/Tokyo)"
    - "reset at 3:30pm"
    - "resets at 14:00"
    - "will reset at 9am"
    """
    text_lower = text.lower()

    # Pattern: "reset at Xpm/am (Timezone)" or "reset at X:XXpm/am (Timezone)"
    # Matches: "7pm", "7:30pm", "14:00", "2:30 pm"
    patterns = [
        # "reset at 7pm (Asia/Tokyo)" or "reset at 7:30pm (America/New_York)"
        r"reset\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?",
        # "resets at 14:00"
        r"resets?\s+at\s+(\d{1,2}):(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            groups = match.groups()
            log_debug(f"Matched pattern '{pattern}' with groups: {groups}")

            hour = int(groups[0])
            minute = int(groups[1]) if groups[1] else 0

            # Handle am/pm if present
            if len(groups) > 2 and groups[2]:
                ampm = groups[2]
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

            # Get timezone if specified
            tz: tzinfo | None = None
            if len(groups) > 3 and groups[3]:
                try:
                    tz = ZoneInfo(groups[3])
                except Exception:
                    log_debug(f"Could not parse timezone: {groups[3]}")

            if tz is None:
                tz = datetime.now().astimezone().tzinfo

            # Build the reset datetime
            now = datetime.now(tz)
            reset_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If reset time is in the past, it's tomorrow
            if reset_time <= now:
                reset_time += timedelta(days=1)

            log_debug(f"Parsed reset time: {reset_time}")
            return reset_time

    return None


def extract_wait_seconds(text: str) -> int | None:
    """Fallback: extract wait time in seconds from text like 'try again in 30 seconds'."""
    patterns = [
        r"(\d+)\s*(second|minute|hour|sec|min|hr)",
        r'retry[_-]?after["\s:]+(\d+)',
        r"in\s+(\d+):(\d+)",  # "in 5:30" format
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            groups = match.groups()
            if len(groups) == 2 and groups[1] and not groups[1].isdigit():
                # Pattern like "30 seconds"
                amount = int(groups[0])
                unit = groups[1]
                if "min" in unit:
                    amount *= 60
                elif "hour" in unit or "hr" in unit:
                    amount *= 3600
                return amount
            elif len(groups) == 2 and groups[1] and groups[1].isdigit():
                # Pattern like "5:30"
                return int(groups[0]) * 60 + int(groups[1])
            else:
                return int(groups[0])

    return None


def read_transcript_tail(transcript_path: str, lines: int = 100) -> list[dict[str, Any]]:
    """Read the last N lines of the transcript JSONL file."""
    path = Path(transcript_path)
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with open(path) as f:
        all_lines = f.readlines()
        for line in all_lines[-lines:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def find_rate_limit_info(
    hook_input: dict[str, Any], transcript_entries: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """
    Search for rate limit information in hook input and transcript.
    Returns dict with either 'reset_time' (datetime) or 'wait_seconds' (int).
    """
    # Combine all text to search
    all_text = json.dumps(hook_input)
    for entry in reversed(transcript_entries[-20:]):  # Check recent entries
        all_text += " " + json.dumps(entry)

    all_text_lower = all_text.lower()

    # Check for rate limit indicators
    rate_limit_indicators = [
        "usage limit",
        "rate limit",
        "limit reached",
        "rate_limit",
        "ratelimit",
        "429",
        "too many requests",
        "try again",
    ]

    if not any(ind in all_text_lower for ind in rate_limit_indicators):
        return None

    log_debug("Rate limit indicator found in text")
    log_debug(f"Text sample: {all_text[:500]}")

    # Try to parse reset time first (preferred)
    reset_time = parse_reset_time(all_text)
    if reset_time:
        return {"reset_time": reset_time}

    # Fallback to wait seconds
    wait_seconds = extract_wait_seconds(all_text)
    if wait_seconds:
        return {"wait_seconds": wait_seconds}

    # Default wait if rate limit detected but no time found
    return {"wait_seconds": 300}  # 5 minute default


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


def main() -> int:
    """Main entry point for the hook."""
    log_debug("=" * 60)
    log_debug("Hook invoked")

    # Read hook input from stdin
    try:
        raw_input = sys.stdin.read()
        log_debug(f"Raw stdin length: {len(raw_input)}")
        hook_input: dict[str, Any] = json.loads(raw_input) if raw_input.strip() else {}
    except json.JSONDecodeError as e:
        log_debug(f"JSON decode error: {e}")
        print(json.dumps({"decision": "allow"}))
        return 0

    # Read transcript
    transcript_path = hook_input.get("transcript_path", "")
    entries: list[dict[str, Any]] = []
    if transcript_path:
        entries = read_transcript_tail(transcript_path)
        log_debug(f"Read {len(entries)} transcript entries")

    # Look for rate limit info
    rate_limit_info = find_rate_limit_info(hook_input, entries)

    if not rate_limit_info:
        log_debug("No rate limit detected, allowing stop")
        print(json.dumps({"decision": "allow"}))
        return 0

    # Calculate wait time
    reset_str: str | None = None
    if "reset_time" in rate_limit_info:
        reset_time = rate_limit_info["reset_time"]
        now = datetime.now(reset_time.tzinfo)
        wait_seconds = int((reset_time - now).total_seconds())
        reset_str = reset_time.strftime("%H:%M %Z")
        log_debug(f"Reset time: {reset_time}, wait: {wait_seconds}s")
    else:
        wait_seconds = rate_limit_info["wait_seconds"]
        log_debug(f"Wait seconds: {wait_seconds}")

    # Sanity check wait time
    if wait_seconds <= 0:
        log_debug("Wait time <= 0, allowing stop")
        print(json.dumps({"decision": "allow"}))
        return 0

    # Cap at 6 hours (rate limits reset every 5 hours max)
    max_wait = 6 * 3600
    if wait_seconds > max_wait:
        log_debug(f"Capping wait from {wait_seconds}s to {max_wait}s")
        wait_seconds = max_wait

    # Display wait info
    duration_str = format_duration(wait_seconds)
    if reset_str:
        print(
            f"⏳ Rate limit reached. Waiting until {reset_str} ({duration_str})...", file=sys.stderr
        )
    else:
        print(f"⏳ Rate limit reached. Waiting {duration_str}...", file=sys.stderr)

    # Wait with periodic status updates for long waits
    start_time = time.time()
    update_interval = 300  # Update every 5 minutes for long waits

    while True:
        elapsed = time.time() - start_time
        remaining = wait_seconds - elapsed

        if remaining <= 0:
            break

        # Sleep in chunks for long waits
        sleep_time = min(remaining, update_interval)
        time.sleep(sleep_time)

        remaining = wait_seconds - (time.time() - start_time)
        if remaining > 60:
            print(f"⏳ {format_duration(int(remaining))} remaining...", file=sys.stderr)

    print("✓ Rate limit reset. Continuing...", file=sys.stderr)

    # Block stopping and tell Claude to continue
    output = {"decision": "block", "reason": "continue"}
    log_debug(f"Returning: {output}")
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
