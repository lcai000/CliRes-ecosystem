import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq

st.set_page_config(page_title="Fourier Concept Demo", layout="wide")

st.header("📚 Educational Demo: How Fourier Works")
st.markdown("""
This page uses **synthetic data** (fake/simulated data) to demonstrate exactly what the Fourier Transform does mathematically.
It shows how the algorithm takes a "messy" sensor reading and finds the hidden "clean" biological wave inside it.
""")

# 1. Create Synthetic Data (7 Days of Tree Growth)
# We simulate 7 days (168 hours) with 2 data points per hour
hours = np.linspace(0, 168, 168*2) 

# The "Signal": A perfect 24-hour sine wave (This represents the Tree's Biological Rhythm)
signal = 10 * np.sin(2 * np.pi * hours / 24) 

# The "Noise": Random jitter (This represents Wind, Electronics, or Vibration)
noise = 3 * np.random.normal(0, 1, len(hours))

# The "Observed Data": Signal + Noise (This is what the sensor actually records)
data = signal + noise

# 2. Perform Fourier Transform
N = len(data)
T = 0.5 # Sample spacing (30 mins)
yf = fft(data)
xf = fftfreq(N, T)[:N//2]
# ensure yf is an ndarray (avoid potential tuple/dispatchable typing issues)
yf = np.asarray(yf)
# compute amplitude with clear grouping to satisfy type-checkers
amplitude = (2.0 / N) * np.abs(yf[:N//2])

# Handle division by zero for period calculation
with np.errstate(divide='ignore'):
    periods = 1 / xf

# 3. Create Plots to explain the concept
fig, axs = plt.subplots(3, 1, figsize=(10, 12))

# Plot A: The Raw Data (What the user sees)
axs[0].plot(hours, data, color='green', alpha=0.8)
axs[0].set_title("1. The Input: What the Sensor Sees (Raw Data)", fontsize=14, fontweight='bold')
axs[0].set_ylabel("Microns")
axs[0].set_xlabel("Time (Hours)")
axs[0].grid(True, alpha=0.3)

# Plot B: The "Hidden" Cycle (What Fourier finds)
axs[1].plot(hours, signal, color='blue', linewidth=2, label="Biological Cycle (24h)")
axs[1].plot(hours, noise, color='red', alpha=0.3, label="Random Noise")
axs[1].set_title("2. The Reality: Signal vs. Noise Deconstructed", fontsize=14, fontweight='bold')
axs[1].set_ylabel("Microns")
axs[1].legend(loc='upper right')
axs[1].grid(True, alpha=0.3)

# Plot C: The Fourier Spectrum (The Output)
# We filter to show only relevant cycles (6h to 100h)
mask = (periods >= 6) & (periods <= 100)
axs[2].plot(periods[mask], amplitude[mask], color='purple', linewidth=3)
axs[2].set_title("3. The Result: Fourier Spectrum (Frequency Analysis)", fontsize=14, fontweight='bold')
axs[2].set_xlabel("Cycle Length (Hours)")
axs[2].set_ylabel("Strength (Amplitude)")
axs[2].axvline(x=24, color='green', linestyle='--', linewidth=2, label="24h Spike (Healthy)")
axs[2].text(26, 8, "← The 'Heartbeat'", color='green', fontsize=12)
axs[2].grid(True, alpha=0.3)
axs[2].legend()

plt.tight_layout()

# Display in Streamlit
st.pyplot(fig)

st.info("""
**Conclusion:** Even though the top graph (Raw Data) looks messy and jagged, the Fourier Transform (Bottom Graph) ignores the noise and clearly identifies a **single, strong spike at 24 hours**. 
This is why we can use it to detect if a tree is alive even when the sensor data looks noisy.
""")