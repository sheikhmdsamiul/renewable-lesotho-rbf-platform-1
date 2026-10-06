"""Project archive.

A project is archived when it completes. The archive covers the whole lifecycle, from tender
creation to completion and contract closure:

* a permanent ProjectArchive record is written: a timeline of every step and a snapshot of
  the procurement (tender, lot, bids, evaluation scores, intent to award, challenges, award),
  the contract, and delivery (milestones, installations, verification, claims, disbursements,
  KPIs, oversight and audit), plus a PDF dossier;
* the project's contract is closed;
* once every project delivered under a tender is archived, the tender itself is archived and
  its procurement records become read-only too (a lot-wise tender waits for all its lots).

Archiving keeps every record (nothing is deleted: the SRS requires completed projects to stay
available for internal and external audit) but:

* the project and everything under it becomes read-only: milestones, completion reviews,
  setup, updates, documents, installations, verification tasks and field verifications,
  payment claims and disbursements, meter data, anomaly flags, DoE monitoring visits and
  KPI reviews. Any attempt to create, change or delete them is refused;
* those records leave the operational lists (work queues, maps, claim lists) and are
  reached through the Archived view instead (`?archived=1`), or by asking for one project.

Oversight reviews and audit cases are NOT frozen: PSC, RMT and the Auditor must still be
able to review and audit an archived project.

Only the Super Admin can restore an archived project, with a reason, for corrections.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Q
from django.db.models.signals import pre_delete, pre_save
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

import logging
from pathlib import Path

from django.core.files import File

from .models import (
    ProjectArchive,
    AnomalyEvidenceFile,
    AnomalyFlag,
    AnomalyReviewEvent,
    Disbursement,
    FieldVerification,
    InstallationReport,
    KpiReview,
    MeterDataBatch,
    Milestone,
    MilestoneCompletionReview,
    PaymentClaim,
    Project,
    ProjectDocument,
    ProjectSetup,
    ProjectUpdate,
    SiteMonitoringPhoto,
    SiteMonitoringVisit,
    SmartMeterReading,
    VerificationTask,
)

ARCHIVED_MESSAGE = 'This project is completed and archived. Its records are read-only.'
TENDER_ARCHIVED_MESSAGE = 'This tender is archived: every project delivered under it is completed. Its records are read-only.'
CONTRACT_CLOSED_MESSAGE = 'This contract is closed: its project is completed and archived.'

logger = logging.getLogger(__name__)

# Record type -> attribute path to its project.
FROZEN_MODELS = {
    Milestone: 'project',
    MilestoneCompletionReview: 'project',
    ProjectSetup: 'project',
    ProjectUpdate: 'project',
    ProjectDocument: 'project',
    PaymentClaim: 'project',
    Disbursement: 'claim.project',
    InstallationReport: 'project',
    VerificationTask: 'report.project',
    FieldVerification: 'installation.project',
    MeterDataBatch: 'project',
    SmartMeterReading: 'project',
    AnomalyFlag: 'project',
    AnomalyReviewEvent: 'flag.project',
    AnomalyEvidenceFile: 'flag.project',
    SiteMonitoringVisit: 'project',
    SiteMonitoringPhoto: 'visit.project',
    KpiReview: 'project',
}

# Integration bookkeeping that may still be written on an archived record (e.g. a queued
# Prospect push finishing after completion). Business data never is.
SYSTEM_FIELDS = {'prospect_sync_status', 'prospect_sync_error', 'prospect_synced_at', 'updated_at'}

_bypass = ContextVar('project_archive_bypass', default=False)


class ProjectArchived(PermissionDenied):
    default_detail = ARCHIVED_MESSAGE
    default_code = 'project_archived'


@contextmanager
def archive_bypass():
    """Let the archive/restore steps themselves write to an archived project."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def is_archived(project_or_id) -> bool:
    if project_or_id is None:
        return False
    if isinstance(project_or_id, Project):
        return project_or_id.archived_at is not None
    return Project.objects.filter(pk=project_or_id, archived_at__isnull=False).exists()


def assert_not_archived(project_or_id):
    if is_archived(project_or_id):
        raise ProjectArchived()


def _project_id_for(instance, path: str):
    obj = instance
    *parents, last = path.split('.')
    for name in parents:
        obj = getattr(obj, name, None)
        if obj is None:
            return None
    return getattr(obj, f'{last}_id', None)


def _guard_write(sender, instance, update_fields=None, **kwargs):
    if _bypass.get() or kwargs.get('raw'):
        return
    if update_fields is not None and set(update_fields) <= SYSTEM_FIELDS:
        return
    if sender is Project:
        if instance.pk and Project.objects.filter(pk=instance.pk, archived_at__isnull=False).exists():
            raise ProjectArchived()
        return
    project_id = _project_id_for(instance, FROZEN_MODELS[sender])
    if project_id and Project.objects.filter(pk=project_id, archived_at__isnull=False).exists():
        raise ProjectArchived()


