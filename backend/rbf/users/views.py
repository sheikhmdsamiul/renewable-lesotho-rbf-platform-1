import json
import random
import string
import time
from datetime import timedelta, datetime
from pathlib import Path
import shutil

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.management import call_command
from django.contrib.sessions.models import Session
from django.db import connections
from django.db.utils import OperationalError
from django.utils._os import safe_join
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.views import TokenObtainPairView
from .blacklisting import (
    apply_blacklist_confirmation,
    apply_blacklist_initiation,
    get_active_blacklist_case,
    release_blacklist_case,
)
from .models import (
    BlacklistAppeal,
    BlacklistAppealStatus,
    BlacklistCaseStatus,
    Organization,
    PlatformConfiguration,
    User,
    UserRole,
    UserStatus,
    VendorBlacklistCase,
    VendorPrequalification,
    PrequalificationStatus,
)

# Simple in-process OTP fallback store for dev/local environments.
# Key: cache key, Value: (otp, expires_at_epoch)
_OTP_FALLBACK = {}
from .serializers import (
    AdminManagedUserDetailSerializer,
    AdminManagedUserSerializer,
    OrganizationSerializer,
    PlatformConfigurationSerializer,
    BlacklistAppealSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
    VendorBlacklistCaseSerializer,
    VendorPrequalificationSerializer,
)
from rbf.projects.audit import log_audit, AuditLogger
from rbf.projects.integrations import SyncToProspectJob, normalize_prospect_gender
from rbf.projects.models import AuditLog, Project, ProjectStatus, ProspectSyncLog, ProspectSyncStatus
from rbf.notifications.models import Notification


DEFAULT_ORGANIZATIONS = [
    {
        'name': 'Ministry of Energy',
        'type': 'Government',
        'contact_person': 'Permanent Secretary',
        'email': 'energy@gov.ls',
        'phone': '+266 2231 0000',
        'address': 'Maseru, Lesotho',
    },
    {
        'name': 'UNDP',
        'type': 'International',
        'contact_person': 'Programme Specialist',
        'email': 'registry.ls@undp.org',
        'phone': '+266 2231 6800',
        'address': 'United Nations House, Maseru',
    },
    {
        'name': 'Department of Energy',
        'type': 'Government',
        'contact_person': 'Director of Energy',
        'email': 'doe@gov.ls',
        'phone': '+266 2231 0200',
        'address': 'Maseru, Lesotho',
    },
    {
        'name': 'EU Delegation',
        'type': 'International',
        'contact_person': 'Cooperation Section',
        'email': 'delegation-lesotho@eeas.europa.eu',
        'phone': '+266 2231 4200',
        'address': 'Maseru, Lesotho',
    },
    {
        'name': 'PSC Members Secretariat',
        'type': 'Government',
        'contact_person': 'PSC Coordinator',
        'email': 'psc@gov.ls',
        'phone': '+266 2232 1100',
        'address': 'Maseru, Lesotho',
    },
]


def ensure_default_organizations():
    if Organization.objects.exists():
        return
    Organization.objects.bulk_create([Organization(**payload) for payload in DEFAULT_ORGANIZATIONS], ignore_conflicts=True)


def build_system_health_payload():
    db_ok = True
    db_error = None
    try:
        connections['default'].cursor()
    except OperationalError as exc:
        db_ok = False
        db_error = str(exc)

    media_path = Path(getattr(settings, 'MEDIA_ROOT', settings.BASE_DIR))
    usage = shutil.disk_usage(media_path)
    pending_jobs = ProspectSyncLog.objects.filter(status=ProspectSyncStatus.PENDING).count()
    failed_jobs = ProspectSyncLog.objects.filter(status=ProspectSyncStatus.FAILED).count()
    processing_rate = ProspectSyncLog.objects.filter(
        status=ProspectSyncStatus.SUCCESS,
        created_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    files_uploaded_today = (
        Project.objects.filter(created_at__date=timezone.localdate()).count()
        + AuditLog.objects.filter(created_at__date=timezone.localdate(), action__icontains='uploaded').count()
    )
    recent_errors = list(
        ProspectSyncLog.objects.filter(status=ProspectSyncStatus.FAILED)
        .order_by('-updated_at')
        .values('id', 'method_name', 'error_message', 'updated_at')[:20]
    )
    recent_activity = ProspectSyncLog.objects.order_by('-updated_at').first()
    return {
        'database': {
            'status': 'Connected' if db_ok else 'Disconnected',
            'error': db_error,
            'slow_queries_last_24h': 0,
            'table_sizes': {
                'users': User.objects.count(),
                'projects': Project.objects.count(),
                'audit_logs': AuditLog.objects.count(),
            },
        },
        'queue': {
            'worker_status': 'Running',
            'pending_jobs_count': pending_jobs,
            'failed_jobs_count': failed_jobs,
            'processing_rate_last_24h': processing_rate,
        },
        'scheduler': {
            'status': 'Running',
            'last_monthly_report_sync': recent_activity.updated_at.isoformat() if recent_activity else None,
        },
        'prospect_api': {
            'status': 'Connected' if getattr(settings, 'PROSPECT_BASE_URL', '') else 'Not Configured',
        },
        'storage': {
            'total_bytes': usage.total,
            'used_bytes': usage.used,
            'free_bytes': usage.free,
            'files_uploaded_today': files_uploaded_today,
        },
        'errors': recent_errors,
    }


class IsAdminOrRbfOfficial:
    @staticmethod
    def check(user):
        return bool(
            user
            and user.is_authenticated
            and user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}
        )


