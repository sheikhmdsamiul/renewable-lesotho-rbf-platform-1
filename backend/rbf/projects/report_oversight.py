"""Oversight, programme-board and impact reports: follow-ups, risks, decisions, vendor scorecards,
inclusion oversight, regional impact, budget utilisation, annual results and national access
figures, plus the vendor's own compliance notices."""
from __future__ import annotations

from collections import Counter, defaultdict

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from rbf.users.models import PlatformConfiguration, UserRole as R

from . import claim_status
from .models import (
    AnomalyFlag,
    AnomalyFlagStatus,
    AuditCase,
    AuditCaseStatus,
    AuditLog,
    CorrectiveActionStatus,
    FieldVerification,
    FieldVerificationStatus,
    InstallationReport,
    InstallationStatus,
    MeterDataBatch,
    OversightFollowUpStatus,
    OversightReview,
    OversightReviewStatus,
    PaymentClaim,
    PaymentClaimStatus,
    SiteMonitoringVisit,
    SiteVisitFollowUpStatus,
    SmartMeterReading,
)
from .report_engine import inclusion_targets, project_inclusion_targets, ReportContext, ReportData, Table, _d, _inclusion_row, _money, _pct, _user_name
from .report_programme import RESULTS_COLUMNS, results_rows

NATIONAL_ROLES = {R.RBF_OFFICIAL, R.ADMIN, R.UNDP_DONOR, R.AUDITOR, R.TAC}
SHARED_AUDIT_STATUSES = [AuditCaseStatus.MANAGEMENT_RESPONSE, AuditCaseStatus.FINALIZED, AuditCaseStatus.CLOSED]
OPEN_FOLLOW_UP = [OversightFollowUpStatus.OPEN, OversightFollowUpStatus.IN_PROGRESS]


def _days_since(value) -> int | str:
    if not value:
        return ''
    if hasattr(value, 'tzinfo'):
        return (timezone.now() - value).days
    return (timezone.localdate() - value).days


def _overdue(due) -> str:
    return 'Overdue' if due and due < timezone.localdate() else ''


def _reviews(ctx: ReportContext):
    """Oversight reviews on projects in scope; vendor-level reviews only for national roles."""
    q = Q(project__in=ctx.projects())
    if ctx.role in NATIONAL_ROLES and not (ctx.district or ctx.project_id):
        q |= Q(project__isnull=True)
    return OversightReview.objects.filter(q).select_related('project', 'reviewer', 'vendor')


def _shared_audit_cases(ctx: ReportContext):
    if ctx.role not in NATIONAL_ROLES - {R.TAC}:
        return AuditCase.objects.none()
    q = Q(project__in=ctx.projects()) | Q(project__isnull=True)
    return AuditCase.objects.filter(q, status__in=SHARED_AUDIT_STATUSES).select_related('project', 'vendor')


# ---------------------------------------------------------------------------------------
# Follow-ups, risks and decisions
# ---------------------------------------------------------------------------------------

