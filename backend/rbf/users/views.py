import random
import string

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.management import call_command
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import User, UserRole, VendorPrequalification, PrequalificationStatus
from .serializers import UserSerializer, CustomTokenObtainPairSerializer, VendorPrequalificationSerializer
from rbf.projects.audit import log_audit


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


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if IsAdminOrRbfOfficial.check(user):
            return User.objects.all().order_by('-id')
        return User.objects.filter(id=getattr(user, 'id', None)).order_by('-id')

    def update(self, request, *args, **kwargs):
        target_user = self.get_object()
        if target_user.id != request.user.id and not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('You do not have permission to update this user.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        target_user = self.get_object()
        if target_user.id != request.user.id and not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('You do not have permission to update this user.')
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['patch', 'post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not IsAdminOrRbfOfficial.check(request.user):
            raise PermissionDenied('Only RBF Official or Digital Admin can approve vendors.')

        user = self.get_object()
        if user.role != UserRole.VENDOR:
            return Response({'detail': 'Only vendor accounts can be approved.'}, status=status.HTTP_400_BAD_REQUEST)

        user.status = 'Active'
        user.is_active = True
        user.save(update_fields=['status', 'is_active'])
        log_audit(request.user, 'vendor_account_approved', user, {'username': user.username})
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class VendorPrequalificationViewSet(viewsets.ModelViewSet):
    queryset = VendorPrequalification.objects.select_related('vendor', 'reviewed_by').all()
    serializer_class = VendorPrequalificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if IsReviewerRole.check(user):
            return self.queryset
        return self.queryset.filter(vendor=user)

    def create(self, request, *args, **kwargs):
        if request.user.role != UserRole.VENDOR:
            raise PermissionDenied('Only vendors can submit pre-qualification forms.')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preq = serializer.save(vendor=request.user, status=PrequalificationStatus.PENDING)
        log_audit(request.user, 'prequalification_submitted', preq, {'vendor_id': request.user.id})
        return Response(self.get_serializer(preq).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not IsReviewerRole.check(request.user):
            raise PermissionDenied('Only reviewer roles can update pre-qualification records.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
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


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    DEMO_USERNAMES = {
        'vendor_approved',
        'admin_user',
        'rbf_official',
        'tac_member',
        'doe_officer',
        'field_verifier',
        'donor_user',
        'auditor_user',
    }

    def post(self, request, *args, **kwargs):
        username = (request.data.get('username') or '').strip()
        try:
            response = super().post(request, *args, **kwargs)
        except APIException as exc:
            if settings.DEBUG and username in self.DEMO_USERNAMES:
                call_command('seed_demo_users')
                return super().post(request, *args, **kwargs)
            raise

        # In debug/local setups, keep demo credentials usable even if DB was reset
        if (
            settings.DEBUG
            and username in self.DEMO_USERNAMES
            and response.status_code == status.HTTP_401_UNAUTHORIZED
        ):
            call_command('seed_demo_users')
            response = super().post(request, *args, **kwargs)

        return response


class RequestRegistrationOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        otp_length = max(4, int(getattr(settings, 'OTP_LENGTH', 6)))
        otp = ''.join(random.choices(string.digits, k=otp_length))
        cache_key = f'registration_otp:{email}'
        cache.set(cache_key, otp, timeout=int(getattr(settings, 'OTP_EXPIRY_SECONDS', 300)))

        expiry_minutes = max(1, int(getattr(settings, 'OTP_EXPIRY_SECONDS', 300)) // 60)
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
        expected = cache.get(cache_key)
        if expected is None:
            return Response({'detail': 'OTP has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
        if otp != expected:
            return Response({'detail': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(cache_key)
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
