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

load_dotenv()


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
    try:
        reading = json.loads(json_input)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON input: {exc}"}

    # 1. Validate
    validation = validator.validate(reading)

    if validation["is_fault"]:
        return {
            "reading":    reading,
            "validation": validation,
            "error":      validation["fault_reason"],
        }

    # 2. Calculate
    try:
        calculation = calculator.run_calculation(reading, validation)
    except Exception as exc:  # noqa: BLE001
        return {
            "reading":    reading,
            "validation": validation,
            "error":      f"Calculation error: {exc}",
        }

    # 3. Classify
    classification = classifier.classify(calculation["wbgt"])

    # 4. Persist
    db_payload = {
        **reading,
        **calculation,
        "risk_level":   classification["level"],
        "data_quality": calculation["data_quality"],
    }
    try:
        db_id = database.insert_reading(db_payload)
    except Exception as exc:  # noqa: BLE001
        db_id = None
        classification["db_error"] = str(exc)

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
    # Initialise the DB (creates tables if absent).
    database.init_db()

    # Determine if this is the long-lived process or a one-shot subprocess.
    # If --scheduler flag is passed, start the report scheduler.
    long_lived = "--scheduler" in sys.argv

    if long_lived:
        import report as report_module
        report_module.start_scheduler()

    # Read one JSON object from stdin (blocking).
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "Empty stdin — no reading provided."}))
        sys.exit(1)

    result = process_reading(raw)
    print(json.dumps(result))
    sys.stdout.flush()

    # In long-lived mode, keep the process alive so the scheduler can fire.
    if long_lived:
        import time
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
