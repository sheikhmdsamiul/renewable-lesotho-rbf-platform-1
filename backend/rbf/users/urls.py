from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserViewSet,
    LoginView,
    CurrentUserView,
    RequestRegistrationOtpView,
    VerifyRegistrationOtpView,
    BootstrapDemoUsersView,
    VendorPrequalificationViewSet,
)

router = DefaultRouter()
router.register(r'prequalifications', VendorPrequalificationViewSet, basename='vendor-prequalification')
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('auth/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', CurrentUserView.as_view(), name='current_user'),
    path('auth/request-otp/', RequestRegistrationOtpView.as_view(), name='request_registration_otp'),
    path('auth/verify-otp/', VerifyRegistrationOtpView.as_view(), name='verify_registration_otp'),
    path('auth/bootstrap-demo-users/', BootstrapDemoUsersView.as_view(), name='bootstrap_demo_users'),
]
urlpatterns += router.urls
