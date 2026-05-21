# Renewable Lesotho RBF Platform - Complete User Guide

## 1. Introduction

This guide provides a comprehensive overview of the Renewable Lesotho RBF Digital Platform, designed for Results-Based Financing (RBF) in the off-grid solar sector. It explains how each user role can perform their work and test the system, even without technical expertise.

The platform connects:
- **Administrators** (System configuration and governance)
- **RBF Management Team** (Tender and project management)
- **Technical Advisory Committee** (Technical evaluation)
- **Department of Energy Officers** (Regional monitoring)
- **Project Steering Committee** (Strategic oversight)
- **Auditors** (Compliance and fraud detection)
- **Field Verifiers** (On-site verification)
- **Vendors** (Bidding, project execution, and claims)

## 2. Demo User Credentials

Use the following credentials to access the platform during testing:

| Role | Username | Password |
| :--- | :--- | :--- |
| **Platform Administrator (Super Admin)** | `admin_user` | `Admin@1234` |
| **RBF Management Team (RMT)** | `rbf_official` | `Rbf@1234` |
| **TAC Member** | `tac_member` | `Tac@1234` |
| **DoE Officer** | `doe_officer` | `Doe@1234` |
| **PSC (Project Steering Committee)** | `donor_user` | `Donor@1234` |
| **Auditor** | `auditor_user` | `Auditor@1234` |
| **Field Verifier** | `field_verifier` | `Field@1234` |
| **Approved Vendor** | `vendor_approved` | `Vendor@1234` |

> **Note**: For vendor registration during testing, use the registration flow with any valid details.

## 3. Platform Overview

The Renewable Lesotho RBF Platform manages the complete RBF lifecycle:
1. **Tender Creation & Publication** (by RMT)
2. **Vendor Registration & Bidding** (by Vendors)
3. **Bid Evaluation** (by TAC)
4. **Contracting** (PBA generation and signing by RMT and Vendors)
5. **Project Setup** (by Vendors)
6. **Installation & Verification** (by Vendors and Field Verifiers)
7. **Payment Claims** (submission, verification, approval, and payment)
8. **Monitoring & Compliance** (by DoE, PSC, Auditor)

## 4. Role-Based Functionalities & Testing Guide

### 4.1 Platform Administrator (Super Admin)

**Primary Responsibility**: System governance, user management, and technical configuration.

**Key Functions**:
- **User Management**: Create, edit, deactivate users; reset passwords.
- **Organization Management**: Manage government, NGO, and international organization registry.
- **System Configuration**: Set global targets (female inclusion %, GPS thresholds, currency).
- **Prospect Sync Control**: Monitor data sync with external Prospect system; retry failed jobs.
- **System Audit Logs**: Access full history of all actions; export to CSV/PDF.
- **System Health**: Monitor server uptime, database status, API performance.

**Testing Steps**:
1. Log in as `admin_user` / `Admin@1234`.
2. Navigate to **User Management** to create a new test user.
3. Go to **System Configuration** to adjust a setting (e.g., female inclusion target).
4. Visit **Prospect Sync Control** to check sync status and trigger a manual sync.
5. Check **System Audit Logs** for recent activities and export a sample log.

### 4.2 RBF Management Team (RMT)

**Primary Responsibility**: Operational management of tenders, projects, and payments.

**Key Functions**:
- **Tender Lifecycle Management**: Create, verify, publish tenders; manage awarding.
- **Project Oversight**: Approve project setups; track milestones; review vendor documents.
- **Contracting (PBA)**: Generate Performance-Based Agreements; review signatures; finalize.
- **Payment Claim Processing**: Multi-stage review (Verify → Approve → Finalize).
- **Vendor Prequalification**: Review and approve/reject vendor applications.
- **Blacklisting**: Initiate, review, confirm blacklisting for non-compliant vendors.
- **Issue Resolution**: Respond to concerns from DoE officers and Auditor findings.
- **Notice Management**: Create and publish system-wide announcements.

