"""Generate the PSC / DoE Officer / Auditor roles manual (.docx).

Mirrors the styling and helpers used by create_rbf_official_manual.py so the
output is consistent with the existing training manual in the repository.

The content is grounded in the application source:
  - Sidebar definitions:        src/App.tsx  (getSidebarItems)
  - Role routing per sidebar:   src/App.tsx  (renderActiveTab)
  - PSC components:             src/components/PscPortal.tsx
  - DoE components:             src/components/DoePortal.tsx
  - Auditor components:         src/components/AuditorPortal.tsx
  - Shared UI:                  src/App.tsx (Disbursements, VendorDirectory,
                                ProjectsHub, Blacklisting), and
                                src/components/RoleBasedKpiPanels.tsx
                                (MacroKpiPortal), PortfolioMonitoringView.tsx
  - Backend role constants:     backend/rbf/users/models.py
  - Permission / role gates:    backend/rbf/projects/views.py and
                                backend/rbf/tenders/views.py

Run from the repository root:

    python3 create_psc_doe_audit_manual.py
"""

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = Path("PSC_DoE_Auditor_Roles_Manual.docx")


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_text(cell, text, bold=False, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text))
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    for i, header in enumerate(headers):
        set_cell_text(t.rows[0].cells[i], header, bold=True, color=(255, 255, 255))
        shade(t.rows[0].cells[i], "1F4E78")
    for idx, row in enumerate(rows):
        cells = t.add_row().cells
        for i, value in enumerate(row):
            set_cell_text(cells[i], value)
        if idx % 2 == 1:
            for cell in cells:
                shade(cell, "EAF2F8")
    if widths:
        for row in t.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = Inches(width)
    doc.add_paragraph()
    return t


def bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.add_run(text)
    return p


def number(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.add_run(text)
    return p


def callout(doc, title, text, fill="FFF2CC"):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.cell(0, 0)
    shade(cell, fill)
    p = cell.paragraphs[0]
    r = p.add_run(title + "\n")
    r.bold = True
    p.add_run(text)
    doc.add_paragraph()


def heading(doc, text, level=1):
    return doc.add_heading(text, level=level)


def page_break(doc):
    doc.add_page_break()


def add_toc(paragraph):
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "TOC \\o \"1-3\" \\h \\z \\u"
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "Right-click to update this table of contents."
    fld_char2.append(text)
    fld_char3 = OxmlElement("w:fldChar")
    fld_char3.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char1, instr, fld_char2, fld_char3])


def configure(doc):
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos")
    styles["Normal"].font.size = Pt(10)
    for name, size, color in [
        ("Title", 28, "1F4E78"),
        ("Heading 1", 18, "1F4E78"),
        ("Heading 2", 13, "2F75B5"),
        ("Heading 3", 11, "2F75B5"),
    ]:
        styles[name].font.name = "Aptos Display"
        styles[name]._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos Display")
        styles[name].font.size = Pt(size)
        styles[name].font.color.rgb = RGBColor.from_string(color)
    header = section.header.paragraphs[0]
    header.text = (
        "Renewable Lesotho RBF Platform  |  PSC, DoE & Auditor Roles Manual"
    )
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Internal training reference  |  ")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    footer._p.append(fld)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------


def role_overview(doc, heading_text, summary_paragraphs):
    heading(doc, heading_text, 1)
    for paragraph in summary_paragraphs:
        doc.add_paragraph(paragraph)


def sidebar_table(doc, rows, widths=(1.7, 5.4)):
    table(
        doc,
        ["Sidebar item", "Where it goes and what you do there"],
        rows,
        list(widths),
    )


def permission_callout(doc, allowed, denied):
    """Render an amber callout listing what the role can and cannot do."""
    lines = []
    if allowed:
        lines.append("You can: " + "; ".join(allowed) + ".")
    if denied:
        lines.append("You cannot: " + "; ".join(denied) + ".")
    callout(doc, "Role boundary", " ".join(lines), "FCE4D6")


# ---------------------------------------------------------------------------
# Content: Part 1 - PSC
# ---------------------------------------------------------------------------


