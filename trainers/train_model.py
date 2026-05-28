import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, GridSearchCV, TimeSeriesSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import xgboost as xgb
import joblib
import os
from datetime import datetime, timedelta, date
import sys
import toml
import time

# --- Add the parent directory to the Python path ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Import your own helper files and constants ---
from helpers.api_helpers import get_access_token, fetch_plant_names, fetch_all_data
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME, TARGET_VARIABLE

# --- Configuration ---
MODELS_DIR = os.path.join(project_root, 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

# Enhanced Feature Set
# Added Light, Rainfall, and Dew Point which are critical for plant physiology
BASE_FEATURES = ['Temperature_C', 'Humidity', 'Rainfall_mm', 'Light (W/m^2)', 'Dew Point']
MIN_DATA_POINTS_PER_PLANT = 50 
RESAMPLE_FREQUENCY = '1h' 

# --- Manual Overrides ---
MANUAL_PLANT_LIST = [
    "Live Oak 1",
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

# Manual install dates (Keep your existing dictionary here)
MANUAL_INSTALL_DATES = {
    "Live Oak 1": date(2024, 11, 24),
    "HEB-10 Anacacho S": date(2024, 12, 10),
    "Ashe juniper - uneffected tree 2": date(2025, 7, 5),
    "Ashe juniper Inf Tree 3": date(2025, 7, 2),
    "Ashe juniper Unf tree 1": date(2025, 6, 12),
    "HEB-7-Anacacho N": date(2025, 3, 5),
    "HEB-1-Lacey Oak": date(2024, 12, 10),
    "HEB-2-Montezuma Cypress": date(2024, 12, 10),
    "HEB-3-Mexican Sycamore": date(2024, 12, 10),
    "HEB-4-Little Gem Magnolia": date(2025, 3, 5),
    "HEB-6-Desert Willow N": date(2024, 12, 10),
    "HEB-9-Desert Willow S": date(2024, 12, 10),
    "JBWS Anacua ": date(2024, 12, 10),
    "P2-T3-Biochar Elm": date(2024, 12, 9),
    "P2-T4-Control Elm": date(2024, 12, 9),
    "P2-T5-Chinquapin": date(2024, 12, 9),
    "P3-T2-Redbud": date(2024, 12, 10),
    "P3-T3-Biochar Elm": date(2024, 12, 10),
    "P3-T4-Control Elm": date(2025, 3, 5),
    "P3-T5-Chinquapin": date(2024, 12, 10),
    "P4-T3-Biochar Elm": date(2024, 12, 9),
    "P4-T4-Control Elm": date(2024, 12, 9),
    "P4-T5-Chinquapin": date(2024, 12, 9),
    "P5-T2-Redbud": date(2024, 12, 9),
    "P5-T3-Biochar Elm": date(2024, 12, 9),
    "P5-T4-Control Elm": date(2025, 3, 5),
    "P5-T5-Chinquapin": date(2024, 12, 9)
}

def add_time_features(df):
    """Adds cyclical time features which are crucial for tree data."""
    df = df.copy()
    df['Hour'] = df[COL_TIMESTAMP].dt.hour
    df['Month'] = df[COL_TIMESTAMP].dt.month
    df['Hour_Sin'] = np.sin(2 * np.pi * df['Hour'] / 24)
    df['Hour_Cos'] = np.cos(2 * np.pi * df['Hour'] / 24)
    # Day of year captures seasonal progression better than just Month
    df['DayOfYear'] = df[COL_TIMESTAMP].dt.dayofyear
    return df

def add_extreme_weather_flags(df):
    """Adds binary flags for extreme weather conditions that cause non-linear tree responses."""
    df = df.copy()
    # Freezing: Water expansion/phase change < 0°C (32°F)
    df['Is_Freezing'] = (df['Temperature_C'] < 0).astype(int)
    # Extreme Heat: Stomatal closure > 35°C (95°F)
    df['Is_Heat_Stress'] = (df['Temperature_C'] > 35).astype(int)
    return df

def add_lag_features(df, group_col, features, lags=[1, 2, 3, 6]):
    """Adds previous time step values as features."""
    df = df.copy()
    df = df.sort_values(by=[group_col, COL_TIMESTAMP])
    for feature in features:
        if feature in df.columns:
            for lag in lags:
                df[f'{feature}_Lag{lag}'] = df.groupby(group_col)[feature].shift(lag)
    return df

def add_rolling_features(df, group_col, features, windows=[6, 24]):
    """Adds rolling mean statistics (e.g., average temp of last 24h)."""
    df = df.copy()
    df = df.sort_values(by=[group_col, COL_TIMESTAMP])
    for feature in features:
        if feature in df.columns:
            for window in windows:
                # Calculate rolling mean
                df[f'{feature}_RollMean{window}'] = df.groupby(group_col)[feature].transform(
                    lambda x: x.rolling(window=window, min_periods=1).mean()
                )
    return df

def print_regression_report(y_true, y_pred, model_name):
    """Prints a detailed performance report for a regression model."""
    mse = mean_squared_error(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    
    print(f"\n--- {model_name} Performance Report ---")
    print(f"R² Score (Accuracy): {r2:.4f}")
    print(f"Mean Absolute Error (MAE): {mae:.4f} microns")
    print(f"Mean Squared Error (MSE): {mse:.4f}")
    print("-" * 40)

def train_with_api_data():
    print("--- Starting Advanced Model Training (Enhanced) ---")
    
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
    if MANUAL_PLANT_LIST:
        devices_to_process = [d for d in all_available_devices if d.get('name') in MANUAL_PLANT_LIST]
    else:
        devices_to_process = all_available_devices

    # --- 3. Data Fetching Loop ---
    all_data_chunks = []
    chunk_size_days = 30
    
    print(f"\nFetching data for {len(devices_to_process)} plants...")

    for device in devices_to_process:
        plant_name = device.get('name')
        install_date = None

        if plant_name in MANUAL_INSTALL_DATES:
            install_date = MANUAL_INSTALL_DATES[plant_name]
        else:
            install_date_str = device.get('install_date')
            if not install_date_str:
                continue
            try:
                install_date = pd.to_datetime(install_date_str).date()
            except Exception:
                continue
        
        current_chunk_start = install_date
        training_end_date = date.today()
        
        while current_chunk_start < training_end_date:
            current_chunk_end = current_chunk_start + timedelta(days=chunk_size_days)
            if current_chunk_end > training_end_date:
                current_chunk_end = training_end_date

            print(f"  - Fetching {plant_name}: {current_chunk_start} to {current_chunk_end}")
            try:
                data_chunk = fetch_all_data(tuple([device]), current_chunk_start, current_chunk_end, access_token, st=None)
                if not data_chunk.empty:
                    all_data_chunks.append(data_chunk)
                time.sleep(0.5) 
            except Exception as e:
                print(f"    - Warning: Error fetching chunk: {e}")
            
            current_chunk_start += timedelta(days=chunk_size_days)

    if not all_data_chunks:
        print("\nFATAL ERROR: No data could be fetched.")
        return
        
    combined_df = pd.concat(all_data_chunks, ignore_index=True)
    print(f"\nTotal raw rows received: {len(combined_df)}")

    # --- 4. Cleaning and Resampling ---
    if COL_TIMESTAMP in combined_df.columns:
        combined_df[COL_TIMESTAMP] = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce', utc=True).dt.tz_localize(None)
    
    # Ensure all base features exist
    for col in BASE_FEATURES + [TARGET_VARIABLE]:
        if col not in combined_df.columns:
            combined_df[col] = np.nan
        combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')

    # FIX: Calculate Dew Point if missing (Crucial for avoiding data loss)
    if combined_df['Dew Point'].isna().all() and 'Temperature_C' in combined_df.columns and 'Humidity' in combined_df.columns:
        print("  - Note: 'Dew Point' missing. Calculating from Temp and Humidity.")
        combined_df['Dew Point'] = combined_df['Temperature_C'] - ((100 - combined_df['Humidity']) / 5.0)

    # Initial Drop only for Target (we can fill others)
    combined_df.dropna(subset=[TARGET_VARIABLE], inplace=True)

    print(f"\n--- Resampling Data to {RESAMPLE_FREQUENCY} Intervals ---")
    
    # Select numeric columns explicitly to avoid FutureWarning and string errors
    numeric_cols = combined_df.select_dtypes(include=np.number).columns.tolist()
    
    # Perform Resampling
    combined_df = combined_df.set_index(COL_TIMESTAMP).groupby(COL_PLANT_NAME)[numeric_cols].resample(RESAMPLE_FREQUENCY).mean().reset_index()
    
    # Fill gaps in continuous data (Zero fill is reasonable for these)
    combined_df['Rainfall_mm'] = combined_df['Rainfall_mm'].fillna(0)
    combined_df['Light (W/m^2)'] = combined_df['Light (W/m^2)'].fillna(0)
    
    # Drop remaining NaNs (e.g. missing temp/humidity that couldn't be resampled)
    combined_df.dropna(subset=BASE_FEATURES, inplace=True)
    
    print(f"Total rows after resampling: {len(combined_df)}")
    
    if combined_df.empty:
        print("CRITICAL ERROR: Data empty after cleaning. Check if Temperature/Humidity columns are populated.")
        return

    # --- 5. Advanced Feature Engineering ---
    print("\n--- Generating Advanced Features ---")
    combined_df = add_time_features(combined_df)
    combined_df = add_extreme_weather_flags(combined_df)
    
    # Add Lags (Previous hours)
    combined_df = add_lag_features(combined_df, COL_PLANT_NAME, BASE_FEATURES, lags=[1, 2, 3, 6])
    
    # Add Rolling Means (Trends over 6h and 24h)
    combined_df = add_rolling_features(combined_df, COL_PLANT_NAME, BASE_FEATURES, windows=[6, 24])
    
    combined_df.dropna(inplace=True)
    
    # Construct Feature Column List dynamically
    feature_cols = BASE_FEATURES + ['Hour_Sin', 'Hour_Cos', 'DayOfYear', 'Is_Freezing', 'Is_Heat_Stress']
    
    # Add generated lag columns
    for feat in BASE_FEATURES:
        for i in [1, 2, 3, 6]:
            col_name = f'{feat}_Lag{i}'
            if col_name in combined_df.columns: feature_cols.append(col_name)
    
    # Add generated rolling columns
    for feat in BASE_FEATURES:
        for w in [6, 24]:
            col_name = f'{feat}_RollMean{w}'
            if col_name in combined_df.columns: feature_cols.append(col_name)

    if 'Plant Name' in feature_cols: feature_cols.remove('Plant Name')

    print(f"Training with {len(feature_cols)} features.")

    # --- 6. Final Preparation ---
    X = combined_df[feature_cols + ['Plant Name']]
    y = combined_df[TARGET_VARIABLE]
    
    X = pd.get_dummies(X, columns=['Plant Name'], prefix='Plant')
    model_columns = X.columns.tolist()
    joblib.dump(model_columns, os.path.join(MODELS_DIR, 'model_columns.pkl'))
    
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    models = {}
    model_summaries = []

    # --- Train Models & Print Reports ---
    
    # RandomForest
    print("\nTraining RandomForestRegressor...")
    # Increased estimators for better performance with more features
    rf_model = RandomForestRegressor(n_estimators=300, max_depth=25, min_samples_split=4, random_state=42, n_jobs=-1)
    rf_model.fit(X_train, y_train)
    rf_preds = rf_model.predict(X_val)
    
    # --- PRINT REPORT FOR RANDOM FOREST ---
    print_regression_report(y_val, rf_preds, "Random Forest Regressor")
    
    rf_score = r2_score(y_val, rf_preds)
    models['RandomForest'] = {'model': rf_model, 'score': rf_score}
    model_summaries.append(f"RandomForestRegressor: R2={rf_score:.3f}")

    # XGBoost
    print("\nTraining XGBoost Regressor...")
    xgb_model = xgb.XGBRegressor(n_estimators=600, learning_rate=0.03, max_depth=7, subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, early_stopping_rounds=20)
    xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    xgb_preds = xgb_model.predict(X_val)
    
    # --- PRINT REPORT FOR XGBOOST ---
    print_regression_report(y_val, xgb_preds, "XGBoost Regressor")
    
    xgb_score = r2_score(y_val, xgb_preds)
    models['XGBoost'] = {'model': xgb_model, 'score': xgb_score}
    model_summaries.append(f"XGBoostRegressor: R2={xgb_score:.3f}")

    # --- Compare and Save ---
    best_model_name = max(models, key=lambda name: models[name]['score'])
    best_model = models[best_model_name]['model']
    best_score = models[best_model_name]['score']
    
    print(f"\n>>> BEST MODEL: {best_model_name} (Score: {best_score:.3f})")
    
    model_path = os.path.join(MODELS_DIR, 'tree_growth_model.pkl')
    joblib.dump(best_model, model_path)
    
    # Save summary for Chatbot
    summary_path = os.path.join(MODELS_DIR, 'model_performance.txt')
    with open(summary_path, 'w') as f:
        f.write("Model Training Performance Summary\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 30 + "\n")
        for summary in model_summaries:
            f.write(summary + "\n")
        f.write("-" * 30 + "\n")
        f.write(f"Selected Best Model: {best_model_name} ({best_score:.3f})\n")
        
    print("--- Training Complete ---")

if __name__ == '__main__':
    train_with_api_data()