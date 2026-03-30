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
    ProjectUpdate,
    ProjectDocument,
    InstallationReport,
    InstallationStatus,
    VerificationTask,
    VerificationStatus,
    SmartMeterReading,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    DisbursementStatus,
    AuditLog,
)
from .serializers import (
    ProjectSerializer,
    MilestoneSerializer,
    ProjectUpdateSerializer,
    ProjectDocumentSerializer,
    InstallationReportSerializer,
    VerificationTaskSerializer,
    SmartMeterReadingSerializer,
    PaymentClaimSerializer,
    DisbursementSerializer,
    AuditLogSerializer,
)
from rbf.users.models import UserRole
from rbf.users.models import User
from rbf.users.blacklisting import is_vendor_restricted
from .audit import log_audit
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus


def vendor_query_filter(user, prefix: str = ''):
    vendor_ids = {str(user.id)}
    if user.username:
        vendor_ids.add(user.username)
    vendor_names = {user.full_name, user.organization_name, user.username}
    vendor_names = {name for name in vendor_names if name}
    return Q(**{f'{prefix}vendor_id__in': vendor_ids}) | Q(**{f'{prefix}vendor_name__in': vendor_names})


def create_project_activity_update(project: Project, author, title: str, body: str):
    return ProjectUpdate.objects.create(
        project=project,
        author=author,
        title=title,
        body=body,
    )


def assert_user_not_blacklisted_for_writes(user: User, message: str):
    if is_vendor_restricted(user):
        raise PermissionDenied(message)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related('tender').prefetch_related('milestones').all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tech_type', 'region', 'district']
    search_fields = ['vendor_name', 'vendor_id']
    ordering_fields = ['progress', 'energy_output', 'uptime', 'gender_impact']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = Project.objects.select_related('tender').prefetch_related('milestones').all().order_by('id')
        user = self.request.user
        if user.role != UserRole.VENDOR:
            return qs
        return qs.filter(vendor_query_filter(user)).distinct()

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify projects.')
        if user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Project updates are restricted.')

    def _enforce_vendor_locked_fields(self, data):
        allowed = {
            'deployment_team_roster',
            'deployment_equipment_plan',
            'deployment_work_schedule',
        }
        attempted = {key for key in data.keys() if key not in allowed}
        if attempted:
            raise PermissionDenied('Only deployment planning fields can be updated by vendors.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        if request.user.role == UserRole.VENDOR:
            self._enforce_vendor_locked_fields(request.data)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        if request.user.role == UserRole.VENDOR:
            self._enforce_vendor_locked_fields(request.data)
        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = self.get_object()
        tracked_fields = {
            'deployment_team_roster': 'field team roster',
            'deployment_equipment_plan': 'equipment sourcing plan',
            'deployment_work_schedule': 'work schedule',
        }
        changed_labels = []
        for field_name, label in tracked_fields.items():
            if field_name in serializer.validated_data:
                previous = getattr(instance, field_name, '') or ''
                current = serializer.validated_data.get(field_name) or ''
                if previous != current:
                    changed_labels.append(label)

        project = serializer.save()
        if changed_labels:
            create_project_activity_update(
                project,
                self.request.user,
                'Deployment Plan Updated',
                f"Updated deployment planning details: {', '.join(changed_labels)}.",
            )

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
        if user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Milestone changes are restricted.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        milestone = serializer.save()
        create_project_activity_update(
            milestone.project,
            self.request.user,
            'Milestone Added',
            f"Added milestone '{milestone.name}' for project tracking.",
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        field_labels = {
            'name': 'name',
            'description': 'description',
            'target_date': 'target date',
            'completed_date': 'completed date',
            'progress_percentage': 'progress',
            'status': 'status',
        }
        changed_labels = []
        for field_name, label in field_labels.items():
            if field_name in serializer.validated_data:
                previous = getattr(instance, field_name, None)
                current = serializer.validated_data.get(field_name)
                if previous != current:
                    changed_labels.append(label)

        milestone = serializer.save()
        if changed_labels:
            create_project_activity_update(
                milestone.project,
                self.request.user,
                'Milestone Updated',
                f"Updated milestone '{milestone.name}': {', '.join(changed_labels)}.",
            )

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)


class ProjectUpdateViewSet(viewsets.ModelViewSet):
    queryset = ProjectUpdate.objects.select_related('project', 'author').all()
    serializer_class = ProjectUpdateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project']
    search_fields = ['title', 'body']
    ordering_fields = ['created_at']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = ProjectUpdate.objects.select_related('project', 'author').all()
        user = self.request.user
        if user.role != UserRole.VENDOR:
            return qs
        return qs.filter(vendor_query_filter(user, prefix='project__')).distinct()

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify project updates.')
        if user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Project updates are restricted.')

    def _assert_project_access(self, project_id: str):
        if not project_id:
            raise PermissionDenied('project is required.')
        if not Project.objects.filter(id=project_id).exists():
            raise PermissionDenied('project not found.')
        if self.request.user.role == UserRole.VENDOR:
            if not Project.objects.filter(id=project_id).filter(vendor_query_filter(self.request.user)).exists():
                raise PermissionDenied('You can only update your own projects.')

    def perform_create(self, serializer):
        self._assert_write_permission()
        project_id = str(serializer.validated_data.get('project').id) if serializer.validated_data.get('project') else ''
        self._assert_project_access(project_id)
        update = serializer.save(author=self.request.user)
        log_audit(self.request.user, 'project_update_added', update, {'project_id': project_id})

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)


