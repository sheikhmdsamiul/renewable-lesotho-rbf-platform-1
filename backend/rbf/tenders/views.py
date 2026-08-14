from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS, BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, DateFromToRangeFilter, RangeFilter, CharFilter, ChoiceFilter
from .models import (
    Tender,
    TenderStatus,
    TenderBid,
    TenderBidSite,
    BidStatus,
    TenderBidEvaluation,
    EvaluationStatus,
    TenderContract,
    ContractStatus,
    ContractSignatureStatus,
    TenderChallenge,
    ChallengeStatus,
    ChallengeCategory,
    ChallengeDocument,
    ChallengeEvent,
    Notice,
)
from .serializers import (
    TenderSerializer,
    TenderBidSerializer,
    TenderListSerializer,
    TenderBidEvaluationSerializer,
    TenderContractSerializer,
    ProjectAssignmentSerializer,
    normalize_tender_stage,
    is_site_specific_stage,
    tender_stage_label,
    NoticeSerializer,
    NoticeListSerializer,
    TenderChallengeSerializer,
    ChallengeDocumentSerializer,
    ChallengeEventSerializer,
    ChallengeCreateSerializer,
)
from .pba_pdf import generate_contract_pdf
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.users.models import User
from rbf.users.blacklisting import is_vendor_restricted
from rbf.common.urls import build_frontend_url
from rbf.projects.models import Project, Milestone, MilestoneStatus, ProjectStatus, VerificationMethod
from rbf.projects.audit import log_audit, AuditLogger
from rbf.projects.integrations import SyncToProspectJob, queue_project_targets_sync
from rbf.projects.serializers import ProjectSerializer
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.notifications.services import NotificationService


LESOTHO_DISTRICTS = [
    'Berea',
    'Butha-Buthe',
    'Leribe',
    'Mafeteng',
    'Maseru',
    'Mohale\'s Hoek',
    'Mokhotlong',
    'Qacha\'s Nek',
    'Quthing',
    'Thaba-Tseka',
]

APPLICATION_WINDOW = 'application window'
ACCESS_WINDOW = 'access window'


def _normalized_application_type(tender: Tender) -> str:
    return str(getattr(tender, 'application_type', '') or '').strip().lower()


def _uses_hard_deadline(tender: Tender) -> bool:
    return _normalized_application_type(tender) == APPLICATION_WINDOW


CONTRACT_ANNEX_SPECS = (
    (
        'annex_a_file',
        'Annex A',
        'Results Framework',
        'Gender Action Plan',
        ('gender_action_plan_file',),
    ),
    (
        'annex_b_file',
        'Annex B',
        'Implementation Schedule',
        'Implementation Plan',
        ('implementation_plan_file',),
    ),
    (
        'annex_c_file',
        'Annex C',
        'Payment Terms',
        'BOQ and Disbursement Table',
        ('financial_proposal_file', 'boq_file'),
    ),
    (
        'annex_d_file',
        'Annex D',
        'Reporting Formats',
        'Standardized System Templates',
        ('reporting_templates_file', 'milestone_payment_schedule_file', 'schedule_file'),
    ),
    (
        'annex_e_file',
        'Annex E',
        'Technical Standards',
        'Technical Proposal',
        ('technical_proposal_file',),
    ),
)


def _resolve_contract_source_file(tender: Tender, bid: TenderBid, source_fields):
    for field_name in source_fields:
        source = bid if bid is not None and hasattr(bid, field_name) else tender
        file_obj = getattr(source, field_name, None)
        if file_obj:
            return file_obj.name
    return None


def _get_contract_bid(contract: TenderContract):
    if contract.bid_id:
        return contract.bid
    return (
        TenderBid.objects.filter(tender=contract.tender, vendor_id=contract.vendor_id)
        .order_by('-version_number', '-submitted_at')
        .first()
    )


def _attach_awarded_bid_annexes(contract: TenderContract, tender: Tender, bid: TenderBid):
    for contract_field, _label, _title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        setattr(contract, contract_field, _resolve_contract_source_file(tender, bid, source_fields))


def _missing_contract_annexes(contract: TenderContract):
    bid = _get_contract_bid(contract)
    missing = []
    for contract_field, label, title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        if getattr(contract, contract_field) or _resolve_contract_source_file(contract.tender, bid, source_fields):
            continue
        missing.append(f'{label} ({title})')
    return missing


def _hydrate_contract_from_bid(contract: TenderContract):
    bid = _get_contract_bid(contract)
    if not bid:
        return None
    update_fields = []
    if not contract.bid_id:
        contract.bid = bid
        update_fields.append('bid')
    for contract_field, _label, _title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        if getattr(contract, contract_field):
            continue
        resolved_name = _resolve_contract_source_file(contract.tender, bid, source_fields)
        if resolved_name:
            setattr(contract, contract_field, resolved_name)
            update_fields.append(contract_field)
    if update_fields:
        update_fields.append('updated_at')
        contract.save(update_fields=update_fields)
    return bid


def _assignment_defaults(contract: TenderContract):
    bid = _get_contract_bid(contract)
    vendor = User.objects.filter(id=contract.vendor_id).first()
    technology_choices = _assignment_technology_choices(contract)
    technology_type = technology_choices[0] if technology_choices else _normalize_technology_type(contract.tender.category)
    if bid:
        system_configuration = getattr(bid, 'system_configuration', None)
        bid_technology_type = ''
        if isinstance(system_configuration, dict):
            bid_technology_type = _normalize_technology_type(system_configuration.get('technology_type'))
        if not bid_technology_type:
            bid_technology_type = _normalize_technology_type(getattr(bid, 'technology_type', ''))
        if bid_technology_type and bid_technology_type in technology_choices:
            technology_type = bid_technology_type
    tender_target_districts = [
        str(value or '').strip()
        for value in (contract.tender.target_districts if isinstance(contract.tender.target_districts, list) else [])
        if str(value or '').strip()
    ]
    bid_preferred_district = ''
    if bid:
        bid_preferred_district = str(getattr(bid, 'preferred_district', '') or '').strip()
    
    # Priority: bid_preferred_district > tender_target_districts > site districts > vendor zone
    assignment_districts = []
    if bid_preferred_district:
        assignment_districts = [bid_preferred_district]
    
    # Even if bid has preferred, we might want to include tender targets as fallback or options?
    # But requirement says "District should get the value of the selected primary district of the Bid"
    
    if not assignment_districts:
        if tender_target_districts:
            assignment_districts = tender_target_districts
        elif bid:
            for site in bid.sites.all():
                district = str(getattr(site, 'district', '') or '').strip()
                if district and district not in assignment_districts:
                    assignment_districts.append(district)
    
    if not assignment_districts and vendor:
        fallback_district = (
            (vendor.verification_zone if vendor and vendor.verification_zone else '')
            or (vendor.region if vendor and vendor.region else '')
        )
        if str(fallback_district or '').strip():
            assignment_districts = [str(fallback_district).strip()]
    
    installation_target = contract.tender.approximate_installation_target or (len(list(bid.sites.all())) if bid else 0)
    start_date = contract.tender.awarded_at.date() if contract.tender.awarded_at else timezone.now().date()
    contract_value = _contract_value(contract)
    return {
        'project_duration_months': 12,
        'installation_target': installation_target or 1,
        'technology_type': _normalize_technology_type(technology_type),
        'energy_output_target_kwh': '20000.00',
        'district_zone': ', '.join(assignment_districts),
        'district_zones': assignment_districts,
        'verification_method': VerificationMethod.MANUAL,
        'female_target_pct': 50,
        'vulnerable_target_pct': 30,
        'low_income_target_pct': 60,
        'start_date': start_date.isoformat(),
        'disbursement_preview': _disbursement_preview(contract_value),
    }


def _assignment_technology_choices(contract: TenderContract) -> list[str]:
    tender_technology_types = contract.tender.technology_types if isinstance(contract.tender.technology_types, list) else []
    normalized_choices = []
    for value in tender_technology_types:
        normalized = _normalize_technology_type(value)
        if normalized and normalized not in normalized_choices:
            normalized_choices.append(normalized)
    if normalized_choices:
        return normalized_choices
    normalized_category = _normalize_technology_type(contract.tender.category)
    if normalized_category:
        return [normalized_category]
    return [choice for choice, _label in Project._meta.get_field('technology_type').choices]


def _contract_value(contract: TenderContract) -> Decimal:
    if contract.bid and contract.bid.bid_amount:
        return Decimal(str(contract.bid.bid_amount))
    if contract.tender and contract.tender.budget:
        return Decimal(str(contract.tender.budget))
    return Decimal('0.00')


def _normalize_technology_type(value: str) -> str:
    raw = str(value or '').strip().lower()
    mapping = {
        'shs': 'SHS',
        'solar home system': 'SHS',
        'ics': 'ICS',
        'improved cookstove': 'ICS',
        'gmg': 'GMG',
        'mini-grid': 'GMG',
        'mini grid': 'GMG',
        'swp': 'SWP',
        'solar water pump': 'SWP',
        'pue': 'PUE',
        'productive use': 'PUE',
    }
    return mapping.get(raw, str(value or '').strip().upper())


def _disbursement_preview(contract_value: Decimal) -> dict:
    m1 = (contract_value * Decimal('0.20')).quantize(Decimal('0.01'))
    m2 = (contract_value * Decimal('0.50')).quantize(Decimal('0.01'))
    m3 = (contract_value * Decimal('0.30')).quantize(Decimal('0.01'))
    return {
        'milestone_1_amount_lsl': str(m1),
        'milestone_2_amount_lsl': str(m2),
        'milestone_3_amount_lsl': str(m3),
        'total_amount_lsl': str(contract_value.quantize(Decimal('0.01'))),
    }