def psc_part(doc):
    heading(doc, "Part 1 — Project Steering Committee (PSC / UNDP Donor)", 1)
    doc.add_paragraph(
        "The PSC is the programme steering and financial-authorization role. "
        "In the source it is the UserRole.UNDP_DONOR role, shown in the "
        "application as Project Steering Committee. PSC performs strategic "
        "oversight, gives the penultimate financial approval in the claim "
        "chain (the PSC Approved step), receives audit findings and DoE "
        "concerns escalated for direction, and can flag project-level "
        "issues."
    )
    callout(
        doc,
        "Operating principle",
        "PSC actions are recorded against the audit trail. Use the platform "
        "to read evidence, request RMT updates, add PSC directives, and "
        "approve payment only when the full chain — Submitted > RMT "
        "Approved > TAC Endorsed — is complete and the claim is eligible. "
        "Do not skip TAC or RMT stages.",
    )

    heading(doc, "PSC sidebar at a glance", 2)
    sidebar_table(
        doc,
        [
            ("Dashboard", "National portfolio KPI overview, district performance, "
                          "payment pacing, inclusion compliance and system alerts."),
            ("All Vendors", "Paginated, searchable vendor directory across all "
                           "districts; open each profile with role-based access."),
            ("Portfolio Overview", "Full project portfolio with project tabs "
                                   "(Overview, KPI, Map, Milestones, Payments, "
                                   "Documents, Updates) for read-only oversight."),
            ("Disbursements", "Claim review workspace. PSC performs the PSC "
                              "Approval step in the payment chain and may view "
                              "vendor bank details."),
            ("Issues", "Audit findings raised to PSC and DoE concerns escalated "
                       "to PSC. PSC adds directives and resolves escalated "
                       "concerns."),
            ("Briefings & Reports", "Renders the same Issues view; this is the "
                                    "briefings queue for PSC."),
            ("Briefings", "In-app notification log; click a notification to "
                          "jump to the related tender, project, prequalification "
                          "or report."),
        ],
    )

    # Sidebar-by-sidebar detail for PSC
    heading(doc, "PSC sidebar, section by section", 2)

    heading(doc, "1. Dashboard", 3)
    doc.add_paragraph(
        "Renders the MacroKpiPortal (portalType=\"psc\") from "
        "src/components/RoleBasedKpiPanels.tsx. It is the same macro KPI "
        "engine used by RMT, scoped to PSC with the title \"Project "
        "Steering Committee\" and the description \"Macro portfolio "
        "monitoring for national progress, inclusion compliance, payment "
        "pacing, and system alerts.\""
    )
    bullet(doc, "See national KPIs: progress, gender and inclusion targets, "
                "installed capacity, energy output, regional coverage.")
    bullet(doc, "See district-level rollups: verified, pending, and flagged "
                "installations.")
    bullet(doc, "See payment pacing across the portfolio and any open "
                "system alerts.")
    bullet(doc, "Drill into individual projects (via Portfolio Overview) for "
                "the underlying KPI summary.")
    permission_callout(
        doc,
        allowed=["read national KPIs, districts, pacing, alerts"],
        denied=["edit vendors, submit bids, modify claims, change project setup"],
    )

    heading(doc, "2. All Vendors", 3)
    doc.add_paragraph(
        "Renders VendorDirectory from src/App.tsx. The PSC sees the full "
        "directory titled \"All Vendors\". The directory shows "
        "organization name, district, approved technology categories, "
        "pre-qualification status, and operational standing (Active, "
        "Suspended, Blacklisted, Reinstated). PSC opens any vendor "
        "profile using its role-based access scope."
    )
    bullet(doc, "Search by vendor name, district, tag, email or username.")
    bullet(doc, "Filter visible vendors and review pre-qualification and "
                "operational standing at a glance.")
    bullet(doc, "Open a vendor profile to review projects, performance, "
                "payment history, documents, and audit trail.")
    permission_callout(
        doc,
        allowed=["read vendor directory and profiles"],
        denied=["change pre-qualification status, suspend, reinstate, "
                "initiate blacklist"],
    )

    heading(doc, "3. Portfolio Overview", 3)
    doc.add_paragraph(
        "Renders ProjectsHub with mode=\"psc\" (or mode=\"undp\"). The "
        "portfolio is read-only oversight. Available project tabs are "
        "Overview, KPI, Map, Milestones, Payments, Documents and Updates."
    )
    bullet(doc, "Overview — status, contract reference, milestone progress, "
                "claim history, audit activity and the most recent issue.")
    bullet(doc, "KPI — achievement versus targets; gender, vulnerability, "
                "low-income inclusion; at-risk flags; performance notes.")
    bullet(doc, "Map — GIS installations with verified/pending/flagged "
                "states, district and technology filters.")
    bullet(doc, "Milestones — eligibility conditions, completion status, "
                "claim history and the amount available to claim.")
    bullet(doc, "Payments — full claim chain, payment proof (reference "
                "number), holds, delays and bank-detail access controls.")
    bullet(doc, "Documents — contract, annexes and project evidence.")
    bullet(doc, "Updates — chronological activity, decisions and actor "
                "history.")
    permission_callout(
        doc,
        allowed=["review every project, KPI, milestone, payment, document "
                 "and update"],
        denied=["edit project setup, submit installations, change "
                "milestone eligibility, modify claims directly"],
    )

    heading(doc, "4. Disbursements (Claim Reviews)", 3)
    doc.add_paragraph(
        "Renders the Disbursements component (src/App.tsx) in PSC view "
        "(isPscView = role === UNDP_DONOR). This is the workspace where "
        "PSC performs the PSC Approval step in the claim chain. The "
        "normal chain is Submitted > RMT Approved > TAC Endorsed > "
        "PSC Approved > Completed (Paid)."
    )
    bullet(doc, "See every claim with project, vendor, milestone, amount, "
                "status, and the full chain of timestamps.")
    bullet(doc, "Open a TAC-Endorsed claim to review the evidence: project "
                "KPI scorecard, RMT verification, TAC technical endorsement, "
                "milestone, amount and supporting documents.")
    bullet(doc, "Click \"Approve Payment\" on a TAC-Endorsed claim to issue "
                "the PSC Approval step.")
    bullet(doc, "View vendor bank details via the masked-account disclosure. "
                "PSC sees the masked account (****1234) by default and may "
                "request full disclosure (the view_bank_details API action "
                "requires role UNDP_DONOR and the claim must be TAC-Endorsed "
                "or PSC-Approved; the request is logged to the audit trail).")
    bullet(doc, "Flag a project-level issue from a claim (payment delay, "
                "contract issue, compliance, general). The issue is routed "
                "to RMT oversight.")
    bullet(doc, "Eligibility is checked automatically: PSC cannot approve "
                "own-related or restricted-vendor claims (selectedClaimBlockedForPsc).")
    table(
        doc,
        ["Status", "PSC action"],
        [
            ("Submitted", "Read-only. Wait for RMT review."),
            ("RMT Approved", "Read-only. Wait for TAC endorsement."),
            ("TAC Endorsed", "Review evidence and approve or escalate."),
            ("PSC Approved", "Read-only. Wait for Finance / RMT to mark paid."),
            ("Completed (Paid)", "Read-only. The payment reference is the audit proof."),
            ("Rejected / Held-Audit", "Read-only. Investigate via Issues."),
        ],
        [1.8, 5.3],
    )
    callout(
        doc,
        "PSC financial discipline",
        "PSC approval does not release funds. After PSC Approval, Finance "
        "processes payment (Admin) and RMT marks the claim paid with the "
        "payment reference. Until that reference exists, the claim is not "
        "completed.",
        "FCE4D6",
    )

    heading(doc, "5. Issues", 3)
    doc.add_paragraph(
        "Renders PscIssuesView from src/components/PscPortal.tsx. Two "
        "queues are shown: Audit Findings raised to PSC and DoE Concerns "
        "escalated to PSC."
    )
    bullet(doc, "Open a finding or concern to see the source, linked "
                "project, severity, RMT investigation response and "
                "recommended action.")
    bullet(doc, "Add a PSC comment or directive. The action_taken is "
                "recorded as \"psc_directive\"; RMT is notified and the "
                "audit trail captures the exchange.")
    bullet(doc, "Mark an escalated DoE Concern as resolved when satisfied.")
    bullet(doc, "Audit Findings cannot be closed by PSC — only the Auditor "
                "can close them. PSC may resolve an audit finding via the "
        "Mark as Resolved button on escalated findings as the modal "
        "permits, but ownership remains with Audit.")
    table(
        doc,
        ["Item type", "Source", "PSC outcome"],
        [
            ("DoE Concern (escalated)", "DoE Officer raised it; ticked \"notify PSC\"",
             "Add directive, request RMT update, or mark resolved."),
            ("Audit Finding (raised to PSC)", "Auditor raised it; ticked \"notify PSC\"",
             "Add directive; close-out is owned by the Auditor."),
        ],
        [1.8, 2.6, 2.7],
    )

    heading(doc, "6. Briefings & Reports", 3)
    doc.add_paragraph(
        "Renders PscReports from src/components/PscPortal.tsx, which in "
        "turn renders PscIssuesView. Functionally this sidebar entry is "
        "the same briefings view as Issues. Use it as the canonical PSC "
        "briefings queue."
    )
    bullet(doc, "Same queues as Issues: Audit Findings raised to PSC and "
                "DoE Concerns escalated to PSC.")
    bullet(doc, "Same controls: add PSC comment, mark resolved.")

    heading(doc, "7. Briefings (notifications)", 3)
    doc.add_paragraph(
        "Renders NotificationLogs from src/App.tsx — the in-app "
        "notification feed scoped to the current PSC user."
    )
    bullet(doc, "Read event notifications: tender deadlines, claim "
                "approvals, project setup changes, vendor issues, audit "
                "findings, payment events.")
    bullet(doc, "Click a notification to navigate to the related tender, "
                "project, prequalification or report.")
    bullet(doc, "Use it as your daily attention list — do not rely on it "
                "as the only action queue; cross-check Issues, "
                "Disbursements and Portfolio Overview.")

    heading(doc, "PSC quick reference — role boundary", 2)
    table(
        doc,
        ["Capability", "PSC posture"],
        [
            ("Approve claims at the PSC Approval step",
             "Yes — only when status is TAC Endorsed."),
            ("Mark a claim as Paid",
             "No — Finance (Admin) processes; RMT marks paid."),
            ("View vendor bank details (masked)",
             "Yes — for TAC-Endorsed / PSC-Approved claims."),
            ("Reveal full bank account number",
             "Yes — explicit reveal request, logged to audit trail."),
            ("Close an Audit Finding",
             "No — only the Auditor closes findings."),
            ("Resolve an escalated DoE Concern",
             "Yes."),
            ("Initiate blacklisting",
             "No — only RMT and Auditor can initiate."),
            ("Edit vendor pre-qualification status",
             "No."),
            ("Modify project setup",
             "No."),
        ],
        [3.0, 4.1],
    )
    page_break(doc)


