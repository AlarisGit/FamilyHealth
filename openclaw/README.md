# FamilyHealth OpenClaw Reproduction Package

This package recreates the working FamilyHealth Telegram scheduling agent without shipping live secrets or runtime state.

It contains:
- `repo-overlay/`: only the OpenClaw source files changed relative to base commit `dc4441322f9dc15f19de7bb89c3b2daf703d71e6`
- `config-overlay/`: sanitized OpenClaw config, plugin, skill, and `workspace-clinic` persona files
- `repo-remove-paths.txt`: upstream paths that must be removed to match the working tree
- `apply_package.py`: helper that overlays repo/config files and renders secret placeholders
- `secrets.env.example`: template for required secret values

It intentionally does not contain:
- live API keys, bot tokens, or gateway tokens
- device identity, pairing state, sessions, logs, memory databases, Telegram offsets, or other runtime artifacts
- older export bundles and their instructions

## Package File Guide

This section explains what each non-obvious file in the package does.

Top-level files:
- `BASE_COMMIT.txt`: the upstream OpenClaw commit that must be checked out before applying the overlay
- `repo-remove-paths.txt`: upstream paths that were absent in the deployed tree and should be removed after overlaying files
- `apply_package.py`: renders placeholders from `secrets.env` and copies both overlays into the target repo/config roots
- `secrets.env.example`: minimal secret contract required to make the packaged config runnable

Repo overlay:
- `repo-overlay/src/...`: source-level OpenClaw behavior changes relative to upstream
- `repo-overlay/tools/...`: helper scripts that were added locally to export and import reproducible bundles

Config overlay:
- `config-overlay/openclaw.json`: the main runtime config that binds Telegram to the `clinic` agent and enables the external `fh-api` plugin
- `config-overlay/agents/...`: model catalogs and auth profile stubs for the `main` and `clinic` agents
- `config-overlay/extensions/fh-api/...`: the custom plugin that turns FamilyHealth REST API operations into an OpenClaw tool
- `config-overlay/skills/family-health-scheduler/SKILL.md`: the strict tool-usage policy for scheduling conversations
- `config-overlay/workspace-clinic/...`: agent persona, behavioral guardrails, bootstrap text, and workspace metadata for the FamilyHealth agent

## Base Version

Start from upstream OpenClaw commit:

```text
dc4441322f9dc15f19de7bb89c3b2daf703d71e6
```

This is the closest upstream match to the deployed code. The running service reports `OpenClaw 2026.3.9`.

## What Changed Relative To Upstream

Repo overlay files:
- `docker-compose.yml`
- `src/agents/pi-embedded-runner/run/attempt.ts`
- `src/agents/session-tool-result-guard-wrapper.ts`
- `src/agents/session-tool-result-guard.tool-result-persist-hook.test.ts`
- `src/agents/system-prompt.ts`
- `src/agents/system-prompt.test.ts`
- `src/agents/workspace.ts`
- `src/agents/workspace.test.ts`
- `src/auto-reply/reply/inbound-meta.ts`
- `src/auto-reply/reply/inbound-meta.test.ts`
- `src/auto-reply/reply/session-reset-prompt.ts`
- `tools/agent_bundle_export.py`
- `tools/agent_bundle_import.py`

Repo removals:
- `src/gateway/server-methods/CLAUDE.md`

Functional effect of the overlay:
- builds a local Docker image instead of pulling `ghcr.io/openclaw/openclaw:latest`
- enables LLM trace logging to `/tmp/openclaw/llm-trace.jsonl`
- summarizes `fh_api` tool results before persistence
- injects exact current time into the system prompt
- stops injecting stale `BOOTSTRAP.md` and empty `HEARTBEAT.md`
- trims inbound metadata noise in direct Telegram chats
- forces English startup greeting after `/new` or `/reset`

## Detailed Repo Overlay Changes

This section explains the purpose of each code file in `repo-overlay/`.

### `docker-compose.yml`

Purpose:
- changes OpenClaw startup from a pulled image to a locally built image
- ensures the modified source tree is what actually gets packaged into the container
- enables LLM trace logging through environment variables

Why it matters:
- without this change, the deployment would keep running upstream `ghcr.io/openclaw/openclaw:latest` and would ignore local source modifications
- `OPENCLAW_LLM_TRACE=1` and `OPENCLAW_LLM_TRACE_PATH=/tmp/openclaw/llm-trace.jsonl` make troubleshooting much easier during bot behavior debugging

