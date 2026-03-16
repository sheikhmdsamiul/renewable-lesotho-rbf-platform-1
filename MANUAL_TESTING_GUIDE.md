# Tender Management - Manual Frontend Testing Guide

## Prerequisites

1. **Backend Running**: Confirm backend is healthy
   ```bash
   curl http://localhost:8000/api/health/
   # Should return: {"status": "ok", "checks": {"database": {"ok": true}}}
   ```

2. **Frontend Running**: 
   ```bash
   npm run dev
   # Vite should be running on http://localhost:5173
   ```

3. **Login as RBF Official**:
   - Navigate to `http://localhost:5173/` 
   - Use credentials for RBF_OFFICIAL role
   - Demo user: `rbf_official` (check .env for password)

4. **Test Data Ready**:
   - Have technology types available (Mini-grid, SHS, ICS, SWP, PUE, SAS)
   - Have a test PDF file ready for tender schedule upload
   - Have test vendors/vendors created for awarding

---

## Feature 1: Create Tender with All Required Fields

### UI Path
```
Dashboard → Tenders → Add Tender / Create New Tender
```

### Required Fields to Fill

| Field | Test Value | Notes |
|-------|-----------|-------|
| **Tender Name** | "Solar Installation Project - Region A" | Max 50 chars |
| **Department** | "Energy Department" | Mandatory |
| **Category** | "Solar / Mini-grid" | Choose from dropdown |
| **Application Type** | "Open Access" | Dropdown selection |
| **Stage Type** | "Pre-Qualification" | Pre-Qual or Site-Specific |
| **Procurement Method** | "Competitive Bidding" | Dropdown |
| **Address for Tender Document** | "Energy Ministry, Main Office, Capital City" | Valid address format |
| **Address for Tender Security** | "Central Bank, Head Office, Capital City" | Valid address format |
| **Place for Tender Opening** | "Conference Room 203, Energy Ministry" | Valid format |
| **Bidders Eligibility** | "Must be registered businesses with 2+ years experience in renewable energy" | Detailed text (300 chars) |
| **Time for Completion** | "6 months from award date" | General text |
| **Tender Invited By** | "UNDP Lesotho Office" | Organization name |
| **Bidding Currency** | "LSL (Lesotho Loti)" | Currency dropdown |
| **Instructions** | "All bids must be submitted in sealed envelopes..." | Detailed instructions |
| **Contact Details** | "Tel: +266-123-4567, Email: tenders@energy.ls" | Valid contact format |
| **Target Site Type** | "Household" | Household/Business/School/Clinic |
| **Deadline** | 2026-04-15 23:59 | Future date |
| **Security Deadline** | 2026-04-10 17:00 | Before deadline |
| **Submission Deadline** | 2026-04-14 17:00 | Before opening |
| **Opening Date** | 2026-04-16 10:00 | After submission |

### Optional Fields (Leave Default)
- Pre-Tender Meeting Info: (leave blank or add if needed)
- Bidders Schedule Purchase: (unchecked)
- Tender Security Required: (unchecked)
- Budget: (leave empty)
- Funding Source: (leave empty)

### Technology Types Selection
**Action**: Click "Technology Types" multi-select
- ✓ Select at least 1: Check **"Mini-grid"**
- ✓ Can select multiple: e.g., Mini-grid + SHS + ICS

### File Upload
**Action**: Click "Upload Schedule" or file input
- Select a test PDF/DOC file (≤10MB)
- **Success**: File name appears below input
- **Error**: Size > 10MB or wrong format shows error message

### Submit
**Action**: Click "Save" button
- **Success Scenario (Draft)**:
  ```
  Tender created successfully
  Status: Draft
  Reference Number: TND-000001 (auto-generated)
  Redirect to: Tender Details page
  ```

### Verify in UI
1. Navigate to **Tenders List**
2. Look for your tender with:
   - Status badge: **"Draft"** (grey color)
   - Reference: **TND-000001**
   - Your tender name
3. Click on tender to view full details
4. Confirm all fields saved correctly

---

## Feature 2: Search & Filter Tenders

### UI Path
```
Tenders → Filter/Search Section (at top of list)
```

### Test Case 1: Filter by Status
**Action**:
1. Find filter dropdown: "Status"
2. Select: **"Published"**
3. Click: **"Search Now"** or auto-filter applies
4. **Expected Result**: 
   - Only published tenders appear
   - Count updates (e.g., "Showing 3 of 15")

