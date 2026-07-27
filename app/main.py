"""FastAPI application — the gateway entrypoint.

Exposes two OpenAI-compatible surfaces backed by ChatGPT Codex subscription
accounts (``auth/*.json``):

  * ``POST /v1/responses``         — near-verbatim passthrough to the Codex backend
  * ``POST /v1/chat/completions``  — translated to/from the Responses API

plus ``/v1/models``, ``/healthz`` and ``/admin/status``. Point any OpenAI SDK at
this server and authenticate with the gateway master key.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import require_master_key
from .config import get_settings
from .credentials import (
    CredentialError,
    delete_account_file,
    load_accounts,
    save_account_file,
    valid_account_id,
)
from .dedup import DedupStore, DuplicateInFlight
from .device_login import DeviceLoginManager
from .model_catalog import ModelCatalog, ModelCatalogError
from .models import (
    AccountStatus,
    ChatCompletionRequest,
    HealthResponse,
    OpenCodeGoKeyCreate,
    ResponsesRequest,
    StatusResponse,
)
from .observability import configure_logging, log_access, new_request_id, request_id_var
from .proxy import (
    AllAccountsFailed,
    CODEX_SUPPORTED_ENDPOINTS,
    CodexProxy,
    OPENCODE_GO_CHAT_ENDPOINT,
    OPENCODE_GO_MESSAGES_ENDPOINT,
    OPENCODE_GO_MESSAGES_MODELS,
    OpenCodeGoProxy,
    is_opencode_go_model,
    strip_opencode_go_model,
)
from .quota import QuotaStore
from .router import AccountRouter, NoAccountAvailable
from .translate import (
    UpstreamError,
    aggregate_response,
    chat_to_responses,
    iter_sse,
    new_chat_id,
    responses_sse_to_chat_sse,
    responses_to_chat,
)

log = logging.getLogger("gateway")
WEB_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    accounts = load_accounts(settings)

    quota = QuotaStore(settings.redis_url)
    dedup = DedupStore(settings.redis_url, settings.dedup_ttl)
    router = AccountRouter(settings, accounts, quota)
    client = httpx.AsyncClient(http2=True, timeout=settings.request_timeout)
    proxy = CodexProxy(settings, router, client)
    opencode_go_proxy = OpenCodeGoProxy(settings, router, client)
    catalog = ModelCatalog(settings, router, client)
    device_logins = DeviceLoginManager(settings, router)

    app.state.settings = settings
    app.state.router = router
    app.state.quota = quota
    app.state.dedup = dedup
    app.state.proxy = proxy
    app.state.opencode_go_proxy = opencode_go_proxy
    app.state.catalog = catalog
    app.state.device_logins = device_logins
    app.state.client = client

    redis_ok = await quota.ping()
    log.info(
        "gateway up: %d accounts, strategy=%s, redis=%s",
        len(accounts), settings.strategy, "ok" if redis_ok else "DOWN",
    )
    try:
        yield
    finally:
        await device_logins.close()
        await client.aclose()
        await quota.close()
        await dedup.close()


app = FastAPI(title="Codex Multi-Account Gateway", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    new_request_id()
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id_var.get()
    log_access(
        log, method=request.method, path=request.url.path, status=response.status_code,
        account=response.headers.get("X-Gateway-Account", "-"),
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _error(status: int, message: str, code: str, etype: str = "gateway_error") -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": {"message": message, "type": etype, "code": code}
    })


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gateway Dashboard</title>
  <style>
    :root { color-scheme: light dark; --bg:#f7f8fa; --panel:#ffffff; --ink:#16202a; --muted:#647080; --line:#d9dee5; --ok:#0d7a4f; --warn:#b35c00; --chip:#eef2f6; }
    @media (prefers-color-scheme: dark) { :root { --bg:#111418; --panel:#191f26; --ink:#edf2f7; --muted:#9aa6b2; --line:#303943; --chip:#242c35; } }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }
    header { border-bottom:1px solid var(--line); background:var(--panel); }
    .wrap { max-width:1180px; margin:0 auto; padding:20px; }
    .top { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
    h1 { font-size:24px; line-height:1.2; margin:0; letter-spacing:0; }
    h2 { font-size:16px; margin:0 0 12px; letter-spacing:0; }
    .auth { display:flex; gap:8px; min-width:min(100%, 440px); }
    input { flex:1; min-width:180px; padding:10px 12px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink); }
    button { padding:10px 14px; border:1px solid var(--line); border-radius:6px; background:var(--ink); color:var(--panel); cursor:pointer; }
    main.wrap { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
    section { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }
    .wide { grid-column:1 / -1; }
    .stats { display:grid; grid-template-columns:repeat(4, minmax(120px, 1fr)); gap:12px; }
    .stat { border:1px solid var(--line); border-radius:8px; padding:12px; background:var(--bg); }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; font-weight:700; margin-top:4px; overflow-wrap:anywhere; }
    table { width:100%; border-collapse:collapse; table-layout:fixed; }
    th, td { padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; overflow-wrap:anywhere; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .pill { display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border-radius:999px; background:var(--chip); font-size:12px; }
    .dot { width:8px; height:8px; border-radius:50%; background:var(--warn); }
    .dot.ok { background:var(--ok); }
    .muted { color:var(--muted); }
    .error { color:#b3261e; }
    @media (max-width: 780px) { main.wrap { grid-template-columns:1fr; } .stats { grid-template-columns:repeat(2, minmax(0, 1fr)); } .auth { width:100%; } }
  </style>
</head>
<body>
  <header><div class="wrap top"><h1>Gateway Dashboard</h1><form class="auth" id="auth"><input id="key" type="password" autocomplete="current-password" placeholder="Gateway API key"><button type="submit">Refresh</button></form></div></header>
  <main class="wrap">
    <section class="wide"><div class="stats" id="stats"></div><p class="muted" id="message"></p></section>
    <section><h2>Providers</h2><table><thead><tr><th>Provider</th><th>Accounts</th><th>Active</th><th>Supported endpoints</th></tr></thead><tbody id="providers"></tbody></table></section>
    <section><h2>Available Models</h2><table><thead><tr><th>Model</th><th>Provider</th><th>Context</th><th>Supported endpoints</th></tr></thead><tbody id="models"></tbody></table></section>
  </main>
  <script>
    const keyInput = document.querySelector("#key");
    const form = document.querySelector("#auth");
    const stats = document.querySelector("#stats");
    const providers = document.querySelector("#providers");
    const models = document.querySelector("#models");
    const message = document.querySelector("#message");
    // Keep this origin-relative so the dashboard works on any deployed host.
    const dashboardDataPath = "/dashboard/data";
    keyInput.value = sessionStorage.getItem("gatewayKey") || "";
    function cell(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
    }
    function gatewayLabel(model) {
      return model.gateway || ((model.id || "").startsWith("opencode-go/") ? "opencode-go" : "codex");
    }
    function stat(label, value) { return `<div class="stat"><div class="label">${label}</div><div class="value">${cell(value)}</div></div>`; }
    async function load() {
      const key = keyInput.value.trim();
      if (!key) { message.textContent = "Enter the gateway API key to load live data."; return; }
      sessionStorage.setItem("gatewayKey", key);
      message.textContent = "Loading...";
      const res = await fetch(dashboardDataPath, { headers: { "X-Gateway-Key": key } });
      if (!res.ok) { message.textContent = `Could not load dashboard data (${res.status}).`; return; }
      const data = await res.json();
      const gatewayRows = Array.isArray(data.gateways) ? data.gateways : [];
      const providerRows = Array.isArray(data.providers) ? data.providers : [];
      const modelRows = Array.isArray(data.models) ? data.models : [];
      const active = gatewayRows.filter(g => g.active).length;
      stats.innerHTML = stat("Accounts", gatewayRows.length) + stat("Active", active) + stat("Models", modelRows.length) + stat("Strategy", data.status?.strategy || "");
      providers.innerHTML = providerRows.map(p => `<tr><td>${cell(p.id)}</td><td>${cell(p.accounts)}</td><td>${cell(p.active_accounts)}</td><td>${cell((p.supported_endpoints || []).join(", "))}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">No providers configured</td></tr>`;
      models.innerHTML = modelRows.map(m => `<tr><td>${cell(m.id)}</td><td>${cell(gatewayLabel(m))}</td><td>${cell(m.context_window || m.max_context_window || "")}</td><td>${cell((m.supported_endpoints || []).join(", "))}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">No models available</td></tr>`;
      message.className = data.model_error ? "error" : "muted";
      message.textContent = data.model_error || `Last updated ${new Date().toLocaleTimeString()}`;
    }
    form.addEventListener("submit", event => { event.preventDefault(); load().catch(err => { message.textContent = err.message; }); });
    if (keyInput.value) load().catch(err => { message.textContent = err.message; });
  </script>
</body>
</html>"""


