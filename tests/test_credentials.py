import json

import httpx

from app import jwt_util
from app.credentials import CodexAccount, load_accounts
from tests.conftest import make_account, make_jwt, make_settings


def test_account_id_falls_back_to_id_token(tmp_path):
    acct = make_account(tmp_path, "a", account_id=None)
    # account_id field defaults to "a"; ensure id_token claim path also works.
    data = json.loads(acct.path.read_text())
    data["tokens"]["account_id"] = None
    data["tokens"]["id_token"] = make_jwt(
        {"https://api.openai.com/auth": {"chatgpt_account_id": "from-id-token"}})
    acct2 = CodexAccount(acct.path, data, make_settings())
    assert acct2.account_id == "from-id-token"


async def test_ensure_fresh_refreshes_expired_token(tmp_path):
    settings = make_settings()
    acct = make_account(tmp_path, "a", exp_offset=-10, settings=settings)  # already expired
    new_access = make_jwt({"exp": 9999999999})
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={
            "access_token": new_access,
            "refresh_token": "refresh-rotated",
            "id_token": make_jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "a"}}),
            "expires_in": 3600,
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await acct.ensure_fresh(client)
    finally:
        await client.aclose()

    # Token rotated in memory...
    assert acct.access_token == new_access
    assert acct.refresh_token == "refresh-rotated"
    # ...and persisted to disk.
    persisted = json.loads(acct.path.read_text())
    assert persisted["tokens"]["access_token"] == new_access
    # Correct OAuth call shape.
    assert captured["url"] == settings.oauth_token_url
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["client_id"] == settings.oauth_client_id


async def test_ensure_fresh_noop_when_valid(tmp_path):
    acct = make_account(tmp_path, "a", exp_offset=3600)  # valid for an hour

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not refresh a valid token")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await acct.ensure_fresh(client)  # must not call the token endpoint
    finally:
        await client.aclose()


def test_load_accounts_reads_directory(tmp_path):
    make_account(tmp_path, "a")
    make_account(tmp_path, "b")
    (tmp_path / "broken.json").write_text("{ not json")
    accounts = load_accounts(make_settings(auth_dir=str(tmp_path)))
    assert sorted(a.id for a in accounts) == ["a", "b"]


def test_jwt_decode_payload():
    tok = make_jwt({"exp": 123, "foo": "bar"})
    assert jwt_util.decode_payload(tok)["foo"] == "bar"
    assert jwt_util.expiry(tok) == 123


def test_save_and_delete_account_file(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path))
    data = json.loads(make_account(tmp_path, "tmpseed").path.read_text())
    (tmp_path / "tmpseed.json").unlink()  # start clean
    from app.credentials import save_account_file, delete_account_file, valid_account_id
    acct = save_account_file(settings, "newacct", data)
    assert acct.id == "newacct"
    assert (tmp_path / "newacct.json").exists()
    assert oct((tmp_path / "newacct.json").stat().st_mode)[-3:] == "600"
    assert delete_account_file(settings, "newacct") is True
    assert not (tmp_path / "newacct.json").exists()
    assert delete_account_file(settings, "newacct") is False


def test_save_account_rejects_bad_id_and_shape(tmp_path):
    from app.credentials import save_account_file, valid_account_id
    from app.credentials import CredentialError
    settings = make_settings(auth_dir=str(tmp_path))
    assert valid_account_id("ok-1.2_x") and not valid_account_id("../evil")
    import pytest
    good = json.loads(make_account(tmp_path, "seed2").path.read_text())
    with pytest.raises(CredentialError):
        save_account_file(settings, "../evil", good)
    with pytest.raises(CredentialError):
        save_account_file(settings, "missingtokens", {"tokens": {}})
