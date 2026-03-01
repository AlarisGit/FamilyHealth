#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

OUTPUT_DIR=""
CONFIG_DIR=""
WORKSPACE_DIR=""
FORCE=0

usage() {
  cat <<'EOF'
Export a git-safe OpenClaw bundle from current Docker/OpenClaw state.

Usage:
  scripts/export-openclaw-git-bundle.sh [options]

Options:
  --output <dir>         Output directory (default: ./artifacts/openclaw-share-bundle-<timestamp>)
  --config-dir <dir>     Source OPENCLAW_CONFIG_DIR (default: docker compose config -> env -> ~/.openclaw)
  --workspace-dir <dir>  Source OPENCLAW_WORKSPACE_DIR (default: docker compose config -> env -> <config>/workspace)
  --force                Overwrite output directory if it exists
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --config-dir)
      CONFIG_DIR="${2:-}"
      shift 2
      ;;
    --workspace-dir)
      WORKSPACE_DIR="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    exit 1
  fi
}

require_cmd node
require_cmd rsync
require_cmd rg

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

resolve_mounts_from_compose() {
  local compose_output
  compose_output="$(cd "$ROOT_DIR" && docker compose config 2>/dev/null || true)"
  if [[ -z "$compose_output" ]]; then
    return 0
  fi

  local gateway_block
  gateway_block="$(printf '%s\n' "$compose_output" | awk '
    $0 ~ /^  openclaw-gateway:/ { in_svc=1; print; next }
    in_svc && $0 ~ /^  [^ ]/ { in_svc=0 }
    in_svc { print }
  ')"
  if [[ -z "$gateway_block" ]]; then
    return 0
  fi

  local -a sources=()
  while IFS= read -r line; do
    line="$(trim "$line")"
    if [[ "$line" == source:* ]]; then
      sources+=("$(trim "${line#source:}")")
    fi
  done < <(printf '%s\n' "$gateway_block")

  if [[ ${#sources[@]} -ge 1 && -z "$CONFIG_DIR" ]]; then
    CONFIG_DIR="${sources[0]}"
  fi
  if [[ ${#sources[@]} -ge 2 && -z "$WORKSPACE_DIR" ]]; then
    WORKSPACE_DIR="${sources[1]}"
  fi
}

resolve_mounts_from_compose

if [[ -z "$CONFIG_DIR" ]]; then
  CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-$HOME/.openclaw}"
fi
if [[ -z "$WORKSPACE_DIR" ]]; then
  WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-$CONFIG_DIR/workspace}"
fi

CONFIG_DIR="$(cd "$(dirname "$CONFIG_DIR")" && pwd)/$(basename "$CONFIG_DIR")"
WORKSPACE_DIR="$(cd "$(dirname "$WORKSPACE_DIR")" && pwd)/$(basename "$WORKSPACE_DIR")"

if [[ ! -d "$CONFIG_DIR" ]]; then
  echo "Config directory not found: $CONFIG_DIR" >&2
  exit 1
fi
if [[ ! -d "$WORKSPACE_DIR" ]]; then
  echo "Workspace directory not found: $WORKSPACE_DIR" >&2
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$ROOT_DIR/artifacts/openclaw-share-bundle-$DEFAULT_TIMESTAMP"
fi
mkdir -p "$(dirname "$OUTPUT_DIR")"
OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"

if [[ -e "$OUTPUT_DIR" && $FORCE -ne 1 ]]; then
  echo "Output already exists: $OUTPUT_DIR (use --force to overwrite)" >&2
  exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/config" "$OUTPUT_DIR/workspace" "$OUTPUT_DIR/deployment"

sanitize_json() {
  local src="$1"
  local dst="$2"

  node - "$src" "$dst" <<'NODE'
const fs = require("node:fs");
const [src, dst] = process.argv.slice(2);

const secretKeyRegex =
  /(token|api[_-]?key|secret|password|cookie|session|authorization|bearer|webhook|private[_-]?key|client[_-]?secret)/i;

const secretValueRegex =
  /(^xox[baprs]-)|(^gh[pousr]_[A-Za-z0-9_]{20,}$)|(^sk-[A-Za-z0-9]{20,}$)|(^[0-9]{8,}:[A-Za-z0-9_-]{30,}$)/;

function redactLike(value) {
  if (Array.isArray(value)) {
    return value.map((item) => redactLike(item));
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = redactNode(k, v);
    }
    return out;
  }
  if (typeof value === "string") {
    return "__REDACTED__";
  }
  return value;
}

function redactNode(key, value) {
  if (secretKeyRegex.test(String(key))) {
    return redactLike(value);
  }
  if (typeof value === "string" && secretValueRegex.test(value.trim())) {
    return "__REDACTED__";
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactNode(key, item));
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = redactNode(k, v);
    }
    return out;
  }
  return value;
}

const raw = fs.readFileSync(src, "utf8");
const parsed = JSON.parse(raw);
const sanitized = redactNode("root", parsed);
fs.writeFileSync(dst, `${JSON.stringify(sanitized, null, 2)}\n`, "utf8");
NODE
}

sanitize_env_file() {
  local src="$1"
  local dst="$2"

  node - "$src" "$dst" <<'NODE'
const fs = require("node:fs");
const [src, dst] = process.argv.slice(2);
const secretKeyRegex =
  /(token|api[_-]?key|secret|password|cookie|session|authorization|bearer|private[_-]?key|client[_-]?secret)/i;

const lines = fs.readFileSync(src, "utf8").split(/\r?\n/);
const out = [];
for (const line of lines) {
  if (!line || line.trimStart().startsWith("#") || !line.includes("=")) {
    out.push(line);
    continue;
  }
  const idx = line.indexOf("=");
  const key = line.slice(0, idx).trim();
  const value = line.slice(idx + 1);
  if (secretKeyRegex.test(key)) {
    out.push(`${key}=__REDACTED__`);
  } else {
    out.push(`${key}=${value}`);
  }
}
fs.writeFileSync(dst, `${out.join("\n")}\n`, "utf8");
NODE
}

sanitize_config_tree() {
  local root="$1"
  node - "$root" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");
const [root] = process.argv.slice(2);

const secretKeyRegex =
  /(token|api[_-]?key|secret|password|cookie|session|authorization|bearer|webhook|private[_-]?key|client[_-]?secret)/i;
const secretValueRegex =
  /(xox[baprs]-|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|[0-9]{8,}:[A-Za-z0-9_-]{30,})/;

function redactLike(value) {
  if (Array.isArray(value)) {
    return value.map((item) => redactLike(item));
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = redactNode(k, v);
    }
    return out;
  }
  if (typeof value === "string") {
    return "__REDACTED__";
  }
  return value;
}

function redactNode(key, value) {
  if (secretKeyRegex.test(String(key))) {
    return redactLike(value);
  }
  if (typeof value === "string" && secretValueRegex.test(value.trim())) {
    return "__REDACTED__";
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactNode(key, item));
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = redactNode(k, v);
    }
    return out;
  }
  return value;
}

function sanitizeJson(filePath) {
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = JSON.parse(raw);
    const redacted = redactNode("root", parsed);
    fs.writeFileSync(filePath, `${JSON.stringify(redacted, null, 2)}\n`, "utf8");
  } catch {
    // Keep file as is if it is not valid JSON.
  }
}

