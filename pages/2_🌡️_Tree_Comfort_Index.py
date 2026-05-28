# File: pages/2_🌡️_Tree_Comfort_Index.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Import from your own project files
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from helpers.data_processing import filter_dataframe,aggregate_dataframe
# --- HELPER FUNCTION 1: DATA CALCULATION ---
def calculate_comfort_index(df):
    """Takes a DataFrame and adds VPD and Tree Comfort Index columns."""
    df_processed = df.copy()
    temp_col, rh_col, dew_point_col = 'Temperature_C', 'Humidity', 'Dew Point'
    required_cols = [temp_col, rh_col, dew_point_col]

    for col in required_cols:
        if col not in df_processed.columns:
            st.error(f"Error: A required column named '{col}' was not found in the uploaded Kestrel data.")
            st.stop()
        df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
    df_processed.dropna(subset=required_cols, inplace=True)
    
    def compute_vpd(temp_c, rh):
        es = 0.6108 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
        ea = rh / 100.0 * es
        return es - ea
    df_processed['VPD (kPa)'] = compute_vpd(df_processed[temp_col], df_processed[rh_col])

    def vectorized_score(series, ideal_min, ideal_max, soft_range=5):
        conditions = [(series >= ideal_min) & (series <= ideal_max), (series >= ideal_min - soft_range) & (series <= ideal_max + soft_range)]
        choices = [1, 0.5]
        return np.select(conditions, choices, default=0)

    df_processed['Temp Score'] = vectorized_score(df_processed[temp_col], 15, 25)
    df_processed['RH Score'] = vectorized_score(df_processed[rh_col], 40, 60)
    df_processed['Dew Score'] = vectorized_score(df_processed[dew_point_col], 10, 17)
    df_processed['VPD Score'] = vectorized_score(df_processed['VPD (kPa)'], 0.4, 1.2)
    df_processed['Tree Comfort Index'] = df_processed[['Temp Score', 'RH Score', 'Dew Score', 'VPD Score']].mean(axis=1)
    
    return df_processed

# --- HELPER FUNCTION 2: PLOTTING ---
def plot_comfort_index(df, timestamp_col, plant_name_col, use_facets=False):
    """Creates a detailed line plot of the comfort index over time."""
    if use_facets:
        g = sns.relplot(data=df, x=timestamp_col, y='Tree Comfort Index', col=plant_name_col, kind='line', height=4, aspect=1.5, col_wrap=3, facet_kws={'sharey': True, 'sharex': True})
        g.set_titles(col_template="{col_name}")
        g.fig.suptitle("Tree Comfort Index Over Time", y=1.03, fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        return g.fig
    else:
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.lineplot(data=df, x=timestamp_col, y='Tree Comfort Index', hue=plant_name_col, ax=ax)
        ax.set_title("Tree Comfort Index Over Time", fontsize=16)
        ax.set_ylabel("Comfort Index (1.0 is ideal)")
        ax.set_xlabel("Date")
        ax.grid(True)
        ax.legend(title="Plant")
        fig.autofmt_xdate()
        return fig

# --- MAIN PAGE LOGIC ---
def TCI_Main():
    st.header("🌡️ Tree Comfort Index")
    st.write("This tool uses your uploaded Kestrel files to calculate a comfort index.")

    # 1. Check for the specific kestrel data in session state
    if 'kestrel_df' not in st.session_state or st.session_state.kestrel_df.empty:
        st.info("Please upload a Kestrel data file on the Home page sidebar to use this tool.")
        st.stop()

    # 2. Get the data and apply the global date filter
    kestrel_data = st.session_state['kestrel_df']
    configs = {}
    if 'start_date' in st.session_state:
        configs['start_date'] = st.session_state.start_date
        configs['end_date'] = st.session_state.end_date

    filtered_df = filter_dataframe(kestrel_data, configs, COL_TIMESTAMP)

    if filtered_df.empty:
        st.warning("No Kestrel data found for the selected date range.")
        st.stop()

    # 3. Calculate the index and display the results
    try:
        st.write("Calculating Comfort Index...")
        indexed_df = calculate_comfort_index(filtered_df)
        st.success("Calculation complete!")

        # --- NEW: Add UI for selecting aggregation level ---
        st.subheader("Analysis Options")
        agg_level = st.selectbox(
            "Select Time Granularity:",
            ["Raw", "Daily", "Weekly", "Monthly"],
            index=1 # Default to Daily for a cleaner initial view
        )

        # --- MODIFIED: Aggregate the data before plotting ---
        if agg_level != "Raw":
            st.write(f"Aggregating comfort index to {agg_level.lower()} level...")
            agg_configs = {'aggregation_level': agg_level, 'aggregation_method': 'Mean (Average)'}
            data_to_plot = aggregate_dataframe(indexed_df, agg_configs, COL_TIMESTAMP)
        else:
            data_to_plot = indexed_df # Use the raw data if selected

        if data_to_plot.empty:
            st.warning("No data remains after aggregation.")
            st.stop()

        # --- Display the plot ---
        st.subheader("Comfort Index Over Time")
        st.write("A score of 1.0 is ideal, while a score closer to 0 indicates more stressful conditions.")
        
        use_facets = st.checkbox("Show each plant in a separate graph")
        
        fig = plot_comfort_index(data_to_plot, COL_TIMESTAMP, COL_PLANT_NAME, use_facets)
        st.pyplot(fig)

        st.subheader("Detailed Data and Scores")
        display_cols = [COL_TIMESTAMP, COL_PLANT_NAME, 'Temperature_C', 'Humidity', 'VPD (kPa)', 'Tree Comfort Index']
        # Show the aggregated data table if not raw
        st.dataframe(data_to_plot[[col for col in display_cols if col in data_to_plot.columns]])

    except Exception as e:
        st.error("Failed to calculate or plot the Comfort Index.")
        st.exception(e)

TCI_Main()