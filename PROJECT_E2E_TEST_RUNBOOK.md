# Project E2E Test Runbook

This guide is for the project implementation flow, not the tender flow.

It is written so you can test the portal end to end without searching through the codebase for:
- login credentials
- UI tab names
- button labels
- backend truth-check endpoints
- meter CSV format

## 1. Local URLs

- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/api/docs/`
- MailHog: `http://localhost:8025`
- Health check: `http://localhost:8000/api/health/`

## 2. Startup

Backend:

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

Frontend:

```bash
npm install
npm run dev
```

## 3. Demo Logins

These users are seeded automatically by `python manage.py seed_demo_users`.

| Role | Username | Password |
|---|---|---|
| Vendor | `vendor_approved` | `Vendor@1234` |
| RBF Management Team | `rbf_official` | `Rbf@1234` |
| TAC Member | `tac_member` | `Tac@1234` |
| Project Steering Committee | `donor_user` | `Donor@1234` |
| Field Verifier | `field_verifier` | `Field@1234` |
| Admin | `admin_user` | `Admin@1234` |

## 4. Important Precondition

The repo seeds demo users, but it does not seed a guaranteed vendor-owned project for `vendor_approved`.

For the full 17-step flow to work, you need a project that already has:
- the vendor assigned
- an approved contract
- milestones present

Without that, step 1 can fail even though login works.

Current live local database status I verified:
- the app is running on `2026-04-16`
- there are existing projects in the database
- there are existing claims and installation records
- but those projects are not guaranteed to belong to the seeded `vendor_approved` account

If step 1 does not show a project for `vendor_approved`, use one of these approaches:
- use the existing database snapshot/environment where a vendor already owns a project
- assign a project to the test vendor from the admin/RMT side before starting this runbook

## 5. Vendor UI Map

After vendor login:
- left nav: `Projects Hub`
- inside a project: `Overview`, `Planning`, `Map View`, `Milestones`, `Field Work`, `Payments`, `Documents`, `Updates`

Important vendor buttons:
- `Complete Setup`
- `Submit Installation`
- `Submit Project Setup`
- `Submit Claim`
- `+ Submit New Installation`
- `Upload CSV Meter Data`

Important RMT / approval-side labels:
- claim action for RMT: approve at RMT step
- TAC step: endorse / approve the claim
- PSC step: approve and initiate payment
- RMT final action: `Mark As Paid`

## 6. Project Setup Sections

The `Planning` tab has 4 sections.

### Section A - Team & Resources
- Team roster file
- Equipment sourcing plan
- Team roster finalized
- Equipment sourcing confirmed
- Deployment sites confirmed
- Safety briefing completed
- Logistics mobilization confirmed

### Section B - Site Preparation
- Site status
- Work schedule start
- Work schedule end
- Permits / compliance docs
- Insurance certificate

### Section C - Technology Details
- Device brand
- Device model
- Technology tier

### Section D - Verification Method
- Manual verification confirmation
- or meter API endpoint/token if the project verification method is IoT

## 7. Meter CSV Format

The frontend template downloads this exact header:

```csv
meter_id,installation_id,recorded_at,kwh_generated,uptime_pct
METER-001,,2026-04-01T08:00:00Z,12.5,98.7
```

Backend validation rules:
- file must be `.csv`
- max size is `5MB`
- `meter_id` is required
- `installation_id` or `meter_id` must match an installation in the same project for the same vendor
- `kwh_generated` must be non-negative
- `uptime_pct` must be between `0` and `100`
- `recorded_at` must be valid ISO 8601 datetime

## 8. Step-By-Step Test Flow

### Step 1. Log in as Vendor

Path:
- Frontend -> login
- sign in as `vendor_approved`
- open `Projects Hub`
- open an assigned project

Expected:
- project card/details are visible
- if setup is incomplete, the `Project Setup Required` banner is visible
- `Submit Installation` is disabled until setup is complete

If you cannot find a project:
- this is a data setup issue, not a UI issue
- the repo does not auto-seed a project for `vendor_approved`

### Step 2. Complete Project Setup

Path:
- project -> `Planning`

Fill all 4 sections:
- Section A - Team & Resources
- Section B - Site Preparation
- Section C - Technology Details
- Section D - Verification Method

Upload required files:
- Team roster file
- Equipment sourcing plan
- Permits / compliance docs
- Insurance certificate

Action:
- click `Submit Project Setup`

