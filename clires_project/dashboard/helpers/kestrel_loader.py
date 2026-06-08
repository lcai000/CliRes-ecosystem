import pandas as pd
from dashboard.helpers.config import COL_PLANT_NAME, COL_TIMESTAMP
from dashboard.helpers.cache_utils import DataResult


def load_uploaded_data(uploaded_files):
    """Parses dirty Kestrel CSVs and returns a standardized DataFrame."""
    dataframes = {}
    errors = []
    warnings = []

    for uploaded_file in uploaded_files:
        try:
            uploaded_file.seek(0)
            device_name_line = pd.read_csv(uploaded_file, header=None, nrows=1).iloc[0, 1]
            uploaded_file.seek(0)

            df = pd.read_csv(uploaded_file, skiprows=7, header=None)
            df = df.iloc[:, :5]
            df.columns = ['Date_str', 'Temperature_F', 'Humidity', 'Heat Index', 'Dew Point']

            df[COL_PLANT_NAME] = device_name_line
            df[COL_TIMESTAMP] = pd.to_datetime(df['Date_str'], format='%m/%d/%y %H:%M')
            df['Temperature_C'] = pd.to_numeric(df['Temperature_F'], errors='coerce').apply(
                lambda f: (f - 32) * 5.0 / 9.0
            )
            df['Humidity'] = pd.to_numeric(df['Humidity'], errors='coerce')
            df['Dew Point'] = pd.to_numeric(df['Dew Point'], errors='coerce')

            final_cols = [COL_TIMESTAMP, COL_PLANT_NAME, 'Temperature_C', 'Humidity', 'Dew Point']
            df_final = df[[col for col in final_cols if col in df.columns]].copy()
            df_final.dropna(inplace=True)

            if not df_final.empty:
                dataframes[device_name_line] = df_final

        except Exception as e:
            errors.append(f"Failed to process Kestrel file '{getattr(uploaded_file, 'name', 'unknown')}': {e}")

    return DataResult(data=dataframes, errors=errors, warnings=warnings)
