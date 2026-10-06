"""The report catalogue: every report offered, who may generate it, and what it uses.

Builders live in report_engine (core reports), report_programme (programme, PSC, TAC, DoE,
field and vendor reports) and report_audit (independent audit reports).
"""
from rest_framework.exceptions import PermissionDenied, ValidationError

from rbf.users.models import UserRole as R

from .report_engine import *  # noqa: F401,F403 - builders and ReportDefinition
from .report_engine import PROJECT_FILTERS, ReportDefinition
from .report_audit import (
    build_findings_tracker,
    build_kpi_compliance,
    build_payment_chain,
    build_reconciliation,
    build_red_flags,
)
from .report_exports import (
    build_anomaly_integrity,
    build_beneficiary_export,
    build_energy_export,
    build_iati_export,
    build_meter_exceptions,
    build_project_package,
    build_report_usage,
    build_site_register,
    build_system_access,
    render_audit_package,
    render_geojson,
    render_iati_xml,
)
from .report_oversight import (
    build_annual_report,
    build_budget_utilisation,
    build_decisions_log,
    build_followup_tracker,
    build_gender_oversight,
    build_national_access,
    build_regional_impact,
    build_risk_log,
    build_vendor_compliance,
    build_vendor_scorecard,
)
from .report_procurement import (
    build_my_score_sheet,
    build_procurement_compliance,
    build_procurement_oversight,
    build_procurement_pack,
    build_technical_evaluation,
)
from .report_programme import (
    build_claims_awaiting_endorsement,
    build_claims_pipeline,
    build_financial_delivery,
    build_monitoring_visits,
    build_psc_briefing,
    build_results,
    build_route_list,
    build_technical_performance,
    build_vendor_claim_statement,
    build_vendor_installations,
)


def _roles(*roles):
    return frozenset(roles)


CLAIM_METHOD = (
    'Claims are those submitted in the period for projects matching the filters. Paid = Completed (and legacy Paid); '
    'Approved, awaiting payment = PSC Approved (and legacy Approved); In review = Submitted, RMT Approved or TAC Endorsed. '
    'Contracted is the budget of every project in scope, whatever the period.'
)
INCLUSION_METHOD = (
    'Shares are of verified installations whose installation was reported in the period, by the household type recorded at '
    'installation (female-headed, vulnerable, low-income). Targets are the programme minimums set by the Super Admin in '
    'Platform Configuration (printed in the summary), or each project\'s contracted targets where a report shows them per project.'
)
VERIFICATION_METHOD = (
    'Counts field verification visits made in the period. A visit passes when the verifier records it as verified; '
    'GPS mismatch means the verifier stood more than 50 m from the vendor-reported location. Re-verified installations '
    'are those in their second or later verification round.'
)
SNAPSHOT_FILTERS = ('district', 'technology', 'vendor', 'tender')
PROCUREMENT_METHOD = (
    'Tenders open at any time in the period: created before the period ended and not closed before it began. Bids exclude drafts '
    'and withdrawn bids. Award value is the winning bid (or lot offer) converted to the tender currency.'
)

