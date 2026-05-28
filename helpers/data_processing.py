
import pandas as pd
import streamlit as st
import numpy as np

# Import your constants from the shared config file
from helpers.config import COL_PLANT_NAME, TIME_GRANULARITY_MAP, COL_TIMESTAMP

def filter_dataframe(df, configs, timestamp_col): # <-- MODIFIED
    """
    Filters a dataframe based on selected plants and a date range.
    """
    filtered_df = df.copy()
    
    # Use the timestamp_col passed as an argument
    if timestamp_col and timestamp_col in filtered_df.columns:
        if 'start_date' in configs and 'end_date' in configs:
            filtered_df[timestamp_col] = pd.to_datetime(filtered_df[timestamp_col], errors='coerce')
            filtered_df.dropna(subset=[timestamp_col], inplace=True)
            filtered_df = filtered_df[
                (filtered_df[timestamp_col].dt.date >= configs['start_date']) &
                (filtered_df[timestamp_col].dt.date <= configs['end_date'])
            ]

    if configs.get('selected_plants'):
        filtered_df = filtered_df[filtered_df[COL_PLANT_NAME].isin(configs['selected_plants'])]
    
    # The year filter logic is no longer needed as we have a global date filter
    
    return filtered_df

def aggregate_dataframe(df, configs, timestamp_col):
    """
    Aggregates a dataframe by a specified time granularity. This version is
    more robust and uses the modern pd.Grouper for time-based operations.
    """
    agg_level = configs.get('aggregation_level', '5-minute (Raw)')

    if agg_level in ['5-minute (Raw)', 'Raw']:
        return df
        
    if not timestamp_col or timestamp_col not in df.columns:
        st.warning(f"Cannot aggregate by time without a valid timestamp column.")
        return pd.DataFrame()

    agg_method_map = {"Mean (Average)": "mean", "Minimum": "min", "Maximum": "max", "Mean with Min/Max Range": ["mean", "min", "max"]}
    agg_func = agg_method_map.get(configs.get('aggregation_method', 'Mean (Average)'))
    
    # Get the correct resampling frequency from our (now updated) map
    resample_freq = TIME_GRANULARITY_MAP.get(agg_level)
    
    # Determine the columns to aggregate (all numeric columns)
    cols_to_agg = [c for c in df.select_dtypes(include=np.number).columns]
    
    # Determine the columns to group by
    should_group_by_plant = COL_PLANT_NAME in df.columns and not configs.get('plot_overall_average', False)
    grouping_cols = [pd.Grouper(key=timestamp_col, freq=resample_freq)]
    if should_group_by_plant:
        grouping_cols.insert(0, COL_PLANT_NAME)

    # Perform the aggregation in a try...except block for safety
    try:
        aggregated_df = df.groupby(grouping_cols)[cols_to_agg].agg(agg_func)
    except Exception as e:
        st.error(f"Failed to aggregate data. Error: {e}")
        return pd.DataFrame()

    # Flatten multi-level columns if they were created
    if isinstance(aggregated_df.columns, pd.MultiIndex):
        aggregated_df.columns = ['_'.join(col).strip() for col in aggregated_df.columns.values]
        
    aggregated_df.reset_index(inplace=True)
    
    # Drop rows only if ALL of the aggregated value columns are empty
    # This is more robust than dropping if any single value is empty.
    value_cols = [c for c in aggregated_df.columns if c not in [COL_PLANT_NAME, timestamp_col]]
    aggregated_df.dropna(how='all', subset=value_cols, inplace=True)
    
    return aggregated_df

def standardize_dataframe(df):
    """
    Takes a raw combined dataframe and standardizes column names and data types
    from various sources into a single, clean format.
    """
    df_processed = df.copy()

    # --- 1. Standardize Column Names ---
    # Create a map of possible raw column names (in lowercase) to our standard app names
    rename_map = {
        'sample time': COL_TIMESTAMP,
        'timestamp': COL_TIMESTAMP,
        'sample_time': COL_TIMESTAMP,
        'temperature': 'Temperature_C',
        'temperature_f': 'Temperature_F',
        'humidity': 'Humidity',
        'relative humidity': 'Humidity',
        'dendrometer': 'Dendrometer (microns)',
        'dendrometer (microns)': 'Dendrometer (microns)',
        'dew point': 'Dew Point'
    }
    df_processed.rename(columns=lambda c: rename_map.get(str(c).lower().strip(), c), inplace=True)

    # --- 2. Standardize Timestamp Column (The Fix) ---
    if COL_TIMESTAMP in df_processed.columns:
        # This robustly handles mixed timezone-aware and naive data.
        # It converts everything to UTC, then removes the timezone info,
        # leaving a consistent, naive timestamp for easy comparison.
        df_processed[COL_TIMESTAMP] = pd.to_datetime(df_processed[COL_TIMESTAMP], errors='coerce', utc=True).dt.tz_localize(None)
        df_processed.dropna(subset=[COL_TIMESTAMP], inplace=True)
    else:
        st.error("A valid timestamp column could not be found.")
        return pd.DataFrame()

    # --- 3. Standardize Other Numeric Columns ---
    if 'Temperature_F' in df_processed.columns:
        df_processed['Temperature_C'] = pd.to_numeric(df_processed['Temperature_F'], errors='coerce').apply(lambda f: (f - 32) * 5.0 / 9.0)

    numeric_cols = ['Temperature_C', 'Humidity', 'Dendrometer (microns)', 'Dew Point', 'Girth_cm', 'Growth_cm']
    for col in numeric_cols:
         if col in df_processed.columns:
            df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')

    return df_processed