def build_followup_tracker(ctx: ReportContext) -> ReportData:
    rows = []
    for r in _reviews(ctx).filter(follow_up_status__in=OPEN_FOLLOW_UP).order_by('follow_up_date', 'created_at'):
        rows.append(['Oversight review', f'OR-{r.id}', r.project.project_reference if r.project_id else (r.vendor.organization_name if r.vendor_id else ''),
                     f'{r.get_subject_type_display()}: {r.get_review_status_display()}', r.action_required or r.comment,
                     f'{_user_name(r.reviewer)} ({r.reviewer_role})', r.get_follow_up_status_display(), _d(r.follow_up_date),
                     _days_since(r.created_at), _overdue(r.follow_up_date)])
    visits = SiteMonitoringVisit.objects.filter(
        project__in=ctx.projects(), follow_up_status__in=[SiteVisitFollowUpStatus.OPEN, SiteVisitFollowUpStatus.IN_PROGRESS],
    ).select_related('project', 'visited_by')
    for v in visits.order_by('visit_date'):
        rows.append(['Monitoring visit', f'MV-{v.id}', v.project.project_reference or v.project_id, v.observations[:200], v.follow_up_action,
                     _user_name(v.visited_by), v.get_follow_up_status_display(), '', _days_since(v.visit_date), ''])
    for c in _shared_audit_cases(ctx).filter(corrective_action_status__in=[CorrectiveActionStatus.OPEN, CorrectiveActionStatus.IN_PROGRESS]):
        rows.append(['Audit corrective action', c.reference, c.project.project_reference if c.project_id else '',
                     f'{c.title} ({c.get_risk_level_display() or "risk not rated"})', c.corrective_action, c.corrective_action_owner,
                     c.get_corrective_action_status_display(), _d(c.corrective_action_due), _days_since(c.finding_recorded_at or c.created_at),
                     _overdue(c.corrective_action_due)])
    data = ReportData(title='Oversight and Audit Follow-up Tracker')
    data.details = [('Scope', ctx.scope_label())]
    kinds = Counter(r[0] for r in rows)
    data.summary = [('Open follow-ups', len(rows)), ('Overdue', sum(1 for r in rows if r[9])),
                    *[(k, n) for k, n in kinds.most_common()]]
    data.tables.append(Table('Open follow-ups', ['Source', 'Reference', 'Project or vendor', 'Issue', 'Action required', 'Owner', 'Status',
                                                 'Due', 'Age (days)', 'Overdue'], rows))
    if ctx.role not in NATIONAL_ROLES:
        data.notes.append('Audit corrective actions are not included for your role.')
    data.notes.append('This tracker shows what is open now; it is not limited to a period.')
    return data


def build_risk_log(ctx: ReportContext) -> ReportData:
    rows = []
    reviews = ctx.in_period(_reviews(ctx).filter(review_status__in=[OversightReviewStatus.FLAGGED, OversightReviewStatus.DELAYED]), 'created_at')
    for r in reviews.order_by('-created_at'):
        rows.append(['Oversight', r.get_review_status_display(), r.project.project_reference if r.project_id else '', r.issue_category or r.get_subject_type_display(),
                     r.comment, r.get_follow_up_status_display(), _d(r.created_at)])
    for c in ctx.in_period(_shared_audit_cases(ctx).filter(risk_level__in=['major', 'critical']), 'finding_recorded_at'):
        rows.append(['Audit finding', c.get_risk_level_display(), c.project.project_reference if c.project_id else '', c.get_audit_area_display(),
                     c.finding or c.title, c.get_corrective_action_status_display(), _d(c.finding_recorded_at)])
    anomalies = ctx.in_period(AnomalyFlag.objects.filter(project__in=ctx.projects(), is_resolved=False, severity__in=['high', 'critical']), 'created_at')
    for a in anomalies.select_related('project'):
        rows.append(['Anomaly', a.get_severity_display(), a.project.project_reference or a.project_id, a.flag_type, a.description, a.get_status_display(), _d(a.created_at)])
    for c in PaymentClaim.objects.filter(project__in=ctx.projects(), status=PaymentClaimStatus.HELD_AUDIT).select_related('project'):
        rows.append(['Claim held for audit', 'High', c.project.project_reference or c.project_id, f'Claim {c.id}', _money(c.claim_amount), 'Held', _d(c.submitted_at)])
    if ctx.role in NATIONAL_ROLES and not ctx.district:
        from rbf.tenders.models import TenderChallenge

        for ch in TenderChallenge.objects.filter(resolved_at__isnull=True, withdrawn_at__isnull=True, filed_at__isnull=False).select_related('tender'):
            rows.append(['Procurement challenge', 'High' if ch.priority == 'urgent' else 'Medium', ch.tender.reference_number,
                         ch.get_category_display(), ch.grounds[:300], ch.get_status_display(), _d(ch.filed_at)])
    data = ReportData(title='Risk and Issue Log')
    data.summary = [('Risks and issues', len(rows)), *Counter(r[0] for r in rows).most_common()]
    data.tables.append(Table('By source', ['Source', 'Items'], Counter(r[0] for r in rows).most_common(), chart=(0, 1)))
    data.tables.append(Table('Risks and issues', ['Source', 'Rating', 'Project or tender', 'Category', 'Description', 'Status', 'Raised'], rows))
    data.notes.append('Oversight items, audit findings and anomalies are those raised in the period; claims held for audit and open '
                      'procurement challenges are listed whatever their date.')
    return data


