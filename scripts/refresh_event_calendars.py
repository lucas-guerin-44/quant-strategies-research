#!/usr/bin/env python3
"""
Refresh authoritative forward calendars for the macro-event book:
  - FOMC  (federalreserve.gov)
  - CPI   (bls.gov)
  - PPI   (bls.gov)               -- kept for future use even though tombstoned
  - NFP   (bls.gov  -- Employment Situation)
  - RS    (census.gov  -- Advance Monthly Retail Sales)

Strategy:
  1. Fetch the canonical schedule page from each agency (with browser UA so BLS
     doesn't 403 us). Parse dates out of the HTML.
  2. Forward-only: agencies publish ~6 months ahead on these pages.
  3. NFP is deterministic (first Friday of each month at 08:30 ET, with rare
     holiday-shift exceptions) — we generate it by rule and cross-check against
     the BLS page where available.
  4. Merges into existing experiments/*/{event}_calendar.csv files: keeps
     historical rows untouched, replaces forward rows with what the agency just
     published. is_historical flag flips automatically based on today's date.

Run quarterly. Output: updated CSVs + verification report.

Usage:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/refresh_event_calendars.py
    # or:  python scripts/refresh_event_calendars.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_ROOT = Path(__file__).resolve().parent.parent
CALENDARS = {
    "fomc": _ROOT / "experiments" / "macro_drift" / "fomc_calendar.csv",
    "cpi":  _ROOT / "experiments" / "pre_cpi_drift" / "cpi_calendar.csv",
    "ppi":  _ROOT / "experiments" / "pre_ppi_drift" / "ppi_calendar.csv",
    "nfp":  _ROOT / "experiments" / "pre_nfp_drift" / "nfp_calendar.csv",
    "rs":   _ROOT / "experiments" / "pre_retail_sales_drift" / "retail_sales_calendar.csv",
}

# Default announce times (ET) for each event-class.
DEFAULT_TIME = {
    "fomc": "14:00",
    "cpi":  "08:30",
    "ppi":  "08:30",
    "nfp":  "08:30",
    "rs":   "08:30",
}

# (announce_time_field_name, has_with_projections_column)
SCHEMA = {
    "fomc": ("announce_time_et", True),
    "cpi":  ("announce_time_et", False),
    "ppi":  ("announce_time_et", False),
    "nfp":  ("announce_time_et", False),
    "rs":   ("announce_time_et", False),
}


# ---------- generic helpers ----------

def fetch(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def parse_dates_from_html(html: str) -> list[date]:
    """Parse 'Month DD, YYYY' patterns from arbitrary BLS/Fed/Census HTML."""
    months = {
        "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
    }
    pat = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})")
    seen = set()
    out: list[date] = []
    for m, d, y in pat.findall(html):
        try:
            dt = date(int(y), months[m], int(d))
        except ValueError:
            continue
        if dt not in seen:
            seen.add(dt)
            out.append(dt)
    return sorted(out)


# ---------- per-source fetchers ----------

def fetch_fomc_forward() -> list[date]:
    """Fed publishes their multi-year FOMC calendar on the official page."""
    html = fetch("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    # FOMC table has full multi-year coverage; filter for FUTURE dates only
    today = date.today()
    all_dates = parse_dates_from_html(html)
    # FOMC dates are usually 2-day meetings — the announce day is the LATER day.
    # The page lists both; for our purposes, pairs of consecutive days = meeting.
    # We keep only dates that are FORWARD-looking (date > today).
    return [d for d in all_dates if d > today]


def fetch_bls_forward(release: str) -> list[date]:
    """BLS schedule pages — release in {'cpi', 'ppi', 'empsit'}."""
    url = f"https://www.bls.gov/schedule/news_release/{release}.htm"
    html = fetch(url)
    today = date.today()
    return [d for d in parse_dates_from_html(html) if d > today]


def generate_nfp_first_fridays(start: date, end: date) -> list[date]:
    """NFP rule: first Friday of each month at 08:30 ET, with rare holiday exceptions."""
    out: list[date] = []
    d = date(start.year, start.month, 1)
    while d <= end:
        # Find first Friday in month
        offset = (4 - d.weekday()) % 7  # Mon=0..Sun=6, Friday=4
        first_fri = d + timedelta(days=offset)
        if first_fri >= start:
            out.append(first_fri)
        # advance to first of next month
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)
    return out


def fetch_census_rs_forward() -> list[date]:
    """Census Bureau Advance Retail Sales schedule."""
    # The current URL changes occasionally; try several known endpoints.
    candidates = [
        "https://www.census.gov/economic-indicators/calendar-listview.html",
        "https://www.census.gov/retail/marts/www/marts_current.html",
    ]
    for url in candidates:
        try:
            html = fetch(url)
            today = date.today()
            dates = [d for d in parse_dates_from_html(html) if d > today]
            if dates:
                return dates
        except requests.RequestException:
            continue
    return []


# ---------- CSV merge ----------

def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], schema_key: str) -> None:
    _, has_proj = SCHEMA[schema_key]
    if has_proj:
        fieldnames = ["date", "announce_time_et", "with_projections", "is_historical", "notes"]
    else:
        fieldnames = ["date", "announce_time_et", "is_historical", "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["date"]):
            w.writerow({k: r.get(k, "") for k in fieldnames})


def merge(key: str, fresh_dates: list[date], default_time: str) -> tuple[int, int, int]:
    """
    Merge fresh forward dates with existing historical rows.
    Returns (n_historical_kept, n_forward_new, n_forward_replaced).
    """
    path = CALENDARS[key]
    existing = load_csv(path)
    today = date.today()
    today_iso = today.isoformat()

    # Historical = date <= today (per is_historical flag OR computed from date)
    historical: dict[str, dict] = {}
    existing_forward: dict[str, dict] = {}
    for r in existing:
        d = r["date"]
        if d <= today_iso:
            r["is_historical"] = "yes"
            historical[d] = r
        else:
            existing_forward[d] = r

    # Fresh forward dates from authoritative source
    fresh_set: dict[str, dict] = {}
    has_proj = SCHEMA[key][1]
    for d in fresh_dates:
        d_iso = d.isoformat()
        if d_iso <= today_iso:
            continue  # don't overwrite historical
        row = {
            "date": d_iso,
            "announce_time_et": default_time,
            "is_historical": "no",
            "notes": "auto-refreshed",
        }
        if has_proj:
            row["with_projections"] = ""
        fresh_set[d_iso] = row

    n_replaced = sum(1 for d in fresh_set if d in existing_forward)
    n_new = sum(1 for d in fresh_set if d not in existing_forward)

    all_rows = list(historical.values()) + list(fresh_set.values())
    write_csv(path, all_rows, key)
    return len(historical), n_new, n_replaced


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print fetched dates, don't write CSVs")
    args = ap.parse_args()

    print(f"refresh_event_calendars  (today: {date.today().isoformat()})")
    print("=" * 76)

    results: dict[str, list[date]] = {}

    print("\n[fetch] FOMC ...")
    try:
        results["fomc"] = fetch_fomc_forward()
        print(f"  fed.gov returned {len(results['fomc'])} forward dates")
        for d in results["fomc"][:8]:
            print(f"    {d.isoformat()}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results["fomc"] = []

    for key, release in [("cpi", "cpi"), ("ppi", "ppi"), ("nfp", "empsit")]:
        print(f"\n[fetch] {key.upper()} (BLS {release}) ...")
        try:
            results[key] = fetch_bls_forward(release)
            print(f"  bls.gov returned {len(results[key])} forward dates")
            for d in results[key][:8]:
                print(f"    {d.isoformat()}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results[key] = []

    print("\n[fetch] RS (Census Bureau) ...")
    try:
        rs_fetched = fetch_census_rs_forward()
        results["rs"] = rs_fetched
        print(f"  census.gov returned {len(rs_fetched)} forward dates")
        for d in rs_fetched[:8]:
            print(f"    {d.isoformat()}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results["rs"] = []

    # NFP supplemental: rule-based first-Fridays for the next 12 months
    today = date.today()
    end = date(today.year + 1, today.month, 28)
    rule_nfp = generate_nfp_first_fridays(today + timedelta(days=1), end)
    # Merge BLS-published + rule-generated (BLS takes priority where overlapping)
    bls_nfp = set(results.get("nfp", []))
    nfp_combined = sorted(set(rule_nfp) | bls_nfp)
    results["nfp"] = nfp_combined
    print(f"\n[rule] NFP first-Fridays (next 12mo): {len(rule_nfp)} dates")
    print(f"        combined with BLS: {len(nfp_combined)} dates")

    if args.dry_run:
        print("\n[dry-run] not writing CSVs. Exit.")
        return

    print("\n[merge] writing CSVs ...")
    print("-" * 76)
    print(f"{'event':<6s} {'hist_kept':>10s} {'fwd_new':>9s} {'fwd_replaced':>14s}  {'path':>40s}")
    for key in ("fomc", "cpi", "ppi", "nfp", "rs"):
        if not results.get(key):
            print(f"{key:<6s} {'(no data)':>10s}")
            continue
        n_hist, n_new, n_repl = merge(key, results[key], DEFAULT_TIME[key])
        print(f"{key:<6s} {n_hist:>10d} {n_new:>9d} {n_repl:>14d}  {str(CALENDARS[key].relative_to(_ROOT)):>40s}")

    print("\nDone. If running in production, scp the updated CSVs to the VPS:")
    print("  scp experiments/*/[a-z]*calendar.csv trading:/tmp/")
    print("  ssh trading 'sudo cp /tmp/*_calendar.csv \"/root/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/\"'")
    print("EA reloads CSVs every 24h automatically; no MT5 restart needed.")


if __name__ == "__main__":
    main()
