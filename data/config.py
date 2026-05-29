"""Single source of truth for data-layer configuration.

The data layer lives in *this* repo, not in the backtesting engine. This module
loads THIS repo's ``.env`` (via an absolute path, so it works regardless of the
caller's cwd) and exposes the datalake URL/key plus the local-cache directories.

There is deliberately **no localhost fallback** for ``DATALAKE_URL``: a missing
value raises loudly rather than silently pointing a process at a dead local port
(the bug this module exists to kill -- see
``docs/handoffs/HANDOFF_data_layer_and_client.md``).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# data/ -> repo root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATALAKE_URL = os.getenv("DATALAKE_URL", "").strip().rstrip("/")
DATALAKE_API_KEY = os.getenv("DATALAKE_API_KEY", "").strip()
DATALAKE_INGEST_PATH = os.getenv("DATALAKE_INGEST_PATH", "/ingest").strip()

# Local CSV cache layer (absolute, so cwd never matters).
LOCAL_DATA_DIR = PROJECT_ROOT / "ohlc_data"
LOCAL_TICK_DIR = PROJECT_ROOT / "tick_data"


def require_datalake() -> tuple[str, str]:
    """Return ``(url, api_key)``, raising loudly if either is unset.

    No localhost fallback by design -- a missing var must fail fast, not
    silently hit a dead local port.
    """
    if not DATALAKE_URL:
        raise RuntimeError(
            "DATALAKE_URL is not set. Define it in this repo's .env "
            f"({PROJECT_ROOT / '.env'}). There is no localhost fallback."
        )
    if not DATALAKE_API_KEY:
        raise RuntimeError(
            "DATALAKE_API_KEY is not set. Define it in this repo's .env "
            f"({PROJECT_ROOT / '.env'})."
        )
    return DATALAKE_URL, DATALAKE_API_KEY
