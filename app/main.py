"""Entry point. `uvicorn app.main:app` continues to work.

Everything of substance lives in the modules beside this one; see
docs/architecture.md for the map.
"""

import logging

from .api import create_app
from .config import PROJECT_ROOT, load_dotenv

# uvicorn configures its own loggers; ours need a handler of their own.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Before anything reads its configuration.
load_dotenv(PROJECT_ROOT / ".env")

app = create_app()
