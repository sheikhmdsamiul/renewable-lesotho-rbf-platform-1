"""Independent audit reports, built from source records and the audit log, read-only."""
from __future__ import annotations

from collections import Counter, defaultdict

from django.db.models import Count, Q
from django.utils import timezone

from . import claim_status
from .milestone_reviews import ADVANCING_DECISIONS, is_zero_value_milestone, previous_milestone
from .models import (
    AnomalyFlag,
    AuditCase,
    AuditLog,
    Disbursement,
    FieldVerification,
    FieldVerificationStatus,
    InstallationReport,
    MeterDataBatch,
    PaymentClaim,
    PaymentClaimStatus,
    VerificationTask,
)
from .report_engine import ReportContext, ReportData, Table, _d, _money, _pct, _scoped_claims

# The approval chain as recorded in the audit log, in order, with the role expected to act.
CHAIN = [
    ('payment_claim_submitted', 'Submitted', {'Vendor'}),
    ('claim_rmt_approved', 'RMT approved', {'RBF Management Team', 'Platform Administrator (Super Admin)'}),
    ('claim_tac_endorsed', 'TAC endorsed', {'TAC Member'}),
    ('claim_psc_approved', 'PSC approved', {'Project Steering Committee'}),
    ('finance_payment_processed', 'Payment processed', {'Platform Administrator (Super Admin)'}),
    ('payment_confirmed', 'Payment confirmed', {'RBF Management Team', 'Platform Administrator (Super Admin)'}),
]
APPROVAL_STEPS = [step for step in CHAIN if step[0] != 'payment_claim_submitted']


def claim_chain(claims) -> dict:
    """claim id -> {action: (time, actor id, actor name, role)} from the audit log (first occurrence)."""
    ids = [str(c.id) for c in claims]
    chain: dict = defaultdict(dict)
    logs = AuditLog.objects.filter(
        entity_type='PaymentClaim', entity_id__in=ids, action__in=[a for a, _, _ in CHAIN],
    ).select_related('actor').order_by('created_at')
    for log in logs:
        steps = chain[int(log.entity_id)]
        if log.action not in steps:
            name = (log.actor.full_name or log.actor.username) if log.actor_id else 'System'
            steps[log.action] = (log.created_at, log.actor_id, name, log.actor_role)
    return chain


def build_payment_chain(ctx: ReportContext) -> ReportData:
    claims = list(_scoped_claims(ctx))
    chain = claim_chain(claims)
    rows, exceptions = [], []
    counts = Counter()
    for claim in claims:
        steps = chain.get(claim.id, {})
        issues = []
        reached = [a for a, _, _ in APPROVAL_STEPS if a in steps]
        # Steps the claim's status says happened but the log does not show.
        # Payment processing by Finance is optional: RMT's payment confirmation records the disbursement itself.
        required = {
            PaymentClaimStatus.RMT_APPROVED: ['claim_rmt_approved'],
            PaymentClaimStatus.TAC_ENDORSED: ['claim_rmt_approved', 'claim_tac_endorsed'],
            PaymentClaimStatus.PSC_APPROVED: ['claim_rmt_approved', 'claim_tac_endorsed', 'claim_psc_approved'],
            PaymentClaimStatus.COMPLETED: ['claim_rmt_approved', 'claim_tac_endorsed', 'claim_psc_approved', 'payment_confirmed'],
        }.get(claim.status, [])
        labels = {action: label for action, label, _ in CHAIN}
        missing = [labels[action] for action in required if action not in steps]
        if missing:
            issues.append('No audit record for: ' + ', '.join(missing))
        times = [steps[a][0] for a in reached]
        if any(later < earlier for earlier, later in zip(times, times[1:])):
            issues.append('Steps recorded out of order')
        # Segregation of duties covers the four decisions; RMT confirming a payment it approved is by design.
        decisions = [a for a in ('claim_rmt_approved', 'claim_tac_endorsed', 'claim_psc_approved', 'finance_payment_processed') if a in steps]
        actors = [steps[a][1] for a in decisions if steps[a][1]]
        if len(actors) != len(set(actors)):
            issues.append('Same person approved more than one step')
        for action, label, roles in APPROVAL_STEPS:
            if action in steps and steps[action][3] and steps[action][3] not in roles:
                issues.append(f'{label} recorded by role "{steps[action][3]}"')
        if claim.status in claim_status.PAID and 'claim_psc_approved' not in steps:
            issues.append('Paid without a recorded PSC approval')
        for issue in issues:
            counts[issue.split(':')[0].split(' by role')[0]] += 1
        row = [claim.id, claim.project.project_reference or claim.project_id, claim.project.vendor_name, float(claim.claim_amount or 0), claim.status]
        for action, _label, _roles in CHAIN:
            step = steps.get(action)
            row += [_d(step[0]) if step else '', step[2] if step else '']
        row.append('; '.join(issues) or 'No exception')
        rows.append(row)
        if issues:
            exceptions.append([claim.id, claim.project.project_reference or claim.project_id, claim.status, '; '.join(issues)])
    columns = ['Claim', 'Project', 'Vendor', 'Amount (LSL)', 'Status']
    for _action, label, _roles in CHAIN:
        columns += [f'{label} at', f'{label} by']
    columns.append('Exceptions')
    data = ReportData(title='Payment Chain Audit')
    data.summary = [('Claims tested', len(claims)), ('With exceptions', len(exceptions)), ('Without exceptions', len(claims) - len(exceptions))]
    data.tables.append(Table('Exceptions by type', ['Exception', 'Claims'], [[k, v] for k, v in counts.most_common()], chart=(0, 1)))
    data.tables.append(Table('Claims with exceptions', ['Claim', 'Project', 'Status', 'Exceptions'], exceptions))
    data.tables.append(Table('Approval chain', columns, rows))
    return data


