from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    BlacklistAppealViewSet,
    UserViewSet,
    LoginView,
    CurrentUserView,
    ChangePasswordView,
    RequestRegistrationOtpView,
    VerifyRegistrationOtpView,
    BootstrapDemoUsersView,
    VendorBlacklistCaseViewSet,
    VendorPrequalificationViewSet,
    OrganizationViewSet,
    PlatformConfigurationView,
    PlatformConfigurationBoundaryRefreshView,
    PlatformConfigurationBoundaryUploadView,
    SystemHealthView,
    SuperAdminDashboardView,
)

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'prequalifications', VendorPrequalificationViewSet, basename='vendor-prequalification')
router.register(r'blacklisting-cases', VendorBlacklistCaseViewSet, basename='vendor-blacklisting-case')
router.register(r'blacklisting-appeals', BlacklistAppealViewSet, basename='vendor-blacklisting-appeal')
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('auth/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', CurrentUserView.as_view(), name='current_user'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/request-otp/', RequestRegistrationOtpView.as_view(), name='request_registration_otp'),
    path('auth/verify-otp/', VerifyRegistrationOtpView.as_view(), name='verify_registration_otp'),
    path('auth/bootstrap-demo-users/', BootstrapDemoUsersView.as_view(), name='bootstrap_demo_users'),
    path('admin/dashboard/', SuperAdminDashboardView.as_view(), name='super_admin_dashboard'),
    path('platform-configuration/', PlatformConfigurationView.as_view(), name='platform_configuration'),
    path('platform-configuration/refresh-boundary/', PlatformConfigurationBoundaryRefreshView.as_view(), name='platform_configuration_refresh_boundary'),
    path('platform-configuration/upload-boundary/', PlatformConfigurationBoundaryUploadView.as_view(), name='platform_configuration_upload_boundary'),
    path('system-health/', SystemHealthView.as_view(), name='system_health'),
]
urlpatterns += router.urls
