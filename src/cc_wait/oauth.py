"""OAuth credential loading and usage API client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"


@dataclass
class UsageWindow:
    """Rate limit usage for a time window."""

    utilization: float  # 0-100 percentage
    resets_at: datetime | None

    @property
    def is_limited(self) -> bool:
        """True if utilization is at or above 100%."""
        return self.utilization >= 100.0

    @property
    def resets_in_seconds(self) -> int | None:
        """Seconds until reset, or None if no reset time."""
        if self.resets_at is None:
            return None
        delta = self.resets_at - datetime.now(UTC)
        return max(0, int(delta.total_seconds()))


@dataclass
class UsageStatus:
    """Current rate limit status from OAuth API."""

    five_hour: UsageWindow
    seven_day: UsageWindow
    seven_day_opus: UsageWindow | None = None

    @property
    def is_limited(self) -> bool:
        """True if any window is at limit."""
        return self.five_hour.is_limited or self.seven_day.is_limited

    @property
    def next_reset(self) -> datetime | None:
        """Earliest reset time across all limited windows."""
        resets = []
        if self.five_hour.is_limited and self.five_hour.resets_at:
            resets.append(self.five_hour.resets_at)
        if self.seven_day.is_limited and self.seven_day.resets_at:
            resets.append(self.seven_day.resets_at)
        return min(resets) if resets else None


def load_oauth_token() -> str | None:
    """Load OAuth access token from Claude Code credentials file."""
    if not CREDENTIALS_PATH.exists():
        return None

    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)

        oauth_data = creds.get("claudeAiOauth", {})
        return oauth_data.get("accessToken")
    except (json.JSONDecodeError, KeyError):
        return None


def _parse_datetime(s: str | None) -> datetime | None:
    """Parse ISO datetime string to datetime."""
    if not s:
        return None
    try:
        # Handle various ISO formats
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _parse_window(data: dict) -> UsageWindow:
    """Parse a usage window from API response."""
    return UsageWindow(
        utilization=float(data.get("utilization", 0)),
        resets_at=_parse_datetime(data.get("resets_at")),
    )


def fetch_usage_status(token: str | None = None) -> UsageStatus | None:
    """
    Fetch current usage status from OAuth API.

    Returns None if credentials unavailable or API call fails.
    """
    if token is None:
        token = load_oauth_token()
    if token is None:
        return None

    try:
        response = httpx.get(
            USAGE_API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        opus_data = data.get("seven_day_opus")
        return UsageStatus(
            five_hour=_parse_window(data.get("five_hour", {})),
            seven_day=_parse_window(data.get("seven_day", {})),
            seven_day_opus=_parse_window(opus_data) if opus_data else None,
        )
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return None