async def _passthrough_error(acct_id: str, upstream: httpx.Response) -> Response:
    content = await upstream.aread()
    await upstream.aclose()
    return Response(
        content=content, status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
        headers={"X-Gateway-Account": acct_id},
    )


async def _open(proxy: CodexProxy, responses_body: dict):
    """Open an upstream stream, mapping router errors to HTTP responses."""
    try:
        acct, upstream = await proxy.open_stream(responses_body)
        return acct, upstream, None
    except NoAccountAvailable as exc:
        return None, None, _error(503, str(exc), "no_account_available")
    except AllAccountsFailed as exc:
        return None, None, _error(exc.status_code, exc.detail, "upstream_unavailable")


# --------------------------------------------------------------------------- #
# Operational endpoints
# --------------------------------------------------------------------------- #

@app.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    s = request.app.state
    return HealthResponse(
        status="ok", version=__version__,
        redis="ok" if await s.quota.ping() else "down",
        accounts=len(s.router.accounts()), strategy=s.settings.strategy,
    )


@app.get("/admin/status", response_model=StatusResponse,
         dependencies=[Depends(require_master_key)])
async def admin_status(request: Request) -> StatusResponse:
    s = request.app.state
    rows = []
    for acct in s.router.accounts():
        rows.append(AccountStatus(
            id=acct.id, provider=getattr(acct, "provider", "codex"),
            account_id=acct.account_id, plan=acct.plan,
            access_token=acct.masked_token(), expires_at=acct.expires_at(),
            used_today=await s.quota.used_today(acct.id),
            cooling_down=await s.quota.is_cooling_down(acct.id),
        ))
    return StatusResponse(strategy=s.settings.strategy, accounts=rows)


