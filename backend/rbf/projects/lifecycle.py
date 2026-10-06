"""The full lifecycle of a project, from tender creation to completion and contract closure.

Used to write the permanent archive record (ProjectArchive) when a project is archived:
a timeline of every step and a snapshot of the records behind each phase.

Procurement: tender created/published/closed, bids, evaluation scores, intent to award,
  challenges, award.
Contract: generated, signed, approved, closed.
Delivery: project created, setup, milestones, installations, field verification, meter data,
  anomalies, payment claims and disbursements, KPIs, oversight reviews and audit cases.
"""
from __future__ import annotations

from collections import Counter

from django.db.models import Q
from django.utils import timezone

from .models import (
    AnomalyFlag,
    AuditCase,
    AuditLog,
    Disbursement,
    FieldVerification,
    KpiReview,
    OversightReview,
    PaymentClaim,
    Project,
    SmartMeterReading,
    VerificationTask,
)


def _iso(value):
    return value.isoformat() if value else None


def _num(value):
    return float(value) if value is not None else None


def _event(events: list, when, phase: str, title: str, detail: str = '', actor: str = ''):
    if when:
        events.append({'at': _iso(when), 'phase': phase, 'title': title, 'detail': detail, 'actor': actor})


def project_contract(project: Project):
    from rbf.tenders.models import TenderContract

    if project.contract_id:
        return project.contract
    return TenderContract.objects.filter(project_id=str(project.id)).order_by('-generated_at').first()