### Test Case 2: Filter by Category
**Action**:
1. Find dropdown: "Category"
2. Select: **"Solar"**
3. Apply filter
4. **Expected Result**:
   - Only Solar category tenders shown
   - Can combine with Status filter

### Test Case 3: Filter by Department
**Action**:
1. Find dropdown: "Department"
2. Select: **"Energy Department"**
3. Apply
4. **Expected Result**:
   - Filtered by department
   - Works with other filters

### Test Case 4: Search by Keyword
**Action**:
1. Find "Search" text input
2. Type: **"Solar"** or **"TND-000001"**
3. Click **"Search Now"**
4. **Expected Result**:
   - Tenders matched by name or reference number
   - Results update with highlighted matches

### Test Case 5: Advanced Filters (if implemented in UI)
**Action**:
1. Click **"Advanced Filters"** (if available)
2. Set **Date Range**: From: 2026-03-01, To: 2026-04-01
3. Set **Budget Range**: Min: 50000, Max: 500000
4. Set **Procurement Method**: "Competitive Bidding"
5. Apply
6. **Expected Result**:
   - Filtered by all criteria
   - Results narrow down correctly

### Test Case 6: Sort Results
**Action**:
1. Find "Sort By" dropdown
2. Select: **"Deadline (Nearest)"**
3. **Expected Result**:
   - List reorders by deadline ascending
4. Select: **"Budget (Highest)"**
5. **Expected Result**:
   - List reorders by budget descending

### Verify Multi-Filter Works
**Action**: Apply Status=Published + Category=Solar + Department=Energy
- **Expected**: List shows only published solar tenders from Energy Dept
- Filters stack/combine correctly

---

## Feature 3: Verify Tender

### Prerequisites
- Have a tender in "Draft" status
- Be logged in as RBF Official

### UI Path
```
Tenders List → Find Draft tender → Click → Details Page
OR
Tenders → Search for Draft tender
```

### Action: Verify Tender
1. Open tender in **Draft** status
2. Look for button: **"Verify"** or **"Verify Tender"**
3. Click the button
4. **Modal/Dialog appears** (confirm verification):
   - Shows tender details for review
   - Message: "Confirm verification of this tender?"
5. Click: **"Confirm Verify"**

### Verify Success
1. **UI Updates**:
   - Status badge changes: **"Draft"** → **"Verified"**
   - New field appears: **"Verified At"**: 2026-03-11 04:21 (timestamp)
   - Button "Verify" disappears/disables
   - New button appears: **"Publish"** (activates)

2. **In Tender List**:
   - Tender now shows: Status = "Verified" or pending publish
   - Can see verified timestamp

3. **Audit Log** (if visible in UI):
   - Shows: "Tender verified by RBF_OFFICIAL at 2026-03-11 04:21"

---

## Feature 4: Publish Tender with Notifications

### Prerequisites
- Tender status: **"Verified"**
- Have at least one vendor account created

### UI Path
```
Tenders List → Click Verified Tender → Details Page → "Publish" Button
```

### Action: Open Publish Dialog
1. Click button: **"Publish Tender"**
2. **Dialog/Modal Opens** with options:
   ```
   ☐ Send Email Notification (recommended)
   ☐ Send SMS Notification
   
   ○ Notify All Bidders
   ○ Notify Category-Specific Bidders
   
   [Publish] [Cancel]
   ```

### Test Case 1: Publish with Email Only
1. Check: ✓ **"Send Email Notification"**
2. Uncheck: ☐ SMS
3. Select: ○ **"Notify All Bidders"**
4. Click: **"Publish"**
5. **Expected Result**:
   ```
   ✓ Tender Published Successfully
   Status: Published
   Published At: 2026-03-11 04:25
   ```

### Verify Notifications Sent
1. **In-App Notifications**:
   - Switch to Vendor account
   - Check "Notifications" bell icon
   - Should see: "Tender Published: Solar Installation Project - Region A"
   - Click to navigate to tender

2. **Email Notifications**:
   - Check MailHog (email simulator): `http://localhost:8025`
   - Look for email from: `noreply@rbf.local`
   - Subject: "Tender Published: Solar Installation Project - Region A"
   - Body contains:
     - Tender name
     - Reference number
     - Deadline
     - View link

### Test Case 2: Publish with SMS Option
1. Check: ✓ **"Send Email"**
2. Check: ✓ **"Send SMS"**
3. Publish
4. **Expected Result**:
   - Success message
   - Tender status: Published
   - Note: SMS won't actually send unless gateway configured (logs attempt)

