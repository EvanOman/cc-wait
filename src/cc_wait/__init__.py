"""Claude Code hook that waits for rate limits to reset and continues automatically."""

from cc_wait.hook import main
from cc_wait.schema import (
    HOOK_OUTPUT_JSON_SCHEMA,
    VALID_DECISIONS,
    VALID_FIELDS,
    StopHookOutputError,
    assert_valid_stop_hook_output,
    create_approve_output,
    create_block_output,
    get_schema_as_json,
    validate_stop_hook_output,
    validate_stop_hook_output_strict,
)

__all__ = [
    "main",
    "HOOK_OUTPUT_JSON_SCHEMA",
    "VALID_DECISIONS",
    "VALID_FIELDS",
    "StopHookOutputError",
    "assert_valid_stop_hook_output",
    "create_approve_output",
    "create_block_output",
    "get_schema_as_json",
    "validate_stop_hook_output",
    "validate_stop_hook_output_strict",
]
