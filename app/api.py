"""The HTTP surface, and the factory that wires the application together.

`create_app` builds its own settings, stores and collectors, so an isolated instance
can be constructed for a test without touching the real database or the real radio.
Routes reach their collaborators through `request.app.state` rather than globals.
"""

import asyncio
import hashlib
import hmac
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .config import STATIC_DIR, Settings, default_database_path
from .devices import DELTA2, DEVICE_KINDS
from .security import LoginGuard
from .storage import TelemetryStore

if TYPE_CHECKING:  # importing these for real would pull in bleak
    from .collector import DeviceCollector

router = APIRouter()


class RevalidatedStatics(StaticFiles):
    """Static files that must be revalidated rather than assumed fresh.

    The page's own URL carries a version, but the ES modules it imports do not -
    `import "./format.js"` has no query string to version. Without this the browser
    would serve a cached copy of an edited module against a fresh entry point.
    Revalidation is cheap: unchanged files answer 304 on their ETag.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return super().is_not_modified(response_headers, request_headers)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


class LoginRequest(BaseModel):
    password: str


class ControlRequest(BaseModel):
    value: Any




def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _collectors(request: Request) -> "dict[str, DeviceCollector]":
    return request.app.state.collectors


def _collector(request: Request, key: str) -> "DeviceCollector":
    found = _collectors(request).get(key)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown device '{key}'.")
    return found


def require_login(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Sign in required.")


def asset_version() -> str:
    """A token that changes whenever the content of static/ changes.

    Hashing content rather than modification times means restoring a file, checking
    out the same revision or copying the tree does not invalidate a cache for no
    reason - only a genuine edit does.

    The dashboard is edited in place and left open in a long-lived browser tab.
    Without a versioned URL the browser keeps serving app.js and styles.css from
    its own cache long after the file on disk changed.
    """
    digest = hashlib.sha256()
    # rglob, not iterdir: the JavaScript lives in static/js/.
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(STATIC_DIR)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@router.get("/")
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text()
    return HTMLResponse(
        html.replace("__ASSETS__", asset_version()),
        # The page carries the version, so it must never be a stale copy itself.
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": asset_version(),
        "collectors": {key: item.state for key, item in _collectors(request).items()},
    }


@router.get("/api/auth/me")
async def current_user(request: Request) -> dict[str, bool]:
    return {"authenticated": bool(request.session.get("authenticated"))}


def _source(request: Request) -> str:
    """Who is knocking.

    `request.client.host` is the immediate peer. Behind a reverse proxy that is the
    proxy itself, so every caller would share one bucket; trusting a forwarded header
    instead would let anyone forge their identity. Fix this by configuring the proxy
    and Uvicorn's `--forwarded-allow-ips` together, not by reading the header here.
    """
    return request.client.host if request.client else "unknown"


@router.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, bool]:
    settings = _settings(request)
    if not settings.dashboard_ready:
        raise HTTPException(
            status_code=503,
            detail="Set APP_ADMIN_PASSWORD and APP_SESSION_SECRET first.",
        )

    guard: LoginGuard = request.app.state.login_guard
    source = _source(request)
    now = time.time()

    wait = guard.retry_after(source, now)
    if wait:
        seconds = guard.seconds_to_report(wait)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )

    if not hmac.compare_digest(
        payload.password.encode("utf-8"), settings.admin_password.encode("utf-8")
    ):
        guard.record_failure(source, now)
        raise HTTPException(status_code=401, detail="Incorrect password.")

    guard.record_success(source)
    request.session["authenticated"] = True
    return {"authenticated": True}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    request.session.clear()
    response.delete_cookie("session")
    return {"authenticated": False}


@router.get("/api/status")
async def status(request: Request) -> dict[str, Any]:
    require_login(request)
    return {"devices": {key: item.status() for key, item in _collectors(request).items()}}


@router.get("/api/history")
async def history(request: Request, device: str = DELTA2.key) -> dict[str, Any]:
    require_login(request)
    return {"items": _collector(request, device).store.history()}


@router.post("/api/refresh")
async def refresh(request: Request, device: str = DELTA2.key) -> dict[str, Any]:
    require_login(request)
    target = _collector(request, device)
    try:
        await target.refresh()
    except Exception as error:
        # Anything from "not configured" to a Bluetooth timeout ends up here; the
        # dashboard shows the message, so report it rather than a bare 500.
        target.failed(error, asyncio.get_running_loop().time())
        raise HTTPException(status_code=409, detail=str(error)) from error
    target.succeeded()
    return target.status()


@router.post("/api/control/{control}")
async def set_control(control: str, payload: ControlRequest, request: Request) -> dict[str, Any]:
    require_login(request)
    owner = next(
        (item for item in _collectors(request).values() if control in item.kind.controls), None
    )
    if owner is None:
        raise HTTPException(
            status_code=404, detail=f"'{control}' is not a controllable setting."
        )
    try:
        confirmed = await owner.set_control(control, payload.value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"confirmed": confirmed, **owner.status()}


def create_app(
    settings: Settings | None = None,
    database_path: Path | None = None,
    *,
    collect: bool = True,
) -> FastAPI:
    """Build the application.

    `collect=True` is the gateway in the van: it owns the Bluetooth radio and polls
    the hardware. `collect=False` is the remote server, which only ever holds what a
    gateway sent it - and which must never need `bleak` installed, hence the import
    living inside this branch rather than at the top of the module.
    """
    settings = settings or Settings.from_environment()
    database_path = database_path or default_database_path()
    stores = {kind.key: TelemetryStore(database_path, kind) for kind in DEVICE_KINDS.values()}

    collectors: dict[str, Any] = {}
    manager = None
    if collect:
        from .collector import DeviceCollector
        from .manager import CollectorManager

        # One lock for the Bluetooth radio, shared by every collector.
        radio_lock = asyncio.Lock()
        collectors = {
            kind.key: DeviceCollector(kind, settings, stores[kind.key], radio_lock)
            for kind in DEVICE_KINDS.values()
        }
        manager = CollectorManager(settings, collectors)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if manager:
            await manager.start()
        yield
        if manager:
            await manager.stop()
        for store in stores.values():
            store.close()

    application = FastAPI(title="EcoFlow Local", lifespan=lifespan)
    application.state.settings = settings
    application.state.collectors = collectors
    application.state.stores = stores
    application.state.manager = manager
    application.state.collects = collect
    application.state.login_guard = LoginGuard()
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret or "not-configured",
        https_only=settings.cookie_secure,
        same_site="lax",
    )
    application.mount(
        "/static", RevalidatedStatics(directory=STATIC_DIR), name="static"
    )
    application.include_router(router)
    return application
