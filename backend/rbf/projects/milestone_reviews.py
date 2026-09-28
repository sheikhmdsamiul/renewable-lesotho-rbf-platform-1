"""Milestone completion reviews: after each milestone is paid, RBF / Super Admin
verifies it and decides whether the project proceeds to the next milestone, is
closed, or is transferred to another vendor."""

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


def milestone_cleared_to_proceed(milestone: Milestone | None) -> bool:
    """True when `milestone` has been verified with a decision that lets the
    project move on to the next milestone."""
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
