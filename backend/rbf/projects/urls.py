from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet,
    MilestoneViewSet,
    ProjectUpdateViewSet,
    ProjectDocumentViewSet,
    InstallationReportViewSet,
    VerificationTaskViewSet,
    SmartMeterReadingViewSet,
    PaymentClaimViewSet,
    DisbursementViewSet,
    AuditLogViewSet,
    ProspectSyncLogViewSet,
    AnomalyFlagViewSet,
    ConcernViewSet,
    ConcernResponseViewSet,
    AuditFindingViewSet,
    ProjectReportTemplatesView,
    ProjectReportGenerateView,
    ProjectReportHistoryView,
    ProjectReportDownloadView,
)

router = DefaultRouter()
router.register(r'prospect-sync-logs', ProspectSyncLogViewSet, basename='prospect-sync-log')
router.register(r'anomaly-flags', AnomalyFlagViewSet, basename='anomaly-flag')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'disbursements', DisbursementViewSet, basename='disbursement')
router.register(r'claims', PaymentClaimViewSet, basename='payment-claim')
router.register(r'updates', ProjectUpdateViewSet, basename='project-update')
router.register(r'documents', ProjectDocumentViewSet, basename='project-document')
router.register(r'installations', InstallationReportViewSet, basename='installation-report')
router.register(r'verification-tasks', VerificationTaskViewSet, basename='verification-task')
router.register(r'smart-meter-readings', SmartMeterReadingViewSet, basename='smart-meter-reading')
router.register(r'milestones', MilestoneViewSet, basename='milestone')
router.register(r'concerns', ConcernViewSet, basename='concern')
router.register(r'concern-responses', ConcernResponseViewSet, basename='concern-response')
router.register(r'audit-findings', AuditFindingViewSet, basename='audit-finding')
router.register(r'', ProjectViewSet, basename='project')

urlpatterns = router.urls + [
    # Backwards-compatible path (older frontend)
    path('report-templates/', ProjectReportTemplatesView.as_view(), name='report-templates-legacy'),
    # Current frontend path
    path('reports/templates/', ProjectReportTemplatesView.as_view(), name='report-templates'),
    path('reports/generate/', ProjectReportGenerateView.as_view(), name='report-generate'),
    path('reports/history/', ProjectReportHistoryView.as_view(), name='report-history'),
    path('reports/<uuid:report_id>/download/', ProjectReportDownloadView.as_view(), name='report-download'),
]
