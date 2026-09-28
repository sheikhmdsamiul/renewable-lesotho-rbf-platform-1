import json
import os
import re
from decimal import Decimal
from math import ceil
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import serializers
from .models import (
    Tender,
    TenderBid,
    TenderBidSite,
    TenderBidEvaluation,
    EvaluationStatus,
    TenderContract,
    TenderChallenge,
    ChallengeStatus,
    ChallengeCategory,
    ChallengeDocument,
    ChallengeEvent,
    Notice,
    TenderStatus,
    BidStatus,
    BidStage,
    ProcurementWorkflow,
    ContractStatus,
    ContractSignatureStatus,
    TenderRequiredDocument,
    TenderLot,
    TenderBoqItem,
    TenderBidLotOffer,
    TenderEvaluationCommitteeMember,
    TenderInvitedVendor,
    ProcurementMethod,
    EvaluationStage,
    EvaluationSubmissionStatus,
    BudgetDisclosure,
    TenderAwardRecommendation,
    IntentToAwardRequest,
    IntentAwardRequestStatus,
)
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.projects.models import TechnologyType, VerificationMethod
from rbf.users.models import User, PlatformConfiguration


PRE_QUALIFICATION_STAGE_KEYS = {
    'pre_qualification',
    'prequalification',
    'pre-qualification',
    'concept',
    'stage_1',
    'stage1',
    'stage_1:_concept',
}
SITE_SPECIFIC_STAGE_KEYS = {
    'site_specific',
    'site-specific',
    'sitespecific',
    'detailed',
    'stage_2',
    'stage2',
    'stage_2:_detailed',
}
EOI_STAGE_KEYS = {
    'eoi',
    'expression_of_interest',
    'expression of interest',
    'pre_qualification',
    'prequalification',
    'pre-qualification',
    'concept',
    'stage_1',
    'stage1',
    'stage_1:_concept',
}
TECHNICAL_STAGE_KEYS = {
    'technical',
    'technical_bid',
    'rfp',
    'site_specific',
    'site-specific',
    'detailed',
    'stage_2',
    'stage2',
}
FINANCIAL_STAGE_KEYS = {'financial', 'financial_bid', 'price', 'price_bid', 'sealed', 'stage_3', 'stage3'}
COMBINED_STAGE_KEYS = {'combined', 'combined_bid', 'combined_bid_submission', 'stage_2_and_3'}

STAGE_ORDER = ('eoi', 'technical', 'financial')


def workflow_has_eoi_stage(tender, workflow=None) -> bool:
    """Whether a tender's procurement workflow includes an EOI stage.

    - eoi_combined: always has an EOI stage.
    - sequential: legacy, always has an EOI stage.
    - combined: has an EOI stage only for legacy tenders that set an eoi_deadline;
      newly created single-stage 'Combined' tenders have no EOI stage.
    """
    workflow = workflow or getattr(tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
    if workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.SEQUENTIAL):
        return True
    if workflow == ProcurementWorkflow.COMBINED:
        return bool(getattr(tender, 'eoi_deadline', None))
    return False


def workflow_is_combined_style(tender, workflow=None) -> bool:
    """Whether a workflow submits Technical and Financial together in a single record.

    True for 'EOI → Combined' and 'Combined' — both carry a combined (tech+fin) bid
    record rather than separate technical then financial stages. Only the legacy
    'Sequential' workflow uses distinct technical and financial records.
    """
    workflow = workflow or getattr(tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
    return workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.COMBINED)


def normalize_bid_stage(value) -> str:
    """Normalize any stage value to: eoi | technical | financial | combined."""
    raw = str(value or '').strip().lower().replace(' ', '_')
    if raw in COMBINED_STAGE_KEYS:
        return BidStage.COMBINED
    if raw in EOI_STAGE_KEYS:
        return BidStage.EOI
    if raw in FINANCIAL_STAGE_KEYS:
        return BidStage.FINANCIAL
    if raw in TECHNICAL_STAGE_KEYS:
        return BidStage.TECHNICAL
    return BidStage.TECHNICAL


def bid_stage_label(value) -> str:
    key = normalize_bid_stage(value)
    return {
        BidStage.EOI: 'EOI',
        BidStage.TECHNICAL: 'Technical',
        BidStage.FINANCIAL: 'Financial',
        BidStage.COMBINED: 'Technical & Financial',
    }.get(key, 'EOI')


def is_financial_stage(value) -> bool:
    return normalize_bid_stage(value) == BidStage.FINANCIAL


SITE_TARGET_BENEFICIARY_CHOICES = (
    ('female_headed', 'female_headed'),
    ('vulnerable', 'vulnerable'),
    ('low_income', 'low_income'),
    ('standard', 'standard'),
)
TECH_TIER_CHOICES = {f"Tier {idx}" for idx in range(1, 6)}


def normalize_tech_tier(value) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    normalized = raw.lower().replace('level', 'tier')
    match = normalized.replace('-', ' ').split()
    if len(match) == 2 and match[0] == 'tier' and match[1].isdigit():
        tier_number = int(match[1])
        if 1 <= tier_number <= 5:
            return f'Tier {tier_number}'
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits:
        tier_number = int(digits)
        if 1 <= tier_number <= 5:
            return f'Tier {tier_number}'
    return raw


def normalize_tender_stage(stage_value) -> str:
    raw = str(stage_value or '').strip()
    normalized = raw.lower().replace(' ', '_')
    if normalized in PRE_QUALIFICATION_STAGE_KEYS:
        return 'pre_qualification'
    if normalized in SITE_SPECIFIC_STAGE_KEYS:
        return 'site_specific'
    return 'pre_qualification'


def tender_stage_label(stage_value) -> str:
    return 'Stage 1: Concept' if normalize_tender_stage(stage_value) == 'pre_qualification' else 'Stage 2: Detailed'


def is_site_specific_stage(stage_value) -> bool:
    return normalize_tender_stage(stage_value) == 'site_specific'


def normalize_technology_type(value) -> str:
    raw = str(value or '').strip().upper()
    normalized = ' '.join(raw.replace('_', ' ').replace('/', ' ').split())
    mapping = {
        'SOLAR HOME SYSTEM': TechnologyType.SHS,
        'IMPROVED COOKSTOVE': TechnologyType.ICS,
        'MINI-GRID': TechnologyType.GMG,
        'MINI GRID': TechnologyType.GMG,
        'SOLAR MINI-GRID': TechnologyType.GMG,
        'SOLAR MINI GRID': TechnologyType.GMG,
        'SOLAR WATER PUMP': TechnologyType.SWP,
        'PRODUCTIVE USE': TechnologyType.PUE,
    }
    canonical_choices = {choice for choice, _ in TechnologyType.choices}
    return mapping.get(normalized, raw if raw in canonical_choices else '')


@lru_cache(maxsize=1)
def _load_lesotho_boundary_coordinates():
    geojson_path = Path(__file__).resolve().parents[2] / 'public' / 'geojson' / 'lesotho.geojson'
    if not geojson_path.exists():
        geojson_path = Path(__file__).resolve().parents[3] / 'public' / 'geojson' / 'lesotho.geojson'
    with geojson_path.open('r', encoding='utf-8') as geojson_file:
        payload = json.load(geojson_file)

    polygons = []
    if payload.get('type') == 'FeatureCollection':
        features = payload.get('features') or []
        for feature in features:
            geometry = feature.get('geometry') or {}
            geo_type = geometry.get('type')
            coordinates = geometry.get('coordinates') or []
            if geo_type == 'Polygon':
                polygons.append(coordinates)
            elif geo_type == 'MultiPolygon':
                polygons.extend(coordinates)
    elif payload.get('type') == 'Polygon':
        polygons.append(payload.get('coordinates') or [])
    elif payload.get('type') == 'MultiPolygon':
        polygons.extend(payload.get('coordinates') or [])
    elif payload.get('type') == 'Feature':
        geometry = payload.get('geometry') or {}
        geo_type = geometry.get('type')
        coordinates = geometry.get('coordinates') or []
        if geo_type == 'Polygon':
            polygons.append(coordinates)
        elif geo_type == 'MultiPolygon':
            polygons.extend(coordinates)
    return polygons


def _point_in_ring(longitude: Decimal, latitude: Decimal, ring) -> bool:
    inside = False
    x = float(longitude)
    y = float(latitude)
    ring_len = len(ring)
    if ring_len < 3:
        return False
    j = ring_len - 1
    for i in range(ring_len):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_lesotho(longitude: Decimal, latitude: Decimal) -> bool:
    for polygon in _load_lesotho_boundary_coordinates():
        if not polygon:
            continue
        outer_ring = polygon[0]
        if not _point_in_ring(longitude, latitude, outer_ring):
            continue
        holes = polygon[1:] if len(polygon) > 1 else []
        if any(_point_in_ring(longitude, latitude, hole) for hole in holes):
            continue
        return True
    return False


def has_stage_two_shortlist_access(bid) -> bool:
    if bid is None or not getattr(bid, 'stage_two_unlocked', False):
        return False
    source_bid = getattr(bid, 'stage_two_source_bid', None)
    return bool(source_bid and source_bid.status == BidStatus.ACCEPTED)


def has_technical_stage_access(bid) -> bool:
    """True when a vendor may work on the Technical stage bid for this tender."""
    if bid is None:
        return False
    if getattr(bid, 'bid_stage', '') in (BidStage.TECHNICAL, BidStage.COMBINED):
        if getattr(bid, 'technical_stage_unlocked', False):
            return True
        # Backward compat: legacy stage-two unlocked bids are treated as technical.
        if getattr(bid, 'stage_two_unlocked', False):
            source = getattr(bid, 'stage_two_source_bid', None)
            return bool(source and source.status == BidStatus.ACCEPTED)
        return True
    return False


def has_financial_stage_access(bid) -> bool:
    """True when a vendor may see/work the Financial stage for this tender."""
    if bid is None:
        return False
    if getattr(bid, 'financial_stage_unlocked', False):
        return True
    # Backward compat: a legacy unlocked stage-two bid carried both tech + fin.
    if getattr(bid, 'stage_two_unlocked', False):
        source = getattr(bid, 'stage_two_source_bid', None)
        return bool(source and source.status == BidStatus.ACCEPTED)
    return False


def financial_bid_is_sealed(bid, request=None) -> bool:
    """Financial pricing is hidden from evaluators until technical clearance.

    A financial bid is considered open only when its financial stage is unlocked
    AND the requesting user is not an evaluator who must wait for clearance.
    Vendors always see their own bid; RMT sees it once the financial stage is open.
    """
    if bid is None:
        return False
    # EOI-stage pricing is a rough, non-binding estimate — there's no final price to
    # protect from collusion yet, so it's never sealed. Only Financial/Combined bids
    # carry the binding figure this function exists to protect.
    if normalize_bid_stage(getattr(bid, 'bid_stage', None) or getattr(bid, 'stage', '') or '') == BidStage.EOI:
        return False
    if request is not None:
        user = getattr(request, 'user', None)
        role = getattr(user, 'role', None) if user is not None else None
        if role == UserRole.VENDOR:
            return False  # owners see their own bid including pricing
        if role == UserRole.EVALUATION_COMMITTEE:
            if not getattr(bid, 'financial_stage_unlocked', False):
                return True
        # Admin may review financials once the stage is open.
    return not bool(getattr(bid, 'financial_stage_unlocked', False))


