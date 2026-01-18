"""tmux pane detection and interaction."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass


def _get_tmux_env() -> dict[str, str]:
    """Get environment variables for tmux commands."""
    env = os.environ.copy()
    # Allow overriding tmux socket directory (useful for Docker)
    if "TMUX_TMPDIR" in os.environ:
        env["TMUX_TMPDIR"] = os.environ["TMUX_TMPDIR"]
    return env


@dataclass
class TmuxPane:
    """A tmux pane running Claude."""

    pane_id: str
    session_name: str
    command: str
    is_rate_limited: bool = False
    reset_info: str | None = None


def is_tmux_available() -> bool:
    """Check if tmux is available and has sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            timeout=5,
            env=_get_tmux_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_claude_panes() -> list[TmuxPane]:
    """Find all tmux panes running Claude."""
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_id}\t#{session_name}\t#{pane_current_command}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=_get_tmux_env(),
        )
        if result.returncode != 0:
            return []

        panes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                pane_id, session_name, command = parts[0], parts[1], parts[2]
                if "claude" in command.lower():
                    panes.append(
                        TmuxPane(
                            pane_id=pane_id,
                            session_name=session_name,
                            command=command,
                        )
                    )
        return panes
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def capture_pane_content(pane_id: str, lines: int = 100) -> str:
    """Capture the visible content of a tmux pane."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", f"-{lines}"],
            capture_output=True,
            text=True,
            timeout=5,
            env=_get_tmux_env(),
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def detect_rate_limit(content: str) -> dict | None:
    """
    Check if pane content shows a rate limit message.

    Expected message format:
    "Claude usage limit reached. Your limit will reset at 7pm (America/Chicago)."

    Returns dict with reset info if found, None otherwise.
    """
    content_lower = content.lower()

    # Look for the specific Claude rate limit message
    # Pattern: "Claude usage limit reached" followed by reset time
    full_pattern = (
        r"claude\s+usage\s+limit\s+reached.*?"
        r"limit\s+will\s+reset\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*(?:\(([^)]+)\))?"
    )

    match = re.search(full_pattern, content_lower, re.DOTALL)
    if not match:
        return None

    # Reject matches that appear to be from code, tests, or diffs
    # Look at context around the match for indicators
    raw_match = match.group(0)
    start = max(0, match.start() - 50)
    context = content_lower[start : match.end()]

    # Code/diff indicators: quotes, assignment, diff markers
    code_indicators = ['content = "', 'content="', '= "claude', ">>> ", "... ", "\n+"]
    if any(ind in context for ind in code_indicators):
        return None

    groups = match.groups()
    hour = int(groups[0])
    minute = int(groups[1]) if groups[1] else 0
    ampm = groups[2]
    timezone = groups[3] if len(groups) > 3 else None

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    return {
        "reset_hour": hour,
        "reset_minute": minute,
        "timezone": timezone,
        "raw_match": raw_match,
    }


def find_rate_limited_panes() -> list[TmuxPane]:
    """Find all Claude panes that are showing rate limit messages."""
    panes = get_claude_panes()
    limited = []

    for pane in panes:
        content = capture_pane_content(pane.pane_id)
        rate_info = detect_rate_limit(content)

        if rate_info:
            pane.is_rate_limited = True
            pane.reset_info = rate_info.get("raw_match")
            limited.append(pane)

    return limited


def send_continue(pane_id: str) -> bool:
    """
    Send 'continue' command to a tmux pane.

    Returns True if successful, False otherwise.
    """
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "continue", "Enter"],
            capture_output=True,
            timeout=5,
            env=_get_tmux_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