def build_decisions_log(ctx: ReportContext) -> ReportData:
    decisions = ctx.in_period(AuditLog.objects.filter(actor_role=R.UNDP_DONOR).select_related('actor'), 'created_at').order_by('-created_at')
    # Decisions only: sign-ins, views and report activity are not decisions.
    decisions = decisions.exclude(action__in=['login_succeeded', 'report_downloaded', 'report_generated']).exclude(action__contains='viewed')
    decisions = decisions.exclude(action__startswith='report_')
    directives = ctx.in_period(_reviews(ctx).filter(reviewer_role=R.UNDP_DONOR), 'created_at').order_by('-created_at')
    data = ReportData(title='Decisions and Actions Log')
    data.summary = [('PSC decisions recorded', decisions.count()), ('PSC directives', directives.count()),
                    ('Directives still open', directives.filter(follow_up_status__in=OPEN_FOLLOW_UP).count())]
    data.tables.append(Table('Directives and follow-up', ['Date', 'Member', 'Subject', 'Project', 'Review', 'Action required', 'Follow-up',
                                                          'Due', 'Resolved', 'Resolution'], [
        [_d(r.created_at), _user_name(r.reviewer), r.get_subject_type_display(), r.project.project_reference if r.project_id else '',
         r.get_review_status_display(), r.action_required or r.comment, r.get_follow_up_status_display(), _d(r.follow_up_date),
         _d(r.resolved_at), r.resolution_note]
        for r in directives
    ]))
    data.tables.append(Table('Decisions', ['Date', 'Member', 'Action', 'Record', 'From', 'To', 'Notes'], [
        [_d(log.created_at), _user_name(log.actor) if log.actor_id else 'System', log.action.replace('_', ' '),
         f'{log.entity_type}#{log.entity_id}' if log.entity_id else log.entity_type, log.old_status, log.new_status, log.notes]
        for log in decisions
    ]))
    data.notes.append('Decisions are the actions PSC members recorded on the platform (for example claim approvals). '
                      'Meeting minutes held outside the platform are not included.')
    return data


# ---------------------------------------------------------------------------------------
# Vendors and inclusion
# ---------------------------------------------------------------------------------------

SCORE_WEIGHTS = {'delivery': 30, 'pass_rate': 25, 'uptime': 20, 'inclusion': 15, 'issues': 10}


