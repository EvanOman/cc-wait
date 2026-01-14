#!/bin/bash
# Install cc-wait hook into Claude Code system settings

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_PATH="$SCRIPT_DIR/src/cc_wait/hook.py"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "Installing cc-wait hook..."

# Ensure .claude directory exists
mkdir -p "$HOME/.claude"

# Create or update settings.json
if [ -f "$SETTINGS_FILE" ]; then
    # Check if file has content
    if [ -s "$SETTINGS_FILE" ]; then
        # Use Python to merge the hook into existing settings
        python3 << EOF
import json

settings_file = "$SETTINGS_FILE"
hook_path = "$HOOK_PATH"

with open(settings_file, 'r') as f:
    settings = json.load(f)

# Ensure hooks structure exists
if 'hooks' not in settings:
    settings['hooks'] = {}

if 'Stop' not in settings['hooks']:
    settings['hooks']['Stop'] = []

# Check if our hook is already installed
hook_command = f'python3 "{hook_path}"'
already_installed = False

for matcher in settings['hooks']['Stop']:
    for hook in matcher.get('hooks', []):
        if 'cc_wait' in hook.get('command', '') or 'cc-wait' in hook.get('command', ''):
            # Update existing hook
            hook['command'] = hook_command
            hook['timeout'] = 21600
            already_installed = True
            print(f"Updated existing cc-wait hook")
            break

if not already_installed:
    # Add new hook
    settings['hooks']['Stop'].append({
        'hooks': [{
            'type': 'command',
            'command': hook_command,
            'timeout': 21600
        }]
    })
    print(f"Added cc-wait hook")

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print(f"Settings saved to {settings_file}")
EOF
    else
        # Empty file, create new settings
        cat > "$SETTINGS_FILE" << EOF
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOOK_PATH\"",
            "timeout": 21600
          }
        ]
      }
    ]
  }
}
EOF
        echo "Created new settings file"
    fi
else
    # No settings file, create new one
    cat > "$SETTINGS_FILE" << EOF
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOOK_PATH\"",
            "timeout": 21600
          }
        ]
      }
    ]
  }
}
EOF
    echo "Created new settings file"
fi

echo ""
echo "cc-wait installed successfully!"
echo "The hook will automatically wait when you hit rate limits."
echo ""
echo "To enable debug logging: export CC_WAIT_DEBUG=1"
