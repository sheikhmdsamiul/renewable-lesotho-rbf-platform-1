"""Background report generation.

A request queues a GeneratedReport row (status "queued") after checking access and filters,
so permission and input errors are returned immediately. The report scheduler process
(`run_report_scheduler`, running in both docker-compose files) claims queued rows every few
seconds and generates them, so large reports never hit the web request timeout. The
requester gets an in-app notification when the report is ready or has failed.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus

from .models import GeneratedReport, Project
from . import report_engine

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=20)
S = GeneratedReport.Status


def reference_for(report: GeneratedReport) -> str:
    return f'RPT-{report.id.hex[:8].upper()}'


def filename_for(title: str, ext: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in title).strip('_') or 'report'
    return f'{safe}_{timezone.localdate().isoformat()}.{ext}'


def enqueue(user, report_id: str, fmt: str, filters: dict) -> GeneratedReport:
    definition, ctx = report_engine.build(user, report_id, filters)
    if fmt not in definition.formats:
        raise ValidationError({'format': f'This report is available as {", ".join(definition.formats)}.'})
    if ctx.project_id:
        ctx.project()  # raises if the project is outside the viewer's scope
    return GeneratedReport.objects.create(
        report_type=report_id,
        format=fmt,
        filters=filters,
        title=definition.title,
        scope_label=ctx.scope_label(),
        project=Project.objects.filter(id=ctx.project_id).first() if (ctx.project_id or '').isdigit() else None,
        generated_by=user,
        status=S.QUEUED,
    )


def _notify(report: GeneratedReport, *, ok: bool):
    user = report.generated_by
    if user is None:
        return
    Notification.objects.create(
        recipient_id=str(user.id),
        recipient_name=user.full_name or user.username,
        type=NotificationChannel.IN_APP,
        event='report_ready' if ok else 'report_failed',
        title=f'Report ready: {report.title}' if ok else f'Report failed: {report.title}',
        body=(f'{report.title} ({report.get_format_display()}) is ready to download from Reports.' if ok
              else f'{report.title} could not be generated: {report.error}'),
        status=NotificationStatus.SENT,
        linked_entity_id=str(report.id),
    )


def run(report: GeneratedReport) -> GeneratedReport:
    """Generate one claimed report and store the result."""
    from .audit import log_audit

    try:
        _definition, data, content, _ctype, ext = report_engine.generate(
            report.generated_by, report.report_type, report.format, report.filters, reference=reference_for(report),
        )
        report.file.save(filename_for(data.title, ext), ContentFile(content), save=False)
        report.title = data.title
        report.row_count = data.row_count
        report.status = S.READY
        report.error = ''
    except Exception as exc:  # noqa: BLE001 - every failure must end the job, not leave it running
        logger.exception('Report %s (%s) failed', report.id, report.report_type)
        report.status = S.FAILED
        report.error = str(exc.detail) if isinstance(exc, APIException) else 'The report could not be generated. The error has been logged.'
    report.completed_at = timezone.now()
    report.save()
    if report.status == S.READY:
        from .report_workflow import on_ready

        try:
            on_ready(report)
        except Exception:  # noqa: BLE001 - a distribution failure must not undo the generated report
            logger.exception('Report %s was generated but sign-off or distribution failed', report.id)
    log_audit(report.generated_by, 'report_generated' if report.status == S.READY else 'report_failed', report, {
        'module': 'report', 'report_type': report.report_type, 'format': report.format, 'filters': report.filters,
        'rows': report.row_count,
    })
    _notify(report, ok=report.status == S.READY)
    return report


def claim_next() -> GeneratedReport | None:
    with transaction.atomic():
        report = (
            GeneratedReport.objects.select_for_update(skip_locked=True)
            .filter(status=S.QUEUED).order_by('generated_at').first()
        )
        if report is None:
            return None
        report.status = S.RUNNING
        report.started_at = timezone.now()
        report.save(update_fields=['status', 'started_at'])
        return report


def fail_stale():
    """Jobs left running by a crashed worker are marked failed so they do not hang forever."""
    stale = GeneratedReport.objects.filter(status=S.RUNNING, started_at__lt=timezone.now() - STALE_AFTER)
    return stale.update(status=S.FAILED, error='Generation was interrupted. Generate the report again.', completed_at=timezone.now())


def process(limit: int = 10) -> int:
    """Generate up to `limit` queued reports. Returns how many were processed."""
    fail_stale()
    done = 0
    while done < limit:
        report = claim_next()
        if report is None:
            break
        run(report)
        done += 1
    return done
