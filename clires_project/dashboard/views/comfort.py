import pandas as pd
import numpy as np
from django.shortcuts import render
from django.contrib import messages

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.data_processing import filter_dataframe, aggregate_dataframe
from dashboard.views.home import get_session_df
from dashboard.views.charting_utils import fig_to_b64


def comfort_view(request):
    """Tree Comfort Index page."""
    if not request.session.session_key:
        request.session.save()

    kestrel_df = get_session_df(request, 'kestrel_df')
    if kestrel_df is None or kestrel_df.empty:
        messages.info(request, "Please upload a Kestrel data file on the Home page sidebar to use this tool.")
        return render(request, 'dashboard/comfort.html', {'has_data': False})

    plant_names = sorted(kestrel_df[COL_PLANT_NAME].unique().tolist()) if COL_PLANT_NAME in kestrel_df.columns else []
    return render(request, 'dashboard/comfort.html', {
        'has_data': True,
        'plant_names': plant_names,
    })
