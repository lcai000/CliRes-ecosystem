# This file holds all the configuration constants for your app.

# --- Data Schema ---
COL_TIMESTAMP = 'Sample Time (UTC)'
COL_PLANT_NAME = 'Plant Name'
COL_YEAR = 'Year'
POTENTIAL_NUMERIC_COLS = [
    'Year', 'Temperature_C', 'Rainfall_mm', 'Girth_cm', 'Growth_cm',
    'serial number', 'Daily Growth', 'Humidity', 'Dendrometer (microns)'
]

# --- Aggregation and Plotting ---
TIME_GRANULARITY_MAP = {"Hourly": "h", "Daily": "D", "Weekly": "W", "Monthly": "ME"}
TRENDLINE_STYLE = {'linestyle': '--', 'color': 'gray', 'alpha': 0.7}

# This defines what we want to predict and the features to use.
TARGET_VARIABLE = 'Dendrometer (microns)'
FEATURES = ['Temperature_C', 'Humidity', 'Plant Name']
