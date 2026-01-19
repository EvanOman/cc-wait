# cc-wait Development Notes

## Local Deployment

After making local code changes, run:

```bash
just redeploy
```

This clears Python bytecode cache and restarts the systemd service so changes take effect.

## Service Details

- **Service**: `cc-wait-dashboard` (systemd user service)
- **Port**: 18800
- **URL**: https://omachine.werewolf-universe.ts.net/cc-wait/
- **Logs**: `journalctl --user -u cc-wait-dashboard -f`

## Quick Commands

```bash
just fc          # Format, lint, type-check, test (run before commits)
just redeploy    # Deploy local changes
just test        # Run tests only
```