**Testing Steps**:
1. Log in as `rbf_official` / `Rbf@1234`.
2. **Create a Tender**:
   - Go to Tenders → Create New Tender.
   - Fill in all required fields (name, department, technology type, budget, deadline, etc.).
   - Save as Draft, then Verify, then Publish.
3. **Manage Bids**:
   - After vendor bidding, go to the tender's Evaluation stage.
   - Review bids (if TAC role not available, simulate by approving).
4. **Award Tender**:
   - In the Award stage, select a winning bid and confirm award.
5. **Generate PBA**:
   - After awarding, go to Contracting → Generate PBA.
   - Review the generated PBA and mark as ready for vendor signature.
6. **Process Payment Claim**:
   - After vendor submits a claim, go to Payment Claims.
   - Perform Verify → Approve → Finalize stages.
7. **Review Vendor Prequalification**:
   - Go to Vendor Management → Prequalifications.
   - Review a pending application and approve or reject.
8. **Post a Notice**:
   - Go to Notice Management → Create Notice.
   - Publish a test announcement.

### 4.3 TAC Member (Technical Advisory Committee)

**Primary Responsibility**: Technical evaluation and endorsement.

**Key Functions**:
- **Bid Evaluation**: Review and score technical bids during tender stages.
- **Claim Endorsement**: Technically verify and endorse payment claims before RMT approval.
- **Technical Dashboard**: View items awaiting technical review.
- **Reports**: Access technical performance reports via Reports Hub.

**Testing Steps**:
1. Log in as `tac_member` / `Tac@1234`.
2. **Evaluate a Bid**:
   - Go to Tenders → Find a tender in Evaluation stage.
   - Open a bid and complete the technical evaluation form (score, comments).
   - Submit evaluation.
3. **Endorse a Payment Claim**:
   - Go to Payment Claims → Find a claim in Verification stage.
   - Review technical details and endorse the claim.
4. **Check Technical Dashboard**:
   - View your dashboard for pending technical reviews.
5. **Generate a Report**:
   - Go to Reports Hub → Select a technical report (e.g., Bid Evaluation Summary).
   - Generate and download the report.

### 4.4 DoE Officer (Department of Energy)

**Primary Responsibility**: Regional monitoring and community-level oversight.

**Key Functions**:
- **Regional Dashboard**: Monitor projects in assigned districts.
- **Raise Concerns**: Flag project-level issues (quality, KPI risks) to RMT/PSC.
- **Regional GIS Map**: View installations in region (read-only).
- **Regional KPI Monitoring**: Track regional progress against national targets.

**Testing Steps**:
1. Log in as `doe_officer` / `Doe@1234`.
2. **Access Regional Dashboard**:
   - View projects assigned to your district (e.g., Maseru).
3. **Raise a Concern**:
   - Find a project and click "Raise Concern".
   - Describe an issue (e.g., "Potential GPS mismatch") and submit.
4. **View Regional GIS Map**:
   - Go to Regional Map to see installation locations.
5. **Check Regional KPIs**:
   - View KPI progress for your region vs. national targets.

### 4.5 Project Steering Committee (PSC)

**Primary Responsibility**: Strategic oversight and escalation management.

**Key Functions**:
- **Macro KPI Portal**: National progress, inclusion compliance, payment pacing.
- **Escalation Oversight**: View serious concerns from DoE or Auditor findings.
- **PSC Directives**: Add comments/directives to escalated issues for RMT.
- **Resolution Power**: Mark escalated issues as resolved after RMT action.

**Testing Steps**:
1. Log in as `donor_user` / `Donor@1234`.
2. **Access Macro KPI Portal**:
   - View national dashboards for progress, inclusion, payments.
3. **Review Escalations**:
   - Go to Escalation Oversight to see issues raised by DoE or Auditor.
4. **Add a Directive**:
   - On an escalated issue, add a comment instructing RMT on required action.
5. **Mark as Resolved**:
   - After RMT action, mark the issue as resolved.

### 4.6 Auditor

**Primary Responsibility**: Compliance verification and fraud detection.

