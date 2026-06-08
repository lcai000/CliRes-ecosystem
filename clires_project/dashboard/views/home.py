import pandas as pd
import numpy as np
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib import messages
from django.core.cache import cache
from datetime import timedelta, date

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
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
    """HTMX endpoint to fetch device list for sidebar."""
    devices, error = _get_cached_devices()
    if error:
        devices_html = f'<select name="selected_devices" multiple class="form-select form-select-sm" size="6"><option disabled>{error}</option></select>'
        return HttpResponse(devices_html)

    rows = ''.join(
        f'<option value="{d["name"]}">{d["name"]}</option>'
        for d in devices
    )
    devices_html = f'<select name="selected_devices" multiple class="form-select form-select-sm" size="6">{rows}</select>'
    return HttpResponse(devices_html)


