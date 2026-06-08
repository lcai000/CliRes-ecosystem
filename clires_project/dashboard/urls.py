from django.urls import path
from dashboard.views import home, graphing, comfort, prediction, fourier, api_ajax

urlpatterns = [
    path('', home.home_view, name='home'),
    path('graphing/', graphing.graphing_view, name='graphing'),
    path('comfort/', comfort.comfort_view, name='comfort'),
    path('prediction/', prediction.prediction_view, name='prediction'),
    path('fourier/', fourier.fourier_view, name='fourier'),
    # HTMX partial endpoints
    path('api/chart/', api_ajax.generate_chart, name='api_chart'),
    path('api/data/load/', api_ajax.load_api_data, name='api_load_data'),
    path('api/data/download/', api_ajax.download_data, name='api_download_data'),
    path('api/data/clear/', api_ajax.clear_data, name='api_clear_data'),
    path('api/weather/fetch/', api_ajax.fetch_weather, name='api_weather_fetch'),
    path('api/lcra/fetch/', api_ajax.fetch_lcra_live, name='api_lcra_fetch'),
    path('api/prediction/run/', api_ajax.run_prediction, name='api_prediction_run'),
    path('api/data/upload/', api_ajax.upload_kestrel, name='api_upload_kestrel'),
    path('api/data/historical/', api_ajax.extract_historical, name='api_extract_historical'),
    path('api/fourier/run/', api_ajax.run_fourier, name='api_fourier_run'),
    path('api/comfort/run/', api_ajax.compute_comfort, name='api_comfort_run'),
    path('api/devices/list/', home.devices_list, name='api_devices_list'),
]