@app.api_route("/admin/accounts/{account_id}", methods=["PUT", "POST"],
               dependencies=[Depends(require_master_key)])
async def upload_account(account_id: str, request: Request) -> Response:
    """Upload (create/replace) a Codex auth.json for ``account_id``.

    Body is the raw auth.json. Hot-loaded into the router — no restart needed.
    """
    s = request.app.state
    if not valid_account_id(account_id):
        return _error(400, "invalid account id: use letters, digits, '.', '_', '-'",
                      "invalid_account_id", "invalid_request_error")
    try:
        data = json.loads(await request.body())
    except (json.JSONDecodeError, ValueError):
        return _error(400, "body must be a Codex auth.json (valid JSON)",
                      "invalid_json", "invalid_request_error")
    if not isinstance(data, dict):
        return _error(400, "auth.json must be a JSON object", "invalid_auth_file",
                      "invalid_request_error")
    try:
        acct = save_account_file(s.settings, account_id, data)
    except CredentialError as exc:
        return _error(400, str(exc), "invalid_auth_file", "invalid_request_error")
    replaced = s.router.add_account(acct)
    log.info("account %s %s via API", account_id, "replaced" if replaced else "added")
    return JSONResponse(status_code=200 if replaced else 201, content={
        "status": "ok", "account": account_id, "replaced": replaced,
        "provider": getattr(acct, "provider", "codex"),
        "account_id": acct.account_id, "plan": acct.plan, "expires_at": acct.expires_at(),
    })