function sanitizeKeyValueText(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split(/\r?\n/);
  const out = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      return line;
    }

    const eq = line.match(/^(\s*[^#=\s][^=]*?)(\s*=\s*)(.*)$/);
    if (eq && secretKeyRegex.test(eq[1].trim())) {
      return `${eq[1]}${eq[2]}__REDACTED__`;
    }

    const colon = line.match(/^(\s*[^#:\s][^:]*?)(\s*:\s*)(.*)$/);
    if (colon && secretKeyRegex.test(colon[1].trim())) {
      return `${colon[1]}${colon[2]}__REDACTED__`;
    }

    if (secretValueRegex.test(line)) {
      return line.replace(secretValueRegex, "__REDACTED__");
    }
    return line;
  });
  fs.writeFileSync(filePath, `${out.join("\n")}\n`, "utf8");
}

function isLikelyTextFile(filePath) {
  try {
    const buf = fs.readFileSync(filePath);
    const limit = Math.min(buf.length, 2048);
    for (let i = 0; i < limit; i += 1) {
      const byte = buf[i];
      if (byte === 0) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  }
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
      continue;
    }
    if (!entry.isFile()) {
      continue;
    }
    const ext = path.extname(entry.name).toLowerCase();
    if (ext === ".json") {
      sanitizeJson(full);
      continue;
    }
    if (!isLikelyTextFile(full)) {
      continue;
    }
    if ([".env", ".yml", ".yaml", ".toml", ".ini", ".conf", ".txt"].includes(ext) || !ext) {
      sanitizeKeyValueText(full);
    }
  }
}

if (fs.existsSync(root) && fs.statSync(root).isDirectory()) {
  walk(root);
}
NODE
}

copy_dir_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ ! -d "$src" ]]; then
    return 0
  fi
  mkdir -p "$dst"
  rsync -a \
    --exclude '.DS_Store' \
    --exclude '.git' \
    --exclude 'node_modules' \
    "$src"/ "$dst"/
}

