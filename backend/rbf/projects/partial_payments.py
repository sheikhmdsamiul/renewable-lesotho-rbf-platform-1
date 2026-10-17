"""Partial milestone payments, carry-overs and returns for completion.

When RMT verifies a submitted milestone claim it can:
  * approve it in full,
  * approve it partially — pay the verified share of the claim when at least
    PlatformConfiguration.partial_payment_min_pct of the milestone was delivered; the
    unpaid rest becomes a MilestoneCarryOver added to the next milestone's claim,
  * return it for completion — list what is missing; the vendor fixes it and resubmits
    the same claim,
  * or reject it (unchanged).

Installation thresholds are cumulative (M2 = 80% of the project target verified, M3 =
100%), so a milestone's own units are its cumulative requirement minus the previous
milestone's. Units carried in from a partially-paid milestone are added on top.
"""
import math
from decimal import ROUND_HALF_UP, Decimal

from rbf.users.models import PlatformConfiguration

from .milestone_reviews import is_zero_value_milestone
from .models import (
    CarryOverStatus,
    InstallationReport,
    InstallationStatus,
    Milestone,
    MilestoneCarryOver,
    PaymentClaim,
    Project,
)

DECISION_FULL = 'full'
DECISION_PARTIAL = 'partial'
RMT_DECISIONS = {DECISION_FULL, DECISION_PARTIAL}
MAX_DEFICIENCIES = 50
CENT = Decimal('0.01')


def _config() -> PlatformConfiguration:
    return PlatformConfiguration.objects.order_by('id').first() or PlatformConfiguration()


def partial_payment_min_pct() -> int:
    return int(_config().partial_payment_min_pct or 70)


def _active_milestones(project: Project):
    return Milestone.objects.filter(project=project).exclude(status='cancelled').order_by('milestone_number', 'id')


def required_installation_pct(milestone: Milestone) -> int:
    """Share (%) of the project's installation target that must be verified for this
    milestone, with the same M2/M3 fallbacks the KPI eligibility check uses."""
    value = int(milestone.required_installation_pct or 0)
    if value > 0:
        return value
    config = _config()
    if milestone.milestone_number == 2:
        return int(config.m2_verification_required_pct or 80)
    if milestone.milestone_number == 3:
        return int(config.m3_verification_required_pct or 100)
    return 0


def _project_target(project: Project) -> int:
    return int(project.target_installations or project.installation_target or 0)


def cumulative_required_units(milestone: Milestone) -> int:
    pct = required_installation_pct(milestone)
    return math.ceil(_project_target(milestone.project) * pct / 100) if pct else 0


def _previous_cumulative_units(milestone: Milestone) -> int:
    earlier = _active_milestones(milestone.project).filter(milestone_number__lt=milestone.milestone_number)
    return max((cumulative_required_units(m) for m in earlier), default=0)


def next_payable_milestone(milestone: Milestone) -> Milestone | None:
    """The milestone a shortfall is carried into: the next active one that disburses money."""
    for candidate in _active_milestones(milestone.project).filter(milestone_number__gt=milestone.milestone_number):
        if not is_zero_value_milestone(candidate):
            return candidate
    return None


def pending_carry_ins(milestone: Milestone):
    return MilestoneCarryOver.objects.filter(to_milestone=milestone, status=CarryOverStatus.PENDING)


def carry_in_totals(milestone: Milestone) -> tuple[Decimal, int]:
    amount = Decimal('0')
    units = 0
    for carry in pending_carry_ins(milestone):
        amount += carry.shortfall_amount
        units += carry.shortfall_units
    return amount, units


def assess_claim(claim: PaymentClaim) -> dict:
    """How much of the claimed milestone is verified as delivered right now.

    completion_pct is None when the milestone has no installation requirement (e.g. M1
    mobilisation); RMT then records an assessed percentage instead.
    """
    milestone = claim.milestone
    if milestone is None:
        return {'expected_units': 0, 'verified_units': 0, 'completion_pct': None, 'carry_in_units': 0}
    previous = _previous_cumulative_units(milestone)
    own_units = max(cumulative_required_units(milestone) - previous, 0)
    carry_in_units = int(claim.carry_in_units or 0)
    expected = own_units + carry_in_units
    if expected == 0:
        return {'expected_units': 0, 'verified_units': 0, 'completion_pct': None, 'carry_in_units': carry_in_units}
    # Units already paid for by earlier milestones: their cumulative requirement less
    # whatever was carried into this claim as unpaid.
    credited_before = max(previous - carry_in_units, 0)
    verified_total = InstallationReport.objects.filter(
        project_id=claim.project_id, status=InstallationStatus.VERIFIED
    ).count()
    verified = min(max(verified_total - credited_before, 0), expected)
    pct = (Decimal(verified) * 100 / Decimal(expected)).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        'expected_units': expected,
        'verified_units': verified,
        'completion_pct': float(pct),
        'carry_in_units': carry_in_units,
    }


