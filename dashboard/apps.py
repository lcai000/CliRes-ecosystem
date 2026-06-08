from django.apps import AppConfig
import os
import joblib


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        """Load ML model at startup."""
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
