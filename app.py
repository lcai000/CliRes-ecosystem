#-- to run locally: python -m streamlit run app.py --

#-- to to add a visual compoent as another page (allowing the person to see what is happening)
#-- add a frequency catagorization of the data collected so we can unserstand what is happening.

import streamlit as st
import pandas as pd
from datetime import timedelta, date
import json

# --- Import your helper functions ---
from helpers.kestrel_loader import load_uploaded_data
from helpers.api_helpers import get_access_token, fetch_plant_names, fetch_all_data, process_large_historical_csv
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME

# Import helpers safely to avoid crashes if files are missing
try:
    from helpers.lcra_helpers import fetch_lcra_data
except ImportError:
    fetch_lcra_data = None

try:
    from helpers.weather_helpers import fetch_historical_weather
except ImportError:
    fetch_historical_weather = None

# Set the page configuration for the entire app
st.set_page_config(layout="wide", page_title="Cli-Res Project Dashboard")

# --- This is the content for your main "Home" page ---
st.image("Images/Cli-Res_LogoWithBackground.png", width=250)
st.title("🌳 SEU Cli-Res Analysis Helper")
st.header("Welcome to the Project Dashboard!")
st.markdown("""
This application contains several tools to help you analyze your tree and environmental data.

**To get started:**
1.  Use the **Data Sources** sections in the sidebar to load your data.
2.  Once data is loaded, select a tool from the navigation menu on the left.
3.  Note that data loaded here is available across all pages until you clear it or close the app.

            
**Below you will find:** 
1.  A map with the location of the plots and a list of the trees in each plot.
2.  the status of the sensors and the data they are collecting. (work in progress)
""")




# --- Maps and Images of Plots --- 
st.divider()
st.markdown("### Maps and Images of Plots")
st.image("Images/St.Edwards_plot_map.jpg")
st.image("Images/Plot1.jpg")
st.image("Images/Plot2.jpg")
st.image("Images/Plot3.jpg")
st.image("Images/Plot4.jpg")
st.image("Images/Plot5.jpg")
st.divider()