**Key Functions**:
- **Auditor Dashboard**: System compliance summary, anomaly statistics, failed syncs.
- **Full GIS & KPI Access**: Read-only access to all geographic and performance data.
- **Anomaly Reporting**: Flag suspicious patterns (GPS fraud, KPI manipulation).
- **Audit Findings**: Formalize findings, recommend actions, track RMT responses.
- **Full System Audit Trail**: Unrestricted access to logs and Prospect sync activity.

**Testing Steps**:
1. Log in as `auditor_user` / `Auditor@1234`.
2. **Review Auditor Dashboard**:
   - Check compliance summary and anomaly statistics.
3. **Access Full GIS Map**:
   - View all installations nationwide.
4. **Run Anomaly Check**:
   - Use the Anomaly Reporting tool to scan for irregularities.
5. **Create an Audit Finding**:
   - Formalize an observation, recommend action, and assign to RMT.
6. **Access Audit Logs**:
   - Review system logs for a specific time period or user action.

### 4.7 Field Verifier

**Primary Responsibility**: Physical verification of installations and field-level data integrity.

**Key Functions**:
- **Field Inspections**: Access verification tasks assigned to district/zone.
- **Mobile-Optimized Verification**: Capture GPS, verify serials, document functionality.
- **Inspection Outcomes**: Mark as Verified, Flagged (issues), or Partial.
- **Regional GIS Mapping**: View assigned sites to plan routes.
- **Activity & History**: Track personal verification performance.
- **Task Notifications**: Alerts for new installations ready for verification.

**Testing Steps**:
1. Log in as `field_verifier` / `Field@1234`.
2. **Access Verification Tasks**:
   - Go to Field Verification → View assigned tasks.
3. **Perform a Verification**:
   - Select a task and follow the multi-step inspection:
     - Capture live GPS coordinates.
     - Verify equipment serial numbers against records.
     - Test system functionality (e.g., light operation).
     - Take photos of the installation.
   - Submit outcome as Verified, Flagged, or Partial.
4. **View Regional Map**:
   - Use the map to locate assigned sites and plan your route.
5. **Check History**:
   - Review your past verification activities and performance.

### 4.8 Vendor (For Testing the Full Lifecycle)

**Primary Responsibility**: Bidding, project execution, installation, and payment claims.

**Key Functions**:
- **Registration**: Sign up with organizational and technical details.
- **Bidding**: View tenders, prepare and submit bids.
- **Contracting**: Review and sign PBA upon award.
- **Project Setup**: Enter technical details, upload documents, test meter connection.
- **Installation**: Report progress, upload installation details and photos.
- **Payment Claims**: Submit claims for verified installations.
- **Dashboard**: Monitor bid status, project progress, claim status.

**Testing Steps (End-to-End Flow)**:
> *Note: This flow tests the complete RBF cycle from vendor registration to payment.*

1. **Register as a Vendor**:
   - Go to the login page and click "Register your organization first".
   - Fill in registration form (use any valid details for testing).
   - Upload a dummy registration certificate (PDF/JPG).
   - Verify email with OTP (use debug OTP if shown).
   - Complete registration.

2. **Log in as Vendor**:
   - Use your newly created credentials.

3. **View and Bid on a Tender**:
   - Go to Tenders → Find a published tender (e.g., one created by RMT).
   - Review tender details.
   - Click "Prepare Bid" and fill in technical and commercial details.
   - Submit bid.

4. **Await Award and Sign Contract**:
   - Monitor tender status.
   - If awarded, go to Contracting → Review PBA.
   - Sign the PBA digitally.

5. **Complete Project Setup**:
   - Go to My Projects → Select the awarded project.
   - Enter technical details (device model, brand, tech tier, etc.).
   - Upload required documents (team roster, equipment plan, compliance, insurance).
   - Enter meter API endpoint and token (use test values if needed).
   - Test connection or save draft.
   - Mark setup as complete.

6. **Report Installation**:
   - After installations are done, go to Installation Reporting.
   - For each installation:
     - Enter GPS coordinates.
     - Upload photos.
     - Enter beneficiary details and serial numbers.
     - Submit report.

7. **Request Field Verification**:
   - After reporting installations, request verification from Field Verifiers.