def _guard_delete(sender, instance, **kwargs):
    if _bypass.get():
        return
    if sender is Project:
        if instance.archived_at:
            raise ProjectArchived('Archived projects are kept for audit and cannot be deleted.')
        return
    project_id = _project_id_for(instance, FROZEN_MODELS[sender])
    if project_id and Project.objects.filter(pk=project_id, archived_at__isnull=False).exists():
        raise ProjectArchived()


def _tender_frozen_models():
    from rbf.tenders import models as t

    # Procurement record -> attribute path to its tender. (View logs and notices are not records of the procurement.)
    return {
        t.Tender: '',
        t.TenderLot: 'tender',
        t.TenderBoqItem: 'tender',
        t.TenderRequiredDocument: 'tender',
        t.TenderEvaluationCommitteeMember: 'tender',
        t.TenderInvitedVendor: 'tender',
        t.EvaluationConflictOfInterest: 'tender',
        t.TenderBid: 'tender',
        t.TenderBidSite: 'bid.tender',
        t.TenderBidLotOffer: 'bid.tender',
        t.TenderBidEvaluation: 'bid.tender',
        t.TenderBidEvaluationRevision: 'evaluation.bid.tender',
        t.TenderAwardRecommendation: 'tender',
        t.IntentToAwardRequest: 'tender',
        t.TenderChallenge: 'tender',
        t.ChallengeDocument: 'challenge.tender',
        t.ChallengeEvent: 'challenge.tender',
    }


def _tender_archived(sender, instance) -> bool:
    from rbf.tenders.models import Tender

    path = _tender_frozen_models()[sender]
    tender_id = instance.pk if path == '' else _project_id_for(instance, path)
    return bool(tender_id) and Tender.objects.filter(pk=tender_id, archived_at__isnull=False).exists()


def _guard_tender_write(sender, instance, **kwargs):
    if _bypass.get() or kwargs.get('raw'):
        return
    if _tender_archived(sender, instance):
        raise ProjectArchived(TENDER_ARCHIVED_MESSAGE)


def _guard_contract_write(sender, instance, **kwargs):
    from rbf.tenders.models import ContractStatus, TenderContract

    if _bypass.get() or kwargs.get('raw') or not instance.pk:
        return
    if TenderContract.objects.filter(pk=instance.pk, status=ContractStatus.CLOSED).exists():
        raise ProjectArchived(CONTRACT_CLOSED_MESSAGE)


def connect_signals():
    from rbf.tenders.models import TenderContract

    for model in [Project, *FROZEN_MODELS]:
        pre_save.connect(_guard_write, sender=model, dispatch_uid=f'archive_guard_save_{model.__name__}')
        pre_delete.connect(_guard_delete, sender=model, dispatch_uid=f'archive_guard_delete_{model.__name__}')
    for model in _tender_frozen_models():
        pre_save.connect(_guard_tender_write, sender=model, dispatch_uid=f'archive_guard_save_{model.__name__}')
        pre_delete.connect(_guard_tender_write, sender=model, dispatch_uid=f'archive_guard_delete_{model.__name__}')
    pre_save.connect(_guard_contract_write, sender=TenderContract, dispatch_uid='archive_guard_save_TenderContract')
    pre_delete.connect(_guard_contract_write, sender=TenderContract, dispatch_uid='archive_guard_delete_TenderContract')


def archive_project(project: Project, actor, *, reason: str = 'Project completed.') -> Project:
    """Archive a completed project and its whole lifecycle. Idempotent."""
    from rbf.tenders.models import ContractStatus

    from .audit import log_audit
    from .kpi import create_project_activity_update
    from .lifecycle import build_lifecycle, project_contract

    if project.archived_at:
        return project
    user = actor if getattr(actor, 'is_authenticated', False) else None
    now = timezone.now()
    with archive_bypass():
        contract = project_contract(project)
        contract_status_before = contract.status if contract else ''
        if contract and contract.status != ContractStatus.CLOSED:
            contract.status = ContractStatus.CLOSED
            contract.closed_at = now
            contract.save(update_fields=['status', 'closed_at', 'updated_at'])
        create_project_activity_update(
            project, actor, 'Project Archived',
            f'{reason} The project, its contract and its full lifecycle record are now archived and read-only.',
        )
        lifecycle = build_lifecycle(project, ended_at=now)
        lifecycle['snapshot']['contract_status_before_closure'] = contract_status_before
        record = ProjectArchive.objects.create(
            project=project,
            tender=project.tender,
            contract=contract,
            archived_by=user,
            reason=reason,
            lifecycle_started_at=lifecycle['started_at'],
            lifecycle_ended_at=lifecycle['ended_at'],
            timeline=lifecycle['timeline'],
            snapshot=lifecycle['snapshot'],
        )
        project.archived_at = now
        project.archived_by = user
        project.save(update_fields=['archived_at', 'archived_by', 'updated_at'])
        tender_archived = _archive_tender_if_delivered(project.tender, now)
    _attach_dossier(record)
    log_audit(actor, 'project_archived', project, {
        'project_id': str(project.id), 'reason': reason, 'module': 'projects', 'archive_id': record.id,
        'contract_id': str(contract.id) if contract else '', 'tender_archived': tender_archived,
        'record_counts': archive_counts(project),
    })
    return project


