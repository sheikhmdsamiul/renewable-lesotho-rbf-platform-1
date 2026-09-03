from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Notification, NotificationStatus
from .serializers import NotificationSerializer
from rbf.users.models import UserRole


STAFF_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}


class NotificationPermission(BasePermission):
    """
    Authenticated users can read their own notifications. Write access
    (create/update/delete/broadcast) is restricted to the RBF Management Team
    and Platform Administrator. Recipient-facing read-status actions are always
    allowed but are scoped to the requesting user's own rows.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if view.action in {'mark_read', 'mark_all_read'}:
            return True
        return user.role in STAFF_ROLES


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-timestamp')
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, NotificationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'status', 'recipient_id']
    search_fields = ['title', 'body', 'event']
    ordering_fields = ['timestamp']

    def get_queryset(self):
        qs = Notification.objects.all().order_by('-timestamp')
        user = self.request.user
        if user.role in STAFF_ROLES:
            return qs
        return qs.filter(recipient_id=str(user.id))

    def _assert_write_permission(self):
        user = self.request.user
        if user.role not in STAFF_ROLES:
            raise PermissionDenied('Only RBF Management Team or Platform Administrator (Super Admin) can modify notifications.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = self.get_queryset().filter(status=NotificationStatus.SENT).count()
        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.recipient_id != str(request.user.id) and request.user.role not in STAFF_ROLES:
            raise PermissionDenied('You can only mark your own notifications as read.')
        notification.status = NotificationStatus.READ
        notification.save(update_fields=['status'])
        return Response({'id': str(notification.id), 'status': notification.status})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(status=NotificationStatus.SENT).update(
            status=NotificationStatus.READ
        )
        return Response({'updated': updated})
