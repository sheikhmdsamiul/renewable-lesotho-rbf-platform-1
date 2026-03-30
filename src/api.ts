import {
  Tender,
  Project,
  Notification,
  User,
  UserRole,
  Milestone,
  ProjectUpdate,
  ProjectDocument,
  InstallationReport,
  VerificationTask,
  VendorPrequalification,
  VendorPrequalificationSubmission,
  PaymentClaim,
  PaymentClaimSubmission,
  Disbursement,
  AuditLog,
  TenderBid,
  TenderBidSite,
  BidStatus,
  TenderBidEvaluation,
  TenderContract,
  TenderAwardRankingRow,
  VendorBlacklistCase,
  BlacklistAppeal,
} from "./types";

const env = (import.meta as any)?.env ?? {};
const configuredApiBase = (env?.VITE_API_URL as string | undefined)?.replace(/\/$/, "");
const requestTimeoutMs = Number(env?.VITE_API_TIMEOUT_MS ?? 15000);
const isDevMode = Boolean(env?.DEV);
const ACCESS_TOKEN_KEY = "rbf_access_token";
const REFRESH_TOKEN_KEY = "rbf_refresh_token";
const USER_KEY = "rbf_user";
const DEMO_USERNAMES = new Set([
  "vendor_approved",
  "admin_user",
  "rbf_official",
  "tac_member",
  "doe_officer",
  "field_verifier",
  "donor_user",
  "auditor_user",
]);

function uniq(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    if (item === "") {
      if (!seen.has("__EMPTY__")) {
        seen.add("__EMPTY__");
        out.push("");
      }
      continue;
    }
    const key = item.trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

function stripApiSuffix(base: string): string {
  return base.replace(/\/$/, "").replace(/\/api$/i, "");
}

function joinApiUrl(base: string, url: string): string {
  if (!base) return url;
  const normalizedBase = base.replace(/\/$/, "");
  if (normalizedBase.toLowerCase().endsWith("/api") && url.startsWith("/api/")) {
    return `${normalizedBase}${url.slice(4)}`;
  }
  return `${normalizedBase}${url}`;
}

function normalizeFileUrl(raw?: string): string | undefined {
  if (!raw) return raw;
  if (typeof window === "undefined") return raw;
  if (!/^https?:\/\//i.test(raw)) return raw;
  try {
    const url = new URL(raw);
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      url.hostname = window.location.hostname;
      url.port = "8000";
      return url.toString();
    }
  } catch {
    return raw;
  }
  return raw;
}

function extractApiErrorDetail(text: string): string {
  const trimmed = (text || "").trim();
  if (!trimmed) return "";

  try {
    const payload = JSON.parse(trimmed);
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.non_field_errors) && payload.non_field_errors.length) {
      return String(payload.non_field_errors[0]);
    }
    if (payload && typeof payload === "object") {
      const firstKey = Object.keys(payload)[0];
      if (firstKey) {
        const value = payload[firstKey];
        if (Array.isArray(value) && value.length) return `${firstKey}: ${String(value[0])}`;
        if (typeof value === "string") return `${firstKey}: ${value}`;
      }
    }
  } catch {
    // Not JSON; fall through to raw text.
  }

  return trimmed;
}

function headersInitToObject(input?: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {};
  if (!input) return out;

  if (input instanceof Headers) {
    input.forEach((value, key) => {
      out[key] = value;
    });
    return out;
  }

  if (Array.isArray(input)) {
    for (const [key, value] of input) {
      out[String(key)] = String(value);
    }
    return out;
  }

  for (const [key, value] of Object.entries(input)) {
    if (value == null) continue;
    out[key] = String(value);
  }
  return out;
}

function getHeaderValue(headers: Record<string, string>, name: string): string | undefined {
  const target = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === target) return value;
  }
  return undefined;
}

function getApiBaseCandidates(): string[] {
  const normalizedConfigured = configuredApiBase ? stripApiSuffix(configuredApiBase) : "";
  const browserBackends: string[] = [];

  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    if (hostname === "127.0.0.1" || hostname === "localhost") {
      // Prefer direct backend in local development to avoid proxy-only failure modes.
      browserBackends.push("http://127.0.0.1:8000", "http://localhost:8000");
    } else if (hostname) {
      browserBackends.push(`${protocol}//${hostname}:8000`, `http://${hostname}:8000`);
    }
  }

  const bases: string[] = [];

  if (isDevMode) {
    // In local development, prefer Vite proxy (/api) first.
    bases.push("");
    if (normalizedConfigured) bases.push(normalizedConfigured);
    bases.push(...browserBackends);
  } else {
    bases.push(""); // same-origin first for production deployments
    if (normalizedConfigured) bases.push(normalizedConfigured);
    bases.push(...browserBackends);
  }

  bases.push("http://127.0.0.1:8000", "http://localhost:8000");
  return uniq(bases);
}

const API_BASE_CANDIDATES = getApiBaseCandidates();
export const API_BASE: string =
  (configuredApiBase ? stripApiSuffix(configuredApiBase) : "") ||
  API_BASE_CANDIDATES.find((base) => Boolean(base)) ||
  "http://127.0.0.1:8000";

// ============ Mapping helpers ============

function mapTenderFromApi(api: any): Tender {
  return {
    id: String(api.id ?? ""),
    referenceNumber: api.reference_number ?? "",
    name: api.name ?? "",
    department: api.department ?? "",
    category: api.category ?? "",
    status: api.status ?? "Draft",
    deadline: api.deadline ?? "",
    budget: api.budget != null ? Number(api.budget) : undefined,
    applicationType: api.application_type ?? undefined,
    stageType: api.stage_type ?? undefined,
    procurementMethod: api.procurement_method ?? undefined,
    addressForDocument: api.address_for_document ?? undefined,
    addressForSecurity: api.address_for_security ?? undefined,
    placeForOpening: api.place_for_opening ?? undefined,
    biddersEligibility: api.bidders_eligibility ?? undefined,
    timeForCompletion: api.time_for_completion ?? undefined,
    invitedBy: api.invited_by ?? undefined,
    biddingCurrency: api.bidding_currency ?? undefined,
    instruction: api.instruction ?? undefined,
    lastDateSecurity: api.last_date_security ?? undefined,
    lastDateSubmission: api.last_date_submission ?? undefined,
    dateOpening: api.date_opening ?? undefined,
    preTenderMeetingInfo: api.pre_tender_meeting_info ?? undefined,
    biddersSchedulePurchase: api.bidders_schedule_purchase ?? undefined,
    tenderSecurityRequired: api.tender_security_required ?? undefined,
    contactDetails: api.contact_details ?? undefined,
    technologyTypes: api.technology_types ?? undefined,
    targetSiteType: api.target_site_type ?? undefined,
    isVerified: api.is_verified ?? undefined,
    fundingSource: api.funding_source ?? undefined,
    technicalWeight: api.technical_weight != null ? Number(api.technical_weight) : undefined,
    financialWeight: api.financial_weight != null ? Number(api.financial_weight) : undefined,
    technicalThreshold: api.technical_threshold != null ? Number(api.technical_threshold) : undefined,
    coolingOffDays: api.cooling_off_days != null ? Number(api.cooling_off_days) : undefined,
    scheduleFile: normalizeFileUrl(api.schedule_file ?? undefined),
    rfpDocumentsFile: normalizeFileUrl(api.rfp_documents_file ?? undefined),
    milestonePaymentScheduleFile: normalizeFileUrl(api.milestone_payment_schedule_file ?? undefined),
    intentToAwardBidId: api.intent_to_award_bid != null ? String(api.intent_to_award_bid) : undefined,
    intentToAwardAt: api.intent_to_award_at ?? undefined,
    coolingOffUntil: api.cooling_off_until ?? undefined,
    createdAt: api.created_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
    publishedAt: api.published_at ?? undefined,
    verifiedAt: api.verified_at ?? undefined,
    awardedAt: api.awarded_at ?? undefined,
    closedAt: api.closed_at ?? undefined,
    awardedVendorName: api.awarded_vendor_name ?? undefined,
    awardedVendorId: api.awarded_vendor_id ?? undefined,
    bidCount: api.bid_count ?? undefined,
  };
}

