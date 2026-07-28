"""
classifier.py

Classifies a WBGT value into a risk level using the thresholds defined in .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

THRESHOLD_SAFE_MAX    = float(os.getenv("THRESHOLD_SAFE_MAX",    "26.7"))
THRESHOLD_CAUTION_MAX = float(os.getenv("THRESHOLD_CAUTION_MAX", "29.4"))
THRESHOLD_WARNING_MAX = float(os.getenv("THRESHOLD_WARNING_MAX", "31.1"))


def classify(wbgt: float) -> dict:
    """
    Classify a WBGT value into a risk level.

    Returns:
        {
            level:  str  — SAFE | CAUTION | WARNING | DANGER
            color:  str  — green | yellow | orange | red
            action: str  — recommended action string
        }
    """
    if wbgt < THRESHOLD_SAFE_MAX:
        return {
            "level":  "SAFE",
            "color":  "green",
            "action": "Normal work, no restrictions",
        }
    elif wbgt < THRESHOLD_CAUTION_MAX:
        return {
            "level":  "CAUTION",
            "color":  "yellow",
            "action": "Increase water breaks",
        }
    elif wbgt < THRESHOLD_WARNING_MAX:
        return {
            "level":  "WARNING",
            "color":  "orange",
            "action": "Enforce work/rest cycles (50 min work, 10 min rest)",
        }
    else:
        return {
            "level":  "DANGER",
            "color":  "red",
            "action": "Halt heavy work, mandatory rest, evacuate",
        }
