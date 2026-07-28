"""
report.py

Generates periodic WBGT summary reports and schedules them to run
every REPORT_INTERVAL_HOURS using threading.Timer.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

import database

load_dotenv()

REPORT_INTERVAL_HOURS = float(os.getenv("REPORT_INTERVAL_HOURS", "24"))
REPORT_OUTPUT_DIR     = os.getenv("REPORT_OUTPUT_DIR", "./reports")

RISK_LEVELS = ["SAFE", "CAUTION", "WARNING", "DANGER"]


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------

def generate_report(start: datetime, end: datetime) -> dict:
    """
    Generate a summary report for the given time window.

    Returns:
        {
            "generated_at": ISO str,
            "window":       {"start": ISO str, "end": ISO str},
            "zones":        {zone_id: zone_summary, ...}
        }

    Each zone_summary:
        {
            min_wbgt:       float | None,
            max_wbgt:       float | None,
            avg_wbgt:       float | None,
            time_in_level:  {SAFE: int, CAUTION: int, WARNING: int, DANGER: int},
            danger_count:   int,
            warning_count:  int,
            total_readings: int,
        }
    """
    rows = database.get_readings(start=start, end=end)

    # Group by zone
    zones: dict[str, list] = {}
    for row in rows:
        zid = row.get("zone_id") or "unknown"
        zones.setdefault(zid, []).append(row)

    zone_summaries = {}
    for zid, zone_rows in zones.items():
        wbgt_values = [r["wbgt"] for r in zone_rows if r.get("wbgt") is not None]

        time_in_level = {lvl: 0 for lvl in RISK_LEVELS}
        danger_count  = 0
        warning_count = 0

        for row in zone_rows:
            level = row.get("risk_level")
            if level in time_in_level:
                time_in_level[level] += 1
            if level == "DANGER":
                danger_count  += 1
            if level == "WARNING":
                warning_count += 1

        zone_summaries[zid] = {
            "min_wbgt":       round(min(wbgt_values), 4) if wbgt_values else None,
            "max_wbgt":       round(max(wbgt_values), 4) if wbgt_values else None,
            "avg_wbgt":       round(sum(wbgt_values) / len(wbgt_values), 4) if wbgt_values else None,
            "time_in_level":  time_in_level,
            "danger_count":   danger_count,
            "warning_count":  warning_count,
            "total_readings": len(zone_rows),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {
            "start": start.isoformat(),
            "end":   end.isoformat(),
        },
        "zones": zone_summaries,
    }


def write_report(report_dict: dict) -> str:
    """
    Serialize report_dict as JSON to a timestamped file in REPORT_OUTPUT_DIR.

    Returns the file path written.
    """
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"wbgt_report_{ts}.json"
    filepath = os.path.join(REPORT_OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(report_dict, fh, indent=2)

    return filepath


# ---------------------------------------------------------------------------
# Scheduler (no extra dependencies — uses threading.Timer)
# ---------------------------------------------------------------------------

def _run_and_reschedule():
    """Generate a report for the last REPORT_INTERVAL_HOURS window, save it,
    then schedule the next run."""
    now   = datetime.now(timezone.utc)
    start = now - timedelta(hours=REPORT_INTERVAL_HOURS)

    try:
        report = generate_report(start, now)
        path   = write_report(report)
        print(f"[report] Wrote {path}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[report] Error generating report: {exc}", flush=True)

    _schedule_next()


def _schedule_next():
    interval_seconds = REPORT_INTERVAL_HOURS * 3600
    t = threading.Timer(interval_seconds, _run_and_reschedule)
    t.daemon = True   # won't block clean process exit
    t.start()


def start_scheduler():
    """Call once from main.py to begin the periodic reporting loop."""
    _schedule_next()
    print(
        f"[report] Scheduler started — report every {REPORT_INTERVAL_HOURS}h "
        f"into '{REPORT_OUTPUT_DIR}/'",
        flush=True,
    )
