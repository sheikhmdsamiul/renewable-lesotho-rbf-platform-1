from urllib.parse import urlsplit

from django.conf import settings


def _normalized_origin(candidate: str) -> str:
    value = str(candidate or '').strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')


def build_frontend_url(path: str = '/', request=None) -> str:
    normalized_path = '/' + str(path or '/').lstrip('/')
    base = ''

    if request is not None:
        base = (
            _normalized_origin(request.headers.get('Origin'))
            or _normalized_origin(request.headers.get('Referer'))
            or _normalized_origin(request.build_absolute_uri('/'))
        )

    if not base:
        base = _normalized_origin(getattr(settings, 'FRONTEND_URL', ''))

    return f'{base}{normalized_path}' if base else normalized_path
