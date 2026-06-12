import json
import os
import base64
from io import BytesIO
from datetime import date, timedelta

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.fft import fft, fftfreq
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib import messages
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from dashboard.helpers.config import COL_TIMESTAMP, COL_PLANT_NAME, TRENDLINE_STYLE
from dashboard.helpers.utils import get_base_col_name
from dashboard.helpers.data_processing import filter_dataframe, aggregate_dataframe, standardize_dataframe
from dashboard.helpers.cache_utils import DataResult
from dashboard.views.home import (
    get_session_df, set_session_df, delete_session_df, merge_combine_data
)
from dashboard.views.charting_utils import (
    create_plot, fig_to_b64, _plot_trendline, _plot_trendline_on_facet
)


# ---- DATA LOADING ----

@require_http_methods(["POST"])
def load_api_data(request):
    """Load tree data from ePlant API."""
    from dashboard.helpers.api_helpers import get_access_token, fetch_all_data
    from dashboard.views.home import _get_cached_devices

    if not request.session.session_key:
        request.session.save()

    username = settings.EPLANT_USERNAME
    password = settings.EPLANT_PASSWORD
    client_id = settings.EPLANT_CLIENT_ID

    if not all([username, password, client_id]):
        return HttpResponse(
            '<div class="alert alert-warning">API credentials not found. Please configure .env file.</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    selected = request.POST.getlist('selected_devices', [])
    if isinstance(selected, str):
        selected = json.loads(selected)

    if not selected:
        return HttpResponse(
            '<div class="alert alert-warning">Please select at least one tree.</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    start_date_str = request.POST.get('api_start_date', '')
    end_date_str = request.POST.get('api_end_date', '')

    try:
        start_date = date.fromisoformat(start_date_str) if start_date_str else date.today() - timedelta(days=7)
        end_date = date.fromisoformat(end_date_str) if end_date_str else date.today()
    except ValueError:
        return HttpResponse(
            '<div class="alert alert-danger">Invalid date format.</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    token_result = get_access_token(username, password, client_id)
    if not token_result.ok:
        return HttpResponse(
            f'<div class="alert alert-danger">{token_result.errors[0]}</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    access_token = token_result.data

    # Use shared cached device list (avoids duplicate API call)
    all_devices, error = _get_cached_devices()
    if error:
        return HttpResponse(
            f'<div class="alert alert-danger">{error}</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    selected_devices = [d for d in all_devices if d.get('name') in selected]

    if not selected_devices:
        return HttpResponse(
            '<div class="alert alert-warning">Selected trees not found in device list.</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    data_result = fetch_all_data(selected_devices, start_date, end_date, access_token)
    if not data_result.ok:
        return HttpResponse(
            f'<div class="alert alert-danger">{data_result.errors[0]}</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    api_df = data_result.data
    loaded_count = len(api_df)
    if api_df.empty:
        return HttpResponse(
            '<div class="alert alert-warning">No data found for selected range. Please try a different date range or tree selection.</div>'
            '<div hx-get="/api/devices/list/" hx-target="#device-select-container" hx-trigger="load" hx-swap="innerHTML" id="dev-refresh"></div>'
        )

    existing_df = get_session_df(request, 'api_df')
    if existing_df is not None and not existing_df.empty:
        api_df = pd.concat([existing_df, api_df], ignore_index=True)
        api_df = api_df.drop_duplicates(subset=[COL_TIMESTAMP, COL_PLANT_NAME], keep='last')
    set_session_df(request, 'api_df', api_df)
    merge_combine_data(request)

    total_count = len(api_df)
    count_warning = ''
    if total_count > 10000:
        count_warning = (
            f'<div class="alert alert-warning mt-2">'
            f'Total {total_count:,} records in session. Large datasets may slow down charts. '
            f'Consider narrowing the date range or clearing unused data.'
            f'</div>'
        )

    existing_count = total_count - loaded_count
    accum_note = f' ({existing_count:,} existing + {loaded_count:,} new)' if existing_count > 0 else ''
    plant_list = ', '.join(d.get('name', '') for d in selected_devices)
    response = HttpResponse(f"""
    <div class="alert alert-success">Loaded {loaded_count:,} records for {plant_list}. Total in session: {total_count:,} records across all plants{accum_note}.</div>
    {count_warning}
    <div class="d-flex gap-2 mt-2">
        <a href="/api/data/download/?format=csv" class="btn btn-sm btn-outline-primary">Download CSV</a>
        <a href="/api/data/download/?format=json" class="btn btn-sm btn-outline-secondary">Download JSON</a>
    </div>
    """)
    response['HX-Trigger'] = 'plantDataLoaded'
    return response


@require_http_methods(["POST"])
def clear_data(request):
    """Clear all session data."""
    if not request.session.session_key:
        request.session.save()
    for key in ['api_df', 'kestrel_df', 'lcra_df', 'history_df', 'hist_csv_df', 'combined_df']:
        delete_session_df(request, key)
    return HttpResponse(
        '<div class="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 mb-3">All data cleared. Reloading...</div>'
        '<div hx-get="/" hx-target="#main-content" hx-select="#main-content" hx-trigger="load delay:300ms" hx-swap="innerHTML"></div>'
    )


@require_http_methods(["POST"])
def fetch_weather(request):
    """Fetch historical weather from Open-Meteo."""
    from dashboard.helpers.weather_helpers import fetch_historical_weather

    start_str = request.POST.get('weather_start', '')
    end_str = request.POST.get('weather_end', '')
    try:
        s = date.fromisoformat(start_str) if start_str else date.today() - timedelta(days=7)
        e = date.fromisoformat(end_str) if end_str else date.today()
    except ValueError:
        return HttpResponse('<div class="alert alert-danger">Invalid date format.</div>')

    result = fetch_historical_weather(s, e)
    if not result.ok:
        return HttpResponse(f'<div class="alert alert-danger">{result.errors[0]}</div>')
    if result.data.empty:
        return HttpResponse('<div class="alert alert-warning">History unavailable.</div>')

    set_session_df(request, 'history_df', result.data)
    merge_combine_data(request)
    response = HttpResponse('<div class="alert alert-success">Historical weather loaded!</div>')
    response['HX-Trigger'] = 'plantDataLoaded'
    return response


@require_http_methods(["POST"])
def fetch_lcra_live(request):
    """Fetch live LCRA weather data."""
    from dashboard.helpers.lcra_helpers import fetch_lcra_data

    result = fetch_lcra_data()
    if not result.ok:
        return HttpResponse(f'<div class="alert alert-danger">{result.errors[0]}</div>')
    if result.data.empty:
        return HttpResponse('<div class="alert alert-warning">Could not fetch live weather.</div>')

    set_session_df(request, 'lcra_df', result.data)
    merge_combine_data(request)
    response = HttpResponse('<div class="alert alert-success">Live weather loaded!</div>')
    response['HX-Trigger'] = 'plantDataLoaded'
    return response


@require_http_methods(["POST"])
def upload_kestrel(request):
    """Handle Kestrel file upload."""
    from dashboard.helpers.kestrel_loader import load_uploaded_data

    uploaded_files = request.FILES.getlist('kestrel_files')
    if not uploaded_files:
        return HttpResponse('<div class="alert alert-warning">No files selected.</div>')

    result = load_uploaded_data(uploaded_files)
    msgs = ''.join(
        f'<div class="alert alert-{"danger" if e else "warning"}">{e if e else w}</div>'
        for e in result.errors for w in result.warnings
    )
    if result.errors:
        msgs += ''.join(f'<div class="alert alert-danger">{e}</div>' for e in result.errors)
    if result.data:
        kestrel_df = pd.concat(result.data.values(), ignore_index=True)
        set_session_df(request, 'kestrel_df', kestrel_df)
        merge_combine_data(request)
        msgs += f'<div class="alert alert-success">Kestrel files loaded! ({len(kestrel_df)} rows)</div>'

    response = HttpResponse(msgs or '<div class="alert alert-warning">No data found in files.</div>')
    if result.data:
        response['HX-Trigger'] = 'plantDataLoaded'
    return response


@require_http_methods(["GET"])
def download_data(request):
    """Download API data as CSV or JSON."""
    fmt = request.GET.get('format', 'csv')
    api_df = get_session_df(request, 'api_df')
    if api_df is None or api_df.empty:
        return HttpResponse('No API data loaded yet.', content_type='text/plain', status=404)

    if fmt == 'json':
        content = api_df.to_json(orient="records", date_format="iso")
        resp = HttpResponse(content, content_type='application/json')
        resp['Content-Disposition'] = 'attachment; filename="api_data.json"'
    else:
        content = api_df.to_csv(index=False)
        resp = HttpResponse(content, content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="api_data.csv"'
    return resp


@require_http_methods(["POST"])
def extract_historical(request):
    """Extract specific trees from a large historical CSV."""
    from dashboard.helpers.api_helpers import process_large_historical_csv

    uploaded_file = request.FILES.get('large_csv')
    target_trees_str = request.POST.get('target_trees', '')

    if not uploaded_file or not target_trees_str:
        return HttpResponse('<div class="alert alert-warning">Please upload a file and specify target trees.</div>')

    target_trees = [t.strip() for t in target_trees_str.split(',')]
    result = process_large_historical_csv(uploaded_file, target_trees)

    if not result.ok:
        return HttpResponse(f'<div class="alert alert-danger">{result.errors[0]}</div>')
    if result.data.empty:
        return HttpResponse('<div class="alert alert-warning">No matching data found.</div>')

    set_session_df(request, 'hist_csv_df', result.data)
    merge_combine_data(request)
    response = HttpResponse(f'<div class="alert alert-success">Extracted {len(result.data)} readings for target trees!</div>')
    response['HX-Trigger'] = 'plantDataLoaded'
    return response


# ---- CHARTING ----

@require_http_methods(["POST"])
def generate_chart(request):
    """Generate a chart based on graphing form submission. Returns HTML partial with chart image."""
    combined_df = get_session_df(request, 'combined_df')
    if combined_df is None or combined_df.empty:
        return HttpResponse('<div class="alert alert-warning">No data available. Please load data first.</div>')

    # Parse form data
    agg_level = request.POST.get('aggregation_level', '5-minute (Raw)')
    agg_method = request.POST.get('aggregation_method', 'Mean (Average)')
    plot_overall = request.POST.get('plot_overall_average') == 'on'
    selected_plants = request.POST.getlist('selected_plants', [])
    group_by_pattern = request.POST.get('group_by_pattern') == 'on'
    group_patterns_str = request.POST.get('group_patterns', '')
    use_facets = request.POST.get('use_facets') == 'facets'
    filter_zeros = request.POST.get('filter_zeros') == 'on'
    min_val = float(request.POST.get('min_val', 100))
    auto_stitch = request.POST.get('auto_stitch') == 'on'
    jump_threshold = float(request.POST.get('jump_threshold', 1000))
    norm_mode = request.POST.get('normalization_mode', 'None (Raw Data)')
    x_axis_col = request.POST.get('x_axis_col', COL_TIMESTAMP)
    y_axis_col = request.POST.get('y_axis_col', 'Dendrometer (microns)')
    plot_type = request.POST.get('plot_type', 'Line Plot')
    title = request.POST.get('title', 'Plot')
    x_label = request.POST.get('x_label', '')
    y_label = request.POST.get('y_label', '')
    smooth_window = int(request.POST.get('smooth_window', 1))
    enable_binning = request.POST.get('enable_binning') == 'on'
    bin_size = float(request.POST.get('bin_size', 2.0))
    start_date_str = request.POST.get('start_date', '')
    end_date_str = request.POST.get('end_date', '')

    # Standardize
    result = standardize_dataframe(combined_df)
    if not result.ok:
        return HttpResponse(f'<div class="alert alert-danger">{result.errors[0]}</div>')
    df = result.data

    if df.empty:
        return HttpResponse('<div class="alert alert-danger">Data is empty after standardization.</div>')

    # Build configs dict
    configs = {
        'aggregation_level': agg_level,
        'aggregation_method': agg_method,
        'plot_overall_average': plot_overall,
        'selected_plants': selected_plants if selected_plants else None,
        'group_by_pattern': group_by_pattern,
        'group_patterns': group_patterns_str,
        'use_facets': use_facets,
        'filter_zeros': filter_zeros,
        'min_val': min_val,
        'auto_stitch': auto_stitch,
        'jump_threshold': jump_threshold,
        'normalization_mode': norm_mode,
    }

    # Parse dates
    start_date = date.fromisoformat(start_date_str) if start_date_str else None
    end_date = date.fromisoformat(end_date_str) if end_date_str else None

    # Filter
    filtered_df = filter_dataframe(df, start_date=start_date, end_date=end_date,
                                   selected_plants=selected_plants, timestamp_col=COL_TIMESTAMP)

    # Filter zeros
    if filter_zeros:
        dendro_col = "Dendrometer (microns)"
        if dendro_col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df[dendro_col] >= min_val]

    # Group by pattern
    if group_by_pattern and group_patterns_str:
        patterns = [p.strip() for p in group_patterns_str.split(',') if p.strip()]

        def assign_group(name):
            for p in patterns:
                if p.lower() in str(name).lower():
                    return p
            return "Other"

        if COL_PLANT_NAME in filtered_df.columns:
            unique_plants = filtered_df[COL_PLANT_NAME].unique()
            group_map = {name: assign_group(name) for name in unique_plants}
            filtered_df[COL_PLANT_NAME] = filtered_df[COL_PLANT_NAME].map(group_map)

    # Aggregate
    agg_result = aggregate_dataframe(filtered_df, aggregation_level=agg_level,
                                     aggregation_method=agg_method,
                                     plot_overall_average=plot_overall)
    if not agg_result.ok:
        return HttpResponse(f'<div class="alert alert-danger">{agg_result.errors[0]}</div>')
    data_to_plot = agg_result.data

    if data_to_plot.empty:
        return HttpResponse('<div class="alert alert-warning">No data remains after filtering and aggregation.</div>')

    # Auto-stitch
    if auto_stitch:
        dendro_col = "Dendrometer (microns)"
        if dendro_col in data_to_plot.columns:
            try:
                data_to_plot = data_to_plot.sort_values(by=[COL_PLANT_NAME, COL_TIMESTAMP]).copy()
                diffs = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform(
                    lambda x: x.ffill().diff()).fillna(0)
                jumps = diffs.where(diffs.abs() > jump_threshold, 0)
                adjustments = jumps.groupby(data_to_plot[COL_PLANT_NAME]).cumsum()
                data_to_plot[dendro_col] = data_to_plot[dendro_col] - adjustments
            except Exception as e:
                pass

    # Normalization
    if norm_mode == "% Deviation from Mean":
        dendro_col = "Dendrometer (microns)"
        if dendro_col in data_to_plot.columns:
            plant_means = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform('mean')
            new_col = "Dendrometer (% Deviation)"
            data_to_plot[new_col] = ((data_to_plot[dendro_col] - plant_means) / plant_means) * 100
            if y_axis_col == dendro_col:
                y_axis_col = new_col
    elif norm_mode == "Change from Start (Zero-Indexed)":
        dendro_col = "Dendrometer (microns)"
        if dendro_col in data_to_plot.columns:
            def zero_index(group):
                valid = group.dropna()
                if valid.empty:
                    return group
                return group - valid.iloc[0]
            new_col = "Dendrometer (Change from Start)"
            data_to_plot[new_col] = data_to_plot.groupby(COL_PLANT_NAME)[dendro_col].transform(zero_index)
            if y_axis_col == dendro_col:
                y_axis_col = new_col

    # Binning
    if enable_binning and pd.api.types.is_numeric_dtype(data_to_plot[x_axis_col]):
        binned_col = f"{x_axis_col} (Binned)"
        data_to_plot[binned_col] = np.floor(data_to_plot[x_axis_col] / bin_size) * bin_size
        group_cols = [binned_col]
        if COL_PLANT_NAME in data_to_plot.columns:
            group_cols.insert(0, COL_PLANT_NAME)
        data_to_plot = data_to_plot.groupby(group_cols).mean(numeric_only=True).reset_index()
        x_axis_col = binned_col

    # Smoothing
    if x_axis_col == COL_TIMESTAMP and smooth_window > 1:
        if COL_PLANT_NAME in data_to_plot.columns:
            data_to_plot[y_axis_col] = data_to_plot.groupby(COL_PLANT_NAME)[y_axis_col].transform(
                lambda x: x.rolling(smooth_window, min_periods=1).mean())
        else:
            data_to_plot[y_axis_col] = data_to_plot[y_axis_col].rolling(smooth_window, min_periods=1).mean()

    # Generate plot
    fig = create_plot(data_to_plot, x_axis_col, y_axis_col, plot_type, title, x_label, y_label, configs)

    if fig is None:
        return HttpResponse('<div class="alert alert-warning">Cannot create plot with current data.</div>')

    chart_b64 = fig_to_b64(fig)

    # Net growth metrics
    growth_html = ""
    if "Dendrometer" in y_axis_col and x_axis_col == COL_TIMESTAMP:
        growth_html = '<div class="mt-3"><h5>Net Growth Analysis</h5><div class="row">'
        if COL_PLANT_NAME in data_to_plot.columns:
            for plant in data_to_plot[COL_PLANT_NAME].unique():
                plant_data = data_to_plot[data_to_plot[COL_PLANT_NAME] == plant].sort_values(by=COL_TIMESTAMP)
                if not plant_data.empty:
                    first_val = plant_data[y_axis_col].iloc[0]
                    last_val = plant_data[y_axis_col].iloc[-1]
                    net = last_val - first_val
                    growth_html += f"""
                    <div class="col-auto">
                        <div class="card"><div class="card-body text-center">
                            <h6>{plant}</h6>
                            <span class="fs-5">{last_val:.1f} um</span><br>
                            <span class="{'text-success' if net >= 0 else 'text-danger'}">{net:+.1f} um</span>
                        </div></div>
                    </div>"""
        growth_html += '</div></div>'

    return HttpResponse(f"""
    <img src="{chart_b64}" class="img-fluid" alt="Chart">
    {growth_html}
    <div class="alert alert-info mt-2">
        <small>Interpreting Anomalies: Large vertical jumps usually indicate sensor resets. Daily patterns remain valid.</small>
    </div>
    <a href="{chart_b64}" download="chart.png" class="btn btn-sm btn-outline-primary mt-2">Download PNG</a>
    """)


# ---- PREDICTION ----

@require_http_methods(["POST"])
def run_prediction(request):
    """Run ML prediction based on slider inputs."""
    import joblib

    model_path = os.path.join(settings.MODELS_DIR, 'tree_growth_model.pkl')
    columns_path = os.path.join(settings.MODELS_DIR, 'model_columns.pkl')

    try:
        model = joblib.load(model_path)
        model_columns = joblib.load(columns_path)
    except FileNotFoundError:
        return HttpResponse('<div class="alert alert-danger">Model not found. Please train the model first.</div>')

    try:
        temp = float(request.POST.get('temp', 25.0))
        humidity = float(request.POST.get('humidity', 50.0))
        dew_point = float(request.POST.get('dew_point', 15.0))
        plant_name = request.POST.get('plant_name', '')
    except ValueError:
        return HttpResponse('<div class="alert alert-danger">Invalid input values.</div>')

    input_data = {
        'Temperature_C': [temp],
        'Plant Name': [plant_name]
    }
    if any('Humidity' in col for col in model_columns):
        input_data['Humidity'] = [humidity]
    if any('Dew Point' in col for col in model_columns):
        input_data['Dew Point'] = [dew_point]

    input_df = pd.DataFrame(input_data)
    input_df_encoded = pd.get_dummies(input_df, columns=['Plant Name'], prefix='Plant')
    input_df_processed = input_df_encoded.reindex(columns=model_columns, fill_value=0)

    prediction = model.predict(input_df_processed)
    predicted_value = float(prediction[0])

    return HttpResponse(f"""
    <div class="card">
        <div class="card-body text-center">
            <h5>Predicted Dendrometer Reading for {plant_name}</h5>
            <span class="fs-3 fw-bold">{predicted_value:.2f} microns</span>
        </div>
    </div>
    """)


# ---- COMFORT INDEX ----

@require_http_methods(["POST"])
def compute_comfort(request):
    """Calculate and plot Tree Comfort Index from Kestrel data."""
    kestrel_df = get_session_df(request, 'kestrel_df')
    if kestrel_df is None or kestrel_df.empty:
        return HttpResponse('<div class="alert alert-warning">No Kestrel data found. Please upload files on the Home page.</div>')

    agg_level = request.POST.get('aggregation_level', 'Daily')
    use_facets = request.POST.get('use_facets') == 'facets'

    df = kestrel_df.copy()
    temp_col, rh_col, dew_col = 'Temperature_C', 'Humidity', 'Dew Point'

    for col in [temp_col, rh_col, dew_col]:
        if col not in df.columns:
            return HttpResponse(f'<div class="alert alert-danger">Required column "{col}" not found in data.</div>')
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df.dropna(subset=[temp_col, rh_col, dew_col], inplace=True)

    # VPD calculation
    es = 0.6108 * np.exp((17.27 * df[temp_col]) / (df[temp_col] + 237.3))
    ea = df[rh_col] / 100.0 * es
    df['VPD (kPa)'] = es - ea

    def vectorized_score(series, ideal_min, ideal_max, soft_range=5):
        conditions = [
            (series >= ideal_min) & (series <= ideal_max),
            (series >= ideal_min - soft_range) & (series <= ideal_max + soft_range)
        ]
        choices = [1, 0.5]
        return np.select(conditions, choices, default=0)

    df['Temp Score'] = vectorized_score(df[temp_col], 15, 25)
    df['RH Score'] = vectorized_score(df[rh_col], 40, 60)
    df['Dew Score'] = vectorized_score(df[dew_col], 10, 17)
    df['VPD Score'] = vectorized_score(df['VPD (kPa)'], 0.4, 1.2)
    df['Tree Comfort Index'] = df[['Temp Score', 'RH Score', 'Dew Score', 'VPD Score']].mean(axis=1)

    # Aggregate
    if agg_level != 'Raw':
        from dashboard.helpers.data_processing import aggregate_dataframe
        agg_result = aggregate_dataframe(df, aggregation_level=agg_level, aggregation_method='Mean (Average)')
        if agg_result.ok:
            df = agg_result.data

    # Plot
    if use_facets and COL_PLANT_NAME in df.columns:
        g = sns.relplot(data=df, x=COL_TIMESTAMP, y='Tree Comfort Index', col=COL_PLANT_NAME,
                        kind='line', height=4, aspect=1.5, col_wrap=3,
                        facet_kws={'sharey': True, 'sharex': True})
        g.set_titles(col_template="{col_name}")
        g.fig.suptitle("Tree Comfort Index Over Time", y=1.03, fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        fig = g.fig
    else:
        fig, ax = plt.subplots(figsize=(12, 6))
        if COL_PLANT_NAME in df.columns:
            sns.lineplot(data=df, x=COL_TIMESTAMP, y='Tree Comfort Index', hue=COL_PLANT_NAME, ax=ax)
        else:
            sns.lineplot(data=df, x=COL_TIMESTAMP, y='Tree Comfort Index', ax=ax)
        ax.set_title("Tree Comfort Index Over Time", fontsize=16)
        ax.set_ylabel("Comfort Index (1.0 is ideal)")
        ax.set_xlabel("Date")
        ax.grid(True)
        if COL_PLANT_NAME in df.columns:
            ax.legend(title="Plant")
        fig.autofmt_xdate()
        fig = ax.figure

    chart_b64 = fig_to_b64(fig)

    # Display data table
    display_cols = [COL_TIMESTAMP, COL_PLANT_NAME, 'Temperature_C', 'Humidity', 'VPD (kPa)', 'Tree Comfort Index']
    available_cols = [c for c in display_cols if c in df.columns]
    table_html = df[available_cols].head(50).to_html(classes='table table-sm table-striped', index=False) if not df.empty else ''

    return HttpResponse(f"""
    <img src="{chart_b64}" class="img-fluid mb-3" alt="Comfort Index Chart">
    <h5>Comfort Index Score: 1.0 is ideal, closer to 0 indicates stress</h5>
    <details>
        <summary>Data Table (first 50 rows)</summary>
        <div class="table-responsive mt-2">{table_html}</div>
    </details>
    """)


# ---- FOURIER ----

@require_http_methods(["POST"])
def run_fourier(request):
    """Run FFT analysis for a selected plant and return chart + diagnosis."""
    combined_df = get_session_df(request, 'combined_df')
    if combined_df is None or combined_df.empty:
        return HttpResponse('<div class="alert alert-warning">No data available.</div>')

    selected_plant = request.POST.get('plant_name', '')
    target_col = request.POST.get('target_col', 'Dendrometer (microns)')
    max_view = int(request.POST.get('max_view', 168))

    df = combined_df.copy()
    df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP], errors='coerce', utc=True).dt.tz_localize(None)
    df.dropna(subset=[COL_TIMESTAMP], inplace=True)

    # Apply date filter
    start_str = request.POST.get('start_date', '')
    end_str = request.POST.get('end_date', '')
    if start_str and end_str:
        s = pd.to_datetime(start_str)
        e = pd.to_datetime(end_str) + pd.Timedelta(days=1)
        df = df[(df[COL_TIMESTAMP] >= s) & (df[COL_TIMESTAMP] < e)]

    plant_df = df[df[COL_PLANT_NAME] == selected_plant].copy()
    plant_df = plant_df.sort_values(COL_TIMESTAMP)

    try:
        resampled = plant_df.set_index(COL_TIMESTAMP)[target_col].resample('1h').mean()
    except Exception as e:
        return HttpResponse(f'<div class="alert alert-danger">Error resampling: {e}</div>')

    resampled = resampled.interpolate(method='linear').dropna()

    if len(resampled) < 24:
        return HttpResponse(f'<div class="alert alert-danger">Need at least 24 data points (got {len(resampled)}).</div>')

    N = len(resampled)
    T_spacing = 1.0
    yf = fft(resampled.values)
    xf = fftfreq(N, T_spacing)[:N // 2]
    amplitude = 2.0 / N * np.abs(np.array(yf[0:N // 2]))

    with np.errstate(divide='ignore'):
        periods = 1 / xf

    mask = (periods >= 6) & (periods <= max_view)
    valid_periods = periods[mask]
    valid_amplitudes = amplitude[mask]

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(valid_periods, valid_amplitudes, color='purple', linewidth=2)
    ax.set_title(f"Cycle Strength for {selected_plant} ({target_col})", fontsize=16)
    ax.set_xlabel("Cycle Length (Hours)", fontsize=12)
    ax.set_ylabel("Amplitude (microns)", fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.axvline(x=24, color='green', linestyle='--', label="24 Hour Cycle (Daily)")
    ax.axvline(x=12, color='orange', linestyle=':', alpha=0.5, label="12 Hour Cycle")
    ax.legend()
    chart_b64 = fig_to_b64(fig)

    # Health assessment
    diagnosis_html = ""
    if len(valid_periods) > 0:
        idx_closest = (np.abs(valid_periods - 24.0)).argmin()
        amp_24h = valid_amplitudes.iloc[idx_closest]
        avg_noise = np.mean(valid_amplitudes)
        snr = amp_24h / avg_noise if avg_noise > 0 else 0

        if snr >= 3.0:
            if amp_24h > 15.0:
                diag = f"Healthy Active Tree: Strong 24h rhythm ({snr:.1f}x noise) with high amplitude ({amp_24h:.1f}um)."
                diag_class = "success"
            elif amp_24h > 5.0:
                diag = f"Dormant or Low Activity: Clear 24h rhythm, moderate amplitude ({amp_24h:.1f}um)."
                diag_class = "info"
            else:
                diag = f"Possible Passive/Dead Signal: Weak 24h rhythm ({amp_24h:.1f}um). Likely thermal expansion."
                diag_class = "warning"
        elif snr >= 2.5:
            diag = f"Stressed/Dead/Sensor Issue: 24h cycle present ({snr:.1f}x noise) but buried in noise."
            diag_class = "warning"
        else:
            diag = f"No Rhythm Detected: 24-hour cycle lost in noise ({snr:.1f}x)."
            diag_class = "danger"

        diagnosis_html = f"""
        <div class="row mt-3">
            <div class="col">24h Amplitude: <strong>{amp_24h:.2f} um</strong></div>
            <div class="col">Background Noise: <strong>{avg_noise:.2f} um</strong></div>
            <div class="col">Clarity (SNR): <strong>{snr:.1f}x</strong></div>
        </div>
        <div class="alert alert-{diag_class} mt-2"><strong>Diagnosis:</strong> {diag}</div>
        """

    return HttpResponse(f"""
    <img src="{chart_b64}" class="img-fluid" alt="Fourier Spectrum">
    {diagnosis_html}
    """)
