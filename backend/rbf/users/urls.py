from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    BlacklistAppealViewSet,
    BlacklistRecommendationViewSet,
    UserViewSet,
    LoginView,
    CurrentUserView,
    ChangePasswordView,
    RequestRegistrationOtpView,
    ValidateRegistrationView,
    VerifyRegistrationOtpView,
    BootstrapDemoUsersView,
    VendorBlacklistCaseViewSet,
    VendorPrequalificationViewSet,
    OrganizationViewSet,
    PlatformConfigurationView,
    PlatformConfigurationBoundaryRefreshView,
    PlatformConfigurationBoundaryUploadView,
    EvaluationScoringConfigView,
    ProcurementMethodsConfigView,
    CurrenciesConfigView,
    InclusionTargetsConfigView,
    SystemHealthView,
    SuperAdminDashboardView,
    RolePermissionsView,
)

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'prequalifications', VendorPrequalificationViewSet, basename='vendor-prequalification')
router.register(r'blacklisting-cases', VendorBlacklistCaseViewSet, basename='vendor-blacklisting-case')
router.register(r'blacklisting-appeals', BlacklistAppealViewSet, basename='vendor-blacklisting-appeal')
router.register(r'blacklisting-recommendations', BlacklistRecommendationViewSet, basename='vendor-blacklisting-recommendation')
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('auth/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', CurrentUserView.as_view(), name='current_user'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/validate-registration/', ValidateRegistrationView.as_view(), name='validate_registration'),
    path('auth/request-otp/', RequestRegistrationOtpView.as_view(), name='request_registration_otp'),
    path('auth/verify-otp/', VerifyRegistrationOtpView.as_view(), name='verify_registration_otp'),
    path('auth/bootstrap-demo-users/', BootstrapDemoUsersView.as_view(), name='bootstrap_demo_users'),
    path('admin/dashboard/', SuperAdminDashboardView.as_view(), name='super_admin_dashboard'),
    path('admin/permissions/', RolePermissionsView.as_view(), name='role_permissions'),
    path('platform-configuration/', PlatformConfigurationView.as_view(), name='platform_configuration'),
    path('platform-configuration/refresh-boundary/', PlatformConfigurationBoundaryRefreshView.as_view(), name='platform_configuration_refresh_boundary'),
    path('platform-configuration/upload-boundary/', PlatformConfigurationBoundaryUploadView.as_view(), name='platform_configuration_upload_boundary'),
    path('platform-configuration/evaluation-scoring/', EvaluationScoringConfigView.as_view(), name='evaluation_scoring_config'),
    path('platform-configuration/procurement-methods/', ProcurementMethodsConfigView.as_view(), name='procurement_methods_config'),
    path('platform-configuration/currencies/', CurrenciesConfigView.as_view(), name='currencies_config'),
    path('platform-configuration/inclusion-targets/', InclusionTargetsConfigView.as_view(), name='inclusion_targets_config'),
    path('system-health/', SystemHealthView.as_view(), name='system_health'),
]
urlpatterns += router.urls
