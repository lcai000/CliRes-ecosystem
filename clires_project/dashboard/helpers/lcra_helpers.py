import pandas as pd
import numpy as np
from django.core.cache import cache
from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.cache_utils import DataResult

TEMP_URL = "https://hydromet.lcra.org/media/Temperature.csv"
HUMIDITY_URL = "https://hydromet.lcra.org/media/Humidity.csv"
RAINFALL_URL = "https://hydromet.lcra.org/media/Rainfall.csv"

PROXY_SITES = [
    {'id': 4543, 'name': "Reference: Austin (Lady Bird Lake)"},
    {'id': 3999, 'name': "Reference: Austin (Tom Miller Dam)"},
    {'id': 4558, 'name': "Reference: Austin (Colorado River)"}
]


def fetch_lcra_data():
    """Fetches the latest Temperature, Humidity, and Rainfall data from LCRA."""
    cache_key = "lcra:live"
    cached = cache.get(cache_key)
    if cached is not None:
        return DataResult(data=cached)

    try:
        temp_df = pd.read_csv(TEMP_URL, header=None, usecols=[0, 2, 3],
                              names=['Site', 'Timestamp_str', 'Temperature_F'], on_bad_lines='skip')
        humidity_df = pd.read_csv(HUMIDITY_URL, header=None, usecols=[0, 3],
                                  names=['Site', 'Humidity'], on_bad_lines='skip')
        rain_df = pd.read_csv(RAINFALL_URL, header=None, usecols=[0, 3],
                              names=['Site', 'Rainfall_in'], on_bad_lines='skip')
    except Exception as e:
        return DataResult(errors=[f"LCRA CSV Download Error: {e}"])

    valid_site = None
    site_temp_row = pd.DataFrame()

    for site_info in PROXY_SITES:
        site_id = site_info['id']
        temp_df['Site'] = pd.to_numeric(temp_df['Site'], errors='coerce')
        temp_row = temp_df[temp_df['Site'] == site_id].copy()
        if not temp_row.empty:
            try:
                pd.to_datetime(temp_row['Timestamp_str'].iloc[0])
                valid_site = site_info
                site_temp_row = temp_row
                break
            except Exception:
                continue

    if not valid_site:
        return DataResult(errors=["Could not find live temperature data for any South Austin proxy sites."])

    site_id = valid_site['id']
    site_name = valid_site['name']

    humidity_df['Site'] = pd.to_numeric(humidity_df['Site'], errors='coerce')
    rain_df['Site'] = pd.to_numeric(rain_df['Site'], errors='coerce')
    humidity_row = humidity_df[humidity_df['Site'] == site_id].copy()
    rain_row = rain_df[rain_df['Site'] == site_id].copy()

    final_df = pd.DataFrame()
    final_df[COL_PLANT_NAME] = [site_name]
    raw_timestamp = site_temp_row['Timestamp_str'].iloc[0]
    final_df[COL_TIMESTAMP] = pd.to_datetime(raw_timestamp).tz_localize(None)

    temp_f = pd.to_numeric(site_temp_row['Temperature_F'].iloc[0], errors='coerce')
    final_df['Temperature_C'] = (temp_f - 32) * 5.0 / 9.0
    final_df['Austin_Temp_C'] = final_df['Temperature_C']

    if not humidity_row.empty:
        hum_val = pd.to_numeric(humidity_row['Humidity'].iloc[0], errors='coerce')
        final_df['Humidity'] = hum_val
        final_df['Austin_Humidity'] = hum_val
    else:
        final_df['Humidity'] = np.nan
        final_df['Austin_Humidity'] = np.nan

    if not rain_row.empty:
        rain_in = pd.to_numeric(rain_row['Rainfall_in'].iloc[0], errors='coerce')
        final_df['Rainfall_mm'] = rain_in * 25.4
    else:
        final_df['Rainfall_mm'] = 0.0

    final_df['Dendrometer (microns)'] = np.nan

    if not pd.isna(final_df['Humidity']).any() and not pd.isna(final_df['Temperature_C']).any():
        final_df['Dew Point'] = final_df['Temperature_C'] - ((100 - final_df['Humidity']) / 5)
    else:
        final_df['Dew Point'] = np.nan

    cache.set(cache_key, final_df, timeout=300)
    return DataResult(data=final_df)
