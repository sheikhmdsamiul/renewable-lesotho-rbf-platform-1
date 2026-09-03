from django.conf import settings
from django.core.cache import cache

_UNSET = object()


class EmailConfigMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._last_version = _UNSET

    def __call__(self, request):
        version = cache.get('email_config_version', 0)
        if version != self._last_version:
            self._sync_email_config()
            self._last_version = version
        return self.get_response(request)

    @staticmethod
    def _sync_email_config():
        try:
            from .models import PlatformConfiguration
            config = PlatformConfiguration.objects.order_by('id').first()
            if config and config.email_host:
                settings.EMAIL_HOST = config.email_host
                settings.EMAIL_PORT = config.email_port
                settings.EMAIL_USE_TLS = config.email_use_tls
                settings.EMAIL_HOST_USER = config.email_host_user
                if config.email_host_password:
                    settings.EMAIL_HOST_PASSWORD = config.email_host_password
                settings.DEFAULT_FROM_EMAIL = config.default_from_email or settings.DEFAULT_FROM_EMAIL
        except Exception:
            pass