Expected:
- setup becomes read-only
- project status becomes `active`
- installation submission becomes enabled
- milestone 1 becomes `Claimable`
- setup banner changes to complete/read-only messaging

### Step 3. Confirm KPI / Prospect / milestone effect after setup

Path:
- project -> `Milestones`
- project -> `KPI`
- later, admin/RMT -> Prospect sync logs if exposed in UI

Expected:
- M1 shows `Claimable`
- M2 and M3 remain locked
- KPI cards show little or no data yet
- backend should eventually show a `pushAgent` Prospect sync entry

### Step 4. Submit Milestone 1 Claim as Vendor

Path:
- project -> `Milestones`
- on the claimable milestone, click `Submit Claim`
- tick declaration
- submit

Expected:
- claim appears in vendor payment history
- milestone goes to an under-review/claimed state
- duplicate M1 claim is blocked

### Step 5. Log in as RMT

Path:
- log out
- log in as `rbf_official`
- open claims / disbursement area
- open the submitted M1 claim
- approve at the RMT step

Expected:
- claim status becomes `RMT Approved`

### Step 6. Log in as TAC

Path:
- log out
- log in as `tac_member`
- open the same claim
- endorse it

Expected:
- claim status becomes `TAC Endorsed`

### Step 7. Log in as PSC

Path:
- log out
- log in as `donor_user`
- open the same claim
- approve and initiate payment

Expected:
- claim status becomes `PSC Approved`
- this means approved and initiated, not fully paid yet

### Step 8. Log back in as RMT

Path:
- log in as `rbf_official`
- open the same claim again
- click `Mark As Paid`

Expected:
- claim status becomes `Completed`
- milestone 1 becomes paid

### Step 9. Submit an Installation as Vendor

Path:
- log back in as vendor
- project -> `Field Work`
- click `+ Submit New Installation`

Enter:
- beneficiary info
- serial number
- GPS latitude/longitude
- installation date if needed
- photos / receipt
- meter ID and kWh if available

Expected:
- new installation appears in the table
- it starts as pending/submitted
- GIS/map shows pending marker
- verified KPI should not increase yet

### Step 10. Verify the Installation as Field Verifier

Path:
- log out
- log in as `field_verifier`
- open verification queue
- open the submitted installation
- complete the verification form
- submit as verified

Expected:
- installation becomes verified
- GIS marker turns green
- KPI verified count increases
- female/vulnerable/low-income metrics update based on the installation data

### Step 11. Test a Flagged Verification

Action:
- submit another installation as vendor
- verify it as field verifier with a mismatch or flagged outcome

Expected:
- installation becomes flagged
- GIS marker turns red
- anomaly flag appears
- milestone readiness should reflect open flags where relevant

### Step 12. Upload Meter CSV as Vendor

Path:
- vendor -> project -> `Field Work`
- go to `CSV upload section`
- click `Download CSV Template`
- upload a valid CSV

Expected:
- success message appears
- energy and uptime KPI cards update
- invalid rows are reported if present
- anomaly flags appear when anomaly conditions are triggered

### Step 13. Check KPI After Verification + Meter Upload

Path:
- project -> `KPI`

Expected:
- installation progress changes
- female-headed KPI changes
- uptime changes
- energy changes
- milestone readiness conditions update

### Step 14. Check GIS

Path:
- project -> `Map View`

Expected:
- pending installations show pending markers
- verified installations show green markers
- flagged installations show red markers
- counts match installation statuses

### Step 15. Check Payment Progression for M2 and M3

Action:
- keep submitting and verifying installations
- upload meter data when needed
- watch milestone readiness in `KPI` and `Milestones`

Expected:
- M2 becomes claimable only when its conditions are met
- M3 becomes claimable only when its conditions are met
- once claimable, they should not downgrade back to locked because ratios later shift

### Step 16. Confirm Prospect

Frontend alone is not enough for this.

Check after:
- setup submit
- installation submit
- verification
- meter CSV upload
- final completion

Expected Prospect log types:
- setup: `pushAgent`
- installation submit: `pushCustomer`, `pushInstallation`
- verification update: `pushInstallation`
- meter CSV: `pushInstallationTimeSeries`
- completion: `pushReport`

### Step 17. Final Completion

Action:
- complete the M2 and M3 claim chain the same way as M1
- after final payment confirmation, refresh the project

Expected:
- project status becomes `Completed`
- all milestones show paid/completed
- final report sync is queued

## 9. GIS and KPI State Progression

This section maps the project from the moment setup is completed through installation submission, verification, meter upload, and milestone unlocking.

