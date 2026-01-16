"""Claude Code hook that waits for rate limits to reset and continues automatically."""

from cc_wait.hook import main
from cc_wait.schema import (
    VALID_DECISIONS,
    VALID_FIELDS,
    StopHookOutputError,
    assert_valid_stop_hook_output,
    create_approve_output,
    create_block_output,
    validate_stop_hook_output,
)

__all__ = [
    "main",
    "VALID_DECISIONS",
    "VALID_FIELDS",
    "StopHookOutputError",
    "assert_valid_stop_hook_output",
    "create_approve_output",
    "create_block_output",
    "validate_stop_hook_output",
]
