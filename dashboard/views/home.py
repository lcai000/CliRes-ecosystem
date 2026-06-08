import os
import joblib
import pandas as pd
import numpy as np
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib import messages
from django.core.cache import cache
from django.conf import settings
from datetime import timedelta, date

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.data_processing import standardize_dataframe
from dashboard.helpers.cache_utils import DataResult


def _get_cached_devices():
    """Fetch device list from cache or ePlant API.

    Caches the raw device list under 'devices:shared' so the
    devices_list view can reuse a single API call.
    Returns (devices, error_message) tuple.
    """
    CACHE_KEY = 'devices:shared:v1'

    devices = cache.get(CACHE_KEY)
    if devices and isinstance(devices, list) and all(isinstance(d, dict) for d in devices):
        return devices, None

    try:
        from django.conf import settings
        from dashboard.helpers.api_helpers import get_access_token, fetch_plant_names

        username = settings.EPLANT_USERNAME
        password = settings.EPLANT_PASSWORD
        client_id = settings.EPLANT_CLIENT_ID

        if not all([username, password, client_id]):
            return None, "API credentials not configured. Check your .env file."

        token_result = get_access_token(username, password, client_id)
        if not token_result.ok:
            return None, token_result.errors[0]

        devices_result = fetch_plant_names(token_result.data)
        if not devices_result.ok:
            return None, devices_result.errors[0]

        if not devices_result.data:
            return None, "No devices found for this account."

        cache.set(CACHE_KEY, devices_result.data, timeout=3600)
        return devices_result.data, None
    except Exception as e:
        return None, str(e)


def get_session_df(request, key):
    """Retrieve a DataFrame from the cache for this session."""
    if not request.session.session_key:
        return None
    cache_key = f"user:{request.session.session_key}:{key}"
    return cache.get(cache_key)


def set_session_df(request, key, df):
    """Store a DataFrame in the cache for this session."""
    if not request.session.session_key:
        request.session.save()
    cache_key = f"user:{request.session.session_key}:{key}"
    cache.set(cache_key, df, timeout=86400)


def delete_session_df(request, key):
    if not request.session.session_key:
        return
    cache_key = f"user:{request.session.session_key}:{key}"
    cache.delete(cache_key)


def merge_combine_data(request):
    """Re-create combined_df from all source dataframes."""
    data_to_combine = []
    api_df = get_session_df(request, 'api_df')
    history_df = get_session_df(request, 'history_df')
    lcra_df = get_session_df(request, 'lcra_df')
    kestrel_df = get_session_df(request, 'kestrel_df')
    hist_csv_df = get_session_df(request, 'hist_csv_df')

    if api_df is not None:
        api_df = api_df.copy()
        if history_df is not None:
            history_df = history_df.sort_values(COL_TIMESTAMP)
            api_df = api_df.sort_values(COL_TIMESTAMP)
            if pd.api.types.is_datetime64_any_dtype(api_df[COL_TIMESTAMP]):
                if api_df[COL_TIMESTAMP].dt.tz is not None:
                    api_df[COL_TIMESTAMP] = api_df[COL_TIMESTAMP].dt.tz_convert('UTC').dt.tz_localize(None)
            try:
                merged_api = pd.merge_asof(
                    api_df,
                    history_df[[COL_TIMESTAMP, 'Austin_Temp_C', 'Austin_Humidity', 'Rainfall_mm']],
                    on=COL_TIMESTAMP,
                    direction='nearest',
                    tolerance=pd.Timedelta('1 hour')
                )
                api_df = merged_api
            except Exception:
                pass
        elif lcra_df is not None:
            ref_vals = lcra_df.iloc[0]
            for col in ['Austin_Temp_C', 'Austin_Humidity', 'Rainfall_mm']:
                if col in ref_vals:
                    api_df[col] = ref_vals[col]
        data_to_combine.append(api_df)

    if kestrel_df is not None:
        data_to_combine.append(kestrel_df)
    if lcra_df is not None:
        data_to_combine.append(lcra_df)
    if history_df is not None:
        data_to_combine.append(history_df)
    if hist_csv_df is not None:
        data_to_combine.append(hist_csv_df)

    if data_to_combine:
        combined = pd.concat(data_to_combine, ignore_index=True)
        set_session_df(request, 'combined_df', combined)
        return combined
    return None


def home_view(request):
    """Home page with plots and sidebar data loading."""
    if not request.session.session_key:
        request.session.save()

    today = date.today()
    context = {
        'api_df_exists': get_session_df(request, 'api_df') is not None,
        'kestrel_df_exists': get_session_df(request, 'kestrel_df') is not None,
        'combined_df_exists': get_session_df(request, 'combined_df') is not None,
        'default_start_date': (today - timedelta(days=30)).isoformat(),
        'default_end_date': today.isoformat(),
    }

    # Date range for combined data
    combined_df = get_session_df(request, 'combined_df')
    if combined_df is not None and not combined_df.empty:
        if COL_TIMESTAMP in combined_df.columns:
            ts = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce')
            min_date = ts.min().date()
            max_date = ts.max().date()
            if max_date < today:
                max_date = today
            if min_date >= max_date:
                max_date = min_date + timedelta(days=1)
            context['min_date'] = min_date.isoformat()
            context['max_date'] = max_date.isoformat()

    return render(request, 'dashboard/home.html', context)


