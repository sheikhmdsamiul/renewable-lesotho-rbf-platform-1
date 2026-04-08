import base64
import html
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils import timezone

from rbf.projects.models import Milestone, Project
from rbf.users.models import PrequalificationStatus, VendorPrequalification

logger = logging.getLogger(__name__)


PBA_DISBURSEMENT_PLAN = (
    ("Mobilization", 20, "Signed field survey, executed agreement, and mobilization readiness confirmation."),
    ("Installation", 50, "Installed system evidence pack, geo-tagged QA logs, and commissioning acceptance."),
    ("Performance", 30, "Smart meter data sync, beneficiary validation, and final performance verification."),
)

ANNEX_SECTION_SPECS = (
    ("annex_a_file", "Annex A", "Results Framework", "Mapped from the awarded Gender Action Plan."),
    ("annex_b_file", "Annex B", "Implementation Schedule", "Mapped from the awarded Vendor Implementation Plan."),
    ("annex_c_file", "Annex C", "Payment Terms", "Includes the BOQ and generated disbursement table."),
    ("annex_d_file", "Annex D", "Reporting Formats", "Includes standardized system reporting templates."),
    ("annex_e_file", "Annex E", "Technical Standards", "Mapped from the awarded Technical Proposal."),
)


@dataclass
class AnnexPart:
    field_name: str
    label: str
    title: str
    description: str
    source_path: Path | None


def _svg_data_uri(svg_markup: str) -> str:
    encoded = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _brand_logo_data_uri(left: bool) -> str:
    if left:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="320" height="72" viewBox="0 0 320 72">
          <rect width="320" height="72" rx="14" fill="#0f4c5c"/>
          <rect x="14" y="14" width="44" height="44" rx="12" fill="#ffffff" opacity="0.18"/>
          <circle cx="36" cy="36" r="15" fill="#8ecae6"/>
          <path d="M36 18 L42 36 L36 54 L30 36 Z" fill="#ffffff"/>
          <text x="72" y="30" font-size="17" font-family="Inter, Roboto, Arial, sans-serif" font-weight="700" fill="#ffffff">Renewable Lesotho</text>
          <text x="72" y="50" font-size="11" font-family="Inter, Roboto, Arial, sans-serif" fill="#d7eef6">Results-Based Financing Digital Platform</text>
        </svg>
        """
    else:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="336" height="72" viewBox="0 0 336 72">
          <rect width="336" height="72" rx="14" fill="#123b64"/>
          <rect x="16" y="16" width="42" height="40" rx="8" fill="#ffffff"/>
          <rect x="22" y="22" width="8" height="28" fill="#ef476f"/>
          <rect x="34" y="22" width="8" height="28" fill="#ffd166"/>
          <text x="72" y="30" font-size="16" font-family="Inter, Roboto, Arial, sans-serif" font-weight="700" fill="#ffffff">Department of Energy / UNDP</text>
          <text x="72" y="50" font-size="11" font-family="Inter, Roboto, Arial, sans-serif" fill="#dce7f5">Contracting authority and programme oversight</text>
        </svg>
        """
    return _svg_data_uri(" ".join(line.strip() for line in svg.splitlines()))


def _format_date(value) -> str:
    if not value:
        return "N/A"
    if hasattr(value, "strftime"):
        return value.strftime("%B %d, %Y")
    return str(value)


