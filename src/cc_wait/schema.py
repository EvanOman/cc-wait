"""
Claude Code Stop hook output schema definition and validation.

This schema is extracted from Claude Code's actual Zod schema in cli.js:

```typescript
z.object({
  continue: z.boolean().optional(),
  suppressOutput: z.boolean().optional(),
  stopReason: z.string().optional(),
  decision: z.enum(["approve", "block"]).optional(),
  reason: z.string().optional(),
  systemMessage: z.string().optional(),
  hookSpecificOutput: z.union([...]).optional()
})
```

For Stop hooks specifically, only these fields are relevant:
- decision: "approve" | "block"
- reason: string (explanation for the decision)
- continue: boolean (alternative to decision)
- stopReason: string (message when continue is false)
- suppressOutput: boolean
- systemMessage: string
"""

from __future__ import annotations

import json
from typing import Any, Literal

# JSON Schema for Claude Code hook output (extracted from cli.js Zod schema)
# This is the authoritative schema that Claude Code validates against
HOOK_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "continue": {
            "type": "boolean",
            "description": "Whether Claude should continue after hook (default: true)",
        },
        "suppressOutput": {
            "type": "boolean",
            "description": "Hide stdout from transcript (default: false)",
        },
        "stopReason": {
            "type": "string",
            "description": "Message shown when continue is false",
        },
        "decision": {
            "type": "string",
            "enum": ["approve", "block"],
            "description": "Decision for the hook",
        },
        "reason": {
            "type": "string",
            "description": "Explanation for the decision",
        },
        "systemMessage": {
            "type": "string",
            "description": "Warning message shown to the user",
        },
        "hookSpecificOutput": {
            "type": "object",
            "description": "Hook-specific output (varies by hook type)",
        },
    },
}

# Valid values for the decision field (from z.enum(["approve", "block"]))
VALID_DECISIONS: frozenset[str] = frozenset(["approve", "block"])

# All valid top-level fields for hook output
VALID_FIELDS: frozenset[str] = frozenset(HOOK_OUTPUT_JSON_SCHEMA["properties"].keys())

# Field type mapping for validation
FIELD_TYPES: dict[str, type] = {
    "continue": bool,
    "suppressOutput": bool,
    "stopReason": str,
    "decision": str,
    "reason": str,
    "systemMessage": str,
    "hookSpecificOutput": dict,
}


class StopHookOutputError(Exception):
    """Raised when Stop hook output doesn't conform to schema."""

    pass


def validate_stop_hook_output(output: dict[str, Any]) -> list[str]:
    """
    Validate a Stop hook output dictionary against the Claude Code schema.

    This validates against the exact schema extracted from Claude Code's cli.js.
    Returns a list of validation errors (empty if valid).
    """
    errors: list[str] = []

    if not isinstance(output, dict):
        errors.append(f"Output must be a dict, got {type(output).__name__}")
        return errors

    # Check for unknown fields (additionalProperties: false in schema)
    for field in output:
        if field not in VALID_FIELDS:
            errors.append(f"Unknown field '{field}'. Valid fields: {sorted(VALID_FIELDS)}")

    # Check field types match schema
    for field, value in output.items():
        if field not in FIELD_TYPES:
            continue  # Already reported as unknown field

        expected_type = FIELD_TYPES[field]
        if not isinstance(value, expected_type):
            errors.append(
                f"Field '{field}' must be {expected_type.__name__}, got {type(value).__name__}"
            )

    # Check decision enum values (from z.enum(["approve", "block"]))
    if "decision" in output:
        decision = output["decision"]
        if isinstance(decision, str) and decision not in VALID_DECISIONS:
            errors.append(
                f"Invalid decision '{decision}'. "
                f"Must be one of: {sorted(VALID_DECISIONS)} (per z.enum in Claude Code)"
            )

    return errors


def validate_stop_hook_output_strict(output: dict[str, Any]) -> list[str]:
    """
    Strict validation that also checks for best practices.

    In addition to schema validation, checks:
    - reason is provided when decision is "block"
    """
    errors = validate_stop_hook_output(output)

    # Best practice: provide reason when blocking
    if output.get("decision") == "block" and "reason" not in output:
        errors.append("Best practice: 'reason' should be provided when decision is 'block'")

    return errors


def assert_valid_stop_hook_output(output: dict[str, Any], strict: bool = False) -> None:
    """
    Assert that a Stop hook output is valid, raising StopHookOutputError if not.

    Args:
        output: The hook output dict to validate
        strict: If True, also check best practices (not just schema)
    """
    if strict:
        errors = validate_stop_hook_output_strict(output)
    else:
        errors = validate_stop_hook_output(output)

    if errors:
        raise StopHookOutputError(f"Invalid Stop hook output: {'; '.join(errors)}")


def create_approve_output() -> dict[str, Literal["approve"]]:
    """
    Create a valid 'approve' (allow stop) output.

    This output tells Claude Code to allow the stop to proceed normally.
    """
    return {"decision": "approve"}


def create_block_output(reason: str) -> dict[str, str]:
    """
    Create a valid 'block' (prevent stop) output with reason.

    This output tells Claude Code to block the stop and continue working.
    The reason is shown to Claude to explain why it should continue.
    """
    return {"decision": "block", "reason": reason}


def get_schema_as_json() -> str:
    """Return the JSON Schema as a formatted JSON string."""
    return json.dumps(HOOK_OUTPUT_JSON_SCHEMA, indent=2)
