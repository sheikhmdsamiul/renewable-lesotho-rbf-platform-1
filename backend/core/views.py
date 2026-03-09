from django.db import connections
from django.db.utils import OperationalError
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        }
    )
    def get(self, request):
        db_ok = True
        db_error = None
        try:
            connections['default'].cursor()
        except OperationalError as exc:
            db_ok = False
            db_error = str(exc)

        payload = {
            'status': 'ok' if db_ok else 'degraded',
            'timestamp': timezone.now().isoformat(),
            'checks': {
                'database': {
                    'ok': db_ok,
                    'error': db_error,
                }
            },
        }
        return Response(
            payload,
            status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
