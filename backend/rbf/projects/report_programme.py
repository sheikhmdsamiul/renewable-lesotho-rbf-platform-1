"""Programme, governance, technical, regional, field and vendor reports."""
from __future__ import annotations

from collections import Counter

from django.db.models import Avg, Count, Max, Q, Sum
from django.utils import timezone

from rbf.users.models import PlatformConfiguration

from . import claim_status
from .district_scope import field_verifier_task_scope_filter
from .models import (
    AnomalyFlag,
    AuditCase,
    FieldVerification,
    FieldVerificationStatus,
    InstallationReport,
    InstallationStatus,
    MeterDataBatch,
    OversightReview,
    PaymentClaimStatus,
    ProjectStatus,
    ResultsIndicator,
    ResultsMeasure,
    SiteMonitoringVisit,
    SmartMeterReading,
    VerificationTask,
)
from .report_audit import claim_chain
from .report_engine import (
    CLAIM_COLUMNS,
    ReportContext,
    ReportData,
    Table,
    _claim_rows,
    _claim_totals,
    _d,
    _inclusion_row,
    _money,
    _pct,
    _scoped_claims,
    _user_name,
)
from .results import measure


def _fmt(value):
    if value is None or value == '':
        return ''
    return round(float(value), 2)


# ---------------------------------------------------------------------------------------
# Results framework
# ---------------------------------------------------------------------------------------

def results_rows(ctx: ReportContext) -> tuple[list[list], bool]:
    """One row per results indicator. Returns (rows, configured) where configured is False when
    no indicators have been entered and the platform's own measures are listed without targets."""
    projects = ctx.projects()
    indicators = list(ResultsIndicator.objects.all())
    configured = bool(indicators)
    if not configured:
        indicators = [
            ResultsIndicator(code=m.value, name=m.label, measure=m.value)
            for m in ResultsMeasure if m != ResultsMeasure.MANUAL
        ]
    rows = []
    for ind in indicators:
        if ind.measure == ResultsMeasure.MANUAL:
            to_date, in_period = ind.manual_actual, None
            source = f'Entered manually{f" (as of {ind.manual_actual_as_of:%d %b %Y})" if ind.manual_actual_as_of else ""}'
        else:
            to_date, in_period = measure(ind.measure, projects, ctx.date_from, ctx.date_to, ind.technology)
            source = 'Measured by the platform'
        progress = ''
        if ind.target and to_date is not None:
            span = float(ind.target) - float(ind.baseline or 0)
            progress = round((float(to_date) - float(ind.baseline or 0)) / span * 100.0, 1) if span else ''
        rows.append([
            ind.code, ind.name + (f' ({ind.technology})' if ind.technology else ''), ind.unit, _fmt(ind.baseline), _fmt(ind.target),
            _d(ind.target_date), _fmt(to_date), _fmt(in_period), progress, source + (f'. {ind.source_note}' if ind.source_note else ''),
        ])
    return rows, configured


RESULTS_COLUMNS = ['Code', 'Indicator', 'Unit', 'Baseline', 'Target', 'Target date', 'Actual to date', 'In period', '% of target', 'Source']


def build_results(ctx: ReportContext) -> ReportData:
    rows, configured = results_rows(ctx)
    verified = ctx.in_period(InstallationReport.objects.filter(project__in=ctx.projects(), status=InstallationStatus.VERIFIED), 'submitted_at')
    data = ReportData(title='Programme Results Report')
    data.summary = [
        ('Indicators', len(rows)),
        ('With a target', sum(1 for r in rows if r[4] != '')),
        ('On or above target', sum(1 for r in rows if isinstance(r[8], float) and r[8] >= 100)),
    ]
    if not configured:
        data.notes.append('No results framework has been entered yet, so the platform measures are listed without baselines or targets. '
                          'The Super Admin enters indicators, baselines and targets under Results Framework.')
    data.tables.append(Table('Results framework', RESULTS_COLUMNS, rows, chart=(1, 8) if configured else None))
    cols = ['Group', 'Verified installations', 'Female-headed %', 'Vulnerable %', 'Low-income %']
    data.tables.append(Table('Verified installations by district (period)', cols, [
        _inclusion_row(d, verified.filter(district=d)) for d in sorted({d for d in verified.values_list('district', flat=True) if d})
    ], chart=(0, 1)))
    data.tables.append(Table('Verified installations by technology (period)', cols, [
        _inclusion_row(t, verified.filter(project__tech_type=t)) for t in sorted({t for t in verified.values_list('project__tech_type', flat=True) if t})
    ]))
    return data


