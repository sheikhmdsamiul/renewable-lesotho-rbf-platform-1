"""What each notification event means to its reader: category, priority, and the record it is about.

Senders store only an `event` and a `linked_entity_id`; the meaning of that id depends on the
event (a project for claim events, an installation report for verification events, a tender for
procurement events, and so on). This module turns those into something the inbox can show and
link to, resolving the related project or tender in a few batched queries per page.
"""
from __future__ import annotations

from collections import defaultdict

# (prefix, category, entity_type). The first matching prefix wins, so longer prefixes come first.
EVENT_RULES: list[tuple[str, str, str]] = [
    ('payment_claim_', 'payments', 'project'),
    ('milestone_', 'payments', 'project'),
    ('installation_', 'verification', 'installation'),
    ('verification_', 'verification', 'installation'),
    ('meter_', 'data', 'project'),
    ('anomaly_', 'data', 'anomaly'),
    ('audit_', 'oversight', 'audit_case'),
    # The overdue reminder links 'oversight:<review id>'; the follow-up update links the project id.
    ('oversight_follow_up_overdue', 'oversight', 'oversight'),
    ('oversight_', 'oversight', 'project'),
    ('project_oversight_flag', 'oversight', 'project'),
    ('project_', 'projects', 'project'),
    ('projects_', 'projects', 'project'),
    ('report_', 'reports', 'report'),
    ('tenders_', 'procurement', 'bid'),
    ('eoi_', 'procurement', 'bid'),
    ('tender_', 'procurement', 'tender'),
    ('bid_', 'procurement', 'tender'),
    ('stage_one_', 'procurement', 'tender'),
    ('intent_', 'procurement', 'tender'),
    ('award_', 'procurement', 'tender'),
    ('challenge_', 'procurement', 'tender'),
    ('contract_', 'procurement', 'tender'),
    ('evaluation_', 'procurement', 'tender'),
    ('prequalification_', 'compliance', 'prequalification'),
    ('vendor_blacklist', 'compliance', 'blacklist_case'),
    ('blacklist_recommendation', 'compliance', 'blacklist_recommendation'),
    ('notice_', 'notices', 'notice'),
]

CATEGORY_LABELS = {
    'payments': 'Payments',
    'verification': 'Field verification',
    'data': 'Meter data & anomalies',
    'oversight': 'Oversight & audit',
    'projects': 'Projects',
    'reports': 'Reports',
    'procurement': 'Procurement',
    'compliance': 'Compliance',
    'notices': 'Notices',
    'general': 'General',
}

# Events that ask the reader to act soon, or tell them something went against them.
HIGH_PRIORITY_EVENTS = {
    'anomaly_escalated', 'anomaly_escalated_vendor', 'anomaly_correction_requested', 'anomaly_evidence_requested',
    'payment_claim_returned', 'payment_claim_rejected', 'payment_claim_pushed_back', 'vendor_blacklisted', 'vendor_blacklisting_initiated',
    'audit_response_requested', 'audit_corrective_action_overdue', 'oversight_follow_up_overdue',
    'verification_concern', 'verification_reverification_requested', 'award_paused', 'intent_revoked',
    'contract_rejected', 'bid_rejected', 'bid_revision_required', 'project_setup_rejected',
    'project_setup_changes_requested', 'meter_data_batch_rejected', 'meter_data_batch_correction_requested',
    'meter_data_batch_flagged', 'meter_csv_anomaly_detected', 'intent_to_award_approval_requested',
    'report_failed', 'report_approval_needed', 'report_review_needed', 'project_oversight_flag',
}


def classify(event: str) -> tuple[str, str]:
    """(category, entity_type) for an event name."""
    event = str(event or '')
    for prefix, category, entity_type in EVENT_RULES:
        if event.startswith(prefix):
            return category, entity_type
    return 'general', ''


def priority(event: str) -> str:
    event = str(event or '')
    if event in HIGH_PRIORITY_EVENTS or event.startswith('intent_to_award_approval_requested'):
        return 'high'
    return 'normal'


def _entity_key(notification) -> tuple[str, str]:
    _, entity_type = classify(notification.event)
    raw = str(notification.linked_entity_id or '')
    if raw.startswith('oversight:'):
        return 'oversight', raw.split(':', 1)[1]
    return entity_type, raw


def _int_ids(values) -> list[int]:
    return [int(v) for v in values if str(v).isdigit()]


