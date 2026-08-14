import json
import os
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from django.conf import settings
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
    ContractStatus,
    ContractSignatureStatus,
)
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.projects.models import TechnologyType, VerificationMethod
from rbf.users.models import User


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


class TenderBidSiteSerializer(serializers.ModelSerializer):
    target_beneficiary_type = serializers.ChoiceField(
        choices=SITE_TARGET_BENEFICIARY_CHOICES,
        required=False,
        allow_blank=True,
    )
    system_configuration = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = TenderBidSite
        fields = [
            'id',
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


class TenderBidSerializer(serializers.ModelSerializer):
    """Serializer for vendor bid submissions and tracking"""
    sites = TenderBidSiteSerializer(many=True, required=False)
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
    document_requirements = serializers.SerializerMethodField()
    document_counts = serializers.SerializerMethodField()
    stage_two_ready = serializers.SerializerMethodField()
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
            'bid_amount', 'subsidy_requested', 'proposal_file', 'stage', 'stage_key', 'stage_badge', 'technology_type', 'tender_technology_types', 'technology_types', 'concept_note',
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
            'document_requirements', 'document_counts',
            'deadline', 'deadline_passed', 'deadline_countdown_seconds', 'is_locked', 'version_history',
            'evaluation_status', 'technical_score_total', 'financial_score_total', 'has_challenge',
            'status', 'version_number',
            'submitted_at', 'reviewed_at', 'reviewed_by', 'rejection_reason',
            'created_at', 'updated_at', 'sites'
        ]
        read_only_fields = ['id', 'submitted_at', 'created_at', 'updated_at', 'stage', 'stage_key', 'stage_badge', 'technology_type', 'stage_two_unlocked', 'stage_two_unlocked_at', 'stage_two_source_bid', 'stage_two_ready']

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
        for field_name in ('sites', 'system_configuration', 'boq_items', 'boq_details'):
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

    def _required_document_fields(self):
        return [
            'technical_proposal_file',
            'financial_proposal_file',
            'boq_file',
            'gender_action_plan_file',
            'implementation_plan_file',
            'om_plan_file',
        ]

    def _effective_stage_key(self, attrs):
        instance = getattr(self, 'instance', None)
        if instance is not None and has_stage_two_shortlist_access(instance):
            return 'site_specific'
        tender = attrs.get('tender') or getattr(getattr(self, 'instance', None), 'tender', None)
        if tender is not None:
            return normalize_tender_stage(tender.stage_type)
        return 'pre_qualification'

    def _effective_stage_label(self, attrs):
        tender = attrs.get('tender') or getattr(getattr(self, 'instance', None), 'tender', None)
        if tender is not None:
            return tender_stage_label(tender.stage_type)
        return 'Stage 1: Concept'

    def validate(self, attrs):
        errors = {}
        request = self.context.get('request')
        instance = getattr(self, 'instance', None)
        tender = attrs.get('tender') or getattr(instance, 'tender', None)
        stage_key = self._effective_stage_key(attrs)
        attrs['stage'] = self._effective_stage_label(attrs)

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

        stage_key = self._effective_stage_key(attrs)
        if stage_key == 'site_specific':
            boq_items = attrs.get('boq_items', instance.boq_items if instance else [])
            if not boq_items:
                boq_items = attrs.get('boq_details', [])
            boq_total = Decimal('0')
            if not boq_items:
                errors['boq_items'] = 'Bill of Quantities is required for site-specific submissions.'
            elif isinstance(boq_items, list):
                for item in boq_items:
                    qty = item.get('qty') if isinstance(item, dict) else None
                    unit_price = item.get('unit_price') if isinstance(item, dict) else None
                    if qty not in (None, '') and unit_price not in (None, ''):
                        boq_total += Decimal(str(qty)) * Decimal(str(unit_price))
                if bid_amount not in (None, '') and boq_total != Decimal(str(bid_amount)):
                    errors['boq_items'] = f'BOQ grand total must equal the bid amount. Current total: {boq_total}.'

            if stage_key == 'site_specific':
                om_strategy_summary = attrs.get('om_strategy_summary', instance.om_strategy_summary if instance else '')
                if not str(om_strategy_summary or '').strip():
                    errors['om_strategy_summary'] = 'O&M strategy summary is required for site-specific submissions.'

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

            if not attrs.get('inclusion_commitment_confirmed', instance.inclusion_commitment_confirmed if instance else False):
                errors['inclusion_commitment_confirmed'] = 'You must confirm the inclusion commitment before submitting.'
            sites = attrs.get('sites', instance.sites.all() if instance and hasattr(instance, 'sites') else [])
            if stage_key == 'site_specific':
                if not sites:
                    errors['sites'] = 'At least 1 project site is required.'
                else:
                    site_errors = {}
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
                    if site_errors:
                        errors['sites'] = site_errors
            elif sites:
                site_errors = {}
                for idx, site in enumerate(sites):
                    latitude = getattr(site, 'latitude', None) if not isinstance(site, dict) else site.get('latitude')
                    longitude = getattr(site, 'longitude', None) if not isinstance(site, dict) else site.get('longitude')
                    if latitude in (None, '') or longitude in (None, ''):
                        continue
                    if not point_in_lesotho(Decimal(str(longitude)), Decimal(str(latitude))):
                        site_errors[idx] = 'Site coordinates must fall within Lesotho.'
                if site_errors:
                    errors['sites'] = site_errors
        if stage_key == 'pre_qualification':
            attrs['technical_proposal'] = ''
            attrs['financial_proposal'] = ''
        if not attrs.get('boq_details') and attrs.get('boq_items'):
            attrs['boq_details'] = attrs['boq_items']

        bid_status = attrs.get('status', getattr(instance, 'status', None) if instance else None)

        # Stage 1: enforce concept note minimum length on final submission
        if stage_key == 'pre_qualification' and bid_status == BidStatus.SUBMITTED:
            concept_note = str(attrs.get('concept_note', getattr(instance, 'concept_note', '') if instance else '') or '').strip()
            if len(concept_note) < 200:
                errors['concept_note'] = 'Concept note must be at least 200 characters before submission.'

        # Stage 2: enforce tech tier ceiling on final submission
        if stage_key == 'site_specific' and bid_status == BidStatus.SUBMITTED:
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

        # Stage 2: enforce required files on final submission
        if stage_key == 'site_specific' and bid_status == BidStatus.SUBMITTED:
            required_file_fields = [
                ('technical_proposal_file', 'Technical Proposal'),
                ('financial_proposal_file', 'Financial Proposal'),
                ('boq_file', 'Bill of Quantities'),
            ]
            for field_name, label in required_file_fields:
                file_obj = attrs.get(field_name, getattr(instance, field_name, None) if instance else None)
                if not file_obj:
                    errors[field_name] = f'{label} document is required for Stage 2 submissions.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        sites_data = validated_data.pop('sites', [])
        bid = super().create(validated_data)
        if sites_data:
            TenderBidSite.objects.bulk_create(
                [TenderBidSite(bid=bid, **site) for site in sites_data]
            )
        return bid

    def update(self, instance, validated_data):
        sites_data = validated_data.pop('sites', None)
        bid = super().update(instance, validated_data)
        if sites_data is not None:
            bid.sites.all().delete()
            if sites_data:
                TenderBidSite.objects.bulk_create(
                    [TenderBidSite(bid=bid, **site) for site in sites_data]
                )
        return bid

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
        data['stage'] = tender_stage_label('site_specific' if instance.stage_two_unlocked else (instance.tender.stage_type if instance.tender_id else instance.stage))
        data['device_brand'] = system_configuration.get('device_brand', '')
        data['device_model'] = system_configuration.get('device_model', '')
        data['rated_power_w'] = system_configuration.get('rated_power_w')
        data['battery_capacity_wh'] = system_configuration.get('battery_capacity_wh')
        data['pv_panel_size_w'] = system_configuration.get('pv_panel_size_w')
        data['inverter_type'] = system_configuration.get('inverter_type', '')
        data['co_financing_amount'] = system_configuration.get('co_financing_amount_lsl')
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
            ]
            for field in file_fields:
                if data.get(field):
                    data[field] = request.build_absolute_uri(data[field])
            if data.get('om_plan_document'):
                data['om_plan_document'] = request.build_absolute_uri(data['om_plan_document'])
        return data

    def get_stage_key(self, obj):
        if has_stage_two_shortlist_access(obj):
            return 'site_specific'
        stage_source = obj.stage or (obj.tender.stage_type if obj.tender_id else '')
        return normalize_tender_stage(stage_source)

    def get_stage_badge(self, obj):
        if has_stage_two_shortlist_access(obj):
            return tender_stage_label('site_specific')
        stage_source = obj.stage or (obj.tender.stage_type if obj.tender_id else '')
        return tender_stage_label(stage_source)

    def get_stage_two_ready(self, obj):
        if has_stage_two_shortlist_access(obj):
            return True
        return bool(
            TenderBid.objects.filter(
                tender=obj.tender,
                vendor_id=obj.vendor_id,
                stage_two_unlocked=True,
                status=BidStatus.DRAFT,
                stage_two_source_bid__status=BidStatus.ACCEPTED,
            ).exclude(id=obj.id).exists()
        )

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

    def get_document_requirements(self, obj):
        required = self._required_document_fields()
        return [
            {
                'field': field_name,
                'required': is_site_specific_stage(obj.tender.stage_type if obj.tender_id else obj.stage),
                'uploaded': bool(getattr(obj, field_name)),
            }
            for field_name in required
        ]

    def get_document_counts(self, obj):
        required = self._required_document_fields()
        uploaded = sum(1 for field_name in required if getattr(obj, field_name))
        return {'uploaded': uploaded, 'required': len(required)}

    def get_deadline(self, obj):
        return obj.tender.last_date_submission or obj.tender.deadline

    def get_deadline_passed(self, obj):
        deadline = obj.tender.last_date_submission or obj.tender.deadline
        return bool(deadline and timezone.now() > deadline)

    def get_deadline_countdown_seconds(self, obj):
        deadline = obj.tender.last_date_submission or obj.tender.deadline
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
        if self.get_stage_key(obj) != 'site_specific':
            return []
        evaluations = getattr(obj, '_prefetched_objects_cache', {}).get('evaluations')
        if evaluations is None:
            evaluations = obj.evaluations.select_related('evaluator').all()
        return [ev for ev in evaluations if ev.status == EvaluationStatus.SCORED]

    def get_evaluation_status(self, obj):
        scored_evaluations = self._stage_two_scored_evaluations(obj)
        if not scored_evaluations:
            return 'pending'
        has_financial = any(getattr(getattr(ev, 'evaluator', None), 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN} for ev in scored_evaluations)
        has_technical = any(getattr(getattr(ev, 'evaluator', None), 'role', None) in {UserRole.TAC, UserRole.ADMIN} for ev in scored_evaluations)
        if has_financial:
            return 'evaluated'
        if has_technical:
            return 'technical_scored'
        return 'pending'

    def get_technical_score_total(self, obj):
        scored_evaluations = [
            ev for ev in self._stage_two_scored_evaluations(obj)
            if getattr(getattr(ev, 'evaluator', None), 'role', None) in {UserRole.TAC, UserRole.ADMIN}
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
            if getattr(getattr(ev, 'evaluator', None), 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
        ]
        if not scored_evaluations:
            return None
        totals = [
            (ev.technical_score or 0)
            + (ev.feasibility_score or 0)
            + (ev.kpi_score or 0)
            + (ev.gender_score or 0)
            for ev in scored_evaluations
        ]
        return round(sum(totals) / len(totals))

    def get_has_challenge(self, obj):
        return obj.challenges.filter(
            status__in=[ChallengeStatus.SUBMITTED, ChallengeStatus.UNDER_REVIEW]
        ).exists()


class TenderBidEvaluationSerializer(serializers.ModelSerializer):
    evaluator_username = serializers.CharField(source='evaluator.username', read_only=True)
    evaluator_role = serializers.CharField(source='evaluator.role', read_only=True)
    TECHNICAL_ROLE_KEYS = {UserRole.TAC, UserRole.ADMIN}
    FINANCIAL_ROLE_KEYS = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
    TECHNICAL_SCORE_FIELDS = (
        'technical_score',
        'feasibility_score',
        'om_score',
        'kpi_score',
        'gender_score',
        'environmental_score',
    )
    TECHNICAL_SCORE_LIMITS = {
        'technical_score': 20,
        'feasibility_score': 15,
        'om_score': 10,
        'kpi_score': 10,
        'gender_score': 10,
        'environmental_score': 5,
        'inclusivity_score': 0,
    }
    FINANCIAL_SCORE_COMPONENT_LIMITS = {
        'technical_score': 10,
        'feasibility_score': 10,
        'kpi_score': 5,
        'gender_score': 5,
        'financial_score': 30,
        'environmental_score': 0,
        'om_score': 0,
        'inclusivity_score': 0,
    }

    class Meta:
        model = TenderBidEvaluation
        fields = [
            'id',
            'bid',
            'evaluator',
            'evaluator_username',
            'evaluator_role',
            'status',
            'technical_score',
            'financial_score',
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
        read_only_fields = ['id', 'total_score', 'created_at', 'updated_at', 'evaluator_username', 'evaluator_role']

    def _role(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'role', None)

    def _technical_total(self, instance, attrs):
        return sum(
            int(attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0) or 0)
            for field_name in self.TECHNICAL_SCORE_FIELDS
        )

    def _financial_total(self, instance, attrs):
        fields = ('technical_score', 'feasibility_score', 'kpi_score', 'gender_score')
        return sum(
            int(attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0) or 0)
            for field_name in fields
        )

    def _bid(self, attrs):
        return attrs.get('bid') or getattr(getattr(self, 'instance', None), 'bid', None)

    def _technical_clearance_bid(self, bid):
        return bid

    def validate(self, attrs):
        role = self._role()
        instance = getattr(self, 'instance', None)
        bid = self._bid(attrs)
        score_limits = self.FINANCIAL_SCORE_COMPONENT_LIMITS if role == UserRole.RBF_OFFICIAL else self.TECHNICAL_SCORE_LIMITS

        field_errors = {}
        for field_name, limit in score_limits.items():
            score = attrs.get(field_name, getattr(instance, field_name, 0) if instance else 0)
            if score is None:
                score = 0
            if score < 0 or score > limit:
                field_errors[field_name] = f'Score must be between 0 and {limit}.'
        if field_errors:
            raise serializers.ValidationError(field_errors)

        if role == UserRole.TAC:
            financial_score = attrs.get('financial_score', instance.financial_score if instance else 0)
            if financial_score not in (None, 0):
                raise serializers.ValidationError({'financial_score': 'Financial evaluation is reserved for the RBF Management Team after technical clearance.'})
            if attrs.get('inclusivity_score', getattr(instance, 'inclusivity_score', 0) if instance else 0) not in (None, 0):
                raise serializers.ValidationError({'inclusivity_score': 'This score is no longer used in the Stage 2 technical matrix.'})
        if role == UserRole.RBF_OFFICIAL:
            technical_total = None
            if bid is not None:
                technical_bid = self._technical_clearance_bid(bid)
                technical_evaluations = TenderBidEvaluation.objects.filter(
                    bid=technical_bid,
                    status=EvaluationStatus.SCORED,
                    evaluator__role__in=self.TECHNICAL_ROLE_KEYS,
                )
                technical_total = None
                if technical_evaluations.exists():
                    technical_values = [
                        sum(getattr(ev, field_name, 0) for field_name in self.TECHNICAL_SCORE_FIELDS)
                        for ev in technical_evaluations
                    ]
                    technical_total = round(sum(technical_values) / len(technical_values))
            threshold = getattr(getattr(bid, 'tender', None), 'technical_threshold', 70) or 70
            minimum_technical_total = round((Decimal(str(threshold)) / Decimal('100')) * Decimal('70'))
            if technical_total is None or technical_total < minimum_technical_total:
                raise serializers.ValidationError({'financial_score': f'Financial evaluation can only start after the technical score passes the threshold ({threshold}% of 70).'})
            if attrs.get('environmental_score', getattr(instance, 'environmental_score', 0) if instance else 0) not in (None, 0):
                raise serializers.ValidationError({'environmental_score': 'RMT can only submit the 30-point financial matrix in this workflow.'})
            if attrs.get('om_score', getattr(instance, 'om_score', 0) if instance else 0) not in (None, 0):
                raise serializers.ValidationError({'om_score': 'RMT can only submit the 30-point financial matrix in this workflow.'})
            if attrs.get('inclusivity_score', getattr(instance, 'inclusivity_score', 0) if instance else 0) not in (None, 0):
                raise serializers.ValidationError({'inclusivity_score': 'RMT can only submit the 30-point financial matrix in this workflow.'})
        return attrs

    def _compute_total(self, instance, attrs):
        role = self._role()
        if role == UserRole.RBF_OFFICIAL:
            financial_total = self._financial_total(instance, attrs)
            attrs['financial_score'] = financial_total
            return financial_total
        return self._technical_total(instance, attrs)

    def create(self, validated_data):
        validated_data['total_score'] = self._compute_total(None, validated_data)
        validated_data['status'] = EvaluationStatus.SCORED
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['total_score'] = self._compute_total(instance, validated_data)
        validated_data['status'] = EvaluationStatus.SCORED
        return super().update(instance, validated_data)


