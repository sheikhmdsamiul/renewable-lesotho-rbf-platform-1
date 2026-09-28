"""Server-side checks for user-uploaded documents: extension, size and file
signature (so a renamed executable cannot pass as a PDF)."""

from rest_framework import serializers

DOCUMENT_SIGNATURES = {
    'pdf': (b'%PDF-',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'docx': (b'PK\x03\x04',),
}
DEFAULT_MAX_UPLOAD_MB = 10


def max_upload_mb() -> int:
    from rbf.users.models import PlatformConfiguration

    config = PlatformConfiguration.objects.order_by('id').first()
    return int(getattr(config, 'max_file_size_mb', 0) or DEFAULT_MAX_UPLOAD_MB)


def validate_document_upload(upload, *, label='File', allowed=('pdf', 'jpg', 'jpeg', 'png')):
    """Raise serializers.ValidationError (a plain message) when `upload` is not an
    acceptable document. Returns the upload unchanged."""
    if upload is None:
        return upload
    name = str(getattr(upload, 'name', '') or '')
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if extension not in allowed:
        readable = ', '.join(sorted({ext.upper() for ext in allowed if ext != 'jpeg'}))
        raise serializers.ValidationError(f'{label} must be one of: {readable}.')

    limit_mb = max_upload_mb()
    size = int(getattr(upload, 'size', 0) or 0)
    if size <= 0:
        raise serializers.ValidationError(f'{label} is empty.')
    if size > limit_mb * 1024 * 1024:
        raise serializers.ValidationError(f'{label} is larger than the {limit_mb} MB limit.')

    signatures = DOCUMENT_SIGNATURES.get(extension)
    if signatures:
        position = upload.tell() if hasattr(upload, 'tell') else 0
        head = upload.read(16)
        upload.seek(position)
        if not any(head.startswith(signature) for signature in signatures):
            raise serializers.ValidationError(f'{label} does not look like a valid {extension.upper()} file.')
    return upload