def devices_list(request):
    """HTMX endpoint to fetch device list for sidebar/toolbar."""
    devices, error = _get_cached_devices()
    if error:
        devices_html = f'<select name="selected_devices" multiple class="w-full border border-slate-300 rounded-xl px-3 py-1.5 text-sm h-28 focus:ring-2 focus:ring-primary/20 focus:border-primary transition"><option disabled>{error}</option></select>'
        return HttpResponse(devices_html)

    rows = ''.join(
        f'<option value="{d["name"]}">{d["name"]}</option>'
        for d in devices
    )
    devices_html = f'<select name="selected_devices" multiple class="w-full border border-slate-300 rounded-xl px-3 py-1.5 text-sm h-28 focus:ring-2 focus:ring-primary/20 focus:border-primary transition">{rows}</select>'
    return HttpResponse(devices_html)


def dashboard_view(request):
    """Single unified dashboard page with all sections.

    Merges context from all old page views into one super-context so that
    every section partial has the variables it needs.
    """
    if not request.session.session_key:
        request.session.save()

    today = date.today()
    context = {
        'default_start_date': (today - timedelta(days=30)).isoformat(),
        'default_end_date': today.isoformat(),
    }

    # ---- Data existence flags ----
    api_df = get_session_df(request, 'api_df')
    kestrel_df = get_session_df(request, 'kestrel_df')
    combined_df = get_session_df(request, 'combined_df')

    context['api_df_exists'] = api_df is not None
    context['kestrel_df_exists'] = kestrel_df is not None
    context['combined_df_exists'] = combined_df is not None

    # Date range from combined data
    if combined_df is not None and not combined_df.empty and COL_TIMESTAMP in combined_df.columns:
        ts = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce')
        min_d = ts.min().date()
        max_d = ts.max().date()
        if max_d < today:
            max_d = today
        if min_d >= max_d:
            max_d = min_d + timedelta(days=1)
        context['min_date'] = min_d.isoformat()
        context['max_date'] = max_d.isoformat()

    # ---- Data Stats (for overview cards) ----
    data_stats = {'row_count': '--', 'plant_count': '--', 'date_range': '--'}
    if combined_df is not None and not combined_df.empty:
        data_stats['row_count'] = f"{len(combined_df):,}"
        if COL_PLANT_NAME in combined_df.columns:
            data_stats['plant_count'] = str(combined_df[COL_PLANT_NAME].nunique())
        if COL_TIMESTAMP in combined_df.columns:
            ts = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce')
            if not ts.empty:
                data_stats['date_range'] = f"{ts.min().date()} – {ts.max().date()}"
    context['data_stats'] = data_stats

    # ---- Graphing Tool context ----
    if combined_df is not None and not combined_df.empty:
        result = standardize_dataframe(combined_df)
        if result.ok:
            cdf = result.data
            context['has_graph_data'] = True
            context['data_head'] = cdf.head(10).to_html(
                classes='table-auto w-full text-xs border-collapse', index=False
            )
            context['graph_columns'] = cdf.columns.tolist()
            context['graph_numeric_columns'] = cdf.select_dtypes(include=np.number).columns.tolist()
            context['graph_plant_names'] = sorted(cdf[COL_PLANT_NAME].unique().tolist()) if COL_PLANT_NAME in cdf.columns else []
        else:
            context['has_graph_data'] = False
            messages.error(request, result.errors[0])
    else:
        context['has_graph_data'] = False

    # ---- Comfort context ----
    if kestrel_df is not None and not kestrel_df.empty:
        context['has_comfort_data'] = True
    else:
        context['has_comfort_data'] = False

    # ---- Fourier context ----
    if combined_df is not None and not combined_df.empty:
        context['has_fourier_data'] = True
        context['fourier_plant_names'] = sorted(combined_df[COL_PLANT_NAME].unique().tolist()) if COL_PLANT_NAME in combined_df.columns else []
        numeric_cols = combined_df.select_dtypes(include=np.number).columns.tolist()
        context['fourier_numeric_columns'] = numeric_cols
        default_col_idx = 0
        for i, col in enumerate(numeric_cols):
            if "Dendrometer" in col:
                default_col_idx = i
                break
        context['fourier_default_col_idx'] = default_col_idx
    else:
        context['has_fourier_data'] = False

    # ---- Prediction context ----
    model_columns = None
    pred_plant_names = []
    perf_text = ""
    try:
        model_path = os.path.join(settings.MODELS_DIR, 'tree_growth_model.pkl')
        columns_path = os.path.join(settings.MODELS_DIR, 'model_columns.pkl')
        if os.path.exists(model_path) and os.path.exists(columns_path):
            model_columns = joblib.load(columns_path)
            pred_plant_names = sorted([col.replace('Plant_', '') for col in model_columns if col.startswith('Plant_')])
    except Exception:
        pass

    has_pred_model = model_columns is not None and len(pred_plant_names) > 0

    perf_path = os.path.join(settings.MODELS_DIR, 'model_performance.txt')
    if os.path.exists(perf_path):
        with open(perf_path, 'r') as f:
            perf_text = f.read()

    context['has_pred_model'] = has_pred_model
    context['pred_plant_names'] = pred_plant_names
    context['model_performance'] = perf_text

    return render(request, 'dashboard/dashboard.html', context)


