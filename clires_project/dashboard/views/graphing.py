import json
import pandas as pd
import numpy as np
from django.shortcuts import render
from django.contrib import messages

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.data_processing import filter_dataframe, aggregate_dataframe, standardize_dataframe
from dashboard.helpers.utils import get_base_col_name
from dashboard.views.home import get_session_df, merge_combine_data
from dashboard.views.charting_utils import create_plot, fig_to_b64


def graphing_view(request):
    """Graphing Tool page."""
    if not request.session.session_key:
        request.session.save()

    combined_df = get_session_df(request, 'combined_df')
    if combined_df is None:
        # Try to rebuild
        combined_df = merge_combine_data(request)

    if combined_df is None or combined_df.empty:
        messages.info(request, "Please load data on the Home page to begin.")
        return render(request, 'dashboard/graphing.html', {
            'has_data': False,
            'data_head': None,
            'columns': [],
            'plant_names': [],
        })

    # Standardize
    result = standardize_dataframe(combined_df)
    if not result.ok:
        messages.error(request, result.errors[0])
        return render(request, 'dashboard/graphing.html', {'has_data': False})
    combined_df = result.data

    plant_names = sorted(combined_df[COL_PLANT_NAME].unique().tolist()) if COL_PLANT_NAME in combined_df.columns else []
    columns = combined_df.columns.tolist()
    numeric_cols = combined_df.select_dtypes(include=np.number).columns.tolist()

    return render(request, 'dashboard/graphing.html', {
        'has_data': True,
        'data_head': combined_df.head(10).to_html(classes='table table-sm table-striped', index=False),
        'columns': columns,
        'numeric_columns': numeric_cols,
        'plant_names': plant_names,
    })
