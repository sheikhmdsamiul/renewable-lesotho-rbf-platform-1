from rest_framework.routers import DefaultRouter
from .views import TenderViewSet, TenderBidViewSet, TenderBidEvaluationViewSet, TenderContractViewSet, NoticeViewSet

router = DefaultRouter()
router.register(r'tenders', TenderViewSet, basename='tender')
router.register(r'tender-bids', TenderBidViewSet, basename='tender-bid')
router.register(r'tender-bid-evaluations', TenderBidEvaluationViewSet, basename='tender-bid-evaluation')
router.register(r'tender-contracts', TenderContractViewSet, basename='tender-contract')
router.register(r'notices', NoticeViewSet, basename='notice')

urlpatterns = router.urls