def _create_project_assignment(request, contract: TenderContract, assignment_data: dict):
    tender = contract.tender
    vendor = assignment_data['vendor']
    
    district_zones = [str(value or '').strip() for value in assignment_data.get('district_zones', []) if str(value or '').strip()]
    primary_district = district_zones[0] if district_zones else str(assignment_data.get('district_zone') or '').strip()
    district_zone_label = ', '.join(district_zones) if district_zones else primary_district
    start_date = assignment_data.get('start_date') or (
        tender.awarded_at.date() if tender.awarded_at else timezone.now().date()
    )
    duration_months = int(assignment_data['project_duration_months'])
    end_date = start_date + timedelta(days=duration_months * 30)
    project_reference = f'PRJ-{tender.reference_number}-{contract.vendor_id}'
    milestone_plan_id = f'MS-{tender.reference_number}-{contract.vendor_id}'

    project_budget = _contract_value(contract)

    project = Project.objects.create(
        tender=tender,
        contract=contract,
        project_title=tender.name,
        project_reference=project_reference,
        milestone_plan_id=milestone_plan_id,
        vendor_id=str(vendor.id),
        vendor_name=vendor.organization_name or vendor.full_name or vendor.username,
        tech_type=_normalize_technology_type(assignment_data['technology_type']),
        technology_type=_normalize_technology_type(assignment_data['technology_type']),
        region=vendor.region or '',
        district=primary_district,
        district_zone=district_zone_label,
        status=ProjectStatus.SETUP_PENDING,
        contract_file=contract.signed_file,
        created_by=request.user,
        start_date=start_date,
        end_date=end_date,
        budget=project_budget,
        target_installations=assignment_data['installation_target'],
        installation_target=assignment_data['installation_target'],
        target_female_pct=assignment_data.get('female_target_pct', 50),
        female_target_pct=assignment_data.get('female_target_pct', 50),
        target_vulnerable_pct=assignment_data.get('vulnerable_target_pct', 30),
        vulnerable_target_pct=assignment_data.get('vulnerable_target_pct', 30),
        target_low_income_pct=assignment_data.get('low_income_target_pct', 60),
        low_income_target_pct=assignment_data.get('low_income_target_pct', 60),
        installation_target_summary=f"{assignment_data['installation_target']} installations",
        project_duration_months=duration_months,
        verification_method=assignment_data['verification_method'],
        energy_output=float(assignment_data['energy_output_target_kwh']),
        energy_output_target_kwh=assignment_data['energy_output_target_kwh'],
    )

    base_amount = Decimal(str(project_budget or 0))
    for milestone_number, name, disbursement_pct, milestone_status in [
        (1, 'Mobilization', 20, MilestoneStatus.PENDING),
        (2, '80% Implementation', 50, MilestoneStatus.LOCKED),
        (3, 'Final', 30, MilestoneStatus.LOCKED),
    ]:
        Milestone.objects.create(
            project=project,
            milestone_number=milestone_number,
            disbursement_pct=disbursement_pct,
            name=name,
            percentage=disbursement_pct,
            status=milestone_status,
            amount=(base_amount * Decimal(disbursement_pct) / Decimal('100')).quantize(Decimal('0.01')) if base_amount else Decimal('0.00'),
            amount_lsl=(base_amount * Decimal(disbursement_pct) / Decimal('100')).quantize(Decimal('0.01')) if base_amount else Decimal('0.00'),
        )

    contract.project_id = str(project.id)
    contract.milestone_plan_id = milestone_plan_id
    contract.save(update_fields=['project_id', 'milestone_plan_id', 'updated_at'])

    AuditLogger.log(
        'milestone_assigned',
        'projects',
        project.id,
        'project',
        old_status='',
        new_status=project.status,
        notes='Project created and milestone assignment saved from approved contract.',
    )
    queue_project_targets_sync(str(project.id), run_immediately=True, record_type='project')
    NotificationService.send(
        str(vendor.id),
        'Project Assigned',
        f'You have been assigned to Project PRJ-{project.id}. Complete setup to begin.',
        'info',
        'projects',
        project.id,
    )
    log_audit(
        request.user,
        'prospect_sync_queued',
        project,
        {'endpoint': '/v1/in/targets', 'project_id': str(project.id), 'mode': 'immediate'},
    )
    return project


def _populate_generated_contract_package(contract: TenderContract, tender: Tender, bid: TenderBid, vendor: User):
    _attach_awarded_bid_annexes(contract, tender, bid)
    generate_contract_pdf(contract, tender, bid, vendor)


def _round_score(value) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _latest_vendor_prequalification(vendor_id: str):
    return (
        VendorPrequalification.objects.filter(
            vendor_id=vendor_id,
        )
        .order_by('-submitted_at', '-id')
        .first()
    )


TECHNICAL_EVALUATOR_ROLES = {UserRole.TAC, UserRole.ADMIN}
FINANCIAL_EVALUATOR_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
TECHNICAL_SCORE_LIMITS = {
    'technical_score': 20,
    'feasibility_score': 15,
    'om_score': 10,
    'kpi_score': 10,
    'gender_score': 10,
    'environmental_score': 5,
}
FINANCIAL_SCORE_COMPONENT_LIMITS = {
    'technical_score': 10,
    'feasibility_score': 10,
    'kpi_score': 5,
    'gender_score': 5,
    'financial_score': 30,
}


def _sum_score_fields(evaluation: TenderBidEvaluation, score_limits: dict[str, int]) -> Decimal:
    return sum(Decimal(str(getattr(evaluation, field_name, 0) or 0)) for field_name in score_limits)


def _fits_score_matrix(evaluation: TenderBidEvaluation, score_limits: dict[str, int]) -> bool:
    for field_name, limit in score_limits.items():
        value = Decimal(str(getattr(evaluation, field_name, 0) or 0))
        if value < 0 or value > Decimal(str(limit)):
            return False
    return True


def _technical_evaluation_score(evaluation: TenderBidEvaluation) -> Decimal:
    if _fits_score_matrix(evaluation, TECHNICAL_SCORE_LIMITS):
        raw_total = _sum_score_fields(evaluation, TECHNICAL_SCORE_LIMITS)
        return (raw_total / Decimal("70")) * Decimal("100")

    values = [
        Decimal(str(evaluation.technical_score or 0)),
        Decimal(str(evaluation.feasibility_score or 0)),
        Decimal(str(evaluation.kpi_score or 0)),
        Decimal(str(evaluation.gender_score or 0)),
        Decimal(str(evaluation.environmental_score or 0)),
        Decimal(str(evaluation.om_score or 0)),
        Decimal(str(evaluation.inclusivity_score or 0)),
    ]
    populated_values = [value for value in values if value > 0]
    if populated_values:
        return sum(populated_values) / Decimal(len(populated_values))
    return Decimal("0")


def _technical_threshold_passed(technical_evaluations, threshold: int) -> bool:
    compatible_evaluations = [
        ev for ev in technical_evaluations
        if _fits_score_matrix(ev, TECHNICAL_SCORE_LIMITS)
    ]
    if compatible_evaluations:
        raw_total = sum(_sum_score_fields(ev, TECHNICAL_SCORE_LIMITS) for ev in compatible_evaluations) / Decimal(len(compatible_evaluations))
        minimum_raw_total = (Decimal(str(threshold)) / Decimal("100")) * Decimal("70")
        return raw_total >= minimum_raw_total

    technical_score = sum(_technical_evaluation_score(ev) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
    return technical_score >= Decimal(str(threshold))


def _financial_evaluation_score(evaluation: TenderBidEvaluation) -> Decimal:
    if _fits_score_matrix(evaluation, FINANCIAL_SCORE_COMPONENT_LIMITS):
        raw_total = Decimal(str(evaluation.financial_score or 0))
        return (raw_total / Decimal("30")) * Decimal("100")
    return Decimal(str(evaluation.financial_score or 0))


def _technical_score_for_bid(bid: TenderBid) -> Decimal | None:
    technical_evaluations = [
        ev for ev in bid.evaluations.all()
        if ev.status == EvaluationStatus.SCORED and getattr(getattr(ev, 'evaluator', None), 'role', None) in TECHNICAL_EVALUATOR_ROLES
    ]
    if not technical_evaluations:
        return None
    return sum(_technical_evaluation_score(ev) for ev in technical_evaluations) / Decimal(len(technical_evaluations))


def _clone_sites_to_bid(source_bid: TenderBid, target_bid: TenderBid):
    source_sites = list(source_bid.sites.all())
    if not source_sites:
        return
    TenderBidSite.objects.bulk_create([
        TenderBidSite(
            bid=target_bid,
            site_name=site.site_name,
            district=site.district,
            village_sub_district=site.village_sub_district,
            latitude=site.latitude,
            longitude=site.longitude,
            number_of_households=site.number_of_households,
            target_beneficiary_type=site.target_beneficiary_type,
            estimated_energy_demand_kwh_month=site.estimated_energy_demand_kwh_month,
            road_access_available=site.road_access_available,
            notes=site.notes,
            system_configuration=site.system_configuration,
        )
        for site in source_sites
    ])


def _copy_bid_sites_if_missing(source_bid: TenderBid, target_bid: TenderBid):
    if target_bid.sites.exists():
        return
    _clone_sites_to_bid(source_bid, target_bid)


def _copy_bid_documents(source_bid: TenderBid, target_bid: TenderBid):
    file_fields = (
        'proposal_file',
        'technical_proposal_file',
        'financial_proposal_file',
        'boq_file',
        'gender_action_plan_file',
        'implementation_plan_file',
        'om_plan_file',
        'reporting_templates_file',
        'distribution_map_file',
    )
    updated_fields = []
    for field_name in file_fields:
        source_value = getattr(source_bid, field_name, None)
        target_value = getattr(target_bid, field_name, None)
        if source_value and not target_value:
            setattr(target_bid, field_name, source_value)
            updated_fields.append(field_name)
    if updated_fields:
        target_bid.save(update_fields=[*updated_fields, 'updated_at'])


def _ensure_stage_two_draft(bid: TenderBid):
    if bid.stage_two_unlocked:
        return bid
    existing = (
        TenderBid.objects.filter(
            tender=bid.tender,
            vendor_id=bid.vendor_id,
            stage_two_unlocked=True,
            status=BidStatus.DRAFT,
        )
        .order_by('-version_number', '-created_at')
        .first()
    )
    if existing:
        _copy_bid_documents(bid, existing)
        _copy_bid_sites_if_missing(bid, existing)
        return existing

    latest_version = (
        TenderBid.objects.filter(tender=bid.tender, vendor_id=bid.vendor_id)
        .order_by('-version_number')
        .values_list('version_number', flat=True)
        .first()
    )
    next_version = (latest_version or 0) + 1
    draft = TenderBid.objects.create(
        tender=bid.tender,
        vendor_id=bid.vendor_id,
        vendor_name=bid.vendor_name,
        vendor_email=bid.vendor_email,
        bid_amount=bid.bid_amount,
        subsidy_requested=bid.subsidy_requested,
        proposal_file=bid.proposal_file,
        stage=tender_stage_label('site_specific'),
        concept_note=bid.concept_note,
        technical_proposal=bid.technical_proposal,
        financial_proposal=bid.financial_proposal,
        system_configuration=bid.system_configuration,
        boq_items=bid.boq_items,
        boq_details=bid.boq_details,
        device_brand_model=bid.device_brand_model,
        tech_tier=bid.tech_tier,
        energy_target_kwh_month=bid.energy_target_kwh_month,
        female_target_pct=bid.female_target_pct,
        vulnerable_target_pct=bid.vulnerable_target_pct,
        low_income_target_pct=bid.low_income_target_pct,
        inclusion_commitment_confirmed=bid.inclusion_commitment_confirmed,
        om_strategy_summary=bid.om_strategy_summary,
        local_technicians_to_be_trained=bid.local_technicians_to_be_trained,
        warranty_period_months=bid.warranty_period_months,
        offer_paygo=bid.offer_paygo,
        paygo_platform=bid.paygo_platform,
        daily_payment_amount_lsl=bid.daily_payment_amount_lsl,
        collection_method=bid.collection_method,
        version_number=next_version,
        status=BidStatus.DRAFT,
        stage_two_unlocked=True,
        stage_two_unlocked_at=timezone.now(),
        stage_two_source_bid=bid,
    )
    _copy_bid_documents(bid, draft)
    _clone_sites_to_bid(bid, draft)
    return draft


def _has_stage_two_shortlist_access(bid: TenderBid | None) -> bool:
    if bid is None or not bid.stage_two_unlocked:
        return False
    source_bid = bid.stage_two_source_bid
    return bool(source_bid and source_bid.status == BidStatus.ACCEPTED)


def _backfill_stage_two_drafts_for_vendor(vendor_id: str):
    eligible_bids = (
        TenderBid.objects.filter(
            vendor_id=vendor_id,
            status=BidStatus.ACCEPTED,
            stage_two_unlocked=False,
        )
        .select_related('tender')
    )
    for bid in eligible_bids:
        if normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) != 'pre_qualification':
            continue
        _ensure_stage_two_draft(bid)