@app.delete("/admin/accounts/{account_id}", dependencies=[Depends(require_master_key)])
async def delete_account(account_id: str, request: Request) -> Response:
    """Delete an account: drop it from the router and remove its auth.json."""
    s = request.app.state
    if not valid_account_id(account_id):
        return _error(400, "invalid account id", "invalid_account_id", "invalid_request_error")
    removed_mem = s.router.remove_account(account_id)
    removed_file = delete_account_file(s.settings, account_id)
    if not (removed_mem or removed_file):
        return _error(404, f"no account '{account_id}'", "account_not_found")
    log.info("account %s deleted via API", account_id)
    return JSONResponse({"status": "ok", "account": account_id, "deleted": True})


@app.post("/admin/accounts/{account_id}/login/device", dependencies=[Depends(require_master_key)])
async def start_device_login(account_id: str, request: Request) -> Response:
    if not valid_account_id(account_id):
        return _error(400, "invalid account id", "invalid_account_id", "invalid_request_error")
    try:
        login = await request.app.state.device_logins.start(account_id)
    except FileNotFoundError:
        return _error(503, "Codex login support is not installed", "codex_unavailable")
    if login.status == "failed":
        return _error(502, login.error or "could not start device login", "login_start_failed")
    return JSONResponse(status_code=201, content={
        "id": login.id, "account_id": account_id, "status": login.status,
        "verification_url": login.verification_url, "user_code": login.user_code,
    })


@app.get("/admin/logins/{login_id}", dependencies=[Depends(require_master_key)])
async def device_login_status(login_id: str, request: Request) -> Response:
    login = request.app.state.device_logins.get(login_id)
    if not login:
        return _error(404, "login not found", "login_not_found")
    return JSONResponse({"id": login.id, "account_id": login.account_id, "status": login.status,
                         "verification_url": login.verification_url, "user_code": login.user_code,
                         "error": login.error})


@app.post("/v1/admin/opencode-go/keys", dependencies=[Depends(require_master_key)])
async def add_opencode_go_key(payload: OpenCodeGoKeyCreate, request: Request) -> Response:
    """Persist and hot-load an OpenCode Go subscription API key.

    Credentials use the existing account-file storage so a key added here is
    available after a restart. Supplying an existing ``identifier`` replaces
    that key; omitting it creates a generated identifier.
    """
    s = request.app.state
    account_id = payload.identifier or f"opencode-go-{uuid4().hex}"
    if not valid_account_id(account_id):
        return _error(400, "invalid identifier: use letters, digits, '.', '_', '-'",
                      "invalid_account_id", "invalid_request_error")

    data = {"type": "opencode-go", "api_key": payload.api_key}
    if payload.label:
        data["label"] = payload.label
    try:
        acct = save_account_file(s.settings, account_id, data)
    except CredentialError as exc:
        return _error(400, str(exc), "invalid_api_key", "invalid_request_error")

    replaced = s.router.add_account(acct)
    log.info("OpenCode Go key %s %s via API", account_id, "replaced" if replaced else "added")
    return JSONResponse(status_code=200 if replaced else 201, content={
        "status": "ok",
        "id": account_id,
        "label": payload.label,
        "replaced": replaced,
        "provider": "opencode-go",
    })


@app.get("/v1/models", dependencies=[Depends(require_master_key)])
async def list_models(request: Request) -> Response:
    # Live catalog fetched from the Codex backend (cached), never hardcoded.
    try:
        return JSONResponse(await request.app.state.catalog.openai_list())
    except ModelCatalogError as exc:
        return _error(502, f"could not fetch models: {exc}", "models_unavailable")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> Response:
    index = WEB_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(_dashboard_html())