def build_vendor_scorecard(ctx: ReportContext) -> ReportData:
    projects = list(ctx.projects())
    by_vendor: dict = defaultdict(list)
    for p in projects:
        by_vendor[p.vendor_id].append(p)
    visits = ctx.in_period(FieldVerification.objects.filter(installation__project__in=projects), 'verified_at')
    visit_stats = {r['installation__project__vendor_id']: r for r in visits.values('installation__project__vendor_id').annotate(
        n=Count('id'), ok=Count('id', filter=Q(verification_status=FieldVerificationStatus.VERIFIED)))}
    readings = ctx.in_period(SmartMeterReading.objects.filter(project__in=projects), 'recorded_at')
    meter = {r['project__vendor_id']: r for r in readings.values('project__vendor_id').annotate(kwh=Sum('kwh'), uptime=Avg('uptime_pct'))}
    rejected = Counter(ctx.in_period(PaymentClaim.objects.filter(project__in=projects, status__in=claim_status.REJECTED), 'submitted_at')
                       .values_list('project__vendor_id', flat=True))
    anomalies = Counter(AnomalyFlag.objects.filter(project__in=projects, is_resolved=False).values_list('project__vendor_id', flat=True))
    follow_ups = Counter(OversightReview.objects.filter(project__in=projects, follow_up_status__in=OPEN_FOLLOW_UP).values_list('project__vendor_id', flat=True))
    female_target = inclusion_targets()['female']
    rows = []
    for vendor_id, vps in by_vendor.items():
        target = sum(p.target_installations or p.installation_target or 0 for p in vps)
        verified_qs = InstallationReport.objects.filter(project__in=vps, status=InstallationStatus.VERIFIED)
        verified = verified_qs.count()
        female = _pct(verified_qs.filter(household_type__icontains='female').count(), verified)
        v = visit_stats.get(vendor_id, {})
        m = meter.get(vendor_id, {})
        delivery = min(_pct(verified, target), 100.0) if target else 0.0
        pass_rate = _pct(v.get('ok', 0), v.get('n', 0))
        uptime = round(float(m['uptime']), 1) if m.get('uptime') is not None else None
        issues = anomalies[vendor_id] + follow_ups[vendor_id] + rejected[vendor_id]
        score = (SCORE_WEIGHTS['delivery'] * delivery / 100 + SCORE_WEIGHTS['pass_rate'] * pass_rate / 100
                 + SCORE_WEIGHTS['uptime'] * (uptime or 0) / 100 + SCORE_WEIGHTS['inclusion'] * (min(female / female_target, 1) if female_target else 1)
                 + SCORE_WEIGHTS['issues'] * max(0.0, 1 - issues / 10))
        rows.append([vps[0].vendor_name, len(vps), target, verified, delivery, v.get('n', 0), pass_rate,
                     uptime if uptime is not None else 'No data', round(float(m.get('kwh') or 0), 1), female,
                     rejected[vendor_id], anomalies[vendor_id], follow_ups[vendor_id], round(score, 1)])
    rows.sort(key=lambda r: -r[-1])
    for i, row in enumerate(rows, start=1):
        row.insert(0, i)
    data = ReportData(title='Vendor Performance Scorecard')
    data.summary = [('Vendors', len(rows)), ('Highest score', rows[0][-1] if rows else '-'),
                    ('Average score', round(sum(r[-1] for r in rows) / len(rows), 1) if rows else '-')]
    data.tables.append(Table('Scorecard', ['Rank', 'Vendor', 'Projects', 'Target installations', 'Verified', 'Delivery %', 'Visits in period',
                                           'Pass rate %', 'Uptime %', 'kWh in period', 'Female-headed %', 'Claims rejected', 'Open anomalies',
                                           'Open follow-ups', 'Score (0-100)'], rows, chart=(1, 14)))
    data.notes.append('Score = delivery (verified / target, 30) + verification pass rate (25) + average uptime (20) + female-headed share '
                      f'against the {female_target}% programme target (15) + 10 less one point per open issue (claims rejected, open anomalies, open follow-ups). '
                      'Delivery, inclusion and open issues are to date; visits, uptime, energy and rejections are for the period. '
                      'The weights are a starting point for the programme team to confirm.')
    return data


def build_gender_oversight(ctx: ReportContext) -> ReportData:
    rows, plans = [], []
    for p in ctx.projects().order_by('vendor_name', 'id'):
        verified = InstallationReport.objects.filter(project=p, status=InstallationStatus.VERIFIED)
        row = _inclusion_row(p.project_reference or str(p.id), verified)
        t = project_inclusion_targets(p)
        targets = (t['female'], t['vulnerable'], t['low_income'])
        below = [name for name, actual, target in zip(('female-headed', 'vulnerable', 'low-income'), row[2:5], targets) if actual < target]
        if row[1] < 20:
            verdict = 'Too few installations to judge'
        elif below:
            verdict = 'Corrective action plan needed'
            plans.append([p.vendor_name, row[0], row[1], ', '.join(below)])
        else:
            verdict = 'On target'
        rows.append([p.vendor_name, row[0], p.tech_type, row[1], row[2], targets[0], row[3], targets[1], row[4], targets[2], verdict])
    data = ReportData(title='Gender KPI Oversight')
    data.summary = [('Projects', len(rows)), ('On target', sum(1 for r in rows if r[10] == 'On target')),
                    ('Corrective action plan needed', len(plans)), ('Too few installations', sum(1 for r in rows if r[10].startswith('Too few')))]
    data.tables.append(Table('Corrective action plans needed', ['Vendor', 'Project', 'Verified installations', 'Below target on'], plans))
    data.tables.append(Table('Inclusion against project targets', ['Vendor', 'Project', 'Technology', 'Verified installations', 'Female-headed %',
                                                                   'Target', 'Vulnerable %', 'Target', 'Low-income %', 'Target', 'Assessment'], rows))
    data.notes.append('Uses every verified installation to date against each project\'s contracted inclusion targets. Projects with fewer '
                      'than 20 verified installations are not judged.')
    return data


# ---------------------------------------------------------------------------------------
# Regional, budget, annual and national figures
# ---------------------------------------------------------------------------------------

