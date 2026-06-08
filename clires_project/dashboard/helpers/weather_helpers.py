import pandas as pd
import requests
import numpy as np
from datetime import date, timedelta
from django.core.cache import cache
from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.cache_utils import DataResult

ST_EDS_LAT = 30.2303
ST_EDS_LON = -97.7556
HISTORICAL_PLANT_NAME = "Reference: Austin Historical (St. Eds)"


def fetch_historical_weather(start_date=None, end_date=None):
    """Fetches historical hourly weather data for St. Edward's University from Open-Meteo."""
    if not start_date:
        start_date = date.today() - timedelta(days=7)
    if not end_date:
        end_date = date.today()

    cache_key = f"weather:history:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached is not None:
        return DataResult(data=cached)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": ST_EDS_LAT,
        "longitude": ST_EDS_LON,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": ["temperature_2m", "relative_humidity_2m", "rain"],
        "timezone": "UTC"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        hourly = data.get('hourly', {})

        df = pd.DataFrame({
            COL_TIMESTAMP: pd.to_datetime(hourly['time']),
            'Temperature_C': hourly['temperature_2m'],
            'Humidity': hourly['relative_humidity_2m'],
            'Rainfall_mm': hourly['rain']
        })

        df[COL_PLANT_NAME] = HISTORICAL_PLANT_NAME
        df['Austin_Temp_C'] = df['Temperature_C']
        df['Austin_Humidity'] = df['Humidity']
        df['Dendrometer (microns)'] = np.nan
        df[COL_TIMESTAMP] = df[COL_TIMESTAMP].dt.tz_localize(None)

        cache.set(cache_key, df, timeout=3600)
        return DataResult(data=df)

    except Exception as e:
        return DataResult(errors=[f"Open-Meteo Fetch Error: {e}"])