# ---------------------------------------------------------------------------------------
# Claims and money
# ---------------------------------------------------------------------------------------

OPEN_STAGES = {
    PaymentClaimStatus.SUBMITTED: 'Waiting for RMT', PaymentClaimStatus.LEGACY_PENDING: 'Waiting for RMT',
    PaymentClaimStatus.RMT_APPROVED: 'Waiting for TAC', PaymentClaimStatus.LEGACY_VERIFIED: 'Waiting for TAC',
    PaymentClaimStatus.TAC_ENDORSED: 'Waiting for PSC',
    PaymentClaimStatus.PSC_APPROVED: 'Waiting for payment', PaymentClaimStatus.LEGACY_APPROVED: 'Waiting for payment',
    PaymentClaimStatus.HELD_AUDIT: 'Held for audit',
}
STAGE_STARTED_BY = {
    PaymentClaimStatus.RMT_APPROVED: 'claim_rmt_approved', PaymentClaimStatus.TAC_ENDORSED: 'claim_tac_endorsed',
    PaymentClaimStatus.PSC_APPROVED: 'claim_psc_approved',
}


def _age_bucket(days: int) -> str:
    if days <= 7:
        return '0-7 days'
    if days <= 14:
        return '8-14 days'
    if days <= 30:
        return '15-30 days'
    return 'Over 30 days'


def build_claims_pipeline(ctx: ReportContext) -> ReportData:
    claims = [c for c in _scoped_claims(ctx) if c.status in OPEN_STAGES]
    chain = claim_chain(claims)
    now = timezone.now()
    rows, stages = [], {}
    for claim in claims:
        started = chain.get(claim.id, {}).get(STAGE_STARTED_BY.get(claim.status, ''), (None,))[0] or claim.submitted_at
        days = max(0, (now - started).days)
        stage = OPEN_STAGES[claim.status]
        entry = stages.setdefault(stage, [stage, 0, 0.0, 0])
        entry[1] += 1
        entry[2] += float(claim.claim_amount or 0)
        entry[3] = max(entry[3], days)
        rows.append([claim.id, claim.project.project_reference or claim.project_id, claim.project.vendor_name,
                     f'M{claim.milestone.milestone_number}' if claim.milestone_id else '', float(claim.claim_amount or 0),
                     stage, _d(started), days, _age_bucket(days), _d(claim.submitted_at)])
    rows.sort(key=lambda r: -r[7])
    paid = [c for c in _scoped_claims(ctx) if c.status in claim_status.PAID and c.paid_at]
    avg_days = round(sum((c.paid_at - c.submitted_at).days for c in paid) / len(paid), 1) if paid else None
    order = list(dict.fromkeys(OPEN_STAGES.values()))
    data = ReportData(title='Claims Pipeline and Ageing')
    data.summary = [
        ('Open claims', len(rows)), ('Value open', _money(sum(r[4] for r in rows))),
        ('Over 30 days in stage', sum(1 for r in rows if r[7] > 30)),
        ('Average days submit to paid', avg_days if avg_days is not None else 'No paid claims'),
    ]
    data.tables.append(Table('By stage', ['Stage', 'Claims', 'Value (LSL)', 'Longest wait (days)'],
                             sorted(stages.values(), key=lambda r: order.index(r[0])), chart=(0, 1)))
    data.tables.append(Table('Open claims', ['Claim', 'Project', 'Vendor', 'Milestone', 'Amount (LSL)', 'Waiting for', 'In stage since',
                                             'Days in stage', 'Age', 'Submitted'], rows))
    return data