# ---------------------------------------------------------------------------
# Content: Part 2 - DoE Officer
# ---------------------------------------------------------------------------


def doe_part(doc):
    heading(doc, "Part 2 — DoE Officer (Department of Energy)", 1)
    doc.add_paragraph(
        "The DoE Officer is the regional field-oversight role. In the "
        "source it is the UserRole.DOE_OFFICER role, shown in the "
        "application as DoE Officer. The officer is scoped to one or more "
        "assigned districts (currentUser.district / currentUser.region) "
        "and raises concerns when projects, installations, verifications, "
        "KPIs or vendor behaviour warrant RMT or PSC attention. DoE also "
        "participates in the blacklisting workflow as a reviewer and a "
        "confirmer."
    )
    callout(
        doc,
        "Operating principle",
        "DoE concerns are the principal escalation channel from the "
        "regional level. Always describe the issue with project link, "
        "concern type and severity; tick notify RMT (always required) and "
        "tick notify PSC only for serious issues. Do not modify vendor "
        "deliverables directly.",
    )

    heading(doc, "DoE sidebar at a glance", 2)
    sidebar_table(
        doc,
        [
            ("Dashboard", "Regional overview: active projects, installations, "
                          "attention items and quick actions to map and KPIs."),
            ("All Vendors", "Vendor directory scoped to vendors in the "
                           "officer's assigned districts."),
            ("Regional Projects", "Projects assigned to the officer's region; "
                                  "the same project tabs as other oversight "
                                  "roles but filtered regionally."),
            ("Regional Monitoring", "GIS map of installations in assigned "
                                    "districts; flag a specific installation."),
            ("KPI Review", "Regional KPI performance for the assigned "
                           "region."),
            ("Blacklisting", "Review blacklist cases and confirm or reject; "
                             "DoE participates as a reviewer and confirmer."),
        ],
    )

    heading(doc, "DoE sidebar, section by section", 2)

    heading(doc, "1. Dashboard", 3)
    doc.add_paragraph(
        "Renders DoeDashboard from src/components/DoePortal.tsx. The "
        "dashboard filters projects to the districts listed on the "
        "currentUser record (userDistricts)."
    )
    bullet(doc, "Header line shows the region (e.g. \"Maseru + Berea\").")
    bullet(doc, "Summary cards — Active Projects count and total "
                "Installations across the region.")
    bullet(doc, "Projects in My Region — top 10 rows with project "
                "reference, district, vendor, progress, status, and KPI "
                "(OK if uptime ≥ 95%, LOW otherwise). Each row has a "
                "\"Raise Concern\" action.")
    bullet(doc, "Attention Items — count of projects with KPIs below "
                "target and count of unverified installations older than "
                "7 days.")
    bullet(doc, "My Concerns — your own previously raised concerns with "
                "severity and status chips.")
    bullet(doc, "Quick Actions — buttons to jump to the Regional Map, "
                "Regional KPI or Regional Projects.")
    heading(doc, "Raise Concern (from a project row)", 4)
    doc.add_paragraph(
        "Opens the concern modal. The form requires:"
    )
    bullet(doc, "Concern Type — one of KPI Issue, GPS / Location Issue, "
                "Field Verification Issue, Vendor Behaviour, Installation "
                "Quality, Data Discrepancy, or Other.")
    bullet(doc, "Severity — Low (informational, monitor only), Medium "
                "(needs attention within 7 days) or High (urgent, immediate "
                "action).")
    bullet(doc, "Description — at least 50 characters of detail.")
    bullet(doc, "Notify — RMT is always notified; tick PSC for serious "
                "issues.")
    bullet(doc, "Submit creates the concern, logs an audit entry, and "
                "notifies the selected recipients.")
    permission_callout(
        doc,
        allowed=["raise concerns (project-scoped) with type, severity and "
                 "description; notify RMT and optionally PSC"],
        denied=["approve claims, edit vendor profiles, change pre-"
                "qualification status, submit installations"],
    )

    heading(doc, "2. All Vendors", 3)
    doc.add_paragraph(
        "Renders VendorDirectory from src/App.tsx. For DoE the title is "
        "\"Regional Vendors\" and the description notes that browsing is "
        "scoped to vendors in the assigned districts."
    )
    bullet(doc, "Search vendors by name, district, tag, email or username.")
    bullet(doc, "Open a vendor profile with role-based access to review "
                "documents, projects, performance and payment history.")
    bullet(doc, "Review pre-qualification status and operational standing "
                "(Active, Suspended, Blacklisted, Reinstated).")
    permission_callout(
        doc,
        allowed=["read vendor profiles in your region"],
        denied=["change pre-qualification status, suspend, reinstate, "
                "initiate blacklist"],
    )

    heading(doc, "3. Regional Projects", 3)
    doc.add_paragraph(
        "Renders ProjectsHub with mode=\"doe\". The list is filtered to "
        "projects whose district / region matches the officer's "
        "assignedDistricts. Available tabs are the read-only oversight "
        "set: Overview, KPI, Map, Milestones, Payments, Documents and "
        "Updates."
    )
    bullet(doc, "Use the KPI tab to identify projects drifting against "
                "targets.")
    bullet(doc, "Use the Map tab to spot GPS, district or technology "
                "anomalies.")
    bullet(doc, "Use the Milestones tab to verify eligibility before any "
                "claim is approved.")
    bullet(doc, "Use the Payments tab to read the claim chain and any "
                "payment holds.")

    heading(doc, "4. Regional Monitoring (map)", 3)
    doc.add_paragraph(
        "Renders DoeRegionalMap from src/components/DoePortal.tsx. The "
        "map shows installations in the officer's districts and exposes a "
        "Gender Impact Layer toggle."
    )
    bullet(doc, "Click any installation marker to see its details.")
    bullet(doc, "Use the Gender Impact Layer toggle to overlay inclusion "
                "data when investigating gender or inclusion findings.")
    bullet(doc, "From an installation marker, choose \"Flag This "
                "Installation\" to raise a concern linked to that "
                "specific installation (concern modal: type, severity, "
                "description, notify RMT, optionally notify PSC).")

    heading(doc, "5. KPI Review", 3)
    doc.add_paragraph(
        "Renders PortfolioMonitoringView (src/components/PortfolioMonitoringView.tsx) "
        "titled \"KPI Review\" with description \"Regional KPI "
        "performance for [your region].\" Combines the portfolio KPI "
        "summary, a project selector, and a per-project KPI dashboard."
    )
    bullet(doc, "Read portfolio-level totals: progress, gender and "
                "inclusion percentages, capacity, output, districts.")
    bullet(doc, "Drill into any project in the region to read its KPI "
                "scorecard.")
    bullet(doc, "Use the map panel to correlate KPI weakness with "
                "geographic distribution.")

    heading(doc, "6. Blacklisting", 3)
    doc.add_paragraph(
        "Renders the Blacklisting component from src/App.tsx. DoE does "
        "not initiate cases (initiation is RMT / Auditor) and does not "
        "review appeals (Auditor / Admin). DoE can review and can confirm "
        "or reject."
    )
    table(
        doc,
        ["Capability", "DoE posture"],
        [
            ("Initiate a new blacklist case", "No (RMT or Auditor)"),
            ("Review an open case (provide review notes)",
             "Yes — DoE is an authorized reviewer."),
            ("Confirm / finalize a case after review",
             "Yes — DoE is an authorized confirmer."),
            ("Reject a case after review", "Yes."),
            ("Review vendor appeals",
             "No (Auditor or Admin)"),
        ],
        [3.2, 4.0],
    )
    bullet(doc, "Open the case and read the allegation, evidence, "
                "initiator, cooling-off period and any prior review notes.")
    bullet(doc, "Record review notes that explain what you checked, what "
                "you found and your conclusion.")
    bullet(doc, "Confirm only after the cooling-off period has elapsed "
                "and separation of duties is satisfied (you did not "
                "initiate the case).")
    permission_callout(
        doc,
        allowed=["review open cases and confirm or reject them; raise "
                 "concerns about vendors from any project or installation"],
        denied=["initiate cases, review appeals, modify vendor pre-"
                "qualification"],
    )

    heading(doc, "DoE quick reference — role boundary", 2)
    table(
        doc,
        ["DoE can", "DoE cannot"],
        [
            ("Raise regional concerns (KPI, GPS, verification, vendor, "
             "quality, data, other)", "Approve claims or modify milestones"),
            ("Flag a specific installation from the map",
             "Submit installations or change verification outcome"),
            ("Review and confirm blacklist cases",
             "Initiate blacklist cases or review appeals"),
            ("Read vendors, projects, KPIs and audit trail in assigned "
             "regions", "Edit vendor profiles or change pre-qualification"),
            ("Notify RMT (always) and PSC (for serious issues)",
             "Bypass RMT by notifying only PSC"),
        ],
        [3.5, 3.6],
    )
    page_break(doc)


