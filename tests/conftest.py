"""Shared fixtures.

`create_app` takes its settings and database path as arguments, so a test never has to
redirect environment variables or risk touching the live database.
"""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from app.devices import ALTERNATOR, DELTA2  # noqa: E402
from app.storage import TelemetryStore  # noqa: E402

TEST_PASSWORD = "test-password"


@pytest.fixture
def settings():
    return Settings(
        admin_password=TEST_PASSWORD,
        session_secret="s" * 64,
        cookie_secure=False,
        user_id="1234567890123456789",
        poll_seconds=15,
        gateway_token="gateway-token-for-tests",
        eflib_root=PROJECT_ROOT / "vendor/ha-ef-ble/custom_components/ef_ble/eflib",
    )


@pytest.fixture
def store(tmp_path):
    made = TelemetryStore(tmp_path / "t.sqlite3", DELTA2)
    yield made
    made.close()


@pytest.fixture
def alternator_store(tmp_path):
    made = TelemetryStore(tmp_path / "t.sqlite3", ALTERNATOR)
    yield made
    made.close()


@pytest.fixture
def unconfigured(settings):
    return replace(settings, admin_password="", session_secret="")


@pytest.fixture
def build_app(tmp_path):
    """Builds isolated apps and closes their stores afterwards.

    `create_app` opens a SQLite connection per device. The lifespan closes them, but
    tests do not enter it - starting it would launch the Bluetooth collectors.
    """
    made = []

    def build(app_settings, name="t.sqlite3"):
        application = create_app(
            settings=app_settings, database_path=tmp_path / name
        )
        made.append(application)
        return application

    yield build

    for application in made:
        for collector in application.state.collectors.values():
            collector.store.close()
