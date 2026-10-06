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
    MeterDataBatchViewSet,
    PaymentClaimViewSet,
    DisbursementViewSet,
    AuditLogViewSet,
    ProspectSyncLogViewSet,
    AnomalyFlagViewSet,
    KpiReviewViewSet,
    OversightReviewViewSet,
    AuditCaseViewSet,
    ResultsIndicatorViewSet,
    VendorPerformanceViewSet,
    SiteMonitoringVisitViewSet,
    ProjectReportTemplatesView,
    ProjectReportGenerateView,
    ProjectReportHistoryView,
    ProjectReportDownloadView,
    ProjectReportFilterOptionsView,
    ProjectReportStatusView,
    ProjectReportActionView,
    ProjectReportInboxView,
    ReportScheduleViewSet,
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
router.register(r'meter-data-batches', MeterDataBatchViewSet, basename='meter-data-batch')
router.register(r'milestones', MilestoneViewSet, basename='milestone')
router.register(r'monitoring-visits', SiteMonitoringVisitViewSet, basename='monitoring-visit')
router.register(r'kpi-reviews', KpiReviewViewSet, basename='kpi-review')
router.register(r'oversight-reviews', OversightReviewViewSet, basename='oversight-review')
router.register(r'audit-cases', AuditCaseViewSet, basename='audit-case')
router.register(r'results-indicators', ResultsIndicatorViewSet, basename='results-indicator')
router.register(r'report-schedules', ReportScheduleViewSet, basename='report-schedule')
router.register(r'vendor-performance', VendorPerformanceViewSet, basename='vendor-performance')
router.register(r'', ProjectViewSet, basename='project')

urlpatterns = router.urls + [
    # Backwards-compatible path (older frontend)
    path('report-templates/', ProjectReportTemplatesView.as_view(), name='report-templates-legacy'),
    # Current frontend path
    path('reports/templates/', ProjectReportTemplatesView.as_view(), name='report-templates'),
    path('reports/generate/', ProjectReportGenerateView.as_view(), name='report-generate'),
    path('reports/history/', ProjectReportHistoryView.as_view(), name='report-history'),
    path('reports/filter-options/', ProjectReportFilterOptionsView.as_view(), name='report-filter-options'),
    path('reports/inbox/', ProjectReportInboxView.as_view(), name='report-inbox'),
    path('reports/<uuid:report_id>/', ProjectReportStatusView.as_view(), name='report-status'),
    path('reports/<uuid:report_id>/download/', ProjectReportDownloadView.as_view(), name='report-download'),
    path('reports/<uuid:report_id>/<str:step>/', ProjectReportActionView.as_view(), name='report-action'),
]