def _format_money(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"LSL {amount:,.2f}"


def _safe(value) -> str:
    return html.escape(str(value or ""))


def _payment_rows(total_award) -> list[dict]:
    total = Decimal(str(total_award or 0))
    rows = []
    running = Decimal("0.00")
    for index, (name, pct, verification) in enumerate(PBA_DISBURSEMENT_PLAN):
        if index < len(PBA_DISBURSEMENT_PLAN) - 1:
            amount = (total * Decimal(pct) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            running += amount
        else:
            amount = (total - running).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append(
            {
                "name": name,
                "percentage": f"{pct}%",
                "amount": _format_money(amount),
                "verification": verification,
            }
        )
    return rows


def _project_milestone_rows(project: Project | None, total_award) -> list[dict]:
    if not project:
        return _payment_rows(total_award)

    milestones = list(project.milestones.order_by("id"))
    if not milestones:
        return _payment_rows(total_award)

    rows = []
    for milestone in milestones:
        verification = _verification_requirement_for_milestone(milestone)
        rows.append(
            {
                "name": milestone.name or "Milestone",
                "percentage": f"{int(milestone.percentage or 0)}%",
                "amount": _format_money(milestone.amount or 0),
                "verification": verification,
            }
        )
    return rows


def _verification_requirement_for_milestone(milestone: Milestone) -> str:
    name = (milestone.name or "").strip().lower()
    if "mobil" in name:
        return "Signed field survey, mobilization readiness checklist, and authorized notice to proceed."
    if "install" in name:
        return "Installation log, geo-tagged photos, QA sign-off, and commissioning checklist."
    if "perform" in name or "commission" in name:
        return "Smart meter data sync, beneficiary validation, and final performance verification."
    return milestone.description or "Verification evidence to be confirmed by the RBF contract administrator."


def _reporting_template_rows() -> list[dict]:
    return [
        {
            "template": "Monthly Progress Brief",
            "purpose": "Narrative progress update, milestone risks, and implementation blockers.",
            "minimum_fields": "Reporting month, milestone status, workforce deployed, issues, mitigation actions.",
        },
        {
            "template": "Field Installation Log",
            "purpose": "Site-by-site deployment evidence submitted by the vendor.",
            "minimum_fields": "Site ID, GPS coordinates, beneficiary ID, serial number, installer, photo references.",
        },
        {
            "template": "Beneficiary Verification Sheet",
            "purpose": "Tracks social inclusion commitments and beneficiary sign-off.",
            "minimum_fields": "Household details, gender marker, vulnerability category, consent signature, verification date.",
        },
    ]


def _resolve_social_commitments(vendor) -> dict:
    approved_prequal = (
        VendorPrequalification.objects.filter(
            vendor=vendor,
            status=PrequalificationStatus.APPROVED,
        )
        .order_by("-submitted_at")
        .first()
    )
    female_target = approved_prequal.female_beneficiary_target if approved_prequal else 50
    vulnerable_target = approved_prequal.vulnerable_group_target if approved_prequal else 30
    return {
        "female_target": female_target,
        "vulnerable_target": vulnerable_target,
        "summary": (
            f"At least {female_target}% female-headed households and "
            f"{vulnerable_target}% vulnerable beneficiary inclusion."
        ),
    }


def _resolve_target_installations(bid) -> int:
    try:
        bid_sites = list(bid.sites.all())
    except Exception:
        bid_sites = []

    units_total = 0
    bid_config = getattr(bid, "system_configuration", {}) or {}
    if isinstance(bid_config, dict):
        for key in ("units", "unit_count", "systems", "total_units", "installation_target"):
            if key in bid_config and isinstance(bid_config[key], (int, float)):
                units_total += int(bid_config[key])
                break

    for site in bid_sites:
        households = getattr(site, "number_of_households", 0) or 0
        if households:
            units_total += int(households)
            continue
        config = getattr(site, "system_configuration", {}) or {}
        if not isinstance(config, dict):
            continue
        for key in ("units", "unit_count", "systems", "total_units"):
            if key in config and isinstance(config[key], (int, float)):
                units_total += int(config[key])
                break

    if units_total > 0:
        return units_total
    return len(bid_sites)


def _header_template(contract_reference: str) -> str:
    left_logo = _brand_logo_data_uri(True)
    right_logo = _brand_logo_data_uri(False)
    return f"""
    <div style="width:100%;padding:0 24px 6px 24px;font-size:10px;color:#334155;">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #cbd5e1;padding-bottom:10px;">
        <img src="{left_logo}" style="height:40px;" />
        <img src="{right_logo}" style="height:40px;" />
      </div>
      <div style="margin-top:5px;font-family:Inter,Roboto,Arial,sans-serif;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;">
        Performance-Based Agreement · {html.escape(contract_reference)}
      </div>
    </div>
    """


def _footer_template(contract_reference: str) -> str:
    return f"""
    <div style="width:100%;padding:0 24px 12px 24px;font-family:Inter,Roboto,Arial,sans-serif;font-size:9px;color:#475569;">
      <div style="border-top:1px solid #cbd5e1;padding-top:6px;display:flex;justify-content:space-between;align-items:center;">
        <div>Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>
        <div>Contract Ref: {html.escape(contract_reference)}</div>
        <div>Initial here: ____________________</div>
      </div>
    </div>
    """


def _base_html(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        @page {{
          size: A4;
          margin: 0;
        }}
        body {{
          margin: 0;
          font-family: Inter, Roboto, Arial, Helvetica, sans-serif;
          color: #0f172a;
          background: #ffffff;
        }}
        .page {{
          padding: 108px 52px 88px 52px;
          box-sizing: border-box;
        }}
        h1, h2, h3 {{
          margin: 0;
        }}
        h1 {{
          font-size: 24px;
          letter-spacing: -0.02em;
        }}
        h2 {{
          font-size: 16pt;
          margin-bottom: 12px;
          color: #0f172a;
        }}
        h3 {{
          font-size: 12pt;
          margin-bottom: 8px;
          color: #1e293b;
        }}
        p, li, td, th, span, div {{
          font-size: 10pt;
          line-height: 1.5;
        }}
        .eyebrow {{
          text-transform: uppercase;
          letter-spacing: 0.18em;
          font-size: 9px;
          color: #64748b;
          font-weight: 700;
          margin-bottom: 12px;
        }}
        .hero {{
          border: 1px solid #cbd5e1;
          border-radius: 18px;
          padding: 28px;
          background: linear-gradient(145deg, #f8fafc 0%, #eef6ff 52%, #ffffff 100%);
          margin-bottom: 24px;
        }}
        .section {{
          margin-top: 24px;
        }}
        .table {{
          width: 100%;
          border-collapse: collapse;
          margin-top: 12px;
        }}
        .table th {{
          background: #0f172a;
          color: white;
          text-align: left;
          font-weight: 700;
          padding: 10px 12px;
        }}
        .table td {{
          border: 1px solid #cbd5e1;
          padding: 10px 12px;
          vertical-align: top;
        }}
        .summary-grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-top: 16px;
        }}
        .summary-card {{
          border: 1px solid #dbe5f0;
          border-radius: 14px;
          padding: 14px;
          background: #ffffff;
        }}
        .summary-label {{
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: #64748b;
          font-weight: 700;
          margin-bottom: 6px;
        }}
        .summary-value {{
          font-size: 13px;
          font-weight: 700;
          color: #0f172a;
        }}
        .meta-grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-top: 18px;
        }}
        .meta-box {{
          border: 1px solid #dbe5f0;
          border-radius: 12px;
          padding: 14px 16px;
          background: rgba(255,255,255,0.78);
        }}
        .clause-box {{
          border-left: 4px solid #0f4c5c;
          background: #f8fafc;
          padding: 14px 16px;
          margin-top: 16px;
        }}
        .signature-grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 18px;
          margin-top: 16px;
        }}
        .signature-card {{
          border: 1px solid #cbd5e1;
          border-radius: 14px;
          padding: 18px;
          min-height: 210px;
        }}
        .field-label {{
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: #64748b;
          font-weight: 700;
          margin-top: 14px;
        }}
        .line {{
          border-bottom: 1px solid #94a3b8;
          height: 24px;
          margin-top: 8px;
        }}
        .muted {{
          color: #64748b;
        }}
        .annex-hero {{
          border: 1px solid #bfdbfe;
          background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
          border-radius: 18px;
          padding: 24px;
        }}
        .pill {{
          display: inline-block;
          border-radius: 999px;
          padding: 6px 10px;
          background: #dbeafe;
          color: #1d4ed8;
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.14em;
          font-weight: 700;
          margin-bottom: 12px;
        }}
      </style>
      <title>{html.escape(title)}</title>
    </head>
    <body>{body}</body>
    </html>
    """


def _main_agreement_html(contract, tender, bid, vendor, project) -> str:
    tech_type = (project.tech_type if project else "") or (
        tender.technology_types[0] if isinstance(tender.technology_types, list) and tender.technology_types else tender.category
    )
    total_award = bid.bid_amount or tender.budget or 0
    project_location = ", ".join(
        part for part in [
            project.region if project else "",
            project.district if project else "",
        ] if part
    ) or vendor.region or tender.department or "Lesotho"
    vendor_signatory_name = vendor.full_name or vendor.organization_name or vendor.username or "Authorized representative"
    vendor_signatory_title = vendor.organization_type or "Vendor Authorized Signatory"
    authority_signatory_title = "RBF Authorized Signatory"
    project_reference = (project.project_reference if project else "") or f"PRJ-{tender.reference_number}-{contract.vendor_id}"
    social_commitments = _resolve_social_commitments(vendor)
    project_summary = [
        ("Project Title", tender.name),
        ("Vendor Organization", vendor.organization_name or vendor.full_name or vendor.username),
        ("Technology Type", tech_type or "N/A"),
        ("Award Value", _format_money(total_award)),
    ]
    payment_rows = _project_milestone_rows(project, total_award)
    target_installations = _resolve_target_installations(bid)
    standard_terms = tender.instruction or tender.bidders_eligibility or "Standard RBF terms and reporting obligations apply."

    summary_html = "".join(
        f"""
        <div class="summary-card">
          <div class="summary-label">{_safe(label)}</div>
          <div class="summary-value">{_safe(value)}</div>
        </div>
        """
        for label, value in project_summary
    )

    payment_rows_html = "".join(
        f"""
        <tr>
          <td>{_safe(row['name'])}</td>
          <td>{_safe(row['percentage'])}</td>
          <td>{_safe(row['amount'])}</td>
          <td>{_safe(row['verification'])}</td>
        </tr>
        """
        for row in payment_rows
    )

    return _base_html(
        "Performance-Based Agreement",
        f"""
        <div class="page">
          <div class="hero">
            <div class="eyebrow">Performance-Based Agreement</div>
            <h1>Renewable Lesotho Results-Based Financing Agreement</h1>
            <p class="muted" style="margin-top:10px;">
              Contract Reference ID: <strong>{_safe(contract.reference_number)}</strong><br/>
              Tender Reference: <strong>{_safe(tender.reference_number)}</strong><br/>
              Effective Award Date: <strong>{_safe(_format_date(tender.awarded_at or timezone.now()))}</strong>
            </p>
            <div class="meta-grid">
              <div class="meta-box">
                <div class="summary-label">Parties</div>
                <div>
                  Renewable Lesotho Results-Based Financing Platform acting through the Department of Energy<br/>
                  and<br/>
                  <strong>{_safe(vendor.organization_name or vendor.full_name or vendor.username)}</strong>
                </div>
              </div>
              <div class="meta-box">
                <div class="summary-label">Contract Scope</div>
                <div>
                  Project Reference: <strong>{_safe(project_reference)}</strong><br/>
                  Technology: <strong>{_safe(tech_type or 'N/A')}</strong><br/>
                  Contract Value: <strong>{_format_money(total_award)}</strong>
                </div>
              </div>
            </div>
            <div class="summary-grid">{summary_html}</div>
          </div>

          <div class="section">
            <h2>1. Agreement Overview</h2>
            <p>
              This Performance-Based Agreement ("PBA") is entered into between the Renewable Lesotho Results-Based Financing
              programme acting through the Department of Energy and the Vendor named above for delivery of awarded renewable energy installations.
            </p>
            <div class="clause-box">
              The awarded bid documents and the annex package attached to this agreement form a legally binding contract set. The vendor may not commence physical implementation work until the signed package is reviewed and the contract is formally finalized by the RBF authority.
            </div>
          </div>

          <div class="section">
            <h2>2. Project Summary</h2>
            <table class="table">
              <tr><th>Field</th><th>Value</th></tr>
              <tr><td>Tender Name</td><td>{_safe(tender.name)}</td></tr>
              <tr><td>Vendor Organization</td><td>{_safe(vendor.organization_name or vendor.full_name or vendor.username)}</td></tr>
              <tr><td>Technology Type</td><td>{_safe(tech_type or 'N/A')}</td></tr>
              <tr><td>Total Subsidy Amount</td><td>{_format_money(total_award)}</td></tr>
              <tr><td>Project Reference</td><td>{_safe(project_reference)}</td></tr>
              <tr><td>Target Installations</td><td>{_safe(target_installations or 'N/A')}</td></tr>
              <tr><td>Region / District</td><td>{_safe(project_location)}</td></tr>
              <tr><td>Social Inclusion Commitments</td><td>{_safe(social_commitments['summary'])}</td></tr>
            </table>
          </div>

          <div class="section">
            <h2>3. Core Performance Obligations</h2>
            <p>{_safe(standard_terms)}</p>
            <div class="clause-box">
              Tender-derived terms incorporated into this agreement include the project title, technology type, implementation geography,
              and the standard tender obligations. Award-derived commercial terms include the proposed subsidy amount, total installation
              targets, and the vendor's social inclusion commitments. System-derived control terms include the contract reference identifier
              and the 20/50/30 disbursement schedule.
            </div>
            <p>
              The Vendor shall deliver the approved implementation schedule, maintain required reporting formats, meet technical standards, and satisfy all verification conditions linked to disbursement.
            </p>
            <p>
              This document package is issued as the professional contract record for the awarded tender and is intended for archival retention in PDF/A form after generation.
            </p>
          </div>

          <div class="section">
            <h2>4. Award Data & Inclusion Commitments</h2>
            <table class="table">
              <tr><th>Field</th><th>Value</th></tr>
              <tr><td>Contract Reference Number</td><td>{_safe(contract.reference_number)}</td></tr>
              <tr><td>Proposed Subsidy Amount</td><td>{_format_money(total_award)}</td></tr>
              <tr><td>Total Installation Targets</td><td>{_safe(target_installations or 'N/A')}</td></tr>
              <tr><td>Female-Headed Household Target</td><td>{_safe(f"{social_commitments['female_target']}%")}</td></tr>
              <tr><td>Vulnerable Group Inclusion Target</td><td>{_safe(f"{social_commitments['vulnerable_target']}%")}</td></tr>
            </table>
          </div>

          <div class="section">
            <h2>5. Annex C Disbursement Table</h2>
            <table class="table">
              <tr>
                <th>Milestone Name</th>
                <th>Percentage</th>
                <th>LSL Amount</th>
                <th>Verification Requirement</th>
              </tr>
              {payment_rows_html}
            </table>
          </div>

          <div class="section">
            <h2>6. Execution Block</h2>
            <div class="signature-grid">
              <div class="signature-card">
                <h3>RBF Authorized Signatory</h3>
                <div class="field-label">Name</div>
                <div class="line"></div>
                <div class="field-label">Title</div>
                <div class="line">{_safe(authority_signatory_title)}</div>
                <div class="field-label">Date</div>
                <div class="line"></div>
                <div class="field-label">Stamp / Seal</div>
                <div class="line"></div>
              </div>
              <div class="signature-card">
                <h3>Vendor Authorized Signatory</h3>
                <div class="field-label">Name</div>
                <div class="line">{_safe(vendor_signatory_name)}</div>
                <div class="field-label">Title</div>
                <div class="line">{_safe(vendor_signatory_title)}</div>
                <div class="field-label">Date</div>
                <div class="line"></div>
                <div class="field-label">Stamp / Seal</div>
                <div class="line"></div>
              </div>
            </div>
          </div>
        </div>
        """,
    )


def _annex_section_html(contract, annex_part: AnnexPart, total_award) -> str:
    generated_content = ""
    if annex_part.field_name == "annex_c_file":
        rows_data = _project_milestone_rows(_resolve_contract_project(contract), total_award)
        rows = "".join(
            f"""
            <tr>
              <td>{_safe(row['name'])}</td>
              <td>{_safe(row['percentage'])}</td>
              <td>{_safe(row['amount'])}</td>
              <td>{_safe(row['verification'])}</td>
            </tr>
            """
            for row in rows_data
        )
        generated_content = f"""
        <div class="section">
          <h2>Contractual Payment Terms</h2>
          <p>
            This annex records the official payment mechanics for the awarded tender package, including the bill of quantities source
            document where provided and the system-generated milestone disbursement grid used for administration of the 20/50/30 schedule.
          </p>
        </div>
        <div class="section">
          <h3>Generated Disbursement Table</h3>
          <table class="table">
            <tr>
              <th>Milestone Name</th>
              <th>Percentage</th>
              <th>LSL Amount</th>
              <th>Verification Requirement</th>
            </tr>
            {rows}
          </table>
        </div>
        """
    elif annex_part.field_name == "annex_d_file":
        rows = "".join(
            f"""
            <tr>
              <td>{_safe(row['template'])}</td>
              <td>{_safe(row['purpose'])}</td>
              <td>{_safe(row['minimum_fields'])}</td>
            </tr>
            """
            for row in _reporting_template_rows()
        )
        generated_content = f"""
        <div class="section">
          <h2>Standard Reporting Formats</h2>
          <p>
            This annex sets the minimum reporting formats that the vendor must use throughout implementation and verification, whether or not
            an awarded source template PDF was attached to the bid package.
          </p>
        </div>
        <div class="section">
          <h3>Standardized System Templates</h3>
          <table class="table">
            <tr>
              <th>Reporting Template</th>
              <th>Purpose</th>
              <th>Minimum Required Fields</th>
            </tr>
            {rows}
          </table>
        </div>
        """

    source_text = (
        f"Submitted source file: {annex_part.source_path.name}"
        if _is_mergeable_pdf(annex_part.source_path)
        else "No valid submitted source PDF was available, so the system-generated annex pages included here serve as the contractual record for this section."
    )

    return _base_html(
        f"{annex_part.label} - {annex_part.title}",
        f"""
        <div class="page">
          <div class="annex-hero">
            <div class="pill">{_safe(annex_part.label)}</div>
            <h1>{_safe(annex_part.title)}</h1>
            <p style="margin-top:12px;">{_safe(annex_part.description)}</p>
            <p class="muted" style="margin-top:10px;">{_safe(source_text)}</p>
            <p class="muted" style="margin-top:10px;">Contract Reference ID: {_safe(contract.reference_number)}</p>
          </div>
          {generated_content}
        </div>
        """,
    )


def _resolve_contract_project(contract) -> Project | None:
    project_id = getattr(contract, "project_id", "")
    if project_id:
        project = Project.objects.filter(id=project_id).first()
        if project:
            return project

    tender_id = getattr(contract, "tender_id", None)
    vendor_id = str(getattr(contract, "vendor_id", "") or "")
    if not tender_id or not vendor_id:
        return None
    return Project.objects.filter(tender_id=tender_id, vendor_id=vendor_id).order_by("-id").first()


def _resolve_source_path(contract, annex_field: str) -> Path | None:
    file_field = getattr(contract, annex_field, None)
    if not file_field:
        return None
    try:
        return Path(file_field.path)
    except Exception:
        relative_name = getattr(file_field, "name", "")
        if not relative_name:
            return None
        candidate = Path(settings.MEDIA_ROOT) / relative_name
        return candidate if candidate.exists() else None


def _is_mergeable_pdf(path: Path | None) -> bool:
    if not path or not path.exists() or path.suffix.lower() != ".pdf":
        return False
    try:
        with path.open("rb") as file_obj:
            return file_obj.read(5) == b"%PDF-"
    except Exception:
        return False


def _render_pdf(html_string: str, output_path: Path, contract_reference: str):
    script_path = Path(getattr(settings, "PBA_RENDER_SCRIPT", "")) if getattr(settings, "PBA_RENDER_SCRIPT", "") else (Path(settings.BASE_DIR) / "scripts" / "render_pdf.mjs")
    if not script_path.exists():
        raise RuntimeError(f"PDF renderer script not found: {script_path}")
    chrome_path = (
        getattr(settings, "PBA_CHROME_PATH", "")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium-browser")
        or shutil.which("chromium")
    )
    if not chrome_path:
        raise RuntimeError("Chrome/Chromium executable not found for PBA PDF generation.")

    payload = {
        "html": html_string,
        "outputPath": str(output_path),
        "chromePath": chrome_path,
        "headerTemplate": _header_template(contract_reference),
        "footerTemplate": _footer_template(contract_reference),
        "margin": {"top": "92px", "right": "36px", "bottom": "72px", "left": "36px"},
    }
    input_json = output_path.with_suffix(".json")
    input_json.write_text(json.dumps(payload), encoding="utf-8")
    subprocess.run(
        ["node", str(script_path), str(input_json)],
        cwd=settings.BASE_DIR,
        check=True,
        capture_output=True,
        text=True,
    )


def _pdfa_merge(parts: list[Path], output_path: Path):
    icc_profile = Path("/usr/share/color/icc/colord/sRGB.icc")
    pdfa_def = output_path.with_name("pdfa_def.ps")
    pdfa_def.write_text(
        f"""
