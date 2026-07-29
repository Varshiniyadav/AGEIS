"""
report.py

Generates periodic WBGT summary reports (CSV format) and schedules them
to run every REPORT_INTERVAL_HOURS using threading.Timer.

CSV columns (important fields only):
    zone_id, timestamp, ta_c, rh_pct, tg_c, tnwb_c, wbgt,
    risk_level, action, is_outdoor, location_type,
    min_wbgt, max_wbgt, avg_wbgt, danger_count, warning_count, total_readings
"""

import csv
import os
import threading
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

import database
from logger import get_logger

load_dotenv()

log = get_logger(__name__)

REPORT_INTERVAL_SECONDS = float(os.getenv("REPORT_INTERVAL_SECONDS", "10"))
REPORT_OUTPUT_DIR       = os.getenv("REPORT_OUTPUT_DIR", "./reports")

# CSV columns in output order
CSV_FIELDS = [
    "Timestamp",
    "Temperature(C)",
    "Humidity(%)",
    "WetBulbTemperature(C)",
    "GlobeTemperature(C)",
    "WBGT(C)",
    "Classification",
]


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------

def generate_report(start: datetime, end: datetime) -> list[dict]:
    """
    Generate a per-reading report for the given time window.

    Returns a list of row dicts mapped to the new CSV fields.
    """
    rows = database.get_readings(start=start, end=end)
    log.info(f"[REPORT] Fetched {len(rows)} readings for window "
             f"{start.isoformat()} → {end.isoformat()}")

    if not rows:
        log.warning("[REPORT] No readings found in window — empty report.")
        return []

    csv_rows = []
    for row in rows:
        csv_rows.append({
            "Timestamp":             row.get("timestamp", ""),
            "Temperature(C)":        row.get("ta", ""),
            "Humidity(%)":           row.get("rh", ""),
            "WetBulbTemperature(C)": row.get("tnwb", ""),
            "GlobeTemperature(C)":   row.get("tg", ""),
            "WBGT(C)":               row.get("wbgt", ""),
            "Classification":        row.get("risk_level", ""),
        })

    return csv_rows


def write_report(csv_rows: list[dict]) -> str:
    """
    Write report rows to a single CSV file (wbgt_report.csv) in REPORT_OUTPUT_DIR.

    Returns the file path written.
    """
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

    filename = "wbgt_report.csv"
    filepath = os.path.join(REPORT_OUTPUT_DIR, filename)

    file_exists = os.path.exists(filepath)

    with open(filepath, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, delimiter=",", extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(csv_rows)

    log.info(f"[REPORT] CSV report appended: {filepath} ({len(csv_rows)} rows)")
    return filepath


# ---------------------------------------------------------------------------
# Scheduler (no extra dependencies — uses threading.Timer)
# ---------------------------------------------------------------------------

def _run_and_reschedule():
    """Generate a report for the last REPORT_INTERVAL_SECONDS window, save it,
    then schedule the next run."""
    now   = datetime.now(timezone.utc)
    start = now - timedelta(seconds=REPORT_INTERVAL_SECONDS + 2)

    log.info(f"[REPORT] Scheduler triggered — generating report for last "
             f"{REPORT_INTERVAL_SECONDS}s window")
    try:
        csv_rows = generate_report(start, now)
        path     = write_report(csv_rows)
        log.info(f"[REPORT] Scheduler wrote: {path}")
        print(f"[report] Wrote {path}", flush=True)
    except Exception as exc:  # noqa: BLE001
        log.error(f"[REPORT] Error generating report: {exc}")
        print(f"[report] Error generating report: {exc}", flush=True)

    _schedule_next()


def _schedule_next():
    t = threading.Timer(REPORT_INTERVAL_SECONDS, _run_and_reschedule)
    t.daemon = True   # won't block clean process exit
    t.start()
    log.debug(f"[REPORT] Next report scheduled in {REPORT_INTERVAL_SECONDS}s")


def start_scheduler():
    """Call once from main.py to begin the periodic reporting loop."""
    _schedule_next()
    msg = (f"[report] Scheduler started — report every {REPORT_INTERVAL_SECONDS}s "
           f"into '{REPORT_OUTPUT_DIR}/'")
    print(msg, flush=True)
    log.info(msg)
