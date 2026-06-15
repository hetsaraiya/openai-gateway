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
from typing import Callable

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

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
from .model_catalog import ModelCatalog, ModelCatalogError
from .models import (
    AccountStatus,
    ChatCompletionRequest,
    HealthResponse,
    ResponsesRequest,
    StatusResponse,
)
from .observability import configure_logging, log_access, new_request_id, request_id_var
from .proxy import AllAccountsFailed, CodexProxy
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
    catalog = ModelCatalog(settings, router, client)

    app.state.settings = settings
    app.state.router = router
    app.state.quota = quota
    app.state.dedup = dedup
    app.state.proxy = proxy
    app.state.catalog = catalog
    app.state.client = client

    redis_ok = await quota.ping()
    log.info(
        "gateway up: %d Codex accounts, strategy=%s, redis=%s",
        len(accounts), settings.strategy, "ok" if redis_ok else "DOWN",
    )
    try:
        yield
    finally:
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
            id=acct.id, account_id=acct.account_id, plan=acct.plan,
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


@app.get("/v1/models", dependencies=[Depends(require_master_key)])
async def list_models(request: Request) -> Response:
    # Live catalog fetched from the Codex backend (cached), never hardcoded.
    try:
        return JSONResponse(await request.app.state.catalog.openai_list())
    except ModelCatalogError as exc:
        return _error(502, f"could not fetch models: {exc}", "models_unavailable")


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

@app.post("/v1/responses", dependencies=[Depends(require_master_key)])
async def responses(request: Request, payload: ResponsesRequest) -> Response:
    s = request.app.state
    rbody = payload.model_dump(exclude_unset=True)

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
