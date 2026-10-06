"""PDF dossier of an archived project's full lifecycle (tender creation to completion)."""
import html
import tempfile
from pathlib import Path

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ProjectArchive


def _e(value) -> str:
    return html.escape('' if value is None else str(value))


def _when(value) -> str:
    parsed = parse_datetime(value) if isinstance(value, str) else value
    return timezone.localtime(parsed).strftime('%Y-%m-%d %H:%M') if parsed else '-'


def _money(value) -> str:
    return f'LSL {value:,.2f}' if isinstance(value, (int, float)) else '-'


def _table(headers, rows, empty='None recorded.') -> str:
    if not rows:
        return f'<p class="muted">{_e(empty)}</p>'
    head = ''.join(f'<th>{_e(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{_e(cell)}</td>' for cell in row) + '</tr>' for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _pairs(items) -> str:
    rows = ''.join(f'<tr><th>{_e(k)}</th><td>{_e(v if v not in (None, "") else "-")}</td></tr>' for k, v in items)
    return f'<table class="pairs">{rows}</table>'


def build_dossier_html(record: ProjectArchive) -> str:
    snap = record.snapshot or {}
    tender = snap.get('tender') or {}
    lot = snap.get('lot') or {}
    contract = snap.get('contract') or {}
    project = snap.get('project') or {}
    kpis = project.get('final_kpis') or {}

    sections = [
        ('Project', _pairs([
            ('Reference', project.get('reference')), ('Title', project.get('title')), ('Vendor', project.get('vendor_name')),
            ('Technology', project.get('tech_type')), ('Region / district', f"{project.get('region') or '-'} / {project.get('district') or '-'}"),
            ('Budget', _money(project.get('budget'))), ('Target installations', project.get('target_installations')),
            ('Final uptime %', kpis.get('uptime_pct')), ('Final energy output (kWh)', kpis.get('energy_output_kwh')),
            ('Female beneficiaries %', kpis.get('gender_impact_pct')),
        ])),
        ('Lifecycle Timeline', _table(
            ['When', 'Phase', 'Event', 'Detail', 'By'],
            [[_when(e.get('at')), e.get('phase'), e.get('title'), e.get('detail'), e.get('actor')] for e in record.timeline or []],
        )),
        ('Procurement: Tender', _pairs([
            ('Reference', tender.get('reference')), ('Name', tender.get('name')), ('Department', tender.get('department')),
            ('Method', tender.get('procurement_method')), ('Budget', _money(tender.get('budget'))),
            ('Created', _when(tender.get('created_at'))), ('Published', _when(tender.get('published_at'))),
            ('Closed', _when(tender.get('closed_at'))), ('Awarded', _when(tender.get('awarded_at'))),
            ('Lot', lot.get('name')), ('Lot awarded to', lot.get('awarded_vendor_name')),
        ]) if tender else '<p class="muted">This project was not created from a tender.</p>'),
        ('Procurement: Bids', _table(
            ['Vendor', 'Stage', 'Status', 'Amount', 'Submitted', 'Rejection reason'],
            [[b.get('vendor_name'), b.get('stage'), b.get('status'), _money(b.get('bid_amount')), _when(b.get('submitted_at')), b.get('rejection_reason')]
             for b in snap.get('bids') or []],
        )),
        ('Procurement: Evaluation Scores', _table(
            ['Bidder', 'Stage', 'Evaluator', 'Technical', 'Financial', 'Total', 'Submitted'],
            [[v.get('vendor_name'), v.get('stage'), v.get('evaluator'), v.get('technical_score'), v.get('financial_score'), v.get('total_score'), _when(v.get('submitted_at'))]
             for v in snap.get('evaluations') or []],
        )),
        ('Award: Intent to Award and Challenges', _table(
            ['Proposed vendor', 'Status', 'Requested by', 'Requested', 'Reviewed by', 'Reviewed'],
            [[r.get('proposed_vendor_name'), r.get('status'), r.get('requested_by'), _when(r.get('requested_at')), r.get('reviewed_by'), _when(r.get('reviewed_at'))]
             for r in snap.get('intent_to_award_requests') or []],
        ) + _table(
            ['Filed by', 'Category', 'Status', 'Filed', 'Resolved', 'Resolution'],
            [[c.get('filed_by'), c.get('category'), c.get('status'), _when(c.get('filed_at')), _when(c.get('resolved_at')), c.get('resolution_notes')]
             for c in snap.get('challenges') or []],
            empty='No challenges filed.',
        )),
        ('Contract', _pairs([
            ('Reference', contract.get('reference')), ('Vendor', contract.get('vendor_name')), ('Award value', _money(contract.get('award_value'))),
            ('Generated', _when(contract.get('generated_at'))), ('Signed', _when(contract.get('signed_at'))),
            ('Approved', f"{_when(contract.get('approved_at'))} {contract.get('approved_by') or ''}"),
            ('Closed', _when(contract.get('closed_at'))), ('Status', contract.get('status')),
        ]) if contract else '<p class="muted">No contract on record.</p>'),
        ('Milestones', _table(
            ['#', 'Name', 'Share %', 'Amount', 'Status', 'Unlocked', 'Completed'],
            [[m.get('number'), m.get('name'), m.get('disbursement_pct'), _money(m.get('amount')), m.get('status'), _when(m.get('unlocked_at')), m.get('completed_date') or '-']
             for m in snap.get('milestones') or []],
        )),
        ('Payment Claims and Disbursements', _table(
            ['Claim', 'Milestone', 'Amount', 'Status', 'Submitted', 'Approved', 'Paid', 'Reference', 'Disbursed'],
            [[f"#{c.get('id')}", c.get('milestone'), _money(c.get('amount')), c.get('status'), _when(c.get('submitted_at')),
              _when(c.get('approved_at')), _when(c.get('paid_at')), c.get('payment_reference'),
              _money((c.get('disbursement') or {}).get('amount'))]
             for c in snap.get('payment_claims') or []],
        )),
        ('Installations, Verification and Monitoring', _pairs([
            ('Installations', (snap.get('installations') or {}).get('total')),
            ('By status', ', '.join(f'{k}: {v}' for k, v in ((snap.get('installations') or {}).get('by_status') or {}).items())),
            ('Field verification visits', (snap.get('field_verification') or {}).get('visits')),
            ('Outcomes', ', '.join(f'{k}: {v}' for k, v in ((snap.get('field_verification') or {}).get('by_outcome') or {}).items())),
            ('Re-verified installations', (snap.get('field_verification') or {}).get('reverified_installations')),
            ('GPS mismatches', (snap.get('field_verification') or {}).get('location_mismatches')),
            ('Meter readings', (snap.get('meter_data') or {}).get('readings')),
            ('Anomaly flags (unresolved)', f"{(snap.get('anomalies') or {}).get('total')} ({(snap.get('anomalies') or {}).get('unresolved')})"),
            ('Oversight reviews (open follow-ups)', f"{(snap.get('oversight_reviews') or {}).get('total')} ({(snap.get('oversight_reviews') or {}).get('open_follow_ups')})"),
            ('Audit cases', ', '.join(f"{a.get('reference')} ({a.get('status')})" for a in snap.get('audit_cases') or []) or 'None'),
        ])),
        ('Audit Trail', _table(
            ['When', 'Action', 'Record', 'By', 'Role', 'Status change'],
            [[_when(a.get('at')), a.get('action'), a.get('entity'), a.get('actor'), a.get('role'),
              f"{a.get('old_status') or ''} -> {a.get('new_status') or ''}" if a.get('new_status') else '']
             for a in snap.get('audit_trail') or []],
        )),
    ]
    body = ''.join(f'<h2>{_e(title)}</h2>{content}' for title, content in sections)
    return f"""
    <html><head><style>
      body {{ font-family: Arial, sans-serif; color: #0f172a; padding: 24px; font-size: 10.5px; }}
      h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 13px; margin: 18px 0 6px; border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 6px; }}
      th, td {{ border: 1px solid #e2e8f0; padding: 4px 5px; text-align: left; vertical-align: top; }}
      th {{ background: #f1f5f9; }} table.pairs th {{ width: 30%; }}
      .muted {{ color: #64748b; }}
    </style></head><body>
      <h1>Project Lifecycle Archive: {_e(project.get('reference') or record.project_id)}</h1>
      <p class="muted">From tender creation ({_e(_when(record.lifecycle_started_at))}) to completion and contract closure
        ({_e(_when(record.lifecycle_ended_at))}). Archived {_e(_when(record.archived_at))}. Reason: {_e(record.reason)}</p>
      {body}
    </body></html>
    """


def render_dossier(record: ProjectArchive) -> Path:
    from rbf.tenders.pba_pdf import _render_pdf

    reference = (record.snapshot or {}).get('project', {}).get('reference') or f'project_{record.project_id}'
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in reference)
    output = Path(tempfile.mkdtemp(prefix='archive_dossier_')) / f'{safe}_lifecycle_archive.pdf'
    from .report_pdf import report_footer, report_header

    _render_pdf(build_dossier_html(record), output, reference, header_template=report_header(f'Lifecycle Archive {reference}'),
                footer_template=report_footer('the programme archive'))
    return output
