from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from .views import HealthCheckView
from rbf.projects.views import (
    MapBoundaryView,
    MapInstallationView,
    PortfolioKpiView,
    PublicPortfolioKpiView,
    ProjectKpiPdfView,
    ProjectKpiView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', HealthCheckView.as_view(), name='health'),
    path('api/kpi/project/<str:project_id>', ProjectKpiView.as_view(), name='kpi-project'),
    path('api/kpi/project/<str:project_id>/export-pdf', ProjectKpiPdfView.as_view(), name='kpi-project-export-pdf'),
    path('api/kpi/portfolio', PortfolioKpiView.as_view(), name='kpi-portfolio'),
    path('api/kpi/public-portfolio', PublicPortfolioKpiView.as_view(), name='kpi-public-portfolio'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/map/boundary', MapBoundaryView.as_view(), name='map-boundary'),
    path('api/map/installations', MapInstallationView.as_view(), name='map-installations'),
    path('api/installations/map-data', MapInstallationView.as_view(), name='installation-map-data'),
    path('api/users/', include('rbf.users.urls')),
    path('api/', include('rbf.tenders.urls')),
    path('api/projects/', include('rbf.projects.urls')),
    path('api/notifications/', include('rbf.notifications.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
