import pandas as pd
import numpy as np
from django.shortcuts import render
from django.contrib import messages
from datetime import timedelta, date

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.views.home import get_session_df
from dashboard.views.charting_utils import fig_to_b64


def _date_defaults():
    today = date.today()
    return {
        'default_start_date': (today - timedelta(days=30)).isoformat(),
        'default_end_date': today.isoformat(),
    }


def fourier_view(request):
    """Fourier Analysis page."""
    if not request.session.session_key:
        request.session.save()

    combined_df = get_session_df(request, 'combined_df')
    if combined_df is None or combined_df.empty:
        messages.info(request, "No data found. Please load data on the Home page first.")
        return render(request, 'dashboard/fourier.html', {'has_data': False, **_date_defaults()})

    plant_names = sorted(combined_df[COL_PLANT_NAME].unique().tolist()) if COL_PLANT_NAME in combined_df.columns else []
    numeric_cols = combined_df.select_dtypes(include=np.number).columns.tolist()

    default_col_idx = 0
    for i, col in enumerate(numeric_cols):
        if "Dendrometer" in col:
            default_col_idx = i
            break

    return render(request, 'dashboard/fourier.html', {
        'has_data': True,
        'plant_names': plant_names,
        'numeric_columns': numeric_cols,
        'default_col_idx': default_col_idx,
        **_date_defaults(),
    })
