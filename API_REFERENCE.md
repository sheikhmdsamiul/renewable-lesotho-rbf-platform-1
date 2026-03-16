# Tender Management API - Quick Reference

## Base URL
```
http://localhost:8000/api/
```

## Authentication
All endpoints require JWT token in Authorization header:
```
Authorization: Bearer {access_token}
```

---

## Tender Endpoints

### List Tenders (with advanced filtering)
```
GET /tenders/
Query Parameters:
  ?status=Published
  ?category=Category1
  ?department=Department1
  ?is_verified=true
  ?procurement_method=Method1
  ?search=reference_number_or_name
  ?deadline_range_after=2026-03-15&deadline_range_before=2026-03-31
  ?budget_range_min=1000&budget_range_max=100000
  ?technology_types=Mini-grid
  ?ordering=-created_at (or deadline, published_at, verified_at, budget)
```

**Response**: List of tenders with bid count

---

### Get Tender Details
```
GET /tenders/{id}/
Response: Complete tender object with all fields
```

---

### Create Tender (RBF Official only)
```
POST /tenders/
Content-Type: multipart/form-data

Required Fields:
  - name: string(50)
  - department: string
  - category: string
  - application_type: string
  - stage_type: string (Pre-Qualification | Site-Specific)
  - procurement_method: string
  - address_for_document: string(50)
  - address_for_security: string(50)
  - place_for_opening: string(50)
  - bidders_eligibility: text
  - time_for_completion: string
  - invited_by: string
  - bidding_currency: string
  - instruction: text
  - contact_details: string
  - target_site_type: string
  - deadline: ISO datetime
  - last_date_security: ISO datetime
  - last_date_submission: ISO datetime
  - date_opening: ISO datetime
  - technology_types: array (at least 1)
  - schedule_file: file (PDF/DOC/DOCX, max 10MB)

Optional Fields:
  - budget: decimal
  - pre_tender_meeting_info: text
  - bidders_schedule_purchase: boolean
  - tender_security_required: boolean
  - funding_source: string
```

---

### Update Tender (RBF Official only)
```
PUT/PATCH /tenders/{id}/
```

---

### Delete Tender (RBF Official only)
```
DELETE /tenders/{id}/
```

---

### Verify Tender (RBF Official only)
```
POST /tenders/{id}/verify/

Response: Tender with is_verified=true, verified_at=timestamp
Audit Log: tender_verified
```

---

### Publish Tender (RBF Official only)
```
POST /tenders/{id}/publish/
Body:
{
  "send_email": true,          // Send email notifications
  "send_sms": false,           // Send SMS notifications
  "notify_all_bidders": true   // All vendors vs. category-specific
}

Validations:
  - Tender must be verified first
  - Cannot publish closed tenders

Side Effects:
  - Status → Published
  - published_at = now
  - Notifications sent to eligible vendors
  - Audit log created
```

---

### Award Tender (RBF Official only)
```
POST /tenders/{id}/award/
Body:
{
  "awarded_vendor_id": "vendor_123",
  "awarded_vendor_name": "Vendor Name",
  "send_email": true,
  "send_sms": false
}

Validations:
  - Tender must be in Published or Evaluation status
  - Either vendor_id or vendor_name required

Side Effects:
  - Status → Awarded
  - awarded_at = now
  - Notifications sent to vendor
  - Audit log created
```

---

### Close Tender (RBF Official only)
```
POST /tenders/{id}/close/

Side Effects:
  - Status → Closed
  - closed_at = now
  - No further bids accepted
  - Audit log created
```

---

### Verify Security Deposit (RBF Official only)
```
POST /tenders/{id}/verify_security/

Side Effects:
  - security_deposit_verified = true
  - security_deposit_verified_at = now
  - Audit log created for audit trail
```

---

### Search Tenders for Security Verification (RBF Official only)
```
GET /tenders/security_verification_search/

Query Parameters:
  ?search_key=reference_or_name        // Search by reference number or tender name
  ?award_date_from=2026-03-01          // ISO date format
  ?award_date_to=2026-03-31
  ?sort_by=-awarded_at                 // Sort field with optional minus for desc
  ?limit=50                            // Number of results (default 50)

Filters:
  Automatically filters to:
  - status = Awarded
  - security_deposit_verified = false

Response: List of filtered tenders
```

---

## Tender Bid Endpoints

### List Bids
```
GET /tender-bids/
Query Parameters:
  ?tender={tender_id}
  ?vendor_id={vendor_id}
  ?status=Submitted|Under Review|Accepted|Rejected|Withdrawn
  ?search=vendor_name_or_email
  ?ordering=-submitted_at (or bid_amount)

Permissions:
  - Vendors see only their own bids
  - RBF Officials see all bids
```

---