def build_reconciliation(ctx: ReportContext) -> ReportData:
    claims = list(_scoped_claims(ctx))
    disbursements = {d.claim_id: d for d in Disbursement.objects.filter(claim__in=claims)}
    rows, exceptions = [], 0
    for claim in claims:
        milestone_amount = float((claim.milestone.amount_lsl or claim.milestone.amount) or 0) if claim.milestone_id else None
        claimed = float(claim.claim_amount or 0)
        disb = disbursements.get(claim.id)
        paid = disb.amount if disb else None
        issues = []
        if milestone_amount is not None and abs(claimed - milestone_amount) > 0.5:
            issues.append(f'Claim differs from milestone amount by {_money(claimed - milestone_amount)}')
        if claim.status in claim_status.PAID and disb is None:
            issues.append('Marked paid with no disbursement record')
        if disb is not None and abs(float(paid) - claimed) > 0.5:
            issues.append(f'Disbursed amount differs from claim by {_money(float(paid) - claimed)}')
        if disb is not None and claim.status not in claim_status.PAID | claim_status.APPROVED_AWAITING_PAYMENT | claim_status.HELD:
            issues.append(f'Disbursement exists while claim is "{claim.status}"')
        if disb is not None and claim.payment_reference and disb.reference and disb.reference != claim.payment_reference:
            issues.append('Payment references differ')
        exceptions += bool(issues)
        rows.append([
            claim.id, claim.project.project_reference or claim.project_id, claim.project.vendor_name,
            f'M{claim.milestone.milestone_number}' if claim.milestone_id else '', milestone_amount if milestone_amount is not None else '',
            claimed, float(paid) if paid is not None else '', claim.status, claim.payment_reference, disb.reference if disb else '',
            '; '.join(issues) or 'Reconciled',
        ])
    data = ReportData(title='Claim, Verification and Payment Reconciliation')
    data.summary = [
        ('Claims', len(claims)), ('Reconciled', len(claims) - exceptions), ('With differences', exceptions),
        ('Claimed', _money(sum(float(c.claim_amount or 0) for c in claims))),
        ('Disbursed', _money(sum(float(d.amount or 0) for d in disbursements.values()))),
    ]
    data.tables.append(Table('Reconciliation', [
        'Claim', 'Project', 'Vendor', 'Milestone', 'Milestone amount (LSL)', 'Claimed (LSL)', 'Disbursed (LSL)', 'Claim status',
        'Claim payment ref', 'Disbursement ref', 'Result',
    ], rows))
    return data