function mapUserFromApi(api: any): User {
  return {
    id: String(api.id ?? ""),
    fullName: api.full_name ?? api.fullName ?? api.username ?? "",
    email: api.email ?? "",
    role: (api.role as UserRole) ?? UserRole.VENDOR,
    gender: api.gender === "Male" || api.gender === "Female" || api.gender === "Other" ? api.gender : "Other",
    region: api.region ?? undefined,
    mobileNumber: api.mobile_number ?? undefined,
    nationalId: api.national_id ?? undefined,
    address: api.address ?? undefined,
    organizationName: api.organization_name ?? undefined,
    organizationType: api.organization_type ?? undefined,
    technologyTypes: Array.isArray(api.technology_types) ? api.technology_types : undefined,
    registrationCertificateName: api.registration_certificate_name ?? undefined,
    taxId: api.tax_id ?? undefined,
    deviceId: api.device_id ?? undefined,
    tierAssignment: api.tier_assignment ?? undefined,
    verificationZone: api.verification_zone ?? undefined,
    status: api.status ?? "Active",
    mustChangePassword: api.must_change_password ?? false,
    vendorTag: api.vendor_tag ?? undefined,
    blacklistSummary: api.blacklist_summary ?? undefined,
  };
}

function randomRef(): string {
  const n = Math.floor(100000 + Math.random() * 900000);
  return `REF-${n}`;
}

function mapTenderToApi(ui: Partial<Tender>): any {
  return {
    reference_number: ui.referenceNumber ?? "",
    name: ui.name ?? "",
    department: ui.department ?? "",
    category: ui.category ?? "",
    status: ui.status ?? "Draft",
    deadline: ui.deadline ?? ui.lastDateSubmission ?? null,
    budget: ui.budget ?? null,
    application_type: ui.applicationType ?? null,
    stage_type: ui.stageType ?? null,
    procurement_method: ui.procurementMethod ?? null,
    address_for_document: ui.addressForDocument ?? "",
    address_for_security: ui.addressForSecurity ?? "",
    place_for_opening: ui.placeForOpening ?? "",
    bidders_eligibility: ui.biddersEligibility ?? "",
    time_for_completion: ui.timeForCompletion ?? "",
    invited_by: ui.invitedBy ?? "",
    bidding_currency: ui.biddingCurrency ?? null,
    instruction: ui.instruction ?? "",
    last_date_security: ui.lastDateSecurity ?? null,
    last_date_submission: ui.lastDateSubmission ?? ui.deadline ?? null,
    date_opening: ui.dateOpening ?? ui.deadline ?? null,
    pre_tender_meeting_info: ui.preTenderMeetingInfo ?? "",
    bidders_schedule_purchase: ui.biddersSchedulePurchase ?? false,
    tender_security_required: ui.tenderSecurityRequired ?? false,
    contact_details: ui.contactDetails ?? "",
    technology_types: ui.technologyTypes ?? [],
    target_site_type: ui.targetSiteType ?? null,
    is_verified: ui.isVerified ?? false,
    funding_source: ui.fundingSource ?? null,
    technical_weight: ui.technicalWeight ?? 70,
    financial_weight: ui.financialWeight ?? 30,
    technical_threshold: ui.technicalThreshold ?? 70,
    cooling_off_days: ui.coolingOffDays ?? 7,
  };
}

function buildTenderForm(payload: Partial<Tender> & { scheduleFile?: File | null }): FormData {
  const apiPayload = mapTenderToApi(payload);
  const form = new FormData();
  Object.entries(apiPayload).forEach(([k, v]) => {
    if (v == null) return;
    if (k === 'technology_types' && Array.isArray(v)) {
      // JSONField expects JSON-encoded string
      form.append('technology_types', JSON.stringify(v));
      return;
    }
    if (Array.isArray(v)) {
      v.forEach((item) => form.append(`${k}[]`, String(item)));
    } else {
      form.append(k, String(v));
    }
  });
  const scheduleFile = (payload as any).scheduleFile;
  if (scheduleFile instanceof File) {
    form.set('schedule_file', scheduleFile);
  }
  const rfpDocumentsFile = (payload as any).rfpDocumentsFile;
  if (rfpDocumentsFile instanceof File) {
    form.set('rfp_documents_file', rfpDocumentsFile);
  }
  const milestonePaymentScheduleFile = (payload as any).milestonePaymentScheduleFile;
  if (milestonePaymentScheduleFile instanceof File) {
    form.set('milestone_payment_schedule_file', milestonePaymentScheduleFile);
  }
  return form;
}

function mapProjectFromApi(api: any): Project {
  return {
    id: String(api.id ?? ""),
    tenderId: api.tender != null ? String(api.tender) : undefined,
    projectTitle: api.project_title ?? undefined,
    projectReference: api.project_reference ?? undefined,
    tenderReferenceNumber: api.tender_reference_number ?? undefined,
    tenderName: api.tender_name ?? undefined,
    tenderBudget: api.tender_budget != null ? Number(api.tender_budget) : undefined,
    tenderDeadline: api.tender_deadline ?? undefined,
    tenderAwardedAt: api.tender_awarded_at ?? undefined,
    tenderStatus: api.tender_status ?? undefined,
    contractReference: api.contract_reference ?? undefined,
    contractStatus: api.contract_status ?? undefined,
    contractSignedFile: api.contract_signed_file ?? undefined,
    milestoneTotalAmount: api.milestone_total_amount != null ? Number(api.milestone_total_amount) : undefined,
    milestoneCount: api.milestone_count != null ? Number(api.milestone_count) : undefined,
    milestonePlanId: api.milestone_plan_id ?? undefined,
    vendorId: api.vendor_id ?? "",
    vendorName: api.vendor_name ?? "",
    techType: api.tech_type ?? "",
    region: api.region ?? "",
    district: api.district ?? undefined,
    status: api.status ?? "Pre-Qualification",
    progress: Number(api.progress ?? 0),
    startDate: api.start_date ?? undefined,
    endDate: api.end_date ?? undefined,
    budget: api.budget != null ? Number(api.budget) : undefined,
    targetInstallations: api.target_installations != null ? Number(api.target_installations) : undefined,
    targetFemalePct: api.target_female_pct != null ? Number(api.target_female_pct) : undefined,
    targetVulnerablePct: api.target_vulnerable_pct != null ? Number(api.target_vulnerable_pct) : undefined,
    targetBeneficiaries: api.target_beneficiaries != null ? Number(api.target_beneficiaries) : undefined,
    deploymentTeamRoster: api.deployment_team_roster ?? "",
    deploymentEquipmentPlan: api.deployment_equipment_plan ?? "",
    deploymentWorkSchedule: api.deployment_work_schedule ?? "",
    energyOutput: Number(api.energy_output ?? 0),
    uptime: Number(api.uptime ?? 0),
    genderImpact: Number(api.gender_impact ?? 0),
  };
}

function mapMilestoneFromApi(api: any): Milestone {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    name: api.name ?? "",
    description: api.description ?? undefined,
    percentage: Number(api.percentage ?? 0),
    status: api.status ?? "Pending",
    amount: Number(api.amount ?? 0),
    progressPercentage: Number(api.progress_percentage ?? 0),
    targetDate: api.target_date ?? undefined,
    completedDate: api.completed_date ?? undefined,
  };
}

function mapProjectUpdateFromApi(api: any): ProjectUpdate {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    title: api.title ?? undefined,
    body: api.body ?? "",
    author: api.author != null ? String(api.author) : undefined,
    authorUsername: api.author_username ?? undefined,
    createdAt: api.created_at ?? "",
  };
}

function mapProjectDocumentFromApi(api: any): ProjectDocument {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    title: api.title ?? undefined,
    file: normalizeFileUrl(api.file ?? api.file_url ?? "") ?? "",
    uploadedBy: api.uploaded_by != null ? String(api.uploaded_by) : undefined,
    uploadedByUsername: api.uploaded_by_username ?? undefined,
    uploadedAt: api.uploaded_at ?? "",
  };
}

function mapInstallationReportFromApi(api: any): InstallationReport {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    vendorId: String(api.vendor ?? ""),
    vendorUsername: api.vendor_username ?? undefined,
    milestoneId: api.milestone != null ? String(api.milestone) : undefined,
    gpsLat: Number(api.gps_lat ?? 0),
    gpsLng: Number(api.gps_lng ?? 0),
    serialNumber: api.serial_number ?? "",
    beneficiaryId: api.beneficiary_id ?? "",
    receiptFile: normalizeFileUrl(api.receipt_file ?? undefined),
    receiptFileUrl: normalizeFileUrl(api.receipt_file_url ?? undefined),
    photoFiles: Array.isArray(api.photo_files) ? api.photo_files.map(normalizeFileUrl) : [],
    meterId: api.meter_id ?? undefined,
    kwhReading: api.kwh_reading != null ? Number(api.kwh_reading) : undefined,
    status: api.status ?? "Submitted",
    submittedAt: api.submitted_at ?? "",
  };
}

