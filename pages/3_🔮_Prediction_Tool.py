import streamlit as st
import pandas as pd
import joblib
import os

# --- Import LCRA Helper ---
try:
    from helpers.lcra_helpers import fetch_lcra_data
except ImportError:
    fetch_lcra_data = None

# --- Configuration ---
MODELS_DIR = 'models'

# --- Helper function to load the saved model and other artifacts ---
@st.cache_resource
def load_model_artifacts():
    """Loads the saved model and the list of columns it was trained on."""
    try:
        model_path = os.path.join(MODELS_DIR, 'tree_growth_model.pkl')
        model = joblib.load(model_path)
        
        columns_path = os.path.join(MODELS_DIR, 'model_columns.pkl')
        model_columns = joblib.load(columns_path)
        
        return model, model_columns
    except FileNotFoundError:
        return None, None

# --- Main Page Logic ---
st.header("🔮 AI Prediction Tool")
st.info("""
    **How to use this tool:** This AI model has learned the patterns between environmental conditions and tree growth from your historical data. 
    
    Use the sliders below or the preset buttons to simulate conditions and predict tree growth (Dendrometer reading).
""")

# --- 1. Load the Model ---
model, model_columns = load_model_artifacts()

if model is None or model_columns is None:
    st.error("Model not found. Please train the model first by running the `trainers/train_model.py` script.")
    st.stop()

# --- 2. Get User Input with UI Widgets ---
plant_names = sorted([col.replace('Plant_', '') for col in model_columns if col.startswith('Plant_')])

if not plant_names:
    st.warning("No plant names were found in the trained model. The model may be invalid.")
    st.stop()

# --- PRESET SCENARIOS ---
st.subheader("1. Select a Scenario (Optional)")
st.markdown("Quickly set the sliders to specific conditions:")

col_live, col_best, col_worst = st.columns(3)

with col_live:
    st.markdown("**Real-Time Analysis**")
    if st.button("📍 Use Live Austin Weather", use_container_width=True, help="Fetches current Temperature, Humidity, and Rain from LCRA sensors."):
        if fetch_lcra_data:
            with st.spinner("Fetching LCRA data..."):
                lcra_data = fetch_lcra_data()
                if not lcra_data.empty:
                    # Update session state with live values
                    st.session_state['temp_slider'] = float(lcra_data['Temperature_C'].iloc[0])
                    st.session_state['humidity_slider'] = float(lcra_data['Humidity'].iloc[0])
                    
                    if 'Dew Point' in lcra_data.columns and not pd.isna(lcra_data['Dew Point'].iloc[0]):
                         st.session_state['dew_slider'] = float(lcra_data['Dew Point'].iloc[0])
                    else:
                         t = st.session_state['temp_slider']
                         rh = st.session_state['humidity_slider']
                         st.session_state['dew_slider'] = t - ((100 - rh)/5)
                    
                    st.success("Loaded live weather!")
                    st.rerun()
                else:
                    st.error("Could not fetch live weather.")
        else:
            st.error("LCRA helper not found.")

with col_best:
    st.markdown("**Hypothetical Ideal**")
    if st.button("🌟 Best Conditions", use_container_width=True, help="Sets conditions known to promote growth (Moderate Temp, High Humidity)."):
        st.session_state['temp_slider'] = 24.0
        st.session_state['humidity_slider'] = 65.0
        st.session_state['dew_slider'] = 17.0
        st.rerun()

with col_worst:
    st.markdown("**Hypothetical Stress**")
    if st.button("🔥 Worst Conditions", use_container_width=True, help="Sets conditions known to cause stress (High Heat, Low Humidity)."):
        st.session_state['temp_slider'] = 38.0
        st.session_state['humidity_slider'] = 20.0
        st.session_state['dew_slider'] = 5.0
        st.rerun()

st.divider()

# --- SLIDERS ---
st.subheader("2. Fine-Tune Conditions")
col1, col2 = st.columns(2)

with col1:
    temp = st.slider(
        "Temperature (°C)", 
        min_value=-10.0, max_value=45.0, 
        value=st.session_state.get('temp_slider', 25.0), 
        step=0.5,
        key='temp_slider'
    )
    
    if any('Humidity' in col for col in model_columns):
        humidity = st.slider(
            "Humidity (%)", 
            min_value=0.0, max_value=100.0, 
            value=st.session_state.get('humidity_slider', 50.0), 
            step=1.0,
            key='humidity_slider'
        )
    else:
        humidity = None

with col2:
    if any('Dew Point' in col for col in model_columns):
        dew_point = st.slider(
            "Dew Point (°C)", 
            min_value=-10.0, max_value=30.0, 
            value=st.session_state.get('dew_slider', 15.0), 
            step=0.5,
            key='dew_slider'
        )
    else:
        dew_point = None
        
    plant_name = st.selectbox("Select Plant Name", options=plant_names)

# --- 3. Make Prediction ---
st.divider()
st.subheader("3. Generate Prediction")

# Create a dictionary from the user's input
input_data = {
    'Temperature_C': [temp],
    'Plant Name': [plant_name]
}
if humidity is not None:
    input_data['Humidity'] = [humidity]
if dew_point is not None:
    input_data['Dew Point'] = [dew_point]
    
input_df = pd.DataFrame(input_data)
input_df_encoded = pd.get_dummies(input_df, columns=['Plant Name'], prefix='Plant')

# Reindex the input dataframe to match the training columns exactly.
input_df_processed = input_df_encoded.reindex(columns=model_columns, fill_value=0)

if st.button("Run Prediction Model", type="primary", use_container_width=True):
    prediction = model.predict(input_df_processed)
    predicted_value = prediction[0]

    st.metric(
        label=f"Predicted Dendrometer Reading for {plant_name}", 
        value=f"{predicted_value:.2f} microns"
    )

    # if predicted_value > 12000:
    #     st.success("This prediction indicates healthy hydration/growth.")
    # elif predicted_value < 500:
    #     st.warning("This prediction suggests potential water stress.")

# --- DISPLAY MODEL TRAINING STATS (Small & Unbolded) ---
st.divider()
with st.expander("ℹ️ Model Details & Performance", expanded=False):
    summary_path = os.path.join(MODELS_DIR, 'model_performance.txt')
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            stats = f.read()
        # Using caption for small text
        st.caption("Training Statistics:")
        st.text(stats)
    else:
        st.caption("No training summary found.")