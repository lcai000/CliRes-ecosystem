# CLAUDE.md — Cli-Res Dashboard

## Project Overview
Django monolith dashboard for tree health monitoring — fetches dendrometer/weather data from ePlant API, Open-Meteo, and LCRA; visualizes with matplotlib/seaborn; ML prediction and FFT analysis. Migrated from Streamlit.

**Stack:** Django 4.2+, Python, SQLite, Redis, HTMX + Alpine.js + Tailwind + Bootstrap 5 (CDN, no JS build step)

## Directory Structure
```
clires_project/
├── manage.py                          # Django management script
├── requirements.txt                   # Python dependencies
├── .env                               # Secrets (DEBUG, REDIS_URL, EPLANT_*)
├── db.sqlite3                         # SQLite DB (sessions only, no app models)
├── media/                             # Uploaded media (empty)
├── clires_dashboard/                  # Django project package
│   ├── settings.py                    # All config (DB, cache, ePlant creds, model paths)
│   ├── urls.py                        # Root URLconf → includes dashboard.urls
│   └── wsgi.py                        # WSGI entry point
└── dashboard/                         # Main (and only) Django app
    ├── apps.py                        # AppConfig — loads ML model in ready()
    ├── context_processors.py          # sidebar_devices — injects cached device list
    ├── urls.py                        # All app routes (pages + API partials)
    ├── views/                         # View modules (one per page + shared)
    │   ├── home.py                    # Home page, device listing, session df helpers
    │   ├── graphing.py                # Graphing Tool page
    │   ├── comfort.py                 # Tree Comfort Index page
    │   ├── prediction.py              # ML Prediction page
    │   ├── fourier.py                 # Fourier Analysis page
    │   ├── api_ajax.py                # All HTMX POST endpoints (data load, chart, predict, FFT, etc.)
    │   └── charting_utils.py          # matplotlib/seaborn plot creation + fig_to_b64()
    ├── helpers/                       # Data-fetching & processing (no Django imports)
    │   ├── cache_utils.py             # DataResult dataclass (core pattern)
    │   ├── config.py                  # Constants: COL_TIMESTAMP, COL_PLANT_NAME, TRENDLINE_STYLE
    │   ├── api_helpers.py             # ePlant API: auth, fetch devices, fetch data, CSV processing
    │   ├── weather_helpers.py         # Open-Meteo historical weather
    │   ├── lcra_helpers.py            # LCRA live weather (temp, humidity, rainfall CSVs)
    │   ├── kestrel_loader.py          # Kestrel CSV file parser
    │   ├── data_processing.py         # filter, aggregate, standardize DataFrames
    │   └── utils.py                   # get_base_col_name()
    ├── templates/dashboard/           # Django templates
    │   ├── base.html                  # Layout: sidebar, nav, CDN includes, CSRF via hx-headers
    │   ├── home.html, graphing.html, comfort.html, prediction.html, fourier.html
    ├── static/dashboard/
    │   ├── css/styles.css
    │   └── images/                    # Logos, plot maps
    └── templatetags/
        └── dashboard_tags.py          # get_item, startswith filters
```

## Entry Points & Core Files

- **Django entry:** `manage.py` → `clires_dashboard.wsgi.application`
- **Root URLconf:** `clires_dashboard/urls.py` — only includes `dashboard.urls`
- **App URLconf:** `dashboard/urls.py` — defines all 13 routes
- **Base template:** `dashboard/templates/dashboard/base.html` — entire layout, sidebar, CDN deps, CSRF via `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`

## URL Routes
| Pattern | View | Method | Purpose |
|---------|------|--------|---------|
| `/` | `home.home_view` | GET | Home (plots, device list) |
| `/graphing/` | `graphing.graphing_view` | GET | Graphing tool page |
| `/comfort/` | `comfort.comfort_view` | GET | Comfort Index page |
| `/prediction/` | `prediction.prediction_view` | GET | ML prediction page |
| `/fourier/` | `fourier.fourier_view` | GET | Fourier analysis page |
| `/api/chart/` | `api_ajax.generate_chart` | POST | Generate matplotlib chart |
| `/api/data/load/` | `api_ajax.load_api_data` | POST | Fetch ePlant API data |
| `/api/data/download/` | `api_ajax.download_data` | GET | Download as CSV/JSON |
| `/api/data/clear/` | `api_ajax.clear_data` | POST | Clear all session data |
| `/api/weather/fetch/` | `api_ajax.fetch_weather` | POST | Fetch historical weather |
| `/api/lcra/fetch/` | `api_ajax.fetch_lcra_live` | POST | Fetch live LCRA weather |
| `/api/prediction/run/` | `api_ajax.run_prediction` | POST | Run ML prediction |
| `/api/data/upload/` | `api_ajax.upload_kestrel` | POST | Upload Kestrel CSV files |
| `/api/data/historical/` | `api_ajax.extract_historical` | POST | Extract from large CSV |
| `/api/fourier/run/` | `api_ajax.run_fourier` | POST | Run FFT analysis |
| `/api/comfort/run/` | `api_ajax.compute_comfort` | POST | Compute comfort index |
| `/api/devices/list/` | `home.devices_list` | GET | HTMX device select partial |

## Commands