### `src/agents/pi-embedded-runner/run/attempt.ts`

Purpose:
- adds JSONL tracing for the embedded LLM runtime

What changed:
- serializes system prompt, current prompt, conversation history, assistant output, and tool metadata
- writes one trace record per run to `/tmp/openclaw/llm-trace.jsonl`
- supports optional gating through environment variables

Why it matters:
- this is the main observability patch for understanding why the FamilyHealth bot answered a certain way
- it captures the exact LLM input/output around tool use and prompt construction

### `src/agents/session-tool-result-guard-wrapper.ts`

Purpose:
- compresses verbose `fh_api` JSON tool results before they are persisted into session history and passed through hooks

What changed:
- detects tool results produced by `fh_api`
- parses the returned JSON payload
- rewrites large raw API responses into short, structured summaries like `fh_api ok visits: items=2 ...`
- preserves booking-critical IDs such as `doctor_id`, `clinic_id`, and `visit_id`

Why it matters:
- raw FamilyHealth API payloads are noisy and large
- large tool payloads make history harder to reason over and can degrade later model behavior
- summarization reduces token pressure while keeping the identifiers needed for follow-up booking/cancellation actions

### `src/agents/session-tool-result-guard.tool-result-persist-hook.test.ts`

Purpose:
- tests the `fh_api` summarization behavior added above

What changed:
- verifies summary formatting for visit lists, bookings, errors, doctors, and slots
- checks that guard integration applies the summary automatically

Why it matters:
- this patch changes persistence semantics, so tests are needed to keep summaries stable and to ensure IDs are not lost

### `src/agents/system-prompt.ts`

Purpose:
- extends system prompt generation to include exact current time, not only timezone

What changed:
- adds `userTime` into the “Current Date & Time” section when available

Why it matters:
- the scheduling bot frequently interprets “today”, “tomorrow”, “evening”, and similar temporal phrases
- having exact current time in the prompt reduces ambiguity for date-sensitive booking behavior

### `src/agents/system-prompt.test.ts`

Purpose:
- updates tests for the changed system prompt time behavior

Why it matters:
- upstream tests expected no exact time in the system prompt
- local behavior intentionally diverges from upstream for scheduling accuracy

### `src/agents/workspace.ts`

Purpose:
- changes which workspace bootstrap files are injected into the model context

What changed:
- skips injecting `HEARTBEAT.md` when it is effectively empty
- skips injecting stale `BOOTSTRAP.md` once a workspace looks initialized or completed

Why it matters:
- the FamilyHealth workspace uses stable persona files and does not need repeated bootstrap chatter in normal operation
- this reduces prompt clutter and avoids confusing the model with stale startup instructions

### `src/agents/workspace.test.ts`

Purpose:
- tests the bootstrap injection rules above

Why it matters:
- protects the local prompt-shaping behavior from regressions

### `src/auto-reply/reply/inbound-meta.ts`

Purpose:
- simplifies inbound metadata injected into user context

What changed:
- JSON metadata blocks are rendered compactly instead of pretty-printed
- sender metadata block is omitted for direct chats to avoid duplicating envelope identity information

Why it matters:
- Telegram DM scheduling conversations do not benefit from repeated sender envelope noise
- smaller context means less distraction for the model and lower token use

### `src/auto-reply/reply/inbound-meta.test.ts`

Purpose:
- tests the direct-chat metadata suppression and compact formatting behavior

### `src/auto-reply/reply/session-reset-prompt.ts`

Purpose:
- modifies the prompt used after `/new` and `/reset`

What changed:
- startup greeting is explicitly required to be in English unless the reset message itself asked for another language

Why it matters:
- this avoids carrying over language from previous conversations into a fresh session reset
- useful for predictable operator/demo startup behavior

### `tools/agent_bundle_export.py`

Purpose:
- exports a sanitized reproducible bundle of the modified repo and OpenClaw config

What changed locally:
- supports comparing the current repo to a baseline source tree and exporting only changed files plus removals

Why it matters:
- this is how the deployment could be packaged cleanly even though the working tree was not itself a git checkout

### `tools/agent_bundle_import.py`

Purpose:
- restores a sanitized bundle into a target repo/config pair