8. **Submit Payment Claim**:
   - Go to Payment Claims → Submit New Claim.
   - Select verified installations.
   - Enter claimed amount based on RBF formula.
   - Upload supporting documents (installation reports, verification certificates).
   - Submit claim.

9. **Monitor Claim Status**:
   - Track claim through stages: Submission → TAC Verification → RMT Approval → Finalization → Payment.

## 5. Common Portal Features

### 5.1 Notifications
- All users receive real-time alerts for tasks requiring attention (e.g., new bids to evaluate, verification tasks, claim submissions).
- Access via the bell icon in the top navigation.

### 5.2 Reports Hub
- Centralized location to generate and download reports (Excel/PDF).
- Available reports include: tender status, project progress, payment summary, KPI compliance, audit trails.
- Users can filter by date, region, project, etc.

### 5.3 Impact Portal
- Public-facing dashboard showing social and environmental impact of the RBF program.
- Accessible to all logged-in users via the main navigation.
- Displays metrics like: households powered, CO2 savings, female inclusion, jobs created.

## 6. End-to-End Testing Scenario

To test the entire system, follow this scenario using multiple user roles:

1. **Admin Setup**:
   - Admin logs in and sets global female inclusion target to 40%.

2. **Tender Creation**:
   - RMT logs in and creates a tender for 500 SHS installations in Maseru district.
   - Tender is published.

3. **Vendor Participation**:
   - Vendor registers and logs in.
   - Vendor views tender, prepares bid (proposing 45% female inclusion), and submits.

4. **Technical Evaluation**:
   - TAC logs in, reviews bid for technical compliance, and endorses.

5. **Award and Contracting**:
   - RMT awards tender to vendor.
   - RMT generates PBA; vendor reviews and signs it.

6. **Project Setup**:
   - Vendor logs in, enters project details (device info, meter API), uploads documents, and completes setup.

7. **Installation and Verification**:
   - Vendor reports 100 installations.
   - Field Verifier logs in, assigns verification tasks, and verifies 80 installations (20 flagged for minor issues).
   - Vendor corrects flagged installations and re-reports.

8. **Payment Claim**:
   - Vendor submits claim for 80 verified installations.
   - TAC logs in, technically endorses claim.
   - RMT logs in, verifies, approves, and finalizes claim.
   - System marks claim as paid.

9. **Monitoring and Compliance**:
   - DoE Officer logs in, checks regional dashboard for Maseru, and raises a concern about one installation's GPS.
   - PSC logs in, views escalation, adds directive to RMT to investigate.
   - Auditor logs in, runs anomaly check, finds no systemic issues, and notes the DoE concern.
   - RMT investigates concern, resolves it, and updates PSC and Auditor.

10. **Reporting**:
    - All users can generate reports from Reports Hub to review the tender, project, and payment details.

## 7. Troubleshooting and FAQs

**Q: I can't log in with demo credentials.**
A: Ensure you are using the exact username and password. Demo users may need to be bootstrapped on first login; wait a moment and try again.

**Q: I don't see any tenders to bid on.**
A: Check that a tender has been published by the RMT. If not, ask an RMT user to create and publish one.

**Q: My payment claim is stuck in verification.**
A: Ensure the TAC has technically endorsed the claim. If not, notify the TAC member to review.

**Q: I can't upload a file; it says invalid format.**
A: Check the accepted formats (usually PDF, JPG, PNG for certificates; CSV for meter data). Ensure file size is under the limit (typically 10MB).

**Q: The map isn't showing any installations.**
A: Verify that installations have been reported and verified. Check that your region filter matches the installation locations.

**Q: I forgot my password.**
A: Password reset must be done by an Administrator. Contact the Platform Administrator (`admin_user`) to reset it.

## 8. Conclusion

This guide provides all necessary information for non-technical users to understand, navigate, and test the Renewable Lesotho RBF Platform. By following the role-specific steps and the end-to-end scenario, users can validate the entire RBF lifecycle from tender to payment and compliance monitoring.

For further assistance, contact the system administrator or refer to the in-platform help tooltips.

---
*Document Version: 1.0*
*Last Updated: $(date)*