def build_regional_impact(ctx: ReportContext) -> ReportData:
    projects = ctx.projects()
    verified_all = InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED)
    verified_period = ctx.in_period(verified_all, 'submitted_at')
    claims = list(PaymentClaim.objects.filter(project__in=projects, status__in=claim_status.PAID).select_related('project'))
    paid_by_district: dict = defaultdict(float)
    for c in claims:
        paid_by_district[c.project.district or c.project.region or 'Unknown'] += float(c.claim_amount or 0)
    budget_by_district: dict = defaultdict(float)
    project_count: Counter = Counter()
    for p in projects:
        key = p.district or p.region or 'Unknown'
        budget_by_district[key] += float(p.budget or 0)
        project_count[key] += 1
    # An installation counts in the district it was captured in, or its project's district if none was recorded.
    def in_district(qs, d):
        return qs.filter(Q(district=d) | Q(district='', project__district=d))

    districts = sorted(set(project_count) | {d for d in verified_all.values_list('district', flat=True) if d})
    rows = []
    for d in districts:
        incl = _inclusion_row(d, in_district(verified_all, d))
        rows.append([d, project_count[d], incl[1], in_district(verified_period, d).count(),
                     incl[2], incl[3], incl[4], budget_by_district[d], paid_by_district[d]])
    tech_rows = []
    for (district, tech), n in Counter(verified_all.values_list('district', 'project__tech_type')).most_common():
        tech_rows.append([district or 'Unknown', tech or 'Unknown', n])
    data = ReportData(title='Regional Impact Report')
    data.details = [('Scope', ctx.scope_label())]
    data.summary = [('Districts', len(rows)), ('Verified installations to date', verified_all.count()),
                    ('Verified in period', verified_period.count()), ('Paid to date', _money(sum(paid_by_district.values())))]
    data.tables.append(Table('By district', ['District', 'Projects', 'Verified to date', 'Verified in period', 'Female-headed %', 'Vulnerable %',
                                             'Low-income %', 'Budget (LSL)', 'Paid to date (LSL)'], rows, chart=(0, 2)))
    data.tables.append(Table('By district and technology', ['District', 'Technology', 'Verified installations'], sorted(tech_rows)))
    data.notes.append('Installations are counted in the district where they were captured. Budget and payments are counted in each '
                      'project\'s primary district.')
    return data