Why it matters:
- it complements the export tooling and documents the expected overlay/import model for reproducing the deployment

## Config Included In This Package

The sanitized config overlay contains only the files needed to reproduce this agent:
- `openclaw.json`
- `agents/main/agent/{models.json,auth-profiles.json,auth.json}`
- `agents/clinic/agent/{models.json,auth-profiles.json}`
- `extensions/fh-api/*`
- `skills/family-health-scheduler/SKILL.md`
- `workspace-clinic/*`

Not included on purpose:
- `identity/*`
- `devices/*`
- `credentials/*`
- `telegram/*`
- `agents/*/sessions/*`
- `workspace-clinic/memory/*`

Those files are runtime-generated or environment-specific and should be recreated on the target host.

## Detailed Config Overlay Guide

This section explains the role of each config file and how the FamilyHealth agent is assembled.

### `config-overlay/openclaw.json`

This is the central deployment config. Key sections:

- `models.providers.xai`: registers the xAI endpoint and the `grok-4-1-fast-non-reasoning` model
- `agents.defaults`: shared defaults such as workspace root, compaction policy, concurrency, and sandbox mode
- `agents.list`: defines the `clinic` agent and the fallback `main` agent
- `bindings`: routes Telegram traffic to the `clinic` agent
- `session.dmScope = per-channel-peer`: critical for `fh_api`, because the plugin derives `patient_id` from the Telegram DM session key
- `channels.telegram`: Telegram transport settings, pairing mode, retries, timeout, and group allowlist behavior
- `plugins.allow`, `plugins.load.paths`, `plugins.entries.fh-api`: enables loading the custom plugin and points it at the external FamilyHealth API
- `skills.allowBundled = ["__none__"]`: prevents accidental use of unrelated bundled skills

Most important behavior encoded here:
- all Telegram traffic is handled by the `clinic` agent
- the `clinic` agent gets only the `fh_api` tool plus a minimal tool profile
- the FamilyHealth API endpoint is configured centrally here

### `config-overlay/agents/clinic/agent/models.json`

Purpose:
- declares the model catalog available to the `clinic` agent

Why it exists separately from `openclaw.json`:
- OpenClaw supports per-agent model state and provider auth material
- this file is where the effective xAI API key is injected

### `config-overlay/agents/clinic/agent/auth-profiles.json`

Purpose:
- defines the named auth profile used by the `clinic` agent for xAI

What it controls:
- profile name `xai:default`
- provider type `api_key`
- the secret key placeholder that must be rendered at deployment time

### `config-overlay/agents/main/agent/models.json`
### `config-overlay/agents/main/agent/auth-profiles.json`
### `config-overlay/agents/main/agent/auth.json`

Purpose:
- keep the fallback `main` agent aligned with the same xAI provider family

Why they are included:
- even though Telegram is bound to `clinic`, OpenClaw still has a `main` agent slot
- keeping `main` valid avoids broken defaults inside CLI/dashboard flows

### `config-overlay/extensions/fh-api/openclaw.plugin.json`

Purpose:
- plugin manifest for the custom FamilyHealth extension

What it controls:
- plugin id and display name
- config schema for `baseUrl` and `timeoutMs`
- UI hints used by OpenClaw when inspecting plugin config
- extension entrypoint path

### `config-overlay/extensions/fh-api/index.ts`

Purpose:
- implementation of the custom `fh_api` tool

What it does:
- exposes FamilyHealth operations as a single tool with actions:
  - `list_clinics`
  - `list_directions`
  - `list_doctors`
  - `list_services`
  - `search_slots`
  - `book_visit`
  - `list_visits`
  - `cancel_visit`
- derives `patient_id` from the Telegram session key instead of asking the user
- normalizes times and slot/visit types
- filters out past or busy slots by default
- resolves some doctor-name ambiguity client-side
- can infer `clinic_id` for booking if the user selected a concrete slot first
- blocks repeated identical failing requests for a short window

Why it matters:
- this file is the actual integration layer between OpenClaw and FamilyHealth
- without it, the agent prompt alone would not be sufficient to safely talk to the clinic API

### `config-overlay/skills/family-health-scheduler/SKILL.md`

Purpose:
- defines the high-level task contract for the scheduling assistant

What it enforces:
- only scheduling-related operations are allowed
- live API lookups must be used for facts and mutations
- unsupported actions must be refused
- booking requires confirmation first
- doctor/specialty resolution must be based on API data, not hardcoded dictionaries

