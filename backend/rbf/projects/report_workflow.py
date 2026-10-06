"""Sign-off, distribution and schedules for generated reports.

Formal reports (programme results, PSC packs, verification) follow
    Draft -> In review -> Reviewed -> Approved   (or Returned for correction at either step)
with separation of duties: the reviewer is not the preparer, and the approver is neither the
preparer nor the reviewer. The file never changes; a correction is a new version that
supersedes the returned one. Approved reports are the ones distributed.

PROVISIONAL: reviewers and approvers are the RBF Management Team and the Super Admin until the
programme names who reviews and approves each formal report.

Distribution sends an in-app notice and an email with a link to the platform (never the file
itself), and lets each recipient download that report.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.users.models import User, UserRole as R

from .models import GeneratedReport, ReportSchedule

logger = logging.getLogger(__name__)

A = GeneratedReport.Approval
SIGN_OFF_ROLES = frozenset({R.RBF_OFFICIAL, R.ADMIN})


def _name(user) -> str:
    return (user.full_name or user.username) if user else ''


def _notify(users, *, event: str, title: str, body: str, report: GeneratedReport):
    Notification.objects.bulk_create([
        Notification(
            recipient_id=str(u.id), recipient_name=_name(u), type=NotificationChannel.IN_APP, event=event,
            title=title, body=body, status=NotificationStatus.SENT, linked_entity_id=str(report.id),
        )
        for u in users
    ], ignore_conflicts=True)


def _sign_off_users(exclude_ids):
    return User.objects.filter(role__in=SIGN_OFF_ROLES, is_active=True).exclude(id__in=[i for i in exclude_ids if i])


def _append_note(report: GeneratedReport, actor, text: str):
    stamp = timezone.localtime().strftime('%Y-%m-%d %H:%M')
    line = f'[{stamp}] {_name(actor)}: {text}'.strip()
    report.review_notes = f'{report.review_notes}\n{line}'.strip() if report.review_notes else line


def _log(actor, action: str, report: GeneratedReport, **extra):
    from .audit import log_audit

    log_audit(actor, action, report, {'module': 'report', 'report_type': report.report_type, 'version': report.version, **extra})


def is_formal(report: GeneratedReport) -> bool:
    from .report_catalogue import REGISTRY

    definition = REGISTRY.get(report.report_type)
    return bool(definition and definition.formal)


def on_ready(report: GeneratedReport):
    """Called when a job finishes successfully: start sign-off or distribute."""
    if is_formal(report):
        report.approval_status = A.DRAFT
        report.save(update_fields=['approval_status'])
        if report.schedule_id:
            submit_for_review(report, report.generated_by, automatic=True)
    elif report.schedule_id:
        distribute(report, report.generated_by)


def submit_for_review(report: GeneratedReport, actor, automatic: bool = False) -> GeneratedReport:
    if report.status != GeneratedReport.Status.READY:
        raise ValidationError({'detail': 'Only a generated report can be submitted for review.'})
    if report.approval_status not in {A.DRAFT}:
        raise ValidationError({'detail': 'Only a draft can be submitted for review.'})
    if not automatic and report.generated_by_id != getattr(actor, 'id', None) and getattr(actor, 'role', None) != R.ADMIN:
        raise PermissionDenied('Only the person who prepared the report can submit it for review.')
    report.approval_status = A.IN_REVIEW
    _append_note(report, actor, 'Submitted for review' + (' (scheduled)' if automatic else ''))
    report.save(update_fields=['approval_status', 'review_notes'])
    _log(actor, 'report_submitted_for_review', report)
    _notify(_sign_off_users([report.generated_by_id]), event='report_review_needed',
            title=f'Review needed: {report.title} v{report.version}',
            body=f'{report.title} (version {report.version}) is waiting for review in Reports.', report=report)
    return report


def _assert_signer(actor, report: GeneratedReport, *, also_exclude=()):
    if getattr(actor, 'role', None) not in SIGN_OFF_ROLES:
        raise PermissionDenied('Only the RBF Management Team or Super Admin can review and approve formal reports.')
    if actor.id == report.generated_by_id or actor.id in also_exclude:
        raise PermissionDenied('A report must be reviewed and approved by someone other than the person who prepared or reviewed it.')


def review(report: GeneratedReport, actor, *, accept: bool, notes: str) -> GeneratedReport:
    if report.approval_status != A.IN_REVIEW:
        raise ValidationError({'detail': 'This report is not waiting for review.'})
    _assert_signer(actor, report)
    if not accept and len(notes.strip()) < 5:
        raise ValidationError({'notes': 'Say what needs correcting.'})
    report.reviewed_by = actor
    report.reviewed_at = timezone.now()
    report.approval_status = A.REVIEWED if accept else A.RETURNED
    _append_note(report, actor, ('Reviewed. ' if accept else 'Returned for correction. ') + notes.strip())
    report.save(update_fields=['reviewed_by', 'reviewed_at', 'approval_status', 'review_notes'])
    _log(actor, 'report_reviewed' if accept else 'report_returned', report, notes=notes.strip()[:500])
    if accept:
        _notify(_sign_off_users([report.generated_by_id, actor.id]), event='report_approval_needed',
                title=f'Approval needed: {report.title} v{report.version}',
                body=f'{report.title} (version {report.version}) was reviewed by {_name(actor)} and is waiting for approval.', report=report)
    elif report.generated_by:
        _notify([report.generated_by], event='report_returned', title=f'Returned: {report.title} v{report.version}',
                body=f'{_name(actor)} returned the report for correction: {notes.strip()[:200]}', report=report)
    return report


def approve(report: GeneratedReport, actor, *, accept: bool, notes: str) -> GeneratedReport:
    if report.approval_status != A.REVIEWED:
        raise ValidationError({'detail': 'This report must be reviewed before it can be approved.'})
    _assert_signer(actor, report, also_exclude=(report.reviewed_by_id,))
    if not accept and len(notes.strip()) < 5:
        raise ValidationError({'notes': 'Say what needs correcting.'})
    if accept:
        report.approved_by = actor
        report.approved_at = timezone.now()
    report.approval_status = A.APPROVED if accept else A.RETURNED
    _append_note(report, actor, ('Approved. ' if accept else 'Returned for correction. ') + notes.strip())
    report.save(update_fields=['approved_by', 'approved_at', 'approval_status', 'review_notes'])
    _log(actor, 'report_approved' if accept else 'report_returned', report, notes=notes.strip()[:500])
    if report.generated_by:
        _notify([report.generated_by], event='report_approved' if accept else 'report_returned',
                title=f'{"Approved" if accept else "Returned"}: {report.title} v{report.version}',
                body=f'{_name(actor)} {"approved" if accept else "returned"} the report. {notes.strip()[:200]}', report=report)
    if accept and report.schedule_id:
        distribute(report, actor)
    return report


def new_version(report: GeneratedReport, actor) -> GeneratedReport:
    """Regenerate a returned (or draft) formal report with the same settings as a new version."""
    from .report_queue import enqueue

    if report.approval_status not in {A.RETURNED, A.DRAFT}:
        raise ValidationError({'detail': 'Only a draft or returned report can be replaced by a new version.'})
    if report.generated_by_id != actor.id and actor.role != R.ADMIN:
        raise PermissionDenied('Only the person who prepared the report can prepare a new version.')
    successor = enqueue(report.generated_by or actor, report.report_type, report.format, report.filters)
    successor.version = report.version + 1
    successor.supersedes = report
    successor.schedule = report.schedule
    successor.save(update_fields=['version', 'supersedes', 'schedule'])
    _log(actor, 'report_new_version', successor, supersedes=str(report.id))
    return successor


def recipients_for(schedule: ReportSchedule | None, roles=None) -> list:
    roles = list(roles if roles is not None else (schedule.recipient_roles if schedule else []))
    users = {u.id: u for u in User.objects.filter(role__in=roles, is_active=True)}
    if schedule:
        users.update({u.id: u for u in schedule.recipient_users.filter(is_active=True)})
    return list(users.values())


def report_link() -> str:
    base = (getattr(settings, 'FRONTEND_BASE_URL', '') or getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    return f'{base}/app/reports' if base else 'the Reports page of the RBF platform'


def distribute(report: GeneratedReport, actor, roles=None, users=None) -> int:
    """Share a ready (and, if formal, approved) report with its recipients. Returns how many."""
    from rbf.notifications.services import NotificationService

    if report.status != GeneratedReport.Status.READY:
        raise ValidationError({'detail': 'The report is not ready.'})
    if is_formal(report) and report.approval_status != A.APPROVED:
        raise ValidationError({'detail': 'A formal report can only be distributed once approved.'})
    recipients = recipients_for(report.schedule, roles) if users is None else list(users)
    recipients = [u for u in recipients if u.id != report.generated_by_id]
    if not recipients:
        return 0
    report.distributed_to.add(*recipients)
    report.distributed_at = timezone.now()
    report.save(update_fields=['distributed_at'])
    period = report.filters.get('from') and f"{report.filters.get('from')} to {report.filters.get('to') or 'today'}"
    title = f'Report available: {report.title}' + (f' v{report.version}' if report.version > 1 else '')
    body = f'{report.title}{f" for {period}" if period else ""} has been shared with you. Download it from Reports.'
    _notify(recipients, event='report_shared', title=title, body=body, report=report)
    NotificationService.dispatch_email(
        f'[RBF Platform] {title}',
        f'{body}\n\nOpen {report_link()} and sign in to download it. The file is not attached to this email.\n\n'
        f'Reference: RPT-{report.id.hex[:8].upper()}',
        [u.email for u in recipients if u.email],
    )
    _log(actor, 'report_distributed', report, recipients=len(recipients))
    return len(recipients)


# ---------------------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------------------

def previous_period(frequency: str, today: date) -> tuple[date, date]:
    first_this_month = today.replace(day=1)
    if frequency == ReportSchedule.Frequency.MONTHLY:
        end = first_this_month - timedelta(days=1)
        return end.replace(day=1), end
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    this_quarter_start = today.replace(month=quarter_start_month, day=1)
    end = this_quarter_start - timedelta(days=1)
    return end.replace(month=((end.month - 1) // 3) * 3 + 1, day=1), end


def next_run(schedule: ReportSchedule, after: datetime) -> datetime:
    """The next run date strictly after `after`, at 06:00 local time on the schedule's day."""
    tz = timezone.get_current_timezone()
    local = timezone.localtime(after, tz)
    day = max(1, min(28, schedule.run_day))
    year, month = local.year, local.month
    for _ in range(15):
        runs_this_month = schedule.frequency == ReportSchedule.Frequency.MONTHLY or month in (1, 4, 7, 10)
        if runs_this_month:
            candidate = timezone.make_aware(datetime.combine(date(year, month, day), time(6, 0)), tz)
            if candidate > after:
                return candidate
        month += 1
        if month > 12:
            month, year = 1, year + 1
    raise ValueError('Could not compute the next run date.')


