# OpenClaw Git-Safe Bundle

Generated: 2026-02-28 08:48:52 UTC

## What Is Included

- `config/openclaw.json` (sanitized)
- `config/extensions/` (if present)
- `config/skills/` (if present)
- `config/workspace-clinic/` (if present)
- `workspace/` (copied from current mounted workspace)
- `deployment/docker-compose.reference.yml`
- `deployment/.env.sanitized` (if local `.env` exists)

Source paths:
- Resolved automatically during export from Docker Compose / env.
- Absolute local paths are intentionally omitted from this bundle for safe sharing.

Secret scan status: **clean**

## Restore On Another Host

1. Copy this bundle into your shared repository (or unpack it on target host).
2. Choose target state paths (example):
   - `OPENCLAW_CONFIG_DIR=~/.openclaw`
   - `OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace`
3. Restore files:

```bash
mkdir -p "$OPENCLAW_CONFIG_DIR" "$OPENCLAW_WORKSPACE_DIR"
rsync -a ./config/openclaw.json "$OPENCLAW_CONFIG_DIR/openclaw.json"
rsync -a ./config/extensions/ "$OPENCLAW_CONFIG_DIR/extensions/" 2>/dev/null || true
rsync -a ./config/skills/ "$OPENCLAW_CONFIG_DIR/skills/" 2>/dev/null || true
rsync -a ./workspace/ "$OPENCLAW_WORKSPACE_DIR/"
```

4. Fill real secrets manually:
   - `openclaw.json` secret fields marked as `__REDACTED__`
   - `deployment/.env.sanitized` (if used)
5. Start/restart OpenClaw in Docker:

```bash
cd /path/to/openclaw-repo
./docker-setup.sh
docker compose restart openclaw-gateway
```

## Notes

- This bundle intentionally excludes credentials/session/runtime artifacts (`credentials/`, `agents/`, `telegram/`, logs, queues).
- If `potential-secrets-report.txt` exists, review it before committing to git.
