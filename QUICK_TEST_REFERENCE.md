# Tender Management - Quick Reference Card

## One-Page Feature Checklist

### ✓ Feature 1: Create Tender
**Where**: Dashboard → Tenders → "Add Tender"  
**Check**: 
- [ ] Form has all 20+ fields visible
- [ ] File upload works (PDF/DOC/DOCX)
- [ ] Technology types multi-select works
- [ ] Submit creates draft tender with auto-generated reference
- [ ] Status shows: **Draft**

---

### ✓ Feature 2: Search & Filter  
**Where**: Tenders List → Filter Panel  
**Check**:
- [ ] Status filter works (Draft, Verified, Published, Awarded, Closed)
- [ ] Category filter works
- [ ] Department filter works
- [ ] Keyword search works (name or reference #)
- [ ] Multiple filters combine correctly
- [ ] Sort by deadline/status/date works
- [ ] Results update in real-time

---

### ✓ Feature 3: Verify Tender
**Where**: Tender Details (Draft status) → "Verify" Button  
**Check**:
- [ ] Button visible only for RBF Officials  
- [ ] Confirmation dialog appears
- [ ] Status changes from **Draft** → **Verified**
- [ ] Timestamp appears: "Verified At: [date]"
- [ ] "Publish" button becomes available

---

### ✓ Feature 4: Publish with Notifications
**Where**: Tender Details (Verified) → "Publish" Button  
**Check**:
- [ ] Publish dialog shows notification options
- [ ] Options: Send Email ✓, Send SMS ✓, Notify All ○
- [ ] Published status shows: **Published**  
- [ ] Timestamp shows: "Published At: [date]"
- [ ] **Email arrives in MailHog** (localhost:8025)
  - Subject line: "Tender Published: [Tender Name]"
  - Contains: Reference #, deadline, link
- [ ] Vendors notified (check notification bell)

---

### ✓ Feature 5: Close Tender
**Where**: Tender Details → "Close Tender" Button  
**Check**:
- [ ] Button shows (red/danger color)
- [ ] Confirmation dialog appears
- [ ] Status changes to: **Closed**
- [ ] Timestamp: "Closed At: [date]"
- [ ] Vendors cannot submit bids (blocked with error)
- [ ] Button disappears after closing

---

### ✓ Feature 6: Award Tender + Notifications
**Where**: Tender Details (Published) → "Award" Button  
**Check**:
- [ ] Award dialog opens
- [ ] Vendor selection dropdown works (search + select)
- [ ] Notification checkboxes: Email ✓, SMS ✓
- [ ] Status changes: **Awarded**
- [ ] Shows: "Awarded To: [Vendor Name]"
- [ ] Shows: "Awarded Date: [date]"
- [ ] **Email sent** (MailHog):
  - Subject: "Tender Award Notification: [Name]"
  - Contains: "Congratulations", tender details
- [ ] **Vendor sees notification** (notification bell)
- [ ] **Security Verify button appears**

---

### ✓ Feature 7: Verify Security Deposit
**Where**: Tenders → "Security Verification" Tab / Search  
**Check**:
- [ ] Search form with filters appears
- [ ] Shows awarded tenders pending verification
- [ ] Search by reference/name works
- [ ] Date range filter works
- [ ] Sort by option works
- [ ] "Verify Security" button on each record
- [ ] After clicking:
  - Status: **Verified** ✓
  - Shows: "Security Verified At: [date]"
  - Button disappears
  - Field: "Security Deposit Verified: ✓ Yes"

---

### ✓ Feature 8: Submit Tender Bid (Stage 1)
**Where**: Tenders List → Vendor user → Published Tender → "Submit Bid"  
**Check**:
- [ ] Form shows for Pre-Qualification stage
- [ ] Fields: Bid Amount, Concept Note, Upload File
- [ ] File upload works (< 10MB, PDF/DOC/DOCX)
- [ ] Submit works
- [ ] Message: "Bid Submitted Successfully"
- [ ] Status shows: **Submitted**
- [ ] Timestamp: "Submitted: [date]"
- [ ] **Prevent duplicate**: Try submitting again → Error

---

### ✓ Feature 9: Submit Tender Bid (Stage 2)  
**Where**: Site-Specific tender → Vendor → "Submit Bid"  
**Check**:
- [ ] Form shows for Site-Specific stage
- [ ] Fields: Bid Amount, Technical Proposal, Financial Proposal, Upload
- [ ] Submit works
- [ ] Status: **Submitted**
- [ ] All fields saved correctly

---

### ✓ Feature 10: Bid Review Workflow
**Where**: Tenders → Bid Management / RBF Official "Bids" Tab  
**Check**:
- [ ] **List all bids** for tender
  - Shows: Vendor, Amount, Status, Date
  - Shows: [Review], [Accept], [Reject] buttons
  
- [ ] **Review Bid**:
  - Click [Review] → Status: **Under Review**
  - Timestamp + reviewer name saved
  
- [ ] **Accept Bid**:
  - Click [Accept] from Submitted
  - Status: **Accepted** ✓
  - Vendor gets notification
  
- [ ] **Reject Bid**:
  - Click [Reject] → Dialog for rejection reason
  - Enter reason
  - Status: **Rejected** ✗
  - Vendor sees reason in notification/dashboard

---

### ✓ Feature 11: Deadline Enforcement
**Where**: Vendor Try to Submit After Deadline  
**Check**:
- [ ] Past deadline tender visible to vendor
- [ ] Try to submit bid → **Error: "Deadline passed"**
- [ ] Cannot submit even with all fields filled

---

### ✓ Feature 12: Bid Count Display
**Where**: Tenders List (default view)  
**Check**:
- [ ] Each tender shows: "Bids: 2" or similar count
- [ ] Count increases as vendors submit bids
- [ ] Refresh list → Count updates

---

## ⚡ Quick Test Flow (5 minutes)

```
1. Login: rbf_official user
2. Create tender: Fill form → Save
   ✓ See: Draft status, auto-generated reference
3. Verify: Click Verify button
   ✓ See: Status → Verified
4. Publish: Click Publish, check Email ✓, All Bidders ○
   ✓ See: Published status
   ✓ Check: MailHog has email with tender info
5. Login: vendor user (new tab)
   ✓ See: Published tender in list
6. Submit bid: Click Submit Bid, fill form, upload PDF
   ✓ See: Submitted status
7. Login: rbf_official (original tab)
   ✓ See: Bid count increased to 1
   ✓ Go to Bids tab
8. Accept bid: Click Accept
   ✓ See: Bid status → Accepted
   ✓ Vendor notification sent
9. Award tender: Click Award, select vendor, Email ✓
   ✓ See: Status → Awarded
   ✓ Check: MailHog has award email
10. Verify Security: Click Verify Security
    ✓ See: Verified ✓, timestamp added
```

---

## 🔍 Manual Verification Points

| Feature | Visual | Data | Notification |
|---------|--------|------|--------------|
| **Create** | Draft badge | All fields saved | - |
| **Verify** | Verified badge | verified_at timestamp | Log message |
| **Publish** | Published badge | published_at timestamp | Email + In-app |
| **Award** | Awarded badge | awarded_to + date | Email + SMS option |
| **Security** | Verified checkmark | security_verified_at | - |
| **Close** | Closed badge | closed_at timestamp | - |
| **Bid Submit** | Submitted badge | bid amount, content | - |
| **Bid Review** | Under Review | reviewed_by field | - |
| **Bid Accept** | Accepted ✓ | reviewed_at timestamp | In-app notification |
| **Bid Reject** | Rejected ✗ | rejection_reason text | In-app notification |

---

## 📧 Email Check (MailHog)

**URL**: http://localhost:8025

**Expected Emails**:
1. **Tender Published**
   - To: All vendors
   - Subject: "Tender Published: [Name]"
   - Contains: Reference, deadline, link

2. **Tender Award**
   - To: Winning vendor only
   - Subject: "Tender Award Notification: [Name]"
   - Contains: "Congratulations", tender details

3. **Bid Accepted**
   - (via In-app if email not configured)
   - Contains: Tender name, acceptance message

4. **Bid Rejected**
   - (via In-app if email not configured)
   - Contains: Rejection reason

---

## 🚨 Common Issues & Quick Fixes

| Issue | Check |
|-------|-------|
| **No email in MailHog** | Backend email settings OK? (docker logs rbf_web\|grep -i email) |
| **Filter not working** | Clear browser cache (Ctrl+Shift+Del), refresh page |
| **Bid submit fails** | Tender Published? Deadline future? File < 10MB? |
| **Can't find tender** | Verify tender visibility (vendor can't see Draft ones) |
| **Notifications not showing** | Refresh page, check notification bell icon |
| **Duplicate bid error** | Vendor already submitted for this tender (expected) |
| **Award button missing** | Tender must be Published or Evaluation state |
| **File upload error** | File must be PDF/DOC/DOCX, max 10MB |

---

## 📱 Browser DevTools (F12) Checks

### Network Tab
- POST /api/tenders/ → Status **201** (create)
- POST /api/tenders/{id}/verify/ → Status **200**
- POST /api/tenders/{id}/publish/ → Status **200**
- POST /api/tenders/{id}/award/ → Status **200**
- POST /api/tender-bids/ → Status **201** (submit bid)

### Console Tab
- Look for: No red error messages
- Warnings OK (yellow)
- Check: Network errors if UI doesn't update

### Application Tab (Storage)
- localStorage: Check `rbf_access_token` exists
- Check: `rbf_user` contains role (RBF_OFFICIAL or VENDOR)

---

## ✅ Sign-Off Checklist

- [ ] All 12 features tested
- [ ] No JavaScript errors (Console clean)
- [ ] All API responses 200/201
- [ ] Emails working (MailHog)
- [ ] Notifications showing
- [ ] UI updates immediately
- [ ] Error messages helpful
- [ ] Role-based access working
- [ ] File upload validated
- [ ] Deadline enforcement working
- [ ] Timestamps correct (UTC/local)
- [ ] Performance acceptable (< 2sec load)

---

*Quick Testing Reference - Print this page for manual testing sessions*
*Last Updated: 2026-03-11*
