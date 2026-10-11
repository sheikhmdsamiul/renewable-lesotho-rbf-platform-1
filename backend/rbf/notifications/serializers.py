from rest_framework import serializers

from . import catalog
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)
    category = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    priority = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient_id', 'recipient_name', 'type', 'event', 'title', 'body', 'status', 'timestamp',
            'linked_entity_id', 'read_at', 'archived_at', 'is_read', 'category', 'category_label', 'priority', 'related',
        ]
        read_only_fields = ['id', 'timestamp', 'read_at', 'archived_at']

    def get_category(self, obj):
        return catalog.classify(obj.event)[0]

    def get_category_label(self, obj):
        return catalog.CATEGORY_LABELS[catalog.classify(obj.event)[0]]

    def get_priority(self, obj):
        return catalog.priority(obj.event)

    def get_related(self, obj):
        related = self.context.get('related')
        if related is None:
            related = catalog.resolve_related([obj])
        return related.get(obj.id) or catalog.resolve_related([obj]).get(obj.id)
