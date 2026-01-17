"""Tests for the cc-wait hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cc_wait.hook import check_terminal_output, extract_wait_seconds, format_duration, parse_reset_time

HOOK_SCRIPT = Path(__file__).parent.parent / "src" / "cc_wait" / "hook.py"


class TestParseResetTime:
    """Tests for parse_reset_time function."""

    @pytest.mark.parametrize(
        ("text", "expected_hour", "expected_minute"),
        [
            ("Your limit will reset at 7pm", 19, 0),
            ("reset at 3:30pm (America/New_York)", 15, 30),
            ("resets at 14:00", 14, 0),
            ("will reset at 9am", 9, 0),
            ("reset at 12pm", 12, 0),
            ("reset at 12am", 0, 0),
        ],
    )
    def test_parses_reset_times(self, text: str, expected_hour: int, expected_minute: int) -> None:
        result = parse_reset_time(text)
        assert result is not None
        assert result.hour == expected_hour
        assert result.minute == expected_minute

    def test_returns_none_for_no_match(self) -> None:
        result = parse_reset_time("no reset time here")
        assert result is None


class TestExtractWaitSeconds:
    """Tests for extract_wait_seconds function."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("try again in 30 seconds", 30),
            ("wait 5 minutes", 300),
            ("retry after 2 hours", 7200),
            ("retry-after: 60", 60),
            ("in 5:30", 330),
        ],
    )
    def test_extracts_wait_seconds(self, text: str, expected: int) -> None:
        result = extract_wait_seconds(text)
        assert result == expected

    def test_returns_none_for_no_match(self) -> None:
        result = extract_wait_seconds("no time here")
        assert result is None


class TestFormatDuration:
    """Tests for format_duration function."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (30, "30s"),
            (60, "1m"),
            (90, "1m 30s"),
            (3600, "1h"),
            (3660, "1h 1m"),
            (7200, "2h"),
        ],
    )
    def test_formats_duration(self, seconds: int, expected: str) -> None:
        result = format_duration(seconds)
        assert result == expected


class TestHookIntegration:
    """Integration tests for the hook script."""

    def test_allows_empty_input(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "approve"

    def test_allows_normal_stop(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps({"session_id": "test", "stop_reason": "end_turn"}),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "approve"

    def test_detects_rate_limit_and_waits(self) -> None:
        """Test that the hook detects rate limits and starts waiting (will timeout)."""
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, str(HOOK_SCRIPT)],
                input=json.dumps({"message": "Usage limit reached. Your limit will reset at 7pm"}),
                capture_output=True,
                text=True,
                timeout=2,  # Short timeout - should fail because hook is waiting
            )


class TestTerminalOutputDetection:
    """Tests for terminal output file detection."""

    def test_returns_none_when_file_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None when output file doesn't exist."""
        monkeypatch.setenv("CC_OUTPUT_FILE", str(tmp_path / "nonexistent.log"))
        result = check_terminal_output()
        assert result is None

    def test_detects_rate_limit_in_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect rate limit message in terminal output."""
        output_file = tmp_path / "session_output.log"
        output_file.write_text(
            "Some output...\n"
            "Claude usage limit reached. Your limit will reset at 7pm (America/Chicago).\n"
            "More output..."
        )
        monkeypatch.setenv("CC_OUTPUT_FILE", str(output_file))

        result = check_terminal_output()
        assert result is not None
        assert "reset_time" in result
        assert result["reset_time"].hour == 19

    def test_ignores_output_without_rate_limit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None when output has no rate limit message."""
        output_file = tmp_path / "session_output.log"
        output_file.write_text("Normal output without any rate limit messages")
        monkeypatch.setenv("CC_OUTPUT_FILE", str(output_file))

        result = check_terminal_output()
        assert result is None

    def test_handles_ansi_escape_codes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect rate limit even with ANSI escape codes."""
        output_file = tmp_path / "session_output.log"
        # Simulate terminal output with escape codes
        output_file.write_text(
            "\x1b[32m✓\x1b[0m Some task done\n"
            "\x1b[31mClaude usage limit reached.\x1b[0m Your limit will reset at 3pm.\n"
        )
        monkeypatch.setenv("CC_OUTPUT_FILE", str(output_file))

        result = check_terminal_output()
        assert result is not None
        assert "reset_time" in result
        assert result["reset_time"].hour == 15