function mapVerificationTaskFromApi(api: any): VerificationTask {
  return {
    id: String(api.id ?? ""),
    report: String(api.report ?? ""),
    assignedVerifier: api.assigned_verifier != null ? String(api.assigned_verifier) : undefined,
    assignedVerifierUsername: api.assigned_verifier_username ?? undefined,
    vendorLat: Number(api.vendor_lat ?? 0),
    vendorLng: Number(api.vendor_lng ?? 0),
    verifierLat: api.verifier_lat != null ? Number(api.verifier_lat) : undefined,
    verifierLng: api.verifier_lng != null ? Number(api.verifier_lng) : undefined,
    distanceMeters: api.distance_meters != null ? Number(api.distance_meters) : undefined,
    anomalyFlag: Boolean(api.anomaly_flag),
    status: api.status ?? "Pending",
    createdAt: api.created_at ?? "",
    updatedAt: api.updated_at ?? "",
  };
}

function mapBidEvaluationFromApi(api: any): TenderBidEvaluation {
  return {
    id: String(api.id ?? ""),
    bid: String(api.bid ?? ""),
    evaluator: api.evaluator != null ? String(api.evaluator) : undefined,
    evaluatorUsername: api.evaluator_username ?? undefined,
    status: api.status ?? "Pending",
    technicalScore: Number(api.technical_score ?? 0),
    financialScore: Number(api.financial_score ?? 0),
    feasibilityScore: Number(api.feasibility_score ?? 0),
    kpiScore: Number(api.kpi_score ?? 0),
    genderScore: Number(api.gender_score ?? 0),
    environmentalScore: Number(api.environmental_score ?? 0),
    omScore: Number(api.om_score ?? 0),
    inclusivityScore: Number(api.inclusivity_score ?? 0),
    totalScore: Number(api.total_score ?? 0),
    comments: api.comments ?? "",
    createdAt: api.created_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
  };
}

function mapTenderContractFromApi(api: any): TenderContract {
  return {
    id: String(api.id ?? ""),
    tender: String(api.tender ?? ""),
    bid: api.bid != null ? String(api.bid) : undefined,
    vendorId: String(api.vendor_id ?? ""),
    vendorName: api.vendor_name ?? "",
    vendorEmail: api.vendor_email ?? undefined,
    referenceNumber: api.reference_number ?? "",
    templateName: api.template_name ?? undefined,
    status: api.status ?? "Generated",
    generatedFile: normalizeFileUrl(api.generated_file ?? undefined),
    signedFile: normalizeFileUrl(api.signed_file ?? undefined),
    annexAFile: normalizeFileUrl(api.annex_a_file ?? undefined),
    annexBFile: normalizeFileUrl(api.annex_b_file ?? undefined),
    annexCFile: normalizeFileUrl(api.annex_c_file ?? undefined),
    annexDFile: normalizeFileUrl(api.annex_d_file ?? undefined),
    annexEFile: normalizeFileUrl(api.annex_e_file ?? undefined),
    signedAt: api.signed_at ?? undefined,
    approvedAt: api.approved_at ?? undefined,
    approvedBy: api.approved_by ?? undefined,
    rejectionReason: api.rejection_reason ?? undefined,
    milestonePlanId: api.milestone_plan_id ?? undefined,
    projectId: api.project_id ?? undefined,
    generatedAt: api.generated_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
  };
}

function mapNotificationFromApi(api: any): Notification {
  return {
    id: String(api.id ?? ""),
    recipientId: api.recipient_id ?? "",
    recipientName: api.recipient_name ?? "",
    type: api.type ?? "In-App",
    event: api.event ?? "",
    title: api.title ?? "",
    body: api.body ?? "",
    status: api.status ?? "Sent",
    timestamp: api.timestamp ?? new Date().toISOString(),
    linkedEntityId: api.linked_entity_id ?? undefined,
  };
}

function mapVendorBlacklistCaseFromApi(api: any): VendorBlacklistCase {
  return {
    id: String(api.id ?? ""),
    vendor: String(api.vendor ?? ""),
    vendorUsername: api.vendor_username ?? undefined,
    reason: api.reason ?? "",
    description: api.description ?? undefined,
    justificationDocument: normalizeFileUrl(api.justification_document ?? undefined),
    status: api.status ?? "",
    initiatedBy: api.initiated_by != null ? String(api.initiated_by) : undefined,
    initiatedByUsername: api.initiated_by_username ?? undefined,
    initiatedAt: api.initiated_at ?? undefined,
    noticeSentAt: api.notice_sent_at ?? undefined,
    coolingOffUntil: api.cooling_off_until ?? undefined,
    reviewedBy: api.reviewed_by != null ? String(api.reviewed_by) : undefined,
    reviewedByUsername: api.reviewed_by_username ?? undefined,
    reviewedAt: api.reviewed_at ?? undefined,
    reviewNotes: api.review_notes ?? undefined,
    confirmedBy: api.confirmed_by != null ? String(api.confirmed_by) : undefined,
    confirmedByUsername: api.confirmed_by_username ?? undefined,
    confirmedAt: api.confirmed_at ?? undefined,
    finalDecisionNotes: api.final_decision_notes ?? undefined,
    isPermanent: Boolean(api.is_permanent),
    expiryDate: api.expiry_date ?? undefined,
    reinstatedAt: api.reinstated_at ?? undefined,
    reinstatedBy: api.reinstated_by != null ? String(api.reinstated_by) : undefined,
    reinstatedByUsername: api.reinstated_by_username ?? undefined,
  };
}

function mapBlacklistAppealFromApi(api: any): BlacklistAppeal {
  return {
    id: String(api.id ?? ""),
    case: String(api.case ?? ""),
    vendor: String(api.vendor ?? ""),
    vendorUsername: api.vendor_username ?? undefined,
    rebuttalText: api.rebuttal_text ?? undefined,
    rebuttalDocument: normalizeFileUrl(api.rebuttal_document ?? undefined),
    status: api.status ?? "",
    submittedAt: api.submitted_at ?? undefined,
    reviewedBy: api.reviewed_by != null ? String(api.reviewed_by) : undefined,
    reviewedByUsername: api.reviewed_by_username ?? undefined,
    reviewedAt: api.reviewed_at ?? undefined,
    resolutionNotes: api.resolution_notes ?? undefined,
  };
}

function mapTenderBidSiteFromApi(api: any): TenderBidSite {
  return {
    id: api.id != null ? String(api.id) : undefined,
    siteName: api.site_name ?? "",
    district: api.district ?? undefined,
    latitude: api.latitude != null ? Number(api.latitude) : undefined,
    longitude: api.longitude != null ? Number(api.longitude) : undefined,
    systemConfiguration: api.system_configuration ?? undefined,
    boqItems: Array.isArray(api.boq_items) ? api.boq_items : [],
    notes: api.notes ?? undefined,
  };
}

function mapTenderBidFromApi(api: any): TenderBid {
  return {
    id: String(api.id ?? ""),
    tender: String(api.tender ?? ""),
    tender_reference: api.tender_reference ?? undefined,
    tender_name: api.tender_name ?? undefined,
    vendor_id: api.vendor_id ?? "",
    vendor_name: api.vendor_name ?? "",
    vendor_email: api.vendor_email ?? undefined,
    bid_amount: api.bid_amount != null ? Number(api.bid_amount) : undefined,
    stage: api.stage ?? undefined,
    concept_note: api.concept_note ?? undefined,
    technical_proposal: api.technical_proposal ?? undefined,
    financial_proposal: api.financial_proposal ?? undefined,
    technical_proposal_file: normalizeFileUrl(api.technical_proposal_file ?? undefined),
    financial_proposal_file: normalizeFileUrl(api.financial_proposal_file ?? undefined),
    boq_file: normalizeFileUrl(api.boq_file ?? undefined),
    gender_action_plan_file: normalizeFileUrl(api.gender_action_plan_file ?? undefined),
    implementation_plan_file: normalizeFileUrl(api.implementation_plan_file ?? undefined),
    reporting_templates_file: normalizeFileUrl(api.reporting_templates_file ?? undefined),
    status: (api.status as BidStatus) ?? BidStatus.DRAFT,
    version_number: Number(api.version_number ?? 0),
    submitted_at: api.submitted_at ?? undefined,
    reviewed_at: api.reviewed_at ?? undefined,
    reviewed_by: api.reviewed_by ?? undefined,
    rejection_reason: api.rejection_reason ?? undefined,
    sites: Array.isArray(api.sites) ? api.sites.map(mapTenderBidSiteFromApi) : [],
  };
}