### Starting State

After successful setup submission:
- `project.status = active`
- `project_setup.setup_completed_at` is set
- M1 becomes `claimable`
- M2 and M3 remain locked
- zero installations may still exist

### Vendor GIS Immediately After Setup Completion

What to expect:
- `Map View` loads the Lesotho outline
- if no installations exist yet, no pins appear
- summary row should remain at:
  - verified `0`
  - pending `0`
  - flagged `0`

Meaning:
- setup completion alone does not create installation pins
- GIS stays empty until the first installation is submitted

### Vendor KPI Immediately After Setup Completion

What to expect:
- installation progress shows `0 / target`
- female %, uptime %, and energy may show `No data` or empty values
- milestone readiness should show:
  - M1 `CLAIMABLE`
  - M2 `Locked`
  - M3 `Locked`

Meaning:
- setup unlocks milestone eligibility logic
- setup does not create verified-installation KPI values by itself

### After Vendor Submits the First Installation

Database effect:
- a new installation record is created
- `gis_status = yellow`
- installation status remains pending/submitted until field verification
- Prospect sync jobs are queued for installation/customer payloads

Vendor GIS effect:
- one yellow pin appears on the map
- summary row should now show:
  - verified `0`
  - pending `1`
  - flagged `0`

Vendor KPI effect:
- KPI totals should still not count this as verified progress
- installation submission alone does not increase verified KPI counts

Meaning:
- yellow means submitted but not yet verified
- pending installations are visible on GIS before they affect KPI readiness

### After Field Verification Marks the Installation as Verified

Database effect:
- installation status becomes `Verified`
- `gis_status` changes from `yellow` to `green`
- KPI refresh runs
- Prospect installation update is re-queued

Vendor GIS effect:
- that same pin turns green
- summary row updates from pending to verified

Vendor KPI effect:
- verified installation count increases
- installation progress recalculates
- gender KPI starts reflecting actual verified household composition
- M2 and M3 conditions are re-evaluated

Meaning:
- verified installations are what drive KPI progress
- pending installations are visible operationally, but they do not satisfy milestone thresholds

### After a Verification is Flagged

Database effect:
- installation becomes `Flagged`
- `gis_status = red`
- anomaly flag record is created

GIS effect:
- the installation pin turns red
- flagged count increases

KPI effect:
- unresolved flags can block milestone readiness
- milestone conditions around anomaly clearance must be re-checked

Meaning:
- red indicates a verification issue or anomaly
- open flags can keep M2/M3 locked even when counts look strong

### After Meter CSV Upload

Database effect:
- smart meter readings are created for valid rows
- meter CSV audit log is created
- anomaly flags may be raised for:
  - `zero_uptime`
  - `no_data`
  - `output_deviation`
- `pushInstallationTimeSeries` is queued to Prospect

KPI effect:
- uptime KPI updates
- energy KPI updates
- milestone readiness checks that depend on meter data can flip to met

Meaning:
- installation verification drives beneficiary/count KPIs
- meter CSV drives uptime/energy KPIs

### When M2 Threshold Is Reached

Typical expectation:
- once the project satisfies M2 readiness conditions, M2 changes to `CLAIMABLE`
- M1 may already be `PAID`
- M3 remains locked until final completion criteria are met

Core readiness checks for M2 include:
- setup complete
- sufficient verified installation progress
- female-headed KPI at target
- no unresolved blocking anomaly flags
- meter data present

### Role-Limited Visibility on GIS and KPI

#### Vendor

Can see:
- own projects only
- own project installations only
- project-level KPI dashboard
- pending, verified, and flagged installation states

Cannot see:
- other vendors' projects
- system-wide map or portfolio-wide KPI

#### Field Verifier

Can see:
- installations in current verifier scope
- district-level route-planning map
- verification queue and verification history
- anomaly review within verifier scope

Cannot see:
- vendor KPI dashboard
- portfolio KPI dashboard

#### RMT / Admin

Can see:
- all projects
- portfolio KPI summary
- project KPI dashboards
- full GIS views
- Prospect sync logs
- anomaly flags
- disbursement and claim workflow

Can do:
- approve submitted claims at RMT step
- mark PSC-approved claims as paid
- resolve anomaly flags

#### TAC

Can see:
- project KPI dashboards through backend permissions
- claim review workflow

Current frontend note:
- TAC is routed to the technical evaluation interface, so project GIS/KPI evidence may not yet appear as a dedicated TAC-specific claim evidence screen in the same polished form as the vendor/RMT project hub