def _send_vendor_stage_one_outcome_email(bid: TenderBid, subject: str, message: str):
    email_configured = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD) or settings.DEBUG
    if not email_configured or not bid.vendor_email:
        return False
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [bid.vendor_email],
            fail_silently=False,
        )
        return True
    except Exception:
        return False


def _notify_stage_one_outcome(bid: TenderBid, passed: bool, draft: TenderBid | None = None):
    if normalize_tender_stage(bid.tender.stage_type) != 'pre_qualification':
        return

    event = 'stage_one_passed' if passed else 'stage_one_failed'
    title = (
        f'Stage 1 Passed: {bid.tender.reference_number}'
        if passed else
        f'Stage 1 Unsuccessful: {bid.tender.reference_number}'
    )
    body = (
        f'Your Stage 1 submission passed technical review. Stage 2 is now unlocked as draft version {draft.version_number}.'
        if passed and draft is not None else
        'Your Stage 1 submission did not meet the technical threshold. Please review the outcome in My Bids.'
    )
    if not Notification.objects.filter(
        recipient_id=bid.vendor_id,
        event=event,
        linked_entity_id=str(bid.id),
    ).exists():
        Notification.objects.create(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            linked_entity_id=str(bid.id),
        )
    _send_vendor_stage_one_outcome_email(
        bid,
        title,
        f'{body}\n\nTender: {bid.tender.name} ({bid.tender.reference_number})\nBid Version: {bid.version_number}',
    )