def _archive_tender_if_delivered(tender, now) -> bool:
    """Archive the tender once it is fully awarded and every project under it is archived."""
    from rbf.tenders.models import TenderStatus

    if tender is None or tender.archived_at or tender.status != TenderStatus.AWARDED:
        return False
    if tender.projects.filter(archived_at__isnull=True).exists():
        return False
    tender.archived_at = now
    tender.save(update_fields=['archived_at', 'updated_at'])
    return True


def _attach_dossier(record: ProjectArchive):
    """Render the lifecycle dossier PDF. A rendering failure never blocks archiving: the
    record itself holds the full lifecycle, and the dossier can be regenerated."""
    from .lifecycle_dossier import render_dossier

    try:
        path = render_dossier(record)
        with Path(path).open('rb') as handle:
            with archive_bypass():
                record.dossier.save(Path(path).name, File(handle), save=True)
    except Exception:  # noqa: BLE001
        logger.exception('Archive dossier rendering failed for project %s', record.project_id)


def restore_project(project: Project, actor, *, reason: str) -> Project:
    """Super Admin only: reopen an archived project for correction. The archive record is
    kept (marked superseded); archiving again writes a new one."""
    from rbf.tenders.models import ContractStatus

    from .audit import log_audit
    from .kpi import create_project_activity_update

    if not project.archived_at:
        return project
    archived_at = project.archived_at
    record = project.archives.filter(superseded_at__isnull=True).first()
    with archive_bypass():
        if record:
            record.superseded_at = timezone.now()
            record.save(update_fields=['superseded_at'])
            contract = record.contract
            previous = (record.snapshot or {}).get('contract_status_before_closure') or ContractStatus.APPROVED
            if contract and contract.status == ContractStatus.CLOSED:
                contract.status = previous
                contract.closed_at = None
                contract.save(update_fields=['status', 'closed_at', 'updated_at'])
        if project.tender_id and project.tender.archived_at:
            project.tender.archived_at = None
            project.tender.save(update_fields=['archived_at', 'updated_at'])
        project.archived_at = None
        project.archived_by = None
        project.save(update_fields=['archived_at', 'archived_by', 'updated_at'])
        create_project_activity_update(project, actor, 'Project Restored From Archive', f'Restored for correction: {reason}')
    log_audit(actor, 'project_restored', project, {
        'project_id': str(project.id), 'reason': reason, 'archived_at': archived_at.isoformat(), 'module': 'projects',
    })
    return project


def archive_counts(project: Project) -> dict:
    """What the archive holds, recorded with the archive event."""
    return {
        'milestones': project.milestones.count(),
        'installations': project.installation_reports.count(),
        'field_verifications': FieldVerification.objects.filter(installation__project=project).count(),
        'payment_claims': project.payment_claims.count(),
        'disbursements': Disbursement.objects.filter(claim__project=project).count(),
        'meter_readings': SmartMeterReading.objects.filter(project=project).count(),
        'documents': project.documents.count(),
    }


def archived_scope(request, queryset, prefix: str = 'project__', scope_params: tuple = ('project',)):
    """Apply archive visibility to a list endpoint.

    * `?archived=1` -> only records of archived projects (the Archived view);
    * `?archived=all` -> both;
    * filtered to one project (e.g. `?project=12`) -> that project's records, archived or not;
    * otherwise -> archived projects' records are left out of the operational list.

    The Auditor reviews archives as part of the job, so sees everything by default.
    """
    from rbf.users.models import UserRole

    params = request.query_params
    archived_filter = Q(**{f'{prefix}archived_at__isnull': False})
    choice = str(params.get('archived') or '').strip().lower()
    if choice in {'1', 'true', 'only'}:
        return queryset.filter(archived_filter)
    if choice == 'all':
        return queryset
    if any(params.get(name) for name in scope_params):
        return queryset
    if getattr(request.user, 'role', None) == UserRole.AUDITOR:
        return queryset
    return queryset.exclude(archived_filter)
