from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS, BasePermission
from rbf.common.permissions import has_module_permission
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
import json
import re
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from django.conf import settings
from django.db import transaction
from django.db import models
from django.db import IntegrityError
from django.db.models import Q, Count
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, DateFromToRangeFilter, RangeFilter, CharFilter, ChoiceFilter
from .models import (
    Tender,
    TenderViewLog,
    TenderStatus,
    TenderBid,
    TenderBidSite,
    BidStatus,
    TenderBidEvaluation,
    EvaluationStatus,
    EvaluationSubmissionStatus,
    EvaluationRevisionAction,
    TenderBidEvaluationRevision,
    EvaluationConflictOfInterest,
    ConflictOfInterestRelationship,
    TenderContract,
    ContractStatus,
    ContractSignatureStatus,
    TenderChallenge,
    ChallengeStatus,
    ChallengeCategory,
    ChallengeDocument,
    ChallengeEvent,
    Notice,
    BidStage,
    ProcurementWorkflow,
    PublishApprovalStatus,
    TenderLot,
    TenderBidLotOffer,
    TenderEvaluationCommitteeMember,
    TenderInvitedVendor,
    ProcurementMethod,
    EvaluationStage,
    TenderAwardRecommendation,
    IntentToAwardRequest,
    IntentAwardRequestStatus,
)
from .serializers import (
    TenderSerializer,
    TenderBidSerializer,
    TenderListSerializer,
    TenderBidEvaluationSerializer,
    TenderContractSerializer,
    ProjectAssignmentSerializer,
    normalize_tender_stage,
    normalize_bid_stage,
    bid_stage_label,
    workflow_has_eoi_stage,
    workflow_is_combined_style,
    is_site_specific_stage,
    tender_stage_label,
    NoticeSerializer,
    NoticeListSerializer,
    TenderChallengeSerializer,
    ChallengeDocumentSerializer,
    ChallengeEventSerializer,
    ChallengeCreateSerializer,
    TenderEvaluationCommitteeMemberSerializer,
    TenderInvitedVendorSerializer,
    TenderAwardRecommendationSerializer,
    IntentToAwardRequestSerializer,
)
from .pba_pdf import generate_contract_pdf
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.users.models import User, PlatformConfiguration, FinancialScoringFormula
from rbf.users.blacklisting import is_vendor_restricted
from rbf.common.urls import build_frontend_url
from rbf.projects.models import Project, Milestone, MilestoneStatus, ProjectStatus, VerificationMethod, AuditLog
from rbf.projects.audit import log_audit, AuditLogger
from rbf.projects.integrations import SyncToProspectJob, queue_project_targets_sync
from rbf.projects.serializers import ProjectSerializer, AuditLogSerializer
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.notifications.services import NotificationService, email_configured


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


def _invite_gated_procurement_values() -> set:
    """Every procurement method value (built-in or Super-Admin-added custom) whose
    vendor pool is a hand-picked invite list — Restricted, Limited/Single-Source,
    and RFQ all share the same TenderInvitedVendor gate."""
    config = PlatformConfiguration.objects.order_by('id').first()
    if config is None:
        return {ProcurementMethod.RESTRICTED}
    return config.invite_gated_procurement_method_values()


def _framework_procurement_values() -> set:
    """Every procurement method value whose vendor pool is gated by pre-qualification
    tier/technology match instead of an invite list (Framework / Pre-Qualified Pool)."""
    return _platform_configuration().framework_procurement_method_values()


def _limited_procurement_values() -> set:
    """Every procurement method value capped to exactly one invited vendor
    (Limited Tendering / Single-Source / Direct Contracting)."""
    return _platform_configuration().limited_procurement_method_values()


def _vendor_tier_number(tier: str):
    match = re.search(r'\d+', str(tier or ''))
    return int(match.group()) if match else None


def _vendor_meets_framework_requirements(tender: Tender, prequalification) -> bool:
    """Framework/Pre-Qualified Pool eligibility: the vendor's own approved
    pre-qualification tier must be at least the tender's minimum_service_tier
    (blank = no requirement), and if the tender lists technology_types, the
    vendor's own technology_types must overlap it (blank tender list = no
    requirement)."""
    if prequalification is None:
        return False
    min_tier = _vendor_tier_number(getattr(tender, 'minimum_service_tier', ''))
    if min_tier is not None:
        vendor_tier = _vendor_tier_number(getattr(prequalification, 'tech_tier', ''))
        if vendor_tier is None or vendor_tier < min_tier:
            return False
    tender_tech_types = set(getattr(tender, 'technology_types', None) or [])
    if tender_tech_types:
        vendor_tech_types = set(getattr(prequalification, 'technology_types', None) or [])
        if not (tender_tech_types & vendor_tech_types):
            return False
    return True


def _normalized_application_type(tender: Tender) -> str:
    return str(getattr(tender, 'application_type', '') or '').strip().lower()


def _uses_hard_deadline(tender: Tender) -> bool:
    return _normalized_application_type(tender) == APPLICATION_WINDOW


def _auto_close_tender_on_deadline(tender: Tender) -> bool:
    """Automatically close a published tender once its submission deadline passes.

    Only application-window tenders auto-close on their deadline; access-window
    tenders remain published until the RMT closes them manually.

    Returns True when the tender was transitioned to CLOSED.
    """
    if tender.status != TenderStatus.PUBLISHED:
        return False
    if not _uses_hard_deadline(tender):
        return False
    deadline = tender.master_deadline()
    if deadline and timezone.now() >= deadline:
        tender.status = TenderStatus.CLOSED
        tender.closed_at = tender.closed_at or timezone.now()
        tender.save(update_fields=['status', 'closed_at', 'updated_at'])
        return True
    return False


def _assert_evaluation_window_open(tender: Tender) -> None:
    """Technical/Financial submissions unlock per-bid via the staged EOI -> Technical ->
    Financial workflow (each stage has its own deadline) — the tender's overall status
    only reaches CLOSED once the *last* staged deadline passes, which is after Financial
    too. Requiring CLOSED here would make it impossible to evaluate Technical proposals
    in time to open Financial for shortlisted vendors, so evaluation is allowed while the
    tender is still live (PUBLISHED), CLOSED, or already in EVALUATION — mirroring the
    check EOI (Stage 1) review already uses.
    """
    _auto_close_tender_on_deadline(tender)
    if tender.status not in {TenderStatus.PUBLISHED, TenderStatus.CLOSED, TenderStatus.EVALUATION}:
        raise ValidationError(
            {'detail': 'Evaluation requires the tender to be Published, Closed, or in Evaluation.'}
        )
    if tender.status == TenderStatus.CLOSED:
        tender.status = TenderStatus.EVALUATION
        tender.save(update_fields=['status', 'updated_at'])


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
        'Financial Proposal and Disbursement Table',
        ('financial_proposal_file',),
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


def _missing_required_bid_documents(tender: Tender, bid: TenderBid | None):
    """Required bid documents THIS tender configured that the awarded vendor did not upload.

    This is the only bid-completeness rule that applies when signing. It deliberately does
    not consider the Annex A-E contract sections: those are structural pages of the
    generated PBA rather than vendor uploads (see ANNEX_SECTION_SPECS in pba_pdf.py), so an
    absent annex source is never a reason to refuse a signature — gating on it blocked
    vendors whose bid legitimately omitted a source document, and asked them to upload a
    document the tender never required of them. What genuinely matters is whether the
    vendor delivered what this tender asked for, configured at tender creation.

    Mirrors the submission-time rule in TenderBidSerializer.validate so both agree on what
    "required" means and on how custom documents are matched.
    """
    if not bid:
        return []
    uploaded_custom = {}
    for entry in (bid.custom_documents or []):
        if isinstance(entry, dict) and entry.get('name'):
            uploaded_custom[str(entry['name']).strip()] = entry

    missing = []
    for required in tender.required_documents.all():
        if required.field_key:
            if not getattr(bid, required.field_key, None):
                missing.append(required.name)
            continue
        uploaded = uploaded_custom.get(str(required.name).strip())
        if not (uploaded and (uploaded.get('file_url') or uploaded.get('file_name'))):
            missing.append(required.name)
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
    # For a lot-wise award the lot's own target districts are the relevant scope, not the
    # whole tender's — a lot may cover districts the tender-level list does not.
    lot_target_districts = []
    if contract.lot_id:
        lot_target_districts = [
            str(value or '').strip()
            for value in (contract.lot.target_districts if isinstance(contract.lot.target_districts, list) else [])
            if str(value or '').strip()
        ]
    tender_target_districts = [
        str(value or '').strip()
        for value in (contract.tender.target_districts if isinstance(contract.tender.target_districts, list) else [])
        if str(value or '').strip()
    ]
    bid_preferred_district = ''
    if bid:
        bid_preferred_district = str(getattr(bid, 'preferred_district', '') or '').strip()
    
    # Priority: bid_preferred_district > lot_target_districts > tender_target_districts > site districts > vendor zone
    assignment_districts = []
    if bid_preferred_district:
        assignment_districts = [bid_preferred_district]
    
    # Even if bid has preferred, we might want to include tender targets as fallback or options?
    # But requirement says "District should get the value of the selected primary district of the Bid"
    
    if not assignment_districts:
        if lot_target_districts:
            assignment_districts = lot_target_districts
        elif tender_target_districts:
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
    
    # A lot's estimated installation target describes just that lot's scope, so it is the
    # better default than the tender-wide figure.
    lot_installation_target = 0
    if contract.lot_id:
        lot_installation_target = int(contract.lot.estimated_installation_target or 0)
    installation_target = lot_installation_target or contract.tender.approximate_installation_target or (len(list(bid.sites.all())) if bid else 0)
    start_date = contract.tender.awarded_at.date() if contract.tender.awarded_at else timezone.now().date()
    contract_value = _contract_value(contract)
    platform_config = _platform_configuration()
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
        'm1_disbursement_pct': DEFAULT_MILESTONE_DISBURSEMENT_PCTS[0],
        'm2_disbursement_pct': DEFAULT_MILESTONE_DISBURSEMENT_PCTS[1],
        'm3_disbursement_pct': DEFAULT_MILESTONE_DISBURSEMENT_PCTS[2],
        'm2_installation_required_pct': platform_config.m2_verification_required_pct or 80,
        'm3_installation_required_pct': platform_config.m3_verification_required_pct or 100,
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
    return contract.resolved_award_value()


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


DEFAULT_MILESTONE_DISBURSEMENT_PCTS = (20, 50, 30)


def _milestone_amounts(contract_value: Decimal, disbursement_pcts) -> list[Decimal]:
    """Split the contract value by milestone percentage; the last milestone takes
    the rounding remainder so the amounts always sum to the contract value."""
    total = Decimal(str(contract_value or 0)).quantize(Decimal('0.01'))
    amounts = [
        (total * Decimal(pct) / Decimal('100')).quantize(Decimal('0.01'))
        for pct in disbursement_pcts[:-1]
    ]
    amounts.append(total - sum(amounts, Decimal('0.00')))
    return amounts


def _milestone_requirement_descriptions(project: Project, m2_installation_pct: int, m3_installation_pct: int) -> dict[int, str]:
    female = project.female_target_pct or project.target_female_pct
    vulnerable = project.vulnerable_target_pct or project.target_vulnerable_pct
    low_income = project.low_income_target_pct or project.target_low_income_pct
    return {
        1: 'Contract approved; project setup completed.',
        2: (
            f'At least {m2_installation_pct}% of target installations verified; '
            f'female-headed households at or above {female}%; '
            'no unresolved blocking anomaly flags; meter data received within the last 30 days.'
        ),
        3: (
            f'At least {m3_installation_pct}% of target installations verified; '
            f'female-headed households at or above {female}%; '
            f'vulnerable households at or above {vulnerable}%; '
            f'low-income households at or above {low_income}%; '
            'all anomaly flags resolved; Milestone 2 fully paid.'
        ),
    }


def _disbursement_preview(contract_value: Decimal, disbursement_pcts=DEFAULT_MILESTONE_DISBURSEMENT_PCTS) -> dict:
    m1, m2, m3 = _milestone_amounts(contract_value, list(disbursement_pcts))
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
    # A vendor can win several lots of the same tender under a single bid, so without a lot
    # suffix every one of those projects would carry an identical reference and plan id.
    # Mirrors the contract reference convention (see TenderContract creation).
    if contract.lot_id:
        project_reference = f'{project_reference}-LOT{contract.lot_id}'
        milestone_plan_id = f'{milestone_plan_id}-LOT{contract.lot_id}'

    project_budget = _contract_value(contract)

    project = Project.objects.create(
        tender=tender,
        contract=contract,
        lot=contract.lot,
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

    disbursement_pcts = [
        assignment_data.get('m1_disbursement_pct', DEFAULT_MILESTONE_DISBURSEMENT_PCTS[0]),
        assignment_data.get('m2_disbursement_pct', DEFAULT_MILESTONE_DISBURSEMENT_PCTS[1]),
        assignment_data.get('m3_disbursement_pct', DEFAULT_MILESTONE_DISBURSEMENT_PCTS[2]),
    ]
    m2_installation_pct = int(assignment_data.get('m2_installation_required_pct') or 80)
    m3_installation_pct = int(assignment_data.get('m3_installation_required_pct') or 100)
    amounts = _milestone_amounts(project_budget, disbursement_pcts)
    descriptions = _milestone_requirement_descriptions(project, m2_installation_pct, m3_installation_pct)
    for milestone_number, name, required_installation_pct, milestone_status in [
        (1, 'Mobilization', 0, MilestoneStatus.PENDING),
        (2, f'{m2_installation_pct}% Implementation', m2_installation_pct, MilestoneStatus.LOCKED),
        (3, 'Final', m3_installation_pct, MilestoneStatus.LOCKED),
    ]:
        disbursement_pct = disbursement_pcts[milestone_number - 1]
        amount = amounts[milestone_number - 1]
        Milestone.objects.create(
            project=project,
            milestone_number=milestone_number,
            disbursement_pct=disbursement_pct,
            name=name,
            description=descriptions[milestone_number],
            percentage=disbursement_pct,
            required_installation_pct=required_installation_pct,
            status=milestone_status,
            amount=amount,
            amount_lsl=amount,
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


def _platform_configuration() -> PlatformConfiguration:
    return PlatformConfiguration.objects.order_by('id').first() or PlatformConfiguration()


def _technical_score_limits() -> dict[str, int]:
    """Super-Admin-configurable technical rubric (PlatformConfiguration.technical_scoring_criteria)."""
    return _platform_configuration().technical_score_limits()


def _technical_score_total() -> int:
    return sum(_technical_score_limits().values()) or 70


def _financial_scoring_formula() -> str:
    return _platform_configuration().financial_scoring_formula


def _score_from_price(lowest: Decimal, price: Decimal) -> Decimal:
    """The two Super-Admin-selectable financial formulas — the lowest qualifying
    price is always the reference point, either proportionally (QCBS-style) or
    via a linear deviation from it."""
    if _financial_scoring_formula() == FinancialScoringFormula.LINEAR_DEVIATION_100:
        score = Decimal("100") - ((price - lowest) / lowest) * Decimal("100")
        return max(score, Decimal("0"))
    return (lowest / price) * Decimal("100")


def _to_base_currency(tender: Tender, amount, currency: str | None) -> Decimal | None:
    """Convert `amount` (in `currency`) into the tender's base currency, for any
    comparison across bids that might be priced in different currencies."""
    if amount is None:
        return None
    return Decimal(str(amount)) * tender.currency_rate_to_base(currency)


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
    limits = _technical_score_limits()
    if _fits_score_matrix(evaluation, limits):
        raw_total = _sum_score_fields(evaluation, limits)
        return (raw_total / Decimal(str(_technical_score_total()))) * Decimal("100")

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
    limits = _technical_score_limits()
    compatible_evaluations = [
        ev for ev in technical_evaluations
        if _fits_score_matrix(ev, limits)
    ]
    if compatible_evaluations:
        raw_total = sum(_sum_score_fields(ev, limits) for ev in compatible_evaluations) / Decimal(len(compatible_evaluations))
        minimum_raw_total = (Decimal(str(threshold)) / Decimal("100")) * Decimal(str(_technical_score_total()))
        return raw_total >= minimum_raw_total

    technical_score = sum(_technical_evaluation_score(ev) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
    return technical_score >= Decimal(str(threshold))


def _financial_evaluation_score(evaluation: TenderBidEvaluation) -> Decimal:
    # New rows carry an auto-calculated 0-100 score already (see _compute_auto_financial_score).
    # Legacy rows (pre-Evaluation-Committee) stored a manually-typed 0-30 component instead.
    if evaluation.financial_score_auto_calculated:
        return Decimal(str(evaluation.financial_score or 0))
    if _fits_score_matrix(evaluation, FINANCIAL_SCORE_COMPONENT_LIMITS):
        raw_total = Decimal(str(evaluation.financial_score or 0))
        return (raw_total / Decimal("30")) * Decimal("100")
    return Decimal(str(evaluation.financial_score or 0))


def _evaluation_committee_quorum(tender: Tender) -> int:
    """Majority of the tender's assigned Evaluation Committee roster (0 if none assigned
    yet). A committee's decision only counts as final once this many members have
    scored — one member's click isn't a committee decision."""
    assigned_count = TenderEvaluationCommitteeMember.objects.filter(tender=tender).count()
    return ceil(assigned_count / 2) if assigned_count else 0


def _quorum_met_evaluations(bid: TenderBid, stage: str, evaluations=None) -> list | None:
    """Scored evaluations for this bid+stage if the committee's majority quorum has been
    reached, else None. A Super Admin (ADMIN role)-authored score is an override and
    always counts as decisive, bypassing quorum."""
    pool = evaluations if evaluations is not None else bid.evaluations.all()
    scored = [ev for ev in pool if ev.status == EvaluationStatus.SCORED and ev.stage == stage]
    if not scored:
        return None
    has_admin_override = any(getattr(getattr(ev, 'evaluator', None), 'role', None) == UserRole.ADMIN for ev in scored)
    quorum = _evaluation_committee_quorum(bid.tender)
    if not has_admin_override and quorum and len(scored) < quorum:
        return None
    return scored


def _technical_score_for_bid(bid: TenderBid, lot=None) -> Decimal | None:
    """Average of the quorum-met technical evaluations for a bid.

    `lot` scopes the average to that lot's own technical rows (a lot-wise tender can
    hold one technical evaluation per lot per evaluator). When no per-lot rows exist yet
    — or `lot` is None on a non-lot-wise tender — the legacy shared technical row
    (lot=NULL) is used, so older data keeps working."""
    def _avg(evals):
        return sum(_technical_evaluation_score(ev) for ev in evals) / Decimal(len(evals))

    if lot is not None:
        per_lot = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, bid.evaluations.filter(lot=lot))
        if per_lot:
            return _avg(per_lot)
        legacy = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, bid.evaluations.filter(lot__isnull=True))
        if legacy:
            return _avg(legacy)
        return None
    legacy = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, bid.evaluations.filter(lot__isnull=True))
    if legacy:
        return _avg(legacy)
    aggregated = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, bid.evaluations.all())
    if not aggregated:
        return None
    return _avg(aggregated)


def _lowest_qualifying_bid_amount(tender: Tender, exclude_bid_id=None) -> Decimal | None:
    """Lowest bid_amount (converted to the tender's base currency) among this
    (non-lot-wise) tender's technically-qualified bids — the basis for the QCBS
    financial formula (100 x lowest / this bid's price)."""
    amounts = []
    for bid in _financial_bids_for_tender(tender):
        if exclude_bid_id is not None and bid.id == exclude_bid_id:
            continue
        if bid.bid_amount and Decimal(str(bid.bid_amount)) > 0:
            amounts.append(_to_base_currency(tender, bid.bid_amount, bid.bid_currency))
    return min(amounts) if amounts else None


def _compute_auto_financial_score(bid: TenderBid, lowest_amount: Decimal | None = None) -> Decimal:
    """QCBS-style financial score: the lowest technically-qualified bid (in base-currency
    terms) scores 100; every other qualifying bid is scored proportionally against it."""
    if not bid.bid_amount or Decimal(str(bid.bid_amount)) <= 0:
        return Decimal("0")
    lowest = lowest_amount if lowest_amount is not None else _lowest_qualifying_bid_amount(bid.tender)
    if not lowest:
        return Decimal("0")
    return _score_from_price(lowest, _to_base_currency(bid.tender, bid.bid_amount, bid.bid_currency))


def _lowest_qualifying_lot_offer_amount(lot, exclude_offer_id=None) -> Decimal | None:
    """Lowest offered price for one lot (converted to the tender's base currency) among
    offers from technically-qualified bids."""
    passing_bid_ids = {bid.id for bid in _financial_bids_for_tender(lot.tender)}
    amounts = []
    for offer in lot.bid_offers.filter(bid_id__in=passing_bid_ids).select_related('bid'):
        if exclude_offer_id is not None and offer.id == exclude_offer_id:
            continue
        if offer.bid_amount and Decimal(str(offer.bid_amount)) > 0:
            amounts.append(_to_base_currency(lot.tender, offer.bid_amount, offer.bid.bid_currency))
    return min(amounts) if amounts else None


def _compute_auto_financial_score_for_offer(offer, lowest_amount: Decimal | None = None) -> Decimal:
    if not offer.bid_amount or Decimal(str(offer.bid_amount)) <= 0:
        return Decimal("0")
    lowest = lowest_amount if lowest_amount is not None else _lowest_qualifying_lot_offer_amount(offer.lot)
    if not lowest:
        return Decimal("0")
    return _score_from_price(lowest, _to_base_currency(offer.lot.tender, offer.bid_amount, offer.bid.bid_currency))


