import streamlit as st
import pandas as pd
import os

# Import your constants
from helpers.config import COL_PLANT_NAME, COL_TIMESTAMP

@st.cache_data
def load_uploaded_data(uploaded_files, plant_name_col, timestamp_col):
    """
    Parses "dirty" Kestrel CSVs and returns a standardized DataFrame.
    """
    dataframes = {}
    st.write("Processing uploaded Kestrel files...")

    for uploaded_file in uploaded_files:
        try:
            uploaded_file.seek(0)
            device_name_line = pd.read_csv(uploaded_file, header=None, nrows=1).iloc[0, 1]
            uploaded_file.seek(0)

            df = pd.read_csv(uploaded_file, skiprows=7, header=None)
            df = df.iloc[:, :5]
            df.columns = ['Date_str', 'Temperature_F', 'Humidity', 'Heat Index', 'Dew Point']
            
            df[plant_name_col] = device_name_line
            df[timestamp_col] = pd.to_datetime(df['Date_str'], format='%m/%d/%y %H:%M')
            df['Temperature_C'] = pd.to_numeric(df['Temperature_F'], errors='coerce').apply(lambda f: (f - 32) * 5.0 / 9.0)
            df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
            df['Dew Point'] = pd.to_numeric(df['Dew Point'], errors='coerce')

            final_cols = [timestamp_col, plant_name_col, 'Temperature_C', 'Humidity', 'Dew Point']
            
            # --- THIS IS THE FIX ---
            # We create a new, clean DataFrame from the original 'df'
            # This avoids the SettingWithCopyWarning.
            df_final = df[[col for col in final_cols if col in df.columns]].copy()
            df_final.dropna(inplace=True)
            
            if not df_final.empty:
                dataframes[device_name_line] = df_final
                st.success(f"Successfully processed '{uploaded_file.name}'")

        except Exception as e:
            st.error(f"Failed to process Kestrel file '{uploaded_file.name}'.")
            st.exception(e)

    return dataframes