#### DoE Officer

Backend scope:
- KPI access is region-limited
- anomaly flags are region-limited

Current frontend note:
- the DoE interface in `src/App.tsx` is currently more of a regional monitoring/demo-style screen than a fully backend-driven GIS/KPI workspace

#### PSC / Project Steering Committee

Backend scope:
- can process the PSC approval/initiation step for claims
- can read Prospect sync logs
- can access KPI dashboards via backend permissions

Current frontend note:
- the PSC role is implemented as `Project Steering Committee`
- the frontend emphasizes disbursements and donor-style portfolio views rather than a dedicated PSC claim evidence screen with embedded map/KPI widgets

#### Auditor

Backend scope:
- read access to audit logs, Prospect sync logs, KPI dashboards, and anomaly flags

Current frontend note:
- the auditor portal includes audit/compliance views, but parts of it are still demo-style rather than fully wired to the same live project GIS/KPI workflows as vendor/RMT

#### Super Admin

Can see:
- effectively the full RMT/admin scope
- system management views in addition to project and claim data

## 10. GIS and KPI Scope Matrix

| User | GIS Scope | KPI Scope | Notes |
|---|---|---|---|
| Vendor | Own project only | Own project only | Full project implementation testing happens here |
| Field Verifier | Current verifier scope / district workflow | No dedicated KPI dashboard | Map is operational for route planning and verification |
| RMT | All projects | Portfolio + project KPI | Main oversight role |
| Admin | All projects | Portfolio + project KPI | Similar to RMT with extra admin controls |
| TAC | Limited by current frontend flow | Backend allows project KPI access | Frontend is not yet a dedicated KPI/map evidence workspace |
| DoE Officer | Region-oriented concept | Region-limited KPI access in backend | Frontend currently more demo/regional-monitoring style |
| PSC | No dedicated standalone GIS page today | Donor/disbursement-oriented portfolio view | Payment approval role |
| Auditor | Read-only broad access | Read-only broad access | Frontend partly demo-style |

## 11. Complete Data Flow

```text
Vendor submits installation
        ↓
Installation record created
status = submitted/pending
gis_status = yellow
        ↓
GIS map shows yellow pin
        ↓
KPI does not yet count it as verified progress
        ↓
Prospect jobs queue:
pushCustomer + pushInstallation
        ↓
Field verifier verifies on site
        ↓
Installation updated
status = verified or flagged
gis_status = green or red
        ↓
GIS pin color changes
        ↓
KPI refresh runs
verified totals / gender / readiness recompute
        ↓
Prospect installation sync re-queued
        ↓
If meter CSV uploaded:
smart meter readings created
uptime + energy KPI update
pushInstallationTimeSeries queued
        ↓
If milestone conditions are met:
M2 or M3 becomes claimable
vendor can submit next claim
```

## 12. Backend Truth-Check Endpoints

Use these to verify what the UI is showing.

### Prospect sync logs

```text
/api/projects/prospect-sync-logs/
```

Use this to confirm:
- queued sync method names
- pending/failed/success states
- whether setup/installations/meter uploads are creating sync records

### Project KPI summary

```text
/api/kpi/project/<project_id>
```

Use this to confirm:
- verified installation counts
- female/vulnerable/low-income metrics
- uptime and energy metrics
- milestone readiness conditions

### GIS installation map data

```text
/api/map/installations?project_id=<project_id>
```

Use this to confirm:
- pending markers
- green verified markers
- red flagged markers
- map count/status consistency

## 13. What Frontend Alone Can and Cannot Prove

Frontend can confirm:
- portal flow
- status transitions
- KPI rendering
- GIS rendering
- role-based actions

Frontend cannot fully prove:
- Prospect delivery really succeeded downstream
- retry logic worked
- all backend notifications fired
- async jobs completed on the external side

For those, also inspect:
- `/api/projects/prospect-sync-logs/`
- `/api/kpi/project/<project_id>`
- `/api/map/installations?project_id=<project_id>`

## 14. Fast Failure Checklist

If the flow breaks early, check these first:
- backend health is up at `/api/health/`
- frontend is using `http://localhost:8000`
- your vendor actually has an assigned project
- the project contract is approved before setup submission
- the project setup is completed before installation or meter CSV upload
- the field verifier is allowed to verify the project district
- the claim is moving in the correct role order:
  - Vendor submit
  - RMT approve
  - TAC endorse
  - PSC approve/initiate
  - RMT confirm paid