def _clone_sites_to_bid(source_bid: TenderBid, target_bid: TenderBid):
    source_sites = list(source_bid.sites.all())
    if not source_sites:
        return
    TenderBidSite.objects.bulk_create([
        TenderBidSite(
            bid=target_bid,
            lot_id=site.lot_id,
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
    return _ensure_stage_draft(bid, BidStage.TECHNICAL)


def _ensure_stage_draft(bid: TenderBid, stage: str):
    """Create (or return) a draft bid for a later stage (technical or financial).

    In combined mode the technical bid record doubles as the financial record, so
    only sequential tenders create a distinct financial draft. That shared record is
    persisted with bid_stage=COMBINED (not TECHNICAL), matching what a combined-workflow
    tender's forms actually are.
    """
    stage = normalize_bid_stage(stage)
    workflow = getattr(bid.tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
    combined_style = workflow_is_combined_style(bid.tender, workflow)

    # Combined-style workflow ('EOI → Combined' / 'Combined'): the technical bid record
    # carries technical + financial content, so there is no distinct financial draft.
    if stage == BidStage.FINANCIAL and combined_style:
        return bid

    # The stage transition being unlocked (TECHNICAL/FINANCIAL) determines which
    # unlocked_flag/source_field bookkeeping applies; persisted_stage is what actually
    # gets written to bid_stage, which differs for a combined-style shared draft.
    persisted_stage = stage
    if stage == BidStage.TECHNICAL and combined_style:
        persisted_stage = BidStage.COMBINED

    if stage == BidStage.TECHNICAL:
        unlocked_flag, unlocked_at, source_field = (
            'technical_stage_unlocked', 'technical_stage_unlocked_at', 'technical_stage_source_bid'
        )
    elif stage == BidStage.FINANCIAL:
        unlocked_flag, unlocked_at, source_field = (
            'financial_stage_unlocked', 'financial_stage_unlocked_at', 'financial_stage_source_bid'
        )
    if stage in (BidStage.EOI, BidStage.COMBINED):
        return bid
    if getattr(bid, 'bid_stage', '') and normalize_bid_stage(bid.bid_stage) == persisted_stage and getattr(bid, 'status', None) == BidStatus.DRAFT:
        return bid

    existing = (
        TenderBid.objects.filter(
            tender=bid.tender,
            vendor_id=bid.vendor_id,
            bid_stage=persisted_stage,
            status=BidStatus.DRAFT,
        )
        .order_by('-version_number', '-created_at')
        .first()
    )
    if existing is None:
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
    # Indicative pricing carries forward only into the Financial draft (a starting point
    # the vendor then finalizes there). The Technical stage never sees or edits pricing,
    # so it stays sealed from evaluators until the technical threshold is cleared.
    pricing_fields = (
        {'bid_amount': bid.bid_amount, 'subsidy_requested': bid.subsidy_requested}
        if stage == BidStage.FINANCIAL
        else {}
    )
    draft = TenderBid.objects.create(
        tender=bid.tender,
        vendor_id=bid.vendor_id,
        vendor_name=bid.vendor_name,
        vendor_email=bid.vendor_email,
        proposal_file=bid.proposal_file,
        stage=bid_stage_label(persisted_stage),
        bid_stage=persisted_stage,
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
        declared_lots=bid.declared_lots,
        version_number=next_version,
        status=BidStatus.DRAFT,
        **pricing_fields,
        **{unlocked_flag: True, unlocked_at: timezone.now(), source_field: bid},
        **({
            'stage_two_unlocked': True,
            'stage_two_unlocked_at': timezone.now(),
            'stage_two_source_bid': bid,
        } if stage == BidStage.TECHNICAL else {}),
    )
    _copy_bid_documents(bid, draft)
    _clone_sites_to_bid(bid, draft)
    return draft


def _unlock_stage_for_bid(bid: TenderBid, stage: str):
    """Open the given stage for an accepted bid and return its draft."""
    stage = normalize_bid_stage(stage)
    workflow = getattr(bid.tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
    if stage == BidStage.TECHNICAL:
        unlocked_flag, unlocked_at = 'technical_stage_unlocked', 'technical_stage_unlocked_at'
    elif stage == BidStage.FINANCIAL:
        unlocked_flag, unlocked_at = 'financial_stage_unlocked', 'financial_stage_unlocked_at'
    else:
        return bid
    if workflow_is_combined_style(bid.tender, workflow):
        # Financial is unlocked/already carried on the technical/combined record.
        if stage == BidStage.FINANCIAL:
            bid.financial_stage_unlocked = True
            if not bid.financial_unsealed_at:
                bid.financial_unsealed_at = timezone.now()
            bid.financial_sealed = False
            bid.save(update_fields=['financial_stage_unlocked', 'financial_unsealed_at', 'financial_sealed', 'updated_at'])
            return bid
    if not getattr(bid, unlocked_flag, False):
        setattr(bid, unlocked_flag, True)
        setattr(bid, unlocked_at, timezone.now())
        bid.save(update_fields=[unlocked_flag, unlocked_at, 'updated_at'])
    return _ensure_stage_draft(bid, stage)


def _has_stage_two_shortlist_access(bid: TenderBid | None) -> bool:
    if bid is None or not bid.stage_two_unlocked:
        return False
    source_bid = bid.stage_two_source_bid
    return bool(source_bid and source_bid.status == BidStatus.ACCEPTED)


def _has_technical_stage_access(bid: TenderBid | None) -> bool:
    if bid is None:
        return False
    if getattr(bid, 'bid_stage', '') in (BidStage.TECHNICAL, BidStage.COMBINED):
        if getattr(bid, 'technical_stage_unlocked', False):
            return True
        if getattr(bid, 'stage_two_unlocked', False):
            return _has_stage_two_shortlist_access(bid)
        return True
    return False


def _has_financial_stage_access(bid: TenderBid | None) -> bool:
    if bid is None:
        return False
    return bool(getattr(bid, 'financial_stage_unlocked', False))


def _bid_lineage_ids(bid: TenderBid) -> set:
    """All ancestor bid ids in this bid's EOI -> Technical -> Financial stage lineage.

    Each *_source_bid field only points one hop back (e.g. a Financial draft's
    financial_stage_source_bid points at the Technical bid it was unlocked from, not at
    the EOI bid further up the chain). Walking only one hop left the duplicate-submission
    check below unable to see past the immediate parent, so a vendor's own earlier,
    already-decided EOI bid would be mistaken for "an existing submitted bid" and block
    Financial submission with "You have already submitted a bid for this tender."
    """
    ids = set()
    current = bid
    seen = {bid.id}
    while current is not None:
        next_id = (
            getattr(current, 'technical_stage_source_bid_id', None)
            or getattr(current, 'financial_stage_source_bid_id', None)
            or getattr(current, 'stage_two_source_bid_id', None)
        )
        if not next_id or next_id in seen:
            break
        ids.add(next_id)
        seen.add(next_id)
        current = TenderBid.objects.filter(id=next_id).first()
    return ids


def _bid_stage_spec(bid: TenderBid | None, tender: Tender):
    """Resolve the stage + applicable deadline for a bid (or a new opening bid)."""
    if bid is not None and getattr(bid, 'bid_stage', ''):
        stage = normalize_bid_stage(bid.bid_stage)
    else:
        # A new single-stage 'Combined' tender opens directly at the Combined stage; so
        # does a tender linked to an EOI Invite tender (its EOI already happened on the
        # linked tender — invited vendors were copied over at link time, see
        # TenderSerializer._sync_linked_eoi_vendors). Every other workflow opens with an
        # EOI stage.
        stage = BidStage.COMBINED if (
            (
                getattr(tender, 'procurement_workflow', '') == ProcurementWorkflow.COMBINED
                and not getattr(tender, 'eoi_deadline', None)
            )
            or getattr(tender, 'linked_eoi_tender_id', None)
        ) else BidStage.EOI
    workflow = getattr(tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
    if stage == BidStage.FINANCIAL:
        deadline = getattr(tender, 'financial_deadline', None)
    elif stage in (BidStage.TECHNICAL, BidStage.COMBINED):
        deadline = getattr(tender, 'technical_deadline', None)
    else:
        deadline = getattr(tender, 'eoi_deadline', None)
    deadline = deadline or tender.master_deadline()
    return {'stage': stage, 'deadline': deadline, 'workflow': workflow}


def _backfill_stage_two_drafts_for_vendor(vendor_id: str):
    """Lazily create a Stage 2 draft for legacy pre-qualification bids accepted before
    stage_two_unlocked existed. This runs on every vendor bid list fetch (see
    TenderBidViewSet.get_queryset), so it must be idempotent per tender: stage_two_unlocked
    only ever gets set on the *new* draft it creates, never on the source EOI bid, so
    re-matching on `stage_two_unlocked=False` alone would recreate a fresh blank draft on
    every single page load. Skip any tender where the vendor already has a technical/
    combined-stage bid (in any status) or an already-unlocked legacy record.
    """
    already_progressed_tender_ids = TenderBid.objects.filter(
        vendor_id=vendor_id,
    ).filter(
        Q(bid_stage__in=[BidStage.TECHNICAL, BidStage.COMBINED]) | Q(stage_two_unlocked=True)
    ).values_list('tender_id', flat=True)
    eligible_bids = (
        TenderBid.objects.filter(
            vendor_id=vendor_id,
            status=BidStatus.ACCEPTED,
            stage_two_unlocked=False,
        )
        .exclude(tender_id__in=list(already_progressed_tender_ids))
        .select_related('tender')
    )
    for bid in eligible_bids:
        if normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) != 'pre_qualification':
            continue
        _ensure_stage_two_draft(bid)


def _technical_passing_bids(tender: Tender):
    """Return technical/combined bids whose technical score clears the threshold."""
    threshold = Decimal(str(tender.technical_threshold or 70))
    passing = []
    bids = (
        TenderBid.objects.filter(
            tender=tender,
            bid_stage__in=[BidStage.TECHNICAL, BidStage.COMBINED],
        )
        .prefetch_related('evaluations')
    )
    for bid in bids:
        score = _technical_score_for_bid(bid)
        if score is not None and score >= threshold:
            passing.append(bid)
    return passing


def _financial_bid_for_technical(bid: TenderBid) -> TenderBid | None:
    """The bid whose financial content counts for a technically-passing bid.

    In a combined-workflow tender the technical record doubles as the financial record
    (bid_stage=COMBINED) and carries the pricing itself, so it is returned unchanged.
    In a sequential tender the financial proposal lives on a separate FINANCIAL-stage
    bid unlocked from this technical bid, so amounts, lot offers and financial
    evaluations must be read from that bid — the technical record never carries them.
    Returns None if the vendor has not (yet) submitted a financial proposal.
    """
    stage = normalize_bid_stage(getattr(bid, 'bid_stage', ''))
    if stage == BidStage.COMBINED:
        return bid
    if stage != BidStage.TECHNICAL:
        return None
    linked = (
        TenderBid.objects.filter(
            tender=bid.tender,
            financial_stage_source_bid=bid,
        )
        .exclude(status=BidStatus.DRAFT)
        .order_by('-version_number', '-submitted_at', '-id')
        .first()
    )
    if linked:
        return linked
    distinct = (
        TenderBid.objects.filter(
            tender=bid.tender,
            vendor_id=f'{bid.vendor_id}',
            bid_stage=BidStage.FINANCIAL,
        )
        .exclude(status=BidStatus.DRAFT)
        .order_by('-version_number', '-submitted_at', '-id')
        .first()
    )
    if distinct:
        return distinct
    # Legacy direct-scoring records: a technical bid that itself carries pricing (no
    # separate financial bid was ever created) is its own financial record. This never
    # fires for real sequential tenders — pricing fields are never written to their
    # technical bids (they live on the financial-stage bid only).
    if getattr(bid, 'bid_amount', None):
        return bid
    return None


def _technical_bid_for_financial(financial_bid: TenderBid) -> TenderBid:
    """The technical/combined record that carries a (possibly distinct) financial bid's
    technical evaluations — the reverse of _financial_bid_for_technical. For a
    sequential tender a financial-stage bid points back at the technical bid it was
    unlocked from via financial_stage_source_bid; combined bids carry both themselves."""
    stage = normalize_bid_stage(getattr(financial_bid, 'bid_stage', ''))
    if stage in (BidStage.TECHNICAL, BidStage.COMBINED):
        return financial_bid
    source = getattr(financial_bid, 'financial_stage_source_bid', None)
    return source if source is not None else financial_bid


def _financial_bids_for_tender(tender: Tender):
    """The bids the Evaluation Committee scores financially for a tender: for each bid
    that cleared the technical threshold its financial counterpart (itself in combined
    mode; the vendor's latest submitted financial-stage bid in sequential mode)."""
    financial = []
    seen = set()
    for bid in _technical_passing_bids(tender):
        financial_bid = _financial_bid_for_technical(bid)
        if financial_bid is not None and financial_bid.id not in seen:
            seen.add(financial_bid.id)
            financial.append(financial_bid)
    return financial


def _open_financial_stage_for_tender(tender: Tender):
    """Batch-open the Financial stage for every technical-passing bidder at once."""
    opened = []
    for bid in _technical_passing_bids(tender):
        _unlock_stage_for_bid(bid, BidStage.FINANCIAL)
        opened.append(bid)
    return opened


def _detailed_evaluation_bids(tender: Tender):
    """The bids that entered the committee's detailed (technical/financial) evaluation:
    the Technical/Combined-stage records a vendor has submitted for this tender, plus
    legacy pre-EOI stage-two records. Mirrors the candidate set used by award ranking."""
    return list(
        TenderBid.objects.filter(
            tender=tender,
        )
        .filter(
            Q(bid_stage__in=[BidStage.TECHNICAL, BidStage.COMBINED]) | Q(stage_two_unlocked=True)
        )
        .filter(
            status__in={BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED, BidStatus.AWARDED}
        )
        .distinct()
        .prefetch_related('evaluations__evaluator')
    )


def _tender_evaluation_status(tender: Tender) -> dict:
    """Whether the committee's evaluation of this tender is complete enough for the RBF
    Official to submit their post-evaluation comment. Complete means: the tender has an
    assigned Evaluation Committee, every bid that entered detailed evaluation has a
    technical score meeting quorum, and every bid that cleared the technical threshold
    has a finalized financial score (quorum met; per lot, for lot-wise tenders)."""
    reasons = []
    quorum = _evaluation_committee_quorum(tender)
    if quorum == 0:
        reasons.append('No Evaluation Committee has been assigned to this tender yet.')

    threshold = Decimal(str(tender.technical_threshold or 70))
    is_lot_wise = tender.lots.exists()

    technical_pending = []
    for bid in _detailed_evaluation_bids(tender):
        if not _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL):
            technical_pending.append(bid.vendor_name)
    if technical_pending:
        reasons.append(f'Technical scoring is not final (committee quorum not reached): {", ".join(sorted(set(technical_pending)))}.')

    financial_pending = []
    for bid in _financial_bids_for_tender(tender):
        scored_financial = bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, status=EvaluationStatus.SCORED)
        if is_lot_wise:
            offered_lot_ids = set(TenderBidLotOffer.objects.filter(bid=bid).values_list('lot_id', flat=True))
            missing_lots = []
            for lot_id in sorted(offered_lot_ids):
                member_ids = set(scored_financial.filter(lot_id=lot_id).values_list('evaluator_id', flat=True))
                if len([mid for mid in member_ids if mid is not None]) < quorum:
                    missing_lots.append(lot_id)
            if missing_lots:
                lot_names = dict(TenderLot.objects.filter(id__in=missing_lots).values_list('id', 'name'))
                financial_pending.append(f"{bid.vendor_name} (lots: {', '.join(lot_names.get(lid, str(lid)) for lid in missing_lots)})")
        else:
            member_ids = set(scored_financial.values_list('evaluator_id', flat=True))
            if len([mid for mid in member_ids if mid is not None]) < quorum:
                financial_pending.append(bid.vendor_name)
    if financial_pending:
        reasons.append(f'Financial scores are not yet finalized: {", ".join(financial_pending)}.')

    return {
        'complete': not reasons,
        'reasons': reasons,
        'committee_size': quorum,
        'detailed_bid_count': len(_detailed_evaluation_bids(tender)),
    }


def _award_recommendation_unit(tender: Tender, lot) -> dict:
    """Every assigned committee member's latest winner suggestion for one decision unit
    (the whole tender, or a single lot), whether they all agree on one bid, and who has
    not suggested yet. Consensus = EVERY assigned member's suggestion points to the same bid."""
    members = TenderEvaluationCommitteeMember.objects.filter(tender=tender).select_related('member').order_by('id')
    assigned = [
        {'member_id': str(m.member_id), 'member_name': m.member.full_name or m.member.username}
        for m in members
    ]
    recommendations = (
        TenderAwardRecommendation.objects.filter(tender=tender, lot=lot)
        .select_related('bid', 'suggested_by')
    )
    suggestions = [{
        'recommendation_id': str(r.id),
        'suggested_by': str(r.suggested_by_id),
        'suggested_by_name': r.suggested_by.full_name or r.suggested_by.username,
        'bid_id': str(r.bid_id),
        'vendor_name': r.bid.vendor_name,
        'rationale': r.rationale,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None,
    } for r in recommendations]
    by_member = {s['suggested_by']: s for s in suggestions}
    pending_member_ids = [a['member_id'] for a in assigned if a['member_id'] not in by_member]
    vote_ids = {s['bid_id'] for s in suggestions}
    consensus = bool(assigned) and len(suggestions) == len(assigned) and len(vote_ids) == 1
    agreed_bid_id = next(iter(vote_ids)) if consensus else None
    agreed_vendor_name = next((s['vendor_name'] for s in suggestions if s['bid_id'] == agreed_bid_id), None) if agreed_bid_id else None
    return {
        'lot_id': str(lot.id) if lot else None,
        'lot_name': lot.name if lot else '',
        'assigned_members': assigned,
        'suggestions': suggestions,
        'pending_member_ids': pending_member_ids,
        'consensus': consensus,
        'agreed_bid_id': agreed_bid_id,
        'agreed_vendor_name': agreed_vendor_name,
        'intent_to_award_bid_id': str(lot.intent_to_award_bid_id) if lot and lot.intent_to_award_bid_id else None,
    }


def _award_recommendation_consensus(tender: Tender) -> dict:
    """Consensus for every decision unit of a tender: { is_lot_wise, evaluation_complete, units }."""
    lots = list(tender.lots.order_by('position', 'id'))
    units = [_award_recommendation_unit(tender, lot) for lot in lots] if lots else [_award_recommendation_unit(tender, None)]
    return {
        'is_lot_wise': bool(lots),
        'evaluation_complete': _tender_evaluation_status(tender)['complete'],
        'units': units,
    }


def _bid_covers_lot(bid: TenderBid, lot_id) -> bool:
    """Whether a bid covers a given lot (declared lots, priced offers, or site tags)."""
    if not lot_id:
        return True
    covered = set(bid.declared_lots or [])
    covered |= set(bid.lot_offers.values_list('lot_id', flat=True))
    covered |= set(bid.sites.values_list('lot_id', flat=True))
    return str(lot_id) in {str(c) for c in covered}


def _bid_financial_finalized(tender: Tender, bid: TenderBid, quorum: int) -> bool:
    """Whether the committee has finalized the bid's financial score — quorum of distinct
    members with a SCORED financial-stage row. For a lot-wise tender every lot the bid
    offered on must have reached quorum independently."""
    if quorum <= 0:
        return False
    financial_bid = _financial_bid_for_technical(bid) or bid
    scored_financial = financial_bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, status=EvaluationStatus.SCORED)
    if tender.lots.exists():
        offered_lot_ids = set(TenderBidLotOffer.objects.filter(bid=financial_bid).values_list('lot_id', flat=True))
        if not offered_lot_ids:
            return False
        for lot_id in offered_lot_ids:
            member_ids = {mid for mid in scored_financial.filter(lot_id=lot_id).values_list('evaluator_id', flat=True) if mid is not None}
            if len(member_ids) < quorum:
                return False
        return True
    member_ids = {mid for mid in scored_financial.values_list('evaluator_id', flat=True) if mid is not None}
    return len(member_ids) >= quorum


def _tender_evaluation_scoreboard(tender: Tender):
    """Per-bid, per-committee-member score breakdown for the RBF Official / Super Admin
    — the raw marks each Evaluation Committee member gave, so RMT can see exactly where
    each score came from rather than only the averaged result."""
    members = list(
        TenderEvaluationCommitteeMember.objects.filter(tender=tender).select_related('member').order_by('assigned_at', 'id')
    )
    quorum_count = _evaluation_committee_quorum(tender)
    score_limits = _technical_score_limits()
    technical_total = _technical_score_total()
    lots = list(tender.lots.all())
    lot_by_id = {str(l.id): l for l in lots}

    bid_rows = []
    for bid in _detailed_evaluation_bids(tender):
        financial_bid = _financial_bid_for_technical(bid) or bid
        technical_quorum = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL)
        technical_average = None
        technical_raw_average = Decimal('0')
        if technical_quorum:
            technical_average = sum(
                _technical_evaluation_score(ev) for ev in technical_quorum
            ) / Decimal(len(technical_quorum))
            technical_raw_average = (
                sum(_sum_score_fields(ev, score_limits) for ev in technical_quorum) / Decimal(len(technical_quorum))
            )

        lot_financial_finalized = {}
        # A lot-wise tender is scored lot by lot, so the bid-level technical average
        # above is only a roll-up. Report the same quorum/average/threshold facts per
        # lot as well — otherwise the oversight view would show one blended technical
        # number for a bid that was actually marked separately for each lot.
        lot_technical_summary = {}
        if lots:
            scored_financial = financial_bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, status=EvaluationStatus.SCORED)
            for lot in lots:
                member_ids = {mid for mid in scored_financial.filter(lot_id=lot.id).values_list('evaluator_id', flat=True) if mid is not None}
                lot_financial_finalized[str(lot.id)] = quorum_count > 0 and len(member_ids) >= quorum_count

                lot_technical_rows = list(
                    bid.evaluations.filter(lot_id=lot.id, stage=EvaluationStage.TECHNICAL, status=EvaluationStatus.SCORED)
                )
                lot_quorum_rows = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, lot_technical_rows)
                lot_average = lot_raw_average = None
                if lot_quorum_rows:
                    lot_average = sum(_technical_evaluation_score(ev) for ev in lot_quorum_rows) / Decimal(len(lot_quorum_rows))
                    lot_raw_average = sum(_sum_score_fields(ev, score_limits) for ev in lot_quorum_rows) / Decimal(len(lot_quorum_rows))
                lot_technical_summary[str(lot.id)] = {
                    'quorum_met': lot_quorum_rows is not None,
                    'member_count': len(lot_technical_rows),
                    'average_score': str(lot_average) if lot_average is not None else None,
                    'raw_average': str(lot_raw_average) if lot_raw_average is not None else None,
                    'passed_threshold': lot_average is not None and lot_average >= Decimal(str(tender.technical_threshold or 70)),
                }

        evaluation_rows = []
        evaluations = list(bid.evaluations.all())
        if financial_bid is not bid:
            evaluations.extend(financial_bid.evaluations.all())
        evaluations.sort(key=lambda ev: (ev.stage, str(ev.lot_id) if ev.lot_id else '', ev.created_at or timezone.now()))
        for ev in evaluations:
            evaluator = getattr(ev, 'evaluator', None)
            revisions = []
            for rev in ev.revisions.all().select_related('changed_by').order_by('created_at'):
                changes = [
                    {'field': field, 'before': before, 'after': after}
                    for field, before, after in _evaluation_snapshot_diff(rev.before or {}, rev.after or {})
                ]
                changed_by = getattr(rev, 'changed_by', None)
                revisions.append({
                    'action': rev.action,
                    'reason': rev.reason or '',
                    'changed_by': (changed_by.full_name if changed_by and changed_by.full_name else (changed_by.username if changed_by else '')) or '',
                    'changed_at': rev.created_at.isoformat() if rev.created_at else None,
                    'changes': changes,
                })
            evaluation_rows.append({
                'evaluation_id': str(ev.id),
                'evaluator': str(ev.evaluator_id) if ev.evaluator_id else None,
                'evaluator_name': (evaluator.full_name if evaluator and evaluator.full_name else (evaluator.username if evaluator else '')) or 'Unknown',
                'stage': ev.stage,
                'lot': str(ev.lot_id) if ev.lot_id else None,
                'lot_name': lot_by_id.get(str(ev.lot_id)).name if ev.lot_id else None,
                'status': ev.status,
                'submission_status': ev.submission_status,
                'submitted_at': ev.submitted_at.isoformat() if ev.submitted_at else None,
                'justifications': ev.justifications or {},
                'technical_score': ev.technical_score,
                'feasibility_score': ev.feasibility_score,
                'kpi_score': ev.kpi_score,
                'gender_score': ev.gender_score,
                'environmental_score': ev.environmental_score,
                'om_score': ev.om_score,
                'inclusivity_score': ev.inclusivity_score,
                'financial_score': ev.financial_score,
                'financial_score_auto_calculated': ev.financial_score_auto_calculated,
                'total_score': ev.total_score,
                'comments': ev.comments or '',
                'created_at': ev.created_at.isoformat() if ev.created_at else None,
                'updated_at': ev.updated_at.isoformat() if ev.updated_at else None,
                'revisions': revisions,
            })

        bid_rows.append({
            'bid_id': str(bid.id),
            'vendor_id': str(bid.vendor_id),
            'vendor_name': bid.vendor_name,
            'bid_stage': bid.bid_stage,
            'status': bid.status,
            'technical_quorum_met': technical_quorum is not None,
            'technical_average_score': str(technical_average) if technical_average is not None else None,
            'technical_raw_average': str(technical_raw_average) if technical_quorum else None,
            'passed_technical_threshold': technical_average is not None and technical_average >= Decimal(str(tender.technical_threshold or 70)),
            'financial_finalized': _bid_financial_finalized(tender, bid, quorum_count),
            'lot_financial_finalized': lot_financial_finalized,
            'lot_technical_summary': lot_technical_summary,
            'evaluations': evaluation_rows,
        })

    return {
        'committee_members': [
            {
                'id': str(m.member_id),
                'name': (m.member.full_name or m.member.username),
            }
            for m in members
        ],
        'score_limits': score_limits,
        'technical_score_total': technical_total,
        # The technical rubric is Super-Admin-configurable (technical_score_total), but
        # the financial stage still contributes exactly this tender's financial_weight
        # (30 by default) to the combined 100 — the client needs both to report a
        # member's per-stage marks on a common scale.
        'financial_weight': tender.financial_weight or 30,
        'technical_threshold': tender.technical_threshold or 70,
        'is_lot_wise': bool(lots),
        'lots': [{'lot_id': str(l.id), 'lot_name': l.name} for l in lots],
        'bids': bid_rows,
        'committee_size': len(members),
        'quorum': quorum_count,
    }


