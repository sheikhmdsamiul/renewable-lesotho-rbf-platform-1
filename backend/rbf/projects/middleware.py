from __future__ import annotations

from threading import local


_request_state = local()


def get_current_request():
    return getattr(_request_state, 'request', None)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _request_state.request = request
        try:
            return self.get_response(request)
        finally:
            _request_state.request = None
