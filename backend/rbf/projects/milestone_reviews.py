"""Milestone completion reviews: after each milestone is paid — or, for a 0% milestone,
once its conditions are met — RBF / Super Admin verifies it and decides whether the
project proceeds to the next milestone, is closed, or is transferred to another vendor."""

from .models import (
    Milestone,
    MilestoneCompletionReview,
    MilestoneReviewDecision,
    MilestoneReviewStatus,
    Project,
    ProjectStatus,
)

# Decisions that allow the following milestone to be worked on and claimed.
ADVANCING_DECISIONS = {MilestoneReviewDecision.PROCEED, MilestoneReviewDecision.TRANSFER}
TERMINAL_PROJECT_STATUSES = {ProjectStatus.CLOSED, ProjectStatus.COMPLETED, ProjectStatus.LEGACY_COMPLETED}
REVIEW_ROLES_LABEL = 'RBF Management Team or Super Admin'


def previous_milestone(milestone: Milestone) -> Milestone | None:
    return (
        Milestone.objects.filter(project_id=milestone.project_id, milestone_number__lt=milestone.milestone_number)
        .order_by('-milestone_number', '-id')
        .first()
    )


def is_last_milestone(milestone: Milestone) -> bool:
    return not (
        Milestone.objects.filter(project_id=milestone.project_id, milestone_number__gt=milestone.milestone_number)
        .exclude(status='cancelled')
        .exists()
    )


def is_zero_value_milestone(milestone: Milestone | None) -> bool:
    """True when a milestone disburses nothing.

    RMT may set a milestone's share to 0% (e.g. a Mobilization milestone paid entirely on
    delivery and performance — see ProjectAssignmentSerializer, where only M2 and M3 carry
    a 1% floor). Such a milestone has no amount, so it can never be claimed and no claim can
    ever be raised against it. Instead, once its conditions are met its completion review is
    opened directly (see KpiService), and RMT decides whether the vendor proceeds — the same
    gate a paid milestone goes through.
    """
    if milestone is None:
        return False
    if not (milestone.disbursement_pct or 0):
        return True
    # Rounding can also land a tiny share on 0 while the stored percentage is non-zero.
    return not (milestone.amount or 0) and not (milestone.amount_lsl or 0)


def milestone_cleared_to_proceed(milestone: Milestone | None) -> bool:
    """True when `milestone` has been verified with a decision that lets the
    project move on to the next milestone. A zero-value milestone needs this decision too;
    its review opens when its conditions are met rather than after a payment."""
    if milestone is None:
        return False
    review = MilestoneCompletionReview.objects.filter(milestone=milestone).first()
    return bool(review and review.status == MilestoneReviewStatus.DECIDED and review.decision in ADVANCING_DECISIONS)


def next_milestone_blocker(milestone: Milestone) -> str:
    """Why `milestone` cannot be worked on / claimed yet, or '' when it can."""
    project: Project = milestone.project
    if project.status in TERMINAL_PROJECT_STATUSES:
        return f'Project is {project.get_status_display().lower()}; no further milestones can be claimed.'
    if str(milestone.status).lower() == 'cancelled':
        return 'This milestone was cancelled when the project was closed.'
    if is_zero_value_milestone(milestone):
        # Nothing was allocated to this milestone, so there is no amount to claim against.
        # RMT verifies it directly once its conditions are met.
        return (
            f'Milestone {milestone.milestone_number} is set to 0% disbursement, so there is '
            f'nothing to claim. Once its conditions are met, the {REVIEW_ROLES_LABEL} verifies it '
            f'and decides whether the project proceeds to the next milestone.'
        )
    prior = previous_milestone(milestone)
    if prior is not None and not milestone_cleared_to_proceed(prior):
        return (
            f'Milestone {prior.milestone_number} must be completed and verified by the '
            f'{REVIEW_ROLES_LABEL} (decision: proceed) before Milestone {milestone.milestone_number} can be claimed.'
        )
    return ''


def open_completion_review(milestone: Milestone) -> tuple[MilestoneCompletionReview, bool]:
    project = milestone.project
    return MilestoneCompletionReview.objects.get_or_create(
        milestone=milestone,
        defaults={
            'project': project,
            'status': MilestoneReviewStatus.PENDING,
            'vendor_id': project.vendor_id,
            'vendor_name': project.vendor_name,
        },
    )