class IsReviewerRole:
    @staticmethod
    def check(user):
        return bool(
            user
            and user.is_authenticated
            and user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR}
        )


class IsBlacklistInitiatorRole:
    @staticmethod
    def check(user):
        return bool(
            user
            and user.is_authenticated
            and user.role in {UserRole.RBF_OFFICIAL, UserRole.AUDITOR}
        )


class IsBlacklistReviewerRole:
    @staticmethod
    def check(user):
        return bool(
            user
            and user.is_authenticated
            and user.role in {UserRole.TAC, UserRole.DOE_OFFICER, UserRole.AUDITOR}
        )


class IsBlacklistConfirmerRole:
    @staticmethod
    def check(user):
        return bool(
            user
            and user.is_authenticated
            and user.role in {UserRole.ADMIN, UserRole.DOE_OFFICER}
        )


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer

    ADMIN_MANAGED_ROLES = {
        UserRole.RBF_OFFICIAL,
        UserRole.TAC,
        UserRole.DOE_OFFICER,
        UserRole.FIELD_VERIFIER,
        UserRole.UNDP_DONOR,
        UserRole.AUDITOR,
    }

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['cache'] = cache
        return context

    def get_serializer_class(self):
        user = getattr(self.request, 'user', None)
        if self.action == 'retrieve' and IsAdminOrRbfOfficial.check(user) and getattr(user, 'role', None) == UserRole.ADMIN:
            return AdminManagedUserDetailSerializer
        if self.action in {'create', 'update', 'partial_update'} and IsAdminOrRbfOfficial.check(user) and getattr(user, 'role', None) == UserRole.ADMIN:
            return AdminManagedUserSerializer
        return UserSerializer

    def _assert_super_admin(self, user):
        if not (user and user.is_authenticated and user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can manage admin-created users.')

    def _invalidate_user_sessions(self, user: User):
        for session in Session.objects.all().iterator():
            data = session.get_decoded()
            if str(data.get('_auth_user_id') or '') == str(user.id):
                session.delete()

    def create(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self._assert_super_admin(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        user = serializer.instance
        headers = self.get_success_headers(serializer.data)

        data = dict(serializer.data)
        generated_password = getattr(serializer, 'generated_password', None)
        email_configured = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD) or settings.DEBUG
        email_error = None
        if generated_password and user.email:
            subject = 'Your account has been created'
            message = (
                'Your account has been created.\n'
                f'Username: {user.username}\n'
                f'Temporary password: {generated_password}\n'
                'Please log in and change your password.'
            )
            if email_configured:
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                except Exception as exc:
                    email_error = str(exc)
            else:
                email_error = 'Email service is not configured.'

        if settings.DEBUG and generated_password:
            data['initial_password'] = generated_password
            if email_error:
                data['email_error'] = email_error

        location_area_1 = user.verification_zone or user.region or ''
        SyncToProspectJob.dispatch_async(
            'pushAgent',
            [{
                'external_id': str(user.id),
                'agent_type': 'installer' if user.role == UserRole.FIELD_VERIFIER else 'sales_agent',
                'gender': normalize_prospect_gender(user.gender),
                'country': 'LS',
                'location_area_1': location_area_1,
            }],
            record_id=int(user.id),
            record_type='user',
        )
        AuditLogger.log('user_created', 'users', user.id, 'user', new_status=user.status, notes=f'Created {user.role} user.')

        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        user = serializer.save()
        if user.role != UserRole.VENDOR and not user.must_change_password:
            user.must_change_password = True
            user.save(update_fields=['must_change_password'])

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        elevated_actions = {
            'approve',
            'initiate_blacklisting',
            'review_blacklisting',
            'confirm_blacklisting',
            'reinstate_vendor',
            'appeal_review',
        }
        if self.action in elevated_actions and IsAdminOrRbfOfficial.check(user):
            return User.objects.all().order_by('-id')
        if user and user.is_authenticated and user.role == UserRole.ADMIN:
            queryset = User.objects.exclude(role=UserRole.VENDOR).order_by('-id')
            role = str(self.request.query_params.get('role') or '').strip()
            district = str(self.request.query_params.get('district') or '').strip()
            status_value = str(self.request.query_params.get('status') or '').strip()
            if role:
                queryset = queryset.filter(role=role)
            if district:
                queryset = queryset.filter(Q(region__iexact=district) | Q(verification_zone__iexact=district))
            if status_value:
                normalized = status_value.lower()
                if normalized in {'active', 'inactive'}:
                    queryset = queryset.filter(is_active=(normalized == 'active'))
            return queryset
        return User.objects.filter(id=getattr(user, 'id', None)).order_by('-id')

    def update(self, request, *args, **kwargs):
        target_user = self.get_object()
        if request.user.role == UserRole.ADMIN and target_user.role != UserRole.VENDOR:
            partial = False
            serializer = self.get_serializer(target_user, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            updated_user = serializer.instance
            if getattr(serializer, 'was_deactivated', False):
                self._invalidate_user_sessions(updated_user)
                AuditLogger.log('user_deactivated', 'users', updated_user.id, 'user', old_status='Active', new_status='Inactive', notes='User deactivated by Super Admin.')
            else:
                AuditLogger.log('user_updated', 'users', updated_user.id, 'user', new_status=updated_user.status, notes='User profile updated by Super Admin.')
            return Response(self.get_serializer(updated_user).data)
        if target_user.id != request.user.id and not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('You do not have permission to update this user.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        target_user = self.get_object()
        if request.user.role == UserRole.ADMIN and target_user.role != UserRole.VENDOR:
            serializer = self.get_serializer(target_user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            updated_user = serializer.instance
            if getattr(serializer, 'was_deactivated', False):
                self._invalidate_user_sessions(updated_user)
                AuditLogger.log('user_deactivated', 'users', updated_user.id, 'user', old_status='Active', new_status='Inactive', notes='User deactivated by Super Admin.')
            else:
                AuditLogger.log('user_updated', 'users', updated_user.id, 'user', new_status=updated_user.status, notes='User profile updated by Super Admin.')
            return Response(self.get_serializer(updated_user).data)
        if target_user.id != request.user.id and not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('You do not have permission to update this user.')
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='deactivate')
    def deactivate(self, request, pk=None):
        self._assert_super_admin(request.user)
        user = self.get_object()
        if user.role in {UserRole.VENDOR, UserRole.ADMIN}:
            return Response({'detail': 'This action is only for admin-created non-vendor users.'}, status=status.HTTP_400_BAD_REQUEST)
        user.status = UserStatus.INACTIVE
        user.is_active = False
        user.save(update_fields=['status', 'is_active'])
        self._invalidate_user_sessions(user)
        AuditLogger.log('user_deactivated', 'users', user.id, 'user', old_status='Active', new_status='Inactive', notes='User deactivated by Super Admin.')
        return Response(AdminManagedUserDetailSerializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='reset-password')
    def reset_password(self, request, pk=None):
        self._assert_super_admin(request.user)
        user = self.get_object()
        if user.role in {UserRole.VENDOR, UserRole.ADMIN}:
            return Response({'detail': 'Password reset is only available for admin-managed non-vendor users.'}, status=status.HTTP_400_BAD_REQUEST)

        temporary_password = generate_temporary_password(12)
        user.set_password(temporary_password)
        user.must_change_password = True
        user.save(update_fields=['password', 'must_change_password'])
        self._invalidate_user_sessions(user)
        AuditLogger.log('user_password_reset', 'users', user.id, 'user', notes='Temporary password reset by Super Admin.')

        email_error = None
        email_configured = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD) or settings.DEBUG
        if user.email and email_configured:
            try:
                send_mail(
                    subject='Your password has been reset',
                    message=(
                        'Your password has been reset by the platform administrator.\n'
                        f'Username: {user.username}\n'
                        f'Temporary password: {temporary_password}\n'
                        'Please sign in and change your password immediately.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as exc:  # noqa: BLE001
                email_error = str(exc)
        elif user.email:
            email_error = 'Email service is not configured.'

        payload = {
            'status': 'ok',
            'temporary_password': temporary_password if settings.DEBUG else None,
            'email_error': email_error,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='management/meta')
    def management_meta(self, request):
        self._assert_super_admin(request.user)
        return Response({
            'roles': [
                {'label': 'RMT', 'value': UserRole.RBF_OFFICIAL},
                {'label': 'TAC', 'value': UserRole.TAC},
                {'label': 'DoE', 'value': UserRole.DOE_OFFICER},
                {'label': 'Field Officer', 'value': UserRole.FIELD_VERIFIER},
                {'label': 'PSC', 'value': UserRole.UNDP_DONOR},
                {'label': 'UNDP', 'value': UserRole.UNDP_DONOR},
                {'label': 'Auditor', 'value': UserRole.AUDITOR},
            ],
        })

    @action(detail=True, methods=['patch', 'post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('Only RBF Management Team or Platform Administrator (Super Admin) can approve vendors.')

        user = self.get_object()
        if user.role != UserRole.VENDOR:
            return Response({'detail': 'Only vendor accounts can be approved.'}, status=status.HTTP_400_BAD_REQUEST)

        user.status = 'Active'
        user.is_active = True
        user.save(update_fields=['status', 'is_active'])
        log_audit(request.user, 'vendor_account_approved', user, {'username': user.username})
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.role == UserRole.ADMIN):
            return Organization.objects.none()
        ensure_default_organizations()
        return self.queryset.order_by('name')

    def _assert_super_admin(self):
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can manage organizations.')

    def create(self, request, *args, **kwargs):
        self._assert_super_admin()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_super_admin()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_super_admin()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_super_admin()
        return super().destroy(request, *args, **kwargs)


class PlatformConfigurationView(APIView):
    permission_classes = [IsAuthenticated]

    def _assert_super_admin(self, user):
        if not (user and user.is_authenticated and user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can manage system configuration.')

    def _get_config(self):
        config = PlatformConfiguration.objects.order_by('id').first()
        if config is None:
            config = PlatformConfiguration.objects.create(
                allowed_file_types=['PDF', 'DOCX', 'JPG', 'PNG', 'XLSX'],
            )
        return config

    def get(self, request):
        self._assert_super_admin(request.user)
        serializer = PlatformConfigurationSerializer(self._get_config())
        boundary_path = Path(settings.BASE_DIR) / 'public' / 'geojson' / 'lesotho.geojson'
        payload = dict(serializer.data)
        payload['lesotho_boundary'] = {
            'path': str(boundary_path),
            'exists': boundary_path.exists(),
            'last_modified': datetime.utcfromtimestamp(boundary_path.stat().st_mtime).isoformat() + "+00:00" if boundary_path.exists() else None,
        }
        return Response(payload, status=status.HTTP_200_OK)

    def patch(self, request):
        self._assert_super_admin(request.user)
        serializer = PlatformConfigurationSerializer(self._get_config(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        AuditLogger.log('platform_configuration_updated', 'configuration', serializer.instance.id, 'platform_configuration', notes='Platform configuration updated by Super Admin.')
        return Response(serializer.data, status=status.HTTP_200_OK)


class PlatformConfigurationBoundaryRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not (request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can refresh the Lesotho boundary file.')
        call_command('download_lesotho_geojson')
        AuditLogger.log('lesotho_boundary_refreshed', 'configuration', None, 'boundary', notes='Boundary file re-downloaded by Super Admin.')
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)


class PlatformConfigurationBoundaryUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not (request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can upload the Lesotho boundary file.')
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if not file.name.lower().endswith('.geojson'):
            return Response({'error': 'File must be a GeoJSON file.'}, status=status.HTTP_400_BAD_REQUEST)
        boundary_path = Path(settings.BASE_DIR) / 'public' / 'geojson' / 'lesotho.geojson'
        boundary_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(file.read().decode('utf-8'))
        except Exception:
            return Response({'error': 'Invalid JSON file.'}, status=status.HTTP_400_BAD_REQUEST)
        geometry = payload.get('geometry') or {}
        if geometry.get('type') not in {'Polygon', 'MultiPolygon'} or not geometry.get('coordinates'):
            return Response({'error': 'Invalid GeoJSON: must contain a Polygon or MultiPolygon.'}, status=status.HTTP_400_BAD_REQUEST)
        with boundary_path.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        AuditLogger.log('lesotho_boundary_uploaded', 'configuration', None, 'boundary', notes='Boundary file uploaded by Super Admin.')
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)


class SystemHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can view system health.')
        return Response(build_system_health_payload(), status=status.HTTP_200_OK)


class SuperAdminDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (request.user and request.user.is_authenticated and request.user.role == UserRole.ADMIN):
            raise PermissionDenied('Only Platform Administrator (Super Admin) can view the dashboard summary.')

        ensure_default_organizations()
        health_payload = build_system_health_payload()
        recent_activity = AuditLog.objects.select_related('actor').order_by('-created_at')[:20]
        latest_sync = ProspectSyncLog.objects.order_by('-updated_at').first()

        payload = {
            'stats': {
                'total_users': User.objects.exclude(role=UserRole.VENDOR).count(),
                'active_projects': Project.objects.filter(status__in={
                    ProjectStatus.ACTIVE,
                    ProjectStatus.INSTALLATION,
                    ProjectStatus.VERIFICATION,
                    ProjectStatus.DISBURSEMENT,
                    ProjectStatus.CONTRACTING,
                }).count(),
                'total_vendors': User.objects.filter(role=UserRole.VENDOR).count(),
                'pending_prequalifications': VendorPrequalification.objects.filter(
                    status__in={PrequalificationStatus.PENDING, PrequalificationStatus.UNDER_REVIEW}
                ).count(),
            },
            'system_health': health_payload,
            'recent_activity': [
                {
                    'id': log.id,
                    'timestamp': log.created_at,
                    'actor': log.actor.full_name or log.actor.username if log.actor else 'System',
                    'role': log.actor_role,
                    'action': log.action,
                    'module': log.module,
                    'record': log.entity_id or log.record_id or '',
                    'notes': log.notes,
                    'old_status': log.old_status,
                    'new_status': log.new_status,
                }
                for log in recent_activity
            ],
            'prospect_sync_summary': {
                'failed_jobs': ProspectSyncLog.objects.filter(status=ProspectSyncStatus.FAILED).count(),
                'last_sync_at': latest_sync.updated_at if latest_sync else None,
            },
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], parser_classes=[MultiPartParser, FormParser])
    def initiate_blacklisting(self, request, pk=None):
        if not IsBlacklistInitiatorRole.check(request.user):
            raise PermissionDenied('Only RBF Management Team or Auditors can initiate blacklisting.')
        vendor = self.get_object()
        if vendor.role != UserRole.VENDOR:
            return Response({'detail': 'Only vendor accounts can be blacklisted.'}, status=status.HTTP_400_BAD_REQUEST)
        open_case = get_active_blacklist_case(vendor)
        if open_case:
            return Response({'detail': 'This vendor already has an active blacklisting case.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'A blacklist reason is required.'}, status=status.HTTP_400_BAD_REQUEST)

        cooling_off_days = max(1, int(request.data.get('cooling_off_days') or 14))
        case = VendorBlacklistCase.objects.create(
            vendor=vendor,
            reason=reason,
            description=request.data.get('description', ''),
            justification_document=request.data.get('justification_document'),
            initiated_by=request.user,
            cooling_off_until=timezone.now() + timedelta(days=cooling_off_days),
            is_permanent=str(request.data.get('is_permanent', '')).lower() in {'1', 'true', 'yes'},
            expiry_date=request.data.get('expiry_date') or None,
        )
        apply_blacklist_initiation(case, request.user)
        return Response(VendorBlacklistCaseSerializer(case).data, status=status.HTTP_201_CREATED)


class VendorPrequalificationViewSet(viewsets.ModelViewSet):
    queryset = VendorPrequalification.objects.select_related('vendor', 'reviewed_by').all()
    serializer_class = VendorPrequalificationSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]

    def _refresh_vendor_resubmission_priority(self, preq: VendorPrequalification, response: Response) -> Response:
        preq.submitted_at = timezone.now()
        preq.save(update_fields=['submitted_at'])
        response.data = self.get_serializer(preq).data
        return response

    def get_queryset(self):
        user = self.request.user
        if IsReviewerRole.check(user):
            return self.queryset.order_by('-submitted_at', '-id')
        return self.queryset.filter(vendor=user).order_by('-submitted_at', '-id')

    def create(self, request, *args, **kwargs):
        if request.user.role != UserRole.VENDOR:
            raise PermissionDenied('Only vendors can submit pre-qualification forms.')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preq = serializer.save(vendor=request.user, status=PrequalificationStatus.PENDING)
        log_audit(request.user, 'prequalification_submitted', preq, {'vendor_id': request.user.id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        preq = self.get_object()
        if request.user.role == UserRole.VENDOR and preq.vendor_id == request.user.id:
            if preq.status != PrequalificationStatus.CLARIFICATION_REQUESTED:
                raise PermissionDenied('Only submissions marked Partial (Resubmit) can be edited.')
            response = super().update(request, *args, **kwargs)
            response = self._refresh_vendor_resubmission_priority(preq, response)
            log_audit(request.user, 'prequalification_resubmitted', preq, {'vendor_id': preq.vendor_id})
            return response
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can update pre-qualification records.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        preq = self.get_object()
        if request.user.role == UserRole.VENDOR and preq.vendor_id == request.user.id:
            if preq.status != PrequalificationStatus.CLARIFICATION_REQUESTED:
                raise PermissionDenied('Only submissions marked Partial (Resubmit) can be edited.')
            response = super().partial_update(request, *args, **kwargs)
            response = self._refresh_vendor_resubmission_priority(preq, response)
            log_audit(request.user, 'prequalification_resubmitted', preq, {'vendor_id': preq.vendor_id})
            return response
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can update pre-qualification records.')
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def start_review(self, request, pk=None):
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can start review.')
        preq = self.get_object()
        preq.status = PrequalificationStatus.UNDER_REVIEW
        preq.reviewed_by = request.user
        preq.reviewed_at = timezone.now()
        preq.reviewer_comments = request.data.get('reviewer_comments', preq.reviewer_comments)
        preq.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments'])
        log_audit(request.user, 'prequalification_under_review', preq, {'vendor_id': preq.vendor_id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can approve submissions.')
        preq = self.get_object()
        preq.status = PrequalificationStatus.APPROVED
        preq.reviewed_by = request.user
        preq.reviewed_at = timezone.now()
        preq.reviewer_comments = request.data.get('reviewer_comments', preq.reviewer_comments)
        preq.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments'])
        log_audit(request.user, 'prequalification_approved', preq, {'vendor_id': preq.vendor_id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def request_clarification(self, request, pk=None):
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can request clarification.')
        preq = self.get_object()
        preq.status = PrequalificationStatus.CLARIFICATION_REQUESTED
        preq.reviewed_by = request.user
        preq.reviewed_at = timezone.now()
        preq.reviewer_comments = request.data.get('reviewer_comments', preq.reviewer_comments)
        preq.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments'])
        log_audit(request.user, 'prequalification_clarification_requested', preq, {'vendor_id': preq.vendor_id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can reject submissions.')
        preq = self.get_object()
        preq.status = PrequalificationStatus.REJECTED
        preq.reviewed_by = request.user
        preq.reviewed_at = timezone.now()
        preq.reviewer_comments = request.data.get('reviewer_comments', preq.reviewer_comments)
        preq.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reviewer_comments'])
        log_audit(request.user, 'prequalification_rejected', preq, {'vendor_id': preq.vendor_id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_200_OK)


class VendorBlacklistCaseViewSet(viewsets.ModelViewSet):
    queryset = VendorBlacklistCase.objects.select_related(
        'vendor', 'initiated_by', 'reviewed_by', 'confirmed_by', 'reinstated_by'
    ).all()
    serializer_class = VendorBlacklistCaseSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]

    def get_queryset(self):
        qs = self.queryset.order_by('-initiated_at', '-id')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        if user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL, UserRole.AUDITOR, UserRole.TAC, UserRole.DOE_OFFICER}:
            return qs
        return qs.none()

    def create(self, request, *args, **kwargs):
        raise PermissionDenied('Use the initiate_blacklisting vendor action.')

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        if not IsBlacklistReviewerRole.check(request.user):
            raise PermissionDenied('Only TAC, Auditor, or DoE Officer can review blacklisting cases.')
        case = self.get_object()
        if case.initiated_by_id == request.user.id:
            raise PermissionDenied('Four-eyes control: the initiator cannot review the same blacklisting case.')
        case.status = BlacklistCaseStatus.UNDER_REVIEW
        case.reviewed_by = request.user
        case.reviewed_at = timezone.now()
        case.review_notes = request.data.get('review_notes', case.review_notes)
        case.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])
        log_audit(request.user, 'vendor_blacklisting_reviewed', case, {'vendor_id': str(case.vendor_id)})
        return Response(self.get_serializer(case).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        if not IsBlacklistConfirmerRole.check(request.user):
            raise PermissionDenied('Only Platform Administrator (Super Admin) or DoE Officer can confirm blacklisting.')
        case = self.get_object()
        if case.status not in {BlacklistCaseStatus.INITIATED, BlacklistCaseStatus.UNDER_REVIEW}:
            return Response({'detail': 'Only initiated or under-review cases can be confirmed.'}, status=status.HTTP_400_BAD_REQUEST)
        if case.initiated_by_id == request.user.id or case.reviewed_by_id == request.user.id:
            raise PermissionDenied('Four-eyes control: the confirmer must be different from the initiator and reviewer.')
        if case.cooling_off_until and timezone.now() < case.cooling_off_until:
            return Response({'detail': 'Cooling-off period is still active.'}, status=status.HTTP_400_BAD_REQUEST)
        case.confirmed_by = request.user
        case.final_decision_notes = request.data.get('final_decision_notes', case.final_decision_notes)
        if request.data.get('expiry_date'):
            case.expiry_date = request.data.get('expiry_date')
        if 'is_permanent' in request.data:
            case.is_permanent = str(request.data.get('is_permanent', '')).lower() in {'1', 'true', 'yes'}
        case.save(update_fields=['confirmed_by', 'final_decision_notes', 'expiry_date', 'is_permanent'])
        apply_blacklist_confirmation(case, request.user)
        return Response(self.get_serializer(case).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if not (IsBlacklistReviewerRole.check(request.user) or IsBlacklistConfirmerRole.check(request.user)):
            raise PermissionDenied('Only reviewer or confirmer roles can reject blacklisting cases.')
        case = self.get_object()
        case.status = BlacklistCaseStatus.REJECTED
        case.final_decision_notes = request.data.get('final_decision_notes', case.final_decision_notes)
        case.save(update_fields=['status', 'final_decision_notes'])
        case.vendor.status = UserStatus.ACTIVE
        case.vendor.save(update_fields=['status'])
        log_audit(request.user, 'vendor_blacklisting_rejected', case, {'vendor_id': str(case.vendor_id)})
        return Response(self.get_serializer(case).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reinstate(self, request, pk=None):
        if not IsBlacklistConfirmerRole.check(request.user):
            raise PermissionDenied('Only Platform Administrator (Super Admin) or DoE Officer can reinstate a vendor.')
        case = self.get_object()
        if case.status != BlacklistCaseStatus.BLACKLISTED:
            return Response({'detail': 'Only blacklisted cases can be reinstated.'}, status=status.HTTP_400_BAD_REQUEST)
        release_blacklist_case(case, request.user, expired=False)
        return Response(self.get_serializer(case).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def appeal(self, request, pk=None):
        case = self.get_object()
        if request.user.role != UserRole.VENDOR or case.vendor_id != request.user.id:
            raise PermissionDenied('Only the affected vendor can submit an appeal.')
        appeal = BlacklistAppeal.objects.create(
            case=case,
            vendor=request.user,
            rebuttal_text=request.data.get('rebuttal_text', ''),
            rebuttal_document=request.data.get('rebuttal_document'),
            status=BlacklistAppealStatus.SUBMITTED,
        )
        log_audit(request.user, 'vendor_blacklisting_appealed', appeal, {'case_id': str(case.id)})
        return Response(BlacklistAppealSerializer(appeal).data, status=status.HTTP_201_CREATED)


class BlacklistAppealViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlacklistAppeal.objects.select_related('case', 'vendor', 'reviewed_by').all()
    serializer_class = BlacklistAppealSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = self.queryset.order_by('-submitted_at', '-id')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor=user)
        if user.role in {UserRole.ADMIN, UserRole.AUDITOR, UserRole.RBF_OFFICIAL, UserRole.TAC, UserRole.DOE_OFFICER}:
            return qs
        return qs.none()

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        if request.user.role not in {UserRole.AUDITOR, UserRole.ADMIN}:
            raise PermissionDenied('Only Auditor or Platform Administrator (Super Admin) can review appeals.')
        appeal = self.get_object()
        appeal.status = BlacklistAppealStatus.RESOLVED
        appeal.reviewed_by = request.user
        appeal.reviewed_at = timezone.now()
        appeal.resolution_notes = request.data.get('resolution_notes', appeal.resolution_notes)
        appeal.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'resolution_notes'])
        log_audit(request.user, 'vendor_blacklisting_appeal_reviewed', appeal, {'case_id': str(appeal.case_id)})
        return Response(self.get_serializer(appeal).data, status=status.HTTP_200_OK)


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RequestRegistrationOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        otp_length = max(4, int(getattr(settings, 'OTP_LENGTH', 6)))
        otp = ''.join(random.choices(string.digits, k=otp_length))
        cache_key = f'registration_otp:{email}'
        otp_timeout = int(getattr(settings, 'OTP_EXPIRY_SECONDS', 600))
        # Cache is preferred, but keep a local fallback for dev/local setups.
        try:
            cache.set(cache_key, otp, timeout=otp_timeout)
        except Exception:
            pass
        _OTP_FALLBACK[cache_key] = (otp, time.time() + otp_timeout)

        expiry_minutes = max(1, otp_timeout // 60)
        subject = 'Your RBF registration OTP'
        message = (
            f'Your OTP for Renewable Lesotho RBF registration is: {otp}\n'
            f'This code expires in {expiry_minutes} minute(s).'
        )
        email_configured = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
        if not email_configured:
            if settings.DEBUG:
                return Response(
                    {
                        'detail': 'OTP generated in debug mode (email is not configured).',
                        'debug_otp': otp,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response({'detail': 'Email service is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({'detail': 'OTP sent successfully.'}, status=status.HTTP_200_OK)
        except Exception as exc:
            # Keep registration testable in local/debug even if SMTP auth/network fails
            if settings.DEBUG:
                return Response(
                    {
                        'detail': 'OTP generated in debug mode (email send failed).',
                        'debug_otp': otp,
                        'email_error': str(exc),
                    },
                    status=status.HTTP_200_OK,
                )
            return Response({'detail': 'Failed to send OTP email.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class VerifyRegistrationOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        otp = (request.data.get('otp') or '').strip()
        if not email or not otp:
            return Response({'detail': 'Email and OTP are required.'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'registration_otp:{email}'
        expected = None
        try:
            expected = cache.get(cache_key)
        except Exception:
            expected = None
        if expected is None:
            # Fallback: handle cache version mismatch if any
            try:
                expected = cache.get(cache_key, version=0)
            except Exception:
                expected = None
        if expected is None:
            fallback = _OTP_FALLBACK.get(cache_key)
            if fallback:
                fallback_otp, fallback_expires = fallback
                if time.time() <= fallback_expires:
                    expected = fallback_otp
                else:
                    _OTP_FALLBACK.pop(cache_key, None)
        if expected is None:
            return Response({'detail': 'OTP has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
        if otp != expected:
            return Response({'detail': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cache.delete(cache_key)
        except Exception:
            pass
        _OTP_FALLBACK.pop(cache_key, None)
        verified_key = f'registration_otp_verified:{email}'
        verified_timeout = int(getattr(settings, 'OTP_VERIFIED_SECONDS', 1800))
        try:
            cache.set(verified_key, True, timeout=verified_timeout)
        except Exception:
            pass
        return Response({'detail': 'OTP verified.'}, status=status.HTTP_200_OK)


class BootstrapDemoUsersView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.DEBUG:
            return Response({'detail': 'Not available.'}, status=status.HTTP_404_NOT_FOUND)
        call_command('seed_demo_users')
        return Response({'detail': 'Demo users ready.'}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        current_password = serializer.validated_data.get('current_password') or ''
        if not user.must_change_password and not user.check_password(current_password):
            return Response({'detail': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        AuditLogger.log('password_changed', 'users', user.id, 'user', notes='Password changed and first-login requirement cleared.')
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)
