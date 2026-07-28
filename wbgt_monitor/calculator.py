"""
calculator.py

Computes WBGT (Wet Bulb Globe Temperature) from sensor readings.
Handles missing data according to the fallback rules.
"""

import math
import os
import json

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Zone globe-temperature offsets (loaded once from .env)
# ---------------------------------------------------------------------------
_raw_offsets = os.getenv("ZONE_TG_OFFSETS", '{"default": 5}')
try:
    ZONE_TG_OFFSETS: dict = json.loads(_raw_offsets)
except json.JSONDecodeError:
    ZONE_TG_OFFSETS = {"default": 5}


# ---------------------------------------------------------------------------
# Weather API client (outdoor Ta/RH/dew point)
# ---------------------------------------------------------------------------

class WeatherClient:
    """Minimal client for the configured weather API."""

    def __init__(self):
        self.base_url = os.getenv("WEATHER_API_BASE_URL", "").rstrip("/")
        self.api_key  = os.getenv("WEATHER_API_KEY", "")
        self.lat      = os.getenv("WEATHER_API_LAT", "")
        self.lon      = os.getenv("WEATHER_API_LON", "")

    def get_current(self) -> dict:
        """
        Fetch current conditions from the weather API.

        Returns:
            {
                "temperature_c": float,
                "dew_point_c":   float,
                "humidity_pct":  float,
            }
        Raises:
            RuntimeError on any network or parsing failure.
        """
        if not self.base_url:
            raise RuntimeError("WEATHER_API_BASE_URL is not configured.")

        params = {
            "lat":   self.lat,
            "lon":   self.lon,
            "appid": self.api_key,
            "units": "metric",
        }
        try:
            resp = requests.get(self.base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"Weather API request failed: {exc}") from exc

        # Support OpenWeatherMap-style response; adapt if using a different API.
        try:
            temperature_c = float(data["main"]["temp"])
            humidity_pct  = float(data["main"]["humidity"])
            # OWM doesn't include dew_point in /weather; fall back if absent.
            dew_point_c   = float(
                data.get("main", {}).get("dew_point",
                    _estimate_dew_point(temperature_c, humidity_pct))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Unexpected weather API response structure: {exc}\nResponse: {data}"
            ) from exc

        return {
            "temperature_c": temperature_c,
            "dew_point_c":   dew_point_c,
            "humidity_pct":  humidity_pct,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _estimate_dew_point(ta: float, rh: float) -> float:
    """Magnus approximation for dew point (°C)."""
    a, b = 17.67, 243.5
    alpha = math.log(rh / 100.0) + (a * ta) / (b + ta)
    return (b * alpha) / (a - alpha)


def _stull_tnwb(ta: float, rh: float) -> float:
    """
    Stull (2011) natural wet-bulb temperature approximation.

    Tnwb = Ta*atan(0.151977*(RH+8.313659)^0.5)
           + atan(Ta+RH) - atan(RH-1.676331)
           + 0.00391838*(RH^1.5)*atan(0.023101*RH)
           - 4.686035
    """
    return (
        ta * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(ta + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )


def _estimate_tg(ta: float, location_type: str) -> float:
    """Estimate globe temperature using zone offset."""
    offset = ZONE_TG_OFFSETS.get(location_type, ZONE_TG_OFFSETS.get("default", 5))
    return ta + offset


def _rh_from_dew_point(ta: float, td: float) -> float:
    """
    Estimate RH from dew point using the simplified formula:
        RH% = 100 - 5*(Ta - Td)
    Clamped to [0, 100].
    """
    rh = 100.0 - 5.0 * (ta - td)
    return max(0.0, min(100.0, rh))


def _indoor_rh_from_weather(ta_in: float, weather_client: WeatherClient) -> float:
    """
    Estimate indoor RH using outdoor weather data and the vapour-pressure
    conservation formula.

    Clamps result to [0, 100].
    """
    wx = weather_client.get_current()
    t_out  = wx["temperature_c"]
    rh_out = wx["humidity_pct"]

    psat_out = 6.112 * math.exp((17.67 * t_out)  / (t_out  + 243.5))
    p_actual = (rh_out / 100.0) * psat_out
    psat_in  = 6.112 * math.exp((17.67 * ta_in) / (ta_in + 243.5))
    rh_in    = 100.0 * (p_actual / psat_in)

    return max(0.0, min(100.0, rh_in))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_calculation(reading: dict, validation: dict) -> dict:
    """
    Apply the appropriate formula chain based on the detected data condition.

    Returns:
        {
            ta:           float,
            rh:           float,
            tg:           float,
            tnwb:         float,
            wbgt:         float,
            data_quality: {field: "sensor"|"estimated"|"calculated"|"api"}
        }
    """
    condition     = validation["condition"]
    is_outdoor    = bool(reading.get("is_outdoor", False))
    location_type = reading.get("location_type", "default")

    quality: dict = {}
    weather = WeatherClient()

    # ---- Resolve Ta --------------------------------------------------------
    if reading.get("air_temp_c") is not None:
        ta = float(reading["air_temp_c"])
        quality["ta"] = "sensor"
    else:
        # MINIMAL_DATA: outdoor only; use weather API outdoor Ta.
        wx = weather.get_current()
        ta = wx["temperature_c"]
        quality["ta"] = "api"

    # ---- Resolve RH --------------------------------------------------------
    if reading.get("relative_humidity_pct") is not None:
        rh = float(reading["relative_humidity_pct"])
        quality["rh"] = "sensor"
    elif reading.get("dew_point_c") is not None and is_outdoor:
        # Outdoor: estimate RH from dew point.
        td = float(reading["dew_point_c"])
        rh = _rh_from_dew_point(ta, td)
        quality["rh"] = "estimated"
    elif is_outdoor:
        # Outdoor, no dew point either: fetch from weather API.
        wx = weather.get_current()
        rh = wx["humidity_pct"]
        quality["rh"] = "api"
    else:
        # Indoor, RH missing: estimate via vapour-pressure formula.
        rh = _indoor_rh_from_weather(ta, weather)
        quality["rh"] = "estimated"

    # ---- Resolve Tg --------------------------------------------------------
    if reading.get("globe_temp_c") is not None:
        tg = float(reading["globe_temp_c"])
        quality["tg"] = "sensor"
    else:
        tg = _estimate_tg(ta, location_type)
        quality["tg"] = "estimated"

    # ---- Tnwb (always calculated) ------------------------------------------
    tnwb = _stull_tnwb(ta, rh)
    quality["tnwb"] = "calculated"

    # ---- WBGT --------------------------------------------------------------
    if is_outdoor:
        wbgt = 0.7 * tnwb + 0.2 * tg + 0.1 * ta
    else:
        wbgt = 0.7 * tnwb + 0.3 * tg

    quality["wbgt"] = "calculated"

    return {
        "ta":           round(ta,   2),
        "rh":           round(rh,   2),
        "tg":           round(tg,   2),
        "tnwb":         round(tnwb, 4),
        "wbgt":         round(wbgt, 4),
        "data_quality": quality,
    }
