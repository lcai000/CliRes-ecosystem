from django.apps import AppConfig
import os
import joblib


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        """Load ML model and warm device cache at startup."""
        from django.conf import settings
        model_path = os.path.join(settings.MODELS_DIR, 'tree_growth_model.pkl')
        columns_path = os.path.join(settings.MODELS_DIR, 'model_columns.pkl')
        self.model = None
        self.model_columns = None
        try:
            self.model = joblib.load(model_path)
            self.model_columns = joblib.load(columns_path)
        except FileNotFoundError:
            pass

        # Warm the device list cache so first user doesn't wait
        try:
            from dashboard.views.home import _get_cached_devices
            _get_cached_devices()
        except Exception:
            pass
