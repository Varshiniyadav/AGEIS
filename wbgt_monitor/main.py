"""
main.py

Entry point for the WBGT monitoring pipeline.

Two modes:
  1. Subprocess mode (default, spawned by receiver.js):
       Reads one JSON object from stdin → runs the full pipeline →
       prints result JSON to stdout → exits.

  2. Long-lived process mode (started directly by an operator):
       Same as above for the first reading from stdin, but also
       starts the background report scheduler and keeps running.

Usage:
    echo '{"zone_id":"furnace",...}' | python main.py
"""

import json
import sys

from dotenv import load_dotenv

import calculator
import classifier
import database
import validator
from logger import get_logger

load_dotenv()

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def process_reading(json_input: str) -> dict:
    """
    Run the full pipeline on a single reading JSON string.

    Returns a dict with:
        reading       : the original parsed reading
        validation    : validator output
        calculation   : calculator output  (absent on fault)
        classification: classifier output  (absent on fault)
        db_id         : int row id         (absent on fault)
        error         : str                (present on fault)
    """
    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        reading = json.loads(json_input)
    except json.JSONDecodeError as exc:
        log.error(f"Invalid JSON input: {exc}")
        return {"error": f"Invalid JSON input: {exc}"}

    if "zone" in reading and "zone_id" not in reading:
        reading["zone_id"] = reading["zone"]
    if "temperature" in reading and "air_temp_c" not in reading:
        reading["air_temp_c"] = reading["temperature"]
    if "humidity" in reading and "relative_humidity_pct" not in reading:
        reading["relative_humidity_pct"] = reading["humidity"]
    if "globe_temperature" in reading and "globe_temp_c" not in reading:
        reading["globe_temp_c"] = reading["globe_temperature"]

    zone      = reading.get("zone_id", "unknown")
    timestamp = reading.get("timestamp", "?")
    log.info(f"[READING] zone={zone} | timestamp={timestamp}")
    log.debug(f"[READING] raw={json_input[:200]}")

    # ── 1. Validate ───────────────────────────────────────────────────────────
    validation = validator.validate(reading)
    log.debug(f"[VALIDATE] zone={zone} | condition={validation['condition']} | "
              f"missing={validation['missing_fields']} | flags={validation['flags']}")

    if validation["is_fault"]:
        reason = validation["fault_reason"]
        log.debug(f"[FAULT] zone={zone} | timestamp={timestamp} | reason={reason}")
        return {
            "reading":    reading,
            "validation": validation,
            "error":      reason,
        }

    # ── 2. Calculate ──────────────────────────────────────────────────────────
    try:
        calculation = calculator.run_calculation(reading, validation)
        log.info(f"[CALC] zone={zone} | ta={calculation['ta']} | rh={calculation['rh']} | "
                 f"tg={calculation['tg']} | tnwb={calculation['tnwb']} | wbgt={calculation['wbgt']}")
        log.debug(f"[CALC] data_quality={calculation['data_quality']}")
    except Exception as exc:  # noqa: BLE001
        log.error(f"[CALC ERROR] zone={zone} | timestamp={timestamp} | error={exc}")
        return {
            "reading":    reading,
            "validation": validation,
            "error":      f"Calculation error: {exc}",
        }

    # ── 3. Classify ───────────────────────────────────────────────────────────
    classification = classifier.classify(calculation["wbgt"])
    level  = classification["level"]
    action = classification["action"]
    log.info(f"[CLASSIFY] zone={zone} | wbgt={calculation['wbgt']} | "
             f"risk={level} | action={action}")

    if level == "DANGER":
        log.warning(f"[DANGER ALERT] zone={zone} | wbgt={calculation['wbgt']} | {action}")
    elif level == "WARNING":
        log.warning(f"[WARNING ALERT] zone={zone} | wbgt={calculation['wbgt']} | {action}")

    # ── 4. Persist ────────────────────────────────────────────────────────────
    db_payload = {
        **reading,
        **calculation,
        "risk_level":   classification["level"],
        "data_quality": calculation["data_quality"],
    }
    try:
        db_id = database.insert_reading(db_payload)
        log.info(f"[DB] zone={zone} | db_id={db_id} | saved OK")
    except Exception as exc:  # noqa: BLE001
        db_id = None
        classification["db_error"] = str(exc)
        log.debug(f"[DB ERROR] zone={zone} | error={exc}")

    return {
        "reading":        reading,
        "validation":     validation,
        "calculation":    calculation,
        "classification": classification,
        "db_id":          db_id,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("WBGT Monitor starting up")

    # Initialise the DB (creates tables if absent).
    database.init_db()
    log.info("Database initialised")

    # Determine if this is the long-lived process or a one-shot subprocess.
    # If --scheduler flag is passed, start the report scheduler.
    long_lived = "--scheduler" in sys.argv

    if long_lived:
        import report as report_module
        report_module.start_scheduler()
        log.info("Report scheduler started")

    # Read one JSON object from stdin (blocking).
    raw = sys.stdin.read().strip()
    if not raw:
        msg = "Empty stdin — no reading provided."
        log.error(msg)
        print(json.dumps({"error": msg}))
        sys.exit(1)

    result = process_reading(raw)
    print(json.dumps(result))
    sys.stdout.flush()

    if "error" in result and "classification" not in result:
        log.debug(f"Pipeline completed with fault: {result.get('error')}")
    else:
        log.info(f"Pipeline completed OK | db_id={result.get('db_id')}")

    # In long-lived mode, keep the process alive so the scheduler can fire.
    if long_lived:
        import time
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            log.info("WBGT Monitor shutting down (KeyboardInterrupt)")