Why it matters:
- this is the first line of task-level guardrails around the custom plugin

### `config-overlay/workspace-clinic/AGENTS.md`

Purpose:
- primary operating instructions for the `clinic` agent persona

What it adds beyond the skill:
- stricter refusal behavior for non-clinic topics
- fact guardrails around doctor/clinic availability
- conflict guardrails for overlapping appointments
- explicit follow-up behavior when context changes mid-conversation

### `config-overlay/workspace-clinic/BOOTSTRAP.md`

Purpose:
- startup/bootstrap framing for the workspace

Why it matters:
- helps ensure the workspace is interpreted as a scheduling-only environment during initialization

### `config-overlay/workspace-clinic/IDENTITY.md`

Purpose:
- short identity card for the assistant

What it controls:
- role
- scope
- tone
- expected user population

### `config-overlay/workspace-clinic/SOUL.md`

Purpose:
- stable behavioral style and safety rules

What it controls:
- concise response style
- fresh-API-first behavior
- preserving conversation context
- not presenting guessed clinic availability as fact

### `config-overlay/workspace-clinic/TOOLS.md`

Purpose:
- identifies `fh_api` as the primary operational tool

Why it matters:
- reinforces that clinic data and mutations must go through the plugin, not through ad hoc reasoning

### `config-overlay/workspace-clinic/USER.md`

Purpose:
- lightweight user-context framing for Telegram patients

### `config-overlay/workspace-clinic/HEARTBEAT.md`

Purpose:
- intentionally empty heartbeat file

Why it matters:
- with the local `workspace.ts` patch, effectively empty heartbeat content is ignored and does not pollute prompt context

### `config-overlay/workspace-clinic/.openclaw/workspace-state.json`

Purpose:
- records workspace bootstrap state

Why it matters:
- helps OpenClaw understand that the workspace has already been initialized
- interacts with the local `BOOTSTRAP.md` injection logic

## Required Secrets

Copy `secrets.env.example` to `secrets.env` and fill:

```dotenv
XAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
OPENCLAW_GATEWAY_TOKEN=...
```

Secret usage:
- `XAI_API_KEY`: inserted into both `agents/main/agent/*` and `agents/clinic/agent/*`
- `TELEGRAM_BOT_TOKEN`: inserted into `config-overlay/openclaw.json`
- `OPENCLAW_GATEWAY_TOKEN`: inserted into `config-overlay/openclaw.json`

`OPENCLAW_GATEWAY_TOKEN` can be any strong random hex string, for example:

```bash
openssl rand -hex 32
```

## Prerequisites

- Docker and Docker Compose
- git
- Python 3
- access from the OpenClaw container to the external FamilyHealth demo API

The FamilyHealth demo service is not part of this package.

Use the already deployed external service:
- API base: `http://ai-chatbot-demo.int.alarislabs.com:8080/api/v1`
- OpenAPI: `http://ai-chatbot-demo.int.alarislabs.com:8080/openapi.json`

## Package Layout

```text
familyhealth-openclaw-package-20260412/
├── BASE_COMMIT.txt
├── README.md
├── apply_package.py
├── secrets.env.example
├── repo-remove-paths.txt
├── repo-overlay/
└── config-overlay/
```

## Rebuild From Scratch

### 1. Clone OpenClaw And Check Out The Base Commit

```bash
git clone https://github.com/openclaw/openclaw.git
cd openclaw
git checkout dc4441322f9dc15f19de7bb89c3b2daf703d71e6
```

### 2. Prepare The Target Config Directory

Choose a config directory and create it. Example:

```bash
export OPENCLAW_CONFIG_DIR=$HOME/.openclaw
export OPENCLAW_WORKSPACE_DIR=$OPENCLAW_CONFIG_DIR/workspace
mkdir -p "$OPENCLAW_CONFIG_DIR" "$OPENCLAW_WORKSPACE_DIR"
```

This package also installs a separate clinic workspace at:

```text
$OPENCLAW_CONFIG_DIR/workspace-clinic
```

### 3. Fill Secrets

```bash
cp /path/to/familyhealth-openclaw-package-20260412/secrets.env.example \
   /path/to/familyhealth-openclaw-package-20260412/secrets.env
```