class ProjectDocumentViewSet(viewsets.ModelViewSet):
    queryset = ProjectDocument.objects.select_related('project', 'uploaded_by').all()
    serializer_class = ProjectDocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project']
    search_fields = ['title']
    ordering_fields = ['uploaded_at']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = ProjectDocument.objects.select_related('project', 'uploaded_by').all()
        user = self.request.user
        if user.role != UserRole.VENDOR:
            return qs
        return qs.filter(vendor_query_filter(user, prefix='project__')).distinct()

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify project documents.')
        if user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Project documents are restricted.')

    def _assert_project_access(self, project_id: str):
        if not project_id:
            raise PermissionDenied('project is required.')
        if not Project.objects.filter(id=project_id).exists():
            raise PermissionDenied('project not found.')
        if self.request.user.role == UserRole.VENDOR:
            if not Project.objects.filter(id=project_id).filter(vendor_query_filter(self.request.user)).exists():
                raise PermissionDenied('You can only update your own projects.')

    def perform_create(self, serializer):
        self._assert_write_permission()
        project_id = str(serializer.validated_data.get('project').id) if serializer.validated_data.get('project') else ''
        self._assert_project_access(project_id)
        document = serializer.save(uploaded_by=self.request.user)
        log_audit(self.request.user, 'project_document_uploaded', document, {'project_id': project_id})
        create_project_activity_update(
            document.project,
            self.request.user,
            'Document Uploaded',
            f"Uploaded project document '{document.title or document.file.name.split('/')[-1]}'.",
        )

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
        if self.request.user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(
                self.request.user,
                'Your vendor account is suspended or blacklisted. Payment claims are on hold for audit.',
            )

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
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Claim Submitted',
            f"Submitted a payment claim for M {claim.claim_amount} with status {claim.status}.",
        )
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
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. Claim remains on Held/Audit.'}, status=status.HTTP_400_BAD_REQUEST)
        if claim.status not in {PaymentClaimStatus.PENDING, PaymentClaimStatus.VERIFIED}:
            return Response({'detail': 'Only pending claims can be verified.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.VERIFIED
        claim.verified_at = timezone.now()
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'verified_at', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'payment_claim_verified', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Claim Verified',
            f"Payment claim {claim.id} was verified.",
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to approve claims.')
        claim = self.get_object()
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. Claim remains on Held/Audit.'}, status=status.HTTP_400_BAD_REQUEST)
        if claim.status not in {PaymentClaimStatus.VERIFIED, PaymentClaimStatus.PENDING}:
            return Response({'detail': 'Claim cannot be approved in its current status.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.APPROVED
        claim.approved_at = timezone.now()
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'approved_at', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'payment_claim_approved', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Claim Approved',
            f"Payment claim {claim.id} was approved.",
        )
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
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Claim Rejected',
            f"Payment claim {claim.id} was rejected.",
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to process disbursements.')
        claim = self.get_object()
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. New disbursements are frozen.'}, status=status.HTTP_400_BAD_REQUEST)
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
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Disbursed',
            f"Payment claim {claim.id} was paid with reference {reference}.",
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


class InstallationReportViewSet(viewsets.ModelViewSet):
    queryset = InstallationReport.objects.select_related('project', 'vendor', 'milestone').all()
    serializer_class = InstallationReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'status', 'vendor']
    search_fields = ['serial_number', 'beneficiary_id', 'meter_id']
    ordering_fields = ['submitted_at']

    WRITE_ROLES = {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER}

    def get_queryset(self):
        qs = self.queryset.order_by('-submitted_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(verification_task__assigned_verifier=user)
        return qs

    def _assert_write_permission(self):
        if self.request.user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to submit installation reports.')
        if self.request.user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(
                self.request.user,
                'Your vendor account is suspended or blacklisted. Installation reporting is restricted.',
            )

    def _assert_project_access(self, project_id: str):
        if not project_id:
            raise PermissionDenied('project is required.')
        if not Project.objects.filter(id=project_id).exists():
            raise PermissionDenied('project not found.')
        if self.request.user.role == UserRole.VENDOR:
            if not Project.objects.filter(id=project_id).filter(vendor_query_filter(self.request.user)).exists():
                raise PermissionDenied('You can only report installations for your own projects.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data.copy()
        project_id = str(data.get('project') or '')
        self._assert_project_access(project_id)

        if request.user.role == UserRole.VENDOR:
            data['vendor'] = request.user.id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        if request.user.role == UserRole.VENDOR:
            report = serializer.save(vendor=request.user)
        else:
            report = serializer.save()

        photo_paths: list[str] = []
        files = request.FILES.getlist('photos')
        if files:
            from django.core.files.storage import default_storage
            for file in files:
                saved = default_storage.save(f'installation_photos/{file.name}', file)
                photo_paths.append(saved)
        if photo_paths:
            report.photo_files = photo_paths
            report.save(update_fields=['photo_files'])

        assigned_verifier = User.objects.filter(
            role=UserRole.FIELD_VERIFIER,
            verification_zone__iexact=report.project.district,
        ).first()

        task = VerificationTask.objects.create(
            report=report,
            assigned_verifier=assigned_verifier,
            vendor_lat=report.gps_lat,
            vendor_lng=report.gps_lng,
            status=VerificationStatus.PENDING,
        )
        log_audit(request.user, 'installation_report_submitted', report, {'verification_task': str(task.id)})
        create_project_activity_update(
            report.project,
            request.user,
            'Installation Report Submitted',
            f"Submitted installation report for serial number {report.serial_number}.",
        )
        if assigned_verifier:
            Notification.objects.create(
                recipient_id=str(assigned_verifier.id),
                recipient_name=assigned_verifier.full_name or assigned_verifier.username,
                type=NotificationChannel.IN_APP,
                event='verification_task_created',
                title='New Verification Task',
                body=f'Installation report {report.id} requires field verification.',
                linked_entity_id=str(report.project_id),
            )
        return Response(self.get_serializer(report).data, status=status.HTTP_201_CREATED)


class VerificationTaskViewSet(viewsets.ModelViewSet):
    queryset = VerificationTask.objects.select_related('report', 'assigned_verifier').all()
    serializer_class = VerificationTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'assigned_verifier', 'report__project']
    search_fields = ['report__serial_number', 'report__beneficiary_id']
    ordering_fields = ['created_at']

    VERIFY_ROLES = {UserRole.FIELD_VERIFIER, UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = self.queryset.order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(assigned_verifier=user)
        if user.role == UserRole.VENDOR:
            return qs.filter(report__vendor=user)
        return qs

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        if request.user.role not in self.VERIFY_ROLES:
            raise PermissionDenied('You do not have permission to verify installations.')
        task = self.get_object()
        lat = request.data.get('verifier_lat')
        lng = request.data.get('verifier_lng')
        try:
            verifier_lat = float(lat)
            verifier_lng = float(lng)
        except (TypeError, ValueError):
            return Response({'detail': 'verifier_lat and verifier_lng are required.'}, status=status.HTTP_400_BAD_REQUEST)

        import math
        def haversine(lat1, lon1, lat2, lon2):
            r = 6371000
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = haversine(float(task.vendor_lat), float(task.vendor_lng), verifier_lat, verifier_lng)
        anomaly = distance > 100

        task.verifier_lat = verifier_lat
        task.verifier_lng = verifier_lng
        task.distance_meters = distance
        task.anomaly_flag = anomaly
        task.status = VerificationStatus.FLAGGED if anomaly else VerificationStatus.VERIFIED
        task.save(update_fields=['verifier_lat', 'verifier_lng', 'distance_meters', 'anomaly_flag', 'status', 'updated_at'])

        report = task.report
        report.status = InstallationStatus.FLAGGED if anomaly else InstallationStatus.VERIFIED
        report.save(update_fields=['status'])
        log_audit(request.user, 'installation_verified', report, {'distance_meters': distance, 'anomaly': anomaly})
        create_project_activity_update(
            report.project,
            request.user,
            'Installation Verification Completed',
            f"Installation report {report.id} was {'flagged' if anomaly else 'verified'} after field verification.",
        )
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)


class SmartMeterReadingViewSet(viewsets.ModelViewSet):
    queryset = SmartMeterReading.objects.select_related('project').all()
    serializer_class = SmartMeterReadingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'meter_id']
    search_fields = ['meter_id']
    ordering_fields = ['recorded_at']

    WRITE_ROLES = {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER}

    def get_queryset(self):
        qs = self.queryset.order_by('-recorded_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(project__vendor_id=str(user.id))
        return qs

    def _assert_write_permission(self):
        if self.request.user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to submit smart meter readings.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)


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