CONFIG_JSON_SRC="$CONFIG_DIR/openclaw.json"
if [[ ! -f "$CONFIG_JSON_SRC" ]]; then
  echo "Missing $CONFIG_JSON_SRC" >&2
  exit 1
fi
sanitize_json "$CONFIG_JSON_SRC" "$OUTPUT_DIR/config/openclaw.json"

copy_dir_if_exists "$CONFIG_DIR/extensions" "$OUTPUT_DIR/config/extensions"
copy_dir_if_exists "$CONFIG_DIR/skills" "$OUTPUT_DIR/config/skills"

if [[ -d "$CONFIG_DIR/workspace-clinic" ]]; then
  copy_dir_if_exists "$CONFIG_DIR/workspace-clinic" "$OUTPUT_DIR/config/workspace-clinic"
fi

sanitize_config_tree "$OUTPUT_DIR/config"

copy_dir_if_exists "$WORKSPACE_DIR" "$OUTPUT_DIR/workspace"

if [[ -f "$ROOT_DIR/.env" ]]; then
  sanitize_env_file "$ROOT_DIR/.env" "$OUTPUT_DIR/deployment/.env.sanitized"
fi

cat >"$OUTPUT_DIR/deployment/docker-compose.reference.yml" <<'EOF'
services:
  openclaw-gateway:
    image: ${OPENCLAW_IMAGE:-openclaw:local}
    volumes:
      - ${OPENCLAW_CONFIG_DIR}:/home/node/.openclaw
      - ${OPENCLAW_WORKSPACE_DIR}:/home/node/.openclaw/workspace
    ports:
      - "${OPENCLAW_GATEWAY_PORT:-18789}:18789"
      - "${OPENCLAW_BRIDGE_PORT:-18790}:18790"
EOF

if rg -n --hidden -S \
  -e '(xox[baprs]-|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|[0-9]{8,}:[A-Za-z0-9_-]{30,})' \
  "$OUTPUT_DIR" >"$OUTPUT_DIR/potential-secrets-report.txt"; then
  SECRET_SCAN_STATUS="warnings"
else
  rm -f "$OUTPUT_DIR/potential-secrets-report.txt"
  SECRET_SCAN_STATUS="clean"
fi

cat >"$OUTPUT_DIR/README.md" <<EOF
# OpenClaw Git-Safe Bundle

Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

## What Is Included

- \`config/openclaw.json\` (sanitized)
- \`config/extensions/\` (if present)
- \`config/skills/\` (if present)
- \`config/workspace-clinic/\` (if present)
- \`workspace/\` (copied from current mounted workspace)
- \`deployment/docker-compose.reference.yml\`
- \`deployment/.env.sanitized\` (if local \`.env\` exists)

Source paths:
- Resolved automatically during export from Docker Compose / env.
- Absolute local paths are intentionally omitted from this bundle for safe sharing.

Secret scan status: **$SECRET_SCAN_STATUS**

## Restore On Another Host

1. Copy this bundle into your shared repository (or unpack it on target host).
2. Choose target state paths (example):
   - \`OPENCLAW_CONFIG_DIR=~/.openclaw\`
   - \`OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace\`
3. Restore files:

\`\`\`bash
mkdir -p "\$OPENCLAW_CONFIG_DIR" "\$OPENCLAW_WORKSPACE_DIR"
rsync -a ./config/openclaw.json "\$OPENCLAW_CONFIG_DIR/openclaw.json"
rsync -a ./config/extensions/ "\$OPENCLAW_CONFIG_DIR/extensions/" 2>/dev/null || true
rsync -a ./config/skills/ "\$OPENCLAW_CONFIG_DIR/skills/" 2>/dev/null || true
rsync -a ./workspace/ "\$OPENCLAW_WORKSPACE_DIR/"
\`\`\`

4. Fill real secrets manually:
   - \`openclaw.json\` secret fields marked as \`__REDACTED__\`
   - \`deployment/.env.sanitized\` (if used)
5. Start/restart OpenClaw in Docker:

\`\`\`bash
cd /path/to/openclaw-repo
./docker-setup.sh
docker compose restart openclaw-gateway
\`\`\`

## Notes

- This bundle intentionally excludes credentials/session/runtime artifacts (\`credentials/\`, \`agents/\`, \`telegram/\`, logs, queues).
- If \`potential-secrets-report.txt\` exists, review it before committing to git.
EOF

echo "Bundle created: $OUTPUT_DIR"
echo "Next step: inspect $OUTPUT_DIR/README.md and commit only after reviewing redaction results."