function mapVendorPrequalificationFromApi(api: any): VendorPrequalification {
  return {
    id: String(api.id ?? ""),
    vendorId: api.vendor != null ? String(api.vendor) : undefined,
    vendorUsername: api.vendor_username ?? undefined,
    companyName: api.company_name ?? "",
    organizationType: api.organization_type ?? undefined,
    taxId: api.tax_id ?? undefined,
    hqAddress: api.hq_address ?? undefined,
    technologyTypes: Array.isArray(api.technology_types) ? api.technology_types : [],
    registrationCertificateName: api.registration_certificate_name ?? undefined,
    tradingLicense: normalizeFileUrl(api.trading_license ?? undefined),
    registrationCertificate: normalizeFileUrl(api.registration_certificate ?? undefined),
    taxComplianceCertificate: normalizeFileUrl(api.tax_compliance_certificate ?? undefined),
    authorizedSignatoryId: api.authorized_signatory_id ?? undefined,
    experienceFinancialProof: normalizeFileUrl(api.experience_financial_proof ?? undefined),
    techTier: api.tech_tier ?? undefined,
    yearsExperience: Number(api.years_experience ?? 0),
    priorProjects: Number(api.prior_projects ?? 0),
    annualRevenue: api.annual_revenue != null ? Number(api.annual_revenue) : undefined,
    districtsCovered: Number(api.districts_covered ?? 0),
    femaleBeneficiaryTarget: Number(api.female_beneficiary_target ?? 50),
    vulnerableGroupTarget: Number(api.vulnerable_group_target ?? 30),
    bankAccountName: api.bank_account_name ?? undefined,
    bankAccountNumber: api.bank_account_number ?? undefined,
    contactNumber: api.contact_number ?? undefined,
    email: api.email ?? undefined,
    genderOfFocalPerson: api.gender_of_focal_person ?? undefined,
    declarationAccepted: Boolean(api.declaration_accepted),
    reviewerComments: api.reviewer_comments ?? undefined,
    status: api.status ?? "Pending",
    submittedAt: api.submitted_at ?? "",
    reviewedAt: api.reviewed_at ?? undefined,
    reviewedBy: api.reviewed_by != null ? String(api.reviewed_by) : undefined,
    reviewedByUsername: api.reviewed_by_username ?? undefined,
  };
}

function mapDisbursementFromApi(api: any): Disbursement {
  return {
    id: String(api.id ?? ""),
    claimId: String(api.claim ?? ""),
    amount: Number(api.amount ?? 0),
    status: api.status ?? "Initiated",
    reference: api.reference ?? undefined,
    notes: api.notes ?? undefined,
    processedBy: api.processed_by != null ? String(api.processed_by) : undefined,
    processedByUsername: api.processed_by_username ?? undefined,
    processedAt: api.processed_at ?? undefined,
  };
}

function mapPaymentClaimFromApi(api: any): PaymentClaim {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    vendorId: String(api.vendor ?? ""),
    milestoneId: api.milestone != null ? String(api.milestone) : undefined,
    completionDate: api.completion_date ?? undefined,
    claimAmount: Number(api.claim_amount ?? 0),
    actualBeneficiaries: Number(api.actual_beneficiaries ?? 0),
    actualFemaleBeneficiaries: Number(api.actual_female_beneficiaries ?? 0),
    implementationNotes: api.implementation_notes ?? undefined,
    evidenceFiles: Array.isArray(api.evidence_files) ? api.evidence_files : [],
    declarationAccepted: Boolean(api.declaration_accepted),
    status: api.status ?? "Pending",
    submittedAt: api.submitted_at ?? "",
    verifiedAt: api.verified_at ?? undefined,
    approvedAt: api.approved_at ?? undefined,
    paidAt: api.paid_at ?? undefined,
    paymentReference: api.payment_reference ?? undefined,
    remarks: api.remarks ?? undefined,
    reviewedBy: api.reviewed_by != null ? String(api.reviewed_by) : undefined,
    reviewedByUsername: api.reviewed_by_username ?? undefined,
    vendorUsername: api.vendor_username ?? undefined,
    disbursement: api.disbursement ? mapDisbursementFromApi(api.disbursement) : undefined,
  };
}

function mapAuditLogFromApi(api: any): AuditLog {
  return {
    id: String(api.id ?? ""),
    action: api.action ?? "",
    entityType: api.entity_type ?? "",
    entityId: api.entity_id != null ? String(api.entity_id) : "",
    details: api.details && typeof api.details === "object" ? api.details : {},
    actor: api.actor != null ? String(api.actor) : undefined,
    actorUsername: api.actor_username ?? undefined,
    createdAt: api.created_at ?? "",
  };
}

function unwrapListResponse<T>(data: any): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && Array.isArray(data.results)) return data.results as T[];
  return [];
}

// ============ HTTP helpers ============

type ApiRequestInit = RequestInit & {
  timeoutMs?: number;
};

async function http<T>(url: string, init?: ApiRequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null;
  const initHeaders = headersInitToObject(init?.headers as HeadersInit | undefined);
  const skipAuth = Boolean(getHeaderValue(initHeaders, "X-Skip-Auth"));
  const timeoutMs = init?.timeoutMs ?? requestTimeoutMs;
  
  // Don't set Content-Type for FormData - let browser set multipart/form-data
  const isFormData = init?.body instanceof FormData;
  const headers: Record<string, string> = isFormData ? {} : {
    "Content-Type": "application/json",
    ...initHeaders,
  };
  
  // If FormData, merge init headers but skip Content-Type
  if (isFormData) {
    Object.entries(initHeaders).forEach(([k, v]) => {
      if (k.toLowerCase() !== 'content-type') {
        headers[k] = v;
      }
    });
  }
  
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === "x-skip-auth") {
      delete headers[key];
    }
  }
  if (token && !skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const { headers: _ignoredHeaders, timeoutMs: _ignoredTimeoutMs, ...requestInit } = init ?? {};

  const isAbsolute = /^https?:\/\//i.test(url);
  const requestUrls = isAbsolute
    ? [url]
    : API_BASE_CANDIDATES.map((base) => joinApiUrl(base, url));

  let lastError: Error | null = null;
  for (let i = 0; i < requestUrls.length; i += 1) {
    const requestUrl = requestUrls[i];
    const isLastAttempt = i === requestUrls.length - 1;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(requestUrl, {
        ...requestInit,
        headers,
        signal: controller.signal,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        const detail = extractApiErrorDetail(text);
        const statusError = new Error(`HTTP ${res.status} ${res.statusText}: ${detail || text}`);
        if (res.status === 401 && !skipAuth) {
          const refreshed = await refreshAccessToken();
          if (refreshed) {
            const retryHeaders = { ...headers, Authorization: `Bearer ${refreshed}` };
            const retryRes = await fetch(requestUrl, {
              ...requestInit,
              headers: retryHeaders,
              signal: controller.signal,
            });
            if (retryRes.ok) {
              if (retryRes.status === 204) {
                return undefined as T;
              }
              return (await retryRes.json()) as T;
            }
          }
        }
        // If same-origin /api path doesn't exist, try explicit backends.
        if (!isAbsolute && res.status === 404 && requestUrls.length > 1) {
          lastError = statusError;
          continue;
        }
        throw statusError;
      }
      if (res.status === 204) {
        return undefined as T;
      }
      return (await res.json()) as T;
    } catch (error: any) {
      const rawMessage = String(error?.message || "");
      if (rawMessage.startsWith("HTTP ")) {
        // Preserve real API/auth errors instead of masking them with fallback failures.
        throw (error instanceof Error ? error : new Error(rawMessage));
      }

      if (error?.name === "AbortError") {
        lastError = new Error(`Request timed out after ${timeoutMs}ms`);
      } else {
        lastError = error instanceof Error ? error : new Error(String(error));
      }

      if (isLastAttempt) {
        throw lastError;
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }

  throw lastError ?? new Error("Request failed");
}

async function refreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refresh) return null;
  try {
    const data = await http<any>(`/api/users/auth/token/refresh/`, {
      method: "POST",
      headers: { "X-Skip-Auth": "1" } as any,
      body: JSON.stringify({ refresh }),
    });
    if (data?.access) {
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
      return data.access;
    }
  } catch {
    logoutUser();
  }
  return null;
}

// ============ API functions ============

