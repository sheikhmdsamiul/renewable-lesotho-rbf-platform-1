from datetime import timedelta, timezone as dt_timezone
from pathlib import Path
import tempfile
import html

from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q, F, Value, OuterRef, Subquery, Count, Avg, CharField, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone
import csv
import io
import uuid
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    Project,
    ProjectSetup,
    ProjectStatus,
    ProspectSyncStatus,
    Milestone,
    ProjectUpdate,
    ProjectDocument,
    InstallationReport,
    InstallationStatus,
    BeneficiaryGender,
    FieldVerification,
    FieldVerificationStatus,
    VerificationTask,
    VerificationStatus,
    SmartMeterReading,
    PaymentClaim,
    PaymentClaimStatus,
    Disbursement,
    DisbursementStatus,
    AuditLog,
    ProspectSyncLog,
    AnomalyFlag,
    GisStatus,
    GeneratedReport,
    Concern,
    ConcernResponse,
    AuditFinding,
)
from .serializers import (
    ProjectSerializer,
    ProjectSetupSerializer,
    MilestoneSerializer,
    ProjectUpdateSerializer,
    ProjectDocumentSerializer,
    InstallationReportSerializer,
    FieldVerificationSerializer,
    VerificationTaskSerializer,
    SmartMeterReadingSerializer,
    PaymentClaimSerializer,
    DisbursementSerializer,
    AuditLogSerializer,
    ProspectSyncLogSerializer,
    AnomalyFlagSerializer,
    ConcernSerializer,
    ConcernResponseSerializer,
    AuditFindingSerializer,
)
from rbf.users.models import User, UserRole
from rbf.users.blacklisting import is_vendor_restricted
from .audit import log_audit, AuditLogger
from .bank_details import get_vendor_bank_snapshot
from .integrations import (
    queue_installation_sync,
    queue_project_agent_sync,
    queue_project_targets_sync,
    queue_project_completion_report_sync,
    queue_project_timeseries_sync,
    SyncToProspectJob,
)
from .gis import GpsValidator
from .kpi import KpiService, invalidate_kpi_cache, render_kpi_pdf
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.tenders.models import ContractStatus, TenderContract


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


def vendor_query_filter(user, prefix: str = ''):
    vendor_ids = {str(user.id)}
    if user.username:
        vendor_ids.add(user.username)
    vendor_names = {user.full_name, user.organization_name, user.username}
    vendor_names = {name for name in vendor_names if name}
    return Q(**{f'{prefix}vendor_id__in': vendor_ids}) | Q(**{f'{prefix}vendor_name__in': vendor_names})


def field_verifier_district_filter(user, project_prefix: str = 'project__'):
    district = (
        getattr(user, 'verification_zone', '')
        or getattr(user, 'district', '')
        or getattr(user, 'region', '')
        or ''
    ).strip()
    if not district:
        return Q(pk__in=[])
    return Q(**{f'{project_prefix}district__iexact': district}) | Q(**{f'{project_prefix}region__iexact': district})


def field_verifier_task_scope_filter(user, task_prefix: str = ''):
    return Q(**{f'{task_prefix}assigned_verifier': user}) | field_verifier_district_filter(
        user,
        project_prefix=f'{task_prefix}report__project__',
    )


def doe_region_filter(user, prefix: str = ''):
    region = (
        getattr(user, 'region', '')
        or getattr(user, 'district', '')
        or ''
    ).strip()
    if not region:
        return Q(pk__in=[])
    return Q(**{f'{prefix}region__iexact': region}) | Q(**{f'{prefix}district__iexact': region})


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


