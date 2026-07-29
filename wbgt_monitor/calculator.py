"""
calculator.py

Computes WBGT (Wet Bulb Globe Temperature) for indoor environments.
Handles missing sensor parameters using physics-based fallbacks.
"""

import math
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Load zone globe-temperature offsets from .env
_raw_offsets = os.getenv("ZONE_TG_OFFSETS", '{"default": 5}')
try:
    ZONE_TG_OFFSETS = json.loads(_raw_offsets)
except json.JSONDecodeError:
    ZONE_TG_OFFSETS = {"default": 5}


class WeatherClient:
    """Minimal client to fetch outdoor conditions for indoor RH estimation fallback."""

    def __init__(self):
        self.base_url = os.getenv("WEATHER_API_BASE_URL", "").rstrip("/")
        self.api_key  = os.getenv("WEATHER_API_KEY", "")
        self.lat      = os.getenv("WEATHER_API_LAT", "")
        self.lon      = os.getenv("WEATHER_API_LON", "")

    def get_current(self) -> dict:
        """Fetch current outdoor temperature and humidity."""
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
            return {
                "temperature_c": float(data["main"]["temp"]),
                "humidity_pct":  float(data["main"]["humidity"]),
            }
        except Exception as exc:
            raise RuntimeError(f"Weather API request failed: {exc}") from exc


def _stull_tnwb(ta: float, rh: float) -> float:
    """Stull (2011) natural wet-bulb temperature approximation."""
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


def _indoor_rh_from_weather(ta: float, weather_client: WeatherClient) -> float:
    """Estimate indoor RH using outdoor weather data via vapor-pressure conservation."""
    wx = weather_client.get_current()
    t_out  = wx["temperature_c"]
    rh_out = wx["humidity_pct"]

    psat_out = 6.112 * math.exp((17.67 * t_out)  / (t_out  + 243.5))
    p_actual = (rh_out / 100.0) * psat_out
    psat_in  = 6.112 * math.exp((17.67 * ta) / (ta + 243.5))
    rh_in    = 100.0 * (p_actual / psat_in)

    return max(0.0, min(100.0, rh_in))


def run_calculation(reading: dict, validation: dict) -> dict:
    """
    Computes indoor WBGT. Resolves missing/0 sensor parameters using:
      - Indoor air temperature (Ta) - Required.
      - Relative humidity (RH) - Estimated via outdoor vapor pressure if missing/0.
      - Globe temperature (Tg) - Estimated via offset if missing/0.
      - Wet bulb temperature (Tnwb) - Calculated via Stull equation if missing/0.
    """
    location_type = reading.get("location_type", "default")
    quality = {}
    weather = WeatherClient()

    # ---- Resolve Air Temperature (Ta) ----
    ta = float(reading["air_temp_c"])
    quality["ta"] = "sensor"

    # ---- Resolve Relative Humidity (RH) ----
    rh_val = reading.get("relative_humidity_pct")
    if rh_val is not None and rh_val != "" and float(rh_val) != 0:
        rh = float(rh_val)
        quality["rh"] = "sensor"
    else:
        rh = _indoor_rh_from_weather(ta, weather)
        quality["rh"] = "estimated"

    # ---- Resolve Globe Temperature (Tg) ----
    tg_val = reading.get("globe_temp_c")
    if tg_val is not None and tg_val != "" and float(tg_val) != 0:
        tg = float(tg_val)
        quality["tg"] = "sensor"
    else:
        tg = _estimate_tg(ta, location_type)
        quality["tg"] = "estimated"

    # ---- Resolve Natural Wet-Bulb Temperature (Tnwb) ----
    tnwb_val = reading.get("wet_bulb_temperature")
    if tnwb_val is not None and tnwb_val != "" and float(tnwb_val) != 0:
        tnwb = float(tnwb_val)
        quality["tnwb"] = "sensor"
    else:
        tnwb = _stull_tnwb(ta, rh)
        quality["tnwb"] = "calculated"

    # ---- Calculate Indoor WBGT ----
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
