"""Procurement reports: the procurement pack, PSC oversight summary, evaluation reports and the
procurement compliance audit. Built read-only from tender, bid, evaluation, award, challenge,
contract and debarment records."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from .report_engine import ReportContext, ReportData, Table, _d, _money, _pct, _user_name

POST_EVALUATION = {'Evaluation', 'Standstill', 'Disputed', 'Awarded', 'Closed'}
AWARDED = {'Awarded', 'Closed'}


def _period_bounds(ctx: ReportContext):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(ctx.date_from, time.min), tz) if ctx.date_from else None
    end = timezone.make_aware(datetime.combine(ctx.date_to + timedelta(days=1), time.min), tz) if ctx.date_to else None
    return start, end


def active_tenders(ctx: ReportContext):
    """Tenders open at any time in the period: created before it ended and not closed before it began."""
    qs = ctx.tenders()
    start, end = _period_bounds(ctx)
    if end:
        qs = qs.filter(created_at__lt=end)
    if start:
        qs = qs.filter(Q(closed_at__isnull=True) | Q(closed_at__gte=start))
    return qs


def _submitted_bids(tender):
    from rbf.tenders.models import BidStatus

    return tender.bids.exclude(status__in=[BidStatus.DRAFT, BidStatus.WITHDRAWN])


def _awarded_label(tender) -> str:
    lots = list(tender.lots.all())
    if lots:
        awarded = [f'{lot.name}: {lot.awarded_vendor_name}' for lot in lots if lot.awarded_vendor_name]
        return '; '.join(awarded)
    return tender.awarded_vendor_name or ''


def _tender_rows(tenders) -> list[list]:
    rows = []
    for t in tenders:
        bids = _submitted_bids(t)
        rows.append([
            t.reference_number, t.name, t.procurement_method or '', ', '.join(t.technology_types or []), t.status,
            float(t.budget or 0), _d(t.published_at), _d(t.deadline), bids.count(), t.lots.count(), _awarded_label(t), _d(t.awarded_at),
        ])
    return rows


TENDER_COLUMNS = ['Tender', 'Name', 'Method', 'Technologies', 'Status', 'Budget (LSL)', 'Published', 'Deadline', 'Bids', 'Lots', 'Awarded to', 'Awarded']


def _contract_rows(contracts) -> list[list]:
    return [
        [c.reference_number, c.tender.reference_number, c.lot.name if c.lot_id else '', c.vendor_name, c.status,
         float(c.resolved_award_value()), _d(c.generated_at), _d(c.signed_at), _d(c.approved_at), _d(c.closed_at), c.project_id or '']
        for c in contracts
    ]


CONTRACT_COLUMNS = ['Contract', 'Tender', 'Lot', 'Vendor', 'Status', 'Award value (LSL)', 'Generated', 'Signed', 'Approved', 'Closed', 'Project']


def _challenge_rows(challenges) -> list[list]:
    now = timezone.now()
    rows = []
    for c in challenges:
        end = c.resolved_at or c.withdrawn_at or now
        days = (end - c.filed_at).days if c.filed_at else ''
        rows.append([c.id, c.tender.reference_number, c.filed_by_vendor_name, c.get_category_display(), c.get_status_display(),
                     c.priority, _d(c.filed_at), _d(c.response_deadline), _d(c.resolved_at), days, c.resolution_notes or ''])
    return rows


CHALLENGE_COLUMNS = ['Challenge', 'Tender', 'Filed by', 'Grounds', 'Status', 'Priority', 'Filed', 'Response due', 'Resolved', 'Days open', 'Resolution']


def _challenges(tenders):
    from rbf.tenders.models import ChallengeStatus, TenderChallenge

    return (TenderChallenge.objects.filter(tender__in=tenders).exclude(status=ChallengeStatus.DRAFT)
            .select_related('tender').order_by('-filed_at'))


def build_procurement_pack(ctx: ReportContext) -> ReportData:
    from rbf.projects.models import Project
    from rbf.tenders.models import TenderContract
    from rbf.users.models import VendorBlacklistCase

    tenders = list(active_tenders(ctx).prefetch_related('lots'))
    contracts = list(TenderContract.objects.filter(tender__in=tenders).select_related('tender', 'lot', 'bid').order_by('tender_id', 'id'))
    challenges = list(_challenges(tenders))
    data = ReportData(title='Procurement Pack')
    award_value = sum(float(c.resolved_award_value()) for c in contracts if c.status != 'Rejected')
    data.summary = [
        ('Tenders', len(tenders)), ('Awarded or closed', sum(1 for t in tenders if t.status in AWARDED)),
        ('Contracts', len(contracts)), ('Contracted value', _money(award_value)),
        ('Challenges', len(challenges)), ('Challenges open', sum(1 for c in challenges if not (c.resolved_at or c.withdrawn_at))),
    ]
    data.tables.append(Table('Tender summary', TENDER_COLUMNS, _tender_rows(tenders)))
    by_tech: dict = {}
    for t in tenders:
        for key in (t.technology_types or ['Not stated']):
            e = by_tech.setdefault(key, [key, 0, 0])
            e[1] += 1
            e[2] += int(t.status in AWARDED)
    data.tables.append(Table('Tenders by technology', ['Technology', 'Tenders', 'Awarded'], sorted(by_tech.values(), key=lambda r: -r[1]), chart=(0, 1)))
    plan = []
    for t in tenders:
        t_contracts = [c for c in contracts if c.tender_id == t.id and c.status != 'Rejected']
        value = sum(float(c.resolved_award_value()) for c in t_contracts)
        installs = sum(p.target_installations or 0 for p in Project.objects.filter(tender=t))
        plan.append([t.reference_number, float(t.budget or 0), t.approximate_installation_target or 0, len(t_contracts), value,
                     installs, _pct(value, float(t.budget or 0)) if t.budget else ''])
    data.tables.append(Table('Plan against award', ['Tender', 'Budget (LSL)', 'Planned installations', 'Contracts', 'Award value (LSL)',
                                                    'Contracted installations', 'Budget awarded %'], plan))
    data.tables.append(Table('Contract register', CONTRACT_COLUMNS, _contract_rows(contracts)))
    data.tables.append(Table('Challenges log', CHALLENGE_COLUMNS, _challenge_rows(challenges)))
    cases = VendorBlacklistCase.objects.select_related('vendor').order_by('-initiated_at')
    data.tables.append(Table('Debarment register', ['Case', 'Vendor', 'Reason', 'Status', 'Initiated', 'Confirmed', 'Until', 'Reinstated'], [
        [c.id, c.vendor.organization_name or _user_name(c.vendor), c.reason, c.status, _d(c.initiated_at), _d(c.confirmed_at),
         ('Permanent' if c.is_permanent else _d(c.expiry_date)) if c.status in ('Blacklisted', 'Expired') else '', _d(c.reinstated_at)]
        for c in cases
    ]))
    data.notes.append('A tender covering several technologies counts under each in "Tenders by technology".')
    data.notes.append('Contract amendments are not recorded on the platform, so the contract register shows each contract as awarded. '
                      'The debarment register lists every case, whatever the period.')
    return data


def build_procurement_oversight(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import BidStatus, TenderBid, TenderContract

    tenders = list(active_tenders(ctx).prefetch_related('lots'))
    challenges = list(_challenges(tenders))
    rejected = (TenderBid.objects.filter(tender__in=tenders, status__in=[BidStatus.REJECTED, BidStatus.NOT_AWARDED])
                .select_related('tender').order_by('tender_id', 'vendor_name'))
    contracts = TenderContract.objects.filter(tender__in=tenders)
    by_status = Counter(t.status for t in tenders)
    data = ReportData(title='Procurement Oversight Summary')
    data.summary = [
        ('Tenders', len(tenders)), ('Awarded or closed', sum(by_status[s] for s in AWARDED)),
        ('Under evaluation or standstill', by_status['Evaluation'] + by_status['Standstill']),
        ('Disputed', by_status['Disputed']), ('Challenges', len(challenges)), ('Bids not successful', rejected.count()),
    ]
    data.tables.append(Table('Tenders by status', ['Status', 'Tenders'], sorted(by_status.items(), key=lambda r: -r[1]), chart=(0, 1)))
    data.tables.append(Table('Tenders', TENDER_COLUMNS, _tender_rows(tenders)))
    data.tables.append(Table('Contracts by status', ['Status', 'Contracts'], [
        [s, n] for s, n in Counter(contracts.values_list('status', flat=True)).most_common()
    ]))
    data.tables.append(Table('Challenges', CHALLENGE_COLUMNS, _challenge_rows(challenges)))
    data.tables.append(Table('Unsuccessful bids', ['Tender', 'Vendor', 'Outcome', 'Reason'], [
        [b.tender.reference_number, b.vendor_name, b.status, b.rejection_reason or ''] for b in rejected
    ]))
    return data


# ---------------------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------------------

CRITERIA = [('technical_score', 'Technical'), ('feasibility_score', 'Feasibility'), ('kpi_score', 'KPI'), ('gender_score', 'Gender'),
            ('environmental_score', 'Environmental'), ('om_score', 'O&M'), ('inclusivity_score', 'Inclusivity')]


def _justification_text(evaluation) -> str:
    j = evaluation.justifications or {}
    if not isinstance(j, dict):
        return str(j)
    return ' | '.join(f'{k}: {v}' for k, v in j.items() if v)


def _evaluations(tender, **filters):
    from rbf.tenders.models import TenderBidEvaluation

    return (TenderBidEvaluation.objects.filter(bid__tender=tender, **filters)
            .select_related('bid', 'lot', 'evaluator').order_by('lot_id', 'bid__vendor_name', 'evaluator_id'))


def build_technical_evaluation(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import EvaluationStage, EvaluationSubmissionStatus

    tender = ctx.tender_obj()
    submitted = EvaluationSubmissionStatus.SUBMITTED
    technical = list(_evaluations(tender, stage=EvaluationStage.TECHNICAL, submission_status=submitted))
    financial = list(_evaluations(tender, stage=EvaluationStage.FINANCIAL, submission_status=submitted))
    members = list(tender.evaluation_committee_members.select_related('member'))
    conflicts = list(tender.conflict_of_interests.select_related('evaluator'))
    data = ReportData(title=f'Technical Evaluation Report: {tender.reference_number}')
    data.details = [('Tender', f'{tender.reference_number} - {tender.name}'), ('Status', tender.status),
                    ('Weights', f'Technical {tender.technical_weight}%, financial {tender.financial_weight}%'),
                    ('Technical pass mark', tender.technical_threshold)]
    data.tables.append(Table('Evaluation committee', ['Member', 'Assigned', 'No-conflict attestation', 'Attested', 'Conflicts declared'], [
        [_user_name(m.member), _d(m.assigned_at), 'Yes' if m.coi_attested else 'No', _d(m.coi_attested_at),
         sum(1 for c in conflicts if c.evaluator_id == m.member_id)]
        for m in members
    ]))
    if conflicts:
        data.tables.append(Table('Declared conflicts of interest', ['Member', 'Bidder', 'Relationship', 'Details', 'Resolved', 'Resolution'], [
            [_user_name(c.evaluator), c.vendor_name, c.get_relationship_display(), c.details, 'Yes' if c.resolved else 'No', c.resolution_notes]
            for c in conflicts
        ]))
    # Average each bid's marks per lot across evaluators, then rank within the lot.
    groups: dict = defaultdict(list)
    for ev in technical:
        groups[(ev.lot.name if ev.lot_id else 'Whole tender', ev.bid_id)].append(ev)
    fin: dict = defaultdict(list)
    for ev in financial:
        if not ev.bid.financial_sealed:
            fin[(ev.lot.name if ev.lot_id else 'Whole tender', ev.bid_id)].append(ev.financial_score)
    ranking = []
    for (lot, _bid_id), evs in groups.items():
        tech = sum(e.total_score for e in evs) / len(evs)
        fin_scores = fin.get((lot, _bid_id))
        fin_avg = sum(fin_scores) / len(fin_scores) if fin_scores else None
        combined = round(tech * tender.technical_weight / 100 + fin_avg * tender.financial_weight / 100, 1) if fin_avg is not None else ''
        ranking.append([lot, evs[0].bid.vendor_name, len(evs), round(tech, 1), 'Pass' if tech >= tender.technical_threshold else 'Below pass mark',
                        round(fin_avg, 1) if fin_avg is not None else 'Sealed or not scored', combined])
    ranking.sort(key=lambda r: (r[0], -(r[6] if isinstance(r[6], float) else -1), -r[3]))
    rank, last_lot = 0, None
    for row in ranking:
        rank = 1 if row[0] != last_lot else rank + 1
        last_lot = row[0]
        row.insert(1, rank)
    data.summary = [
        ('Committee members', len(members)), ('Bids scored', len(groups)), ('Technical evaluations submitted', len(technical)),
        ('Passing the technical mark', sum(1 for r in ranking if r[5] == 'Pass')),
    ]
    data.tables.append(Table('Ranking', ['Lot', 'Rank', 'Bidder', 'Evaluators', 'Technical (avg)', 'Technical result', 'Financial (avg)', 'Combined'],
                             ranking, chart=(2, 4) if len({r[0] for r in ranking}) == 1 else None))
    data.tables.append(Table('Technical scores by evaluator',
                             ['Lot', 'Bidder', 'Evaluator', *[label for _, label in CRITERIA], 'Total', 'Submitted', 'Justifications'], [
        [ev.lot.name if ev.lot_id else 'Whole tender', ev.bid.vendor_name, _user_name(ev.evaluator),
         *[getattr(ev, f) for f, _ in CRITERIA], ev.total_score, _d(ev.submitted_at), _justification_text(ev)]
        for ev in technical
    ]))
    recs = tender.award_recommendations.select_related('bid', 'lot', 'suggested_by')
    data.tables.append(Table('Award recommendations', ['Lot', 'Recommended bidder', 'Member', 'Rationale', 'Date'], [
        [r.lot.name if r.lot_id else 'Whole tender', r.bid.vendor_name, _user_name(r.suggested_by), r.rationale, _d(r.created_at)]
        for r in recs
    ]))
    data.notes.append('Only submitted evaluations are counted. Financial scores are shown once the financial envelopes are unsealed. '
                      'Combined = technical x technical weight + financial x financial weight.')
    return data


def build_my_score_sheet(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import TenderBidEvaluation

    tenders = ctx.tenders()
    evaluations = (TenderBidEvaluation.objects.filter(evaluator=ctx.user, bid__tender__in=tenders)
                   .select_related('bid__tender', 'lot').order_by('bid__tender_id', 'stage', 'lot_id', 'bid__vendor_name'))
    memberships = ctx.user.evaluation_committee_assignments.filter(tender__in=tenders).select_related('tender')
    data = ReportData(title='My Evaluation Score Sheet')
    data.details = [('Evaluator', _user_name(ctx.user))]
    data.summary = [('Tenders', memberships.count()), ('Evaluations', evaluations.count()),
                    ('Submitted', evaluations.filter(submission_status='submitted').count())]
    data.tables.append(Table('Conflict-of-interest attestations', ['Tender', 'Attested', 'Date', 'Conflicts declared'], [
        [m.tender.reference_number, 'Yes' if m.coi_attested else 'No', _d(m.coi_attested_at),
         '; '.join(f'{c.vendor_name} ({c.get_relationship_display()})' for c in m.tender.conflict_of_interests.filter(evaluator=ctx.user)) or 'None']
        for m in memberships
    ]))
    data.tables.append(Table('My scores', ['Tender', 'Stage', 'Lot', 'Bidder', *[label for _, label in CRITERIA], 'Financial', 'Total',
                                           'Status', 'Submitted', 'Justifications', 'Comments'], [
        [ev.bid.tender.reference_number, ev.get_stage_display(), ev.lot.name if ev.lot_id else '', ev.bid.vendor_name,
         *[getattr(ev, f) for f, _ in CRITERIA], ev.financial_score, ev.total_score, ev.get_submission_status_display(),
         _d(ev.submitted_at), _justification_text(ev), ev.comments]
        for ev in evaluations
    ]))
    return data


# ---------------------------------------------------------------------------------------
# Procurement compliance audit
# ---------------------------------------------------------------------------------------

def _check(rows, exceptions, tender, name, result, detail=''):
    rows.append([tender.reference_number, name, result, detail])
    if result == 'Exception':
        exceptions.append([tender.reference_number, name, detail])


def build_procurement_compliance(ctx: ReportContext) -> ReportData:
    from rbf.tenders.models import (
        EvaluationStage, EvaluationSubmissionStatus, IntentAwardRequestStatus, TenderBidEvaluation,
    )

    from .models import AuditLog

    tenders = list(active_tenders(ctx).prefetch_related('lots', 'evaluation_committee_members', 'conflict_of_interests'))
    approvals: dict = {}
    for entity_id, when in (AuditLog.objects.filter(entity_type='Tender', action='tender_publish_approved', entity_id__in=[str(t.id) for t in tenders])
                            .order_by('created_at').values_list('entity_id', 'created_at')):
        approvals.setdefault(entity_id, when)
    rows, exceptions = [], []
    for t in tenders:
        published = t.published_at is not None or t.status not in {'Draft', 'Pending Publish Approval'}
        if published and t.is_eoi_invite_only:
            _check(rows, exceptions, t, 'Publication approved by Super Admin', 'Not required', 'Expression-of-interest invitation.')
        elif published:
            # Publishing resets the approval field, so the approval is taken from the audit log.
            approved_at = approvals.get(str(t.id))
            ok = approved_at is not None and (t.published_at is None or approved_at <= t.published_at)
            _check(rows, exceptions, t, 'Publication approved by Super Admin', 'Pass' if ok else 'Exception',
                   f'Approved {_d(approved_at)}.' if ok else 'No Super Admin publish approval recorded before publication.')
        if t.status not in POST_EVALUATION:
            _check(rows, exceptions, t, 'Evaluation checks', 'Not yet applicable', f'Tender is {t.status}.')
            continue
        members = list(t.evaluation_committee_members.all())
        size_ok = 3 <= len(members) <= 5
        _check(rows, exceptions, t, 'Committee of 3 to 5 members', 'Pass' if size_ok else 'Exception', f'{len(members)} members.')
        evals = list(TenderBidEvaluation.objects.filter(bid__tender=t).select_related('bid'))
        late = []
        for m in members:
            first = min((e.created_at for e in evals if e.evaluator_id == m.member_id), default=None)
            if first and (not m.coi_attested_at or m.coi_attested_at > first):
                late.append(_user_name(m.member))
        _check(rows, exceptions, t, 'No-conflict attestation before scoring', 'Exception' if late else 'Pass',
               ('Scored before attesting: ' + ', '.join(late)) if late else '')
        conflicts = list(t.conflict_of_interests.all())
        conflicted_scoring = [
            f'{_user_name(c.evaluator)} scored {c.vendor_name}'
            for c in conflicts if any(e.evaluator_id == c.evaluator_id and e.bid.vendor_id == c.vendor_id for e in evals)
        ]
        unresolved = [c for c in conflicts if not c.resolved]
        detail = '; '.join(conflicted_scoring + [f'{len(unresolved)} declaration(s) unresolved'] if unresolved else conflicted_scoring)
        _check(rows, exceptions, t, 'Declared conflicts kept out of scoring', 'Exception' if conflicted_scoring or unresolved else 'Pass', detail)
        submitted = [e for e in evals if e.stage == EvaluationStage.TECHNICAL and e.submission_status == EvaluationSubmissionStatus.SUBMITTED]
        missing = []
        for bid in _submitted_bids(t):
            scored_by = {e.evaluator_id for e in submitted if e.bid_id == bid.id}
            absent = [m for m in members if m.member_id not in scored_by]
            if absent:
                missing.append(f'{bid.vendor_name} ({len(absent)} missing)')
        _check(rows, exceptions, t, 'Every bid scored by every member', 'Exception' if missing else 'Pass', '; '.join(missing))
        no_reason = sum(1 for e in submitted if not _justification_text(e))
        _check(rows, exceptions, t, 'Technical scores justified', 'Exception' if no_reason else 'Pass',
               f'{no_reason} submitted evaluation(s) without justification.' if no_reason else '')
        # Standstill: each award confirmed no earlier than the end of its standstill.
        units = [(lot.name, lot.awarded_at, lot.cooling_off_until, lot) for lot in t.lots.all()] or [('Whole tender', t.awarded_at, t.cooling_off_until, None)]
        early = [f'{name} awarded {_d(awarded)} before standstill ended {_d(until)}' for name, awarded, until, _ in units
                 if awarded and until and awarded < until]
        if any(awarded for _, awarded, _, _ in units):
            _check(rows, exceptions, t, 'Standstill period kept', 'Exception' if early else 'Pass', '; '.join(early))
            approved_intents = t.intent_award_requests.filter(status=IntentAwardRequestStatus.APPROVED)
            no_intent = [name for name, awarded, _, lot in units if awarded and not approved_intents.filter(lot=lot).exists()]
            _check(rows, exceptions, t, 'Intent to award approved by Super Admin', 'Exception' if no_intent else 'Pass',
                   ('No approved intent for: ' + ', '.join(no_intent)) if no_intent else '')
            first_award = min(a for _, a, _, _ in units if a)
            pending = [c for c in _challenges([t]) if c.filed_at and c.filed_at < first_award
                       and not ((c.resolved_at and c.resolved_at <= first_award) or (c.withdrawn_at and c.withdrawn_at <= first_award))]
            _check(rows, exceptions, t, 'Challenges decided before award', 'Exception' if pending else 'Pass',
                   f'{len(pending)} challenge(s) open at award.' if pending else '')
    data = ReportData(title='Procurement Compliance Audit')
    data.summary = [('Tenders tested', len(tenders)), ('Checks', len(rows)), ('Exceptions', len(exceptions)),
                    ('Tenders with an exception', len({e[0] for e in exceptions}))]
    data.tables.append(Table('Exceptions', ['Tender', 'Check', 'Detail'], exceptions))
    data.tables.append(Table('All checks', ['Tender', 'Check', 'Result', 'Detail'], rows))
    return data