# ---------------------------------------------------------------------------
# Content: Part 3 - Auditor
# ---------------------------------------------------------------------------


def auditor_part(doc):
    heading(doc, "Part 3 — Auditor", 1)
    doc.add_paragraph(
        "The Auditor is the independent compliance role. In the source it "
        "is the UserRole.AUDITOR role, shown in the application as "
        "Auditor. The Auditor has read access across the full portfolio "
        "and can raise and close audit findings, and initiate blacklisting "
        "cases. Auditor evidence and findings are the basis for PSC "
        "directives and for RMT corrective action."
    )
    callout(
        doc,
        "Operating principle",
        "Auditor findings must be factual, time-bound and evidence-linked. "
        "Use the dedicated audit sections (Audit Logs, Audit Findings, "
        "Anomaly Report, Claims Audit, Prospect Sync Log) rather than "
        "relying on summary dashboards. Findings can be closed only by "
        "the Auditor; PSC may add comments but cannot close them.",
    )

    heading(doc, "Auditor sidebar at a glance", 2)
    sidebar_table(
        doc,
        [
            ("Dashboard", "Project summary, anomaly stats, findings summary, "
                          "recent activity."),
            ("All Projects", "Full portfolio with read-only project tabs, "
                             "including the Audit Trail tab."),
            ("GIS Map", "Full system GIS map; filter to flagged installations."),
            ("KPI Dashboard", "Full portfolio and per-project KPI in read-only mode."),
            ("Audit Logs", "Full system audit trail with search, date filters "
                           "and CSV / PDF export."),
            ("Audit Findings", "List, raise, track and close audit findings."),
            ("Anomaly Report", "All anomaly flags across all projects; "
                               "filter by resolved / unresolved and by type."),
            ("Claims Audit", "Full payment claim chain with filter by project, "
                              "vendor and status; export the chain as PDF or CSV."),
            ("Prospect Sync Log", "External Prospect integration log; filter "
                                   "by operation and status."),
            ("Reports", "Reports workspace (list, analytics and hub) for "
                        "programme-level impact analytics and report download."),
            ("Notifications", "In-app notification feed."),
        ],
    )

    heading(doc, "Auditor sidebar, section by section", 2)

    heading(doc, "1. Dashboard", 3)
    doc.add_paragraph(
        "Renders AuditorDashboard from src/components/AuditorPortal.tsx. "
        "Loads the projects summary, the full project list and the "
        "unresolved anomalies. Auto-refresh is available."
    )
    bullet(doc, "Project summary tiles (totals by status / tech / "
                "district).")
    bullet(doc, "Anomaly stats — total, resolved, unresolved, breakdown "
                "by flag type.")
    bullet(doc, "Audit findings summary and recent activity feed.")
    bullet(doc, "Refresh action to pull the latest summary.")
    permission_callout(
        doc,
        allowed=["read portfolio summary, anomaly stats, findings and "
                 "activity"],
        denied=["edit projects, submit installations, change claims"],
    )

    heading(doc, "2. All Projects", 3)
    doc.add_paragraph(
        "Renders ProjectsHub with mode=\"auditor\". The auditor sees the "
        "full portfolio in read-only mode and the project tabs include the "
        "Audit Trail view that exposes the per-project audit events."
    )
    bullet(doc, "Open any project to see Overview, KPI, Map, Milestones, "
                "Payments, Documents, Updates and Audit Trail.")
    bullet(doc, "Use the Audit Trail tab to see who did what and when for "
                "a project — supports finding validation.")

    heading(doc, "3. GIS Map", 3)
    doc.add_paragraph(
        "Renders AuditorGisMap from src/components/AuditorPortal.tsx. "
        "Same map view as other oversight roles, read-only, with an extra "
        "filter: \"Show only flagged installations.\""
    )
    bullet(doc, "Toggle the flagged-only filter to focus sampling on "
                "projects with active anomaly flags.")
    bullet(doc, "Use the map alongside the Anomaly Report and Claims Audit "
                "to triangulate GPS or district anomalies.")

    heading(doc, "4. KPI Dashboard", 3)
    doc.add_paragraph(
        "Renders AuditorKpiDashboard from src/components/AuditorPortal.tsx. "
        "Full portfolio and per-project KPI summary, read-only. The "
        "description makes the read-only intent explicit: \"Full portfolio "
        "and per-project KPI view. Same as RMT KPI view but read-only.\""
    )
    bullet(doc, "Refresh to pull the latest KPI summary.")
    bullet(doc, "Drill into a project for the underlying scorecard.")

    heading(doc, "5. Audit Logs", 3)
    doc.add_paragraph(
        "Renders AuditorAuditLogs from src/components/AuditorPortal.tsx. "
        "The full system audit trail with search and date filters, plus "
        "CSV and PDF export."
    )
    bullet(doc, "Search across actor, action and entity type.")
    bullet(doc, "Filter by date range using the From / To date pickers.")
    bullet(doc, "Click \"Export CSV\" or \"Export PDF\" to download the "
                "filtered log for an evidence pack.")
    bullet(doc, "The table columns are Timestamp, Actor, Action, Entity "
                "(type and id) and Details / Module.")
    table(
        doc,
        ["Use case", "Where to look"],
        [
            ("Reconstruct a decision", "Filter by actor + action; cross-check "
                                       "project Updates."),
            ("Verify the approval chain on a claim",
             "Filter by claim id and the action verbs (claim_rmt_approved, "
             "claim_tac_endorsed, claim_psc_approved, finance_payment_"
             "processed, claim_confirmed_paid)."),
            ("Export an evidence pack", "Apply date filter, then export PDF "
                                          "or CSV."),
        ],
        [2.0, 5.1],
    )

    heading(doc, "6. Audit Findings", 3)
    doc.add_paragraph(
        "Renders AuditorAuditFindings from src/components/AuditorPortal.tsx. "
        "This is where the auditor records compliance findings, links them "
        "to a project or a payment claim, recommends action, and chooses "
        "who to notify."
    )
    bullet(doc, "Two counts at the top: Open findings and Resolved "
                "findings.")
    bullet(doc, "Open findings list and resolved findings list.")
    heading(doc, "Raise Audit Finding (modal)", 4)
    bullet(doc, "Finding Category — one of Payment Compliance, Approval "
                "Chain Violation, Data Integrity, GPS / Location Fraud, "
                "KPI Manipulation, Document Irregularity, Process "
                "Violation, Conflict of Interest, or Other Compliance "
                "Issue.")
    bullet(doc, "Risk Level — Observation (note for record), Minor "
                "(corrective action needed), Major (serious breach, "
                "immediate action), Critical (fraud suspected, escalate "
                "immediately).")
    bullet(doc, "Linked Project — optional select to anchor the finding.")
    bullet(doc, "Linked Payment Claim — optional; only enabled once a "
                "project is selected; populated with claims for that "
                "project.")
    bullet(doc, "Finding Description — required free-text detail.")
    bullet(doc, "Recommended Action — optional recommended remediation.")
    bullet(doc, "Notify — RMT is always notified; tick PSC and / or Super "
                "Admin as needed.")
    bullet(doc, "Submit creates the finding, logs an audit event and "
                "notifies the selected recipients.")
    table(
        doc,
        ["Risk level", "Auditor expectation"],
        [
            ("Observation", "Note for record; close when accepted."),
            ("Minor", "Assign corrective action and a due date; verify "
                      "closure evidence before closing."),
            ("Major", "Escalate; consider payment hold; require management "
                      "response."),
            ("Critical", "Immediate escalation; protect funds and evidence; "
                         "follow the approved investigation / suspension / "
                         "blacklist / legal process."),
        ],
        [1.6, 5.5],
    )
    permission_callout(
        doc,
        allowed=["raise findings, link to project / claim, recommend "
                 "action, notify RMT / PSC / Super Admin, close findings"],
        denied=["change claim status, edit vendor pre-qualification, "
                "approve payments"],
    )

    heading(doc, "7. Anomaly Report", 3)
    doc.add_paragraph(
        "Renders AuditorAnomalyReport from src/components/AuditorPortal.tsx. "
        "Lists every anomaly flag across every project, with filters by "
        "resolved / unresolved and by type, and a CSV export."
    )
    bullet(doc, "Summary cards — Total, Resolved, Unresolved, By Type.")
    bullet(doc, "Filter by Resolved status and by Flag Type.")
    bullet(doc, "Click \"Export Report\" to download the filtered list as "
                "CSV.")
    bullet(doc, "Triangulate with the Claims Audit and the GIS Map to "
                "verify the anomaly's impact.")

    heading(doc, "8. Claims Audit", 3)
    doc.add_paragraph(
        "Renders AuditorClaimsAudit from src/components/AuditorPortal.tsx. "
        "Loads the full payment claim chain (page size 200) and exposes "
        "the four-stage chain timestamps for each claim: vendor submitted, "
        "RMT verified, TAC / PSC approved, and paid."
    )
    bullet(doc, "Filter by Project, by Vendor, and by Status "
                "(Submitted, RMT Approved, TAC Endorsed, PSC Approved, "
                "Paid).")
    bullet(doc, "Open the chain column to confirm every timestamp.")
    bullet(doc, "Click \"Export Claims Audit PDF\" to download the "
                "filtered set as CSV. (The button label is \"PDF\" but the "
                "implementation produces CSV.)")
    table(
        doc,
        ["Status to look for", "What it tells you"],
        [
            ("Submitted", "Vendor has filed; RMT review has not started."),
            ("RMT Approved", "RMT approved; TAC endorsement pending."),
            ("TAC Endorsed", "Technical endorsement complete; PSC approval pending."),
            ("PSC Approved", "PSC approval complete; Finance / RMT payment "
                              "processing pending."),
            ("Paid", "Payment processed and confirmed by RMT; transaction "
                     "reference exists."),
            ("Rejected / Held-Audit", "Exception state; investigate via "
                                        "Issues."),
        ],
        [1.8, 5.3],
    )

    heading(doc, "9. Prospect Sync Log", 3)
    doc.add_paragraph(
        "Renders AuditorProspectSyncLog from src/components/AuditorPortal.tsx. "
        "Logs every push / pull call to the external Prospect system, "
        "with filters by operation (post / get) and status (pending / "
        "success / failed), and a CSV export."
    )
    bullet(doc, "Read the summary — total, success, failed, pending.")
    bullet(doc, "Filter by operation and status to investigate a "
                "specific integration event.")
    bullet(doc, "Export the filtered list as CSV.")
    bullet(doc, "Use the log alongside the Audit Logs to compare a system "
                "action with the integration outcome.")

    heading(doc, "10. Reports", 3)
    doc.add_paragraph(
        "Renders the Reports component from src/App.tsx. The Reports "
        "workspace exposes a list view, an analytics view, and a hub "
        "view. The analytics view surfaces programme-level impact "
        "metrics: gender participation, installed capacity, total "
        "energy output, regional coverage, and a regional impact table "
        "across the ten districts."
    )
    bullet(doc, "Switch between List, Analytics and Hub views from the "
                "page header.")
    bullet(doc, "Use the date-range selector to scope the analytics view.")
    bullet(doc, "Export the current dashboard; the Hub view also exposes "
                "download helpers per report card.")

    heading(doc, "11. Notifications", 3)
    doc.add_paragraph(
        "Renders NotificationLogs from src/App.tsx. The Auditor sees "
        "their own in-app notification feed."
    )
    bullet(doc, "Read event notifications related to findings, audit "
                "events, integration outcomes and project updates.")
    bullet(doc, "Click a notification to navigate to the related record.")

    heading(doc, "Auditor quick reference — role boundary", 2)
    table(
        doc,
        ["Capability", "Auditor posture"],
        [
            ("Read every project, KPI, map, claim, anomaly and audit log",
             "Yes — full read access across the system."),
            ("Export Audit Logs as CSV / PDF",
             "Yes."),
            ("Export Anomaly Report and Claims Audit as CSV",
             "Yes."),
            ("Raise and close Audit Findings",
             "Yes — only the Auditor closes findings."),
            ("Initiate a blacklist case", "Yes."),
            ("Review vendor appeals", "Yes."),
            ("Approve claims or mark claims paid",
             "No."),
            ("Edit vendor pre-qualification or vendor profile",
             "No."),
            ("Modify project setup or submit installations",
             "No."),
        ],
        [3.5, 3.6],
    )
    page_break(doc)


