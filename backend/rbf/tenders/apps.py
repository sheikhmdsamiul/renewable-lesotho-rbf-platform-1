from django.apps import AppConfig


class TendersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rbf.tenders'

    def ready(self):
        from . import signals  # noqa: F401