def build_kpi_compliance(ctx: ReportContext) -> ReportData:
    """For each claim that moved past submission: were the milestone's conditions met when it was claimed?"""
    claims = [c for c in _scoped_claims(ctx) if c.milestone_id and c.status not in {PaymentClaimStatus.SUBMITTED, PaymentClaimStatus.LEGACY_PENDING}]
    rows, exceptions = [], 0
    for claim in claims:
        milestone, project = claim.milestone, claim.project
        target = project.target_installations or project.installation_target or 0
        verified_then = FieldVerification.objects.filter(
            installation__project=project, verification_status=FieldVerificationStatus.VERIFIED, verified_at__lte=claim.submitted_at,
        ).values('installation_id').distinct().count()
        share = _pct(verified_then, target) if target else None
        issues = []
        if milestone.required_installation_pct and (share is None or share < milestone.required_installation_pct):
            issues.append(f'Verified installations {share if share is not None else 0:.1f}% at claim, {milestone.required_installation_pct}% required')
        prior = previous_milestone(milestone)
        if prior is not None and not is_zero_value_milestone(prior):
            review = getattr(prior, 'completion_review', None)
            if review is None or review.decision not in ADVANCING_DECISIONS or (review.reviewed_at and review.reviewed_at > claim.submitted_at):
                issues.append(f'Milestone {prior.milestone_number} was not cleared before this claim')
        # Batch status is current, not as at the claim date, so this flags batches uploaded before the claim
        # that are flagged or awaiting correction now.
        if MeterDataBatch.objects.filter(project=project, status__in=['flagged', 'correction_requested'], created_at__lte=claim.submitted_at).exists():
            issues.append('A meter data batch uploaded before the claim is flagged or awaiting correction')
        exceptions += bool(issues)
        rows.append([
            claim.id, project.project_reference or project.id, project.vendor_name, f'M{milestone.milestone_number}', claim.status,
            _d(claim.submitted_at), milestone.required_installation_pct, verified_then, target, share if share is not None else '',
            '; '.join(issues) or 'Compliant',
        ])
    data = ReportData(title='KPI Compliance Audit')
    data.summary = [('Claims tested', len(claims)), ('Compliant', len(claims) - exceptions), ('Exceptions', exceptions)]
    data.tables.append(Table('Milestone conditions at claim', [
        'Claim', 'Project', 'Vendor', 'Milestone', 'Status', 'Claimed at', 'Required verified %', 'Verified installations at claim',
        'Target installations', 'Verified % at claim', 'Result',
    ], rows))
    return data


