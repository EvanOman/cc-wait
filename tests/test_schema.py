"""Tests for Stop hook output schema validation."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from cc_wait.schema import (
    VALID_DECISIONS,
    VALID_FIELDS,
    StopHookOutputError,
    assert_valid_stop_hook_output,
    create_approve_output,
    create_block_output,
    validate_stop_hook_output,
)

HOOK_SCRIPT = Path(__file__).parent.parent / "src" / "cc_wait" / "hook.py"


class TestSchemaConstants:
    """Test schema constants are correctly defined."""

    def test_valid_decisions_contains_approve(self) -> None:
        assert "approve" in VALID_DECISIONS

    def test_valid_decisions_contains_block(self) -> None:
        assert "block" in VALID_DECISIONS

    def test_valid_decisions_does_not_contain_allow(self) -> None:
        """Ensure we don't accidentally use 'allow' which is invalid."""
        assert "allow" not in VALID_DECISIONS

    def test_valid_fields_contains_required_fields(self) -> None:
        required = {
            "decision",
            "reason",
            "continue",
            "stopReason",
            "suppressOutput",
            "systemMessage",
        }
        assert required.issubset(VALID_FIELDS)


class TestValidateStopHookOutput:
    """Test the validate_stop_hook_output function."""

    def test_valid_approve_output(self) -> None:
        output = {"decision": "approve"}
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_valid_block_output_with_reason(self) -> None:
        output = {"decision": "block", "reason": "continue"}
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_valid_empty_output(self) -> None:
        """Empty output is valid (allows stop by default)."""
        output: dict[str, str] = {}
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_valid_continue_field(self) -> None:
        output = {"continue": True}
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_invalid_decision_allow(self) -> None:
        """'allow' is NOT a valid decision value - must use 'approve'."""
        output = {"decision": "allow"}
        errors = validate_stop_hook_output(output)
        assert any("allow" in e and "Invalid decision" in e for e in errors)

    def test_invalid_decision_deny(self) -> None:
        output = {"decision": "deny"}
        errors = validate_stop_hook_output(output)
        assert any("Invalid decision" in e for e in errors)

    def test_invalid_unknown_field(self) -> None:
        output = {"decision": "approve", "unknownField": "value"}
        errors = validate_stop_hook_output(output)
        assert any("Unknown field" in e for e in errors)

    def test_invalid_decision_type(self) -> None:
        output: dict[str, Any] = {"decision": 123}
        errors = validate_stop_hook_output(output)
        assert any("must be str" in e for e in errors)

    def test_invalid_continue_type(self) -> None:
        output: dict[str, Any] = {"continue": "true"}
        errors = validate_stop_hook_output(output)
        assert any("must be bool" in e for e in errors)

    def test_block_without_reason_warns(self) -> None:
        output = {"decision": "block"}
        errors = validate_stop_hook_output(output)
        assert any("reason" in e for e in errors)


class TestAssertValidStopHookOutput:
    """Test the assert_valid_stop_hook_output function."""

    def test_valid_output_does_not_raise(self) -> None:
        output = {"decision": "approve"}
        assert_valid_stop_hook_output(output)  # Should not raise

    def test_invalid_output_raises(self) -> None:
        output = {"decision": "invalid"}
        with pytest.raises(StopHookOutputError):
            assert_valid_stop_hook_output(output)


class TestCreateApproveOutput:
    """Test the create_approve_output helper."""

    def test_creates_valid_output(self) -> None:
        output = create_approve_output()
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_output_has_correct_decision(self) -> None:
        output = create_approve_output()
        assert output["decision"] == "approve"

    def test_output_is_json_serializable(self) -> None:
        output = create_approve_output()
        json_str = json.dumps(output)
        assert json_str == '{"decision": "approve"}'


class TestCreateBlockOutput:
    """Test the create_block_output helper."""

    def test_creates_valid_output(self) -> None:
        output = create_block_output("test reason")
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_output_has_correct_decision(self) -> None:
        output = create_block_output("test")
        assert output["decision"] == "block"

    def test_output_has_reason(self) -> None:
        output = create_block_output("my reason")
        assert output["reason"] == "my reason"

    def test_output_is_json_serializable(self) -> None:
        output = create_block_output("continue")
        json_str = json.dumps(output)
        assert json_str == '{"decision": "block", "reason": "continue"}'


class TestHookOutputConformsToSchema:
    """Integration tests verifying actual hook output conforms to schema."""

    def test_empty_input_produces_valid_output(self) -> None:
        """When no rate limit, hook should output valid 'approve' response."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

        output = json.loads(result.stdout)
        errors = validate_stop_hook_output(output)
        assert errors == [], f"Schema validation errors: {errors}"
        assert output["decision"] == "approve"

    def test_normal_stop_produces_valid_output(self) -> None:
        """Normal stop (no rate limit) should produce valid output."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps({"session_id": "test", "stop_reason": "end_turn"}),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

        output = json.loads(result.stdout)
        errors = validate_stop_hook_output(output)
        assert errors == [], f"Schema validation errors: {errors}"

    def test_output_contains_only_json(self) -> None:
        """Stdout should contain ONLY the JSON output, nothing else."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )
        stdout = result.stdout.strip()

        # Should be valid JSON
        output = json.loads(stdout)

        # Should be a dict
        assert isinstance(output, dict)

        # Re-serializing should match (no extra whitespace/content)
        assert json.loads(stdout) == output

    def test_status_messages_go_to_stderr_not_stdout(self) -> None:
        """All status messages should go to stderr, not stdout."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Stdout should be pure JSON
        stdout_lines = result.stdout.strip().split("\n")
        assert len(stdout_lines) == 1  # Only one line of JSON

        # That line should be valid JSON
        json.loads(stdout_lines[0])