REGISTRY: dict[str, ReportDefinition] = {d.id: d for d in [
    ReportDefinition('rmt_kpi_project', 'KPI Report (Per Project)', 'Installation progress, inclusion, uptime and energy for one project.',
                     'KPI Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR, R.TAC, R.VENDOR), build_kpi_project, requires_project=True, filters=(),
                     method='KPIs are calculated by the platform KPI service over the whole life of the project to the time of generation.'),
    ReportDefinition('rmt_verification_project', 'Verification Report', 'Verification visits, outcomes, re-verification and GPS checks, by project.',
                     'Verification Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR, R.TAC), build_verification_summary, formal=True,
                     method=VERIFICATION_METHOD),
    ReportDefinition('rmt_financial_disbursement', 'Financial Disbursement Report', 'Contracted, claimed, approved and paid amounts, by project and claim.',
                     'Financial Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR), build_financial_disbursement, method=CLAIM_METHOD),
    ReportDefinition('rmt_portfolio_summary', 'Portfolio Summary', 'Every project with status, progress, inclusion, uptime and budget.',
                     'Portfolio Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR, R.UNDP_DONOR), build_portfolio_summary, filters=SNAPSHOT_FILTERS,
                     method='The current position of each project matching the filters at the time of generation.'),
    ReportDefinition('rmt_anomaly_report', 'Anomaly and Data Integrity Report', 'Anomaly flags by type, vendor and district with severity and status, plus duplicate, GPS and meter data checks.',
                     'Anomaly Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR), build_anomaly_integrity,
                     method='Anomaly flags raised in the period on projects matching the filters, with their current status. Duplicate and '
                            'GPS checks cover every installation in scope; meter batch checks are for batches uploaded in the period.'),
    ReportDefinition('rmt_gender_impact', 'Gender and Inclusion Report', 'Female-headed, vulnerable and low-income shares against target, by technology, district and vendor.',
                     'Portfolio Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR, R.TAC), build_gender_impact, method=INCLUSION_METHOD),
    ReportDefinition('psc_financial_summary', 'Financial Summary', 'Contracted, claimed, approved and paid amounts for PSC review.',
                     'Financial Reports', _roles(R.UNDP_DONOR), build_financial_disbursement, method=CLAIM_METHOD),
    ReportDefinition('psc_gender_impact_portfolio', 'Gender and Inclusion (Portfolio)', 'Inclusion shares against target across the portfolio.',
                     'Portfolio Reports', _roles(R.UNDP_DONOR), build_gender_impact, method=INCLUSION_METHOD),
    ReportDefinition('psc_vendor_payment_trail', 'Vendor Payment Trail', 'Claims and payments by vendor, with each claim\'s approval dates.',
                     'Financial Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL, R.AUDITOR), build_vendor_payment_trail, method=CLAIM_METHOD),
    ReportDefinition('doe_regional_progress', 'Regional Progress Report', 'Projects and installations in your districts.',
                     'Regional Reports', _roles(R.DOE_OFFICER), build_regional_progress, filters=SNAPSHOT_FILTERS,
                     method='The current position of each project in your districts at the time of generation.'),
    ReportDefinition('doe_verification_summary', 'Regional Verification Summary', 'Verification outcomes for projects in your districts.',
                     'Regional Reports', _roles(R.DOE_OFFICER), build_verification_summary, method=VERIFICATION_METHOD),
    ReportDefinition('doe_regional_kpi', 'Regional KPI Report', 'Installations, inclusion and performance in your districts.',
                     'Regional Reports', _roles(R.DOE_OFFICER), build_regional_kpi,
                     method='Installations reported in the period in your districts; uptime and energy are each project\'s latest platform figures. ' + INCLUSION_METHOD),
    ReportDefinition('doe_technology_breakdown', 'Technology Breakdown', 'Projects and installations by technology in your districts.',
                     'Regional Reports', _roles(R.DOE_OFFICER, R.RBF_OFFICIAL, R.UNDP_DONOR), build_technology_breakdown, quick=False, filters=SNAPSHOT_FILTERS,
                     method='The current position of projects in your districts, grouped by technology.'),
    ReportDefinition('doe_gender_impact', 'Regional Gender and Inclusion', 'Inclusion shares against target in your districts.',
                     'Regional Reports', _roles(R.DOE_OFFICER), build_gender_impact, quick=False, method=INCLUSION_METHOD),
    ReportDefinition('fo_verification_history', 'My Verification History', 'Every verification visit you submitted in the period.',
                     'My Reports', _roles(R.FIELD_VERIFIER), build_fo_history, filters=('period',),
                     method='Every field verification visit you submitted in the period.'),
    ReportDefinition('fo_daily_summary', 'Daily Summary', 'Visits you completed on one day, and tasks still assigned to you.',
                     'My Reports', _roles(R.FIELD_VERIFIER), build_fo_daily, filters=('period',),
                     method='The day is the end date of the period, or today when no date is chosen.'),
    ReportDefinition('fo_performance_summary', 'Performance Summary', 'Your visits, pass rate and GPS accuracy, by month.',
                     'My Reports', _roles(R.FIELD_VERIFIER), build_fo_performance, filters=('period',), method=VERIFICATION_METHOD),
    ReportDefinition('auditor_full_audit', 'Audit Trail Report', 'Every recorded action in the period, by module, with actor and change.',
                     'Audit Reports', _roles(R.AUDITOR), build_full_audit, filters=('period',),
                     method='Every audit-log entry recorded in the period, newest first, exactly as stored.'),
    ReportDefinition('auditor_data_integrity', 'Data Integrity Report', 'Duplicate, missing and inconsistent records across the platform.',
                     'Audit Reports', _roles(R.AUDITOR, R.RBF_OFFICIAL), build_data_integrity, filters=(),
                     method='Checks run across the whole database at the time of generation. "Review" means at least one record needs attention.'),
    ReportDefinition('auditor_prospect_sync', 'Prospect Sync Audit', 'Prospect integration sync attempts and failures in the period.',
                     'Audit Reports', _roles(R.AUDITOR, R.RBF_OFFICIAL), build_prospect_sync, filters=('period',),
                     method='Every Prospect integration sync attempt recorded in the period, with its outcome.'),
    # --- Phase 2 -----------------------------------------------------------------------
    ReportDefinition('programme_results', 'Programme Results Report', 'Results framework: baseline, target and actual for each indicator, with inclusion by district and technology.',
                     'Programme Reports', _roles(R.RBF_OFFICIAL, R.UNDP_DONOR, R.AUDITOR), build_results,
                     formal=True,
                     method='Actuals are measured from platform records up to the end of the period ("to date") and within it ("in period"). '
                            'Baselines and targets are those entered by the Super Admin under Results Framework. % of target = '
                            '(actual - baseline) / (target - baseline). ' + INCLUSION_METHOD),
    ReportDefinition('rmt_claims_pipeline', 'Claims Pipeline and Ageing', 'Every open claim, the step it is waiting for, and how long it has waited.',
                     'Financial Reports', _roles(R.RBF_OFFICIAL, R.UNDP_DONOR, R.AUDITOR), build_claims_pipeline, filters=SNAPSHOT_FILTERS,
                     method='Open claims are those not yet paid or rejected. Time in stage runs from the audit-log record of the last approval '
                            '(or submission) to now. Average days to paid covers every paid claim in scope.'),
    ReportDefinition('psc_briefing', 'PSC Briefing', 'Results, payments, decisions needed, open risks, audit findings and procurement, for the PSC meeting.',
                     'Programme Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL), build_psc_briefing,
                     formal=True,
                     method='Money is for claims submitted in the period. Decisions needed are claims endorsed by TAC and awaiting PSC approval. '
                            'Risks are open flagged or delayed oversight reviews; audit findings are major or critical cases shared with management.'),
    ReportDefinition('psc_financial_delivery', 'Financial Delivery Report', 'Programme budget, commitments under approved contracts, claims and payments, by tender and technology.',
                     'Financial Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL, R.AUDITOR), build_financial_delivery,
                     formal=True,
                     method='Budget is the national programme budget in Platform Configuration. Committed is the award value of approved or '
                            'closed contracts for projects in scope. ' + CLAIM_METHOD),
    ReportDefinition('auditor_payment_chain_audit', 'Payment Chain Audit', 'Each claim through RMT, TAC, PSC and payment, with who acted when, and every exception.',
                     'Audit Reports', _roles(R.AUDITOR), build_payment_chain,
                     method='Each step is taken from the audit log. Exceptions: a step the claim status implies but the log does not show; '
                            'steps out of order; one person approving more than one step; a step recorded by an unexpected role; '
                            'a claim paid without a recorded PSC approval.'),
    ReportDefinition('auditor_reconciliation', 'Claim and Payment Reconciliation', 'Milestone amount, claimed amount and disbursed amount for every claim, with differences.',
                     'Audit Reports', _roles(R.AUDITOR), build_reconciliation,
                     method='Compares each claim with its milestone amount and its disbursement record; differences of more than LSL 0.50 are reported.'),
    ReportDefinition('auditor_kpi_compliance_audit', 'KPI Compliance Audit', 'Whether each claimed milestone met its conditions at the time it was claimed.',
                     'Audit Reports', _roles(R.AUDITOR), build_kpi_compliance,
                     method='For each claim past submission: verified installations at the claim date against the milestone\'s required share, '
                            'whether the previous milestone was cleared before the claim, and whether a meter data batch uploaded before the '
                            'claim is now flagged or awaiting correction.'),
    ReportDefinition('auditor_red_flags', 'Red-flag Report', 'Fraud and quality signals by vendor: duplicates, GPS mismatches, failed visits, re-verification, rejections and anomalies.',
                     'Audit Reports', _roles(R.AUDITOR, R.RBF_OFFICIAL), build_red_flags,
                     method='Duplicates cover all installations in scope; visits and GPS mismatches are those in the period. A vendor counts a '
                            'signal for each indicator above zero, and for a failed-visit rate above 20%.'),
    ReportDefinition('auditor_findings_tracker', 'Audit Findings Tracker', 'Audit cases, findings, management responses and corrective actions, with overdue actions.',
                     'Audit Reports', _roles(R.AUDITOR), build_findings_tracker, filters=('period',),
                     method='Audit cases opened in the period. A corrective action is overdue when its due date has passed and it is still open or in progress.'),
    ReportDefinition('tac_technical_performance', 'Technical Performance Report', 'Uptime, energy delivered and meter data health by project.',
                     'Technical Reports', _roles(R.TAC, R.RBF_OFFICIAL), build_technical_performance,
                     method='From smart-meter readings recorded in the period. Uptime below 95% is flagged. Meter batches needing review are '
                            'flagged or awaiting correction.'),
    ReportDefinition('tac_claims_awaiting_endorsement', 'Claims Awaiting TAC Endorsement', 'Claims approved by RMT and waiting for TAC, with the evidence behind each.',
                     'Technical Reports', _roles(R.TAC, R.RBF_OFFICIAL), build_claims_awaiting_endorsement, filters=SNAPSHOT_FILTERS,
                     method='Claims in RMT Approved status now. Verified % compares verified installations today with the project target.'),
    ReportDefinition('doe_monitoring_visits', 'Monitoring Visit Report', 'DoE site visits in the period, observations and follow-ups.',
                     'Regional Reports', _roles(R.DOE_OFFICER, R.RBF_OFFICIAL, R.UNDP_DONOR), build_monitoring_visits,
                     method='Site monitoring visits dated within the period, for projects in scope.'),
    ReportDefinition('fo_route_list', 'Assignment and Route List', 'Installations waiting for your visit, with location and contact, by district.',
                     'My Reports', _roles(R.FIELD_VERIFIER), build_route_list, filters=(),
                     method='Verification tasks assigned to you or in your area that are pending, partial or need re-verification, now.'),
    ReportDefinition('vendor_claim_statement', 'Claim Statement', 'Your claims with status, approval dates, payments and reviewer remarks.',
                     'My Reports', _roles(R.VENDOR), build_vendor_claim_statement, filters=('period', 'district', 'technology', 'tender'),
                     method=CLAIM_METHOD),
    ReportDefinition('vendor_installations', 'Installation and Verification Status', 'Your installations with their latest field verification result.',
                     'My Reports', _roles(R.VENDOR), build_vendor_installations, filters=('period', 'district', 'technology', 'tender'),
                     method='Installations reported in the period, with the outcome of their most recent field verification visit.'),
    # --- Phase 4 -----------------------------------------------------------------------
    ReportDefinition('rmt_procurement_pack', 'Procurement Pack', 'Tender summary, plan against award, contract register, challenges log and debarment register.',
                     'Procurement Reports', _roles(R.RBF_OFFICIAL, R.AUDITOR), build_procurement_pack, formats=('pdf', 'excel'),
                     filters=('period', 'tender'), quick=False,
                     method=PROCUREMENT_METHOD),
    ReportDefinition('psc_procurement_oversight', 'Procurement Oversight Summary', 'Tenders, awards, challenges, unsuccessful bids and contract status.',
                     'Procurement Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL), build_procurement_oversight, filters=('period', 'tender'),
                     method=PROCUREMENT_METHOD),
    ReportDefinition('tac_technical_evaluation', 'Technical Evaluation Report', 'For one tender: committee, conflicts declared, scores by criterion and evaluator, ranking and award recommendations.',
                     'Procurement Reports', _roles(R.TAC, R.RBF_OFFICIAL, R.AUDITOR), build_technical_evaluation, formats=('pdf', 'excel'),
                     filters=('tender',), requires_tender=True,
                     method='Submitted evaluations of the chosen tender. Each bid\'s technical score is the average of its evaluators\' totals; '
                            'the ranking is within each lot.'),
    ReportDefinition('auditor_procurement_compliance', 'Procurement Compliance Audit', 'Per tender: publication approval, committee, conflict-of-interest, scoring, standstill, intent approval and challenges.',
                     'Audit Reports', _roles(R.AUDITOR), build_procurement_compliance, filters=('period', 'tender'),
                     method='Tests every tender open in the period against the Public Procurement Regulations 2025 steps recorded on the platform. '
                            'Evaluation checks apply once a tender reaches evaluation; award checks once an award is confirmed.'),
    ReportDefinition('ec_my_score_sheet', 'My Evaluation Score Sheet', 'Your scores, justifications and conflict-of-interest attestations, per tender.',
                     'My Reports', _roles(R.EVALUATION_COMMITTEE), build_my_score_sheet, formats=('pdf', 'excel'), filters=('tender',),
                     method='Every evaluation you recorded on tenders you are assigned to, draft or submitted.'),
    ReportDefinition('oversight_followup_tracker', 'Oversight and Audit Follow-up Tracker', 'Open DoE, PSC and TAC follow-ups, monitoring-visit actions and audit corrective actions, with owner, due date and age.',
                     'Oversight Reports', _roles(R.RBF_OFFICIAL, R.UNDP_DONOR, R.DOE_OFFICER, R.AUDITOR), build_followup_tracker,
                     formats=('excel', 'pdf', 'csv'), filters=SNAPSHOT_FILTERS,
                     method='Oversight reviews and monitoring visits whose follow-up is open or in progress, and audit corrective actions that '
                            'are open or in progress on cases shared with management, now. Overdue means the due date has passed.'),
    ReportDefinition('psc_risk_issue_log', 'Risk and Issue Log', 'Flagged and delayed reviews, major audit findings, severe anomalies, held claims and open challenges.',
                     'Programme Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL), build_risk_log,
                     method='See the note in the report for which items are limited to the period.'),
    ReportDefinition('psc_decisions_log', 'Decisions and Actions Log', 'PSC decisions recorded on the platform and PSC directives with their follow-up.',
                     'Programme Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL, R.AUDITOR), build_decisions_log, filters=('period',),
                     method='Actions recorded in the period by Project Steering Committee members, and oversight reviews they raised.'),
    ReportDefinition('rmt_vendor_scorecard', 'Vendor Performance Scorecard', 'Vendors ranked on delivery, verification pass rate, uptime, inclusion and open issues.',
                     'Portfolio Reports', _roles(R.RBF_OFFICIAL, R.TAC, R.UNDP_DONOR, R.AUDITOR), build_vendor_scorecard,
                     method='See the scoring note in the report. The weights are provisional until the programme team confirms them.'),
    ReportDefinition('tac_gender_oversight', 'Gender KPI Oversight', 'Inclusion against each project\'s contracted targets, and the vendors that need a corrective action plan.',
                     'Technical Reports', _roles(R.TAC, R.RBF_OFFICIAL, R.UNDP_DONOR), build_gender_oversight, filters=SNAPSHOT_FILTERS,
                     method=INCLUSION_METHOD.replace('whose installation was reported in the period', 'to date')),
    ReportDefinition('psc_regional_impact', 'Regional Impact Report', 'Access, inclusion, budget and payments by district, and installations by district and technology.',
                     'Programme Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL, R.DOE_OFFICER), build_regional_impact, formats=('excel', 'pdf', 'csv'),
                     method='Verified installations to date and in the period, by the district where they were captured. ' + INCLUSION_METHOD),
    ReportDefinition('psc_budget_utilisation', 'Budget Utilisation', 'Committed, disbursed and remaining by funding source, tender and lot, against the programme budget.',
                     'Financial Reports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL, R.AUDITOR), build_budget_utilisation,
                     method='Committed is the award value of approved or closed contracts for projects in scope. Disbursed counts paid claims '
                            '(Completed and legacy Paid) submitted up to the end of the period.'),
    ReportDefinition('programme_annual_report', 'Annual and Final Progress Report', 'Results framework with baseline, target and actual, households reached by sex, and breakdowns by type, technology and district.',
                     'Programme Reports', _roles(R.RBF_OFFICIAL, R.UNDP_DONOR, R.AUDITOR), build_annual_report, formal=True, formats=('pdf', 'excel'),
                     method='Run for the year (or the whole programme for the final report). Actuals are measured from platform records; '
                            'baselines and targets come from the Results Framework. ' + INCLUSION_METHOD),
    ReportDefinition('doe_national_access', 'National Access Statistics', 'The programme\'s verified new connections by technology and district, for national SDG 7 reporting.',
                     'Regional Reports', _roles(R.DOE_OFFICER, R.RBF_OFFICIAL, R.UNDP_DONOR), build_national_access, formats=('excel', 'pdf', 'csv'),
                     method='Verified installations to date and in the period. One verified installation is one household or site with new access.'),
    ReportDefinition('vendor_compliance_notices', 'Compliance Notices and Corrective Actions', 'Anomalies to resolve, meter data to correct, inclusion plans needed and returned claims.',
                     'My Reports', _roles(R.VENDOR), build_vendor_compliance, filters=('period', 'district', 'technology', 'tender'),
                     method='Open items on your projects now; returned claims are those submitted in the period.'),
    ReportDefinition('rmt_energy_output_export', 'Energy Output Export', 'Every accepted smart-meter reading in the period, by installation, with a project summary.',
                     'Technical Reports', _roles(R.RBF_OFFICIAL, R.TAC, R.AUDITOR, R.VENDOR), build_energy_export, formats=('csv', 'excel'),
                     method='Accepted readings recorded in the period. The CSV contains the readings; Excel adds the project summary.'),
    ReportDefinition('tac_meter_exceptions', 'Meter Data Exceptions', 'Readings failing integrity checks or rejected, and the findings on each uploaded batch.',
                     'Technical Reports', _roles(R.TAC, R.RBF_OFFICIAL, R.AUDITOR), build_meter_exceptions, formats=('excel', 'pdf', 'csv'),
                     method='Readings recorded in the period with at least one integrity check raised or a rejected review, and batches uploaded in the period.'),
    ReportDefinition('site_register_gis', 'Site Register and GIS Export', 'Every installation with location, technology, status and last field verification, as CSV, Excel or GeoJSON.',
                     'Portfolio Reports', _roles(R.RBF_OFFICIAL, R.DOE_OFFICER, R.TAC, R.AUDITOR, R.UNDP_DONOR), build_site_register,
                     formats=('csv', 'geojson', 'excel'), renderers={'geojson': render_geojson},
                     method='Installations reported in the period on projects in scope. GeoJSON opens directly in QGIS, ArcGIS and web maps.'),
    ReportDefinition('rmt_beneficiary_export', 'Beneficiary Data Export', 'Beneficiary identity, contact, sex, household type and location. Requires a stated reason, which is logged.',
                     'Data Exports', _roles(R.RBF_OFFICIAL, R.AUDITOR), build_beneficiary_export, formats=('csv', 'excel'), quick=False,
                     filters=PROJECT_FILTERS + ('reason',), requires_reason=True,
                     method='Installations reported in the period. Sex is as recorded at the latest field verification.'),
    ReportDefinition('donor_iati_export', 'Donor Data Export (IATI)', 'Activity, results and disbursements aligned to the IATI Activity Standard 2.03.',
                     'Data Exports', _roles(R.UNDP_DONOR, R.RBF_OFFICIAL), build_iati_export, formats=('excel', 'xml'), filters=('period',),
                     renderers={'xml': render_iati_xml},
                     method='Disbursements are paid results-based claims submitted in the period; results come from the Results Framework.'),
    ReportDefinition('auditor_project_package', 'Project Audit Package', 'One ZIP per project: lifecycle dossier, installations, verification log, meter readings, claims, disbursements, anomalies and audit log.',
                     'Audit Reports', _roles(R.AUDITOR, R.RBF_OFFICIAL), build_project_package, formats=('zip',), requires_project=True, filters=(),
                     quick=False, renderers={'zip': render_audit_package},
                     method='Every record for the project at the time of generation. MANIFEST.txt lists each file with its SHA-256 checksum.'),
    ReportDefinition('auditor_system_access', 'System Access Report', 'Sign-ins, failed sign-ins and account and permission changes.',
                     'Audit Reports', _roles(R.AUDITOR), build_system_access, filters=('period',),
                     method='From the audit log for the period.'),
    ReportDefinition('admin_report_usage', 'Report Usage and Download Log', 'Who generated, downloaded, signed off and shared which reports.',
                     'Audit Reports', _roles(R.AUDITOR), build_report_usage, filters=('period',), formats=('csv', 'excel', 'pdf'),
                     method='Report actions recorded in the audit log for the period.'),
]}


def definitions_for(user) -> list[ReportDefinition]:
    role = getattr(user, 'role', None)
    if role == R.ADMIN:
        return list(REGISTRY.values())
    return [d for d in REGISTRY.values() if role in d.roles]


def definition_for(user, report_id: str) -> ReportDefinition:
    definition = REGISTRY.get(report_id)
    if definition is None:
        raise ValidationError({'report_type': 'This report is not available.'})
    if getattr(user, 'role', None) != R.ADMIN and getattr(user, 'role', None) not in definition.roles:
        raise PermissionDenied('This report is not available to your role.')
    return definition
