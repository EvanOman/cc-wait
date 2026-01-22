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
        content = "Claude usage limit reached. Your limit will reset at 3:30pm (America/New_York)."
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 15
        assert result["reset_minute"] == 30

    def test_detects_am_time(self) -> None:
        content = "Claude usage limit reached. Your limit will reset at 9am"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 9
        assert result["reset_minute"] == 0

    def test_detects_12pm(self) -> None:
        content = "Claude usage limit reached. Your limit will reset at 12pm"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 12

    def test_detects_12am(self) -> None:
        content = "Claude usage limit reached. Your limit will reset at 12am"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 0

    def test_returns_none_for_no_match(self) -> None:
        content = "Normal output without any rate limit messages"
        result = detect_rate_limit(content)
        assert result is None

    def test_returns_none_without_claude_prefix(self) -> None:
        # Must have "Claude usage limit reached" - generic messages don't match
        content = "Usage limit reached. Your limit will reset at 7pm"
        result = detect_rate_limit(content)
        assert result is None

    def test_ignores_code_snippets_with_keywords(self) -> None:
        # This is what caused false positives - code explaining the detection
        content = """
        indicators = ["usage limit", "limit reached", "limit will reset"]
        if not any(ind in content_lower for ind in indicators):
            return None
        """
        result = detect_rate_limit(content)
        assert result is None

    def test_ignores_test_strings_in_diffs(self) -> None:
        # Git diff output with test strings should not match
        content = """
        -        content = "Your limit will reset at 3:30pm (America/New_York)."
        +        content = "Your limit will reset at 3:30pm (America/New_York)."
        """
        result = detect_rate_limit(content)
        assert result is None

    def test_handles_ansi_escape_codes(self) -> None:
        # ANSI codes typically wrap the whole message, not break up words
        content = "\x1b[31mClaude usage limit reached. Your limit will reset at 7pm\x1b[0m"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 19

    def test_extracts_timezone(self) -> None:
        content = "Claude usage limit reached. Your limit will reset at 7pm (America/Chicago)"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["timezone"] == "america/chicago"  # lowercase from regex

    def test_handles_multiline_message(self) -> None:
        # The message might span lines in some terminals
        content = "Claude usage limit reached.\nYour limit will reset at 7pm (America/Chicago)."
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 19

    def test_detects_hit_your_limit_format(self) -> None:
        # Alternative format: "You've hit your limit · resets 2am"
        content = "You've hit your limit · resets 2am (America/Chicago)"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 2
        assert result["reset_minute"] == 0
        assert result["timezone"] == "america/chicago"

    def test_detects_hit_your_limit_with_minutes(self) -> None:
        content = "You've hit your limit · resets 3:30pm (America/New_York)"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 15
        assert result["reset_minute"] == 30

    def test_detects_hit_your_limit_with_dash(self) -> None:
        # Sometimes uses dash instead of middle dot
        content = "You've hit your limit - resets 7pm"
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 19

    def test_detects_real_terminal_output(self) -> None:
        # Real captured output from a rate-limited pane
        content = """
        ⎿  You've hit your limit · resets 2am (America/Chicago)

❯ /rate-limit-options

─────────────────────────────────────────────────────────────────────────────────
 What do you want to do?

 ❯ 1. Stop and wait for limit to reset
   2. Upgrade your plan

 Enter to confirm · escape to cancel
"""
        result = detect_rate_limit(content)
        assert result is not None
        assert result["reset_hour"] == 2
