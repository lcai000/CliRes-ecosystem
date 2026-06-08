import os
import joblib
import pandas as pd
from django.shortcuts import render
from django.conf import settings
from datetime import timedelta, date


def _date_defaults():
    today = date.today()
    return {
        'default_start_date': (today - timedelta(days=30)).isoformat(),
        'default_end_date': today.isoformat(),
    }


def prediction_view(request):
    """Prediction Tool page."""
    if not request.session.session_key:
        request.session.save()

    model_columns = None
    plant_names = []

    try:
        model_path = os.path.join(settings.MODELS_DIR, 'tree_growth_model.pkl')
        columns_path = os.path.join(settings.MODELS_DIR, 'model_columns.pkl')
        if os.path.exists(model_path) and os.path.exists(columns_path):
            model_columns = joblib.load(columns_path)
            plant_names = sorted([col.replace('Plant_', '') for col in model_columns if col.startswith('Plant_')])
    except Exception:
        pass

    has_model = model_columns is not None and len(plant_names) > 0

    # Model performance summary
    perf_text = ""
    perf_path = os.path.join(settings.MODELS_DIR, 'model_performance.txt')
    if os.path.exists(perf_path):
        with open(perf_path, 'r') as f:
            perf_text = f.read()

    return render(request, 'dashboard/prediction.html', {
        'has_model': has_model,
        'plant_names': plant_names,
        'model_performance': perf_text,
        **_date_defaults(),
    })
