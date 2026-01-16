"""Tests for Stop hook output schema validation.

These tests validate that our hook output conforms to the exact schema
extracted from Claude Code's cli.js Zod definitions.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator, ValidationError, validate

from cc_wait.schema import (
    HOOK_OUTPUT_JSON_SCHEMA,
    VALID_DECISIONS,
    VALID_FIELDS,
    StopHookOutputError,
    assert_valid_stop_hook_output,
    create_approve_output,
    create_block_output,
    validate_stop_hook_output,
)

HOOK_SCRIPT = Path(__file__).parent.parent / "src" / "cc_wait" / "hook.py"


class TestJsonSchemaIsValid:
    """Verify our JSON Schema itself is valid."""

    def test_schema_is_valid_draft7(self) -> None:
        """Our schema should be a valid JSON Schema Draft 7."""
        Draft7Validator.check_schema(HOOK_OUTPUT_JSON_SCHEMA)

    def test_schema_has_required_properties(self) -> None:
        """Schema should define all expected properties."""
        props = HOOK_OUTPUT_JSON_SCHEMA["properties"]
        expected = {
            "continue",
            "suppressOutput",
            "stopReason",
            "decision",
            "reason",
            "systemMessage",
        }
        assert expected.issubset(set(props.keys()))

    def test_decision_enum_matches_claude_code(self) -> None:
        """Decision enum should match exactly what Claude Code expects."""
        decision_schema = HOOK_OUTPUT_JSON_SCHEMA["properties"]["decision"]
        assert decision_schema["enum"] == ["approve", "block"]


class TestJsonSchemaValidation:
    """Test validation using the JSON Schema directly."""

    def test_approve_output_passes_jsonschema(self) -> None:
        """Approve output should pass JSON Schema validation."""
        output = {"decision": "approve"}
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)  # Raises if invalid

    def test_block_output_passes_jsonschema(self) -> None:
        """Block output with reason should pass JSON Schema validation."""
        output = {"decision": "block", "reason": "continue"}
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_empty_output_passes_jsonschema(self) -> None:
        """Empty output should pass (all fields optional)."""
        output: dict[str, Any] = {}
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_all_valid_fields_pass_jsonschema(self) -> None:
        """Output with all valid fields should pass."""
        output = {
            "continue": True,
            "suppressOutput": False,
            "stopReason": "test",
            "decision": "approve",
            "reason": "test reason",
            "systemMessage": "test message",
        }
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_invalid_decision_fails_jsonschema(self) -> None:
        """Invalid decision value should fail JSON Schema validation."""
        output = {"decision": "allow"}  # 'allow' is NOT valid
        with pytest.raises(ValidationError) as exc_info:
            validate(output, HOOK_OUTPUT_JSON_SCHEMA)
        assert "allow" in str(exc_info.value)

    def test_unknown_field_fails_jsonschema(self) -> None:
        """Unknown fields should fail (additionalProperties: false)."""
        output = {"decision": "approve", "unknownField": "value"}
        with pytest.raises(ValidationError):
            validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_wrong_type_fails_jsonschema(self) -> None:
        """Wrong field types should fail."""
        output = {"continue": "true"}  # Should be boolean
        with pytest.raises(ValidationError):
            validate(output, HOOK_OUTPUT_JSON_SCHEMA)


class TestSchemaConstants:
    """Test schema constants are correctly defined."""

    def test_valid_decisions_matches_schema(self) -> None:
        """VALID_DECISIONS should match the JSON Schema enum."""
        schema_enum = set(HOOK_OUTPUT_JSON_SCHEMA["properties"]["decision"]["enum"])
        assert VALID_DECISIONS == schema_enum

    def test_valid_fields_matches_schema(self) -> None:
        """VALID_FIELDS should match JSON Schema properties."""
        schema_props = set(HOOK_OUTPUT_JSON_SCHEMA["properties"].keys())
        assert VALID_FIELDS == schema_props

    def test_valid_decisions_does_not_contain_allow(self) -> None:
        """Ensure we don't accidentally use 'allow' which is invalid."""
        assert "allow" not in VALID_DECISIONS


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
        output: dict[str, Any] = {}
        errors = validate_stop_hook_output(output)
        assert errors == []

    def test_invalid_decision_allow(self) -> None:
        """'allow' is NOT a valid decision value - must use 'approve'."""
        output = {"decision": "allow"}
        errors = validate_stop_hook_output(output)
        assert any("allow" in e for e in errors)

    def test_invalid_unknown_field(self) -> None:
        output = {"decision": "approve", "unknownField": "value"}
        errors = validate_stop_hook_output(output)
        assert any("Unknown field" in e for e in errors)

    def test_invalid_decision_type(self) -> None:
        output: dict[str, Any] = {"decision": 123}
        errors = validate_stop_hook_output(output)
        assert any("must be str" in e for e in errors)


class TestAssertValidStopHookOutput:
    """Test the assert_valid_stop_hook_output function."""

    def test_valid_output_does_not_raise(self) -> None:
        output = {"decision": "approve"}
        assert_valid_stop_hook_output(output)

    def test_invalid_output_raises(self) -> None:
        output = {"decision": "invalid"}
        with pytest.raises(StopHookOutputError):
            assert_valid_stop_hook_output(output)

    def test_strict_mode_warns_on_block_without_reason(self) -> None:
        output = {"decision": "block"}
        # Non-strict should pass (it's valid per schema)
        assert_valid_stop_hook_output(output, strict=False)
        # Strict should fail (best practice violation)
        with pytest.raises(StopHookOutputError):
            assert_valid_stop_hook_output(output, strict=True)


class TestCreateApproveOutput:
    """Test the create_approve_output helper."""

    def test_passes_jsonschema_validation(self) -> None:
        output = create_approve_output()
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_output_has_correct_decision(self) -> None:
        output = create_approve_output()
        assert output["decision"] == "approve"

    def test_output_is_json_serializable(self) -> None:
        output = create_approve_output()
        json_str = json.dumps(output)
        assert json_str == '{"decision": "approve"}'


class TestCreateBlockOutput:
    """Test the create_block_output helper."""

    def test_passes_jsonschema_validation(self) -> None:
        output = create_block_output("test reason")
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_output_has_correct_decision(self) -> None:
        output = create_block_output("test")
        assert output["decision"] == "block"

    def test_output_has_reason(self) -> None:
        output = create_block_output("my reason")
        assert output["reason"] == "my reason"


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

        # Validate against JSON Schema
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

        # Also check with our validator
        errors = validate_stop_hook_output(output)
        assert errors == [], f"Schema validation errors: {errors}"

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
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

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
        assert isinstance(output, dict)

        # Should pass schema validation
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)

    def test_status_messages_go_to_stderr_not_stdout(self) -> None:
        """All status messages should go to stderr, not stdout."""
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Stdout should be pure JSON (one line)
        stdout_lines = result.stdout.strip().split("\n")
        assert len(stdout_lines) == 1

        # That line should pass JSON Schema validation
        output = json.loads(stdout_lines[0])
        validate(output, HOOK_OUTPUT_JSON_SCHEMA)
