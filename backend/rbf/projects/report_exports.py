"""Data exports and system reports: energy output, site register (GeoJSON), beneficiary data,
donor (IATI) data, the per-project audit package (ZIP), meter data exceptions, the anomaly and
data integrity report, system access and report usage."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from xml.etree import ElementTree as ET

from django.conf import settings
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from rbf.users.models import PlatformConfiguration

from . import claim_status
from .models import (
    AnomalyFlag,
    AuditLog,
    Disbursement,
    FieldVerification,
    GeneratedReport,
    InstallationReport,
    MeterDataBatch,
    PaymentClaim,
    ProjectArchive,
    SmartMeterReading,
)
from .report_engine import ReportContext, ReportData, Table, _cell, _d, _money, _pct, _user_name, render_xlsx

# ---------------------------------------------------------------------------------------
# Energy and meters
# ---------------------------------------------------------------------------------------

def _accepted_readings(ctx: ReportContext):
    readings = SmartMeterReading.objects.filter(project__in=ctx.projects(), review_status='accepted').exclude(
        batch__status__in=['rejected', 'superseded'],
    )
    return ctx.in_period(readings, 'recorded_at').select_related('project', 'installation', 'batch')


def build_energy_export(ctx: ReportContext) -> ReportData:
    readings = _accepted_readings(ctx).order_by('project_id', 'meter_id', 'recorded_at')
    by_project = readings.values('project__project_reference', 'project_id', 'project__vendor_name').annotate(
        n=Count('id'), meters=Count('meter_id', distinct=True), kwh=Sum('kwh'), uptime=Avg('uptime_pct'),
    ).order_by('project_id')
    data = ReportData(title='Energy Output Export')
    total = readings.aggregate(kwh=Sum('kwh'))['kwh'] or 0
    data.summary = [('Readings', readings.count()), ('Meters', readings.values('meter_id').distinct().count()), ('Energy', f'{float(total):,.1f} kWh')]
    data.tables.append(Table('By project', ['Project', 'Vendor', 'Meters', 'Readings', 'kWh', 'Average uptime %'], [
        [r['project__project_reference'] or r['project_id'], r['project__vendor_name'], r['meters'], r['n'], round(float(r['kwh'] or 0), 3),
         round(float(r['uptime'] or 0), 1)]
        for r in by_project
    ], chart=(0, 4)))
    data.tables.append(Table('Readings', ['Project', 'Meter', 'Installation serial', 'Recorded at', 'kWh', 'Uptime %', 'Output power (W)',
                                          'Source', 'Batch'], [
        [r.project.project_reference or r.project_id, r.meter_id, r.installation.serial_number if r.installation_id else '',
         _d(r.recorded_at), r.kwh, r.uptime_pct, r.output_power_w if r.output_power_w is not None else '', r.get_source_display(),
         r.batch_id or '']
        for r in readings
    ]))
    data.notes.append('Only accepted readings are exported; readings from rejected or superseded batches are left out.')
    return data


def build_meter_exceptions(ctx: ReportContext) -> ReportData:
    readings = ctx.in_period(SmartMeterReading.objects.filter(project__in=ctx.projects()), 'recorded_at')
    exceptions = readings.filter(Q(review_status='rejected') | ~Q(integrity_flags=[])).select_related('project', 'batch').order_by('-recorded_at')
    batches = ctx.in_period(MeterDataBatch.objects.filter(project__in=ctx.projects()), 'created_at').select_related('project')
    codes = Counter()
    for flags in exceptions.values_list('integrity_flags', flat=True):
        codes.update(flags or ['rejected'])
    findings = []
    for b in batches.order_by('-created_at'):
        for f in b.integrity_findings or []:
            findings.append([b.project.project_reference or b.project_id, b.id, b.file_name, b.get_status_display(), f.get('label') or f.get('code'),
                             f.get('severity', ''), f.get('meter_id', ''), len(f.get('reading_ids') or []), f.get('message', '')])
    data = ReportData(title='Meter Data Exceptions')
    data.summary = [('Readings in period', readings.count()), ('Readings with exceptions', exceptions.count()),
                    ('Share', f'{_pct(exceptions.count(), readings.count()):.1f}%'), ('Batches uploaded', batches.count()),
                    ('Batches flagged or to correct', batches.filter(status__in=['flagged', 'correction_requested']).count()),
                    ('Rows rejected on upload', batches.aggregate(n=Sum('rows_rejected_on_upload'))['n'] or 0)]
    data.tables.append(Table('By check', ['Check', 'Readings'], codes.most_common(), chart=(0, 1)))
    data.tables.append(Table('Batch findings', ['Project', 'Batch', 'File', 'Batch status', 'Finding', 'Severity', 'Meter', 'Readings', 'Detail'], findings))
    data.tables.append(Table('Readings with exceptions', ['Project', 'Meter', 'Recorded at', 'kWh', 'Uptime %', 'Checks', 'Review', 'Reason', 'Batch'], [
        [r.project.project_reference or r.project_id, r.meter_id, _d(r.recorded_at), r.kwh, r.uptime_pct, ', '.join(r.integrity_flags or []),
         r.get_review_status_display(), r.rejection_reason, r.batch_id or '']
        for r in exceptions
    ]))
    return data


def build_anomaly_integrity(ctx: ReportContext) -> ReportData:
    projects = ctx.projects()
    flags = ctx.in_period(AnomalyFlag.objects.filter(project__in=projects).select_related('project', 'installation'), 'created_at')
    total = flags.count()
    open_count = flags.filter(is_resolved=False).count()
    installs = InstallationReport.objects.filter(project__in=projects)
    dup_serials = list(installs.values('serial_number').annotate(n=Count('id')).filter(n__gt=1).order_by('-n'))
    dup_beneficiaries = installs.exclude(beneficiary_id='').values('beneficiary_id').annotate(n=Count('id')).filter(n__gt=1).count()
    batches = ctx.in_period(MeterDataBatch.objects.filter(project__in=projects), 'created_at')
    data = ReportData(title='Anomaly and Data Integrity Report')
    data.summary = [('Flags raised', total), ('Open', open_count), ('Resolved', total - open_count),
                    ('High or critical open', flags.filter(is_resolved=False, severity__in=['high', 'critical']).count()),
                    ('Duplicate serial numbers', len(dup_serials)), ('Meter batches flagged', batches.filter(status='flagged').count())]
    data.tables.append(Table('By type', ['Type', 'Raised', 'Open'], chart=(0, 1), rows=[
        [row['flag_type'], row['n'], row['open']]
        for row in flags.values('flag_type').annotate(n=Count('id'), open=Count('id', filter=Q(is_resolved=False))).order_by('-n')
    ]))
    data.tables.append(Table('By vendor', ['Vendor', 'Raised', 'Open', 'High or critical'], [
        [row['project__vendor_name'], row['n'], row['open'], row['severe']]
        for row in flags.values('project__vendor_name').annotate(
            n=Count('id'), open=Count('id', filter=Q(is_resolved=False)), severe=Count('id', filter=Q(severity__in=['high', 'critical'])),
        ).order_by('-n')
    ]))
    data.tables.append(Table('By district', ['District', 'Raised', 'Open'], [
        [row['project__district'] or 'Unknown', row['n'], row['open']]
        for row in flags.values('project__district').annotate(n=Count('id'), open=Count('id', filter=Q(is_resolved=False))).order_by('-n')
    ]))
    data.tables.append(Table('Data integrity checks', ['Check', 'Records', 'Result'], [
        [c, n, 'Pass' if n == 0 else 'Review'] for c, n in [
            ['Serial numbers used more than once', len(dup_serials)],
            ['Beneficiary IDs used more than once', dup_beneficiaries],
            ['Installations without GPS', installs.filter(Q(gps_lat=0) | Q(gps_lng=0)).count()],
            ['Meter batches flagged in period', batches.filter(status='flagged').count()],
            ['Meter batches awaiting correction', batches.filter(status='correction_requested').count()],
            ['Meter rows rejected on upload in period', batches.aggregate(n=Sum('rows_rejected_on_upload'))['n'] or 0],
        ]
    ]))
    data.tables.append(Table('Flags', ['Flag', 'Project', 'Vendor', 'Installation serial', 'Type', 'Severity', 'Status', 'Raised', 'Due', 'Resolved',
                                       'Description', 'Corrective action'], [
        [f.id, f.project.project_reference or f.project_id, f.project.vendor_name, f.installation.serial_number if f.installation_id else '',
         f.flag_type, f.get_severity_display(), f.get_status_display(), _d(f.created_at), _d(f.due_date), _d(f.resolved_at),
         f.description or '', f.corrective_action]
        for f in flags.order_by('-created_at')
    ]))
    data.notes.append('Duplicate and GPS checks cover every installation in scope; flags and meter batches are those in the period.')
    return data


# ---------------------------------------------------------------------------------------
# Sites, beneficiaries and GIS
# ---------------------------------------------------------------------------------------

def _latest_verification(installs) -> dict:
    latest: dict = {}
    for inst_id, status, gender, when in (FieldVerification.objects.filter(installation__in=installs)
                                          .order_by('installation_id', '-verified_at')
                                          .values_list('installation_id', 'verification_status', 'beneficiary_gender', 'verified_at')):
        latest.setdefault(inst_id, (status, gender, when))
    return latest


SITE_COLUMNS = ['Installation', 'Serial number', 'Project', 'Vendor', 'Technology', 'District', 'Household type', 'Status', 'GIS status',
                'Latitude', 'Longitude', 'Installation date', 'Last field verification', 'Verified on']


def build_site_register(ctx: ReportContext) -> ReportData:
    installs = ctx.in_period(InstallationReport.objects.filter(project__in=ctx.projects()), 'submitted_at').select_related('project').order_by('project_id', 'id')
    latest = _latest_verification(installs)
    rows = []
    for i in installs:
        status, _gender, when = latest.get(i.id, ('', '', None))
        rows.append([i.id, i.serial_number, i.project.project_reference or i.project_id, i.project.vendor_name, i.project.tech_type,
                     i.district or i.project.district, i.household_type, i.get_status_display(), i.get_gis_status_display(),
                     float(i.gps_lat), float(i.gps_lng), _d(i.installation_date), status, _d(when)])
    data = ReportData(title='Site Register and GIS Export')
    data.details = [('Scope', ctx.scope_label())]
    data.summary = [('Sites', len(rows)), *Counter(r[7] for r in rows).most_common()]
    data.tables.append(Table('By district', ['District', 'Sites'], Counter(r[5] or 'Unknown' for r in rows).most_common(), chart=(0, 1)))
    data.tables.append(Table('Sites', SITE_COLUMNS, rows, pii={'Latitude': 'gps', 'Longitude': 'gps'}))
    data.notes.append('Coordinates are WGS 84 decimal degrees. The GeoJSON file contains one point per site with the same attributes.')
    return data


def render_geojson(data: ReportData, ctx: ReportContext, header, notes):
    table = data.tables[-1]
    lat_i, lng_i = table.columns.index('Latitude'), table.columns.index('Longitude')
    features = []
    for row in table.rows:
        try:
            lng, lat = float(row[lng_i]), float(row[lat_i])
        except (TypeError, ValueError):
            continue
        if not (lat or lng):
            continue
        props = {col: _cell(val) for col, val in zip(table.columns, row) if col not in ('Latitude', 'Longitude')}
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lng, lat]}, 'properties': props})
    collection = {
        'type': 'FeatureCollection',
        'name': data.title,
        'metadata': {label: str(value) for label, value in header},
        'features': features,
    }
    return json.dumps(collection, ensure_ascii=False, indent=1).encode('utf-8'), 'application/geo+json', 'geojson'


def build_beneficiary_export(ctx: ReportContext) -> ReportData:
    installs = ctx.in_period(InstallationReport.objects.filter(project__in=ctx.projects()), 'submitted_at').select_related('project').order_by('project_id', 'id')
    latest = _latest_verification(installs)
    rows = []
    for i in installs:
        _status, gender, _when = latest.get(i.id, ('', '', None))
        rows.append([i.beneficiary_id, i.beneficiary_name, i.beneficiary_phone, (gender or 'not recorded').title(), i.household_type,
                     i.district or i.project.district, i.project.project_reference or i.project_id, i.project.vendor_name, i.project.tech_type,
                     float(i.gps_lat), float(i.gps_lng), _d(i.installation_date), i.get_status_display()])
    data = ReportData(title='Beneficiary Data Export')
    data.details = [('Reason given', ctx.reason)]
    data.summary = [('Beneficiaries', len(rows)), *Counter(r[3] for r in rows).most_common()]
    data.tables.append(Table('Beneficiaries', ['Beneficiary ID', 'Name', 'Phone', 'Sex', 'Household type', 'District', 'Project', 'Vendor',
                                               'Technology', 'Latitude', 'Longitude', 'Installation date', 'Status'], rows,
                             pii={'Beneficiary ID': 'identity', 'Name': 'identity', 'Phone': 'identity', 'Latitude': 'gps', 'Longitude': 'gps'}))
    data.notes.append('Personal data protected under the Lesotho Data Protection Act 2011. Use it only for the reason given, do not '
                      'share it further, and delete it when that purpose is met. The reason and this export are recorded in the audit log.')
    return data


# ---------------------------------------------------------------------------------------
# Donor data (IATI)
# ---------------------------------------------------------------------------------------

IATI_SECTOR = '23210'  # Energy generation, renewable sources - multiple technologies (OECD DAC CRS)


def build_iati_export(ctx: ReportContext) -> ReportData:
    from .report_programme import results_rows

    projects = ctx.projects()
    identifier = getattr(settings, 'IATI_ACTIVITY_IDENTIFIER', '') or 'XM-DAC-41114-RENEWABLE-LESOTHO'
    org_ref = getattr(settings, 'IATI_REPORTING_ORG_REF', '') or 'XM-DAC-41114'
    config = PlatformConfiguration.objects.order_by('id').first()
    budget = float(getattr(config, 'national_main_program_budget', 0) or 0)
    claims = ctx.in_period(PaymentClaim.objects.filter(project__in=projects, status__in=claim_status.PAID), 'submitted_at').select_related('project')
    transactions = []
    for c in claims.order_by('paid_at', 'id'):
        when = c.paid_at or c.submitted_at
        transactions.append([f'CLAIM-{c.id}', '3', 'Disbursement', when.date().isoformat() if when else '', float(c.claim_amount or 0), 'LSL',
                             c.project.vendor_name, f'Results-based payment, {c.project.project_reference or c.project_id}'])
    results, _configured = results_rows(ctx)
    starts = [p.start_date for p in projects if p.start_date]
    activity = [
        ['IATI identifier', identifier], ['Reporting organisation', f'UNDP ({org_ref})'],
        ['Title', 'Renewable Lesotho: results-based financing for off-grid energy'], ['Activity status', '2 (Implementation)'],
        ['Recipient country', 'LS (Lesotho)'], ['Sector', f'{IATI_SECTOR} (Energy generation, renewable sources)'],
        ['Default currency', 'LSL'], ['Actual start', min(starts).isoformat() if starts else ''],
        ['Period start', ctx.date_from.isoformat() if ctx.date_from else ''], ['Period end', ctx.date_to.isoformat() if ctx.date_to else ''],
        ['Programme budget (LSL)', budget or ''],
    ]
    data = ReportData(title='Donor Data Export (IATI)')
    data.summary = [('Disbursement transactions', len(transactions)), ('Disbursed', _money(sum(t[4] for t in transactions))),
                    ('Result indicators', len(results))]
    data.tables.append(Table('Activity', ['Field', 'Value'], activity))
    data.tables.append(Table('Results', ['Code', 'Indicator', 'Unit', 'Baseline', 'Target', 'Target date', 'Actual to date', 'In period',
                                         '% of target', 'Source'], results))
    data.tables.append(Table('Transactions', ['Reference', 'Type code', 'Type', 'Date', 'Value', 'Currency', 'Receiver', 'Description'], transactions))
    data.extra = {'identifier': identifier, 'org_ref': org_ref, 'budget': budget}
    if not getattr(settings, 'IATI_ACTIVITY_IDENTIFIER', ''):
        data.notes.append(f'The IATI activity identifier "{identifier}" is a placeholder. UNDP must confirm the published identifier '
                          '(set IATI_ACTIVITY_IDENTIFIER) before this file is published to the IATI Registry.')
    data.notes.append('Aligned to the IATI Activity Standard 2.03. Transactions are paid results-based claims; the full UNDP activity '
                      'file also carries commitments and expenditure that are not held on this platform.')
    return data


def _narrative(parent, tag, text, **attrs):
    el = ET.SubElement(parent, tag, **attrs)
    ET.SubElement(el, 'narrative').text = str(text)
    return el


def render_iati_xml(data: ReportData, ctx: ReportContext, header, notes):
    now = timezone.now().replace(microsecond=0).isoformat()
    root = ET.Element('iati-activities', version='2.03', **{'generated-datetime': now})
    act = ET.SubElement(root, 'iati-activity', **{'default-currency': 'LSL', 'last-updated-datetime': now, 'xml:lang': 'en'})
    ET.SubElement(act, 'iati-identifier').text = data.extra['identifier']
    _narrative(act, 'reporting-org', 'United Nations Development Programme', ref=data.extra['org_ref'], type='40')
    _narrative(act, 'title', 'Renewable Lesotho: results-based financing for off-grid energy')
    _narrative(act, 'description', 'Results-based financing for verified off-grid energy installations in Lesotho.', type='1')
    _narrative(act, 'participating-org', 'European Union', role='1')
    _narrative(act, 'participating-org', 'United Nations Development Programme', role='4', ref=data.extra['org_ref'])
    ET.SubElement(act, 'activity-status', code='2')
    activity = dict(data.tables[0].rows)
    if activity.get('Actual start'):
        ET.SubElement(act, 'activity-date', type='2', **{'iso-date': activity['Actual start']})
    ET.SubElement(act, 'recipient-country', code='LS', percentage='100')
    ET.SubElement(act, 'sector', vocabulary='1', code=IATI_SECTOR, percentage='100')
    if data.extra.get('budget') and ctx.date_from and ctx.date_to:
        b = ET.SubElement(act, 'budget', type='1', status='1')
        ET.SubElement(b, 'period-start', **{'iso-date': ctx.date_from.isoformat()})
        ET.SubElement(b, 'period-end', **{'iso-date': ctx.date_to.isoformat()})
        ET.SubElement(b, 'value', currency='LSL', **{'value-date': ctx.date_from.isoformat()}).text = f"{data.extra['budget']:.2f}"
    for ref, code, _type, when, value, currency, receiver, desc in data.tables[2].rows:
        t = ET.SubElement(act, 'transaction', ref=ref)
        ET.SubElement(t, 'transaction-type', code=code)
        ET.SubElement(t, 'transaction-date', **{'iso-date': when})
        ET.SubElement(t, 'value', currency=currency, **{'value-date': when}).text = f'{value:.2f}'
        _narrative(t, 'description', desc)
        _narrative(t, 'receiver-org', receiver)
    for code, name, unit, baseline, target, target_date, to_date, _in_period, _pct_target, _source in data.tables[1].rows:
        if target == '':
            continue
        r = ET.SubElement(act, 'result', type='1')
        _narrative(r, 'title', f'{code} {name}')
        ind = ET.SubElement(r, 'indicator', measure='1')
        _narrative(ind, 'title', f'{name} ({unit})' if unit else name)
        if baseline != '':
            ET.SubElement(ind, 'baseline', value=str(baseline))
        period = ET.SubElement(ind, 'period')
        ET.SubElement(period, 'period-start', **{'iso-date': ctx.date_from.isoformat() if ctx.date_from else ''})
        ET.SubElement(period, 'period-end', **{'iso-date': target_date or (ctx.date_to.isoformat() if ctx.date_to else '')})
        ET.SubElement(period, 'target', value=str(target))
        if to_date != '':
            ET.SubElement(period, 'actual', value=str(to_date))
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), 'application/xml', 'xml'


# ---------------------------------------------------------------------------------------
# Project audit package
# ---------------------------------------------------------------------------------------

def build_project_package(ctx: ReportContext) -> ReportData:
    project = ctx.project()
    installs = list(InstallationReport.objects.filter(project=project).order_by('id'))
    visits = FieldVerification.objects.filter(installation__project=project).select_related('installation', 'field_officer').order_by('verified_at')
    readings = SmartMeterReading.objects.filter(project=project).order_by('recorded_at')
    claims = list(PaymentClaim.objects.filter(project=project).select_related('milestone').order_by('submitted_at'))
    disbursements = Disbursement.objects.filter(claim__project=project).select_related('processed_by')
    flags = AnomalyFlag.objects.filter(project=project).select_related('installation').order_by('created_at')
    entity_ids = {
        'Project': [str(project.id)], 'PaymentClaim': [str(c.id) for c in claims], 'InstallationReport': [str(i.id) for i in installs],
        'Milestone': [str(m) for m in project.milestones.values_list('id', flat=True)],
    }
    q = Q()
    for entity_type, ids in entity_ids.items():
        q |= Q(entity_type=entity_type, entity_id__in=ids)
    logs = AuditLog.objects.filter(q).select_related('actor').order_by('created_at')
    data = ReportData(title=f'Project Audit Package: {project.project_reference or project.id}')
    data.details = [('Project', project.project_reference or project.id), ('Vendor', project.vendor_name), ('Status', project.get_status_display())]
    data.summary = [('Installations', len(installs)), ('Verification visits', visits.count()), ('Meter readings', readings.count()),
                    ('Claims', len(claims)), ('Anomaly flags', flags.count()), ('Audit-log entries', logs.count())]
    data.tables.append(Table('Installations', ['Installation', 'Serial number', 'Beneficiary ID', 'Household type', 'District', 'Latitude', 'Longitude',
                                               'Installation date', 'Status', 'Submitted', 'Receipt file', 'Photos'], [
        [i.id, i.serial_number, i.beneficiary_id, i.household_type, i.district, float(i.gps_lat), float(i.gps_lng), _d(i.installation_date),
         i.get_status_display(), _d(i.submitted_at), i.receipt_file.name if i.receipt_file else '', len(i.photo_files or [])]
        for i in installs
    ], pii={'Beneficiary ID': 'identity', 'Latitude': 'gps', 'Longitude': 'gps'}))
    data.tables.append(Table('Verification log', ['Visit', 'Installation serial', 'Outcome', 'Round', 'GPS distance (m)', 'Location match',
                                                  'Flag reason', 'Verifier', 'Verified at'], [
        [v.id, v.installation.serial_number, v.get_verification_status_display(), v.verification_round, round(float(v.location_distance_meters or 0), 1),
         'Yes' if v.location_match else 'No', v.flag_reason or '', _user_name(v.field_officer), _d(v.verified_at)]
        for v in visits
    ]))
    data.tables.append(Table('Meter readings', ['Meter', 'Recorded at', 'kWh', 'Uptime %', 'Source', 'Review', 'Checks', 'Batch'], [
        [r.meter_id, _d(r.recorded_at), r.kwh, r.uptime_pct, r.get_source_display(), r.get_review_status_display(), ', '.join(r.integrity_flags or []), r.batch_id or '']
        for r in readings
    ]))
    data.tables.append(Table('Claims', ['Claim', 'Milestone', 'Amount (LSL)', 'Status', 'Submitted', 'RMT approved', 'TAC endorsed', 'Paid', 'Payment reference'], [
        [c.id, f'M{c.milestone.milestone_number}' if c.milestone_id else '', float(c.claim_amount or 0), c.status, _d(c.submitted_at),
         _d(c.verified_at), _d(c.approved_at), _d(c.paid_at), c.payment_reference]
        for c in claims
    ]))
    data.tables.append(Table('Disbursements', ['Disbursement', 'Claim', 'Amount (LSL)', 'Status', 'Reference', 'Processed by', 'Processed at'], [
        [d.id, d.claim_id, float(d.amount or 0), d.get_status_display(), d.reference, _user_name(d.processed_by), _d(d.processed_at)]
        for d in disbursements
    ]))
    data.tables.append(Table('Anomalies', ['Flag', 'Installation serial', 'Type', 'Severity', 'Status', 'Raised', 'Resolved', 'Description', 'Resolution'], [
        [f.id, f.installation.serial_number if f.installation_id else '', f.flag_type, f.get_severity_display(), f.get_status_display(),
         _d(f.created_at), _d(f.resolved_at), f.description, f.resolution_reason]
        for f in flags
    ]))
    data.tables.append(Table('Audit log', ['Time', 'Actor', 'Role', 'Action', 'Record', 'From', 'To', 'Notes', 'IP address'], [
        [_d(log.created_at), _user_name(log.actor) if log.actor_id else 'System', log.actor_role, log.action,
         f'{log.entity_type}#{log.entity_id}', log.old_status, log.new_status, log.notes, log.ip_address]
        for log in logs
    ]))
    data.extra = {'project_id': project.id}
    return data


def _dossier_pdf(project_id) -> tuple[bytes | None, str]:
    """The lifecycle dossier: the archived one if the project is archived, otherwise rendered now."""
    archive = ProjectArchive.objects.filter(project_id=project_id, superseded_at__isnull=True).order_by('-archived_at').first()
    if archive and archive.dossier:
        with archive.dossier.open('rb') as handle:
            return handle.read(), 'Lifecycle dossier from the project archive.'
    from .lifecycle import build_lifecycle
    from .lifecycle_dossier import render_dossier
    from .models import Project

    project = Project.objects.get(id=project_id)
    life = build_lifecycle(project)
    record = ProjectArchive(project=project, tender=project.tender, contract=None, reason='Audit package (project not archived)',
                            lifecycle_started_at=life['started_at'], lifecycle_ended_at=life['ended_at'],
                            timeline=life['timeline'], snapshot=life['snapshot'])
    record.archived_at = timezone.now()
    path = render_dossier(record)
    return path.read_bytes(), 'Lifecycle dossier rendered for this package (the project is not archived).'


def render_audit_package(data: ReportData, ctx: ReportContext, header, notes):
    files: dict[str, bytes] = {}
    files['workbook.xlsx'] = render_xlsx(data, ctx, header, notes)
    for n, table in enumerate(data.tables, start=1):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(table.columns)
        writer.writerows([[_cell(v) for v in row] for row in table.rows])
        name = ''.join(ch if ch.isalnum() else '_' for ch in table.title.lower()).strip('_')
        files[f'data/{n:02d}_{name}.csv'] = buffer.getvalue().encode('utf-8-sig')
    dossier_note = ''
    try:
        pdf, dossier_note = _dossier_pdf(data.extra['project_id'])
        if pdf:
            files['lifecycle_dossier.pdf'] = pdf
    except Exception:  # noqa: BLE001 - the package is still useful without the rendered dossier
        dossier_note = 'The lifecycle dossier could not be rendered; generate the package again or use the project archive.'
    lines = [f'{label}: {value}' for label, value in header]
    lines += ['', 'Contents (SHA-256):']
    lines += [f'  {hashlib.sha256(content).hexdigest()}  {name}' for name, content in sorted(files.items())]
    lines += ['', dossier_note, 'Evidence files (receipts, photos) are listed by name in the Installations table; they remain in the platform store.']
    lines += ['', *[f'{label}: {text}' for label, text in notes]]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('MANIFEST.txt', '\n'.join(lines))
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue(), 'application/zip', 'zip'


# ---------------------------------------------------------------------------------------
# System access and report usage
# ---------------------------------------------------------------------------------------

ACCOUNT_CHANGES = ['user_created', 'user_updated', 'user_deactivated', 'user_deleted', 'user_password_reset', 'password_changed',
                   'Updated role permissions', 'vendor_account_approved']
FAILED_SIGN_IN_ALERT = 5


def build_system_access(ctx: ReportContext) -> ReportData:
    logs = ctx.in_period(AuditLog.objects.select_related('actor'), 'created_at')
    sign_ins = logs.filter(action='login_succeeded')
    failed = logs.filter(action='login_failed')
    changes = logs.filter(action__in=ACCOUNT_CHANGES).order_by('-created_at')
    by_user: dict = defaultdict(lambda: ['', '', 0, None])
    for log in sign_ins:
        e = by_user[log.actor_id]
        e[0], e[1] = _user_name(log.actor) if log.actor_id else 'Unknown', log.actor_role
        e[2] += 1
        e[3] = max(e[3], log.created_at) if e[3] else log.created_at
    failures: dict = defaultdict(lambda: [0, set(), None])
    for log in failed:
        ident = (log.details or {}).get('identifier') or 'Unknown'
        f = failures[ident]
        f[0] += 1
        if log.ip_address:
            f[1].add(log.ip_address)
        f[2] = max(f[2], log.created_at) if f[2] else log.created_at
    fail_rows = sorted([[ident, n, ', '.join(sorted(ips)), _d(last), 'Review' if n >= FAILED_SIGN_IN_ALERT else '']
                        for ident, (n, ips, last) in failures.items()], key=lambda r: -r[1])
    data = ReportData(title='System Access Report')
    data.summary = [('Sign-ins', sign_ins.count()), ('People signing in', len(by_user)), ('Failed sign-ins', failed.count()),
                    (f'Accounts with {FAILED_SIGN_IN_ALERT}+ failures', sum(1 for r in fail_rows if r[4])),
                    ('Account and permission changes', changes.count())]
    data.tables.append(Table('Sign-ins by person', ['Person', 'Role', 'Sign-ins', 'Last sign-in'],
                             sorted([[n, r, c, _d(last)] for n, r, c, last in by_user.values()], key=lambda r: -r[2]), chart=(0, 2)))
    data.tables.append(Table('Failed sign-ins', ['Username tried', 'Failures', 'IP addresses', 'Last attempt', 'Alert'], fail_rows))
    data.tables.append(Table('Account and permission changes', ['Time', 'By', 'Role', 'Change', 'Record', 'From', 'To', 'Notes', 'IP address'], [
        [_d(log.created_at), _user_name(log.actor) if log.actor_id else 'System', log.actor_role, log.action.replace('_', ' '),
         f'{log.entity_type}#{log.entity_id}' if log.entity_id else log.entity_type, log.old_status, log.new_status, log.notes, log.ip_address]
        for log in changes
    ]))
    data.notes.append(f'From the audit log. Usernames with {FAILED_SIGN_IN_ALERT} or more failed sign-ins in the period are marked for review. '
                      'Passwords are never recorded.')
    return data


def build_report_usage(ctx: ReportContext) -> ReportData:
    from .report_catalogue import REGISTRY

    logs = ctx.in_period(AuditLog.objects.filter(Q(action__startswith='report_') | Q(action='audit_report_generated')).select_related('actor'), 'created_at')
    reports = ctx.in_period(GeneratedReport.objects.all(), 'generated_at')
    title = {k: d.title for k, d in REGISTRY.items()}
    usage: dict = defaultdict(lambda: [0, 0, 0])
    for log in logs:
        rt = (log.details or {}).get('report_type') or ''
        if log.action == 'report_generated':
            usage[rt][0] += 1
        elif log.action == 'report_downloaded':
            usage[rt][1] += 1
        elif log.action == 'report_failed':
            usage[rt][2] += 1
    data = ReportData(title='Report Usage and Download Log')
    data.summary = [('Reports generated', reports.filter(status='ready').count()), ('Failed', reports.filter(status='failed').count()),
                    ('Downloads', logs.filter(action='report_downloaded').count()), ('People', logs.exclude(actor__isnull=True).values('actor').distinct().count()),
                    ('Shared with recipients', reports.filter(distributed_at__isnull=False).count())]
    data.tables.append(Table('By report', ['Report', 'Generated', 'Downloaded', 'Failed'], sorted(
        [[title.get(rt, rt or 'Unknown'), *v] for rt, v in usage.items()], key=lambda r: -r[1]), chart=(0, 1)))
    data.tables.append(Table('By person', ['Person', 'Role', 'Actions'], [
        [row['actor__full_name'] or row['actor__username'] or 'System', row['actor_role'], row['n']]
        for row in logs.values('actor__full_name', 'actor__username', 'actor_role').annotate(n=Count('id')).order_by('-n')
    ]))
    data.tables.append(Table('Log', ['Time', 'Person', 'Role', 'Action', 'Report', 'Format', 'Report ID', 'IP address'], [
        [_d(log.created_at), _user_name(log.actor) if log.actor_id else 'System', log.actor_role, log.action.replace('_', ' '),
         title.get((log.details or {}).get('report_type'), (log.details or {}).get('report_type') or ''), (log.details or {}).get('format', ''),
         log.entity_id, log.ip_address]
        for log in logs.order_by('-created_at')
    ]))
    data.notes.append('Generation, download, sign-off and sharing of reports as recorded in the audit log.')
    return data