# ---------------------------------------------------------------------------
# Cross-role notes and appendix
# ---------------------------------------------------------------------------


def shared_notes(doc):
    heading(doc, "Cross-role notes", 1)
    doc.add_paragraph(
        "Three pieces of context apply to all three roles: the audit trail, "
        "the notification feed, and the role / sidebar mapping."
    )
    heading(doc, "Audit trail", 2)
    bullet(doc, "Every action that changes a record creates an Audit Log "
                "entry with actor, action, entity, timestamp and details.")
    bullet(doc, "The audit trail is the single source of truth for "
                "compliance review. PSC, DoE and Auditor all rely on it.")
    bullet(doc, "Only the Auditor sidebar exports the audit log directly. "
                "Other roles can read project-scoped audit events from the "
                "project Updates and Audit Trail views.")
    heading(doc, "Notifications", 2)
    bullet(doc, "Every role has an in-app Notifications feed "
                "(NotificationLogs). Click a notification to navigate to "
                "the related tender, project, prequalification or report.")
    bullet(doc, "Use Notifications as a daily attention list — but always "
                "cross-check the relevant sidebar (Issues, Disbursements, "
                "Audit Findings) for the complete picture.")
    heading(doc, "Sidebar mapping reference", 2)
    table(
        doc,
        ["Sidebar item", "PSC", "DoE", "Auditor"],
        [
            ("Dashboard", "Yes (MacroKpiPortal)",
             "Yes (DoeDashboard)", "Yes (AuditorDashboard)"),
            ("All Vendors / All Projects",
             "All Vendors", "All Vendors (Regional Vendors)",
             "All Projects (mode=auditor)"),
            ("Portfolio Overview / Regional Projects",
             "Portfolio Overview (ProjectsHub psc)",
             "Regional Projects (ProjectsHub doe)",
             "— (use All Projects)"),
            ("Disbursements / Regional Monitoring",
             "Disbursements (claims)",
             "Regional Monitoring (GIS + flag installation)",
             "— (use Claims Audit)"),
            ("Issues / KPI Review",
             "Issues (audit findings + DoE concerns)",
             "KPI Review (PortfolioMonitoringView)",
             "— (use Audit Findings)"),
            ("Briefings & Reports",
             "Briefings & Reports (issues view)",
             "—", "— (use Reports + Notifications)"),
            ("Blacklisting", "—",
             "Yes (review and confirm)", "— (initiate and review appeals)"),
            ("Audit Logs", "—", "—", "Yes"),
            ("Audit Findings", "—", "—", "Yes"),
            ("Anomaly Report", "—", "—", "Yes"),
            ("Claims Audit", "—", "—", "Yes"),
            ("Prospect Sync Log", "—", "—", "Yes"),
            ("Reports", "—", "—", "Yes"),
            ("GIS Map", "— (use Portfolio Map tab)",
             "— (use Regional Monitoring)",
             "Yes (AuditorGisMap, flagged-only filter)"),
            ("KPI Dashboard", "— (use Portfolio KPI tab)",
             "— (use KPI Review)",
             "Yes (AuditorKpiDashboard)"),
            ("Notifications / Briefings", "Briefings",
             "— (no sidebar item)", "Notifications"),
        ],
        [2.4, 1.6, 1.6, 1.6],
    )
    page_break(doc)


