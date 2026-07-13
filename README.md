# OpenAI Gateway

An OpenAI-compatible gateway for routing requests through one or more Codex
accounts. It supports `/v1/chat/completions` and `/v1/responses`.

## Quick setup

### 1. Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/hetsaraiya/openai-gateway.git
cd openai-gateway
uv sync
```

### 2. Configure an account and environment

Sign in with the Codex CLI, then copy its generated credentials into this
project. Repeat for each account you want the gateway to use.

```bash
codex login
mkdir -p auth
cp ~/.codex/auth.json auth/main.json

cp .env.example .env
# Edit .env and set GATEWAY_API_KEY to a long, random value.
```

`auth/` is gitignored. The gateway refreshes tokens, so keep this directory
writable and persistent.

### 3. Start the gateway

Start Redis, then run the app:

```bash
docker run -d --name openai-gateway-redis -p 6379:6379 redis:7-alpine
uv run uvicorn app.main:app --reload
```

The gateway listens at `http://localhost:8000`. Confirm it is running:

```bash
curl http://localhost:8000/healthz
```

## Use it

Point an OpenAI client at the local `/v1` endpoint and use the gateway key:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-gateway-api-key",
)

response = client.chat.completions.create(
    model="gpt-5.1-codex",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Available models are exposed at `GET /v1/models`.

## Configuration

Copy `.env.example` to `.env`. Usually only `GATEWAY_API_KEY` is required.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GATEWAY_API_KEY` | required | Key clients use to access the gateway |
| `AUTH_DIR` | `auth` | Directory containing Codex credential JSON files |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `ROUTING_STRATEGY` | `fallback` | `fallback`, `round_robin`, or `quota_aware` |
| `DEFAULT_MODEL` | empty | Model to use when a chat request omits one |

See [`.env.example`](.env.example) for all optional settings.

## Docker Compose

With `.env` configured and credentials in `auth/`:

```bash
sudo chown -R 10001:10001 auth && chmod 700 auth
docker compose up --build
```

The gateway will be available on port 8000.

## Notes

Use only accounts and workloads you are authorized to operate. The upstream
Codex backend may change without notice.