def _build_award_ranking(tender: Tender):
    candidate_bids = list(
        TenderBid.objects.filter(
            tender=tender,
            status__in={BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED, BidStatus.AWARDED},
        )
        .prefetch_related('evaluations')
        .order_by('-version_number', '-submitted_at', '-updated_at', '-id')
    )
    bids_by_vendor = {}
    for bid in candidate_bids:
        bids_by_vendor.setdefault(str(bid.vendor_id), bid)
    bids = list(bids_by_vendor.values())
    technical_threshold = tender.technical_threshold or 70
    technical_weight = Decimal(str(tender.technical_weight or 70)) / Decimal("100")
    financial_weight = Decimal(str(tender.financial_weight or 30)) / Decimal("100")

    ranking_rows = []
    qualifying_rows = []

    for bid in bids:
        scored_evaluations = [ev for ev in bid.evaluations.all() if ev.status == EvaluationStatus.SCORED]
        technical_evaluations = [
            ev for ev in scored_evaluations
            if getattr(getattr(ev, 'evaluator', None), 'role', None) in TECHNICAL_EVALUATOR_ROLES
        ]
        financial_evaluations = [
            ev for ev in scored_evaluations
            if getattr(getattr(ev, 'evaluator', None), 'role', None) in FINANCIAL_EVALUATOR_ROLES
            and Decimal(str(ev.financial_score or 0)) > Decimal("0")
        ]
        if not technical_evaluations:
            ranking_rows.append({
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'vendor_name': bid.vendor_name,
                'bid_amount': float(bid.bid_amount or 0),
                'technical_score': None,
                'financial_score': None,
                'combined_score': None,
                'gender_score': None,
                'female_headed_household_target': 0,
                'passed_technical_threshold': False,
                'financial_opened': False,
                'is_recommended_winner': False,
                'disqualification_reason': 'No scored technical evaluation has been submitted yet.',
            })
            continue

        technical_score = sum(_technical_evaluation_score(ev) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
        gender_score = sum(Decimal(str(ev.gender_score or 0)) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
        prequal = _latest_vendor_prequalification(str(bid.vendor_id))
        female_target = prequal.female_beneficiary_target if prequal else 0
        passed_technical_threshold = _technical_threshold_passed(technical_evaluations, technical_threshold)

        row = {
            'bid_id': str(bid.id),
            'vendor_id': str(bid.vendor_id),
            'vendor_name': bid.vendor_name,
            'bid_amount': float(bid.bid_amount or 0),
            'technical_score': _round_score(technical_score),
            'financial_score': None,
            'combined_score': None,
            'gender_score': _round_score(gender_score),
            'female_headed_household_target': female_target,
            'passed_technical_threshold': passed_technical_threshold,
            'financial_opened': False,
            'is_recommended_winner': False,
            'disqualification_reason': '',
        }

        if not row['passed_technical_threshold']:
            row['disqualification_reason'] = f'Technical score below threshold ({technical_threshold}%).'
            ranking_rows.append(row)
            continue
        if not financial_evaluations:
            row['disqualification_reason'] = 'Technical score passed. Awaiting RMT financial evaluation.'
            ranking_rows.append(row)
            continue
        if not bid.bid_amount or Decimal(str(bid.bid_amount or 0)) <= 0:
            row['disqualification_reason'] = 'Financial proposal is missing or invalid.'
            ranking_rows.append(row)
            continue

        financial_score = sum(_financial_evaluation_score(ev) for ev in financial_evaluations) / Decimal(len(financial_evaluations))
        qualifying_rows.append((bid, row, financial_score))

    if qualifying_rows:
        for bid, row, financial_score in qualifying_rows:
            combined_score = (
                technical_weight * Decimal(str(row['technical_score']))
                + financial_weight * financial_score
            )
            row['financial_opened'] = True
            row['financial_score'] = _round_score(financial_score)
            row['combined_score'] = _round_score(combined_score)
            ranking_rows.append(row)

        ranking_rows.sort(
            key=lambda item: (
                item['combined_score'] is None,
                -(item['combined_score'] or 0),
                -(item['female_headed_household_target'] or 0),
                -(item['gender_score'] or 0),
                item['bid_amount'] or 0,
            )
        )
        recommended_bid_id = next((row['bid_id'] for row in ranking_rows if row['combined_score'] is not None), None)
        for index, row in enumerate(ranking_rows, start=1):
            row['rank'] = index
            row['is_recommended_winner'] = row['bid_id'] == recommended_bid_id
    else:
        for index, row in enumerate(ranking_rows, start=1):
            row['rank'] = index

    recommended_row = next((row for row in ranking_rows if row.get('is_recommended_winner')), None)
    return {
        'technical_weight': tender.technical_weight,
        'financial_weight': tender.financial_weight,
        'technical_threshold': technical_threshold,
        'cooling_off_days': tender.cooling_off_days,
        'rows': ranking_rows,
        'recommended': recommended_row,
    }


def _notify_intent_to_award(tender: Tender, ranking_payload: dict, send_email=True):
    recommended = ranking_payload.get('recommended')
    if not recommended:
        return

    bids_by_vendor = {row['vendor_id']: row for row in ranking_payload.get('rows', [])}
    cooling_off_until = tender.cooling_off_until
    cooling_date_text = cooling_off_until.strftime('%Y-%m-%d %H:%M:%S') if cooling_off_until else 'N/A'
    email_enabled = send_email and bool(
        (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
        or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
    )

    vendors = User.objects.filter(id__in=list(bids_by_vendor.keys())).only('id', 'email', 'full_name', 'username')
    for vendor in vendors:
        row = bids_by_vendor.get(str(vendor.id))
        if not row:
            continue
        is_winner = row['vendor_id'] == recommended['vendor_id']
        title = (
            f'Notice of Best Evaluated Bidder: {tender.reference_number}'
            if is_winner
            else f'Regret Letter: {tender.reference_number}'
        )
        body = (
            f"Tender: {tender.name} ({tender.reference_number})\n"
            f"Technical Score: {row['technical_score'] if row['technical_score'] is not None else 'N/A'}\n"
            f"Financial Score: {row['financial_score'] if row['financial_score'] is not None else 'Not opened'}\n"
            f"Combined Score: {row['combined_score'] if row['combined_score'] is not None else 'N/A'}\n"
        )
        if is_winner:
            body += (
                f"\nStatus: You are the Best Evaluated Bidder.\n"
                f"Cooling-off period ends on: {cooling_date_text}\n"
                f"The final award and PBA generation will only occur after the cooling-off period expires without a formal protest.\n"
            )
        else:
            body += "\nStatus: Another vendor achieved the highest combined score under the weighted RBF evaluation.\n"
            if row.get('disqualification_reason'):
                body += f"Reason: {row['disqualification_reason']}\n"

        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.EMAIL if email_enabled else NotificationChannel.IN_APP,
            event='intent_to_award',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

        if email_enabled and vendor.email:
            try:
                send_mail(
                    subject=title,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vendor.email],
                    fail_silently=True,
                )
            except Exception:
                pass


class IsRbfOfficialOrReadOnly(BasePermission):
    """
    Allows only the RBF Management Team to perform write actions; 
    authenticated users can read; optionally allows public read for GET requests.
    """

    def has_permission(self, request, view):
        # Allow public (unauthenticated) read access for GET requests
        if request.method in SAFE_METHODS:
            # Check if this is a public API request (e.g., from public portal)
            # For now, allow unauthenticated read access for all GET requests
            # This enables the public impact portal to work without authentication
            return True  # Allow both authenticated and unauthenticated read access
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
        )


class TenderFilterSet(FilterSet):
    """Advanced filtering for tenders"""
    deadline_range = DateFromToRangeFilter(field_name='deadline')
    budget_range = RangeFilter(field_name='budget')
    department = CharFilter(field_name='department', lookup_expr='icontains')
    technology_types = CharFilter(method='filter_technology_types')
    
    def filter_technology_types(self, queryset, name, value):
        if value:
            return queryset.filter(technology_types__contains=value)
        return queryset
    
    class Meta:
        model = Tender
        fields = ['status', 'category', 'department', 'is_verified', 'procurement_method']


class TenderPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class TenderViewSet(viewsets.ModelViewSet):
    queryset = Tender.objects.all().order_by('-created_at')
    serializer_class = TenderSerializer
    permission_classes = [IsRbfOfficialOrReadOnly]
    pagination_class = TenderPagination
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TenderFilterSet
    search_fields = ['reference_number', 'name', 'department', 'category']
    ordering_fields = ['created_at', 'deadline', 'published_at', 'verified_at', 'budget']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_permissions(self):
        if self.action == 'create_challenge':
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = Tender.objects.all().order_by('-created_at')
        user = self.request.user
        # Handle unauthenticated users - return all published tenders
        if not user.is_authenticated:
            return qs.filter(status=TenderStatus.PUBLISHED)
        if user.role == UserRole.VENDOR:
            is_approved = VendorPrequalification.objects.filter(
                vendor=user,
                status=PrequalificationStatus.APPROVED,
            ).exists()
            if not is_approved:
                return qs.none()
            return qs.filter(status=TenderStatus.PUBLISHED)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return TenderListSerializer
        return TenderSerializer

    def _assert_write_permission(self):
        user = self.request.user
        if getattr(user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can create or modify tenders.')

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in SAFE_METHODS and getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            if self.action != 'create_challenge':
                self.permission_denied(request, message='Only the RBF Management Team can create or modify tenders.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data
        if not data.get('stage_type'):
            data = {**data, 'stage_type': 'Pre-Qualification'}
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

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        tender.is_verified = True
        tender.verified_at = timezone.now()
        tender.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
        log_audit(request.user, 'tender_verified', tender, {'reference_number': tender.reference_number})
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if not tender.is_verified:
            return Response({'detail': 'Tender must be verified before publishing.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.status == TenderStatus.CLOSED:
            return Response({'detail': 'Closed tender cannot be published.'}, status=status.HTTP_400_BAD_REQUEST)

        tender.status = TenderStatus.PUBLISHED
        tender.published_at = timezone.now()
        tender.save(update_fields=['status', 'published_at', 'updated_at'])
        log_audit(request.user, 'tender_published', tender, {'reference_number': tender.reference_number})

        # Always notify all approved (pre-qualified) vendors on publish
        send_email = True
        notify_all = True

        notification_summary = self._notify_vendors_of_publish(tender, send_email, notify_all)
        if not notification_summary.get('recipient_count'):
            return Response(
                {'detail': 'No approved pre-qualified vendors found to notify.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if send_email and (not notification_summary.get('email_enabled') or notification_summary.get('email_error')):
            return Response(
                {'detail': notification_summary.get('email_error') or 'Email is not configured.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        data = TenderSerializer(tender).data
        data['notification_summary'] = notification_summary
        return Response(data, status=status.HTTP_200_OK)

    def _notify_vendors_of_publish(self, tender: Tender, send_email=True, notify_all=True):
        from rbf.users.models import User, VendorPrequalification, PrequalificationStatus

        # Always notify approved (pre-qualified) vendors
        vendors = User.objects.filter(role=UserRole.VENDOR)
        vendors = vendors.filter(prequalifications__status=PrequalificationStatus.APPROVED)
        vendors = list(vendors.distinct().only('id', 'email', 'full_name', 'username'))
        stakeholders = list(
            User.objects.filter(role__in={UserRole.DOE_OFFICER, UserRole.UNDP_DONOR})
            .distinct()
            .only('id', 'email', 'full_name', 'username', 'role')
        )
        recipients = vendors + stakeholders
        recipient_count = len(recipients)
        
        notifications = []
        email_subject = f"Tender Published: {tender.name}"
        email_body = (
            f"A new tender has been published.\n\n"
            f"Reference: {tender.reference_number}\n"
            f"Name: {tender.name}\n"
            f"Category: {tender.category}\n"
            f"Deadline: {tender.deadline}\n"
            f"View details: {build_frontend_url(f'/rbf-official/tenders?view=details&tenderId={tender.id}', request=self.request)}\n"
        )

        email_enabled = send_email and bool(
            (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
            or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
        )

        for recipient in recipients:
            notifications.append(
                Notification(
                    recipient_id=str(recipient.id),
                    recipient_name=recipient.full_name or recipient.username or recipient.email,
                    type=NotificationChannel.IN_APP,
                    event='tender_published',
                    title=email_subject,
                    body=email_body,
                    status=NotificationStatus.SENT,
                    linked_entity_id=str(tender.id),
                )
            )

        if notifications:
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)

        email_recipients = []
        email_error = None
        if email_enabled:
            email_recipients = list(dict.fromkeys([recipient.email for recipient in recipients if recipient.email]))
            if email_recipients:
                try:
                    send_mail(
                        subject=email_subject,
                        message=email_body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=email_recipients,
                        fail_silently=False,
                    )
                except Exception as exc:
                    email_error = str(exc)

        return {
            'recipient_count': recipient_count,
            'vendor_recipient_count': len(vendors),
            'stakeholder_recipient_count': len(stakeholders),
            'email_enabled': email_enabled,
            'email_recipient_count': len(email_recipients),
            'email_error': email_error,
        }


    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status not in {TenderStatus.PUBLISHED, TenderStatus.EVALUATION}:
            return Response(
                {'detail': 'Tender can be awarded only from Published or Evaluation state.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bid_id = str(request.data.get('bid_id') or '').strip()
        if not bid_id:
            return Response(
                {'detail': 'bid_id is required and must reference a submitted bid.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bid = TenderBid.objects.get(id=bid_id, tender=tender)
        except TenderBid.DoesNotExist:
            return Response(
                {'detail': 'Bid not found for this tender.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be awarded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ranking_payload = _build_award_ranking(tender)
        recommended = ranking_payload.get('recommended')
        if not recommended:
            return Response(
                {'detail': 'No qualifying bid passed the technical threshold for intent to award.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if str(recommended['bid_id']) != str(bid.id):
            return Response(
                {
                    'detail': 'Intent to award can only be issued to the recommended winner with the highest combined score.',
                    'recommended_bid_id': recommended['bid_id'],
                    'recommended_vendor_id': recommended['vendor_id'],
                    'recommended_vendor_name': recommended['vendor_name'],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        awarded_vendor_id = str(request.data.get('awarded_vendor_id') or '').strip()
        awarded_vendor_name = str(request.data.get('awarded_vendor_name') or '').strip()
        if awarded_vendor_id and awarded_vendor_id != bid.vendor_id:
            return Response(
                {'detail': 'awarded_vendor_id must match the selected bid vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if awarded_vendor_name and bid.vendor_name and awarded_vendor_name != bid.vendor_name:
            return Response(
                {'detail': 'awarded_vendor_name must match the selected bid vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        awarded_vendor_id = awarded_vendor_id or bid.vendor_id
        awarded_vendor_name = awarded_vendor_name or bid.vendor_name
        if not awarded_vendor_id and not awarded_vendor_name:
            return Response(
                {'detail': 'awarded_vendor_id or awarded_vendor_name is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        tender.status = TenderStatus.STANDSTILL
        tender.intent_to_award_bid = bid
        tender.intent_to_award_at = now
        tender.awarded_vendor_id = awarded_vendor_id
        tender.awarded_vendor_name = awarded_vendor_name
        cooling_off_days = tender.cooling_off_days if tender.cooling_off_days is not None else 7
        tender.cooling_off_until = now + timedelta(days=cooling_off_days)
        tender.save(
            update_fields=[
                'status',
                'intent_to_award_bid',
                'intent_to_award_at',
                'awarded_vendor_id',
                'awarded_vendor_name',
                'cooling_off_until',
                'updated_at',
            ]
        )
        if bid.status != BidStatus.ACCEPTED:
            bid.status = BidStatus.ACCEPTED
            bid.reviewed_at = bid.reviewed_at or timezone.now()
            bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
            bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])
        log_audit(
            request.user,
            'intent_to_award_issued',
            tender,
            {
                'reference_number': tender.reference_number,
                'bid_id': bid_id,
                'recommended_vendor_id': awarded_vendor_id,
                'recommended_vendor_name': awarded_vendor_name,
                'cooling_off_until': tender.cooling_off_until.isoformat() if tender.cooling_off_until else None,
            },
        )

        send_email = request.data.get('send_email', True)
        _notify_intent_to_award(tender, ranking_payload, send_email)

        data = TenderSerializer(tender).data
        data['award_ranking'] = ranking_payload['rows']
        data['recommended_bid_id'] = recommended['bid_id']
        data['recommended_vendor_id'] = recommended['vendor_id']
        data['recommended_vendor_name'] = recommended['vendor_name']
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def award_ranking(self, request, pk=None):
        tender = self.get_object()
        ranking_payload = _build_award_ranking(tender)
        return Response(ranking_payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm_award(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Tender has already been awarded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.DISPUTED:
            return Response(
                {'detail': 'Cannot finalize award while a dispute is active. Resolve all challenges first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.CLOSED:
            return Response(
                {'detail': 'Closed tender cannot be awarded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status not in {TenderStatus.STANDSTILL, TenderStatus.EVALUATION}:
            return Response(
                {'detail': 'Final award can only be issued from Standstill or Evaluation state.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bid = tender.intent_to_award_bid
        if bid is None:
            return Response(
                {'detail': 'Intent to award must be issued before confirming the final award.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.cooling_off_until and timezone.now() < tender.cooling_off_until:
            return Response(
                {
                    'detail': 'Cooling-off period has not yet expired.',
                    'cooling_off_until': tender.cooling_off_until.isoformat(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            tender.status = TenderStatus.AWARDED
            tender.awarded_vendor_id = bid.vendor_id
            tender.awarded_vendor_name = bid.vendor_name
            tender.awarded_at = timezone.now()
            tender.cooling_off_until = None
            tender.dispute_started_at = None
            tender.save(
                update_fields=[
                    'status',
                    'awarded_vendor_id',
                    'awarded_vendor_name',
                    'awarded_at',
                    'cooling_off_until',
                    'dispute_started_at',
                    'updated_at',
                ]
            )
            if bid.status != BidStatus.AWARDED:
                bid.status = BidStatus.AWARDED
                bid.reviewed_at = bid.reviewed_at or timezone.now()
                bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
                bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])

            contract = self._ensure_award_contract(tender, bid, bid.vendor_id)

            log_audit(
                request.user,
                'tender_awarded',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'bid_id': str(bid.id),
                    'awarded_vendor_id': bid.vendor_id,
                    'awarded_vendor_name': bid.vendor_name,
                    'contract_id': str(contract.id) if contract else None,
                },
            )

        send_email = request.data.get('send_email', True)
        self._notify_award(tender, bid.vendor_id, bid.vendor_name, send_email)
        response_data = TenderSerializer(tender, context={'request': request}).data
        if contract:
            response_data['generated_contract'] = TenderContractSerializer(
                contract,
                context={'request': request},
            ).data
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pause_award(self, request, pk=None):
        """
        Pause the award process and freeze the cooling-off clock.
        Sets tender status to DISPUTED so challenges can be reviewed.
        """
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status == TenderStatus.DISPUTED:
            return Response(
                {'detail': 'Award process is already paused.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not tender.intent_to_award_at:
            return Response(
                {'detail': 'No intent to award has been issued yet. Nothing to pause.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Tender has already been awarded. Cannot pause.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = tender.status
        tender.status = TenderStatus.DISPUTED
        tender.dispute_started_at = timezone.now()
        tender.save(update_fields=['status', 'dispute_started_at', 'updated_at'])

        log_audit(
            request.user,
            'award_paused',
            tender,
            {
                'reference_number': tender.reference_number,
                'previous_status': old_status,
                'cooling_off_until': tender.cooling_off_until.isoformat() if tender.cooling_off_until else None,
                'dispute_started_at': tender.dispute_started_at.isoformat(),
            },
        )

        # Notify all bidders that award is paused
        self._notify_award_paused(tender)

        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def revoke_intent(self, request, pk=None):
        """
        Revoke the intent to award, clearing all award fields.
        Tender returns to EVALUATION status.
        """
        self._assert_write_permission()
        tender = self.get_object()

        if not tender.intent_to_award_at:
            return Response(
                {'detail': 'No intent to award has been issued yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Tender has already been awarded. Cannot revoke intent.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_bid_id = str(tender.intent_to_award_bid.id) if tender.intent_to_award_bid else None
        previous_vendor_id = tender.awarded_vendor_id
        previous_vendor_name = tender.awarded_vendor_name

        tender.intent_to_award_bid = None
        tender.intent_to_award_at = None
        tender.awarded_vendor_id = ''
        tender.awarded_vendor_name = ''
        tender.cooling_off_until = None
        tender.dispute_started_at = None
        tender.status = TenderStatus.EVALUATION
        tender.save(update_fields=[
            'intent_to_award_bid',
            'intent_to_award_at',
            'awarded_vendor_id',
            'awarded_vendor_name',
            'cooling_off_until',
            'dispute_started_at',
            'status',
            'updated_at',
        ])

        log_audit(
            request.user,
            'intent_revoked',
            tender,
            {
                'reference_number': tender.reference_number,
                'previous_bid_id': previous_bid_id,
                'previous_vendor_id': previous_vendor_id,
                'previous_vendor_name': previous_vendor_name,
            },
        )

        self._notify_intent_revoked(tender, previous_vendor_id, previous_vendor_name)

        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def create_challenge(self, request, pk=None):
        """
        Log a challenge/protest filed by an unsuccessful bidder.
        Sets tender to DISPUTED status and freezes cooling-off.
        """
        try:
            tender = Tender.objects.get(id=pk)
        except Tender.DoesNotExist:
            return Response(
                {'detail': 'Tender not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not tender.intent_to_award_at:
            return Response(
                {'detail': 'No intent to award has been issued. Cannot file a challenge.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Tender has already been awarded. Cannot file a challenge.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filed_by_vendor_id = str(request.data.get('filed_by_vendor_id') or '').strip()
        filed_by_vendor_name = str(request.data.get('filed_by_vendor_name') or '').strip()
        grounds = str(request.data.get('grounds') or '').strip()
        challenger_bid_id = request.data.get('challenger_bid_id')

        if not filed_by_vendor_id or not filed_by_vendor_name:
            return Response(
                {'detail': 'filed_by_vendor_id and filed_by_vendor_name are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not grounds:
            return Response(
                {'detail': 'grounds is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenger_bid = None
        if challenger_bid_id:
            try:
                challenger_bid = TenderBid.objects.get(id=challenger_bid_id, tender=tender)
            except TenderBid.DoesNotExist:
                return Response(
                    {'detail': 'Challenger bid not found for this tender.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        challenge = TenderChallenge.objects.create(
            tender=tender,
            filed_by_vendor_id=filed_by_vendor_id,
            filed_by_vendor_name=filed_by_vendor_name,
            challenger_bid=challenger_bid,
            grounds=grounds,
            status=ChallengeStatus.SUBMITTED,
        )

        # Auto-pause award if not already paused
        if tender.status != TenderStatus.DISPUTED:
            tender.status = TenderStatus.DISPUTED
            tender.dispute_started_at = timezone.now()
            tender.save(update_fields=['status', 'dispute_started_at', 'updated_at'])

        log_audit(
            request.user,
            'challenge_filed',
            tender,
            {
                'reference_number': tender.reference_number,
                'challenge_id': str(challenge.id),
                'filed_by_vendor_id': filed_by_vendor_id,
                'filed_by_vendor_name': filed_by_vendor_name,
            },
        )

        self._notify_award_paused(tender)

        from .serializers import TenderChallengeSerializer
        data = TenderChallengeSerializer(challenge, context={'request': request}).data
        data['tender'] = TenderSerializer(tender, context={'request': request}).data
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def challenges(self, request, pk=None):
        """List all challenges for this tender."""
        tender = self.get_object()
        challenges = tender.challenges.all()
        from .serializers import TenderChallengeSerializer
        return Response(
            TenderChallengeSerializer(challenges, many=True, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def resolve_challenge(self, request, pk=None):
        """
        Resolve a challenge with outcome 'upheld' or 'dismissed'.
        If upheld: revokes old intent, sets challenger as new recommended winner, resets cooling-off.
        If dismissed: returns tender to EVALUATION, resumes cooling-off clock.
        """
        self._assert_write_permission()
        tender = self.get_object()

        challenge_id = request.data.get('challenge_id')
        outcome = request.data.get('outcome', '').strip().lower()
        resolution_notes = request.data.get('resolution_notes', '')

        if not challenge_id:
            return Response(
                {'detail': 'challenge_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if outcome not in {'upheld', 'dismissed'}:
            return Response(
                {'detail': 'outcome must be "upheld" or "dismissed".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            challenge = tender.challenges.get(id=challenge_id)
        except TenderChallenge.DoesNotExist:
            return Response(
                {'detail': 'Challenge not found for this tender.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if challenge.status in {ChallengeStatus.UPHELD, ChallengeStatus.DISMISSED}:
            return Response(
                {'detail': f'Challenge has already been resolved as {challenge.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge.status = ChallengeStatus.UPHELD if outcome == 'upheld' else ChallengeStatus.DISMISSED
        challenge.reviewed_by = request.user
        challenge.resolution_notes = resolution_notes
        challenge.resolved_at = timezone.now()
        challenge.save(update_fields=['status', 'reviewed_by', 'resolution_notes', 'resolved_at'])

        if outcome == 'dismissed':
            remaining_seconds = 0
            if tender.dispute_started_at and tender.cooling_off_until:
                total_cooling = (tender.cooling_off_until - tender.dispute_started_at).total_seconds()
                elapsed = (timezone.now() - tender.dispute_started_at).total_seconds()
                remaining_seconds = max(0, total_cooling - elapsed)
            tender.cooling_off_until = timezone.now() + timedelta(seconds=remaining_seconds)
            tender.dispute_started_at = None
            tender.status = TenderStatus.STANDSTILL
            tender.save(update_fields=['cooling_off_until', 'dispute_started_at', 'status', 'updated_at'])

            log_audit(
                request.user,
                'challenge_dismissed',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'challenge_id': str(challenge.id),
                    'filed_by': challenge.filed_by_vendor_name,
                    'resolution_notes': resolution_notes,
                },
            )

            self._notify_challenge_dismissed(tender, challenge)

        elif outcome == 'upheld':
            previous_bid_id = str(tender.intent_to_award_bid.id) if tender.intent_to_award_bid else None
            previous_vendor_id = tender.awarded_vendor_id
            previous_vendor_name = tender.awarded_vendor_name

            challenger_bid = challenge.challenger_bid
            if not challenger_bid:
                return Response(
                    {'detail': 'Challenger bid is not set. Cannot re-issue intent.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tender.intent_to_award_bid = challenger_bid
            tender.intent_to_award_at = timezone.now()
            tender.awarded_vendor_id = challenger_bid.vendor_id
            tender.awarded_vendor_name = challenger_bid.vendor_name
            cooling_off_days = tender.cooling_off_days if tender.cooling_off_days is not None else 7
            tender.cooling_off_until = timezone.now() + timedelta(days=cooling_off_days)
            tender.dispute_started_at = None
            tender.status = TenderStatus.STANDSTILL
            tender.save(update_fields=[
                'intent_to_award_bid',
                'intent_to_award_at',
                'awarded_vendor_id',
                'awarded_vendor_name',
                'cooling_off_until',
                'dispute_started_at',
                'status',
                'updated_at',
            ])

            log_audit(
                request.user,
                'intent_revoked',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'previous_bid_id': previous_bid_id,
                    'previous_vendor_id': previous_vendor_id,
                    'previous_vendor_name': previous_vendor_name,
                    'reason': f'Challenge UPHELD — challenge_id={challenge.id}',
                },
            )
            log_audit(
                request.user,
                'challenge_upheld',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'challenge_id': str(challenge.id),
                    'filed_by': challenge.filed_by_vendor_name,
                    'new_intent_bid_id': str(challenger_bid.id),
                    'new_intent_vendor_id': challenger_bid.vendor_id,
                    'new_intent_vendor_name': challenger_bid.vendor_name,
                    'new_cooling_off_until': tender.cooling_off_until.isoformat(),
                    'resolution_notes': resolution_notes,
                },
            )
            log_audit(
                request.user,
                'intent_reissued',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'bid_id': str(challenger_bid.id),
                    'vendor_id': challenger_bid.vendor_id,
                    'vendor_name': challenger_bid.vendor_name,
                    'new_cooling_off_until': tender.cooling_off_until.isoformat(),
                },
            )

            if previous_vendor_id:
                self._notify_intent_revoked(tender, previous_vendor_id, previous_vendor_name)
            self._notify_challenge_upheld(tender, challenge, challenger_bid)

        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def update_cooling_off(self, request, pk=None):
        """
        Extend or shorten the cooling-off period for a tender with active intent to award.
        Body: { "action": "extend" | "shorten", "days": <positive integer> }
        """
        self._assert_write_permission()
        tender = self.get_object()

        action = request.data.get('action', '').strip().lower()
        days_str = request.data.get('days')

        if action not in {'extend', 'shorten'}:
            return Response(
                {'detail': 'action must be "extend" or "shorten".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            days = int(days_str)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'days must be a positive integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if days <= 0:
            return Response(
                {'detail': 'days must be a positive integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not tender.cooling_off_until:
            return Response(
                {'detail': 'Cooling-off period is not active. No intent to award has been issued.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Cannot adjust cooling-off after final award.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prev_cooling_off_until = tender.cooling_off_until

        if action == 'extend':
            tender.cooling_off_until += timedelta(days=days)
        else:  # shorten
            min_allowed = timezone.now() + timedelta(hours=1)
            new_cooling_off = tender.cooling_off_until - timedelta(days=days)
            if new_cooling_off < min_allowed:
                return Response(
                    {'detail': 'Shortening by that many days would leave less than 1 hour before the deadline.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            tender.cooling_off_until = new_cooling_off

        tender.save(update_fields=['cooling_off_until', 'updated_at'])

        log_audit(
            request.user,
            'cooling_off_adjusted',
            tender,
            {
                'reference_number': tender.reference_number,
                'action': action,
                'days': days,
                'previous_cooling_off_until': prev_cooling_off_until.isoformat(),
                'new_cooling_off_until': tender.cooling_off_until.isoformat(),
            },
        )

        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    def _notify_award_paused(self, tender: Tender):
        """Notify all bidders that the award process has been paused."""
        from rbf.users.models import User
        bids = TenderBid.objects.filter(tender=tender, status__in={
            BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED, BidStatus.AWARDED,
        }).values('vendor_id').distinct()
        vendor_ids = [b['vendor_id'] for b in bids]
        vendors = User.objects.filter(id__in=vendor_ids).only('id', 'email', 'full_name', 'username')
        title = f'Award Process Paused: {tender.reference_number}'
        body = (
            f"The award process for {tender.name} ({tender.reference_number}) has been paused.\n"
            f"A challenge has been filed and is under review.\n"
            f"You will be notified when the process resumes.\n"
        )
        for vendor in vendors:
            Notification.objects.create(
                recipient_id=str(vendor.id),
                recipient_name=vendor.full_name or vendor.username or vendor.email,
                type=NotificationChannel.IN_APP,
                event='award_paused',
                title=title,
                body=body,
                status=NotificationStatus.SENT,
                linked_entity_id=str(tender.id),
            )

    def _notify_intent_revoked(self, tender: Tender, vendor_id: str, vendor_name: str):
        """Notify the previously selected winner that intent has been revoked."""
        from rbf.users.models import User
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return
        title = f'Intent to Award Revoked: {tender.reference_number}'
        body = (
            f"The Intent to Award previously issued for {tender.name} ({tender.reference_number}) "
            f"has been revoked.\n"
            f"A challenge was upheld by the review committee.\n"
        )
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.IN_APP,
            event='intent_revoked',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

    def _notify_challenge_dismissed(self, tender: Tender, challenge: TenderChallenge):
        """Notify the challenging vendor that their challenge was dismissed."""
        from rbf.users.models import User
        try:
            vendor = User.objects.get(id=challenge.filed_by_vendor_id)
        except User.DoesNotExist:
            return
        title = f'Challenge Dismissed: {tender.reference_number}'
        body = (
            f"Your challenge for {tender.name} ({tender.reference_number}) has been reviewed and dismissed.\n"
            f"The award process will continue with the current intent to award.\n"
        )
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.IN_APP,
            event='challenge_dismissed',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

    def _notify_challenge_upheld(self, tender: Tender, challenge: TenderChallenge, new_bid: TenderBid):
        """Notify the challenging vendor that their challenge was upheld and they are the new winner."""
        from rbf.users.models import User
        try:
            vendor = User.objects.get(id=challenge.filed_by_vendor_id)
        except User.DoesNotExist:
            return
        cooling_date_text = tender.cooling_off_until.strftime('%Y-%m-%d %H:%M:%S') if tender.cooling_off_until else 'N/A'
        title = f'Challenge Upheld — New Intent to Award: {tender.reference_number}'
        body = (
            f"Your challenge for {tender.name} ({tender.reference_number}) has been upheld.\n"
            f"You are now the Best Evaluated Bidder.\n"
            f"Cooling-off period ends on: {cooling_date_text}\n"
            f"The final award will occur after the cooling-off period expires without further protest.\n"
        )
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.IN_APP,
            event='challenge_upheld_new_intent',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )
        # Also notify the new winner via email if possible
        if vendor.email:
            try:
                send_mail(
                    subject=title,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vendor.email],
                    fail_silently=True,
                )
            except Exception:
                pass

    def _notify_award(self, tender: Tender, vendor_id: str, vendor_name: str, send_email=True):
        """Send award notification to winning vendor"""
        from rbf.users.models import User

        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return

        email_subject = f"Congratulations! You have been awarded {tender.name}"
        email_body = (
            f"Congratulations! You have been awarded {tender.name}.\n\n"
            f"Please review and sign the Performance-Based Agreement to proceed.\n\n"
            f"Tender: {tender.name} ({tender.reference_number})\n"
            f"Department: {tender.department}\n"
            f"Awarded at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Next step: Log in, open the Contracting tab, review the generated agreement package, and sign the Performance-Based Agreement.\n"
        )

        email_enabled = send_email and bool(
            (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
            or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
        )

        # In-app notification
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.EMAIL if email_enabled else NotificationChannel.IN_APP,
            event='tender_awarded',
            title=email_subject,
            body=email_body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

        # Email notification
        if email_enabled and vendor.email:
            try:
                send_mail(
                    subject=email_subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vendor.email],
                    fail_silently=True,
                )
            except Exception:
                pass

    def _ensure_award_contract(self, tender: Tender, bid: TenderBid, vendor_id: str):
        """Create a generated contract on award if one doesn't exist."""
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return None

        existing = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if existing:
            if bid and not existing.bid_id:
                existing.bid = bid
            _populate_generated_contract_package(existing, tender, bid, vendor)
            existing.save(update_fields=[
                'bid',
                'generated_file',
                'annex_a_file',
                'annex_b_file',
                'annex_c_file',
                'annex_d_file',
                'annex_e_file',
                'updated_at',
            ])
            return existing

        reference_number = f"CTR-{tender.reference_number}-{vendor_id}"
        contract = TenderContract.objects.create(
            tender=tender,
            bid=bid,
            vendor_id=vendor_id,
            vendor_name=vendor.full_name or vendor.username,
            vendor_email=vendor.email or '',
            reference_number=reference_number,
            template_name='Performance-Based Agreement',
            status=ContractStatus.GENERATED,
        )
        _populate_generated_contract_package(contract, tender, bid, vendor)
        contract.save(update_fields=[
            'bid',
            'generated_file',
            'annex_a_file',
            'annex_b_file',
            'annex_c_file',
            'annex_d_file',
            'annex_e_file',
            'updated_at',
        ])
        log_audit(self.request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'Performance-Based Agreement Ready: {tender.reference_number}',
            body=f'Congratulations! You have been awarded {tender.name}. Please review and sign the Performance-Based Agreement to proceed.',
            linked_entity_id=str(tender.id),
        )
        return contract


    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a tender, preventing further bids"""
        self._assert_write_permission()
        tender = self.get_object()
        
        if tender.status == TenderStatus.CLOSED:
            return Response(
                {'detail': 'Tender is already closed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        tender.status = TenderStatus.CLOSED
        tender.closed_at = timezone.now()
        tender.save(update_fields=['status', 'closed_at', 'updated_at'])
        log_audit(
            request.user,
            'tender_closed',
            tender,
            {'reference_number': tender.reference_number},
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def verify_security(self, request, pk=None):
        """Verify tender security deposit"""
        self._assert_write_permission()
        tender = self.get_object()
        
        if not tender.tender_security_required:
            return Response(
                {'detail': 'Security deposit not required for this tender.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        tender.security_deposit_verified = True
        tender.security_deposit_verified_at = timezone.now()
        tender.save(update_fields=['security_deposit_verified', 'security_deposit_verified_at', 'updated_at'])
        
        log_audit(
            request.user,
            'tender_security_verified',
            tender,
            {'reference_number': tender.reference_number},
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def security_verification_search(self, request):
        """Search tenders for security verification"""
        self._assert_write_permission()
        
        # Filter by awarded tenders not yet verified
        queryset = Tender.objects.filter(
            status=TenderStatus.AWARDED,
            security_deposit_verified=False
        ).order_by('-awarded_at')
        
        # Apply search filters
        search_key = request.query_params.get('search_key', '')
        if search_key:
            queryset = queryset.filter(
                reference_number__icontains=search_key
            ) | queryset.filter(name__icontains=search_key)
        
        # Apply date range filter
        award_date_from = request.query_params.get('award_date_from')
        award_date_to = request.query_params.get('award_date_to')
        
        if award_date_from:
            queryset = queryset.filter(awarded_at__gte=award_date_from)
        if award_date_to:
            queryset = queryset.filter(awarded_at__lte=award_date_to)
        
        sort_by = request.query_params.get('sort_by', '-awarded_at')
        queryset = queryset.order_by(sort_by)
        
        limit = int(request.query_params.get('limit', 50))
        queryset = queryset[:limit]
        
        serializer = TenderListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TenderBidViewSet(viewsets.ModelViewSet):
    """ViewSet for managing vendor bids/submissions"""
    queryset = TenderBid.objects.all().order_by('-updated_at', '-submitted_at', '-created_at')
    serializer_class = TenderBidSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tender', 'vendor_id', 'status']
    search_fields = ['vendor_name', 'vendor_email', 'tender__reference_number']
    ordering_fields = ['submitted_at', 'updated_at', 'bid_amount']

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.VENDOR:
            _backfill_stage_two_drafts_for_vendor(str(user.id))
            return TenderBid.objects.filter(vendor_id=str(user.id)).order_by('-updated_at', '-submitted_at', '-created_at')
        return TenderBid.objects.all().order_by('-updated_at', '-submitted_at', '-created_at')

    def _assert_vendor_submission_access(self, request, tender: Tender, bid: TenderBid | None = None):
        if request.user.role != UserRole.VENDOR:
            raise ValidationError({'detail': 'Only vendors can submit bids.'})
        if is_vendor_restricted(request.user):
            raise ValidationError({'detail': 'Your vendor account is suspended or blacklisted. Bid submission is disabled.'})
        latest_prequalification = _latest_vendor_prequalification(str(request.user.id))
        if latest_prequalification is None or latest_prequalification.status != PrequalificationStatus.APPROVED:
            raise ValidationError({'detail': 'Complete pre-qualification first'})
        if tender.status != TenderStatus.PUBLISHED:
            raise ValidationError({'tender': 'Tender is not open for bidding.'})
        deadline = tender.last_date_submission or tender.deadline
        if _uses_hard_deadline(tender) and deadline and timezone.now() >= deadline:
            raise ValidationError({'tender': 'Bidding deadline has passed.'})
        existing_submitted_bid = TenderBid.objects.filter(
            tender=tender,
            vendor_id=str(request.user.id),
        ).exclude(status__in={BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN})
        if bid is not None:
            if bid.stage_two_unlocked and not _has_stage_two_shortlist_access(bid):
                raise ValidationError({'detail': 'Only shortlisted vendors can submit Stage 2 proposals.'})
            existing_submitted_bid = existing_submitted_bid.exclude(id=bid.id)
            if bid.stage_two_source_bid_id:
                existing_submitted_bid = existing_submitted_bid.exclude(id=bid.stage_two_source_bid_id)
        if existing_submitted_bid.exists():
            raise ValidationError({'tender': 'You have already submitted a bid for this tender.'})

    def _assert_stage_one_review_permission(self, request, bid: TenderBid):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can decide Stage 1 submissions.')
        if normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) != 'pre_qualification':
            raise ValidationError({'detail': 'Stage 1 review actions only apply to pre-qualification bids.'})

    def create(self, request, *args, **kwargs):
        """Submit a bid for a tender"""
        tender_id = request.data.get('tender')
        if not tender_id:
            raise ValidationError({'tender': 'Tender ID is required.'})
        
        try:
            tender = Tender.objects.get(id=tender_id)
        except Tender.DoesNotExist:
            raise ValidationError({'tender': 'Tender not found.'})
        self._assert_vendor_submission_access(request, tender)

        bid_status = request.data.get('status') or BidStatus.DRAFT
        if bid_status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'status': 'Invalid status for bid submission.'})

        latest_version = (
            TenderBid.objects.filter(tender=tender, vendor_id=str(request.user.id))
            .order_by('-version_number')
            .values_list('version_number', flat=True)
            .first()
        )
        next_version = (latest_version or 0) + 1

        payload = request.data.copy()
        payload['vendor_id'] = str(request.user.id)
        payload['vendor_name'] = request.user.full_name or request.user.username
        payload['vendor_email'] = request.user.email
        payload['version_number'] = next_version
        payload['status'] = bid_status
        payload['stage'] = tender_stage_label(tender.stage_type)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        bid = serializer.instance
        headers = self.get_success_headers(serializer.data)
        if bid.status == BidStatus.SUBMITTED:
            bid.submitted_at = timezone.now()
            bid.save(update_fields=['submitted_at', 'updated_at'])
            self._record_bid_submission(request, bid)
        return Response(
            TenderBidSerializer(bid, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        bid = self.get_object()
        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can update this bid.')
        if bid.status not in {BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Submitted bids are locked. Create or edit a draft before final submission.'})
        self._assert_vendor_submission_access(request, bid.tender, bid=bid)

        submitting = self._is_submitting(bid, request)
        
        payload = {}
        for key in request.data.keys():
            value = request.data.getlist(key) if len(request.data.getlist(key)) > 1 else request.data.get(key)
            payload[key] = value
        
        payload['stage'] = tender_stage_label('site_specific' if bid.stage_two_unlocked else bid.tender.stage_type)
        
        if submitting:
            latest_version = (
                TenderBid.objects.filter(tender=bid.tender, vendor_id=str(request.user.id))
                .order_by('-version_number')
                .values_list('version_number', flat=True)
                .first()
            )
            next_version = (latest_version or 0) + 1
            payload['version_number'] = next_version
            payload['status'] = BidStatus.SUBMITTED
        
        serializer = self.get_serializer(bid, data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        bid.refresh_from_db()
        if submitting:
            bid.submitted_at = timezone.now()
            bid.status = BidStatus.SUBMITTED
            bid.save(update_fields=['submitted_at', 'status', 'updated_at'])
            self._record_bid_submission(request, bid)
        return Response(TenderBidSerializer(bid, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        bid = self.get_object()
        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can update this bid.')
        if bid.status not in {BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Submitted bids are locked. Create or edit a draft before final submission.'})
        self._assert_vendor_submission_access(request, bid.tender, bid=bid)

        submitting = self._is_submitting(bid, request)
        
        payload = {}
        for key in request.data.keys():
            value = request.data.getlist(key) if len(request.data.getlist(key)) > 1 else request.data.get(key)
            payload[key] = value
        
        payload['stage'] = tender_stage_label('site_specific' if bid.stage_two_unlocked else bid.tender.stage_type)
        
        if submitting:
            latest_version = (
                TenderBid.objects.filter(tender=bid.tender, vendor_id=str(request.user.id))
                .order_by('-version_number')
                .values_list('version_number', flat=True)
                .first()
            )
            next_version = (latest_version or 0) + 1
            payload['version_number'] = next_version
            payload['status'] = BidStatus.SUBMITTED
        
        serializer = self.get_serializer(bid, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        bid.refresh_from_db()
        if submitting:
            bid.submitted_at = timezone.now()
            bid.status = BidStatus.SUBMITTED
            bid.save(update_fields=['submitted_at', 'status', 'updated_at'])
            self._record_bid_submission(request, bid)
        return Response(TenderBidSerializer(bid, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        bid = self.get_object()
        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can delete this bid.')
        if bid.status not in {BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN}:
            return Response(
                {'detail': 'Only draft or withdrawn bids can be deleted. Please contact the RBF Management Team to withdraw a submitted bid.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    def _is_submitting(self, bid: TenderBid, request) -> bool:
        target_status = request.data.get('status')
        return target_status == BidStatus.SUBMITTED and bid.status in {BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.SUBMITTED}

    def _record_bid_submission(self, request, bid: TenderBid):
        log_audit(
            request.user,
            'bid_submitted',
            bid,
            {
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'tender_id': str(bid.tender_id),
                'stage': bid.stage,
                'amount': str(bid.bid_amount or ''),
                'version': bid.version_number,
            },
        )
        AuditLogger.log(
            'bid_submitted',
            'tenders',
            bid.id,
            'tender_bid',
            notes=f'Vendor {bid.vendor_id} submitted version {bid.version_number} for tender {bid.tender.reference_number}.',
        )
        rmt_users = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        message = f'New bid submitted by {bid.vendor_name} for {bid.tender.name} — LSL {bid.bid_amount or 0}'
        for rmt_user in rmt_users:
            NotificationService.send(
                recipient_id=str(rmt_user.id),
                title='New Bid Submitted',
                body=message,
                module='tenders',
                record_id=bid.id,
            )
        Notification.objects.create(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            type=NotificationChannel.IN_APP,
            event='bid_submitted',
            title=f'Bid Submitted: {bid.tender.reference_number}',
            body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
            linked_entity_id=str(bid.tender.id),
        )

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Mark bid as under review"""
        bid = self.get_object()
        
        if bid.status != BidStatus.SUBMITTED:
            return Response(
                {'detail': 'Only submitted bids can be reviewed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        bid.status = BidStatus.UNDER_REVIEW
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        if bid.tender.status == TenderStatus.PUBLISHED:
            deadline = bid.tender.last_date_submission or bid.tender.deadline
            if _uses_hard_deadline(bid.tender) and deadline and timezone.now() >= deadline:
                bid.tender.status = TenderStatus.EVALUATION
                bid.tender.save(update_fields=['status', 'updated_at'])
        log_audit(request.user, 'bid_under_review', bid, {'tender_id': str(bid.tender_id)})
        
        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit a draft bid (final submission)"""
        bid = self.get_object()

        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can submit this bid.')

        if bid.status not in {BidStatus.DRAFT, BidStatus.REVISION_REQUIRED}:
            return Response(
                {'detail': 'Only draft or revision-required bids can be submitted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deadline = bid.tender.last_date_submission or bid.tender.deadline
        if _uses_hard_deadline(bid.tender) and deadline and timezone.now() >= deadline:
            return Response(
                {'detail': 'Bidding deadline has passed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if is_site_specific_stage(bid.tender.stage_type or bid.stage):
            if not bid.technical_proposal_file or not bid.financial_proposal_file:
                return Response(
                    {'detail': 'Technical and financial proposal files are required for site-specific bids.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not bid.boq_file:
                return Response(
                    {'detail': 'BOQ file is required for site-specific bids.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        bid.status = BidStatus.SUBMITTED
        bid.submitted_at = timezone.now()
        bid.save(update_fields=['status', 'submitted_at', 'updated_at'])
        log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(bid.tender_id), 'version': bid.version_number})
        Notification.objects.create(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            type=NotificationChannel.IN_APP,
            event='bid_submitted',
            title=f'Bid Submitted: {bid.tender.reference_number}',
            body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
            linked_entity_id=str(bid.tender.id),
        )

        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a bid"""
        bid = self.get_object()
        self._assert_stage_one_review_permission(request, bid)

        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be accepted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bid.status = BidStatus.ACCEPTED
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        log_audit(request.user, 'bid_accepted', bid, {'tender_id': str(bid.tender_id)})

        if normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) == 'pre_qualification':
            draft = _ensure_stage_two_draft(bid)
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='stage_one_shortlisted',
                title=f'Shortlisted: {bid.tender.reference_number}',
                body='Congratulations! You have been shortlisted. Submit your full proposal to proceed.',
                linked_entity_id=str(bid.tender.id),
            )
            log_audit(
                request.user,
                'stage_one_shortlisted',
                bid,
                {'tender_id': str(bid.tender_id), 'draft_bid_id': str(draft.id)},
            )
            return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

        try:
            from rbf.users.models import User
            User.objects.get(id=bid.vendor_id)
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_accepted',
                title=f'Bid Accepted: {bid.tender.reference_number}',
                body=f'Your bid for tender {bid.tender.name} has been accepted.',
                linked_entity_id=str(bid.tender.id),
            )
        except Exception:
            pass

        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def partial_conformity(self, request, pk=None):
        bid = self.get_object()
        self._assert_stage_one_review_permission(request, bid)

        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be marked for revision.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        revision_reason = str(request.data.get('rejection_reason') or request.data.get('revision_reason') or '').strip()
        if not revision_reason:
            raise ValidationError({'rejection_reason': 'Feedback is required for partial conformity.'})

        bid.status = BidStatus.REVISION_REQUIRED
        bid.rejection_reason = revision_reason
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'reviewed_by', 'updated_at'])
        log_audit(request.user, 'bid_revision_required', bid, {'tender_id': str(bid.tender_id), 'reason': revision_reason})
        Notification.objects.create(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            type=NotificationChannel.IN_APP,
            event='bid_revision_required',
            title=f'Revision Required: {bid.tender.reference_number}',
            body=f'Partial conformity identified. Please revise and resubmit. Feedback: {revision_reason}',
            linked_entity_id=str(bid.tender.id),
        )
        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a bid with reason"""
        bid = self.get_object()
        self._assert_stage_one_review_permission(request, bid)

        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be rejected.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rejection_reason = request.data.get('rejection_reason', '')
        if not rejection_reason:
            raise ValidationError({'rejection_reason': 'Reason for rejection is required.'})

        bid.status = BidStatus.REJECTED
        bid.rejection_reason = rejection_reason
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'reviewed_by'])
        log_audit(request.user, 'bid_rejected', bid, {'tender_id': str(bid.tender_id), 'reason': rejection_reason})

        try:
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_rejected',
                title=f'Bid Not Accepted: {bid.tender.reference_number}',
                body=f'Your bid for tender {bid.tender.name} was not accepted. Reason: {rejection_reason}',
                linked_entity_id=str(bid.tender.id),
            )
        except Exception:
            pass

        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)


class TenderBidEvaluationViewSet(viewsets.ModelViewSet):
    queryset = TenderBidEvaluation.objects.select_related('bid', 'evaluator').all().order_by('-created_at')
    serializer_class = TenderBidEvaluationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['bid', 'status']
    search_fields = ['bid__vendor_name', 'bid__tender__reference_number']
    ordering_fields = ['created_at', 'total_score']

    def get_queryset(self):
        user = self.request.user
        qs = TenderBidEvaluation.objects.select_related('bid', 'evaluator')
        if user.role == UserRole.VENDOR:
            return qs.filter(bid__vendor_id=str(user.id))
        return qs

    def _assert_eval_permission(self, request):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC}:
            raise PermissionDenied('Only the RBF Management Team or TAC members can score bids.')

    def create(self, request, *args, **kwargs):
        self._assert_eval_permission(request)
        data = request.data.copy()
        data['evaluator'] = request.user.id
        existing = TenderBidEvaluation.objects.filter(
            bid_id=data.get('bid'),
            evaluator=request.user,
        ).order_by('-created_at').first()
        if existing is not None:
            serializer = self.get_serializer(existing, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            evaluation = serializer.instance
            log_audit(request.user, 'bid_evaluated', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score, 'mode': 'updated_existing'})
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        evaluation = serializer.instance
        log_audit(request.user, 'bid_evaluated', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score, 'mode': 'created'})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        self._assert_eval_permission(request)
        evaluation = self.get_object()
        if request.user.role != UserRole.ADMIN and str(getattr(evaluation, 'evaluator_id', '')) != str(request.user.id):
            raise PermissionDenied('You can only edit your own evaluation record.')
        return super().update(request, *args, **kwargs)


class TenderContractViewSet(viewsets.ModelViewSet):
    queryset = TenderContract.objects.select_related('tender', 'bid').all().order_by('-generated_at')
    serializer_class = TenderContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tender', 'status', 'vendor_id']
    search_fields = ['reference_number', 'vendor_name', 'tender__reference_number']
    ordering_fields = ['generated_at']
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]

    def get_queryset(self):
        user = self.request.user
        qs = TenderContract.objects.select_related('tender', 'bid')
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor_id=str(user.id))
        return qs

    def _assert_admin_permission(self, request):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team or Platform Administrators can manage contracts.')

    @action(detail=False, methods=['post'])
    def generate(self, request):
        self._assert_admin_permission(request)
        tender_id = request.data.get('tender')
        bid_id = request.data.get('bid')
        if not tender_id:
            raise ValidationError({'tender': 'Tender ID is required.'})
        try:
            tender = Tender.objects.get(id=tender_id)
        except Tender.DoesNotExist:
            raise ValidationError({'tender': 'Tender not found.'})
        if tender.status != TenderStatus.AWARDED:
            raise ValidationError({'tender': 'Tender must be awarded before generating a contract.'})

        bid = None
        if bid_id:
            try:
                bid = TenderBid.objects.get(id=bid_id, tender=tender)
            except TenderBid.DoesNotExist:
                raise ValidationError({'bid': 'Bid not found for this tender.'})

        vendor_id = str(request.data.get('vendor_id') or (bid.vendor_id if bid else tender.awarded_vendor_id))
        if not vendor_id:
            raise ValidationError({'vendor_id': 'Vendor ID is required.'})
        if tender.awarded_vendor_id and vendor_id != str(tender.awarded_vendor_id):
            raise ValidationError({'vendor_id': 'Vendor must match the awarded vendor for this tender.'})
        if bid and vendor_id != str(bid.vendor_id):
            raise ValidationError({'vendor_id': 'Vendor must match the selected bid vendor.'})
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            raise ValidationError({'vendor_id': 'Vendor not found.'})

        existing = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if existing:
            if bid:
                existing.bid = bid
            source_bid = bid or existing.bid
            update_fields = ['bid', 'updated_at']
            if source_bid:
                _populate_generated_contract_package(existing, tender, source_bid, vendor)
                update_fields.extend([
                    'generated_file',
                    'annex_a_file',
                    'annex_b_file',
                    'annex_c_file',
                    'annex_d_file',
                    'annex_e_file',
                ])
            existing.save(update_fields=update_fields)
            return Response(TenderContractSerializer(existing, context={'request': request}).data, status=status.HTTP_200_OK)

        reference_number = f"CTR-{tender.reference_number}-{vendor_id}"
        contract = TenderContract.objects.create(
            tender=tender,
            bid=bid,
            vendor_id=vendor_id,
            vendor_name=vendor.organization_name or vendor.full_name or vendor.username,
            vendor_email=vendor.email or '',
            reference_number=reference_number,
            template_name=str(request.data.get('template_name') or 'Performance-Based Agreement'),
            status=ContractStatus.GENERATED,
        )
        if bid:
            _populate_generated_contract_package(contract, tender, bid, vendor)
            contract.save(update_fields=[
                'generated_file',
                'annex_a_file',
                'annex_b_file',
                'annex_c_file',
                'annex_d_file',
                'annex_e_file',
                'updated_at',
            ])
        log_audit(request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'PBA Package Ready: {tender.reference_number}',
            body='The Performance-Based Agreement and annex package are ready for vendor signature.',
            linked_entity_id=str(tender.id),
        )
        return Response(TenderContractSerializer(contract, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract = self.get_object()
        _hydrate_contract_from_bid(contract)
        if request.user.role != UserRole.VENDOR or contract.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the awarded vendor can sign this contract.')
        if contract.tender.awarded_vendor_id and str(contract.tender.awarded_vendor_id) != str(contract.vendor_id):
            raise ValidationError({'detail': 'Only the awarded vendor can sign this contract.'})
        signed_file = request.data.get('signed_file')
        if not signed_file:
            raise ValidationError({'signed_file': 'Signed contract file is required.'})
        signed_file_name = str(getattr(signed_file, 'name', '') or '').lower()
        if not signed_file_name.endswith('.pdf'):
            raise ValidationError({'signed_file': 'Signed contract must be uploaded as a PDF.'})
        if getattr(signed_file, 'size', 0) > 10 * 1024 * 1024:
            raise ValidationError({'signed_file': 'Signed contract PDF must not exceed 10MB.'})
        missing_annexes = _missing_contract_annexes(contract)
        if missing_annexes:
            raise ValidationError({'annexes': f"The contract package is incomplete. Missing: {', '.join(missing_annexes)}."})
        contract.signed_file = signed_file
        contract.signed_at = timezone.now()
        contract.status = ContractStatus.SUBMITTED
        contract.signature_status = ContractSignatureStatus.UPLOADED
        contract.save(update_fields=['signed_file', 'signed_at', 'status', 'signature_status', 'updated_at'])
        log_audit(request.user, 'contract_signed', contract, {'tender_id': str(contract.tender_id)})
        admins = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        if admins:
            notifications = []
            for admin in admins:
                notifications.append(
                    Notification(
                        recipient_id=str(admin.id),
                        recipient_name=admin.full_name or admin.username,
                        type=NotificationChannel.IN_APP,
                        event='contract_signed',
                        title=f'Contract Uploaded: {contract.reference_number}',
                        body=f'A signed contract package was uploaded by {contract.vendor_name}. Please review and finalize.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(contract.tender_id),
                    )
                )
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        self._assert_admin_permission(request)
        contract = self.get_object()
        tender = contract.tender
        _hydrate_contract_from_bid(contract)
        if not contract.signed_file:
            return Response({'detail': 'Signed contract file is required before approval.'}, status=status.HTTP_400_BAD_REQUEST)
        if contract.status == ContractStatus.GENERATED:
            contract.status = ContractStatus.SUBMITTED
            contract.save(update_fields=['status', 'updated_at'])
        if contract.status not in {ContractStatus.SUBMITTED, ContractStatus.SIGNED}:
            return Response({'detail': 'Contract must be submitted by the vendor before approval.'}, status=status.HTTP_400_BAD_REQUEST)
        contract.status = ContractStatus.APPROVED
        contract.signature_status = ContractSignatureStatus.APPROVED
        contract.approved_at = timezone.now()
        contract.approved_by = request.user.full_name or request.user.username
        contract.save(update_fields=['status', 'signature_status', 'approved_at', 'approved_by', 'updated_at'])
        log_audit(request.user, 'contract_approved', contract, {'record_type': 'contract', 'module': 'contracts'})
        Notification.objects.create(
            recipient_id=contract.vendor_id,
            recipient_name=contract.vendor_name,
            type=NotificationChannel.IN_APP,
            event='contract_approved',
            title=f'Contract Approved: {tender.reference_number}',
            body='Your contract has been approved. RMT can now assign milestones and create the project.',
            linked_entity_id=str(tender.id),
        )
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'], url_path='assign')
    def assign(self, request, pk=None):
        contract = self.get_object()
        if request.user.role != UserRole.RBF_OFFICIAL:
            raise PermissionDenied('Only RMT can assign projects from approved contracts.')
        if contract.status != ContractStatus.APPROVED:
            raise ValidationError({'detail': 'Contract status must be approved before assigning milestones.'})
        existing_project = Project.objects.filter(contract=contract).order_by('-id').first()
        if existing_project:
            raise ValidationError({'detail': 'This contract already has an assigned project.'})
        if request.method.lower() == 'get':
            contract_value = _contract_value(contract)
            defaults = _assignment_defaults(contract)
            technology_type = defaults['technology_type']
            technology_choices = _assignment_technology_choices(contract)
            bid_preferred_district = str(getattr(contract.bid, 'preferred_district', '') or '').strip() if contract.bid else ''
            return Response({
                'contract': TenderContractSerializer(contract, context={'request': request}).data,
                'contract_details': {
                    'contract_ref': contract.reference_number,
                    'vendor_name': contract.vendor_name,
                    'technology': technology_type,
                    'bid_amount': str(contract_value),
                    'signed_date': contract.signed_at.isoformat() if contract.signed_at else None,
                    'bid_preferred_district': bid_preferred_district,
                },
                'assignment_defaults': defaults,
                'assignment_fields': {
                    'project_duration_months': [6, 12, 18],
                    'technology_type': technology_choices,
                    'technology_type_read_only': len(technology_choices) == 1,
                    'verification_method': [choice for choice, _label in Project._meta.get_field('verification_method').choices],
                    'district_zone': contract.tender.target_districts if contract.tender.target_districts else LESOTHO_DISTRICTS,
                    'district_zones': contract.tender.target_districts if contract.tender.target_districts else LESOTHO_DISTRICTS,
                },
                'disbursement_preview': defaults['disbursement_preview'],
            })
        if not contract.signed_file:
            raise ValidationError({'detail': 'Signed contract file is required before assigning a project.'})
        serializer = ProjectAssignmentSerializer(data=request.data, context={'contract': contract})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            project = _create_project_assignment(request, contract, serializer.validated_data)
        project_url = request.build_absolute_uri(reverse('project-detail', args=[project.id]))
        return Response(
            {
                'message': f'Project PRJ-{project.id} assigned successfully.',
                'project_id': project.id,
                'redirect_url': project_url,
                'project_detail_url': project_url,
                'project': ProjectSerializer(project, context={'request': request}).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        self._assert_admin_permission(request)
        contract = self.get_object()
        reason = str(request.data.get('rejection_reason') or '').strip()
        if not reason:
            raise ValidationError({'rejection_reason': 'Rejection reason is required.'})
        contract.status = ContractStatus.REJECTED
        contract.rejection_reason = reason
        contract.approved_at = timezone.now()
        contract.approved_by = request.user.full_name or request.user.username
        contract.save(update_fields=['status', 'rejection_reason', 'approved_at', 'approved_by', 'updated_at'])
        log_audit(request.user, 'contract_rejected', contract, {'reason': reason})
        Notification.objects.create(
            recipient_id=contract.vendor_id,
            recipient_name=contract.vendor_name,
            type=NotificationChannel.IN_APP,
            event='contract_rejected',
            title=f'Contract Rejected: {contract.tender.reference_number}',
            body=f'Your contract was rejected. Reason: {reason}',
            linked_entity_id=str(contract.tender.id),
        )
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)


class NoticeViewSet(viewsets.ModelViewSet):
    queryset = Notice.objects.all().order_by('-is_pinned', '-published_at')
    serializer_class = NoticeSerializer
    pagination_class = TenderPagination
    permission_classes = []

    def get_queryset(self):
        qs = Notice.objects.all().order_by('-is_pinned', '-published_at')
        status = self.request.query_params.get('status')
        category = self.request.query_params.get('category')
        if status:
            qs = qs.filter(status=status)
        else:
            qs = qs.filter(status='published')
        if category and category != 'All':
            qs = qs.filter(category=category)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return NoticeListSerializer
        return NoticeSerializer

    def _assert_write_permission(self):
        user = self.request.user
        if not user.is_authenticated or user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only RBF Officials can manage notices.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        self._assert_write_permission()
        try:
            notice = Notice.objects.get(pk=pk)
            notice.status = 'published'
            notice.published_at = timezone.now()
            notice.save(update_fields=['status', 'published_at', 'updated_at'])
            return Response(NoticeSerializer(notice).data, status=status.HTTP_200_OK)
        except Notice.DoesNotExist:
            return Response({'error': 'Notice not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        self._assert_write_permission()
        try:
            notice = Notice.objects.get(pk=pk)
            notice.status = 'draft'
            notice.published_at = None
            notice.save(update_fields=['status', 'published_at', 'updated_at'])
            return Response(NoticeSerializer(notice).data, status=status.HTTP_200_OK)
        except Notice.DoesNotExist:
            return Response({'error': 'Notice not found'}, status=status.HTTP_404_NOT_FOUND)
