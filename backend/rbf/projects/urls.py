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
)

router = DefaultRouter()
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'disbursements', DisbursementViewSet, basename='disbursement')
router.register(r'claims', PaymentClaimViewSet, basename='payment-claim')
router.register(r'updates', ProjectUpdateViewSet, basename='project-update')
router.register(r'documents', ProjectDocumentViewSet, basename='project-document')
router.register(r'installations', InstallationReportViewSet, basename='installation-report')
router.register(r'verification-tasks', VerificationTaskViewSet, basename='verification-task')
router.register(r'smart-meter-readings', SmartMeterReadingViewSet, basename='smart-meter-reading')
router.register(r'milestones', MilestoneViewSet, basename='milestone')
router.register(r'', ProjectViewSet, basename='project')

urlpatterns = router.urls
