import sys
import os

# --- FIX: Add project root to path for direct execution ---
if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import numpy as np

# Import your shared config constants
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME

# --- Configuration ---
# Direct links to the CSV files on the LCRA Hydromet site
TEMP_URL = "https://hydromet.lcra.org/media/Temperature.csv"
HUMIDITY_URL = "https://hydromet.lcra.org/media/Humidity.csv"
RAINFALL_URL = "https://hydromet.lcra.org/media/Rainfall.csv" 

# List of Proxies
# We use a distinct name starting with "Reference:" to separate it from trees
PROXY_SITES = [
    {'id': 4543, 'name': "Reference: Austin (Lady Bird Lake)"},
    {'id': 3999, 'name': "Reference: Austin (Tom Miller Dam)"},
    {'id': 4558, 'name': "Reference: Austin (Colorado River)"}
]

@st.cache_data(ttl=300)  # Cache the data for 5 minutes
def fetch_lcra_data():
    """
    Fetches the latest Temperature, Humidity, and Rainfall data from LCRA.
    Includes robust error handling and failover logic.
    """
    try:
        # 1. Load the CSVs
        try:
            # Use on_bad_lines='skip' to avoid crashing on malformed rows
            temp_df = pd.read_csv(TEMP_URL, header=None, usecols=[0, 2, 3], names=['Site', 'Timestamp_str', 'Temperature_F'], on_bad_lines='skip')
            humidity_df = pd.read_csv(HUMIDITY_URL, header=None, usecols=[0, 3], names=['Site', 'Humidity'], on_bad_lines='skip')
            rain_df = pd.read_csv(RAINFALL_URL, header=None, usecols=[0, 3], names=['Site', 'Rainfall_in'], on_bad_lines='skip')
        except Exception as csv_err:
            print(f"LCRA CSV Download Error: {csv_err}")
            return pd.DataFrame()

        # 2. Find a valid site (Failover Logic)
        valid_site = None
        site_temp_row = pd.DataFrame()
        
        for site_info in PROXY_SITES:
            site_id = site_info['id']
            
            # Check for temp data
            temp_df['Site'] = pd.to_numeric(temp_df['Site'], errors='coerce')
            temp_row = temp_df[temp_df['Site'] == site_id].copy()
            
            if not temp_row.empty:
                # Check if the timestamp is actually parseable
                try:
                    pd.to_datetime(temp_row['Timestamp_str'].iloc[0])
                    valid_site = site_info
                    site_temp_row = temp_row
                    break # Found a working site!
                except:
                    continue 
        
        if not valid_site:
            st.warning("Could not find live temperature data for any South Austin proxy sites.")
            return pd.DataFrame()

        # 3. --- Fetch Other Metrics ---
        site_id = valid_site['id']
        site_name = valid_site['name']
        
        humidity_df['Site'] = pd.to_numeric(humidity_df['Site'], errors='coerce')
        rain_df['Site'] = pd.to_numeric(rain_df['Site'], errors='coerce')
        
        humidity_row = humidity_df[humidity_df['Site'] == site_id].copy()
        rain_row = rain_df[rain_df['Site'] == site_id].copy()

        # 4. --- Combine and Standardize ---
        final_df = pd.DataFrame()
        final_df[COL_PLANT_NAME] = [site_name]
        
        # Timestamp
        raw_timestamp = site_temp_row['Timestamp_str'].iloc[0]
        final_df[COL_TIMESTAMP] = pd.to_datetime(raw_timestamp).tz_localize(None)

        # Temperature
        temp_f = pd.to_numeric(site_temp_row['Temperature_F'].iloc[0], errors='coerce')
        # Standard column for shared plotting
        final_df['Temperature_C'] = (temp_f - 32) * 5.0 / 9.0
        # Specific column for isolated plotting (as requested)
        final_df['Austin_Temp_C'] = final_df['Temperature_C']

        # Humidity
        if not humidity_row.empty:
            hum_val = pd.to_numeric(humidity_row['Humidity'].iloc[0], errors='coerce')
            final_df['Humidity'] = hum_val
            final_df['Austin_Humidity'] = hum_val # Specific column
        else:
            final_df['Humidity'] = np.nan
            final_df['Austin_Humidity'] = np.nan

        # Rainfall
        if not rain_row.empty:
            rain_in = pd.to_numeric(rain_row['Rainfall_in'].iloc[0], errors='coerce')
            final_df['Rainfall_mm'] = rain_in * 25.4
        else:
            final_df['Rainfall_mm'] = 0.0
        
        final_df['Dendrometer (microns)'] = np.nan
        
        # Dew Point
        if not pd.isna(final_df['Humidity']).any() and not pd.isna(final_df['Temperature_C']).any():
            final_df['Dew Point'] = final_df['Temperature_C'] - ((100 - final_df['Humidity'])/5)
        else:
            final_df['Dew Point'] = np.nan

        return final_df

    except Exception as e:
        print(f"LCRA General Processing Error: {e}")
        return pd.DataFrame()

# Add this block to run the file directly for debugging
if __name__ == "__main__":
    print("--- Starting LCRA Debug Test ---")
    try:
        # Mock streamlit caching for local run
        st.cache_data = lambda ttl=None: lambda func: func
        
        df = fetch_lcra_data()
        if not df.empty:
            print("\nSuccess! Data Retrieved:")
            print(df)
        else:
            print("\nFailed to retrieve data.")
    except Exception as e:
        print(f"\nCritical Failure: {e}")