"""Tests for tmux module."""

from cc_wait.tmux import detect_rate_limit


class TestDetectRateLimit:
    """Tests for rate limit detection in pane content."""

    def test_detects_usage_limit_message(self) -> None:
        content = "Claude usage limit reached. Your limit will reset at 7pm (America/Chicago)."
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 19
        assert result["reset_minute"] == 0

    def test_detects_with_minutes(self) -> None:
        content = "Your limit will reset at 3:30pm (America/New_York)."
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 15
        assert result["reset_minute"] == 30

    def test_detects_am_time(self) -> None:
        content = "limit will reset at 9am"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 9
        assert result["reset_minute"] == 0

    def test_detects_12pm(self) -> None:
        content = "limit will reset at 12pm"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 12

    def test_detects_12am(self) -> None:
        content = "limit will reset at 12am"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 0

    def test_returns_none_for_no_match(self) -> None:
        content = "Normal output without any rate limit messages"
        result = detect_rate_limit(content)
        assert result is None

    def test_returns_dict_when_indicator_but_no_time(self) -> None:
        content = "Usage limit reached but no time info"
        result = detect_rate_limit(content)
        assert result is not None
        assert result.get("raw_match") is None

    def test_handles_ansi_escape_codes(self) -> None:
        content = "\x1b[31mUsage limit\x1b[0m reached. limit will reset at 7pm"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 19

    def test_extracts_timezone(self) -> None:
        content = "limit will reset at 7pm (America/Chicago)"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["timezone"] == "america/chicago"  # lowercase from regex
