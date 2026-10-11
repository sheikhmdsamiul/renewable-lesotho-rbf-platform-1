"""Open findings that hold a milestone claim back, and the daily sweep that enforces due dates.

A claim cannot move through RMT approval, TAC/PSC approval or payment while its project has a
serious finding still open. "Serious" means:

- an anomaly flag that is high/critical, of a type that already blocks milestone eligibility,
  or escalated;
- an oversight flag (DoE, PSC, RMT) recorded with ``holds_payment``, until its follow-up is resolved;
- an audit case on the claim itself that the Auditor has started and not yet finalized, or a
  major/critical exception or non-compliance on the project whose corrective action is not verified;
- a DoE site visit that found a system not working, until its follow-up is closed.

The rest of the platform keeps working: findings are resolved through their own workflows and
the claim moves on once nothing is left in this list.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils import timezone

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.users.models import User, UserRole

from .models import (
    AnomalyFlag,
    AnomalyFlagStatus,
    AnomalyReviewEvent,
    AuditCase,
    AuditCaseStatus,
    AuditFindingType,
    AuditRiskLevel,
    CorrectiveActionStatus,
    OversightFollowUpStatus,
    OversightReview,
    OversightReviewStatus,
    SiteMonitoringVisit,
    SiteVisitFollowUpStatus,
)

# Same types that keep Milestone 2 from unlocking (see KpiService._get_milestone_eligibility).
BLOCKING_ANOMALY_TYPES = ('zero_uptime', 'output_deviation')
BLOCKING_ANOMALY_SEVERITIES = ('high', 'critical')
# Statuses where the next move is the vendor's; past the due date they escalate automatically.
VENDOR_ACTION_STATUSES = (AnomalyFlagStatus.CORRECTION_REQUESTED, AnomalyFlagStatus.AWAITING_EVIDENCE)
OPEN_FOLLOW_UP = (OversightFollowUpStatus.OPEN, OversightFollowUpStatus.IN_PROGRESS)
OPEN_CORRECTIVE_ACTION = (CorrectiveActionStatus.OPEN, CorrectiveActionStatus.IN_PROGRESS, CorrectiveActionStatus.IMPLEMENTED)
# A finding is shared with management from the response request on (see AuditCaseViewSet).
SHARED_AUDIT_STATUSES = (AuditCaseStatus.MANAGEMENT_RESPONSE, AuditCaseStatus.FINALIZED)
ESCALATION_ROLES = (UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.UNDP_DONOR)


def _overdue(due: date | None, today: date) -> bool:
    return bool(due and due < today)


def _blocking_anomalies(project_id):
    return AnomalyFlag.objects.filter(project_id=project_id, is_resolved=False).filter(
        Q(severity__in=BLOCKING_ANOMALY_SEVERITIES)
        | Q(flag_type__in=BLOCKING_ANOMALY_TYPES)
        | Q(status=AnomalyFlagStatus.ESCALATED)
    )


def claim_payment_blockers(claim) -> list[dict]:
    """Every open finding that holds this claim, oldest first within each source."""
    today = timezone.localdate()
    project_id = claim.project_id
    blockers: list[dict] = []

    for flag in _blocking_anomalies(project_id).order_by('created_at'):
        blockers.append({
            'source': 'anomaly',
            'id': str(flag.id),
            'title': f'Anomaly #{flag.id}: {flag.flag_type.replace("_", " ")} ({flag.severity})',
            'status': flag.status,
            'owner': 'vendor' if flag.status in VENDOR_ACTION_STATUSES else 'rmt',
            'due_date': flag.due_date.isoformat() if flag.due_date else None,
            'overdue': _overdue(flag.due_date, today),
        })

    reviews = OversightReview.objects.filter(
        project_id=project_id, holds_payment=True, follow_up_status__in=OPEN_FOLLOW_UP,
    ).order_by('created_at')
    for review in reviews:
        blockers.append({
            'source': 'oversight',
            'id': str(review.id),
            'title': f'{review.get_review_status_display()} by {review.reviewer_role or "oversight"}: {review.comment[:120]}',
            'status': review.follow_up_status,
            'owner': 'rmt',
            'due_date': review.follow_up_date.isoformat() if review.follow_up_date else None,
            'overdue': _overdue(review.follow_up_date, today),
        })

    # Only the reference is shown for a case still in fieldwork: the Auditor's papers stay private.
    cases = AuditCase.objects.filter(
        Q(payment_claim_id=claim.id) & ~Q(status__in=[AuditCaseStatus.DRAFT, AuditCaseStatus.FINALIZED, AuditCaseStatus.CLOSED])
        & ~Q(finding_type=AuditFindingType.COMPLIANT)
        | Q(project_id=project_id)
        & Q(finding_type__in=[AuditFindingType.EXCEPTION, AuditFindingType.NON_COMPLIANCE])
        & Q(risk_level__in=[AuditRiskLevel.MAJOR, AuditRiskLevel.CRITICAL])
        & Q(corrective_action_status__in=OPEN_CORRECTIVE_ACTION)
        & Q(status__in=SHARED_AUDIT_STATUSES)
    ).order_by('created_at')
    for case in cases:
        has_finding = case.status in SHARED_AUDIT_STATUSES and case.corrective_action_status in OPEN_CORRECTIVE_ACTION
        blockers.append({
            'source': 'audit',
            'id': str(case.id),
            'title': (
                f'Audit {case.reference}: {case.get_risk_level_display().lower()} '
                f'{case.get_finding_type_display().lower()}, corrective action {case.get_corrective_action_status_display().lower()}'
                if has_finding else f'Audit {case.reference}: this claim is under independent audit'
            ),
            'status': case.status,
            'owner': 'rmt' if has_finding else 'auditor',
            'due_date': case.corrective_action_due.isoformat() if has_finding and case.corrective_action_due else None,
            'overdue': has_finding and _overdue(case.corrective_action_due, today),
        })

    visits = SiteMonitoringVisit.objects.filter(
        project_id=project_id, system_working=False,
        follow_up_status__in=[SiteVisitFollowUpStatus.OPEN, SiteVisitFollowUpStatus.IN_PROGRESS],
    ).order_by('visit_date')
    for visit in visits:
        blockers.append({
            'source': 'site_visit',
            'id': str(visit.id),
            'title': f'DoE site visit {visit.visit_date.isoformat()}: system not working'
                     + (f' (installation {visit.installation_id})' if visit.installation_id else ''),
            'status': visit.follow_up_status,
            'owner': 'vendor',
            'due_date': None,
            'overdue': False,
        })
    return blockers


def blocker_message(blockers: list[dict]) -> str:
    listed = '; '.join(b['title'] + (' — overdue' if b['overdue'] else '') for b in blockers[:5])
    more = f' and {len(blockers) - 5} more' if len(blockers) > 5 else ''
    return f'Payment is on hold until these findings are closed: {listed}{more}.'


def _notify_once(users, *, event: str, title: str, body: str, linked_entity_id: str, key: str = '') -> None:
    """One notification per recipient and finding (or per `key`): re-running the sweep does not repeat it."""
    Notification.objects.bulk_create([
        Notification(
            recipient_id=str(user.id),
            recipient_name=user.full_name or user.username,
            type=NotificationChannel.IN_APP,
            event=event,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=linked_entity_id,
            dedupe_key=f'{event}:{key or linked_entity_id}'[:191],
        )
        for user in users
    ], ignore_conflicts=True)


def _escalation_recipients():
    return User.objects.filter(role__in=ESCALATION_ROLES, is_active=True).only('id', 'full_name', 'username')


def notify_anomaly_escalated(flag: AnomalyFlag, reason: str) -> None:
    """Escalation goes to the RBF Management Team, the Administrator and the PSC, and the
    flag now holds every claim on the project until it is resolved."""
    project_ref = getattr(flag.project, 'project_reference', '') or str(flag.project_id)
    _notify_once(
        _escalation_recipients(),
        event='anomaly_escalated',
        title=f'Anomaly escalated: {project_ref}',
        body=f'Flag #{flag.id} ({flag.flag_type.replace("_", " ")}) was escalated: {reason} '
             'Milestone payments for this project are on hold until it is resolved.',
        linked_entity_id=str(flag.id),
        # A flag escalated again later (after being investigated) notifies again.
        key=f'{flag.id}:{flag.escalated_at.isoformat() if flag.escalated_at else ""}',
    )


def escalate_overdue_findings(today: date | None = None) -> dict[str, int]:
    """Daily sweep. Vendor-owned anomaly requests past their due date escalate; overdue oversight
    follow-ups and audit corrective actions alert the people who own them (once each)."""
    from .views import _notify_vendor_of_anomaly_review  # avoid a circular import at load time

    today = today or timezone.localdate()
    now = timezone.now()
    escalated = 0
    for flag in AnomalyFlag.objects.select_related('project').filter(
        is_resolved=False, status__in=VENDOR_ACTION_STATUSES, due_date__lt=today,
    ):
        previous = flag.status
        reason = f'The vendor did not respond by the due date ({flag.due_date.isoformat()}).'
        flag.status = AnomalyFlagStatus.ESCALATED
        flag.resolution_reason = reason
        flag.escalated_at = now
        flag.save(update_fields=['status', 'resolution_reason', 'escalated_at'])
        AnomalyReviewEvent.objects.create(
            flag=flag, actor=None, actor_role='System', from_status=previous, to_status=flag.status,
            investigation_notes=flag.investigation_notes or '', corrective_action=flag.corrective_action or '',
            resolution_reason=reason, evidence_reference=flag.evidence_reference or '',
        )
        notify_anomaly_escalated(flag, reason)
        _notify_vendor_of_anomaly_review(
            flag,
            event='anomaly_escalated_vendor',
            title='Anomaly Escalated: Response Overdue',
            body=f'Project {flag.project.project_reference or flag.project_id}: you did not respond to flag #{flag.id} '
                 f'by {flag.due_date.isoformat()}. It has been escalated and your milestone payments are on hold until it is resolved.',
        )
        escalated += 1

    rmt = list(User.objects.filter(role__in=(UserRole.RBF_OFFICIAL, UserRole.ADMIN), is_active=True).only('id', 'full_name', 'username'))
    reviews = OversightReview.objects.select_related('project', 'reviewer').filter(
        follow_up_status__in=OPEN_FOLLOW_UP, follow_up_date__lt=today,
    )
    for review in reviews:
        recipients = list(rmt)
        if review.reviewer and review.reviewer not in recipients:
            recipients.append(review.reviewer)
        project_ref = getattr(review.project, 'project_reference', '') or str(review.project_id or '')
        _notify_once(
            recipients,
            event='oversight_follow_up_overdue',
            title=f'Oversight follow-up overdue: {project_ref}',
            body=f'The follow-up on "{review.comment}" was due {review.follow_up_date.isoformat()} and is still open.',
            linked_entity_id=f'oversight:{review.id}',
        )

    cases = AuditCase.objects.select_related('auditor').filter(
        corrective_action_status__in=(CorrectiveActionStatus.OPEN, CorrectiveActionStatus.IN_PROGRESS),
        corrective_action_due__lt=today,
    ).exclude(status=AuditCaseStatus.CLOSED)
    for case in cases:
        recipients = list(rmt)
        if case.auditor and case.auditor not in recipients:
            recipients.append(case.auditor)
        _notify_once(
            recipients,
            event='audit_corrective_action_overdue',
            title=f'Corrective action overdue: {case.reference}',
            body=f'The corrective action for "{case.title}" was due {case.corrective_action_due.isoformat()} and is not implemented.',
            linked_entity_id=str(case.id),
        )
    return {'anomalies_escalated': escalated, 'oversight_overdue': reviews.count(), 'audit_overdue': cases.count()}