### Test Case 3: Category-Specific Notification
1. Select: ○ **"Notify Category-Specific Bidders"**
2. (If UI shows category selector, select specific category)
3. Publish
4. **Expected Result**:
   - Only vendors in that category receive notifications

### Verify UI Updates
1. **Tender Details Page**:
   - Status: **"Published"** (blue badge)
   - "Published At": timestamp updated
   - "Publish" button hidden/disabled
   - New button: **"Award"** appears

2. **Tenders List**:
   - Status shows: Published
   - Vendor can now see this tender

---

## Feature 5: Security Verification Workflow

### Prerequisites
- Tender status: **"Awarded"**
- Have an awarded tender ready

### UI Path
```
Tenders → Security Verification (or Admin Tab)
OR
Tenders List → Filter by Status="Awarded" → "Verify Security" button
```

### Test Case 1: Search for Tenders Needing Security Verification

**Action**: 
1. Go to **"Security Verification"** section/page
2. See search filters:
   ```
   Search By: [Search Key...]
   Award Date: [From] [To]
   Sort By: [Dropdown]
   Limit: [50]
   [Search Now]
   ```

**Fill Search**:
- Search Key: Leave empty (or type tender name/reference)
- Award Date: Leave empty or set range
- Click: **"Search Now"**

**Expected Result**:
```
Matching Tenders:
┌─────────────────────────────────────────┤
│ TND-000002 | Solar Project | Awarded    │
│ Awarded Date: 2026-03-10                │
│ Status: Pending Security Verification   │
│ [Verify Security] Button                │
└─────────────────────────────────────────┘
```

### Test Case 2: Verify Security Deposit
**Action**:
1. Find tender in security verification list
2. Click: **"Verify Security"** button

**Confirmation Dialog**:
```
Confirm Security Deposit Verification?

Tender: TND-000002 - Solar Installation
Awarded to: Vendor Name
Award Date: 2026-03-10

[Verify Now] [Cancel]
```

3. Click: **"Verify Now"**

**Expected Result**:
```
✓ Security Deposit Verified Successfully

Tender updated:
- Security Deposit Verified: ✓ Yes
- Verified At: 2026-03-11 04:28
- Status: Still "Awarded" (can now proceed to closeout)
```

### Verify in Tender Details
1. Open verified tender
2. Check field: **"Security Deposit Verified"**: ✓ Yes
3. Check timestamp: **"Security Verified At"**: 2026-03-11 04:28
4. **Verify** button now hidden/disabled

---

## Feature 6: Award Tender with Notifications

### Prerequisites
- Tender status: **"Published"**
- Have vendors in system for testing

### UI Path
```
Tenders List → Click Published Tender → Details Page → "Award" Button
```

### Action: Open Award Dialog
1. Click: **"Award Tender"** button
2. **Award Dialog Opens**:
```
Award Tender

Select Winning Vendor:
[Search/Select Vendor Dropdown ▼]

Notification Options:
☑ Send Email Notification
☐ Send SMS Notification

[Award] [Cancel]
```

### Fill Award Form
1. **Vendor Selection**:
   - Click dropdown
   - Type vendor name or ID
   - Select: **"Solar Corp (vendor_001)"**

2. **Notifications**:
   - Check: ✓ **"Send Email"**
   - Uncheck or check: **"Send SMS"** (for testing)

3. Click: **"Award"**

### Verify Success
1. **Tender Status Updates**:
   ```
   Status: Awarded (green badge)
   Awarded To: Solar Corp
   Awarded Date: 2026-03-11 04:30
   Button "Award" → Hidden
   Button "Close" → Appears
   ```

2. **Check Vendor Notifications**:
   - Switch to awarded vendor's account
   - Check **"Notifications"** bell
   - See: "Tender Award Notification: Solar Installation Project"
   - Click to view award details