def _send_vendor_stage_one_outcome_email(bid: TenderBid, subject: str, message: str):
    if not email_configured() or not bid.vendor_email:
        return False
    return NotificationService.dispatch_email(subject, message, [bid.vendor_email]) > 0


def _notify_stage_one_outcome(bid: TenderBid, passed: bool, draft: TenderBid | None = None):
    is_eoi_bid = normalize_bid_stage(getattr(bid, 'bid_stage', '')) == BidStage.EOI
    is_legacy = normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) == 'pre_qualification'
    if not (is_eoi_bid or is_legacy):
        return

    event = 'eoi_passed' if passed else 'eoi_failed'
    title = (
        f'EOI Shortlisted: {bid.tender.reference_number}'
        if passed else
        f'EOI Unsuccessful: {bid.tender.reference_number}'
    )
    body = (
        f'Congratulations! Your EOI passed the shortlisting review. The next stage is now open as draft version {draft.version_number}.'
        if passed and draft is not None else
        'Your EOI did not pass the shortlisting review. Please review the outcome in My Bids.'
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


def _ec_verdict_check(tender, selected_bid_id, recommended_bid_id, lot=None) -> dict:
    """Apply the EC's winner-suggestion verdict when issuing an intent to award.

    Selection rule for a decision unit (whole tender, or one lot):
      * The committee's agreed bid — the one EVERY assigned member's latest suggestion
        points at — may be issued even if it is not the highest-scoring recommended bid;
        the committee's verdict wins.
      * Issuing to the score-recommended bid is allowed when the committee has NO
        verdict (either no suggestions yet, or no consensus). If the committee DID
        agree on a different bid, issuing to the score-recommended bid instead
        overrides the verdict and needs a recorded reason.
      * Any other bids require an explicit `ec_override_reason`.

    Returns {'allowed', 'needs_override', 'reason_required', 'ec'} where `ec` is the
    unit's consensus payload (useful for the UI to surface members' votes)."""
    unit = _award_recommendation_unit(tender, lot)
    agreed = unit['agreed_bid_id']
    has_verdict = unit['consensus'] and bool(agreed)
    is_ec_agreed = has_verdict and str(agreed) == str(selected_bid_id)
    is_recommended = str(recommended_bid_id) == str(selected_bid_id)
    if is_ec_agreed or (is_recommended and not has_verdict):
        return {'allowed': True, 'needs_override': False, 'reason_required': False, 'ec': unit}
    reason_required = bool(is_recommended and has_verdict) or not is_recommended
    return {'allowed': False, 'needs_override': True, 'reason_required': reason_required, 'ec': unit}


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
        bids_by_vendor.setdefault(str(bid.vendor_id), []).append(bid)
    bids = []
    for group in bids_by_vendor.values():
        # The vendor's detailed-evaluation record (technical/combined) is the ranking
        # candidate: its technical marks live on it. In sequential mode the financial
        # content is read from the linked financial bid inside the loop instead.
        detailed = [
            b for b in group
            if normalize_bid_stage(getattr(b, 'bid_stage', '')) in (BidStage.TECHNICAL, BidStage.COMBINED)
        ]
        pool = detailed or group
        pool.sort(
            key=lambda b: (b.version_number or 0, b.submitted_at or b.updated_at or timezone.now(), str(b.id)),
            reverse=True,
        )
        bids.append(pool[0])
    technical_threshold = tender.technical_threshold or 70
    technical_weight = Decimal(str(tender.technical_weight or 70)) / Decimal("100")
    financial_weight = Decimal(str(tender.financial_weight or 30)) / Decimal("100")

    ranking_rows = []
    qualifying_rows = []

    quorum = _evaluation_committee_quorum(tender)

    for bid in bids:
        scored_evaluations = [ev for ev in bid.evaluations.all() if ev.status == EvaluationStatus.SCORED]
        raw_technical_evaluations = [ev for ev in scored_evaluations if ev.stage == EvaluationStage.TECHNICAL]
        technical_evaluations = _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL, scored_evaluations)
        financial_bid = _financial_bid_for_technical(bid) or bid
        financial_evaluations = [
            ev for ev in financial_bid.evaluations.all()
            if ev.status == EvaluationStatus.SCORED and ev.stage == EvaluationStage.FINANCIAL
        ]
        bid_amount = financial_bid.bid_amount if financial_bid.bid_amount else bid.bid_amount
        bid_amount_base_currency = float(
            _to_base_currency(tender, bid_amount, financial_bid.bid_currency or bid.bid_currency) or 0
        )
        bid_currency = financial_bid.bid_currency or bid.bid_currency or tender.bidding_currency
        if not raw_technical_evaluations:
            ranking_rows.append({
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'vendor_name': bid.vendor_name,
                'bid_amount': float(bid_amount or 0),
                'bid_currency': bid_currency,
                'bid_amount_base_currency': bid_amount_base_currency,
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
        if not technical_evaluations:
            ranking_rows.append({
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'vendor_name': bid.vendor_name,
                'bid_amount': float(bid_amount or 0),
                'bid_currency': bid_currency,
                'bid_amount_base_currency': bid_amount_base_currency,
                'technical_score': None,
                'financial_score': None,
                'combined_score': None,
                'gender_score': None,
                'female_headed_household_target': 0,
                'passed_technical_threshold': False,
                'financial_opened': False,
                'is_recommended_winner': False,
                'disqualification_reason': f'Awaiting more committee scores ({len(raw_technical_evaluations)}/{quorum}).',
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
            'bid_amount': float(bid_amount or 0),
            'bid_currency': bid_currency,
            'bid_amount_base_currency': bid_amount_base_currency,
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
        if not bid_amount or Decimal(str(bid_amount or 0)) <= 0:
            row['disqualification_reason'] = 'Financial proposal is missing or invalid.'
            ranking_rows.append(row)
            continue
        financial_quorum = _quorum_met_evaluations(financial_bid, EvaluationStage.FINANCIAL, financial_evaluations)
        if not financial_quorum:
            count = len(financial_evaluations)
            row['disqualification_reason'] = (
                f'Technical score passed. Awaiting more committee financial scores ({count}/{quorum}) for a finalized financial score.'
            )
            ranking_rows.append(row)
            continue

        financial_score = sum(_financial_evaluation_score(ev) for ev in financial_quorum) / Decimal(len(financial_quorum))
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
                item['bid_amount_base_currency'] or 0,
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


def _build_lot_award_ranking(tender: Tender, lot, *, include_pending_request=False, request=None):
    """Award ranking for one lot of a lot-wise tender.

    Technical merit is shared across a bid's lots (a vendor's technical capability
    doesn't change per lot), so the bid's existing technical evaluation/threshold gate
    still applies. Financial comparison is per lot: among bids that pass the technical
    threshold, the Evaluation Committee's per-lot financial evaluation (finalized via
    the Financial Evaluation screen, stored as a FINANCIAL-stage TenderBidEvaluation
    scoped to this lot) is blended with the technical score using the tender's own
    technical_weight/financial_weight — the same weighted methodology as
    _build_award_ranking, just scoped to one lot's offers instead of the whole bid.
    """
    technical_threshold = tender.technical_threshold or 70
    technical_weight = Decimal(str(tender.technical_weight or 70)) / Decimal("100")
    financial_weight = Decimal(str(tender.financial_weight or 30)) / Decimal("100")
    offers = (
        TenderBidLotOffer.objects.filter(
            lot=lot,
            bid__status__in={BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED, BidStatus.AWARDED},
        )
        .select_related('bid')
        .prefetch_related('bid__evaluations')
        .order_by('-bid__version_number', '-bid__submitted_at', '-bid__id')
    )
    offers_by_vendor = {}
    for offer in offers:
        offers_by_vendor.setdefault(str(offer.bid.vendor_id), offer)

    quorum = _evaluation_committee_quorum(tender)
    rows = []
    qualifying_rows = []
    for offer in offers_by_vendor.values():
        bid = offer.bid
        tech_bid = _technical_bid_for_financial(bid)
        tech_scored = [ev for ev in tech_bid.evaluations.all() if ev.status == EvaluationStatus.SCORED]
        raw_technical_evaluations = [ev for ev in tech_scored if ev.stage == EvaluationStage.TECHNICAL]
        technical_evaluations = _quorum_met_evaluations(tech_bid, EvaluationStage.TECHNICAL, tech_scored)
        lot_scored_evaluations = [ev for ev in bid.evaluations.all() if ev.status == EvaluationStatus.SCORED and ev.lot_id == lot.id]
        financial_evaluations = _quorum_met_evaluations(bid, EvaluationStage.FINANCIAL, lot_scored_evaluations)
        prequal = _latest_vendor_prequalification(str(bid.vendor_id))
        female_target = prequal.female_beneficiary_target if prequal else 0
        row = {
            'bid_id': str(bid.id),
            'vendor_id': str(bid.vendor_id),
            'vendor_name': bid.vendor_name,
            'bid_amount': float(offer.bid_amount or 0),
            'bid_currency': bid.bid_currency or tender.bidding_currency,
            'bid_amount_base_currency': float(_to_base_currency(tender, offer.bid_amount, bid.bid_currency) or 0),
            'subsidy_requested': float(offer.subsidy_requested) if offer.subsidy_requested is not None else None,
            'technical_score': None,
            'financial_score': None,
            'combined_score': None,
            'gender_score': None,
            'female_headed_household_target': female_target,
            'passed_technical_threshold': False,
            'financial_opened': False,
            'is_recommended_winner': False,
            'disqualification_reason': '',
        }
        if not raw_technical_evaluations:
            row['disqualification_reason'] = 'No scored technical evaluation has been submitted yet.'
            rows.append(row)
            continue
        if not technical_evaluations:
            row['disqualification_reason'] = f'Awaiting more committee scores ({len(raw_technical_evaluations)}/{quorum}).'
            rows.append(row)
            continue
        technical_score = sum(_technical_evaluation_score(ev) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
        row['technical_score'] = _round_score(technical_score)
        row['gender_score'] = _round_score(
            sum(Decimal(str(ev.gender_score or 0)) for ev in technical_evaluations) / Decimal(len(technical_evaluations))
        )
        row['passed_technical_threshold'] = _technical_threshold_passed(technical_evaluations, technical_threshold)
        if not row['passed_technical_threshold']:
            row['disqualification_reason'] = f'Technical score below threshold ({technical_threshold}%).'
            rows.append(row)
            continue
        if not offer.bid_amount or Decimal(str(offer.bid_amount or 0)) <= 0:
            row['disqualification_reason'] = 'Financial proposal is missing or invalid for this lot.'
            rows.append(row)
            continue
        if not financial_evaluations:
            row['disqualification_reason'] = 'Technical score passed. Awaiting the Evaluation Committee to finalize the financial score for this lot.'
            rows.append(row)
            continue

        financial_score = sum(_financial_evaluation_score(ev) for ev in financial_evaluations) / Decimal(len(financial_evaluations))
        qualifying_rows.append((row, financial_score))

    if qualifying_rows:
        for row, financial_score in qualifying_rows:
            combined_score = (
                technical_weight * Decimal(str(row['technical_score']))
                + financial_weight * financial_score
            )
            row['financial_opened'] = True
            row['financial_score'] = _round_score(financial_score)
            row['combined_score'] = _round_score(combined_score)
            rows.append(row)

        rows.sort(
            key=lambda item: (
                item['combined_score'] is None,
                -(item['combined_score'] or 0),
                -(item['female_headed_household_target'] or 0),
                -(item['gender_score'] or 0),
                item['bid_amount_base_currency'] or 0,
            )
        )
        recommended_bid_id = next((row['bid_id'] for row in rows if row['combined_score'] is not None), None)
        for index, row in enumerate(rows, start=1):
            row['rank'] = index
            row['is_recommended_winner'] = row['bid_id'] == recommended_bid_id
    else:
        for index, row in enumerate(rows, start=1):
            row['rank'] = index

    recommended_row = next((row for row in rows if row.get('is_recommended_winner')), None)
    return {
        'lot_id': str(lot.id),
        'lot_name': lot.name,
        'rows': rows,
        'recommended': recommended_row,
        'awarded_vendor_id': lot.awarded_vendor_id or None,
        'awarded_vendor_name': lot.awarded_vendor_name or None,
        'intent_to_award_bid_id': str(lot.intent_to_award_bid_id) if lot.intent_to_award_bid_id else None,
        'intent_to_award_at': lot.intent_to_award_at.isoformat() if lot.intent_to_award_at else None,
        'cooling_off_until': lot.cooling_off_until.isoformat() if lot.cooling_off_until else None,
        'awarded_at': lot.awarded_at.isoformat() if lot.awarded_at else None,
        'pending_intent_award_request': (
            _pending_intent_award_request_payload(lot.tender, lot=lot, request=request)
            if include_pending_request else None
        ),
    }


def _pending_intent_award_request_queryset(tender: Tender, lot=None):
    """Pending intent-to-award requests for one decision unit — `lot` for a lot-wise
    award, or the whole-tender unit when `lot` is None."""
    qs = tender.intent_award_requests.filter(status=IntentAwardRequestStatus.PENDING)
    return qs.filter(lot=lot) if lot is not None else qs.filter(lot__isnull=True)


def _pending_intent_award_request_payload(tender: Tender, lot=None, request=None):
    """The pending request for a decision unit, as plain JSON, or None. Embedded in the
    award-ranking payloads so the Award panel can grey out the row it is waiting on.

    `award_ranking` is a public read, and a queued request names the proposed winner
    before the Super Admin has approved it — so it is only embedded for RBF/Super Admin
    callers (see `intent_award_proposal_visible`).
    """
    pending = _pending_intent_award_request_queryset(tender, lot=lot).select_related('lot', 'bid').first()
    if pending is None:
        return None
    return IntentToAwardRequestSerializer(pending, context={'request': request}).data


def _notify_intent_to_award(tender: Tender, ranking_payload: dict, send_email=True, cooling_off_until=None, lot_name=None):
    recommended = ranking_payload.get('recommended')
    if not recommended:
        return

    bids_by_vendor = {row['vendor_id']: row for row in ranking_payload.get('rows', [])}
    cooling_off_until = cooling_off_until if cooling_off_until is not None else tender.cooling_off_until
    cooling_date_text = cooling_off_until.strftime('%Y-%m-%d %H:%M:%S') if cooling_off_until else 'N/A'
    email_enabled = send_email and email_configured()
    lot_suffix = f' — {lot_name}' if lot_name else ''

    # (address, subject, body) collected now, sent after the transaction commits.
    outbound = []

    vendors = User.objects.filter(id__in=list(bids_by_vendor.keys())).only('id', 'email', 'full_name', 'username')
    for vendor in vendors:
        row = bids_by_vendor.get(str(vendor.id))
        if not row:
            continue
        is_winner = row['vendor_id'] == recommended['vendor_id']
        title = (
            f'Notice of Best Evaluated Bidder: {tender.reference_number}{lot_suffix}'
            if is_winner
            else f'Regret Letter: {tender.reference_number}{lot_suffix}'
        )
        body = (
            f"Tender: {tender.name} ({tender.reference_number}){lot_suffix}\n"
            f"Technical Score: {row['technical_score'] if row['technical_score'] is not None else 'N/A'}\n"
            f"Financial Score: {row['financial_score'] if row['financial_score'] is not None else 'Not opened'}\n"
            f"Combined Score: {row['combined_score'] if row['combined_score'] is not None else 'N/A'}\n"
        )
        if is_winner:
            body += (
                f"\nStatus: You are the Best Evaluated Bidder{lot_suffix}.\n"
                f"Cooling-off period ends on: {cooling_date_text}\n"
                f"The final award and PBA generation will only occur after the cooling-off period expires without a formal protest.\n"
            )
        else:
            body += f"\nStatus: Another vendor achieved the highest combined score{lot_suffix} under the weighted RBF evaluation.\n"
            if row.get('disqualification_reason'):
                body += f"Reason: {row['disqualification_reason']}\n"

        # update_or_create (not create): a lot-wise tender calls this once per lot, and
        # a vendor bidding on multiple lots would otherwise collide on the
        # (recipient, event, tender) uniqueness constraint — the notification is kept
        # as one evolving "intent to award" notice per vendor per tender, refreshed
        # with whichever lot's outcome was decided most recently.
        Notification.objects.update_or_create(
            recipient_id=str(vendor.id),
            event='intent_to_award',
            linked_entity_id=str(tender.id),
            defaults={
                'recipient_name': vendor.full_name or vendor.username or vendor.email,
                'type': NotificationChannel.IN_APP,
                'title': title,
                'body': body,
                'status': NotificationStatus.SENT,
            },
        )

        if email_enabled and vendor.email:
            outbound.append((vendor.email, title, body))

    if not outbound:
        return

    def _send_all():
        for address, title, body in outbound:
            NotificationService.dispatch_email(title, body, [address])

    # Issued from inside the award transaction, so the SMTP round trips used to hold the
    # request — and the request's SELECT ... FOR UPDATE row lock — open for the whole
    # fan-out, which left the Super Admin staring at a spinner long after the award had
    # been decided. on_commit also means a bidder can never be told they won by an award
    # that then rolled back. Outside a transaction this runs immediately, as before.
    transaction.on_commit(_send_all)


class _IntentToAwardError(Exception):
    """A validation failure raised while preparing or applying an intent to award.

    Carries the HTTP status the calling action should answer with, so the shared
    preparation/apply logic below can be reused by the RBF's request path and the Super
    Admin's approval path without either re-implementing the checks (or collapsing the
    409 "evaluation not finished" case into a generic 400).
    """

    def __init__(self, detail, status_code=status.HTTP_400_BAD_REQUEST, **extra):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra

    def as_response(self):
        return Response({'detail': self.detail, **self.extra}, status=self.status_code)


def _check_intent_to_award_preconditions(tender, lot=None):
    """The guards shared by every intent-to-award path: a live tender/lot, and a
    finished Evaluation Committee evaluation. Raises _IntentToAwardError."""
    allowed = {TenderStatus.PUBLISHED, TenderStatus.EVALUATION}
    if lot is not None:
        # Each lot is approved and applied independently, so once the tender has moved
        # into standstill the remaining lots can still be queued.
        allowed.add(TenderStatus.STANDSTILL)
        # ...but a lot that already carries a live intent (or a confirmed award) is
        # closed. Without this, a second request for an already-issued lot would queue
        # successfully and its approval would silently re-award the lot, restart the
        # cooling-off window and re-notify the bidders. Revoking the intent re-opens
        # the lot, so a genuine re-award still works.
        if lot.awarded_at or lot.awarded_vendor_id:
            raise _IntentToAwardError(
                f'{lot.name} has already been awarded and confirmed. It cannot be awarded again.'
            )
        if lot.intent_to_award_bid_id:
            raise _IntentToAwardError(
                f'{lot.name} already has an issued intent to award with the cooling-off period '
                'running. Revoke it before proposing a different bidder for this lot.'
            )
    if tender.status not in allowed:
        if lot is not None:
            detail = 'Lots can be awarded only from Published, Evaluation, or Standstill state.'
        else:
            detail = 'Tender can be awarded only from Published or Evaluation state.'
        raise _IntentToAwardError(detail)

    evaluation_status = _tender_evaluation_status(tender)
    if evaluation_status['committee_size'] and not evaluation_status['complete']:
        raise _IntentToAwardError(
            'Finalize the Evaluation Committee scores before issuing an intent to award.',
            status.HTTP_409_CONFLICT,
            reasons=evaluation_status['reasons'],
        )
    return evaluation_status


def _prepare_intent_to_award(tender, *, bid_id, awarded_vendor_id='', awarded_vendor_name='',
                             ec_override_reason='', lot=None):
    """Validate a proposed intent to award and return everything needed to apply it.

    This is pure validation — it never mutates. Both the RBF's "request" call and the
    Super Admin's "approve" call run it, so a queued request can never be approved on
    the strength of a bid that has since been withdrawn, a committee evaluation that
    has since been reopened, or a ranking that has since changed underneath it.
    """
    _check_intent_to_award_preconditions(tender, lot=lot)

    bid_id = str(bid_id or '').strip()
    if not bid_id:
        raise _IntentToAwardError('bid_id is required and must reference a submitted bid.')
    try:
        bid = TenderBid.objects.get(id=bid_id, tender=tender)
    except (TenderBid.DoesNotExist, ValueError, DjangoValidationError):
        raise _IntentToAwardError('Bid not found for this tender.')
    if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED}:
        raise _IntentToAwardError('Only submitted or under-review bids can be awarded.')

    ranking_payload = _build_lot_award_ranking(tender, lot) if lot is not None else _build_award_ranking(tender)
    recommended = ranking_payload.get('recommended')
    if not recommended:
        scope = f' for {lot.name}' if lot is not None else ''
        raise _IntentToAwardError(f'No qualifying bid passed the technical threshold{scope} for intent to award.')

    verdict = _ec_verdict_check(tender, str(bid.id), str(recommended['bid_id']), lot=lot)
    if not verdict['allowed']:
        ec_override_reason = str(ec_override_reason or '').strip()
        if not ec_override_reason:
            scope = f' for {lot.name}' if lot is not None else ''
            raise _IntentToAwardError(
                f'Intent to award{scope} can only be issued to the Evaluation Committee\'s agreed bid, '
                'or (when the committee has no verdict) the recommended '
                f'{"(highest weighted score) bid" if lot is not None else "winner with the highest combined score"}. '
                'A different choice requires an explicit EC override reason.',
                recommended_bid_id=recommended['bid_id'],
                recommended_vendor_id=recommended['vendor_id'],
                recommended_vendor_name=recommended['vendor_name'],
                ec_override_reason_required=True,
                ec=verdict['ec'],
            )
        verdict['reason'] = ec_override_reason

    awarded_vendor_id = str(awarded_vendor_id or '').strip()
    awarded_vendor_name = str(awarded_vendor_name or '').strip()
    if awarded_vendor_id and awarded_vendor_id != bid.vendor_id:
        raise _IntentToAwardError('awarded_vendor_id must match the selected bid vendor.')
    if awarded_vendor_name and bid.vendor_name and awarded_vendor_name != bid.vendor_name:
        raise _IntentToAwardError('awarded_vendor_name must match the selected bid vendor.')
    awarded_vendor_id = awarded_vendor_id or bid.vendor_id
    awarded_vendor_name = awarded_vendor_name or bid.vendor_name
    if not awarded_vendor_id and not awarded_vendor_name:
        raise _IntentToAwardError('awarded_vendor_id or awarded_vendor_name is required.')

    return {
        'bid': bid,
        'lot': lot,
        'ranking': ranking_payload,
        'recommended': recommended,
        'verdict': verdict,
        'awarded_vendor_id': awarded_vendor_id,
        'awarded_vendor_name': awarded_vendor_name,
    }


def _apply_intent_to_award(tender, prepared, *, actor, send_email=True, from_challenge=False):
    """Actually issue the intent to award: standstill + cooling-off, ACCEPTED on the
    winning bid, audit trail, bidder notices.

    This is the ONLY place the tender/lot award state is moved. It is reached only
    through a Super Admin approval (`approve_intent_award`) — the RBF's `award` /
    `award_lot` calls only ever queue a request.
    """
    bid = prepared['bid']
    lot = prepared['lot']
    verdict = prepared['verdict']
    now = timezone.now()
    cooling_off_days = tender.cooling_off_days if tender.cooling_off_days is not None else 7

    if lot is not None:
        # awarded_vendor_id/name are intentionally NOT set here — they represent a
        # CONFIRMED award and are only set in confirm_award, alongside awarded_at. This
        # lot's own cooling_off_until (not the tender's shared one) is what gates when
        # confirm_award may finalize it, so a lot whose intent is issued later than
        # another still gets its own full standstill window.
        lot_cooling_off_until = now + timedelta(days=cooling_off_days)
        lot.intent_to_award_bid = bid
        lot.intent_to_award_at = now
        lot.cooling_off_until = lot_cooling_off_until
        lot.save(update_fields=['intent_to_award_bid', 'intent_to_award_at', 'cooling_off_until', 'updated_at'])

        if tender.status != TenderStatus.STANDSTILL:
            tender.status = TenderStatus.STANDSTILL
            tender.intent_to_award_at = now
            tender.cooling_off_until = lot_cooling_off_until
            tender.save(update_fields=['status', 'intent_to_award_at', 'cooling_off_until', 'updated_at'])
    else:
        lot_cooling_off_until = None
        tender.status = TenderStatus.STANDSTILL
        tender.intent_to_award_bid = bid
        tender.intent_to_award_at = now
        tender.awarded_vendor_id = prepared['awarded_vendor_id']
        tender.awarded_vendor_name = prepared['awarded_vendor_name']
        tender.cooling_off_until = now + timedelta(days=cooling_off_days)
        tender.save(update_fields=[
            'status', 'intent_to_award_bid', 'intent_to_award_at', 'awarded_vendor_id',
            'awarded_vendor_name', 'cooling_off_until', 'updated_at',
        ])

    if bid.status != BidStatus.ACCEPTED:
        bid.status = BidStatus.ACCEPTED
        bid.reviewed_at = bid.reviewed_at or now
        bid.reviewed_by = bid.reviewed_by or (actor.full_name or actor.username)
        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])

    log_audit(
        actor,
        'lot_intent_to_award_issued' if lot is not None else 'intent_to_award_issued',
        tender,
        {
            'reference_number': tender.reference_number,
            'lot_id': str(lot.id) if lot is not None else None,
            'lot_name': lot.name if lot is not None else None,
            'bid_id': str(bid.id),
            'awarded_vendor_id': bid.vendor_id,
            'awarded_vendor_name': bid.vendor_name,
            'from_challenge': from_challenge,
            'ec_agreed_bid_id': verdict['ec'].get('agreed_bid_id'),
            'ec_consensus': verdict['ec'].get('consensus'),
            'ec_override_reason': verdict.get('reason', ''),
            'cooling_off_until': (lot_cooling_off_until or tender.cooling_off_until).isoformat(),
        },
    )

    _notify_intent_to_award(
        tender, prepared['ranking'], send_email,
        cooling_off_until=lot_cooling_off_until, lot_name=lot.name if lot is not None else None,
    )


def _intent_award_event(intent_request, prefix):
    """Build a notification event key that is unique per decision unit.

    Notification is unique on (recipient, event, linked_entity), so a lot-wise tender
    with several lots approving in turn would otherwise collide on one event.
    """
    if intent_request.lot_id:
        return f'{prefix}_lot_{intent_request.lot_id}'
    return prefix


def _clear_intent_award_approval_notifications(intent_request, *, to_recipients=None):
    """Retire the "awaiting approval" notices once their request is decided or withdrawn.

    Without this the Super Admin's bell keeps showing a request that is no longer in the
    queue, which reads as a stale action waiting to be taken.
    """
    qs = Notification.objects.filter(
        event=_intent_award_event(intent_request, 'intent_to_award_approval_requested'),
        linked_entity_id=str(intent_request.tender_id),
    )
    if to_recipients is not None:
        qs = qs.filter(recipient_id__in=[str(uid) for uid in to_recipients])
    return qs.update(status=NotificationStatus.READ)


def _notify_intent_award_request_submitted(tender, intent_request):
    """Tell the Super Admins an intent to award is waiting on their decision."""
    unit = f" — Lot: {intent_request.lot.name}" if intent_request.lot_id else ''
    vendor = intent_request.proposed_vendor_name or 'the proposed bidder'
    recipients = User.objects.filter(role=UserRole.ADMIN).only('id', 'full_name', 'username', 'email')
    for user in recipients:
        title = f'Intent to Award Awaiting Approval: {tender.reference_number}{unit}'
        body = (
            f'Tender: {tender.name} ({tender.reference_number})\n'
            f'Proposed winner: {vendor}\n'
            f'Raised by: {intent_request.requested_by_name or "Unknown"}'
            f'{" (upheld challenge)" if intent_request.from_challenge else ""}\n'
            f'EC agreed bid: {intent_request.ec_agreed_bid_id or "No committee verdict"}\n'
            f'EC consensus: {"Yes" if intent_request.ec_consensus else ("No" if intent_request.ec_consensus is False else "N/A")}\n'
            + (f'EC override reason: {intent_request.ec_override_reason}\n' if intent_request.ec_override_reason else '')
            + '\nThe intent to award, the standstill period and the bidder notices are only issued once you approve this request.'
        )
        Notification.objects.update_or_create(
            recipient_id=str(user.id),
            event=_intent_award_event(intent_request, 'intent_to_award_approval_requested'),
            linked_entity_id=str(tender.id),
            defaults={
                'recipient_name': user.full_name or user.username,
                'type': NotificationChannel.IN_APP,
                'title': title,
                'body': body,
                'status': NotificationStatus.SENT,
            },
        )
        if email_configured() and user.email:
            NotificationService.dispatch_email(title, body, [user.email])


def _notify_intent_award_decision(tender, intent_request, *, status_value, title, body):
    """Tell the RBF (and, for a challenge re-issue, the new bidder) how their request
    was decided."""
    recipients = set()
    if intent_request.requested_by_id:
        recipients.add(str(intent_request.requested_by_id))
    recipients.update(
        str(user.id)
        for user in User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id')
    )
    users = User.objects.filter(id__in=recipients).only('id', 'full_name', 'username', 'email')
    emails = []
    for user in users:
        Notification.objects.update_or_create(
            recipient_id=str(user.id),
            recipient_name=user.full_name or user.username,
            type=NotificationChannel.IN_APP,
            event=_intent_award_event(intent_request, f'intent_to_award_{status_value}'),
            linked_entity_id=str(tender.id),
            defaults={
                'title': title,
                'body': body,
                'status': NotificationStatus.SENT,
            },
        )
        if user.email:
            emails.append(user.email)

    # One SMTP session for the whole list, not one per recipient: the subject and body
    # are identical for everyone, so a per-user send bought nothing but a full TCP +
    # TLS handshake (and its timeout) multiplied by the number of RBF officials and
    # administrators on the platform. This runs after the award has committed, but it is
    # still in the request that the Super Admin is staring at, so it has to stay cheap.
    if emails and email_configured():
        NotificationService.dispatch_email(title, body, emails)


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
        if not request.user or not request.user.is_authenticated:
            return False
        action = 'create' if request.method == 'POST' else 'edit'
        return has_module_permission(request.user, 'tenders', action)



# Human-readable labels for the Activity tab's field-change diff — falls back to a
# title-cased version of the field name for anything not listed here.
TENDER_FIELD_LABELS = {
    'name': 'Tender Name',
    'department': 'Department Entity',
    'category': 'Category',
    'application_type': 'Application Type',
    'procurement_method': 'Procurement Method',
    'procurement_workflow': 'Procurement Workflow',
    'invited_by': 'Invited By',
    'time_for_completion': 'Time for Completion',
    'language_of_bid_submission': 'Language of Bid Submission',
    'budget_disclosure': 'Budget Disclosure',
    'funding_source': 'Funding Source',
    'budget': 'Budget Estimate',
    'bidding_currency': 'Bidding Currency',
    'currency_rates': 'Additional Currency Rates',
    'tender_security_required': 'Tender Security Required',
    'address_for_security': 'Security Address',
    'bidders_schedule_purchase': 'Bidders Must Purchase Schedule',
    'document_fee_amount': 'Document Fee Amount',
    'document_fee_type': 'Document Fee Type',
    'document_fee_refundable': 'Document Fee Refundable',
    'minimum_warranty_period_months': 'Minimum Warranty Period',
    'submission_method': 'Submission Method',
    'digital_signature_required': 'Digital Signature Required',
    'status': 'Status',
    'deadline': 'Submission Deadline',
    'eoi_deadline': 'EOI Deadline',
    'technical_deadline': 'Technical Deadline',
    'financial_deadline': 'Financial Deadline',
    'clarification_deadline': 'Clarification / Query Deadline',
    'site_visit_date': 'Site Visit Date',
    'bid_validity_period_days': 'Bid Validity Period (Days)',
    'pre_tender_meeting_info': 'Pre-Tender Meeting Info',
    'cooling_off_days': 'Cooling-Off Period (Days)',
    'technology_types': 'Technology Types',
    'target_districts': 'Target Districts',
    'target_site_type': 'Target Site Type',
    'minimum_service_tier': 'Minimum Service Tier',
    'approximate_installation_target': 'Approximate Installation Target',
    'bidders_eligibility': 'Bidders Eligibility',
    'instruction': 'Instructions',
    'contact_details': 'Contact Details',
    'address_for_document': 'Document Address',
    'place_for_opening': 'Place for Opening',
    'advertisement_channels': 'Advertisement Channels',
    'max_vendors_to_shortlist': 'Max Vendors to Shortlist',
    'schedule_file': 'Tender Schedule',
    'rfp_documents_file': 'RFP / Subsidy Framework',
    'milestone_payment_schedule_file': 'Milestone Payment Schedule',
    'is_verified': 'Verification Status',
    'publish_approval_status': 'Publish Approval Status',
}

# Only these are safe to snapshot/diff — concrete columns on Tender itself, excluding
# reverse relations (lots, required_documents, invited_vendors, etc.) which aren't
# meaningfully comparable as a single before/after value.
_TENDER_DIFFABLE_FIELDS = {
    f.name for f in Tender._meta.get_fields()
    if getattr(f, 'concrete', False) and not getattr(f, 'many_to_many', False) and not getattr(f, 'one_to_many', False)
}


def _tender_field_display_value(tender, field):
    """Render a Tender field's current value as a short, human-readable string (or
    None if empty) — used to build a before/after diff for the Activity tab."""
    try:
        value = getattr(tender, field)
    except Exception:
        return None
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (list, tuple)):
        return ', '.join(str(v) for v in value) if value else None
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str) if value else None
    if hasattr(value, 'url') and hasattr(value, 'name'):  # FileField/ImageField
        return value.name or None
    return str(value)