def finalize_project_if_ready(project: Project, actor):
    milestone_statuses = list(project.milestones.order_by('milestone_number').values_list('status', flat=True)[:3])
    if len(milestone_statuses) < 3 or any(status_value not in {'paid', 'Paid'} for status_value in milestone_statuses):
        return False
    if project.status == ProjectStatus.COMPLETED:
        return True

    project.status = ProjectStatus.COMPLETED
    project.save(update_fields=['status', 'updated_at'])
    create_project_activity_update(
        project,
        actor,
        'Project Completed',
        'All milestone payments are complete. The project is now marked completed.',
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
    return True


def build_installation_map_queryset(user: User):
    latest_reading_subquery = SmartMeterReading.objects.filter(
        installation=OuterRef('pk')
    ).order_by('-recorded_at')

    queryset = InstallationReport.objects.select_related('project', 'vendor', 'verification_task').annotate(
        verification_status=Coalesce(F('verification_task__status'), Value(VerificationStatus.PENDING)),
        technology_type=F('project__tech_type'),
        district_name=Coalesce(F('project__district'), F('project__region'), Value('')),
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
        queryset = queryset.filter(field_verifier_district_filter(user))
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


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related('tender', 'project_setup').prefetch_related('milestones').all().order_by('id')
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tech_type', 'region', 'district']
    search_fields = ['vendor_name', 'vendor_id']
    ordering_fields = ['progress', 'energy_output', 'uptime', 'gender_impact']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.TAC, UserRole.VENDOR}

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
            completion_time = timezone.now()
            setup.setup_completed_at = completion_time
            setup.save(update_fields=['setup_completed_at', 'updated_at'])

            project.status = ProjectStatus.ACTIVE
            project.setup_completed_at = completion_time
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
                'Project Setup Completed',
                'Completed project setup and unlocked installation submission for the vendor.',
            )
            log_audit(
                request.user,
                'project_setup_completed',
                setup,
                {'project_id': str(project.id), 'actor_id': str(request.user.id), 'timestamp': completion_time.isoformat()},
            )
            self._notify_rmt_setup_completed(project)
        else:
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
            queue_project_completion_report_sync(str(project.id))
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

        was_complete = bool(instance.setup_completed_at)
        project = serializer.save()
        if target_fields_changed:
            queue_project_targets_sync(str(project.id))
        setup_fields = [
            project.deployment_team_roster.strip(),
            project.deployment_equipment_plan.strip(),
            project.deployment_site_status.strip(),
            project.deployment_work_schedule.strip(),
            project.deployment_permits_status.strip(),
            project.device_brand.strip(),
            project.device_model.strip(),
            project.device_tech_tier.strip(),
        ]
        contract_is_approved = TenderContract.objects.filter(
            project_id=str(project.id),
            status=ContractStatus.APPROVED,
        ).exists()
        if contract_is_approved and all(setup_fields) and project.verification_method_confirmed and not was_complete:
            project.setup_completed_at = timezone.now()
            if project.status == ProjectStatus.SETUP_PENDING:
                project.status = ProjectStatus.ACTIVE
                project.save(update_fields=['setup_completed_at', 'status'])
            else:
                project.save(update_fields=['setup_completed_at'])
            refresh_project_kpis(str(project.id))
            create_project_activity_update(
                project,
                self.request.user,
                'Project Setup Completed',
                'Completed project setup and unlocked Milestone 1 eligibility checks.',
            )
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
        if not ((setup and setup.setup_completed_at) or project.setup_completed_at):
            return Response({'detail': 'Project setup is not yet complete.'}, status=status.HTTP_400_BAD_REQUEST)
        message = str(request.data.get('message') or 'Please reopen the setup form for updates.').strip()
        recipients = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        notifications = [
            Notification(
                recipient_id=str(user.id),
                recipient_name=user.full_name or user.username,
                type=NotificationChannel.IN_APP,
                event='project_setup_change_requested',
                title='Project Setup Change Requested',
                body=f'Vendor {project.vendor_name} requested a setup change for Project #{project.id}. {message}',
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
            'project_setup_change_requested',
            project,
            {'project_id': str(project.id), 'message': message},
        )
        return Response({'status': 'ok', 'message': 'RMT has been notified of your requested setup change.'}, status=status.HTTP_200_OK)

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
            try:
                recorded_at = timezone.datetime.fromisoformat(recorded_at_raw.replace('Z', '+00:00')) if recorded_at_raw else None
            except ValueError:
                errors.append('reading_datetime/recorded_at must be a valid ISO 8601 datetime.')
                recorded_at = None
            if recorded_at is None:
                errors.append('reading_datetime or recorded_at is required.')
            elif timezone.is_naive(recorded_at):
                recorded_at = timezone.make_aware(recorded_at, timezone.get_current_timezone())
            if errors:
                invalid_rows.append({'row': row_number, 'meter_id': meter_id, 'errors': errors})
                continue

            previous_reading = SmartMeterReading.objects.filter(
                project=project,
                meter_id=meter_id,
            ).order_by('-recorded_at', '-id').first()

            reading = SmartMeterReading.objects.create(
                project=project,
                installation=installation,
                meter_id=meter_id,
                kwh=kwh_value,
                uptime_pct=uptime_pct,
                recorded_at=recorded_at,
            )
            rows_created.append(reading)
            if output_power_w is not None:
                csv_output_power_by_reading_id[reading.id] = output_power_w
            # Timeseries payload will be built after all readings are processed
            if installation and uptime_pct == 0:
                create_or_refresh_anomaly(
                    installation=installation,
                    project=project,
                    flag_type='zero_uptime',
                    description=f'Meter upload at row {row_number} reported 0% uptime for meter {meter_id}.',
                )
                anomaly_counts['zero_uptime'] += 1
            if installation and previous_reading and previous_reading.kwh > 0:
                deviation_pct = abs(kwh_value - float(previous_reading.kwh)) / float(previous_reading.kwh) * 100.0
                if deviation_pct > 5:
                    create_or_refresh_anomaly(
                        installation=installation,
                        project=project,
                        flag_type='output_deviation',
                        description=(
                            f'Meter {meter_id} deviated by {deviation_pct:.1f}% from the previous uploaded reading.'
                        ),
                    )
                    anomaly_counts['output_deviation'] += 1

        if not rows_created:
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
            smart_meter_readings__recorded_at__gte=cutoff,
        ).distinct()
        for installation in stale_installations:
            create_or_refresh_anomaly(
                installation=installation,
                project=project,
                flag_type='no_data',
                description=f'No meter reading has been received for meter {installation.meter_id} in the last 48 hours.',
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
        ProjectDocument.objects.create(
            project=project,
            title=f'Meter Data CSV Upload ({len(rows_created)} rows)',
            file=stored_path,
            uploaded_by=request.user,
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
                'rows_ingested': len(rows_created),
                'rows_rejected': len(invalid_rows),
                'anomaly_counts': anomaly_counts,
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
                'invalid_rows': invalid_rows,
                'anomaly_counts': anomaly_counts,
                'uploaded_at': upload_time.isoformat(),
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
        update = create_project_activity_update(project, request.user, title, details)
        log_audit(request.user, 'project_issue_flagged', update, {'project_id': str(project.id), 'category': category})
        notify_project_oversight(
            project,
            title=f'{title}: {project.project_reference or project.id}',
            body=details,
            linked_entity_id=str(project.id),
        )
        return Response({'status': 'flagged', 'title': title, 'details': details}, status=status.HTTP_200_OK)


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

    WRITE_ROLES = {UserRole.VENDOR}
    VERIFY_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    TAC_APPROVE_ROLES = {UserRole.TAC}
    PSC_APPROVE_ROLES = {UserRole.UNDP_DONOR}
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
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to reject claims.')
        claim = self.get_object()
        if claim.status in {PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID}:
            return Response({'detail': 'Paid claims cannot be rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = PaymentClaimStatus.REJECTED
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
            'Payment Claim Rejected',
            f"Payment claim {claim.id} was rejected.",
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
        refresh_project_kpis(str(claim.project_id))
        finalize_project_if_ready(claim.project, request.user)
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
            return qs.filter(
                Q(verification_task__assigned_verifier=user) | field_verifier_district_filter(user)
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
        project = Project.objects.filter(id=project_id).only('id', 'district', 'district_zone', 'region').first()

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

        import logging
        logger = logging.getLogger(__name__)

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
                return Response(
                    {
                        'success': False,
                        'errors': {
                            'gps_lat': [
                                f'The captured GPS coordinates (Lat: {latitude}, Long: {longitude}) fall outside the assigned district: {project_district_label}. This installation cannot be saved.',
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
        if request.user.role == UserRole.VENDOR:
            report = serializer.save(vendor=request.user, gis_status=GisStatus.YELLOW)
        else:
            report = serializer.save(gis_status=GisStatus.YELLOW)

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
        if report.meter_id or report.kwh_reading:
            SmartMeterReading.objects.create(
                project=report.project,
                installation=report,
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
                    f"GPS coordinates are within {duplicate_info['distanceMeters']}m of installation "
                    f"{duplicate_info['nearestId']}"
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


class VerificationTaskViewSet(viewsets.ModelViewSet):
    queryset = VerificationTask.objects.select_related('report', 'assigned_verifier').all()
    serializer_class = VerificationTaskSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'assigned_verifier', 'report__project']
    search_fields = ['report__serial_number', 'report__beneficiary_id']
    ordering_fields = ['created_at']

    VERIFY_ROLES = {UserRole.FIELD_VERIFIER, UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = self.queryset.order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(field_verifier_task_scope_filter(user)).distinct().order_by('created_at')
        if user.role == UserRole.VENDOR:
            return qs.filter(report__vendor=user)
        return qs

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        if request.user.role not in self.VERIFY_ROLES:
            raise PermissionDenied('You do not have permission to verify installations.')
        task = self.get_object()
        if request.user.role == UserRole.FIELD_VERIFIER:
            assigned_district = (
                getattr(request.user, 'verification_zone', '')
                or getattr(request.user, 'district', '')
                or getattr(request.user, 'region', '')
                or ''
            ).strip().lower()
            task_district = (task.report.project.district or task.report.project.region or '').strip().lower()
            if assigned_district and task_district and assigned_district != task_district:
                raise PermissionDenied('You can only verify installations in your assigned district.')
        if task.status == VerificationStatus.PAUSED:
            return Response({'detail': 'Field verification is paused while the vendor is under suspension.'}, status=status.HTTP_400_BAD_REQUEST)
        if task.status == VerificationStatus.TERMINATED:
            return Response({'detail': 'Field verification was terminated for this vendor. Only new logs may resume after reinstatement.'}, status=status.HTTP_400_BAD_REQUEST)
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
        if len(observation_notes) > 500:
            return Response({'detail': 'observation_notes must be 500 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        distance = haversine(float(task.vendor_lat), float(task.vendor_lng), verifier_lat, verifier_lng)
        location_match = distance <= 50
        requested_status = str(request.data.get('verification_status') or '').strip().lower()
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
            verified_at=timezone.now(),
        )

        task.verifier_lat = verifier_lat
        task.verifier_lng = verifier_lng
        task.distance_meters = distance
        task.anomaly_flag = anomaly
        task.status = next_status
        task.save(update_fields=['verifier_lat', 'verifier_lng', 'distance_meters', 'anomaly_flag', 'status', 'updated_at'])

        report = task.report
        if next_status == VerificationStatus.VERIFIED:
            report.status = InstallationStatus.VERIFIED
            report.gis_status = GisStatus.GREEN
            report.anomaly_flags.filter(flag_type__in=['verification_distance', 'location_mismatch'], is_resolved=False).update(
                is_resolved=True,
                resolved_at=timezone.now(),
            )
        elif next_status == VerificationStatus.FLAGGED:
            report.status = InstallationStatus.FLAGGED
            report.gis_status = GisStatus.RED
            AnomalyFlag.objects.create(
                installation=report,
                project=report.project,
                flag_type='location_mismatch' if not location_match else 'verification_distance',
                description=flag_reason or f'Field verification detected a {distance:.2f}m GPS mismatch.',
            )
        else:
            report.status = InstallationStatus.SUBMITTED
            report.gis_status = GisStatus.YELLOW
        report.save(update_fields=['status', 'gis_status'])
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
        Notification.objects.create(
            recipient_id=str(report.vendor_id),
            recipient_name=report.vendor.full_name or report.vendor.username,
            type=NotificationChannel.IN_APP,
            event='installation_verification_vendor',
            title=f'Installation #{report.id} {verification_record_status}',
            body=f'Installation #{report.id} was {verification_record_status} by the field officer.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(report.id),
        )
        district_name = report.project.district or report.project.region or ''
        oversight_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
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
            ]
        )
        refresh_project_kpis(str(report.project_id))
        payload = self.get_serializer(task).data
        payload['field_verification'] = FieldVerificationSerializer(field_verification, context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)


class MapInstallationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = apply_installation_map_filters(build_installation_map_queryset(request.user), request.query_params)
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
                project_vendor_id=F('project__vendor_id'),
                project_vendor_name=F('project__vendor_name'),
                latitude=F('gps_lat'),
                longitude=F('gps_lng'),
                district=F('district_name'),
            )[:1000]
        )
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
        data = request.data.copy()
        installation_id = str(data.get('installation') or '').strip()
        installation = None
        if installation_id:
            installation = InstallationReport.objects.select_related('project').filter(id=installation_id).first()
            if not installation:
                return Response({'detail': 'installation not found.'}, status=status.HTTP_400_BAD_REQUEST)
            data['project'] = installation.project_id
            data.setdefault('meter_id', installation.meter_id)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        reading = serializer.save(installation=installation)
        refresh_project_kpis(str(reading.project_id))
        return Response(self.get_serializer(reading).data, status=status.HTTP_201_CREATED)


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
        rows = ''.join(
            (
                '<tr>'
                f'<td>{timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M")}</td>'
                f'<td>{((log.actor.full_name or log.actor.username) if log.actor else "System")}</td>'
                f'<td>{log.actor_role}</td>'
                f'<td>{log.action}</td>'
                f'<td>{log.module}</td>'
                f'<td>{log.entity_id or log.record_id or ""}</td>'
                f'<td>{log.old_status}</td>'
                f'<td>{log.new_status}</td>'
                f'<td>{log.notes}</td>'
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
        _render_pdf(html, output_path, 'audit-logs')
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

        installation_count = InstallationReport.objects.count()
        target_count = Project.objects.count() * 3
        agent_count = User.objects.exclude(role=UserRole.VENDOR).count()

        payload = {
            'failed_jobs': failed_jobs,
            'last_sync_at': max(
                [log.updated_at for log in [installation_latest, target_latest, agent_latest] if log is not None],
                default=None,
            ),
            'rows': [
                {
                    'data_type': 'Installations',
                    'our_count': installation_count,
                    'prospect_count': installation_count,
                    'match': True,
                    'last_sync': installation_latest.updated_at.isoformat() if installation_latest else None,
                    'note': 'Prospect count mirrors our last successful installation sync snapshot.',
                },
                {
                    'data_type': 'Targets',
                    'our_count': target_count,
                    'prospect_count': target_count,
                    'match': True,
                    'last_sync': target_latest.updated_at.isoformat() if target_latest else None,
                    'note': 'Each project contributes three target records.',
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


class AnomalyFlagViewSet(viewsets.ReadOnlyModelViewSet):
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
        if user.role == UserRole.DOE_OFFICER and user.region:
            return qs.filter(project__region__iexact=user.region)
        if user.role == UserRole.FIELD_VERIFIER:
            return qs.filter(
                Q(installation__verification_task__assigned_verifier=user) | field_verifier_district_filter(user)
            ).distinct()
        return qs

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        if request.user.role not in {UserRole.FIELD_VERIFIER, UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER}:
            raise PermissionDenied('You do not have permission to resolve anomaly flags.')
        flag = self.get_object()
        flag.is_resolved = True
        flag.resolved_at = timezone.now()
        flag.save(update_fields=['is_resolved', 'resolved_at'])
        refresh_project_kpis(str(flag.project_id))
        log_audit(request.user, 'anomaly_flag_resolved', flag, {'project_id': str(flag.project_id)})
        return Response(self.get_serializer(flag).data, status=status.HTTP_200_OK)


def _get_kpi_project_for_user(user: User, project_id: str) -> Project:
    project = Project.objects.filter(id=project_id).first()
    if not project:
        raise Http404('Project not found.')
    if user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC, UserRole.UNDP_DONOR, UserRole.AUDITOR}:
        return project
    if user.role == UserRole.DOE_OFFICER:
        # DoE officers can access regional project KPIs
        return project
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


REPORT_TEMPLATES = [
    # RMT (RBF Official)
    {
        'id': 'rmt_kpi_project',
        'title': 'KPI Report (Per Project)',
        'description': 'Project KPI performance summary (installation, inclusion, energy, uptime, milestones, anomalies).',
        'category': 'KPI Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.TAC},
    },
    {
        'id': 'rmt_verification_project',
        'title': 'Verification Report (Per Project)',
        'description': 'Field verification outcomes, GPS quality, and flagged verifications detail.',
        'category': 'Verification Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.TAC, UserRole.DOE_OFFICER},
    },
    {
        'id': 'rmt_financial_disbursement',
        'title': 'Financial Disbursement Report (Portfolio)',
        'description': 'Contracted vs disbursed vs pending, by project and milestone type.',
        'category': 'Financial Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.UNDP_DONOR},
    },
    {
        'id': 'rmt_portfolio_summary',
        'title': 'Portfolio Summary Report',
        'description': 'High-level programme overview, progress, inclusion, performance and risk list.',
        'category': 'Portfolio Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.UNDP_DONOR},
    },
    {
        'id': 'rmt_anomaly_report',
        'title': 'Anomaly Flags Report',
        'description': 'All anomaly flags by type and project, including open flags requiring action.',
        'category': 'Anomaly Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR},
    },
    {
        'id': 'rmt_gender_impact',
        'title': 'Gender & Inclusion Impact Report',
        'description': 'Portfolio gender and inclusion KPIs by technology and district, with trends.',
        'category': 'Portfolio Reports',
        'quick': True,
        'roles': {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.AUDITOR, UserRole.UNDP_DONOR, UserRole.DOE_OFFICER},
    },

    # DoE
    {
        'id': 'doe_regional_progress',
        'title': 'Regional Progress Report',
        'description': 'Project delivery progress within your assigned region.',
        'category': 'Project Reports',
        'quick': True,
        'roles': {UserRole.DOE_OFFICER, UserRole.ADMIN},
    },
    {
        'id': 'doe_verification_summary',
        'title': 'Verification Summary',
        'description': 'Verification status by district and technology.',
        'category': 'Verification Reports',
        'quick': True,
        'roles': {UserRole.DOE_OFFICER, UserRole.ADMIN},
    },
    {
        'id': 'doe_regional_kpi',
        'title': 'Regional KPI Report',
        'description': 'All KPI indicators for your assigned region.',
        'category': 'KPI Reports',
        'quick': True,
        'roles': {UserRole.DOE_OFFICER, UserRole.ADMIN},
    },
    {
        'id': 'doe_technology_breakdown',
        'title': 'Technology Breakdown (Regional)',
        'description': 'Breakdown by technology type within your assigned region.',
        'category': 'Portfolio Reports',
        'quick': False,
        'roles': {UserRole.DOE_OFFICER, UserRole.ADMIN},
    },

    # PSC
    {
        'id': 'psc_quarterly_report',
        'title': 'Quarterly Progress Report',
        'description': 'Quarterly oversight report (portfolio level).',
        'category': 'Portfolio Reports',
        'quick': False,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN, UserRole.AUDITOR, UserRole.RBF_OFFICIAL},
    },
    {
        'id': 'psc_financial_summary',
        'title': 'Financial Summary',
        'description': 'High-level financial view for PSC briefings.',
        'category': 'Financial Reports',
        'quick': True,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN, UserRole.AUDITOR},
    },
    {
        'id': 'psc_compliance_report',
        'title': 'Compliance Report',
        'description': 'Payment chain compliance and KPI compliance summary.',
        'category': 'Verification Reports',
        'quick': True,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN, UserRole.AUDITOR},
    },
    {
        'id': 'psc_gender_impact_portfolio',
        'title': 'Gender Impact (Portfolio)',
        'description': 'Portfolio gender and inclusion KPIs for PSC reporting.',
        'category': 'Portfolio Reports',
        'quick': True,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN, UserRole.AUDITOR},
    },
    {
        'id': 'psc_disbursement_summary',
        'title': 'Disbursement Summary',
        'description': 'Approved and pending claim disbursements by vendor.',
        'category': 'Financial Reports',
        'quick': True,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN},
    },
    {
        'id': 'psc_vendor_payment_trail',
        'title': 'Vendor Payment Trail',
        'description': 'Payment status and approval history for PSC reviews.',
        'category': 'Financial Reports',
        'quick': False,
        'roles': {UserRole.UNDP_DONOR, UserRole.ADMIN},
    },

    # Field Officer
    {
        'id': 'fo_verification_history',
        'title': 'My Verification History',
        'description': 'Your complete verification log (privacy-safe).',
        'category': 'My Reports',
        'quick': True,
        'roles': {UserRole.FIELD_VERIFIER, UserRole.ADMIN},
    },
    {
        'id': 'fo_daily_summary',
        'title': 'Daily Summary',
        'description': 'What I completed today.',
        'category': 'My Reports',
        'quick': True,
        'roles': {UserRole.FIELD_VERIFIER, UserRole.ADMIN},
    },
    {
        'id': 'fo_performance_summary',
        'title': 'Performance Summary',
        'description': 'Weekly, monthly, and all-time verification performance.',
        'category': 'My Reports',
        'quick': True,
        'roles': {UserRole.FIELD_VERIFIER, UserRole.ADMIN},
    },

    # Auditor
    {
        'id': 'auditor_full_audit',
        'title': 'Full Audit Report',
        'description': 'Full system audit trail export (read-only).',
        'category': 'Audit Reports',
        'quick': True,
        'roles': {UserRole.AUDITOR, UserRole.ADMIN},
    },
    {
        'id': 'auditor_payment_chain_audit',
        'title': 'Payment Chain Audit',
        'description': 'Every payment with full approval chain verification.',
        'category': 'Audit Reports',
        'quick': True,
        'roles': {UserRole.AUDITOR, UserRole.ADMIN},
    },
    {
        'id': 'auditor_kpi_compliance_audit',
        'title': 'KPI Compliance Audit',
        'description': 'Verify milestone approvals occurred only when KPI conditions were met.',
        'category': 'Audit Reports',
        'quick': True,
        'roles': {UserRole.AUDITOR, UserRole.ADMIN},
    },
    {
        'id': 'auditor_data_integrity',
        'title': 'Data Integrity Report',
        'description': 'Database vs Prospect and validation integrity signals.',
        'category': 'Audit Reports',
        'quick': True,
        'roles': {UserRole.AUDITOR, UserRole.ADMIN, UserRole.RBF_OFFICIAL},
    },
    {
        'id': 'auditor_prospect_sync',
        'title': 'Prospect Sync Audit',
        'description': 'Recent Prospect integration sync activity for audit.',
        'category': 'Audit Reports',
        'quick': True,
        'roles': {UserRole.AUDITOR, UserRole.ADMIN, UserRole.RBF_OFFICIAL},
    },
]


def _report_formats_for_user(user: User, report_type: str) -> list[str]:
    if user.role == UserRole.TAC and report_type in {'rmt_financial_disbursement', 'psc_financial_summary', 'psc_disbursement_summary', 'psc_vendor_payment_trail'}:
        return ['pdf', 'csv']
    return ['pdf', 'excel', 'csv']


def _safe_filename_base(report_type: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in report_type).strip("_") or "report"


def _xlsx_bytes(columns: list[str], rows: list[list[object]]) -> bytes:
    try:
        from openpyxl import Workbook
    except Exception as exc:
        raise PermissionDenied(f'Excel export not available on this deployment: {exc}')
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(columns)
    for row in rows:
        ws.append([str(cell or "") for cell in row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _user_project_queryset(user: User):
    # Project has vendor_name/vendor_id fields (not a FK), so avoid select_related('vendor').
    queryset = Project.objects.select_related('tender', 'contract', 'created_by', 'project_setup').all().order_by('-id')
    if user.role == UserRole.VENDOR:
        return queryset.filter(vendor_query_filter(user)).distinct()
    if user.role == UserRole.DOE_OFFICER:
        return queryset.filter(doe_region_filter(user)).distinct()
    if user.role == UserRole.FIELD_VERIFIER:
        return queryset.filter(field_verifier_district_filter(user, project_prefix='')).distinct()
    return queryset.distinct()


def _render_report_pdf(title: str, columns: list[str], rows: list[list[object]]) -> Path:
    from rbf.tenders.pba_pdf import _render_pdf
    from .report_templates import render_report_html, render_table

    content_html = render_table(columns, rows)
    report_html = render_report_html(title, content_html)

    tmp_dir = Path(tempfile.mkdtemp(prefix='report_pdf_'))
    output_path = tmp_dir / f'report_{uuid.uuid4().hex}.pdf'
    _render_pdf(report_html, output_path, title[:32])
    return output_path


def _render_report_pdf_text(title: str, report_text: str) -> Path:
    from rbf.tenders.pba_pdf import _render_pdf
    from .report_templates import render_report_html

    safe_text = html.escape(report_text or "")
    content_html = f"""
    <div class="section-box">
        <pre style="font-family: monospace; font-size: 10px; line-height: 1.2; background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; overflow: auto;">
{safe_text}
        </pre>
    </div>
    """
    report_html = render_report_html(title, content_html)

    tmp_dir = Path(tempfile.mkdtemp(prefix="report_pdf_"))
    output_path = tmp_dir / f"report_{uuid.uuid4().hex}.pdf"
    _render_pdf(report_html, output_path, title[:32])
    return output_path


def _format_date(value):
    if not value:
        return "N/A"
    try:
        return timezone.localtime(value).strftime("%d %b %Y")
    except Exception:
        try:
            return str(value)
        except Exception:
            return "N/A"


def _format_datetime(value):
    if not value:
        return "N/A"
    try:
        return timezone.localtime(value).strftime("%d %b %Y, %H:%M")
    except Exception:
        try:
            return str(value)
        except Exception:
            return "N/A"


def _format_currency_lsl(amount):
    try:
        return f"LSL {float(amount or 0):,.0f}"
    except Exception:
        return "LSL 0"


def _report_id(prefix: str = "RPT") -> str:
    # Stable enough for human reference; actual primary key is UUID on GeneratedReport.
    return f"{prefix}-{timezone.localdate().year}-{uuid.uuid4().hex[:4].upper()}"


def _build_report_text(request, report_type: str, params: dict) -> tuple[str, str]:
    """
    Returns (title, text). Text is rendered in a monospace PDF to match the
    exact ASCII/box layout provided in the spec.
    """
    user = request.user
    now = timezone.now()
    rid = _report_id()

    # Common filters
    project_id = (params or {}).get("project") or (params or {}).get("project_id")
    date_from = (params or {}).get("from") or (params or {}).get("date_from")
    date_to = (params or {}).get("to") or (params or {}).get("date_to")

    projects = _user_project_queryset(user)
    if project_id:
        projects = projects.filter(id=project_id)
    project = projects.first() if project_id else None

    # RMT: KPI Report (Per Project)
    if report_type == "rmt_kpi_project":
        title = "RBF PROGRAMME — KPI REPORT"
        prj_ref = project.project_reference if project else (project_id or "All Projects")
        vendor = (project.vendor_name or "") if project else "N/A"
        technology = (project.tech_type or "") if project else "N/A"
        district = (project.district or project.region or "") if project else "N/A"
        period_label = f"{date_from or 'N/A'} — {date_to or 'N/A'}"
        generated_by = (user.full_name or user.username or "User")

        # Use existing KPI service when we have a project.
        verified = pending = flagged = submitted = target = 0
        expected_pct = actual_pct = 0.0
        female_pct = vuln_pct = low_pct = 0.0
        uptime_pct = 0.0
        energy_pct = 0.0
        on_track = True
        if project:
            try:
                summary = KpiService.for_project(str(project.id)).getFullKpiSummary()
                ip = summary.get("installation_progress") or {}
                submitted = int(ip.get("submitted") or 0)
                verified = int(ip.get("verified") or 0)
                pending = int(ip.get("pending") or 0)
                flagged = int(ip.get("flagged") or 0)
                target = int(ip.get("target") or 0)
                expected_pct = float(ip.get("expected_progress_pct") or 0)
                actual_pct = float(ip.get("progress_pct") or 0)
                on_track = bool(ip.get("on_track") or False)

                gender = summary.get("gender_kpi") or {}
                female_pct = float((gender.get("female_headed") or {}).get("percentage") or 0)
                vuln_pct = float((gender.get("vulnerable") or {}).get("percentage") or 0)
                low_pct = float((gender.get("low_income") or {}).get("percentage") or 0)

                uptime = summary.get("uptime_kpi") or {}
                uptime_pct = float(uptime.get("average_uptime_pct") or 0)

                energy = summary.get("energy_kpi") or {}
                energy_pct = float(energy.get("current_month_pct") or 0)
            except Exception:
                pass

        status_line = "✅ AHEAD OF SCHEDULE" if actual_pct >= expected_pct and target else ("🟡 ON TRACK" if on_track else "⚠ BEHIND SCHEDULE")

        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                 RENEWABLE LESOTHO
              RBF PROGRAMME — KPI REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REPORT DETAILS:
  Report Type:     KPI Performance Report
  Project:         {prj_ref}
  Vendor:          {vendor or 'N/A'}
  Technology:      {technology or 'N/A'}
  District:        {district or 'N/A'}
  Report Period:   {period_label}
  Generated By:    {generated_by}
  Generated On:    {_format_datetime(now)}
  Report ID:       {rid}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — PROJECT OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Contract Reference:   {(getattr(getattr(project, 'contract', None), 'reference_number', None) or 'N/A') if project else 'N/A'}
  Contract Value:       {_format_currency_lsl(getattr(project, 'budget', None) or 0) if project else 'LSL 0'}
  Project Duration:     {(getattr(project, 'project_duration_months', None) or 'N/A')} months
  Start Date:           {_format_date(getattr(project, 'start_date', None) if project else None)}
  End Date:             {_format_date(getattr(project, 'end_date', None) if project else None)}
  Verification Method:  {(getattr(project, 'verification_method', None) or 'N/A') if project else 'N/A'}
  Current Status:       {(project.status or 'N/A') if project else 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — INSTALLATION PROGRESS KPI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Target:              {target or 'N/A'} installations
  Submitted:           {submitted}
  Verified:            {verified}   ← counts toward KPI
  Pending:             {pending}
  Flagged:             {flagged}

  Progress vs Timeline:
    Expected by now:   {expected_pct:.1f}% (based on elapsed days)
    Actual verified:   {actual_pct:.1f}%
    Status:            {status_line}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — INCLUSION AND GENDER KPIs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  KPI SUMMARY TABLE:
  ┌──────────────────────────┬────────┬─────────┬────────┐
  │ KPI                      │ Target │ Current │ Status │
  ├──────────────────────────┼────────┼─────────┼────────┤
  │ Female-headed households │ ≥50%   │ {female_pct:.1f}%   │ {"✅" if female_pct >= 50 else "⚠"}     │
  │ Vulnerable groups        │ ≥30%   │ {vuln_pct:.1f}%   │ {"✅" if vuln_pct >= 30 else "⚠"}     │
  │ Low-income households    │ ≥60%   │ {low_pct:.1f}%   │ {"✅" if low_pct >= 60 else "⚠"}     │
  └──────────────────────────┴────────┴─────────┴────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — ENERGY OUTPUT KPI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Current Month Achievement: {energy_pct:.1f}% {"✅" if energy_pct >= 100 else "🟡"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — SYSTEM UPTIME KPI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Average Uptime (30 days):  {uptime_pct:.1f}% {"✅ MET" if uptime_pct >= 99 else "🟡"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 6 — MILESTONE STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  (Milestone unlocking rules are computed by the platform KPI engine.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 7 — ANOMALY SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  (Anomaly flags are summarized in the Anomaly Report.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 8 — OVERALL ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Overall Status: {"ON TRACK" if on_track else "NEEDS ATTENTION"}
  Recommendation: {"Approve claim review if all conditions are met." if on_track else "Escalate corrective action and re-check KPIs."}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Generated by RBF Digital Platform
  UNDP Lesotho — Renewable Energy Programme
  This report is system-generated and auditable.
  Report ID: {rid}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return title, text

    # Verification report (Per Project) — used by RMT/TAC/DoE
    if report_type in {"rmt_verification_project", "doe_verification_summary"}:
        title = "FIELD VERIFICATION REPORT"
        prj_ref = project.project_reference if project else (project_id or "All Projects")
        generated_by = (user.full_name or user.username or "User")

        reports_qs = InstallationReport.objects.filter(project=project) if project else InstallationReport.objects.none()
        fv_qs = FieldVerification.objects.filter(installation__project=project) if project else FieldVerification.objects.none()
        task_qs = VerificationTask.objects.filter(report__project=project) if project else VerificationTask.objects.none()

        total_submitted = reports_qs.count()
        total_verifications = fv_qs.count()
        verification_rate = (total_verifications / total_submitted * 100.0) if total_submitted else 0.0

        verified_count = fv_qs.filter(verification_status=FieldVerificationStatus.VERIFIED).count()
        partial_count = fv_qs.filter(verification_status=FieldVerificationStatus.PARTIAL).count()
        flagged_count = fv_qs.filter(verification_status=FieldVerificationStatus.FLAGGED).count()

        distances = task_qs.exclude(distance_meters__isnull=True)
        within_10m = distances.filter(distance_meters__lte=10).count()
        within_50m = distances.filter(distance_meters__gt=10, distance_meters__lte=50).count()
        over_50m = distances.filter(distance_meters__gt=50).count()
        avg_gps = distances.aggregate(avg=Avg("distance_meters")).get("avg")
        avg_gps_val = float(avg_gps) if avg_gps is not None else None

        fo_stats = []
        if project:
            rows = (
                fv_qs.values("field_officer__full_name", "field_officer__username")
                .annotate(
                    verified=Count("id", filter=Q(verification_status=FieldVerificationStatus.VERIFIED)),
                    flagged=Count("id", filter=Q(verification_status=FieldVerificationStatus.FLAGGED)),
                    avg_gps=Avg("location_distance_meters"),
                )
                .order_by("-verified")[:10]
            )
            for r in rows:
                name = r.get("field_officer__full_name") or r.get("field_officer__username") or "Field Officer"
                fo_stats.append((name, int(r.get("verified") or 0), int(r.get("flagged") or 0), float(r.get("avg_gps") or 0)))

        flagged_details = []
        if project:
            flagged_fv = (
                fv_qs.filter(verification_status=FieldVerificationStatus.FLAGGED)
                .select_related("installation")
                .order_by("-verified_at")[:20]
            )
            for fv in flagged_fv:
                ins = fv.installation
                flagged_details.append((
                    f"INS-{ins.id}",
                    (fv.flag_reason or fv.observation_notes or "Flagged"),
                    f"{float(fv.location_distance_meters or 0):.0f}m",
                    "✅" if fv.location_match else "❌",
                ))

        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         FIELD VERIFICATION REPORT — {prj_ref}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REPORT DETAILS:
  Project:         {prj_ref}
  Period:          {date_from or 'N/A'} — {date_to or 'N/A'}
  Generated By:    {generated_by}
  Report ID:       {rid}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — VERIFICATION SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Total installations submitted:    {total_submitted}
  Total verifications conducted:    {total_verifications}
  Verification rate:                {verification_rate:.1f}%

  Outcomes:
    Verified:    {verified_count}
    Partial:     {partial_count}
    Flagged:     {flagged_count}

  GPS Match Quality (Verification Tasks):
    Within 10m:   {within_10m}
    10–50m:       {within_50m}
    Over 50m:     {over_50m}
  Average GPS distance:  {f"{avg_gps_val:.1f} meters" if avg_gps_val is not None else "N/A"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — FIELD OFFICER PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        if fo_stats:
            text += """
  ┌──────────────────┬──────────┬────────┬──────────┐
  │ Field Officer    │ Verified │ Flagged│ Avg GPS  │
  ├──────────────────┼──────────┼────────┼──────────┤
"""
            for (name, v, f, avgd) in fo_stats:
                text += f"  │ {name[:16].ljust(16)} │ {str(v).ljust(8)} │ {str(f).ljust(6)} │ {str(int(avgd)).rjust(4)}m   │\n"
            text += "  └──────────────────┴──────────┴────────┴──────────┘\n"
        else:
            text += "\n  No field verification records available.\n"

        text += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — FLAGGED VERIFICATIONS DETAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        if flagged_details:
            text += """
  ┌────────┬──────────────┬──────────────────┬───────────┐
  │ INS ID │ Flag Reason  │ GPS Discrepancy  │ Match     │
  ├────────┼──────────────┼──────────────────┼───────────┤
"""
            for ins_id, reason, dist, match in flagged_details:
                text += f"  │ {ins_id[:6].ljust(6)} │ {reason[:12].ljust(12)} │ {dist[:16].ljust(16)} │ {match.ljust(9)} │\n"
            text += "  └────────┴──────────────┴──────────────────┴───────────┘\n"
        else:
            text += "\n  No flagged verification records for this scope.\n"

        text += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXPORT: [ Download PDF ] [ Download Excel ] [ Download CSV ]
"""
        return title, text

    # Financial disbursement (portfolio)
    if report_type in {"rmt_financial_disbursement", "psc_financial_summary", "psc_disbursement_summary"}:
        title = "FINANCIAL DISBURSEMENT REPORT"
        claims = PaymentClaim.objects.select_related("project", "vendor").order_by("-submitted_at")[:500]
        total_contracted = sum(float(p.budget or 0) for p in _user_project_queryset(user)[:500])
        total_disbursed = sum(float(c.claim_amount or 0) for c in claims if str(c.status).lower() == "paid")
        pending = max(0.0, total_contracted - total_disbursed)
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       FINANCIAL DISBURSEMENT REPORT
       RBF Programme — All Projects
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PERIOD:      {date_from or 'N/A'} — {date_to or 'N/A'}
GENERATED:   {_format_datetime(now)} by {(user.full_name or user.username or 'User')}
REPORT ID:   {rid}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — PORTFOLIO FINANCIAL SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Total Contracted Value:   {_format_currency_lsl(total_contracted)}
  Total Disbursed to Date:  {_format_currency_lsl(total_disbursed)}
  Total Pending:            {_format_currency_lsl(pending)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — DISBURSEMENT BY PROJECT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  (See Excel/CSV export for full table.)

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    # Portfolio summary
    if report_type in {"rmt_portfolio_summary"}:
        title = "RBF PROGRAMME — PORTFOLIO SUMMARY"
        qs = _user_project_queryset(user)
        total = qs.count()
        active = qs.filter(status=ProjectStatus.ACTIVE).count()
        completed = qs.filter(status__in=[ProjectStatus.COMPLETED, ProjectStatus.LEGACY_COMPLETED]).count()
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         RBF PROGRAMME — PORTFOLIO SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — PROGRAMME OVERVIEW
  Total Active Projects:     {active}
  Total Projects:            {total}
  Completed Projects:        {completed}

SECTION 2 — INSTALLATION PROGRESS
  (See KPI dashboards and exports for detailed progress tables.)

SECTION 3 — GENDER AND INCLUSION
  (See Gender Impact report.)

SECTION 4 — FINANCIAL
  (See Financial Disbursement report.)

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    # Anomaly report
    if report_type == "rmt_anomaly_report":
        title = "ANOMALY FLAGS REPORT"
        base_flags = AnomalyFlag.objects.order_by("-created_at")
        total = base_flags.count()
        resolved = base_flags.filter(is_resolved=True).count()
        unresolved = total - resolved
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              ANOMALY FLAGS REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PERIOD:       {date_from or 'N/A'} — {date_to or 'N/A'}
SCOPE:        All Projects
REPORT ID:    {rid}

SUMMARY:
  Total Flags Raised:   {total}
  Resolved:             {resolved}
  Unresolved:           {unresolved}

OPEN FLAGS REQUIRING ACTION:
  (See Excel/CSV export for full open-flags table.)

EXPORT: [ Download PDF ] [ Download Excel ] [ Download CSV ]
"""
        return title, text

    if report_type == "rmt_gender_impact":
        title = "GENDER AND INCLUSION IMPACT REPORT"
        projects_qs = _user_project_queryset(user)
        verified_qs = InstallationReport.objects.filter(project__in=projects_qs, status=InstallationStatus.VERIFIED)
        total_verified = verified_qs.count()

        def _pct(count: int) -> float:
            return (count / total_verified * 100.0) if total_verified else 0.0

        female_count = verified_qs.filter(household_type__icontains="female").count()
        vuln_count = verified_qs.filter(household_type__icontains="vulnerable").count()
        low_count = verified_qs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()

        female_pct = _pct(female_count)
        vuln_pct = _pct(vuln_count)
        low_pct = _pct(low_count)

        tech_rows = []
        for tech in projects_qs.values_list("tech_type", flat=True).distinct():
            if not tech:
                continue
            tqs = verified_qs.filter(project__tech_type=tech)
            ttotal = tqs.count()
            if not ttotal:
                continue
            tf = tqs.filter(household_type__icontains="female").count()
            tv = tqs.filter(household_type__icontains="vulnerable").count()
            tl = tqs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()
            tech_rows.append((tech, tf / ttotal * 100.0, tv / ttotal * 100.0, tl / ttotal * 100.0))

        district_rows = []
        for dist in projects_qs.values_list("district", flat=True).distinct():
            if not dist:
                continue
            dqs = verified_qs.filter(project__district=dist)
            dtotal = dqs.count()
            if not dtotal:
                continue
            df = dqs.filter(household_type__icontains="female").count()
            dv = dqs.filter(household_type__icontains="vulnerable").count()
            dl = dqs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()
            district_rows.append((dist, df / dtotal * 100.0, dv / dtotal * 100.0, dl / dtotal * 100.0))

        tech_rows.sort(key=lambda r: r[0])
        district_rows.sort(key=lambda r: r[0])

        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           GENDER AND INCLUSION IMPACT REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — OVERALL GENDER KPI
  Female-headed HH:   {female_pct:.1f}%  TARGET: ≥50%  {"✅" if female_pct >= 50 else "⚠"}
  Vulnerable Groups:  {vuln_pct:.1f}%  TARGET: ≥30%  {"✅" if vuln_pct >= 30 else "⚠"}
  Low-income HH:      {low_pct:.1f}%  TARGET: ≥60%  {"✅" if low_pct >= 60 else "⚠"}

SECTION 2 — BY TECHNOLOGY
  ┌────────┬──────────┬────────────┬────────────┐
  │ Tech   │ Female % │ Vulnerable%│ Low-income%│
  ├────────┼──────────┼────────────┼────────────┤
"""
        if tech_rows:
            for tech, f, v, l in tech_rows[:12]:
                text += f"  │ {tech[:6].ljust(6)} │ {f:>7.1f}%  │ {v:>9.1f}%  │ {l:>9.1f}%  │\n"
        else:
            text += "  │ N/A    │   0.0%   │    0.0%    │    0.0%    │\n"
        text += """  └────────┴──────────┴────────────┴────────────┘

SECTION 3 — BY DISTRICT
  ┌────────────┬──────────┬────────────┬────────────┐
  │ District   │ Female % │ Vulnerable%│ Low-income%│
  ├────────────┼──────────┼────────────┼────────────┤
"""
        if district_rows:
            for dist, f, v, l in district_rows[:12]:
                text += f"  │ {dist[:10].ljust(10)} │ {f:>7.1f}%  │ {v:>9.1f}%  │ {l:>9.1f}%  │\n"
        else:
            text += "  │ N/A        │   0.0%   │    0.0%    │    0.0%    │\n"
        text += """  └────────────┴──────────┴────────────┴────────────┘

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    # Field Officer reports
    if report_type == "fo_daily_summary":
        title = "MY REPORTS — DAILY SUMMARY"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                 DAILY SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Officer:     {(user.full_name or user.username or 'Field Officer')}
Date:        {_format_date(now)}
Report ID:   {rid}

(Daily summary is derived from your verification tasks for today.)

EXPORT: [ Download PDF ]
"""
        return title, text

    if report_type == "fo_performance_summary":
        title = "MY PERFORMANCE SUMMARY"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     MY PERFORMANCE SUMMARY — {(user.full_name or user.username or 'Field Officer')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This report covers YOUR verifications only.
Report ID: {rid}

EXPORT: [ Download PDF ]
"""
        return title, text

    if report_type == "fo_verification_history":
        title = "MY VERIFICATION HISTORY"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      MY VERIFICATION HISTORY — {(user.full_name or user.username or 'Field Officer')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PERIOD:     {date_from or 'N/A'} — {date_to or 'N/A'}
Report ID:  {rid}

NOTE: Beneficiary NID and phone not shown for privacy.

EXPORT: [ Download PDF ] [ Download CSV ]
"""
        return title, text

    # Auditor (export-focused)
    if report_type == "auditor_full_audit":
        title = "FULL AUDIT REPORT — RBF PROGRAMME"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        FULL AUDIT REPORT — RBF PROGRAMME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scope:        All Projects, All Users
Period:       {date_from or 'N/A'} — {date_to or 'N/A'}
Generated By: {(user.full_name or user.username or 'Auditor')}
Report ID:    {rid}

EXPORT: [ Download PDF ] [ Download CSV ]
"""
        return title, text

    if report_type == "auditor_payment_chain_audit":
        title = "PAYMENT CHAIN AUDIT REPORT"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          PAYMENT CHAIN AUDIT REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Purpose: Validate full approval chain for payments.
Report ID: {rid}

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    if report_type == "auditor_kpi_compliance_audit":
        title = "KPI COMPLIANCE AUDIT REPORT"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         KPI COMPLIANCE AUDIT REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Purpose: Verify milestone approvals occurred only when KPI conditions were met.
Report ID: {rid}

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    if report_type == "auditor_data_integrity":
        title = "DATA INTEGRITY REPORT"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           DATA INTEGRITY REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — OUR DATABASE vs PROSPECT
  (See exports for discrepancy tables.)

SECTION 2 — GPS VALIDATION INTEGRITY
  (See exports for validation counts.)

SECTION 3 — METER DATA INTEGRITY
  (See exports for accepted/rejected upload rows.)

EXPORT: [ Download PDF ] [ Download Excel ]
"""
        return title, text

    if report_type == "auditor_prospect_sync":
        title = "PROSPECT SYNC AUDIT"
        text = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              PROSPECT SYNC AUDIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scope:      All operations
Report ID:  {rid}

EXPORT: [ Download PDF ] [ Download Excel ] [ Download CSV ]
"""
        return title, text

    # Default fallback (should not happen if templates are correct)
    return report_type, f"Report template '{report_type}' is not implemented."


def _build_report_payload(request, report_type: str, params: dict) -> tuple[list[str], list[list[object]]]:
    user = request.user
    projects = _user_project_queryset(user)
    project_id = (params or {}).get('project') or (params or {}).get('project_id')
    if project_id:
        projects = projects.filter(id=project_id)

    if report_type in {'rbf_portfolio_matrix', 'rmt_portfolio_summary'}:
        columns = ['Project ID', 'Reference', 'Vendor', 'Technology', 'Progress %', 'Gender Impact %', 'Status']
        rows = [
            [
                str(project.id),
                project.project_reference or '',
                project.vendor_name or '',
                project.tech_type or '',
                str(project.progress or 0),
                str(project.gender_impact or 0),
                project.status or '',
            ]
            for project in projects.order_by('-progress')[:200]
        ]
        return columns, rows

    if report_type in {'doe_regional_progress'}:
        columns = ['Project ID', 'Reference', 'District/Region', 'Technology', 'Progress', 'Verified', 'Female %', 'Status']
        rows = [
            [
                str(project.id),
                project.project_reference or '',
                project.district or project.region or '',
                project.tech_type or '',
                f"{project.progress or 0}%",
                f"{project.verified_installations or 0}",
                f"{project.gender_impact or 0}%",
                project.status or '',
            ]
            for project in projects.order_by('-progress')[:200]
        ]
        return columns, rows

    if report_type in {'doe_verification_summary', 'rmt_verification_project'}:
        columns = ['Project ID', 'Reference', 'District/Region', 'Technology', 'Verified', 'Flagged']
        rows = [
            [
                str(project.id),
                project.project_reference or '',
                project.district or project.region or '',
                project.tech_type or '',
                f"{getattr(project, 'verified_installations', 0) or 0}",
                f"{getattr(project, 'flagged_installations', 0) or 0}",
            ]
            for project in projects.order_by('-progress')[:200]
        ]
        return columns, rows

    if report_type in {'rmt_kpi_project'}:
        # One-row KPI snapshot for Excel/CSV exports.
        project = projects.first()
        if not project:
            return ['Message'], [['No project selected or project not found for scope.']]
        try:
            summary = KpiService.for_project(str(project.id)).getFullKpiSummary()
        except Exception:
            summary = {}
        ip = summary.get('installation_progress') or {}
        gender = summary.get('gender_kpi') or {}
        energy = summary.get('energy_kpi') or {}
        uptime = summary.get('uptime_kpi') or {}
        columns = [
            'Project',
            'Vendor',
            'Technology',
            'District',
            'Target Installations',
            'Submitted',
            'Verified',
            'Pending',
            'Flagged',
            'Progress %',
            'Expected %',
            'Female %',
            'Vulnerable %',
            'Low-income %',
            'Current Energy Achievement %',
            'Average Uptime %',
            'Generated At',
        ]
        rows = [[
            project.project_reference or str(project.id),
            project.vendor_name or '',
            project.tech_type or '',
            project.district or project.region or '',
            int(ip.get('target') or project.target_installations or 0),
            int(ip.get('submitted') or 0),
            int(ip.get('verified') or 0),
            int(ip.get('pending') or 0),
            int(ip.get('flagged') or 0),
            float(ip.get('progress_pct') or 0),
            float(ip.get('expected_progress_pct') or 0),
            float((gender.get('female_headed') or {}).get('percentage') or 0),
            float((gender.get('vulnerable') or {}).get('percentage') or 0),
            float((gender.get('low_income') or {}).get('percentage') or 0),
            float(energy.get('current_month_pct') or 0),
            float(uptime.get('average_uptime_pct') or 0),
            summary.get('generated_at') or '',
        ]]
        return columns, rows

    if report_type in {'psc_disbursement_summary', 'psc_financial_summary', 'rmt_financial_disbursement'}:
        claims = PaymentClaim.objects.select_related('project', 'vendor').order_by('-submitted_at')[:300]
        columns = ['Claim ID', 'Project', 'Vendor', 'Status', 'Claim Amount', 'Submitted At', 'Approved At', 'Paid At']
        rows = [
            [
                str(claim.id),
                claim.project.project_reference if claim.project else '',
                claim.vendor.full_name or claim.vendor.username if claim.vendor else '',
                claim.status,
                str(claim.claim_amount or 0),
                claim.submitted_at.isoformat() if getattr(claim, 'submitted_at', None) else '',
                claim.approved_at.isoformat() if getattr(claim, 'approved_at', None) else '',
                claim.paid_at.isoformat() if getattr(claim, 'paid_at', None) else '',
            ]
            for claim in claims[:300]
        ]
        return columns, rows

    if report_type in {'psc_vendor_payment_trail', 'auditor_payment_chain_audit'}:
        claims = PaymentClaim.objects.select_related('project', 'vendor').order_by('-submitted_at')[:300]
        columns = ['Claim ID', 'Vendor', 'Project', 'Status', 'Requested', 'Approved', 'Paid']
        rows = [
            [
                str(claim.id),
                claim.vendor.full_name or claim.vendor.username if claim.vendor else '',
                claim.project.project_reference if claim.project else '',
                claim.status,
                str(claim.claim_amount or 0),
                claim.approved_at.isoformat() if getattr(claim, 'approved_at', None) else '',
                claim.paid_at.isoformat() if getattr(claim, 'paid_at', None) else '',
            ]
            for claim in claims[:300]
        ]
        return columns, rows

    if report_type in {'field_verifier_activity', 'fo_verification_history'}:
        tasks = VerificationTask.objects.filter(field_verifier_task_scope_filter(user, task_prefix='')).select_related('report', 'report__project').order_by('-created_at')[:300]
        columns = ['Task ID', 'Installation', 'Project', 'Outcome', 'GPS Distance (m)', 'Submitted At', 'Updated At']
        rows = [
            [
                str(task.id),
                str(task.report.id) if task.report else '',
                task.report.project.project_reference if task.report and task.report.project else '',
                task.status,
                str(getattr(task, 'distance_meters', '') or ''),
                task.created_at.isoformat() if task.created_at else '',
                task.updated_at.isoformat() if task.updated_at else '',
            ]
            for task in tasks
        ]
        return columns, rows

    if report_type in {'auditor_audit_report', 'auditor_full_audit'}:
        logs = AuditLog.objects.select_related('actor').order_by('-created_at')[:500]
        columns = ['Timestamp', 'Actor', 'Role', 'Action', 'Module', 'Record', 'Notes']
        rows = [
            [
                timezone.localtime(log.created_at).isoformat(),
                (log.actor.full_name or log.actor.username) if log.actor else 'System',
                log.actor_role,
                log.action,
                log.module,
                log.entity_id or log.record_id or '',
                log.notes,
            ]
            for log in logs
        ]
        return columns, rows

    if report_type in {'auditor_prospect_sync', 'auditor_prospect_sync'}:
        syncs = ProspectSyncLog.objects.order_by('-created_at')[:300]
        columns = ['Sync ID', 'Method', 'Status', 'Created At', 'Updated At', 'Attempts', 'Error']
        rows = [
            [
                str(sync.id),
                sync.method_name,
                sync.status,
                sync.created_at.isoformat() if sync.created_at else '',
                sync.updated_at.isoformat() if sync.updated_at else '',
                str(sync.attempts or 0),
                sync.error_message or '',
            ]
            for sync in syncs
        ]
        return columns, rows

    if report_type in {'rmt_anomaly_report'}:
        flags = AnomalyFlag.objects.select_related('project').order_by('-created_at')[:500]
        columns = ['Flag ID', 'Project', 'Type', 'Resolved', 'Created At', 'Resolved At', 'Description']
        rows = [
            [
                str(flag.id),
                flag.project.project_reference if getattr(flag, 'project', None) else '',
                flag.flag_type,
                'Yes' if flag.is_resolved else 'No',
                flag.created_at.isoformat() if flag.created_at else '',
                flag.resolved_at.isoformat() if flag.resolved_at else '',
                flag.description or '',
            ]
            for flag in flags
        ]
        return columns, rows

    if report_type in {'rmt_gender_impact'}:
        projects_qs = _user_project_queryset(user)
        verified_qs = InstallationReport.objects.filter(project__in=projects_qs, status=InstallationStatus.VERIFIED)
        columns = ['Group', 'Key', 'Total Verified', 'Female %', 'Vulnerable %', 'Low-income %']
        rows: list[list[object]] = []

        total = verified_qs.count()
        if total:
            female = verified_qs.filter(household_type__icontains="female").count()
            vuln = verified_qs.filter(household_type__icontains="vulnerable").count()
            low = verified_qs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()
            rows.append(['overall', 'portfolio', total, female / total * 100.0, vuln / total * 100.0, low / total * 100.0])

        for tech in projects_qs.values_list("tech_type", flat=True).distinct():
            if not tech:
                continue
            tqs = verified_qs.filter(project__tech_type=tech)
            ttotal = tqs.count()
            if not ttotal:
                continue
            female = tqs.filter(household_type__icontains="female").count()
            vuln = tqs.filter(household_type__icontains="vulnerable").count()
            low = tqs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()
            rows.append(['technology', tech, ttotal, female / ttotal * 100.0, vuln / ttotal * 100.0, low / ttotal * 100.0])

        for dist in projects_qs.values_list("district", flat=True).distinct():
            if not dist:
                continue
            dqs = verified_qs.filter(project__district=dist)
            dtotal = dqs.count()
            if not dtotal:
                continue
            female = dqs.filter(household_type__icontains="female").count()
            vuln = dqs.filter(household_type__icontains="vulnerable").count()
            low = dqs.filter(Q(household_type__icontains="low") | Q(household_type__icontains="income")).count()
            rows.append(['district', dist, dtotal, female / dtotal * 100.0, vuln / dtotal * 100.0, low / dtotal * 100.0])

        rows.sort(key=lambda r: (str(r[0]), str(r[1])))
        return columns, rows

    # Placeholder payloads for reports whose live view exists elsewhere.
    columns = ['Report', 'Status', 'Note']
    rows = [[report_type, 'AVAILABLE', 'This export is a structured placeholder; KPI dashboards provide the live view.']]
    return columns, rows


class ProjectReportTemplatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == UserRole.ADMIN:
            templates = REPORT_TEMPLATES
        else:
            templates = [tpl for tpl in REPORT_TEMPLATES if user.role in tpl['roles']]
        return Response([
            {
                'id': tpl['id'],
                'title': tpl['title'],
                'description': tpl['description'],
                'category': tpl.get('category') or 'Reports',
                'quick': bool(tpl.get('quick')),
                'formats': _report_formats_for_user(user, tpl['id']),
            }
            for tpl in templates
        ])


class ProjectReportGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        report_type = str(request.data.get('report_type') or '').strip()
        format_type = str(request.data.get('format') or 'csv').strip().lower()
        if format_type not in {'csv', 'pdf', 'excel'}:
            raise PermissionDenied('Unsupported report format.')
        filters = request.data.get('filters') or {}
        columns, rows = _build_report_payload(request, report_type, filters)
        
        filename_base = f'{_safe_filename_base(report_type)}_{timezone.localdate().isoformat()}'
        project = None
        project_id = filters.get('project') or filters.get('project_id')
        if project_id:
            try:
                project = Project.objects.get(id=project_id)
            except Exception:
                project = None

        content_bytes: bytes
        content_type: str
        ext: str

        if format_type == 'csv':
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([str(item or '') for item in row])
            content_bytes = buffer.getvalue().encode('utf-8')
            content_type = 'text/csv'
            ext = 'csv'
        elif format_type == 'excel':
            content_bytes = _xlsx_bytes(columns, rows)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            # Professional PDF rendering
            from .reports import build_report_html
            pdf_title, report_html = build_report_html(request, report_type, filters)
            
            # Use the existing _render_pdf but with our professional HTML
            from rbf.tenders.pba_pdf import _render_pdf
            tmp_dir = Path(tempfile.mkdtemp(prefix="report_pdf_"))
            output_path = tmp_dir / f"report_{uuid.uuid4().hex}.pdf"
            
            # _render_pdf expects (html_string, output_path, contract_reference)
            # We'll use the title or RID as contract_reference for the header
            _render_pdf(report_html, output_path, pdf_title[:32])
            
            content_bytes = output_path.read_bytes()
            content_type = 'application/pdf'
            ext = 'pdf'

        generated = GeneratedReport.objects.create(
            report_type=report_type,
            format=format_type,
            filters=filters,
            scope_label=str(filters.get('scope_label') or ''),
            project=project,
            generated_by=request.user,
            file=ContentFile(content_bytes, name=f'{filename_base}.{ext}'),
        )
        AuditLog.objects.create(
            actor=request.user if getattr(request.user, 'is_authenticated', False) else None,
            actor_role=str(getattr(request.user, 'role', '') or ''),
            action='report_generated',
            module='report',
            entity_type='Report',
            entity_id=str(generated.id),
            record_id=None,
            record_type='Report',
            old_status='',
            new_status='',
            notes=f'{report_type} generated as {format_type}',
            ip_address=AuditLogger._ip_address(request),
            details={'report_type': report_type, 'format': format_type, 'generated_report_id': str(generated.id)},
        )
        response = HttpResponse(content_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename_base}.{ext}"'
        response['X-Generated-Report-Id'] = str(generated.id)
        return response


class ProjectReportHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = GeneratedReport.objects.select_related('generated_by', 'project').order_by('-generated_at')
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.UNDP_DONOR, UserRole.DOE_OFFICER}:
            queryset = queryset.filter(generated_by=request.user)
        items = []
        for report in queryset[:20]:
            items.append({
                'id': str(report.id),
                'reportType': report.report_type,
                'project': report.project.project_reference if report.project else '',
                'generatedBy': (report.generated_by.full_name or report.generated_by.username) if report.generated_by else '',
                'generatedAt': timezone.localtime(report.generated_at).isoformat(),
                'format': report.format,
                'downloadUrl': f'/api/projects/reports/{report.id}/download/',
            })
        return Response(items)


class ProjectReportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = GeneratedReport.objects.select_related('generated_by').get(id=report_id)
        privileged = request.user.role in {
            UserRole.ADMIN,
            UserRole.RBF_OFFICIAL,
            UserRole.AUDITOR,
            UserRole.UNDP_DONOR,
            UserRole.DOE_OFFICER,
            UserRole.TAC,
        }
        if not privileged and report.generated_by_id != request.user.id:
            raise PermissionDenied('You do not have permission to download this report.')
        return FileResponse(report.file.open('rb'), as_attachment=True, filename=Path(report.file.name).name)


class ConcernViewSet(viewsets.ModelViewSet):
    queryset = Concern.objects.select_related('raised_by', 'linked_project').all()
    serializer_class = ConcernSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'severity', 'concern_type']
    search_fields = ['description', 'id']
    ordering_fields = ['created_at', 'severity']

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.DOE_OFFICER:
            return self.queryset.filter(raised_by=user)
        if user.role == UserRole.AUDITOR:
            return self.queryset.none()
        if user.role == UserRole.RBF_OFFICIAL:
            return self.queryset.all()
        if user.role == "Project Steering Committee" or user.role == "UNDP_DONOR":
            return self.queryset.filter(notify_psc=True)
        return self.queryset.none()

    def perform_create(self, serializer):
        concern = serializer.save(raised_by=self.request.user)
        if concern.notify_rmt:
            Notification.objects.create(
                recipient_id="rmt",
                recipient_name="RMT Team",
                type=NotificationChannel.IN_APP,
                event="doe_concern",
                title=f"[{concern.severity.upper()}] New concern raised by DoE",
                body=f"{concern.linked_project.project_reference if concern.linked_project else 'General'} — {concern.get_concern_type_display()}",
                status=NotificationStatus.SENT,
            )
        if concern.notify_psc:
            Notification.objects.create(
                recipient_id="psc",
                recipient_name="PSC Team",
                type=NotificationChannel.IN_APP,
                event="doe_concern",
                title=f"DoE has flagged a concern",
                body=f"Review recommended: {concern.description[:100]}",
                status=NotificationStatus.SENT,
            )


class ConcernResponseViewSet(viewsets.ModelViewSet):
    queryset = ConcernResponse.objects.select_related('responded_by', 'concern').all()
    serializer_class = ConcernResponseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            return self.queryset.all()
        if user.role == "Project Steering Committee" or user.role == "UNDP_DONOR":
            return self.queryset.all()
        return self.queryset.none()

    def perform_create(self, serializer):
        response = serializer.save(responded_by=self.request.user)
        
        user = self.request.user
        if user.role == "Project Steering Committee" or user.role == "UNDP_DONOR":
            Notification.objects.create(
                recipient_id="rmt",
                recipient_name="RMT Team",
                type=NotificationChannel.IN_APP,
                event="psc_comment",
                title=f"PSC Comment on {response.concern.id}",
                body=f"PSC has added a comment to concern {response.concern.id}: {response.response_text[:100]}",
                status=NotificationStatus.SENT,
                linked_entity_id=response.concern.id,
            )


class AuditFindingViewSet(viewsets.ModelViewSet):
    queryset = AuditFinding.objects.select_related('raised_by', 'linked_project').all()
    serializer_class = AuditFindingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'risk_level', 'finding_category']
    search_fields = ['description', 'id']
    ordering_fields = ['created_at', 'risk_level']

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.AUDITOR:
            return self.queryset.filter(raised_by=user)
        if user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            return self.queryset.all()
        if user.role == "Project Steering Committee" or user.role == "UNDP_DONOR":
            return self.queryset.all()
        return self.queryset.none()

    def perform_create(self, serializer):
        finding = serializer.save(raised_by=self.request.user)
        
        log_audit(
            actor=self.request.user,
            action="audit_finding_raised",
            entity=finding,
            details={
                "finding_category": finding.finding_category,
                "risk_level": finding.risk_level,
                "linked_project": finding.linked_project.id if finding.linked_project else None,
                "linked_claim": finding.linked_claim.id if finding.linked_claim else None,
                "description": finding.description[:200],
            },
        )
        
        if finding.rised_to_rmt:
            Notification.objects.create(
                recipient_id="rmt",
                recipient_name="RMT Team",
                type=NotificationChannel.IN_APP,
                event="audit_finding",
                title=f"[{finding.risk_level.upper()} AUDIT FINDING] raised by Auditor",
                body=f"{finding.linked_project.project_reference if finding.linked_project else 'General'} — {finding.get_finding_category_display()}",
                status=NotificationStatus.SENT,
                linked_entity_id=finding.id,
            )
        if finding.rised_to_psc:
            Notification.objects.create(
                recipient_id="psc",
                recipient_name="PSC Team",
                type=NotificationChannel.IN_APP,
                event="audit_finding",
                title=f"Audit finding requires your attention",
                body=f"A {finding.risk_level} finding has been raised on {finding.linked_project.project_reference if finding.linked_project else 'project'}.",
                status=NotificationStatus.SENT,
                linked_entity_id=finding.id,
            )
        if finding.risk_level == 'critical':
            Notification.objects.create(
                recipient_id="super_admin",
                recipient_name="Super Admin",
                type=NotificationChannel.IN_APP,
                event="critical_audit_finding",
                title="CRITICAL AUDIT FINDING — Immediate action required",
                body=finding.description[:200],
                status=NotificationStatus.SENT,
                linked_entity_id=finding.id,
            )

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        finding = self.get_object()
        response_text = request.data.get('response', '')
        action_taken = request.data.get('action_taken', '')

        if not response_text:
            return Response({'error': 'Response text is required'}, status=400)

        user_role = str(request.user.role)
        is_psc = user_role == "Project Steering Committee" or user_role == "UNDP_DONOR"

        if is_psc and action_taken == 'psc_directive':
            finding.psc_comment = response_text
            finding.psc_commented_at = timezone.now()
            finding.psc_commented_by = request.user
            finding.save()

            Notification.objects.create(
                recipient_id="rmt",
                recipient_name="RMT Team",
                type=NotificationChannel.IN_APP,
                event="psc_comment",
                title=f"PSC Comment on {finding.id}",
                body=f"PSC has commented on audit finding {finding.id}: {response_text[:100]}",
                status=NotificationStatus.SENT,
                linked_entity_id=finding.id,
            )
        else:
            resolution_statuses = [
                'evidence_reviewed_no_issue',
                'issue_confirmed_corrective',
                'issue_confirmed_suspend',
                'issue_confirmed_blacklist',
                'referred_legal'
            ]

            if action_taken in resolution_statuses:
                finding.status = 'resolved'
            elif action_taken == 'escalated_to_psc':
                finding.status = 'escalated_to_psc'
            elif action_taken == 'under_investigation':
                finding.status = 'under_investigation'
            else:
                finding.status = 'open'

            finding.rmt_response = response_text
            finding.rmt_response_action = action_taken
            finding.rmt_responded_by = request.user
            finding.rmt_responded_at = timezone.now()
            finding.save()

        return Response(AuditFindingSerializer(finding).data)
