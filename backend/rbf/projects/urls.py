from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet,
    MilestoneViewSet,
    PaymentClaimViewSet,
    DisbursementViewSet,
    AuditLogViewSet,
)

router = DefaultRouter()
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'disbursements', DisbursementViewSet, basename='disbursement')
router.register(r'claims', PaymentClaimViewSet, basename='payment-claim')
router.register(r'milestones', MilestoneViewSet, basename='milestone')
router.register(r'', ProjectViewSet, basename='project')

urlpatterns = router.urls
