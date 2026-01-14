#!/bin/bash
# Uninstall cc-wait hook from Claude Code system settings

set -e

SETTINGS_FILE="$HOME/.claude/settings.json"

echo "Uninstalling cc-wait hook..."

if [ ! -f "$SETTINGS_FILE" ]; then
    echo "No settings file found at $SETTINGS_FILE"
    exit 0
fi

python3 << EOF
import json

settings_file = "$SETTINGS_FILE"

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'hooks' not in settings or 'Stop' not in settings['hooks']:
    print("No Stop hooks found")
    exit(0)

# Filter out cc-wait hooks
original_count = len(settings['hooks']['Stop'])
settings['hooks']['Stop'] = [
    matcher for matcher in settings['hooks']['Stop']
    if not any(
        'cc_wait' in hook.get('command', '') or 'cc-wait' in hook.get('command', '')
        for hook in matcher.get('hooks', [])
    )
]

removed = original_count - len(settings['hooks']['Stop'])

if removed > 0:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
    print(f"Removed {removed} cc-wait hook(s)")
else:
    print("cc-wait hook not found in settings")
EOF

echo "cc-wait uninstalled successfully!"
