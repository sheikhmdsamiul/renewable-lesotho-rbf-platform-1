from django.db.models import Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rbf.users.models import UserRole

from . import catalog
from .models import Notification, NotificationStatus
from .serializers import NotificationSerializer

# Only the Platform Administrator may look at other users' notifications (delivery log).
DELIVERY_LOG_ROLES = {UserRole.ADMIN}
MAX_BULK = 500


class NotificationViewSet(viewsets.ModelViewSet):
    """Each user's own inbox.

    List filters: ``unread=1``, ``archived=1`` (archived only; default excludes archived),
    ``category=<key>``, ``priority=high``, ``search=``. The Platform Administrator may pass
    ``scope=all`` to read every user's notifications (read-only delivery log); every write
    action works on the caller's own notifications only.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'status', 'event']
    search_fields = ['title', 'body', 'event', 'recipient_name']
    ordering_fields = ['timestamp']
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def _own(self):
        return Notification.objects.filter(recipient_id=str(self.request.user.id))

    def _wants_all(self):
        return self.action == 'list' and self.request.query_params.get('scope') == 'all'

    def get_queryset(self):
        params = self.request.query_params
        if self._wants_all():
            if self.request.user.role not in DELIVERY_LOG_ROLES:
                raise PermissionDenied('Only the Platform Administrator can view all users’ notifications.')
            qs = Notification.objects.all()
            if params.get('recipient_id'):
                qs = qs.filter(recipient_id=params['recipient_id'])
        else:
            qs = self._own()
        if self.action == 'list':
            if params.get('archived') in {'1', 'true'}:
                qs = qs.filter(archived_at__isnull=False)
            elif params.get('archived') != 'any':
                qs = qs.filter(archived_at__isnull=True)
            if params.get('unread') in {'1', 'true'}:
                qs = qs.filter(status=NotificationStatus.SENT)
            category = params.get('category')
            if category:
                qs = qs.filter(_category_q(category))
            if params.get('priority') == 'high':
                qs = qs.filter(_high_priority_q())
        return qs.order_by('-timestamp', '-id')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['related'] = getattr(self, '_related', None)
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        self._related = catalog.resolve_related(rows)
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        raise PermissionDenied('Notifications are created by the platform, not through this endpoint.')

    def destroy(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- counts -------------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        own = self._own().filter(archived_at__isnull=True)
        unread = own.filter(status=NotificationStatus.SENT)
        return Response({
            'count': unread.count(),
            'high_priority': unread.filter(_high_priority_q()).count(),
            'total': own.count(),
        })

    # --- single-item state ------------------------------------------------------------------
    def _set_read(self, notification, read: bool):
        notification.status = NotificationStatus.READ if read else NotificationStatus.SENT
        notification.read_at = (notification.read_at or timezone.now()) if read else None
        notification.save(update_fields=['status', 'read_at'])
        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        return self._set_read(self.get_object(), True)

    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        return self._set_read(self.get_object(), False)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        notification = self.get_object()
        notification.archived_at = notification.archived_at or timezone.now()
        if notification.status == NotificationStatus.SENT:
            notification.status = NotificationStatus.READ
            notification.read_at = notification.read_at or timezone.now()
        notification.save(update_fields=['archived_at', 'status', 'read_at'])
        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        notification = self.get_object()
        notification.archived_at = None
        notification.save(update_fields=['archived_at'])
        return Response(self.get_serializer(notification).data)

    # --- bulk ---------------------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        updated = self._own().filter(status=NotificationStatus.SENT, archived_at__isnull=True).update(
            status=NotificationStatus.READ, read_at=timezone.now(),
        )
        return Response({'updated': updated})

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """Apply one action to several of the caller's notifications: {"ids": [...], "action": ...}."""
        ids = request.data.get('ids')
        operation = str(request.data.get('action') or '')
        if not isinstance(ids, list) or not ids or len(ids) > MAX_BULK:
            raise ValidationError({'ids': f'Send a list of 1 to {MAX_BULK} notification ids.'})
        qs = self._own().filter(id__in=[i for i in ids if str(i).isdigit()])
        now = timezone.now()
        if operation == 'read':
            updated = qs.filter(status=NotificationStatus.SENT).update(status=NotificationStatus.READ, read_at=now)
        elif operation == 'unread':
            updated = qs.update(status=NotificationStatus.SENT, read_at=None)
        elif operation == 'archive':
            qs.filter(status=NotificationStatus.SENT).update(status=NotificationStatus.READ, read_at=now)
            updated = qs.filter(archived_at__isnull=True).update(archived_at=now)
        elif operation == 'unarchive':
            updated = qs.update(archived_at=None)
        elif operation == 'delete':
            updated, _ = qs.delete()
        else:
            raise ValidationError({'action': 'Use read, unread, archive, unarchive or delete.'})
        return Response({'updated': updated})


def _prefix_q(prefixes):
    q = Q()
    for prefix in prefixes:
        q |= Q(event__startswith=prefix)
    return q


def _high_priority_q():
    return Q(event__in=catalog.HIGH_PRIORITY_EVENTS) | Q(event__startswith='intent_to_award_approval_requested')


def _category_q(category):
    """Events in `category`, mirroring catalog.classify (first matching prefix wins)."""
    rules = catalog.EVENT_RULES
    if category == 'general':
        return ~_prefix_q([p for p, _, _ in rules])
    own = [p for p, c, _ in rules if c == category]
    if not own:
        return Q(pk__in=[])
    # A more specific prefix of another category shadows ours (e.g. project_oversight_flag vs project_).
    shadowing = [p for p, c, _ in rules if c != category and any(p.startswith(o) and p != o for o in own)]
    q = _prefix_q(own)
    if shadowing:
        q &= ~_prefix_q(shadowing)
    return q