def build_red_flags(ctx: ReportContext) -> ReportData:
    projects = ctx.projects()
    installs = InstallationReport.objects.filter(project__in=projects)
    dup_ids = {
        row['beneficiary_id'] for row in installs.exclude(beneficiary_id='').values('beneficiary_id').annotate(n=Count('id')).filter(n__gt=1)
    }
    dup_phones = {
        row['beneficiary_phone'] for row in installs.exclude(beneficiary_phone='').values('beneficiary_phone').annotate(n=Count('id')).filter(n__gt=1)
    }
    visits = ctx.in_period(FieldVerification.objects.filter(installation__project__in=projects), 'verified_at')
    vendors: dict = {}

    def entry(name):
        return vendors.setdefault(name or 'Unknown', {
            'installations': 0, 'dup_ids': 0, 'dup_phones': 0, 'visits': 0, 'failed': 0, 'gps': 0,
            'reverified': 0, 'rejected': 0, 'anomalies': 0, 'meter': 0,
        })

    for row in installs.values('project__vendor_name', 'beneficiary_id', 'beneficiary_phone'):
        e = entry(row['project__vendor_name'])
        e['installations'] += 1
        e['dup_ids'] += row['beneficiary_id'] in dup_ids
        e['dup_phones'] += row['beneficiary_phone'] in dup_phones
    for row in visits.values('installation__project__vendor_name', 'verification_status', 'location_match'):
        e = entry(row['installation__project__vendor_name'])
        e['visits'] += 1
        e['failed'] += row['verification_status'] != FieldVerificationStatus.VERIFIED
        e['gps'] += not row['location_match']
    for row in VerificationTask.objects.filter(report__project__in=projects, verification_round__gt=1).values('report__project__vendor_name'):
        entry(row['report__project__vendor_name'])['reverified'] += 1
    for row in _scoped_claims(ctx).filter(status=PaymentClaimStatus.REJECTED).values('project__vendor_name'):
        entry(row['project__vendor_name'])['rejected'] += 1
    for row in AnomalyFlag.objects.filter(project__in=projects, is_resolved=False).values('project__vendor_name'):
        entry(row['project__vendor_name'])['anomalies'] += 1
    for row in MeterDataBatch.objects.filter(project__in=projects, status__in=['flagged', 'rejected', 'correction_requested']).values('project__vendor_name'):
        entry(row['project__vendor_name'])['meter'] += 1

    vendor_rows = []
    for name, e in vendors.items():
        signals = sum(1 for key in ('dup_ids', 'dup_phones', 'gps', 'reverified', 'rejected', 'anomalies', 'meter') if e[key]) \
            + (1 if e['visits'] and e['failed'] / e['visits'] > 0.2 else 0)
        vendor_rows.append([name, signals, e['installations'], e['dup_ids'], e['dup_phones'], e['visits'],
                            _pct(e['failed'], e['visits']), e['gps'], e['reverified'], e['rejected'], e['anomalies'], e['meter']])
    vendor_rows.sort(key=lambda r: (-r[1], r[0]))
    duplicate_rows = [
        [i.project.project_reference or i.project_id, i.project.vendor_name, i.serial_number, i.beneficiary_id, i.beneficiary_phone,
         'Beneficiary ID' if i.beneficiary_id in dup_ids else 'Phone', _d(i.submitted_at)]
        for i in installs.filter(Q(beneficiary_id__in=dup_ids) | Q(beneficiary_phone__in=dup_phones)).select_related('project').order_by('beneficiary_id')
    ]
    data = ReportData(title='Red-flag Report')
    data.summary = [
        ('Vendors with any signal', sum(1 for r in vendor_rows if r[1])), ('Duplicate beneficiary IDs', len(dup_ids)),
        ('Duplicate phone numbers', len(dup_phones)), ('GPS mismatches in period', sum(r[7] for r in vendor_rows)),
    ]
    data.tables.append(Table('By vendor', [
        'Vendor', 'Signals', 'Installations', 'Duplicate IDs', 'Duplicate phones', 'Visits in period', 'Failed visit %',
        'GPS mismatches', 'Re-verified', 'Rejected claims', 'Open anomalies', 'Meter data issues',
    ], vendor_rows, chart=(0, 1)))
    data.tables.append(Table('Duplicate beneficiaries', ['Project', 'Vendor', 'Installation serial', 'Beneficiary ID', 'Phone', 'Duplicated', 'Reported'],
                             duplicate_rows, pii={'Beneficiary ID': 'identity', 'Phone': 'identity'}))
    return data


def build_findings_tracker(ctx: ReportContext) -> ReportData:
    cases = ctx.in_period(AuditCase.objects.select_related('project', 'auditor', 'responded_by'), 'created_at').order_by('-created_at')
    today = timezone.localdate()
    rows = []
    for case in cases:
        overdue = bool(case.corrective_action_due and case.corrective_action_due < today and case.corrective_action_status in {'open', 'in_progress'})
        rows.append([
            case.reference, case.title, case.get_audit_area_display(), case.get_status_display(),
            case.get_finding_type_display() if case.finding_type else '', case.get_risk_level_display() if case.risk_level else '',
            case.project.project_reference if case.project_id else '', case.corrective_action, case.corrective_action_owner,
            _d(case.corrective_action_due), case.get_corrective_action_status_display(), 'Yes' if overdue else 'No',
            'Yes' if case.responded_at else 'No', _d(case.created_at), _d(case.closed_at),
        ])
    data = ReportData(title='Audit Findings and Recommendations Tracker')
    data.summary = [
        ('Cases', len(rows)), ('Open', sum(1 for r in rows if r[3] not in {'Closed'})),
        ('Major or critical', sum(1 for r in rows if r[5] in {'Major', 'Critical'})),
        ('Corrective actions overdue', sum(1 for r in rows if r[11] == 'Yes')),
    ]
    data.tables.append(Table('By status', ['Status', 'Cases'], [[k, v] for k, v in Counter(r[3] for r in rows).most_common()], chart=(0, 1)))
    data.tables.append(Table('Cases', [
        'Reference', 'Title', 'Area', 'Status', 'Finding', 'Risk', 'Project', 'Corrective action', 'Owner', 'Due', 'Action status',
        'Overdue', 'Management responded', 'Opened', 'Closed',
    ], rows))
    return data
