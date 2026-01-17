#!/bin/bash
# claude-wait: Run Claude Code with rate limit detection
#
# Usage: Source this in your .bashrc/.zshrc:
#   source /path/to/wrapper.sh
#
# Then use `claude-wait` instead of `claude` when you want auto-wait on rate limits.

CC_OUTPUT_FILE="${CC_OUTPUT_FILE:-$HOME/.claude/session_output.log}"

claude-wait() {
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

    # Run claude with output capture using script
    # -q = quiet, -e = return exit status of child
    if command -v script &>/dev/null; then
        script -q -e -c "\"$real_claude\" $*" "$CC_OUTPUT_FILE"
        return $?
    else
        # Fallback: just capture stderr (may miss some output)
        "$real_claude" "$@" 2> >(tee -a "$CC_OUTPUT_FILE" >&2)
        return $?
    fi
}

# Export for subshells
export -f claude-wait 2>/dev/null || true
export CC_OUTPUT_FILE