# --- SHARED SIDEBAR FOR DATA LOADING ---
with st.sidebar:
    st.header("Data Sources")

    # --- Data Source 1: API ---
    with st.expander("1. Tree Sensors (API)", expanded=True):
        
        # 1. MOVED TO THE TOP: Always create dates first so they are globally available!
        today = pd.to_datetime('today').date()
        default_start = today - timedelta(days=7)
        api_start_date = st.date_input("Start Date", value=default_start, key='api_start')
        api_end_date = st.date_input("End Date", value=today, key='api_end')

        # 2. Now run your risky API code
        try:
            username = st.secrets.get("username")
            password = st.secrets.get("password")
            client_id = st.secrets.get("client_id")
            
            if not all([username, password, client_id]):
                st.info("API credentials not found in secrets.toml.")
            else:
                access_token = get_access_token(username, password, client_id)
                devices_list = fetch_plant_names(access_token)
                
                selected_devices = st.multiselect(
                    "Select Trees:", 
                    options=devices_list,
                    format_func=lambda device: device.get('name', 'Unnamed Device'),
                )

                if st.button("Fetch Tree Data", type="primary"):
                    if 'api_df' in st.session_state:
                        del st.session_state['api_df']
                    
                    if selected_devices:
                        # Safely uses the dates created above
                        api_df = fetch_all_data(tuple(selected_devices), api_start_date, api_end_date, access_token)
                        if not api_df.empty:
                            st.session_state['api_df'] = api_df
                            st.success(f"Loaded data for {len(selected_devices)} trees!")
                            
                            st.divider() 
                            st.caption("Export Data:")
                            csv_data = api_df.to_csv(index=False).encode('utf-8')
                            json_data = api_df.to_json(orient="records", date_format="iso")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.download_button(
                                    "CSV", 
                                    data=csv_data, 
                                    file_name="data.csv", 
                                    mime="text/csv", 
                                    use_container_width=True
                                )
                            with col2:
                                st.download_button(
                                    "JSON", 
                                    data=json_data, 
                                    file_name="data.json", 
                                    mime="application/json", 
                                    use_container_width=True
                                )





                        else:
                            st.warning("No data found for selected range.")
                    else:
                        st.warning("Please select at least one tree.")
                    
                        
        except Exception as e:
            st.error("Could not connect to API.")
            st.exception(e)
    
    # --- Data Source 2: Reference Weather ---
    with st.expander("2. Reference Weather (Austin)", expanded=False):
        st.write("**History**")
        st.caption("(Open-Meteo)")
        if st.button("Fetch History"):
            if fetch_historical_weather:
                hist_df = fetch_historical_weather(api_start_date, api_end_date)
                if not hist_df.empty:
                    st.session_state['history_df'] = hist_df
                    st.success("History loaded!")
                else:
                    st.warning("History unavailable.")
            else:
                st.error("Weather helper missing.")


    # --- Data Source 3: Kestrel File Upload ---
    with st.expander("3. Manual Upload (Kestrel)", expanded=False):
        uploaded_files = st.file_uploader("Upload Kestrel CSV files:", accept_multiple_files=True)
        if uploaded_files:
            kestrel_dataframes = load_uploaded_data(uploaded_files, COL_PLANT_NAME, COL_TIMESTAMP)
            if kestrel_dataframes:
                kestrel_df = pd.concat(kestrel_dataframes.values(), ignore_index=True)
                st.session_state['kestrel_df'] = kestrel_df
                st.success("Kestrel files loaded!")

    # --- Data Source 4: Massive Historical Export ---
    with st.expander("4. Large Historical CSV", expanded=False):
        st.write("Extract specific trees from a massive export file without crashing memory.")
        large_csv = st.file_uploader("Upload Large Yearly Export:", type=['csv'], key="large_csv")
        
        # Let the user type the exact names of the trees they want to extract
        target_trees_input = st.text_input(
            "Trees to extract (comma separated):", 
            placeholder="e.g., P2-T2-Redbud, P4-T4-Control Elm"
        )
        
        if st.button("Extract Target Trees", type="primary"):
            if large_csv and target_trees_input:
                # Clean up the user input into a proper Python list
                target_trees = [t.strip() for t in target_trees_input.split(",")]
                
                with st.spinner("Ripping through massive file..."):
                    hist_csv_df = process_large_historical_csv(large_csv, target_trees)
                    
                    if not hist_csv_df.empty:
                        st.session_state['hist_csv_df'] = hist_csv_df
                        st.success(f"Successfully extracted {len(hist_csv_df)} readings for your targets!")
            else:
                st.warning("Please upload a file and type the target trees first.")

    #---- Data Management ---- 
    st.divider()
    if st.button("Clear All Data", type="secondary"):
        keys_to_clear = ['api_df', 'kestrel_df', 'lcra_df', 'history_df', 'combined_df']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.cache_data.clear()
        st.success("All data cleared.")
        st.rerun()


# --- Combine and Smart Merge Data ---
data_to_combine = []

# 1. Gather and Merge API Data with History (if available)
if 'api_df' in st.session_state:
    api_df = st.session_state.api_df.copy()
    
    # SMART MERGE: If we have history, merge it into API data so tree rows get weather context
    if 'history_df' in st.session_state:
        history_df = st.session_state.history_df.sort_values(COL_TIMESTAMP)
        api_df = api_df.sort_values(COL_TIMESTAMP)
        
        # Ensure timestamp compatibility (make api_df timezone-naive)
        if pd.api.types.is_datetime64_any_dtype(api_df[COL_TIMESTAMP]):
            if api_df[COL_TIMESTAMP].dt.tz is not None:
                api_df[COL_TIMESTAMP] = api_df[COL_TIMESTAMP].dt.tz_convert('UTC').dt.tz_localize(None)
        
        try:
            # Use merge_asof to find the closest weather reading for each tree reading
            merged_api = pd.merge_asof(
                api_df, 
                history_df[[COL_TIMESTAMP, 'Austin_Temp_C', 'Austin_Humidity', 'Rainfall_mm']], 
                on=COL_TIMESTAMP, 
                direction='nearest',
                tolerance=pd.Timedelta('1 hour')
            )
            api_df = merged_api
        except Exception as e:
            st.error(f"Merge error: {e}")
            
    # BROADCAST: If we DON'T have history but DO have live data, use that as fallback
    elif 'lcra_df' in st.session_state:
        ref_vals = st.session_state.lcra_df.iloc[0]
        # Broadcast columns if they exist in the reference data
        cols_to_broadcast = ['Austin_Temp_C', 'Austin_Humidity', 'Rainfall_mm']
        for col in cols_to_broadcast:
            if col in ref_vals:
                api_df[col] = ref_vals[col]

    data_to_combine.append(api_df)