def _tender_field_snapshot(tender, fields):
    return {f: _tender_field_display_value(tender, f) for f in fields if f in _TENDER_DIFFABLE_FIELDS}


def _tender_field_changes(old_snapshot, new_snapshot):
    """Diff two snapshots into a list of {field, label, old, new} — only fields whose
    displayed value actually changed."""
    changes = []
    for field in sorted(set(old_snapshot) | set(new_snapshot)):
        old_val = old_snapshot.get(field)
        new_val = new_snapshot.get(field)
        if old_val == new_val:
            continue
        changes.append({
            'field': field,
            'label': TENDER_FIELD_LABELS.get(field, field.replace('_', ' ').title()),
            'old': old_val,
            'new': new_val,
        })
    return changes


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
        fields = ['status', 'category', 'department', 'is_verified', 'procurement_method', 'is_eoi_invite_only']


class TenderPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class TenderViewSet(viewsets.ModelViewSet):
    queryset = Tender.objects.all().order_by(Coalesce('published_at', 'created_at').desc())
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
        # Pending intent-to-award requests ride along on every tender payload so the
        # Award panel can show "Awaiting Super Admin approval" without extra round-trips.
        qs = Tender.objects.all().prefetch_related(
            models.Prefetch(
                'intent_award_requests',
                queryset=IntentToAwardRequest.objects.filter(
                    status=IntentAwardRequestStatus.PENDING,
                ).select_related('lot', 'bid'),
                to_attr='pending_intent_award_request_rows',
            ),
        ).order_by(Coalesce('published_at', 'created_at').desc())
        user = self.request.user
        # Handle unauthenticated users - return all published tenders
        if not user.is_authenticated:
            return qs.filter(status=TenderStatus.PUBLISHED)
        if user.role == UserRole.VENDOR:
            latest_prequalification = VendorPrequalification.objects.filter(
                vendor=user,
                status=PrequalificationStatus.APPROVED,
            ).order_by('-submitted_at', '-id').first()
            if latest_prequalification is None:
                return qs.none()
            invite_gated_values = _invite_gated_procurement_values()
            framework_values = _framework_procurement_values()
            not_open_values = invite_gated_values | framework_values
            framework_q = Q(pk__in=[])
            if framework_values:
                min_tier = _vendor_tier_number(latest_prequalification.tech_tier)
                tier_ok_q = Q(minimum_service_tier='') | Q(minimum_service_tier__isnull=True)
                if min_tier is not None:
                    qualifying_tiers = [t for t in ('Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5') if (_vendor_tier_number(t) or 0) <= min_tier]
                    tier_ok_q |= Q(minimum_service_tier__in=qualifying_tiers)
                tech_ok_q = Q(technology_types=[]) | Q(technology_types__isnull=True)
                for tag in (latest_prequalification.technology_types or []):
                    tech_ok_q |= Q(technology_types__contains=[tag])
                framework_q = Q(procurement_method__in=framework_values) & tier_ok_q & tech_ok_q
            return qs.filter(status=TenderStatus.PUBLISHED).filter(
                Q(invited_vendors__vendor=user)
                # A Restricted-family 'EOI → Combined' tender is still visible to every
                # approved vendor so they can see and respond to the EOI invite; only the
                # combined (actual tender) stage is limited to shortlisted/invited vendors.
                | Q(procurement_method__in=invite_gated_values, procurement_workflow=ProcurementWorkflow.EOI_COMBINED)
                | ~Q(procurement_method__in=not_open_values)
                | framework_q
            ).distinct()
        if user.role == UserRole.EVALUATION_COMMITTEE:
            return qs.filter(evaluation_committee_members__member=user).distinct()
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return TenderListSerializer
        return TenderSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if (
            user.is_authenticated
            and getattr(user, 'role', None) == UserRole.VENDOR
            and instance.status == TenderStatus.PUBLISHED
        ):
            vendor_name = (
                getattr(user, 'organization_name', '')
                or getattr(user, 'full_name', '')
                or user.get_username()
            )
            TenderViewLog.objects.get_or_create(
                tender=instance,
                vendor=user,
                defaults={'vendor_name': vendor_name},
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='viewers')
    def viewers(self, request, pk=None):
        """List the vendors that have viewed this tender."""
        if getattr(request.user, 'role', None) not in {
            UserRole.RBF_OFFICIAL,
            UserRole.ADMIN,
        }:
            raise PermissionDenied('Only RMT and Admin users can view tender viewers.')

        tender = self.get_object()
        viewers = tender.view_logs.values(
            'vendor_id',
            'vendor_name',
            'viewed_at',
        )
        return Response({
            'total_viewers': tender.view_logs.count(),
            'viewers': list(viewers),
        })

    def _assert_write_permission(self):
        user = self.request.user
        if getattr(user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can create or modify tenders.')

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in SAFE_METHODS and getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            if self.action not in {'create_challenge', 'attest_coi', 'declare_coi'}:
                self.permission_denied(request, message='Only the RBF Management Team can create or modify tenders.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        data = request.data
        if not data.get('stage_type'):
            data = {**data, 'stage_type': 'Pre-Qualification'}
        response = super().create(request, *args, **kwargs)
        tender = self.get_queryset().get(pk=response.data['id'])
        log_audit(
            request.user,
            'tender_created',
            tender,
            {'module': 'tenders', 'reference_number': tender.reference_number, 'notes': 'Tender created.'},
        )
        return response

    def _update_with_audit(self, request, partial, *args, **kwargs):
        self._assert_write_permission()
        tender = self.get_object()
        old_status = tender.status
        submitted_fields = sorted(str(field) for field in request.data.keys())
        old_snapshot = _tender_field_snapshot(tender, submitted_fields)
        serializer = self.get_serializer(tender, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(tender, '_prefetched_objects_cache', None):
            tender._prefetched_objects_cache = {}
        response = Response(serializer.data)
        tender.refresh_from_db()
        new_snapshot = _tender_field_snapshot(tender, submitted_fields)
        field_changes = _tender_field_changes(old_snapshot, new_snapshot)
        changed_labels = [c['label'] for c in field_changes]
        log_audit(
            request.user,
            'tender_updated',
            tender,
            {
                'module': 'tenders',
                'reference_number': tender.reference_number,
                'changed_fields': [c['field'] for c in field_changes],
                'field_changes': field_changes,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender edited. Fields changed: {", ".join(changed_labels) or "none"}.',
            },
        )
        return response

    def update(self, request, *args, **kwargs):
        return self._update_with_audit(request, False, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self._update_with_audit(request, True, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()
        old_status = tender.status

        tender.is_verified = True
        tender.verified_at = timezone.now()
        tender.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
        log_audit(
            request.user,
            'tender_verified',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender {tender.reference_number} marked as verified.',
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """Audit trail specific to this tender's own lifecycle events (newest first)."""
        tender = self.get_object()
        logs = AuditLog.objects.filter(
            entity_type='Tender',
            entity_id=str(tender.id),
            record_type='Tender',
            record_id=tender.id,
        ).order_by('-created_at')
        serializer = AuditLogSerializer(logs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=False, methods=['get'])
    def pending_publish_approvals(self, request):
        """Super Admin-only list of tenders awaiting publish approval."""
        user = request.user
        if not user.is_authenticated or getattr(user, 'role', None) != UserRole.ADMIN:
            raise PermissionDenied('Only the Platform Administrator (Super Admin) can view pending publish approvals.')
        qs = Tender.objects.filter(
            status=TenderStatus.PENDING_PUBLISH_APPROVAL,
            publish_approval_status=PublishApprovalStatus.PENDING,
        ).order_by('-publish_approval_requested_at')
        serializer = TenderSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def tenders_ready_for_award(self, request):
        """RBF Official/Admin-only list of tenders relevant to the award pipeline:
        either evaluation is complete and awaiting an award decision, already mid-award
        (intent issued, in standstill, disputed), or already awarded and still moving
        through contract approval / milestone assignment. Backs the dedicated "Award
        Management" tab so Tender Management itself never needs to surface award
        actions."""
        if getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team or Super Admin can view the award pipeline.')
        candidates = Tender.objects.filter(
            status__in=[TenderStatus.PUBLISHED, TenderStatus.EVALUATION, TenderStatus.STANDSTILL,
                        TenderStatus.DISPUTED, TenderStatus.AWARDED],
        ).order_by('-updated_at')
        results = [
            t for t in candidates
            if t.status in {TenderStatus.STANDSTILL, TenderStatus.DISPUTED, TenderStatus.AWARDED}
            or bool(t.intent_to_award_at)
            or _tender_evaluation_status(t)['complete']
        ]
        serializer = TenderSerializer(results, many=True, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def eoi_invite_candidates(self, request):
        """EOI Invite tenders eligible to be linked from a new EOI → Combined tender:
        published or closed (so their EOI window is open or has concluded), with at
        least one shortlisted vendor."""
        if getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can view EOI Invite candidates.')
        qs = Tender.objects.filter(
            is_eoi_invite_only=True,
            status__in=[TenderStatus.PUBLISHED, TenderStatus.CLOSED],
        ).annotate(
            invited_count=Count('invited_vendors'),
            linked_count=Count('linked_tenders'),  # reverse FK from Tender.linked_eoi_tender
        ).filter(
            invited_count__gt=0,
            linked_count=0,  # exclude EOI invites already used for a tender
        ).order_by('-created_at')
        return Response([
            {
                'id': str(t.id),
                'reference_number': t.reference_number,
                'name': t.name,
                'status': t.status,
                'eoi_deadline': t.eoi_deadline,
                'invited_vendor_count': t.invited_count,
            }
            for t in qs
        ], status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def request_publish_approval(self, request, pk=None):
        """RBF submits a tender for Super Admin approval before publication."""
        self._assert_write_permission()
        tender = self.get_object()

        if not tender.is_verified:
            return Response({'detail': 'Tender must be verified before requesting publish approval.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.status == TenderStatus.PUBLISHED:
            return Response({'detail': 'Tender is already published.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.status == TenderStatus.CLOSED:
            return Response({'detail': 'Closed tender cannot be published.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.publish_approval_status == PublishApprovalStatus.PENDING:
            return Response({'detail': 'Publish approval has already been requested and is pending review.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = tender.status
        old_pub_status = tender.publish_approval_status
        tender.status = TenderStatus.PENDING_PUBLISH_APPROVAL
        tender.publish_approval_status = PublishApprovalStatus.PENDING
        tender.publish_approval_requested_at = timezone.now()
        tender.publish_approval_reviewed_at = None
        tender.publish_approval_reviewed_by = ''
        tender.publish_approval_notes = ''
        tender.save(update_fields=[
            'status', 'publish_approval_status', 'publish_approval_requested_at',
            'publish_approval_reviewed_at', 'publish_approval_reviewed_by',
            'publish_approval_notes', 'updated_at',
        ])
        log_audit(
            request.user,
            'tender_publish_approval_requested',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender {tender.reference_number} submitted for Super Admin publish approval (was {old_pub_status}).',
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve_publish(self, request, pk=None):
        """Super Admin approves the tender for publication."""
        self._assert_admin_approval_permission()
        tender = self.get_object()

        if tender.status != TenderStatus.PENDING_PUBLISH_APPROVAL or tender.publish_approval_status != PublishApprovalStatus.PENDING:
            return Response({'detail': 'Tender is not awaiting publish approval.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = tender.status
        tender.publish_approval_status = PublishApprovalStatus.APPROVED
        tender.publish_approval_reviewed_at = timezone.now()
        tender.publish_approval_reviewed_by = self._admin_reference(request.user)
        tender.publish_approval_notes = (request.data.get('notes') or '').strip()
        tender.status = TenderStatus.DRAFT  # Return to draft so RBF can proceed to publish
        tender.save(update_fields=[
            'publish_approval_status', 'publish_approval_reviewed_at',
            'publish_approval_reviewed_by', 'publish_approval_notes', 'status', 'updated_at',
        ])
        log_audit(
            request.user,
            'tender_publish_approved',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender {tender.reference_number} approved for publication by Super Admin.',
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject_publish(self, request, pk=None):
        """Super Admin rejects the tender publication request."""
        self._assert_admin_approval_permission()
        tender = self.get_object()

        if tender.status != TenderStatus.PENDING_PUBLISH_APPROVAL or tender.publish_approval_status != PublishApprovalStatus.PENDING:
            return Response({'detail': 'Tender is not awaiting publish approval.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = tender.status
        tender.publish_approval_status = PublishApprovalStatus.REJECTED
        tender.publish_approval_reviewed_at = timezone.now()
        tender.publish_approval_reviewed_by = self._admin_reference(request.user)
        tender.publish_approval_notes = (request.data.get('notes') or '').strip()
        tender.status = TenderStatus.DRAFT
        tender.save(update_fields=[
            'publish_approval_status', 'publish_approval_reviewed_at',
            'publish_approval_reviewed_by', 'publish_approval_notes', 'status', 'updated_at',
        ])
        log_audit(
            request.user,
            'tender_publish_rejected',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender {tender.reference_number} publish approval rejected by Super Admin.'
                         + (f' Reason: {tender.publish_approval_notes}' if tender.publish_approval_notes else ''),
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def request_publish_changes(self, request, pk=None):
        """Super Admin asks the RBF to revise the tender before it can be published.

        Unlike reject_publish, this is not a final decision — the tender returns to
        Draft with a distinct 'changes_requested' status so the RBF can see this was
        a request for revisions (with notes explaining what to change) rather than an
        outright rejection, then edit and resubmit for approval.
        """
        self._assert_admin_approval_permission()
        tender = self.get_object()

        if tender.status != TenderStatus.PENDING_PUBLISH_APPROVAL or tender.publish_approval_status != PublishApprovalStatus.PENDING:
            return Response({'detail': 'Tender is not awaiting publish approval.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = tender.status
        tender.publish_approval_status = PublishApprovalStatus.CHANGES_REQUESTED
        tender.publish_approval_reviewed_at = timezone.now()
        tender.publish_approval_reviewed_by = self._admin_reference(request.user)
        tender.publish_approval_notes = (request.data.get('notes') or '').strip()
        tender.status = TenderStatus.DRAFT
        tender.save(update_fields=[
            'publish_approval_status', 'publish_approval_reviewed_at',
            'publish_approval_reviewed_by', 'publish_approval_notes', 'status', 'updated_at',
        ])
        log_audit(
            request.user,
            'tender_publish_changes_requested',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'notes': f'Tender {tender.reference_number} sent back to the RBF for changes by Super Admin.'
                         + (f' Requested changes: {tender.publish_approval_notes}' if tender.publish_approval_notes else ''),
            },
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status == TenderStatus.CLOSED:
            return Response({'detail': 'Closed tender cannot be published.'}, status=status.HTTP_400_BAD_REQUEST)
        # An EOI Invite carries no award/financial risk (see is_eoi_invite_only) — it
        # skips the verification + Super Admin publish-approval pipeline real tenders
        # go through, so RBF Officials can publish one directly.
        if not tender.is_eoi_invite_only:
            if not tender.is_verified:
                return Response({'detail': 'Tender must be verified before publishing.'}, status=status.HTTP_400_BAD_REQUEST)
            if tender.publish_approval_status != PublishApprovalStatus.APPROVED:
                return Response({'detail': 'This tender must be approved by the Super Admin before it can be published.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = tender.status
        tender.status = TenderStatus.PUBLISHED
        tender.published_at = timezone.now()
        tender.publish_approval_status = PublishApprovalStatus.NOT_REQUESTED
        tender.publish_approval_requested_at = None
        tender.publish_approval_reviewed_at = None
        tender.publish_approval_reviewed_by = ''
        tender.publish_approval_notes = ''
        tender.save(update_fields=[
            'status', 'published_at', 'publish_approval_status', 'publish_approval_requested_at',
            'publish_approval_reviewed_at', 'publish_approval_reviewed_by', 'publish_approval_notes', 'updated_at',
        ])
        log_audit(
            request.user,
            'tender_published',
            tender,
            {
                'reference_number': tender.reference_number,
                'old_status': old_status,
                'new_status': tender.status,
                'publishApprovalStatus': 'approved',
                'notes': f'Tender {tender.reference_number} published.',
            },
        )

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

    def _assert_admin_approval_permission(self):
        user = self.request.user
        if getattr(user, 'role', None) != UserRole.ADMIN:
            raise PermissionDenied('Only the Platform Administrator (Super Admin) can approve or reject tender publication.')

    def _admin_reference(self, user):
        name = (getattr(user, 'full_name', None) or '').strip()
        return name or getattr(user, 'username', None) or str(user.id)

    def _notify_vendors_of_publish(self, tender: Tender, send_email=True, notify_all=True):
        from rbf.users.models import User, VendorPrequalification, PrequalificationStatus

        # Always notify approved (pre-qualified) vendors
        vendors = list(
            User.objects.filter(role=UserRole.VENDOR)
            .filter(prequalifications__status=PrequalificationStatus.APPROVED)
            .distinct()
            .only('id', 'email', 'full_name', 'username', 'role')
        )
        stakeholders = list(
            User.objects.filter(role__in={UserRole.DOE_OFFICER, UserRole.UNDP_DONOR})
            .distinct()
            .only('id', 'email', 'full_name', 'username', 'role')
        )
        recipients = vendors + stakeholders
        recipient_count = len(recipients)

        subject = f"Tender Published: {tender.name}"
        body = (
            f"A new tender has been published.\n\n"
            f"Reference: {tender.reference_number}\n"
            f"Name: {tender.name}\n"
            f"Category: {tender.category}\n"
            f"Deadline: {tender.deadline}\n"
        )

        vendor_link = build_frontend_url(f'/vendor/tenders?view=details&tenderId={tender.id}', request=self.request)
        official_link = build_frontend_url(f'/rbf-official/tenders?view=details&tenderId={tender.id}', request=self.request)

        # In-app notifications
        NotificationService.notify_users(
            users=vendors,
            title=subject,
            body=f"{body}View details: {vendor_link}\n",
            event='tender_published',
            linked_entity_id=tender.id,
        )
        NotificationService.notify_users(
            users=stakeholders,
            title=subject,
            body=f"{body}View details: {official_link}\n",
            event='tender_published',
            linked_entity_id=tender.id,
        )

        email_enabled = send_email and email_configured()

        email_recipients = []
        email_error = None
        if email_enabled:
            # Role-aware deep links: vendors land on the vendor portal, staff on the RBF portal.
            groups = [
                (vendors, vendor_link),
                (stakeholders, official_link),
            ]
            for group_recipients, group_link in groups:
                group_emails = list(
                    dict.fromkeys(
                        r.email for r in group_recipients if r.email
                    )
                )
                if not group_emails:
                    continue
                email_recipients.extend(group_emails)
                sent = NotificationService.dispatch_email(
                    subject,
                    f"{body}View details: {group_link}\n",
                    group_emails,
                )
                if sent <= 0:
                    email_error = email_error or f'Email delivery failed for {len(group_emails)} recipient(s).'

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
        """RBF selects the winner for a whole tender.

        This only *proposes* the intent to award: it queues a pending
        IntentToAwardRequest for Super Admin approval and changes nothing on the
        tender — no standstill, no cooling-off clock, no bidder notices. The intent is
        actually issued by `approve_intent_award`, which only a Super Admin can call.
        """
        self._assert_write_permission()
        tender = self.get_object()

        if tender.lots.exists():
            return Response(
                {'detail': 'This is a lot-wise tender — use award_lot with a lot_id instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            prepared = _prepare_intent_to_award(
                tender,
                bid_id=request.data.get('bid_id'),
                awarded_vendor_id=request.data.get('awarded_vendor_id') or '',
                awarded_vendor_name=request.data.get('awarded_vendor_name') or '',
                ec_override_reason=request.data.get('ec_override_reason') or '',
            )
            intent_request = self._queue_intent_award_request(
                tender, prepared, actor=request.user,
                send_email=request.data.get('send_email', True),
            )
        except _IntentToAwardError as exc:
            return exc.as_response()

        data = TenderSerializer(tender, context={'request': request}).data
        data['intent_award_request'] = IntentToAwardRequestSerializer(
            intent_request, context={'request': request},
        ).data
        data['award_ranking'] = prepared['ranking']['rows']
        data['recommended_bid_id'] = prepared['recommended']['bid_id']
        data['recommended_vendor_id'] = prepared['recommended']['vendor_id']
        data['recommended_vendor_name'] = prepared['recommended']['vendor_name']
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def award_ranking(self, request, pk=None):
        tender = self.get_object()
        lots = list(tender.lots.all())
        if lots:
            return Response({
                'is_lot_wise': True,
                'cooling_off_days': tender.cooling_off_days,
                'technical_weight': tender.technical_weight,
                'financial_weight': tender.financial_weight,
                'evaluation_status': _tender_evaluation_status(tender),
                'lots': [
                    _build_lot_award_ranking(
                        tender, lot, include_pending_request=True, request=request,
                    )
                    for lot in lots
                ],
            }, status=status.HTTP_200_OK)
        ranking_payload = _build_award_ranking(tender)
        ranking_payload['evaluation_status'] = _tender_evaluation_status(tender)
        ranking_payload['pending_intent_award_request'] = _pending_intent_award_request_payload(
            tender, request=request,
        )
        return Response(ranking_payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def award_lot(self, request, pk=None):
        """RBF selects the winner for one lot of a lot-wise tender.

        Like `award`, this only queues the request. Each lot gets its own request and
        its own Super Admin decision, and the lot's independent standstill/cooling-off
        window (TenderLot.cooling_off_until) only starts once THAT lot's request is
        approved — so a lot approved later still gets its own full standstill window.
        """
        self._assert_write_permission()
        tender = self.get_object()

        lot_id = str(request.data.get('lot_id') or '').strip()
        bid_id = str(request.data.get('bid_id') or '').strip()
        if not lot_id or not bid_id:
            return Response({'detail': 'lot_id and bid_id are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lot = tender.lots.get(id=lot_id)
        except (TenderLot.DoesNotExist, ValueError, DjangoValidationError):
            return Response({'detail': 'Lot not found for this tender.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            prepared = _prepare_intent_to_award(
                tender, bid_id=bid_id,
                ec_override_reason=request.data.get('ec_override_reason') or '',
                lot=lot,
            )
            intent_request = self._queue_intent_award_request(
                tender, prepared, actor=request.user,
                send_email=request.data.get('send_email', True),
            )
        except _IntentToAwardError as exc:
            return exc.as_response()

        data = TenderSerializer(tender, context={'request': request}).data
        data['intent_award_request'] = IntentToAwardRequestSerializer(
            intent_request, context={'request': request},
        ).data
        return Response(data, status=status.HTTP_200_OK)

    # --- Intent to Award approval (RBF proposes, Super Admin decides) ---

    def _queue_intent_award_request(self, tender, prepared, *, actor, send_email=True, from_challenge=False):
        """Persist a PENDING IntentToAwardRequest for a validated proposal and alert the
        Super Admins. Raises _IntentToAwardError when the decision unit is already
        queued, so a tender can never sit in the approval queue twice for the same
        lot (or whole-tender award)."""
        lot = prepared['lot']
        scope = f' for {lot.name}' if lot is not None else ''
        already_pending = (
            f'An intent to award{scope} is already awaiting Super Admin approval. '
            'Withdraw the pending request before proposing a different bidder.'
        )
        pending = _pending_intent_award_request_queryset(tender, lot=lot).first()
        if pending is not None:
            raise _IntentToAwardError(
                already_pending, intent_award_request_id=str(pending.id),
            )

        try:
            with transaction.atomic():
                # The unique constraint (one pending request per tender/lot) is the real
                # guard: two concurrent proposals would both pass the check above, and
                # without catching it the loser would surface as a 500, not a clean 400.
                intent_request = IntentToAwardRequest.objects.create(
                    tender=tender,
                    lot=lot,
                    bid=prepared['bid'],
                    proposed_vendor_id=prepared['awarded_vendor_id'],
                    proposed_vendor_name=prepared['awarded_vendor_name'],
                    ec_agreed_bid_id=str(prepared['verdict']['ec'].get('agreed_bid_id') or ''),
                    ec_consensus=prepared['verdict']['ec'].get('consensus'),
                    ec_override_reason=prepared['verdict'].get('reason', '') or '',
                    send_email=bool(send_email),
                    requested_by=actor if getattr(actor, 'pk', None) else None,
                    requested_by_name=self._admin_reference(actor),
                    from_challenge=from_challenge,
                )
        except IntegrityError:
            raise _IntentToAwardError(already_pending)
        log_audit(
            actor,
            'lot_intent_to_award_approval_requested' if lot is not None else 'intent_to_award_approval_requested',
            tender,
            {
                'reference_number': tender.reference_number,
                'intent_award_request_id': str(intent_request.id),
                'lot_id': str(lot.id) if lot is not None else None,
                'lot_name': lot.name if lot is not None else None,
                'bid_id': str(prepared['bid'].id),
                'proposed_vendor_id': prepared['awarded_vendor_id'],
                'proposed_vendor_name': prepared['awarded_vendor_name'],
                'ec_agreed_bid_id': intent_request.ec_agreed_bid_id,
                'ec_consensus': intent_request.ec_consensus,
                'ec_override_reason': intent_request.ec_override_reason,
            },
        )
        _notify_intent_award_request_submitted(tender, intent_request)
        return intent_request

    def _get_pending_intent_award_request(self, tender, request):
        """Resolve the request a decision action applies to: by `request_id` when the
        caller names one, otherwise by `lot_id` (lot-wise) / the whole-tender unit."""
        qs = tender.intent_award_requests.filter(status=IntentAwardRequestStatus.PENDING)
        request_id = str(request.data.get('request_id') or '').strip()
        if request_id:
            return qs.filter(id=request_id).select_related('lot', 'bid').first()
        lot_id = str(request.data.get('lot_id') or '').strip()
        if lot_id:
            return qs.filter(lot_id=lot_id).select_related('lot', 'bid').first()
        return qs.filter(lot__isnull=True).select_related('lot', 'bid').first()

    def _assert_intent_award_approval_permission(self):
        if getattr(self.request.user, 'role', None) != UserRole.ADMIN:
            raise PermissionDenied(
                'Only the Platform Administrator (Super Admin) can decide an intent to award request.'
            )

    def _no_pending_request_response(self):
        return Response(
            {'detail': 'No intent to award is awaiting approval for this tender.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=['get'])
    def pending_intent_award_approvals(self, request):
        """Super Admin-only queue of intent-to-award requests awaiting a decision."""
        if getattr(request.user, 'role', None) != UserRole.ADMIN:
            raise PermissionDenied(
                'Only the Platform Administrator (Super Admin) can view pending intent to award approvals.'
            )
        qs = (
            IntentToAwardRequest.objects.filter(status=IntentAwardRequestStatus.PENDING)
            .select_related('tender', 'lot', 'bid', 'requested_by')
            .order_by('requested_at')
        )
        return Response(IntentToAwardRequestSerializer(qs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def intent_award_requests(self, request, pk=None):
        """Every intent-to-award request raised for this tender, decided or not."""
        if getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied(
                'Only the RBF Management Team or Super Admin can view intent to award requests.'
            )
        tender = self.get_object()
        qs = (
            tender.intent_award_requests
            .select_related('lot', 'bid', 'requested_by', 'reviewed_by')
            .order_by('-requested_at')
        )
        return Response(IntentToAwardRequestSerializer(qs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def approve_intent_award(self, request, pk=None):
        """Super Admin approves a queued intent to award.

        This is the moment the intent actually takes effect: the tender/lot enters
        standstill, the cooling-off clock starts, the winning bid is marked ACCEPTED and
        the bidder notices go out. The proposal is re-validated first, so a request that
        went stale while it sat in the queue (bid withdrawn, evaluation reopened) is
        refused rather than issued blind.
        """
        self._assert_intent_award_approval_permission()
        tender = self.get_object()
        intent_request = self._get_pending_intent_award_request(tender, request)
        if intent_request is None:
            return self._no_pending_request_response()

        notes = (request.data.get('notes') or '').strip()
        unit = f' — Lot: {intent_request.lot.name}' if intent_request.lot_id else ''
        with transaction.atomic():
            # Re-read under a row lock: a second Super Admin click (or a reject racing
            # this approve) must not both decide the same request and both issue the
            # intent, which would reset the cooling-off window and re-notify bidders.
            locked = IntentToAwardRequest.objects.select_for_update().filter(
                pk=intent_request.pk, status=IntentAwardRequestStatus.PENDING,
            ).first()
            if locked is None:
                return self._no_pending_request_response()
            intent_request = locked
            try:
                prepared = _prepare_intent_to_award(
                    tender,
                    bid_id=intent_request.bid_id,
                    awarded_vendor_id=intent_request.proposed_vendor_id,
                    awarded_vendor_name=intent_request.proposed_vendor_name,
                    ec_override_reason=intent_request.ec_override_reason,
                    lot=intent_request.lot,
                )
            except _IntentToAwardError as exc:
                return exc.as_response()

            intent_request.status = IntentAwardRequestStatus.APPROVED
            intent_request.reviewed_by = request.user
            intent_request.reviewed_by_name = self._admin_reference(request.user)
            intent_request.reviewed_at = timezone.now()
            intent_request.notes = notes
            intent_request.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'notes',
            ])
            _apply_intent_to_award(
                tender, prepared, actor=request.user,
                send_email=intent_request.send_email,
                from_challenge=intent_request.from_challenge,
            )
            log_audit(
                request.user,
                'intent_to_award_approved',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'intent_award_request_id': str(intent_request.id),
                    'lot_id': str(intent_request.lot_id) if intent_request.lot_id else None,
                    'bid_id': str(intent_request.bid_id),
                    'proposed_vendor_id': intent_request.proposed_vendor_id,
                    'proposed_vendor_name': intent_request.proposed_vendor_name,
                    'notes': notes or f'Intent to award approved by Super Admin{unit}.',
                },
            )

        winner = intent_request.proposed_vendor_name or str(intent_request.bid_id)
        _clear_intent_award_approval_notifications(intent_request)
        _notify_intent_award_decision(
            tender, intent_request,
            status_value='approved',
            title=f'Intent to Award Approved: {tender.reference_number}{unit}',
            body=(
                f'The Super Admin approved the intent to award{unit} to {winner}.\n'
                'The standstill period has started and the bidders have been notified.\n'
                + (f'Approval notes: {notes}' if notes else '')
            ),
        )

        data = TenderSerializer(tender, context={'request': request}).data
        data['intent_award_request'] = IntentToAwardRequestSerializer(
            intent_request, context={'request': request},
        ).data
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def request_intent_award_changes(self, request, pk=None):
        """Super Admin sends the proposal back to the RBF, which can then pick a
        different bidder and queue a fresh request. Nothing is issued."""
        return self._close_intent_award_request(
            request,
            status_value=IntentAwardRequestStatus.CHANGES_REQUESTED,
            log_action='intent_to_award_changes_requested',
            require_notes=True,
            title_suffix='Changes Requested',
            body_text=(
                'The Super Admin asked for changes before the intent to award can be issued. '
                'Nothing has been issued and no bidder has been notified. Pick a different '
                'bidder (or revise your justification) and submit a new request.'
            ),
        )

    @action(detail=True, methods=['post'])
    def reject_intent_award(self, request, pk=None):
        """Super Admin refuses the proposal outright. Nothing is issued."""
        return self._close_intent_award_request(
            request,
            status_value=IntentAwardRequestStatus.REJECTED,
            log_action='intent_to_award_rejected',
            require_notes=False,
            title_suffix='Rejected',
            body_text=(
                'The Super Admin rejected the intent to award request. Nothing has been '
                'issued and no bidder has been notified.'
            ),
        )

    def _close_intent_award_request(self, request, *, status_value, log_action, require_notes,
                                    title_suffix, body_text):
        self._assert_intent_award_approval_permission()
        tender = self.get_object()
        intent_request = self._get_pending_intent_award_request(tender, request)
        if intent_request is None:
            return self._no_pending_request_response()

        notes = (request.data.get('notes') or '').strip()
        if require_notes and not notes:
            return Response(
                {'detail': 'Notes are required when requesting changes — tell the RBF what to revise.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Same row lock as approve: a decision racing an approval must not both land.
            locked = IntentToAwardRequest.objects.select_for_update().filter(
                pk=intent_request.pk, status=IntentAwardRequestStatus.PENDING,
            ).first()
            if locked is None:
                return self._no_pending_request_response()
            intent_request = locked
            intent_request.status = status_value
            intent_request.reviewed_by = request.user
            intent_request.reviewed_by_name = self._admin_reference(request.user)
            intent_request.reviewed_at = timezone.now()
            intent_request.notes = notes
            intent_request.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'notes',
            ])

        _clear_intent_award_approval_notifications(intent_request)
        unit = f' — Lot: {intent_request.lot.name}' if intent_request.lot_id else ''
        log_audit(
            request.user,
            log_action,
            tender,
            {
                'reference_number': tender.reference_number,
                'intent_award_request_id': str(intent_request.id),
                'lot_id': str(intent_request.lot_id) if intent_request.lot_id else None,
                'bid_id': str(intent_request.bid_id),
                'proposed_vendor_id': intent_request.proposed_vendor_id,
                'proposed_vendor_name': intent_request.proposed_vendor_name,
                'notes': notes or f'Intent to award {title_suffix.lower()} by Super Admin{unit}.',
            },
        )
        _notify_intent_award_decision(
            tender, intent_request,
            status_value=status_value,
            title=f'Intent to Award {title_suffix}: {tender.reference_number}{unit}',
            body=body_text + (f'\n\nSuper Admin notes: {notes}' if notes else ''),
        )

        data = TenderSerializer(tender, context={'request': request}).data
        data['intent_award_request'] = IntentToAwardRequestSerializer(
            intent_request, context={'request': request},
        ).data
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def withdraw_intent_award_request(self, request, pk=None):
        """The RBF pulls its own queued request back so a different bidder can be proposed.

        Only the official who raised the request may withdraw it (or a Super Admin) — a
        queued request belongs to the person who submitted it, not to the whole team.
        """
        self._assert_write_permission()
        tender = self.get_object()
        intent_request = self._get_pending_intent_award_request(tender, request)
        if intent_request is None:
            return self._no_pending_request_response()

        is_requester = str(intent_request.requested_by_id or '') == str(self.request.user.pk or '')
        if not (is_requester or getattr(self.request.user, 'role', None) == UserRole.ADMIN):
            raise PermissionDenied(
                'Only the RBF official who submitted this request (or a Super Admin) can withdraw it.'
            )

        notes = (request.data.get('notes') or '').strip()
        with transaction.atomic():
            locked = IntentToAwardRequest.objects.select_for_update().filter(
                pk=intent_request.pk, status=IntentAwardRequestStatus.PENDING,
            ).first()
            if locked is None:
                return self._no_pending_request_response()
            intent_request = locked
            intent_request.status = IntentAwardRequestStatus.WITHDRAWN
            intent_request.reviewed_by = request.user
            intent_request.reviewed_by_name = self._admin_reference(request.user)
            intent_request.reviewed_at = timezone.now()
            if notes:
                intent_request.notes = notes
            intent_request.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'notes',
            ])

        # The Super Admins were told to expect a decision on this; drop that notice.
        _clear_intent_award_approval_notifications(intent_request)
        unit = f' for {intent_request.lot.name}' if intent_request.lot_id else ''
        log_audit(
            request.user,
            'intent_to_award_request_withdrawn',
            tender,
            {
                'reference_number': tender.reference_number,
                'intent_award_request_id': str(intent_request.id),
                'lot_id': str(intent_request.lot_id) if intent_request.lot_id else None,
                'bid_id': str(intent_request.bid_id),
                'notes': notes or f'Intent to award request{unit} withdrawn by the RBF before a Super Admin decision.',
            },
        )
        data = TenderSerializer(tender, context={'request': request}).data
        data['intent_award_request'] = IntentToAwardRequestSerializer(
            intent_request, context={'request': request},
        ).data
        return Response(data, status=status.HTTP_200_OK)

    def _assert_super_admin(self):
        if getattr(self.request.user, 'role', None) != UserRole.ADMIN:
            raise PermissionDenied('Only Platform Administrator (Super Admin) can manage the Evaluation Committee.')

    @action(detail=True, methods=['get', 'post'], url_path='evaluation_committee')
    def evaluation_committee(self, request, pk=None):
        """Super Admin assembles this tender's Evaluation Committee: 3-5 members,
        each drawn from users holding the Evaluation Committee role. GET returns the
        current roster plus the pool of eligible users to choose from; POST replaces
        the roster."""
        tender = self.get_object()
        if request.method == 'GET':
            self._assert_super_admin()
            roster = tender.evaluation_committee_members.select_related('member', 'assigned_by').all()
            pool = User.objects.filter(role=UserRole.EVALUATION_COMMITTEE, status='Active').order_by('full_name')
            return Response({
                'roster': TenderEvaluationCommitteeMemberSerializer(roster, many=True, context={'request': request}).data,
                'available_members': [
                    {'id': str(u.id), 'full_name': u.full_name, 'email': u.email}
                    for u in pool
                ],
            })

        self._assert_super_admin()
        member_ids = request.data.get('member_ids')
        if not isinstance(member_ids, list):
            return Response({'detail': 'member_ids must be a list of user ids.'}, status=status.HTTP_400_BAD_REQUEST)
        member_ids = [str(mid) for mid in member_ids]
        if not (3 <= len(set(member_ids)) <= 5):
            return Response({'detail': 'An Evaluation Committee must have between 3 and 5 members.'}, status=status.HTTP_400_BAD_REQUEST)
        members = list(User.objects.filter(id__in=member_ids))
        if len(members) != len(set(member_ids)):
            return Response({'detail': 'One or more selected users could not be found.'}, status=status.HTTP_400_BAD_REQUEST)
        non_ec_members = [u for u in members if u.role != UserRole.EVALUATION_COMMITTEE]
        if non_ec_members:
            return Response(
                {'detail': f'These users do not hold the Evaluation Committee role: {", ".join(u.full_name or u.username for u in non_ec_members)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previously_assigned_ids = set(tender.evaluation_committee_members.values_list('member_id', flat=True))
        previous_attestation = {
            m.member_id: m for m in tender.evaluation_committee_members.select_related('member').all()
        }
        with transaction.atomic():
            tender.evaluation_committee_members.all().delete()
            TenderEvaluationCommitteeMember.objects.bulk_create([
                TenderEvaluationCommitteeMember(
                    tender=tender,
                    member=member,
                    assigned_by=request.user,
                    # Re-assigning a member who already attested keeps their attestation —
                    # only genuinely new members must sign it fresh.
                    coi_attested=(member.id in previous_attestation and previous_attestation[member.id].coi_attested),
                    coi_attested_at=(previous_attestation[member.id].coi_attested_at if
                                     member.id in previous_attestation else None),
                )
                for member in members
            ])
        log_audit(request.user, 'evaluation_committee_assigned', tender, {
            'reference_number': tender.reference_number,
            'member_ids': [str(u.id) for u in members],
        })
        for member in members:
            if member.id in previously_assigned_ids:
                continue
            Notification.objects.create(
                recipient_id=str(member.id),
                recipient_name=member.full_name or member.username,
                type=NotificationChannel.IN_APP,
                event='evaluation_committee_assigned',
                title=f'Assigned to Evaluation Committee: {tender.reference_number}',
                body=f'You have been assigned to the Evaluation Committee for "{tender.name}" ({tender.reference_number}). You can now score its bids under Evaluations.',
                linked_entity_id=str(tender.id),
            )
        roster = tender.evaluation_committee_members.select_related('member', 'assigned_by').all()
        return Response({
            'roster': TenderEvaluationCommitteeMemberSerializer(roster, many=True, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    def _assert_evaluation_oversight(self):
        if getattr(self.request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team and Platform Administrators can view Evaluation Committee scores.')

    @action(detail=True, methods=['get'], url_path='evaluation_scores')
    def evaluation_scores(self, request, pk=None):
        """The raw marks each Evaluation Committee member gave, per bid — the RBF
        Official's / Super Admin's oversight view of the committee's scoring, showing
        every member's component scores rather than just the averaged result."""
        self._assert_evaluation_oversight()
        tender = self.get_object()
        return Response(_tender_evaluation_scoreboard(tender))

    @action(detail=True, methods=['get', 'post'], url_path='evaluation_comment')
    def evaluation_comment(self, request, pk=None):
        """The RBF Official's comment on the tender's evaluation, written only once the
        committee's whole evaluation is complete. GET returns the saved comment and
        whether the evaluation has finished; POST saves it (RBF Official / Super Admin
        only, and only when the evaluation is complete)."""
        self._assert_evaluation_oversight()
        tender = self.get_object()
        status_data = _tender_evaluation_status(tender)
        if request.method == 'GET':
            return Response({
                'comment': tender.evaluation_comment,
                'author': tender.evaluation_comment_author,
                'updated_at': tender.evaluation_comment_updated_at,
                'evaluation_complete': status_data['complete'],
                'incomplete_reasons': status_data['reasons'],
                'committee_size': status_data['committee_size'],
            })

        if not status_data['complete']:
            return Response({
                'detail': 'The Evaluation Committee\'s scores are not complete yet. The RBF Official comment can only be added once the whole evaluation is finished.',
                'evaluation_complete': False,
                'incomplete_reasons': status_data['reasons'],
                'committee_size': status_data['committee_size'],
            }, status=status.HTTP_400_BAD_REQUEST)

        comment = str(request.data.get('comment') or '').strip()
        user = request.user
        tender.evaluation_comment = comment
        tender.evaluation_comment_author = user.full_name or user.username or ''
        tender.evaluation_comment_updated_at = timezone.now()
        tender.save(update_fields=['evaluation_comment', 'evaluation_comment_author', 'evaluation_comment_updated_at'])
        log_audit(user, 'evaluation_comment_saved', tender, {
            'reference_number': tender.reference_number,
            'comment': comment,
        })
        return Response({
            'comment': tender.evaluation_comment,
            'author': tender.evaluation_comment_author,
            'updated_at': tender.evaluation_comment_updated_at,
            'evaluation_complete': True,
            'incomplete_reasons': [],
            'committee_size': status_data['committee_size'],
        })

    @action(detail=True, methods=['get'], url_path='coi_status')
    def coi_status(self, request, pk=None):
        """A committee member's conflict-of-interest posture on this tender: whether
        they have attested, plus their declared (and unresolved) conflicts. Super Admin
        sees the whole committee's attestations."""
        tender = self.get_object()
        user = request.user
        is_oversight = user.role in {UserRole.ADMIN, UserRole.RBF_OFFICIAL}
        memberships = TenderEvaluationCommitteeMember.objects.filter(tender=tender)
        if is_oversight:
            roster = [
                {
                    'member_id': str(m.member_id),
                    'name': m.member.full_name or m.member.username or '',
                    'coi_attested': m.coi_attested,
                    'coi_attested_at': m.coi_attested_at.isoformat() if m.coi_attested_at else None,
                }
                for m in memberships.select_related('member').order_by('assigned_at', 'id')
            ]
            declarations = [
                {
                    'id': str(c.id),
                    'evaluator_id': str(c.evaluator_id),
                    'evaluator_name': c.evaluator.full_name or c.evaluator.username or '',
                    'vendor_id': c.vendor_id,
                    'vendor_name': c.vendor_name,
                    'relationship': c.relationship,
                    'details': c.details,
                    'resolved': c.resolved,
                    'resolved_at': c.resolved_at.isoformat() if c.resolved_at else None,
                    'resolution_notes': c.resolution_notes,
                    'declared_at': c.declared_at.isoformat() if c.declared_at else None,
                }
                for c in tender.conflict_of_interests.select_related('evaluator', 'resolved_by').order_by('-declared_at')
            ]
        else:
            membership = memberships.filter(member=user).first()
            if membership is None:
                raise PermissionDenied('You are not assigned to this tender\'s Evaluation Committee.')
            roster = [{
                'member_id': str(user.id),
                'name': user.full_name or user.username or '',
                'coi_attested': membership.coi_attested,
                'coi_attested_at': membership.coi_attested_at.isoformat() if membership.coi_attested_at else None,
            }]
            declarations = [
                {
                    'id': str(c.id),
                    'vendor_id': c.vendor_id,
                    'vendor_name': c.vendor_name,
                    'relationship': c.relationship,
                    'details': c.details,
                    'resolved': c.resolved,
                    'declared_at': c.declared_at.isoformat() if c.declared_at else None,
                }
                for c in EvaluationConflictOfInterest.objects.filter(evaluator=user, tender=tender).order_by('-declared_at')
            ]
        return Response({'committee': roster, 'declarations': declarations})

    @action(detail=True, methods=['post'], url_path='attest_coi')
    def attest_coi(self, request, pk=None):
        """Blanket attestation a committee member signs before scoring anything on a
        tender — confirming they have no conflict of interest with any bidder, or that
        any conflict they do have is already declared (and will be handled)."""
        tender = self.get_object()
        user = request.user
        membership = TenderEvaluationCommitteeMember.objects.filter(tender=tender, member=user).first()
        if user.role != UserRole.ADMIN and membership is None:
            raise PermissionDenied('Only assigned Evaluation Committee members (or Super Admin) can attest on this tender.')
        if membership is not None:
            membership.coi_attested = True
            membership.coi_attested_at = timezone.now()
            membership.save(update_fields=['coi_attested', 'coi_attested_at'])
        log_audit(user, 'evaluation_coi_attested', tender, {'reference_number': tender.reference_number})
        return Response({'detail': 'Conflict-of-interest attestation recorded.', 'coi_attested': True})

    @action(detail=True, methods=['post'], url_path='declare_coi')
    def declare_coi(self, request, pk=None):
        """Declare a conflict of interest against a specific bidder on this tender.
        The declaration blocks the member from scoring that bidder's bids until a
        Super Admin resolves it."""
        tender = self.get_object()
        user = request.user
        membership = TenderEvaluationCommitteeMember.objects.filter(tender=tender, member=user).first()
        if user.role != UserRole.ADMIN and membership is None:
            raise PermissionDenied('Only assigned Evaluation Committee members (or Super Admin) can declare a conflict of interest here.')
        vendor_id = str(request.data.get('vendor_id') or '').strip()
        relationship = str(request.data.get('relationship') or ConflictOfInterestRelationship.OTHER)
        details = str(request.data.get('details') or '').strip()
        if not vendor_id:
            raise ValidationError({'vendor_id': 'The bidder you have a conflict with is required.'})
        if relationship not in ConflictOfInterestRelationship.values:
            raise ValidationError({'relationship': 'Valid relationships: ' + ', '.join(ConflictOfInterestRelationship.values) + '.'})
        vendor_bid = TenderBid.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if vendor_bid is None:
            raise ValidationError({'vendor_id': 'That bidder has not submitted a bid on this tender.'})
        coi = EvaluationConflictOfInterest.objects.create(
            evaluator=user,
            tender=tender,
            vendor_id=vendor_id,
            vendor_name=vendor_bid.vendor_name,
            relationship=relationship,
            details=details,
        )
        log_audit(user, 'evaluation_coi_declared', coi, {
            'tender_id': str(tender.id),
            'vendor_id': vendor_id,
            'vendor_name': vendor_bid.vendor_name,
            'relationship': relationship,
        })
        return Response({
            'id': str(coi.id),
            'detail': f'Conflict of interest declared against {vendor_bid.vendor_name}. You cannot score their bids until a Super Admin resolves this declaration.',
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='resolve_coi')
    def resolve_coi(self, request, pk=None):
        """Super Admin only: resolve a declared conflict of interest. Once resolved the
        member may score that bidder's bids again (the resolution is audited)."""
        tender = self.get_object()
        user = request.user
        if user.role != UserRole.ADMIN:
            raise PermissionDenied('Only Super Admin can resolve a declared conflict of interest.')
        coi_id = request.data.get('coi_id')
        try:
            coi = tender.conflict_of_interests.get(id=coi_id, resolved=False)
        except EvaluationConflictOfInterest.DoesNotExist:
            raise ValidationError({'coi_id': 'No unresolved conflict-of-interest declaration found with that id.'})
        coi.resolved = True
        coi.resolved_by = user
        coi.resolved_at = timezone.now()
        coi.resolution_notes = str(request.data.get('resolution_notes') or '').strip()
        coi.save(update_fields=['resolved', 'resolved_by', 'resolved_at', 'resolution_notes'])
        log_audit(user, 'evaluation_coi_resolved', coi, {
            'tender_id': str(tender.id),
            'vendor_id': coi.vendor_id,
            'vendor_name': coi.vendor_name,
        })
        return Response({'detail': 'Conflict of interest resolved. The member may now score this bidder.', 'id': str(coi.id)})

    @action(detail=True, methods=['get', 'post'], url_path='invited_vendors')
    def invited_vendors(self, request, pk=None):
        """Manage the invited-vendor list for a Restricted Tendering tender. Only
        vendors on this list may bid once the tender is Restricted (enforced in
        _assert_vendor_submission_access and TenderViewSet.get_queryset). GET returns
        the current roster plus the pool of eligible (approved, active) vendors to
        choose from; POST replaces the roster."""
        tender = self.get_object()
        if request.method == 'GET':
            self._assert_write_permission()
            roster = tender.invited_vendors.select_related('vendor', 'invited_by').all()
            # Only vendors whose CURRENT prequalification status is Approved are
            # eligible to be invited — their most recent submission overall (approved
            # or not), matching the exact same lookup _assert_vendor_submission_access
            # uses (_latest_vendor_prequalification: order_by('-submitted_at', '-id'),
            # no status filter). A vendor whose approval was superseded by a
            # not-yet-re-approved resubmission is excluded, since inviting them would
            # be pointless — they can't currently bid even if invited.
            latest_prequal_by_vendor = {}
            for prequal in VendorPrequalification.objects.order_by('vendor_id', '-submitted_at', '-id'):
                latest_prequal_by_vendor.setdefault(prequal.vendor_id, prequal)
            approved_vendor_ids = {
                vendor_id for vendor_id, prequal in latest_prequal_by_vendor.items()
                if prequal.status == PrequalificationStatus.APPROVED
            }
            # Account status is still surfaced (not filtered) so the official can see
            # e.g. a Suspended account before inviting it — only prequalification
            # status gates who appears in the pool at all.
            pool = User.objects.filter(
                role=UserRole.VENDOR, id__in=approved_vendor_ids
            ).order_by('full_name')
            tender_tech_types = set(tender.technology_types or [])

            def _vendor_capability(user):
                prequal = latest_prequal_by_vendor.get(user.id)
                vendor_tech_types = set(prequal.technology_types or []) if prequal else set()
                return {
                    'id': str(user.id),
                    'full_name': user.full_name,
                    'email': user.email,
                    'organization_name': user.organization_name,
                    # computed_status (blacklist status, else prequalification status),
                    # not the raw `status` field, which is what the vendor's own
                    # profile page and the Vendor Directory both display — keeping
                    # this consistent so the badge here never disagrees with what an
                    # official would see if they opened this vendor's profile.
                    'account_status': user.computed_status,
                    'prequalification_status': prequal.status if prequal else '',
                    'technology_types': sorted(vendor_tech_types),
                    'tech_tier': prequal.tech_tier if prequal else '',
                    'years_experience': prequal.years_experience if prequal else None,
                    'prior_projects': prequal.prior_projects if prequal else None,
                    'matches_tender_technology': bool(tender_tech_types & vendor_tech_types) if tender_tech_types else True,
                }

            available = [_vendor_capability(u) for u in pool]
            # Vendors whose pre-qualified technology matches this tender surface
            # first — the most genuinely relevant candidates up top.
            available.sort(key=lambda v: not v['matches_tender_technology'])
            return Response({
                'invited': TenderInvitedVendorSerializer(roster, many=True, context={'request': request}).data,
                'available_vendors': available,
            })

        self._assert_write_permission()
        vendor_ids = request.data.get('vendor_ids')
        if not isinstance(vendor_ids, list):
            return Response({'detail': 'vendor_ids must be a list of user ids.'}, status=status.HTTP_400_BAD_REQUEST)
        vendor_ids = [str(vid) for vid in vendor_ids]
        vendors = list(User.objects.filter(id__in=vendor_ids))
        if len(vendors) != len(set(vendor_ids)):
            return Response({'detail': 'One or more selected users could not be found.'}, status=status.HTTP_400_BAD_REQUEST)
        non_vendors = [u for u in vendors if u.role != UserRole.VENDOR]
        if non_vendors:
            return Response(
                {'detail': f'These users are not vendors: {", ".join(u.full_name or u.username for u in non_vendors)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(vendor_ids) > 1 and tender.procurement_method in _limited_procurement_values():
            return Response(
                {'detail': 'Limited/Single-Source tenders may only be directed to one vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previously_invited_ids = set(tender.invited_vendors.values_list('vendor_id', flat=True))
        with transaction.atomic():
            tender.invited_vendors.all().delete()
            TenderInvitedVendor.objects.bulk_create([
                TenderInvitedVendor(tender=tender, vendor=vendor, invited_by=request.user)
                for vendor in vendors
            ])
        log_audit(request.user, 'tender_invited_vendors_updated', tender, {
            'reference_number': tender.reference_number,
            'vendor_ids': [str(u.id) for u in vendors],
        })
        for vendor in vendors:
            if vendor.id in previously_invited_ids:
                continue
            Notification.objects.create(
                recipient_id=str(vendor.id),
                recipient_name=vendor.full_name or vendor.username,
                type=NotificationChannel.IN_APP,
                event='tender_invited_vendor_added',
                title=f'Invited to bid: {tender.reference_number}',
                body=f'You have been invited to bid on the Restricted tender "{tender.name}" ({tender.reference_number}).',
                linked_entity_id=str(tender.id),
            )
        roster = tender.invited_vendors.select_related('vendor', 'invited_by').all()
        return Response({
            'invited': TenderInvitedVendorSerializer(roster, many=True, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='financial_evaluation')
    def financial_evaluation(self, request, pk=None):
        """The Evaluation Committee's financial evaluation screen: every bid (or, for a
        lot-wise tender, every lot offer) that has cleared technical evaluation, with its
        financial score computed live from the price formula — 100 x lowest qualifying
        price / this price. Nothing here is persisted until a committee member finalizes
        a row via TenderBidEvaluationViewSet (stage=financial)."""
        tender = self.get_object()
        user = request.user
        if user.role == UserRole.EVALUATION_COMMITTEE and not TenderEvaluationCommitteeMember.objects.filter(tender=tender, member=user).exists():
            raise PermissionDenied('You are not assigned to this tender\'s Evaluation Committee.')
        elif user.role not in {UserRole.EVALUATION_COMMITTEE, UserRole.ADMIN}:
            raise PermissionDenied('Only Evaluation Committee members (or Super Admin) can view financial evaluation.')

        lots = list(tender.lots.all())
        financial_bids = _financial_bids_for_tender(tender)
        if lots:
            payload = []
            financial_bid_ids = {b.id for b in financial_bids}
            for lot in lots:
                lowest = _lowest_qualifying_lot_offer_amount(lot)
                offer_rows = []
                for offer in lot.bid_offers.select_related('bid').filter(bid_id__in=financial_bid_ids):
                    finalized = offer.bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, lot=lot, status=EvaluationStatus.SCORED).order_by('-created_at').first()
                    mine = offer.bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, lot=lot, evaluator=user).order_by('-created_at').first()
                    offer_rows.append({
                        'bid_id': str(offer.bid_id),
                        'vendor_id': str(offer.bid.vendor_id),
                        'vendor_name': offer.bid.vendor_name,
                        'bid_amount': float(offer.bid_amount or 0),
                        'bid_currency': offer.bid.bid_currency or tender.bidding_currency,
                        'bid_amount_base_currency': float(_to_base_currency(tender, offer.bid_amount, offer.bid.bid_currency) or 0),
                        'subsidy_requested': float(offer.subsidy_requested) if offer.subsidy_requested is not None else None,
                        'computed_financial_score': _round_score(_compute_auto_financial_score_for_offer(offer, lowest)),
                        'finalized': finalized is not None,
                        'finalized_by_me': finalized is not None and str(finalized.evaluator_id) == str(user.id),
                        'submission_status': mine.submission_status if mine is not None else None,
                        'submitted_at': mine.submitted_at.isoformat() if mine is not None and mine.submitted_at else None,
                    })
                offer_rows.sort(key=lambda r: r['bid_amount_base_currency'])
                payload.append({'lot_id': str(lot.id), 'lot_name': lot.name, 'rows': offer_rows})
            return Response({'is_lot_wise': True, 'lots': payload})

        lowest = _lowest_qualifying_bid_amount(tender)
        rows = []
        for bid in financial_bids:
            finalized = bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, lot__isnull=True, status=EvaluationStatus.SCORED).order_by('-created_at').first()
            mine = bid.evaluations.filter(stage=EvaluationStage.FINANCIAL, lot__isnull=True, evaluator=user).order_by('-created_at').first()
            rows.append({
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'vendor_name': bid.vendor_name,
                'bid_amount': float(bid.bid_amount or 0),
                'bid_currency': bid.bid_currency or tender.bidding_currency,
                'bid_amount_base_currency': float(_to_base_currency(tender, bid.bid_amount, bid.bid_currency) or 0),
                'subsidy_requested': float(bid.subsidy_requested or 0) if bid.subsidy_requested is not None else None,
                'computed_financial_score': _round_score(_compute_auto_financial_score(bid, lowest)),
                'finalized': finalized is not None,
                'finalized_by_me': finalized is not None and str(finalized.evaluator_id) == str(user.id),
                'submission_status': mine.submission_status if mine is not None else None,
                'submitted_at': mine.submitted_at.isoformat() if mine is not None and mine.submitted_at else None,
            })
        rows.sort(key=lambda r: r['bid_amount_base_currency'])
        return Response({'is_lot_wise': False, 'rows': rows})

    @action(detail=True, methods=['post'])
    def confirm_award(self, request, pk=None):
        """Finalize the award after standstill. For a lot-wise tender, an optional
        `lot_id` confirms just that one lot (gated on ITS OWN cooling_off_until) —
        letting different lots finalize independently as each one's window elapses.
        Without `lot_id`, every lot whose own cooling-off has already elapsed is
        confirmed in one call (lots still pending are left untouched). The tender only
        flips to AWARDED once no lot is left with an unconfirmed intent."""
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

        lots = list(tender.lots.all())
        is_lot_wise = bool(lots)
        requested_lot_id = str(request.data.get('lot_id') or '').strip()
        lots_to_confirm = []

        if is_lot_wise:
            pending_lots = [lot for lot in lots if lot.intent_to_award_bid_id and not lot.awarded_at]
            if requested_lot_id:
                lot = next((l for l in lots if str(l.id) == requested_lot_id), None)
                if lot is None:
                    return Response({'detail': 'Lot not found for this tender.'}, status=status.HTTP_400_BAD_REQUEST)
                if not lot.intent_to_award_bid_id:
                    return Response(
                        {'detail': f'Intent to award must be issued for {lot.name} before confirming.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if lot.awarded_at:
                    return Response(
                        {'detail': f'{lot.name} has already been confirmed as awarded.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if lot.cooling_off_until and timezone.now() < lot.cooling_off_until:
                    return Response(
                        {
                            'detail': f'Cooling-off period for {lot.name} has not yet expired.',
                            'cooling_off_until': lot.cooling_off_until.isoformat(),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                lots_to_confirm = [lot]
            else:
                if not pending_lots:
                    return Response(
                        {'detail': 'Intent to award must be issued for at least one lot before confirming.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                lots_to_confirm = [
                    lot for lot in pending_lots
                    if not lot.cooling_off_until or timezone.now() >= lot.cooling_off_until
                ]
                if not lots_to_confirm:
                    return Response(
                        {'detail': 'No lots have cleared their cooling-off period yet.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            if tender.intent_to_award_bid is None:
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

        contracts = []
        confirmed_lots = []
        with transaction.atomic():
            now = timezone.now()
            if is_lot_wise:
                for lot in lots_to_confirm:
                    bid = lot.intent_to_award_bid
                    if bid.status != BidStatus.AWARDED:
                        bid.status = BidStatus.AWARDED
                        bid.reviewed_at = bid.reviewed_at or now
                        bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
                        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])
                    # This is the moment the award actually becomes confirmed — only now
                    # do awarded_vendor_id/name get set (see TenderLot model comment).
                    lot.awarded_at = now
                    lot.awarded_vendor_id = bid.vendor_id
                    lot.awarded_vendor_name = bid.vendor_name
                    lot.save(update_fields=['awarded_at', 'awarded_vendor_id', 'awarded_vendor_name', 'updated_at'])
                    confirmed_lots.append(lot)
                    contract = self._ensure_award_contract(tender, bid, bid.vendor_id, lot=lot)
                    if contract:
                        contracts.append(contract)
                    log_audit(
                        request.user,
                        'lot_awarded',
                        tender,
                        {
                            'reference_number': tender.reference_number,
                            'lot_id': str(lot.id),
                            'lot_name': lot.name,
                            'bid_id': str(bid.id),
                            'awarded_vendor_id': bid.vendor_id,
                            'awarded_vendor_name': bid.vendor_name,
                            'contract_id': str(contract.id) if contract else None,
                        },
                    )
                # Only close out the whole tender once every lot that received intent
                # has actually been confirmed — other lots may still be mid-standstill.
                still_pending = any(l.intent_to_award_bid_id and not l.awarded_at for l in lots)
                if not still_pending:
                    tender.status = TenderStatus.AWARDED
                    tender.awarded_at = now
                    tender.cooling_off_until = None
                    tender.dispute_started_at = None
                    tender.save(update_fields=['status', 'awarded_at', 'cooling_off_until', 'dispute_started_at', 'updated_at'])
            else:
                bid = tender.intent_to_award_bid
                tender.status = TenderStatus.AWARDED
                tender.awarded_vendor_id = bid.vendor_id
                tender.awarded_vendor_name = bid.vendor_name
                tender.awarded_at = now
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
                    bid.reviewed_at = bid.reviewed_at or now
                    bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
                    bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])

                # Give every other qualified-but-losing bid an explicit, final outcome
                # instead of leaving it in a submitted/under-review limbo forever.
                TenderBid.objects.filter(
                    tender=tender,
                    status__in=[BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED],
                ).exclude(id=bid.id).update(status=BidStatus.NOT_AWARDED)

                contract = self._ensure_award_contract(tender, bid, bid.vendor_id)
                if contract:
                    contracts.append(contract)

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
        if is_lot_wise:
            for lot in confirmed_lots:
                bid = lot.intent_to_award_bid
                self._notify_award(tender, bid.vendor_id, bid.vendor_name, send_email)
        else:
            bid = tender.intent_to_award_bid
            self._notify_award(tender, bid.vendor_id, bid.vendor_name, send_email)
        response_data = TenderSerializer(tender, context={'request': request}).data
        if contracts:
            response_data['generated_contracts'] = TenderContractSerializer(
                contracts,
                many=True,
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
        Revoke any PENDING (not yet confirmed) intent to award. Never touches a lot
        that has already been confirmed-awarded (lot.awarded_at set) — those are done
        deals with a real contract and must not be silently wiped out by a revoke
        triggered over a different, still-pending lot. Only resets the tender back to
        EVALUATION when nothing on it has actually been confirmed yet.
        """
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status == TenderStatus.AWARDED:
            return Response(
                {'detail': 'Tender has already been awarded. Cannot revoke intent.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lots = list(tender.lots.all())
        is_lot_wise = bool(lots)
        pending_lots = [lot for lot in lots if lot.intent_to_award_bid_id and not lot.awarded_at] if is_lot_wise else []

        if is_lot_wise:
            if not pending_lots:
                return Response(
                    {'detail': 'No pending intent to award to revoke.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif not tender.intent_to_award_at:
            return Response(
                {'detail': 'No intent to award has been issued yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_bid_id = str(tender.intent_to_award_bid.id) if tender.intent_to_award_bid else None
        previous_vendor_id = tender.awarded_vendor_id
        previous_vendor_name = tender.awarded_vendor_name
        revoked_lots = []

        for lot in pending_lots:
            bid = lot.intent_to_award_bid
            revoked_lots.append({'lot': lot, 'vendor_id': bid.vendor_id if bid else '', 'vendor_name': bid.vendor_name if bid else ''})
            lot.intent_to_award_bid = None
            lot.intent_to_award_at = None
            lot.cooling_off_until = None
            lot.awarded_vendor_id = ''
            lot.awarded_vendor_name = ''
            lot.save(update_fields=['intent_to_award_bid', 'intent_to_award_at', 'cooling_off_until', 'awarded_vendor_id', 'awarded_vendor_name', 'updated_at'])

        any_lot_confirmed = any(lot.awarded_at for lot in lots)
        if not any_lot_confirmed:
            # Nothing on this tender has actually been finalized yet — safe to fully
            # reset it back to EVALUATION, matching the pre-per-lot-confirm behavior.
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
        # else: at least one lot is already confirmed-awarded with a real contract —
        # leave the tender's own status/award fields untouched; only the still-pending
        # lots above were revoked.

        log_audit(
            request.user,
            'intent_revoked',
            tender,
            {
                'reference_number': tender.reference_number,
                'previous_bid_id': previous_bid_id,
                'previous_vendor_id': previous_vendor_id,
                'previous_vendor_name': previous_vendor_name,
                'revoked_lot_ids': [str(entry['lot'].id) for entry in revoked_lots],
            },
        )

        if is_lot_wise:
            for entry in revoked_lots:
                if entry['vendor_id']:
                    self._notify_intent_revoked(tender, entry['vendor_id'], entry['vendor_name'])
        else:
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
        was_already_disputed = tender.status == TenderStatus.DISPUTED
        if not was_already_disputed:
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

        # Only notify bidders that the award is paused if this challenge newly
        # paused the award (pause_award already notified on its own path).
        if not was_already_disputed:
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
        If upheld: revokes the current intent immediately and queues a request to award
        the challenger's bid — like every other intent to award, that re-issue only
        takes effect once a Super Admin approves it, so the fresh standstill window
        starts at approval, not at the resolution.
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

            # An upheld challenge invalidates the intent that is currently standing, so
            # the revocation is applied immediately and unconditionally. The challenger's
            # replacement intent is NOT issued here: it is queued like any other proposal
            # and only takes effect once a Super Admin approves it, which is also when
            # the fresh cooling-off window starts.
            tender.intent_to_award_bid = None
            tender.intent_to_award_at = None
            tender.awarded_vendor_id = ''
            tender.awarded_vendor_name = ''
            tender.cooling_off_until = None
            tender.dispute_started_at = None
            tender.status = TenderStatus.EVALUATION

            # The challenger's bid is by definition not the committee's ranked winner, so
            # the upheld challenge is the recorded justification for the override.
            challenge_override_reason = f'Challenge upheld (challenge_id={challenge.id}).'
            try:
                prepared = _prepare_intent_to_award(
                    tender, bid_id=challenger_bid.id, ec_override_reason=challenge_override_reason,
                )
            except _IntentToAwardError as exc:
                return exc.as_response()

            # A proposal already sitting in the Super Admin queue for this tender is
            # superseded by the challenge outcome, so it is withdrawn rather than left to
            # compete with the replacement.
            superseded = _pending_intent_award_request_queryset(tender).first()
            if superseded is not None:
                superseded.status = IntentAwardRequestStatus.WITHDRAWN
                superseded.reviewed_at = timezone.now()
                superseded.notes = f'Superseded by upheld challenge {challenge.id}.'
                superseded.save(update_fields=['status', 'reviewed_at', 'notes'])

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
                    'new_intent_awaiting_super_admin_approval': True,
                    'resolution_notes': resolution_notes,
                },
            )

            self._queue_intent_award_request(
                tender, prepared, actor=request.user,
                send_email=request.data.get('send_email', True), from_challenge=True,
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
        """Tell the challenging vendor their challenge was upheld and their bid has been
        put forward as the new intent to award — which still needs Super Admin approval
        before it is issued and the cooling-off period starts."""
        from rbf.users.models import User
        try:
            vendor = User.objects.get(id=challenge.filed_by_vendor_id)
        except User.DoesNotExist:
            return
        title = f'Challenge Upheld — New Intent to Award Pending Approval: {tender.reference_number}'
        body = (
            f"Your challenge for {tender.name} ({tender.reference_number}) has been upheld.\n"
            f"Your bid has been put forward as the new Best Evaluated Bidder.\n"
            f"The intent to award is pending approval by the Platform Administrator (Super Admin).\n"
            f"You will be notified, and the cooling-off period will start, once it is approved.\n"
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
            NotificationService.dispatch_email(title, body, [vendor.email])

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

        email_enabled = send_email and email_configured()

        # In-app notification
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.IN_APP,
            event='tender_awarded',
            title=email_subject,
            body=email_body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

        # Email notification
        if email_enabled and vendor.email:
            NotificationService.dispatch_email(email_subject, email_body, [vendor.email])

    def _ensure_award_contract(self, tender: Tender, bid: TenderBid, vendor_id: str, lot=None):
        """Create a generated contract on award if one doesn't exist.

        For lot-wise tenders, pass `lot` — a vendor can win several lots with the same
        bid, so the contract must be keyed by (tender, vendor, lot), not just vendor.
        """
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return None

        existing_qs = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id, lot=lot)
        existing = existing_qs.first()
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
        if lot is not None:
            reference_number = f"{reference_number}-LOT{lot.id}"
        contract = TenderContract.objects.create(
            tender=tender,
            bid=bid,
            lot=lot,
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
    def open_financial_stage(self, request, pk=None):
        """Batch-open the Financial stage for all technical-passing bidders.

        Only the RBF Management Team may perform this action. It unlocks the
        Financial stage (and unseals combined pricing) for every bid that cleared
        the technical threshold, once all technical bids have been evaluated.
        """
        self._assert_write_permission()
        tender = self.get_object()
        workflow = getattr(tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)

        passing_bids = _technical_passing_bids(tender)
        technical_pending = []
        for bid in _detailed_evaluation_bids(tender):
            if not _quorum_met_evaluations(bid, EvaluationStage.TECHNICAL):
                technical_pending.append(bid.vendor_name)
        if technical_pending:
            return Response(
                {
                    'detail': 'Not all technical bids have been evaluated yet. Evaluate every technical submission before opening the Financial stage.',
                    'pending': sorted(set(technical_pending)),
                },
                status=status.HTTP_409_CONFLICT,
            )

        opened = _open_financial_stage_for_tender(tender)
        log_audit(
            request.user,
            'financial_stage_opened',
            tender,
            {
                'reference_number': tender.reference_number,
                'workflow': workflow,
                'opened_bids': len(opened),
                'notes': 'Financial stage opened for all technical-passing bidders.',
            },
        )
        return Response({
            'detail': f'Financial stage opened for {len(opened)} bidder(s).',
            'opened_bids': [str(b.id) for b in opened],
            'workflow': workflow,
        }, status=status.HTTP_200_OK)

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
        if user.role == UserRole.EVALUATION_COMMITTEE:
            assigned_tender_ids = TenderEvaluationCommitteeMember.objects.filter(member=user).values_list('tender_id', flat=True)
            return TenderBid.objects.filter(tender_id__in=list(assigned_tender_ids)).order_by('-updated_at', '-submitted_at', '-created_at')
        return TenderBid.objects.all().order_by('-updated_at', '-submitted_at', '-created_at')

    def _assert_vendor_submission_access(self, request, tender: Tender, bid: TenderBid | None = None):
        if request.user.role != UserRole.VENDOR:
            raise ValidationError({'detail': 'Only vendors can submit bids.'})
        if is_vendor_restricted(request.user):
            raise ValidationError({'detail': 'Your vendor account is suspended or blacklisted. Bid submission is disabled.'})
        latest_prequalification = _latest_vendor_prequalification(str(request.user.id))
        if latest_prequalification is None or latest_prequalification.status != PrequalificationStatus.APPROVED:
            raise ValidationError({'detail': 'Complete pre-qualification first'})
        _auto_close_tender_on_deadline(tender)
        if tender.status != TenderStatus.PUBLISHED:
            raise ValidationError({'tender': 'Tender is not open for bidding.'})

        workflow = getattr(tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
        spec = _bid_stage_spec(bid, tender)
        stage = spec['stage']

        # A Restricted-family tender (Restricted / Limited-Single-Source / RFQ) normally
        # only allows invited vendors to bid. The one exception is the EOI stage of an
        # 'EOI → Combined' tender: it is an open invitation every approved vendor can
        # respond to; the invite (shortlist) gate only applies to the actual combined
        # bid submission after the tender is published. Legacy 'sequential' Restricted
        # tenders do NOT get this exemption — their EOI stage is already gated behind
        # invites.
        is_invite_gated = tender.procurement_method in _invite_gated_procurement_values()
        is_eoi_combined = getattr(tender, 'procurement_workflow', '') == ProcurementWorkflow.EOI_COMBINED
        is_open_eoi_stage = (
            is_invite_gated
            and is_eoi_combined
            and stage == BidStage.EOI
        )
        if is_invite_gated and not is_open_eoi_stage and not tender.invited_vendors.filter(vendor_id=str(request.user.id)).exists():
            raise ValidationError({'detail': 'This is a Restricted tender — only specifically invited vendors can bid.'})

        # A Framework/Pre-Qualified Pool tender has no invite list at all — the vendor's
        # own approved pre-qualification tier/technology types must meet the tender's
        # minimum_service_tier/technology_types requirements instead.
        if tender.procurement_method in _framework_procurement_values() and not _vendor_meets_framework_requirements(tender, latest_prequalification):
            raise ValidationError({'detail': 'Your pre-qualification tier or technology types do not meet this tender\'s requirements.'})

        deadline = spec['deadline']
        if _uses_hard_deadline(tender) and deadline and timezone.now() >= deadline:
            raise ValidationError({'tender': 'Bidding deadline has passed.'})

        if stage == BidStage.EOI:
            # Normal EOI access; no prior shortlisting requirement.
            pass
        elif stage == BidStage.TECHNICAL:
            if bid is not None and not _has_technical_stage_access(bid):
                raise ValidationError({'detail': 'Only shortlisted vendors can submit a Technical proposal.'})
        elif stage == BidStage.FINANCIAL:
            if not _has_financial_stage_access(bid):
                raise ValidationError({'detail': 'The Financial stage is not yet open for this vendor.'})
        elif stage == BidStage.COMBINED:
            # Workflows that begin with an EOI stage ('EOI → Combined', and legacy
            # 'combined'/sequential tenders that carry an eoi_deadline) require prior
            # shortlisting before the combined stage opens. A genuine single-stage
            # 'Combined' tender has no EOI gate — any eligible vendor may bid directly.
            if workflow_has_eoi_stage(tender) and bid is not None and not _has_technical_stage_access(bid):
                raise ValidationError({'detail': 'Only shortlisted vendors can submit a combined Technical & Financial proposal.'})

        # Prevent duplicate submissions within the SAME stage lineage.
        existing_submitted_bid = TenderBid.objects.filter(
            tender=tender,
            vendor_id=str(request.user.id),
        ).exclude(status__in={BidStatus.DRAFT, BidStatus.REVISION_REQUIRED, BidStatus.WITHDRAWN})
        if bid is not None:
            if bid.stage_two_unlocked and not _has_stage_two_shortlist_access(bid):
                raise ValidationError({'detail': 'Only shortlisted vendors can submit Stage 2 proposals.'})
            existing_submitted_bid = existing_submitted_bid.exclude(id=bid.id)
            existing_submitted_bid = existing_submitted_bid.exclude(id__in=_bid_lineage_ids(bid))
        if existing_submitted_bid.exists():
            raise ValidationError({'tender': 'You have already submitted a bid for this tender.'})

    def _assert_stage_one_review_permission(self, request, bid: TenderBid):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only the RBF Management Team can decide EOI submissions.')
        if normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) not in {'pre_qualification'} \
                and normalize_bid_stage(getattr(bid, 'bid_stage', '')) != BidStage.EOI:
            raise ValidationError({'detail': 'EOI review actions only apply to EOI submissions.'})

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
        new_stage = normalize_bid_stage(payload.get('bid_stage') or BidStage.EOI)
        if not payload.get('bid_stage'):
            payload['bid_stage'] = new_stage
        payload['stage'] = bid_stage_label(new_stage)

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
        
        payload['stage'] = bid_stage_label(getattr(bid, 'bid_stage', None) or bid.stage or 'eoi')
        
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
        
        payload['stage'] = bid_stage_label(getattr(bid, 'bid_stage', None) or bid.stage or 'eoi')
        
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
        NotificationService.notify_user(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            title=f'Bid Submitted: {bid.tender.reference_number}',
            body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
            event='bid_submitted',
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

        spec = _bid_stage_spec(bid, bid.tender)
        total_deadline = spec['deadline']
        if _uses_hard_deadline(bid.tender) and total_deadline and timezone.now() >= total_deadline:
            return Response(
                {'detail': 'Bidding deadline has passed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stage = spec['stage']
        if stage in (BidStage.TECHNICAL, BidStage.COMBINED):
            if not bid.technical_proposal_file or not bid.financial_proposal_file:
                return Response(
                    {'detail': 'Technical and financial proposal files are required for technical submissions.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not bid.boq_file:
                return Response(
                    {'detail': 'BOQ file is required for technical submissions.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif stage == BidStage.FINANCIAL:
            if not bid.financial_proposal_file:
                return Response(
                    {'detail': 'Financial Proposal file is required for the Financial stage.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not bid.boq_file:
                return Response(
                    {'detail': 'BOQ file is required for the Financial stage.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        bid.status = BidStatus.SUBMITTED
        bid.submitted_at = timezone.now()
        bid.save(update_fields=['status', 'submitted_at', 'updated_at'])
        log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(bid.tender_id), 'version': bid.version_number})
        NotificationService.notify_user(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            title=f'Bid Submitted: {bid.tender.reference_number}',
            body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
            event='bid_submitted',
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

        is_eoi_bid = normalize_bid_stage(getattr(bid, 'bid_stage', '')) == BidStage.EOI
        is_legacy = normalize_tender_stage(getattr(bid.tender, 'stage_type', '')) == 'pre_qualification'
        if is_eoi_bid or is_legacy:
            workflow = getattr(bid.tender, 'procurement_workflow', ProcurementWorkflow.SEQUENTIAL)
            draft = _unlock_stage_for_bid(bid, BidStage.TECHNICAL)
            if workflow_is_combined_style(bid.tender, workflow):
                _unlock_stage_for_bid(bid, BidStage.FINANCIAL)

            # For a Restricted-family tender the vendor must also be on the invited-vendor
            # list to bid (enforced in _assert_vendor_submission_access). Shortlisting is
            # the RBF's decision that this vendor may proceed, so add them to the roster
            # now — idempotently — while still allowing manual review/management later.
            if bid.tender.procurement_method in _invite_gated_procurement_values():
                vendor_user = User.objects.filter(id=bid.vendor_id).first()
                if vendor_user is not None:
                    TenderInvitedVendor.objects.get_or_create(
                        tender=bid.tender,
                        vendor=vendor_user,
                        defaults={'invited_by': request.user},
                    )

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


EVALUATION_SNAPSHOT_FIELDS = (
    'stage',
    'lot_id',
    'submission_status',
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
    'justifications',
)


def _evaluation_score_snapshot(evaluation: TenderBidEvaluation) -> dict:
    """JSON-serializable snapshot of every scoring-relevant field on an evaluation.
    Used as the before/after pair inside TenderBidEvaluationRevision so an audit can
    reconstruct exactly how (and why) marks evolved."""
    return {
        field: getattr(evaluation, field, None)
        for field in EVALUATION_SNAPSHOT_FIELDS
        if field != 'lot_id' or getattr(evaluation, 'lot_id', None) is not None
    }


def _evaluation_snapshot_diff(before: dict, after: dict):
    """Yield (field, before, after) triples for every field that changed between two
    evaluation snapshots. Values are normalized (lists/dicts coerced to strings) so
    the diff is trivially JSON-serializable for the audit/reporting surface."""
    key_order = list(EVALUATION_SNAPSHOT_FIELDS)
    for field in key_order:
        b = before.get(field)
        a = after.get(field)
        b_norm = json.dumps(b, default=str, sort_keys=True) if isinstance(b, (dict, list)) else b
        a_norm = json.dumps(a, default=str, sort_keys=True) if isinstance(a, (dict, list)) else a
        if b_norm != a_norm:
            yield field, before.get(field), after.get(field)


def _write_evaluation_revision(evaluation, changed_by, action, before, after, reason=''):
    """Append an immutable revision row for an evaluation. Skips writing noise when a
    draft re-save didn't actually change anything."""
    if before == after and action == EvaluationRevisionAction.DRAFT_SAVED:
        return None
    try:
        return TenderBidEvaluationRevision.objects.create(
            evaluation=evaluation,
            changed_by=changed_by if getattr(changed_by, 'is_authenticated', False) else None,
            action=action,
            reason=reason,
            before=before or {},
            after=after or {},
        )
    except Exception:  # noqa: BLE001 — an audit write must never break a score save
        return None


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
        if user.role == UserRole.EVALUATION_COMMITTEE:
            assigned_tender_ids = TenderEvaluationCommitteeMember.objects.filter(member=user).values_list('tender_id', flat=True)
            return qs.filter(bid__tender_id__in=list(assigned_tender_ids))
        return qs

    def _assert_eval_permission(self, request, bid=None):
        user = request.user
        if user.role == UserRole.ADMIN:
            return
        if user.role != UserRole.EVALUATION_COMMITTEE:
            raise PermissionDenied('Only Evaluation Committee members (or Super Admin) can score bids.')
        if bid is not None:
            membership = TenderEvaluationCommitteeMember.objects.filter(tender_id=bid.tender_id, member=user).first()
            if membership is None:
                raise PermissionDenied('You are not assigned to this tender\'s Evaluation Committee.')
            if not membership.coi_attested:
                raise PermissionDenied('You must attest to having no conflict of interest on this tender before scoring bids.')
            if EvaluationConflictOfInterest.objects.filter(
                evaluator=user, tender_id=bid.tender_id, resolved=False, vendor_id=str(bid.vendor_id or ''),
            ).exists():
                raise PermissionDenied('You have a declared, unresolved conflict of interest with this bidder and cannot score their bid.')

    def _assert_can_write(self, evaluation, user):
        """Enforces the submit-to-finalize lock: a SUBMITTED evaluation is sealed and
        only a Super Admin may touch it (reopening is recorded as a revision)."""
        if user.role == UserRole.ADMIN:
            return
        if evaluation.submission_status == EvaluationSubmissionStatus.SUBMITTED:
            raise PermissionDenied('This evaluation has been submitted and locked. A Super Admin must unlock it before it can be changed.')

    def _assert_tender_closed_for_evaluation(self, bid, evaluation_stage=EvaluationStage.TECHNICAL):
        stage = normalize_bid_stage(getattr(bid, 'bid_stage', '') or bid.stage)
        is_detailed = stage in (BidStage.TECHNICAL, BidStage.COMBINED) or getattr(bid, 'stage_two_unlocked', False)
        if is_detailed:
            # Scoring a TECHNICAL evaluation never touches or exposes financial pricing
            # (the payload is technical/feasibility/kpi/gender/environmental/om scores
            # only) — financial pricing visibility is independently controlled by
            # financial_bid_is_sealed() in the bid serializer, and FINANCIAL scoring
            # itself is already gated on the technical threshold/quorum having cleared
            # first (see _apply_auto_financial_score). There is nothing to block here:
            # scoring Technical is exactly the action that's supposed to clear that gate.
            _assert_evaluation_window_open(bid.tender)
            return
        _auto_close_tender_on_deadline(bid.tender)
        if bid.tender.status not in {TenderStatus.PUBLISHED, TenderStatus.CLOSED, TenderStatus.EVALUATION}:
            raise ValidationError(
                {'detail': 'EOI evaluation requires the tender to be Published, Closed, or in Evaluation.'}
            )

    def _apply_auto_financial_score(self, data, bid):
        """For a financial-stage submission, the score is always computed server-side
        from the price formula — whatever the client sent for financial_score is
        ignored. Lot-wise tenders compute per lot (a bid can offer on several lots);
        non-lot-wise tenders compute once for the bid's own bid_amount."""
        lot_id = data.get('lot')
        technical_score = _technical_score_for_bid(bid, lot_id)
        threshold = Decimal(str(bid.tender.technical_threshold or 70))
        if technical_score is None:
            raise ValidationError({'stage': 'This bid has not yet cleared technical evaluation (committee quorum not reached).'})
        if technical_score < threshold:
            raise ValidationError({'stage': f'This bid has not cleared the technical threshold ({threshold}%) yet.'})

        if lot_id:
            try:
                lot = TenderLot.objects.get(id=lot_id, tender_id=bid.tender_id)
                offer = TenderBidLotOffer.objects.get(bid=bid, lot=lot)
            except (TenderLot.DoesNotExist, TenderBidLotOffer.DoesNotExist):
                raise ValidationError({'lot': 'This bid has no offer for that lot.'})
            computed = _compute_auto_financial_score_for_offer(offer)
        else:
            data['lot'] = None
            computed = _compute_auto_financial_score(bid)
        data['financial_score'] = int(computed.to_integral_value(rounding=ROUND_HALF_UP))
        data['financial_score_auto_calculated'] = True

    def create(self, request, *args, **kwargs):
        bid_id = request.data.get('bid')
        if not bid_id:
            raise ValidationError({'bid': 'This field is required.'})
        try:
            bid = TenderBid.objects.get(id=bid_id)
        except TenderBid.DoesNotExist:
            raise ValidationError({'bid': 'Bid not found.'})
        self._assert_eval_permission(request, bid)
        stage = request.data.get('stage') or EvaluationStage.TECHNICAL
        self._assert_tender_closed_for_evaluation(bid, stage)
        data = request.data.copy()
        data['evaluator'] = request.user.id
        data['stage'] = stage
        if stage == EvaluationStage.FINANCIAL:
            self._apply_auto_financial_score(data, bid)
        else:
            data['financial_score_auto_calculated'] = False
            # Lot-wise tenders score each lot a bid covers separately (one technical
            # evaluation per lot per evaluator); non-lot-wise tenders always keep lot=NULL.
            # A lot-wise tender MUST be given an explicit lot here — silently falling back
            # to lot=NULL previously let a client that hadn't loaded the tender's lots yet
            # create an ambiguous "no lot" row that no serial-order/quorum check could ever
            # distinguish from a real per-lot score.
            lot_id = data.get('lot') or None
            if not bid.tender.lots.exists():
                data['lot'] = None
            elif lot_id is None:
                raise ValidationError({'lot': 'This is a lot-wise tender — select which lot this technical score applies to.'})
            else:
                try:
                    lot = TenderLot.objects.get(id=lot_id, tender_id=bid.tender_id)
                except TenderLot.DoesNotExist:
                    raise ValidationError({'lot': 'Lot not found for this tender.'})
                bid_lot_ids = (
                    set(bid.declared_lots or [])
                    | set(bid.lot_offers.values_list('lot_id', flat=True))
                    | set(bid.sites.values_list('lot_id', flat=True))
                )
                if lot.id not in bid_lot_ids:
                    raise ValidationError({'lot': 'This bid does not cover that lot.'})
        data.setdefault('submission_status', EvaluationSubmissionStatus.DRAFT)
        filter_kwargs = {
            'bid_id': data.get('bid'),
            'evaluator': request.user,
            'stage': stage,
        }
        lot_id = data.get('lot') or None
        if lot_id:
            filter_kwargs['lot_id'] = lot_id
        existing = TenderBidEvaluation.objects.filter(**filter_kwargs).order_by('-created_at').first()
        if existing is not None:
            self._assert_can_write(existing, request.user)
            before = _evaluation_score_snapshot(existing)
            serializer = self.get_serializer(existing, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            submitted_now = data.get('submission_status') == EvaluationSubmissionStatus.SUBMITTED and existing.submission_status != EvaluationSubmissionStatus.SUBMITTED
            with transaction.atomic():
                self.perform_update(serializer)
                evaluation = serializer.instance
                _write_evaluation_revision(
                    evaluation, request.user,
                    EvaluationRevisionAction.SUBMITTED if submitted_now else EvaluationRevisionAction.DRAFT_SAVED,
                    before,
                    _evaluation_score_snapshot(evaluation),
                )
            log_audit(request.user, 'bid_evaluated', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score, 'mode': 'updated_existing'})
            return Response(serializer.data, status=status.HTTP_200_OK)

        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                evaluation = serializer.instance
        except IntegrityError:
            # A concurrent request created the same (bid, evaluator, stage[, lot]) row
            # between our lookup and insert — fall back to that row instead of erroring.
            existing = TenderBidEvaluation.objects.filter(**filter_kwargs).order_by('-created_at').first()
            if existing is None:
                raise
            _write_evaluation_revision(
                existing, request.user, EvaluationRevisionAction.DRAFT_SAVED,
                _evaluation_score_snapshot(existing), _evaluation_score_snapshot(existing),
            )
            return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        _write_evaluation_revision(
            evaluation, request.user,
            EvaluationRevisionAction.SUBMITTED if data.get('submission_status') == EvaluationSubmissionStatus.SUBMITTED else EvaluationRevisionAction.DRAFT_SAVED,
            {},
            _evaluation_score_snapshot(evaluation),
        )
        log_audit(request.user, 'bid_evaluated', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score, 'mode': 'created'})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        evaluation = self.get_object()
        self._assert_eval_permission(request, evaluation.bid)
        self._assert_tender_closed_for_evaluation(evaluation.bid, request.data.get('stage') or evaluation.stage)
        if request.user.role != UserRole.ADMIN and str(getattr(evaluation, 'evaluator_id', '')) != str(request.user.id):
            raise PermissionDenied('You can only edit your own evaluation record.')
        self._assert_can_write(evaluation, request.user)
        data = request.data.copy()
        before = _evaluation_score_snapshot(evaluation)
        revision_action = EvaluationRevisionAction.DRAFT_SAVED
        if evaluation.submission_status == EvaluationSubmissionStatus.SUBMITTED:
            # A Super Admin patching a submitted row is, in effect, reopening it — log it
            # as such so the audit trail is unambiguous.
            revision_action = EvaluationRevisionAction.REOPENED
        if evaluation.stage == EvaluationStage.FINANCIAL or data.get('stage') == EvaluationStage.FINANCIAL:
            if 'lot' not in data:
                data['lot'] = evaluation.lot_id
            self._apply_auto_financial_score(data, evaluation.bid)
            serializer = self.get_serializer(evaluation, data=data, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            _write_evaluation_revision(
                evaluation, request.user, revision_action, before, _evaluation_score_snapshot(evaluation),
                reason='Super Admin reopened a submitted financial evaluation.' if revision_action == EvaluationRevisionAction.REOPENED else '',
            )
            return Response(serializer.data)
        serializer = self.get_serializer(evaluation, data=data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        _write_evaluation_revision(
            evaluation, request.user, revision_action, before, _evaluation_score_snapshot(evaluation),
            reason='Super Admin reopened a submitted evaluation.' if revision_action == EvaluationRevisionAction.REOPENED else '',
        )
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Seal this evaluation as the member's final mark. For a technical evaluation
        this re-validates that every criterion carries a rationale first; financial
        evaluations just need the auto-calculated score. A submitted row cannot be
        edited without a Super Admin unlock ('/unlock/')."""
        evaluation = self.get_object()
        self._assert_eval_permission(request, evaluation.bid)
        if request.user.role != UserRole.ADMIN and str(getattr(evaluation, 'evaluator_id', '')) != str(request.user.id):
            raise PermissionDenied('You can only submit your own evaluation record.')
        if evaluation.submission_status == EvaluationSubmissionStatus.SUBMITTED:
            return Response(self.get_serializer(evaluation).data)
        payload = {
            'bid': str(evaluation.bid_id),
            'lot': evaluation.lot_id,
            'stage': evaluation.stage,
            'evaluator': evaluation.evaluator_id,
            'technical_score': evaluation.technical_score,
            'financial_score': evaluation.financial_score,
            'feasibility_score': evaluation.feasibility_score,
            'kpi_score': evaluation.kpi_score,
            'gender_score': evaluation.gender_score,
            'environmental_score': evaluation.environmental_score,
            'om_score': evaluation.om_score,
            'inclusivity_score': evaluation.inclusivity_score,
            'comments': request.data.get('comments', evaluation.comments),
            'justifications': request.data.get('justifications', evaluation.justifications or {}),
            'submission_status': EvaluationSubmissionStatus.SUBMITTED,
        }
        before = _evaluation_score_snapshot(evaluation)
        serializer = self.get_serializer(evaluation, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_update(serializer)
            evaluation = serializer.instance
            _write_evaluation_revision(
                evaluation, request.user, EvaluationRevisionAction.SUBMITTED, before,
                _evaluation_score_snapshot(evaluation), reason='Evaluation submitted for the record.',
            )
        log_audit(request.user, 'bid_evaluation_submitted', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """Super Admin only: reopen a submitted evaluation so the evaluator may correct
        their marks. The reopen is itself recorded as a revision for the audit trail."""
        evaluation = self.get_object()
        if request.user.role != UserRole.ADMIN:
            raise PermissionDenied('Only Super Admin can unlock a submitted evaluation.')
        if evaluation.submission_status != EvaluationSubmissionStatus.SUBMITTED:
            return Response(self.get_serializer(evaluation).data)
        before = _evaluation_score_snapshot(evaluation)
        evaluation.submission_status = EvaluationSubmissionStatus.DRAFT
        evaluation.submitted_at = None
        evaluation.save(update_fields=['submission_status', 'submitted_at', 'updated_at'])
        _write_evaluation_revision(
            evaluation, request.user, EvaluationRevisionAction.REOPENED, before,
            _evaluation_score_snapshot(evaluation), reason=request.data.get('reason') or 'Super Admin reopened the evaluation.',
        )
        log_audit(request.user, 'bid_evaluation_unlocked', evaluation, {'bid_id': str(evaluation.bid_id)})
        return Response(self.get_serializer(evaluation).data)


class TenderAwardRecommendationViewSet(viewsets.ModelViewSet):
    """Evaluation Committee members' suggested winners, used to reach a verdict on who
    should receive the intent to award. POST is an upsert keyed on (tender, lot, member):
    an assigned member re-submitting changes their latest suggestion (they may revise it
    until an intent to award is issued). Admin (RBF) access is unrestricted."""
    queryset = TenderAwardRecommendation.objects.select_related('bid', 'suggested_by', 'lot').all()
    serializer_class = TenderAwardRecommendationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['tender', 'lot']

    def get_queryset(self):
        qs = TenderAwardRecommendation.objects.select_related('bid', 'suggested_by', 'lot')
        tender_id = self.request.query_params.get('tender')
        lot_id = self.request.query_params.get('lot')
        if tender_id:
            qs = qs.filter(tender_id=tender_id)
        if lot_id:
            qs = qs.filter(lot_id=lot_id)
        return qs

    def _tender(self):
        data = getattr(self.request, 'data', {})
        tender_id = str(data.get('tender') or '').strip()
        if not tender_id:
            raise ValidationError({'tender': 'tender is required.'})
        return Tender.objects.filter(id=tender_id).first()

    def _assert_can_suggest(self, tender):
        user = self.request.user
        if getattr(user, 'role', None) == UserRole.ADMIN:
            return True
        if getattr(user, 'role', None) != UserRole.EVALUATION_COMMITTEE:
            raise PermissionDenied('Only assigned Evaluation Committee members can suggest a winner.')
        if not TenderEvaluationCommitteeMember.objects.filter(tender=tender, member=user).exists():
            raise PermissionDenied('You are not assigned to this tender\'s Evaluation Committee.')
        if not _tender_evaluation_status(tender)['complete']:
            raise PermissionDenied('Winner suggestions open only after the full technical and financial evaluation is complete.')
        return False

    def _validate_payload(self, tender, lot_id):
        """Returns (bid, lot) after validating the suggestion references this tender's
        bids/lots, and that on a lot-wise tender the bid actually covers the chosen lot."""
        bid_id = str(self.request.data.get('bid') or '').strip()
        if not bid_id:
            raise ValidationError({'bid': 'bid is required.'})
        bid = TenderBid.objects.filter(id=bid_id, tender=tender).first()
        if bid is None:
            raise ValidationError({'bid': 'Bid not found for this tender.'})
        lots = list(tender.lots.all())
        lot = None
        if lots:
            if not lot_id:
                raise ValidationError({'lot': 'This is a lot-wise tender — a lot is required for the suggestion.'})
            lot = next((l for l in lots if str(l.id) == lot_id), None)
            if lot is None:
                raise ValidationError({'lot': 'Lot not found for this tender.'})
            if not _bid_covers_lot(bid, lot_id):
                raise ValidationError({'bid': 'This bid did not offer on the selected lot.'})
        elif lot_id:
            raise ValidationError({'lot': 'This tender is not lot-wise — omit the lot.'})
        return bid, lot

    def create(self, request, *args, **kwargs):
        tender = self._tender()
        if tender is None:
            raise ValidationError({'tender': 'Tender not found.'})
        self._assert_can_suggest(tender)
        lot_id = str(request.data.get('lot') or '').strip() or None
        bid, lot = self._validate_payload(tender, lot_id)
        recommendation, created = TenderAwardRecommendation.objects.get_or_create(
            tender=tender,
            lot=lot,
            suggested_by=request.user,
            defaults={'bid': bid, 'rationale': str(request.data.get('rationale') or '').strip()},
        )
        if not created:
            changed = False
            if str(recommendation.bid_id) != str(bid.id):
                recommendation.bid = bid
                changed = True
            rationale = str(request.data.get('rationale') or '').strip()
            if rationale != recommendation.rationale:
                recommendation.rationale = rationale
                changed = True
            if changed:
                recommendation.save(update_fields=['bid', 'rationale', 'updated_at'])
        action = 'award_recommendation_created' if created else 'award_recommendation_updated'
        log_audit(
            request.user, action, tender,
            {
                'lot_id': lot_id,
                'bid_id': str(bid.id),
                'vendor_name': bid.vendor_name,
                'ec_consensus': _award_recommendation_unit(tender, lot)['consensus'],
            },
        )
        serializer = self.get_serializer(recommendation)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def _assert_can_edit(self, recommendation):
        user = self.request.user
        if getattr(user, 'role', None) == UserRole.ADMIN:
            return
        if str(recommendation.suggested_by_id) != str(user.id):
            raise PermissionDenied('You can only change your own recommendation.')

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        recommendation = self.get_object()
        self._assert_can_edit(recommendation)
        tender = recommendation.tender
        lot_id = str(request.data.get('lot') or '').strip() or None
        if lot_id and lot_id != str(recommendation.lot_id or ''):
            raise ValidationError({'lot': 'Cannot move a recommendation between decision units — update the other unit directly.'})
        self._assert_can_suggest(tender)
        bid, lot = self._validate_payload(tender, lot_id)
        before = str(recommendation.bid_id)
        recommendation.bid = bid
        recommendation.rationale = str(request.data.get('rationale') or recommendation.rationale).strip()
        recommendation.save(update_fields=['bid', 'rationale', 'updated_at'])
        log_audit(
            request.user, 'award_recommendation_updated', tender,
            {
                'lot_id': lot_id,
                'bid_before': before,
                'bid_after': str(bid.id),
                'vendor_name': bid.vendor_name,
            },
        )
        return Response(self.get_serializer(recommendation).data)

    @action(detail=False, methods=['get'])
    def consensus(self, request):
        """Live verdict per decision unit: every assigned member's latest suggestion,
        who has not suggested yet, whether the committee agrees, and whether the full
        evaluation has been finalized (which gates suggestions)."""
        tender_id = request.query_params.get('tender')
        if not tender_id:
            return Response({'detail': 'tender is required.'}, status=status.HTTP_400_BAD_REQUEST)
        tender = Tender.objects.filter(id=tender_id).first()
        if tender is None:
            return Response({'detail': 'Tender not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_award_recommendation_consensus(tender))

    def destroy(self, request, *args, **kwargs):
        recommendation = self.get_object()
        self._assert_can_edit(recommendation)
        tender = recommendation.tender
        lot_id = str(recommendation.lot_id or '')
        self._assert_can_suggest(tender)
        super().destroy(request, *args, **kwargs)
        log_audit(
            request.user, 'award_recommendation_withdrawn', tender,
            {'lot_id': lot_id, 'bid_id': str(recommendation.bid_id)},
        )
        return Response({'detail': 'Recommendation withdrawn.'}, status=status.HTTP_200_OK)


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
        # The vendor signs ONE document: the generated PBA. Annexes A-E are not separate
        # uploads they have to supply — they are sections compiled into that PDF from
        # whatever the vendor attached to its own bid, and the PBA builder emits a page
        # for each one even when the bid left it empty (see ANNEX_SECTION_SPECS in
        # pba_pdf.py). Gating on "all five annexes resolved" therefore blocked signature
        # whenever a bid legitimately omitted one of those source documents — for example
        # Annex B, whose only source is implementation_plan_file, a field the bid form does
        # not always require — and told the vendor to upload a document it was never asked
        # for. The package is complete by construction.
        #
        # What we do require is the agreement itself, plus the bid documents this tender
        # actually asked for at creation time.
        if not contract.generated_file:
            raise ValidationError({
                'detail': 'The Performance-Based Agreement has not been generated yet, so there is nothing to sign. Please contact RMT.'
            })
        missing_required = _missing_required_bid_documents(contract.tender, _get_contract_bid(contract))
        if missing_required:
            raise ValidationError({
                'required_documents': f"Your bid submission is missing required documents for this tender: {', '.join(missing_required)}. Please contact RMT to resolve before signing."
            })
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
                    'lot_id': str(contract.lot_id) if contract.lot_id else None,
                    'lot_name': contract.lot.name if contract.lot_id else None,
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
        """Reject the vendor's uploaded signed copy. This is NOT a dead end: the
        contract is reset back to Generated (signed file cleared) so the vendor's
        upload form reopens and they can submit a corrected signed copy — the
        rejection reason is kept on the record as context for that re-upload."""
        self._assert_admin_permission(request)
        contract = self.get_object()
        reason = str(request.data.get('rejection_reason') or '').strip()
        if not reason:
            raise ValidationError({'rejection_reason': 'Rejection reason is required.'})
        contract.status = ContractStatus.GENERATED
        contract.rejection_reason = reason
        contract.signed_file = None
        contract.signed_at = None
        contract.signature_status = ContractSignatureStatus.AWAITING
        contract.approved_at = timezone.now()
        contract.approved_by = request.user.full_name or request.user.username
        contract.save(update_fields=[
            'status', 'rejection_reason', 'signed_file', 'signed_at', 'signature_status',
            'approved_at', 'approved_by', 'updated_at',
        ])
        log_audit(request.user, 'contract_rejected', contract, {'reason': reason})
        Notification.objects.create(
            recipient_id=contract.vendor_id,
            recipient_name=contract.vendor_name,
            type=NotificationChannel.IN_APP,
            event='contract_rejected',
            title=f'Contract Rejected: {contract.tender.reference_number}',
            body=f'Your signed contract was rejected. Reason: {reason}\n\nPlease review and upload a corrected signed copy.',
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

            data = NoticeSerializer(notice).data
            if notice.send_email_notification:
                data['notification_summary'] = self._notify_notice_recipients(notice)
            return Response(data, status=status.HTTP_200_OK)
        except Notice.DoesNotExist:
            return Response({'error': 'Notice not found'}, status=status.HTTP_404_NOT_FOUND)

    def _notify_notice_recipients(self, notice: Notice):
        from rbf.users.models import VendorPrequalification, PrequalificationStatus

        vendors = list(
            User.objects.filter(role=UserRole.VENDOR)
            .filter(prequalifications__status=PrequalificationStatus.APPROVED)
            .distinct()
            .only('id', 'email', 'full_name', 'username', 'role')
        )
        stakeholders = list(
            User.objects.filter(role__in={UserRole.DOE_OFFICER, UserRole.UNDP_DONOR})
            .distinct()
            .only('id', 'email', 'full_name', 'username', 'role')
        )
        recipients = vendors + stakeholders

        subject = f"Notice Published: {notice.title}"
        body = (
            f"A new notice has been published.\n\n"
            f"Title: {notice.title}\n"
            f"Category: {notice.get_category_display()}\n"
            f"{f'Summary: {notice.summary}\n' if notice.summary else ''}"
        )
        notice_link = build_frontend_url('/', request=self.request)

        NotificationService.notify_users(
            users=recipients,
            title=subject,
            body=f"{body}View notices: {notice_link}\n",
            event='notice_published',
            linked_entity_id=notice.id,
        )

        email_enabled = email_configured()
        email_recipients = []
        email_error = None
        if email_enabled:
            email_recipients = list(dict.fromkeys(r.email for r in recipients if r.email))
            if email_recipients:
                sent = NotificationService.dispatch_email(
                    subject,
                    f"{body}View notices: {notice_link}\n",
                    email_recipients,
                )
                if sent <= 0:
                    email_error = 'Email delivery failed.'

        return {
            'recipient_count': len(recipients),
            'email_enabled': email_enabled,
            'email_recipient_count': len(email_recipients),
            'email_error': email_error,
        }

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
