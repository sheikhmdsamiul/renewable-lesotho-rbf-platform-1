from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = Path("RBF_Official_Training_Manual.docx")


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
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            set_cell_text(cells[i], value)
            if len(t.rows) % 2 == 0:
                shade(cells[i], "EAF2F8")
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
    for name, size, color in [("Title", 28, "1F4E78"), ("Heading 1", 18, "1F4E78"), ("Heading 2", 13, "2F75B5"), ("Heading 3", 11, "2F75B5")]:
        styles[name].font.name = "Aptos Display"
        styles[name]._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos Display")
        styles[name].font.size = Pt(size)
        styles[name].font.color.rgb = RGBColor.from_string(color)
    header = section.header.paragraphs[0]
    header.text = "Renewable Lesotho RBF Platform  |  RBF Official Training Manual"
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Internal training reference  |  ")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    footer._p.append(fld)


def build():
    doc = Document()
    configure(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("RBF OFFICIAL\n").bold = True
    p.runs[0].font.size = Pt(14)
    p.runs[0].font.color.rgb = RGBColor(47, 117, 181)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Full-Lifecycle Training Manual")
    r.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor(31, 78, 120)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run("Renewable Lesotho Results-Based Financing Platform\nOperational guide for the RBF Management Team").font.size = Pt(13)
    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f"Version 1.0  |  {date.today().isoformat()}\nUse with the deployed application and approved programme procedures").italic = True
    page_break(doc)

    heading(doc, "How to Use This Manual", 1)
    doc.add_paragraph("This guide is written for the RBF Official, also shown in the platform as RMT or RBF Management Team. It follows the programme from vendor readiness through procurement, implementation, verification, payment, monitoring, reporting, and corrective action.")
    callout(doc, "Important operating principle", "The platform records decisions and evidence; it does not replace the approved RBF policy, procurement rules, contract, delegation of authority, or financial controls. Apply the programme rule first, then record the decision in the corresponding workflow.")
    table(doc, ["Before you start", "What to confirm"], [
        ("Access", "Your account has the RBF Management Team role and your assigned permissions."),
        ("Data", "The tender, vendor, project, claim, and supporting documents are the correct records."),
        ("Evidence", "Every approval, rejection, return, escalation, or payment has a clear reason and evidence."),
        ("Separation of duties", "Do not bypass TAC, PSC, DoE, field verification, audit, or four-eyes controls."),
    ], [1.5, 5.6])
    heading(doc, "Contents", 1)
    add_toc(doc.add_paragraph())
    page_break(doc)

    heading(doc, "1. Role, Scope, and Navigation", 1)
    doc.add_paragraph("The RBF Official is the programme-level operator and control point. You coordinate the procurement pipeline, monitor the portfolio, approve the RMT stage of claims, manage official notices, investigate issues, and initiate compliance action.")
    table(doc, ["Menu", "Use it for"], [
        ("Dashboard", "National KPIs, target progress, at-risk projects, active tenders, pending disbursements, inclusion, and alerts."),
        ("All Vendors", "Company profile, prequalification, documents, bids, projects, performance, payments, and audit trail."),
        ("Tender Management", "Create, verify, publish, evaluate, award, challenge, contract, and close tenders."),
        ("Notice Board", "Prepare and publish tender, deadline, award, clarification, training, and general notices."),
        ("Financial Evaluation", "Score the financial part of eligible bids after the technical gate is passed."),
        ("Pre-Qualification", "Review vendor applications: approve, request clarification, or reject."),
        ("Projects Hub", "Portfolio and project tabs for overview, KPIs, maps, milestones, payments, documents, and updates."),
        ("Blacklisting", "Initiate and monitor cases, evidence, review, appeals, and reinstatement."),
        ("GIS Mapping", "Use the project Map tab for installation locations, verification state, and anomalies."),
        ("Disbursements", "Review RMT claim approvals, payment holds, delays, and final payment confirmation."),
        ("Reports", "Generate, download, and review KPI, verification, financial, portfolio, anomaly, inclusion, and audit reports."),
        ("Issues & Findings", "Respond to DoE concerns and auditor findings, assign action, escalate, or suspend/blacklist."),
        ("Notifications", "Follow workflow events and open the related tender, project, prequalification, or report."),
    ], [1.6, 5.5])
    callout(doc, "Navigation note", "GIS Mapping is available inside each project’s Map tab. If the standalone GIS menu does not open a dedicated screen in your deployment, use Projects Hub > project > Map.", "DDEBF7")

    heading(doc, "2. The Full Lifecycle at a Glance", 1)
    table(doc, ["Gate", "Lifecycle", "RBF Official focus"], [
        ("1", "Vendor prequalification", "Confirm eligibility, documents, clarification, and decision."),
        ("2", "Tender preparation", "Set scope, budget, districts, criteria, deadlines, and required documents."),
        ("3", "Verification and publication", "Check completeness, verify, publish, and notify."),
        ("4", "Bid and evaluation", "Protect the submission process; complete financial evaluation after technical pass."),
        ("5", "Intent, standstill, and award", "Confirm recommendation, manage cooling-off and challenges, then award."),
        ("6", "Contract and project assignment", "Generate, receive signed contract and annexes, approve, assign project."),
        ("7", "Project setup and delivery", "Monitor readiness, installations, evidence, and KPI progress."),
        ("8", "Verification and claim", "Review verified outputs and approve the RMT claim stage."),
        ("9", "Endorsement and payment", "Track TAC/PSC approvals, confirm payment reference, and protect the ledger."),
        ("10", "Closeout and learning", "Review completion, reports, audit trail, issues, and vendor performance."),
    ], [0.5, 2.0, 4.6])
    page_break(doc)

    heading(doc, "3. Access and Daily Start-Up", 1)
    number(doc, "Open the assigned platform URL and sign in with your official account. Never share your password or use demo credentials in production.")
    number(doc, "Confirm the role shown in the application is RBF Management Team/RMT. If the menu is incomplete, stop and request an access correction.")
    number(doc, "Open Notifications and record urgent tender deadlines, claims, verification flags, audit findings, and failed integrations.")
    number(doc, "Open Dashboard and review active tenders, pending disbursements, at-risk projects, verified installations, inclusion metrics, and alerts.")
    number(doc, "Create or update your daily action list from records that are due, blocked, escalated, or waiting for another role.")
    table(doc, ["Daily check", "Question to answer", "Record/action"], [
        ("Procurement", "Are any tenders approaching publication, closing, standstill expiry, or challenge deadlines?", "Open Tender Management; notify stakeholders where required."),
        ("Delivery", "Which projects are stalled, halted, behind schedule, or missing meter/KPI data?", "Open Projects Hub; add note, flag risk, or escalate."),
        ("Verification", "Are there pending, partial, flagged, or anomalous installations?", "Open Map, KPI, and Issues & Findings."),
        ("Finance", "Which claims are submitted, held, awaiting endorsement, or awaiting payment confirmation?", "Open Disbursements; process only eligible claims."),
        ("Compliance", "Are there new concerns, audit findings, or vendor restrictions?", "Open the record and document the response/action."),
    ], [1.2, 3.6, 2.3])

    heading(doc, "4. Vendor Pre-Qualification", 1)
    doc.add_paragraph("An approved prequalification is a gate for tender participation. Do not treat a vendor as tender-eligible until the application is approved and any restriction or blacklist state has been checked.")
    heading(doc, "Procedure", 2)
    for item in [
        "Open Pre-Qualification and filter for Pending or applications requiring action.",
        "Open the vendor application and review legal/company registration, tax clearance, technical capability, experience, financial/banking information, technology coverage, and declarations.",
        "Check the vendor profile for suspension, blacklist, expired status, previous performance, open findings, and related projects.",
        "If information is incomplete but potentially correctable, choose Request Clarification/Resubmission and write exactly what is missing and the due date.",
        "If requirements are met, approve the application and record the basis of the decision. If not met, reject with a reason that can be audited.",
        "Confirm the vendor can now see eligible published tenders and that the decision notification was generated.",
    ]:
        number(doc, item)
    callout(doc, "Control", "A vendor that is suspended or blacklisted must not submit bids, update project records, submit installations, submit claims, or receive new disbursements. Check the computed vendor status, not only the prequalification label.")

    heading(doc, "5. Tender Preparation, Verification, and Publication", 1)
    doc.add_paragraph("Tender status normally moves through Draft > Published > Evaluation > Standstill > Awarded > Closed. A disputed tender cannot proceed to final award until the dispute is resolved.")
    heading(doc, "Create the tender", 2)
    table(doc, ["Area", "Check before saving"], [
        ("Scope", "Technology, service area, target beneficiaries, approximate installation target, and required outputs."),
        ("Money", "Budget, bid amount rules, milestone payment schedule, and any tender security requirement."),
        ("Eligibility", "Prequalification requirements, required company documents, technical threshold, and evaluation weights."),
        ("Geography", "Target districts and any district-specific delivery constraints."),
        ("Time", "Publication date, application deadline, pre-tender meeting details, cooling-off days, and closure conditions."),
        ("Documents", "RFP, schedule, milestone payment schedule, trading licence, tax clearance, registration, and experience requirements."),
    ], [1.3, 5.8])
    heading(doc, "Verify and publish", 2)
    for item in [
        "Open the draft tender and use Verify after checking all fields and attachments against the approved procurement package.",
        "Resolve verification errors before publication. Do not publish an unverified tender.",
        "Publish only when the approval to advertise is complete. Confirm the public tender view, deadline, attachments, and required notices.",
        "Use Notice Board for a linked tender/deadline notice. Tender and deadline notices require the linked tender and countdown date.",
        "Monitor the tender until the deadline. Do not manually bypass deadline controls or accept an out-of-window bid without the approved exception process.",
    ]:
        number(doc, item)

    heading(doc, "6. Bid Review and Evaluation", 1)
    doc.add_paragraph("The platform supports staged procurement. A vendor must be approved, the tender must be published, and the vendor must not be restricted. Finalized bids are locked; revisions are separate versions.")
    table(doc, ["Stage", "RBF Official responsibility", "Gate"], [
        ("Stage 1", "Monitor concept/eligibility submissions and coordinate technical review.", "Accepted Stage 1 unlocks the vendor’s Stage 2 draft."),
        ("Technical", "Monitor TAC scoring and confirm evaluators use the approved matrix.", "Technical average must pass the tender threshold."),
        ("Financial", "Open Financial Evaluation and score eligible bids.", "Financial scoring is blocked until the technical gate passes."),
        ("Ranking", "Review computed ranking, active bid version, scores, weights, tie-breakers, and bid amount.", "Recommended winner must be the computed eligible winner."),
    ], [1.0, 4.0, 2.1])
    doc.add_paragraph("Technical matrix maximum: 70 points (technical 20, feasibility 15, O&M 10, KPI 10, gender 10, environmental 5). Financial matrix maximum: 30 points (technical 10, feasibility 10, KPI 5, gender 5, financial 30). Use the tender’s configured weights and approved evaluation records.")
    callout(doc, "Evaluation discipline", "Do not score a bid because it is the cheapest, most familiar, or most urgent. Score the approved criteria, preserve evaluator independence, and write a reason for any clarification, revision, rejection, or exceptional decision.")

    heading(doc, "7. Intent to Award, Standstill, Challenges, and Award", 1)
    for item in [
        "From Published or Evaluation, review the ranking and select the system-recommended winner. Confirm the bid identity and vendor identity before issuing intent.",
        "Issue Intent to Award. The tender moves to Standstill and the configured cooling-off period starts, normally seven days unless configured otherwise.",
        "Monitor challenges in Tender Management. An active dispute freezes final award.",
        "For a dismissed challenge, confirm the remaining standstill time. For an upheld challenge, review the replacement winner and new cooling-off period.",
        "After cooling-off expires, confirm that there is no active dispute, the tender is not closed, and intent exists. Confirm the award.",
        "Confirm the tender is Awarded, the bid is Awarded, and the contract package has been created before moving to contracting.",
    ]:
        number(doc, item)
    table(doc, ["Challenge result", "System consequence", "Official action"], [
        ("Dismissed", "Standstill resumes with remaining time.", "Record the resolution and continue monitoring."),
        ("Upheld", "Winner changes and a new cooling-off period begins.", "Recheck ranking, notices, and evidence before final award."),
        ("Partially upheld/settled", "Follow the recorded decision and programme procedure.", "Do not finalize until the workflow permits it."),
    ], [1.6, 3.0, 2.5])

    heading(doc, "8. Contract Approval and Project Assignment", 1)
    doc.add_paragraph("A contract can be generated only after award. The awarded vendor must upload a signed PDF and all required annexes before RMT approval and project assignment.")
    for item in [
        "Open the awarded tender’s contract package and confirm the generated contract matches the award, price, vendor, target, and milestone terms.",
        "Check the vendor’s signed PDF is readable and within the 10 MB limit. Confirm the five required annexes: Results Framework, Implementation Schedule, Payment Terms, Reporting Formats, and Technical Standards.",
        "Review signature status and any discrepancies. Reject/return with a precise correction request when required.",
        "Approve only when the contract is complete, signed, and within delegated authority. Record the decision and date.",
        "Assign the project from the approved contract. Confirm the project, vendor, technology, districts, target, budget, verification method, and milestone plan.",
        "Do not assign a contract twice. Notify the vendor and downstream DoE/TAC/field teams as required.",
    ]:
        number(doc, item)
    callout(doc, "Default milestone plan", "Project assignment creates Mobilization at 20%, 80% Implementation at 50%, and Final at 30%. Review the actual contract and approved payment schedule before acting on a claim.")

    heading(doc, "9. Project Setup and Delivery Oversight", 1)
    doc.add_paragraph("Projects may show Setup Pending, Active, Pre-Qualification, Site-Specific Proposal, Contracting, Installation, Field Verification, Disbursement, Halted, or Completed. The vendor must complete setup before installation submission is unlocked.")
    heading(doc, "Setup gate checklist", 2)
    for item in [
        "Team roster and equipment plan uploaded.",
        "Site readiness and implementation schedule recorded.",
        "Compliance and insurance evidence uploaded.",
        "Device brand/model and technology tier recorded.",
        "All readiness checklist items completed.",
        "Manual verification confirmation recorded, or IoT endpoint/token configured where applicable.",
        "Approved contract linked to the project.",
    ]:
        bullet(doc, item)
    heading(doc, "Monitor from Projects Hub", 2)
    table(doc, ["Project tab", "RBF Official review"], [
        ("Overview", "Status, contract, milestones, claims, audit activity, issues, and current conditions."),
        ("KPI", "Progress against targets, gender/inclusion results, performance notes, at-risk flag, report, and Prospect sync."),
        ("Map", "Verified, pending, flagged installations; GPS anomalies; district and technology filters."),
        ("Milestones", "Eligibility conditions, completion, claim history, status, and claimable amount."),
        ("Payments", "Claim status, approval chain, payment proof, holds, delays, and bank-detail access controls."),
        ("Documents", "Contract, annexes, project evidence, and required downloads."),
        ("Updates", "Chronological activity, decisions, notes, and actor history."),
    ], [1.3, 5.8])

    heading(doc, "10. Installation Reporting and Field Verification", 1)
    doc.add_paragraph("Installation records are evidence for performance and payment. Every submission creates a verification task. Coordinates must be valid and within Lesotho; where configured, they must also be inside the assigned project district.")
    for item in [
        "Review the project’s installation list and Map tab for submitted, verified, flagged, paused, and terminated records.",
        "Check GPS accuracy and duplicate-location warnings. A duplicate within 10 metres is an anomaly requiring investigation, not automatic approval.",
        "Confirm the assigned field verifier or DoE process has completed. Do not mark an installation verified merely because a vendor submitted it.",
        "Review verification result, reason, date, photos, meter information, beneficiary information, and any anomaly.",
        "Use Verified only when the evidence supports the result. Flagged or partial outcomes require a reason; a location mismatch can downgrade a requested Verified result to Flagged.",
        "Link material concerns to Issues & Findings and hold or escalate related claims where appropriate.",
    ]:
        number(doc, item)
    table(doc, ["Verification result", "Meaning for oversight"], [
        ("Pending", "Awaiting field or authorized review."),
        ("Partial", "Some evidence reviewed; record remains incomplete and should not be treated as fully verified."),
        ("Verified", "Evidence supports the installation result and the task is complete."),
        ("Flagged", "Anomaly, mismatch, or concern requires follow-up; payment risk may exist."),
        ("Paused/Terminated", "Workflow is stopped by an operational or compliance event."),
    ], [1.5, 5.6])

    heading(doc, "11. Milestone Claims and Disbursement", 1)
    doc.add_paragraph("The normal claim chain is Submitted > RMT Approved > TAC Endorsed > PSC Approved > Completed. Rejected and Held/Audit are exception states. RMT approval is a control gate, not a routine click-through.")
    heading(doc, "RMT claim review procedure", 2)
    for item in [
        "Open Disbursements and select a Submitted or pending claim. Confirm project, vendor, milestone, amount, dates, and the claim is not a duplicate.",
        "Check the milestone is eligible and the output evidence supports the claimed progress. Compare the claim with verified installations, KPI data, contract terms, and payment schedule.",
        "Check beneficiary totals, female beneficiaries, inclusion commitments, implementation notes, declarations, documents, photos, and audit flags.",
        "Review vendor restriction status, open blacklist cases, related issues, and any payment hold. A restricted vendor must not be paid through a normal process.",
        "Approve as RMT only when complete. If incomplete, reject/return with review notes or place on hold for audit according to the available workflow.",
        "Track TAC endorsement and PSC approval. Do not perform a later-stage approval on behalf of another role.",
        "After authorized finance processing and PSC approval, confirm final payment only with the transaction/reference ID. This creates the payment ledger entry.",
        "Confirm the disbursement and claim show Completed, the milestone is Paid, and the project completion rule is satisfied when the final milestone is paid.",
    ]:
        number(doc, item)
    callout(doc, "Never approve on missing evidence", "A claim may be financially plausible and still be ineligible. If verification, milestone eligibility, declaration, budget, contract, or approval-chain evidence is missing, return or hold the claim and explain exactly what is needed.", "FCE4D6")
    table(doc, ["Before RMT approval", "After approval"], [
        ("Milestone", "Claim corresponds to the correct milestone and approved percentage/amount."),
        ("Evidence", "Outputs, installations, verification, KPI, photos, and documents support the claim."),
        ("Controls", "No duplicate claim, blacklist restriction, unresolved critical finding, or budget breach."),
        ("Chain", "TAC and PSC actions are still required; payment is not complete at RMT approval."),
    ], [3.4, 3.7])

    heading(doc, "12. Issues, Findings, and Corrective Action", 1)
    doc.add_paragraph("Use Issues & Findings as the controlled response record for DoE concerns and auditor findings. Responses are part of the audit trail and should be factual, time-bound, and linked to evidence.")
    for item in [
        "Filter by type, severity, project, claim, installation, status, and open/closed state.",
        "Open the record and read the source, evidence, linked project/claim, notifications, prior responses, and due dates.",
        "Choose the narrowest accurate action: under investigation, action initiated, resolved, dismissed, escalated to PSC, corrective action, payment suspension, blacklist initiation, legal referral, or evidence review.",
        "Write what was checked, what was found, who owns the next action, the due date, and what evidence will close the issue.",
        "Use project KPI, GIS, installation, or claim links to validate the finding rather than relying on a summary alone.",
        "Revisit open actions until resolved. Escalate critical findings and payment/compliance risks immediately under programme rules.",
    ]:
        number(doc, item)
    table(doc, ["Severity/risk", "Expected response"], [
        ("Observation/low", "Record and monitor; close only when the observation is addressed or accepted."),
        ("Minor", "Assign corrective action and due date; verify closure evidence."),
        ("Major", "Escalate, consider payment hold, and require management response."),
        ("Critical", "Immediate escalation, protect funds/evidence, and follow the approved investigation, suspension, blacklist, or legal process."),
    ], [1.5, 5.6])

    heading(doc, "13. Blacklisting, Suspension, and Appeals", 1)
    doc.add_paragraph("Blacklisting is a four-eyes compliance process. Initiation, review, and confirmation should be performed by different authorized people where the workflow requires it.")
    table(doc, ["Step", "What happens", "RBF Official action"], [
        ("Initiate", "Case is created; vendor is Suspended; pending verification may pause.", "Document allegation, evidence, affected records, and notice."),
        ("Review", "TAC, DoE, Auditor, or another authorized reviewer examines the case.", "Do not act as reviewer where you are the prohibited initiator; monitor evidence and deadlines."),
        ("Appeal", "Affected vendor may submit an appeal.", "Ensure the appeal is linked and routed to authorized Auditor/Admin review."),
        ("Confirm", "Authorized confirmer applies Blacklisted; projects halt, claims/disbursements hold, tasks may terminate.", "Confirm only after cooling-off and separation-of-duties controls are satisfied."),
        ("Reject/reinstate", "Vendor returns to active/registered status under the decision.", "Check requalification requirements and downstream records before new work."),
    ], [1.2, 3.2, 2.7])
    callout(doc, "Evidence preservation", "Before initiating or escalating a case, preserve the relevant vendor, bid, project, installation, claim, payment, serial, beneficiary, GPS, document, notification, and audit records. Do not edit away the original evidence.")

    heading(doc, "14. Reporting, Audit Trail, and Notifications", 1)
    heading(doc, "Reports", 2)
    doc.add_paragraph("Use Reports to create a repeatable evidence pack. Select the report template, project/date filters, and supported format. Review the generated file before distributing it.")
    table(doc, ["Report family", "Typical use"], [
        ("KPI/project", "Target progress, delivery, gender/inclusion, and performance management."),
        ("Verification", "Installation outcomes, field evidence, verifier history, and exceptions."),
        ("Financial/disbursement", "Claims, approval chain, payment trail, holds, and budget oversight."),
        ("Portfolio", "National or programme-level management review."),
        ("Anomaly/data integrity", "GPS duplicates, meter issues, data discrepancies, and controls."),
        ("Audit/compliance", "Full audit, KPI compliance, findings, and decision history."),
    ], [2.0, 5.1])
    heading(doc, "Audit trail", 2)
    for item in [
        "Use project Updates, claim history, vendor audit trail, and issue response history to reconstruct what happened.",
        "For every decision, ensure the actor, timestamp, status change, reason, and evidence are recorded.",
        "Download reports and preserve the generated file name, date range, filters, and distribution list when used for a meeting or approval.",
        "Review notification status and resend/escalate only when the programme communication procedure allows it.",
    ]:
        bullet(doc, item)

    heading(doc, "15. Exception Playbook", 1)
    table(doc, ["Problem", "Immediate check", "Safe next action"], [
        ("Vendor cannot bid", "Approved prequalification, published tender, deadline, suspension/blacklist.", "Correct the gate or explain the rejection; do not bypass it."),
        ("Financial evaluation unavailable", "Technical evaluations and threshold.", "Complete/resolve technical evaluation first."),
        ("Award cannot confirm", "Standstill expiry, intent, dispute, closed/already awarded status.", "Resolve the blocking condition and keep the record auditable."),
        ("Project cannot activate", "Contract approval and setup checklist.", "Return missing setup evidence to vendor."),
        ("Installation is flagged", "GPS match, duplicate warning, photos, verifier reason, district boundary.", "Investigate and link a concern; do not count as verified without evidence."),
        ("Claim cannot advance", "Milestone eligibility, RMT approval, TAC/PSC sequence, restriction, budget, duplicate.", "Hold/return with notes; never skip the approval chain."),
        ("Vendor appears restricted", "Computed vendor status and open blacklist case.", "Stop new bid/project/claim/payment actions and follow compliance process."),
        ("System appears wrong", "Notification, API health, role, record ID, browser refresh, and audit log.", "Capture timestamp and record ID; escalate to platform support without changing evidence."),
    ], [1.6, 3.1, 2.4])

    heading(doc, "16. Practical Training Exercises", 1)
    doc.add_paragraph("Use a non-production environment and the seeded demo accounts only for practice. Complete each exercise with a second person acting as the relevant independent role.")
    table(doc, ["Exercise", "Expected outcome"], [
        ("Prequalification", "Review a vendor, request clarification, then approve or reject with evidence."),
        ("Tender", "Create a draft, verify it, publish it, and create a linked deadline notice."),
        ("Evaluation", "Review technical results, perform financial evaluation only after the threshold, and inspect ranking."),
        ("Award", "Issue intent, observe standstill, submit/resolve a challenge, and confirm only when permitted."),
        ("Contract", "Review signed PDF and five annexes, approve, and assign one project."),
        ("Verification", "Inspect an installation on Map, distinguish verified/partial/flagged, and create a concern."),
        ("Disbursement", "Review a claim, return one incomplete claim, approve one complete claim, then follow TAC/PSC/payment reference."),
        ("Compliance", "Initiate a blacklist case with evidence and observe suspension/hold effects without confirming your own case."),
        ("Reporting", "Generate a KPI, verification, financial, and audit report using a defined date range."),
    ], [1.6, 5.5])
    heading(doc, "Training sign-off", 2)
    table(doc, ["Capability", "Trainee initials/date", "Trainer initials/date"], [
        ("Can navigate as RBF Official and use the dashboard", "", ""),
        ("Can process prequalification and tender gates", "", ""),
        ("Can manage standstill, challenge, and award controls", "", ""),
        ("Can approve contracts and assign projects", "", ""),
        ("Can review verification and milestone claims", "", ""),
        ("Can manage issues, findings, blacklisting, and appeals", "", ""),
        ("Can produce and interpret management reports", "", ""),
    ], [4.4, 1.3, 1.4])

    heading(doc, "17. Reference: Statuses and Key Rules", 1)
    table(doc, ["Object", "Main statuses / rule"], [
        ("Tender", "Draft > Published > Evaluation > Standstill > Awarded > Closed; Disputed blocks final award."),
        ("Bid", "Draft, Submitted, Under Review, Revision Required, Accepted, Awarded, Rejected, Withdrawn."),
        ("Contract", "Generated > Submitted/Signed > Approved; may be Rejected."),
        ("Project", "Setup Pending, Active, Installation, Field Verification, Disbursement, Halted, Completed plus control states."),
        ("Verification", "Pending, Paused, Partial, Verified, Flagged, Terminated."),
        ("Claim", "Submitted > RMT Approved > TAC Endorsed > PSC Approved > Completed; Rejected/Held-Audit exceptions."),
        ("Blacklist", "Initiated > Under Review > Blacklisted; Rejected, Expired, Reinstated, Requalified alternatives."),
    ], [1.5, 5.6])
    callout(doc, "Local configuration", "Labels, visible actions, thresholds, deadlines, notice templates, and report availability may vary by deployment. If the screen differs from this manual, follow the approved programme procedure and report the discrepancy with the record ID and timestamp.", "DDEBF7")

    heading(doc, "18. Local Setup and Support Notes", 1)
    doc.add_paragraph("For local training environments, the repository documentation describes Docker Compose for the API/database and Vite for the frontend. A typical setup is:")
    for command in [
        "docker compose up --build -d",
        "npm install",
        "npm run dev",
    ]:
        p = doc.add_paragraph()
        p.style = "No Spacing"
        r = p.add_run(command)
        r.font.name = "Courier New"
        r.font.size = Pt(9)
    doc.add_paragraph("Check the API health endpoint before testing login: http://localhost:8000/api/health/. If another local Django process already owns port 8000, stop it or configure the frontend proxy and API port consistently. A 404 from the wrong backend usually means the intended RBF web service is not the service answering on port 8000.")
    callout(doc, "Demo accounts", "The seeded demo account rbf_official / Rbf@1234 is for local training only. Replace, disable, or rotate demo credentials before production use.", "FCE4D6")

    heading(doc, "Appendix A. Source Basis", 1)
    doc.add_paragraph("This manual was prepared from the application’s current frontend, backend, tests, and README files. Useful implementation references for maintainers are:")
    for source in [
        "src/App.tsx and src/components/RoleBasedKpiPanels.tsx: RBF navigation, dashboards, project actions, disbursement actions, issues, and reports.",
        "backend/rbf/users/models.py and views.py: roles, vendor status, prequalification, blacklisting, and appeals.",
        "backend/rbf/tenders/models.py, serializers.py, and views.py: tender, bid, evaluation, challenge, award, contract, and notice workflows.",
        "backend/rbf/projects/models.py, serializers.py, and views.py: projects, milestones, installations, verification, claims, disbursement, concerns, findings, and reports.",
        "README.md, backend/README.md, docker-compose.yml, and seed_demo_users.py: local startup, health checks, demo accounts, and integrations.",
    ]:
        bullet(doc, source)
    doc.add_paragraph("End of manual.").alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.core_properties.title = "RBF Official Full-Lifecycle Training Manual"
    doc.core_properties.subject = "Renewable Lesotho Results-Based Financing Platform"
    doc.core_properties.author = "Renewable Lesotho RBF Platform"
    doc.core_properties.comments = "Generated from the current application workflows and source documentation."
    doc.save(OUTPUT)


if __name__ == "__main__":
    build()