export async function fetchTenders(): Promise<Tender[]> {
  const data = await http<any>(`/api/tenders/`);
  return unwrapListResponse<any>(data).map(mapTenderFromApi);
}

export async function createTender(payload: Partial<Tender>): Promise<Tender> {
  const form = buildTenderForm(payload as any);
  const data = await http<any>(`/api/tenders/`, { method: "POST", body: form });
  return mapTenderFromApi(data);
}

export async function updateTender(
  tenderId: string,
  payload: Partial<Tender> & { scheduleFile?: File | null }
): Promise<Tender> {
  const form = buildTenderForm(payload);
  const data = await http<any>(`/api/tenders/${tenderId}/`, { method: "PATCH", body: form });
  return mapTenderFromApi(data);
}

export async function fetchTender(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/`);
  return mapTenderFromApi(data);
}

export async function verifyTender(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/verify/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function publishTender(
  tenderId: string,
  options?: { sendEmail?: boolean; notifyAllBidders?: boolean }
): Promise<{ tender: Tender; summary?: { recipient_count?: number; email_enabled?: boolean; email_recipient_count?: number; email_error?: string | null } }> {
  const data = await http<any>(`/api/tenders/${tenderId}/publish/`, {
    method: "POST",
    body: JSON.stringify({
      send_email: options?.sendEmail ?? true,
      notify_all_bidders: options?.notifyAllBidders ?? true,
    }),
  });
  return {
    tender: mapTenderFromApi(data),
    summary: data?.notification_summary ?? undefined,
  };
}

export async function awardTender(
  tenderId: string,
  payload: {
    bidId: string;
    awardedVendorId?: string;
    awardedVendorName?: string;
    sendSms?: boolean;
    sendEmail?: boolean;
  }
): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/award/`, {
    method: "POST",
    body: JSON.stringify({
      bid_id: payload.bidId,
      awarded_vendor_id: payload.awardedVendorId ?? "",
      awarded_vendor_name: payload.awardedVendorName ?? "",
      send_sms: payload.sendSms ?? false,
      send_email: payload.sendEmail ?? true,
    }),
  });
  return mapTenderFromApi(data);
}

export async function fetchTenderAwardRanking(
  tenderId: string
): Promise<{
  technical_weight: number;
  financial_weight: number;
  technical_threshold: number;
  cooling_off_days: number;
  rows: TenderAwardRankingRow[];
  recommended?: TenderAwardRankingRow | null;
}> {
  return await http<any>(`/api/tenders/${tenderId}/award_ranking/`);
}

export async function confirmTenderAward(
  tenderId: string,
  payload?: { sendEmail?: boolean }
): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/confirm_award/`, {
    method: "POST",
    timeoutMs: 60000,
    body: JSON.stringify({
      send_email: payload?.sendEmail ?? true,
    }),
  });
  return mapTenderFromApi(data);
}

export async function closeTender(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/close/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function verifyTenderSecurity(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/verify_security/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function searchTendersForSecurityVerification(params?: {
  searchKey?: string;
  awardDateFrom?: string;
  awardDateTo?: string;
  sortBy?: string;
  limit?: number;
}): Promise<Tender[]> {
  const queryParams = new URLSearchParams();
  if (params?.searchKey) queryParams.set("search_key", params.searchKey);
  if (params?.awardDateFrom) queryParams.set("award_date_from", params.awardDateFrom);
  if (params?.awardDateTo) queryParams.set("award_date_to", params.awardDateTo);
  if (params?.sortBy) queryParams.set("sort_by", params.sortBy);
  if (params?.limit) queryParams.set("limit", String(params.limit));

  const url =
    `/api/tenders/security_verification_search/?${queryParams.toString()}`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapTenderFromApi);
}

export async function submitTenderBid(payload: Partial<TenderBid>): Promise<TenderBid> {
  const form = new FormData();
  form.append('tender', String(payload.tender ?? ""));
  if (payload.bid_amount != null) form.append('bid_amount', String(payload.bid_amount));
  form.append('stage', payload.stage ?? "");
  form.append('concept_note', payload.concept_note ?? "");
  form.append('technical_proposal', payload.technical_proposal ?? "");
  form.append('financial_proposal', payload.financial_proposal ?? "");
  form.append('status', payload.status ?? BidStatus.DRAFT);

  const sitesPayload = (payload.sites ?? []).map((site) => ({
    site_name: site.siteName,
    district: site.district ?? "",
    latitude: site.latitude ?? null,
    longitude: site.longitude ?? null,
    system_configuration: site.systemConfiguration ?? {},
    boq_items: site.boqItems ?? [],
    notes: site.notes ?? "",
  }));
  form.append('sites', JSON.stringify(sitesPayload));

  const technicalProposalFile = (payload as any).technical_proposal_file;
  if (technicalProposalFile instanceof File) {
    form.append('technical_proposal_file', technicalProposalFile);
  }
  const financialProposalFile = (payload as any).financial_proposal_file;
  if (financialProposalFile instanceof File) {
    form.append('financial_proposal_file', financialProposalFile);
  }
  const boqFile = (payload as any).boq_file;
  if (boqFile instanceof File) {
    form.append('boq_file', boqFile);
  }
  const genderActionPlanFile = (payload as any).gender_action_plan_file;
  if (genderActionPlanFile instanceof File) {
    form.append('gender_action_plan_file', genderActionPlanFile);
  }
  const implementationPlanFile = (payload as any).implementation_plan_file;
  if (implementationPlanFile instanceof File) {
    form.append('implementation_plan_file', implementationPlanFile);
  }
  const reportingTemplatesFile = (payload as any).reporting_templates_file;
  if (reportingTemplatesFile instanceof File) {
    form.append('reporting_templates_file', reportingTemplatesFile);
  }

  const data = await http<any>(`/api/tender-bids/`, {
    method: "POST",
    body: form,
  });
  return mapTenderBidFromApi(data);
}

export async function updateTenderBid(bidId: string, payload: Partial<TenderBid>): Promise<TenderBid> {
  const form = new FormData();
  if (payload.bid_amount != null) form.append('bid_amount', String(payload.bid_amount));
  if (payload.stage != null) form.append('stage', payload.stage);
  if (payload.concept_note != null) form.append('concept_note', payload.concept_note);
  if (payload.technical_proposal != null) form.append('technical_proposal', payload.technical_proposal);
  if (payload.financial_proposal != null) form.append('financial_proposal', payload.financial_proposal);
  if (payload.status != null) form.append('status', payload.status);

  if (payload.sites) {
    const sitesPayload = (payload.sites ?? []).map((site) => ({
      site_name: site.siteName,
      district: site.district ?? "",
      latitude: site.latitude ?? null,
      longitude: site.longitude ?? null,
      system_configuration: site.systemConfiguration ?? {},
      boq_items: site.boqItems ?? [],
      notes: site.notes ?? "",
    }));
    form.append('sites', JSON.stringify(sitesPayload));
  }

  const technicalProposalFile = (payload as any).technical_proposal_file;
  if (technicalProposalFile instanceof File) {
    form.append('technical_proposal_file', technicalProposalFile);
  }
  const financialProposalFile = (payload as any).financial_proposal_file;
  if (financialProposalFile instanceof File) {
    form.append('financial_proposal_file', financialProposalFile);
  }
  const boqFile = (payload as any).boq_file;
  if (boqFile instanceof File) {
    form.append('boq_file', boqFile);
  }
  const genderActionPlanFile = (payload as any).gender_action_plan_file;
  if (genderActionPlanFile instanceof File) {
    form.append('gender_action_plan_file', genderActionPlanFile);
  }
  const implementationPlanFile = (payload as any).implementation_plan_file;
  if (implementationPlanFile instanceof File) {
    form.append('implementation_plan_file', implementationPlanFile);
  }
  const reportingTemplatesFile = (payload as any).reporting_templates_file;
  if (reportingTemplatesFile instanceof File) {
    form.append('reporting_templates_file', reportingTemplatesFile);
  }

  const data = await http<any>(`/api/tender-bids/${bidId}/`, {
    method: "PATCH",
    body: form,
  });
  return mapTenderBidFromApi(data);
}

export async function submitTenderBidFinal(bidId: string): Promise<TenderBid> {
  const data = await http<any>(`/api/tender-bids/${bidId}/submit/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderBidFromApi(data);
}

export async function fetchTenderBids(tenderId?: string): Promise<TenderBid[]> {
  const url = tenderId
    ? `/api/tender-bids/?tender=${tenderId}`
    : `/api/tender-bids/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapTenderBidFromApi);
}

export async function reviewTenderBid(bidId: string): Promise<TenderBid> {
  const data = await http<any>(`/api/tender-bids/${bidId}/review/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderBidFromApi(data);
}

