# Codex Multi-Account Gateway

An OpenAI-compatible gateway that spreads traffic across several **ChatGPT Codex
subscription accounts**. You drop one Codex `auth.json` per account into `auth/`,
point any OpenAI SDK at this gateway with a single **master key**, and the
gateway picks a healthy account per request — refreshing OAuth tokens, tracking
rate limits, and failing over automatically.

```
        ┌─────────────┐  master key   ┌──────────────────────────┐  Bearer access_token   ┌──────────────────────────────┐
client →│  OpenAI SDK │ ────────────→ │   Gateway (FastAPI)      │ ─────────────────────→ │ chatgpt.com/backend-api/codex │
        └─────────────┘ /v1/chat/...  │  router · translate ·    │  chatgpt-account-id     │        /responses (SSE)       │
                                      │  oauth refresh · proxy   │                         └──────────────────────────────┘
                                      └──────────┬───────────────┘
                                          quota+dedup │   refresh │ token rotation
                                           ┌────▼────┐      ┌──────▼──────┐
                                           │  Redis  │      │ auth/*.json │
                                           └─────────┘      └─────────────┘
```

## How auth works (important)

ChatGPT subscription auth does **not** use API keys against `api.openai.com`.
It uses the OAuth tokens that the Codex CLI writes to `~/.codex/auth.json`, and
talks to a different backend with a different API shape:

- **Upstream:** `POST https://chatgpt.com/backend-api/codex/responses` — the
  **Responses API** (streaming SSE), *not* Chat Completions.
- **Headers:** `Authorization: Bearer <access_token>`,
  `chatgpt-account-id: <account_id>`, `OpenAI-Beta: responses=experimental`,
  `originator: codex_cli_rs`, plus a per-request `session_id`.
- **Token refresh:** `POST https://auth.openai.com/oauth/token` with
  `grant_type=refresh_token` and the Codex public `client_id`; rotated tokens are
  written back to the same `auth.json` (just like the Codex CLI).

Because the backend only speaks the Responses API, the gateway exposes **both**
surfaces:

| You call | Gateway does |
|---|---|
| `POST /v1/responses` | near-verbatim passthrough to the Codex backend |
| `POST /v1/chat/completions` | translates Chat ⇆ Responses (incl. streaming + tool calls) |

## Features

- **Two OpenAI-compatible surfaces** — `/v1/chat/completions` (translated) and
  `/v1/responses` (passthrough), both with streaming SSE.
- **Live model catalog** — `/v1/models` is fetched from the Codex backend
  (`GET /models?client_version=…`, ETag-cached), never hardcoded, so it reflects
  exactly what your accounts can use.
- **Account routing** — `round_robin`, `quota_aware`, or `fallback` (default).
- **Automatic failover** — `429`/`5xx`/transport errors retry on the next
  account; a `401` force-refreshes the token once before moving on.
- **OAuth token refresh** — access tokens are refreshed before expiry and
  persisted back to disk, serialized per account to avoid stampedes.
- **Rate-limit cooldown** — a `429` benches the account for a cooldown window
  (honoring upstream `Retry-After`).
- **Request dedup** — `Idempotency-Key` gives one upstream call across retries.
- **Master-key auth**, **structured JSON logs**, `/admin/status` dashboard, and
  graceful Redis degradation.

## Quick start (uv)

```bash
uv sync
cp .env.example .env                 # set GATEWAY_API_KEY
# drop your Codex auth.json files into auth/  (one per account)
docker run -p 6379:6379 redis:7-alpine &   # or any Redis on REDIS_URL
uv run uvicorn app.main:app --reload
```

### Provide accounts

For each account, log in with the Codex CLI (`codex login`) and copy the
resulting `~/.codex/auth.json` into this repo's `auth/` folder under a
descriptive name:

```
auth/
  acct-a.json
  acct-b.json
```

See [`auth/README.md`](auth/README.md) for the exact file format. **The `auth/`
folder is gitignored** — those files hold live bearer + refresh tokens.

### Call it like OpenAI

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="<GATEWAY_API_KEY>")

