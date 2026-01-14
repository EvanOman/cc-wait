[![CI](https://github.com/EvanOman/cc-wait/actions/workflows/ci.yml/badge.svg)](https://github.com/EvanOman/cc-wait/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/EvanOman/cc-wait/branch/main/graph/badge.svg)](https://codecov.io/gh/EvanOman/cc-wait)

# cc-wait

A Claude Code hook that automatically waits for rate limits to reset, then continues your session.

## What it does

When you hit Claude Code's usage limits, instead of stopping, this hook:

1. Detects the rate limit message (e.g., "Your limit will reset at 7pm")
2. Parses the actual reset time
3. Waits until that time
4. Automatically continues your conversation

```
⏳ Rate limit reached. Waiting until 19:00 CST (1h 32m)...
⏳ 1h 27m remaining...
✓ Rate limit reset. Continuing...
```

## Installation

```bash
# Clone the repo
git clone https://github.com/EvanOman/cc-wait.git
cd cc-wait

# Run the install script
./install.sh
```

Or manually add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/cc-wait/src/cc_wait/hook.py",
            "timeout": 21600
          }
        ]
      }
    ]
  }
}
```

## How it works

This is a **Stop hook** - it runs every time Claude finishes responding. The hook:

1. Reads the transcript and hook input for rate limit indicators
2. Parses reset times like "7pm", "3:30pm (America/New_York)", "14:00"
3. Calculates wait duration until that exact time
4. Sleeps with progress updates every 5 minutes
5. Returns `{"decision": "block", "reason": "continue"}` to resume

## Configuration

**Debug mode:** Set `CC_WAIT_DEBUG=1` to log to `~/.claude/wait_hook_debug.log`

```bash
export CC_WAIT_DEBUG=1
```

**Timeout:** The default timeout is 6 hours (21600s) to handle maximum wait times.

## Development

```bash
# Install dependencies
just install

# Run all checks (format, lint, type, test)
just fc

# Run tests only
just test
```

## Uninstall

```bash
./uninstall.sh
```

Or manually remove the Stop hook from `~/.claude/settings.json`.

## License

MIT
