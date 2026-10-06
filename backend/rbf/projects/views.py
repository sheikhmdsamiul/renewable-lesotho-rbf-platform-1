from datetime import date, timedelta, timezone as dt_timezone
from pathlib import Path
import re
import tempfile
import html
import logging
import os

from rest_framework import viewsets, filters, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q, F, Value, OuterRef, Subquery, Count, Avg, CharField, Case, When, Sum
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
import csv
import io
import uuid
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    ReportSchedule,
    ResultsIndicator,
    ResultsMeasure,
    AuditCase,
    AuditCaseStatus,
    AuditCaseType,
    AuditEvidence,
    AuditEvidenceKind,
    AuditFindingType,
    AuditRiskLevel,
    CorrectiveActionStatus,
    OversightFollowUpStatus,
    OversightReview,
    OversightReviewStatus,
    OversightSubject,
    KpiReview,
    KpiReviewRating,
    SiteMonitoringPhoto,
    SiteMonitoringVisit,
    SiteVisitFollowUpStatus,
    Project,
    ProjectSetup,
    ProjectSetupReviewStatus,
    ProjectStatus,
    ProspectSyncStatus,
    Milestone,
    MilestoneReviewDecision,
    MilestoneReviewStatus,
    ProjectUpdate,
    ProjectDocument,
    InstallationReport,
    InstallationStatus,
    BeneficiaryGender,
    FieldVerification,
    FieldVerificationStatus,
    VerificationTask,
    VerificationStatus,
    MeterDataBatch,
    MeterDataBatchStatus,
    SmartMeterReading,
    SmartMeterReadingReviewStatus,
    SmartMeterReadingSource,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    DisbursementStatus,
    AuditLog,
    ProspectSyncLog,
    AnomalyFlag,
    AnomalyFlagStatus,
    AnomalyReviewEvent,
    AnomalyEvidenceFile,
    GisStatus,
    GeneratedReport,
)
from .serializers import (
    ResultsIndicatorSerializer,
    AuditCaseSerializer,
    AuditEvidenceSerializer,
    OversightReviewSerializer,
    KpiReviewSerializer,
    SiteMonitoringVisitSerializer,
    ProjectSerializer,
    ProjectSetupSerializer,
    MilestoneSerializer,
    MilestoneReviewDecisionSerializer,
    ProjectUpdateSerializer,
    ProjectDocumentSerializer,
    InstallationReportSerializer,
    FieldVerificationSerializer,
    VerificationTaskSerializer,
    SmartMeterReadingSerializer,
    MeterDataBatchSerializer,
    MeterDataBatchDetailSerializer,
    PaymentClaimSerializer,
    DisbursementSerializer,
    AuditLogSerializer,
    ProspectSyncLogSerializer,
    AnomalyFlagSerializer,
)
from rbf.users.models import User, UserRole, PlatformConfiguration
from rbf.users.blacklisting import is_vendor_restricted
from rbf.common.uploads import validate_document_upload
from .audit import log_audit, AuditLogger
from .archive import archive_project, archived_scope, restore_project
from . import claim_status
from .bank_details import get_vendor_bank_snapshot
from .integrations import (
    month_start,
    previous_month_period,
    previous_quarter_period,
    queue_periodic_project_reports,
    queue_installation_sync,
    queue_project_agent_sync,
    queue_project_report_sync,
    queue_project_targets_sync,
    queue_project_timeseries_sync,
    SyncToProspectJob,
)
from .gis import GpsValidator
from .district_scope import (
    doe_districts,
    doe_region_filter,
    vendor_query_filter,
    field_verifier_district_filter,
    field_verifier_districts,
    field_verifier_installation_filter,
    field_verifier_task_scope_filter,
    resolve_installation_district,
)
from .kpi import KpiService, invalidate_kpi_cache, render_kpi_pdf
from .meter_integrity import (
    initial_batch_status,
    parse_meter_timestamp,
    parse_meter_timestamp_error,
    run_integrity_checks,
)
from .milestone_reviews import is_last_milestone, next_milestone_blocker, open_completion_review
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.notifications.services import NotificationService
from rbf.tenders.models import ContractStatus, TenderContract

logger = logging.getLogger(__name__)

# Per-row rejection reasons are returned to the uploader and persisted on the batch so
# they survive a reload. Capped so a wholly malformed file cannot bloat the batch row,
# the audit log, or the response payload.
REJECTED_ROWS_STORED = 100


def _build_disbursement_sheet_payload(claim: PaymentClaim) -> dict:
    bank_snapshot = get_vendor_bank_snapshot(claim.vendor)
    return {
        'claim_id': str(claim.id),
        'project_id': str(claim.project_id),
        'vendor_legal_name': claim.vendor.organization_name or claim.vendor.full_name or claim.vendor.username,
        'vendor_bank_name': bank_snapshot['bank_name'],
        'vendor_bank_branch': bank_snapshot['bank_branch'],
        'vendor_bank_swift_code': bank_snapshot['bank_swift_code'],
        'vendor_bank_sort_code': bank_snapshot['bank_sort_code'],
        'vendor_account_holder_name': bank_snapshot['bank_account_name'],
        'vendor_account_number': bank_snapshot['bank_account_number'],
        'total_approved_amount': str(claim.claim_amount),
        'claim_status': claim.status,
    }


def _assert_national_budget_available(claim: PaymentClaim):
    config = PlatformConfiguration.objects.order_by('id').first()
    configured_budget = float(getattr(config, 'national_main_program_budget', 0) or 0)
    if configured_budget <= 0:
        return
    already_paid = (
        PaymentClaim.objects.filter(status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID})
        .exclude(id=claim.id)
        .aggregate(total=Sum('claim_amount'))
        .get('total')
        or 0
    )
    remaining = configured_budget - float(already_paid)
    claim_amount = float(claim.claim_amount or 0)
    if claim_amount > remaining:
        raise ValueError(
            f'Insufficient National/Main Program Budget. Remaining balance is {remaining:.2f}, '
            f'but this claim requires {claim_amount:.2f}.'
        )


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


def notify_project_oversight(project: Project, title: str, body: str, linked_entity_id: str = ''):
    recipients = User.objects.filter(
        role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR}
    ).only('id', 'full_name', 'username')
    notifications = [
        Notification(
            recipient_id=str(user.id),
            recipient_name=user.full_name or user.username,
            type=NotificationChannel.IN_APP,
            event='project_oversight_flag',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=linked_entity_id or str(project.id),
        )
        for user in recipients
    ]
    if notifications:
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)


def refresh_project_kpis(project_id: str):
    invalidate_kpi_cache(project_id)
    KpiService.for_project(project_id).getFullKpiSummary()


def notify_vendor_and_oversight(project: Project, *, vendor, event: str, title: str, body: str, linked_entity_id: str):
    notifications = [
        Notification(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=linked_entity_id,
        )
    ]
    oversight_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
    notifications.extend(
        Notification(
            recipient_id=str(user.id),
            recipient_name=user.full_name or user.username,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=linked_entity_id,
        )
        for user in oversight_users
    )
    Notification.objects.bulk_create(notifications, ignore_conflicts=True)


def create_or_refresh_anomaly(*, installation: InstallationReport, project: Project, flag_type: str, description: str):
    flag, created = AnomalyFlag.objects.get_or_create(
        installation=installation,
        project=project,
        flag_type=flag_type,
        is_resolved=False,
        defaults={'description': description},
    )
    if not created and flag.description != description:
        flag.description = description
        flag.save(update_fields=['description'])
    return flag


def mark_project_completed(project: Project, actor):
    if project.status == ProjectStatus.COMPLETED:
        if not project.archived_at:
            archive_project(project, actor)
        return True

    project.status = ProjectStatus.COMPLETED
    project.save(update_fields=['status', 'updated_at'])
    create_project_activity_update(
        project,
        actor,
        'Project Completed',
        'The final milestone was paid and verified. The project is now marked completed.',
    )
    log_audit(
        actor,
        'project_completed',
        project,
        {'project_id': str(project.id), 'status': ProjectStatus.COMPLETED},
    )
    vendor = User.objects.filter(id=project.vendor_id).first() or User.objects.filter(username=project.vendor_id).first()
    if vendor:
        notify_vendor_and_oversight(
            project,
            vendor=vendor,
            event='project_completed',
            title='Project Completed',
            body=f'Project {project.project_reference or project.id} has been marked completed.',
            linked_entity_id=str(project.id),
        )
    # Completion archives the project with its whole lifecycle (tender to contract closure).
    archive_project(project, actor)
    return True


class ArchiveScopedListMixin:
    """List endpoints leave out archived projects' records unless asked (see archive.archived_scope)."""

    archive_prefix = 'project__'
    archive_scope_params: tuple = ('project',)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if getattr(self, 'action', None) == 'list':
            queryset = archived_scope(self.request, queryset, self.archive_prefix, self.archive_scope_params)
        return queryset


def build_installation_map_queryset(user: User):
    latest_reading_subquery = SmartMeterReading.objects.filter(
        installation=OuterRef('pk')
    ).exclude(review_status=SmartMeterReadingReviewStatus.REJECTED).order_by('-recorded_at')

    queryset = InstallationReport.objects.select_related('project', 'vendor', 'verification_task').annotate(
        verification_status=Coalesce(F('verification_task__status'), Value(VerificationStatus.PENDING)),
        technology_type=F('project__tech_type'),
        # The installation's own district first: a lot-wise project spans several districts.
        district_name=Coalesce(
            NullIf(F('district'), Value('')),
            NullIf(F('project__district'), Value('')),
            F('project__region'),
            Value(''),
        ),
        vendor_name=Coalesce(
            F('project__vendor_name'),
            Case(
                When(~Q(vendor__organization_name=''), then=F('vendor__organization_name')),
                When(~Q(vendor__full_name=''), then=F('vendor__full_name')),
                default=Coalesce(F('vendor__username'), Value('')),
                output_field=CharField(),
            ),
            Value(''),
            output_field=CharField(),
        ),
        uptime_pct=Subquery(latest_reading_subquery.values('uptime_pct')[:1]),
    )

    if user.role == UserRole.VENDOR:
        queryset = queryset.filter(vendor=user)
    elif user.role == UserRole.FIELD_VERIFIER:
        queryset = queryset.filter(field_verifier_installation_filter(user))
    elif user.role == UserRole.DOE_OFFICER:
        queryset = queryset.filter(doe_region_filter(user, prefix='project__'))

    return queryset