class TenderBidSiteSerializer(serializers.ModelSerializer):
    target_beneficiary_type = serializers.ChoiceField(
        choices=SITE_TARGET_BENEFICIARY_CHOICES,
        required=False,
        allow_blank=True,
    )
    system_configuration = serializers.JSONField(required=False, write_only=True)
    lot = serializers.PrimaryKeyRelatedField(queryset=TenderLot.objects.all(), required=False, allow_null=True)

    class Meta:
        model = TenderBidSite
        fields = [
            'id',
            'lot',
            'site_name',
            'district',
            'village_sub_district',
            'latitude',
            'longitude',
            'system_configuration',
            'number_of_households',
            'target_beneficiary_type',
            'estimated_energy_demand_kwh_month',
            'road_access_available',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def to_internal_value(self, data):
        payload = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'estimated_households' in payload and 'number_of_households' not in payload:
            payload['number_of_households'] = payload.get('estimated_households')
        if 'village' in payload and 'village_sub_district' not in payload:
            payload['village_sub_district'] = payload.get('village')
        if 'primary_beneficiary_type' in payload and 'target_beneficiary_type' not in payload:
            payload['target_beneficiary_type'] = payload.get('primary_beneficiary_type')
        if 'road_access' in payload and 'road_access_available' not in payload:
            payload['road_access_available'] = payload.get('road_access')
        if 'target_technology' in payload:
            current_config = payload.get('system_configuration')
            if isinstance(current_config, str):
                try:
                    current_config = json.loads(current_config)
                except Exception:
                    current_config = {}
            if not isinstance(current_config, dict):
                current_config = {}
            current_config['target_technology'] = payload.get('target_technology')
            payload['system_configuration'] = current_config
        return super().to_internal_value(payload)

    def validate(self, attrs):
        errors = {}
        for field_name in ('site_name', 'district'):
            value = attrs.get(field_name)
            if value is not None and not str(value).strip():
                errors[field_name] = 'This field is required.'
        for field_name in ('latitude', 'longitude'):
            value = attrs.get(field_name)
            if value is None:
                continue
            numeric_value = Decimal(str(value))
            if field_name == 'latitude' and not Decimal('-90') <= numeric_value <= Decimal('90'):
                errors[field_name] = 'Latitude must be between -90 and 90.'
            if field_name == 'longitude' and not Decimal('-180') <= numeric_value <= Decimal('180'):
                errors[field_name] = 'Longitude must be between -180 and 180.'
        households = attrs.get('number_of_households')
        if households is not None and households < 1:
            errors['number_of_households'] = 'Number of households must be at least 1.'
        demand = attrs.get('estimated_energy_demand_kwh_month')
        if demand is not None and Decimal(str(demand)) <= Decimal('0'):
            errors['estimated_energy_demand_kwh_month'] = 'Estimated energy demand must be greater than 0.'
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('system_configuration', None)
        data['estimated_households'] = data.get('number_of_households')
        data['village'] = data.get('village_sub_district')
        data['primary_beneficiary_type'] = data.get('target_beneficiary_type')
        data['road_access'] = data.get('road_access_available')
        data['target_technology'] = (instance.system_configuration or {}).get('target_technology', '')
        return data


def _resolve_boq_from_template(template_items, submitted_items):
    """Reconcile a vendor's submitted BOQ rows against the RBF-designed template for a
    tender (or one of its lots): description/unit/quantity are always taken from the
    template — never trusted from the client — and only unit_price is read from
    whichever submitted row references each template item (matched by
    'template_item_id'). Returns (resolved_items, total, missing_descriptions) where
    missing_descriptions lists any template item the vendor didn't price."""
    submitted_by_id = {}
    for row in (submitted_items or []):
        if not isinstance(row, dict):
            continue
        key = row.get('template_item_id')
        if key is None:
            continue
        try:
            key = int(key)
        except (TypeError, ValueError):
            continue
        submitted_by_id[key] = row

    resolved = []
    total = Decimal('0')
    missing = []
    for idx, item in enumerate(template_items, start=1):
        row = submitted_by_id.get(item.id)
        unit_price = row.get('unit_price') if row else None
        if unit_price in (None, ''):
            missing.append(item.description)
            continue
        try:
            unit_price_dec = Decimal(str(unit_price))
        except Exception:
            missing.append(item.description)
            continue
        if unit_price_dec < 0:
            missing.append(item.description)
            continue
        line_total = Decimal(str(item.quantity)) * unit_price_dec
        total += line_total
        resolved.append({
            'template_item_id': item.id,
            'item_number': idx,
            'description': item.description,
            'unit': item.unit,
            'qty': str(item.quantity),
            'unit_price': str(unit_price_dec),
            'total': str(line_total),
        })
    return resolved, total, missing


class TenderBidSerializer(serializers.ModelSerializer):
    """Serializer for vendor bid submissions and tracking"""
    sites = TenderBidSiteSerializer(many=True, required=False)
    lot_offers = serializers.JSONField(required=False, allow_null=True, write_only=True)
    tender_reference = serializers.CharField(source='tender.reference_number', read_only=True)
    tender_name = serializers.CharField(source='tender.name', read_only=True)
    tender_status = serializers.CharField(source='tender.status', read_only=True)
    tender_intent_to_award_at = serializers.DateTimeField(source='tender.intent_to_award_at', read_only=True)
    tender_intent_to_award_bid_id = serializers.SerializerMethodField()
    tender_awarded_at = serializers.DateTimeField(source='tender.awarded_at', read_only=True)
    tender_awarded_vendor_id = serializers.CharField(source='tender.awarded_vendor_id', read_only=True)
    tender_awarded_vendor_name = serializers.CharField(source='tender.awarded_vendor_name', read_only=True)
    stage = serializers.CharField(read_only=True)
    stage_key = serializers.SerializerMethodField()
    stage_badge = serializers.SerializerMethodField()
    technology_type = serializers.SerializerMethodField()
    tender_technology_types = serializers.SerializerMethodField()
    tender_procurement_workflow = serializers.SerializerMethodField()
    tender_skips_eoi_stage = serializers.SerializerMethodField()
    document_requirements = serializers.SerializerMethodField()
    document_counts = serializers.SerializerMethodField()
    stage_two_ready = serializers.SerializerMethodField()
    financial_stage_open = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()
    deadline_passed = serializers.SerializerMethodField()
    deadline_countdown_seconds = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()
    version_history = serializers.SerializerMethodField()
    evaluation_status = serializers.SerializerMethodField()
    technical_score_total = serializers.SerializerMethodField()
    financial_score_total = serializers.SerializerMethodField()
    has_challenge = serializers.SerializerMethodField()
    
    class Meta:
        model = TenderBid
        fields = [
            'id', 'tender', 'vendor_id', 'vendor_name', 'vendor_email',
            'tender_reference', 'tender_name', 'tender_status',
            'tender_intent_to_award_at', 'tender_intent_to_award_bid_id',
            'tender_awarded_at', 'tender_awarded_vendor_id', 'tender_awarded_vendor_name',
            'bid_amount', 'bid_currency', 'subsidy_requested', 'lot_offers', 'declared_lots', 'proposal_file', 'stage', 'stage_key', 'stage_badge', 'technology_type', 'tender_technology_types', 'technology_types', 'concept_note', 'custom_documents',
            'technical_proposal', 'financial_proposal',
            'system_configuration', 'boq_items', 'boq_details', 'device_brand_model', 'tech_tier', 'energy_target_kwh_month',
            'technical_proposal_file', 'financial_proposal_file', 'boq_file',
            'gender_action_plan_file', 'implementation_plan_file', 'om_plan_file', 'reporting_templates_file', 'distribution_map_file',
            'tender_security_file',
            'female_target_pct', 'vulnerable_target_pct', 'low_income_target_pct',
            'inclusion_commitment_confirmed',
            'om_strategy_summary', 'local_technicians_to_be_trained', 'warranty_period_months',
            'offer_paygo', 'paygo_platform', 'daily_payment_amount_lsl', 'collection_method', 'preferred_district',
            'stage_two_unlocked', 'stage_two_unlocked_at', 'stage_two_source_bid', 'stage_two_ready',
            'bid_stage', 'eoi_narrative',
            'company_credentials_file', 'financial_standing_file', 'technical_experience_file', 'track_record_file',
            'financial_standing_summary', 'technical_experience_summary', 'track_record_summary',
            'technical_stage_unlocked', 'technical_stage_unlocked_at', 'technical_stage_source_bid',
            'financial_stage_unlocked', 'financial_stage_unlocked_at', 'financial_stage_source_bid',
            'financial_sealed', 'financial_unsealed_at',
            'tender_procurement_workflow', 'tender_skips_eoi_stage', 'financial_stage_open',
            'document_requirements', 'document_counts',
            'deadline', 'deadline_passed', 'deadline_countdown_seconds', 'is_locked', 'version_history',
            'evaluation_status', 'technical_score_total', 'financial_score_total', 'has_challenge',
            'status', 'version_number',
            'submitted_at', 'reviewed_at', 'reviewed_by', 'rejection_reason',
            'created_at', 'updated_at', 'sites'
        ]
        read_only_fields = ['id', 'submitted_at', 'created_at', 'updated_at', 'stage', 'stage_key', 'stage_badge', 'technology_type', 'stage_two_unlocked', 'stage_two_unlocked_at', 'stage_two_source_bid', 'stage_two_ready', 'bid_stage', 'technical_stage_unlocked', 'technical_stage_unlocked_at', 'technical_stage_source_bid', 'financial_stage_unlocked', 'financial_stage_unlocked_at', 'financial_stage_source_bid', 'financial_sealed', 'financial_unsealed_at', 'tender_procurement_workflow', 'tender_skips_eoi_stage', 'financial_stage_open']

    def get_tender_intent_to_award_bid_id(self, obj):
        bid_id = getattr(obj.tender, 'intent_to_award_bid_id', None)
        return str(bid_id) if bid_id is not None else None

    def to_internal_value(self, data):
        if hasattr(data, 'lists'):
            payload = {}
            for key, values in data.lists():
                payload[key] = values[-1] if len(values) == 1 else values
        else:
            payload = data.copy() if hasattr(data, 'copy') else dict(data)
        alias_map = {
            'om_plan_document': 'om_plan_file',
            'warranty_period': 'warranty_period_months',
            'warranty_months': 'warranty_period_months',
            'technology_type_list': 'technology_types',
            # The vendor bid wizard only ever sends 'energy_target' (never the canonical
            # field name) - without this mapping it was silently discarded below and
            # energy_target_kwh_month never got saved from any vendor submission.
            'energy_target': 'energy_target_kwh_month',
        }
        for alias, canonical in alias_map.items():
            if alias in payload and canonical not in payload:
                payload[canonical] = payload.get(alias)
        for alias in (
            'om_plan_document',
            'warranty_period',
            'warranty_months',
            'gender_inclusion_target',
            'vulnerable_group_target',
            'low_income_target',
            'energy_target',
            'paygo_offered',
            'min_daily_payment_lsl',
            'local_technicians_count',
        ):
            payload.pop(alias, None)
        for field_name in ('sites', 'system_configuration', 'boq_items', 'boq_details', 'custom_documents', 'lot_offers', 'declared_lots'):
            value = payload.get(field_name)
            if isinstance(value, str):
                try:
                    payload[field_name] = json.loads(value)
                except Exception:
                    pass
        if 'co_financing_amount' in payload and 'system_configuration' not in payload:
            payload['system_configuration'] = {}
        if 'system_configuration' in payload and not isinstance(payload.get('system_configuration'), dict):
            payload['system_configuration'] = {}
        system_configuration = payload.get('system_configuration')
        if isinstance(system_configuration, dict):
            for input_key, target_key in (
                ('device_brand', 'device_brand'),
                ('device_model', 'device_model'),
                ('rated_power_w', 'rated_power_w'),
                ('battery_capacity_wh', 'battery_capacity_wh'),
                ('pv_panel_size_w', 'pv_panel_size_w'),
                ('inverter_type', 'inverter_type'),
                ('co_financing_amount', 'co_financing_amount_lsl'),
            ):
                if input_key in payload and target_key not in system_configuration:
                    system_configuration[target_key] = payload.get(input_key)
            if 'aftersales_description' in payload and isinstance(system_configuration, dict):
                system_configuration['aftersales_description'] = payload.get('aftersales_description')
        return super().to_internal_value(payload)

    def _resolved_stage(self, obj):
        """Stage for an existing bid instance, prioritizing legacy stage-two bids."""
        if obj is None:
            return BidStage.EOI
        if getattr(obj, 'stage_two_unlocked', False):
            return BidStage.TECHNICAL
        return normalize_bid_stage(getattr(obj, 'bid_stage', None) or getattr(obj, 'stage', '') or '')

    def _effective_bid_stage(self, attrs):
        """Return the canonical stage this bid record belongs to."""
        instance = getattr(self, 'instance', None)
        if instance is not None:
            return self._resolved_stage(instance)
        # Creating a new record: use the provided bid_stage or the tender's opening stage.
        bid_stage = attrs.get('bid_stage')
        if not bid_stage:
            # bid_stage is exposed read-only, so it is not in validated_data; fall back to
            # the raw request payload so the client's intended stage is honored on create.
            request = self.context.get('request')
            if request is not None:
                raw = request.data.get('bid_stage') or request.data.get('stage') or ''
                if raw:
                    bid_stage = normalize_bid_stage(raw)
        if bid_stage:
            return normalize_bid_stage(bid_stage)
        tender = attrs.get('tender')
        if tender is not None:
            workflow = getattr(tender, 'procurement_workflow', '') or ''
            # Legacy 'combined' workflow (with an EOI stage) and single-stage 'Combined'
            # both resolve their detailed stage to COMBINED; 'EOI → Combined' opens at EOI.
            if workflow == ProcurementWorkflow.COMBINED:
                return BidStage.COMBINED
        return BidStage.EOI

    def _effective_stage_key(self, attrs):
        return self._effective_bid_stage(attrs)

    def _effective_stage_label(self, attrs):
        return bid_stage_label(self._effective_bid_stage(attrs))

    def validate(self, attrs):
        errors = {}
        request = self.context.get('request')
        instance = getattr(self, 'instance', None)
        tender = attrs.get('tender') or getattr(instance, 'tender', None)
        stage_key = self._effective_stage_key(attrs)
        stage_key = normalize_bid_stage(stage_key)
        attrs['stage'] = self._effective_stage_label(attrs)
        attrs['bid_stage'] = stage_key

        def validate_file(field_name, allowed_ext=None):
            file_obj = attrs.get(field_name, getattr(instance, field_name, None) if instance else None)
            if not file_obj:
                return
            if getattr(file_obj, 'size', 0) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                errors[field_name] = f'File too large (max {settings.MAX_FILE_SIZE_MB}MB).'
                return
            valid_ext = allowed_ext or {'.pdf', '.docx', '.xlsx'}
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                errors[field_name] = 'Invalid file type. Allowed: PDF, DOCX, XLSX.'

        validate_file('proposal_file')
        validate_file('technical_proposal_file')
        validate_file('financial_proposal_file')
        validate_file('boq_file')
        validate_file('gender_action_plan_file')
        validate_file('implementation_plan_file')
        validate_file('om_plan_file')
        validate_file('reporting_templates_file')
        validate_file('company_credentials_file')
        validate_file('financial_standing_file')
        validate_file('technical_experience_file')
        validate_file('track_record_file')

        bid_amount = attrs.get('bid_amount', instance.bid_amount if instance else None)
        subsidy_requested = attrs.get('subsidy_requested', instance.subsidy_requested if instance else None)
        system_configuration = attrs.get('system_configuration', instance.system_configuration if instance else {})
        if system_configuration and not isinstance(system_configuration, dict):
            errors['system_configuration'] = 'System configuration must be an object.'
        elif isinstance(system_configuration, dict):
            numeric_fields = ('rated_power_w', 'battery_capacity_wh', 'pv_panel_size_w')
            for field_name in numeric_fields:
                value = system_configuration.get(field_name)
                if value not in (None, '') and Decimal(str(value)) <= Decimal('0'):
                    errors.setdefault('system_configuration', {})[field_name] = 'Value must be greater than 0.'

        bid_status = attrs.get('status', getattr(instance, 'status', None) if instance else None)

        bid_currency = str(attrs.get('bid_currency', instance.bid_currency if instance else '') or '').strip()
        if bid_currency and tender:
            allowed_currencies = {tender.bidding_currency} | set((tender.currency_rates or {}).keys())
            if bid_currency not in allowed_currencies:
                errors['bid_currency'] = f'{bid_currency} is not an accepted currency for this tender.'

        is_detailed = stage_key in (BidStage.TECHNICAL, BidStage.COMBINED)
        is_eoi = stage_key == BidStage.EOI
        is_financial = stage_key == BidStage.FINANCIAL
        is_lot_wise = bool(tender and tender.lots.exists())

        declared_lots = attrs.get('declared_lots', instance.declared_lots if instance else [])
        declared_lots = declared_lots if isinstance(declared_lots, list) else []
        declared_lot_ids = set()
        for lot_id in declared_lots:
            try:
                declared_lot_ids.add(int(lot_id))
            except (TypeError, ValueError):
                continue

        # ---- EOI stage (Stage 1) ----
        if is_eoi:
            if is_lot_wise and bid_status == BidStatus.SUBMITTED:
                if not declared_lot_ids:
                    errors['declared_lots'] = 'Select at least one lot to bid on.'
                else:
                    tender_lot_ids = set(tender.lots.values_list('id', flat=True))
                    if not declared_lot_ids.issubset(tender_lot_ids):
                        errors['declared_lots'] = 'One or more selected lots are not part of this tender.'
                    max_lots = getattr(tender, 'max_lots_per_bidder', None)
                    if max_lots and len(declared_lot_ids) > max_lots:
                        errors['declared_lots'] = f'You may bid on at most {max_lots} lot(s) for this tender.'
            eoi_narrative = str(attrs.get('eoi_narrative', getattr(instance, 'eoi_narrative', '') if instance else '') or '').strip()
            if bid_status == BidStatus.SUBMITTED and len(eoi_narrative) < 200:
                errors['eoi_narrative'] = 'EOI narrative must be at least 200 characters before submission.'

            # Indicative pricing is optional at EOI, but if provided it must be sane.
            if bid_amount not in (None, '') and Decimal(str(bid_amount)) <= Decimal('0'):
                errors['bid_amount'] = 'Bid amount must be greater than 0.'
            if subsidy_requested not in (None, ''):
                if Decimal(str(subsidy_requested)) < Decimal('0'):
                    errors['subsidy_requested'] = 'Subsidy requested cannot be negative.'
                elif bid_amount not in (None, '') and Decimal(str(subsidy_requested)) > Decimal(str(bid_amount)):
                    errors['subsidy_requested'] = 'Subsidy requested cannot exceed the bid amount.'

            # Inclusion commitment is declared once, here, and carried forward to later stages.
            if bid_status == BidStatus.SUBMITTED:
                female_target_pct = attrs.get('female_target_pct', instance.female_target_pct if instance else 0)
                vulnerable_target_pct = attrs.get('vulnerable_target_pct', instance.vulnerable_target_pct if instance else 0)
                low_income_target_pct = attrs.get('low_income_target_pct', instance.low_income_target_pct if instance else 0)
                if int(female_target_pct or 0) < 50:
                    errors['female_target_pct'] = 'Female-headed household target must be at least 50%.'
                if int(vulnerable_target_pct or 0) < 30:
                    errors['vulnerable_target_pct'] = 'Vulnerable group target must be at least 30%.'
                if int(low_income_target_pct or 0) < 60:
                    errors['low_income_target_pct'] = 'Low-income household target must be at least 60%.'
                if not attrs.get('inclusion_commitment_confirmed', instance.inclusion_commitment_confirmed if instance else False):
                    errors['inclusion_commitment_confirmed'] = 'You must confirm the inclusion commitment before submitting.'

        # ---- Financial pricing (Financial stage, or Combined which bundles both) ----
        collects_final_pricing = is_financial or (is_detailed and stage_key == BidStage.COMBINED)
        if collects_final_pricing and bid_status == BidStatus.SUBMITTED:
            if is_lot_wise:
                lot_offers = attrs.get('lot_offers')
                if lot_offers is None and instance is not None:
                    lot_offers = [
                        {'lot': o.lot_id, 'bid_amount': o.bid_amount, 'subsidy_requested': o.subsidy_requested, 'boq_items': o.boq_items}
                        for o in instance.lot_offers.all()
                    ]
                lot_offers = lot_offers if isinstance(lot_offers, list) else []
                if not lot_offers:
                    errors['lot_offers'] = 'Offer a price for at least one lot.'
                else:
                    max_lots = getattr(tender, 'max_lots_per_bidder', None)
                    if max_lots and len(lot_offers) > max_lots:
                        errors['lot_offers'] = f'You may bid on at most {max_lots} lot(s) for this tender.'
                    # A lot may only be priced here if it was declared at EOI. Bids with no
                    # declared_lots recorded (created before this constraint existed) fall
                    # back to allowing any lot on the tender, for backward compatibility.
                    tender_lot_ids = set(tender.lots.values_list('id', flat=True))
                    allowed_lot_ids = declared_lot_ids if declared_lot_ids else tender_lot_ids
                    for offer in lot_offers:
                        if not isinstance(offer, dict):
                            continue
                        offer_lot_id = offer.get('lot') or offer.get('lot_id')
                        try:
                            offer_lot_id = int(offer_lot_id)
                        except (TypeError, ValueError):
                            offer_lot_id = None
                        if offer_lot_id not in allowed_lot_ids:
                            errors['lot_offers'] = 'One or more offers reference a lot you did not declare at the EOI stage.'
                            break
                        # If the RBF designed a BOQ for this specific lot, the vendor's
                        # unit prices (matched by template_item_id) are the source of
                        # truth for both the line items and the lot's bid amount —
                        # description/unit/quantity are never trusted from the client.
                        lot_boq_template = list(TenderBoqItem.objects.filter(lot_id=offer_lot_id).order_by('position', 'id'))
                        if lot_boq_template:
                            resolved_items, boq_total, missing = _resolve_boq_from_template(lot_boq_template, offer.get('boq_items'))
                            if missing:
                                errors['lot_offers'] = f"Provide a unit price for every BOQ item on this lot: missing {', '.join(missing)}."
                                break
                            offer['boq_items'] = resolved_items
                            offer['bid_amount'] = str(boq_total)
                            offer_amount = boq_total
                        else:
                            offer_amount = offer.get('bid_amount')
                            if offer_amount in (None, '') or Decimal(str(offer_amount)) <= Decimal('0'):
                                errors['lot_offers'] = 'Each lot offer needs a bid amount greater than 0.'
                                break
                        offer_subsidy = offer.get('subsidy_requested')
                        if offer_subsidy not in (None, '') and Decimal(str(offer_subsidy)) > Decimal(str(offer_amount)):
                            errors['lot_offers'] = 'Subsidy requested cannot exceed the bid amount for a lot.'
                            break
            else:
                if bid_amount in (None, '') or Decimal(str(bid_amount)) <= Decimal('0'):
                    errors['bid_amount'] = 'Bid amount is required for the Financial stage and must be greater than 0.'
                if subsidy_requested in (None, ''):
                    errors['subsidy_requested'] = 'Subsidy requested is required for the Financial stage.'
                elif bid_amount not in (None, '') and Decimal(str(subsidy_requested)) > Decimal(str(bid_amount)):
                    errors['subsidy_requested'] = 'Subsidy requested cannot exceed the bid amount.'

        # ---- Technical / Combined stage (Stage 2) ----
        if is_detailed:
            boq_total = Decimal('0')
            boq_present = False
            if is_lot_wise:
                # Lot-wise BOQ is fully validated per lot in the pricing block above
                # (each lot's vendor unit prices are reconciled against that lot's own
                # TenderBoqItem template, or freely typed if the lot has none) — no
                # flat, tender-wide BOQ requirement applies here.
                boq_present = True
            else:
                boq_template_qs = list(tender.boq_template_items.filter(lot__isnull=True).order_by('position', 'id')) if tender else []
                if boq_template_qs:
                    # The RBF designed this tender's BOQ — only the vendor's unit
                    # prices (matched by template_item_id) are trusted; description,
                    # unit, and quantity always come from the template.
                    submitted_items = attrs.get('boq_items')
                    if submitted_items is None:
                        submitted_items = attrs.get('boq_details')
                    if submitted_items is None and instance is not None:
                        submitted_items = instance.boq_items
                    resolved_items, boq_total, missing = _resolve_boq_from_template(boq_template_qs, submitted_items)
                    if missing:
                        errors['boq_items'] = f"Provide a unit price for every BOQ item: missing {', '.join(missing)}."
                    else:
                        attrs['boq_items'] = resolved_items
                        attrs['boq_details'] = resolved_items
                        boq_present = True
                        if (
                            stage_key == BidStage.COMBINED
                            and bid_amount not in (None, '')
                            and boq_total != Decimal(str(bid_amount))
                        ):
                            errors['boq_items'] = f'BOQ grand total must equal the bid amount. Current total: {boq_total}.'
                else:
                    boq_items = attrs.get('boq_items', instance.boq_items if instance else [])
                    if not boq_items:
                        boq_items = attrs.get('boq_details', [])
                    if not boq_items:
                        errors['boq_items'] = 'Bill of Quantities is required for technical submissions.'
                    elif isinstance(boq_items, list):
                        boq_present = True
                        for item in boq_items:
                            qty = item.get('qty') if isinstance(item, dict) else None
                            unit_price = item.get('unit_price') if isinstance(item, dict) else None
                            if qty not in (None, '') and unit_price not in (None, ''):
                                boq_total += Decimal(str(qty)) * Decimal(str(unit_price))
                        if (
                            stage_key == BidStage.COMBINED
                            and bid_amount not in (None, '')
                            and boq_total != Decimal(str(bid_amount))
                        ):
                            errors['boq_items'] = f'BOQ grand total must equal the bid amount. Current total: {boq_total}.'
                        # Technical-stage BOQ is not reconciled against a bid amount: pricing is
                        # decided later, at the Financial stage, and stays sealed until then.

            if boq_present:
                om_strategy_summary = attrs.get('om_strategy_summary', instance.om_strategy_summary if instance else '')
                if not str(om_strategy_summary or '').strip():
                    errors['om_strategy_summary'] = 'O&M strategy summary is required for technical submissions.'

                offer_paygo = attrs.get('offer_paygo', instance.offer_paygo if instance else False)
                technology_type = system_configuration.get('technology_type') if isinstance(system_configuration, dict) else None
                if not technology_type and tender:
                    technology_type = getattr(tender, 'category', None)
                normalized_tender_tech = normalize_technology_type(technology_type)
                if normalized_tender_tech == TechnologyType.SHS or str(technology_type).upper() == 'SHS':
                    paygo_platform = attrs.get('paygo_platform', instance.paygo_platform if instance else '')
                    daily_payment_amount_lsl = attrs.get('daily_payment_amount_lsl', instance.daily_payment_amount_lsl if instance else None)
                    collection_method = attrs.get('collection_method', instance.collection_method if instance else '')
                    if offer_paygo:
                        if not str(paygo_platform or '').strip():
                            errors['paygo_platform'] = 'PAYGO platform is required when PAYGO is offered.'
                        if daily_payment_amount_lsl in (None, '') or Decimal(str(daily_payment_amount_lsl)) <= Decimal('0'):
                            errors['daily_payment_amount_lsl'] = 'Minimum daily payment is required when PAYGO is offered.'
                        if not str(collection_method or '').strip():
                            errors['collection_method'] = 'Collection method is required when PAYGO is offered.'

                # Inclusion commitment is validated once, at the EOI stage, and carried
                # forward — not re-checked here.
                sites = attrs.get('sites', instance.sites.all() if instance and hasattr(instance, 'sites') else [])
                if not sites:
                    errors['sites'] = 'At least 1 project site is required.'
                else:
                    site_errors = {}
                    tender_lot_ids = set(tender.lots.values_list('id', flat=True)) if (is_lot_wise and tender) else set()
                    allowed_site_lot_ids = declared_lot_ids if declared_lot_ids else tender_lot_ids
                    for idx, site in enumerate(sites):
                        site_name = getattr(site, 'site_name', None) if not isinstance(site, dict) else site.get('site_name')
                        district = getattr(site, 'district', None) if not isinstance(site, dict) else site.get('district')
                        beneficiary_type = getattr(site, 'target_beneficiary_type', None) if not isinstance(site, dict) else site.get('target_beneficiary_type')
                        households = getattr(site, 'number_of_households', None) if not isinstance(site, dict) else site.get('number_of_households')
                        latitude = getattr(site, 'latitude', None) if not isinstance(site, dict) else site.get('latitude')
                        longitude = getattr(site, 'longitude', None) if not isinstance(site, dict) else site.get('longitude')
                        if (
                            not str(site_name or '').strip()
                            or not str(district or '').strip()
                            or not str(beneficiary_type or '').strip()
                            or households in (None, '', 0)
                        ):
                            site_errors[idx] = 'Site name, district, primary beneficiary type, and number of households are required before submitting.'
                            continue
                        if latitude in (None, '') or longitude in (None, ''):
                            site_errors[idx] = 'Latitude and longitude are required before submitting.'
                            continue
                        if not point_in_lesotho(Decimal(str(longitude)), Decimal(str(latitude))):
                            site_errors[idx] = 'Site coordinates must fall within Lesotho.'
                            continue
                        if is_lot_wise:
                            site_lot = getattr(site, 'lot', None) if not isinstance(site, dict) else site.get('lot')
                            site_lot_id = getattr(site_lot, 'id', None)
                            if site_lot_id is None:
                                site_errors[idx] = 'Select which lot this site belongs to.'
                            elif allowed_site_lot_ids and site_lot_id not in allowed_site_lot_ids:
                                site_errors[idx] = 'This site references a lot you did not declare at the EOI stage.'
                    if site_errors:
                        errors['sites'] = site_errors

                if bid_status == BidStatus.SUBMITTED:
                    request = self.context.get('request')
                    if request and hasattr(request, 'user') and request.user.role == UserRole.VENDOR:
                        latest_prequal = (
                            VendorPrequalification.objects.filter(vendor_id=str(request.user.id))
                            .order_by('-submitted_at', '-id')
                            .first()
                        )
                        if (
                            latest_prequal
                            and latest_prequal.status == PrequalificationStatus.APPROVED
                            and latest_prequal.tech_tier
                        ):
                            approved_match = re.search(r'\d+', str(latest_prequal.tech_tier))
                            bid_tier_raw = attrs.get('tech_tier', getattr(instance, 'tech_tier', '') if instance else '')
                            bid_match = re.search(r'\d+', str(bid_tier_raw))
                            if approved_match and bid_match:
                                approved_num = int(approved_match.group())
                                bid_num = int(bid_match.group())
                                if bid_num > approved_num:
                                    errors['tech_tier'] = f'Technical tier cannot exceed your approved pre-qualification tier (Tier {approved_num}).'

                    # Required document files (Technical Proposal, BOQ, Financial Proposal,
                    # etc.) are no longer hardcoded here — see the unified required-documents
                    # check below, driven entirely by TenderRequiredDocument.

        if is_eoi:
            attrs['technical_proposal'] = ''
            attrs['financial_proposal'] = ''
        if not attrs.get('boq_details') and attrs.get('boq_items'):
            attrs['boq_details'] = attrs['boq_items']

        # ---- Required documents (fully configurable per tender + bid stage) ----
        # Every required document — whether it maps to a structured TenderBid file field
        # (field_key set, e.g. Technical Proposal, BOQ, Financial Proposal, the 4 EOI
        # credential files) or is a fully custom name the RBF Admin typed in — is enforced
        # from a single source of truth: TenderRequiredDocument rows configured on the
        # tender. A tender with no rows for a stage requires no documents for that stage.
        if bid_status == BidStatus.SUBMITTED and tender is not None:
            required_docs = TenderRequiredDocument.objects.filter(
                tender=tender,
                bid_stage__in=(stage_key, BidStage.COMBINED),
            )
            if required_docs:
                existing_custom = {}
                for d in (attrs.get('custom_documents') or []):
                    if isinstance(d, dict) and d.get('name'):
                        existing_custom[str(d['name']).strip()] = d
                if instance is not None:
                    for d in (instance.custom_documents or []):
                        if isinstance(d, dict) and d.get('name'):
                            existing_custom.setdefault(str(d['name']).strip(), d)

                for doc in required_docs:
                    if doc.field_key:
                        file_obj = attrs.get(doc.field_key, getattr(instance, doc.field_key, None) if instance else None)
                        if not file_obj:
                            errors[doc.field_key] = f'{doc.name} document is required for this stage.'
                    else:
                        uploaded = existing_custom.get(str(doc.name).strip())
                        has_file = bool(uploaded and (uploaded.get('file_url') or uploaded.get('file_name')))
                        if not has_file:
                            errors[f'custom_documents.{doc.name}'] = f'{doc.name} is required for this stage.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        sites_data = validated_data.pop('sites', [])
        docs = validated_data.pop('custom_documents', None)
        lot_offers_data = validated_data.pop('lot_offers', None)
        bid = super().create(validated_data)
        if sites_data:
            TenderBidSite.objects.bulk_create(
                [TenderBidSite(bid=bid, **site) for site in sites_data]
            )
        self._save_custom_documents(bid, docs)
        self._save_lot_offers(bid, lot_offers_data)
        return bid

    def update(self, instance, validated_data):
        sites_data = validated_data.pop('sites', None)
        docs = validated_data.pop('custom_documents', None)
        lot_offers_data = validated_data.pop('lot_offers', None)
        bid = super().update(instance, validated_data)
        if sites_data is not None:
            bid.sites.all().delete()
            if sites_data:
                TenderBidSite.objects.bulk_create(
                    [TenderBidSite(bid=bid, **site) for site in sites_data]
                )
        self._save_custom_documents(bid, docs)
        self._save_lot_offers(bid, lot_offers_data)
        return bid

    def _save_lot_offers(self, bid, lot_offers_data):
        if lot_offers_data is None:
            return
        bid.lot_offers.all().delete()
        if not isinstance(lot_offers_data, list):
            return
        rows = []
        for offer in lot_offers_data:
            if not isinstance(offer, dict):
                continue
            lot_id = offer.get('lot') or offer.get('lot_id')
            bid_amount = offer.get('bid_amount')
            if not lot_id or bid_amount in (None, ''):
                continue
            try:
                lot = TenderLot.objects.get(id=lot_id, tender_id=bid.tender_id)
            except (TenderLot.DoesNotExist, ValueError, TypeError):
                continue
            rows.append(TenderBidLotOffer(
                bid=bid,
                lot=lot,
                bid_amount=bid_amount,
                subsidy_requested=offer.get('subsidy_requested') or None,
                boq_items=offer.get('boq_items') or [],
            ))
        if rows:
            TenderBidLotOffer.objects.bulk_create(rows)

    def _save_custom_documents(self, instance, docs):
        if docs is None:
            return
        request = self.context.get('request')
        files_by_name = {}
        if request is not None:
            for uploaded in request.FILES.getlist('custom_documents_files'):
                files_by_name[uploaded.name] = uploaded
        existing = {
            (d.get('file_name') or d.get('name')): d
            for d in (instance.custom_documents or [])
        }
        saved = []
        for doc in docs if isinstance(docs, list) else []:
            if not isinstance(doc, dict):
                continue
            name = str(doc.get('name') or '').strip()
            if not name:
                continue
            fname = str(doc.get('file_name') or '').strip()
            uploaded = files_by_name.get(fname) if fname else None
            file_url = None
            if uploaded is not None:
                path = default_storage.save(
                    f'custom_documents/{os.path.basename(uploaded.name)}', uploaded
                )
                file_url = f'/media/{path}'
            elif fname and existing.get(fname, {}).get('file_url'):
                file_url = existing[fname]['file_url']
            saved.append({
                'name': name,
                'expected_type': str(doc.get('expected_type') or '').strip(),
                'file_name': uploaded.name if uploaded else fname,
                'file_url': file_url,
            })
        instance.custom_documents = saved
        instance.save(update_fields=['custom_documents', 'updated_at'])

    def to_representation(self, instance):
        data = super().to_representation(instance)
        system_configuration = instance.system_configuration or {}
        data['boq_details'] = data.get('boq_details') or data.get('boq_items') or []
        data['energy_target'] = data.get('energy_target_kwh_month')
        data['warranty_period'] = data.get('warranty_period_months')
        data['om_plan_document'] = data.get('om_plan_file')
        data['technical_summary'] = data.get('technical_proposal')
        data['financial_summary'] = data.get('financial_proposal')
        data['service_tier'] = data.get('tech_tier')
        data['paygo_offered'] = data.get('offer_paygo')
        data['min_daily_payment_lsl'] = data.get('daily_payment_amount_lsl')
        data['local_technicians_count'] = data.get('local_technicians_to_be_trained')
        data['warranty_months'] = data.get('warranty_period_months')
        data['gender_inclusion_target'] = data.get('female_target_pct')
        data['vulnerable_group_target'] = data.get('vulnerable_target_pct')
        data['low_income_target'] = data.get('low_income_target_pct')
        data['aftersales_description'] = system_configuration.get('aftersales_description', '')
        data['stage'] = bid_stage_label(self._resolved_stage(instance))
        data['device_brand'] = system_configuration.get('device_brand', '')
        data['device_model'] = system_configuration.get('device_model', '')
        data['rated_power_w'] = system_configuration.get('rated_power_w')
        data['battery_capacity_wh'] = system_configuration.get('battery_capacity_wh')
        data['pv_panel_size_w'] = system_configuration.get('pv_panel_size_w')
        data['inverter_type'] = system_configuration.get('inverter_type', '')
        data['co_financing_amount'] = system_configuration.get('co_financing_amount_lsl')
        # One currency applies to the whole bid (not per lot line), so the same
        # base-currency rate converts both the top-level bid_amount and every lot offer.
        base_currency_rate = instance.tender.currency_rate_to_base(instance.bid_currency)
        data['bid_amount_base_currency'] = (
            str(Decimal(str(instance.bid_amount)) * base_currency_rate) if instance.bid_amount is not None else None
        )
        data['lot_offers'] = [
            {
                'lot': str(offer.lot_id),
                'lot_name': offer.lot.name,
                'bid_amount': str(offer.bid_amount),
                'bid_amount_base_currency': str(Decimal(str(offer.bid_amount)) * base_currency_rate),
                'subsidy_requested': str(offer.subsidy_requested) if offer.subsidy_requested is not None else None,
                'boq_items': offer.boq_items or [],
            }
            for offer in instance.lot_offers.select_related('lot').all()
        ]
        request = self.context.get('request')
        if request:
            file_fields = [
                'proposal_file',
                'technical_proposal_file',
                'financial_proposal_file',
                'boq_file',
                'gender_action_plan_file',
                'implementation_plan_file',
                'om_plan_file',
                'reporting_templates_file',
                'distribution_map_file',
                'company_credentials_file',
                'financial_standing_file',
                'technical_experience_file',
                'track_record_file',
            ]
            for field in file_fields:
                if data.get(field):
                    data[field] = request.build_absolute_uri(data[field])
            if data.get('om_plan_document'):
                data['om_plan_document'] = request.build_absolute_uri(data['om_plan_document'])
            if data.get('custom_documents'):
                for _cd in data['custom_documents']:
                    if _cd.get('file_url'):
                        _cd['file_url'] = request.build_absolute_uri(_cd['file_url'])

        # Seal financial pricing for evaluators until technical clearance passes.
        if financial_bid_is_sealed(instance, request):
            for field in ('bid_amount', 'subsidy_requested', 'financial_proposal_file', 'financial_proposal', 'bid_amount_base_currency'):
                data[field] = None
            data['lot_offers'] = []
            data['financial_sealed'] = True
        return data

    def get_stage_key(self, obj):
        return self._resolved_stage(obj)

    def get_stage_badge(self, obj):
        return bid_stage_label(self._resolved_stage(obj))

    def get_stage_two_ready(self, obj):
        return bool(
            TenderBid.objects.filter(
                tender=obj.tender,
                vendor_id=obj.vendor_id,
                bid_stage__in=(BidStage.TECHNICAL, BidStage.COMBINED),
                status=BidStatus.DRAFT,
            ).exclude(id=obj.id).exists()
        ) or bool(
            TenderBid.objects.filter(
                tender=obj.tender,
                vendor_id=obj.vendor_id,
                stage_two_unlocked=True,
                status=BidStatus.DRAFT,
                stage_two_source_bid__status=BidStatus.ACCEPTED,
            ).exclude(id=obj.id).exists()
        )

    def get_tender_procurement_workflow(self, obj):
        return getattr(obj.tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL) if obj.tender_id else ProcurementWorkflow.SEQUENTIAL

    def get_tender_skips_eoi_stage(self, obj):
        return bool(obj.tender_id and obj.tender.linked_eoi_tender_id)

    def get_financial_stage_open(self, obj):
        return has_financial_stage_access(obj)

    def get_technology_type(self, obj):
        # Prefer the technology type selected in the bid system configuration
        if isinstance(obj.system_configuration, dict) and obj.system_configuration.get('technology_type'):
            return normalize_technology_type(obj.system_configuration['technology_type'])
        
        # Fallback to tender's first technology type
        technology_types = obj.tender.technology_types if obj.tender_id else []
        if not technology_types:
            return None
        return normalize_technology_type(technology_types[0]) or technology_types[0]

    def get_tender_technology_types(self, obj):
        return obj.tender.technology_types if obj.tender_id else []

    def _resolved_required_documents(self, obj):
        """Required documents for this bid's stage, driven entirely by the tender's
        configured TenderRequiredDocument rows (both structured field_key-bound documents
        and fully custom ones)."""
        if not obj.tender_id:
            return []
        stage = self._resolved_stage(obj)
        docs = TenderRequiredDocument.objects.filter(
            tender_id=obj.tender_id,
            bid_stage__in=(stage, BidStage.COMBINED),
        )
        custom_by_name = {}
        for d in (obj.custom_documents or []):
            if isinstance(d, dict) and d.get('name'):
                custom_by_name[str(d['name']).strip()] = d
        results = []
        for doc in docs:
            if doc.field_key:
                results.append({
                    'field': doc.field_key,
                    'label': doc.name,
                    'required': True,
                    'uploaded': bool(getattr(obj, doc.field_key, None)),
                })
            else:
                uploaded_doc = custom_by_name.get(str(doc.name).strip())
                has_file = bool(uploaded_doc and (uploaded_doc.get('file_url') or uploaded_doc.get('file_name')))
                results.append({
                    'field': f'custom_documents.{doc.name}',
                    'label': doc.name,
                    'required': True,
                    'uploaded': has_file,
                })
        return results

    def get_document_requirements(self, obj):
        return self._resolved_required_documents(obj)

    def get_document_counts(self, obj):
        docs = self._resolved_required_documents(obj)
        uploaded = sum(1 for d in docs if d['uploaded'])
        return {'uploaded': uploaded, 'required': len(docs)}

    def _stage_deadline(self, obj):
        stage = self._resolved_stage(obj)
        if stage == BidStage.FINANCIAL:
            deadline = getattr(obj.tender, 'financial_deadline', None) if obj.tender_id else None
        elif stage in (BidStage.TECHNICAL, BidStage.COMBINED):
            deadline = getattr(obj.tender, 'technical_deadline', None) if obj.tender_id else None
        else:
            deadline = getattr(obj.tender, 'eoi_deadline', None) if obj.tender_id else None
        return deadline or (obj.tender.master_deadline() if obj.tender_id else None)

    def get_deadline(self, obj):
        return self._stage_deadline(obj)

    def get_deadline_passed(self, obj):
        deadline = self._stage_deadline(obj)
        return bool(deadline and timezone.now() > deadline)

    def get_deadline_countdown_seconds(self, obj):
        deadline = self._stage_deadline(obj)
        if not deadline:
            return None
        remaining = int((deadline - timezone.now()).total_seconds())
        return max(0, remaining)

    def get_is_locked(self, obj):
        return obj.status != BidStatus.DRAFT

    def get_version_history(self, obj):
        history_qs = (
            TenderBid.objects.filter(tender=obj.tender, vendor_id=obj.vendor_id)
            .order_by('-version_number', '-updated_at')
            .only('id', 'version_number', 'status', 'updated_at', 'submitted_at')
        )
        return [
            {
                'id': str(item.id),
                'version_number': item.version_number,
                'status': item.status,
                'updated_at': item.updated_at,
                'submitted_at': item.submitted_at,
            }
            for item in history_qs
        ]

    def _stage_two_scored_evaluations(self, obj):
        if self.get_stage_key(obj) not in (BidStage.TECHNICAL, BidStage.COMBINED):
            return []
        evaluations = getattr(obj, '_prefetched_objects_cache', {}).get('evaluations')
        if evaluations is None:
            evaluations = obj.evaluations.select_related('evaluator').all()
        return [ev for ev in evaluations if ev.status == EvaluationStatus.SCORED]

    def get_evaluation_status(self, obj):
        scored_evaluations = self._stage_two_scored_evaluations(obj)
        if not scored_evaluations:
            return 'pending'
        financial_evaluations = [ev for ev in scored_evaluations if ev.stage == EvaluationStage.FINANCIAL]
        if financial_evaluations:
            return 'evaluated'
        technical_evaluations = [ev for ev in scored_evaluations if ev.stage == EvaluationStage.TECHNICAL]
        if not technical_evaluations:
            return 'pending'
        # A committee's technical decision only counts once a majority of the tender's
        # assigned Evaluation Committee roster have scored it (a Super Admin score is an
        # override and always counts). Below that, the bid stays 'pending'.
        has_admin_override = any(getattr(getattr(ev, 'evaluator', None), 'role', None) == UserRole.ADMIN for ev in technical_evaluations)
        assigned_count = TenderEvaluationCommitteeMember.objects.filter(tender_id=obj.tender_id).count()
        quorum = ceil(assigned_count / 2) if assigned_count else 0
        if has_admin_override or not quorum or len(technical_evaluations) >= quorum:
            return 'technical_scored'
        return 'pending'

    def get_technical_score_total(self, obj):
        scored_evaluations = [
            ev for ev in self._stage_two_scored_evaluations(obj)
            if ev.stage == EvaluationStage.TECHNICAL
        ]
        if not scored_evaluations:
            return None
        totals = [
            (ev.technical_score or 0)
            + (ev.feasibility_score or 0)
            + (ev.om_score or 0)
            + (ev.kpi_score or 0)
            + (ev.gender_score or 0)
            + (ev.environmental_score or 0)
            for ev in scored_evaluations
        ]
        return round(sum(totals) / len(totals))

    def get_financial_score_total(self, obj):
        scored_evaluations = [
            ev for ev in self._stage_two_scored_evaluations(obj)
            if ev.stage == EvaluationStage.FINANCIAL
        ]
        if not scored_evaluations:
            return None

        def _normalized(ev):
            if ev.financial_score_auto_calculated:
                return ev.financial_score or 0
            return round(((ev.financial_score or 0) / 30) * 100)

        totals = [_normalized(ev) for ev in scored_evaluations]
        return round(sum(totals) / len(totals))

    def get_has_challenge(self, obj):
        return obj.challenges.filter(
            status__in=[ChallengeStatus.SUBMITTED, ChallengeStatus.UNDER_REVIEW]
        ).exists()


class TenderBidEvaluationSerializer(serializers.ModelSerializer):
    """An Evaluation Committee member's score for one bid, at one stage.

    A committee member submits a TECHNICAL-stage row first (the full quality rubric,
    below), then — once the bid clears the technical threshold with quorum — a
    separate FINANCIAL-stage row per bid (or per lot, for a lot-wise tender). The
    financial score is always computed server-side from the price formula
    (TenderBidEvaluationViewSet._apply_auto_financial_score) before this serializer
    ever sees it; it is never manually typed.
    """
    evaluator_username = serializers.CharField(source='evaluator.username', read_only=True)
    evaluator_role = serializers.CharField(source='evaluator.role', read_only=True)
    justifications = serializers.JSONField(required=False)

    def _score_limits(self) -> dict:
        """Super-Admin-configurable technical rubric (PlatformConfiguration.technical_scoring_criteria),
        plus the legacy 'inclusivity_score' field which stays pinned at 0 (unused, not configurable)."""
        config = PlatformConfiguration.objects.order_by('id').first()
        limits = config.technical_score_limits() if config else {
            c['key']: c['max_score'] for c in PlatformConfiguration().technical_scoring_criteria_normalized()
        }
        return {**limits, 'inclusivity_score': 0}

    def _score_fields(self) -> tuple:
        return tuple(key for key in self._score_limits() if key != 'inclusivity_score')

    class Meta:
        model = TenderBidEvaluation
        fields = [
            'id',
            'bid',
            'lot',
            'stage',
            'evaluator',
            'evaluator_username',
            'evaluator_role',
            'status',
            'submission_status',
            'submitted_at',
            'justifications',
            'technical_score',
            'financial_score',
            'financial_score_auto_calculated',
            'feasibility_score',
            'kpi_score',
            'gender_score',
            'environmental_score',
            'om_score',
            'inclusivity_score',
            'total_score',
            'comments',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'total_score', 'created_at', 'updated_at', 'evaluator_username', 'evaluator_role', 'submitted_at',
        ]

    def _stage(self, attrs):
        instance = getattr(self, 'instance', None)
        return attrs.get('stage', getattr(instance, 'stage', EvaluationStage.TECHNICAL))

    def _submission_status(self, attrs):
        instance = getattr(self, 'instance', None)
        return attrs.get('submission_status', getattr(instance, 'submission_status', EvaluationSubmissionStatus.DRAFT) if instance else EvaluationSubmissionStatus.DRAFT)

    def _technical_total(self, instance, attrs):
        return sum(
            int(attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0) or 0)
            for field_name in self._score_fields()
        )

    def validate(self, attrs):
        stage = self._stage(attrs)
        instance = getattr(self, 'instance', None)

        if stage == EvaluationStage.TECHNICAL:
            field_errors = {}
            for field_name, limit in self._score_limits().items():
                score = attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0)
                if score is None:
                    score = 0
                if score < 0 or score > limit:
                    field_errors[field_name] = f'Score must be between 0 and {limit}.'
            if field_errors:
                raise serializers.ValidationError(field_errors)
            financial_score = attrs.get('financial_score', instance.financial_score if instance else 0)
            if financial_score not in (None, 0):
                raise serializers.ValidationError({'financial_score': 'Financial scoring happens separately, after technical evaluation clears.'})
            # A submitted technical evaluation must justify every criterion — production
            # e-tendering practice requires audible rationale for each mark.
            if self._submission_status(attrs) == EvaluationSubmissionStatus.SUBMITTED:
                justifications = attrs.get('justifications', getattr(instance, 'justifications', None) if instance else None) or {}
                if not isinstance(justifications, dict):
                    raise serializers.ValidationError({'justifications': 'Justifications must be an object keyed by criterion.'})
                missing = [key for key in self._score_fields() if not str(justifications.get(key) or '').strip()]
                if missing:
                    raise serializers.ValidationError({
                        'justifications': 'A rationale is required for every criterion before submitting. Missing: ' + ', '.join(missing) + '.',
                    })
        else:
            # Financial-stage rows carry only the auto-calculated price score — no
            # manual quality re-scoring at this stage (that already happened above).
            for field_name in self._score_fields() + ('inclusivity_score',):
                value = attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0)
                if value not in (None, 0):
                    raise serializers.ValidationError({field_name: 'This score is not used at the financial stage.'})
        return attrs

    def _persist_submission_timestamps(self, validated_data):
        submission_status = validated_data.get('submission_status', EvaluationSubmissionStatus.DRAFT)
        if submission_status == EvaluationSubmissionStatus.SUBMITTED:
            validated_data.setdefault('submitted_at', timezone.now())
        else:
            validated_data['submitted_at'] = None
        return validated_data

    def create(self, validated_data):
        validated_data['total_score'] = self._technical_total(None, validated_data) if validated_data.get('stage') == EvaluationStage.TECHNICAL else int(validated_data.get('financial_score') or 0)
        validated_data['status'] = EvaluationStatus.SCORED
        self._persist_submission_timestamps(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        stage = validated_data.get('stage', instance.stage)
        validated_data['total_score'] = self._technical_total(instance, validated_data) if stage == EvaluationStage.TECHNICAL else int(validated_data.get('financial_score', instance.financial_score) or 0)
        validated_data['status'] = EvaluationStatus.SCORED
        self._persist_submission_timestamps(validated_data)
        return super().update(instance, validated_data)


class TenderAwardRecommendationSerializer(serializers.ModelSerializer):
    """An Evaluation Committee member's suggested winner, exposed read-only to the
    RBF/committee. Creation/updates happen through the viewset (upsert per member per
    decision unit), not the serializer."""
    suggested_by_name = serializers.CharField(source='suggested_by.full_name', read_only=True, default='')
    bid_vendor_name = serializers.CharField(source='bid.vendor_name', read_only=True, default='')
    lot_name = serializers.CharField(source='lot.name', read_only=True, default='')

    class Meta:
        model = TenderAwardRecommendation
        fields = [
            'id', 'tender', 'lot', 'lot_name', 'bid', 'bid_vendor_name',
            'suggested_by', 'suggested_by_name', 'rationale', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'tender', 'lot_name', 'bid_vendor_name', 'suggested_by_name',
            'created_at', 'updated_at',
        ]


class TenderContractSerializer(serializers.ModelSerializer):
    ANNEX_SOURCE_FIELDS = {
        'annex_a_file': ('gender_action_plan_file',),
        'annex_b_file': ('implementation_plan_file',),
        'annex_c_file': ('financial_proposal_file',),
        'annex_d_file': ('reporting_templates_file', 'milestone_payment_schedule_file', 'schedule_file'),
        'annex_e_file': ('technical_proposal_file',),
    }
    lot_name = serializers.CharField(source='lot.name', read_only=True, default=None)

    class Meta:
        model = TenderContract
        fields = '__all__'
        read_only_fields = [
            'id',
            'reference_number',
            'generated_at',
            'signed_at',
            'approved_at',
            'approved_by',
            'milestone_plan_id',
            'project_id',
        ]

    def _resolve_bid(self, instance):
        if instance.bid_id:
            return instance.bid
        return (
            TenderBid.objects.filter(tender=instance.tender, vendor_id=instance.vendor_id)
            .order_by('-version_number', '-submitted_at')
            .first()
        )

    def _resolve_annex_value(self, instance, annex_field):
        current_value = getattr(instance, annex_field, None)
        if current_value:
            return getattr(current_value, 'url', None) or str(current_value)
        bid = self._resolve_bid(instance)
        for source_field in self.ANNEX_SOURCE_FIELDS.get(annex_field, ()):
            source = bid if bid is not None and hasattr(bid, source_field) else instance.tender
            file_obj = getattr(source, source_field, None)
            if file_obj:
                return getattr(file_obj, 'url', None) or str(file_obj)
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and data.get('signed_file'):
            data['signed_file'] = request.build_absolute_uri(data['signed_file'])
        if request and data.get('generated_file'):
            data['generated_file'] = request.build_absolute_uri(data['generated_file'])
        for annex_field in ('annex_a_file', 'annex_b_file', 'annex_c_file', 'annex_d_file', 'annex_e_file'):
            resolved_value = self._resolve_annex_value(instance, annex_field)
            if request and resolved_value:
                data[annex_field] = request.build_absolute_uri(resolved_value)
            else:
                data[annex_field] = resolved_value
        return data


class ProjectAssignmentSerializer(serializers.Serializer):
    PROJECT_DURATION_CHOICES = ((6, 6), (12, 12), (18, 18))

    project_duration_months = serializers.ChoiceField(choices=PROJECT_DURATION_CHOICES)
    installation_target = serializers.IntegerField(min_value=1)
    technology_type = serializers.CharField()
    energy_output_target_kwh = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    district_zone = serializers.CharField(allow_blank=False, required=False)
    district_zones = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        allow_empty=False,
    )
    verification_method = serializers.ChoiceField(choices=VerificationMethod.choices)
    female_target_pct = serializers.IntegerField(min_value=50, max_value=100, required=False, default=50)
    vulnerable_target_pct = serializers.IntegerField(min_value=30, max_value=100, required=False, default=30)
    low_income_target_pct = serializers.IntegerField(min_value=60, max_value=100, required=False, default=60)
    start_date = serializers.DateField(required=False, allow_null=True, input_formats=['%Y-%m-%d'])
    # Milestone plan — disbursement share of the contract value per milestone
    # (must total 100) and the verified-installation checklist thresholds.
    # Milestone 1 is Mobilization, which carries no installation target, so it is
    # legitimately 0% when the vendor is paid entirely on delivery and performance.
    # Milestones 2 and 3 are installation-linked ("N% Implementation" / "Final") and
    # must disburse something. The 100% total is enforced separately in validate().
    m1_disbursement_pct = serializers.IntegerField(min_value=0, max_value=98, required=False, default=20)
    m2_disbursement_pct = serializers.IntegerField(min_value=1, max_value=98, required=False, default=50)
    m3_disbursement_pct = serializers.IntegerField(min_value=1, max_value=98, required=False, default=30)
    m2_installation_required_pct = serializers.IntegerField(min_value=1, max_value=100, required=False)
    m3_installation_required_pct = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def validate_technology_type(self, value):
        normalized = normalize_technology_type(value)
        if not normalized:
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')

        contract = self.context.get('contract')
        tender = getattr(contract, 'tender', None) if contract is not None else None
        tender_technologies = []
        if tender is not None:
            if isinstance(getattr(tender, 'technology_types', None), list):
                for tech in tender.technology_types:
                    normalized_tech = normalize_technology_type(tech)
                    if normalized_tech and normalized_tech not in tender_technologies:
                        tender_technologies.append(normalized_tech)
            if not tender_technologies:
                fallback = normalize_technology_type(getattr(tender, 'category', ''))
                if fallback:
                    tender_technologies.append(fallback)
        if tender_technologies and normalized not in tender_technologies:
            allowed = ', '.join(tender_technologies)
            raise serializers.ValidationError(f'Technology type must be one of tender technologies: {allowed}.')

        return normalized

    def validate(self, attrs):
        district_values = attrs.get('district_zones')
        if not district_values:
            raw_district = str(attrs.get('district_zone') or '').strip()
            if raw_district:
                district_values = [raw_district]
        normalized_districts = []
        for value in district_values or []:
            cleaned = str(value or '').strip()
            if cleaned and cleaned not in normalized_districts:
                normalized_districts.append(cleaned)
        if not normalized_districts:
            raise serializers.ValidationError({'district_zones': 'Select at least one district.'})
        attrs['district_zones'] = normalized_districts
        attrs['district_zone'] = normalized_districts[0]

        disbursement_total = attrs['m1_disbursement_pct'] + attrs['m2_disbursement_pct'] + attrs['m3_disbursement_pct']
        if disbursement_total != 100:
            raise serializers.ValidationError({
                'milestone_disbursement_pct': f'Milestone disbursement percentages must total 100% (currently {disbursement_total}%).',
            })
        platform_config = PlatformConfiguration.objects.order_by('id').first() or PlatformConfiguration()
        attrs.setdefault('m2_installation_required_pct', platform_config.m2_verification_required_pct or 80)
        attrs.setdefault('m3_installation_required_pct', platform_config.m3_verification_required_pct or 100)
        if attrs['m3_installation_required_pct'] < attrs['m2_installation_required_pct']:
            raise serializers.ValidationError({
                'm3_installation_required_pct': 'Milestone 3 installation requirement cannot be lower than Milestone 2.',
            })

        contract = self.context.get('contract')
        if contract is None:
            return attrs
        if contract.status != ContractStatus.APPROVED:
            raise serializers.ValidationError('Contract must have status = approved before assigning milestones.')
        if contract.project_id or getattr(contract, 'projects', None) and contract.projects.exists():
            raise serializers.ValidationError('This contract has already been assigned to a project.')
        vendor = User.objects.filter(id=contract.vendor_id).first()
        if vendor is None:
            raise serializers.ValidationError({'vendor_id': 'Awarded vendor could not be found.'})
        attrs['vendor'] = vendor
        return attrs


class TenderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tender list views"""
    bid_count = serializers.SerializerMethodField()
    skips_eoi_stage = serializers.SerializerMethodField()
    invited_vendor_count = serializers.SerializerMethodField()
    linked_tender_count = serializers.SerializerMethodField()
    lot_count = serializers.SerializerMethodField()
    awarded_lot_count = serializers.SerializerMethodField()

    def get_bid_count(self, obj):
        return obj.bids.count()

    def get_skips_eoi_stage(self, obj):
        return bool(obj.linked_eoi_tender_id)

    def get_invited_vendor_count(self, obj):
        return obj.invited_vendors.count()

    def get_linked_tender_count(self, obj):
        return obj.linked_tenders.count()

    def get_lot_count(self, obj):
        return obj.lots.count()

    def get_awarded_lot_count(self, obj):
        return obj.lots.exclude(awarded_vendor_id='').count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == UserRole.VENDOR and instance.budget_disclosure != BudgetDisclosure.PUBLISHED:
            data.pop('budget', None)
        return data

    class Meta:
        model = Tender
        fields = [
            'id', 'reference_number', 'name', 'department', 'category',
            'status', 'deadline', 'budget', 'published_at', 'is_verified',
            'awarded_vendor_name', 'bid_count', 'created_at',
            'technology_types', 'target_districts', 'procurement_method',
            'application_type', 'tender_security_required',
            'procurement_workflow', 'eoi_deadline', 'technical_deadline', 'financial_deadline',
            'technical_weight', 'financial_weight', 'technical_threshold',
            'publish_approval_status', 'publish_approval_requested_at',
            'publish_approval_reviewed_at', 'publish_approval_reviewed_by', 'publish_approval_notes',
            'evaluation_comment', 'evaluation_comment_author', 'evaluation_comment_updated_at',
            'is_eoi_invite_only', 'linked_eoi_tender', 'skips_eoi_stage', 'invited_vendor_count',
            'linked_tender_count', 'lot_count', 'awarded_lot_count',
        ]


class TenderRequiredDocumentSerializer(serializers.ModelSerializer):
    bid_stage_label = serializers.CharField(source='get_bid_stage_display', read_only=True)

    class Meta:
        model = TenderRequiredDocument
        fields = ['id', 'name', 'expected_type', 'bid_stage', 'bid_stage_label', 'field_key', 'position']
        read_only_fields = ['id']


class TenderBoqItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenderBoqItem
        fields = ['id', 'description', 'unit', 'quantity', 'position']
        read_only_fields = ['id']


def intent_award_proposal_visible(serializer):
    """Whether the caller may see a *queued* intent-to-award proposal.

    A pending request names the proposed winner before the Super Admin has approved it
    and before any bidder notice has gone out, so it is embargoed: only the RBF and the
    Super Admin may read it. Tenders are readable publicly and by every vendor, and
    letting those callers see it would publish the outcome of an unapproved decision and
    break the standstill sequence. Deny-by-default — a serializer built without a
    request in context (internal/background use) sees nothing.
    """
    request = serializer.context.get('request')
    user = getattr(request, 'user', None) if request is not None else None
    return getattr(user, 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}


class IntentToAwardRequestSerializer(serializers.ModelSerializer):
    """One RBF proposal to issue an intent to award, awaiting (or carrying) a Super Admin
    decision. Deliberately does not nest `tender` — the request is always returned
    alongside the tender it belongs to, and nesting would recurse through
    TenderSerializer."""
    lot_id = serializers.UUIDField(source='lot.id', read_only=True, default=None)
    lot_name = serializers.CharField(source='lot.name', read_only=True, default='')
    tender_reference_number = serializers.CharField(source='tender.reference_number', read_only=True)
    tender_name = serializers.CharField(source='tender.name', read_only=True)
    bid_id = serializers.UUIDField(read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = IntentToAwardRequest
        fields = [
            'id', 'tender', 'tender_reference_number', 'tender_name',
            'lot', 'lot_id', 'lot_name', 'bid', 'bid_id',
            'proposed_vendor_id', 'proposed_vendor_name',
            'ec_agreed_bid_id', 'ec_consensus', 'ec_override_reason',
            'status', 'status_label', 'notes',
            'requested_by', 'requested_by_name', 'requested_at', 'from_challenge',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at',
        ]
        read_only_fields = fields


class TenderLotSerializer(serializers.ModelSerializer):
    intent_to_award_bid_id = serializers.SerializerMethodField()
    boq_items = TenderBoqItemSerializer(source='boq_template_items', many=True, read_only=True)
    # Set while this lot's intent to award is queued for Super Admin approval. Lets the
    # Award panel grey out the row and show "Awaiting Super Admin approval" without a
    # second round-trip.
    pending_intent_award_request = serializers.SerializerMethodField()

    class Meta:
        model = TenderLot
        fields = [
            'id', 'name', 'description', 'technology_types', 'target_districts',
            'estimated_installation_target', 'budget', 'position', 'boq_items',
            'awarded_vendor_id', 'awarded_vendor_name',
            'intent_to_award_bid_id', 'intent_to_award_at', 'cooling_off_until', 'awarded_at',
            'pending_intent_award_request',
        ]
        read_only_fields = [
            'id', 'awarded_vendor_id', 'awarded_vendor_name',
            'intent_to_award_bid_id', 'intent_to_award_at', 'cooling_off_until', 'awarded_at',
            'pending_intent_award_request',
        ]

    def get_intent_to_award_bid_id(self, obj):
        return str(obj.intent_to_award_bid_id) if obj.intent_to_award_bid_id is not None else None

    def get_pending_intent_award_request(self, obj):
        if not intent_award_proposal_visible(self):
            return None
        pending = getattr(obj, 'pending_intent_award_requests', None)
        if pending is None:
            pending = list(
                obj.intent_award_requests
                .filter(status=IntentAwardRequestStatus.PENDING)
                .select_related('lot', 'bid')
            )
            obj.pending_intent_award_requests = pending
        if not pending:
            return None
        return IntentToAwardRequestSerializer(pending[0], context=self.context).data


class TenderEvaluationCommitteeMemberSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.full_name', read_only=True)
    member_email = serializers.CharField(source='member.email', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.full_name', read_only=True, default='')

    class Meta:
        model = TenderEvaluationCommitteeMember
        fields = ['id', 'member', 'member_name', 'member_email', 'assigned_by', 'assigned_by_name', 'assigned_at']
        read_only_fields = ['id', 'assigned_by', 'assigned_by_name', 'assigned_at']


class TenderInvitedVendorSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.full_name', read_only=True)
    vendor_email = serializers.CharField(source='vendor.email', read_only=True)
    vendor_organization_name = serializers.CharField(source='vendor.organization_name', read_only=True, default='')
    invited_by_name = serializers.CharField(source='invited_by.full_name', read_only=True, default='')

    class Meta:
        model = TenderInvitedVendor
        fields = ['id', 'vendor', 'vendor_name', 'vendor_email', 'vendor_organization_name', 'invited_by', 'invited_by_name', 'invited_at']
        read_only_fields = ['id', 'invited_by', 'invited_by_name', 'invited_at']


class TenderSerializer(serializers.ModelSerializer):
    reference_number = serializers.CharField(required=False, allow_blank=True, default='')
    bid_count = serializers.SerializerMethodField()
    required_documents = serializers.JSONField(required=False, allow_null=True, write_only=True)
    lots = serializers.JSONField(required=False, allow_null=True, write_only=True)
    # Tender-wide BOQ design — only meaningful for a non-lot-wise tender. A lot-wise
    # tender's BOQ is designed per lot instead, nested inside each entry of `lots`.
    boq_items = serializers.JSONField(required=False, allow_null=True, write_only=True)
    skips_eoi_stage = serializers.SerializerMethodField()
    linked_eoi_tender_name = serializers.CharField(source='linked_eoi_tender.name', read_only=True, default='')
    linked_tenders_summary = serializers.SerializerMethodField()
    invited_vendor_count = serializers.SerializerMethodField()
    # Every intent-to-award request still waiting on a Super Admin decision, keyed by
    # decision unit: `null` = whole-tender award, otherwise the TenderLot id. Lets the
    # Award panel show "Awaiting Super Admin approval" per row straight off the payload.
    pending_intent_award_requests = serializers.SerializerMethodField()

    def get_bid_count(self, obj):
        return obj.bids.count()

    def get_skips_eoi_stage(self, obj):
        return bool(obj.linked_eoi_tender_id)

    def get_invited_vendor_count(self, obj):
        return obj.invited_vendors.count()

    def get_pending_intent_award_requests(self, obj):
        if not intent_award_proposal_visible(self):
            return []
        # Prefetched as `pending_intent_award_request_rows` by TenderViewSet's queryset;
        # fall back to a per-instance query (memoised on the instance) so the field is
        # still correct for tenders serialized straight off a single instance.
        rows = getattr(obj, 'pending_intent_award_request_rows', None)
        if rows is None:
            rows = list(
                obj.intent_award_requests
                .filter(status=IntentAwardRequestStatus.PENDING)
                .select_related('lot', 'bid')
            )
            obj.pending_intent_award_request_rows = rows
        return IntentToAwardRequestSerializer(rows, many=True, context=self.context).data

    def get_linked_tenders_summary(self, obj):
        return [
            {
                'id': str(t.id),
                'name': t.name,
                'reference_number': t.reference_number,
                'status': t.status,
            }
            for t in obj.linked_tenders.all()
        ]

    OPTIONAL_TEXT_FIELDS = (
        'application_type',
        'procurement_method',
        'address_for_document',
        'address_for_security',
        'place_for_opening',
        'bidders_eligibility',
        'time_for_completion',
        'invited_by',
        'bidding_currency',
        'instruction',
        'pre_tender_meeting_info',
        'contact_details',
        'target_site_type',
        'funding_source',
        'awarded_vendor_id',
        'awarded_vendor_name',
        'minimum_service_tier',
        'language_of_bid_submission',
        'budget_disclosure',
        'document_fee_type',
    )
    OPTIONAL_DATE_FIELDS = (
        'deadline',
        'verified_at',
        'published_at',
        'awarded_at',
        'closed_at',
        'security_deposit_verified_at',
        'eoi_deadline',
        'technical_deadline',
        'financial_deadline',
        'clarification_deadline',
        'site_visit_date',
    )
    OPTIONAL_BOOLEAN_FIELDS = (
        'bidders_schedule_purchase',
        'tender_security_required',
        'is_verified',
        'security_deposit_verified',
        'document_fee_refundable',
    )

    def to_internal_value(self, data):
        payload = data.copy() if hasattr(data, 'copy') else dict(data)
        if hasattr(payload, 'getlist'):
            payload = {k: payload.get(k) for k in payload.keys()}

        for field in self.OPTIONAL_TEXT_FIELDS:
            if (not self.partial or field in payload) and payload.get(field) is None:
                payload[field] = ''

        optional_date_fields = list(self.OPTIONAL_DATE_FIELDS)

        for field in optional_date_fields:
            if (not self.partial or field in payload) and payload.get(field) in ('', None):
                payload[field] = None

        for field in self.OPTIONAL_BOOLEAN_FIELDS:
            if payload.get(field) is None:
                payload[field] = False

        if payload.get('technology_types') is None:
            payload['technology_types'] = []
        if payload.get('target_districts') is None:
            payload['target_districts'] = []
        if payload.get('currency_rates') is None:
            payload['currency_rates'] = {}
        if payload.get('advertisement_channels') is None:
            payload['advertisement_channels'] = []

        for _jf in ('technology_types', 'target_districts', 'governing_documents', 'required_documents', 'lots', 'boq_items', 'currency_rates', 'advertisement_channels'):
            _v = payload.get(_jf)
            if isinstance(_v, str):
                try:
                    payload[_jf] = json.loads(_v)
                except Exception:
                    pass
        if payload.get('approximate_installation_target') in ('', None):
            payload['approximate_installation_target'] = None

        return super().to_internal_value(payload)

    def validate(self, attrs):
        errors = {}
        instance = getattr(self, 'instance', None)
        # Resolved early: an EOI Invite tender never itself opens a bid, holds a bid
        # opening event, or runs Combined evaluation, so several otherwise-required
        # fields don't apply to it (see uses below).
        is_eoi_invite_only = attrs.get('is_eoi_invite_only', instance.is_eoi_invite_only if instance else False)

        # 1. Define required fields for both types. `category` is deliberately excluded:
        # it's derived from technology_types below rather than collected separately, so
        # admins configure technology once instead of two overlapping fields.
        required_fields = [
            'name', 'department', 'application_type', 'procurement_method',
            'address_for_document',
            *([] if is_eoi_invite_only else ['place_for_opening']),
            'bidders_eligibility', 'time_for_completion', 'invited_by',
            'bidding_currency', 'instruction', 'contact_details', 'target_site_type',
        ]

        # 2. Standard required fields check
        for field in required_fields:
            value = attrs.get(field)
            if value is None and instance is not None:
                value = getattr(instance, field, None)
            if value in (None, '', []):
                errors[field] = 'This field is required.'

        technology_types = attrs.get('technology_types', instance.technology_types if instance else [])
        if not technology_types and not instance:
            errors['technology_types'] = 'Select at least one technology type.'
        if technology_types:
            # The tender's single "category" always reflects its primary technology —
            # keeps existing category-based filtering/exports working without asking
            # admins to set the same thing twice.
            attrs['category'] = technology_types[0]
        target_districts = attrs.get('target_districts', instance.target_districts if instance else [])
        if not target_districts:
            errors['target_districts'] = 'Select at least one target district.'

        currency_rates = attrs.get('currency_rates', instance.currency_rates if instance else {})
        base_currency = attrs.get('bidding_currency', instance.bidding_currency if instance else '')
        if isinstance(currency_rates, dict):
            for currency, rate in currency_rates.items():
                if currency == base_currency:
                    errors['currency_rates'] = f'{currency} is already the base currency — set additional currencies only.'
                    break
                try:
                    if Decimal(str(rate)) <= 0:
                        raise ValueError
                except Exception:
                    errors['currency_rates'] = f'Exchange rate for {currency} must be a positive number.'
                    break

        tender_security_required = attrs.get(
            'tender_security_required', instance.tender_security_required if instance else False
        )
        if tender_security_required:
            address_for_security = attrs.get('address_for_security')
            if address_for_security is None and instance is not None:
                address_for_security = getattr(instance, 'address_for_security', None)
            if not address_for_security:
                errors['address_for_security'] = 'Required when tender security is enabled.'

        def validate_file(field_name, max_size_mb=10, allowed_ext=None):
            file_obj = attrs.get(field_name)
            if not file_obj:
                return
            if file_obj.size > max_size_mb * 1024 * 1024:
                errors[field_name] = f'File too large (max {max_size_mb}MB).'
                return
            valid_ext = allowed_ext or {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}
            import os
            ext = os.path.splitext(file_obj.name)[1].lower()
            if ext not in valid_ext:
                errors[field_name] = 'Invalid file type. Allowed: PDF, DOC, DOCX, XLS, XLSX.'

        validate_file('schedule_file')
        validate_file('rfp_documents_file')
        validate_file('milestone_payment_schedule_file')

        technical_weight = attrs.get('technical_weight', instance.technical_weight if instance else 70)
        financial_weight = attrs.get('financial_weight', instance.financial_weight if instance else 30)
        technical_threshold = attrs.get('technical_threshold', instance.technical_threshold if instance else 70)
        cooling_off_days = attrs.get('cooling_off_days', instance.cooling_off_days if instance else 7)

        if technical_weight + financial_weight != 100:
            errors['technical_weight'] = 'Technical and financial weights must add up to 100.'
        if technical_threshold < 0 or technical_threshold > 100:
            errors['technical_threshold'] = 'Technical threshold must be between 0 and 100.'
        if cooling_off_days < 0 or cooling_off_days > 14:
            errors['cooling_off_days'] = 'Cooling-off period must be between 0 and 14 days.'

        # linked_eoi_tender: a tender linked to an EOI Invite inherits that EOI's name
        # and invited-vendor roster and skips running its own EOI stage. is_eoi_invite_only
        # and linked_eoi_tender are mutually exclusive, and linking only targets a root
        # (unlinked) EOI Invite.
        linked_eoi_tender = attrs.get('linked_eoi_tender', getattr(instance, 'linked_eoi_tender', None) if instance else None)
        if linked_eoi_tender is not None:
            if is_eoi_invite_only:
                errors['linked_eoi_tender'] = 'An EOI Invite tender cannot itself link to another EOI Invite.'
            elif not linked_eoi_tender.is_eoi_invite_only:
                errors['linked_eoi_tender'] = 'Can only link an EOI Invite tender.'
            elif linked_eoi_tender.linked_eoi_tender_id:
                errors['linked_eoi_tender'] = 'Cannot link to a tender that is itself already linked to an EOI Invite.'
            elif instance is not None and linked_eoi_tender.id == instance.id:
                errors['linked_eoi_tender'] = 'A tender cannot link to itself.'
            elif Tender.objects.filter(linked_eoi_tender=linked_eoi_tender).exclude(pk=getattr(instance, 'pk', None)).exists():
                errors['linked_eoi_tender'] = 'This EOI Invite has already been used to create another tender.'
            else:
                # The tender name always matches the EOI Invite it's linked to.
                attrs['name'] = linked_eoi_tender.name

        # Procurement workflow + staged deadlines
        workflow = attrs.get('procurement_workflow') or (instance.procurement_workflow if instance else ProcurementWorkflow.SEQUENTIAL)
        if is_eoi_invite_only or (linked_eoi_tender is not None and 'linked_eoi_tender' not in errors):
            # Both an EOI Invite and a tender linked to one always run the EOI → Combined
            # workflow — the former to collect EOIs, the latter because that's the only
            # workflow a linked tender's Restricted-Tendering shortlist makes sense under.
            workflow = ProcurementWorkflow.EOI_COMBINED
            attrs['procurement_workflow'] = workflow
        eoi_deadline = attrs.get('eoi_deadline', instance.eoi_deadline if instance else None)
        technical_deadline = attrs.get('technical_deadline', instance.technical_deadline if instance else None)
        financial_deadline = attrs.get('financial_deadline', instance.financial_deadline if instance else None)

        # 'EOI → Combined' auto-locks the procurement method to Restricted Tendering so
        # that only the shortlisted (invited) vendors can bid after the tender is published.
        if workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.SEQUENTIAL):
            attrs['procurement_method'] = ProcurementMethod.RESTRICTED
        elif workflow == ProcurementWorkflow.COMBINED and not eoi_deadline:
            # New single-stage 'Combined': no EOI, method freely selectable.
            pass

        # A combined-style workflow has an EOI stage when it's eoi_combined, or when a
        # legacy 'combined' tender still carries an eoi_deadline. New single-stage
        # 'Combined' tenders have no EOI stage — and neither does a tender linked to an
        # EOI Invite tender: its EOI already happened over there.
        has_eoi = (
            workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.SEQUENTIAL)
            and not (linked_eoi_tender is not None and 'linked_eoi_tender' not in errors)
        ) or bool(
            workflow == ProcurementWorkflow.COMBINED and (eoi_deadline or getattr(instance, 'eoi_deadline', None))
        )

        if workflow == ProcurementWorkflow.SEQUENTIAL:
            if eoi_deadline is None:
                errors['eoi_deadline'] = 'EOI deadline is required for a sequential workflow.'
            if technical_deadline is None:
                errors['technical_deadline'] = 'Technical deadline is required for a sequential workflow.'
            if financial_deadline is None:
                errors['financial_deadline'] = 'Financial deadline is required for a sequential workflow.'
            if eoi_deadline and technical_deadline and technical_deadline <= eoi_deadline:
                errors['technical_deadline'] = 'Technical deadline must be after the EOI deadline.'
            if technical_deadline and financial_deadline and financial_deadline <= technical_deadline:
                errors['financial_deadline'] = 'Financial deadline must be after the Technical deadline.'
        elif workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.COMBINED):
            if has_eoi:
                if eoi_deadline is None:
                    errors['eoi_deadline'] = 'EOI deadline is required.'
            else:
                # Single-stage Combined: no EOI deadline expected.
                if attrs.get('eoi_deadline'):
                    # keep if supplied, but not required
                    pass
            if technical_deadline is None:
                # An EOI Invite tender never itself collects a Combined bid — it only
                # exists to run the EOI stage and shortlist vendors — so it has no
                # Combined submission deadline of its own.
                if not is_eoi_invite_only:
                    errors['technical_deadline'] = 'Combined submission deadline is required.'
            if eoi_deadline and technical_deadline and technical_deadline <= eoi_deadline:
                errors['technical_deadline'] = 'Combined submission deadline must be after the EOI deadline.'
            # no separate financial deadline in combined mode

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        req_serializer = TenderRequiredDocumentSerializer(
            instance.required_documents.all(),
            many=True,
            context=self.context,
        )
        data['required_documents'] = req_serializer.data
        data['lots'] = TenderLotSerializer(instance.lots.all(), many=True, context=self.context).data
        data['lot_count'] = len(data['lots'])
        data['awarded_lot_count'] = sum(1 for lot in data['lots'] if lot.get('awarded_vendor_id'))
        data['boq_items'] = TenderBoqItemSerializer(instance.boq_template_items.filter(lot__isnull=True), many=True, context=self.context).data
        requester_role = getattr(request.user, 'role', None) if request else None
        requester_id = str(getattr(request.user, 'id', '')) if request else ''
        committee_qs = instance.evaluation_committee_members.select_related('member', 'assigned_by').all()
        is_committee_member = any(str(m.member_id) == requester_id for m in committee_qs)
        if requester_role == UserRole.ADMIN or is_committee_member:
            data['evaluation_committee_members'] = TenderEvaluationCommitteeMemberSerializer(committee_qs, many=True, context=self.context).data
        invited_vendors_qs = instance.invited_vendors.select_related('vendor', 'invited_by').all()
        is_invited_vendor = any(str(v.vendor_id) == requester_id for v in invited_vendors_qs)
        if requester_role in (UserRole.ADMIN, UserRole.RBF_OFFICIAL) or is_invited_vendor:
            data['invited_vendors'] = TenderInvitedVendorSerializer(invited_vendors_qs, many=True, context=self.context).data
        if requester_role == UserRole.VENDOR and instance.budget_disclosure != BudgetDisclosure.PUBLISHED:
            data.pop('budget', None)
            for lot in data.get('lots') or []:
                lot.pop('budget', None)
        if request:
            file_fields = [
                'schedule_file',
                'rfp_documents_file',
                'milestone_payment_schedule_file',
                'trading_license_file',
                'tax_clearance_file',
                'company_registration_file',
                'experience_portfolio_file',
            ]
            for field in file_fields:
                if data.get(field):
                    data[field] = request.build_absolute_uri(data[field])
            if isinstance(data.get('governing_documents'), list):
                for _gd in data['governing_documents']:
                    if _gd and _gd.get('file_url'):
                        _gd['file_url'] = request.build_absolute_uri(_gd['file_url'])
        return data

    def _save_required_documents(self, tender, docs):
        if docs is None:
            return
        tender.required_documents.all().delete()
        if not isinstance(docs, (list, tuple)):
            return
        for idx, doc in enumerate(docs):
            name = str((doc or {}).get('name') or '').strip()
            if not name:
                continue
            TenderRequiredDocument.objects.create(
                tender=tender,
                name=name,
                expected_type=str((doc or {}).get('expected_type') or '').strip(),
                bid_stage=(doc or {}).get('bid_stage') or BidStage.EOI,
                field_key=str((doc or {}).get('field_key') or '').strip(),
                position=int((doc or {}).get('position') if (doc or {}).get('position') not in (None, '') else idx),
            )

    def _save_lots(self, tender, lots):
        if lots is None or not isinstance(lots, (list, tuple)):
            return
        existing_by_id = {str(lot.id): lot for lot in tender.lots.all()}
        seen_ids = set()
        for idx, lot_data in enumerate(lots):
            if not isinstance(lot_data, dict):
                continue
            name = str(lot_data.get('name') or '').strip()
            if not name:
                continue
            lot_id = str(lot_data.get('id') or '').strip()
            existing = existing_by_id.get(lot_id) if lot_id else None
            fields = dict(
                name=name,
                description=str(lot_data.get('description') or '').strip(),
                technology_types=lot_data.get('technology_types') or [],
                target_districts=lot_data.get('target_districts') or [],
                estimated_installation_target=lot_data.get('estimated_installation_target') or None,
                budget=lot_data.get('budget') or None,
                position=int(lot_data.get('position')) if lot_data.get('position') not in (None, '') else idx,
            )
            if existing:
                for field, value in fields.items():
                    setattr(existing, field, value)
                existing.save()
                seen_ids.add(existing.id)
                self._save_boq_items(tender, existing, lot_data.get('boq_items'))
            else:
                created = TenderLot.objects.create(tender=tender, **fields)
                seen_ids.add(created.id)
                self._save_boq_items(tender, created, lot_data.get('boq_items'))
        for lot_id, lot in existing_by_id.items():
            if lot.id in seen_ids:
                continue
            if lot.awarded_vendor_id or lot.intent_to_award_bid_id:
                # An award decision already exists for this lot — keep it even if the
                # admin's latest edit dropped it from the list, rather than destroy history.
                continue
            lot.delete()

    def _save_boq_items(self, tender, lot, items):
        """Replace all TenderBoqItem rows for this tender's non-lot-wise BOQ (lot=None)
        or for one specific lot — full delete+recreate on every save, since these are
        simple template lines with no independent state (unlike TenderLot) worth
        preserving across edits. A None `items` (field omitted from the request) is a
        no-op, leaving whatever BOQ design already exists untouched."""
        if items is None or not isinstance(items, (list, tuple)):
            return
        TenderBoqItem.objects.filter(tender=tender, lot=lot).delete()
        rows = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            description = str(item.get('description') or '').strip()
            if not description:
                continue
            quantity = item.get('quantity')
            if quantity in (None, ''):
                continue
            rows.append(TenderBoqItem(
                tender=tender,
                lot=lot,
                description=description,
                unit=str(item.get('unit') or '').strip(),
                quantity=quantity,
                position=int(item.get('position')) if item.get('position') not in (None, '') else idx,
            ))
        if rows:
            TenderBoqItem.objects.bulk_create(rows)

    # Governing-document entries that recognize one of these carry their file into the
    # tender's real, structured FileField instead of the generic JSON list — this is
    # what keeps existing detail views, PDF exports, and vendor screens (which read
    # tender.schedule_file/rfp_documents_file/milestone_payment_schedule_file by name)
    # working unchanged while the admin-facing list becomes fully dynamic.
    GOVERNING_DOCUMENT_FIELD_KEYS = ('schedule_file', 'rfp_documents_file', 'milestone_payment_schedule_file')

    def _save_governing_documents(self, tender, docs, provided):
        if not provided:
            return
        request = self.context.get('request')
        files_by_name = {}
        if request is not None:
            for uploaded in request.FILES.getlist('governing_documents_files'):
                files_by_name[uploaded.name] = uploaded
        existing = {
            (d.get('file_name') or d.get('label')): d
            for d in (tender.governing_documents or [])
        }
        saved = []
        structured_field_updates = []
        for doc in docs if isinstance(docs, list) else []:
            if not isinstance(doc, dict):
                continue
            label = str(doc.get('label') or '').strip()
            if not label:
                continue
            fname = str(doc.get('file_name') or '').strip()
            uploaded = files_by_name.get(fname) if fname else None
            field_key = str(doc.get('field_key') or '').strip()

            if field_key in self.GOVERNING_DOCUMENT_FIELD_KEYS:
                if uploaded is not None:
                    setattr(tender, field_key, uploaded)
                    structured_field_updates.append(field_key)
                # If no new file was uploaded, leave the existing structured field as-is.
                continue

            file_url = None
            if uploaded is not None:
                path = default_storage.save(
                    f'governing_documents/{os.path.basename(uploaded.name)}', uploaded
                )
                file_url = f'/media/{path}'
            elif fname and existing.get(fname, {}).get('file_url'):
                file_url = existing[fname]['file_url']
            elif existing.get(label, {}).get('file_url'):
                file_url = existing[label]['file_url']
            saved.append({
                'label': label,
                'expected_type': str(doc.get('expected_type') or '').strip(),
                'file_name': uploaded.name if uploaded else (fname or (existing.get(label, {}) or {}).get('file_name') or ''),
                'file_url': file_url,
            })
        tender.governing_documents = saved
        tender.save(update_fields=['governing_documents', 'updated_at', *set(structured_field_updates)])

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            role = getattr(request.user, 'role', None)
            if role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
                raise serializers.ValidationError('Only the RBF Management Team or Platform Administrators can create tenders.')
        
        docs = validated_data.pop('required_documents', None)
        gov_provided = 'governing_documents' in validated_data
        gov_docs = validated_data.pop('governing_documents', None)
        lots = validated_data.pop('lots', None)
        boq_items = validated_data.pop('boq_items', None)
        # Final safety for deadline before saving (Database NOT NULL constraint).
        # The master deadline is derived from the staged deadlines (validate() ensures
        # the required staged deadlines are present for the given workflow).
        if not validated_data.get('deadline'):
            staged = [
                v for v in (
                    validated_data.get('eoi_deadline'),
                    validated_data.get('technical_deadline'),
                    validated_data.get('financial_deadline'),
                ) if v
            ]
            validated_data['deadline'] = max(staged) if staged else timezone.now()

        if not validated_data.get('reference_number'):
            last_id = Tender.objects.order_by('-id').values_list('id', flat=True).first() or 0
            validated_data['reference_number'] = f"TND-{last_id + 1:06d}"

        workflow = validated_data.get('procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
        if workflow in (ProcurementWorkflow.EOI_COMBINED, ProcurementWorkflow.COMBINED):
            validated_data['financial_deadline'] = None
        tender = super().create(validated_data)
        self._save_required_documents(tender, docs)
        self._save_governing_documents(tender, gov_docs, gov_provided)
        self._save_lots(tender, lots)
        self._save_boq_items(tender, None, boq_items)
        self._sync_linked_eoi_vendors(tender)
        return tender

    def update(self, instance, validated_data):
        docs = validated_data.pop('required_documents', None)
        gov_provided = 'governing_documents' in validated_data
        gov_docs = validated_data.pop('governing_documents', None)
        lots = validated_data.pop('lots', None)
        boq_items = validated_data.pop('boq_items', None)
        tender = super().update(instance, validated_data)
        self._save_required_documents(tender, docs)
        self._save_governing_documents(tender, gov_docs, gov_provided)
        self._save_lots(tender, lots)
        self._save_boq_items(tender, None, boq_items)
        self._sync_linked_eoi_vendors(tender)
        return tender

    def _sync_linked_eoi_vendors(self, tender):
        """Copy the linked EOI Invite tender's shortlisted vendors onto this tender.

        Runs on every save while linked (additive/idempotent via get_or_create) so
        vendors shortlisted on the EOI Invite tender *after* linking are still picked
        up the next time this tender is saved — it never removes anyone.
        """
        if not tender.linked_eoi_tender_id:
            return
        request = self.context.get('request')
        actor = getattr(request, 'user', None) if request else None
        for invite in tender.linked_eoi_tender.invited_vendors.all():
            TenderInvitedVendor.objects.get_or_create(
                tender=tender,
                vendor=invite.vendor,
                defaults={'invited_by': actor},
            )

    class Meta:
        model = Tender
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'verified_at', 'published_at', 'awarded_at', 'closed_at', 'dispute_started_at', 'security_deposit_verified_at', 'bid_count', 'publish_approval_status', 'publish_approval_requested_at', 'publish_approval_reviewed_at', 'publish_approval_reviewed_by', 'publish_approval_notes', 'evaluation_comment', 'evaluation_comment_author', 'evaluation_comment_updated_at']
        extra_kwargs = {
            'deadline': {'required': False, 'allow_null': True},
            # category is derived from technology_types in validate() rather than
            # collected directly from the admin, so it must be allowed to arrive blank.
            'category': {'required': False, 'allow_blank': True},
            'reference_number': {'required': False, 'allow_blank': True},
            'schedule_file': {'required': False, 'allow_null': True},
            'rfp_documents_file': {'required': False, 'allow_null': True},
            'milestone_payment_schedule_file': {'required': False, 'allow_null': True},
            'trading_license_file': {'required': False, 'allow_null': True},
            'tax_clearance_file': {'required': False, 'allow_null': True},
            'company_registration_file': {'required': False, 'allow_null': True},
            'experience_portfolio_file': {'required': False, 'allow_null': True},
        }


class NoticeSerializer(serializers.ModelSerializer):
    tender_reference = serializers.SerializerMethodField()
    tender_name = serializers.SerializerMethodField()
    notice_id = serializers.CharField(read_only=True)

    def get_tender_reference(self, obj):
        return obj.linked_tender.reference_number if obj.linked_tender else None
    
    def get_tender_name(self, obj):
        return obj.linked_tender.name if obj.linked_tender else None

    def validate(self, data):
        category = data.get('category')
        if category in ['tender', 'deadline']:
            if not data.get('linked_tender'):
                raise serializers.ValidationError({"linked_tender": "Linked tender is required for tender and deadline notices."})
            if not data.get('countdown_date'):
                raise serializers.ValidationError({"countdown_date": "Countdown date is required for tender and deadline notices."})
        return data

    def to_internal_value(self, data):
        # Handle cases where linked_tender might be sent as empty string or "null" string (common in FormData)
        if 'linked_tender' in data and (data['linked_tender'] == '' or data['linked_tender'] == 'null'):
            data = data.copy()
            data['linked_tender'] = None
        return super().to_internal_value(data)

    def _handle_attachments(self, notice, request):
        if not request:
            return

        attachments = notice.attachments or []
        files = request.FILES
        
        # In multipart/form-data, files are sent with keys like attachments-0, attachments-1
        attachment_keys = [k for k in files.keys() if k.startswith('attachments-')]
        
        if attachment_keys:
            from django.core.files.storage import default_storage
            import os
            
            for key in attachment_keys:
                file_obj = files[key]
                path = default_storage.save(
                    os.path.join('notices', 'attachments', file_obj.name),
                    file_obj
                )
                attachments.append({
                    'name': file_obj.name,
                    'url': default_storage.url(path)
                })
            
            notice.attachments = attachments
            notice.save(update_fields=['attachments'])

    def create(self, validated_data):
        last_notice = Notice.objects.order_by('-id').first()
        next_id = (last_notice.id + 1) if last_notice else 1
        validated_data['notice_id'] = f"NTC-{next_id:04d}"
        
        # Pop attachments if they are in validated_data (though they shouldn't be as they are handled manually)
        validated_data.pop('attachments', None)
        
        instance = super().create(validated_data)
        self._handle_attachments(instance, self.context.get('request'))
        return instance

    def update(self, instance, validated_data):
        # Handle attachments separately
        attachments_data = validated_data.pop('attachments', None)
        
        updated_instance = super().update(instance, validated_data)
        
        # If attachments were provided in the JSON payload (existing ones), we use them
        if attachments_data is not None:
            updated_instance.attachments = attachments_data
            updated_instance.save(update_fields=['attachments'])
            
        # Then handle new file uploads
        self._handle_attachments(updated_instance, self.context.get('request'))
        return updated_instance

    class Meta:
        model = Notice
        fields = '__all__'


class NoticeListSerializer(serializers.ModelSerializer):
    tender_reference = serializers.SerializerMethodField()
    tender_name = serializers.SerializerMethodField()

    def get_tender_reference(self, obj):
        return obj.linked_tender.reference_number if obj.linked_tender else None
    
    def get_tender_name(self, obj):
        return obj.linked_tender.name if obj.linked_tender else None

    class Meta:
        model = Notice
        fields = ['id', 'notice_id', 'title', 'category', 'summary', 'content', 'linked_tender', 'tender_reference', 'tender_name', 'is_pinned', 'show_countdown', 'countdown_date', 'attachments', 'status', 'published_at', 'created_at']


class ChallengeDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None

    def get_file_url(self, obj):
        if obj.document:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document.url)
            return obj.document.url
        return None

    class Meta:
        model = ChallengeDocument
        fields = ['id', 'challenge', 'title', 'description', 'document_type', 'file_url', 'uploaded_by', 'uploaded_by_name', 'uploaded_at', 'is_confidential']
        read_only_fields = ['uploaded_by', 'uploaded_at']


class ChallengeEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return "System"

    class Meta:
        model = ChallengeEvent
        fields = ['id', 'event_type', 'description', 'actor', 'actor_name', 'actor_role', 'metadata', 'created_at']


class TenderChallengeSerializer(serializers.ModelSerializer):
    challenger_bid_id = serializers.SerializerMethodField()
    challenger_vendor_name = serializers.SerializerMethodField()
    documents = ChallengeDocumentSerializer(many=True, read_only=True)
    events = ChallengeEventSerializer(many=True, read_only=True)
    assigned_reviewer_name = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    def get_challenger_bid_id(self, obj):
        return str(obj.challenger_bid.id) if obj.challenger_bid else None

    def get_challenger_vendor_name(self, obj):
        return obj.challenger_bid.vendor_name if obj.challenger_bid else None

    def get_assigned_reviewer_name(self, obj):
        if obj.assigned_reviewer:
            return obj.assigned_reviewer.get_full_name() or obj.assigned_reviewer.username
        return None

    def get_days_until_deadline(self, obj):
        if obj.challenge_deadline:
            delta = obj.challenge_deadline - timezone.now()
            return max(0, delta.days)
        return None

    def get_can_withdraw(self, obj):
        return obj.status in [ChallengeStatus.DRAFT, ChallengeStatus.SUBMITTED, ChallengeStatus.UNDER_REVIEW,
                               ChallengeStatus.ADDITIONAL_INFO_REQUESTED, ChallengeStatus.HEARING_SCHEDULED]

    class Meta:
        model = TenderChallenge
        fields = [
            'id', 'tender', 'filed_by_vendor_id', 'filed_by_vendor_name',
            'challenger_bid_id', 'challenger_vendor_name',
            'category', 'category_display', 'grounds', 'legal_basis', 'requested_relief',
            'status', 'status_display', 'priority',
            'challenge_deadline', 'response_deadline', 'hearing_date',
            'assigned_reviewer', 'assigned_reviewer_name', 'review_committee',
            'filed_at', 'acknowledged_at', 'reviewed_by', 'resolution_notes', 'resolved_at',
            'withdrawn_at', 'withdrawal_reason',
            'parent_challenge', 'is_consolidated',
            'documents', 'events',
            'days_until_deadline', 'can_withdraw',
        ]
        read_only_fields = ['filed_at', 'acknowledged_at', 'reviewed_by', 'resolved_at', 'withdrawn_at']


class ChallengeCreateSerializer(serializers.Serializer):
    """Serializer for creating a new challenge with validation."""
    filed_by_vendor_id = serializers.CharField(max_length=64)
    filed_by_vendor_name = serializers.CharField(max_length=255)
    challenger_bid_id = serializers.CharField(required=False, allow_null=True)
    category = serializers.ChoiceField(choices=ChallengeCategory.choices, default=ChallengeCategory.OTHER)
    grounds = serializers.CharField()
    legal_basis = serializers.CharField(required=False, allow_blank=True)
    requested_relief = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=[('normal', 'Normal'), ('urgent', 'Urgent')], default='normal')
    documents = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        required=False
    )
