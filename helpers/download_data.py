import pandas as pd
from datetime import datetime, timedelta, date
import sys
import os
import toml
import time

# --- Add the parent directory to the Python path ---
# This allows the script to find the 'helpers' module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Import your own helper files ---
from helpers.api_helpers import get_access_token, fetch_plant_names, fetch_all_data

# --- Configuration ---
# This is the only section you need to edit.

# 1. Define the output folder and filename for your CSV
OUTPUT_DIR = 'data'
OUTPUT_FILENAME = 'data_for_labeling.csv'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 2. List the exact plant names you want to download data for.
#    To download all plants, leave this list empty: PLANTS_TO_DOWNLOAD = []
PLANTS_TO_DOWNLOAD = [
    "HEB-10 Anacacho S",
    "Ashe juniper - uneffected tree 2",
    "Ashe juniper Inf Tree 3",
    "Ashe juniper Unf tree 1",
    "HEB-7-Anacacho N",
    "HEB-1-Lacey Oak",
    "HEB-2-Montezuma Cypress",
    "HEB-3-Mexican Sycamore",
    "HEB-4-Little Gem Magnolia",
    "HEB-6-Desert Willow N",
    "HEB-9-Desert Willow S",
    "JBWS Anacua ",
    "P2-T3-Biochar Elm",
    "P2-T4-Control Elm",
    "P2-T5-Chinquapin",
    "P3-T2-Redbud",
    "P3-T3-Biochar Elm",
    "P3-T4-Control Elm",
    "P3-T5-Chinquapin",
    "P4-T3-Biochar Elm",
    "P4-T4-Control Elm",
    "P4-T5-Chinquapin",
    "P5-T2-Redbud",
    "P5-T3-Biochar Elm",
    "P5-T4-Control Elm",
    "P5-T5-Chinquapin"
]
# 3. Set the date range for the data you want to download.
#    Format: date(YYYY, M, D)
DOWNLOAD_START_DATE = date(2024, 1, 1)
DOWNLOAD_END_DATE = date.today()


def download_data_for_labeling():
    """
    Fetches historical data for a specific list of plants and date range,
    then saves it to a single CSV file.
    """
    print("--- Starting Data Download Utility ---")
    
    # --- 1. Authenticate and get full device list ---
    try:
        secrets_path = os.path.join(project_root, '.streamlit', 'secrets.toml')
        secrets = toml.load(secrets_path)
        username = secrets["username"]
        password = secrets["password"]
        client_id = secrets["client_id"]
        
        access_token = get_access_token(username, password, client_id, st=None)
        all_available_devices = fetch_plant_names(access_token, st=None)

    except Exception as e:
        print(f"\nFATAL ERROR: Could not authenticate or fetch device list. {e}")
        return

    # --- 2. Determine which plants to process ---
    devices_to_process = []
    if PLANTS_TO_DOWNLOAD:
        print(f"\nNOTE: Targeting {len(PLANTS_TO_DOWNLOAD)} specific plant(s) for download.")
        devices_to_process = [d for d in all_available_devices if d.get('name') in PLANTS_TO_DOWNLOAD]
        if not devices_to_process:
            print("FATAL ERROR: None of the plants in the manual list were found in the API's device list.")
            return
    else:
        print("\nNOTE: No specific plants listed. Downloading data for all available plants.")
        devices_to_process = all_available_devices

    # --- 3. Fetch data in polite, 30-day chunks ---
    all_data_chunks = []
    chunk_size_days = 30
    
    print(f"\nFetching data for {len(devices_to_process)} plants from {DOWNLOAD_START_DATE} to {DOWNLOAD_END_DATE}...")

    for device in devices_to_process:
        plant_name = device.get('name')
        print(f"\nProcessing plant: {plant_name}")
        
        current_chunk_start = DOWNLOAD_START_DATE
        while current_chunk_start < DOWNLOAD_END_DATE:
            current_chunk_end = current_chunk_start + timedelta(days=chunk_size_days)
            if current_chunk_end > DOWNLOAD_END_DATE:
                current_chunk_end = DOWNLOAD_END_DATE

            print(f"  - Fetching chunk: {current_chunk_start} to {current_chunk_end}...")
            try:
                data_chunk = fetch_all_data(tuple([device]), current_chunk_start, current_chunk_end, access_token, st=None)
                if not data_chunk.empty:
                    all_data_chunks.append(data_chunk)
                time.sleep(1) 
            except Exception as e:
                print(f"    - Warning: Could not fetch data for this chunk. Error: {e}")
            
            current_chunk_start += timedelta(days=chunk_size_days)

    if not all_data_chunks:
        print("\nFATAL ERROR: No data could be fetched from the API after all attempts.")
        return
        
    # --- 4. Combine and Save Data ---
    combined_df = pd.concat(all_data_chunks, ignore_index=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    
    # Save the final dataframe to a CSV file, without the pandas index column
    combined_df.to_csv(output_path, index=False)
    
    print("\n--- Data Download Complete ---")
    print(f"Successfully saved {len(combined_df)} rows of data to:")
    print(output_path)


if __name__ == '__main__':
    download_data_for_labeling()