# Chat Completions — translated to the Responses API under the hood
client.chat.completions.create(
    model="gpt-5.1-codex",
    messages=[{"role": "user", "content": "hi"}],
)

# Or the Responses API directly (passthrough)
client.responses.create(model="gpt-5.1-codex", input="hi")
```

Every response carries `X-Gateway-Account` (which account served it) and
`X-Request-ID`.

## Run with Docker

```bash
cp .env.example .env                 # set GATEWAY_API_KEY
# put auth.json files in ./auth and make them owned by the container user (uid 10001):
sudo chown -R 10001:10001 ./auth && chmod 700 ./auth
docker compose up --build            # Redis + gateway on :8000
```

### Pull the published image (GHCR)

CI builds a **multi-arch** (`linux/amd64` + `linux/arm64`) image and pushes it to
GitHub Container Registry on every push to `main` and every `v*` tag:

```bash
docker pull ghcr.io/OWNER/openai-gateway:latest
docker run -p 8000:8000 --env-file .env \
  -v /srv/gateway/auth:/auth \        # read-write, persistent (token rotation writes back)
  ghcr.io/OWNER/openai-gateway:latest
```

### Securing credentials

- **Nothing secret is in the image.** `.dockerignore` excludes `auth/` and `.env`,
  so they never enter image layers — the GHCR image is safe to publish.
- **Mount credentials at runtime, read-write.** The gateway refreshes OAuth tokens
  and writes the rotated values back, so the `auth/` mount must be writable and
  persistent. A read-only secret mount (e.g. a bare Kubernetes `Secret`) will break
  rotation — seed it into a writable volume instead, and run a single refresher
  replica to avoid racing on rotating refresh tokens.
- Restrict it: dir `0700`, files `0600`, owned by uid `10001`; mount only that dir.
- Inject `GATEWAY_API_KEY` via `--env-file`/orchestrator env, never baked in.

## Configuration

Config is loaded with [`python-decouple`](https://pypi.org/project/python-decouple/):
it reads a `.env` file in the project root automatically (copy `.env.example`),
and real environment variables override it. See [`.env.example`](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_API_KEY` | — (required) | Master key clients present to the gateway |
| `AUTH_DIR` | `auth` | Folder of Codex `auth.json` files |
| `ROUTING_STRATEGY` | `fallback` | `round_robin` \| `quota_aware` \| `fallback` |
| `DEFAULT_MODEL` | _(empty)_ | Model when a chat request omits one; empty = resolve from live catalog |
| `CODEX_CLIENT_VERSION` | `0.139.0` | Sent as `?client_version=` when listing models |
| `MODELS_CACHE_TTL` | `3600` | Seconds to trust the fetched catalog before revalidating |
| `RATE_LIMIT_COOLDOWN` | `60` | Seconds to bench an account after a `429` |
| `MAX_ACCOUNT_ATTEMPTS` | `3` | Max accounts tried per request |
| `TOKEN_REFRESH_SKEW` | `300` | Refresh the access token N s before expiry |
| `REQUEST_TIMEOUT` | `600` | Upstream timeout (seconds) |
| `DEDUP_ENABLED` / `DEDUP_TTL` | `true` / `600` | `Idempotency-Key` dedup |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `CODEX_BASE_URL` | `https://chatgpt.com/backend-api/codex` | Upstream backend |
| `OAUTH_TOKEN_URL` | `https://auth.openai.com/oauth/token` | Token refresh endpoint |
| `CODEX_CLIENT_ID` | Codex CLI default | OAuth client id for refresh |
| `OPENCODE_GO_API_KEYS` | _(empty)_ | Optional comma-separated OpenCode Go subscription API keys |
| `OPENCODE_GO_BASE_URL` | `https://opencode.ai/zen/go/v1` | OpenCode Go OpenAI-compatible endpoint |

## Operational endpoints

- `GET /healthz` — liveness + Redis status + account count (no auth).
- `GET /admin/status` — per-account id / plan / token expiry / usage / cooldown
  (master key).
