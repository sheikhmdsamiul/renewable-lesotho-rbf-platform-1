from rest_framework import serializers
from .models import (
    Project,
    Milestone,
    ProjectUpdate,
    ProjectDocument,
    PaymentClaim,
    Disbursement,
    AuditLog,
)
from rbf.tenders.models import TenderContract


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProjectSerializer(serializers.ModelSerializer):
    milestones = MilestoneSerializer(many=True, read_only=True)
    tender_reference_number = serializers.CharField(source='tender.reference_number', read_only=True)
    tender_name = serializers.CharField(source='tender.name', read_only=True)
    tender_budget = serializers.DecimalField(source='tender.budget', max_digits=14, decimal_places=2, read_only=True)
    tender_deadline = serializers.DateTimeField(source='tender.deadline', read_only=True)
    tender_awarded_at = serializers.DateTimeField(source='tender.awarded_at', read_only=True)
    tender_status = serializers.CharField(source='tender.status', read_only=True)
    contract_reference = serializers.SerializerMethodField()
    contract_status = serializers.SerializerMethodField()
    contract_signed_file = serializers.SerializerMethodField()
    milestone_total_amount = serializers.SerializerMethodField()
    milestone_count = serializers.SerializerMethodField()

    def _get_contract(self, obj: Project):
        if not hasattr(self, '_contract_cache'):
            self._contract_cache = {}
        cached = self._contract_cache.get(obj.id)
        if cached is not None:
            return cached
        contract = TenderContract.objects.filter(project_id=str(obj.id)).only(
            'reference_number', 'status', 'signed_file'
        ).first()
        self._contract_cache[obj.id] = contract
        return contract

    def get_contract_reference(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.reference_number if contract else None

    def get_contract_status(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.status if contract else None

    def get_contract_signed_file(self, obj: Project):
        contract = self._get_contract(obj)
        return contract.signed_file.url if contract and contract.signed_file else None

    def get_milestone_total_amount(self, obj: Project):
        milestones = list(obj.milestones.all())
        return sum(m.amount for m in milestones) if milestones else 0

    def get_milestone_count(self, obj: Project):
        return obj.milestones.count()

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id']


class ProjectUpdateSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = ProjectUpdate
        fields = '__all__'
        read_only_fields = ['id', 'author', 'author_username', 'created_at']


class ProjectDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = ProjectDocument
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_by', 'uploaded_by_username', 'uploaded_at']


class DisbursementSerializer(serializers.ModelSerializer):
    processed_by_username = serializers.CharField(source='processed_by.username', read_only=True)

    class Meta:
        model = Disbursement
        fields = '__all__'
        read_only_fields = ['id', 'processed_at', 'processed_by', 'processed_by_username']


class PaymentClaimSerializer(serializers.ModelSerializer):
    vendor_username = serializers.CharField(source='vendor.username', read_only=True)
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)
    disbursement = DisbursementSerializer(read_only=True)

    class Meta:
        model = PaymentClaim
        fields = '__all__'
        read_only_fields = [
            'id',
            'submitted_at',
            'verified_at',
            'approved_at',
            'paid_at',
            'reviewed_by',
            'reviewed_by_username',
            'vendor_username',
            'disbursement',
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'actor_username']