def build_lifecycle(project: Project, *, ended_at=None) -> dict:
    """Return {'started_at', 'ended_at', 'timeline', 'snapshot'} for a project."""
    from rbf.tenders.models import IntentToAwardRequest, TenderBid, TenderBidEvaluation, TenderChallenge

    tender = project.tender
    lot = project.lot
    contract = project_contract(project)
    events: list[dict] = []
    snapshot: dict = {'generated_at': _iso(timezone.now())}

    # --- Procurement -------------------------------------------------------------------
    if tender:
        snapshot['tender'] = {
            'id': tender.id, 'reference': tender.reference_number, 'name': tender.name,
            'department': tender.department, 'category': tender.category,
            'procurement_method': tender.procurement_method, 'budget': _num(tender.budget),
            'status': tender.status, 'created_at': _iso(tender.created_at), 'published_at': _iso(tender.published_at),
            'deadline': _iso(tender.deadline), 'closed_at': _iso(tender.closed_at), 'awarded_at': _iso(tender.awarded_at),
        }
        _event(events, tender.created_at, 'Procurement', 'Tender created', f'{tender.reference_number} - {tender.name}')
        _event(events, tender.published_at, 'Procurement', 'Tender published')
        _event(events, tender.closed_at, 'Procurement', 'Tender closed for submissions')

        if lot:
            snapshot['lot'] = {
                'id': lot.id, 'name': lot.name, 'status': lot.status, 'budget': _num(lot.budget),
                'target_districts': lot.target_districts, 'intent_to_award_at': _iso(lot.intent_to_award_at),
                'awarded_at': _iso(lot.awarded_at), 'awarded_vendor_name': lot.awarded_vendor_name,
            }

        bids = TenderBid.objects.filter(tender=tender).order_by('submitted_at')
        if lot:
            bids = bids.filter(
                Q(lot_offers__lot=lot) | Q(declared_lots__contains=[lot.id]) | Q(declared_lots__contains=[str(lot.id)])
                | Q(id=lot.intent_to_award_bid_id)
            ).distinct()
        bids = list(bids)
        snapshot['bids'] = [
            {
                'id': bid.id, 'vendor_name': bid.vendor_name, 'stage': bid.bid_stage, 'status': bid.status,
                'bid_amount': _num(bid.bid_amount), 'submitted_at': _iso(bid.submitted_at),
                'rejection_reason': bid.rejection_reason,
            }
            for bid in bids
        ]
        for bid in bids:
            _event(events, bid.submitted_at, 'Procurement', f'Bid received from {bid.vendor_name}', f'{bid.bid_stage} stage, now {bid.status}')

        evaluations = TenderBidEvaluation.objects.filter(bid__tender=tender).select_related('bid', 'evaluator')
        if lot:
            evaluations = evaluations.filter(Q(lot=lot) | Q(lot__isnull=True, bid__in=bids))
        snapshot['evaluations'] = [
            {
                'bid_id': ev.bid_id, 'vendor_name': ev.bid.vendor_name, 'stage': ev.stage,
                'evaluator': (ev.evaluator.full_name or ev.evaluator.username) if ev.evaluator_id else '',
                'technical_score': _num(ev.technical_score), 'financial_score': _num(ev.financial_score),
                'total_score': _num(ev.total_score), 'status': ev.status,
                'submission_status': getattr(ev, 'submission_status', ''), 'submitted_at': _iso(getattr(ev, 'submitted_at', None)),
            }
            for ev in evaluations
        ]
        submitted = [ev for ev in evaluations if getattr(ev, 'submitted_at', None)]
        if submitted:
            last = max(ev.submitted_at for ev in submitted)
            _event(events, last, 'Procurement', 'Evaluation completed', f'{len(submitted)} evaluation(s) submitted')

        intents = IntentToAwardRequest.objects.filter(tender=tender).order_by('requested_at')
        if lot:
            intents = intents.filter(lot=lot)
        snapshot['intent_to_award_requests'] = [
            {
                'proposed_vendor_name': req.proposed_vendor_name, 'status': req.status,
                'requested_by': req.requested_by_name, 'requested_at': _iso(req.requested_at),
                'reviewed_by': req.reviewed_by_name, 'reviewed_at': _iso(req.reviewed_at),
                'ec_override_reason': req.ec_override_reason, 'notes': req.notes,
            }
            for req in intents
        ]
        for req in intents:
            _event(events, req.requested_at, 'Award', f'Intent to award proposed: {req.proposed_vendor_name}', actor=req.requested_by_name)
            _event(events, req.reviewed_at, 'Award', f'Intent to award {req.status.lower()} by Super Admin', req.notes, req.reviewed_by_name)
        intent_at = lot.intent_to_award_at if lot else tender.intent_to_award_at
        awarded_at = lot.awarded_at if lot else tender.awarded_at
        _event(events, intent_at, 'Award', 'Intent to award issued; standstill started')
        _event(events, awarded_at, 'Award', 'Award confirmed', (lot.awarded_vendor_name if lot else tender.awarded_vendor_name) or '')

        challenges = TenderChallenge.objects.filter(tender=tender).order_by('filed_at')
        snapshot['challenges'] = [
            {
                'filed_by': ch.filed_by_vendor_name, 'category': ch.category, 'status': ch.status, 'grounds': ch.grounds,
                'filed_at': _iso(ch.filed_at), 'resolved_at': _iso(ch.resolved_at), 'resolution_notes': ch.resolution_notes,
            }
            for ch in challenges
        ]
        for ch in challenges:
            _event(events, ch.filed_at, 'Award', f'Challenge filed by {ch.filed_by_vendor_name}', ch.category)
            _event(events, ch.resolved_at, 'Award', f'Challenge {ch.status.lower()}', ch.resolution_notes)

    # --- Contract ----------------------------------------------------------------------
    if contract:
        snapshot['contract'] = {
            'id': contract.id, 'reference': contract.reference_number, 'vendor_name': contract.vendor_name,
            'status': contract.status, 'award_value': _num(contract.resolved_award_value()),
            'generated_at': _iso(contract.generated_at), 'signed_at': _iso(contract.signed_at),
            'approved_at': _iso(contract.approved_at), 'approved_by': contract.approved_by, 'closed_at': _iso(contract.closed_at),
        }
        _event(events, contract.generated_at, 'Contract', 'Contract generated', contract.reference_number)
        _event(events, contract.signed_at, 'Contract', 'Contract signed by vendor')
        _event(events, contract.approved_at, 'Contract', 'Contract approved', actor=contract.approved_by)
        _event(events, contract.closed_at, 'Contract', 'Contract closed')

    # --- Delivery ----------------------------------------------------------------------
    snapshot['project'] = {
        'id': project.id, 'reference': project.project_reference, 'title': project.project_title,
        'vendor_id': project.vendor_id, 'vendor_name': project.vendor_name, 'tech_type': project.tech_type,
        'region': project.region, 'district': project.district, 'status': project.status,
        'budget': _num(project.budget), 'start_date': _iso(project.start_date), 'end_date': _iso(project.end_date),
        'target_installations': project.target_installations, 'created_at': _iso(project.created_at),
        'setup_completed_at': _iso(project.setup_completed_at),
        'final_kpis': {
            'uptime_pct': project.uptime, 'energy_output_kwh': project.energy_output,
            'gender_impact_pct': project.gender_impact, 'progress_pct': project.progress,
        },
    }
    _event(events, project.created_at, 'Delivery', 'Project created', project.project_reference or '')
    _event(events, project.setup_completed_at, 'Delivery', 'Project setup approved')

    milestones = list(project.milestones.order_by('milestone_number'))
    snapshot['milestones'] = [
        {
            'number': m.milestone_number, 'name': m.name, 'disbursement_pct': m.disbursement_pct, 'status': m.status,
            'amount': _num(m.amount_lsl or m.amount), 'unlocked_at': _iso(m.unlocked_at),
            'target_date': _iso(m.target_date), 'completed_date': _iso(m.completed_date),
        }
        for m in milestones
    ]
    for m in milestones:
        _event(events, m.unlocked_at, 'Delivery', f'Milestone {m.milestone_number} unlocked', m.name)

    claims = list(PaymentClaim.objects.filter(project=project).select_related('milestone').order_by('submitted_at'))
    disbursements = {d.claim_id: d for d in Disbursement.objects.filter(claim__project=project)}
    snapshot['payment_claims'] = []
    for claim in claims:
        disb = disbursements.get(claim.id)
        snapshot['payment_claims'].append({
            'id': claim.id, 'milestone': claim.milestone.milestone_number if claim.milestone_id else None,
            'amount': _num(claim.claim_amount), 'status': claim.status, 'submitted_at': _iso(claim.submitted_at),
            'verified_at': _iso(claim.verified_at), 'approved_at': _iso(claim.approved_at), 'paid_at': _iso(claim.paid_at),
            'payment_reference': claim.payment_reference,
            'disbursement': {
                'amount': _num(disb.amount), 'status': disb.status, 'reference': disb.reference,
                'processed_at': _iso(disb.processed_at),
            } if disb else None,
        })
        label = f'Claim #{claim.id}' + (f' (milestone {claim.milestone.milestone_number})' if claim.milestone_id else '')
        _event(events, claim.submitted_at, 'Payment', f'{label} submitted', f'LSL {claim.claim_amount:,.2f}')
        _event(events, claim.verified_at, 'Payment', f'{label} verified by RMT')
        _event(events, claim.approved_at, 'Payment', f'{label} approved')
        _event(events, claim.paid_at, 'Payment', f'{label} paid', claim.payment_reference)

    installs = project.installation_reports.all()
    verifications = FieldVerification.objects.filter(installation__project=project)
    snapshot['installations'] = {
        'total': installs.count(),
        'by_status': dict(Counter(installs.values_list('status', flat=True))),
        'first_reported_at': _iso(installs.order_by('submitted_at').values_list('submitted_at', flat=True).first()),
        'last_reported_at': _iso(installs.order_by('-submitted_at').values_list('submitted_at', flat=True).first()),
    }
    snapshot['field_verification'] = {
        'visits': verifications.count(),
        'by_outcome': dict(Counter(verifications.values_list('verification_status', flat=True))),
        'reverified_installations': VerificationTask.objects.filter(report__project=project, verification_round__gt=1).count(),
        'location_mismatches': verifications.filter(location_match=False).count(),
    }
    snapshot['meter_data'] = {'readings': SmartMeterReading.objects.filter(project=project).count()}
    flags = AnomalyFlag.objects.filter(project=project)
    snapshot['anomalies'] = {'total': flags.count(), 'unresolved': flags.filter(is_resolved=False).count()}
    snapshot['kpi_reviews'] = [
        {'period': r.review_period, 'rating': r.rating, 'summary': r.summary}
        for r in KpiReview.objects.filter(project=project).order_by('review_period')
    ]
    reviews = OversightReview.objects.filter(project=project)
    snapshot['oversight_reviews'] = {
        'total': reviews.count(),
        'by_status': dict(Counter(reviews.values_list('review_status', flat=True))),
        'open_follow_ups': reviews.filter(follow_up_status__in=['open', 'in_progress']).count(),
    }
    snapshot['audit_cases'] = [
        {'reference': c.reference, 'title': c.title, 'status': c.status, 'finding_type': c.finding_type}
        for c in AuditCase.objects.filter(project=project)
    ]

    completed_at = ended_at or timezone.now()
    _event(events, completed_at, 'Completion', 'Project completed and archived')

    # Everything else that was recorded about this project and its procurement.
    claim_ids = [str(c.id) for c in claims]
    log_filter = Q(details__project_id=str(project.id)) | Q(record_type__iexact='project', record_id=project.id) | Q(
        entity_type='Project', entity_id=str(project.id),
    ) | Q(entity_type='PaymentClaim', entity_id__in=claim_ids)
    if tender:
        log_filter |= Q(entity_type='Tender', entity_id=str(tender.id))
    if contract:
        log_filter |= Q(entity_type='TenderContract', entity_id=str(contract.id))
    logs = AuditLog.objects.filter(log_filter).select_related('actor').order_by('created_at')[:2000]
    snapshot['audit_trail'] = [
        {
            'at': _iso(log.created_at), 'action': log.action, 'entity': f'{log.entity_type}#{log.entity_id}',
            'actor': (log.actor.full_name or log.actor.username) if log.actor_id else 'System', 'role': log.actor_role,
            'old_status': log.old_status, 'new_status': log.new_status,
        }
        for log in logs
    ]

    events.sort(key=lambda e: e['at'])
    started_at = tender.created_at if tender else project.created_at
    return {'started_at': started_at, 'ended_at': completed_at, 'timeline': events, 'snapshot': snapshot}