def build_budget_utilisation(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import ContractStatus, TenderContract

    projects = ctx.projects()
    config = PlatformConfiguration.objects.order_by('id').first()
    programme_budget = float(getattr(config, 'national_main_program_budget', 0) or 0)
    contracts = list(TenderContract.objects.filter(projects__in=projects, status__in=[ContractStatus.APPROVED, ContractStatus.CLOSED])
                     .select_related('tender', 'lot').distinct())
    claims = list(PaymentClaim.objects.filter(project__in=projects).select_related('project__tender', 'project__lot'))
    end_claims = [c for c in claims if not ctx.date_to or (c.submitted_at and timezone.localtime(c.submitted_at).date() <= ctx.date_to)]
    rows: dict = {}

    def entry(tender, lot):
        key = (tender.id if tender else None, lot.id if lot else None)
        if key not in rows:
            budget = float((lot.budget if lot else None) or (tender.budget if tender and not lot else 0) or 0)
            rows[key] = [tender.funding_source if tender and tender.funding_source else 'Not stated',
                         tender.reference_number if tender else 'No tender', lot.name if lot else '', budget, 0.0, 0.0, 0.0, 0.0]
        return rows[key]

    for c in contracts:
        entry(c.tender, c.lot)[4] += float(c.resolved_award_value())
    for c in end_claims:
        e = entry(c.project.tender, c.project.lot)
        if c.status in claim_status.PAID:
            e[5] += float(c.claim_amount or 0)
            if not ctx.date_from or (c.submitted_at and timezone.localtime(c.submitted_at).date() >= ctx.date_from):
                e[6] += float(c.claim_amount or 0)
    for e in rows.values():
        e[7] = e[4] - e[5]
    table = sorted(rows.values(), key=lambda r: (r[0], r[1], r[2]))
    funding: dict = {}
    for r in table:
        f = funding.setdefault(r[0], [r[0], 0.0, 0.0, 0.0])
        f[1] += r[4]
        f[2] += r[5]
        f[3] += r[7]
    committed = sum(r[4] for r in table)
    disbursed = sum(r[5] for r in table)
    data = ReportData(title='Budget Utilisation')
    data.summary = [
        ('Programme budget', _money(programme_budget) if programme_budget else 'Not set'),
        ('Committed (approved contracts)', _money(committed)), ('Disbursed to period end', _money(disbursed)),
        ('Committed, not yet disbursed', _money(committed - disbursed)),
        ('Budget committed', f'{_pct(committed, programme_budget):.1f}%' if programme_budget else 'Budget not set'),
        ('Budget disbursed', f'{_pct(disbursed, programme_budget):.1f}%' if programme_budget else 'Budget not set'),
    ]
    data.tables.append(Table('By funding source', ['Funding source', 'Committed (LSL)', 'Disbursed (LSL)', 'Remaining (LSL)'], list(funding.values()), chart=(0, 2)))
    data.tables.append(Table('By tender and lot', ['Funding source', 'Tender', 'Lot', 'Budget (LSL)', 'Committed (LSL)', 'Disbursed to period end (LSL)',
                                                   'Disbursed in period (LSL)', 'Remaining commitment (LSL)'], table))
    data.notes.append('Committed is the award value of approved or closed contracts. Disbursed counts paid claims submitted up to the end '
                      'of the period. Funding source is taken from each tender.')
    return data


def build_annual_report(ctx: ReportContext) -> ReportData:
    rows, configured = results_rows(ctx)
    projects = ctx.projects()
    verified = ctx.in_period(InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED), 'submitted_at')
    verified_all = InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED)
    # Sex of the beneficiary as recorded at the latest field verification.
    sex: dict = {}
    for inst_id, gender in (FieldVerification.objects.filter(installation__in=verified).order_by('installation_id', '-verified_at')
                            .values_list('installation_id', 'beneficiary_gender')):
        if inst_id not in sex:
            sex[inst_id] = gender or 'unknown'
    by_sex = Counter(sex.values())
    claims = list(ctx.in_period(PaymentClaim.objects.filter(project__in=projects), 'submitted_at'))
    paid = sum(float(c.claim_amount or 0) for c in claims if c.status in claim_status.PAID)
    data = ReportData(title='Annual and Final Progress Report')
    data.summary = [
        ('Verified installations in period', verified.count()), ('Verified installations to date', verified_all.count()),
        ('Households reached in period', verified.count()), ('Paid in period', _money(paid)),
        ('Indicators', len(rows)), ('On or above target', sum(1 for r in rows if isinstance(r[8], float) and r[8] >= 100)),
    ]
    if not configured:
        data.notes.append('No results framework has been entered, so indicators are listed without baselines or targets.')
    data.tables.append(Table('Results framework', RESULTS_COLUMNS, rows, chart=(1, 8) if configured else None))
    data.tables.append(Table('Households reached by sex of beneficiary (period)', ['Sex', 'Households'], [
        [label, by_sex.get(key, 0)] for key, label in (('female', 'Female'), ('male', 'Male'), ('other', 'Other'), ('unknown', 'Not recorded'))
    ] + [['Not verified in the field', verified.count() - len(sex)]]))
    data.tables.append(Table('By household or site type (period)', ['Household or site type', 'Installations'],
                             Counter(t or 'Not recorded' for t in verified.values_list('household_type', flat=True)).most_common()))
    cols = ['Group', 'Verified installations', 'Female-headed %', 'Vulnerable %', 'Low-income %']
    data.tables.append(Table('By technology (period)', cols, [
        _inclusion_row(t, verified.filter(project__tech_type=t)) for t in sorted({t for t in verified.values_list('project__tech_type', flat=True) if t})
    ], chart=(0, 1)))
    data.tables.append(Table('By district (period)', cols, [
        _inclusion_row(d, verified.filter(district=d)) for d in sorted({d for d in verified.values_list('district', flat=True) if d})
    ]))
    data.notes.append('People reached and CO2e avoided are not calculated until the programme confirms the household size per district and '
                      'the emission factors to use. Schools, clinics and productive uses appear under household or site type as vendors record them. '
                      'Sex of beneficiary is as recorded by the field verifier.')
    return data


