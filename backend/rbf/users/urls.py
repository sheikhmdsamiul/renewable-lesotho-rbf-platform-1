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
)

router = DefaultRouter()
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
]
urlpatterns += router.urls