if 'kestrel_df' in st.session_state:
    data_to_combine.append(st.session_state.kestrel_df)

if 'lcra_df' in st.session_state:
    data_to_combine.append(st.session_state.lcra_df)

if 'history_df' in st.session_state:
    data_to_combine.append(st.session_state.history_df)

if 'hist_csv_df' in st.session_state:
    data_to_combine.append(st.session_state.hist_csv_df)

# 2. Final Concatenation
if data_to_combine:
    st.session_state['combined_df'] = pd.concat(data_to_combine, ignore_index=True)
    
    with st.sidebar:
        st.divider()
        st.subheader("Global Filter")
        df = st.session_state['combined_df']
        if COL_TIMESTAMP in df.columns:
            df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP], errors='coerce')
            df.dropna(subset=[COL_TIMESTAMP], inplace=True)

            if not df.empty:
                min_date = df[COL_TIMESTAMP].min().date()
                max_date = df[COL_TIMESTAMP].max().date()
                
                # Allow selecting TODAY even if data is old
                today = date.today()
                if max_date < today:
                    max_date = today

                if min_date >= max_date:
                    max_date = min_date + timedelta(days=1)
                    
                st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, key='start_date')
                st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, key='end_date')

                # =========================================================
                # 📥 EXPORT BUTTONS (Placed directly under the filter)
                # =========================================================
                st.divider()
                st.caption("Export Merged Data:")
                
                # Format the combined dataframe
                csv_data = df.to_csv(index=False).encode('utf-8')
                json_data = df.to_json(orient="records", date_format="iso")
                
                # Display buttons side-by-side
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button("CSV", data=csv_data, file_name="clires_export.csv", mime="text/csv", use_container_width=True)
                with col2:
                    st.download_button("JSON", data=json_data, file_name="clires_export.json", mime="application/json", use_container_width=True)
                    




# --- SENSOR FLEET STATUS (Moved to Top) ---
st.divider()
st.subheader("📡 Device Fleet Inventory")

# We use a container so we can populate this even if the sidebar runs 'after' in the script order
status_container = st.container()

# Check if metadata exists (populated by sidebar execution)
if 'all_devices_metadata' in st.session_state:
    with status_container:
        devices = st.session_state['all_devices_metadata']
        if devices:
            inventory_df = pd.DataFrame(devices)
            
            # --- INTELLIGENT COLUMN SELECTION ---
            # Try to find the 'last seen' column dynamically
            possible_status_cols = ['last_active', 'last_contact', 'latest_data_time', 'last_seen', 'updated_at', 'last_communication']
            status_col = next((c for c in possible_status_cols if c in inventory_df.columns), None)
            
            # Define columns to display
            display_cols = ['name', 'install_date']
            if status_col:
                display_cols.append(status_col)
            
            # Filter and Rename for Display
            final_df = inventory_df[[c for c in display_cols if c in inventory_df.columns]].copy()
            
            rename_map = {
                'name': 'Tree/Device Name',
                'install_date': 'Install Date',
                status_col: 'Last Server Contact (UTC)'
            }
            # Remove None keys
            if None in rename_map: del rename_map[None]
            
            final_df = final_df.rename(columns=rename_map)
            
            # Display
            st.dataframe(
                final_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Install Date": st.column_config.DateColumn("Install Date", format="YYYY-MM-DD"),
                    "Last Server Contact (UTC)": st.column_config.DatetimeColumn("Last Server Contact", format="D MMM YYYY, h:mm a")
                }
            )
        else:
            st.info("No devices found in API account.")
else:
    with status_container:
        st.info("💡 Connect to the API in the sidebar to see the full list of devices and their status.")
