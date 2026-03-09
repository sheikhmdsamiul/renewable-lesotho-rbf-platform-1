from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from .views import HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', HealthCheckView.as_view(), name='health'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/users/', include('rbf.users.urls')),
    path('api/tenders/', include('rbf.tenders.urls')),
    path('api/projects/', include('rbf.projects.urls')),
    path('api/notifications/', include('rbf.notifications.urls')),
]
