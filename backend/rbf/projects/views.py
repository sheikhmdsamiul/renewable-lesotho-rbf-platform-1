from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from django.http import FileResponse, Http404
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q, F, Value, OuterRef, Subquery, Count, CharField, Case, When
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
    ProspectSyncLog,
    AnomalyFlag,
    GisStatus,
)
from .serializers import (
    ProjectSerializer,
    ProjectSetupSerializer,
    MilestoneSerializer,
    ProjectUpdateSerializer,
    ProjectDocumentSerializer,
    InstallationReportSerializer,
    VerificationTaskSerializer,
    SmartMeterReadingSerializer,
    PaymentClaimSerializer,
    DisbursementSerializer,
    AuditLogSerializer,
    ProspectSyncLogSerializer,
    AnomalyFlagSerializer,
)
from rbf.users.models import UserRole
from rbf.users.models import User
from rbf.users.blacklisting import is_vendor_restricted
from .audit import log_audit
from .integrations import queue_installation_sync, queue_project_agent_sync, queue_project_targets_sync, SyncToProspectJob
from .gis import GpsValidator
from .kpi import KpiService, invalidate_kpi_cache, render_kpi_pdf
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.tenders.models import ContractStatus, TenderContract


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
    KpiService.for_project(project_id).getMilestoneEligibility()


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
        queryset = queryset.filter(project__district__iexact=user.verification_zone)

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

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.DOE_OFFICER, UserRole.VENDOR}

    def get_queryset(self):
        qs = Project.objects.select_related('tender', 'project_setup').prefetch_related('milestones').all().order_by('id')
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

        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        rows_created = []
        timeseries_payload = []
        upload_time = timezone.now()

        for row in reader:
            meter_id = str(row.get('meter_id') or '').strip()
            if not meter_id:
                continue
            installation_id = str(row.get('installation_id') or '').strip()
            installation = InstallationReport.objects.filter(
                id=installation_id,
                project=project,
            ).first() if installation_id else InstallationReport.objects.filter(project=project, meter_id=meter_id).first()
            try:
                kwh_value = float(row.get('kwh_generated') or row.get('kwh') or 0)
            except (TypeError, ValueError):
                kwh_value = 0.0
            try:
                uptime_pct = float(row.get('uptime_pct') or 0)
            except (TypeError, ValueError):
                uptime_pct = 0.0
            recorded_at_raw = str(row.get('recorded_at') or '').strip()
            try:
                recorded_at = timezone.datetime.fromisoformat(recorded_at_raw.replace('Z', '+00:00')) if recorded_at_raw else upload_time
            except ValueError:
                recorded_at = upload_time
            if timezone.is_naive(recorded_at):
                recorded_at = timezone.make_aware(recorded_at, timezone.get_current_timezone())

            reading = SmartMeterReading.objects.create(
                project=project,
                installation=installation,
                meter_id=meter_id,
                kwh=kwh_value,
                uptime_pct=uptime_pct,
                recorded_at=recorded_at,
            )
            rows_created.append(reading)
            timeseries_payload.append({
                'external_id': f'meter_{project.id}_{reading.id}',
                'installation_id': str(installation.id) if installation else '',
                'meter_id': meter_id,
                'recorded_at': recorded_at.isoformat(),
                'kwh_generated': kwh_value,
                'output_energy_interval_wh': round(kwh_value * 1000, 2),
                'uptime_pct': uptime_pct,
                'project_id': str(project.id),
                'reporting_phase': f'PRJ-{project.id}',
                'country': 'LS',
            })

        if not rows_created:
            return Response({'detail': 'No valid meter rows were found in the uploaded CSV.'}, status=status.HTTP_400_BAD_REQUEST)

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
            {'project_id': str(project.id), 'rows_ingested': len(rows_created)},
        )
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
    APPROVE_ROLES = {UserRole.TAC}
    PAY_ROLES = {UserRole.UNDP_DONOR}

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
        claim.status = PaymentClaimStatus.PENDING
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
        tac_users = User.objects.filter(role=UserRole.TAC).only('id', 'full_name', 'username')
        if tac_users:
            Notification.objects.bulk_create(
                [
                    Notification(
                        recipient_id=str(user.id),
                        recipient_name=user.full_name or user.username,
                        type=NotificationChannel.IN_APP,
                        event='payment_claim_verified',
                        title='Claim Ready For TAC Review',
                        body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} was verified by RMT and awaits TAC approval.',
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
            title='Milestone Claim Verified By RMT',
            body=f'Claim {claim.id} passed RMT review and is now waiting for TAC approval.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        return Response(self.get_serializer(claim).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.role not in self.APPROVE_ROLES:
            raise PermissionDenied('You do not have permission to approve claims.')
        claim = self.get_object()
        if is_vendor_restricted(claim.vendor):
            return Response({'detail': 'This vendor is suspended or blacklisted. Claim remains on Held/Audit.'}, status=status.HTTP_400_BAD_REQUEST)
        if claim.status != PaymentClaimStatus.VERIFIED:
            return Response({'detail': 'Claim must first be verified by RMT before TAC approval.'}, status=status.HTTP_400_BAD_REQUEST)
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
            f"Payment claim {claim.id} was approved by TAC.",
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
                        body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} was approved by TAC and awaits PSC payment approval.',
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
            title='Milestone Claim Approved By TAC',
            body=f'Claim {claim.id} passed TAC review and is now waiting for PSC payment approval.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
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
        Notification.objects.create(
            recipient_id=str(claim.vendor_id),
            recipient_name=claim.vendor.full_name or claim.vendor.username,
            type=NotificationChannel.IN_APP,
            event='payment_claim_paid',
            title='Milestone Claim Paid',
            body=f'Claim {claim.id} for project {claim.project.project_reference or claim.project.id} has been paid.',
            status=NotificationStatus.SENT,
            linked_entity_id=str(claim.project_id),
        )
        if claim.milestone:
            claim.milestone.status = 'paid'
            claim.milestone.save(update_fields=['status', 'updated_at'])
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

        distance = haversine(float(task.vendor_lat), float(task.vendor_lng), verifier_lat, verifier_lng)
        requested_status = str(request.data.get('verification_status') or '').strip().lower()
        if requested_status == 'partial':
            next_status = VerificationStatus.PARTIAL
        elif requested_status == 'flagged':
            next_status = VerificationStatus.FLAGGED
        elif requested_status == 'verified':
            next_status = VerificationStatus.VERIFIED
        else:
            next_status = VerificationStatus.FLAGGED if distance > 100 else VerificationStatus.VERIFIED
        anomaly = next_status == VerificationStatus.FLAGGED

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
            report.anomaly_flags.filter(flag_type='verification_distance', is_resolved=False).update(
                is_resolved=True,
                resolved_at=timezone.now(),
            )
        elif next_status == VerificationStatus.FLAGGED:
            report.status = InstallationStatus.FLAGGED
            report.gis_status = GisStatus.RED
            AnomalyFlag.objects.create(
                installation=report,
                project=report.project,
                flag_type='verification_distance',
                description=f'Field verification detected a {distance:.2f}m GPS mismatch.',
            )
        else:
            report.status = InstallationStatus.SUBMITTED
            report.gis_status = GisStatus.YELLOW
        report.save(update_fields=['status', 'gis_status'])
        queue_installation_sync(str(report.id), include_customer=False, include_installation=True)
        log_audit(request.user, 'installation_verified', report, {'distance_meters': distance, 'anomaly': anomaly})
        create_project_activity_update(
            report.project,
            request.user,
            'Installation Verification Completed',
            f"Installation report {report.id} was {str(next_status).lower()} after field verification.",
        )
        refresh_project_kpis(str(report.project_id))
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)


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
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.UNDP_DONOR}:
            return self.queryset
        if user.role == UserRole.VENDOR:
            project_ids = [int(pid) for pid in Project.objects.filter(vendor_query_filter(user)).values_list('id', flat=True)]
            claim_ids = [str(cid) for cid in PaymentClaim.objects.filter(vendor=user).values_list('id', flat=True)]
            return self.queryset.filter(
                Q(record_type='project', record_id__in=project_ids) |
                Q(details__project_id__in=[str(pid) for pid in project_ids]) |
                Q(entity_type='Project', entity_id__in=[str(pid) for pid in project_ids]) |
                Q(entity_type='PaymentClaim', entity_id__in=claim_ids) |
                Q(actor=user)
            )
        return self.queryset.filter(actor=user)


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
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.UNDP_DONOR}:
            return self.queryset.order_by('-created_at')
        return self.queryset.none()

    @action(detail=False, methods=['post'], url_path='refresh-panel')
    def refresh_panel(self, request):
        if request.user.role not in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.UNDP_DONOR}:
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
            return qs.filter(installation__verification_task__assigned_verifier=user)
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
        if user.region and (project.region or '').lower() == user.region.lower():
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
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR}:
            raise PermissionDenied('You do not have permission to access the portfolio KPI dashboard.')
        return Response(KpiService.getPortfolioSummary())