export async function acceptTenderBid(bidId: string): Promise<TenderBid> {
  const data = await http<any>(`/api/tender-bids/${bidId}/accept/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderBidFromApi(data);
}

export async function rejectTenderBid(
  bidId: string,
  rejectionReason: string
): Promise<TenderBid> {
  const data = await http<any>(`/api/tender-bids/${bidId}/reject/`, {
    method: "POST",
    body: JSON.stringify({
      rejection_reason: rejectionReason,
    }),
  });
  return mapTenderBidFromApi(data);
}

export async function fetchBidEvaluations(bidId?: string): Promise<TenderBidEvaluation[]> {
  const url = bidId ? `/api/tender-bid-evaluations/?bid=${bidId}` : `/api/tender-bid-evaluations/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapBidEvaluationFromApi);
}

export async function createBidEvaluation(payload: Partial<TenderBidEvaluation> & { bid: string }): Promise<TenderBidEvaluation> {
  const data = await http<any>(`/api/tender-bid-evaluations/`, {
    method: "POST",
    body: JSON.stringify({
      bid: payload.bid,
      technical_score: payload.technicalScore ?? 0,
      financial_score: payload.financialScore ?? 0,
      feasibility_score: payload.feasibilityScore ?? 0,
      kpi_score: payload.kpiScore ?? 0,
      gender_score: payload.genderScore ?? 0,
      environmental_score: payload.environmentalScore ?? 0,
      om_score: payload.omScore ?? 0,
      inclusivity_score: payload.inclusivityScore ?? 0,
      comments: payload.comments ?? "",
    }),
  });
  return mapBidEvaluationFromApi(data);
}

export async function updateBidEvaluation(id: string, payload: Partial<TenderBidEvaluation>): Promise<TenderBidEvaluation> {
  const data = await http<any>(`/api/tender-bid-evaluations/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({
      technical_score: payload.technicalScore,
      financial_score: payload.financialScore,
      feasibility_score: payload.feasibilityScore,
      kpi_score: payload.kpiScore,
      gender_score: payload.genderScore,
      environmental_score: payload.environmentalScore,
      om_score: payload.omScore,
      inclusivity_score: payload.inclusivityScore,
      comments: payload.comments,
    }),
  });
  return mapBidEvaluationFromApi(data);
}

export async function fetchTenderContracts(params?: { tenderId?: string; vendorId?: string; status?: string }): Promise<TenderContract[]> {
  const query = new URLSearchParams();
  if (params?.tenderId) query.set("tender", params.tenderId);
  if (params?.vendorId) query.set("vendor_id", params.vendorId);
  if (params?.status) query.set("status", params.status);
  const url = query.toString() ? `/api/tender-contracts/?${query.toString()}` : `/api/tender-contracts/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapTenderContractFromApi);
}

export async function generateTenderContract(payload: { tenderId: string; bidId?: string; vendorId?: string; templateName?: string }): Promise<TenderContract> {
  const data = await http<any>(`/api/tender-contracts/generate/`, {
    method: "POST",
    timeoutMs: 60000,
    body: JSON.stringify({
      tender: payload.tenderId,
      bid: payload.bidId ?? null,
      vendor_id: payload.vendorId ?? null,
      template_name: payload.templateName ?? "",
    }),
  });
  return mapTenderContractFromApi(data);
}

export async function signTenderContract(contractId: string, payload: {
  signedFile: File;
}): Promise<TenderContract> {
  const form = new FormData();
  form.append("signed_file", payload.signedFile);
  const data = await http<any>(`/api/tender-contracts/${contractId}/sign/`, {
    method: "POST",
    body: form,
  });
  return mapTenderContractFromApi(data);
}

export async function approveTenderContract(contractId: string, milestones?: Array<{ name: string; percentage: number; amount: number }>): Promise<TenderContract> {
  const body: any = {};
  if (milestones) body.milestones = milestones;
  const data = await http<any>(`/api/tender-contracts/${contractId}/approve/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return mapTenderContractFromApi(data);
}

export async function rejectTenderContract(contractId: string, reason: string): Promise<TenderContract> {
  const data = await http<any>(`/api/tender-contracts/${contractId}/reject/`, {
    method: "POST",
    body: JSON.stringify({ rejection_reason: reason }),
  });
  return mapTenderContractFromApi(data);
}

export async function fetchProjects(): Promise<Project[]> {
  const data = await http<any>(`/api/projects/`);
  return unwrapListResponse<any>(data).map(mapProjectFromApi);
}

export async function updateProject(id: string, payload: Partial<Project>): Promise<Project> {
  const body: Record<string, any> = {
    deployment_team_roster: payload.deploymentTeamRoster ?? "",
    deployment_equipment_plan: payload.deploymentEquipmentPlan ?? "",
    deployment_work_schedule: payload.deploymentWorkSchedule ?? "",
  };
  const data = await http<any>(`/api/projects/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return mapProjectFromApi(data);
}

export async function fetchMilestones(projectId?: string): Promise<Milestone[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/milestones/${query}`);
  return unwrapListResponse<any>(data).map(mapMilestoneFromApi);
}

export async function createMilestone(payload: {
  projectId: string;
  name: string;
  description?: string;
  percentage?: number;
  amount?: number;
  status?: "Pending" | "Submitted" | "Verified" | "Paid";
  progressPercentage?: number;
  targetDate?: string;
  completedDate?: string;
}): Promise<Milestone> {
  const data = await http<any>(`/api/projects/milestones/`, {
    method: "POST",
    body: JSON.stringify({
      project: payload.projectId,
      name: payload.name,
      description: payload.description ?? "",
      percentage: payload.percentage ?? 0,
      amount: payload.amount ?? 0,
      status: payload.status ?? "Pending",
      progress_percentage: payload.progressPercentage ?? 0,
      target_date: payload.targetDate ?? null,
      completed_date: payload.completedDate ?? null,
    }),
  });
  return mapMilestoneFromApi(data);
}

export async function updateMilestone(id: string, payload: {
  projectId: string;
  name?: string;
  description?: string;
  percentage?: number;
  amount?: number;
  status?: "Pending" | "Submitted" | "Verified" | "Paid";
  progressPercentage?: number;
  targetDate?: string | null;
  completedDate?: string | null;
}): Promise<Milestone> {
  const body: Record<string, unknown> = {
    project: payload.projectId,
  };
  if (payload.name !== undefined) body.name = payload.name;
  if (payload.description !== undefined) body.description = payload.description;
  if (payload.percentage !== undefined) body.percentage = payload.percentage;
  if (payload.amount !== undefined) body.amount = payload.amount;
  if (payload.status !== undefined) body.status = payload.status;
  if (payload.progressPercentage !== undefined) body.progress_percentage = payload.progressPercentage;
  if (payload.targetDate !== undefined) body.target_date = payload.targetDate;
  if (payload.completedDate !== undefined) body.completed_date = payload.completedDate;

  const data = await http<any>(`/api/projects/milestones/${id}/`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return mapMilestoneFromApi(data);
}

export async function fetchProjectUpdates(projectId?: string): Promise<ProjectUpdate[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/updates/${query}`);
  return unwrapListResponse<any>(data).map(mapProjectUpdateFromApi);
}

export async function createProjectUpdate(payload: {
  projectId: string;
  title?: string;
  body: string;
}): Promise<ProjectUpdate> {
  const data = await http<any>(`/api/projects/updates/`, {
    method: "POST",
    body: JSON.stringify({
      project: payload.projectId,
      title: payload.title ?? "",
      body: payload.body,
    }),
  });
  return mapProjectUpdateFromApi(data);
}

export async function fetchProjectDocuments(projectId?: string): Promise<ProjectDocument[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/documents/${query}`);
  return unwrapListResponse<any>(data).map(mapProjectDocumentFromApi);
}

export async function uploadProjectDocument(payload: {
  projectId: string;
  title?: string;
  file: File;
}): Promise<ProjectDocument> {
  const form = new FormData();
  form.append("project", payload.projectId);
  if (payload.title) {
    form.append("title", payload.title);
  }
  form.append("file", payload.file);
  const data = await http<any>(`/api/projects/documents/`, {
    method: "POST",
    body: form,
  });
  return mapProjectDocumentFromApi(data);
}

export async function fetchInstallationReports(projectId?: string): Promise<InstallationReport[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/installations/${query}`);
  return unwrapListResponse<any>(data).map(mapInstallationReportFromApi);
}

