from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rbf.users'

    def ready(self):
        # Import signals
        from . import signals  # noqa: F401
