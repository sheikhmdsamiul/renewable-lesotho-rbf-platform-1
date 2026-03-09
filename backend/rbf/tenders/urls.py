from rest_framework.routers import DefaultRouter
from .views import TenderViewSet

router = DefaultRouter()
router.register(r'', TenderViewSet, basename='tender')

urlpatterns = router.urls
