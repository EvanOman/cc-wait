#!/bin/bash
# Claude Code wrapper that captures terminal output for rate limit detection
#
# Usage: Source this in your .bashrc/.zshrc:
#   source /path/to/wrapper.sh
#
# Or install as an alias:
#   alias claude='cc-claude-wrapper'

CC_OUTPUT_FILE="${CC_OUTPUT_FILE:-$HOME/.claude/session_output.log}"

cc-claude-wrapper() {
    local real_claude

    # Find the real claude binary
    if command -v claude &>/dev/null; then
        real_claude=$(command -v claude)
    elif [[ -x "$HOME/.claude/local/claude" ]]; then
        real_claude="$HOME/.claude/local/claude"
    elif [[ -x "/usr/local/bin/claude" ]]; then
        real_claude="/usr/local/bin/claude"
    else
        echo "Error: claude binary not found" >&2
        return 1
    fi

    # Ensure output directory exists
    mkdir -p "$(dirname "$CC_OUTPUT_FILE")"

    # Clear previous output
    : > "$CC_OUTPUT_FILE"

    # Run claude with output capture
    # We use script to capture the full terminal output including escape sequences
    # The -q flag makes it quiet, -e returns the exit status of the child
    if command -v script &>/dev/null; then
        script -q -e -c "$real_claude $*" "$CC_OUTPUT_FILE"
        return $?
    else
        # Fallback: just capture stderr (may miss some output)
        "$real_claude" "$@" 2> >(tee -a "$CC_OUTPUT_FILE" >&2)
        return $?
    fi
}

# Export for subshells
export -f cc-claude-wrapper 2>/dev/null || true
export CC_OUTPUT_FILE
