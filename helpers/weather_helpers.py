import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import date, timedelta, datetime

# Import your shared config constants
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME

# --- Configuration ---
# Coordinates for St. Edward's University
ST_EDS_LAT = 30.2303
ST_EDS_LON = -97.7556
HISTORICAL_PLANT_NAME = "Reference: Austin Historical (St. Eds)"

@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_historical_weather(start_date=None, end_date=None):
    """
    Fetches historical hourly weather data for St. Edward's University
    from the Open-Meteo Historical Weather API.
    """
    if not start_date:
        start_date = date.today() - timedelta(days=7)
    if not end_date:
        end_date = date.today()

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

        # Process Hourly Data
        hourly = data.get('hourly', {})
        
        df = pd.DataFrame({
            COL_TIMESTAMP: pd.to_datetime(hourly['time']),
            'Temperature_C': hourly['temperature_2m'],
            'Humidity': hourly['relative_humidity_2m'],
            'Rainfall_mm': hourly['rain']
        })
        
        # Add Plant Name for Long Format
        df[COL_PLANT_NAME] = HISTORICAL_PLANT_NAME
        
        # Duplicate columns for specific referencing (optional but helpful)
        df['Austin_Temp_C'] = df['Temperature_C']
        df['Austin_Humidity'] = df['Humidity']
        
        # Add placeholder for Dendrometer
        df['Dendrometer (microns)'] = np.nan
        
        # Ensure timestamp is naive to match your other data
        df[COL_TIMESTAMP] = df[COL_TIMESTAMP].dt.tz_localize(None)

        return df

    except Exception as e:
        print(f"Open-Meteo Fetch Error: {e}")
        return pd.DataFrame()