def appendix(doc):
    heading(doc, "Appendix A — Source basis", 1)
    doc.add_paragraph(
        "This manual was prepared from the application's current frontend "
        "and backend source. Maintainers can verify each sidebar mapping "
        "and permission claim against the files below."
    )
    for source in [
        "src/App.tsx — sidebar definitions (getSidebarItems, lines "
        "~25394), routing per role (renderActiveTab, lines ~25239-25346), "
        "and the inline Disbursements / Blacklisting / VendorDirectory / "
        "ProjectsHub / Reports / NotificationLogs components.",
        "src/components/PscPortal.tsx — PscDashboard, PscReports and "
        "PscIssuesView (audit findings + DoE concerns briefings).",
        "src/components/DoePortal.tsx — DoeDashboard, DoeRegionalMap and "
        "DoeReports (regional concern + flag installation flows).",
        "src/components/AuditorPortal.tsx — AuditorDashboard, "
        "AuditorGisMap, AuditorKpiDashboard, AuditorAuditLogs, "
        "AuditorAnomalyReport, AuditorClaimsAudit, AuditorProspectSyncLog "
        "and AuditorAuditFindings.",
        "src/components/RoleBasedKpiPanels.tsx — MacroKpiPortal used for "
        "the PSC Dashboard.",
        "src/components/PortfolioMonitoringView.tsx — shared regional KPI "
        "and map view used by the DoE KPI Review sidebar.",
        "backend/rbf/users/models.py — UserRole constants: "
        "UNDP_DONOR (Project Steering Committee), DOE_OFFICER "
        "(DoE Officer), AUDITOR (Auditor).",
        "backend/rbf/projects/views.py — role-gated claim actions "
        "(verify / approve / reject / pay / confirm-paid) and the "
        "vendor-bank-detail masking and reveal rules.",
        "backend/rbf/tenders/views.py — TenderChallenge resolve actions "
        "(referenced in PSC briefings).",
        "README.md and CLAUDE.md — local setup, roles and verification "
        "workflow.",
    ]:
        bullet(doc, source)
    doc.add_paragraph("End of manual.").alignment = WD_ALIGN_PARAGRAPH.CENTER


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build():
    doc = Document()
    configure(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("PSC / DoE / AUDITOR\n").bold = True
    p.runs[0].font.size = Pt(14)
    p.runs[0].font.color.rgb = RGBColor(47, 117, 181)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Roles & Sidebar Operational Guide")
    r.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor(31, 78, 120)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(
        "Renewable Lesotho Results-Based Financing Platform\n"
        "Operational guide for the Project Steering Committee, "
        "DoE Officer and Auditor roles"
    ).font.size = Pt(13)
    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(
        f"Version 1.0  |  {date.today().isoformat()}\n"
        "Use with the deployed application and approved programme procedures"
    ).italic = True
    page_break(doc)

    heading(doc, "How to Use This Manual", 1)
    doc.add_paragraph(
        "This guide is written for three oversight roles in the platform: "
        "the Project Steering Committee (PSC, role UNDP_DONOR), the DoE "
        "Officer (role DOE_OFFICER) and the Auditor (role AUDITOR). The "
        "manual follows the application's sidebar so that you can map any "
        "menu item to the work it supports."
    )
    callout(
        doc,
        "Important operating principle",
        "The platform records decisions and evidence; it does not replace "
        "the approved programme policy, delegation of authority, separation "
        "of duties or financial controls. Apply the programme rule first, "
        "then record the decision in the corresponding workflow.",
    )
    table(
        doc,
        ["Before you start", "What to confirm"],
        [
            ("Access",
             "Your account has the correct role (PSC, DoE Officer or "
             "Auditor) and the menus shown in this guide appear."),
            ("Scope",
             "For DoE, your assigned districts are correct. For PSC, your "
             "visibility spans the portfolio."),
            ("Evidence",
             "Every directive, comment, concern, finding or approval has a "
             "clear reason and is linked to a project, claim or record."),
            ("Separation of duties",
             "Do not bypass RMT, TAC, finance, audit or four-eyes controls. "
             "PSC does not mark claims paid; DoE does not approve claims; "
             "the Auditor closes findings but does not approve claims."),
        ],
        [1.5, 5.6],
    )

    heading(doc, "Contents", 1)
    add_toc(doc.add_paragraph())
    page_break(doc)

    psc_part(doc)
    doe_part(doc)
    auditor_part(doc)
    shared_notes(doc)
    appendix(doc)

    doc.core_properties.title = (
        "PSC, DoE & Auditor Roles Manual — Renewable Lesotho RBF Platform"
    )
    doc.core_properties.subject = (
        "Operational guide for PSC, DoE Officer and Auditor roles"
    )
    doc.core_properties.author = "Renewable Lesotho RBF Platform"
    doc.core_properties.comments = (
        "Generated from the current application workflows and source "
        "documentation. Sidebar mappings grounded in src/App.tsx and "
        "src/components/{PscPortal,DoePortal,AuditorPortal}.tsx."
    )
    doc.save(OUTPUT)


if __name__ == "__main__":
    build()