- `PUT|POST /admin/accounts/{id}` — upload (create/replace) a Codex `auth.json`
  for `{id}`; body is the raw auth.json. Validated and **hot-loaded** into the
  router with no restart. `201` created / `200` replaced.
- `DELETE /admin/accounts/{id}` — remove an account from the router and delete
  its `auth.json`.
- `POST /v1/admin/opencode-go/keys` — persist and hot-load an OpenCode Go
  subscription API key. Takes `api_key`, plus optional `identifier` and `label`.
  This endpoint is protected by the gateway master key.
- `GET /dashboard` — visual dashboard for active gateways and available models.
  Enter the gateway master key in the page; live data is read from authenticated
  `GET /dashboard/data`.

```bash
# status
curl http://localhost:8000/admin/status -H "X-Gateway-Key: $GATEWAY_API_KEY"

# upload / replace an account (id = a name you choose)
curl -X PUT http://localhost:8000/admin/accounts/dodiya \
  -H "X-Gateway-Key: $GATEWAY_API_KEY" -H "Content-Type: application/json" \
  --data-binary @~/.codex/auth.json

# upload / replace an OpenCode Go subscription key
curl -X PUT http://localhost:8000/admin/accounts/go-main \
  -H "X-Gateway-Key: $GATEWAY_API_KEY" -H "Content-Type: application/json" \
  --data '{"type":"opencode-go","api_key":"'"$OPENCODE_GO_API_KEY"'"}'

# add an OpenCode Go key (stored in AUTH_DIR and loaded without a restart)
curl -X POST http://localhost:8000/v1/admin/opencode-go/keys \
  -H "X-Gateway-Key: $GATEWAY_API_KEY" -H "Content-Type: application/json" \
  --data '{"api_key":"'"$OPENCODE_GO_API_KEY"'","identifier":"go-main","label":"Primary Go subscription"}'

# delete an account
curl -X DELETE http://localhost:8000/admin/accounts/dodiya \
  -H "X-Gateway-Key: $GATEWAY_API_KEY"
```

The gateway can boot with **zero** accounts and have them uploaded via the API
(requests `503` until at least one exists). Each Codex account must be used by
**only this gateway** — rotating refresh tokens get invalidated if the same
account is refreshed elsewhere.

OpenCode Go accounts are API-key based. Configure them with
`OPENCODE_GO_API_KEYS` or upload a credential JSON as shown above. Models are
listed as `opencode-go/<model-id>` (for example `opencode-go/glm-5.2`) and are
served through `/v1/chat/completions`. `/v1/responses` remains Codex-only.

## Tests

```bash
uv run pytest
```

Covers routing strategies, quota/cooldown, OAuth refresh + persistence, the
chat⇆Responses translation (request, response, streaming), and the proxy
failover path — all via `httpx.MockTransport` + `fakeredis`, so no network, real
Redis, or live tokens are needed.

## Project layout

```
app/
  main.py            FastAPI app: /v1/chat/completions, /v1/responses, admin
  config.py          Settings (master key, auth dir, codex/oauth endpoints)
  credentials.py     Codex auth.json loading, OAuth refresh, persistence
  jwt_util.py        Dependency-free JWT payload reader (exp, account id, plan)
  router.py          Account selection strategies
  proxy.py           Forwarding to the Codex backend + failover
  model_catalog.py   Live /v1/models fetched from the backend (ETag-cached)
  translate.py       Chat ⇆ Responses translation (incl. streaming SSE)
  quota.py           Redis usage counters + 429 cooldowns
  dedup.py           Idempotency-Key dedup store
  auth.py            Master-key authentication
  observability.py   Structured JSON logging
  models.py          Pydantic models for admin/health
auth/                Your Codex auth.json files (gitignored)
tests/               Router, quota, credentials, translate, and proxy tests
```

## ⚠️ Terms-of-Service note

Pooling one workload across multiple ChatGPT/Codex accounts — and calling the
undocumented `chatgpt.com/backend-api/codex` backend programmatically — may
violate OpenAI's Usage Policies / Terms, and that backend can change without
notice. Use this only for accounts and workloads you are authorized to run.
**Confirm your use case is permitted before deploying.**