export async function createInstallationReport(payload: {
  projectId: string;
  milestoneId?: string;
  gpsLat: number;
  gpsLng: number;
  serialNumber: string;
  beneficiaryId: string;
  receiptFile?: File | null;
  photoFiles?: File[];
  meterId?: string;
  kwhReading?: number;
}): Promise<InstallationReport> {
  const form = new FormData();
  form.append("project", payload.projectId);
  if (payload.milestoneId) form.append("milestone", payload.milestoneId);
  form.append("gps_lat", String(payload.gpsLat));
  form.append("gps_lng", String(payload.gpsLng));
  form.append("serial_number", payload.serialNumber);
  form.append("beneficiary_id", payload.beneficiaryId);
  if (payload.meterId) form.append("meter_id", payload.meterId);
  if (payload.kwhReading != null) form.append("kwh_reading", String(payload.kwhReading));
  if (payload.receiptFile instanceof File) {
    form.append("receipt_file", payload.receiptFile);
  }
  (payload.photoFiles || []).forEach((file) => {
    form.append("photos", file);
  });
  const data = await http<any>(`/api/projects/installations/`, {
    method: "POST",
    body: form,
  });
  return mapInstallationReportFromApi(data);
}

export async function fetchVerificationTasks(projectId?: string): Promise<VerificationTask[]> {
  const query = projectId ? `?report__project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/verification-tasks/${query}`);
  return unwrapListResponse<any>(data).map(mapVerificationTaskFromApi);
}

export async function fetchNotifications(): Promise<Notification[]> {
  const data = await http<any>(`/api/notifications/`);
  return unwrapListResponse<any>(data).map(mapNotificationFromApi);
}

export async function fetchVendorPrequalifications(): Promise<VendorPrequalification[]> {
  const data = await http<any>(`/api/users/prequalifications/`);
  return unwrapListResponse<any>(data).map(mapVendorPrequalificationFromApi);
}

export async function fetchBlacklistCases(): Promise<VendorBlacklistCase[]> {
  const data = await http<any>(`/api/users/blacklisting-cases/`);
  return unwrapListResponse<any>(data).map(mapVendorBlacklistCaseFromApi);
}

export async function fetchBlacklistAppeals(): Promise<BlacklistAppeal[]> {
  const data = await http<any>(`/api/users/blacklisting-appeals/`);
  return unwrapListResponse<any>(data).map(mapBlacklistAppealFromApi);
}

export async function initiateVendorBlacklisting(payload: {
  vendorId: string;
  reason: string;
  description?: string;
  coolingOffDays?: number;
  expiryDate?: string;
  isPermanent?: boolean;
  justificationDocument?: File | null;
}): Promise<VendorBlacklistCase> {
  const form = new FormData();
  form.append("reason", payload.reason);
  form.append("description", payload.description ?? "");
  form.append("cooling_off_days", String(payload.coolingOffDays ?? 14));
  form.append("is_permanent", String(Boolean(payload.isPermanent)));
  if (payload.expiryDate) form.append("expiry_date", payload.expiryDate);
  if (payload.justificationDocument instanceof File) {
    form.append("justification_document", payload.justificationDocument);
  }
  const data = await http<any>(`/api/users/${payload.vendorId}/initiate_blacklisting/`, {
    method: "POST",
    body: form,
  });
  return mapVendorBlacklistCaseFromApi(data);
}

async function postBlacklistCaseAction(
  caseId: string,
  action: "review" | "confirm" | "reject" | "reinstate" | "appeal",
  payload?: Record<string, any> | FormData
): Promise<VendorBlacklistCase | BlacklistAppeal> {
  const data = await http<any>(`/api/users/blacklisting-cases/${caseId}/${action}/`, {
    method: "POST",
    body: payload instanceof FormData ? payload : JSON.stringify(payload ?? {}),
  });
  return action === "appeal" ? mapBlacklistAppealFromApi(data) : mapVendorBlacklistCaseFromApi(data);
}

export async function reviewBlacklistCase(caseId: string, reviewNotes?: string): Promise<VendorBlacklistCase> {
  return postBlacklistCaseAction(caseId, "review", { review_notes: reviewNotes ?? "" }) as Promise<VendorBlacklistCase>;
}

export async function confirmBlacklistCase(caseId: string, payload?: {
  finalDecisionNotes?: string;
  expiryDate?: string;
  isPermanent?: boolean;
}): Promise<VendorBlacklistCase> {
  return postBlacklistCaseAction(caseId, "confirm", {
    final_decision_notes: payload?.finalDecisionNotes ?? "",
    expiry_date: payload?.expiryDate ?? "",
    is_permanent: payload?.isPermanent ?? false,
  }) as Promise<VendorBlacklistCase>;
}

export async function rejectBlacklistCase(caseId: string, finalDecisionNotes?: string): Promise<VendorBlacklistCase> {
  return postBlacklistCaseAction(caseId, "reject", {
    final_decision_notes: finalDecisionNotes ?? "",
  }) as Promise<VendorBlacklistCase>;
}

export async function reinstateBlacklistCase(caseId: string): Promise<VendorBlacklistCase> {
  return postBlacklistCaseAction(caseId, "reinstate", {}) as Promise<VendorBlacklistCase>;
}

export async function submitBlacklistAppeal(caseId: string, payload: {
  rebuttalText?: string;
  rebuttalDocument?: File | null;
}): Promise<BlacklistAppeal> {
  const form = new FormData();
  form.append("rebuttal_text", payload.rebuttalText ?? "");
  if (payload.rebuttalDocument instanceof File) {
    form.append("rebuttal_document", payload.rebuttalDocument);
  }
  return postBlacklistCaseAction(caseId, "appeal", form) as Promise<BlacklistAppeal>;
}

export async function reviewBlacklistAppeal(appealId: string, resolutionNotes?: string): Promise<BlacklistAppeal> {
  const data = await http<any>(`/api/users/blacklisting-appeals/${appealId}/review/`, {
    method: "POST",
    body: JSON.stringify({
      resolution_notes: resolutionNotes ?? "",
    }),
  });
  return mapBlacklistAppealFromApi(data);
}

export async function submitVendorPrequalification(
  payload: VendorPrequalificationSubmission
): Promise<VendorPrequalification> {
  const form = new FormData();
  
  // Add text fields
  form.append('company_name', payload.companyName);
  form.append('organization_type', payload.organizationType ?? "");
  form.append('tax_id', payload.taxId ?? "");
  form.append('hq_address', payload.hqAddress ?? "");
  form.append('technology_types', JSON.stringify(payload.technologyTypes ?? []));
  form.append('registration_certificate_name', payload.registrationCertificateName ?? "");
  form.append('tech_tier', payload.techTier ?? "");
  form.append('years_experience', String(payload.yearsExperience ?? 0));
  form.append('prior_projects', String(payload.priorProjects ?? 0));
  form.append('annual_revenue', String(payload.annualRevenue ?? 0));
  form.append('districts_covered', String(payload.districtsCovered ?? 0));
  form.append('female_beneficiary_target', String(payload.femaleBeneficiaryTarget ?? 50));
  form.append('vulnerable_group_target', String(payload.vulnerableGroupTarget ?? 30));
  form.append('bank_account_name', payload.bankAccountName ?? "");
  form.append('bank_account_number', payload.bankAccountNumber ?? "");
  form.append('contact_number', payload.contactNumber ?? "");
  form.append('email', payload.email ?? "");
  form.append('gender_of_focal_person', payload.genderOfFocalPerson ?? "");
  form.append('declaration_accepted', String(payload.declarationAccepted));
  
  // Add file fields
  if (payload.registrationCertificate instanceof File) {
    form.append('registration_certificate', payload.registrationCertificate);
  }
  if (payload.tradingLicense instanceof File) {
    form.append('trading_license', payload.tradingLicense);
  }
  if (payload.taxComplianceCertificate instanceof File) {
    form.append('tax_compliance_certificate', payload.taxComplianceCertificate);
  }
  if (payload.authorizedSignatoryId instanceof File) {
    form.append('authorized_signatory_id', payload.authorizedSignatoryId);
  }
  if (payload.experienceFinancialProof instanceof File) {
    form.append('experience_financial_proof', payload.experienceFinancialProof);
  }
  
  const data = await http<any>(`/api/users/prequalifications/`, {
    method: "POST",
    body: form,
  });
  return mapVendorPrequalificationFromApi(data);
}

