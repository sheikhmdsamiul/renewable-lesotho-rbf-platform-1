from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from .models import Tender, TenderStatus
from .serializers import TenderSerializer
from rbf.users.models import UserRole
from rbf.projects.audit import log_audit


class TenderViewSet(viewsets.ModelViewSet):
    queryset = Tender.objects.all().order_by('-created_at')
    serializer_class = TenderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'category', 'department', 'is_verified']
    search_fields = ['reference_number', 'name']
    ordering_fields = ['created_at', 'deadline']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = Tender.objects.all().order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.exclude(status=TenderStatus.DRAFT)
        return qs

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('Only RBF Official or Digital Admin can modify tenders.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        tender.is_verified = True
        tender.verified_at = timezone.now()
        tender.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
        log_audit(request.user, 'tender_verified', tender, {'reference_number': tender.reference_number})
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if not tender.is_verified:
            return Response({'detail': 'Tender must be verified before publishing.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.status == TenderStatus.CLOSED:
            return Response({'detail': 'Closed tender cannot be published.'}, status=status.HTTP_400_BAD_REQUEST)

        tender.status = TenderStatus.PUBLISHED
        tender.published_at = timezone.now()
        tender.save(update_fields=['status', 'published_at', 'updated_at'])
        log_audit(request.user, 'tender_published', tender, {'reference_number': tender.reference_number})
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status not in {TenderStatus.PUBLISHED, TenderStatus.EVALUATION}:
            return Response(
                {'detail': 'Tender can be awarded only from Published or Evaluation state.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        awarded_vendor_id = str(request.data.get('awarded_vendor_id') or '').strip()
        awarded_vendor_name = str(request.data.get('awarded_vendor_name') or '').strip()
        if not awarded_vendor_id and not awarded_vendor_name:
            return Response(
                {'detail': 'awarded_vendor_id or awarded_vendor_name is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tender.status = TenderStatus.AWARDED
        tender.awarded_vendor_id = awarded_vendor_id
        tender.awarded_vendor_name = awarded_vendor_name
        tender.awarded_at = timezone.now()
        tender.save(
            update_fields=[
                'status',
                'awarded_vendor_id',
                'awarded_vendor_name',
                'awarded_at',
                'updated_at',
            ]
        )
        log_audit(
            request.user,
            'tender_awarded',
            tender,
            {
                'reference_number': tender.reference_number,
                'awarded_vendor_id': awarded_vendor_id,
                'awarded_vendor_name': awarded_vendor_name,
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)
