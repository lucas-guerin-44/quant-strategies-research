"""One robust datalake HTTP client.

Replaces every ad-hoc ``requests.get(...).json()`` against the lake. It handles
the failure modes that recur across the repo (see
``docs/handoffs/HANDOFF_data_layer_and_client.md`` task 4 and
``HANDOFF_datalake_server.md`` for why the server misbehaves):

* **Auth** -- ``X-API-Key`` is sent on *every* call (reads were previously unauthed).
* **Inconsistent envelopes** -- ``/query`` returns ``{data, pagination}`` or a bare
  list; ``/catalog`` returns a nested dict. ``_unwrap`` normalizes them so callers
  never branch on shape.
* **502 HTML / timeouts under load** -- the single-concurrency server emits non-JSON
  gateway errors when busy. We check ``status_code`` + non-empty body *before*
  ``.json()`` and retry transient failures with exponential backoff.
* **Single concurrency** -- every call is serialized behind a process-wide lock so
  concurrent callers don't trip the server's readiness cron.

Use :func:`get_client` for the shared singleton; construct :class:`DatalakeClient`
directly only when you need custom retry/timeout settings.
"""

from __future__ import annotations

import io
import threading
import time
from typing import Any

import pandas as pd
import requests

from .config import DATALAKE_INGEST_PATH, require_datalake

# The lake serializes on a single DuckDB connection; serialize our side too.
_LAKE_LOCK = threading.Lock()

# Gateway / server statuses worth retrying (transient, not client errors).
_RETRY_STATUSES = {500, 502, 503, 504}
_PAGE_SIZE = 10_000


class DatalakeError(RuntimeError):
    """Raised when the lake returns an unrecoverable error."""


class DatalakeClient:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        *,
        max_retries: int = 5,
        backoff_base: float = 1.5,
        backoff_cap: float = 30.0,
        timeout: int = 120,
    ) -> None:
        cfg_url, cfg_key = require_datalake()
        self.url = (url or cfg_url).rstrip("/")
        self.api_key = api_key or cfg_key
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.timeout = timeout
        self._catalog_cache: dict | None = None

    # -- low-level ----------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def _sleep(self, attempt: int) -> None:
        time.sleep(min(self.backoff_base ** attempt, self.backoff_cap))

    def _request(self, method: str, path: str, *, retry: bool = True, **kw: Any) -> Any:
        """Serialized, JSON-safe request returning parsed JSON (dict or list).

        Retries transient 5xx / timeout / empty-body / non-JSON responses with
        exponential backoff. ``retry=False`` (used for the non-idempotent ingest
        POST) fails fast on the first error.
        """
        full = f"{self.url}{path if path.startswith('/') else '/' + path}"
        attempts = self.max_retries if retry else 1
        last_err: Exception | None = None

        for attempt in range(attempts):
            with _LAKE_LOCK:
                try:
                    resp = requests.request(
                        method, full, headers=self._headers, timeout=self.timeout, **kw
                    )
                except (requests.ConnectionError, requests.Timeout) as exc:
                    last_err = exc
                    if retry and attempt < attempts - 1:
                        self._sleep(attempt)
                        continue
                    raise DatalakeError(f"connection error to {full}: {exc}") from exc

            if resp.status_code in _RETRY_STATUSES:
                last_err = DatalakeError(f"{resp.status_code} from {full}: {resp.text[:300]}")
                if retry and attempt < attempts - 1:
                    self._sleep(attempt)
                    continue
                raise last_err

            if not resp.ok:
                raise DatalakeError(
                    f"{resp.status_code} {resp.reason} from {full}: {resp.text[:500]}"
                )

            text = resp.text or ""
            if not text.strip():
                last_err = DatalakeError(f"empty body from {full}")
                if retry and attempt < attempts - 1:
                    self._sleep(attempt)
                    continue
                raise last_err

            try:
                return resp.json()
            except ValueError as exc:  # JSONDecodeError -- e.g. a 502 HTML page
                last_err = DatalakeError(f"non-JSON body from {full}: {text[:200]}")
                if retry and attempt < attempts - 1:
                    self._sleep(attempt)
                    continue
                raise last_err

        raise DatalakeError(f"giving up after {attempts} attempts to {full}: {last_err}")

    @staticmethod
    def _unwrap(body: Any) -> tuple[list, dict]:
        """Normalize a ``/query`` body to ``(rows, pagination)``."""
        if isinstance(body, dict) and "data" in body:
            return body.get("data") or [], body.get("pagination") or {}
        if isinstance(body, list):
            return body, {}
        return [], {}

    # -- public API ---------------------------------------------------------

    def catalog(self, *, force: bool = False) -> dict:
        """Return the (per-process cached) ``/catalog`` envelope.

        Cached because the catalog only changes on ingest; this lets the loader's
        coverage guard run without spamming the single-concurrency server.
        """
        if self._catalog_cache is None or force:
            self._catalog_cache = self._request("GET", "/catalog")
        return self._catalog_cache

    def coverage(self, instrument: str, timeframe: str) -> dict | None:
        """Return ``{min_date, max_date, record_count}`` for one (instrument, tf).

        Reads the catalog's ``coverage`` list (per instrument+timeframe). Returns
        ``None`` if the pair isn't catalogued.
        """
        cat = self.catalog()
        rows = cat.get("coverage") if isinstance(cat, dict) else None
        if not isinstance(rows, list):
            return None
        for row in rows:
            if row.get("instrument") == instrument and row.get("timeframe") == timeframe:
                return {
                    "min_date": row.get("min_date"),
                    "max_date": row.get("max_date"),
                    "record_count": row.get("record_count"),
                }
        return None

    def query(
        self, instrument: str, timeframe: str, start: str, end: str, limit: int = 0
    ) -> list[dict]:
        """Return OHLC rows for a window, following cursor pagination.

        ``start``/``end`` accept ``YYYY-MM-DD`` (expanded to full-day bounds) or a
        full ``...THH:MM:SS`` timestamp.
        """
        params = {
            "instrument": instrument,
            "timeframe": timeframe,
            "start": str(start) if "T" in str(start) else f"{start}T00:00:00",
            "end": str(end) if "T" in str(end) else f"{end}T23:59:59",
            "limit": _PAGE_SIZE,
        }
        rows: list[dict] = []
        while True:
            page, pagination = self._unwrap(self._request("GET", "/query", params=params))
            if not page:
                break
            rows.extend(page)
            if limit and len(rows) >= limit:
                return rows[:limit]
            if pagination.get("has_more") and pagination.get("next_cursor"):
                params["cursor"] = pagination["next_cursor"]
            else:
                break
        return rows

    def ingest(self, df: pd.DataFrame, instrument: str, timeframe: str) -> int:
        """POST bars as a multipart CSV upload. Returns rows sent.

        Not retried (a re-POST could double-write); fails fast on error.
        """
        if df is None or df.empty:
            return 0
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        files = {"file": (f"{instrument}_{timeframe}.csv", buf.getvalue().encode("utf-8"), "text/csv")}
        data = {"instrument": instrument, "timeframe": timeframe}
        self._request("POST", DATALAKE_INGEST_PATH, retry=False, files=files, data=data)
        return len(df)


_CLIENT: DatalakeClient | None = None


def get_client() -> DatalakeClient:
    """Return the shared process-wide :class:`DatalakeClient` singleton."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = DatalakeClient()
    return _CLIENT