def apply_installation_map_filters(queryset, params):
    project_id = str(params.get('project_id') or '').strip()
    vendor_id = str(params.get('vendor_id') or '').strip()
    status_value = str(params.get('status') or '').strip()
    technology = str(params.get('technology') or '').strip()
    district = str(params.get('district') or '').strip()
    household_type = str(params.get('household_type') or '').strip()
    date_from = str(params.get('date_from') or '').strip()
    date_to = str(params.get('date_to') or '').strip()

    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)
    if status_value:
        queryset = queryset.filter(verification_status__iexact=status_value)
    if technology:
        queryset = queryset.filter(project__tech_type__iexact=technology)
    if district:
        queryset = queryset.filter(district_name__iexact=district)
    if household_type:
        queryset = queryset.filter(household_type__iexact=household_type)
    if date_from:
        queryset = queryset.filter(installation_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(installation_date__lte=date_to)
    return queryset


class ProjectViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    archive_prefix = ''
    archive_scope_params = ()
    queryset = Project.objects.select_related('tender', 'project_setup').prefetch_related('milestones').all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tech_type', 'region', 'district']
    search_fields = ['vendor_name', 'vendor_id']
    ordering_fields = ['progress', 'energy_output', 'uptime', 'gender_impact']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC, UserRole.VENDOR}

    def get_queryset(self):
        qs = Project.objects.select_related('tender', 'project_setup').prefetch_related('milestones').all().order_by('id')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor_query_filter(user)).distinct()
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user)).distinct()
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(field_verifier_district_filter(user, project_prefix='')).distinct()
        return qs

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify projects.')
        if user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Project updates are restricted.')

    def _enforce_vendor_locked_fields(self, data):
        raise PermissionDenied('Use the project setup workflow to update vendor setup details.')

    def _assert_vendor_setup_access(self, project: Project):
        user = self.request.user
        if user.role != UserRole.VENDOR:
            raise PermissionDenied('Only vendors can manage project setup.')
        assert_user_not_blacklisted_for_writes(
            user,
            'Your vendor account is suspended or blacklisted. Project setup is restricted.',
        )
        if not Project.objects.filter(id=project.id).filter(vendor_query_filter(user)).exists():
            raise PermissionDenied('You can only manage setup for your own projects.')

    def _assert_rmt_setup_access(self):
        user = self.request.user
        if user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can review project setup.')

    def _setup_instance_for_project(self, project: Project) -> ProjectSetup:
        user = self.request.user
        defaults = {'vendor': user}
        return ProjectSetup.objects.get_or_create(project=project, defaults=defaults)[0]

    def _notify_rmt_setup_completed(self, project: Project):
        recipients = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        notifications = [
            Notification(
                recipient_id=str(user.id),
                recipient_name=user.full_name or user.username,
                type=NotificationChannel.IN_APP,
                event='project_setup_completed',
                title='Vendor Project Setup Completed',
                body=f'Vendor {project.vendor_name} completed setup for Project #{project.id}.',
                status=NotificationStatus.SENT,
                linked_entity_id=str(project.id),
            )
            for user in recipients
        ]
        if notifications:
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)

    def _notify_setup_submitted_for_review(self, project: Project):
        recipients = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        notifications = [
            Notification(
                recipient_id=str(user.id),
                recipient_name=user.full_name or user.username,
                type=NotificationChannel.IN_APP,
                event='project_setup_submitted',
                title='Project Setup Awaiting Review',
                body=f'Vendor {project.vendor_name} submitted project setup for review on Project #{project.id}.',
                status=NotificationStatus.SENT,
                linked_entity_id=str(project.id),
            )
            for user in recipients
        ]
        if notifications:
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)

    def _notify_vendor_of_setup_decision(self, project: Project, *, event: str, title: str, body: str):
        vendor_id = str(getattr(project, 'vendor_id', '') or '')
        if not vendor_id:
            return
        try:
            vendor = User.objects.only('id', 'full_name', 'username').get(id=vendor_id)
        except User.DoesNotExist:
            return
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(project.id),
        )

    def _save_project_setup(self, request, project: Project, *, submit: bool):
        self._assert_vendor_setup_access(project)
        instance = getattr(project, 'project_setup', None) or self._setup_instance_for_project(project)
        serializer = ProjectSetupSerializer(
            instance,
            data=request.data,
            partial=not submit,
            context={'request': request, 'project': project, 'submit': submit},
        )
        serializer.is_valid(raise_exception=True)
        setup = serializer.save(project=project, vendor=request.user)

        if submit:
            contract_is_approved = TenderContract.objects.filter(
                project_id=str(project.id),
                status=ContractStatus.APPROVED,
            ).exists()
            if not contract_is_approved:
                raise PermissionDenied('Project setup can only be submitted after the contract is approved.')
            submission_time = timezone.now()
            setup.previous_review_notes = setup.review_notes
            setup.review_notes = ''
            setup.review_status = ProjectSetupReviewStatus.SUBMITTED
            setup.submitted_at = submission_time
            setup.reviewed_by = None
            setup.reviewed_at = None
            setup.setup_completed_at = None
            setup.save(
                update_fields=[
                    'review_status',
                    'submitted_at',
                    'reviewed_by',
                    'reviewed_at',
                    'review_notes',
                    'previous_review_notes',
                    'setup_completed_at',
                    'updated_at',
                ]
            )

            project.status = ProjectStatus.SETUP_UNDER_REVIEW
            project.setup_completed_at = None
            project.device_brand = setup.device_brand or project.device_brand
            project.device_model = setup.device_model or project.device_model
            project.device_tech_tier = str(setup.tech_tier or project.device_tech_tier or '')
            project.verification_method_confirmed = setup.manual_verification_confirmed or project.verification_method.lower() == 'iot'
            project.save(
                update_fields=[
                    'status',
                    'setup_completed_at',
                    'device_brand',
                    'device_model',
                    'device_tech_tier',
                    'verification_method_confirmed',
                ]
            )
            queue_project_agent_sync(str(project.id))
            refresh_project_kpis(str(project.id))
            create_project_activity_update(
                project,
                request.user,
                'Project Setup Submitted for Review',
                'Submitted project setup. Awaiting RMT review and approval.',
            )
            log_audit(
                request.user,
                'project_setup_submitted',
                setup,
                {'project_id': str(project.id), 'actor_id': str(request.user.id), 'timestamp': submission_time.isoformat()},
            )
            self._notify_setup_submitted_for_review(project)
        else:
            setup.review_status = ProjectSetupReviewStatus.DRAFT
            setup.save(update_fields=['review_status', 'updated_at'])
            create_project_activity_update(
                project,
                request.user,
                'Project Setup Draft Saved',
                'Saved draft changes in the project setup workspace.',
            )

        project.refresh_from_db()
        return Response(ProjectSerializer(project, context={'request': request}).data, status=status.HTTP_200_OK)

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

    def perform_create(self, serializer):
        project = serializer.save()
        queue_project_targets_sync(str(project.id))

    @action(detail=True, methods=['post'], url_path='prospect-sync')
    def prospect_sync(self, request, pk=None):
        project = self.get_object()
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only RMT and Platform Administrators can trigger Prospect sync actions.')

        action_name = str(request.data.get('action') or 'sync_all_available').strip().lower()
        queued_methods: list[str] = []
        details: dict[str, int | str] = {}

        if action_name in {'push_target', 'sync_all_available'}:
            queue_project_targets_sync(str(project.id))
            queued_methods.append('pushTarget')

        if action_name in {'push_agent', 'sync_all_available'}:
            if getattr(project, 'project_setup', None) or project.setup_completed_at:
                queue_project_agent_sync(str(project.id))
                queued_methods.append('pushAgent')

        if action_name in {'push_installations', 'sync_all_available'}:
            reports = list(InstallationReport.objects.filter(project=project).only('id'))
            for report in reports:
                queue_installation_sync(str(report.id), include_customer=True, include_installation=True)
            if reports:
                queued_methods.extend(['pushCustomer', 'pushInstallation'])
                details['installation_records'] = len(reports)

        if action_name == 'push_installation_updates':
            reports = list(InstallationReport.objects.filter(project=project).only('id'))
            for report in reports:
                queue_installation_sync(str(report.id), include_customer=False, include_installation=True)
            if reports:
                queued_methods.append('pushInstallation')
                details['installation_records'] = len(reports)

        if action_name in {'push_installation_timeseries', 'sync_all_available'}:
            count = queue_project_timeseries_sync(str(project.id))
            if count:
                queued_methods.append('pushInstallationTimeSeries')
                details['timeseries_rows'] = count

        if action_name in {'push_report', 'sync_all_available'}:
            # Manual push: current month-to-date refresh for this specific project.
            queue_project_report_sync(
                str(project.id),
                report_start=month_start(timezone.localdate()),
                report_end=timezone.localdate(),
                period_type='monthly',
            )
            queued_methods.append('pushReport')

        if action_name in {'refresh_status', 'sync_all_available'}:
            filters_payload = {'reporting_phase': f'PRJ-{project.id}'}
            SyncToProspectJob.dispatch_async('getInstallations', filters_payload, record_id=project.id, record_type='sync_panel')
            SyncToProspectJob.dispatch_async('getTargets', filters_payload, record_id=project.id, record_type='sync_panel')
            queued_methods.extend(['getInstallations', 'getTargets'])

        if not queued_methods:
            return Response({'detail': 'No Prospect sync action was queued for this project.'}, status=status.HTTP_400_BAD_REQUEST)

        log_audit(
            request.user,
            'prospect_sync_manual_triggered',
            project,
            {
                'project_id': str(project.id),
                'action': action_name,
                'queued_methods': queued_methods,
                **details,
            },
        )
        return Response(
            {
                'status': 'queued',
                'action': action_name,
                'queued_methods': queued_methods,
                'details': details,
                'message': f'Prospect sync queued for Project {project.project_reference or project.id}.',
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=['post'], url_path='prospect-sync-reports')
    def prospect_sync_reports(self, request):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only RMT and Platform Administrators can trigger Prospect report sync.')

        period = str(request.data.get('period') or 'monthly').strip().lower()
        mode = str(request.data.get('mode') or 'all').strip().lower()
        if period not in {'monthly', 'quarterly'}:
            return Response({'detail': 'Invalid period. Use monthly or quarterly.'}, status=status.HTTP_400_BAD_REQUEST)
        if mode not in {'all', 'project'}:
            return Response({'detail': 'Invalid mode. Use all or project.'}, status=status.HTTP_400_BAD_REQUEST)

        if period == 'monthly':
            report_start, report_end = previous_month_period(timezone.localdate())
        else:
            report_start, report_end = previous_quarter_period(timezone.localdate())

        queued = 0
        project_id = str(request.data.get('project_id') or '').strip()
        if mode == 'project':
            if not project_id:
                return Response({'detail': 'project_id is required when mode=project.'}, status=status.HTTP_400_BAD_REQUEST)
            queued = int(
                queue_project_report_sync(
                    project_id,
                    report_start=report_start,
                    report_end=report_end,
                    period_type=period,
                )
            )
        else:
            queued = queue_periodic_project_reports(
                period_type=period,
                report_start=report_start,
                report_end=report_end,
            )

        log_audit(
            request.user,
            'prospect_report_manual_triggered',
            request.user,
            {
                'module': 'prospect_sync',
                'period': period,
                'mode': mode,
                'project_id': project_id or None,
                'report_start': report_start.isoformat(),
                'report_end': report_end.isoformat(),
                'queued_jobs': queued,
                'notes': f'Manual Prospect {period} report sync queued.',
            },
        )
        return Response(
            {
                'status': 'queued',
                'period': period,
                'mode': mode,
                'report_start': report_start.isoformat(),
                'report_end': report_end.isoformat(),
                'queued_jobs': queued,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        tracked_fields = {
            'deployment_team_roster': 'field team roster',
            'deployment_equipment_plan': 'equipment sourcing plan',
            'deployment_site_status': 'site readiness status',
            'deployment_work_schedule': 'work schedule',
            'deployment_permits_status': 'permits and approvals',
            'device_brand': 'device brand',
            'device_model': 'device model',
            'device_tech_tier': 'technology tier',
            'verification_method_confirmed': 'verification method confirmation',
        }
        changed_labels = []
        for field_name, label in tracked_fields.items():
            if field_name in serializer.validated_data:
                previous = getattr(instance, field_name, '') or ''
                current = serializer.validated_data.get(field_name) or ''
                if previous != current:
                    changed_labels.append(label)
        target_fields = (
            'target_installations',
            'installation_target',
            'target_female_pct',
            'female_target_pct',
            'energy_output_target_kwh',
            'start_date',
        )
        target_fields_changed = any(
            field_name in serializer.validated_data and getattr(instance, field_name, None) != serializer.validated_data.get(field_name)
            for field_name in target_fields
        )

        project = serializer.save()
        if target_fields_changed:
            queue_project_targets_sync(str(project.id))
        if changed_labels:
            create_project_activity_update(
                project,
                self.request.user,
                'Deployment Plan Updated',
                f"Updated deployment planning details: {', '.join(changed_labels)}.",
            )

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        if self.get_object().archived_at:
            raise PermissionDenied('Archived projects are kept for audit and cannot be deleted.')
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get', 'post'], url_path='setup')
    def setup(self, request, pk=None):
        project = self.get_object()
        if request.method.lower() == 'get':
            self._assert_vendor_setup_access(project)
            setup = getattr(project, 'project_setup', None)
            if not setup:
                setup = self._setup_instance_for_project(project)
            serializer = ProjectSetupSerializer(setup, context={'request': request, 'project': project})
            verification_method = str(project.verification_method or '').strip().lower()
            return Response({
                'project': ProjectSerializer(project, context={'request': request}).data,
                'setup': serializer.data,
                'form_sections': [
                    {
                        'key': 'team_resources',
                        'title': 'Section A — Team & Resources',
                        'fields': [
                            'team_roster_file',
                            'equipment_plan_file',
                            'checklist_team_ready',
                            'checklist_equipment_ready',
                            'checklist_site_ready',
                            'checklist_safety_ready',
                            'checklist_logistics_ready',
                        ],
                    },
                    {
                        'key': 'site_preparation',
                        'title': 'Section B — Site Preparation',
                        'fields': [
                            'site_status',
                            'work_schedule_start',
                            'work_schedule_end',
                            'compliance_docs_file',
                            'insurance_certificate_file',
                        ],
                    },
                    {
                        'key': 'technology_details',
                        'title': 'Section C — Technology Details',
                        'fields': ['device_model', 'device_brand', 'tech_tier'],
                    },
                    {
                        'key': 'verification_method',
                        'title': 'Section D — Verification Method',
                        'mode': verification_method,
                        'fields': (
                            ['meter_api_endpoint', 'meter_api_token', 'test_connection']
                            if verification_method == 'iot'
                            else ['manual_verification_confirmed']
                        ),
                    },
                ],
                'submit_installation_disabled': not bool(setup.setup_completed_at),
            })
        return self._save_project_setup(request, project, submit=False)

    @action(detail=True, methods=['post'], url_path='setup/submit')
    def submit_setup(self, request, pk=None):
        project = self.get_object()
        return self._save_project_setup(request, project, submit=True)

    @action(detail=True, methods=['post'], url_path='setup/request-change')
    def request_setup_change(self, request, pk=None):
        project = self.get_object()
        self._assert_vendor_setup_access(project)
        setup = getattr(project, 'project_setup', None)
        review_status = getattr(setup, 'review_status', None)
        if review_status == ProjectSetupReviewStatus.APPROVED:
            return Response(
                {'detail': 'This project setup has been approved by RMT and is locked. Change requests are no longer allowed.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if review_status not in {ProjectSetupReviewStatus.CHANGES_REQUESTED, ProjectSetupReviewStatus.REJECTED}:
            return Response(
                {'detail': 'Project setup must be rejected or already in a changes-requested state before you can request further changes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = str(request.data.get('message') or 'Please reopen the setup form for updates.').strip()
        if not message:
            return Response({'detail': 'A message is required when requesting a setup change.'}, status=status.HTTP_400_BAD_REQUEST)

        previous_notes = setup.review_notes if setup else ''
        if setup:
            setup.previous_review_notes = previous_notes
            setup.review_notes = message
            setup.review_status = ProjectSetupReviewStatus.CHANGES_REQUESTED
            setup.reviewed_by = None
            setup.reviewed_at = None
            setup.setup_completed_at = None
            setup.save(
                update_fields=[
                    'review_status',
                    'review_notes',
                    'previous_review_notes',
                    'reviewed_by',
                    'reviewed_at',
                    'setup_completed_at',
                    'updated_at',
                ]
            )
        project.status = ProjectStatus.SETUP_CHANGES_REQUESTED
        project.setup_completed_at = None
        project.save(update_fields=['status', 'setup_completed_at'])

        recipients = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        notifications = [
            Notification(
                recipient_id=str(user.id),
                recipient_name=user.full_name or user.username,
                type=NotificationChannel.IN_APP,
                event='project_setup_changes_requested',
                title='Project Setup Changes Requested',
                body=f'Vendor {project.vendor_name} requested setup changes for Project #{project.id}. {message}',
                status=NotificationStatus.SENT,
                linked_entity_id=str(project.id),
            )
            for user in recipients
        ]
        if notifications:
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)
        create_project_activity_update(
            project,
            request.user,
            'Setup Change Requested',
            message,
        )
        log_audit(
            request.user,
            'project_setup_changes_requested',
            project,
            {'project_id': str(project.id), 'message': message, 'previous_notes': previous_notes},
        )
        project.refresh_from_db()
        return Response(ProjectSerializer(project, context={'request': request}).data, status=status.HTTP_200_OK)

    def _setup_review_action(
        self,
        request,
        project: Project,
        *,
        next_status: str,
        audit_action: str,
        event: str,
        vendor_title: str,
        require_notes: bool = False,
        body_template: str,
        success_message: str,
        approval: bool = False,
        rejection: bool = False,
    ):
        self._assert_rmt_setup_access()
        setup = getattr(project, 'project_setup', None)
        if not setup:
            return Response({'detail': 'Project setup has not been submitted yet.'}, status=status.HTTP_400_BAD_REQUEST)
        if setup.review_status not in {
            ProjectSetupReviewStatus.SUBMITTED,
            ProjectSetupReviewStatus.UNDER_REVIEW,
            ProjectSetupReviewStatus.CHANGES_REQUESTED,
        }:
            return Response(
                {'detail': f'Project setup is in the "{setup.review_status}" state and cannot be actioned.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notes = str(request.data.get('notes') or '').strip()
        if require_notes and not notes:
            return Response({'detail': 'Notes are required for this action.'}, status=status.HTTP_400_BAD_REQUEST)

        decision_time = timezone.now()
        setup.previous_review_notes = setup.review_notes
        setup.review_notes = notes or setup.review_notes
        setup.review_status = next_status
        setup.reviewed_by = request.user
        setup.reviewed_at = decision_time
        if approval:
            setup.setup_completed_at = decision_time
            project.setup_completed_at = decision_time
            project.status = ProjectStatus.ACTIVE
        elif rejection:
            setup.setup_completed_at = None
            project.setup_completed_at = None
            project.status = ProjectStatus.SETUP_REJECTED
        else:
            setup.setup_completed_at = None
            project.setup_completed_at = None
            project.status = ProjectStatus.SETUP_CHANGES_REQUESTED if next_status == ProjectSetupReviewStatus.CHANGES_REQUESTED else ProjectStatus.SETUP_UNDER_REVIEW

        setup.save(
            update_fields=[
                'review_status',
                'review_notes',
                'previous_review_notes',
                'reviewed_by',
                'reviewed_at',
                'setup_completed_at',
                'updated_at',
            ]
        )
        project.save(update_fields=['status', 'setup_completed_at'])

        if approval:
            queue_project_agent_sync(str(project.id))
        refresh_project_kpis(str(project.id))
        log_audit(
            request.user,
            audit_action,
            setup,
            {
                'project_id': str(project.id),
                'actor_id': str(request.user.id),
                'review_status': next_status,
                'notes': notes,
                'timestamp': decision_time.isoformat(),
            },
        )
        self._notify_vendor_of_setup_decision(
            project,
            event=event,
            title=vendor_title,
            body=body_template.format(
                project_id=project.id,
                vendor=project.vendor_name,
                reviewer=request.user.full_name or request.user.username,
                notes=notes or '(no notes provided)',
            ),
        )
        if approval:
            create_project_activity_update(
                project,
                request.user,
                'Project Setup Approved',
                f'Approved by RMT. Installation submission is unlocked for the vendor. Notes: {notes or "(none)"}',
            )
        elif rejection:
            create_project_activity_update(
                project,
                request.user,
                'Project Setup Rejected',
                f'Rejected by RMT. Vendor must contact RMT. Notes: {notes}',
            )
        else:
            create_project_activity_update(
                project,
                request.user,
                'Project Setup Changes Requested by RMT',
                f'RMT requested changes. Notes: {notes}',
            )

        project.refresh_from_db()
        return Response(
            {
                'status': 'ok',
                'message': success_message,
                'project': ProjectSerializer(project, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='setup/start-review')
    def start_setup_review(self, request, pk=None):
        project = self.get_object()
        setup = getattr(project, 'project_setup', None)
        if not setup or setup.review_status != ProjectSetupReviewStatus.SUBMITTED:
            return Response(
                {'detail': 'Only submitted setups can be claimed for review.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._assert_rmt_setup_access()
        setup.review_status = ProjectSetupReviewStatus.UNDER_REVIEW
        setup.reviewed_by = request.user
        setup.reviewed_at = timezone.now()
        setup.save(update_fields=['review_status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        log_audit(
            request.user,
            'project_setup_review_started',
            setup,
            {'project_id': str(project.id), 'actor_id': str(request.user.id)},
        )
        self._notify_vendor_of_setup_decision(
            project,
            event='project_setup_review_started',
            title='Project Setup Review Started',
            body=f'RMT has begun reviewing the project setup for Project #{project.id}.',
        )
        project.refresh_from_db()
        return Response(
            {
                'status': 'ok',
                'message': 'Review claimed.',
                'project': ProjectSerializer(project, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='setup/approve')
    def approve_setup(self, request, pk=None):
        project = self.get_object()
        return self._setup_review_action(
            request,
            project,
            next_status=ProjectSetupReviewStatus.APPROVED,
            audit_action='project_setup_approved',
            event='project_setup_approved',
            vendor_title='Project Setup Approved',
            require_notes=False,
            approval=True,
            body_template='Project #{project_id} setup was approved by {reviewer}. Installation submission is now unlocked. Notes: {notes}',
            success_message='Setup approved. Installation submission has been unlocked.',
        )

    @action(detail=True, methods=['post'], url_path='setup/request-changes')
    def request_setup_changes(self, request, pk=None):
        project = self.get_object()
        return self._setup_review_action(
            request,
            project,
            next_status=ProjectSetupReviewStatus.CHANGES_REQUESTED,
            audit_action='project_setup_changes_requested_by_rmt',
            event='project_setup_changes_requested',
            vendor_title='Project Setup Changes Requested',
            require_notes=True,
            body_template='RMT requested changes on Project #{project_id}. Reason: {notes}',
            success_message='Change request sent to the vendor.',
        )

    @action(detail=True, methods=['post'], url_path='setup/reject')
    def reject_setup(self, request, pk=None):
        project = self.get_object()
        return self._setup_review_action(
            request,
            project,
            next_status=ProjectSetupReviewStatus.REJECTED,
            audit_action='project_setup_rejected',
            event='project_setup_rejected',
            vendor_title='Project Setup Rejected',
            require_notes=True,
            rejection=True,
            body_template='Project #{project_id} setup was rejected by RMT. Reason: {notes}',
            success_message='Setup rejected. The vendor has been notified.',
        )

    @action(detail=True, methods=['post'], url_path='meter-csv-upload')
    def upload_meter_csv(self, request, pk=None):
        project = self.get_object()
        if request.user.role != UserRole.VENDOR:
            raise PermissionDenied('Only vendors can upload meter CSV data for project field work.')
        self._assert_vendor_setup_access(project)
        setup = getattr(project, 'project_setup', None)
        if not setup or not setup.setup_completed_at:
            raise PermissionDenied('Complete project setup before uploading meter CSV data.')
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'detail': 'CSV file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not str(csv_file.name).lower().endswith('.csv'):
            return Response({'detail': 'Only CSV uploads are supported.'}, status=status.HTTP_400_BAD_REQUEST)
        if csv_file.size > 5 * 1024 * 1024:
            return Response({'detail': 'CSV file must be 5MB or less.'}, status=status.HTTP_400_BAD_REQUEST)

        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        rows_created = []
        csv_output_power_by_reading_id = {}
        upload_time = timezone.now()
        invalid_rows = []
        anomaly_counts = {'zero_uptime': 0, 'no_data': 0, 'output_deviation': 0}
        platform_config = PlatformConfiguration.objects.order_by('id').first()
        deviation_threshold_pct = float(getattr(platform_config, 'anomaly_deviation_threshold', 5) or 5)
        batch = MeterDataBatch.objects.create(
            project=project,
            uploaded_by=request.user,
            file_name=str(getattr(csv_file, 'name', '') or '')[:255],
        )

        for row_number, row in enumerate(reader, start=2):
            meter_id = str(row.get('meter_id') or '').strip()
            errors = []
            if not meter_id:
                errors.append('meter_id is required.')
            installation_id = str(row.get('installation_id') or '').strip()
            installation_lookup = InstallationReport.objects.filter(project=project, vendor=request.user)
            installation = None
            if installation_id:
                if installation_id.isdigit():
                    installation = installation_lookup.filter(id=int(installation_id)).first()
                else:
                    installation = installation_lookup.filter(
                        Q(meter_id=installation_id)
                        | Q(serial_number=installation_id)
                        | Q(beneficiary_id=installation_id)
                    ).first()
            if installation is None and meter_id:
                installation = installation_lookup.filter(meter_id=meter_id).first()
            if installation is None:
                errors.append('meter_id or installation_id must match an installation for this vendor and project.')
            try:
                kwh_value = float(row.get('kwh_generated') or row.get('kwh') or 0)
            except (TypeError, ValueError):
                errors.append('kwh_generated must be a non-negative number.')
                kwh_value = 0.0
            if kwh_value < 0:
                errors.append('kwh_generated must be a non-negative number.')
            try:
                uptime_pct = float(row.get('uptime_pct') or 0)
            except (TypeError, ValueError):
                errors.append('uptime_pct must be a number between 0 and 100.')
                uptime_pct = 0.0
            if uptime_pct < 0 or uptime_pct > 100:
                errors.append('uptime_pct must be a number between 0 and 100.')
            output_power_raw = row.get('output_power_w')
            output_power_w = None
            if output_power_raw not in (None, ''):
                try:
                    output_power_w = float(output_power_raw)
                except (TypeError, ValueError):
                    errors.append('output_power_w must be a number when provided.')
            latitude_raw = str(row.get('latitude') or '').strip()
            longitude_raw = str(row.get('longitude') or '').strip()
            latitude = None
            longitude = None
            if latitude_raw:
                try:
                    latitude = float(latitude_raw)
                    if latitude < -90 or latitude > 90:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append('latitude must be a decimal between -90 and 90 when provided.')
                    latitude = None
            if longitude_raw:
                try:
                    longitude = float(longitude_raw)
                    if longitude < -180 or longitude > 180:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append('longitude must be a decimal between -180 and 180 when provided.')
                    longitude = None
            recorded_at_raw = str(row.get('reading_datetime') or row.get('recorded_at') or '').strip()
            recorded_at = parse_meter_timestamp(recorded_at_raw)
            if recorded_at is None:
                errors.append(parse_meter_timestamp_error(recorded_at_raw))
            if errors:
                invalid_rows.append({'row': row_number, 'meter_id': meter_id, 'errors': errors})
                continue

            previous_reading = SmartMeterReading.objects.filter(
                project=project,
                meter_id=meter_id,
                recorded_at__lt=recorded_at,
            ).exclude(review_status=SmartMeterReadingReviewStatus.REJECTED).order_by('-recorded_at', '-id').first()

            reading = SmartMeterReading.objects.create(
                project=project,
                installation=installation,
                batch=batch,
                source=SmartMeterReadingSource.CSV_UPLOAD,
                submitted_by=request.user,
                meter_id=meter_id,
                kwh=kwh_value,
                uptime_pct=uptime_pct,
                output_power_w=output_power_w,
                latitude=round(latitude, 6) if latitude is not None else None,
                longitude=round(longitude, 6) if longitude is not None else None,
                recorded_at=recorded_at,
            )
            rows_created.append(reading)
            if output_power_w is not None:
                csv_output_power_by_reading_id[reading.id] = output_power_w
            # Timeseries payload will be built after all readings are processed
            if installation and uptime_pct == 0:
                current_recorded = timezone.localtime(reading.recorded_at).strftime('%Y-%m-%d %H:%M %Z')
                current_uploaded = timezone.localtime(reading.created_at).strftime('%Y-%m-%d %H:%M %Z')
                create_or_refresh_anomaly(
                    installation=installation,
                    project=project,
                    flag_type='zero_uptime',
                    description=(
                        f'Meter {meter_id} reported 0.0% uptime (zero-uptime threshold: 0%). '
                        f'Reading: {kwh_value:.2f} kWh, recorded {current_recorded}, uploaded {current_uploaded}. '
                        f'The meter produced no usable uptime during this reporting interval.'
                    ),
                )
                anomaly_counts['zero_uptime'] += 1
            if installation and previous_reading and previous_reading.kwh > 0:
                deviation_pct = abs(kwh_value - float(previous_reading.kwh)) / float(previous_reading.kwh) * 100.0
                if deviation_pct > deviation_threshold_pct:
                    signed_change_pct = (kwh_value - float(previous_reading.kwh)) / float(previous_reading.kwh) * 100.0
                    current_recorded = timezone.localtime(reading.recorded_at).strftime('%Y-%m-%d %H:%M %Z')
                    current_uploaded = timezone.localtime(reading.created_at).strftime('%Y-%m-%d %H:%M %Z')
                    previous_recorded = timezone.localtime(previous_reading.recorded_at).strftime('%Y-%m-%d %H:%M %Z')
                    previous_uploaded = timezone.localtime(previous_reading.created_at).strftime('%Y-%m-%d %H:%M %Z')
                    create_or_refresh_anomaly(
                        installation=installation,
                        project=project,
                        flag_type='output_deviation',
                        description=(
                            f'Meter {meter_id} changed by {signed_change_pct:+.1f}% (review threshold: >{deviation_threshold_pct:g}%). '
                            f'Current reading: {kwh_value:.2f} kWh, recorded {current_recorded}, uploaded {current_uploaded}. '
                            f'Compared with: {float(previous_reading.kwh):.2f} kWh, recorded {previous_recorded}, uploaded {previous_uploaded}.'
                        ),
                    )
                    anomaly_counts['output_deviation'] += 1

        if not rows_created:
            batch.delete()
            return Response(
                {
                    'detail': 'No valid meter rows were found in the uploaded CSV.',
                    'valid_rows': 0,
                    'invalid_rows': len(invalid_rows),
                    'errors': invalid_rows,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cutoff = upload_time - timedelta(hours=48)
        stale_installations = InstallationReport.objects.filter(
            project=project,
            vendor=request.user,
        ).exclude(meter_id='').exclude(
            id__in=SmartMeterReading.objects.filter(recorded_at__gte=cutoff)
            .exclude(review_status=SmartMeterReadingReviewStatus.REJECTED)
            .values('installation_id'),
        ).distinct()
        for installation in stale_installations:
            last_reading = installation.smart_meter_readings.exclude(
                review_status=SmartMeterReadingReviewStatus.REJECTED,
            ).order_by('-recorded_at', '-id').first()
            checked_at = timezone.localtime(upload_time).strftime('%Y-%m-%d %H:%M %Z')
            if last_reading:
                last_recorded = timezone.localtime(last_reading.recorded_at).strftime('%Y-%m-%d %H:%M %Z')
                last_uploaded = timezone.localtime(last_reading.created_at).strftime('%Y-%m-%d %H:%M %Z')
                hours_missing = max(0, (upload_time - last_reading.recorded_at).total_seconds() / 3600)
                finding = (
                    f'No meter reading has been received for meter {installation.meter_id} within the 48-hour rule. '
                    f'Last reading: {float(last_reading.kwh):.2f} kWh, recorded {last_recorded}, uploaded {last_uploaded}. '
                    f'At the check time {checked_at}, the last reading was {hours_missing:.1f} hours old.'
                )
            else:
                finding = (
                    f'No meter reading has been received for meter {installation.meter_id}. '
                    f'The installation has no uploaded reading at the {checked_at} check time; the expected reporting window is 48 hours.'
                )
            create_or_refresh_anomaly(
                installation=installation,
                project=project,
                flag_type='no_data',
                description=finding,
            )
            anomaly_counts['no_data'] += 1

        if any(anomaly_counts.values()):
            notify_vendor_and_oversight(
                project,
                vendor=request.user,
                event='meter_csv_anomaly_detected',
                title='Meter Data Anomaly Detected',
                body=(
                    f'Meter CSV upload for project {project.project_reference or project.id} created anomaly flags: '
                    f'zero_uptime={anomaly_counts["zero_uptime"]}, '
                    f'no_data={anomaly_counts["no_data"]}, '
                    f'output_deviation={anomaly_counts["output_deviation"]}.'
                ),
                linked_entity_id=str(project.id),
            )

        stored_path = default_storage.save(
            f'project_documents/meter_csv_{project.id}_{upload_time.strftime("%Y%m%d%H%M%S")}.csv',
            ContentFile(decoded.encode('utf-8')),
        )
        source_document = ProjectDocument.objects.create(
            project=project,
            title=f'Meter Data CSV Upload ({len(rows_created)} rows)',
            file=stored_path,
            uploaded_by=request.user,
        )
        integrity_findings = run_integrity_checks(batch, rows_created)
        batch.integrity_findings = integrity_findings
        batch.status = initial_batch_status(integrity_findings)
        batch.source_document = source_document
        batch.rows_ingested = len(rows_created)
        batch.rows_rejected_on_upload = len(invalid_rows)
        batch.rejected_rows = invalid_rows[:REJECTED_ROWS_STORED]
        batch.save(update_fields=['integrity_findings', 'status', 'source_document', 'rows_ingested', 'rows_rejected_on_upload', 'rejected_rows'])
        # A fresh upload is the vendor's answer to any outstanding correction request.
        MeterDataBatch.objects.filter(
            project=project,
            status=MeterDataBatchStatus.CORRECTION_REQUESTED,
        ).exclude(pk=batch.pk).update(status=MeterDataBatchStatus.SUPERSEDED)
        if batch.status == MeterDataBatchStatus.FLAGGED:
            high_findings = [finding for finding in integrity_findings if finding['severity'] == 'high']
            notify_vendor_and_oversight(
                project,
                vendor=request.user,
                event='meter_data_batch_flagged',
                title='Meter Data Flagged for Review',
                body=(
                    f'Meter upload {batch.id} for project {project.project_reference or project.id} failed '
                    f'{len(high_findings)} integrity check(s): '
                    + '; '.join(sorted({finding['label'] for finding in high_findings}))
                    + '. Milestone claims are blocked until RBF reviews it.'
                ),
                linked_entity_id=str(project.id),
            )
        create_project_activity_update(
            project,
            request.user,
            'Meter CSV Uploaded',
            f'Uploaded meter CSV with {len(rows_created)} rows ingested.',
        )
        log_audit(
            request.user,
            'meter_csv_uploaded',
            project,
            {
                'project_id': str(project.id),
                'file_name': str(getattr(csv_file, 'name', '') or ''),
                'rows_ingested': len(rows_created),
                'rows_rejected': len(invalid_rows),
                'rejected_rows': invalid_rows[:REJECTED_ROWS_STORED],
                'anomaly_counts': anomaly_counts,
                'meter_data_batch_id': batch.id,
                'meter_data_batch_status': batch.status,
                'integrity_finding_codes': sorted({finding['code'] for finding in integrity_findings}),
            },
        )
        # Build timeseries payload with cumulative data
        timeseries_payload = {'data': []}
        if rows_created:
            new_reading_ids = {reading.id for reading in rows_created}
            meter_ids = {reading.meter_id for reading in rows_created}
            cumulative_wh_by_id = {}
            running_wh_by_meter = {}
            readings_for_payload = SmartMeterReading.objects.filter(
                project=project,
                meter_id__in=meter_ids,
            ).select_related('installation').order_by('meter_id', 'recorded_at', 'id')

            for reading in readings_for_payload:
                running_wh_by_meter.setdefault(reading.meter_id, 0.0)
                running_wh_by_meter[reading.meter_id] += float(reading.kwh) * 1000
                if reading.id in new_reading_ids:
                    cumulative_wh_by_id[reading.id] = round(running_wh_by_meter[reading.meter_id], 2)

            for reading in sorted(rows_created, key=lambda item: (item.meter_id, item.recorded_at, item.id)):
                project_setup = getattr(
                    reading.installation.project if reading.installation else project,
                    'project_setup',
                    None,
                )
                manufacturer = getattr(project_setup, 'device_brand', '') if project_setup else ''
                metered_at = reading.recorded_at.astimezone(dt_timezone.utc).isoformat(timespec='milliseconds')
                timeseries_payload['data'].append({
                    'metered_at': metered_at,
                    'interval_seconds': 3600,
                    'serial_number': reading.meter_id,
                    'manufacturer': manufacturer,
                    'output_energy_interval_wh': round(float(reading.kwh) * 1000, 2),
                    'output_energy_cumulative_wh': cumulative_wh_by_id.get(reading.id, round(float(reading.kwh) * 1000, 2)),
                    'output_power_w': csv_output_power_by_reading_id.get(reading.id),
                })

        SyncToProspectJob.dispatch_async(
            'pushInstallationTimeSeries',
            timeseries_payload,
            record_id=project.id,
            record_type='project',
        )
        refresh_project_kpis(str(project.id))
        return Response(
            {
                'status': 'ok',
                'rows_ingested': len(rows_created),
                'rows_rejected': len(invalid_rows),
                'invalid_rows': invalid_rows[:REJECTED_ROWS_STORED],
                'anomaly_counts': anomaly_counts,
                'uploaded_at': upload_time.isoformat(),
                'batch_id': batch.id,
                'batch_status': batch.status,
                'integrity_findings': integrity_findings,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='setup/test-connection')
    def test_setup_connection(self, request, pk=None):
        project = self.get_object()
        self._assert_vendor_setup_access(project)
        if str(project.verification_method or '').strip().lower() != 'iot':
            return Response({'detail': 'Connection testing is only available for IoT verification projects.'}, status=status.HTTP_400_BAD_REQUEST)
        endpoint = str(request.data.get('meter_api_endpoint') or '').strip()
        token = str(request.data.get('meter_api_token') or '').strip()
        if not endpoint.startswith(('http://', 'https://')):
            return Response({'detail': 'Enter a valid API endpoint URL.'}, status=status.HTTP_400_BAD_REQUEST)
        if not token:
            return Response({'detail': 'Enter the API token before testing the connection.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': 'ok', 'message': 'Connection details look valid for IoT meter ingestion.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def archive(self, request, pk=None):
        """The project's lifecycle archive record(s): timeline and snapshot from tender creation to closure."""
        project = self.get_object()
        records = list(project.archives.select_related('archived_by', 'contract', 'tender'))
        if not records:
            return Response({'detail': 'This project has not been archived.'}, status=status.HTTP_404_NOT_FOUND)
        return Response([
            {
                'id': record.id,
                'archived_at': record.archived_at,
                'archived_by': (record.archived_by.full_name or record.archived_by.username) if record.archived_by_id else None,
                'reason': record.reason,
                'lifecycle_started_at': record.lifecycle_started_at,
                'lifecycle_ended_at': record.lifecycle_ended_at,
                'superseded_at': record.superseded_at,
                'tender_reference': record.tender.reference_number if record.tender_id else None,
                'contract_reference': record.contract.reference_number if record.contract_id else None,
                'has_dossier': bool(record.dossier),
                'timeline': record.timeline,
                'snapshot': record.snapshot,
            }
            for record in records
        ])

    @action(detail=True, methods=['get'], url_path=r'archive/(?P<archive_id>[0-9]+)/dossier')
    def archive_dossier(self, request, pk=None, archive_id=None):
        project = self.get_object()
        record = project.archives.filter(id=archive_id).first()
        if record is None:
            raise Http404('Archive record not found.')
        if not record.dossier:
            from .archive import _attach_dossier

            _attach_dossier(record)
            record.refresh_from_db()
        if not record.dossier:
            return Response({'detail': 'The dossier could not be generated. Try again later.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        log_audit(request.user, 'project_archive_dossier_downloaded', project, {'project_id': str(project.id), 'archive_id': record.id, 'module': 'projects'})
        return FileResponse(record.dossier.open('rb'), as_attachment=True, filename=Path(record.dossier.name).name)

    @action(detail=True, methods=['post'])
    def restore_archive(self, request, pk=None):
        if request.user.role != UserRole.ADMIN:
            raise PermissionDenied('Only the Platform Administrator (Super Admin) can restore an archived project.')
        project = self.get_object()
        if not project.archived_at:
            return Response({'detail': 'This project is not archived.'}, status=status.HTTP_400_BAD_REQUEST)
        reason = str(request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response({'reason': ['Explain why the project is being restored (at least 10 characters).']}, status=status.HTTP_400_BAD_REQUEST)
        restore_project(project, request.user, reason=reason)
        project.refresh_from_db()
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=['post'])
    def flag_issue(self, request, pk=None):
        project = self.get_object()
        if request.user.role not in {UserRole.UNDP_DONOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only Project Steering Committee, RBF Management Team, or Platform Administrator can flag project issues.')

        category = str(request.data.get('category') or 'general').strip() or 'general'
        details = str(request.data.get('details') or request.data.get('message') or '').strip()
        if not details:
            return Response({'detail': 'details is required.'}, status=status.HTTP_400_BAD_REQUEST)

        title_map = {
            'payment_delay': 'Payment Delay Flagged',
            'contract_issue': 'Contract Issue Flagged',
            'compliance': 'Compliance Issue Flagged',
            'general': 'Project Issue Flagged',
        }
        title = title_map.get(category, 'Project Issue Flagged')
        claim_id = str(request.data.get('payment_claim') or '').strip()
        claim = PaymentClaim.objects.filter(id=claim_id, project=project).first() if claim_id.isdigit() else None
        if claim_id and claim is None:
            return Response({'detail': 'The payment claim does not belong to this project.'}, status=status.HTTP_400_BAD_REQUEST)
        # An archived project's activity log is frozen; the flag itself is still recorded below.
        update = None if project.archived_at else create_project_activity_update(project, request.user, title, details)
        review = OversightReview.objects.create(
            reviewer=request.user,
            reviewer_role=request.user.role,
            subject_type=OversightSubject.DISBURSEMENT if category == 'payment_delay' else OversightSubject.PROJECT,
            review_status=OversightReviewStatus.FLAGGED,
            project=project,
            payment_claim=claim,
            comment=details,
            issue_category=category,
            action_required=str(request.data.get('action_required') or '').strip(),
            follow_up_status=OversightFollowUpStatus.OPEN,
        )
        log_audit(request.user, 'project_issue_flagged', update or review, {'project_id': str(project.id), 'category': category, 'review_id': review.id})
        notify_project_oversight(
            project,
            title=f'{title}: {project.project_reference or project.id}',
            body=details,
            linked_entity_id=str(project.id),
        )
        return Response({'status': 'flagged', 'title': title, 'details': details}, status=status.HTTP_200_OK)


class MilestoneViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    queryset = Milestone.objects.all().order_by('id')
    serializer_class = MilestoneSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'project']
    search_fields = ['name']
    ordering_fields = ['percentage', 'amount', 'created_at']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.VENDOR}

    def get_queryset(self):
        qs = Milestone.objects.select_related('project', 'completion_review__reviewed_by').all().order_by('id')
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

    REVIEW_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    @action(detail=True, methods=['post'], url_path='completion-review')
    def completion_review(self, request, pk=None):
        """Verify a paid milestone and decide the project's next step:
        proceed to the next milestone, close the project, transfer the remaining
        milestones to another vendor, or (final milestone) complete the project."""
        if request.user.role not in self.REVIEW_ROLES:
            raise PermissionDenied('Only the RBF Management Team or Super Admin can verify milestone completion.')
        milestone = self.get_object()
        project = milestone.project
        review = getattr(milestone, 'completion_review', None)
        if review is None:
            return Response({'detail': 'This milestone has not been paid yet, so there is nothing to verify.'}, status=status.HTTP_400_BAD_REQUEST)
        if review.status != MilestoneReviewStatus.PENDING:
            return Response({'detail': 'A decision has already been recorded for this milestone.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MilestoneReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['decision']
        notes = serializer.validated_data['verification_notes']
        final_milestone = is_last_milestone(milestone)
        allowed = {MilestoneReviewDecision.COMPLETE} if final_milestone else {
            MilestoneReviewDecision.PROCEED,
            MilestoneReviewDecision.CLOSE,
            MilestoneReviewDecision.TRANSFER,
        }
        if decision not in allowed:
            message = (
                'The final milestone can only be verified to complete the project.'
                if final_milestone
                else 'Choose proceed, close or transfer for this milestone.'
            )
            return Response({'decision': [message]}, status=status.HTTP_400_BAD_REQUEST)

        previous_vendor = User.objects.filter(id=project.vendor_id).first() if str(project.vendor_id).isdigit() else None
        new_vendor = None
        if decision == MilestoneReviewDecision.TRANSFER:
            new_vendor_id = str(serializer.validated_data['new_vendor_id']).strip()
            new_vendor = User.objects.filter(id=new_vendor_id, role=UserRole.VENDOR).first() if new_vendor_id.isdigit() else None
            error = ''
            if new_vendor is None:
                error = 'Selected vendor was not found.'
            elif str(new_vendor.id) == str(project.vendor_id):
                error = 'Select a different vendor from the current one.'
            elif is_vendor_restricted(new_vendor):
                error = 'This vendor is suspended or blacklisted and cannot take over the project.'
            if error:
                return Response({'new_vendor_id': [error]}, status=status.HTTP_400_BAD_REQUEST)

        milestone_label = f'Milestone {milestone.milestone_number}'
        project_label = project.project_reference or project.id
        with transaction.atomic():
            review.status = MilestoneReviewStatus.DECIDED
            review.decision = decision
            review.verification_notes = notes
            review.reviewed_by = request.user
            review.reviewed_at = timezone.now()
            if new_vendor is not None:
                review.transferred_to_vendor_id = str(new_vendor.id)
                review.transferred_to_vendor_name = new_vendor.organization_name or new_vendor.full_name or new_vendor.username
            review.save()

            if decision == MilestoneReviewDecision.PROCEED:
                activity = f'{milestone_label} verified. The vendor may proceed with the next milestone.'
            elif decision == MilestoneReviewDecision.CLOSE:
                cancelled = project.milestones.filter(milestone_number__gt=milestone.milestone_number).exclude(
                    status__in=['paid', 'Paid']
                ).update(status='cancelled', updated_at=timezone.now())
                project.status = ProjectStatus.CLOSED
                project.save(update_fields=['status', 'updated_at'])
                activity = f'{milestone_label} verified and the project was closed. {cancelled} remaining milestone(s) cancelled.'
            elif decision == MilestoneReviewDecision.TRANSFER:
                project.vendor_id = str(new_vendor.id)
                project.vendor_name = review.transferred_to_vendor_name
                project.save(update_fields=['vendor_id', 'vendor_name', 'updated_at'])
                activity = (
                    f'{milestone_label} verified. The remaining milestones were transferred from '
                    f'{review.vendor_name or "the previous vendor"} to {review.transferred_to_vendor_name}.'
                )
            else:
                activity = f'{milestone_label} (final) verified.'

            log_audit(request.user, f'milestone_review_{decision}', milestone, {
                'project_id': str(project.id),
                'milestone_number': milestone.milestone_number,
                'decision': decision,
                'notes': notes,
                'previous_vendor_id': review.vendor_id,
                'new_vendor_id': review.transferred_to_vendor_id,
            })
            create_project_activity_update(project, request.user, 'Milestone Completion Verified', f'{activity} Notes: {notes}')

        if decision == MilestoneReviewDecision.COMPLETE:
            mark_project_completed(project, request.user)
        else:
            vendor_messages = {
                MilestoneReviewDecision.PROCEED: f'{milestone_label} of project {project_label} was verified. You may proceed with the next milestone.',
                MilestoneReviewDecision.CLOSE: f'{milestone_label} of project {project_label} was verified and the project has been closed. Reason: {notes}',
                MilestoneReviewDecision.TRANSFER: f'{milestone_label} of project {project_label} was verified. The remaining milestones have been transferred to another vendor. Reason: {notes}',
            }
            if previous_vendor:
                notify_vendor_and_oversight(
                    project,
                    vendor=previous_vendor,
                    event=f'milestone_review_{decision}',
                    title=f'{milestone_label} Verified',
                    body=vendor_messages[decision],
                    linked_entity_id=str(project.id),
                )
            if new_vendor is not None:
                NotificationService.send(
                    str(new_vendor.id),
                    'Project Transferred To You',
                    f'Project {project_label} has been transferred to you starting after {milestone_label}. Review the project to continue.',
                    'info',
                    'projects',
                    project.id,
                )
        refresh_project_kpis(str(project.id))
        milestone.refresh_from_db()
        return Response(self.get_serializer(milestone).data, status=status.HTTP_200_OK)


class ProjectUpdateViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
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
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
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
        if self.request.user.role == UserRole.DOE_OFFICER:
            if not Project.objects.filter(id=project_id).filter(doe_region_filter(self.request.user)).exists():
                raise PermissionDenied('You can only add notes and documents to projects in your region.')

    def perform_create(self, serializer):
        self._assert_write_permission()
        project_id = str(serializer.validated_data.get('project').id) if serializer.validated_data.get('project') else ''
        self._assert_project_access(project_id)
        update = serializer.save(author=self.request.user)
        log_audit(self.request.user, 'project_update_added', update, {'project_id': project_id})

    def _assert_doe_owns(self):
        # DoE officers may only edit or remove their own regional entries.
        if self.request.user.role == UserRole.DOE_OFFICER and self.get_object().author_id != self.request.user.id:
            raise PermissionDenied('You can only change entries you created.')

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().destroy(request, *args, **kwargs)


class ProjectDocumentViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
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
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
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
        if self.request.user.role == UserRole.DOE_OFFICER:
            if not Project.objects.filter(id=project_id).filter(doe_region_filter(self.request.user)).exists():
                raise PermissionDenied('You can only add notes and documents to projects in your region.')

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

    def _assert_doe_owns(self):
        # DoE officers may only edit or remove their own regional entries.
        if self.request.user.role == UserRole.DOE_OFFICER and self.get_object().uploaded_by_id != self.request.user.id:
            raise PermissionDenied('You can only change entries you created.')

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        self._assert_doe_owns()
        return super().destroy(request, *args, **kwargs)


class PaymentClaimViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    queryset = PaymentClaim.objects.select_related('project', 'vendor', 'milestone', 'reviewed_by').all()
    serializer_class = PaymentClaimSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'project', 'vendor']
    search_fields = ['payment_reference', 'implementation_notes', 'remarks']
    ordering_fields = ['submitted_at', 'claim_amount', 'approved_at', 'paid_at']

    WRITE_ROLES = {UserRole.VENDOR}
    VERIFY_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    TAC_APPROVE_ROLES = {UserRole.TAC}
    PSC_APPROVE_ROLES = {UserRole.UNDP_DONOR}
    REJECT_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC, UserRole.UNDP_DONOR}
    PAY_ROLES = {UserRole.ADMIN}

    def get_queryset(self):
        qs = self.queryset.order_by('-submitted_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        return qs

    def _assert_write_permission(self):
        if self.request.user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to modify claims.')
        assert_user_not_blacklisted_for_writes(
            self.request.user,
            'Your vendor account is suspended or blacklisted. Payment claims are on hold for audit.',
        )

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data.copy()
        data['vendor'] = request.user.id
        project_id = data.get('project')
        if not project_id:
            return Response({'detail': 'project is required.'}, status=status.HTTP_400_BAD_REQUEST)
        project = Project.objects.filter(id=project_id).first()
        if not project:
            return Response({'detail': 'project not found.'}, status=status.HTTP_400_BAD_REQUEST)
        if not Project.objects.filter(id=project.id).filter(vendor_query_filter(request.user)).exists():
            raise PermissionDenied('You can only submit claims for your own projects.')
        data['district'] = (project.district or project.region or '').strip()

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        existing_claim = None
        milestone_id = data.get('milestone')
        if milestone_id:
            existing_claim = PaymentClaim.objects.filter(
                project_id=data.get('project'),
                milestone_id=milestone_id,
            ).exclude(status=PaymentClaimStatus.REJECTED).first()
        if existing_claim:
            return Response(
                {'detail': 'A claim for this milestone already exists and the milestone is locked from duplicate submissions.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        claim_milestone = serializer.validated_data.get('milestone')
        if claim_milestone is not None:
            blocker = next_milestone_blocker(claim_milestone)
            if blocker:
                return Response({'detail': blocker}, status=status.HTTP_400_BAD_REQUEST)
        claim = serializer.save()
        claim.status = PaymentClaimStatus.SUBMITTED
        if claim.milestone and not claim.claim_amount:
            claim.claim_amount = claim.milestone.amount
        claim.save(update_fields=['status', 'claim_amount'])
        if claim.milestone:
            claim.milestone.status = 'claimed'
            claim.milestone.save(update_fields=['status', 'updated_at'])
        log_audit(request.user, 'payment_claim_submitted', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Claim Submitted',
            f"Submitted a payment claim for M {claim.claim_amount} with status {claim.status}.",
        )
        rmt_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        if rmt_users:
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=str(user.id),
                        recipient_name=user.full_name or user.username,
                        type=NotificationChannel.IN_APP,
                        event='payment_claim_submitted',
                        title='Milestone Claim Submitted',
                        body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} is awaiting RMT review.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(claim.project_id),
                    )
                    for user in rmt_users
                ],
                ignore_conflicts=True,
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
        if claim.status not in {PaymentClaimStatus.SUBMITTED, PaymentClaimStatus.LEGACY_PENDING}:
            return Response({'detail': 'Only submitted claims can be approved by RMT.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.RMT_APPROVED
        claim.verified_at = timezone.now()
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'verified_at', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'claim_rmt_approved', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            'Claim Approved By RMT',
            f"Payment claim {claim.id} was approved by RMT.",
        )
        tac_users = User.objects.filter(role=UserRole.TAC).only('id', 'full_name', 'username')
        if tac_users:
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=str(user.id),
                        recipient_name=user.full_name or user.username,
                        type=NotificationChannel.IN_APP,
                        event='payment_claim_verified',
                        title='Claim Ready For TAC Endorsement',
                        body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} was approved by RMT and awaits TAC endorsement.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(claim.project_id),
                    )
                    for user in tac_users
                ],
                ignore_conflicts=True,
            )
        Notification.objects.create(
            recipient_id=str(claim.vendor_id),
            recipient_name=claim.vendor.full_name or claim.vendor.username,
            type=NotificationChannel.IN_APP,
            event='payment_claim_verified',
            title='Milestone Claim Approved By RMT',
            body=f'Claim {claim.id} passed RMT review and is now waiting for TAC endorsement.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.role not in (self.TAC_APPROVE_ROLES | self.PSC_APPROVE_ROLES):
            raise PermissionDenied('You do not have permission to approve claims.')
        claim = self.get_object()
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. Claim remains on Held/Audit.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.role in self.TAC_APPROVE_ROLES:
            if claim.status not in {PaymentClaimStatus.RMT_APPROVED, PaymentClaimStatus.LEGACY_VERIFIED}:
                return Response({'detail': 'Claim must first be approved by RMT before TAC endorsement.'}, status=status.HTTP_400_BAD_REQUEST)
            claim.status = PaymentClaimStatus.TAC_ENDORSED
            claim.approved_at = timezone.now()
            claim.reviewed_by = request.user
            claim.remarks = request.data.get('remarks', claim.remarks)
            claim.save(update_fields=['status', 'approved_at', 'reviewed_by', 'remarks'])
            log_audit(request.user, 'claim_tac_endorsed', claim, {'status': claim.status})
            create_project_activity_update(
                claim.project,
                request.user,
                'Claim Endorsed By TAC',
                f"Payment claim {claim.id} was endorsed by TAC.",
            )
            psc_users = User.objects.filter(role=UserRole.UNDP_DONOR).only('id', 'full_name', 'username')
            if psc_users:
                Notification.objects.bulk_create(
                    [
                        Notification(
                            recipient_id=str(user.id),
                            recipient_name=user.full_name or user.username,
                            type=NotificationChannel.IN_APP,
                            event='payment_claim_approved',
                            title='Claim Ready For PSC Approval',
                            body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} was endorsed by TAC and awaits PSC approval.',
                            status=NotificationStatus.SENT,
                            linked_entity_id=str(claim.project_id),
                        )
                        for user in psc_users
                    ],
                    ignore_conflicts=True,
                )
            Notification.objects.create(
                recipient_id=str(claim.vendor_id),
                recipient_name=claim.vendor.full_name or claim.vendor.username,
                type=NotificationChannel.IN_APP,
                event='payment_claim_approved',
                title='Milestone Claim Endorsed By TAC',
                body=f'Claim {claim.id} passed TAC review and is now waiting for PSC approval.',
                status=NotificationStatus.SENT,
                linked_entity_id=str(claim.project_id),
            )
            return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

        if claim.status not in {PaymentClaimStatus.TAC_ENDORSED, PaymentClaimStatus.LEGACY_APPROVED}:
            return Response({'detail': 'Claim must first be endorsed by TAC before PSC approval.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.PSC_APPROVED
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'reviewed_by', 'remarks'])
        log_audit(request.user, 'claim_psc_approved', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            'Claim Approved By PSC',
            f"Payment claim {claim.id} was approved by PSC and is now waiting for RMT payment confirmation.",
        )
        rmt_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        if rmt_users:
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=str(user.id),
                        recipient_name=user.full_name or user.username,
                        type=NotificationChannel.IN_APP,
                        event='payment_claim_psc_approved',
                        title='Claim Ready For Payment Confirmation',
                        body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} was approved by PSC and is ready for RMT payment confirmation.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(claim.project_id),
                    )
                    for user in rmt_users
                ],
                ignore_conflicts=True,
            )
        Notification.objects.create(
            recipient_id=str(claim.vendor_id),
            recipient_name=claim.vendor.full_name or claim.vendor.username,
            type=NotificationChannel.IN_APP,
            event='payment_claim_psc_approved',
            title='Milestone Claim Approved By PSC',
            body=f'Claim {claim.id} has PSC approval and is now waiting for RMT payment confirmation.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def view_bank_details(self, request, pk=None):
        claim = self.get_object()
        if request.user.role not in {UserRole.UNDP_DONOR, UserRole.ADMIN, UserRole.RBF_OFFICIAL}:
            raise PermissionDenied('You do not have permission to view bank details for this claim.')

        payload = _build_disbursement_sheet_payload(claim)
        account_number = payload['vendor_account_number']
        if request.user.role == UserRole.UNDP_DONOR:
            if claim.status not in {PaymentClaimStatus.TAC_ENDORSED, PaymentClaimStatus.PSC_APPROVED}:
                return Response({'detail': 'Bank details are available to PSC only after technical endorsement or PSC approval.'}, status=status.HTTP_400_BAD_REQUEST)
            reveal_full = str(request.data.get('reveal_full') or '').lower() in {'1', 'true', 'yes'}
            visibility = 'full_reveal' if reveal_full else 'masked'
            if not reveal_full:
                account_number = account_number or ''
                if len(account_number) <= 4:
                    account_number = '****' if account_number else ''
                else:
                    account_number = '*' * max(0, len(account_number) - 4) + account_number[-4:]
            log_audit(request.user, 'claim_vendor_bank_details_viewed', claim, {
                'claim_status': claim.status,
                'visibility': visibility,
                'requested_by': 'PSC',
            })
        else:
            return Response({'detail': 'Use the disbursement sheet to view full payment instructions for this claim.'}, status=status.HTTP_400_BAD_REQUEST)

        payload['vendor_account_number'] = account_number
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='disbursement-sheet')
    def disbursement_sheet(self, request, pk=None):
        claim = self.get_object()
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}:
            raise PermissionDenied('You do not have permission to view the disbursement sheet for this claim.')
        if claim.status not in {
            PaymentClaimStatus.PSC_APPROVED,
            PaymentClaimStatus.COMPLETED,
            PaymentClaimStatus.LEGACY_APPROVED,
            PaymentClaimStatus.LEGACY_PAID,
        }:
            return Response({'detail': 'The disbursement sheet is available only after PSC approval.'}, status=status.HTTP_400_BAD_REQUEST)

        payload = _build_disbursement_sheet_payload(claim)
        log_audit(request.user, 'claim_disbursement_sheet_viewed', claim, {
            'claim_status': claim.status,
            'visibility': 'full',
            'requested_by': 'RMT',
        })
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if request.user.role not in self.REJECT_ROLES:
            raise PermissionDenied('You do not have permission to reject claims.')
        claim = self.get_object()
        if claim.status in {PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID}:
            return Response({'detail': 'Paid claims cannot be rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        # TAC "push back to RMT" should return the claim to the RMT review stage.
        if request.user.role == UserRole.TAC and claim.status in {PaymentClaimStatus.RMT_APPROVED, PaymentClaimStatus.LEGACY_VERIFIED}:
            claim.status = PaymentClaimStatus.SUBMITTED
            activity_title = 'Payment Claim Pushed Back'
            activity_body = f"Payment claim {claim.id} was pushed back to RMT by TAC for clarification."
        else:
            claim.status = PaymentClaimStatus.REJECTED
            activity_title = 'Payment Claim Rejected'
            activity_body = f"Payment claim {claim.id} was rejected."
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('remarks', claim.remarks)
        claim.save(update_fields=['status', 'reviewed_by', 'remarks'])
        if claim.milestone:
            claim.milestone.status = 'claimable'
            claim.milestone.save(update_fields=['status', 'updated_at'])
        log_audit(request.user, 'payment_claim_rejected', claim, {'status': claim.status})
        create_project_activity_update(
            claim.project,
            request.user,
            activity_title,
            activity_body,
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        if request.user.role not in self.PAY_ROLES:
            raise PermissionDenied('You do not have permission to process disbursements.')
        claim = self.get_object()
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. New disbursements are frozen.'}, status=status.HTTP_400_BAD_REQUEST)
        if claim.status not in {PaymentClaimStatus.PSC_APPROVED, PaymentClaimStatus.LEGACY_APPROVED}:
            return Response({'detail': 'Claim must be approved by PSC before Finance can pay it.'}, status=status.HTTP_400_BAD_REQUEST)

        reference = str(request.data.get('payment_reference') or f"PMT-{uuid.uuid4().hex[:10].upper()}")
        claim.payment_reference = reference
        claim.reviewed_by = request.user
        claim.save(update_fields=['payment_reference', 'reviewed_by'])

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
            'finance_payment_processed',
            claim,
            {'status': claim.status, 'payment_reference': reference, 'disbursement_id': disbursement.id},
        )
        create_project_activity_update(
            claim.project,
            request.user,
            'Finance Payment Processed',
            f"Finance processed payment for claim {claim.id} with reference {reference}. RMT now needs to mark the claim as paid.",
        )
        rmt_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        if rmt_users:
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=str(user.id),
                        recipient_name=user.full_name or user.username,
                        type=NotificationChannel.IN_APP,
                        event='payment_claim_finance_paid',
                        title='Claim Ready To Mark Paid',
                        body=f'Finance paid claim {claim.id} for project {claim.project.project_reference or claim.project.id}. RMT can now mark it as paid.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(claim.project_id),
                    )
                    for user in rmt_users
                ],
                ignore_conflicts=True,
            )
        Notification.objects.create(
            recipient_id=str(claim.vendor_id),
            recipient_name=claim.vendor.full_name or claim.vendor.username,
            type=NotificationChannel.IN_APP,
            event='payment_claim_paid',
            title='Finance Payment Processed',
            body=f'Finance processed payment for claim {claim.id}. RMT will mark the claim as paid after confirmation.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='confirm-paid')
    def confirm_paid(self, request, pk=None):
        if request.user.role not in self.VERIFY_ROLES:
            raise PermissionDenied('You do not have permission to confirm completed payments.')
        claim = self.get_object()
        if claim.status in {PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID}:
            return Response({'detail': 'This claim has already been marked as paid.'}, status=status.HTTP_400_BAD_REQUEST)
        if claim.status not in {PaymentClaimStatus.PSC_APPROVED, PaymentClaimStatus.LEGACY_APPROVED}:
            return Response({'detail': 'Claim must be PSC approved before it can be marked as paid.'}, status=status.HTTP_400_BAD_REQUEST)

        reference = str(request.data.get('payment_reference') or '').strip()
        if not reference:
            return Response({'detail': 'payment_reference is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _assert_national_budget_available(claim)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.COMPLETED
        claim.paid_at = timezone.now()
        claim.payment_reference = reference
        claim.reviewed_by = request.user
        claim.remarks = request.data.get('notes', claim.remarks)
        claim.save(update_fields=['status', 'paid_at', 'payment_reference', 'reviewed_by', 'remarks'])

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
            'payment_confirmed',
            claim,
            {'status': claim.status, 'payment_reference': reference, 'disbursement_id': disbursement.id},
        )
        create_project_activity_update(
            claim.project,
            request.user,
            'Payment Marked As Paid',
            f"RMT marked payment claim {claim.id} as paid with reference {reference}.",
        )
        Notification.objects.create(
            recipient_id=str(claim.vendor_id),
            recipient_name=claim.vendor.full_name or claim.vendor.username,
            type=NotificationChannel.IN_APP,
            event='payment_claim_completed',
            title='Milestone Payment Completed',
            body=f'Payment of {claim.claim_amount} for claim {claim.id} has been completed. Reference: {reference}.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        if claim.milestone:
            claim.milestone.status = 'paid'
            claim.milestone.save(update_fields=['status', 'updated_at'])
            _, review_opened = open_completion_review(claim.milestone)
            if review_opened:
                milestone_label = f'Milestone {claim.milestone.milestone_number}'
                project_label = claim.project.project_reference or claim.project.id
                create_project_activity_update(
                    claim.project,
                    request.user,
                    'Milestone Completion Verification Required',
                    f'{milestone_label} was paid. RBF / Super Admin must verify it and decide whether the project '
                    'proceeds, is closed, or is transferred to another vendor.',
                )
                notify_project_oversight(
                    claim.project,
                    f'{milestone_label} Awaiting Verification',
                    f'{milestone_label} of project {project_label} is paid. Verify it and decide the next step.',
                )
        refresh_project_kpis(str(claim.project_id))
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)


class DisbursementViewSet(ArchiveScopedListMixin, viewsets.ReadOnlyModelViewSet):
    archive_prefix = 'claim__project__'
    archive_scope_params = ('claim',)
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


class InstallationReportViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    queryset = InstallationReport.objects.select_related('project', 'vendor', 'milestone').all()
    serializer_class = InstallationReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'status', 'vendor']
    search_fields = ['serial_number', 'beneficiary_id', 'beneficiary_phone', 'meter_id']
    ordering_fields = ['submitted_at']

    WRITE_ROLES = {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = self.queryset.order_by('-submitted_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(
                Q(verification_task__assigned_verifier=user) | field_verifier_installation_filter(user)
            ).distinct()
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
        project = Project.objects.select_related('project_setup').filter(id=project_id).first()
        if not project:
            raise PermissionDenied('project not found.')
        if self.request.user.role == UserRole.VENDOR:
            if not Project.objects.filter(id=project_id).filter(vendor_query_filter(self.request.user)).exists():
                raise PermissionDenied('You can only report installations for your own projects.')
            setup = getattr(project, 'project_setup', None)
            if not setup or not setup.setup_completed_at:
                raise PermissionDenied('Complete project setup before submitting installations.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data.copy()
        project_id = str(data.get('project') or '')
        self._assert_project_access(project_id)
        project = Project.objects.select_related('lot').filter(id=project_id).first()

        errors: dict[str, list[str]] = {}
        lat_raw = data.get('gps_lat')
        lng_raw = data.get('gps_lng')
        try:
            latitude = float(lat_raw)
            if latitude < -90 or latitude > 90:
                raise ValueError
        except (TypeError, ValueError):
            errors['gps_lat'] = ['Latitude must be a decimal between -90 and 90.']
            latitude = None
        try:
            longitude = float(lng_raw)
            if longitude < -180 or longitude > 180:
                raise ValueError
        except (TypeError, ValueError):
            errors['gps_lng'] = ['Longitude must be a decimal between -180 and 180.']
            longitude = None
        if errors:
            return Response({'success': False, 'errors': errors}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            inside_lesotho = GpsValidator.isInsideLesotho(latitude, longitude)
        except FileNotFoundError:
            return Response(
                {
                    'success': False,
                    'errors': {
                        'latitude': [
                            'Lesotho boundary file is missing. Run python manage.py setup_lesotho_boundary first.',
                        ],
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not inside_lesotho:
            return Response(
                {
                    'success': False,
                    'errors': {
                        'latitude': [
                            'Location is outside Lesotho. Please capture GPS at the actual installation site.',
                        ],
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        project_district_label = (
            getattr(project, 'district_zone', '')
            or getattr(project, 'district', '')
            or getattr(project, 'region', '')
            or ''
        ).strip()
        outside_district_warning = None
        if project_district_label and GpsValidator.districtBoundaryConfigured():
            is_inside = GpsValidator.isInsideProjectDistrict(latitude, longitude, project_district_label)
            if not is_inside:
                assigned_distance = GpsValidator.distanceToAssignedDistrict(latitude, longitude, project_district_label)
                resolved_district = GpsValidator.resolveDistrictName(latitude, longitude)
                proximity = ""
                if assigned_distance is not None:
                    if assigned_distance < 1000:
                        proximity = f" The location is {int(assigned_distance)} m beyond the assigned district boundary."
                    else:
                        proximity = f" The location is {round(assigned_distance / 1000, 1)} km beyond the assigned district boundary."
                location_note = f" Per the boundary data, the location falls within {resolved_district}." if resolved_district else ""
                return Response(
                    {
                        'success': False,
                        'errors': {
                            'gps_lat': [
                                f'The captured GPS coordinates (Lat: {latitude}, Long: {longitude}) fall outside the assigned district: {project_district_label}.{proximity}{location_note} This installation cannot be saved.',
                            ],
                        },
                    },
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        duplicate_info = GpsValidator.hasDuplicateCoordinate(latitude, longitude, project_id)

        if request.user.role == UserRole.VENDOR:
            data['vendor'] = request.user.id
        data.setdefault('installation_date', timezone.now().date().isoformat())

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        installation_district = resolve_installation_district(project, latitude, longitude)
        if request.user.role == UserRole.VENDOR:
            report = serializer.save(vendor=request.user, gis_status=GisStatus.YELLOW, district=installation_district)
        else:
            report = serializer.save(gis_status=GisStatus.YELLOW, district=installation_district)

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
            verification_zone__iexact=report.district or report.project.district,
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
        if report.meter_id or report.kwh_reading:
            SmartMeterReading.objects.create(
                project=report.project,
                installation=report,
                source=SmartMeterReadingSource.INSTALLATION_REPORT,
                submitted_by=request.user,
                meter_id=report.meter_id or f"installation-{report.id}",
                kwh=report.kwh_reading or 0,
                uptime_pct=float(report.project.uptime or 0),
                recorded_at=timezone.now(),
            )
        queue_installation_sync(str(report.id))
        response_payload = {
            'success': True,
            'data': self.get_serializer(report).data,
        }
        if duplicate_info['isDuplicate']:
            AnomalyFlag.objects.create(
                installation=report,
                project=report.project,
                flag_type='duplicate_gps',
                description=(
                    f"Installation {report.id} is {duplicate_info['distanceMeters']}m from installation "
                    f"{duplicate_info['nearestId']} (duplicate-location review threshold: 10m). "
                    f"Submitted GPS: ({report.gps_lat:.6f}, {report.gps_lng:.6f}); checked {timezone.localtime().strftime('%Y-%m-%d %H:%M %Z')}."
                ),
            )
            report.gis_status = GisStatus.YELLOW
            report.save(update_fields=['gis_status'])
            response_payload['warning'] = (
                'These coordinates are within 10m of an existing installation. '
                'An anomaly flag has been raised for review.'
            )
            response_payload['data'] = self.get_serializer(report).data
        refresh_project_kpis(str(report.project_id))
        return Response(response_payload, status=status.HTTP_201_CREATED)

    def _assert_editable(self, report):
        # Installation evidence is locked once a field verifier has submitted a verification:
        # only the reporting vendor may correct it before then, and nobody afterwards.
        user = self.request.user
        if user.role != UserRole.VENDOR or report.vendor_id != user.id:
            raise PermissionDenied('Installation reports can only be corrected by the vendor who submitted them.')
        if report.status != InstallationStatus.SUBMITTED or report.field_verifications.exists():
            raise PermissionDenied('This installation has been field-verified; its evidence is locked.')
        assert_user_not_blacklisted_for_writes(user, 'Your vendor account is suspended or blacklisted. Installation reporting is restricted.')

    def update(self, request, *args, **kwargs):
        self._assert_editable(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_editable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied('Installation reports are permanent records and cannot be deleted.')


class VerificationTaskViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    archive_prefix = 'report__project__'
    archive_scope_params = ('report__project',)
    queryset = VerificationTask.objects.select_related('report', 'assigned_verifier').all()
    serializer_class = VerificationTaskSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'assigned_verifier', 'report__project']
    search_fields = ['report__serial_number', 'report__beneficiary_id']
    ordering_fields = ['created_at']

    # Tasks are created with the installation report and change only through the actions below.
    http_method_names = ['get', 'post', 'head', 'options']
    VERIFY_ROLES = {UserRole.FIELD_VERIFIER, UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    REVIEW_ROLES = {UserRole.DOE_OFFICER, UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    VERIFIABLE_STATUSES = {VerificationStatus.PENDING, VerificationStatus.PARTIAL, VerificationStatus.REVERIFICATION_REQUIRED}
    COMPLETED_STATUSES = {VerificationStatus.VERIFIED, VerificationStatus.FLAGGED, VerificationStatus.PARTIAL}

    def get_queryset(self):
        qs = self.queryset.select_related('report__project', 'reverification_requested_by').order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(field_verifier_task_scope_filter(user)).distinct().order_by('created_at')
        if user.role == UserRole.VENDOR:
            return qs.filter(report__vendor=user)
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='report__project__')).distinct()
        return qs

    def create(self, request, *args, **kwargs):
        raise PermissionDenied('Verification tasks are created automatically when an installation is reported.')

    def _assert_reviewer(self, task):
        user = self.request.user
        if user.role not in self.REVIEW_ROLES:
            raise PermissionDenied('Only DoE Officers and the RBF Management Team can review verifications.')
        if user.role == UserRole.DOE_OFFICER and not Project.objects.filter(id=task.report.project_id).filter(doe_region_filter(user)).exists():
            raise PermissionDenied('You can only review verifications in your region.')

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        task = self.get_object()
        self._assert_reviewer(task)
        if task.status not in {VerificationStatus.VERIFIED, VerificationStatus.FLAGGED}:
            return Response({'detail': 'Only completed verifications can be acknowledged.'}, status=status.HTTP_400_BAD_REQUEST)
        if OversightReview.objects.filter(
            verification_task=task, reviewer=request.user, review_status=OversightReviewStatus.ACKNOWLEDGED,
            verification_round=task.verification_round,
        ).exists():
            return Response({'detail': 'You already acknowledged this verification.'}, status=status.HTTP_400_BAD_REQUEST)
        review = OversightReview.objects.create(
            reviewer=request.user,
            reviewer_role=request.user.role,
            subject_type=OversightSubject.VERIFICATION,
            review_status=OversightReviewStatus.ACKNOWLEDGED,
            project=task.report.project,
            verification_task=task,
            verification_round=task.verification_round,
            comment=(str(request.data.get('comment') or '').strip() or 'Verification evidence reviewed and acknowledged.'),
        )
        log_audit(request.user, 'verification_acknowledged', task, {'review_id': review.id, 'round': task.verification_round, 'module': 'field_verification'})
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['post'])
    def request_reverification(self, request, pk=None):
        task = self.get_object()
        self._assert_reviewer(task)
        if task.status not in self.COMPLETED_STATUSES:
            return Response({'detail': 'Re-verification can only be requested after a verification has been submitted.'}, status=status.HTTP_400_BAD_REQUEST)
        reason = str(request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response({'detail': 'Explain why re-verification is needed (at least 10 characters).'}, status=status.HTTP_400_BAD_REQUEST)
        previous_status = task.status
        with transaction.atomic():
            task.status = VerificationStatus.REVERIFICATION_REQUIRED
            task.verification_round += 1
            task.reverification_reason = reason
            task.reverification_requested_by = request.user
            task.reverification_requested_at = timezone.now()
            task.save(update_fields=[
                'status', 'verification_round', 'reverification_reason', 'reverification_requested_by',
                'reverification_requested_at', 'updated_at',
            ])
            report = task.report
            report.status = InstallationStatus.SUBMITTED
            report.gis_status = GisStatus.YELLOW
            report.save(update_fields=['status', 'gis_status'])
            OversightReview.objects.create(
                reviewer=request.user,
                reviewer_role=request.user.role,
                subject_type=OversightSubject.VERIFICATION,
                review_status=OversightReviewStatus.REVERIFICATION_REQUESTED,
                project=report.project,
                verification_task=task,
                verification_round=task.verification_round - 1,
                comment=reason,
                action_required='Field re-verification of the installation.',
                follow_up_status=OversightFollowUpStatus.OPEN,
            )
        log_audit(request.user, 'reverification_requested', task, {
            'old_status': previous_status, 'new_status': task.status, 'round': task.verification_round,
            'reason': reason[:300], 'module': 'field_verification',
        })
        requester = request.user.full_name or request.user.username
        recipients = list(User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username'))
        if task.assigned_verifier_id:
            recipients.append(task.assigned_verifier)
        Notification.objects.bulk_create([
            Notification(
                recipient_id=str(user.id),
                recipient_name=user.full_name or user.username,
                type=NotificationChannel.IN_APP,
                event='verification_reverification_requested',
                title=f'Re-verification required: installation #{report.id}',
                body=f'{requester} requested re-verification of {report.serial_number or report.id}: {reason[:200]}',
                status=NotificationStatus.SENT,
                linked_entity_id=str(report.id),
            )
            for user in recipients
        ], ignore_conflicts=True)
        refresh_project_kpis(str(report.project_id))
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        if request.user.role not in self.VERIFY_ROLES:
            raise PermissionDenied('You do not have permission to verify installations.')
        task = self.get_object()
        if request.user.role == UserRole.FIELD_VERIFIER:
            assigned_districts = [d.lower() for d in field_verifier_districts(request.user)]
            task_district = (
                task.report.district or task.report.project.district or task.report.project.region or ''
            ).strip().lower()
            if task_district and task_district not in assigned_districts:
                raise PermissionDenied('You can only verify installations in your assigned district.')
        if task.status == VerificationStatus.PAUSED:
            return Response({'detail': 'Field verification is paused while the vendor is under suspension.'}, status=status.HTTP_400_BAD_REQUEST)
        if task.status == VerificationStatus.TERMINATED:
            return Response({'detail': 'Field verification was terminated for this vendor. Only new logs may resume after reinstatement.'}, status=status.HTTP_400_BAD_REQUEST)
        if task.status not in self.VERIFIABLE_STATUSES:
            return Response(
                {'detail': 'This verification has already been submitted and is locked. A reviewer must request re-verification first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reverification_round = task.status == VerificationStatus.REVERIFICATION_REQUIRED
        if is_vendor_restricted(task.report.vendor):
            detail = (
                'Field verification is paused while the vendor is under suspension.'
                if task.report.vendor.status == 'Suspended'
                else 'Field verification was terminated for this blacklisted vendor.'
            )
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
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

        beneficiary_present = str(request.data.get('beneficiary_present') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        system_working = str(request.data.get('system_working') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        serial_visible = str(request.data.get('serial_visible') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        beneficiary_gender = str(request.data.get('beneficiary_gender') or 'unknown').strip().lower() or 'unknown'
        if beneficiary_gender not in {choice for choice, _label in BeneficiaryGender.choices}:
            beneficiary_gender = BeneficiaryGender.UNKNOWN
        observation_notes = str(request.data.get('observation_notes') or '').strip()
        flag_reason = str(request.data.get('flag_reason') or '').strip()
        household_type = str(request.data.get('household_type') or '').strip()
        valid_household_types = {'standard', 'female_headed', 'vulnerable', 'low_income'}
        if household_type and household_type.lower() not in valid_household_types:
            household_type = ''
        if len(observation_notes) > 500:
            return Response({'detail': 'observation_notes must be 500 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        distance = haversine(float(task.vendor_lat), float(task.vendor_lng), verifier_lat, verifier_lng)
        location_match = distance <= 50
        requested_status = str(request.data.get('verification_status') or '').strip().lower()
        
        nearest_distance = None
        concern_message = None
        
        if distance <= 50:
            nearby_installations = InstallationReport.objects.filter(
                project_id=task.report.project_id,
                status__in=[InstallationStatus.SUBMITTED, InstallationStatus.VERIFIED]
            ).exclude(id=task.report_id)
            
            for other in nearby_installations:
                if other.gps_lat and other.gps_lng:
                    d = haversine(float(task.vendor_lat), float(task.vendor_lng), float(other.gps_lat), float(other.gps_lng))
                    if nearest_distance is None or d < nearest_distance:
                        nearest_distance = d
            
            if nearest_distance and nearest_distance > 500:
                concern_message = f'This installation is {nearest_distance:.0f}m from the nearest installation in this project. Please verify carefully.'
        
        if requested_status == 'partial':
            next_status = VerificationStatus.PARTIAL
            verification_record_status = FieldVerificationStatus.PARTIAL
        elif requested_status == 'flagged':
            next_status = VerificationStatus.FLAGGED
            verification_record_status = FieldVerificationStatus.FLAGGED
        elif requested_status == 'verified':
            next_status = VerificationStatus.VERIFIED
            verification_record_status = FieldVerificationStatus.VERIFIED
        else:
            next_status = VerificationStatus.FLAGGED if distance > 50 else VerificationStatus.VERIFIED
            verification_record_status = FieldVerificationStatus.FLAGGED if distance > 50 else FieldVerificationStatus.VERIFIED

        if not location_match and next_status == VerificationStatus.VERIFIED:
            next_status = VerificationStatus.FLAGGED
            verification_record_status = FieldVerificationStatus.FLAGGED
            flag_reason = f'Location mismatch: {distance:.2f}m'
        if next_status in {VerificationStatus.FLAGGED, VerificationStatus.PARTIAL} and not flag_reason:
            return Response({'detail': 'flag_reason is required when verification is flagged or partial.'}, status=status.HTTP_400_BAD_REQUEST)
        anomaly = next_status in {VerificationStatus.FLAGGED, VerificationStatus.PARTIAL}

        photo_paths: list[str] = []
        files = request.FILES.getlist('site_photos')
        if len(files) > 5:
            return Response({'detail': 'You can upload at most 5 site photos.'}, status=status.HTTP_400_BAD_REQUEST)
        for file in files:
            if file.size > 5 * 1024 * 1024:
                return Response({'detail': f'{file.name} exceeds the 5MB upload limit.'}, status=status.HTTP_400_BAD_REQUEST)
            extension = file.name.rsplit('.', 1)[-1] if '.' in file.name else 'jpg'
            saved = default_storage.save(f'field_verifications/{uuid.uuid4().hex}.{extension}', file)
            photo_paths.append(saved)

        field_verification = FieldVerification.objects.create(
            installation=task.report,
            field_officer=request.user,
            beneficiary_present=beneficiary_present,
            beneficiary_gender=beneficiary_gender,
            system_working=system_working,
            officer_latitude=verifier_lat,
            officer_longitude=verifier_lng,
            location_match=location_match,
            location_distance_meters=distance,
            site_photos=photo_paths,
            serial_visible=serial_visible,
            observation_notes=observation_notes,
            verification_status=verification_record_status,
            flag_reason=flag_reason or None,
            verification_round=task.verification_round,
            verified_at=timezone.now(),
        )
        if reverification_round:
            OversightReview.objects.filter(
                verification_task=task,
                review_status=OversightReviewStatus.REVERIFICATION_REQUESTED,
                follow_up_status__in=[OversightFollowUpStatus.OPEN, OversightFollowUpStatus.IN_PROGRESS],
            ).update(
                follow_up_status=OversightFollowUpStatus.RESOLVED,
                resolved_by=request.user,
                resolved_at=timezone.now(),
                resolution_note=f'Re-verified in round {task.verification_round}: {verification_record_status}.',
            )

        task.verifier_lat = verifier_lat
        task.verifier_lng = verifier_lng
        task.distance_meters = distance
        task.anomaly_flag = anomaly
        task.status = next_status
        task.save(update_fields=['verifier_lat', 'verifier_lng', 'distance_meters', 'anomaly_flag', 'status', 'updated_at'])

        report = task.report
        if household_type:
            report.household_type = household_type
        if next_status == VerificationStatus.VERIFIED:
            report.status = InstallationStatus.VERIFIED
            report.gis_status = GisStatus.GREEN
            report.anomaly_flags.filter(flag_type__in=['verification_distance', 'location_mismatch'], is_resolved=False).update(
                is_resolved=True,
                status=AnomalyFlagStatus.RESOLVED,
                resolved_at=timezone.now(),
            )
        elif next_status == VerificationStatus.FLAGGED:
            report.status = InstallationStatus.FLAGGED
            report.gis_status = GisStatus.RED
            AnomalyFlag.objects.create(
                installation=report,
                project=report.project,
                flag_type='location_mismatch' if not location_match else 'verification_distance',
                description=(
                    f'{flag_reason or "Field verification detected a GPS mismatch."} '
                    f'Verifier distance: {distance:.2f}m (allowed maximum: 50m). '
                    f'Vendor GPS: ({float(task.vendor_lat):.6f}, {float(task.vendor_lng):.6f}); '
                    f'Verifier GPS: ({verifier_lat:.6f}, {verifier_lng:.6f}); '
                    f'checked {timezone.localtime().strftime("%Y-%m-%d %H:%M %Z")}. '
                    f'Investigate whether the installation location and field visit are valid.'
                ),
            )
        else:
            report.status = InstallationStatus.SUBMITTED
            report.gis_status = GisStatus.YELLOW
        report.save(update_fields=['status', 'gis_status', 'household_type'])
        queue_installation_sync(str(report.id), include_customer=False, include_installation=True)
        log_audit(
            request.user,
            'installation_verified',
            report,
            {
                'distance_meters': distance,
                'anomaly': anomaly,
                'installation_id': str(report.id),
                'outcome': verification_record_status,
                'actor_id': str(request.user.id),
                'module': 'field_verification',
            },
        )
        create_project_activity_update(
            report.project,
            request.user,
            'Installation Verification Completed',
            f"Installation report {report.id} was {str(next_status).lower()} after field verification.",
        )
        Notification.objects.get_or_create(
            recipient_id=str(report.vendor_id),
            event='installation_verification_vendor',
            linked_entity_id=str(report.id),
            defaults={
                'recipient_name': report.vendor.full_name or report.vendor.username,
                'type': NotificationChannel.IN_APP,
                'title': f'Installation #{report.id} {verification_record_status}',
                'body': f'Installation #{report.id} was {verification_record_status} by the field officer.',
                'status': NotificationStatus.SENT,
            },
        )
        district_name = report.district or report.project.district or report.project.region or ''
        project_areas = {value.lower() for value in (report.project.region, report.project.district) if value}
        oversight_users = User.objects.filter(
            Q(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN})
            | (Q(role=UserRole.DOE_OFFICER) & Q(region__iregex=r'^(' + '|'.join(re.escape(area) for area in project_areas) + r')$'))
            if project_areas else Q(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN})
        ).only('id', 'full_name', 'username')
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient_id=str(user.id),
                    recipient_name=user.full_name or user.username,
                    type=NotificationChannel.IN_APP,
                    event='installation_verification_rmt',
                    title=f'Installation #{report.id} verified by field officer',
                    body=(
                        f'Installation #{report.id} was {verification_record_status} by '
                        f'{request.user.full_name or request.user.username} in {district_name}.'
                    ),
                    status=NotificationStatus.SENT,
                    linked_entity_id=str(report.id),
                )
                for user in oversight_users
            ],
            ignore_conflicts=True,
        )
        if concern_message:
            Notification.objects.get_or_create(
                recipient_id=str(report.vendor_id),
                event='verification_concern',
                linked_entity_id=str(report.id),
                defaults={
                    'recipient_name': report.vendor.full_name or report.vendor.username,
                    'type': NotificationChannel.IN_APP,
                    'title': 'Installation Location Concern',
                    'body': concern_message,
                    'status': NotificationStatus.SENT,
                },
            )
        refresh_project_kpis(str(report.project_id))
        payload = self.get_serializer(task).data
        payload['field_verification'] = FieldVerificationSerializer(field_verification, context={'request': request}).data
        if concern_message:
            payload['concern_message'] = concern_message
        return Response(payload, status=status.HTTP_200_OK)


class MapInstallationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = apply_installation_map_filters(build_installation_map_queryset(request.user), request.query_params)
        queryset = archived_scope(request, queryset, 'project__', ('project', 'project_id'))
        summary = queryset.aggregate(
            total=Count('id'),
            verified=Count('id', filter=Q(verification_task__status=VerificationStatus.VERIFIED)),
            pending=Count(
                'id',
                filter=Q(verification_task__status__isnull=True)
                | Q(verification_task__status=VerificationStatus.PENDING)
                | Q(verification_task__status=VerificationStatus.PARTIAL),
            ),
            flagged=Count('id', filter=Q(verification_task__status=VerificationStatus.FLAGGED)),
        )
        records = list(
            queryset.order_by('-installation_date', '-submitted_at').values(
                'id',
                'project_id',
                'gis_status',
                'verification_status',
                'technology_type',
                'household_type',
                'vendor_name',
                'beneficiary_name',
                'serial_number',
                'installation_date',
                'uptime_pct',
                'district_name',
                project_vendor_id=F('project__vendor_id'),
                project_vendor_name=F('project__vendor_name'),
                latitude=F('gps_lat'),
                longitude=F('gps_lng'),
            )[:1000]
        )
        # `district` is a model field, so values() cannot alias the annotation to it.
        for record in records:
            record['district'] = record.pop('district_name')
        vendor_keys = {
            str(record.get('project_vendor_id') or '').strip()
            for record in records
            if str(record.get('project_vendor_id') or '').strip()
        }
        numeric_vendor_ids = [int(key) for key in vendor_keys if key.isdigit()]
        vendor_users = User.objects.filter(
            Q(id__in=numeric_vendor_ids) | Q(username__in=list(vendor_keys))
        ).only('id', 'username', 'organization_name', 'full_name')
        vendor_name_lookup: dict[str, str] = {}
        for vendor_user in vendor_users:
            resolved_name = (
                vendor_user.organization_name
                or vendor_user.full_name
                or ''
            )
            if not resolved_name:
                continue
            vendor_name_lookup[str(vendor_user.id)] = resolved_name
            if vendor_user.username:
                vendor_name_lookup[vendor_user.username] = resolved_name
        for record in records:
            record['latitude'] = float(record['latitude'])
            record['longitude'] = float(record['longitude'])
            if record.get('uptime_pct') is not None:
                record['uptime_pct'] = float(record['uptime_pct'])
            vendor_key = str(record.pop('project_vendor_id', '') or '').strip()
            cached_vendor_name = str(record.pop('project_vendor_name', '') or '').strip()
            resolved_vendor_name = vendor_name_lookup.get(vendor_key) or cached_vendor_name or record.get('vendor_name') or ''
            record['vendor_name'] = resolved_vendor_name
        return Response(
            {
                'success': True,
                'data': {
                    'installations': records,
                    'summary': summary,
                },
                'truncated': summary['total'] > 1000,
            }
        )


class MapBoundaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        path = GpsValidator._geojson_path()
        if not path.exists():
            raise Http404('Lesotho boundary file has not been downloaded yet.')
        return FileResponse(path.open('rb'), content_type='application/geo+json')


class SmartMeterReadingViewSet(ArchiveScopedListMixin, viewsets.ModelViewSet):
    queryset = SmartMeterReading.objects.select_related('project', 'batch', 'submitted_by').all()
    # Readings are evidence for KPI and payment decisions: they are never edited or
    # deleted in place. Wrong data is rejected through the meter data batch review.
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = SmartMeterReadingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'meter_id']
    search_fields = ['meter_id']
    ordering_fields = ['recorded_at']

    WRITE_ROLES = {UserRole.VENDOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN}

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
        data = request.data.copy()
        installation_id = str(data.get('installation') or '').strip()
        installation = None
        if installation_id:
            installation = InstallationReport.objects.select_related('project').filter(id=installation_id).first()
            if not installation:
                return Response({'detail': 'installation not found.'}, status=status.HTTP_400_BAD_REQUEST)
            data['project'] = installation.project_id
            data.setdefault('meter_id', installation.meter_id)
        if request.user.role == UserRole.VENDOR:
            assert_user_not_blacklisted_for_writes(
                request.user,
                'Your vendor account is suspended or blacklisted. Meter data submission is restricted.',
            )
            project_id = str(data.get('project') or '')
            if not Project.objects.filter(id=project_id).filter(vendor_query_filter(request.user)).exists():
                raise PermissionDenied('You can only submit meter readings for your own projects.')
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        reading = serializer.save(installation=installation, source=SmartMeterReadingSource.API, submitted_by=request.user)
        refresh_project_kpis(str(reading.project_id))
        return Response(self.get_serializer(reading).data, status=status.HTTP_201_CREATED)


class MeterDataBatchViewSet(ArchiveScopedListMixin, viewsets.ReadOnlyModelViewSet):
    """Vendor meter-data uploads, and the RBF Official / Super Admin review of whether
    they are genuine: verify, reject (whole batch or single readings), or send back for
    correction. Rejected readings stop counting toward KPIs and milestone eligibility."""

    queryset = MeterDataBatch.objects.select_related(
        'project', 'uploaded_by', 'reviewed_by', 'source_document'
    ).prefetch_related('readings')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'status']
    ordering_fields = ['created_at']

    REVIEW_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    OPEN_STATUSES = {MeterDataBatchStatus.PENDING_REVIEW, MeterDataBatchStatus.FLAGGED, MeterDataBatchStatus.VERIFIED}

    def get_serializer_class(self):
        return MeterDataBatchDetailSerializer if self.action != 'list' else MeterDataBatchSerializer

    def get_queryset(self):
        qs = self.queryset.order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor_query_filter(user, prefix='project__'))
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(field_verifier_district_filter(user)).distinct()
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
        return qs

    def _assert_reviewer(self):
        if self.request.user.role not in self.REVIEW_ROLES:
            raise PermissionDenied('Only the RBF Management Team or the Super Admin can review meter data.')

    def _required_text(self, field: str, label: str) -> str:
        value = str(self.request.data.get(field) or '').strip()
        if not value:
            raise ValidationError({field: f'{label} is required.'})
        return value

    def _reading_ids(self, batch: MeterDataBatch) -> list[int]:
        raw = self.request.data.get('reading_ids')
        if hasattr(self.request.data, 'getlist') and not isinstance(raw, list):
            raw = self.request.data.getlist('reading_ids')
        try:
            ids = sorted({int(value) for value in (raw or [])})
        except (TypeError, ValueError):
            raise ValidationError({'reading_ids': 'reading_ids must be a list of reading ids.'})
        if not ids:
            raise ValidationError({'reading_ids': 'Select at least one reading.'})
        found = set(batch.readings.filter(id__in=ids).values_list('id', flat=True))
        missing = [value for value in ids if value not in found]
        if missing:
            raise ValidationError({'reading_ids': f'Readings {missing} are not part of this upload.'})
        return ids

    def _finish(self, batch: MeterDataBatch, *, action: str, vendor_title: str, vendor_body: str, details: dict):
        batch.reviewed_by = self.request.user
        batch.reviewed_at = timezone.now()
        batch.save()
        project = batch.project
        log_audit(self.request.user, f'meter_data_batch_{action}', project, {
            'meter_data_batch_id': batch.id,
            'status': batch.status,
            **details,
        })
        create_project_activity_update(project, self.request.user, vendor_title, vendor_body)
        vendor = User.objects.filter(id=str(project.vendor_id or '')).only('id', 'full_name', 'username').first() if str(project.vendor_id or '').isdigit() else None
        if vendor:
            Notification.objects.create(
                recipient_id=str(vendor.id),
                recipient_name=vendor.full_name or vendor.username,
                type=NotificationChannel.IN_APP,
                event=f'meter_data_batch_{action}',
                title=vendor_title,
                body=vendor_body,
                status=NotificationStatus.SENT,
                linked_entity_id=str(project.id),
            )
        refresh_project_kpis(str(project.id))
        batch.refresh_from_db()
        return Response(MeterDataBatchDetailSerializer(batch, context={'request': self.request}).data)

    def _label(self, batch: MeterDataBatch) -> str:
        return f'meter upload #{batch.id} ({batch.file_name or "CSV"}) for project {batch.project.project_reference or batch.project_id}'

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        self._assert_reviewer()
        batch = self.get_object()
        if batch.status not in {MeterDataBatchStatus.PENDING_REVIEW, MeterDataBatchStatus.FLAGGED}:
            raise ValidationError({'detail': f'An upload that is {batch.get_status_display().lower()} cannot be verified.'})
        notes = str(request.data.get('notes') or '').strip()
        if batch.status == MeterDataBatchStatus.FLAGGED and not notes:
            raise ValidationError({'notes': 'Explain why the failed integrity checks are acceptable before verifying.'})
        batch.status = MeterDataBatchStatus.VERIFIED
        batch.review_notes = notes
        return self._finish(
            batch,
            action='verified',
            vendor_title='Meter Data Verified',
            vendor_body=f'RBF verified {self._label(batch)}.' + (f' Notes: {notes}' if notes else ''),
            details={'notes': notes},
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        self._assert_reviewer()
        batch = self.get_object()
        if batch.status not in self.OPEN_STATUSES:
            raise ValidationError({'detail': f'An upload that is {batch.get_status_display().lower()} cannot be rejected.'})
        reason = self._required_text('reason', 'A rejection reason')
        rejected = batch.readings.exclude(review_status=SmartMeterReadingReviewStatus.REJECTED).update(
            review_status=SmartMeterReadingReviewStatus.REJECTED,
            rejection_reason=reason,
        )
        batch.status = MeterDataBatchStatus.REJECTED
        batch.review_notes = reason
        return self._finish(
            batch,
            action='rejected',
            vendor_title='Meter Data Rejected',
            vendor_body=f'RBF rejected {self._label(batch)}; its {batch.rows_ingested} readings no longer count toward KPIs or milestones. Reason: {reason}',
            details={'reason': reason, 'readings_rejected': rejected},
        )

    @action(detail=True, methods=['post'], url_path='request-correction')
    def request_correction(self, request, pk=None):
        self._assert_reviewer()
        batch = self.get_object()
        if batch.status not in self.OPEN_STATUSES:
            raise ValidationError({'detail': f'An upload that is {batch.get_status_display().lower()} cannot be sent back for correction.'})
        reason = self._required_text('reason', 'What must be corrected')
        due_raw = str(request.data.get('due_date') or '').strip()
        due_date = None
        if due_raw:
            try:
                due_date = timezone.datetime.fromisoformat(due_raw).date()
            except ValueError:
                raise ValidationError({'due_date': 'Use a YYYY-MM-DD date.'})
        batch.readings.exclude(review_status=SmartMeterReadingReviewStatus.REJECTED).update(
            review_status=SmartMeterReadingReviewStatus.REJECTED,
            rejection_reason=f'Correction requested: {reason}',
        )
        batch.status = MeterDataBatchStatus.CORRECTION_REQUESTED
        batch.review_notes = reason
        batch.correction_due_date = due_date
        due_text = f' Upload corrected data by {due_date:%Y-%m-%d}.' if due_date else ' Upload corrected data.'
        return self._finish(
            batch,
            action='correction_requested',
            vendor_title='Meter Data Correction Requested',
            vendor_body=(
                f'RBF sent back {self._label(batch)} for correction: {reason}.{due_text} '
                'Milestone claims for this project are blocked until you upload a corrected file.'
            ),
            details={'reason': reason, 'due_date': due_raw},
        )

    @action(detail=True, methods=['post'], url_path='reject-readings')
    def reject_readings(self, request, pk=None):
        self._assert_reviewer()
        batch = self.get_object()
        if batch.status not in self.OPEN_STATUSES:
            raise ValidationError({'detail': f'Readings of an upload that is {batch.get_status_display().lower()} cannot be changed.'})
        ids = self._reading_ids(batch)
        reason = self._required_text('reason', 'A rejection reason')
        batch.readings.filter(id__in=ids).update(
            review_status=SmartMeterReadingReviewStatus.REJECTED,
            rejection_reason=reason,
        )
        return self._finish(
            batch,
            action='readings_rejected',
            vendor_title='Meter Readings Rejected',
            vendor_body=f'RBF rejected {len(ids)} reading(s) in {self._label(batch)}. Reason: {reason}',
            details={'reason': reason, 'reading_ids': ids},
        )

    @action(detail=True, methods=['post'], url_path='restore-readings')
    def restore_readings(self, request, pk=None):
        self._assert_reviewer()
        batch = self.get_object()
        if batch.status not in self.OPEN_STATUSES:
            raise ValidationError({'detail': f'Readings of an upload that is {batch.get_status_display().lower()} cannot be changed.'})
        ids = self._reading_ids(batch)
        notes = self._required_text('notes', 'A reason for restoring the readings')
        batch.readings.filter(id__in=ids).update(
            review_status=SmartMeterReadingReviewStatus.ACCEPTED,
            rejection_reason='',
        )
        return self._finish(
            batch,
            action='readings_restored',
            vendor_title='Meter Readings Restored',
            vendor_body=f'RBF restored {len(ids)} previously rejected reading(s) in {self._label(batch)}. Notes: {notes}',
            details={'notes': notes, 'reading_ids': ids},
        )


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('actor').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['action', 'entity_type', 'record_type', 'record_id', 'entity_id']
    search_fields = ['action', 'entity_type', 'entity_id']
    ordering_fields = ['created_at']

    def get_queryset(self):
        user = self.request.user
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR}:
            queryset = self.queryset
        elif user.role == UserRole.VENDOR:
            project_ids = [int(pid) for pid in Project.objects.filter(vendor_query_filter(user)).values_list('id', flat=True)]
            claim_ids = [str(cid) for cid in PaymentClaim.objects.filter(vendor=user).values_list('id', flat=True)]
            queryset = self.queryset.filter(
                Q(record_type='project', record_id__in=project_ids) |
                Q(details__project_id__in=[str(pid) for pid in project_ids]) |
                Q(entity_type='Project', entity_id__in=[str(pid) for pid in project_ids]) |
                Q(entity_type='PaymentClaim', entity_id__in=claim_ids) |
                Q(actor=user)
            )
        else:
            queryset = self.queryset.filter(actor=user)

        actor = str(self.request.query_params.get('actor') or '').strip()
        actor_role = str(self.request.query_params.get('actor_role') or '').strip()
        module = str(self.request.query_params.get('module') or '').strip()
        date_from = str(self.request.query_params.get('date_from') or '').strip()
        date_to = str(self.request.query_params.get('date_to') or '').strip()

        if actor:
            queryset = queryset.filter(Q(actor__username__icontains=actor) | Q(actor__full_name__icontains=actor))
        if actor_role:
            queryset = queryset.filter(actor_role__iexact=actor_role)
        if module:
            queryset = queryset.filter(module__iexact=module)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-created_at')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Actor', 'Role', 'Action', 'Module', 'Record', 'Old Status', 'New Status', 'Notes'])
        for log in queryset:
            writer.writerow([
                timezone.localtime(log.created_at).isoformat(),
                (log.actor.full_name or log.actor.username) if log.actor else 'System',
                log.actor_role,
                log.action,
                log.module,
                log.entity_id or log.record_id or '',
                log.old_status,
                log.new_status,
                log.notes,
            ])
        return response

    @action(detail=False, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request):
        queryset = list(self.filter_queryset(self.get_queryset()).order_by('-created_at')[:500])
        from html import escape as esc

        rows = ''.join(
            (
                '<tr>'
                f'<td>{timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M")}</td>'
                f'<td>{esc((log.actor.full_name or log.actor.username) if log.actor else "System")}</td>'
                f'<td>{esc(log.actor_role)}</td>'
                f'<td>{esc(log.action)}</td>'
                f'<td>{esc(log.module)}</td>'
                f'<td>{esc(str(log.entity_id or log.record_id or ""))}</td>'
                f'<td>{esc(log.old_status)}</td>'
                f'<td>{esc(log.new_status)}</td>'
                f'<td>{esc(log.notes)}</td>'
                '</tr>'
            )
            for log in queryset
        )
        html = f"""
        <html>
          <head>
            <style>
              body {{ font-family: Arial, sans-serif; color: #0f172a; margin: 0; padding: 24px; }}
              h1 {{ margin: 0 0 8px; font-size: 24px; }}
              p {{ color: #475569; font-size: 12px; margin: 0 0 16px; }}
              table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
              th, td {{ border: 1px solid #cbd5e1; padding: 6px; text-align: left; vertical-align: top; }}
              th {{ background: #e2e8f0; }}
            </style>
          </head>
          <body>
            <h1>Audit Logs Export</h1>
            <p>Generated at {timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")}</p>
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Actor</th>
                  <th>Role</th>
                  <th>Action</th>
                  <th>Module</th>
                  <th>Record</th>
                  <th>Old Status</th>
                  <th>New Status</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>{rows or '<tr><td colspan="9">No audit logs matched the selected filters.</td></tr>'}</tbody>
            </table>
          </body>
        </html>
        """
        from rbf.tenders.pba_pdf import _render_pdf

        tmp_dir = Path(tempfile.mkdtemp(prefix='audit_logs_pdf_'))
        output_path = tmp_dir / f'audit_logs_{timezone.localdate().isoformat()}.pdf'
        from .report_pdf import report_footer, report_header

        _render_pdf(html, output_path, 'audit-logs', header_template=report_header('Audit Logs'),
                    footer_template=report_footer(request.user.full_name or request.user.username))
        return FileResponse(output_path.open('rb'), as_attachment=True, filename=output_path.name)


class ProspectSyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProspectSyncLog.objects.all()
    serializer_class = ProspectSyncLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['method_name', 'status']
    search_fields = ['method_name', 'error_message']
    ordering_fields = ['created_at', 'updated_at', 'attempts']

    def get_queryset(self):
        user = self.request.user
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR}:
            return self.queryset.order_by('-created_at')
        return self.queryset.none()

    @action(detail=False, methods=['post'], url_path='refresh-panel')
    def refresh_panel(self, request):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR}:
            raise PermissionDenied('You do not have permission to refresh the Prospect sync panel.')

        filters_payload: dict[str, str | int] = {}
        project_id = str(request.data.get('project_id') or '').strip()
        if project_id:
            filters_payload['reporting_phase'] = f'PRJ-{project_id}'
        for field_name in ('country', 'program', 'external_id'):
            value = str(request.data.get(field_name) or '').strip()
            if value:
                filters_payload[field_name] = value
        for field_name in ('size', 'page'):
            raw_value = request.data.get(field_name)
            if raw_value not in (None, ''):
                filters_payload[field_name] = int(raw_value)

        record_id = int(project_id) if project_id.isdigit() else None
        SyncToProspectJob.dispatch_async('getInstallations', filters_payload, record_id=record_id, record_type='sync_panel')
        SyncToProspectJob.dispatch_async('getTargets', filters_payload, record_id=record_id, record_type='sync_panel')
        return Response(
            {
                'status': 'queued',
                'queued_methods': ['getInstallations', 'getTargets'],
                'filters': filters_payload,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.UNDP_DONOR}:
            raise PermissionDenied('You do not have permission to view the Prospect sync summary.')

        def _latest_sync(method_names: set[str]):
            return (
                ProspectSyncLog.objects
                .filter(method_name__in=method_names, status=ProspectSyncStatus.SUCCESS)
                .order_by('-updated_at')
                .first()
            )

        installation_latest = _latest_sync({'pushInstallation', 'getInstallations'})
        target_latest = _latest_sync({'pushTarget', 'getTargets'})
        agent_latest = _latest_sync({'pushAgent'})
        failed_jobs = ProspectSyncLog.objects.filter(status=ProspectSyncStatus.FAILED).count()

        our_installation_count = InstallationReport.objects.count()
        our_target_count = Project.objects.count() * 3
        agent_count = User.objects.exclude(role=UserRole.VENDOR).count()

        prospect_installation_count = 0
        prospect_target_count = 0
        prospect_error = None

        try:
            from rbf.projects.integrations import ProspectService
            service = ProspectService.from_settings()
            installations = service.getInstallations(size=1, page=1)
            prospect_installation_count = installations.get('total', len(installations.get('data', [])))
        except Exception as e:
            prospect_error = str(e)
            logger.warning(f'Failed to get installations from Prospect: {e}')

        try:
            from rbf.projects.integrations import ProspectService
            service = ProspectService.from_settings()
            targets = service.getTargets(size=1, page=1)
            prospect_target_count = targets.get('total', len(targets.get('data', [])))
        except Exception as e:
            if not prospect_error:
                prospect_error = str(e)
            logger.warning(f'Failed to get targets from Prospect: {e}')

        installations_synced = ProspectSyncLog.objects.filter(
            method_name='pushInstallation', status=ProspectSyncStatus.SUCCESS
        ).count()
        targets_synced = ProspectSyncLog.objects.filter(
            method_name='pushTarget', status=ProspectSyncStatus.SUCCESS
        ).count()

        payload = {
            'failed_jobs': failed_jobs,
            'last_sync_at': max(
                [log.updated_at for log in [installation_latest, target_latest, agent_latest] if log is not None],
                default=None,
            ),
            'rows': [
                {
                    'data_type': 'Installations',
                    'our_count': our_installation_count,
                    'prospect_count': prospect_installation_count if prospect_installation_count > 0 else -1,
                    'match': prospect_installation_count > 0 and our_installation_count == prospect_installation_count,
                    'last_sync': installation_latest.updated_at.isoformat() if installation_latest else None,
                    'note': f'Successfully synced {installations_synced} installations to Prospect' if prospect_installation_count > 0 else f'Prospect API unavailable. {installations_synced} installations synced to Prospect so far.',
                },
                {
                    'data_type': 'Targets',
                    'our_count': our_target_count,
                    'prospect_count': prospect_target_count if prospect_target_count > 0 else -1,
                    'match': prospect_target_count > 0 and our_target_count == prospect_target_count,
                    'last_sync': target_latest.updated_at.isoformat() if target_latest else None,
                    'note': f'Successfully synced {targets_synced} target records to Prospect' if prospect_target_count > 0 else f'Prospect API unavailable. {targets_synced} target records synced to Prospect so far.',
                },
                {
                    'data_type': 'Agents',
                    'our_count': agent_count,
                    'prospect_count': agent_count,
                    'match': True,
                    'last_sync': agent_latest.updated_at.isoformat() if agent_latest else None,
                    'note': 'Agent sync status is derived from the latest successful pushAgent jobs.',
                },
            ],
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='projects-summary')
    def projects_summary(self, request):
        if request.user.role not in {
            UserRole.ADMIN,
            UserRole.RBF_OFFICIAL,
            UserRole.AUDITOR,
            UserRole.UNDP_DONOR,
        }:
            raise PermissionDenied('You do not have permission to view the projects summary.')

        total = Project.objects.count()
        active = Project.objects.filter(status=ProjectStatus.ACTIVE).count()
        completed = Project.objects.filter(status=ProjectStatus.COMPLETED).count()
        at_risk = Project.objects.filter(status=ProjectStatus.HALTED).count()

        return Response({
            'total': total,
            'active': active,
            'completed': completed,
            'at_risk': at_risk,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='check-connection')
    def check_connection(self, request):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}:
            raise PermissionDenied('You do not have permission to check Prospect connectivity.')
        base_url = getattr(settings, 'PROSPECT_BASE_URL', '')
        read_token = (
            getattr(settings, 'PROSPECT_READ_TOKEN', '')
            or getattr(settings, 'PROSPECT_TOKEN_OUT_INSTALLATIONS', '')
            or getattr(settings, 'PROSPECT_TOKEN_OUT_TARGETS', '')
            or getattr(settings, 'PROSPECT_API_SECRET', '')
        )
        required_write_tokens = (
            getattr(settings, 'PROSPECT_TOKEN_IN_AGENTS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            getattr(settings, 'PROSPECT_TOKEN_IN_TARGETS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            getattr(settings, 'PROSPECT_TOKEN_IN_CUSTOMERS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            getattr(settings, 'PROSPECT_TOKEN_IN_INSTALLATIONS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            getattr(settings, 'PROSPECT_TOKEN_IN_INSTALLATIONS_TS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            getattr(settings, 'PROSPECT_TOKEN_IN_REPORTS', '') or getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
        )
        read_ok = bool(base_url and read_token)
        write_ok = bool(base_url and all(required_write_tokens))
        return Response(
            {
                'read_token_ok': read_ok,
                'write_token_ok': write_ok,
                'base_url': base_url,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}:
            raise PermissionDenied('You do not have permission to retry Prospect sync jobs.')
        log = self.get_object()
        SyncToProspectJob.dispatch_async(
            log.method_name,
            log.payload,
            record_id=log.record_id,
            record_type=log.record_type,
            log_id=log.id,
        )
        return Response({'status': 'queued', 'id': log.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='retry-failed')
    def retry_failed(self, request):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}:
            raise PermissionDenied('You do not have permission to retry Prospect sync jobs.')
        failed_logs = list(ProspectSyncLog.objects.filter(status=ProspectSyncStatus.FAILED).order_by('-updated_at'))
        for log in failed_logs:
            SyncToProspectJob.dispatch_async(
                log.method_name,
                log.payload,
                record_id=log.record_id,
                record_type=log.record_type,
                log_id=log.id,
            )
        return Response({'status': 'queued', 'count': len(failed_logs)}, status=status.HTTP_202_ACCEPTED)


ANOMALY_EVIDENCE_ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.pdf'}
ANOMALY_EVIDENCE_MAX_BYTES = 5 * 1024 * 1024


def _record_anomaly_review_event(*, flag: AnomalyFlag, user, from_status: str, to_status: str) -> AnomalyReviewEvent:
    return AnomalyReviewEvent.objects.create(
        flag=flag,
        actor=user if getattr(user, 'is_authenticated', False) else None,
        actor_role=getattr(user, 'role', '') or '',
        from_status=from_status or '',
        to_status=to_status or '',
        investigation_notes=flag.investigation_notes or '',
        corrective_action=flag.corrective_action or '',
        resolution_reason=flag.resolution_reason or '',
        evidence_reference=flag.evidence_reference or '',
    )


def _save_anomaly_evidence_files(*, flag: AnomalyFlag, user, files) -> tuple[list[AnomalyEvidenceFile], list[str]]:
    saved: list[AnomalyEvidenceFile] = []
    errors: list[str] = []
    for file in files or []:
        extension = os.path.splitext(str(file.name or ''))[1].lower()
        if extension not in ANOMALY_EVIDENCE_ALLOWED_EXTENSIONS:
            errors.append(f'{file.name}: only jpg, png, webp, and pdf files are accepted.')
            continue
        if file.size and file.size > ANOMALY_EVIDENCE_MAX_BYTES:
            errors.append(f'{file.name}: files must be 5 MB or smaller.')
            continue
        path = default_storage.save(f'anomaly_evidence/{uuid.uuid4().hex}{extension}', file)
        saved.append(AnomalyEvidenceFile.objects.create(
            flag=flag,
            file=path,
            original_name=str(file.name or '')[:256],
            uploaded_by=user if getattr(user, 'is_authenticated', False) else None,
        ))
    return saved, errors


def _notify_vendor_of_anomaly_review(flag: AnomalyFlag, *, event: str, title: str, body: str):
    vendor_id = str(getattr(flag.project, 'vendor_id', '') or '')
    if not vendor_id:
        return
    try:
        vendor = User.objects.only('id', 'full_name', 'username').get(id=vendor_id)
    except User.DoesNotExist:
        return
    Notification.objects.filter(
        recipient_id=str(vendor.id),
        event=event,
        linked_entity_id=str(flag.id),
    ).delete()
    Notification.objects.create(
        recipient_id=str(vendor.id),
        recipient_name=vendor.full_name or vendor.username,
        type=NotificationChannel.IN_APP,
        event=event,
        title=title,
        body=body,
        status=NotificationStatus.SENT,
        linked_entity_id=str(flag.id),
    )


class AnomalyFlagViewSet(ArchiveScopedListMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AnomalyFlag.objects.select_related('project', 'installation').all()
    serializer_class = AnomalyFlagSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'flag_type', 'is_resolved']
    search_fields = ['description', 'flag_type']
    ordering_fields = ['created_at', 'resolved_at']

    def get_queryset(self):
        qs = self.queryset.order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(project__vendor_id=str(user.id))
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(
                Q(installation__verification_task__assigned_verifier=user)
                | field_verifier_installation_filter(user, report_prefix='installation__')
                | (Q(installation__isnull=True) & field_verifier_district_filter(user))
            ).distinct()
        return qs

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RMT or Platform Administrator can resolve anomaly flags.')
        resolution_notes = str(request.data.get('resolution_notes') or '').strip()
        evidence_reference = str(request.data.get('evidence_reference') or '').strip()
        if not resolution_notes or not evidence_reference:
            return Response({'detail': 'Resolution notes and an evidence reference are required.'}, status=status.HTTP_400_BAD_REQUEST)
        flag = self.get_object()
        current_status = flag.status or (AnomalyFlagStatus.RESOLVED if flag.is_resolved else AnomalyFlagStatus.OPEN)
        if flag.is_resolved or current_status not in {AnomalyFlagStatus.UNDER_INVESTIGATION}:
            return Response(
                {'detail': 'Flags must be under investigation before they can be resolved. Start the investigation first.'},
                status=status.HTTP_409_CONFLICT,
            )
        previous_status = current_status
        flag.is_resolved = True
        flag.status = AnomalyFlagStatus.RESOLVED
        flag.assigned_to = request.user
        flag.investigation_notes = resolution_notes
        flag.resolution_reason = resolution_notes
        flag.evidence_reference = evidence_reference
        flag.resolved_at = timezone.now()
        flag.save(update_fields=['is_resolved', 'status', 'assigned_to', 'investigation_notes', 'resolution_reason', 'evidence_reference', 'resolved_at'])
        _record_anomaly_review_event(flag=flag, user=request.user, from_status=previous_status, to_status=flag.status)
        refresh_project_kpis(str(flag.project_id))
        log_audit(request.user, 'anomaly_flag_resolved', flag, {'project_id': str(flag.project_id), 'previous_status': previous_status})
        return Response(self.get_serializer(flag).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RMT or Platform Administrator can manage anomaly reviews.')

        flag = self.get_object()
        next_status = str(request.data.get('status') or '').strip()
        allowed_statuses = {choice.value for choice in AnomalyFlagStatus}
        if next_status not in allowed_statuses:
            return Response({'status': f'Use one of: {", ".join(sorted(allowed_statuses))}.'}, status=status.HTTP_400_BAD_REQUEST)

        notes = str(request.data.get('investigation_notes') or '').strip()
        resolution_reason = str(request.data.get('resolution_reason') or '').strip()
        current_status = flag.status or (AnomalyFlagStatus.RESOLVED if flag.is_resolved else AnomalyFlagStatus.OPEN)
        allowed_transitions = {
            AnomalyFlagStatus.OPEN: {AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.ESCALATED},
            AnomalyFlagStatus.REOPENED: {AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.ESCALATED},
            AnomalyFlagStatus.UNDER_INVESTIGATION: {AnomalyFlagStatus.CORRECTION_REQUESTED, AnomalyFlagStatus.AWAITING_EVIDENCE, AnomalyFlagStatus.RESOLVED, AnomalyFlagStatus.FALSE_POSITIVE, AnomalyFlagStatus.ESCALATED},
            AnomalyFlagStatus.CORRECTION_REQUESTED: {AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.AWAITING_EVIDENCE, AnomalyFlagStatus.RESOLVED, AnomalyFlagStatus.ESCALATED},
            AnomalyFlagStatus.AWAITING_EVIDENCE: {AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.RESOLVED, AnomalyFlagStatus.ESCALATED},
            AnomalyFlagStatus.RESOLVED: {AnomalyFlagStatus.REOPENED},
            AnomalyFlagStatus.FALSE_POSITIVE: {AnomalyFlagStatus.REOPENED},
            AnomalyFlagStatus.ESCALATED: {AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.REOPENED},
        }
        if next_status != current_status and next_status not in allowed_transitions.get(current_status, set()):
            return Response({'status': f'Cannot move an anomaly from {current_status} to {next_status}.'}, status=status.HTTP_400_BAD_REQUEST)
        if next_status == AnomalyFlagStatus.UNDER_INVESTIGATION and not notes:
            return Response({'detail': 'Investigation notes are required when starting or updating an investigation.'}, status=status.HTTP_400_BAD_REQUEST)
        if next_status == AnomalyFlagStatus.CORRECTION_REQUESTED and (not notes or not str(request.data.get('corrective_action') or '').strip() or not request.data.get('due_date')):
            return Response({'detail': 'Investigation notes, corrective action, and a due date are required when requesting correction.'}, status=status.HTTP_400_BAD_REQUEST)
        if next_status == AnomalyFlagStatus.AWAITING_EVIDENCE and not (notes or str(request.data.get('evidence_reference') or '').strip()):
            return Response({'detail': 'Investigation notes or an evidence request is required when awaiting evidence.'}, status=status.HTTP_400_BAD_REQUEST)
        if next_status in {AnomalyFlagStatus.RESOLVED, AnomalyFlagStatus.FALSE_POSITIVE}:
            required = {
                'investigation notes': notes,
                'corrective action': str(request.data.get('corrective_action') or '').strip(),
                'decision reason': resolution_reason,
                'evidence reference': str(request.data.get('evidence_reference') or '').strip(),
            }
            missing = [label for label, value in required.items() if not value]
            if missing:
                return Response({'detail': f'Required before final decision: {", ".join(missing)}.'}, status=status.HTTP_400_BAD_REQUEST)
        if next_status == AnomalyFlagStatus.ESCALATED and (not notes or not resolution_reason):
            return Response({'detail': 'Investigation notes and an escalation reason are required.'}, status=status.HTTP_400_BAD_REQUEST)
        due_date = request.data.get('due_date')
        if due_date:
            try:
                due_date = date.fromisoformat(str(due_date))
            except ValueError:
                return Response({'due_date': 'Use the YYYY-MM-DD format.'}, status=status.HTTP_400_BAD_REQUEST)

        previous_status = current_status
        evidence_files = list(request.FILES.getlist('evidence_files'))
        for file in evidence_files:
            extension = os.path.splitext(str(file.name or ''))[1].lower()
            if extension not in ANOMALY_EVIDENCE_ALLOWED_EXTENSIONS:
                return Response({'detail': f'{file.name}: only jpg, png, webp, and pdf files are accepted.'}, status=status.HTTP_400_BAD_REQUEST)
            if file.size and file.size > ANOMALY_EVIDENCE_MAX_BYTES:
                return Response({'detail': f'{file.name}: files must be 5 MB or smaller.'}, status=status.HTTP_400_BAD_REQUEST)
        update_fields = ['status', 'assigned_to', 'investigation_notes', 'corrective_action', 'resolution_reason', 'evidence_reference', 'due_date', 'is_resolved', 'resolved_at']
        flag.status = next_status
        flag.assigned_to = request.user
        if notes:
            flag.investigation_notes = notes
        for field in ('corrective_action', 'resolution_reason', 'evidence_reference'):
            if field in request.data:
                setattr(flag, field, str(request.data.get(field) or '').strip())
        if 'due_date' in request.data:
            flag.due_date = due_date or None
        flag.is_resolved = next_status in {AnomalyFlagStatus.RESOLVED, AnomalyFlagStatus.FALSE_POSITIVE}
        flag.resolved_at = timezone.now() if flag.is_resolved else None
        flag.save(update_fields=update_fields)
        _record_anomaly_review_event(flag=flag, user=request.user, from_status=previous_status, to_status=next_status)
        if evidence_files:
            _save_anomaly_evidence_files(flag=flag, user=request.user, files=evidence_files)
        project_ref = getattr(flag.project, 'project_reference', '') or str(flag.project_id)
        finding_title = (flag.description or flag.flag_type or 'anomaly')[:180]
        if next_status == AnomalyFlagStatus.CORRECTION_REQUESTED:
            _notify_vendor_of_anomaly_review(
                flag,
                event='anomaly_correction_requested',
                title='Corrective Action Requested',
                body=f'Project {project_ref}: RMT requested corrective action for {finding_title}. Due {flag.due_date or "soon"}.',
            )
        elif next_status == AnomalyFlagStatus.AWAITING_EVIDENCE:
            _notify_vendor_of_anomaly_review(
                flag,
                event='anomaly_evidence_requested',
                title='Additional Evidence Requested',
                body=f'Project {project_ref}: RMT is awaiting additional evidence for {finding_title}.',
            )
        refresh_project_kpis(str(flag.project_id))
        log_audit(request.user, 'anomaly_flag_reviewed', flag, {
            'project_id': str(flag.project_id),
            'previous_status': previous_status,
            'new_status': next_status,
            'resolution_reason': flag.resolution_reason,
        })
        return Response(self.get_serializer(flag).data, status=status.HTTP_200_OK)


def _get_kpi_project_for_user(user: User, project_id: str) -> Project:
    project = Project.objects.filter(id=project_id).first()
    if not project:
        raise Http404('Project not found.')
    if user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC, UserRole.UNDP_DONOR, UserRole.AUDITOR}:
        return project
    if user.role == UserRole.DOE_OFFICER:
        if Project.objects.filter(id=project_id).filter(doe_region_filter(user)).exists():
            return project
        raise PermissionDenied('You can only access KPI dashboards for projects in your region.')
    if user.role == UserRole.VENDOR:
        if Project.objects.filter(id=project_id).filter(vendor_query_filter(user)).exists():
            return project
        raise PermissionDenied('You can only access KPI dashboards for your own projects.')
    raise PermissionDenied('You do not have permission to access KPI dashboards.')


class ProjectKpiView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id: str):
        project = _get_kpi_project_for_user(request.user, project_id)
        summary = KpiService.for_project(str(project.id)).getFullKpiSummary()
        return Response(summary)


class ProjectKpiPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id: str):
        project = _get_kpi_project_for_user(request.user, project_id)
        summary = KpiService.for_project(str(project.id)).getFullKpiSummary()
        pdf_path = render_kpi_pdf(project, summary)
        return FileResponse(
            pdf_path.open('rb'),
            content_type='application/pdf',
            filename=f'KPI_Report_{project.id}_{timezone.localdate().isoformat()}.pdf',
            as_attachment=True,
        )


class PortfolioKpiView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {
            UserRole.RBF_OFFICIAL,
            UserRole.ADMIN,
            UserRole.UNDP_DONOR,
            UserRole.TAC,
            UserRole.DOE_OFFICER,
            UserRole.AUDITOR,
        }:
            raise PermissionDenied('You do not have permission to access the portfolio KPI dashboard.')
        return Response(KpiService.getPortfolioSummary(request.user))


class PublicPortfolioKpiView(APIView):
    permission_classes = []

    def get(self, request):
        return Response(KpiService.getPublicPortfolioSummary())


# --- Reports ------------------------------------------------------------------------
# Report definitions, data scope and rendering live in report_engine; generation runs in the
# background through report_queue. These views queue jobs and expose their results.

REPORT_HISTORY_ALL_ROLES = {UserRole.ADMIN, UserRole.AUDITOR}
REPORT_HISTORY_PAGE_SIZE = 25


def _report_row(report: GeneratedReport) -> dict:
    filters = report.filters or {}
    period = (
        f"{filters.get('from') or 'start'} to {filters.get('to') or 'today'}"
        if (filters.get('from') or filters.get('to')) else 'Programme to date'
    )
    applied = [f'{key}: {filters[key]}' for key in ('district', 'technology', 'vendor', 'tender') if filters.get(key)]
    return {
        'id': str(report.id),
        'reportType': report.report_type,
        'title': report.title or report.report_type,
        'status': report.status,
        'error': report.error,
        'rowCount': report.row_count,
        'project': report.project.project_reference if report.project else '',
        'period': period,
        'filters': ', '.join(applied),
        'generatedBy': (report.generated_by.full_name or report.generated_by.username) if report.generated_by else '',
        'generatedAt': timezone.localtime(report.generated_at).isoformat(),
        'completedAt': timezone.localtime(report.completed_at).isoformat() if report.completed_at else None,
        'format': report.format,
        'downloadUrl': f'/api/projects/reports/{report.id}/download/' if report.status == GeneratedReport.Status.READY and report.file else None,
        'approvalStatus': report.approval_status,
        'version': report.version,
        'supersedesId': str(report.supersedes_id) if report.supersedes_id else None,
        'reviewedBy': (report.reviewed_by.full_name or report.reviewed_by.username) if report.reviewed_by_id else None,
        'approvedBy': (report.approved_by.full_name or report.approved_by.username) if report.approved_by_id else None,
        'approvedAt': timezone.localtime(report.approved_at).isoformat() if report.approved_at else None,
        'reviewNotes': report.review_notes,
        'generatedById': str(report.generated_by_id) if report.generated_by_id else None,
        'reviewedById': str(report.reviewed_by_id) if report.reviewed_by_id else None,
        'scheduleName': report.schedule.name if report.schedule_id else None,
        'distributedAt': timezone.localtime(report.distributed_at).isoformat() if report.distributed_at else None,
    }


def _visible_reports(user):
    queryset = GeneratedReport.objects.select_related(
        'generated_by', 'project', 'reviewed_by', 'approved_by', 'schedule',
    ).order_by('-generated_at')
    if user.role not in REPORT_HISTORY_ALL_ROLES:
        queryset = queryset.filter(generated_by=user)
    return queryset


class ProjectReportTemplatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .report_engine import definitions_for

        return Response([
            {
                'id': d.id,
                'title': d.title,
                'description': d.description,
                'category': d.category,
                'quick': d.quick,
                'formats': list(d.formats),
                'requires_project': d.requires_project,
                'requires_tender': d.requires_tender,
                'requires_reason': d.requires_reason,
                'filters': list(d.filters),
                'method': d.method,
            }
            for d in definitions_for(request.user)
        ])


class ProjectReportFilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .report_engine import definitions_for, filter_options

        if not definitions_for(request.user):
            return Response({'districts': [], 'technologies': [], 'vendors': [], 'tenders': [], 'projects': []})
        return Response(filter_options(request.user))


class ProjectReportGenerateView(APIView):
    """Queue a report. Access and filters are checked now; the file is generated in the background."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .report_queue import enqueue

        report_type = str(request.data.get('report_type') or '').strip()
        format_type = str(request.data.get('format') or 'pdf').strip().lower()
        filters = request.data.get('filters') or {}
        if not isinstance(filters, dict):
            raise ValidationError({'filters': 'Filters must be an object.'})
        report = enqueue(request.user, report_type, format_type, filters)
        return Response(_report_row(report), status=status.HTTP_202_ACCEPTED)


class ProjectReportStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = _visible_reports(request.user).filter(id=report_id).first()
        if report is None:
            raise Http404('Report not found.')
        return Response(_report_row(report))


class ProjectReportHistoryView(APIView):
    """Your own generated reports, newest first, paged and searchable; Admin and Auditor see everyone's."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = _visible_reports(request.user)
        search = str(request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(report_type__icontains=search) | Q(generated_by__username__icontains=search))
        state = str(request.query_params.get('status') or '').strip()
        if state in GeneratedReport.Status.values:
            queryset = queryset.filter(status=state)
        if request.query_params.get('active') in {'1', 'true'}:
            queryset = queryset.filter(status__in=[GeneratedReport.Status.QUEUED, GeneratedReport.Status.RUNNING])
        try:
            page = max(1, int(request.query_params.get('page') or 1))
        except ValueError:
            page = 1
        total = queryset.count()
        start = (page - 1) * REPORT_HISTORY_PAGE_SIZE
        return Response({
            'count': total,
            'page': page,
            'page_size': REPORT_HISTORY_PAGE_SIZE,
            'results': [_report_row(r) for r in queryset[start:start + REPORT_HISTORY_PAGE_SIZE]],
        })


def _report_for_action(request, report_id) -> GeneratedReport:
    report = GeneratedReport.objects.select_related('generated_by', 'schedule').filter(id=report_id).first()
    if report is None:
        raise Http404('Report not found.')
    return report


class ProjectReportActionView(APIView):
    """Sign-off and distribution steps for a generated report."""

    permission_classes = [IsAuthenticated]

    def post(self, request, report_id, step):
        from . import report_workflow as wf

        report = _report_for_action(request, report_id)
        notes = str(request.data.get('notes') or '').strip()
        if step == 'submit':
            report = wf.submit_for_review(report, request.user)
        elif step == 'review':
            report = wf.review(report, request.user, accept=request.data.get('decision') != 'return', notes=notes)
        elif step == 'approve':
            report = wf.approve(report, request.user, accept=request.data.get('decision') != 'return', notes=notes)
        elif step == 'new-version':
            report = wf.new_version(report, request.user)
            return Response(_report_row(report), status=status.HTTP_202_ACCEPTED)
        elif step == 'distribute':
            if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
                raise PermissionDenied('Only the RBF Management Team or Super Admin can distribute reports.')
            roles = [r for r in (request.data.get('roles') or []) if r in UserRole.values and r != UserRole.VENDOR]
            if not roles:
                raise ValidationError({'roles': 'Choose who should receive the report.'})
            count = wf.distribute(report, request.user, roles=roles)
            return Response({**_report_row(report), 'recipients': count})
        else:
            raise Http404('Unknown step.')
        report.refresh_from_db()
        return Response(_report_row(report))


class ProjectReportInboxView(APIView):
    """Reports shared with me, and formal reports waiting for my review or approval."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        base = GeneratedReport.objects.select_related('generated_by', 'project', 'reviewed_by', 'approved_by', 'schedule')
        shared = base.filter(distributed_to=user).order_by('-distributed_at')[:50]
        waiting = []
        if user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            waiting = list(
                base.filter(approval_status=GeneratedReport.Approval.IN_REVIEW).exclude(generated_by=user)
            ) + list(
                base.filter(approval_status=GeneratedReport.Approval.REVIEWED).exclude(generated_by=user).exclude(reviewed_by=user)
            )
        return Response({
            'shared': [_report_row(r) for r in shared],
            'awaiting': [_report_row(r) for r in sorted(waiting, key=lambda r: r.generated_at)],
        })


class ProjectReportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = GeneratedReport.objects.select_related('generated_by').filter(id=report_id).first()
        if report is None:
            raise Http404('Report not found.')
        shared_with_me = report.distributed_to.filter(id=request.user.id).exists()
        signer = request.user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN} and report.approval_status in {
            GeneratedReport.Approval.IN_REVIEW, GeneratedReport.Approval.REVIEWED, GeneratedReport.Approval.APPROVED,
        }
        if request.user.role not in REPORT_HISTORY_ALL_ROLES and report.generated_by_id != request.user.id and not shared_with_me and not signer:
            raise PermissionDenied('You can only download reports you generated or that were shared with you.')
        if report.status != GeneratedReport.Status.READY or not report.file:
            return Response({'detail': 'This report is not ready yet.'}, status=status.HTTP_409_CONFLICT)
        log_audit(request.user, 'report_downloaded', report, {
            'module': 'report', 'report_type': report.report_type, 'format': report.format, 'filters': report.filters,
        })
        return FileResponse(report.file.open('rb'), as_attachment=True, filename=Path(report.file.name).name)


DOE_RECORD_READ_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.TAC, UserRole.UNDP_DONOR}


class DoeRegionalRecordMixin:
    """Shared rules for records DoE officers create: region-scoped, owner-edited, never deleted."""

    http_method_names = ['get', 'post', 'patch', 'put', 'head', 'options']
    owner_field = ''
    record_label = 'records'

    def scope_queryset(self, qs):
        user = self.request.user
        if user.role == UserRole.DOE_OFFICER:
            return qs.filter(doe_region_filter(user, prefix='project__')).distinct()
        if user.role in DOE_RECORD_READ_ROLES:
            return qs
        return qs.none()

    def assert_can_write(self, project):
        user = self.request.user
        if user.role != UserRole.DOE_OFFICER:
            raise PermissionDenied(f'Only DoE Officers can create or update {self.record_label}.')
        if not Project.objects.filter(id=project.id).filter(doe_region_filter(user)).exists():
            raise PermissionDenied('You can only work on projects in your region.')

    def assert_owner(self, instance):
        if getattr(instance, f'{self.owner_field}_id') != self.request.user.id:
            raise PermissionDenied(f'You can only update {self.record_label} you created.')


class SiteMonitoringVisitViewSet(ArchiveScopedListMixin, DoeRegionalRecordMixin, viewsets.ModelViewSet):
    queryset = SiteMonitoringVisit.objects.select_related('project', 'installation', 'visited_by').prefetch_related('photos')
    serializer_class = SiteMonitoringVisitSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'installation', 'follow_up_status']
    search_fields = ['observations', 'follow_up_action', 'project__project_reference']
    ordering_fields = ['visit_date', 'created_at']
    owner_field = 'visited_by'
    record_label = 'site monitoring visits'

    def get_queryset(self):
        return self.scope_queryset(self.queryset.all())

    def _save_photos(self, visit):
        uploads = self.request.FILES.getlist('photos')
        if len(uploads) + visit.photos.count() > 10:
            raise ValidationError({'photos': 'A visit can have at most 10 photos.'})
        for upload in uploads:
            SiteMonitoringVisitSerializer.validate_photo(upload)
        for upload in uploads:
            SiteMonitoringPhoto.objects.create(visit=visit, file=upload)

    def perform_create(self, serializer):
        self.assert_can_write(serializer.validated_data['project'])
        with transaction.atomic():
            visit = serializer.save(visited_by=self.request.user)
            self._save_photos(visit)
        log_audit(self.request.user, 'site_monitoring_visit_recorded', visit, {'project_id': str(visit.project_id)})
        if visit.follow_up_status in {SiteVisitFollowUpStatus.OPEN, SiteVisitFollowUpStatus.IN_PROGRESS}:
            notify_project_oversight(
                visit.project,
                'DoE site visit needs follow-up',
                f"{self.request.user.full_name or self.request.user.username} visited "
                f"{visit.project.project_reference or visit.project_id} on {visit.visit_date}: "
                f"{visit.follow_up_action or visit.observations[:120]}",
            )

    def perform_update(self, serializer):
        self.assert_can_write(serializer.instance.project)
        self.assert_owner(serializer.instance)
        with transaction.atomic():
            visit = serializer.save()
            self._save_photos(visit)
        log_audit(self.request.user, 'site_monitoring_visit_updated', visit, {'project_id': str(visit.project_id)})

    @action(detail=True, methods=['post'], url_path=r'photos/(?P<photo_id>[^/.]+)/remove')
    def remove_photo(self, request, pk=None, photo_id=None):
        visit = self.get_object()
        self.assert_can_write(visit.project)
        self.assert_owner(visit)
        photo = visit.photos.filter(id=photo_id).first()
        if not photo:
            raise Http404('Photo not found.')
        photo.delete()
        return Response(self.get_serializer(visit).data)


class KpiReviewViewSet(ArchiveScopedListMixin, DoeRegionalRecordMixin, viewsets.ModelViewSet):
    queryset = KpiReview.objects.select_related('project', 'reviewer')
    serializer_class = KpiReviewSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'rating', 'review_period']
    search_fields = ['summary', 'project__project_reference']
    ordering_fields = ['review_period', 'updated_at']
    owner_field = 'reviewer'
    record_label = 'KPI reviews'

    def get_queryset(self):
        return self.scope_queryset(self.queryset.all())

    def _assert_unique_period(self, project, period, exclude_id=None):
        clash = KpiReview.objects.filter(project=project, reviewer=self.request.user, review_period=period)
        if exclude_id:
            clash = clash.exclude(id=exclude_id)
        if clash.exists():
            raise ValidationError({'review_period': 'You already reviewed this project for that month. Edit the existing review instead.'})

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        self.assert_can_write(project)
        self._assert_unique_period(project, serializer.validated_data['review_period'])
        review = serializer.save(reviewer=self.request.user)
        log_audit(self.request.user, 'kpi_review_submitted', review, {'project_id': str(review.project_id), 'rating': review.rating})
        if review.rating == KpiReviewRating.AT_RISK:
            notify_project_oversight(
                review.project,
                'DoE KPI review: project at risk',
                f"{self.request.user.full_name or self.request.user.username} rated "
                f"{review.project.project_reference or review.project_id} at risk for {review.review_period}: {review.summary[:150]}",
            )

    def perform_update(self, serializer):
        instance = serializer.instance
        self.assert_can_write(instance.project)
        self.assert_owner(instance)
        period = serializer.validated_data.get('review_period', instance.review_period)
        self._assert_unique_period(instance.project, period, exclude_id=instance.id)
        review = serializer.save()
        log_audit(self.request.user, 'kpi_review_updated', review, {'project_id': str(review.project_id), 'rating': review.rating})


class OversightReviewViewSet(viewsets.ModelViewSet):
    """Shared oversight reviews, flags and comments (DoE, PSC, RMT) on existing project records.

    Readers: RMT, Admin, PSC, TAC, Auditor (national); DoE (own region). Writers: DoE, PSC, RMT, Admin.
    Records are never deleted; the reviewer may amend their own entry until it is resolved, and the
    RBF Management Team tracks the follow-up.
    """

    queryset = OversightReview.objects.select_related(
        'reviewer', 'resolved_by', 'project', 'vendor', 'verification_task__report', 'payment_claim',
    )
    serializer_class = OversightReviewSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'subject_type', 'review_status', 'follow_up_status', 'project', 'reviewer', 'reviewer_role',
        'verification_task', 'payment_claim', 'vendor', 'milestone',
    ]
    search_fields = ['comment', 'action_required', 'issue_category', 'project__project_reference']
    ordering_fields = ['created_at', 'follow_up_date', 'updated_at']

    READ_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR, UserRole.TAC, UserRole.AUDITOR}
    WRITE_ROLES = {UserRole.DOE_OFFICER, UserRole.UNDP_DONOR, UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    FOLLOW_UP_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    # Statuses a reviewer may record directly; acknowledgement and re-verification are workflow actions.
    ROLE_STATUSES = {
        UserRole.UNDP_DONOR: {OversightReviewStatus.COMPLIANT, OversightReviewStatus.DELAYED, OversightReviewStatus.FLAGGED, OversightReviewStatus.COMMENT},
        UserRole.DOE_OFFICER: {OversightReviewStatus.FLAGGED, OversightReviewStatus.COMMENT},
        UserRole.RBF_OFFICIAL: {OversightReviewStatus.FLAGGED, OversightReviewStatus.COMMENT},
        UserRole.ADMIN: {OversightReviewStatus.FLAGGED, OversightReviewStatus.COMMENT},
    }
    OWNER_EDITABLE = {'comment', 'review_status', 'issue_category', 'action_required', 'follow_up_date'}

    def get_queryset(self):
        qs = self.queryset.all()
        user = self.request.user
        if user.role == UserRole.DOE_OFFICER:
            qs = qs.filter(doe_region_filter(user, prefix='project__')).distinct()
        elif user.role not in self.READ_ROLES:
            return qs.none()
        if self.request.query_params.get('mine') in {'1', 'true'}:
            qs = qs.filter(reviewer=user)
        if self.request.query_params.get('open') in {'1', 'true'}:
            qs = qs.filter(follow_up_status__in=[OversightFollowUpStatus.OPEN, OversightFollowUpStatus.IN_PROGRESS])
        return qs

    @staticmethod
    def _derive_project(data):
        for key, attr in (('verification_task', 'report.project'), ('payment_claim', 'project'), ('milestone', 'project'),
                          ('kpi_review', 'project'), ('monitoring_visit', 'project')):
            obj = data.get(key)
            if obj is not None:
                for part in attr.split('.'):
                    obj = getattr(obj, part)
                return obj
        return data.get('project')

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in self.WRITE_ROLES:
            raise PermissionDenied('You do not have permission to record oversight reviews.')
        data = serializer.validated_data
        if data['review_status'] not in self.ROLE_STATUSES.get(user.role, set()):
            raise ValidationError({'review_status': 'This review status is not available to your role.'})
        project = self._derive_project(data)
        if data.get('project') and project and data['project'].id != project.id:
            raise ValidationError({'project': 'The linked record belongs to a different project.'})
        if data['subject_type'] != OversightSubject.VENDOR and project is None:
            raise ValidationError({'project': 'Link the review to a project or project record.'})
        if data['subject_type'] == OversightSubject.VENDOR and not (data.get('vendor') or project):
            raise ValidationError({'vendor': 'Select the vendor being reviewed.'})
        if user.role == UserRole.DOE_OFFICER:
            if project is None or not Project.objects.filter(id=project.id).filter(doe_region_filter(user)).exists():
                raise PermissionDenied('You can only review records in your region.')
        follow_up = data.get('follow_up_status') or OversightFollowUpStatus.NONE
        if data['review_status'] in {OversightReviewStatus.FLAGGED, OversightReviewStatus.DELAYED} and follow_up == OversightFollowUpStatus.NONE:
            follow_up = OversightFollowUpStatus.OPEN
        if follow_up == OversightFollowUpStatus.RESOLVED:
            raise ValidationError({'follow_up_status': 'A new review cannot be created as resolved.'})
        review = serializer.save(
            reviewer=user,
            reviewer_role=user.role,
            project=project,
            follow_up_status=follow_up,
            verification_round=data['verification_task'].verification_round if data.get('verification_task') else None,
        )
        log_audit(user, 'oversight_review_recorded', review, {
            'subject_type': review.subject_type, 'review_status': review.review_status,
            'project_id': str(review.project_id or ''), 'module': 'oversight',
        })
        if review.review_status in {OversightReviewStatus.FLAGGED, OversightReviewStatus.DELAYED} and review.project:
            notify_project_oversight(
                review.project,
                f'{review.get_review_status_display()} by {user.get_role_display()}: {review.project.project_reference or review.project_id}',
                review.comment[:200],
                linked_entity_id=str(review.project_id),
            )

    def perform_update(self, serializer):
        review = serializer.instance
        user = self.request.user
        if review.reviewer_id != user.id:
            raise PermissionDenied('You can only amend reviews you recorded. Use follow-up to track progress.')
        if review.follow_up_status == OversightFollowUpStatus.RESOLVED:
            raise PermissionDenied('Resolved reviews are closed and cannot be amended.')
        if review.review_status in {OversightReviewStatus.ACKNOWLEDGED, OversightReviewStatus.REVERIFICATION_REQUESTED}:
            raise PermissionDenied('Workflow records cannot be amended.')
        changed = set(serializer.validated_data) - self.OWNER_EDITABLE
        if changed:
            raise ValidationError({field: 'This field cannot be changed after the review is recorded.' for field in changed})
        new_status = serializer.validated_data.get('review_status')
        if new_status and new_status not in self.ROLE_STATUSES.get(user.role, set()):
            raise ValidationError({'review_status': 'This review status is not available to your role.'})
        review = serializer.save()
        log_audit(user, 'oversight_review_amended', review, {'review_status': review.review_status, 'module': 'oversight'})

    @action(detail=True, methods=['post'])
    def follow_up(self, request, pk=None):
        review = self.get_object()
        user = request.user
        if user.role not in self.FOLLOW_UP_ROLES and review.reviewer_id != user.id:
            raise PermissionDenied('Only the RBF Management Team or the reviewer can update the follow-up.')
        new_status = str(request.data.get('follow_up_status') or '').strip()
        if new_status not in OversightFollowUpStatus.values:
            return Response({'detail': 'Choose a valid follow-up status.'}, status=status.HTTP_400_BAD_REQUEST)
        note = str(request.data.get('resolution_note') or '').strip()
        if new_status == OversightFollowUpStatus.RESOLVED and not note:
            return Response({'detail': 'Describe how the issue was resolved.'}, status=status.HTTP_400_BAD_REQUEST)
        previous = review.follow_up_status
        review.follow_up_status = new_status
        if note:
            review.resolution_note = note
        if new_status == OversightFollowUpStatus.RESOLVED:
            review.resolved_by = user
            review.resolved_at = timezone.now()
        else:
            review.resolved_by = None
            review.resolved_at = None
        review.save(update_fields=['follow_up_status', 'resolution_note', 'resolved_by', 'resolved_at', 'updated_at'])
        log_audit(user, 'oversight_follow_up_updated', review, {'old_status': previous, 'new_status': new_status, 'module': 'oversight'})
        if review.reviewer_id and review.reviewer_id != user.id:
            Notification.objects.create(
                recipient_id=str(review.reviewer_id),
                recipient_name=review.reviewer.full_name or review.reviewer.username,
                type=NotificationChannel.IN_APP,
                event='oversight_follow_up',
                title=f'Follow-up {review.get_follow_up_status_display().lower()}',
                body=note or f'Your {review.get_review_status_display().lower()} review is now {review.get_follow_up_status_display().lower()}.',
                status=NotificationStatus.SENT,
                linked_entity_id=str(review.project_id or ''),
            )
        return Response(self.get_serializer(review).data)


def _notify_users(users, *, event: str, title: str, body: str, linked_entity_id: str = ''):
    Notification.objects.bulk_create([
        Notification(
            recipient_id=str(user.id),
            recipient_name=user.full_name or user.username,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=linked_entity_id,
        )
        for user in users
    ], ignore_conflicts=True)


class AuditCaseViewSet(viewsets.ModelViewSet):
    """Independent audit cases and compliance reviews.

    The Auditor creates cases and drives every workflow step; the cases link to the source
    records under audit and never change them. The RBF Management Team sees a case once the
    Auditor asks for a management response, and records that response and corrective-action
    progress. PSC sees cases from that point on, read-only. Cases are never deleted.

    Draft -> Under Review -> Evidence Collected -> Finding Recorded -> Management Response
          -> Audit Finalized -> Closed   (a compliant finding may be finalized without a response)
    """

    queryset = AuditCase.objects.select_related(
        'auditor', 'responded_by', 'project', 'vendor', 'tender', 'contract', 'payment_claim',
        'verification_task__report',
    ).prefetch_related('evidence__added_by')
    serializer_class = AuditCaseSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'status', 'case_type', 'audit_area', 'finding_type', 'risk_level', 'corrective_action_status',
        'project', 'vendor', 'tender', 'payment_claim', 'verification_task',
    ]
    search_fields = ['reference', 'title', 'scope', 'finding', 'project__project_reference']
    ordering_fields = ['created_at', 'updated_at', 'corrective_action_due']

    AUDITOR_ROLES = {UserRole.AUDITOR}
    FULL_READ_ROLES = {UserRole.AUDITOR, UserRole.ADMIN}
    RESPONSE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    SHARED_READ_ROLES = {UserRole.RBF_OFFICIAL, UserRole.UNDP_DONOR}
    # The Auditor's working papers stay private until management is asked to respond.
    SHARED_STATUSES = {AuditCaseStatus.MANAGEMENT_RESPONSE, AuditCaseStatus.FINALIZED, AuditCaseStatus.CLOSED}
    LOCKED_STATUSES = {AuditCaseStatus.FINALIZED, AuditCaseStatus.CLOSED}
    FINDING_FIELDS = {'finding_type', 'risk_level', 'finding', 'recommendation', 'criteria'}

    def get_queryset(self):
        qs = self.queryset.all()
        user = self.request.user
        if user.role in self.FULL_READ_ROLES:
            return qs
        if user.role in self.SHARED_READ_ROLES:
            return qs.filter(status__in=self.SHARED_STATUSES)
        return qs.none()

    def _assert_auditor(self):
        if self.request.user.role not in self.AUDITOR_ROLES:
            raise PermissionDenied('Only the Auditor can manage audit cases.')

    @staticmethod
    def _derive_links(data):
        claim = data.get('payment_claim')
        task = data.get('verification_task')
        contract = data.get('contract')
        if not data.get('project'):
            if claim is not None:
                data['project'] = claim.project
            elif task is not None:
                data['project'] = task.report.project
        if not data.get('tender') and contract is not None:
            data['tender'] = contract.tender
        if not data.get('vendor') and claim is not None:
            data['vendor'] = claim.vendor
        return data

    def perform_create(self, serializer):
        self._assert_auditor()
        data = self._derive_links(dict(serializer.validated_data))
        prefix = 'CR' if data.get('case_type') == AuditCaseType.COMPLIANCE_REVIEW else 'AUD'
        with transaction.atomic():
            case = serializer.save(
                auditor=self.request.user,
                reference=f'TMP-{uuid.uuid4().hex[:20]}',
                status=AuditCaseStatus.DRAFT,
                project=data.get('project'),
                tender=data.get('tender'),
                vendor=data.get('vendor'),
            )
            case.reference = f'{prefix}-{timezone.localdate().year}-{case.id:04d}'
            case.save(update_fields=['reference'])
        log_audit(self.request.user, 'audit_case_opened', case, {
            'new_status': case.status, 'audit_area': case.audit_area, 'module': 'audit',
            'project_id': str(case.project_id or ''),
        })

    def perform_update(self, serializer):
        self._assert_auditor()
        case = serializer.instance
        if case.status in self.LOCKED_STATUSES:
            raise PermissionDenied('A finalized audit case cannot be edited.')
        if self.FINDING_FIELDS & set(serializer.validated_data) and case.status in {AuditCaseStatus.DRAFT, AuditCaseStatus.UNDER_REVIEW}:
            raise ValidationError({'finding': 'Collect evidence before recording a finding.'})
        if 'corrective_action_status' in serializer.validated_data:
            raise ValidationError({'corrective_action_status': 'Corrective-action progress is recorded through its own action.'})
        case = serializer.save()
        log_audit(self.request.user, 'audit_case_updated', case, {'module': 'audit', 'fields': sorted(serializer.validated_data)})

    def _move(self, case, new_status, action_name, **fields):
        previous = case.status
        case.status = new_status
        for key, value in fields.items():
            setattr(case, key, value)
        case.save(update_fields=['status', 'updated_at', *fields.keys()])
        log_audit(self.request.user, action_name, case, {'old_status': previous, 'new_status': new_status, 'module': 'audit'})
        return Response(self.get_serializer(case).data)

    def _expect(self, case, *statuses):
        if case.status not in statuses:
            labels = ', '.join(AuditCaseStatus(s).label for s in statuses)
            raise ValidationError({'detail': f'This step is only available while the case is: {labels}.'})

    @action(detail=True, methods=['post'])
    def start_review(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.DRAFT)
        return self._move(case, AuditCaseStatus.UNDER_REVIEW, 'audit_case_review_started')

    @action(detail=True, methods=['post'])
    def evidence_collected(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.UNDER_REVIEW)
        if not case.evidence.exists():
            raise ValidationError({'detail': 'Add at least one piece of evidence first.'})
        return self._move(case, AuditCaseStatus.EVIDENCE_COLLECTED, 'audit_case_evidence_collected')

    @action(detail=True, methods=['post'])
    def record_finding(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.EVIDENCE_COLLECTED, AuditCaseStatus.FINDING_RECORDED)
        finding_type = str(request.data.get('finding_type') or case.finding_type or '').strip()
        risk_level = str(request.data.get('risk_level') or case.risk_level or '').strip()
        def submitted(field):
            return str(request.data.get(field, getattr(case, field)) or '').strip()

        finding = submitted('finding')
        errors = {}
        if finding_type not in AuditFindingType.values:
            errors['finding_type'] = 'Choose the finding type.'
        if risk_level not in AuditRiskLevel.values:
            errors['risk_level'] = 'Choose the risk level.'
        if len(finding) < 20:
            errors['finding'] = 'Describe the finding (at least 20 characters).'
        corrective_action = submitted('corrective_action')
        needs_action = finding_type in {AuditFindingType.EXCEPTION, AuditFindingType.NON_COMPLIANCE}
        if needs_action and not corrective_action:
            errors['corrective_action'] = 'An exception or non-compliance needs a recommended corrective action.'
        if errors:
            raise ValidationError(errors)
        due = request.data.get('corrective_action_due') or case.corrective_action_due
        return self._move(
            case, AuditCaseStatus.FINDING_RECORDED, 'audit_finding_recorded',
            finding_type=finding_type,
            risk_level=risk_level,
            finding=finding,
            criteria=submitted('criteria'),
            recommendation=submitted('recommendation'),
            corrective_action=corrective_action,
            corrective_action_owner=submitted('corrective_action_owner'),
            corrective_action_due=due or None,
            corrective_action_status=CorrectiveActionStatus.OPEN if corrective_action else CorrectiveActionStatus.NOT_REQUIRED,
            finding_recorded_at=timezone.now(),
        )

    @action(detail=True, methods=['post'])
    def request_response(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.FINDING_RECORDED)
        response = self._move(case, AuditCaseStatus.MANAGEMENT_RESPONSE, 'audit_management_response_requested', response_requested_at=timezone.now())
        _notify_users(
            User.objects.filter(role__in=self.RESPONSE_ROLES, is_active=True).only('id', 'full_name', 'username'),
            event='audit_response_requested',
            title=f'Management response requested: {case.reference}',
            body=f'{case.get_risk_level_display()} {case.get_finding_type_display().lower()}: {case.title}',
            linked_entity_id=str(case.id),
        )
        return response

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        if request.user.role not in self.RESPONSE_ROLES:
            raise PermissionDenied('Only the RBF Management Team can respond to audit findings.')
        case = self.get_object()
        self._expect(case, AuditCaseStatus.MANAGEMENT_RESPONSE)
        text = str(request.data.get('management_response') or '').strip()
        if len(text) < 10:
            raise ValidationError({'management_response': 'Write the management response (at least 10 characters).'})
        fields = {'management_response': text, 'responded_by': request.user, 'responded_at': timezone.now()}
        progress = str(request.data.get('corrective_action_status') or '').strip()
        if progress:
            if case.corrective_action_status == CorrectiveActionStatus.NOT_REQUIRED or progress not in {
                CorrectiveActionStatus.OPEN, CorrectiveActionStatus.IN_PROGRESS, CorrectiveActionStatus.IMPLEMENTED,
            }:
                raise ValidationError({'corrective_action_status': 'Choose open, in progress or implemented.'})
            fields['corrective_action_status'] = progress
        response = self._move(case, AuditCaseStatus.MANAGEMENT_RESPONSE, 'audit_management_response_recorded', **fields)
        if case.auditor_id:
            _notify_users(
                [case.auditor], event='audit_response_received',
                title=f'Management responded: {case.reference}', body=text[:200], linked_entity_id=str(case.id),
            )
        return response

    @action(detail=True, methods=['post'])
    def corrective_action_progress(self, request, pk=None):
        """RMT reports progress; only the Auditor can mark the action verified."""
        user = request.user
        case = self.get_object()
        progress = str(request.data.get('corrective_action_status') or '').strip()
        if case.corrective_action_status == CorrectiveActionStatus.NOT_REQUIRED:
            raise ValidationError({'detail': 'This case has no corrective action.'})
        if user.role in self.AUDITOR_ROLES:
            allowed = {CorrectiveActionStatus.VERIFIED, CorrectiveActionStatus.IN_PROGRESS}
        elif user.role in self.RESPONSE_ROLES:
            allowed = {CorrectiveActionStatus.IN_PROGRESS, CorrectiveActionStatus.IMPLEMENTED}
        else:
            raise PermissionDenied('You cannot update corrective actions.')
        if progress not in allowed:
            raise ValidationError({'corrective_action_status': 'This status is not available to your role.'})
        if case.status not in {AuditCaseStatus.MANAGEMENT_RESPONSE, AuditCaseStatus.FINALIZED}:
            raise ValidationError({'detail': 'Corrective actions are tracked after management is asked to respond and before closure.'})
        if progress == CorrectiveActionStatus.VERIFIED and case.corrective_action_status != CorrectiveActionStatus.IMPLEMENTED:
            raise ValidationError({'corrective_action_status': 'Management must report the action implemented before it can be verified.'})
        previous = case.corrective_action_status
        case.corrective_action_status = progress
        case.save(update_fields=['corrective_action_status', 'updated_at'])
        log_audit(user, 'audit_corrective_action_updated', case, {'old_status': previous, 'new_status': progress, 'module': 'audit'})
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'])
    def finalize(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.FINDING_RECORDED, AuditCaseStatus.MANAGEMENT_RESPONSE)
        if case.status == AuditCaseStatus.FINDING_RECORDED and case.finding_type != AuditFindingType.COMPLIANT:
            raise ValidationError({'detail': 'Request a management response before finalizing this finding.'})
        if case.status == AuditCaseStatus.MANAGEMENT_RESPONSE and not case.responded_at:
            raise ValidationError({'detail': 'Wait for the management response before finalizing.'})
        conclusion = str(request.data.get('conclusion') or '').strip()
        if len(conclusion) < 10:
            raise ValidationError({'conclusion': 'Write the audit conclusion (at least 10 characters).'})
        response = self._move(case, AuditCaseStatus.FINALIZED, 'audit_case_finalized', conclusion=conclusion, finalized_at=timezone.now())
        _notify_users(
            User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR}, is_active=True).only('id', 'full_name', 'username'),
            event='audit_case_finalized',
            title=f'Audit finalized: {case.reference}',
            body=f'{case.title} - {case.get_finding_type_display()} ({case.get_risk_level_display()}).',
            linked_entity_id=str(case.id),
        )
        return response

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        self._expect(case, AuditCaseStatus.FINALIZED)
        if case.corrective_action_status not in {CorrectiveActionStatus.NOT_REQUIRED, CorrectiveActionStatus.VERIFIED}:
            raise ValidationError({'detail': 'Verify the corrective action before closing the case.'})
        return self._move(case, AuditCaseStatus.CLOSED, 'audit_case_closed', closed_at=timezone.now())

    @action(detail=True, methods=['post'], url_path='evidence')
    def add_evidence(self, request, pk=None):
        self._assert_auditor()
        case = self.get_object()
        if case.status in self.LOCKED_STATUSES:
            raise ValidationError({'detail': 'Evidence cannot be added to a finalized case.'})
        serializer = AuditEvidenceSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data['kind']
        upload = serializer.validated_data.get('file')
        if len(serializer.validated_data['description'].strip()) < 5:
            raise ValidationError({'description': 'Describe the evidence (at least 5 characters).'})
        if kind == AuditEvidenceKind.FILE:
            if not upload:
                raise ValidationError({'file': 'Attach the evidence file.'})
            validate_document_upload(upload, label='Evidence file', allowed=('pdf', 'jpg', 'jpeg', 'png', 'csv', 'xlsx', 'docx'))
        elif upload:
            raise ValidationError({'file': 'Only file evidence can carry an attachment.'})
        if kind == AuditEvidenceKind.RECORD and not (serializer.validated_data.get('source_type') and serializer.validated_data.get('source_id')):
            raise ValidationError({'source_id': 'Name the source record type and ID.'})
        evidence = serializer.save(case=case, added_by=request.user)
        log_audit(request.user, 'audit_evidence_added', case, {
            'module': 'audit', 'evidence_id': evidence.id, 'kind': kind,
            'source': f'{evidence.source_type}#{evidence.source_id}' if evidence.source_id else '',
        })
        return Response(self.get_serializer(case).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        case = self.get_object()
        logs = AuditLog.objects.filter(entity_type='AuditCase', entity_id=str(case.id)).select_related('actor').order_by('created_at')
        return Response(AuditLogSerializer(logs, many=True).data)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        case = self.get_object()
        esc = html.escape

        def row(label, value):
            return f'<tr><th>{esc(label)}</th><td>{esc(str(value or "-"))}</td></tr>'

        links = [
            ('Project', case.project.project_reference if case.project_id else ''),
            ('Vendor', AuditCaseSerializer().get_vendor_display(case) or ''),
            ('Tender', case.tender.reference_number if case.tender_id else ''),
            ('Contract', case.contract.reference_number if case.contract_id else ''),
            ('Payment claim', f'#{case.payment_claim_id}' if case.payment_claim_id else ''),
            ('Installation', case.verification_task.report.serial_number if case.verification_task_id else ''),
        ]
        evidence_rows = ''.join(
            f'<tr><td>{esc(e.get_kind_display())}</td><td>{esc(e.description)}</td>'
            f'<td>{esc(f"{e.source_type} #{e.source_id}" if e.source_id else (Path(e.file.name).name if e.file else ""))}</td>'
            f'<td>{esc(timezone.localtime(e.added_at).strftime("%Y-%m-%d"))}</td></tr>'
            for e in case.evidence.all()
        )
        body = f"""
        <html><head><style>
          body {{ font-family: Arial, sans-serif; color: #0f172a; padding: 24px; font-size: 12px; }}
          h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 14px; margin: 20px 0 6px; }}
          table {{ width: 100%; border-collapse: collapse; }}
          th, td {{ border: 1px solid #cbd5e1; padding: 6px; text-align: left; vertical-align: top; }}
          th {{ background: #f1f5f9; width: 28%; }} p.muted {{ color: #475569; margin: 0 0 12px; }}
          .pre {{ white-space: pre-wrap; }}
        </style></head><body>
          <h1>Audit Report {esc(case.reference)}</h1>
          <p class="muted">{esc(case.get_case_type_display())} | {esc(case.get_audit_area_display())} | Status: {esc(case.get_status_display())}
           | Generated {esc(timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M"))}</p>
          <table>
            {row('Title', case.title)}
            {row('Auditor', AuditCaseSerializer().get_auditor_name(case))}
            {''.join(row(label, value) for label, value in links if value)}
            {row('Scope', case.scope)}
            {row('Criteria', case.criteria)}
          </table>
          <h2>Finding</h2>
          <table>
            {row('Finding type', case.get_finding_type_display() if case.finding_type else '')}
            {row('Risk level', case.get_risk_level_display() if case.risk_level else '')}
            {row('Finding', case.finding)}
            {row('Recommendation', case.recommendation)}
          </table>
          <h2>Management Response and Corrective Action</h2>
          <table>
            {row('Management response', case.management_response)}
            {row('Responded by', AuditCaseSerializer().get_responded_by_name(case))}
            {row('Corrective action', case.corrective_action)}
            {row('Owner', case.corrective_action_owner)}
            {row('Due', case.corrective_action_due)}
            {row('Status', case.get_corrective_action_status_display())}
          </table>
          <h2>Conclusion</h2><p class="pre">{esc(case.conclusion or 'Not yet finalized.')}</p>
          <h2>Evidence</h2>
          <table><tr><th>Kind</th><th>Description</th><th>Source</th><th>Added</th></tr>
          {evidence_rows or '<tr><td colspan="4">No evidence recorded.</td></tr>'}</table>
        </body></html>
        """
        from rbf.tenders.pba_pdf import _render_pdf

        tmp_dir = Path(tempfile.mkdtemp(prefix='audit_case_pdf_'))
        output_path = tmp_dir / f'{case.reference}.pdf'
        from .report_pdf import report_footer, report_header

        _render_pdf(body, output_path, case.reference, header_template=report_header(f'Audit Report {case.reference}'),
                    footer_template=report_footer(request.user.full_name or request.user.username))
        log_audit(request.user, 'audit_report_generated', case, {'module': 'audit'})
        return FileResponse(output_path.open('rb'), as_attachment=True, filename=output_path.name)


class VendorPerformanceViewSet(viewsets.ViewSet):
    """Read-only vendor performance computed from the shared project, verification and claim records.

    DoE Officers see vendors working in their region; PSC, TAC, Auditor, RMT and Admin see all.
    """

    permission_classes = [IsAuthenticated]
    READ_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR, UserRole.TAC, UserRole.AUDITOR, UserRole.DOE_OFFICER}
    PAID_STATUSES = claim_status.PAID

    def list(self, request):
        user = request.user
        if user.role not in self.READ_ROLES:
            raise PermissionDenied('You do not have access to vendor performance.')
        projects = Project.objects.exclude(vendor_id='')
        if user.role == UserRole.DOE_OFFICER:
            projects = projects.filter(doe_region_filter(user))
        project_rows = list(projects.values('id', 'vendor_id', 'vendor_name', 'status', 'district', 'region', 'project_reference'))
        if not project_rows:
            return Response([])
        project_ids = [row['id'] for row in project_rows]

        def by_project(qs, **aggregates):
            return {row['project_id']: row for row in qs.values('project_id').annotate(**aggregates)}

        installs = by_project(
            InstallationReport.objects.filter(project_id__in=project_ids),
            total=Count('id'),
            verified=Count('id', filter=Q(status=InstallationStatus.VERIFIED)),
            flagged=Count('id', filter=Q(status=InstallationStatus.FLAGGED)),
        )
        tasks = {
            row['report__project_id']: row
            for row in VerificationTask.objects.filter(report__project_id__in=project_ids).values('report__project_id').annotate(
                pending=Count('id', filter=Q(status__in=[VerificationStatus.PENDING, VerificationStatus.REVERIFICATION_REQUIRED])),
                reverified=Count('id', filter=Q(verification_round__gt=1)),
            )
        }
        claims = by_project(
            PaymentClaim.objects.filter(project_id__in=project_ids),
            count=Count('id'),
            claimed=Sum('claim_amount'),
            paid=Sum('claim_amount', filter=Q(status__in=self.PAID_STATUSES)),
            rejected=Count('id', filter=Q(status=PaymentClaimStatus.REJECTED)),
            held=Count('id', filter=Q(status=PaymentClaimStatus.HELD_AUDIT)),
        )
        open_flags = by_project(
            OversightReview.objects.filter(
                project_id__in=project_ids,
                follow_up_status__in=[OversightFollowUpStatus.OPEN, OversightFollowUpStatus.IN_PROGRESS],
            ),
            n=Count('id'),
        )
        latest_ratings = {}
        for review in KpiReview.objects.filter(project_id__in=project_ids).order_by('review_period', 'updated_at'):
            latest_ratings[review.project_id] = (review.review_period, review.rating)

        vendors: dict[str, dict] = {}
        for row in project_rows:
            pid = row['id']
            entry = vendors.setdefault(row['vendor_id'], {
                'vendor_id': row['vendor_id'], 'vendor_name': row['vendor_name'], 'districts': set(),
                'projects': 0, 'active_projects': 0, 'completed_projects': 0,
                'installations': 0, 'verified': 0, 'flagged': 0, 'pending_verification': 0, 'reverifications': 0,
                'claims': 0, 'claimed_amount': 0, 'paid_amount': 0, 'rejected_claims': 0, 'held_claims': 0,
                'open_issues': 0, 'kpi_reviews': {}, 'project_refs': [],
            })
            entry['projects'] += 1
            entry['project_refs'].append({'id': pid, 'reference': row['project_reference'] or f'Project {pid}'})
            entry['active_projects'] += row['status'] == ProjectStatus.ACTIVE
            entry['completed_projects'] += row['status'] in {'completed', 'Completed'}
            entry['districts'].add(row['district'] or row['region'])
            inst = installs.get(pid, {})
            entry['installations'] += inst.get('total', 0)
            entry['verified'] += inst.get('verified', 0)
            entry['flagged'] += inst.get('flagged', 0)
            task = tasks.get(pid, {})
            entry['pending_verification'] += task.get('pending', 0)
            entry['reverifications'] += task.get('reverified', 0)
            claim = claims.get(pid, {})
            entry['claims'] += claim.get('count', 0)
            entry['claimed_amount'] += float(claim.get('claimed') or 0)
            entry['paid_amount'] += float(claim.get('paid') or 0)
            entry['rejected_claims'] += claim.get('rejected', 0)
            entry['held_claims'] += claim.get('held', 0)
            entry['open_issues'] += open_flags.get(pid, {}).get('n', 0)
            if pid in latest_ratings:
                entry['kpi_reviews'][str(pid)] = latest_ratings[pid]

        account_ids = [vid for vid in vendors if str(vid).isdigit()]
        accounts = {str(u.id): u for u in User.objects.filter(id__in=account_ids).only('id', 'status', 'organization_name', 'full_name', 'username')}
        result = []
        for vendor_id, entry in vendors.items():
            ratings = [rating for _, rating in entry.pop('kpi_reviews').values()]
            account = accounts.get(str(vendor_id))
            entry['districts'] = sorted(d for d in entry['districts'] if d)
            entry['vendor_status'] = account.status if account else ''
            if account:
                entry['vendor_name'] = account.organization_name or account.full_name or entry['vendor_name']
            entry['verification_rate'] = round(100 * entry['verified'] / entry['installations'], 1) if entry['installations'] else None
            entry['kpi_at_risk'] = ratings.count(KpiReviewRating.AT_RISK)
            entry['kpi_needs_attention'] = ratings.count(KpiReviewRating.NEEDS_ATTENTION)
            entry['kpi_on_track'] = ratings.count(KpiReviewRating.ON_TRACK)
            result.append(entry)
        result.sort(key=lambda e: (-(e['flagged'] + e['open_issues'] + e['kpi_at_risk']), e['vendor_name'] or ''))
        return Response(result)


class ResultsIndicatorViewSet(viewsets.ModelViewSet):
    """The programme results framework. Read by the report audiences; edited by the Super Admin only.
    Indicators are never deleted, so past reports can always be explained."""

    queryset = ResultsIndicator.objects.select_related('updated_by').all()
    serializer_class = ResultsIndicatorSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    READ_ROLES = {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.UNDP_DONOR, UserRole.AUDITOR, UserRole.TAC}

    def get_queryset(self):
        if self.request.user.role not in self.READ_ROLES:
            return self.queryset.none()
        return self.queryset

    def _assert_admin(self):
        if self.request.user.role != UserRole.ADMIN:
            raise PermissionDenied('Only the Platform Administrator (Super Admin) can change the results framework.')

    def perform_create(self, serializer):
        self._assert_admin()
        indicator = serializer.save(updated_by=self.request.user)
        log_audit(self.request.user, 'results_indicator_created', indicator, {'module': 'results', 'code': indicator.code})

    def perform_update(self, serializer):
        self._assert_admin()
        before = {f: str(getattr(serializer.instance, f)) for f in ('baseline', 'target', 'target_date', 'manual_actual')}
        indicator = serializer.save(updated_by=self.request.user)
        log_audit(self.request.user, 'results_indicator_updated', indicator, {'module': 'results', 'code': indicator.code, 'before': before})

    @action(detail=False, methods=['get'])
    def measures(self, request):
        return Response([{'value': value, 'label': label} for value, label in ResultsMeasure.choices])


class ReportScheduleSerializer(serializers.ModelSerializer):
    prepared_by_name = serializers.SerializerMethodField()
    report_title = serializers.SerializerMethodField()

    class Meta:
        model = ReportSchedule
        fields = [
            'id', 'name', 'report_type', 'report_title', 'format', 'frequency', 'run_day', 'filters', 'prepared_by',
            'prepared_by_name', 'recipient_roles', 'recipient_users', 'active', 'next_run_at', 'last_run_at', 'created_at',
        ]
        read_only_fields = ['id', 'next_run_at', 'last_run_at', 'created_at']

    def get_prepared_by_name(self, obj):
        return (obj.prepared_by.full_name or obj.prepared_by.username) if obj.prepared_by_id else None

    def get_report_title(self, obj):
        from .report_catalogue import REGISTRY

        definition = REGISTRY.get(obj.report_type)
        return definition.title if definition else obj.report_type

    def validate(self, attrs):
        from .report_catalogue import REGISTRY

        report_type = attrs.get('report_type', getattr(self.instance, 'report_type', None))
        prepared_by = attrs.get('prepared_by', getattr(self.instance, 'prepared_by', None))
        fmt = attrs.get('format', getattr(self.instance, 'format', None))
        definition = REGISTRY.get(report_type)
        if definition is None:
            raise serializers.ValidationError({'report_type': 'Choose a report from the catalogue.'})
        if 'period' not in definition.filters:
            raise serializers.ValidationError({'report_type': 'Only period-based reports can be scheduled.'})
        if definition.requires_project:
            raise serializers.ValidationError({'report_type': 'Per-project reports cannot be scheduled.'})
        if definition.requires_tender or definition.requires_reason:
            raise serializers.ValidationError({'report_type': 'Reports for one tender, or that need a stated reason, cannot be scheduled.'})
        if prepared_by and prepared_by.role != UserRole.ADMIN and prepared_by.role not in definition.roles:
            raise serializers.ValidationError({'prepared_by': f'{prepared_by.username} cannot generate this report.'})
        if fmt not in definition.formats:
            raise serializers.ValidationError({'format': 'This report is not available in that format.'})
        run_day = attrs.get('run_day', getattr(self.instance, 'run_day', 5))
        if not 1 <= int(run_day) <= 28:
            raise serializers.ValidationError({'run_day': 'Choose a day between 1 and 28.'})
        roles = attrs.get('recipient_roles', getattr(self.instance, 'recipient_roles', []))
        if any(r not in UserRole.values or r == UserRole.VENDOR for r in roles):
            raise serializers.ValidationError({'recipient_roles': 'Choose staff roles only.'})
        filters = attrs.get('filters') or {}
        attrs['filters'] = {k: v for k, v in filters.items() if k in {'district', 'technology', 'vendor', 'tender'} and v}
        return attrs


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """Report schedules and distribution lists (Super Admin)."""

    queryset = ReportSchedule.objects.select_related('prepared_by').prefetch_related('recipient_users').all()
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        if self.request.user.role != UserRole.ADMIN:
            return self.queryset.none()
        return self.queryset

    def _assert_admin(self):
        if self.request.user.role != UserRole.ADMIN:
            raise PermissionDenied('Only the Platform Administrator (Super Admin) can manage report schedules.')

    def create(self, request, *args, **kwargs):
        self._assert_admin()
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_admin()
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        from .report_workflow import next_run

        self._assert_admin()
        schedule = serializer.save(created_by=self.request.user)
        schedule.next_run_at = next_run(schedule, timezone.now())
        schedule.save(update_fields=['next_run_at'])
        log_audit(self.request.user, 'report_schedule_created', schedule, {'module': 'report', 'report_type': schedule.report_type})

    def perform_update(self, serializer):
        from .report_workflow import next_run

        self._assert_admin()
        schedule = serializer.save()
        schedule.next_run_at = next_run(schedule, timezone.now()) if schedule.active else None
        schedule.save(update_fields=['next_run_at'])
        log_audit(self.request.user, 'report_schedule_updated', schedule, {'module': 'report', 'active': schedule.active})

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        from .report_workflow import run_schedule

        self._assert_admin()
        schedule = self.get_object()
        report = run_schedule(schedule)
        log_audit(request.user, 'report_schedule_run_now', schedule, {'module': 'report', 'report_id': str(report.id)})
        return Response(_report_row(report), status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'], url_path='form-options')
    def form_options(self, request):
        from .report_catalogue import REGISTRY

        self._assert_admin()
        return Response({
            'reports': [
                {'id': d.id, 'title': d.title, 'formats': list(d.formats), 'roles': sorted(d.roles), 'formal': d.formal}
                for d in REGISTRY.values()
                if 'period' in d.filters and not (d.requires_project or d.requires_tender or d.requires_reason)
            ],
            'roles': [{'value': v, 'label': l} for v, l in UserRole.choices if v != UserRole.VENDOR],
            'preparers': [
                {'id': u.id, 'name': u.full_name or u.username, 'role': u.role}
                for u in User.objects.filter(is_active=True).exclude(role=UserRole.VENDOR).order_by('role', 'username')
            ],
        })
