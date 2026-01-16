"""
Claude Code Stop hook output schema definition and validation.

Based on the Claude Code hooks documentation, the Stop hook output schema is:
- decision: "approve" | "block" (optional) - controls whether Claude can stop
- reason: string (optional) - explanation when blocking
- continue: boolean (optional) - alternative to decision, takes precedence
- stopReason: string (optional) - message shown when continue is false
- suppressOutput: boolean (optional) - hide stdout from transcript
- systemMessage: string (optional) - warning message shown to user
"""

from __future__ import annotations

from typing import Any, Literal

# Valid values for the decision field
VALID_DECISIONS: set[str] = {"approve", "block"}

# All valid top-level fields for Stop hook output
VALID_FIELDS: set[str] = {
    "decision",
    "reason",
    "continue",
    "stopReason",
    "suppressOutput",
    "systemMessage",
}

# Field type definitions
FIELD_TYPES: dict[str, type] = {
    "decision": str,
    "reason": str,
    "continue": bool,
    "stopReason": str,
    "suppressOutput": bool,
    "systemMessage": str,
}


class StopHookOutputError(Exception):
    """Raised when Stop hook output doesn't conform to schema."""

    pass


def validate_stop_hook_output(output: dict[str, Any]) -> list[str]:
    """
    Validate a Stop hook output dictionary against the Claude Code schema.

    Returns a list of validation errors (empty if valid).
    """
    errors: list[str] = []

    # Check for unknown fields
    for field in output:
        if field not in VALID_FIELDS:
            errors.append(f"Unknown field '{field}'. Valid fields: {sorted(VALID_FIELDS)}")

    # Check field types
    for field, expected_type in FIELD_TYPES.items():
        if field in output:
            value = output[field]
            if not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field}' must be {expected_type.__name__}, got {type(value).__name__}"
                )

    # Check decision values
    if "decision" in output:
        decision = output["decision"]
        if isinstance(decision, str) and decision not in VALID_DECISIONS:
            errors.append(
                f"Invalid decision '{decision}'. Must be one of: {sorted(VALID_DECISIONS)}"
            )

    # Check logical consistency
    if output.get("decision") == "block" and "reason" not in output:
        errors.append("Field 'reason' is recommended when decision is 'block'")

    return errors


def assert_valid_stop_hook_output(output: dict[str, Any]) -> None:
    """
    Assert that a Stop hook output is valid, raising StopHookOutputError if not.
    """
    errors = validate_stop_hook_output(output)
    if errors:
        raise StopHookOutputError(f"Invalid Stop hook output: {'; '.join(errors)}")


def create_approve_output() -> dict[str, Literal["approve"]]:
    """Create a valid 'approve' (allow stop) output."""
    return {"decision": "approve"}


def create_block_output(reason: str) -> dict[str, str]:
    """Create a valid 'block' (prevent stop) output with reason."""
    return {"decision": "block", "reason": reason}
