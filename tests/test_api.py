"""HTTP surface: authentication, and that nothing writable is reachable without it."""

from dataclasses import replace

import pytest
from starlette.testclient import TestClient

from app import api
from app.api import asset_version, create_app

PASSWORD = "test-password"  # matches the settings fixture


@pytest.fixture
def client(settings, build_app):
    # An app of its own, with its own database. No lifespan is entered, so the
    # Bluetooth collectors never start.
    return TestClient(build_app(settings))


@pytest.fixture
def signed_in(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    return client


# --- authentication --------------------------------------------------------

def test_login_rejects_the_wrong_password(client):
    response = client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 401


def test_login_accepts_the_right_password_and_establishes_a_session(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json() == {"authenticated": True}


def test_a_non_ascii_password_works(settings, build_app):
    """hmac.compare_digest raises TypeError on non-ASCII str; bytes avoid that."""
    unicode_password = "pärolă-über-✓"
    client = TestClient(build_app(replace(settings, admin_password=unicode_password)))
    assert client.post(
        "/api/auth/login", json={"password": unicode_password}).status_code == 200
    assert client.post(
        "/api/auth/login", json={"password": "wrong-päss"}).status_code == 401


def test_logout_ends_the_session(signed_in):
    signed_in.post("/api/auth/logout")
    assert signed_in.get("/api/auth/me").json() == {"authenticated": False}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/status"),
        ("get", "/api/history"),
        ("post", "/api/refresh"),
        ("post", "/api/control/ac_ports"),
        ("post", "/api/control/charger_open"),
    ],
)
def test_every_data_and_control_route_requires_a_session(client, method, path):
    call = getattr(client, method)
    response = call(path, json={"value": True}) if method == "post" else call(path)
    assert response.status_code == 401


# --- control surface -------------------------------------------------------

def test_unknown_control_is_rejected_without_touching_bluetooth(signed_in):
    response = signed_in.post("/api/control/nonsense", json={"value": True})
    assert response.status_code == 404
    assert "not a controllable setting" in response.json()["detail"]


@pytest.mark.parametrize("name", ["disable_grid_bypass", "power_max", "battery_level"])
def test_read_only_fields_are_not_writable_over_http(signed_in, name):
    assert signed_in.post(f"/api/control/{name}", json={"value": 1}).status_code == 404


def test_control_requires_a_value(signed_in):
    assert signed_in.post("/api/control/ac_ports", json={}).status_code == 422


def test_unknown_device_is_rejected(signed_in):
    assert signed_in.get("/api/history?device=bogus").status_code == 404


# --- public surface --------------------------------------------------------

def test_health_needs_no_session_and_names_both_devices(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert set(body["collectors"]) == {"delta2", "alternator"}


def test_index_is_served_with_versioned_assets_and_no_cache(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "__ASSETS__" not in response.text, "the version placeholder must be filled"
    assert f"js/main.js?v={asset_version()}" in response.text


def test_asset_version_tracks_content_not_timestamps(tmp_path, monkeypatch):
    before = asset_version()
    # A nested module, to prove the hash reaches into static/js/.
    target = api.STATIC_DIR / "js" / "format.js"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n// touched by a test\n")
        assert asset_version() != before, "an edit must bust the cache"
    finally:
        target.write_bytes(original)
    # Rewriting identical bytes changes the mtime but not the content, and must
    # therefore not invalidate anything.
    assert asset_version() == before


def test_an_unconfigured_app_refuses_to_sign_anyone_in(unconfigured, build_app):
    """The original failure: an empty session secret returned 503 for every login."""
    client = TestClient(build_app(unconfigured))
    response = client.post("/api/auth/login", json={"password": "anything"})
    assert response.status_code == 503
    assert "APP_SESSION_SECRET" in response.json()["detail"]


def test_two_apps_do_not_share_state(settings, build_app):
    """The point of the factory: no module-level singletons."""
    first = build_app(settings, "a.sqlite3")
    second = build_app(settings, "b.sqlite3")
    assert first.state.collectors is not second.state.collectors
    assert (
        first.state.collectors["delta2"].store.connection
        is not second.state.collectors["delta2"].store.connection
    )


def test_static_files_must_be_revalidated(client):
    """ES module imports carry no version query, so they must not be assumed fresh."""
    response = client.get("/static/js/format.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_the_page_loads_the_module_entry_point(client):
    assert 'type="module"' in client.get("/").text


# --- login rate limiting ---------------------------------------------------

def test_repeated_wrong_passwords_are_locked_out(client):
    """Unlimited guessing against one password is the weakest point in the system."""
    guard = client.app.state.login_guard
    for _ in range(guard.allowance):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401

    # One more tips it over.
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    locked = client.post("/api/auth/login", json={"password": "wrong"})
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers
    assert int(locked.headers["Retry-After"]) > 0


def test_a_lockout_also_refuses_the_correct_password(client):
    """Otherwise the lockout could be used as an oracle."""
    guard = client.app.state.login_guard
    for _ in range(guard.allowance + 2):
        client.post("/api/auth/login", json={"password": "wrong"})
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429


def test_signing_in_successfully_clears_the_failures(client):
    guard = client.app.state.login_guard
    for _ in range(guard.allowance):
        client.post("/api/auth/login", json={"password": "wrong"})
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    # The counter is reset, so the allowance is whole again.
    for _ in range(guard.allowance):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401


# --- gateway and server are the same code in different roles ---------------

def test_a_server_app_needs_no_bluetooth_libraries(settings, tmp_path, monkeypatch):
    """The remote server receives JSON. It must not need bleak to do that."""
    import sys

    class Blocker:
        def find_module(self, name, path=None):
            if name.split(".")[0] in {"bleak", "bleak_retry_connector", "bluetooth_adapters"}:
                return self

        def load_module(self, name):
            raise ImportError(f"{name} is not installed on this host")

    monkeypatch.setattr(sys, "meta_path", [Blocker(), *sys.meta_path])
    application = create_app(
        settings=settings, database_path=tmp_path / "s.sqlite3", collect=False
    )
    try:
        assert application.state.collects is False
        assert application.state.collectors == {}
        assert application.state.manager is None
        assert sorted(application.state.stores) == ["alternator", "delta2"]
    finally:
        for store in application.state.stores.values():
            store.close()


def test_a_gateway_app_owns_the_collectors(settings, build_app):
    application = build_app(settings)
    assert application.state.collects is True
    assert sorted(application.state.collectors) == ["alternator", "delta2"]
    assert application.state.manager is not None
