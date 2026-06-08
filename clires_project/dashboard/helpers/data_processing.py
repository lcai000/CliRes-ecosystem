import pandas as pd
import numpy as np
from dashboard.helpers.config import COL_PLANT_NAME, TIME_GRANULARITY_MAP, COL_TIMESTAMP
from dashboard.helpers.cache_utils import DataResult


def filter_dataframe(df, start_date=None, end_date=None, selected_plants=None, timestamp_col=None):
    filtered_df = df.copy()
    if timestamp_col and timestamp_col in filtered_df.columns:
        if start_date and end_date:
            filtered_df[timestamp_col] = pd.to_datetime(filtered_df[timestamp_col], errors='coerce')
            filtered_df.dropna(subset=[timestamp_col], inplace=True)
            filtered_df = filtered_df[
                (filtered_df[timestamp_col].dt.date >= start_date) &
                (filtered_df[timestamp_col].dt.date <= end_date)
            ]
    if selected_plants:
        filtered_df = filtered_df[filtered_df[COL_PLANT_NAME].isin(selected_plants)]
    return filtered_df


def aggregate_dataframe(df, aggregation_level='5-minute (Raw)', aggregation_method='Mean (Average)',
                        plot_overall_average=False):
    if aggregation_level in ['5-minute (Raw)', 'Raw']:
        return DataResult(data=df)

    timestamp_col = COL_TIMESTAMP
    if timestamp_col not in df.columns:
        return DataResult(data=pd.DataFrame(), errors=[f"Cannot aggregate by time without a valid timestamp column."])

    agg_method_map = {
        "Mean (Average)": "mean", "Minimum": "min", "Maximum": "max",
        "Mean with Min/Max Range": ["mean", "min", "max"]
    }
    agg_func = agg_method_map.get(aggregation_method, 'mean')
    resample_freq = TIME_GRANULARITY_MAP.get(aggregation_level)
    cols_to_agg = [c for c in df.select_dtypes(include=np.number).columns]

    should_group_by_plant = COL_PLANT_NAME in df.columns and not plot_overall_average
    grouping_cols = [pd.Grouper(key=timestamp_col, freq=resample_freq)]
    if should_group_by_plant:
        grouping_cols.insert(0, COL_PLANT_NAME)

    try:
        aggregated_df = df.groupby(grouping_cols)[cols_to_agg].agg(agg_func)
    except Exception as e:
        return DataResult(data=pd.DataFrame(), errors=[f"Failed to aggregate data. Error: {e}"])

    if isinstance(aggregated_df.columns, pd.MultiIndex):
        aggregated_df.columns = ['_'.join(col).strip() for col in aggregated_df.columns.values]

    aggregated_df.reset_index(inplace=True)
    value_cols = [c for c in aggregated_df.columns if c not in [COL_PLANT_NAME, timestamp_col]]
    aggregated_df.dropna(how='all', subset=value_cols, inplace=True)

    return DataResult(data=aggregated_df)


def standardize_dataframe(df):
    df_processed = df.copy()
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

    if COL_TIMESTAMP in df_processed.columns:
        df_processed[COL_TIMESTAMP] = pd.to_datetime(
            df_processed[COL_TIMESTAMP], errors='coerce', utc=True
        ).dt.tz_localize(None)
        df_processed.dropna(subset=[COL_TIMESTAMP], inplace=True)
    else:
        return DataResult(data=pd.DataFrame(), errors=["A valid timestamp column could not be found."])

    if 'Temperature_F' in df_processed.columns:
        df_processed['Temperature_C'] = pd.to_numeric(
            df_processed['Temperature_F'], errors='coerce'
        ).apply(lambda f: (f - 32) * 5.0 / 9.0)

    numeric_cols = ['Temperature_C', 'Humidity', 'Dendrometer (microns)', 'Dew Point', 'Girth_cm', 'Growth_cm']
    for col in numeric_cols:
        if col in df_processed.columns:
            df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')

    return DataResult(data=df_processed)