async function reviewVendorPrequalification(
  id: string,
  action: "start_review" | "approve" | "request_clarification" | "reject",
  reviewerComments?: string
): Promise<VendorPrequalification> {
  const data = await http<any>(`/api/users/prequalifications/${id}/${action}/`, {
    method: "POST",
    body: JSON.stringify({
      reviewer_comments: reviewerComments ?? "",
    }),
  });
  return mapVendorPrequalificationFromApi(data);
}

export async function startVendorPrequalificationReview(
  id: string,
  reviewerComments?: string
): Promise<VendorPrequalification> {
  return reviewVendorPrequalification(id, "start_review", reviewerComments);
}

export async function approveVendorPrequalification(
  id: string,
  reviewerComments?: string
): Promise<VendorPrequalification> {
  return reviewVendorPrequalification(id, "approve", reviewerComments);
}

export async function requestVendorPrequalificationClarification(
  id: string,
  reviewerComments?: string
): Promise<VendorPrequalification> {
  return reviewVendorPrequalification(id, "request_clarification", reviewerComments);
}

export async function rejectVendorPrequalification(
  id: string,
  reviewerComments?: string
): Promise<VendorPrequalification> {
  return reviewVendorPrequalification(id, "reject", reviewerComments);
}

export async function fetchPaymentClaims(): Promise<PaymentClaim[]> {
  const data = await http<any>(`/api/projects/claims/`);
  return unwrapListResponse<any>(data).map(mapPaymentClaimFromApi);
}

export async function submitPaymentClaim(payload: PaymentClaimSubmission): Promise<PaymentClaim> {
  const data = await http<any>(`/api/projects/claims/`, {
    method: "POST",
    body: JSON.stringify({
      project: payload.projectId,
      milestone: payload.milestoneId ?? null,
      completion_date: payload.completionDate ?? null,
      claim_amount: payload.claimAmount,
      actual_beneficiaries: payload.actualBeneficiaries,
      actual_female_beneficiaries: payload.actualFemaleBeneficiaries,
      implementation_notes: payload.implementationNotes ?? "",
      evidence_files: payload.evidenceFiles ?? [],
      declaration_accepted: payload.declarationAccepted,
    }),
  });
  return mapPaymentClaimFromApi(data);
}

async function reviewPaymentClaim(
  id: string,
  action: "verify" | "approve" | "reject" | "pay",
  payload?: Record<string, any>
): Promise<PaymentClaim> {
  const data = await http<any>(`/api/projects/claims/${id}/${action}/`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
  return mapPaymentClaimFromApi(data);
}

export async function verifyPaymentClaim(id: string, remarks?: string): Promise<PaymentClaim> {
  return reviewPaymentClaim(id, "verify", { remarks: remarks ?? "" });
}

export async function approvePaymentClaim(id: string, remarks?: string): Promise<PaymentClaim> {
  return reviewPaymentClaim(id, "approve", { remarks: remarks ?? "" });
}

export async function rejectPaymentClaim(id: string, remarks?: string): Promise<PaymentClaim> {
  return reviewPaymentClaim(id, "reject", { remarks: remarks ?? "" });
}

export async function payPaymentClaim(
  id: string,
  paymentReference?: string,
  notes?: string
): Promise<PaymentClaim> {
  return reviewPaymentClaim(id, "pay", {
    payment_reference: paymentReference ?? "",
    notes: notes ?? "",
  });
}

export async function fetchDisbursements(): Promise<Disbursement[]> {
  const data = await http<any>(`/api/projects/disbursements/`);
  return unwrapListResponse<any>(data).map(mapDisbursementFromApi);
}

export async function fetchAuditLogs(): Promise<AuditLog[]> {
  const data = await http<any>(`/api/projects/audit-logs/`);
  return unwrapListResponse<any>(data).map(mapAuditLogFromApi);
}

export async function loginUser(username: string, password: string): Promise<{ user: User; access: string; refresh: string }> {
  const normalizedUsername = (username || "").trim();

  if (DEMO_USERNAMES.has(normalizedUsername)) {
    try {
      await http<any>(`/api/users/auth/bootstrap-demo-users/`, {
        method: "POST",
        headers: { "X-Skip-Auth": "1" } as any,
        body: JSON.stringify({}),
      });
    } catch {
      // Ignore bootstrap failures and continue with normal login.
    }
  }

  let data: any;
  try {
    data = await http<any>(`/api/users/auth/token/`, {
      method: "POST",
      headers: { "X-Skip-Auth": "1" } as any,
      body: JSON.stringify({ username: normalizedUsername, password }),
    });
  } catch (err: any) {
    const raw = String(err?.message || "").toLowerCase();
    if (DEMO_USERNAMES.has(normalizedUsername) && raw.includes("no active account")) {
      await http<any>(`/api/users/auth/bootstrap-demo-users/`, {
        method: "POST",
        headers: { "X-Skip-Auth": "1" } as any,
        body: JSON.stringify({}),
      });
      data = await http<any>(`/api/users/auth/token/`, {
        method: "POST",
        headers: { "X-Skip-Auth": "1" } as any,
        body: JSON.stringify({ username: normalizedUsername, password }),
      });
    } else {
      throw err;
    }
  }

  const user = mapUserFromApi(data.user);
  if (typeof window !== "undefined") {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  return { user, access: data.access, refresh: data.refresh };
}

export function logoutUser() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export async function fetchCurrentUser(): Promise<User> {
  const data = await http<any>(`/api/users/auth/me/`);
  const user = mapUserFromApi(data);
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  return user;
}

export async function updateUserPassword(userId: string, newPassword: string): Promise<User> {
  const data = await http<any>(`/api/users/${userId}/`, {
    method: "PATCH",
    body: JSON.stringify({ password: newPassword }),
  });
  const user = mapUserFromApi(data);
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  return user;
}

export async function createOfficialAccount(payload: {
  username: string;
  fullName: string;
  email: string;
  gender: "Male" | "Female" | "Other";
  role: UserRole;
  region: string;
  mobileNumber: string;
  tierAssignment?: string;
  verificationZone?: string;
}): Promise<{ user: User; initialPassword?: string; emailError?: string }> {
  const data = await http<any>(`/api/users/`, {
    method: "POST",
    body: JSON.stringify({
      username: payload.username,
      full_name: payload.fullName,
      email: payload.email,
      gender: payload.gender,
      role: payload.role,
      region: payload.region,
      mobile_number: payload.mobileNumber,
      tier_assignment: payload.tierAssignment ?? "",
      verification_zone: payload.verificationZone ?? "",
    }),
  });
  return {
    user: mapUserFromApi(data),
    initialPassword: data?.initial_password ?? undefined,
    emailError: data?.email_error ?? undefined,
  };
}

export async function registerVendor(payload: {
  username: string;
  password: string;
  fullName: string;
  email: string;
  gender: "Male" | "Female" | "Other";
  mobileNumber: string;
  nationalId: string;
  address: string;
  organizationName: string;
  organizationType: string;
  technologyTypes: string[];
  registrationCertificateName: string;
  taxId: string;
  deviceId?: string;
  region?: string;
}): Promise<User> {
  const body = JSON.stringify({
    username: payload.username,
    password: payload.password,
    full_name: payload.fullName,
    email: payload.email,
    gender: payload.gender,
    mobile_number: payload.mobileNumber,
    national_id: payload.nationalId,
    address: payload.address,
    role: UserRole.VENDOR,
    organization_name: payload.organizationName,
    organization_type: payload.organizationType,
    technology_types: payload.technologyTypes,
    registration_certificate_name: payload.registrationCertificateName,
    tax_id: payload.taxId,
    device_id: payload.deviceId ?? "",
    region: payload.region ?? "",
    status: "Pending",
  });

  const data = await http<any>(`/api/users/`, {
    method: "POST",
    headers: { "X-Skip-Auth": "1" } as any,
    body,
  });
  return mapUserFromApi(data);
}

export async function requestRegistrationOtp(email: string): Promise<{ debugOtp?: string; emailError?: string }> {
  const data = await http<any>(`/api/users/auth/request-otp/`, {
    method: "POST",
    headers: { "X-Skip-Auth": "1" } as any,
    body: JSON.stringify({ email }),
  });
  return {
    debugOtp: data?.debug_otp ?? undefined,
    emailError: data?.email_error ?? undefined,
  };
}

export async function verifyRegistrationOtp(email: string, otp: string): Promise<void> {
  await http<any>(`/api/users/auth/verify-otp/`, {
    method: "POST",
    headers: { "X-Skip-Auth": "1" } as any,
    body: JSON.stringify({ email, otp }),
  });
}
