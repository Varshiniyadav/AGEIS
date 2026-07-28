"""
validator.py

Validates a sensor reading dict and detects the data condition.
"""


def validate(reading: dict) -> dict:
    """
    Validate a sensor reading and detect the data condition.

    Returns a dict with:
        condition     : str  — ALL_DATA | MISSING_TG | MISSING_RH | MINIMAL_DATA
        missing_fields: list — names of absent/None fields
        flags         : list — non-fatal warnings (e.g. Tg suspiciously high)
        is_fault      : bool — True if the reading cannot be processed
        fault_reason  : str  — human-readable reason when is_fault is True
    """
    result = {
        "condition": None,
        "missing_fields": [],
        "flags": [],
        "is_fault": False,
        "fault_reason": "",
    }

    is_outdoor = bool(reading.get("is_outdoor", False))

    ta = reading.get("air_temp_c")
    rh = reading.get("relative_humidity_pct")
    tg = reading.get("globe_temp_c")

    # --- Hard rule: indoor Ta must come from local sensor ---
    if not is_outdoor and (ta is None or ta == ""):
        result["is_fault"] = True
        result["fault_reason"] = (
            "SENSOR_FAULT: indoor zone requires air_temp_c from local sensor; "
            "value is missing. Cannot estimate."
        )
        result["missing_fields"].append("air_temp_c")
        return result

    # --- Range validation for values that ARE present ---
    if ta is not None:
        try:
            ta = float(ta)
        except (ValueError, TypeError):
            result["is_fault"] = True
            result["fault_reason"] = "SENSOR_FAULT: air_temp_c is not a valid number."
            return result
        if not (0 <= ta <= 60):
            result["is_fault"] = True
            result["fault_reason"] = (
                f"SENSOR_FAULT: air_temp_c={ta} is out of valid range 0–60 °C."
            )
            return result

    if rh is not None:
        try:
            rh = float(rh)
        except (ValueError, TypeError):
            result["is_fault"] = True
            result["fault_reason"] = "SENSOR_FAULT: relative_humidity_pct is not a valid number."
            return result
        if not (0 <= rh <= 100):
            result["is_fault"] = True
            result["fault_reason"] = (
                f"SENSOR_FAULT: relative_humidity_pct={rh} is out of valid range 0–100 %."
            )
            return result

    if tg is not None:
        try:
            tg = float(tg)
        except (ValueError, TypeError):
            result["is_fault"] = True
            result["fault_reason"] = "SENSOR_FAULT: globe_temp_c is not a valid number."
            return result
        if ta is not None and tg < ta:
            result["is_fault"] = True
            result["fault_reason"] = (
                f"SENSOR_FAULT: globe_temp_c={tg} is less than air_temp_c={ta}."
            )
            return result
        if tg > 90:
            result["flags"].append(
                f"globe_temp_c={tg} exceeds 90 °C — verify sensor calibration."
            )

    # --- Detect missing fields ---
    missing = []
    if ta is None or ta == "":
        missing.append("air_temp_c")
    if rh is None or rh == "":
        missing.append("relative_humidity_pct")
    if tg is None or tg == "":
        missing.append("globe_temp_c")

    result["missing_fields"] = missing

    # --- Classify condition ---
    ta_present = "air_temp_c" not in missing
    rh_present = "relative_humidity_pct" not in missing
    tg_present = "globe_temp_c" not in missing

    if ta_present and rh_present and tg_present:
        result["condition"] = "ALL_DATA"
    elif ta_present and rh_present and not tg_present:
        result["condition"] = "MISSING_TG"
    elif ta_present and not rh_present:
        result["condition"] = "MISSING_RH"
    else:
        # ta missing — only valid for outdoor (indoor already faulted above)
        result["condition"] = "MINIMAL_DATA"

    return result