def resolve_related(notifications) -> dict[int, dict]:
    """Map notification id -> related-record info, with one query per entity type.

    Returns {'type', 'id', 'label', 'project_id', 'project_label', 'tender_id', 'tender_label'};
    fields that do not apply are empty strings.
    """
    from rbf.projects.models import (
        AnomalyFlag, AuditCase, GeneratedReport, InstallationReport, OversightReview, Project,
    )
    from rbf.tenders.models import Notice, Tender, TenderBid

    by_type: dict[str, set[str]] = defaultdict(set)
    keys = {}
    for n in notifications:
        entity_type, raw = _entity_key(n)
        keys[n.id] = (entity_type, raw)
        if entity_type and raw:
            by_type[entity_type].add(raw)

    project_of: dict[tuple[str, str], int | None] = {}
    tender_of: dict[tuple[str, str], int | None] = {}
    label_of: dict[tuple[str, str], str] = {}

    for row in InstallationReport.objects.filter(id__in=_int_ids(by_type['installation'])).values('id', 'project_id', 'serial_number'):
        k = ('installation', str(row['id']))
        project_of[k] = row['project_id']
        label_of[k] = f"Installation #{row['id']}" + (f" ({row['serial_number']})" if row['serial_number'] else '')
    for row in AnomalyFlag.objects.filter(id__in=_int_ids(by_type['anomaly'])).values('id', 'project_id', 'flag_type'):
        k = ('anomaly', str(row['id']))
        project_of[k] = row['project_id']
        label_of[k] = f"Anomaly flag #{row['id']} ({str(row['flag_type']).replace('_', ' ')})"
    for row in AuditCase.objects.filter(id__in=_int_ids(by_type['audit_case'])).values('id', 'project_id', 'reference'):
        k = ('audit_case', str(row['id']))
        project_of[k] = row['project_id']
        label_of[k] = f"Audit case {row['reference']}"
    for row in OversightReview.objects.filter(id__in=_int_ids(by_type['oversight'])).values('id', 'project_id'):
        k = ('oversight', str(row['id']))
        project_of[k] = row['project_id']
        label_of[k] = f"Oversight review #{row['id']}"
    for row in TenderBid.objects.filter(id__in=_int_ids(by_type['bid'])).values('id', 'tender_id'):
        k = ('bid', str(row['id']))
        tender_of[k] = row['tender_id']
        label_of[k] = f"Bid #{row['id']}"
    for row in Notice.objects.filter(id__in=_int_ids(by_type['notice'])).values('id', 'title'):
        label_of[('notice', str(row['id']))] = f"Notice: {row['title']}"
    report_ids = [v for v in by_type['report'] if v]
    if report_ids:
        try:
            for row in GeneratedReport.objects.filter(id__in=report_ids).values('id', 'title'):
                label_of[('report', str(row['id']))] = f"Report: {row['title'] or row['id']}"
        except (ValueError, Exception):  # malformed UUIDs from old rows
            pass
    project_ids = set(_int_ids(by_type['project'])) | {pid for pid in project_of.values() if pid}
    projects = {
        row['id']: row for row in Project.objects.filter(id__in=project_ids).values('id', 'project_reference', 'project_title')
    }
    tender_ids = set(_int_ids(by_type['tender'])) | {tid for tid in tender_of.values() if tid}
    tenders = {row['id']: row for row in Tender.objects.filter(id__in=tender_ids).values('id', 'reference_number', 'name')}

    def project_label(pid):
        row = projects.get(pid)
        if not row:
            return ''
        return row['project_reference'] or row['project_title'] or f'Project #{pid}'

    def tender_label(tid):
        row = tenders.get(tid)
        if not row:
            return ''
        return f"{row['reference_number']} — {row['name']}" if row['reference_number'] else row['name']

    result = {}
    for nid, (entity_type, raw) in keys.items():
        info = {'type': entity_type, 'id': raw, 'label': '', 'project_id': '', 'project_label': '', 'tender_id': '', 'tender_label': ''}
        if entity_type and raw:
            k = (entity_type, raw)
            pid = int(raw) if entity_type == 'project' and raw.isdigit() else project_of.get(k)
            tid = int(raw) if entity_type == 'tender' and raw.isdigit() else tender_of.get(k)
            if pid and pid in projects:
                info['project_id'] = str(pid)
                info['project_label'] = project_label(pid)
            if tid and tid in tenders:
                info['tender_id'] = str(tid)
                info['tender_label'] = tender_label(tid)
            info['label'] = (
                label_of.get(k)
                or (info['project_label'] and entity_type == 'project' and f"Project {info['project_label']}")
                or (info['tender_label'] and entity_type == 'tender' and f"Tender {info['tender_label']}")
                or ''
            )
        result[nid] = info
    return result
