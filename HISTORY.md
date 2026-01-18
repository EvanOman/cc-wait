# cc-wait: Development History

## The Problem

When Claude Code hits consumer-level rate limits, it displays a message like:

```
Claude usage limit reached. Your limit will reset at 7pm (America/Chicago).
```

The goal: automatically wait until the reset time, then continue the conversation.

## Approach 1: Stop Hook (FAILED)

**Dates:** January 2026

### What We Tried

Claude Code has a "Stop hook" system that runs every time Claude finishes responding. The idea was:

1. Register a Stop hook in `~/.claude/settings.json`
2. When the hook runs, check if we're rate-limited
3. If so, wait until the reset time
4. Return `{"decision": "block", "reason": "continue"}` to resume

### Implementation

```python
# hook.py - Stop hook that checks for rate limits
def main():
    hook_input = json.loads(sys.stdin.read())
    transcript_path = hook_input.get("transcript_path")

    # Check for rate limit in transcript and hook input
    rate_limit_info = find_rate_limit_info(hook_input, transcript_entries)

    if rate_limit_info:
        wait_until_reset(rate_limit_info)
        print(json.dumps({"decision": "block", "reason": "continue"}))
    else:
        print(json.dumps({"decision": "approve"}))
```

### Why It Failed

**The consumer-level rate limit message is NOT passed to hooks.**

When Claude Code hits the consumer rate limit:
- The message "Your limit will reset at Xpm" is displayed in the **terminal UI**
- It is **NOT** written to the transcript JSONL file
- It is **NOT** included in the Stop hook's stdin input

The Stop hook only receives:
```json
{
  "session_id": "...",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "cwd": "/path/to/project",
  "stop_hook_active": false
}
```

No rate limit information is provided.

### Workaround Attempted: Terminal Output Capture

We tried capturing terminal output using a wrapper:

```bash
# claude-wait wrapper
claude-wait() {
    script -q -e -c "claude $*" "$HOME/.claude/session_output.log"
}
```

The hook would then read `session_output.log` to find rate limit messages. This worked but:
- Required users to run `claude-wait` instead of `claude`
- Fragile - depends on `script` command behavior
- The wrapper approach felt hacky

### What Would Make Stop Hooks Work

If Anthropic adds rate limit info to hooks in the future, look for:

1. **Hook input changes**: Check if `hook_input` contains fields like:
   - `rate_limited: true`
   - `reset_time: "2026-01-17T19:00:00Z"`
   - `rate_limit_message: "Your limit will reset at 7pm"`

2. **Transcript entries**: Check if rate limit events are logged with type like:
   - `{"type": "system", "subtype": "rate_limit", ...}`
   - `{"type": "rate_limit", "reset_at": "..."}`

3. **New hook event**: A dedicated `RateLimit` hook event (in addition to Stop, PreToolUse, etc.)

If any of these appear, the Stop hook approach becomes viable again. The parsing code for reset times worked correctly - the issue was purely about data availability.

## Approach 2: Background Daemon + tmux (CURRENT)

**Dates:** January 2026 - Present

### Key Insight

Instead of relying on hooks, we can:
1. Monitor the OAuth usage API to detect when rate limits are active
2. Read tmux pane contents to find which sessions show the rate limit message
3. Send "continue" to only those specific panes

### Why This Works

1. **OAuth Usage API**: Claude Code stores credentials at `~/.claude/.credentials.json`. The endpoint `https://api.anthropic.com/api/oauth/usage` returns:
   ```json
   {
     "five_hour": {"utilization": 100.0, "resets_at": "2026-01-17T22:00:00Z"},
     "seven_day": {"utilization": 45.0, "resets_at": "2026-01-20T00:00:00Z"}
   }
   ```

2. **tmux pane content**: We can read what's visible in each terminal:
   ```bash
   tmux capture-pane -t %0 -p | grep "limit will reset"
   ```

3. **Targeted continue**: Only send input to panes that explicitly show the rate limit message - no false positives.

### Architecture

```
┌─────────────────┐     ┌──────────────────┐
│  OAuth API      │────▶│  cc-wait daemon  │
│  (utilization)  │     │                  │
└─────────────────┘     │  - polls usage   │
                        │  - scans panes   │
┌─────────────────┐     │  - sends continue│
│  tmux panes     │◀────│                  │
│  (terminal UI)  │     └──────────────────┘
└─────────────────┘
```

See README.md for current implementation details.

## Lessons Learned

1. **Don't assume data availability**: The hook system looks powerful, but check what data actually flows through it.

2. **Terminal UI vs structured data**: What users see isn't always what's programmatically accessible.

3. **External monitoring > inline hooks**: For consumer-level limits, polling an API is more reliable than trying to intercept internal events.

4. **tmux is your friend**: Being able to read and write to terminal panes enables automation that would otherwise be impossible.