def build_financial_delivery(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import ContractStatus, TenderContract

    projects = ctx.projects()
    config = PlatformConfiguration.objects.order_by('id').first()
    budget = float(getattr(config, 'national_main_program_budget', 0) or 0)
    contracts = TenderContract.objects.filter(projects__in=projects, status__in=[ContractStatus.APPROVED, ContractStatus.CLOSED]).distinct()
    committed_by_tender: dict = {}
    for contract in contracts.select_related('tender'):
        key = contract.tender.reference_number if contract.tender_id else 'No tender'
        committed_by_tender[key] = committed_by_tender.get(key, 0.0) + float(contract.resolved_award_value())
    claims = list(_scoped_claims(ctx))
    totals = _claim_totals(claims)
    committed = sum(committed_by_tender.values())
    by_tender: dict = {}
    for claim in claims:
        tender = claim.project.tender.reference_number if claim.project.tender_id else 'No tender'
        e = by_tender.setdefault(tender, [tender, committed_by_tender.get(tender, 0.0), 0.0, 0.0])
        e[2] += float(claim.claim_amount or 0)
        if claim.status in claim_status.PAID:
            e[3] += float(claim.claim_amount or 0)
    for tender, value in committed_by_tender.items():
        by_tender.setdefault(tender, [tender, value, 0.0, 0.0])
    tech: dict = {}
    for claim in claims:
        e = tech.setdefault(claim.project.tech_type or 'Unknown', [claim.project.tech_type or 'Unknown', 0.0, 0.0])
        e[1] += float(claim.claim_amount or 0)
        if claim.status in claim_status.PAID:
            e[2] += float(claim.claim_amount or 0)
    data = ReportData(title='Financial Delivery Report')
    data.summary = [
        ('Programme budget', _money(budget) if budget else 'Not set'),
        ('Committed (approved contracts)', _money(committed)),
        ('Claimed in period', _money(totals['claimed'])), ('Paid in period', _money(totals['paid'])),
        ('Approved, awaiting payment', _money(totals['awaiting'])),
        ('Budget remaining after commitments', _money(budget - committed) if budget else 'Not set'),
    ]
    data.tables.append(Table('By tender', ['Tender', 'Committed (LSL)', 'Claimed in period (LSL)', 'Paid in period (LSL)'],
                             sorted(by_tender.values(), key=lambda r: -r[1]), chart=(0, 1)))
    data.tables.append(Table('By technology', ['Technology', 'Claimed in period (LSL)', 'Paid in period (LSL)'], list(tech.values())))
    data.tables.append(Table('Payment claims', CLAIM_COLUMNS, _claim_rows(claims)))
    return data


# ---------------------------------------------------------------------------------------
# PSC
# ---------------------------------------------------------------------------------------

def build_psc_briefing(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import Tender, TenderStatus

    projects = ctx.projects()
    claims = list(_scoped_claims(ctx))
    totals = _claim_totals(claims)
    verified = InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED)
    inclusion = _inclusion_row('', verified)
    awaiting_psc = [c for c in claims if c.status == PaymentClaimStatus.TAC_ENDORSED]
    open_issues = OversightReview.objects.filter(
        project__in=projects, review_status__in=['flagged', 'delayed'], follow_up_status__in=['open', 'in_progress'],
    ).select_related('project', 'reviewer').order_by('-created_at')
    findings = AuditCase.objects.filter(status__in=['management_response', 'finalized'], risk_level__in=['major', 'critical']).select_related('project')
    tenders = Tender.objects.filter(status__in=[TenderStatus.STANDSTILL, TenderStatus.DISPUTED, TenderStatus.EVALUATION]).order_by('-updated_at')
    data = ReportData(title='PSC Briefing')
    data.summary = [
        ('Active projects', projects.filter(status=ProjectStatus.ACTIVE).count()),
        ('Verified installations to date', inclusion[1]),
        ('Female-headed share', f'{inclusion[2]:.1f}%'),
        ('Paid in period', _money(totals['paid'])),
        ('Claims awaiting PSC approval', f'{len(awaiting_psc)} ({_money(sum(float(c.claim_amount or 0) for c in awaiting_psc))})'),
        ('Open flagged or delayed issues', open_issues.count()),
        ('Open major or critical audit findings', findings.count()),
    ]
    data.tables.append(Table('Decisions needed: claims awaiting PSC approval', ['Claim', 'Project', 'Vendor', 'Milestone', 'Amount (LSL)', 'TAC endorsed'], [
        [c.id, c.project.project_reference or c.project_id, c.project.vendor_name, f'M{c.milestone.milestone_number}' if c.milestone_id else '',
         float(c.claim_amount or 0), _d(c.approved_at)] for c in awaiting_psc
    ]))
    rows, configured = results_rows(ctx)
    data.tables.append(Table('Results against targets', RESULTS_COLUMNS, rows))
    data.tables.append(Table('Open risks and issues', ['Project', 'Subject', 'Status', 'Raised by', 'Raised', 'Follow-up', 'Due', 'Comment'], [
        [r.project.project_reference if r.project_id else '', r.get_subject_type_display(), r.get_review_status_display(),
         f'{_user_name(r.reviewer)} ({r.reviewer_role})', _d(r.created_at), r.get_follow_up_status_display(), _d(r.follow_up_date), r.comment]
        for r in open_issues
    ]))
    data.tables.append(Table('Major and critical audit findings', ['Reference', 'Title', 'Risk', 'Status', 'Corrective action', 'Due'], [
        [c.reference, c.title, c.get_risk_level_display(), c.get_status_display(), c.get_corrective_action_status_display(), _d(c.corrective_action_due)]
        for c in findings
    ]))
    data.tables.append(Table('Procurement in progress', ['Tender', 'Name', 'Status', 'Deadline'], [
        [t.reference_number, t.name, t.status, _d(t.deadline)] for t in tenders
    ]))
    if not configured:
        data.notes.append('Results are listed without targets because no results framework has been entered yet.')
    return data


# ---------------------------------------------------------------------------------------
# TAC
# ---------------------------------------------------------------------------------------

def build_technical_performance(ctx: ReportContext) -> ReportData:
    projects = list(ctx.projects())
    readings = ctx.in_period(SmartMeterReading.objects.filter(project__in=projects), 'recorded_at')
    stats = {
        row['project_id']: row for row in readings.values('project_id').annotate(
            kwh=Sum('kwh'), uptime=Avg('uptime_pct'), n=Count('id'), last=Max('recorded_at'), meters=Count('meter_id', distinct=True),
        )
    }
    anomalies = dict(AnomalyFlag.objects.filter(project__in=projects, is_resolved=False).values('project_id').annotate(n=Count('id')).values_list('project_id', 'n'))
    batches = dict(MeterDataBatch.objects.filter(project__in=projects, status__in=['flagged', 'correction_requested']).values('project_id').annotate(n=Count('id')).values_list('project_id', 'n'))
    rows = []
    for p in projects:
        s = stats.get(p.id, {})
        uptime = round(float(s['uptime']), 1) if s.get('uptime') is not None else ''
        rows.append([p.project_reference or p.id, p.vendor_name, p.tech_type, p.device_tech_tier, s.get('meters', 0), s.get('n', 0),
                     round(float(s.get('kwh') or 0), 1), float(p.energy_output_target_kwh or 0), uptime,
                     'Below 95%' if uptime != '' and uptime < 95 else ('OK' if uptime != '' else 'No data'),
                     _d(s.get('last')), batches.get(p.id, 0), anomalies.get(p.id, 0)])
    with_data = [r for r in rows if r[8] != '']
    data = ReportData(title='Technical Performance Report')
    data.summary = [
        ('Projects', len(rows)), ('Reporting meter data', len(with_data)),
        ('Average uptime', f"{sum(r[8] for r in with_data) / len(with_data):.1f}%" if with_data else 'No data'),
        ('Below 95% uptime', sum(1 for r in rows if r[9] == 'Below 95%')),
        ('Energy delivered', f"{sum(r[6] for r in rows):,.1f} kWh"),
    ]
    data.tables.append(Table('By project', ['Project', 'Vendor', 'Technology', 'Tier', 'Meters reporting', 'Readings', 'kWh in period',
                                            'Energy target (kWh)', 'Average uptime %', 'Uptime check', 'Last reading',
                                            'Meter batches needing review', 'Open anomalies'], rows, chart=(0, 6)))
    return data


def build_claims_awaiting_endorsement(ctx: ReportContext) -> ReportData:
    claims = [c for c in _scoped_claims(ctx) if c.status in {PaymentClaimStatus.RMT_APPROVED, PaymentClaimStatus.LEGACY_VERIFIED}]
    now = timezone.now()
    rows = []
    for c in claims:
        p = c.project
        target = p.target_installations or p.installation_target or 0
        verified = InstallationReport.objects.filter(project=p, status=InstallationStatus.VERIFIED).count()
        visits = FieldVerification.objects.filter(installation__project=p)
        failed = visits.exclude(verification_status=FieldVerificationStatus.VERIFIED).count()
        required = c.milestone.required_installation_pct if c.milestone_id else 0
        share = _pct(verified, target) if target else 0
        rows.append([c.id, p.project_reference or p.id, p.vendor_name, f'M{c.milestone.milestone_number}' if c.milestone_id else '',
                     float(c.claim_amount or 0), required, share, 'Met' if share >= required else 'Not met',
                     _pct(failed, visits.count()), AnomalyFlag.objects.filter(project=p, is_resolved=False).count(),
                     _d(c.verified_at), (now - (c.verified_at or c.submitted_at)).days])
    data = ReportData(title='Claims Awaiting TAC Endorsement')
    data.summary = [('Claims waiting', len(rows)), ('Value', _money(sum(r[4] for r in rows))),
                    ('Installation condition not met', sum(1 for r in rows if r[7] == 'Not met'))]
    data.tables.append(Table('Claims', ['Claim', 'Project', 'Vendor', 'Milestone', 'Amount (LSL)', 'Required verified %', 'Verified % now',
                                        'Condition', 'Failed visit %', 'Open anomalies', 'RMT approved', 'Days waiting'], rows))
    return data


# ---------------------------------------------------------------------------------------
# DoE, field verifiers, vendors
# ---------------------------------------------------------------------------------------

def build_monitoring_visits(ctx: ReportContext) -> ReportData:
    visits = SiteMonitoringVisit.objects.filter(project__in=ctx.projects()).select_related('project', 'installation', 'visited_by')
    if ctx.date_from:
        visits = visits.filter(visit_date__gte=ctx.date_from)
    if ctx.date_to:
        visits = visits.filter(visit_date__lte=ctx.date_to)
    visits = list(visits.order_by('-visit_date'))
    by_project = Counter(v.project.project_reference or v.project_id for v in visits)
    data = ReportData(title='Monitoring Visit Report')
    data.details = [('Scope', ctx.scope_label())]
    data.summary = [
        ('Visits', len(visits)), ('Projects visited', len(by_project)),
        ('System not working', sum(1 for v in visits if v.system_working is False)),
        ('Follow-ups open', sum(1 for v in visits if v.follow_up_status in {'open', 'in_progress'})),
    ]
    data.tables.append(Table('Visits by project', ['Project', 'Visits'], [[k, v] for k, v in by_project.most_common()], chart=(0, 1)))
    yes_no = lambda value: '' if value is None else ('Yes' if value else 'No')  # noqa: E731
    data.tables.append(Table('Visits', ['Date', 'Project', 'Installation serial', 'Officer', 'System working', 'Beneficiary present',
                                        'Observations', 'Follow-up action', 'Follow-up status'], [
        [_d(v.visit_date), v.project.project_reference or v.project_id, v.installation.serial_number if v.installation_id else '',
         _user_name(v.visited_by), yes_no(v.system_working), yes_no(v.beneficiary_present), v.observations, v.follow_up_action,
         v.get_follow_up_status_display()] for v in visits
    ]))
    return data


def build_route_list(ctx: ReportContext) -> ReportData:
    tasks = VerificationTask.objects.filter(field_verifier_task_scope_filter(ctx.user)).filter(
        status__in=['Pending', 'Partial', 'Reverification Required'],
    ).select_related('report__project').distinct()
    rows = sorted([
        [t.report.district or t.report.project.district, t.report.project.project_reference or t.report.project_id, t.report.serial_number,
         t.report.beneficiary_name, t.report.beneficiary_phone, float(t.report.gps_lat), float(t.report.gps_lng), t.report.household_type,
         t.status, t.verification_round, t.reverification_reason, _d(t.report.submitted_at),
         'Assigned to you' if t.assigned_verifier_id == ctx.user.id else 'In your area']
        for t in tasks
    ], key=lambda r: (str(r[0]), str(r[1]), str(r[2])))
    data = ReportData(title='Assignment and Route List')
    data.details = [('Verifier', _user_name(ctx.user))]
    data.summary = [('Visits to make', len(rows)), ('Re-verifications', sum(1 for r in rows if r[8] == 'Reverification Required')),
                    ('Districts', len({r[0] for r in rows}))]
    data.tables.append(Table('Visits by district', ['District', 'Visits'], [[k, v] for k, v in Counter(r[0] for r in rows).most_common()]))
    data.tables.append(Table('Visits', ['District', 'Project', 'Installation serial', 'Beneficiary', 'Phone', 'Latitude', 'Longitude',
                                        'Household type', 'Status', 'Round', 'Re-verification reason', 'Reported', 'Assignment'],
                             rows, pii={'Beneficiary': 'identity', 'Phone': 'identity', 'Latitude': 'gps', 'Longitude': 'gps'}))
    return data


def build_vendor_claim_statement(ctx: ReportContext) -> ReportData:
    claims = list(_scoped_claims(ctx))
    totals = _claim_totals(claims)
    data = ReportData(title='Claim Statement')
    data.summary = [('Claims', len(claims)), ('Claimed', _money(totals['claimed'])), ('Paid', _money(totals['paid'])),
                    ('Approved, awaiting payment', _money(totals['awaiting'])), ('In review', _money(totals['review'])),
                    ('Rejected', _money(totals['rejected']))]
    rows = _claim_rows(claims)
    for row, claim in zip(rows, claims):
        row.append(claim.remarks or '')
    data.tables.append(Table('Claims', CLAIM_COLUMNS + ['Reviewer remarks'], rows))
    return data


def build_vendor_installations(ctx: ReportContext) -> ReportData:
    installs = ctx.in_period(InstallationReport.objects.filter(project__in=ctx.projects()).select_related('project'), 'submitted_at')
    latest = {}
    for fv in FieldVerification.objects.filter(installation__in=installs).order_by('installation_id', '-verified_at'):
        latest.setdefault(fv.installation_id, fv)
    rounds = dict(VerificationTask.objects.filter(report__in=installs).values_list('report_id', 'verification_round'))
    rows = []
    for i in installs.order_by('-submitted_at'):
        fv = latest.get(i.id)
        rows.append([i.serial_number, i.project.project_reference or i.project_id, i.district, _d(i.submitted_at), i.status,
                     fv.get_verification_status_display() if fv else 'Not yet visited', rounds.get(i.id, ''),
                     round(float(fv.location_distance_meters or 0), 1) if fv else '', fv.flag_reason if fv else ''])
    data = ReportData(title='Installation and Verification Status')
    data.summary = [('Installations', len(rows)), ('Verified', sum(1 for r in rows if r[4] == InstallationStatus.VERIFIED)),
                    ('Flagged', sum(1 for r in rows if r[4] == InstallationStatus.FLAGGED)),
                    ('Not yet visited', sum(1 for r in rows if r[5] == 'Not yet visited'))]
    data.tables.append(Table('Installations', ['Installation serial', 'Project', 'District', 'Reported', 'Status', 'Latest verification',
                                               'Round', 'GPS distance (m)', 'Flag reason'], rows))
    return data