Edit `secrets.env` and fill the three values.

### 4. Apply The Package

```bash
python3 /path/to/familyhealth-openclaw-package-20260412/apply_package.py \
  --repo-root /path/to/openclaw \
  --config-dir "$OPENCLAW_CONFIG_DIR" \
  --secrets-file /path/to/familyhealth-openclaw-package-20260412/secrets.env
```

Dry-run is available:

```bash
python3 /path/to/familyhealth-openclaw-package-20260412/apply_package.py \
  --repo-root /path/to/openclaw \
  --config-dir "$OPENCLAW_CONFIG_DIR" \
  --secrets-file /path/to/familyhealth-openclaw-package-20260412/secrets.env \
  --dry-run
```

### 5. Build And Start OpenClaw

```bash
cd /path/to/openclaw
export OPENCLAW_DOCKER_COMPOSE=$PWD/docker-compose.yml
export OPENCLAW_CONFIG_DIR
export OPENCLAW_WORKSPACE_DIR
docker compose -f "$OPENCLAW_DOCKER_COMPOSE" build openclaw-gateway
docker compose -f "$OPENCLAW_DOCKER_COMPOSE" up -d --no-build openclaw-gateway
```

This overlay expects the config dir to be mounted into the container as `/home/node/.openclaw`.

### 6. Pair Telegram

The packaged config uses:
- `channels.telegram.enabled = true`
- `channels.telegram.dmPolicy = pairing`
- `session.dmScope = per-channel-peer`

That `dmScope` is important because the `fh_api` plugin derives `patient_id` from the Telegram DM session key.

After the gateway is up, approve the Telegram pairing code:

```bash
docker compose -f "$OPENCLAW_DOCKER_COMPOSE" run --rm openclaw-cli pairing approve telegram <PAIR_CODE>
```

You can also inspect the gateway token or launch the dashboard:

```bash
docker compose -f "$OPENCLAW_DOCKER_COMPOSE" run --rm openclaw-cli config get gateway.auth.token
docker compose -f "$OPENCLAW_DOCKER_COMPOSE" run --rm openclaw-cli dashboard --no-open
```

## FamilyHealth API Endpoint

The packaged config points `fh-api` to:

```text
http://ai-chatbot-demo.int.alarislabs.com:8080/api/v1
```

The matching OpenAPI document is:

```text
http://ai-chatbot-demo.int.alarislabs.com:8080/openapi.json
```

This package assumes the OpenClaw container can reach that hostname directly.

If you need to point to another FamilyHealth environment, update:

```text
config-overlay/openclaw.json
plugins.entries.fh-api.config.baseUrl
```

You may also want to update:

```text
config-overlay/extensions/fh-api/index.ts
config-overlay/extensions/fh-api/openclaw.plugin.json
```

Those files control the plugin default and UI hint placeholder.

## Post-Start Verification

Check containers:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

Confirm OpenClaw version:

```bash
docker exec openclaw-openclaw-gateway-1 sh -lc 'openclaw --version'
```

Confirm HTTP health:

```bash
curl -fsS http://127.0.0.1:18789/healthz
```

Inspect the last LLM trace record:

```bash
docker exec openclaw-openclaw-gateway-1 sh -lc \
  'tail -n 1 /tmp/openclaw/llm-trace.jsonl'
```

## Notes About The Included Persona And Skill

The clinic agent behavior is split across:
- `config-overlay/skills/family-health-scheduler/SKILL.md`
- `config-overlay/workspace-clinic/AGENTS.md`
- `config-overlay/workspace-clinic/IDENTITY.md`
- `config-overlay/workspace-clinic/SOUL.md`
- `config-overlay/workspace-clinic/TOOLS.md`
- `config-overlay/workspace-clinic/USER.md`
- `config-overlay/workspace-clinic/BOOTSTRAP.md`

The essential runtime rules are:
- use only `fh_api` for scheduling facts and mutations
- do not answer unrelated questions
- ask for confirmation before `book_visit`
- keep `session.dmScope=per-channel-peer`
- keep the separate `workspace-clinic`

## Why Runtime Files Are Excluded

The following state should not be copied between hosts:
- device identity and operator tokens
- approved paired devices
- Telegram pairing state
- prior conversations and reset history
- clinic memory notes from demo chats

Those files are specific to the current deployment and would either break pairing or leak environment-specific state.
