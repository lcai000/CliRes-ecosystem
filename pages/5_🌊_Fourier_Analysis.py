import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq

# --- Import from your own project files ---
from helpers.config import COL_TIMESTAMP, COL_PLANT_NAME

st.set_page_config(layout="wide", page_title="Fourier Cycle Analysis")

st.header("🌊 Fourier Analysis (Cycle Detector)")
st.markdown("""
**What is this?**
This tool uses **Fast Fourier Transform (FFT)** to convert your tree's growth history into a "Frequency Spectrum." 
* **Frequency:** Finds repeating patterns (like the 24-hour day/night cycle).
* **Amplitude:** Measures how *strong* that cycle is. This helps distinguish living trees (strong water pumping) from dead wood (weak thermal expansion).
""")

# --- 1. Check for Data ---
if 'combined_df' not in st.session_state or st.session_state['combined_df'].empty:
    st.warning("⚠️ No data found! Please go to the **Home Page** sidebar and click 'Fetch Tree Data' first.")
    st.info("Fourier analysis requires a historical timeline to detect patterns. It cannot run on empty or single-point data.")
    st.stop()

df = st.session_state['combined_df'].copy()

# Ensure timestamp format is correct for analysis
df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP], errors='coerce', utc=True).dt.tz_localize(None)
df.dropna(subset=[COL_TIMESTAMP], inplace=True)

# --- NEW: Apply Global Date Filter ---
if 'start_date' in st.session_state and 'end_date' in st.session_state:
    start_dt = pd.to_datetime(st.session_state.start_date)
    end_dt = pd.to_datetime(st.session_state.end_date) + pd.Timedelta(days=1) # Include the end date
    df = df[(df[COL_TIMESTAMP] >= start_dt) & (df[COL_TIMESTAMP] < end_dt)]
    st.caption(f"📅 Analyzing range: **{st.session_state.start_date}** to **{st.session_state.end_date}**")

if df.empty:
    st.error("No data found for the selected date range.")
    st.stop()

# --- 2. User Selection ---
# Select Plant
available_plants = sorted(df[COL_PLANT_NAME].unique().tolist())
if not available_plants:
    st.error("No plants found in the dataset.")
    st.stop()
    
selected_plant = st.selectbox("Select a Tree to Analyze:", available_plants)

# Filter Data for that Plant
plant_df = df[df[COL_PLANT_NAME] == selected_plant].copy()
plant_df = plant_df.sort_values(COL_TIMESTAMP)

# Select Variable (Dendrometer is best for this)
numeric_cols = plant_df.select_dtypes(include=np.number).columns.tolist()
# Try to default to Dendrometer if available
default_ix = 0
for i, col in enumerate(numeric_cols):
    if "Dendrometer" in col:
        default_ix = i
        break
target_col = st.selectbox("Select Variable:", numeric_cols, index=default_ix)

# --- 3. Prepare Data for FFT (Crucial Step) ---
# FFT requires PERFECTLY evenly spaced data. Real sensor data has gaps.
# We must resample and interpolate to fix the gaps.

st.caption("Processing data... Resampling to 1-hour intervals and interpolating missing values.")

# Resample to 1-hour intervals to smooth out noise
# This creates a fixed grid (10:00, 11:00, 12:00...)
try:
    resampled = plant_df.set_index(COL_TIMESTAMP)[target_col].resample('1h').mean()
except Exception as e:
    st.error(f"Error resampling data: {e}")
    st.stop()

# Fill missing data (Interpolation connects the dots across gaps)
resampled_interpolated = resampled.interpolate(method='linear')

# Remove any remaining NaNs at start/end
resampled_final = resampled_interpolated.dropna()

data_points = len(resampled_final)
if data_points < 24:
    st.error(f"Not enough data points ({data_points}). Need at least 24 hours of continuous data to find a daily cycle.")
    st.stop()

# --- 4. Perform FFT Calculation ---
N = len(resampled_final)
T = 1.0 # Sample spacing (1 hour)

