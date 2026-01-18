# cc-wait

Automatically continue Claude Code sessions after rate limits reset.

## How It Works

When you hit Claude Code's usage limits, this daemon:

1. Monitors the OAuth usage API to detect rate limits (utilization = 100%)
2. Scans your tmux panes to find sessions showing the rate limit message
3. Waits until the reset time
4. Sends "continue" to only the affected sessions

```
$ cc-wait status
5-hour:  100% ██████████  resets in 1h 32m
7-day:    45% ████▌░░░░░  resets in 67h

$ cc-wait daemon
[19:00] Rate limit detected. Reset at 20:32.
[19:00] Found 2 blocked sessions: %33, %48
[20:32] Rate limit reset. Continuing sessions...
[20:32] Sent 'continue' to %33 (agents)
[20:32] Sent 'continue' to %48 (agents)
```

## Requirements

- **tmux**: Sessions must run in tmux for auto-continue to work
- **Claude Code**: With OAuth authentication (Pro/Max subscription)

## Installation

```bash
# Run directly with uvx (no install needed)
uvx --from git+https://github.com/EvanOman/cc-wait cc-wait status

# Or install locally
git clone https://github.com/EvanOman/cc-wait.git
cd cc-wait
uv sync
```

## Usage

### Check current rate limit status

```bash
cc-wait status
```

### Run the daemon (foreground)

```bash
cc-wait daemon
```

### Run as a systemd user service

```bash
# Install the service
mkdir -p ~/.config/systemd/user/
cat > ~/.config/systemd/user/cc-wait.service << 'EOF'
[Unit]
Description=Claude Code Rate Limit Monitor
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/uvx --from git+https://github.com/EvanOman/cc-wait cc-wait daemon
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now cc-wait

# Check status
systemctl --user status cc-wait
journalctl --user -u cc-wait -f
```

### Detect blocked sessions (one-shot)

```bash
cc-wait detect
```

## Configuration

Environment variables:

- `CC_WAIT_POLL_INTERVAL`: Seconds between API polls (default: 60)
- `CC_WAIT_DEBUG`: Set to `1` for verbose logging

## How Detection Works

The daemon avoids false positives by requiring two conditions:

1. **Global rate limit**: OAuth API shows `utilization >= 100%`
2. **Session blocked**: tmux pane content contains "usage limit" or "limit will reset"

Only sessions that explicitly show the rate limit message receive "continue".

## Development

```bash
# Install dev dependencies
uv sync

# Run checks
just fc

# Run tests
just test
```

## History

This project originally tried a Stop hook approach, which failed because Claude Code doesn't pass consumer-level rate limit info to hooks. See [HISTORY.md](HISTORY.md) for details.

## License

MIT
