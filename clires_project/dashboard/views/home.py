import pandas as pd
import numpy as np
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib import messages
from django.core.cache import cache
from datetime import timedelta, date

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME
from dashboard.helpers.cache_utils import DataResult


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

    context = {
        'api_df_exists': get_session_df(request, 'api_df') is not None,
        'kestrel_df_exists': get_session_df(request, 'kestrel_df') is not None,
        'combined_df_exists': get_session_df(request, 'combined_df') is not None,
    }

    # Date range for combined data
    combined_df = get_session_df(request, 'combined_df')
    if combined_df is not None and not combined_df.empty:
        if COL_TIMESTAMP in combined_df.columns:
            ts = pd.to_datetime(combined_df[COL_TIMESTAMP], errors='coerce')
            min_date = ts.min().date()
            max_date = ts.max().date()
            today = date.today()
            if max_date < today:
                max_date = today
            if min_date >= max_date:
                max_date = min_date + timedelta(days=1)
            context['min_date'] = min_date.isoformat()
            context['max_date'] = max_date.isoformat()

    return render(request, 'dashboard/home.html', context)


def devices_list(request):
    """HTMX endpoint to fetch device list for sidebar."""
    devices_html = cache.get('devices:html')
    if devices_html:
        return HttpResponse(devices_html)

    try:
        from django.conf import settings
        from dashboard.helpers.api_helpers import get_access_token, fetch_plant_names

        username = settings.EPLANT_USERNAME
        password = settings.EPLANT_PASSWORD
        client_id = settings.EPLANT_CLIENT_ID

        if all([username, password, client_id]):
            token_result = get_access_token(username, password, client_id)
            if token_result.ok:
                devices_result = fetch_plant_names(token_result.data)
                if devices_result.ok and devices_result.data:
                    rows = ''.join(
                        f'<option value="{d["name"]}">{d["name"]}</option>'
                        for d in devices_result.data
                    )
                    devices_html = f'<select name="selected_devices" multiple class="form-select form-select-sm" size="6">{rows}</select>'
                    cache.set('devices:html', devices_html, timeout=3600)
                    return HttpResponse(devices_html)
    except Exception:
        pass

    devices_html = '<select name="selected_devices" multiple class="form-select form-select-sm" size="6"><option disabled>Could not load devices</option></select>'
    return HttpResponse(devices_html)


def device_inventory(request):
    """HTMX endpoint to fetch device inventory table for home page."""
    cached = cache.get('devices:inventory:html')
    if cached:
        return HttpResponse(cached)

    try:
        from django.conf import settings
        from dashboard.helpers.api_helpers import get_access_token, fetch_plant_names
        import pandas as pd

        username = settings.EPLANT_USERNAME
        password = settings.EPLANT_PASSWORD
        client_id = settings.EPLANT_CLIENT_ID

        if all([username, password, client_id]):
            token_result = get_access_token(username, password, client_id)
            if token_result.ok:
                devices_result = fetch_plant_names(token_result.data)
                if devices_result.ok and devices_result.data:
                    df = pd.DataFrame(devices_result)
                    display_cols = ['name', 'install_date', 'last_active']
                    df = df[[c for c in display_cols if c in df.columns]]
                    df = df.rename(columns={
                        'name': 'Tree/Device Name',
                        'install_date': 'Install Date',
                        'last_active': 'Last Server Contact (UTC)'
                    })
                    html = df.to_html(classes='table table-sm table-striped', index=False)
                    cache.set('devices:inventory:html', html, timeout=3600)
                    return HttpResponse(html)
    except Exception:
        pass

    html = '<div class="alert alert-info">Connect to the API in the sidebar to see device inventory.</div>'
    return HttpResponse(html)