def build_national_access(ctx: ReportContext) -> ReportData:
    projects = ctx.projects()
    verified_all = InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED)
    verified_period = ctx.in_period(verified_all, 'submitted_at')
    rows = []
    for (district, tech), n in sorted(Counter(verified_all.values_list('district', 'project__tech_type')).items(), key=lambda kv: (kv[0][0] or '', kv[0][1] or '')):
        in_period = verified_period.filter(district=district, project__tech_type=tech).count()
        rows.append([district or 'Unknown', tech or 'Unknown', n, in_period])
    by_tech = Counter(verified_all.values_list('project__tech_type', flat=True))
    data = ReportData(title='National Access Statistics')
    data.details = [('Scope', ctx.scope_label())]
    data.summary = [('Households with new access to date', verified_all.count()), ('In period', verified_period.count()),
                    *[(f'{t or "Unknown"} to date', n) for t, n in by_tech.most_common()]]
    data.tables.append(Table('Programme contribution by technology', ['Technology', 'Verified installations to date'],
                             [[t or 'Unknown', n] for t, n in by_tech.most_common()], chart=(0, 1)))
    data.tables.append(Table('By district and technology', ['District', 'Technology', 'Verified to date', 'Verified in period'], rows))
    data.notes.append('These are the programme\'s verified connections, to be added to the national SDG 7 access figures. National '
                      'household totals are not held on the platform, so access rates are not calculated here.')
    return data


# ---------------------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------------------

def build_vendor_compliance(ctx: ReportContext) -> ReportData:
    projects = ctx.projects()
    open_anomaly = [AnomalyFlagStatus.OPEN, AnomalyFlagStatus.UNDER_INVESTIGATION, AnomalyFlagStatus.CORRECTION_REQUESTED,
                    AnomalyFlagStatus.AWAITING_EVIDENCE, AnomalyFlagStatus.ESCALATED, AnomalyFlagStatus.REOPENED]
    anomalies = (AnomalyFlag.objects.filter(project__in=projects, status__in=open_anomaly).select_related('project', 'installation')
                 .order_by('due_date', '-created_at'))
    batches = MeterDataBatch.objects.filter(project__in=projects, status__in=['flagged', 'correction_requested']).select_related('project')
    claims = ctx.in_period(PaymentClaim.objects.filter(project__in=projects, status__in=claim_status.REJECTED), 'submitted_at').select_related('project')
    gender = build_gender_oversight(ctx)
    plans = gender.tables[0].rows
    cases = ctx.user.blacklist_cases.exclude(status='Rejected').order_by('-initiated_at') if hasattr(ctx.user, 'blacklist_cases') else []
    data = ReportData(title='Compliance Notices and Corrective Actions')
    data.summary = [('Open anomalies', anomalies.count()), ('Meter batches to correct', batches.count()),
                    ('Inclusion plans needed', len(plans)), ('Claims returned in period', claims.count())]
    data.tables.append(Table('Anomalies to resolve', ['Project', 'Installation serial', 'Type', 'Severity', 'Status', 'Corrective action', 'Due', 'Raised'], [
        [a.project.project_reference or a.project_id, a.installation.serial_number if a.installation_id else '', a.flag_type, a.get_severity_display(),
         a.get_status_display(), a.corrective_action, _d(a.due_date), _d(a.created_at)]
        for a in anomalies
    ]))
    data.tables.append(Table('Meter data to correct', ['Project', 'File', 'Status', 'Findings', 'Reviewer notes', 'Correction due'], [
        [b.project.project_reference or b.project_id, b.file_name, b.get_status_display(), len(b.integrity_findings or []), b.review_notes, _d(b.correction_due_date)]
        for b in batches
    ]))
    data.tables.append(Table('Inclusion corrective action plans', ['Vendor', 'Project', 'Verified installations', 'Below target on'], plans))
    data.tables.append(Table('Claims returned', ['Claim', 'Project', 'Amount (LSL)', 'Status', 'Submitted'], [
        [c.id, c.project.project_reference or c.project_id, float(c.claim_amount or 0), c.status, _d(c.submitted_at)] for c in claims
    ]))
    if cases:
        data.tables.append(Table('Blacklisting notices', ['Case', 'Reason', 'Status', 'Notice sent', 'Until'], [
            [c.id, c.reason, c.status, _d(c.notice_sent_at), 'Permanent' if c.is_permanent else _d(c.expiry_date)] for c in cases
        ]))
    return data
