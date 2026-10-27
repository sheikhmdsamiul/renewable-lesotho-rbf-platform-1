"""Signed, expiring download links for confidential procurement files.

Bid documents, bid custom documents, challenge evidence and contracts must never be
reachable from a guessable public /media URL (that would break sealed bidding). The
frontend authenticates with a bearer token, which a plain browser link can't carry, so
the API instead hands out short-lived signed URLs, issued only inside serializers that
already decide what the requesting user may see (e.g. sealed financial files are never
issued a link at all). The raw /media paths for these prefixes are refused outright.
"""
import mimetypes
import posixpath
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.urls import reverse
from django.views.static import serve

PROTECTED_MEDIA_PREFIXES = (
    'tender_bids/',
    'custom_documents/',
    'challenge_documents/',
    'tender_contracts/',
)
SIGNED_URL_MAX_AGE_SECONDS = 60 * 60
_SALT = 'rbf.tenders.protected-media'


def _storage_path(value) -> str | None:
    """A storage-relative path from a FieldFile, '/media/...' path or absolute URL."""
    if not value:
        return None
    name = getattr(value, 'name', None)
    if name:
        return str(name).lstrip('/')
    raw = urlparse(str(value)).path or ''
    media_url = (settings.MEDIA_URL or '/media/')
    if not media_url.startswith('/'):
        media_url = '/' + media_url
    if raw.startswith(media_url):
        return unquote(raw[len(media_url):])
    return None


def is_protected_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = posixpath.normpath(path).lstrip('/')
    return normalized.startswith(PROTECTED_MEDIA_PREFIXES)


def media_url_for(request, value) -> str | None:
    """The URL to hand a client for a stored file: a signed, expiring link when the
    file is confidential, otherwise the usual absolute /media URL."""
    if not value:
        return None
    path = _storage_path(value)
    if path and is_protected_path(path):
        user = getattr(request, 'user', None) if request is not None else None
        token = signing.dumps({'p': path, 'u': str(getattr(user, 'id', '') or '')}, salt=_SALT, compress=True)
        url = reverse('protected-media', args=[token])
        return request.build_absolute_uri(url) if request is not None else url
    url = getattr(value, 'url', None) or str(value)
    return request.build_absolute_uri(url) if request is not None else url


def protected_media_download(request, token):
    try:
        payload = signing.loads(token, salt=_SALT, max_age=SIGNED_URL_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        raise Http404('This download link has expired. Reload the page to get a fresh one.')
    except signing.BadSignature:
        raise Http404('Invalid download link.')
    path = posixpath.normpath(str(payload.get('p') or '')).lstrip('/')
    if not is_protected_path(path) or '..' in path.split('/') or not default_storage.exists(path):
        raise Http404('File not found.')
    content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    response = FileResponse(default_storage.open(path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{posixpath.basename(path)}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def public_media_serve(request, path, document_root=None):
    """Django's static media serving, minus the confidential prefixes."""
    if is_protected_path(path):
        raise Http404('File not found.')
    return serve(request, path, document_root=document_root or settings.MEDIA_ROOT)