# Compute FFT
yf = fft(resampled_final.values)
xf = fftfreq(N, T)[:N//2] # Frequencies (Cycles per Hour)

# Calculate Amplitude (Strength of the cycle)
amplitude = 2.0/N * np.abs(np.array(yf[0:N//2]))

# Convert Frequency to Period (Hours per Cycle) to make it readable for humans
# Period = 1 / Frequency
with np.errstate(divide='ignore'):
    periods = 1 / xf

# --- 5. Plotting ---
st.divider()
st.subheader("📊 Cycle Spectrum Graph")

# NEW: Dynamic Slider for View Range
total_duration_hours = len(resampled_final)
# Default to 1 week (168h) or less if data is short
default_view = 168 if total_duration_hours >= 168 else total_duration_hours

max_view = st.slider(
    "Maximum Cycle Length to View (Hours)", 
    min_value=24, 
    max_value=total_duration_hours, 
    value=default_view,
    help="Slide to the right to see longer cycles (like weekly or monthly patterns) if you have enough data."
)

fig, ax = plt.subplots(figsize=(10, 6))

# Plot Frequency vs Amplitude
# We restrict the view to useful cycles (e.g., between 6 hours and the user's selected max)
mask = (periods >= 6) & (periods <= max_view)

ax.plot(periods[mask], amplitude[mask], color='purple', linewidth=2)

ax.set_title(f"Cycle Strength for {selected_plant} ({target_col})", fontsize=16)
ax.set_xlabel("Cycle Length (Hours)", fontsize=12)
ax.set_ylabel("Amplitude (microns)", fontsize=12)
ax.grid(True, linestyle='--', alpha=0.7)

# Highlight the 24-hour mark (The Daily Cycle)
ax.axvline(x=24, color='green', linestyle='--', label="24 Hour Cycle (Daily)")
# Highlight 12-hour mark (Twice daily patterns)
ax.axvline(x=12, color='orange', linestyle=':', alpha=0.5, label="12 Hour Cycle")

ax.legend()

st.pyplot(fig,use_container_width=False)

# --- 6. Automated Health Assessment ---
st.divider()
st.subheader("🤖 Automated Health Assessment")

# Determine Signal-to-Noise Ratio (SNR) for the 24-hour cycle
valid_periods = periods[mask]
valid_amplitudes = amplitude[mask]

if len(valid_periods) > 0:
    # Find the index closest to 24 hours
    idx_closest = (np.abs(valid_periods - 24.0)).argmin()
    amp_24h = valid_amplitudes[idx_closest]
    
    # Calculate "Noise" (Average amplitude of everything else)
    avg_noise = np.mean(valid_amplitudes)
    
    # Calculate Ratio
    snr = amp_24h / avg_noise if avg_noise > 0 else 0
    
    # Display Stats
    c1, c2, c3 = st.columns(3)
    c1.metric("24-Hour Cycle Amplitude", f"{amp_24h:.2f} µm")
    c2.metric("Background Noise", f"{avg_noise:.2f} µm")
    c3.metric("Clarity (SNR)", f"{snr:.1f}x")
    
    st.write("---")
    st.markdown("**Diagnosis:**")

    # Interpretation Logic using Amplitude
    if snr >= 3.0:
        # Strong signal detected, now check Amplitude for life
        if amp_24h > 15.0:
            st.success(f"✅ **Healthy Active Tree:** Strong 24h rhythm ({snr:.1f}x noise) with high amplitude ({amp_24h:.1f}µm). The tree is actively pumping water.")
        elif amp_24h > 5.0:
            st.info(f"⚠️ **Dormant or Low Activity:** Clear 24h rhythm detected, but amplitude is moderate ({amp_24h:.1f}µm). Could be winter dormancy or a smaller tree.")
        else:
            st.warning(f"💀 **Possible Passive/Dead Signal:** A 24h rhythm exists, but it is very weak ({amp_24h:.1f}µm). This low-amplitude cycle is often caused by simple thermal expansion (physics) rather than water flow (biology).")
    elif snr >= 2.5:
             st.warning(f"💀 **Stressed/Dead/Sensor Issue: ** The 24-hour cycle is present:({snr:.1f}x noise) but buried in noise. Tree may be stressed.")
    else:
        st.error(f"❌ **No Rhythm Detected:** The 24-hour cycle is lost in the noise ({snr:.1f}x).")
# --- 7. Interpretation Guide ---
with st.expander("📖 Guide: Biology vs. Physics"):
    st.markdown("""
    **Why do dead trees have a 24-hour cycle?**
    Dead wood expands when it gets hot and shrinks when it dries. This creates a small, perfect daily cycle driven by the sun.
    
    **How to tell the difference:**
    * **Living Tree:** Active transpiration pulls water out, shrinking the trunk significantly. Amplitude is usually **> 15 microns**.
    * **Dead Tree:** Passive thermal expansion is subtle. Amplitude is usually **< 5 microns**.
    """)

plt.close(fig)