def clean_deficiencies(raw) -> list[dict]:
    """Validate the deficiency list RMT sends; raises ValueError with a user-facing message."""
    if raw in (None, ''):
        return []
    if not isinstance(raw, list):
        raise ValueError('deficiencies must be a list.')
    if len(raw) > MAX_DEFICIENCIES:
        raise ValueError(f'List at most {MAX_DEFICIENCIES} deficiencies.')
    cleaned = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {'description': entry}
        if not isinstance(entry, dict):
            raise ValueError('Each deficiency must be an object with a description.')
        description = str(entry.get('description') or '').strip()
        if not description:
            raise ValueError('Each deficiency needs a description.')
        ids = entry.get('installation_ids') or []
        if not isinstance(ids, list) or not all(str(i).isdigit() for i in ids):
            raise ValueError('installation_ids must be a list of installation IDs.')
        cleaned.append({
            'description': description[:500],
            'required_action': str(entry.get('required_action') or '').strip()[:500],
            'installation_ids': [int(i) for i in ids],
        })
    return cleaned


def _parse_pct(value) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        pct = Decimal(str(value))
    except Exception as exc:
        raise ValueError('assessed_pct must be a number.') from exc
    if pct < 0 or pct > 100:
        raise ValueError('assessed_pct must be between 0 and 100.')
    return pct.quantize(CENT, rounding=ROUND_HALF_UP)


def apply_rmt_decision(claim: PaymentClaim, decision: str, *, assessed_pct=None, deficiencies=None) -> None:
    """Record RMT's full / partial approval on the claim (does not save or change status).
    Raises ValueError with a user-facing message when the decision is not allowed."""
    if decision not in RMT_DECISIONS:
        raise ValueError('decision must be "full" or "partial".')
    assessment = assess_claim(claim)
    claim.expected_units = assessment['expected_units']
    claim.verified_units = assessment['verified_units']
    computed = assessment['completion_pct']
    cleaned = clean_deficiencies(deficiencies)

    if decision == DECISION_FULL:
        claim.approved_amount = claim.claim_amount
        claim.completion_pct = Decimal('100') if computed is None else Decimal(str(computed))
        claim.is_partial = False
        claim.deficiencies = cleaned
        return

    pct = _parse_pct(assessed_pct)
    if pct is None:
        if computed is None:
            raise ValueError('This milestone has no installation target; enter the assessed completion percentage.')
        pct = Decimal(str(computed))
    elif computed is not None and pct > Decimal(str(computed)):
        raise ValueError(f'The assessed percentage cannot exceed the verified delivery ({computed}%).')
    minimum = partial_payment_min_pct()
    if pct < minimum:
        raise ValueError(
            f'Partial payment needs at least {minimum}% of the milestone delivered and verified '
            f'(currently {pct}%). Return the claim for completion instead.'
        )
    if pct >= 100:
        raise ValueError('The milestone is fully delivered; approve it in full.')
    if claim.milestone is None or next_payable_milestone(claim.milestone) is None:
        raise ValueError(
            'The final milestone cannot be paid partially because there is no later milestone '
            'to carry the shortfall into. Return the claim for completion instead.'
        )
    if not cleaned:
        raise ValueError('List what is still missing so the vendor knows what to deliver with the next milestone.')
    claim.approved_amount = (claim.claim_amount * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    claim.completion_pct = pct
    claim.is_partial = True
    claim.deficiencies = cleaned


def clear_rmt_decision(claim: PaymentClaim) -> None:
    """Undo a recorded approval (claim rejected, pushed back or returned)."""
    claim.approved_amount = None
    claim.completion_pct = None
    claim.is_partial = False


DECISION_FIELDS = ['approved_amount', 'completion_pct', 'expected_units', 'verified_units', 'is_partial', 'deficiencies']


def settle_on_payment(claim: PaymentClaim) -> MilestoneCarryOver | None:
    """Called once a claim is paid: settle the carry-overs it included and, for a partial
    payment, carry the unpaid rest into the next milestone."""
    milestone = claim.milestone
    if milestone is None:
        return None
    pending_carry_ins(milestone).update(status=CarryOverStatus.SETTLED, settled_by_claim=claim)
    if not claim.is_partial or claim.shortfall_amount <= 0:
        return None
    target = next_payable_milestone(milestone)
    if target is None:
        return None
    shortfall_units = max(int(claim.expected_units or 0) - int(claim.verified_units or 0), 0)
    carry, _ = MilestoneCarryOver.objects.update_or_create(
        from_claim=claim,
        defaults={
            'project': claim.project,
            'from_milestone': milestone,
            'to_milestone': target,
            'shortfall_units': shortfall_units,
            'shortfall_amount': claim.shortfall_amount,
            'status': CarryOverStatus.PENDING,
        },
    )
    return carry


def forfeit_pending_carry_overs(project: Project) -> int:
    """A closed project will never deliver the shortfall, so nothing more is owed."""
    return MilestoneCarryOver.objects.filter(project=project, status=CarryOverStatus.PENDING).update(
        status=CarryOverStatus.FORFEITED
    )
