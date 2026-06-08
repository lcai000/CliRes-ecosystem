import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq
from django.shortcuts import render
from dashboard.views.charting_utils import fig_to_b64


def fourier_concept_view(request):
    """Fourier Concept educational demo page."""
    if not request.session.session_key:
        request.session.save()

    # Generate synthetic data and the demo chart
    hours = np.linspace(0, 168, 168 * 2)
    signal = 10 * np.sin(2 * np.pi * hours / 24)
    noise = 3 * np.random.default_rng(42).normal(0, 1, len(hours))
    data = signal + noise

    N = len(data)
    T = 0.5
    yf = fft(data)
    xf = fftfreq(N, T)[:N // 2]
    yf = np.asarray(yf)
    amplitude = (2.0 / N) * np.abs(yf[:N // 2])

    with np.errstate(divide='ignore'):
        periods = 1 / xf

    fig, axs = plt.subplots(3, 1, figsize=(10, 12))

    axs[0].plot(hours, data, color='green', alpha=0.8)
    axs[0].set_title("1. The Input: What the Sensor Sees (Raw Data)", fontsize=14, fontweight='bold')
    axs[0].set_ylabel("Microns")
    axs[0].set_xlabel("Time (Hours)")
    axs[0].grid(True, alpha=0.3)

    axs[1].plot(hours, signal, color='blue', linewidth=2, label="Biological Cycle (24h)")
    axs[1].plot(hours, noise, color='red', alpha=0.3, label="Random Noise")
    axs[1].set_title("2. The Reality: Signal vs. Noise Deconstructed", fontsize=14, fontweight='bold')
    axs[1].set_ylabel("Microns")
    axs[1].legend(loc='upper right')
    axs[1].grid(True, alpha=0.3)

    mask = (periods >= 6) & (periods <= 100)
    axs[2].plot(periods[mask], amplitude[mask], color='purple', linewidth=3)
    axs[2].set_title("3. The Result: Fourier Spectrum (Frequency Analysis)", fontsize=14, fontweight='bold')
    axs[2].set_xlabel("Cycle Length (Hours)")
    axs[2].set_ylabel("Strength (Amplitude)")
    axs[2].axvline(x=24, color='green', linestyle='--', linewidth=2, label="24h Spike (Healthy)")
    axs[2].text(26, 8, "<- The 'Heartbeat'", color='green', fontsize=12)
    axs[2].grid(True, alpha=0.3)
    axs[2].legend()

    plt.tight_layout()
    chart_img = fig_to_b64(fig)

    return render(request, 'dashboard/fourier_concept.html', {
        'chart_img': chart_img,
    })
