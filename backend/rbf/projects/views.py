from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.utils import timezone
import uuid
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    Project,
    Milestone,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    DisbursementStatus,
    AuditLog,
)
from .serializers import (
    ProjectSerializer,
    MilestoneSerializer,
    PaymentClaimSerializer,
    DisbursementSerializer,
    AuditLogSerializer,
)
from rbf.users.models import UserRole
from .audit import log_audit


def vendor_query_filter(user, prefix: str = ''):
    vendor_ids = {str(user.id)}
    if user.username:
        vendor_ids.add(user.username)
    vendor_names = {user.full_name, user.organization_name, user.username}
    vendor_names = {name for name in vendor_names if name}
    return Q(**{f'{prefix}vendor_id__in': vendor_ids}) | Q(**{f'{prefix}vendor_name__in': vendor_names})


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tech_type', 'region']
    search_fields = ['vendor_name', 'vendor_id']
    ordering_fields = ['progress', 'energy_output', 'uptime', 'gender_impact']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = Project.objects.all().order_by('id')
        user = self.request.user
        if user.role != UserRole.VENDOR:
            return qs
        return qs.filter(vendor_query_filter(user)).distinct()

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify projects.')

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


class MilestoneViewSet(viewsets.ModelViewSet):
    queryset = Milestone.objects.all().order_by('id')
    serializer_class = MilestoneSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'project']
    search_fields = ['name']
    ordering_fields = ['percentage', 'amount', 'created_at']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = Milestone.objects.select_related('project').all().order_by('id')
        user = self.request.user
        if user.role != UserRole.VENDOR:
            return qs
        return qs.filter(vendor_query_filter(user, prefix='project__')).distinct()

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify milestones.')

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


class PaymentClaimViewSet(viewsets.ModelViewSet):
    queryset = PaymentClaim.objects.select_related('project', 'vendor', 'milestone', 'reviewed_by').all()
    serializer_class = PaymentClaimSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'project', 'vendor']
    search_fields = ['payment_reference', 'implementation_notes', 'remarks']
    ordering_fields = ['submitted_at', 'claim_amount', 'approved_at', 'paid_at']

    WRITE_ROLES = {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER}
    VERIFY_ROLES = {UserRole.FIELD_VERIFIER, UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    APPROVE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = self.queryset.order_by('-submitted_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        return qs

    def _assert_write_permission(self):
        if self.request.user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify claims.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data.copy()
        if request.user.role == UserRole.VENDOR:
            data['vendor'] = request.user.id
            project_id = data.get('project')
            if not project_id:
                return Response({'detail': 'project is required.'}, status=status.HTTP_400_BAD_REQUEST)
            project = Project.objects.filter(id=project_id).first()
            if not project:
                return Response({'detail': 'project not found.'}, status=status.HTTP_400_BAD_REQUEST)
            if not Project.objects.filter(id=project.id).filter(vendor_query_filter(request.user)).exists():
                raise PermissionDenied('You can only submit claims for your own projects.')

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        claim = serializer.save()
        log_audit(request.user, 'payment_claim_submitted', claim, {'status': claim.status})
        return Response(self.get_serializer(claim).data, status=status.HTTP_201_CREATED)

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
        if request.user.role not in self.VERIFY_ROLES:
            raise PermissionDenied('You do not have permission to verify claims.')
        claim = self.get_object()
        if claim.status not in {PaymentClaimStatus.PENDING, PaymentClaimStatus.VERIFIED}:
            return Response({'detail': 'Only pending claims can be verified.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.VERIFIED
        claim.verified_at = timezone.now()
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'verified_at', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'payment_claim_verified', claim, {'status': claim.status})
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to approve claims.')
        claim = self.get_object()
        if claim.status not in {PaymentClaimStatus.VERIFIED, PaymentClaimStatus.PENDING}:
            return Response({'detail': 'Claim cannot be approved in its current status.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.APPROVED
        claim.approved_at = timezone.now()
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'approved_at', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'payment_claim_approved', claim, {'status': claim.status})
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to reject claims.')
        claim = self.get_object()
        if claim.status == PaymentClaimStatus.PAID:
            return Response({'detail': 'Paid claims cannot be rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.REJECTED
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'payment_claim_rejected', claim, {'status': claim.status})
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to process disbursements.')
        claim = self.get_object()
        if claim.status not in {PaymentClaimStatus.APPROVED, PaymentClaimStatus.PAID}:
            return Response({'detail': 'Claim must be approved before payment.'}, status=status.HTTP_400_BAD_REQUEST)

        reference = str(request.data.get('payment_reference') or f"PMT-{uuid.uuid4().hex[:10].upper()}")
        claim.status = PaymentClaimStatus.PAID
        claim.paid_at = timezone.now()
        claim.payment_reference = reference
        claim.reviewed_by = request.user
        claim.save(update_fields=['status', 'paid_at', 'payment_reference', 'reviewed_by'])

        disbursement, _ = Disbursement.objects.update_or_create(
            claim=claim,
            defaults={
                'amount': claim.claim_amount,
                'status': DisbursementStatus.COMPLETED,
                'reference': reference,
                'notes': request.data.get('notes', ''),
                'processed_by': request.user,
            },
        )

        log_audit(
            request.user,
            'payment_claim_paid',
            claim,
            {'status': claim.status, 'payment_reference': reference, 'disbursement_id': disbursement.id},
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)


class DisbursementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Disbursement.objects.select_related('claim', 'processed_by').all()
    serializer_class = DisbursementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'claim']
    search_fields = ['reference', 'notes']
    ordering_fields = ['processed_at', 'amount']

    def get_queryset(self):
        qs = self.queryset.order_by('-processed_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(claim__vendor=user)
        return qs


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('actor').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['action', 'entity_type']
    search_fields = ['action', 'entity_type', 'entity_id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        user = self.request.user
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR}:
            return self.queryset
        if user.role == UserRole.VENDOR:
            claim_ids = [str(cid) for cid in PaymentClaim.objects.filter(vendor=user).values_list('id', flat=True)]
            return self.queryset.filter(
                Q(entity_type='PaymentClaim', entity_id__in=claim_ids) |
                Q(actor=user)
            )
        return self.queryset.filter(actor=user)