/ICCProfile ({icc_profile}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} <<
/Type /OutputIntent
/S /GTS_PDFA1
/DestOutputProfile {{icc_PDFA}}
/OutputConditionIdentifier (sRGB)
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [{{OutputIntent_PDFA}}] >> /PUT pdfmark
        """.strip(),
        encoding="utf-8",
    )

    cmd = [
        "gs",
        "-dNOSAFER",
        "-dPDFA=2",
        "-dBATCH",
        "-dNOPAUSE",
        "-dNOOUTERSAVE",
        "-sDEVICE=pdfwrite",
        "-sColorConversionStrategy=RGB",
        "-sProcessColorModel=DeviceRGB",
        "-dPDFACompatibilityPolicy=1",
        f"-sOutputFile={output_path}",
        str(pdfa_def),
        *[str(part) for part in parts],
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Ghostscript PDF/A merge failed for %s; retrying with standard PDF merge. stderr=%s",
            output_path.name,
            (exc.stderr or "").strip()[:1000],
        )
        fallback_cmd = [
            "gs",
            "-dNOSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-sOutputFile={output_path}",
            *[str(part) for part in parts],
        ]
        subprocess.run(fallback_cmd, check=True, capture_output=True, text=True)


def generate_contract_pdf(contract, tender, bid, vendor, project=None):
    with tempfile.TemporaryDirectory(prefix="pba_pdf_") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        total_award = bid.bid_amount or tender.budget or 0
        project = project or _resolve_contract_project(contract)

        main_pdf = tmp_dir / "01_main_agreement.pdf"
        _render_pdf(_main_agreement_html(contract, tender, bid, vendor, project), main_pdf, contract.reference_number)

        parts: list[Path] = [main_pdf]
        for index, (field_name, label, title, description) in enumerate(ANNEX_SECTION_SPECS, start=2):
            annex_source_path = _resolve_source_path(contract, field_name)
            annex_part = AnnexPart(
                field_name=field_name,
                label=label,
                title=title,
                description=description,
                source_path=annex_source_path,
            )
            annex_pdf = tmp_dir / f"{index:02d}_{field_name}.pdf"
            _render_pdf(_annex_section_html(contract, annex_part, total_award), annex_pdf, contract.reference_number)
            parts.append(annex_pdf)
            valid_source_pdf = _is_mergeable_pdf(annex_source_path)
            if not valid_source_pdf and field_name in {"annex_c_file", "annex_d_file"}:
                with annex_pdf.open("rb") as annex_file_obj:
                    getattr(contract, field_name).save(
                        f"{contract.reference_number}_{field_name}.pdf",
                        File(annex_file_obj),
                        save=False,
                    )
            if valid_source_pdf:
                parts.append(annex_source_path)

        final_pdf = tmp_dir / f"{contract.reference_number}.pdf"
        _pdfa_merge(parts, final_pdf)

        with final_pdf.open("rb") as file_obj:
            contract.generated_file.save(f"{contract.reference_number}.pdf", File(file_obj), save=False)
