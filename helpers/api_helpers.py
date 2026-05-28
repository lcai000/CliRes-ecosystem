import streamlit as st
import requests
import pandas as pd
from datetime import timedelta
import json
import time

# Import your constants
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME

# Define the different URLs for authentication and data
AUTH_URL = "https://cognito-idp.us-west-2.amazonaws.com"
API_URL = "https://api.eplant.bio/api/external"


@st.cache_data(ttl=timedelta(minutes=50))
def get_access_token(username, password, client_id, st=st):
    """Authenticates with AWS Cognito to get a temporary AccessToken."""
    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
    }
    payload = {
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": client_id,
        "AuthParameters": {"USERNAME": username, "PASSWORD": password},
    }
    # if st: st.write("🔒 Authenticating with API...")
    
    try:
        response = requests.post(AUTH_URL, headers=headers, json=payload)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data['AuthenticationResult']['AccessToken']
        return access_token
    except Exception as e:
        st.error(f"Authentication Failed: {e}")
        return None


@st.cache_data(ttl="1h")
def fetch_plant_names(access_token, st=st):
    """
    Fetches ALL pages of association metadata to link plant names to serial numbers.
    """
    all_items = []
    start_index = None
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # if st: st.write("Fetching plant list...")
    while True:
        payload = {}
        if start_index:
            payload['startIndex'] = start_index

        try:
            response = requests.post(f"{API_URL}/association-metadata", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            page_data = result.get('data', [])
            if page_data:
                all_items.extend(page_data)
            
            if 'stopIndex' in result and result['stopIndex'] is not None:
                start_index = result['stopIndex']
            else:
                break
        except Exception as e:
            st.error(f"Error fetching plant list: {e}")
            break

    device_map = {}
    for item in all_items:
        serial = item.get('serial_number')
        name = item.get('plant_name')
        install_date = item.get('install_date')
        last_active = item.get('last_active') 
        
        if serial and name:
            device_map[serial] = {
                'name': name,
                'install_date': install_date,
                'last_active': last_active
            }

    devices = []
    for serial, data in device_map.items():
        devices.append({
            'name': data['name'], 
            'id': serial,
            'install_date': data['install_date'],
            'last_active': data['last_active']
        })
        
    return devices


@st.cache_data(ttl="10m")
def fetch_all_data(_selected_devices, start_date, end_date, access_token):
    """
    Fetches detailed data for all selected plants.
    Iterates through each device and chunk of time to isolate errors.
    PURE FUNCTION: No Streamlit UI elements inside the cache!
    """
    if not _selected_devices:
        return pd.DataFrame()
    
    headers = {"Authorization": f"Bearer {access_token}"}
    all_data_chunks = []
    chunk_size_days = 30
    
    print(f"Fetching data for {len(_selected_devices)} plant(s)...")

    for i, device in enumerate(_selected_devices):
        plant_name = device.get('name')
        current_start = start_date
        
        while current_start <= end_date:
            current_end = current_start + timedelta(days=chunk_size_days)
            if current_end > end_date:
                current_end = end_date
            
            print(f"🔍 {plant_name}: Fetching {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")

            payload = {
                "plantNames": [plant_name], 
                "timeStart": current_start.strftime("%Y-%m-%d %H:%M"),
                "timeStop": current_end.strftime("%Y-%m-%d %H:%M")
            }
            
            try:
                response = requests.post(f"{API_URL}/plantdata", headers=headers, json=payload)
                response.raise_for_status()
                
                if response.text:
                    try:
                        json_response = response.json()
                        if isinstance(json_response, dict):
                            for p_name, data_points in json_response.items():
                                if data_points:
                                    df = pd.DataFrame(data_points)
                                    df[COL_PLANT_NAME] = plant_name
                                    all_data_chunks.append(df)
                        elif isinstance(json_response, list):
                            if json_response:
                                df = pd.DataFrame(json_response)
                                df[COL_PLANT_NAME] = plant_name
                                all_data_chunks.append(df)
                    except json.JSONDecodeError:
                        print(f"Warning: Could not decode JSON for {plant_name}. Skipping.")
            
            except Exception as e:
                print(f"Error fetching {plant_name} chunk {current_start}: {e}")
            
            current_start = current_end + timedelta(days=1)
            time.sleep(0.5)

    if not all_data_chunks:
        print("The API returned no data for the selected criteria.")
        return pd.DataFrame()

    combined_df = pd.concat(all_data_chunks, ignore_index=True)
    
    # Standardize the column names and data types
    rename_map = {
        'sample_time': COL_TIMESTAMP,
        'received_time': 'received_time',
        'temperature': 'Temperature_C',
        'humidity': 'Humidity',
        'dendrometer': 'Dendrometer (microns)',
        'dendrometer_value': 'Dendrometer (microns)',
        'dew_point': 'Dew Point',
        'light': 'Light (W/m^2)',
        'system_voltage': 'System Voltage (V)',
        'lean_angle': 'Lean Angle (deg)',
        'lean_direction': 'Lean Direction (deg)'
    }
    combined_df.rename(columns=lambda c: rename_map.get(str(c).lower().strip(), c), inplace=True)

    if COL_TIMESTAMP in combined_df.columns:
        combined_df[COL_TIMESTAMP] = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce')
    else:
        print(f"A valid timestamp column ('{COL_TIMESTAMP}') could not be found.")
        return pd.DataFrame()

    # Convert numerics
    numeric_cols = [
        'Temperature_C', 'Humidity', 'Dendrometer (microns)', 'Dew Point', 
        'Light (W/m^2)', 'System Voltage (V)', 'Lean Angle (deg)', 'Lean Direction (deg)'
    ]
    for col in numeric_cols:
         if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')
    
    print(f"Data fetched! Total records: {len(combined_df)}")
    return combined_df


@st.cache_data(ttl="1h")
def process_large_historical_csv(uploaded_file, target_trees):
    """Safely loads massive local datasets by only grabbing necessary columns and trees."""
    # 1. THE BLINDERS: Only pull these exact columns from the massive file
    columns_to_keep = ['plant_name', 'sample_time', 'dendrometer', 'temperature']
    
    try:
        # Read the file using only the specified columns
        df = pd.read_csv(uploaded_file, usecols=columns_to_keep)
        
        # 2. INSTANT FILTER: Drop any tree that isn't in our target list
        if target_trees:
            df = df[df['plant_name'].isin(target_trees)]
            
        # 3. Translate to the Universal Schema
        translator_map = {
            'sample_time': COL_TIMESTAMP,
            'dendrometer': 'Dendrometer (microns)',
            'temperature': 'Temperature_C',
            'plant_name': COL_PLANT_NAME
        }
        df.rename(columns=translator_map, inplace=True)
        
        # Ensure timestamps are correct
        if COL_TIMESTAMP in df.columns:
            df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP], errors='coerce')
            
        return df
        
    except ValueError as e:
        st.error(f"Could not find the expected columns. Make sure this is an ePlant export. {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error processing CSV: {e}")
        return pd.DataFrame()