3. **Check Email** (MailHog http://localhost:8025):
   - Subject: "Tender Award Notification: Solar Installation Project"
   - Body:
     ```
     Congratulations!
     
     You have been awarded the tender.
     
     Tender: Solar Installation Project (TND-000002)
     Department: Energy Department
     Awarded at: 2026-03-11 04:30
     
     Please contact: Tel: +266-123-4567
     ```

### Test Case 2: Award with SMS
1. Check: ✓ **"Send SMS"**
2. Award
3. **Expected**: SMS attempt logged (visible in backend logs)

---

## Feature 7: Close Tender

### Prerequisites
- Tender status: **"Awarded"** or **"Published"**

### UI Path
```
Tenders List → Click Awarded Tender Details → "Close Tender" Button
```

### Action: Close Tender
1. Find button: **"Close Tender"** (red/danger color)
2. Click
3. **Confirmation Dialog**:
   ```
   Close Tender?
   
   TND-000002 - Solar Installation Project
   
   This action cannot be undone.
   Future bids will not be accepted.
   
   [Close] [Cancel]
   ```

4. Click: **"Close"**

### Verify Success
1. **Tender Status**:
   ```
   Status: Closed (grey badge)
   Closed At: 2026-03-11 04:32
   Buttons disabled: Award, Close
   ```

2. **Try to Submit Bid** (as vendor):
   - Test that closed tender rejects new bids
   - Error message: "Tender is not open for bidding"

---

## Feature 8: Submit Tender Bid (Two-Stage Process)

### Prerequisites
- Tender status: **"Published"**
- Be logged in as Vendor user
- Tender must have before deadline

### UI Path
```
Tenders List → Find Published Tender → "Submit Bid" or "Apply" Button
```

### Test Case 1: Pre-Qualification Stage Bid
1. Open published tender with Stage Type: **"Pre-Qualification"**
2. Click: **"Submit Bid"** button
3. **Bid Submission Form Opens**:
   ```
   Submit Bid for: Solar Installation Project (TND-000002)
   
   Stage: Pre-Qualification (auto-filled)
   
   Bid Amount: [_______________]  (optional)
   
   Concept Note: [Rich Text Editor or Text Area]
   (Your innovative approach, timeline, etc.)
   
   Attach Proposal: [Choose File] (PDF/DOC/DOCX)
   
   [Submit] [Cancel]
   ```

4. **Fill Bid Form**:
   - Bid Amount: `250000`
   - Concept Note: "Our company proposes a innovative solar micro-grid solution that will serve 500+ households in the region. Key features: advanced battery storage, cloud-based monitoring, and community training program..."
   - Attach: proposal_preqal.pdf (optional but test it)

5. Click: **"Submit"**

### Verify Bid Submitted
1. **Success Message**:
   ```
   ✓ Bid Submitted Successfully
   Status: Submitted
   Submitted At: 2026-03-11 04:35
   ```

2. **In Bid List**:
   - Navigate to "My Bids"
   - Show: Your bid for this tender
   - Status: **"Submitted"**
   - Amount: 250000
   - Stage: Pre-Qualification

3. **Prevent Duplicate**:
   - Try submitting another bid for same tender
   - Error: "You have already submitted a bid for this tender"

### Test Case 2: Site-Specific Stage Bid
1. Open tender with Stage: **"Site-Specific"**
2. Submit bid form shows:
   ```
   Stage: Site-Specific
   
   Bid Amount: [________]
   
   Technical Proposal: [Rich Text Editor]
   (Technical approach, methodology, timeline)
   
   Financial Proposal: [Rich Text Editor]
   (Pricing, payment terms, cost breakdown)
   
   Attach Proposal File: [Upload]
   
   [Submit]
   ```

3. Fill details and submit
4. **Expected**: Same success flow as Stage 1

### Test Case 3: Deadline Enforcement
1. Find tender with **past deadline**
2. Try to submit bid
3. **Expected Error**:
   ```
   ✗ Cannot Submit Bid
   Bidding deadline has passed (2026-03-10 17:00)
   ```

---

## Feature 9: Bid Review Workflow (RBF Official)

### Prerequisites
- Be logged in as RBF Official
- Have vendors with submitted bids

### UI Path
```
Tenders → Bid Management / Bids Tab
OR
Tender Details → "Bids" Section
```

### View Submitted Bids
1. Navigate to **"Bid Management"** or tender's **"Bids"** tab
2. **See List**:
   ```
   Bids for: Solar Installation Project (TND-000002)
   
   ┌────────────────────────────────────────┐
   │ Solar Corp (vendor_001)                │
   │ Status: Submitted                      │
   │ Amount: LSL 250,000                    │
   │ Stage: Pre-Qualification               │
   │ Submitted: 2026-03-11 04:35            │
   │ [Review] [Accept] [Reject]             │
   └────────────────────────────────────────┘
   
   ┌────────────────────────────────────────┐
   │ Energy Solutions Ltd (vendor_002)      │
   │ Status: Submitted                      │
   │ Amount: LSL 300,000                    │
   │ Stage: Pre-Qualification               │
   │ Submitted: 2026-03-11 04:40            │
   │ [Review] [Accept] [Reject]             │
   └────────────────────────────────────────┘
   ```

### Test Case 1: Review Bid
1. Click: **"[Review]"** button on a bid
2. **Bid Moves**:
   ```
   Status: Submitted → Under Review
   Reviewed At: 2026-03-11 04:42
   Reviewed By: rbf_official_name
   Buttons Update: [View] [Accept] [Reject]
   ```

3. Vendor sees notification: "Your bid is under review"

### Test Case 2: Accept Bid
1. Click: **"[Accept]"** on submitted or under-review bid
2. **Confirmation**:
   ```
   Accept Bid?
   
   Solar Corp - Pre-Qualification Bid
   Amount: LSL 250,000
   
   [Accept] [Cancel]
   ```
3. Click: **"Accept"**
4. **Success**:
   ```
   Status: Accepted ✓
   Accepted At: 2026-03-11 04:43
   Vendor Notified: "Your bid has been accepted"
   ```

### Test Case 3: Reject Bid
1. Click: **"[Reject]"** on bid
2. **Form Opens**:
   ```
   Reject Bid
   
   Energy Solutions Ltd
   
   Rejection Reason: [Text Area]
   [________________________________________
   Bid amount exceeds tender budget by 15%
   ________________________________________]
   
   [Reject] [Cancel]
   ```
3. Enter reason: "Bid amount exceeds tender budget by 15%"
4. Click: **"Reject"**
5. **Success**:
   ```
   Status: Rejected
   Rejection Reason: Bid amount exceeds...
   Vendor Notified: Email/notification with reason
   ```

### Verify Vendor Sees Rejection
1. Switch to vendor account
2. Check **"My Bids"**
3. See:
   ```
   Tender: Solar Installation Project
   Status: Rejected ✗
   Reason: Bid amount exceeds tender budget by 15%
   ```

---

## Feature 10: Advanced Search with Filters

### UI Path
```
Tenders → Advanced Search / Filters Panel
```

### Test Advanced Filters (if UI supports them)

**Test 1: Date Range Filter**
1. Click: **"Advanced Filters"**
2. Set:
   - Deadline From: 2026-03-15
   - Deadline To: 2026-05-31
3. Click: **"Apply"**
4. **Expected**: Shows only tenders with deadlines in that range

**Test 2: Budget Range Filter**
1. Set:
   - Min Budget: LSL 100,000
   - Max Budget: LSL 1,000,000
2. Apply
3. **Expected**: Only tenders with budgets in range (or no budget if empty)

**Test 3: Technology Type Filter**
1. Select: **"Mini-grid"**
2. Apply
3. **Expected**: Only tenders with Mini-grid technology type

**Test 4: Procurement Method Filter**
1. Select: **"Competitive Bidding"**
2. Apply
3. **Expected**: Only tenders with this procurement method

**Test 5: Combined Filters**
1. Set ALL:
   - Status: Published
   - Category: Solar
   - Department: Energy
   - Deadline: 2026-03-15 to 2026-05-31
   - Technology: Mini-grid
2. Apply
3. **Expected**: Narrow list showing only matching tenders

---

## Feature 11: Bid Count in List

### UI Path
```
Tenders List
```

### Visual Check
1. Open **"Tenders"** list view
2. In each tender row, look for **"Bids: 2"** or **"2 bids submitted"**
3. As vendors submit bids, number should **increase in real-time** (if using live refresh)

### Test
1. Have tender with 0 bids
2. In another browser/tab, submit bid as vendor
3. In admin view, refresh or check bid count
4. **Expected**: Count updates to 1

---

## Testing Checklist

### Quick Smoke Test (10 mins)
- [ ] Login as RBF Official
- [ ] Create new tender with all required fields
- [ ] See tender in list with Draft status
- [ ] Verify tender → Status changes to Verified
- [ ] Publish tender → Status changes to Published
- [ ] Check MailHog for notifications
- [ ] Switch to vendor, see published tender
- [ ] Submit bid as vendor
- [ ] Switch back to RBF, see bid in review queue
- [ ] Accept bid → Vendor gets notification

### Comprehensive Test (30 mins)
- [ ] Test all search/filter combinations
- [ ] Create multiple tenders with different stages
- [ ] Submit bids for both Pre-Qual and Site-Specific
- [ ] Test deadline enforcement (try submitting after deadline)
- [ ] Award tender with email + SMS options
- [ ] Verify security deposit workflow
- [ ] Close tender and verify bid submission blocked
- [ ] Test bid rejection with reason
- [ ] Check all notifications in MailHog
- [ ] Verify audit logs (if visible in UI)

### Edge Cases
- [ ] Submit bid > 10MB file → Should show error
- [ ] Submit bid with wrong file type → Should show error
- [ ] Try to publish unverified tender → Should show error
- [ ] Try to award closed tender → Should show error
- [ ] Try to submit duplicate bid → Should show error
- [ ] Submit bid after deadline → Should show error
- [ ] Try to create tender without required fields → Should show validation errors

---

## API Testing (Browser DevTools)

### Open Browser DevTools
1. Press **F12** or **Right-click → Inspect**
2. Go to **"Network"** tab

### Test Tender Creation
1. Fill tender form
2. Click "Save"
3. **In Network tab**, find POST request to `/api/tenders/`
4. Check:
   - Status: **201** (Created)
   - Response shows: tender with reference_number auto-generated
   - Response includes all fields

### Test Publishing
1. Click "Publish"
2. **In Network tab**, find POST to `/api/tenders/{id}/publish/`
3. Check:
   - Status: **200** (OK)
   - Response: status changed to "Published"
   - published_at timestamp added

### Test Bid Submission
1. Submit bid
2. **Network tab** → POST `/api/tender-bids/`
3. Check:
   - Status: **201** (Created)
   - Response: bid with status "Submitted"
   - Includes all submitted data

### Check Error Responses
1. Try submitting with empty required field
2. **Network tab** → See response with status **400**
3. Check error message: `{"field_name": ["Error message"]}`

---

## Troubleshooting

### "Tender not found" Error
- **Fix**: Confirm tender ID is correct
- Check Network tab for actual endpoint being called
- Verify tender is not deleted

### Notifications Not Showing
- **Check**: MailHog running on http://localhost:8025
- **Check**: Backend EMAIL_HOST_USER configured in .env
- **Check**: Console for JavaScript errors (F12)

### Bid Submission Fails
- **Check deadline**: Is deadline in future?
- **Check**: File size < 10MB for attachments
- **Check**: Tender status is "Published" (not Draft)

### Filter Not Working
- **Check**: Multiple filters might be conflicting
- Try: Reset filters and apply one at a time
- **Check**: Browser cache (Ctrl+Shift+Delete)

### Can't See Notifications
- **Check**: In-app notifications icon (bell)
- **Check**: MailHog for email notifications
- **Check**: Browser permissions for notifications
- **Check**: Network tab to verify notifications endpoint

---

## Performance Notes

### Expected Response Times
- **List Tenders**: < 500ms
- **Create Tender**: < 1-2s (file upload may take longer)
- **Publish Tender**: < 1s (notifications may take 2-3s)
- **Award Tender**: < 1s
- **Search/Filter**: < 500ms

### If Slow
1. Check backend logs: `docker logs rbf_web`
2. Check database: `docker exec rbf_db psql -U rbf_user -d rbf`
3. Run: `SELECT COUNT(*) FROM tenders;` (should be few for testing)

---

## Data Cleanup for Re-Testing

### Reset Demo Data
```bash
# Clear all tenders and bids
docker exec rbf_web python manage.py shell
>>> from rbf.tenders.models import Tender, TenderBid
>>> Tender.objects.all().delete()
>>> TenderBid.objects.all().delete()
```

### Or via SQL
```bash
docker exec rbf_db psql -U rbf_user -d rbf
rbf=# DELETE FROM tenders_tenderbid;
rbf=# DELETE FROM tenders_tender;
rbf=# ALTER SEQUENCE tenders_tender_id_seq RESTART WITH 1;
```

---

## Recording/Screenshots for Documentation

### Recommended Screens to Capture
1. **Tender Creation Form**
2. **Tender List with Filters**
3. **Verify Dialog**
4. **Publish Dialog with Notifications**
5. **Award Dialog with Vendor Selection**
6. **Bid Submission Form (both stages)**
7. **Bid Review Queue**
8. **Security Verification Search**
9. **MailHog Email Notifications**
10. **Vendor Notification Bell with Messages**

---

*Updated: 2026-03-11*
*Test with: Frontend on localhost:5173 | Backend on localhost:8000*