### Submit Bid (Vendor only)
```
POST /tender-bids/
Content-Type: multipart/form-data

Required Fields:
  - tender: tender_id
  - bid_amount: decimal (optional)
  - stage: string (Pre-Qualification | Site-Specific)

Content (choose by stage):
  Stage 1: concept_note (text)
  Stage 2: technical_proposal (text) + financial_proposal (text)

Optional:
  - proposal_file: file (PDF/DOC/DOCX up to 10MB)

Validations:
  - Tender must be Published
  - Deadline not passed
  - No duplicate bids per vendor per tender
  - vendor_id auto-filled from request user
  - vendor_email auto-filled from request user

Response: Created bid object with status=Submitted
```

---

### Review Bid (RBF Official only)
```
POST /tender-bids/{id}/review/

Side Effects:
  - status → Under Review
  - reviewed_at = now
  - reviewed_by = current user name
```

---

### Accept Bid (RBF Official only)
```
POST /tender-bids/{id}/accept/

Side Effects:
  - status → Accepted
  - reviewed_at = now
  - reviewed_by = current user name
  - Vendor notified via in-app notification
```

---

### Reject Bid (RBF Official only)
```
POST /tender-bids/{id}/reject/
Body:
{
  "rejection_reason": "Bid amount exceeds budget"
}

Validations:
  - rejection_reason is required

Side Effects:
  - status → Rejected
  - reviewed_at = now
  - reviewed_by = current user name
  - rejection_reason stored
  - Vendor notified with reason
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Error message",
  "field_name": ["Error for field"]
}
```

### 401 Unauthorized
```json
{
  "detail": "Invalid token"
}
```

### 403 Forbidden
```json
{
  "detail": "Only RBF Officials can perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 409 Conflict
```json
{
  "detail": "Tender is already closed.",
  "detail": "You have already submitted a bid for this tender."
}
```

---

## Notification Flow

### On Publish Tender
**Recipients**: All active vendors (or category-specific)
**Channels**: Email + In-App notification
**Message**: Tender published notification with deadline
**Link**: ${FRONTEND_URL}/tenders/{tender_id}

### On Award Tender
**Recipients**: Winning vendor
**Channels**: Email + In-App + SMS (if requested)
**Message**: Congratulations, tender awarded
**Details**: Tender name, reference, contact info

### On Bid Accept/Reject
**Recipients**: Bidder
**Channels**: In-App notification
**Message**: Bid acceptance/rejection with reason (if rejected)

---

## File Upload

### Tender Schedule File
- **Endpoint**: POST /tenders/
- **Field**: schedule_file
- **Max Size**: 10 MB
- **Allowed Types**: .pdf, .doc, .docx
- **Storage Path**: tender_schedules/

### Bid Proposal File
- **Endpoint**: POST /tender-bids/
- **Field**: proposal_file
- **Max Size**: 10 MB
- **Allowed Types**: .pdf, .doc, .docx
- **Storage Path**: tender_bids/

---

## Pagination

List endpoints return paginated results:
```json
{
  "count": 100,
  "next": "http://localhost:8000/api/tenders/?page=2",
  "previous": null,
  "results": [...]
}

Query: ?page=2 (uses default page size from settings)
```

---

## Status Filter Values

### Tender Status
- `Draft` - Initial state
- `Published` - Open for bidding
- `Evaluation` - Bids being evaluated
- `Awarded` - Winner selected
- `Closed` - No further action

### Bid Status
- `Submitted` - Awaiting review
- `Under Review` - Being evaluated
- `Accepted` - Approved
- `Rejected` - Not approved
- `Withdrawn` - Vendor withdrew

---

## Example cURL Commands

### Create Tender
```bash
curl -X POST http://localhost:8000/api/tenders/ \
  -H "Authorization: Bearer {token}" \
  -F "name=Solar Installation Tender" \
  -F "department=Energy" \
  -F "category=Solar" \
  -F "application_type=Open Access" \
  -F "stage_type=Pre-Qualification" \
  -F "procurement_method=Competitive Bidding" \
  -F "deadline=2026-04-01T23:59:59Z" \
  -F "schedule_file=@tender_schedule.pdf" \
  -F "technology_types[]=Solar" \
  ... (other required fields)
```

### Search Tenders
```bash
curl "http://localhost:8000/api/tenders/?status=Published&category=Solar&search=TND-000001" \
  -H "Authorization: Bearer {token}"
```

### Award Tender
```bash
curl -X POST http://localhost:8000/api/tenders/1/award/ \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "awarded_vendor_id": "vendor_123",
    "awarded_vendor_name": "Solar Corp",
    "send_email": true,
    "send_sms": true
  }'
```

### Submit Bid
```bash
curl -X POST http://localhost:8000/api/tender-bids/ \
  -H "Authorization: Bearer {vendor_token}" \
  -F "tender=1" \
  -F "bid_amount=50000" \
  -F "stage=Pre-Qualification" \
  -F "concept_note=Our innovative approach..." \
  -F "proposal_file=@proposal.pdf"
```

---

*Last Updated: 2026-03-11*