```bash
# Install dependencies (use venv at repo root)
cd clires_project && pip install -r requirements.txt

# Run development server
cd clires_project && python manage.py runserver
# Or from repo root:
cd clires_project && ../venv/bin/python manage.py runserver

# Django management
python manage.py migrate          # Apply migrations (sessions only)
python manage.py shell            # Django shell
python manage.py collectstatic    # Collect static files (for production)
```

**No tests exist.** No lint/format config.

## Core Patterns

### DataResult Pattern
Every helper function returns `DataResult(data, errors, warnings)` — never raises or calls st.error(). Check `.ok` before using `.data`.
- Defined in: `dashboard/helpers/cache_utils.py`

### Session DataFrame Caching
DataFrames stored in Redis (or LocMem fallback) keyed by `user:{session_key}:{key}`:
- `get_session_df(request, key)` / `set_session_df(request, key, df)` / `delete_session_df(request, key)`
- Defined in: `dashboard/views/home.py`
- DataFrame keys: `api_df`, `kestrel_df`, `lcra_df`, `history_df`, `hist_csv_df`, `combined_df`
- `merge_combine_data()` rebuilds `combined_df` from all source DFs (with merge_asof for weather)
- Session auto-created on first visit if no `session_key`
- Cache timeout: 86400s (24h)

### HTMX Partial Pattern
All `/api/*` endpoints return HTML fragments (not JSON). They return `<div class="alert ...">`, `<img src="data:image/png;base64,...">`, etc. directly.

### Charts
- matplotlib backend forced to `'Agg'` (no GUI) in settings.py and charting_utils.py
- `create_plot()` handles line/scatter/bar, single/faceted/overlaid, with optional trendlines
- `fig_to_b64(fig)` → `data:image/png;base64,...` string for `<img>` embedding
- Columns standardized: `data_processing.standardize_dataframe()` maps various column name variants

### Device List Loading
- Cached in Redis under `devices:shared:v1` (1h TTL for devices, 50min for auth token)
- `context_processors.py` pushes cached list to template; if cache miss, template uses HTMX lazy-load via `hx-get="/api/devices/list/" hx-trigger="load"`

## Environment Variables (.env)
| Variable | Purpose |
|----------|---------|
| `DEBUG` | Django debug mode (default: True) |
| `SECRET_KEY` | Django secret key |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts (default: `*`) |
| `REDIS_URL` | Redis URL (default: `redis://127.0.0.1:6379/1`) |
| `EPLANT_USERNAME` | ePlant API username |
| `EPLANT_PASSWORD` | ePlant API password |
| `EPLANT_CLIENT_ID` | ePlant Cognito client ID |

## Configuration

- **Settings:** `clires_dashboard/settings.py` — uses `python-decouple`; loads from `.env`
- **Excluded Django apps:** No admin, auth, or contenttypes in INSTALLED_APPS (only sessions, messages, staticfiles, dashboard)
- **Sessions:** Backed by Redis cache (`SESSION_ENGINE = 'django.contrib.sessions.backends.cache'`)
- **Redis fallback:** If Redis unavailable, falls back to LocMemCache
- **Upload limit:** 100MB (`DATA_UPLOAD_MAX_MEMORY_SIZE`)
- **ML model path:** `BASE_DIR / 'models'` — references `clires_project/models/` directory (ML `.pkl` files)

## Key Dependencies (requirements.txt)
`django>=4.2,<5.0`, `redis`, `hiredis`, `python-decouple`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `requests`, `scikit-learn`, `xgboost`, `scipy`, `joblib`, `tabulate`

## Common Pitfalls & Gotchas

1. **Redis required for multi-user:** Session data and device cache use Redis. Falls back to LocMemCache if Redis is down, but that's per-process and won't work with multiple workers.
2. **No database models:** `dashboard/` has zero Django models. `clires_project/models/` holds `.pkl` files (ML models). `db.sqlite3` only stores Django sessions.
3. **matplotlib backend:** Must be `Agg` before any pyplot import. Set in both `settings.py` (line 5) and `charting_utils.py`/`api_ajax.py`.
5. **Device name duplication:** Multiple devices can share a plant name. The API query groups by plant name, which merges data from multiple sensors.
6. **Large datasets:** API loads data in 30-day chunks with 0.1s sleeps. Count >10k rows triggers a performance warning.
7. **CSRF for HTMX:** Set via `hx-headers` attribute on `<body>` in base.html — required for all POST requests.
8. **Session keys:** Every view calls `request.session.save()` if no `session_key`. This is needed because no auth middleware is installed.

## How to Add a New Page

1. Create `dashboard/views/newpage.py` with a `newpage_view(request)` function
2. Create `dashboard/templates/dashboard/newpage.html` extending `base.html`
3. Add route in `dashboard/urls.py`
4. Add sidebar link in `base.html`
5. If needed, add API endpoints in `api_ajax.py` and register in `dashboard/urls.py`

## How to Add a New Data Source

1. Create `dashboard/helpers/new_source.py` with functions returning `DataResult`
2. Add loading endpoint in `api_ajax.py` (POST → fetch → `set_session_df` → `merge_combine_data`)
3. Register URL in `dashboard/urls.py` under `/api/`
4. Add sidebar form in `base.html` with HTMX attributes
5. Update `merge_combine_data()` in `home.py` if the source should be included in combined_df
6. Update `clear_data` in `api_ajax.py` to include the new session key
