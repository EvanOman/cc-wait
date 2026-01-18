"""Tests for OAuth module."""

from datetime import UTC, datetime, timedelta

from cc_wait.oauth import UsageStatus, UsageWindow, _parse_datetime


class TestParseDateTime:
    """Tests for datetime parsing."""

    def test_parses_iso_with_z(self) -> None:
        result = _parse_datetime("2026-01-17T22:00:00Z")
        assert result is not None
        assert result.hour == 22

    def test_parses_iso_with_offset(self) -> None:
        result = _parse_datetime("2026-01-17T22:00:00+00:00")
        assert result is not None
        assert result.hour == 22

    def test_returns_none_for_invalid(self) -> None:
        result = _parse_datetime("not a date")
        assert result is None

    def test_returns_none_for_none(self) -> None:
        result = _parse_datetime(None)
        assert result is None


class TestUsageWindow:
    """Tests for UsageWindow."""

    def test_is_limited_at_100(self) -> None:
        window = UsageWindow(utilization=100.0, resets_at=None)
        assert window.is_limited is True

    def test_is_limited_over_100(self) -> None:
        window = UsageWindow(utilization=105.0, resets_at=None)
        assert window.is_limited is True

    def test_not_limited_under_100(self) -> None:
        window = UsageWindow(utilization=99.9, resets_at=None)
        assert window.is_limited is False

    def test_resets_in_seconds(self) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        window = UsageWindow(utilization=50.0, resets_at=future)
        seconds = window.resets_in_seconds
        assert seconds is not None
        assert 3500 <= seconds <= 3700  # ~1 hour

    def test_resets_in_seconds_none_when_no_reset_time(self) -> None:
        window = UsageWindow(utilization=50.0, resets_at=None)
        assert window.resets_in_seconds is None


class TestUsageStatus:
    """Tests for UsageStatus."""

    def test_is_limited_when_five_hour_limited(self) -> None:
        status = UsageStatus(
            five_hour=UsageWindow(utilization=100.0, resets_at=None),
            seven_day=UsageWindow(utilization=50.0, resets_at=None),
        )
        assert status.is_limited is True

    def test_is_limited_when_seven_day_limited(self) -> None:
        status = UsageStatus(
            five_hour=UsageWindow(utilization=50.0, resets_at=None),
            seven_day=UsageWindow(utilization=100.0, resets_at=None),
        )
        assert status.is_limited is True

    def test_not_limited_when_neither_limited(self) -> None:
        status = UsageStatus(
            five_hour=UsageWindow(utilization=50.0, resets_at=None),
            seven_day=UsageWindow(utilization=50.0, resets_at=None),
        )
        assert status.is_limited is False

    def test_next_reset_returns_earliest(self) -> None:
        early = datetime.now(UTC) + timedelta(hours=1)
        late = datetime.now(UTC) + timedelta(hours=5)

        status = UsageStatus(
            five_hour=UsageWindow(utilization=100.0, resets_at=early),
            seven_day=UsageWindow(utilization=100.0, resets_at=late),
        )
        assert status.next_reset == early
