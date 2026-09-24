"""Configuration: where the app reads its settings and where things live on disk."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"


def load_dotenv(path: Path) -> None:
    """Read .env into the environment, without overriding real environment variables.

    The service is started in several ways - a shell that sourced .env, the macOS
    launcher app, an IDE run configuration - and only the first of those sets the
    variables itself. Reading the file here means a missing `source .env` can no
    longer leave the dashboard locked with an empty session secret.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def default_database_path() -> Path:
    """Overridable so tests never open the live database."""
    return Path(os.getenv("ECOFLOW_DB_PATH", PROJECT_ROOT / "data" / "telemetry.sqlite3"))


@dataclass(frozen=True)
class Settings:
    admin_password: str
    session_secret: str
    cookie_secure: bool
    user_id: str
    poll_seconds: int
    gateway_token: str
    eflib_root: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        eflib_value = os.getenv(
            "ECOFLOW_EFLIB_ROOT",
            "vendor/ha-ef-ble/custom_components/ef_ble/eflib",
        )
        eflib_root = Path(eflib_value)
        if not eflib_root.is_absolute():
            eflib_root = PROJECT_ROOT / eflib_root
        return cls(
            admin_password=os.getenv("APP_ADMIN_PASSWORD", ""),
            session_secret=os.getenv("APP_SESSION_SECRET", ""),
            cookie_secure=os.getenv("APP_COOKIE_SECURE", "false").lower() == "true",
            user_id=os.getenv("ECOFLOW_USER_ID", "").strip(),
            # Used by the relay to authenticate to the remote server. Never the
            # dashboard password: a machine credential should be rotatable on its own.
            gateway_token=os.getenv("APP_GATEWAY_TOKEN", "").strip(),
            poll_seconds=max(5, int(os.getenv("ECOFLOW_POLL_SECONDS", "15"))),
            eflib_root=eflib_root,
        )

    @property
    def dashboard_ready(self) -> bool:
        return bool(self.admin_password and self.session_secret)

    @property
    def collector_ready(self) -> bool:
        return bool(self.user_id.isdigit() and self.eflib_root.joinpath("__init__.py").is_file())