def run_schedule(schedule: ReportSchedule, now: datetime | None = None) -> GeneratedReport:
    from .report_queue import enqueue

    now = now or timezone.now()
    start, end = previous_period(schedule.frequency, timezone.localtime(now).date())
    filters = {**(schedule.filters or {}), 'from': start.isoformat(), 'to': end.isoformat()}
    report = enqueue(schedule.prepared_by, schedule.report_type, schedule.format, filters)
    report.schedule = schedule
    report.save(update_fields=['schedule'])
    schedule.last_run_at = now
    schedule.next_run_at = next_run(schedule, now)
    schedule.save(update_fields=['last_run_at', 'next_run_at', 'updated_at'])
    return report


def run_due_schedules(now: datetime | None = None) -> int:
    """Queue every active schedule whose run time has come. Safe to call from several processes."""
    now = now or timezone.now()
    ran = 0
    while True:
        with transaction.atomic():
            schedule = (
                ReportSchedule.objects.select_for_update(skip_locked=True)
                .filter(active=True, next_run_at__lte=now).order_by('next_run_at').first()
            )
            if schedule is None:
                return ran
            try:
                run_schedule(schedule, now)
            except Exception:  # noqa: BLE001 - a broken schedule must not stop the others
                logger.exception('Report schedule %s could not run', schedule.id)
                schedule.next_run_at = next_run(schedule, now)
                schedule.save(update_fields=['next_run_at'])
        ran += 1
