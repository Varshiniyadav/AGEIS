"""
validator.py

Validates indoor sensor readings and checks for physical constraints.
"""

def validate(reading: dict) -> dict:
    """
    Validates sensor reading inputs.
    Returns:
        {
            "condition": "ALL_DATA" | "MISSING_TG" | "MISSING_RH",
            "missing_fields": list,
            "flags": list,
            "is_fault": bool,
            "fault_reason": str
        }
    """
    result = {
        "condition": None,
        "missing_fields": [],
        "flags": [],
        "is_fault": False,
        "fault_reason": "",
    }

    ta = reading.get("air_temp_c")
    rh = reading.get("relative_humidity_pct")
    tg = reading.get("globe_temp_c")

    # --- Hard rule: air_temp_c must be present for indoor calculation ---
    if ta is None or ta == "":
        result["is_fault"] = True
        result["fault_reason"] = "SENSOR_FAULT: Indoor monitoring requires air_temp_c from local sensor."
        result["missing_fields"].append("air_temp_c")
        return result

    # --- Range and numeric type validation ---
    try:
        ta = float(ta)
    except (ValueError, TypeError):
        result["is_fault"] = True
        result["fault_reason"] = "SENSOR_FAULT: air_temp_c is not a valid number."
        return result

    if rh is not None and rh != "":
        try:
            rh = float(rh)
            if not (0 <= rh <= 100):
                result["is_fault"] = True
                result["fault_reason"] = f"SENSOR_FAULT: relative_humidity_pct={rh}% is out of valid range (0-100%)."
                return result
        except (ValueError, TypeError):
            result["is_fault"] = True
            result["fault_reason"] = "SENSOR_FAULT: relative_humidity_pct is not a valid number."
            return result

    if tg is not None and tg != "":
        try:
            tg = float(tg)
            if tg < ta:
                result["is_fault"] = True
                result["fault_reason"] = f"SENSOR_FAULT: globe_temp_c={tg} cannot be less than air_temp_c={ta}."
                return result
            if tg > 90:
                result["flags"].append(f"globe_temp_c={tg} exceeds 90 °C — verify sensor calibration.")
        except (ValueError, TypeError):
            result["is_fault"] = True
            result["fault_reason"] = "SENSOR_FAULT: globe_temp_c is not a valid number."
            return result

    # --- Detect missing fields ---
    missing = []
    if rh is None or rh == "":
        missing.append("relative_humidity_pct")
    if tg is None or tg == "":
        missing.append("globe_temp_c")

    result["missing_fields"] = missing

    # --- Classify condition ---
    rh_present = "relative_humidity_pct" not in missing
    tg_present = "globe_temp_c" not in missing

    if rh_present and tg_present:
        result["condition"] = "ALL_DATA"
    elif rh_present and not tg_present:
        result["condition"] = "MISSING_TG"
    else:
        result["condition"] = "MISSING_RH"

    return result