class TenderContractSerializer(serializers.ModelSerializer):
    ANNEX_SOURCE_FIELDS = {
        'annex_a_file': ('gender_action_plan_file',),
        'annex_b_file': ('implementation_plan_file',),
        'annex_c_file': ('financial_proposal_file', 'boq_file'),
        'annex_d_file': ('reporting_templates_file', 'milestone_payment_schedule_file', 'schedule_file'),
        'annex_e_file': ('technical_proposal_file',),
    }

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
    
    def get_bid_count(self, obj):
        return obj.bids.count()
    
    class Meta:
        model = Tender
        fields = [
            'id', 'reference_number', 'name', 'department', 'category',
            'status', 'deadline', 'budget', 'published_at', 'is_verified',
            'awarded_vendor_name', 'bid_count', 'created_at',
            'technology_types', 'target_districts', 'procurement_method',
            'application_type', 'tender_security_required',
        ]


class TenderSerializer(serializers.ModelSerializer):
    reference_number = serializers.CharField(required=False, allow_blank=True, default='')
    bid_count = serializers.SerializerMethodField()
    
    def get_bid_count(self, obj):
        return obj.bids.count()
    
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
    )
    OPTIONAL_DATE_FIELDS = (
        'deadline',
        'last_date_security',
        'last_date_submission',
        'date_opening',
        'verified_at',
        'published_at',
        'awarded_at',
        'closed_at',
        'security_deposit_verified_at',
    )
    OPTIONAL_BOOLEAN_FIELDS = (
        'bidders_schedule_purchase',
        'tender_security_required',
        'is_verified',
        'security_deposit_verified',
    )

    REQUIRED_FIELDS = [
        'name',
        'department',
        'category',
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
        'contact_details',
        'target_site_type',
    ]

    def to_internal_value(self, data):
        payload = data.copy() if hasattr(data, 'copy') else dict(data)

        application_type = payload.get('application_type', '') or ''
        is_access_window = application_type.lower() == 'access window'

        for field in self.OPTIONAL_TEXT_FIELDS:
            if payload.get(field) is None:
                payload[field] = ''

        optional_date_fields = list(self.OPTIONAL_DATE_FIELDS)
        if is_access_window:
            optional_date_fields = [f for f in optional_date_fields if f not in {'last_date_submission', 'last_date_security'}]
        
        for field in optional_date_fields:
            if payload.get(field) in ('', None):
                payload[field] = None

        for field in self.OPTIONAL_BOOLEAN_FIELDS:
            if payload.get(field) is None:
                payload[field] = False

        if payload.get('technology_types') is None:
            payload['technology_types'] = []
        if payload.get('target_districts') is None:
            payload['target_districts'] = []
        
        if payload.get('approximate_installation_target') in ('', None):
            payload['approximate_installation_target'] = None

        return super().to_internal_value(payload)

    def validate(self, attrs):
        errors = {}
        instance = getattr(self, 'instance', None)
        application_type = attrs.get('application_type') or (instance.application_type if instance else '')
        is_access_window = application_type.lower() == 'access window'
        tender_security_required = attrs.get('tender_security_required', instance.tender_security_required if instance else False)

        # 1. Define required fields for both types
        required_fields = [
            'name', 'department', 'category', 'application_type', 'procurement_method',
            'address_for_document', 'address_for_security', 'place_for_opening',
            'bidders_eligibility', 'time_for_completion', 'invited_by',
            'bidding_currency', 'instruction', 'contact_details', 'target_site_type',
        ]

        # 2. Type-specific requirement logic
        if not is_access_window:
            # Application Window requirements: Submission and Opening dates are mandatory
            if not attrs.get('last_date_submission') and not (instance and instance.last_date_submission):
                errors['last_date_submission'] = 'Document Submission Deadline is required for Application Window tenders.'
            if not attrs.get('date_opening') and not (instance and instance.date_opening):
                errors['date_opening'] = 'Tender Opening Date is required for Application Window tenders.'
        
        # 3. Tender Security requirement logic
        if tender_security_required:
            if not attrs.get('last_date_security') and not (instance and instance.last_date_security):
                errors['last_date_security'] = 'Security Submission Deadline is required when Tender Security is enabled.'

        # 4. Standard required fields check
        for field in required_fields:
            value = attrs.get(field)
            if value is None and instance is not None:
                value = getattr(instance, field, None)
            if value in (None, '', []):
                errors[field] = 'This field is required.'

        technology_types = attrs.get('technology_types', instance.technology_types if instance else [])
        if not technology_types and not instance:
            errors['technology_types'] = 'Select at least one technology type.'
        target_districts = attrs.get('target_districts', instance.target_districts if instance else [])
        if not target_districts:
            errors['target_districts'] = 'Select at least one target district.'

        # 5. Handle Deadline mapping
        # For Application Window: must map to submission deadline
        # For Access Window: map to submission deadline if provided, else handled in create()
        if attrs.get('last_date_submission'):
            attrs['deadline'] = attrs['last_date_submission']
        elif not is_access_window:
            # Fallback for Application Window if missing (though validate should catch it)
            if instance and instance.last_date_submission:
                 attrs['deadline'] = instance.last_date_submission

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

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
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
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            role = getattr(request.user, 'role', None)
            if role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
                raise serializers.ValidationError('Only the RBF Management Team or Platform Administrators can create tenders.')
        
        application_type = validated_data.get('application_type', '') or ''
        is_access_window = application_type.lower() == 'access window'
        
        # Final safety for deadline before saving (Database NOT NULL constraint)
        if not validated_data.get('deadline'):
            if is_access_window:
                # 5-year rolling window for Access Window tenders
                validated_data['deadline'] = timezone.now() + timedelta(days=365 * 5)
            else:
                # Should have been caught by validate() but as fallback use submission date
                validated_data['deadline'] = validated_data.get('last_date_submission') or timezone.now()
        
        if not validated_data.get('reference_number'):
            last_id = Tender.objects.order_by('-id').values_list('id', flat=True).first() or 0
            validated_data['reference_number'] = f"TND-{last_id + 1:06d}"
        return super().create(validated_data)

    class Meta:
        model = Tender
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'verified_at', 'published_at', 'awarded_at', 'closed_at', 'dispute_started_at', 'security_deposit_verified_at', 'bid_count']
        extra_kwargs = {
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