# The built console loads its bundle from /assets/*. Without this mount the page
# renders an empty root element. Absent in dev, where the fallback HTML is used.
if (WEB_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.post("/dashboard/auth/check", status_code=204, dependencies=[Depends(require_master_key)])
async def dashboard_auth_check() -> Response:
    """Validate the dashboard token without loading account or model data."""
    return Response(status_code=204)


@app.get("/dashboard/data", dependencies=[Depends(require_master_key)])
async def dashboard_data(request: Request) -> Response:
    s = request.app.state
    try:
        catalog = await s.catalog.openai_list()
        model_error = None
    except ModelCatalogError as exc:
        catalog = {"object": "list", "data": []}
        model_error = str(exc)

    # Normalize the catalog at this boundary so the browser always receives
    # arrays and JSON primitives, even if a catalog implementation is swapped.
    raw_models = catalog.get("data", []) if isinstance(catalog, dict) else []
    models = [_dashboard_model(model) for model in raw_models if isinstance(model, dict)]
    gateways = []
    for acct in s.router.accounts():
        gateways.append({
            "id": acct.id,
            "provider": getattr(acct, "provider", "codex"),
            "plan": acct.plan,
            "active": not await s.quota.is_cooling_down(acct.id),
            "used_today": await s.quota.used_today(acct.id),
        })
    providers = _dashboard_providers(gateways, models)
    return JSONResponse({
        "status": {"strategy": s.settings.strategy, "accounts": gateways},
        "models": models,
        "model_error": model_error,
        "gateways": gateways,
        "providers": providers,
    })


def _dashboard_model(model: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe model row with endpoint capability information."""
    row = dict(model)
    model_id = str(row.get("id") or "")
    provider = row.get("gateway") or ("opencode-go" if is_opencode_go_model(model_id) else "codex")
    row["gateway"] = provider
    endpoints = row.get("supported_endpoints")
    if not isinstance(endpoints, list) or not all(isinstance(item, str) for item in endpoints):
        if provider == "opencode-go":
            upstream_id = strip_opencode_go_model(model_id) if is_opencode_go_model(model_id) else model_id
            endpoints = [OPENCODE_GO_MESSAGES_ENDPOINT if upstream_id in OPENCODE_GO_MESSAGES_MODELS else OPENCODE_GO_CHAT_ENDPOINT]
        else:
            endpoints = list(CODEX_SUPPORTED_ENDPOINTS)
    row["supported_endpoints"] = endpoints
    return row


def _dashboard_providers(gateways: list[dict[str, Any]], models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate account state and model capabilities into stable provider rows."""
    grouped: dict[str, dict[str, Any]] = {}
    for gateway in gateways:
        provider = str(gateway["provider"])
        row = grouped.setdefault(provider, {
            "id": provider, "accounts": 0, "active_accounts": 0, "supported_endpoints": set(),
        })
        row["accounts"] += 1
        row["active_accounts"] += int(bool(gateway["active"]))
        if provider == "codex":
            row["supported_endpoints"].update(CODEX_SUPPORTED_ENDPOINTS)
        elif provider == "opencode-go":
            # Go's documented API is split by model family; individual model
            # rows below identify the exact endpoint to call.
            row["supported_endpoints"].update((OPENCODE_GO_CHAT_ENDPOINT, OPENCODE_GO_MESSAGES_ENDPOINT))
    for model in models:
        provider = str(model["gateway"])
        row = grouped.setdefault(provider, {
            "id": provider, "accounts": 0, "active_accounts": 0, "supported_endpoints": set(),
        })
        row["supported_endpoints"].update(model["supported_endpoints"])
    return [
        {**row, "supported_endpoints": sorted(row["supported_endpoints"])}
        for _, row in sorted(grouped.items())
    ]


# --------------------------------------------------------------------------- #
# Chat Completions  (translated to/from the Responses API)
# --------------------------------------------------------------------------- #

@app.post("/v1/chat/completions", dependencies=[Depends(require_master_key)])
async def chat_completions(request: Request, payload: ChatCompletionRequest) -> Response:
    s = request.app.state
    settings = s.settings
    # exclude_unset keeps only what the client actually sent (incl. extra fields),
    # so we never inject defaults/nulls into the upstream request.
    chat = payload.model_dump(exclude_unset=True)

    model = chat.get("model") or settings.default_model
    if not model:
        try:
            model = await s.catalog.default_model()
        except ModelCatalogError:
            model = None
        if not model:
            return _error(400, "no 'model' specified and no default could be resolved",
                          "model_required", "invalid_request_error")
    stream = bool(chat.get("stream"))
    responses_body = chat_to_responses(chat, model, settings.default_instructions)
    chat_id = new_chat_id()

    log.info("chat/completions model=%s stream=%s", model, stream)

    if is_opencode_go_model(model):
        return await _serve_opencode_go_chat(request, s, chat, model, stream)

    if stream:
        acct, upstream, err = await _open(s.proxy, responses_body)
        if err:
            return err
        if upstream.status_code >= 400:
            return await _passthrough_error(acct.id, upstream)

        async def gen():
            events = iter_sse(upstream.aiter_bytes())
            try:
                async for chunk in responses_sse_to_chat_sse(events, model, chat_id):
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Gateway-Account": acct.id})

    # Non-streaming: aggregate upstream SSE, translate, with optional dedup.
    def transform(final: dict) -> bytes:
        chat_resp = responses_to_chat(final, model, chat_id)
        msg = chat_resp["choices"][0]["message"]
        if msg.get("content") is None and not msg.get("tool_calls"):
            log.warning("empty assistant content; upstream output item types=%s",
                        [it.get("type") for it in final.get("output", [])])
        return json.dumps(chat_resp).encode()

    return await _serve_nonstream(request, s, responses_body, transform)


# --------------------------------------------------------------------------- #
# Responses API  (passthrough)
# --------------------------------------------------------------------------- #

@app.post("/v1/messages", dependencies=[Depends(require_master_key)])
async def messages(request: Request) -> Response:
    """Proxy OpenCode Go's Anthropic-compatible Messages endpoint.

    OpenCode Go documents this surface only for a subset of its models. Models
    retain the ``opencode-go/`` prefix at the gateway boundary so they cannot
    be accidentally sent to a Codex account.
    """
    try:
        body = json.loads(await request.body())
    except (json.JSONDecodeError, ValueError):
        return _error(400, "body must be a JSON object", "invalid_json", "invalid_request_error")
    if not isinstance(body, dict):
        return _error(400, "body must be a JSON object", "invalid_request", "invalid_request_error")
    model = body.get("model")
    if not is_opencode_go_model(model):
        return _error(
            400,
            "only OpenCode Go models are supported by /v1/messages",
            "unsupported_endpoint",
            "invalid_request_error",
        )
    if strip_opencode_go_model(model) not in OPENCODE_GO_MESSAGES_MODELS:
        return _error(
            400,
            f"{model} does not support /v1/messages; use /v1/chat/completions",
            "unsupported_endpoint",
            "invalid_request_error",
        )
    return await _serve_opencode_go_messages(request.app.state, body)

@app.post("/v1/responses", dependencies=[Depends(require_master_key)])
async def responses(request: Request, payload: ResponsesRequest) -> Response:
    s = request.app.state
    rbody = payload.model_dump(exclude_unset=True)
    if is_opencode_go_model(rbody.get("model")):
        return _error(
            400,
            "OpenCode Go models support /v1/chat/completions through this gateway",
            "unsupported_endpoint",
            "invalid_request_error",
        )

    client_stream = bool(rbody.get("stream"))
    rbody["stream"] = True          # the Codex backend always streams
    rbody.setdefault("store", False)

    log.info("responses model=%s stream=%s", rbody.get("model"), client_stream)

    if client_stream:
        acct, upstream, err = await _open(s.proxy, rbody)
        if err:
            return err
        if upstream.status_code >= 400:
            return await _passthrough_error(acct.id, upstream)

        async def gen():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Gateway-Account": acct.id})

    return await _serve_nonstream(request, s, rbody, lambda final: json.dumps(final).encode())


async def _serve_opencode_go_chat(
    request: Request, s, chat: dict, model: str, stream: bool
) -> Response:
    body = dict(chat)
    body["model"] = model
    body["stream"] = stream

    if stream:
        try:
            acct, upstream = await s.opencode_go_proxy.open_chat(body)
        except NoAccountAvailable as exc:
            return _error(503, str(exc), "no_account_available")
        except AllAccountsFailed as exc:
            return _error(exc.status_code, exc.detail, "upstream_unavailable")
        if upstream.status_code >= 400:
            return await _passthrough_error(acct.id, upstream)

        async def gen():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Gateway-Account": acct.id})

    return await _serve_opencode_go_nonstream(request, s, body)


async def _serve_opencode_go_messages(s, body: dict) -> Response:
    try:
        acct, upstream = await s.opencode_go_proxy.open_messages(body)
    except NoAccountAvailable as exc:
        return _error(503, str(exc), "no_account_available")
    except AllAccountsFailed as exc:
        return _error(exc.status_code, exc.detail, "upstream_unavailable")
    if upstream.status_code >= 400:
        return await _passthrough_error(acct.id, upstream)

    if body.get("stream"):
        async def gen():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Gateway-Account": acct.id})

    content = await upstream.aread()
    media_type = upstream.headers.get("content-type", "application/json")
    await upstream.aclose()
    return Response(content=content, status_code=upstream.status_code, media_type=media_type,
                    headers={"X-Gateway-Account": acct.id})


async def _serve_opencode_go_nonstream(request: Request, s, body: dict) -> Response:
    dedup: DedupStore = s.dedup
    idem_key = request.headers.get("idempotency-key")
    use_dedup = s.settings.dedup_enabled and bool(idem_key)

    if use_dedup:
        try:
            cached = await dedup.begin(idem_key)
        except DuplicateInFlight as exc:
            return _error(409, str(exc), "duplicate_in_flight", "gateway_duplicate_request")
        if cached is not None:
            return Response(content=cached.body, status_code=cached.status_code,
                            media_type="application/json",
                            headers={"X-Gateway-Account": cached.account_id, "X-Gateway-Dedup": "hit"})

    try:
        acct, upstream = await s.opencode_go_proxy.open_chat(body)
    except NoAccountAvailable as exc:
        if use_dedup:
            await dedup.release(idem_key)
        return _error(503, str(exc), "no_account_available")
    except AllAccountsFailed as exc:
        if use_dedup:
            await dedup.release(idem_key)
        return _error(exc.status_code, exc.detail, "upstream_unavailable")

    content = await upstream.aread()
    status_code = upstream.status_code
    media_type = upstream.headers.get("content-type", "application/json")
    await upstream.aclose()
    if status_code >= 400:
        if use_dedup:
            await dedup.release(idem_key)
        return Response(content=content, status_code=status_code, media_type=media_type,
                        headers={"X-Gateway-Account": acct.id})
    if use_dedup:
        await dedup.complete(idem_key, status_code, content, acct.id)
    return Response(content=content, status_code=status_code, media_type=media_type,
                    headers={"X-Gateway-Account": acct.id})


# --------------------------------------------------------------------------- #
# Shared non-streaming path (aggregate + dedup)
# --------------------------------------------------------------------------- #

async def _serve_nonstream(
    request: Request, s, responses_body: dict, transform: Callable[[dict], bytes]
) -> Response:
    settings = s.settings
    dedup: DedupStore = s.dedup
    idem_key = request.headers.get("idempotency-key")
    use_dedup = settings.dedup_enabled and bool(idem_key)

    if use_dedup:
        try:
            cached = await dedup.begin(idem_key)
        except DuplicateInFlight as exc:
            return _error(409, str(exc), "duplicate_in_flight", "gateway_duplicate_request")
        if cached is not None:
            return Response(content=cached.body, status_code=cached.status_code,
                            media_type="application/json",
                            headers={"X-Gateway-Account": cached.account_id, "X-Gateway-Dedup": "hit"})

    acct, upstream, err = await _open(s.proxy, responses_body)
    if err:
        if use_dedup:
            await dedup.release(idem_key)
        return err

    if upstream.status_code >= 400:
        if use_dedup:
            await dedup.release(idem_key)
        return await _passthrough_error(acct.id, upstream)

    try:
        final = await aggregate_response(iter_sse(upstream.aiter_bytes()))
    except UpstreamError as exc:
        if use_dedup:
            await dedup.release(idem_key)
        return _error(502, f"upstream error: {exc}", "upstream_error")
    finally:
        await upstream.aclose()

    body = transform(final)
    if use_dedup:
        await dedup.complete(idem_key, 200, body, acct.id)
    return Response(content=body, status_code=200, media_type="application/json",
                    headers={"X-Gateway-Account": acct.id})
