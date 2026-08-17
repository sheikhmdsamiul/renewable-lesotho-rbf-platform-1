import {
  Tender,
  Project,
  ProjectSetup,
  Notification,
  User,
  UserRole,
  Milestone,
  ProjectUpdate,
  ProjectDocument,
  InstallationReport,
  SmartMeterReading,
  VerificationTask,
  FieldVerificationRecord,
  VendorPrequalification,
  VendorPrequalificationSubmission,
  VendorBankDetails,
  VendorProfile,
  VendorDirectoryEntry,
  DisbursementSheet,
  PaymentClaim,
  PaymentClaimSubmission,
  Disbursement,
  AuditLog,
  AnomalyFlag,
  MapInstallationsResponse,
  MapInstallationRecord,
  TenderBid,
  TenderBidSite,
  BidStatus,
  TenderBidEvaluation,
  TenderContract,
  TenderAwardRankingRow,
  VendorBlacklistCase,
  BlacklistAppeal,
  ProjectKpiSummary,
  PortfolioKpiSummary,
  ProspectSyncLog,
  Organization,
  PlatformConfiguration,
  SystemHealthPayload,
  SuperAdminDashboardSummary,
  ReportTemplate,
  ReportHistoryItem,
  ReportFormat,
  Concern,
  ConcernResponse,
  AuditFinding,
  ConcernType,
  ConcernSeverity,
  ConcernStatus,
  FindingCategory,
  RiskLevel,
  Notice,
  NoticeCategory,
  NoticeStatus,
} from "./types";

const env = (import.meta as any)?.env ?? {};
const buildTimeApiBase = (env?.VITE_API_URL as string | undefined)?.replace(/\/$/, "");
let configuredApiBase = buildTimeApiBase;
let requestTimeoutMs = Number(env?.VITE_API_TIMEOUT_MS ?? 60000);
const isDevMode = Boolean(env?.DEV);
const ACCESS_TOKEN_KEY = "rbf_access_token";
const REFRESH_TOKEN_KEY = "rbf_refresh_token";
export const USER_KEY = "rbf_user";
export const SESSION_EXPIRED_KEY = "rbf_session_expired";
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

function getBrowserOrigin(): string {
  if (typeof window === "undefined") return "";
  return window.location.origin.replace(/\/$/, "");
}

export async function initRuntimeConfig(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    const res = await fetch("/config.json");
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.VITE_API_URL) {
      configuredApiBase = String(cfg.VITE_API_URL).replace(/\/$/, "");
    }
    if (cfg.VITE_API_TIMEOUT_MS) {
      requestTimeoutMs = Number(cfg.VITE_API_TIMEOUT_MS);
    }
    recomputeApiBase();
  } catch {
    // /config.json is optional; keep build-time defaults
  }
}

function getConfiguredApiOrigin(): string {
  if (!configuredApiBase || !/^https?:\/\//i.test(configuredApiBase)) return "";
  return stripApiSuffix(configuredApiBase);
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
  if (/^https?:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
        const preferredOrigin = getConfiguredApiOrigin() || getBrowserOrigin();
        if (!preferredOrigin) return raw;
        return `${preferredOrigin}${url.pathname}${url.search}${url.hash}`;
      }
    } catch {
      return raw;
    }
    return raw;
  }
  if (raw.startsWith('/')) {
    const apiOrigin = getConfiguredApiOrigin();
    if (apiOrigin) return `${apiOrigin}${raw}`;
    return raw;
  }
  const clean = raw.replace(/^\/+/, "");
  const mediaPath = clean.startsWith("media/") ? `/${clean}` : `/media/${clean}`;
  const apiOrigin = getConfiguredApiOrigin();
  if (apiOrigin) return `${apiOrigin}${mediaPath}`;
  return mediaPath;
}

function normalizeTechnologyType(raw?: string): string | undefined {
  const value = String(raw || "").trim();
  if (!value) return undefined;
  const key = value.toLowerCase();
  const mapping: Record<string, string> = {
    shs: "SHS",
    "solar home system": "SHS",
    ics: "ICS",
    "improved cookstove": "ICS",
    gmg: "GMG",
    "mini-grid": "GMG",
    "mini grid": "GMG",
    "solar mini-grid": "GMG",
    "solar mini grid": "GMG",
    swp: "SWP",
    "solar water pump": "SWP",
    pue: "PUE",
    "productive use": "PUE",
  };
  return mapping[key] || value.toUpperCase();
}

function flattenErrorValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value == null) return "";
  if (Array.isArray(value)) {
    for (const item of value) {
      const nested = flattenErrorValue(item);
      if (nested) return nested;
    }
    return "";
  }
  if (typeof value === "object") {
    const parts: string[] = [];
    for (const [key, sub] of Object.entries(value as Record<string, unknown>)) {
      const nested = flattenErrorValue(sub);
      if (nested) parts.push(`${key}: ${nested}`);
    }
    return parts.join("; ");
  }
  return "";
}

function extractApiErrorDetail(text: string): string {
  const trimmed = (text || "").trim();
  if (!trimmed) return "";

  try {
    const payload = JSON.parse(trimmed);
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.non_field_errors) && payload.non_field_errors.length) {
      return flattenErrorValue(payload.non_field_errors);
    }
    if (payload && typeof payload === "object") {
      const firstKey = Object.keys(payload)[0];
      if (firstKey) {
        const flattened = flattenErrorValue(payload[firstKey]);
        if (flattened) return `${firstKey}: ${flattened}`;
      }
    }
  } catch {
    // Not JSON; fall through to raw text.
  }

  return trimmed;
}

const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please log in again to continue.";

export const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
export const IDLE_WARNING_MS = 28 * 60 * 1000;
export const IDLE_EVENT_NAME = "rbf-idle-timeout";
export const IDLE_WARNING_EVENT_NAME = "rbf-idle-warning";

function dispatchSessionExpired(message: string) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("rbf-session-expired", { detail: { message } }));
  }
}

function dispatchIdleEvent(eventName: string) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(eventName));
  }
}

export function triggerIdleLogout(message?: string) {
  const finalMessage = message || "You were logged out due to inactivity. Please log in again to continue.";
  logoutUser(finalMessage);
  dispatchSessionExpired(finalMessage);
  dispatchIdleEvent(IDLE_EVENT_NAME);
}

function isSessionExpiredError(raw: string): boolean {
  const lower = raw.toLowerCase();
  return (
    lower.includes("token_not_valid") ||
    lower.includes("token is expired") ||
    lower.includes("given token not valid") ||
    (lower.includes("no active account") && lower.includes("401"))
  );
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
  const normalizedConfigured = getConfiguredApiOrigin();
  const bases: string[] = [""];

  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    if (normalizedConfigured) bases.push(normalizedConfigured);
    if (isDevMode && hostname) {
      if (hostname === "127.0.0.1" || hostname === "localhost") {
        bases.push(`${protocol}//${hostname}:8000`);
      } else {
        bases.push(`${protocol}//${hostname}:8000`, `http://${hostname}:8000`);
      }
      bases.push("http://127.0.0.1:8000", "http://localhost:8000");
    }
  } else {
    if (normalizedConfigured) bases.push(normalizedConfigured);
    if (isDevMode) bases.push("http://127.0.0.1:8000", "http://localhost:8000");
  }
  return uniq(bases);
}

let API_BASE_CANDIDATES = getApiBaseCandidates();
export let API_BASE: string =
  getConfiguredApiOrigin() ||
  getBrowserOrigin() ||
  API_BASE_CANDIDATES.find((base) => Boolean(base)) ||
  "";

function recomputeApiBase(): void {
  API_BASE_CANDIDATES = getApiBaseCandidates();
  API_BASE =
    getConfiguredApiOrigin() ||
    getBrowserOrigin() ||
    API_BASE_CANDIDATES.find((base) => Boolean(base)) ||
    "";
}

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
    targetDistricts: Array.isArray(api.target_districts) ? api.target_districts : undefined,
    targetSiteType: api.target_site_type ?? undefined,
    isVerified: api.is_verified ?? undefined,
    fundingSource: api.funding_source ?? undefined,
    minimumServiceTier: api.minimum_service_tier ?? undefined,
    approximateInstallationTarget: api.approximate_installation_target != null ? Number(api.approximate_installation_target) : undefined,
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
    disputeStartedAt: api.dispute_started_at ?? undefined,
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
    username: api.username ?? undefined,
    fullName: api.full_name ?? api.fullName ?? api.username ?? "",
    email: api.email ?? "",
    role: (api.role as UserRole) ?? UserRole.VENDOR,
    gender: api.gender === "Male" || api.gender === "Female" || api.gender === "Other" ? api.gender : "Other",
    region: api.region ?? undefined,
    district: api.district ?? api.verification_zone ?? api.region ?? undefined,
    districts: Array.isArray(api.districts) ? api.districts : [],
    mobileNumber: api.mobile_number ?? undefined,
    nationalId: api.national_id ?? undefined,
    address: api.address ?? undefined,
    organizationName: api.organization_name ?? undefined,
    organizationType: api.organization_type ?? undefined,
    associatedEntities: Array.isArray(api.associated_entities) ? api.associated_entities : undefined,
    technologyTypes: Array.isArray(api.technology_types) ? api.technology_types : undefined,
    registrationCertificateName: api.registration_certificate_name ?? undefined,
    taxId: api.tax_id ?? undefined,
    deviceId: api.device_id ?? undefined,
    tierAssignment: api.tier_assignment ?? undefined,
    verificationZone: api.verification_zone ?? undefined,
    status: api.status ?? "Active",
    isActive: api.is_active ?? undefined,
    mustChangePassword: api.must_change_password ?? false,
    roleLabel: api.role_label ?? undefined,
    lastLogin: api.last_login ?? undefined,
    recentAuditLogs: Array.isArray(api.recent_audit_logs)
      ? api.recent_audit_logs.map((log: any) => ({
          id: String(log.id ?? ""),
          action: log.action ?? "",
          module: log.module ?? undefined,
          recordId: log.record_id ?? undefined,
          recordType: log.record_type ?? undefined,
          createdAt: log.created_at ?? undefined,
        }))
      : undefined,
    prospectSyncStatus: Array.isArray(api.prospect_sync_status)
      ? api.prospect_sync_status.map(mapProspectSyncLogFromApi)
      : undefined,
    vendorTag: api.vendor_tag ?? undefined,
    blacklistSummary: api.blacklist_summary ?? undefined,
  };
}

function mapVendorProfileFromApi(api: any): VendorProfile {
  return {
    id: String(api.id ?? ""),
    username: api.username ?? "",
    email: api.email ?? "",
    full_name: api.full_name ?? "",
    gender: api.gender ?? "",
    role: api.role ?? "",
    mobile_number: api.mobile_number ?? "",
    national_id: api.national_id ?? undefined,
    address: api.address ?? undefined,
    organization_name: api.organization_name ?? undefined,
    organization_type: api.organization_type ?? undefined,
    technology_types: Array.isArray(api.technology_types) ? api.technology_types : [],
    registration_certificate_name: api.registration_certificate_name ?? undefined,
    tax_id: api.tax_id ?? undefined,
    bank_name: api.bank_name ?? undefined,
    bank_branch: api.bank_branch ?? undefined,
    bank_swift_code: api.bank_swift_code ?? undefined,
    bank_sort_code: api.bank_sort_code ?? undefined,
    bank_account_name: api.bank_account_name ?? undefined,
    bank_account_number: api.bank_account_number ?? undefined,
    tier_assignment: api.tier_assignment ?? undefined,
    verification_zone: api.verification_zone ?? undefined,
    region: api.region ?? undefined,
    status: api.status ?? "",
    date_joined: api.date_joined ?? "",
    last_login: api.last_login ?? undefined,
    prequalification: api.prequalification
      ? {
          status: api.prequalification.status ?? "",
          approved_at: api.prequalification.approved_at ?? undefined,
          submitted_at: api.prequalification.submitted_at ?? undefined,
          company_name: api.prequalification.company_name ?? undefined,
          organization_type: api.prequalification.organization_type ?? undefined,
          tax_id: api.prequalification.tax_id ?? undefined,
          hq_address: api.prequalification.hq_address ?? undefined,
          tech_tier: api.prequalification.tech_tier ?? undefined,
          technology_types: Array.isArray(api.prequalification.technology_types) ? api.prequalification.technology_types : [],
          female_beneficiary_target: Number(api.prequalification.female_beneficiary_target ?? 0),
          vulnerable_group_target: Number(api.prequalification.vulnerable_group_target ?? 0),
          years_experience: Number(api.prequalification.years_experience ?? 0),
          prior_projects: Number(api.prequalification.prior_projects ?? 0),
          annual_revenue: api.prequalification.annual_revenue != null ? Number(api.prequalification.annual_revenue) : undefined,
          districts_covered: Number(api.prequalification.districts_covered ?? 0),
          contact_number: api.prequalification.contact_number ?? undefined,
          email: api.prequalification.email ?? undefined,
          gender_of_focal_person: api.prequalification.gender_of_focal_person ?? undefined,
          bank_name: api.prequalification.bank_name ?? undefined,
          bank_branch: api.prequalification.bank_branch ?? undefined,
          bank_swift_code: api.prequalification.bank_swift_code ?? undefined,
          bank_sort_code: api.prequalification.bank_sort_code ?? undefined,
          bank_account_name: api.prequalification.bank_account_name ?? undefined,
          bank_account_number: api.prequalification.bank_account_number ?? undefined,
          trading_license: normalizeFileUrl(api.prequalification.trading_license ?? undefined),
          registration_certificate: normalizeFileUrl(api.prequalification.registration_certificate ?? undefined),
          tax_compliance_certificate: normalizeFileUrl(api.prequalification.tax_compliance_certificate ?? undefined),
          authorized_signatory_id: normalizeFileUrl(api.prequalification.authorized_signatory_id ?? undefined),
          experience_financial_proof: normalizeFileUrl(api.prequalification.experience_financial_proof ?? undefined),
        }
      : undefined,
    blacklist_status: {
      status: api.blacklist_status?.status ?? "Clear",
      reason: api.blacklist_status?.reason ?? undefined,
      description: api.blacklist_status?.description ?? undefined,
      expiry_date: api.blacklist_status?.expiry_date ?? undefined,
      is_permanent: api.blacklist_status?.is_permanent ?? undefined,
      initiated_at: api.blacklist_status?.initiated_at ?? undefined,
      reviewed_at: api.blacklist_status?.reviewed_at ?? undefined,
      confirmed_at: api.blacklist_status?.confirmed_at ?? undefined,
      reinstated_at: api.blacklist_status?.reinstated_at ?? undefined,
    },
    bid_count: Number(api.bid_count ?? 0),
    project_count: Number(api.project_count ?? 0),
    total_contract_value: Number(api.total_contract_value ?? 0),
    documents: api.documents
      ? {
          prequalification_documents: Array.isArray(api.documents.prequalification_documents)
            ? api.documents.prequalification_documents.map((doc: any) => ({
                label: doc.label ?? "",
                category: doc.category ?? "",
                url: normalizeFileUrl(doc.url ?? "") ?? "",
                uploaded_at: doc.uploaded_at ?? undefined,
              }))
            : [],
          project_documents: Array.isArray(api.documents.project_documents)
            ? api.documents.project_documents.map((doc: any) => ({
                id: String(doc.id ?? ""),
                project_id: String(doc.project_id ?? ""),
                project_reference: doc.project_reference ?? undefined,
                title: doc.title ?? "",
                url: normalizeFileUrl(doc.url ?? "") ?? "",
                uploaded_at: doc.uploaded_at ?? undefined,
                uploaded_by: doc.uploaded_by ?? undefined,
              }))
            : [],
          contract_documents: Array.isArray(api.documents.contract_documents)
            ? api.documents.contract_documents.map((doc: any) => ({
                contract_id: String(doc.contract_id ?? ""),
                reference_number: doc.reference_number ?? undefined,
                title: doc.title ?? "",
                url: normalizeFileUrl(doc.url ?? "") ?? "",
                uploaded_at: doc.uploaded_at ?? undefined,
              }))
            : [],
        }
      : undefined,
    bids_data: api.bids_data
      ? {
          summary: {
            total_bids: Number(api.bids_data.summary?.total_bids ?? 0),
            awarded: Number(api.bids_data.summary?.awarded ?? 0),
            accepted: Number(api.bids_data.summary?.accepted ?? 0),
            rejected: Number(api.bids_data.summary?.rejected ?? 0),
            pending: Number(api.bids_data.summary?.pending ?? 0),
            win_rate_pct: Number(api.bids_data.summary?.win_rate_pct ?? 0),
          },
          bids: Array.isArray(api.bids_data.bids) ? api.bids_data.bids.map(mapTenderBidFromApi) : [],
          evaluations: Array.isArray(api.bids_data.evaluations) ? api.bids_data.evaluations.map(mapBidEvaluationFromApi) : [],
          contracts: Array.isArray(api.bids_data.contracts) ? api.bids_data.contracts.map(mapTenderContractFromApi) : [],
        }
      : null,
    projects_data: api.projects_data
      ? {
          projects: Array.isArray(api.projects_data.projects) ? api.projects_data.projects.map(mapProjectFromApi) : [],
          recent_updates: Array.isArray(api.projects_data.recent_updates) ? api.projects_data.recent_updates : [],
          recent_documents: Array.isArray(api.projects_data.recent_documents)
            ? api.projects_data.recent_documents.map((doc: any) => ({
                id: String(doc.id ?? ""),
                project_id: String(doc.project_id ?? ""),
                project_reference: doc.project_reference ?? undefined,
                title: doc.title ?? "",
                url: normalizeFileUrl(doc.url ?? "") ?? "",
                uploaded_at: doc.uploaded_at ?? undefined,
              }))
            : [],
        }
      : undefined,
    performance_data: api.performance_data
      ? {
          kpi_rows: Array.isArray(api.performance_data.kpi_rows) ? api.performance_data.kpi_rows : [],
          installation_summary: {
            submitted: Number(api.performance_data.installation_summary?.submitted ?? 0),
            verified: Number(api.performance_data.installation_summary?.verified ?? 0),
            flagged: Number(api.performance_data.installation_summary?.flagged ?? 0),
            paused: Number(api.performance_data.installation_summary?.paused ?? 0),
            terminated: Number(api.performance_data.installation_summary?.terminated ?? 0),
            verification_rate_pct: Number(api.performance_data.installation_summary?.verification_rate_pct ?? 0),
          },
          anomaly_summary: {
            total: Number(api.performance_data.anomaly_summary?.total ?? 0),
            resolved: Number(api.performance_data.anomaly_summary?.resolved ?? 0),
            unresolved: Number(api.performance_data.anomaly_summary?.unresolved ?? 0),
            by_type: Array.isArray(api.performance_data.anomaly_summary?.by_type) ? api.performance_data.anomaly_summary.by_type : [],
          },
          meter_summary: {
            average_uptime_pct: Number(api.performance_data.meter_summary?.average_uptime_pct ?? 0),
            total_energy_kwh: Number(api.performance_data.meter_summary?.total_energy_kwh ?? 0),
            target_energy_kwh: Number(api.performance_data.meter_summary?.target_energy_kwh ?? 0),
            reading_count: Number(api.performance_data.meter_summary?.reading_count ?? 0),
          },
          performance_notes: Array.isArray(api.performance_data.performance_notes) ? api.performance_data.performance_notes : [],
        }
      : undefined,
    payments_data: api.payments_data
      ? {
          summary: {
            total_contracted_value: Number(api.payments_data.summary?.total_contracted_value ?? 0),
            total_disbursed: Number(api.payments_data.summary?.total_disbursed ?? 0),
            total_pending: Number(api.payments_data.summary?.total_pending ?? 0),
          },
          claims: Array.isArray(api.payments_data.claims) ? api.payments_data.claims.map(mapPaymentClaimFromApi) : [],
        }
      : null,
    audit_trail: api.audit_trail
      ? {
          limited: Boolean(api.audit_trail.limited),
          entries: Array.isArray(api.audit_trail.entries) ? api.audit_trail.entries.map(mapAuditLogFromApi) : [],
        }
      : null,
    prospect_sync_logs: Array.isArray(api.prospect_sync_logs) ? api.prospect_sync_logs.map(mapProspectSyncLogFromApi) : [],
  };
}

function mapVendorDirectoryEntryFromApi(api: any): VendorDirectoryEntry {
  return {
    id: String(api.id ?? ""),
    username: api.username ?? "",
    fullName: api.full_name ?? api.username ?? "",
    email: api.email ?? "",
    organizationName: api.organization_name ?? undefined,
    organizationType: api.organization_type ?? undefined,
    technologyTypes: Array.isArray(api.technology_types) ? api.technology_types : [],
    region: api.region ?? undefined,
    status: api.status ?? "",
    vendorTag: api.vendor_tag ?? undefined,
    lastLogin: api.last_login ?? undefined,
    prequalificationStatus: api.prequalification_status ?? undefined,
    prequalificationApprovedAt: api.prequalification_approved_at ?? undefined,
    blacklistStatus: api.blacklist_status ?? undefined,
    operationalStanding: api.operational_standing ?? "Active",
    projectCount: Number(api.project_count ?? 0),
    bidCount: Number(api.bid_count ?? 0),
    hasPendingPasswordReset: api.has_pending_password_reset ?? false,
  };
}

function mapOrganizationFromApi(api: any): Organization {
  return {
    id: String(api.id ?? ""),
    name: api.name ?? "",
    type: api.type ?? "Government",
    contactPerson: api.contact_person ?? undefined,
    email: api.email ?? undefined,
    phone: api.phone ?? undefined,
    address: api.address ?? undefined,
    createdAt: api.created_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
  };
}

function mapPlatformConfigurationFromApi(api: any): PlatformConfiguration {
  return {
    id: api.id != null ? String(api.id) : undefined,
    nationalMainProgramBudget: Number(api.national_main_program_budget ?? 0),
    femaleTargetMinimum: Number(api.female_target_minimum ?? 0),
    vulnerableTargetMinimum: Number(api.vulnerable_target_minimum ?? 0),
    lowIncomeTargetMinimum: Number(api.low_income_target_minimum ?? 0),
    uptimeTarget: Number(api.uptime_target ?? 0),
    anomalyDeviationThreshold: Number(api.anomaly_deviation_threshold ?? 0),
    gpsDuplicateRadiusM: Number(api.gps_duplicate_radius_m ?? 0),
    gpsVerificationMaxDistanceM: Number(api.gps_verification_max_distance_m ?? 0),
    m2VerificationRequiredPct: Number(api.m2_verification_required_pct ?? 0),
    m3VerificationRequiredPct: Number(api.m3_verification_required_pct ?? 0),
    emailNotificationsEnabled: Boolean(api.email_notifications_enabled),
    smsNotificationsEnabled: Boolean(api.sms_notifications_enabled),
    emailHost: api.email_host ?? "",
    emailPort: Number(api.email_port ?? 587),
    emailUseTls: Boolean(api.email_use_tls),
    emailHostUser: api.email_host_user ?? "",
    emailHostPassword: "",
    emailHostPasswordSet: Boolean(api.email_host_password_set),
    defaultFromEmail: api.default_from_email ?? "",
    maxFileSizeMb: Number(api.max_file_size_mb ?? 0),
    allowedFileTypes: Array.isArray(api.allowed_file_types) ? api.allowed_file_types : [],
    lesothoBoundary: api.lesotho_boundary
      ? {
          path: api.lesotho_boundary.path ?? "",
          exists: Boolean(api.lesotho_boundary.exists),
          lastModified: api.lesotho_boundary.last_modified ?? undefined,
        }
      : undefined,
  };
}

function mapSystemHealthFromApi(api: any): SystemHealthPayload {
  return {
    database: {
      status: api.database?.status ?? "",
      error: api.database?.error ?? undefined,
      slowQueriesLast24h: Number(api.database?.slow_queries_last_24h ?? 0),
      tableSizes: api.database?.table_sizes ?? {},
    },
    queue: {
      workerStatus: api.queue?.worker_status ?? "",
      pendingJobsCount: Number(api.queue?.pending_jobs_count ?? 0),
      failedJobsCount: Number(api.queue?.failed_jobs_count ?? 0),
      processingRateLast24h: Number(api.queue?.processing_rate_last_24h ?? 0),
    },
    scheduler: {
      status: api.scheduler?.status ?? "",
      lastMonthlyReportSync: api.scheduler?.last_monthly_report_sync ?? undefined,
    },
    prospectApi: {
      status: api.prospect_api?.status ?? "",
    },
    storage: {
      totalBytes: Number(api.storage?.total_bytes ?? 0),
      usedBytes: Number(api.storage?.used_bytes ?? 0),
      freeBytes: Number(api.storage?.free_bytes ?? 0),
      filesUploadedToday: Number(api.storage?.files_uploaded_today ?? 0),
    },
    errors: Array.isArray(api.errors)
      ? api.errors.map((item: any) => ({
          id: String(item.id ?? ""),
          methodName: item.method_name ?? "",
          errorMessage: item.error_message ?? undefined,
          updatedAt: item.updated_at ?? undefined,
        }))
      : [],
  };
}

function mapSuperAdminDashboardSummaryFromApi(api: any): SuperAdminDashboardSummary {
  return {
    stats: {
      totalUsers: Number(api.stats?.total_users ?? 0),
      activeProjects: Number(api.stats?.active_projects ?? 0),
      totalVendors: Number(api.stats?.total_vendors ?? 0),
      pendingPrequalifications: Number(api.stats?.pending_prequalifications ?? 0),
    },
    systemHealth: mapSystemHealthFromApi(api.system_health ?? {}),
    recentActivity: Array.isArray(api.recent_activity)
      ? api.recent_activity.map((item: any) => ({
          id: String(item.id ?? ""),
          timestamp: item.timestamp ?? undefined,
          actor: item.actor ?? "System",
          role: item.role ?? undefined,
          action: item.action ?? "",
          module: item.module ?? undefined,
          record: item.record != null ? String(item.record) : undefined,
          notes: item.notes ?? undefined,
          oldStatus: item.old_status ?? undefined,
          newStatus: item.new_status ?? undefined,
        }))
      : [],
    prospectSyncSummary: {
      failedJobs: Number(api.prospect_sync_summary?.failed_jobs ?? 0),
      lastSyncAt: api.prospect_sync_summary?.last_sync_at ?? undefined,
    },
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
    deadline: ui.deadline && ui.deadline !== "" ? ui.deadline : null,
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
    last_date_security: ui.lastDateSecurity && ui.lastDateSecurity !== "" ? ui.lastDateSecurity : null,
    last_date_submission: ui.lastDateSubmission && ui.lastDateSubmission !== "" ? ui.lastDateSubmission : null,
    date_opening: ui.dateOpening && ui.dateOpening !== "" ? ui.dateOpening : null,
    pre_tender_meeting_info: ui.preTenderMeetingInfo ?? "",
    bidders_schedule_purchase: ui.biddersSchedulePurchase ?? false,
    tender_security_required: ui.tenderSecurityRequired ?? false,
    contact_details: ui.contactDetails ?? "",
    technology_types: ui.technologyTypes ?? [],
    target_districts: ui.targetDistricts ?? [],
    target_site_type: ui.targetSiteType ?? null,
    is_verified: ui.isVerified ?? false,
    funding_source: ui.fundingSource ?? null,
    minimum_service_tier: ui.minimumServiceTier ?? null,
    approximate_installation_target: ui.approximateInstallationTarget ?? null,
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
    if ((k === 'technology_types' || k === 'target_districts') && Array.isArray(v)) {
      // JSONField expects JSON-encoded string
      form.append(k, JSON.stringify(v));
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
    targetLowIncomePct: api.target_low_income_pct != null ? Number(api.target_low_income_pct) : undefined,
    targetBeneficiaries: api.target_beneficiaries != null ? Number(api.target_beneficiaries) : undefined,
    projectDurationMonths: api.project_duration_months != null ? Number(api.project_duration_months) : undefined,
    verificationMethod: api.verification_method ?? undefined,
    deploymentTeamRoster: api.deployment_team_roster ?? "",
    deploymentEquipmentPlan: api.deployment_equipment_plan ?? "",
    deploymentSiteStatus: api.deployment_site_status ?? "",
    deploymentWorkSchedule: api.deployment_work_schedule ?? "",
    deploymentPermitsStatus: api.deployment_permits_status ?? "",
    deviceBrand: api.device_brand ?? "",
    deviceModel: api.device_model ?? "",
    deviceTechTier: api.device_tech_tier ?? "",
    verificationMethodConfirmed: Boolean(api.verification_method_confirmed),
    setupCompletedAt: api.setup_completed_at ?? undefined,
    projectSetup: mapProjectSetupFromApi(api.project_setup),
    claimCount: api.claim_count != null ? Number(api.claim_count) : undefined,
    unresolvedFlagCount: api.unresolved_flag_count != null ? Number(api.unresolved_flag_count) : undefined,
    latestAuditEntry: api.latest_audit_entry ? mapAuditLogFromApi(api.latest_audit_entry) : undefined,
    contractValue: api.contract_value != null ? Number(api.contract_value) : undefined,
    energyOutput: Number(api.energy_output ?? 0),
    uptime: Number(api.uptime ?? 0),
    genderImpact: Number(api.gender_impact ?? 0),
  };
}

function mapProjectSetupFromApi(api: any): ProjectSetup | undefined {
  if (!api || typeof api !== "object") return undefined;
  return {
    id: api.id != null ? String(api.id) : undefined,
    projectId: api.project != null ? String(api.project) : undefined,
    vendorId: api.vendor != null ? String(api.vendor) : undefined,
    teamRosterFile: normalizeFileUrl(api.team_roster_file ?? undefined),
    teamRosterFileUrl: normalizeFileUrl(api.team_roster_file_url ?? undefined),
    equipmentPlanFile: normalizeFileUrl(api.equipment_plan_file ?? undefined),
    equipmentPlanFileUrl: normalizeFileUrl(api.equipment_plan_file_url ?? undefined),
    siteStatus: api.site_status ?? undefined,
    workScheduleStart: api.work_schedule_start ?? undefined,
    workScheduleEnd: api.work_schedule_end ?? undefined,
    complianceDocsFile: normalizeFileUrl(api.compliance_docs_file ?? undefined),
    complianceDocsFileUrl: normalizeFileUrl(api.compliance_docs_file_url ?? undefined),
    insuranceCertificateFile: normalizeFileUrl(api.insurance_certificate_file ?? undefined),
    insuranceCertificateFileUrl: normalizeFileUrl(api.insurance_certificate_file_url ?? undefined),
    deviceModel: api.device_model ?? undefined,
    deviceBrand: api.device_brand ?? undefined,
    techTier: api.tech_tier != null ? Number(api.tech_tier) : undefined,
    meterApiEndpoint: api.meter_api_endpoint ?? undefined,
    hasMeterApiToken: Boolean(api.has_meter_api_token),
    manualVerificationConfirmed: Boolean(api.manual_verification_confirmed),
    checklistTeamReady: Boolean(api.checklist_team_ready),
    checklistEquipmentReady: Boolean(api.checklist_equipment_ready),
    checklistSiteReady: Boolean(api.checklist_site_ready),
    checklistSafetyReady: Boolean(api.checklist_safety_ready),
    checklistLogisticsReady: Boolean(api.checklist_logistics_ready),
    setupCompletedAt: api.setup_completed_at ?? undefined,
    createdAt: api.created_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
  };
}

function mapMilestoneFromApi(api: any): Milestone {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    milestoneNumber: api.milestone_number != null ? Number(api.milestone_number) : undefined,
    disbursementPct: api.disbursement_pct != null ? Number(api.disbursement_pct) : undefined,
    name: api.name ?? "",
    description: api.description ?? undefined,
    percentage: Number(api.percentage ?? 0),
    status: api.status ?? "Submitted",
    amount: Number(api.amount ?? 0),
    amountLsl: api.amount_lsl != null ? Number(api.amount_lsl) : undefined,
    progressPercentage: Number(api.progress_percentage ?? 0),
    targetDate: api.target_date ?? undefined,
    completedDate: api.completed_date ?? undefined,
    unlockedAt: api.unlocked_at ?? undefined,
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
    beneficiaryName: api.beneficiary_name ?? undefined,
    householdType: api.household_type ?? undefined,
    installationDate: api.installation_date ?? undefined,
    verificationStatus: api.verification_status ?? undefined,
    verifiedBy: api.verified_by_username ?? api.verified_by ?? undefined,
    gisStatus: api.gis_status ?? undefined,
  };
}

function mapMapInstallationFromApi(api: any): MapInstallationRecord {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project_id ?? ""),
    latitude: Number(api.latitude ?? 0),
    longitude: Number(api.longitude ?? 0),
    gisStatus: api.gis_status ?? "yellow",
    verificationStatus: api.verification_status ?? "Pending",
    technologyType: api.technology_type ?? "",
    householdType: api.household_type ?? undefined,
    vendorName: api.vendor_name ?? "",
    beneficiaryName: api.beneficiary_name ?? "",
    serialNumber: api.serial_number ?? undefined,
    district: api.district ?? "",
    installationDate: api.installation_date ?? undefined,
    uptimePct: api.uptime_pct != null ? Number(api.uptime_pct) : undefined,
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
    concernMessage: api.concern_message ?? undefined,
    fieldVerification: api.field_verification ? mapFieldVerificationFromApi(api.field_verification) : undefined,
  };
}

function mapFieldVerificationFromApi(api: any): FieldVerificationRecord {
  return {
    id: String(api.id ?? ""),
    fieldOfficerUsername: api.field_officer_username ?? undefined,
    beneficiaryPresent: Boolean(api.beneficiary_present),
    beneficiaryGender: api.beneficiary_gender ?? "unknown",
    systemWorking: Boolean(api.system_working),
    officerLatitude: Number(api.officer_latitude ?? 0),
    officerLongitude: Number(api.officer_longitude ?? 0),
    locationMatch: Boolean(api.location_match),
    locationDistanceMeters: Number(api.location_distance_meters ?? 0),
    sitePhotos: Array.isArray(api.site_photos) ? api.site_photos.map((path: string) => normalizeFileUrl(path)).filter(Boolean) : [],
    serialVisible: Boolean(api.serial_visible),
    observationNotes: api.observation_notes ?? "",
    verificationStatus: api.verification_status ?? "",
    flagReason: api.flag_reason ?? undefined,
    verifiedAt: api.verified_at ?? "",
  };
}

function mapBidEvaluationFromApi(api: any): TenderBidEvaluation {
  return {
    id: String(api.id ?? ""),
    bid: String(api.bid ?? ""),
    evaluator: api.evaluator != null ? String(api.evaluator) : undefined,
    evaluatorUsername: api.evaluator_username ?? undefined,
    evaluatorRole: api.evaluator_role ?? undefined,
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
    signatureStatus: api.signature_status ?? undefined,
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
    villageSubDistrict: api.village_sub_district ?? undefined,
    latitude: api.latitude != null ? Number(api.latitude) : undefined,
    longitude: api.longitude != null ? Number(api.longitude) : undefined,
    estimatedHouseholds: api.estimated_households != null ? Number(api.estimated_households) : (api.number_of_households != null ? Number(api.number_of_households) : undefined),
    numberOfHouseholds: api.number_of_households != null ? Number(api.number_of_households) : undefined,
    targetTechnology: api.target_technology ?? undefined,
    targetBeneficiaryType: api.target_beneficiary_type ?? undefined,
    estimatedEnergyDemandKwhMonth: api.estimated_energy_demand_kwh_month != null ? Number(api.estimated_energy_demand_kwh_month) : undefined,
    roadAccessAvailable: api.road_access_available != null ? Boolean(api.road_access_available) : undefined,
    notes: api.notes ?? undefined,
  };
}

function mapTenderBidSiteToApi(site: Partial<TenderBidSite> | Record<string, any>): Record<string, any> {
  const rawSite = site as any;
  const estimatedHouseholds = rawSite.estimatedHouseholds ?? rawSite.estimated_households ?? rawSite.numberOfHouseholds ?? rawSite.number_of_households;
  return {
    site_name: rawSite.siteName ?? rawSite.site_name ?? "",
    district: rawSite.district ?? "",
    village_sub_district: rawSite.villageSubDistrict ?? rawSite.village_sub_district ?? "",
    latitude: rawSite.latitude ?? undefined,
    longitude: rawSite.longitude ?? undefined,
    estimated_households: estimatedHouseholds ?? undefined,
    number_of_households: estimatedHouseholds ?? undefined,
    target_technology: rawSite.targetTechnology ?? rawSite.target_technology ?? undefined,
    target_beneficiary_type: rawSite.targetBeneficiaryType ?? rawSite.target_beneficiary_type ?? undefined,
    estimated_energy_demand_kwh_month:
      rawSite.estimatedEnergyDemandKwhMonth ?? rawSite.estimated_energy_demand_kwh_month ?? undefined,
    road_access_available: rawSite.roadAccessAvailable ?? rawSite.road_access_available ?? false,
    notes: rawSite.notes ?? "",
  };
}

function mapTenderBidFromApi(api: any): TenderBid {
  return {
    id: String(api.id ?? ""),
    tender: String(api.tender ?? ""),
    tender_reference: api.tender_reference ?? undefined,
    tender_name: api.tender_name ?? undefined,
    tender_status: api.tender_status ?? undefined,
    tender_intent_to_award_at: api.tender_intent_to_award_at ?? undefined,
    tender_intent_to_award_bid_id: api.tender_intent_to_award_bid_id != null ? String(api.tender_intent_to_award_bid_id) : undefined,
    tender_awarded_at: api.tender_awarded_at ?? undefined,
    tender_awarded_vendor_id: api.tender_awarded_vendor_id != null ? String(api.tender_awarded_vendor_id) : undefined,
    tender_awarded_vendor_name: api.tender_awarded_vendor_name ?? undefined,
    vendor_id: api.vendor_id ?? "",
    vendor_name: api.vendor_name ?? "",
    vendor_email: api.vendor_email ?? undefined,
    bid_amount: api.bid_amount != null ? Number(api.bid_amount) : undefined,
    subsidy_requested: api.subsidy_requested != null ? Number(api.subsidy_requested) : undefined,
    stage: api.stage ?? undefined,
    stage_key: api.stage_key ?? undefined,
    stage_badge: api.stage_badge ?? undefined,
    technology_type: api.technology_type ?? undefined,
    tender_technology_types: Array.isArray(api.tender_technology_types) ? api.tender_technology_types : undefined,
    device_brand: api.device_brand ?? undefined,
    device_model: api.device_model ?? undefined,
    co_financing_amount: api.co_financing_amount != null ? Number(api.co_financing_amount) : undefined,
    concept_note: api.concept_note ?? undefined,
    technical_proposal: api.technical_proposal ?? undefined,
    financial_proposal: api.financial_proposal ?? undefined,
    device_brand_model: api.device_brand_model ?? undefined,
    tech_tier: api.tech_tier ?? undefined,
    energy_target_kwh_month: api.energy_target_kwh_month != null ? Number(api.energy_target_kwh_month) : undefined,
    energy_target: api.energy_target != null ? Number(api.energy_target) : undefined,
    system_configuration: api.system_configuration ?? undefined,
    boq_details: Array.isArray(api.boq_details) ? api.boq_details : [],
    boq_items: Array.isArray(api.boq_items) ? api.boq_items : [],
    technical_proposal_file: normalizeFileUrl(api.technical_proposal_file ?? undefined),
    financial_proposal_file: normalizeFileUrl(api.financial_proposal_file ?? undefined),
    boq_file: normalizeFileUrl(api.boq_file ?? undefined),
    gender_action_plan_file: normalizeFileUrl(api.gender_action_plan_file ?? undefined),
    implementation_plan_file: normalizeFileUrl(api.implementation_plan_file ?? undefined),
    om_plan_file: normalizeFileUrl(api.om_plan_file ?? undefined),
    om_plan_document: normalizeFileUrl(api.om_plan_document ?? api.om_plan_file ?? undefined),
    reporting_templates_file: normalizeFileUrl(api.reporting_templates_file ?? undefined),
    distribution_map_file: normalizeFileUrl(api.distribution_map_file ?? undefined),
    tender_security_file: normalizeFileUrl(api.tender_security_file ?? undefined),
    female_target_pct: api.female_target_pct != null ? Number(api.female_target_pct) : undefined,
    gender_inclusion_target: api.gender_inclusion_target != null ? Number(api.gender_inclusion_target) : undefined,
    vulnerable_target_pct: api.vulnerable_target_pct != null ? Number(api.vulnerable_target_pct) : undefined,
    vulnerable_group_target: api.vulnerable_group_target != null ? Number(api.vulnerable_group_target) : undefined,
    low_income_target_pct: api.low_income_target_pct != null ? Number(api.low_income_target_pct) : undefined,
    low_income_target: api.low_income_target != null ? Number(api.low_income_target) : undefined,
    inclusion_commitment_confirmed: api.inclusion_commitment_confirmed != null ? Boolean(api.inclusion_commitment_confirmed) : undefined,
    om_strategy_summary: api.om_strategy_summary ?? undefined,
    local_technicians_to_be_trained: api.local_technicians_to_be_trained != null ? Number(api.local_technicians_to_be_trained) : undefined,
    warranty_period_months: api.warranty_period_months != null ? Number(api.warranty_period_months) : undefined,
    warranty_period: api.warranty_period != null ? Number(api.warranty_period) : undefined,
    offer_paygo: api.offer_paygo != null ? Boolean(api.offer_paygo) : undefined,
    paygo_platform: api.paygo_platform ?? undefined,
    daily_payment_amount_lsl: api.daily_payment_amount_lsl != null ? Number(api.daily_payment_amount_lsl) : undefined,
    collection_method: api.collection_method ?? undefined,
    preferred_district: api.preferred_district ?? undefined,
    technical_summary: api.technical_summary ?? api.technical_proposal ?? undefined,
    financial_summary: api.financial_summary ?? api.financial_proposal ?? undefined,
    aftersales_description: api.aftersales_description ?? undefined,
    service_tier: api.service_tier ?? api.tech_tier ?? undefined,
    stage_two_unlocked: Boolean(api.stage_two_unlocked),
    stage_two_unlocked_at: api.stage_two_unlocked_at ?? undefined,
    stage_two_source_bid: api.stage_two_source_bid != null ? String(api.stage_two_source_bid) : undefined,
    stage_two_ready: api.stage_two_ready != null ? Boolean(api.stage_two_ready) : undefined,
    document_requirements: Array.isArray(api.document_requirements) ? api.document_requirements : [],
    document_counts: api.document_counts ?? undefined,
    deadline: api.deadline ?? undefined,
    deadline_passed: api.deadline_passed != null ? Boolean(api.deadline_passed) : undefined,
    deadline_countdown_seconds: api.deadline_countdown_seconds != null ? Number(api.deadline_countdown_seconds) : undefined,
    is_locked: api.is_locked != null ? Boolean(api.is_locked) : undefined,
    evaluation_status: api.evaluation_status ?? undefined,
    technical_score_total: api.technical_score_total != null ? Number(api.technical_score_total) : undefined,
    financial_score_total: api.financial_score_total != null ? Number(api.financial_score_total) : undefined,
    version_history: Array.isArray(api.version_history) ? api.version_history.map((item: any) => ({
      id: String(item.id ?? ""),
      version_number: Number(item.version_number ?? 0),
      status: (item.status as BidStatus) ?? BidStatus.DRAFT,
      updated_at: item.updated_at ?? undefined,
      submitted_at: item.submitted_at ?? undefined,
    })) : [],
    status: (api.status as BidStatus) ?? BidStatus.DRAFT,
    version_number: Number(api.version_number ?? 0),
    submitted_at: api.submitted_at ?? undefined,
    reviewed_at: api.reviewed_at ?? undefined,
    reviewed_by: api.reviewed_by ?? undefined,
    rejection_reason: api.rejection_reason ?? undefined,
    created_at: api.created_at ?? undefined,
    updated_at: api.updated_at ?? undefined,
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
    bankName: api.bank_name ?? undefined,
    bankBranch: api.bank_branch ?? undefined,
    bankSwiftCode: api.bank_swift_code ?? undefined,
    bankSortCode: api.bank_sort_code ?? undefined,
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
    milestone_details: api.milestone_details ? mapMilestoneFromApi(api.milestone_details) : undefined,
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
    vendorLegalName: api.vendor_legal_name ?? undefined,
    vendorBankName: api.vendor_bank_name ?? undefined,
    vendorBankBranch: api.vendor_bank_branch ?? undefined,
    vendorBankSwiftCode: api.vendor_bank_swift_code ?? undefined,
    vendorBankSortCode: api.vendor_bank_sort_code ?? undefined,
    vendorAccountHolderName: api.vendor_account_holder_name ?? undefined,
    vendorAccountNumber: api.vendor_account_number ?? undefined,
    disbursement: api.disbursement ? mapDisbursementFromApi(api.disbursement) : undefined,
    paymentLocked: Boolean(api.payment_locked),
    paymentLockReason: api.payment_lock_reason ?? undefined,
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
    notes: api.notes ?? undefined,
    recordId: api.record_id != null ? String(api.record_id) : undefined,
    recordType: api.record_type ?? undefined,
    actorRole: api.actor_role ?? undefined,
    module: api.module ?? undefined,
    oldStatus: api.old_status ?? undefined,
    newStatus: api.new_status ?? undefined,
  };
}

function mapSmartMeterReadingFromApi(api: any): SmartMeterReading {
  return {
    id: String(api.id ?? ""),
    projectId: String(api.project ?? ""),
    installationId: api.installation != null ? String(api.installation) : undefined,
    meterId: api.meter_id ?? "",
    kwh: Number(api.kwh ?? 0),
    uptimePct: api.uptime_pct != null ? Number(api.uptime_pct) : undefined,
    recordedAt: api.recorded_at ?? "",
    createdAt: api.created_at ?? "",
  };
}

function mapAnomalyFlagFromApi(api: any): AnomalyFlag {
  return {
    id: String(api.id ?? ""),
    installation: String(api.installation ?? ""),
    project: String(api.project ?? ""),
    flagType: api.flag_type ?? "",
    description: api.description ?? undefined,
    isResolved: Boolean(api.is_resolved),
    createdAt: api.created_at ?? "",
    resolvedAt: api.resolved_at ?? undefined,
  };
}

function mapProspectSyncLogFromApi(api: any): ProspectSyncLog {
  return {
    id: String(api.id ?? ""),
    methodName: api.method_name ?? "",
    status: api.status ?? "",
    attempts: Number(api.attempts ?? 0),
    payload: api.payload ?? undefined,
    errorMessage: api.error_message ?? undefined,
    createdAt: api.created_at ?? undefined,
    updatedAt: api.updated_at ?? undefined,
    recordId: api.record_id != null ? String(api.record_id) : undefined,
    recordType: api.record_type ?? undefined,
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
        (statusError as any).status = res.status;
        try {
          const parsed = JSON.parse((text || "").trim());
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            (statusError as any).detailPayload = parsed;
          }
        } catch {
          // Non-JSON error body; only the message is available.
        }
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
          if (isSessionExpiredError(detail || text || "")) {
            dispatchSessionExpired(SESSION_EXPIRED_MESSAGE);
            const expiredError = new Error(SESSION_EXPIRED_MESSAGE);
            (expiredError as any).status = 401;
            (expiredError as any).isSessionExpired = true;
            throw expiredError;
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
      if (error?.isSessionExpired) {
        throw error;
      }
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
      (lastError as any).isNetworkError = true;

      if (isLastAttempt) {
        throw lastError;
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }
  throw lastError ?? new Error("Request failed");
}

async function httpBlob(url: string, init?: ApiRequestInit): Promise<Blob> {
  const token = typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null;
  const initHeaders = headersInitToObject(init?.headers as HeadersInit | undefined);
  const skipAuth = Boolean(getHeaderValue(initHeaders, "X-Skip-Auth"));
  const timeoutMs = init?.timeoutMs ?? requestTimeoutMs;
  const headers: Record<string, string> = { ...initHeaders };

  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === "x-skip-auth") {
      delete headers[key];
    }
  }
  if (token && !skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const { headers: _ignoredHeaders, timeoutMs: _ignoredTimeoutMs, ...requestInit } = init ?? {};
  const requestUrls = /^https?:\/\//i.test(url)
    ? [url]
    : API_BASE_CANDIDATES.map((base) => joinApiUrl(base, url));

  let lastError: Error | null = null;
  for (let i = 0; i < requestUrls.length; i += 1) {
    const requestUrl = requestUrls[i];
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
              return await retryRes.blob();
            }
          }
          if (isSessionExpiredError(detail || text || "")) {
            dispatchSessionExpired(SESSION_EXPIRED_MESSAGE);
            const expiredError = new Error(SESSION_EXPIRED_MESSAGE);
            (expiredError as any).status = 401;
            (expiredError as any).isSessionExpired = true;
            throw expiredError;
          }
        }
        throw new Error(`HTTP ${res.status} ${res.statusText}: ${detail || text}`);
      }
      return await res.blob();
    } catch (error: any) {
      if (error?.isSessionExpired) {
        throw error;
      }
      lastError = error instanceof Error ? error : new Error(String(error));
      if (i === requestUrls.length - 1) throw lastError;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  throw lastError ?? new Error("Download failed");
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
      if (data?.refresh) {
        localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh);
      }
      return data.access;
    }
  } catch (err: any) {
    if (err?.isNetworkError) {
      return null;
    }
    logoutUser(SESSION_EXPIRED_MESSAGE);
    dispatchSessionExpired(SESSION_EXPIRED_MESSAGE);
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

export async function pauseTenderAward(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/pause_award/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function revokeIntentToAward(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/revoke_intent/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function resolveChallenge(
  tenderId: string,
  payload: { challengeId: string; outcome: "upheld" | "dismissed"; resolutionNotes?: string }
): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/resolve_challenge/`, {
    method: "POST",
    body: JSON.stringify({
      challenge_id: payload.challengeId,
      outcome: payload.outcome,
      resolution_notes: payload.resolutionNotes ?? "",
    }),
  });
  return mapTenderFromApi(data);
}

export async function fetchTenderChallenges(tenderId: string): Promise<any[]> {
  return await http<any[]>(`/api/tenders/${tenderId}/challenges/`);
}

export async function createChallenge(
  tenderId: string,
  payload: { filedByVendorId: string; filedByVendorName: string; grounds: string; challengerBidId?: string }
): Promise<any> {
  return await http<any>(`/api/tenders/${tenderId}/create_challenge/`, {
    method: "POST",
    body: JSON.stringify({
      filed_by_vendor_id: payload.filedByVendorId,
      filed_by_vendor_name: payload.filedByVendorName,
      grounds: payload.grounds,
      challenger_bid_id: payload.challengerBidId ?? "",
    }),
  });
}

export async function updateCoolingOff(
  tenderId: string,
  payload: { action: "extend" | "shorten"; days: number }
): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/update_cooling_off/`, {
    method: "POST",
    body: JSON.stringify(payload),
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
  if (payload.subsidy_requested != null) form.append('subsidy_requested', String(payload.subsidy_requested));
  if (payload.stage != null) form.append('stage', payload.stage);
  form.append('concept_note', payload.concept_note ?? "");
  form.append('technical_proposal', payload.technical_proposal ?? "");
  form.append('financial_proposal', payload.financial_proposal ?? "");
  form.append('device_brand_model', payload.device_brand_model ?? "");
  if (payload.tech_tier != null) form.append('tech_tier', payload.tech_tier);
  if (payload.energy_target != null) form.append('energy_target', String(payload.energy_target));
  if (payload.system_configuration) form.append('system_configuration', JSON.stringify(payload.system_configuration));
  if (payload.boq_details) form.append('boq_details', JSON.stringify(payload.boq_details));
  else if (payload.boq_items) form.append('boq_items', JSON.stringify(payload.boq_items));
  if (payload.female_target_pct != null) form.append('female_target_pct', String(payload.female_target_pct));
  if (payload.vulnerable_target_pct != null) form.append('vulnerable_target_pct', String(payload.vulnerable_target_pct));
  if (payload.low_income_target_pct != null) form.append('low_income_target_pct', String(payload.low_income_target_pct));
  if (payload.inclusion_commitment_confirmed != null) form.append('inclusion_commitment_confirmed', String(payload.inclusion_commitment_confirmed));
  form.append('om_strategy_summary', payload.om_strategy_summary ?? "");
  form.append('aftersales_description', payload.aftersales_description ?? "");
  if (payload.local_technicians_to_be_trained != null) form.append('local_technicians_to_be_trained', String(payload.local_technicians_to_be_trained));
  if (payload.warranty_period != null) form.append('warranty_period', String(payload.warranty_period));
  else if (payload.warranty_period_months != null) form.append('warranty_period_months', String(payload.warranty_period_months));
  if (payload.offer_paygo != null) form.append('offer_paygo', String(payload.offer_paygo));
  form.append('paygo_platform', payload.paygo_platform ?? "");
  if (payload.daily_payment_amount_lsl != null) form.append('daily_payment_amount_lsl', String(payload.daily_payment_amount_lsl));
  form.append('collection_method', payload.collection_method ?? "");
  if (payload.sites) form.append('sites', JSON.stringify(payload.sites.map(mapTenderBidSiteToApi)));
  form.append('status', payload.status ?? BidStatus.DRAFT);
  if (payload.preferred_district) form.append('preferred_district', payload.preferred_district);

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
  const omPlanDocument = (payload as any).om_plan_document;
  if (omPlanDocument instanceof File) {
    form.append('om_plan_document', omPlanDocument);
  }
  const omPlanFile = (payload as any).om_plan_file;
  if (omPlanFile instanceof File) {
    form.append('om_plan_file', omPlanFile);
  }
  const reportingTemplatesFile = (payload as any).reporting_templates_file;
  if (reportingTemplatesFile instanceof File) {
    form.append('reporting_templates_file', reportingTemplatesFile);
  }
  const distributionMapFile = (payload as any).distribution_map_file;
  if (distributionMapFile instanceof File) {
    form.append('distribution_map_file', distributionMapFile);
  }
  const tenderSecurityFile = (payload as any).tender_security_file;
  if (tenderSecurityFile instanceof File) {
    form.append('tender_security_file', tenderSecurityFile);
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
  if (payload.subsidy_requested != null) form.append('subsidy_requested', String(payload.subsidy_requested));
  if (payload.stage != null) form.append('stage', payload.stage);
  if (payload.concept_note != null) form.append('concept_note', payload.concept_note);
  if (payload.technical_proposal != null) form.append('technical_proposal', payload.technical_proposal);
  if (payload.financial_proposal != null) form.append('financial_proposal', payload.financial_proposal);
  if (payload.device_brand_model != null) form.append('device_brand_model', payload.device_brand_model);
  if (payload.tech_tier != null) form.append('tech_tier', payload.tech_tier);
  if (payload.energy_target != null) form.append('energy_target', String(payload.energy_target));
  if (payload.system_configuration != null) form.append('system_configuration', JSON.stringify(payload.system_configuration));
  if (payload.boq_details != null) form.append('boq_details', JSON.stringify(payload.boq_details));
  else if (payload.boq_items != null) form.append('boq_items', JSON.stringify(payload.boq_items));
  if (payload.female_target_pct != null) form.append('female_target_pct', String(payload.female_target_pct));
  if (payload.vulnerable_target_pct != null) form.append('vulnerable_target_pct', String(payload.vulnerable_target_pct));
  if (payload.low_income_target_pct != null) form.append('low_income_target_pct', String(payload.low_income_target_pct));
  if (payload.inclusion_commitment_confirmed != null) form.append('inclusion_commitment_confirmed', String(payload.inclusion_commitment_confirmed));
  if (payload.om_strategy_summary != null) form.append('om_strategy_summary', payload.om_strategy_summary);
  if (payload.aftersales_description != null) form.append('aftersales_description', payload.aftersales_description);
  if (payload.local_technicians_to_be_trained != null) form.append('local_technicians_to_be_trained', String(payload.local_technicians_to_be_trained));
  if (payload.warranty_period != null) form.append('warranty_period', String(payload.warranty_period));
  else if (payload.warranty_period_months != null) form.append('warranty_period_months', String(payload.warranty_period_months));
  if (payload.offer_paygo != null) form.append('offer_paygo', String(payload.offer_paygo));
  if (payload.paygo_platform != null) form.append('paygo_platform', payload.paygo_platform);
  if (payload.daily_payment_amount_lsl != null) form.append('daily_payment_amount_lsl', String(payload.daily_payment_amount_lsl));
  if (payload.collection_method != null) form.append('collection_method', payload.collection_method);
  if (payload.sites != null) form.append('sites', JSON.stringify(payload.sites.map(mapTenderBidSiteToApi)));
  if (payload.status != null) form.append('status', payload.status);
  if (payload.preferred_district != null) form.append('preferred_district', payload.preferred_district);

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
  const omPlanDocument = (payload as any).om_plan_document;
  if (omPlanDocument instanceof File) {
    form.append('om_plan_document', omPlanDocument);
  }
  const omPlanFile = (payload as any).om_plan_file;
  if (omPlanFile instanceof File) {
    form.append('om_plan_file', omPlanFile);
  }
  const reportingTemplatesFile = (payload as any).reporting_templates_file;
  if (reportingTemplatesFile instanceof File) {
    form.append('reporting_templates_file', reportingTemplatesFile);
  }
  const distributionMapFile = (payload as any).distribution_map_file;
  if (distributionMapFile instanceof File) {
    form.append('distribution_map_file', distributionMapFile);
  }
  const tenderSecurityFile = (payload as any).tender_security_file;
  if (tenderSecurityFile instanceof File) {
    form.append('tender_security_file', tenderSecurityFile);
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

export async function markTenderBidPartialConformity(
  bidId: string,
  rejectionReason: string
): Promise<TenderBid> {
  const data = await http<any>(`/api/tender-bids/${bidId}/partial_conformity/`, {
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

export async function approveTenderContract(contractId: string, payload?: {
  sendEmail?: boolean;
}): Promise<TenderContract> {
  const data = await http<any>(`/api/tender-contracts/${contractId}/approve/`, {
    method: "POST",
    body: JSON.stringify({
      send_email: payload?.sendEmail ?? true,
    }),
  });
  return mapTenderContractFromApi(data);
}

export async function assignTenderContract(contractId: string, payload?: {
  projectDurationMonths?: number;
  targetInstallations?: number;
  techType?: string;
  energyOutput?: number;
  districts?: string[];
  verificationMethod?: string;
  targetFemalePct?: number;
  targetVulnerablePct?: number;
  targetLowIncomePct?: number;
}): Promise<TenderContract> {
  const body: any = {};
  if (payload?.projectDurationMonths != null) body.project_duration_months = payload.projectDurationMonths;
  if (payload?.targetInstallations != null) body.installation_target = payload.targetInstallations;
  if (payload?.techType) body.technology_type = normalizeTechnologyType(payload.techType);
  if (payload?.energyOutput != null) body.energy_output_target_kwh = payload.energyOutput;
  if (payload?.districts?.length) body.district_zones = payload.districts;
  if (payload?.verificationMethod) body.verification_method = payload.verificationMethod;
  if (payload?.targetFemalePct != null) body.female_target_pct = payload.targetFemalePct;
  if (payload?.targetVulnerablePct != null) body.vulnerable_target_pct = payload.targetVulnerablePct;
  if (payload?.targetLowIncomePct != null) body.low_income_target_pct = payload.targetLowIncomePct;
  const data = await http<any>(`/api/tender-contracts/${contractId}/assign/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return data;
}

export async function fetchTenderContractAssignment(contractId: string): Promise<any> {
  return await http<any>(`/api/tender-contracts/${contractId}/assign/`);
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

export async function fetchProjectsSummary(): Promise<{
  total: number;
  active: number;
  completed: number;
  atRisk: number;
}> {
  const data = await http<any>(`/api/projects/projects-summary/`);
  return {
    total: data.total || 0,
    active: data.active || 0,
    completed: data.completed || 0,
    atRisk: data.at_risk || 0,
  };
}

export async function triggerProjectProspectSync(
  projectId: string,
  action:
    | "push_target"
    | "push_agent"
    | "push_installations"
    | "push_installation_updates"
    | "push_installation_timeseries"
    | "push_report"
    | "refresh_status"
    | "sync_all_available",
): Promise<{ status: string; action: string; queued_methods: string[]; details?: Record<string, any>; message?: string }> {
  return await http<any>(`/api/projects/${projectId}/prospect-sync/`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function triggerProspectReportSync(
  payload: {
    period: "monthly" | "quarterly";
    mode: "all" | "project";
    projectId?: string;
  },
): Promise<{
  status: string;
  period: "monthly" | "quarterly";
  mode: "all" | "project";
  report_start: string;
  report_end: string;
  queued_jobs: number;
}> {
  return await http<any>(`/api/projects/prospect-sync-reports/`, {
    method: "POST",
    body: JSON.stringify({
      period: payload.period,
      mode: payload.mode,
      project_id: payload.projectId,
    }),
  });
}

export async function fetchProjectKpiSummary(projectId: string): Promise<ProjectKpiSummary> {
  return await http<ProjectKpiSummary>(`/api/kpi/project/${projectId}`);
}

export async function fetchPortfolioKpiSummary(): Promise<PortfolioKpiSummary> {
  return await http<PortfolioKpiSummary>(`/api/kpi/portfolio`);
}

export async function fetchPublicPortfolioKpi(): Promise<Record<string, any>> {
  return await http<Record<string, any>>(`/api/kpi/public-portfolio`, { headers: { "X-Skip-Auth": "true" } });
}

export async function fetchMapBoundaryGeoJson(): Promise<any> {
  return await http<any>(`/api/map/boundary`);
}

export async function downloadProjectKpiPdf(projectId: string): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null;
  const requestUrls = API_BASE_CANDIDATES.map((base) => joinApiUrl(base, `/api/kpi/project/${projectId}/export-pdf`));
  let lastError: Error | null = null;
  for (const requestUrl of requestUrls) {
    try {
      const res = await fetch(requestUrl, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText}`);
      }
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `KPI_Report_${projectId}_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      return;
    } catch (error: any) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }
  throw lastError || new Error("Unable to download KPI report.");
}

export async function updateProject(id: string, payload: Partial<Project>): Promise<Project> {
  const body: Record<string, any> = {
    deployment_team_roster: payload.deploymentTeamRoster ?? "",
    deployment_equipment_plan: payload.deploymentEquipmentPlan ?? "",
    deployment_site_status: payload.deploymentSiteStatus ?? "",
    deployment_work_schedule: payload.deploymentWorkSchedule ?? "",
    deployment_permits_status: payload.deploymentPermitsStatus ?? "",
    device_brand: payload.deviceBrand ?? "",
    device_model: payload.deviceModel ?? "",
    device_tech_tier: payload.deviceTechTier ?? "",
    verification_method_confirmed: Boolean(payload.verificationMethodConfirmed),
  };
  const data = await http<any>(`/api/projects/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return mapProjectFromApi(data);
}

function buildProjectSetupForm(payload: {
  siteStatus?: string;
  workScheduleStart?: string;
  workScheduleEnd?: string;
  deviceModel?: string;
  deviceBrand?: string;
  techTier?: number | string;
  meterApiEndpoint?: string;
  meterApiToken?: string;
  manualVerificationConfirmed?: boolean;
  checklistTeamReady?: boolean;
  checklistEquipmentReady?: boolean;
  checklistSiteReady?: boolean;
  checklistSafetyReady?: boolean;
  checklistLogisticsReady?: boolean;
  teamRosterFile?: File | null;
  equipmentPlanFile?: File | null;
  complianceDocsFile?: File | null;
  insuranceCertificateFile?: File | null;
}): FormData {
  const form = new FormData();
  if (payload.siteStatus) form.append("site_status", payload.siteStatus);
  if (payload.workScheduleStart) form.append("work_schedule_start", payload.workScheduleStart);
  if (payload.workScheduleEnd) form.append("work_schedule_end", payload.workScheduleEnd);
  if (payload.deviceModel) form.append("device_model", payload.deviceModel);
  if (payload.deviceBrand) form.append("device_brand", payload.deviceBrand);
  if (payload.techTier != null && payload.techTier !== "") form.append("tech_tier", String(payload.techTier));
  if (payload.meterApiEndpoint) form.append("meter_api_endpoint", payload.meterApiEndpoint);
  if (payload.meterApiToken) form.append("meter_api_token", payload.meterApiToken);
  form.append("manual_verification_confirmed", String(Boolean(payload.manualVerificationConfirmed)));
  form.append("checklist_team_ready", String(Boolean(payload.checklistTeamReady)));
  form.append("checklist_equipment_ready", String(Boolean(payload.checklistEquipmentReady)));
  form.append("checklist_site_ready", String(Boolean(payload.checklistSiteReady)));
  form.append("checklist_safety_ready", String(Boolean(payload.checklistSafetyReady)));
  form.append("checklist_logistics_ready", String(Boolean(payload.checklistLogisticsReady)));
  if (payload.teamRosterFile instanceof File) form.append("team_roster_file", payload.teamRosterFile);
  if (payload.equipmentPlanFile instanceof File) form.append("equipment_plan_file", payload.equipmentPlanFile);
  if (payload.complianceDocsFile instanceof File) form.append("compliance_docs_file", payload.complianceDocsFile);
  if (payload.insuranceCertificateFile instanceof File) form.append("insurance_certificate_file", payload.insuranceCertificateFile);
  return form;
}

export async function saveProjectSetupDraft(
  projectId: string,
  payload: Parameters<typeof buildProjectSetupForm>[0],
): Promise<Project> {
  const data = await http<any>(`/api/projects/${projectId}/setup/`, {
    method: "POST",
    body: buildProjectSetupForm(payload),
  });
  return mapProjectFromApi(data);
}

export async function submitProjectSetup(
  projectId: string,
  payload: Parameters<typeof buildProjectSetupForm>[0],
): Promise<Project> {
  const data = await http<any>(`/api/projects/${projectId}/setup/submit/`, {
    method: "POST",
    body: buildProjectSetupForm(payload),
  });
  return mapProjectFromApi(data);
}

export async function testProjectSetupConnection(
  projectId: string,
  payload: { meterApiEndpoint: string; meterApiToken: string },
): Promise<{ status: string; message: string }> {
  return await http<{ status: string; message: string }>(`/api/projects/${projectId}/setup/test-connection/`, {
    method: "POST",
    body: JSON.stringify({
      meter_api_endpoint: payload.meterApiEndpoint,
      meter_api_token: payload.meterApiToken,
    }),
  });
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
  householdType?: string;
  confirmOutsideDistrict?: boolean;
}): Promise<{ report: InstallationReport; warning?: string; requiresConfirmation?: string }> {
  const form = new FormData();
  form.append("project", payload.projectId);
  if (payload.milestoneId) form.append("milestone", payload.milestoneId);
  form.append("gps_lat", String(payload.gpsLat));
  form.append("gps_lng", String(payload.gpsLng));
  form.append("serial_number", payload.serialNumber);
  form.append("beneficiary_id", payload.beneficiaryId);
  if (payload.meterId) form.append("meter_id", payload.meterId);
  if (payload.kwhReading != null) form.append("kwh_reading", String(payload.kwhReading));
  if (payload.householdType) form.append("household_type", payload.householdType);
  if (payload.confirmOutsideDistrict) form.append("confirm_outside_district", "true");
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
  if (data?.success && data?.data) {
    return {
      report: mapInstallationReportFromApi(data.data),
      warning: typeof data.warning === "string" ? data.warning : undefined,
    };
  }
  if (data?.errors) {
    const errorMessages = Object.values(data.errors).flat().join(" ");
    const err = new Error(errorMessages || "Unable to submit installation report.");
    (err as any).fieldErrors = data.errors;
    throw err;
  }
  return {
    report: mapInstallationReportFromApi(data),
  };
}

export async function fetchMapInstallations(filters: Record<string, string | undefined> = {}): Promise<MapInstallationsResponse> {
  const search = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value != null && value !== "") search.set(key, value);
  });
  const query = search.toString();
  const data = await http<any>(`/api/map/installations${query ? `?${query}` : ""}`);
  const payload = data?.data ?? {};
  return {
    installations: Array.isArray(payload.installations) ? payload.installations.map(mapMapInstallationFromApi) : [],
    summary: {
      total: Number(payload.summary?.total ?? 0),
      verified: Number(payload.summary?.verified ?? 0),
      pending: Number(payload.summary?.pending ?? 0),
      flagged: Number(payload.summary?.flagged ?? 0),
    },
    truncated: Boolean(data?.truncated),
  };
}

export async function fetchVerificationTasks(projectId?: string): Promise<VerificationTask[]> {
  const query = projectId ? `?report__project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/verification-tasks/${query}`);
  return unwrapListResponse<any>(data).map(mapVerificationTaskFromApi);
}

export async function verifyVerificationTask(
  taskId: string,
  payload:
    | { verifierLat: number; verifierLng: number; verificationStatus?: "verified" | "flagged" | "partial" }
    | FormData
): Promise<VerificationTask> {
  const body = payload instanceof FormData
    ? payload
    : JSON.stringify({
        verifier_lat: payload.verifierLat,
        verifier_lng: payload.verifierLng,
        verification_status: payload.verificationStatus,
      });
  const data = await http<any>(`/api/projects/verification-tasks/${taskId}/verify/`, {
    method: "POST",
    body,
  });
  return mapVerificationTaskFromApi(data);
}

export async function fetchNotifications(): Promise<Notification[]> {
  const data = await http<any>(`/api/notifications/`);
  return unwrapListResponse<any>(data).map(mapNotificationFromApi);
}

export async function fetchUnreadNotificationCount(): Promise<number> {
  const data = await http<any>(`/api/notifications/unread_count/`);
  return Number(data?.count ?? 0);
}

export async function markNotificationRead(id: string): Promise<void> {
  await http<any>(`/api/notifications/${id}/mark_read/`, { method: "POST" });
}

export async function markAllNotificationsRead(): Promise<number> {
  const data = await http<any>(`/api/notifications/mark_all_read/`, { method: "POST" });
  return Number(data?.updated ?? 0);
}

export async function fetchVendorPrequalifications(): Promise<VendorPrequalification[]> {
  const data = await http<any>(`/api/users/prequalifications/`);
  return unwrapListResponse<any>(data).map(mapVendorPrequalificationFromApi);
}

export async function fetchMyProfile(): Promise<VendorProfile> {
  const data = await http<any>(`/api/users/my_profile/`);
  return mapVendorProfileFromApi(data);
}

export async function fetchVendorProfile(vendorId: string): Promise<VendorProfile> {
  const data = await http<any>(`/api/users/${vendorId}/profile/`);
  return mapVendorProfileFromApi(data);
}

const VENDOR_DIRECTORY_PAGE_SIZE = 20;

export async function fetchVendorDirectory(page: number = 1): Promise<{
  vendors: VendorDirectoryEntry[];
  total: number;
  page: number;
  totalPages: number;
}> {
  const data = await http<any>(`/api/users/vendor_directory/?page=${page}`);
  if (Array.isArray(data)) {
    const vendors = data.map(mapVendorDirectoryEntryFromApi);
    return { vendors, total: vendors.length, page: 1, totalPages: 1 };
  }
  const results = (data.results || []).map(mapVendorDirectoryEntryFromApi);
  const total = data.count ?? 0;
  const totalPages = Math.ceil(total / VENDOR_DIRECTORY_PAGE_SIZE) || 1;
  return { vendors: results, total, page, totalPages };
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
  payload: VendorPrequalificationSubmission,
  existingId?: string
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
  form.append('bank_name', payload.bankName ?? "");
  form.append('bank_branch', payload.bankBranch ?? "");
  form.append('bank_swift_code', payload.bankSwiftCode ?? "");
  form.append('bank_sort_code', payload.bankSortCode ?? "");
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
  
  const data = await http<any>(existingId ? `/api/users/prequalifications/${existingId}/` : `/api/users/prequalifications/`, {
    method: existingId ? "PATCH" : "POST",
    body: form,
    timeoutMs: 300000,
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

export async function fetchPaymentClaims(params?: {
  projectId?: string;
  pageSize?: number;
}): Promise<PaymentClaim[]> {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project", params.projectId);
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const url = query.toString() ? `/api/projects/claims/?${query.toString()}` : `/api/projects/claims/`;
  const data = await http<any>(url);
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
  action: "verify" | "approve" | "reject" | "pay" | "confirm-paid",
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

export async function confirmPaymentClaim(
  id: string,
  paymentReference?: string,
  notes?: string
): Promise<PaymentClaim> {
  return reviewPaymentClaim(id, "confirm-paid", {
    payment_reference: paymentReference ?? "",
    notes: notes ?? "",
  });
}

export async function fetchVendorBankDetails(id: string): Promise<VendorBankDetails> {
  const data = await http<any>(`/api/projects/claims/${id}/view_bank_details/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    vendorLegalName: data.vendor_legal_name ?? undefined,
    vendorBankName: data.vendor_bank_name ?? undefined,
    vendorBankBranch: data.vendor_bank_branch ?? undefined,
    vendorBankSwiftCode: data.vendor_bank_swift_code ?? undefined,
    vendorBankSortCode: data.vendor_bank_sort_code ?? undefined,
    vendorAccountHolderName: data.vendor_account_holder_name ?? undefined,
    vendorAccountNumber: data.vendor_account_number ?? undefined,
  };
}

export async function fetchVendorBankDetailsWithAccess(
  id: string,
  revealFull = false
): Promise<VendorBankDetails> {
  const data = await http<any>(`/api/projects/claims/${id}/view_bank_details/`, {
    method: "POST",
    body: JSON.stringify({ reveal_full: revealFull }),
  });
  return {
    vendorLegalName: data.vendor_legal_name ?? undefined,
    vendorBankName: data.vendor_bank_name ?? undefined,
    vendorBankBranch: data.vendor_bank_branch ?? undefined,
    vendorBankSwiftCode: data.vendor_bank_swift_code ?? undefined,
    vendorBankSortCode: data.vendor_bank_sort_code ?? undefined,
    vendorAccountHolderName: data.vendor_account_holder_name ?? undefined,
    vendorAccountNumber: data.vendor_account_number ?? undefined,
  };
}

export async function fetchDisbursementSheet(id: string): Promise<DisbursementSheet> {
  const data = await http<any>(`/api/projects/claims/${id}/disbursement-sheet/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    claimId: data.claim_id != null ? String(data.claim_id) : undefined,
    projectId: data.project_id != null ? String(data.project_id) : undefined,
    claimStatus: data.claim_status ?? undefined,
    totalApprovedAmount: data.total_approved_amount != null ? Number(data.total_approved_amount) : undefined,
    vendorLegalName: data.vendor_legal_name ?? undefined,
    vendorBankName: data.vendor_bank_name ?? undefined,
    vendorBankBranch: data.vendor_bank_branch ?? undefined,
    vendorBankSwiftCode: data.vendor_bank_swift_code ?? undefined,
    vendorBankSortCode: data.vendor_bank_sort_code ?? undefined,
    vendorAccountHolderName: data.vendor_account_holder_name ?? undefined,
    vendorAccountNumber: data.vendor_account_number ?? undefined,
  };
}

export async function fetchDisbursements(): Promise<Disbursement[]> {
  const data = await http<any>(`/api/projects/disbursements/`);
  return unwrapListResponse<any>(data).map(mapDisbursementFromApi);
}

export async function fetchAuditLogs(projectId?: string): Promise<AuditLog[]> {
  const query = projectId
    ? `?record_id=${encodeURIComponent(projectId)}`
    : "";
  const data = await http<any>(`/api/projects/audit-logs/${query}`);
  return unwrapListResponse<any>(data).map(mapAuditLogFromApi);
}

export async function fetchReportTemplates(): Promise<ReportTemplate[]> {
  const data = await http<any>(`/api/projects/reports/templates/`);
  return unwrapListResponse<any>(data).map((item) => ({
    id: String(item.id || ""),
    title: String(item.title || ""),
    description: String(item.description || ""),
    category: item.category != null ? String(item.category) : undefined,
    quick: item.quick != null ? Boolean(item.quick) : undefined,
    formats: Array.isArray(item.formats)
      ? item.formats
          .map((format: any) => String(format).toLowerCase())
          .filter((format: any) => format === "csv" || format === "pdf" || format === "excel") as ReportFormat[]
      : [],
  }));
}

export async function fetchReportHistory(): Promise<ReportHistoryItem[]> {
  const data = await http<any>(`/api/projects/reports/history/`);
  return unwrapListResponse<any>(data).map((item) => ({
    id: String(item.id || ""),
    reportType: String(item.report_type || item.reportType || ""),
    format: String(item.format || "").toLowerCase() as ReportFormat,
    generatedAt: String(item.generated_at || item.generatedAt || ""),
    notes: String(item.notes || ""),
    project: item.project != null ? String(item.project) : undefined,
    generatedBy: item.generatedBy != null ? String(item.generatedBy) : undefined,
    downloadUrl: item.downloadUrl != null ? String(item.downloadUrl) : undefined,
  }));
}

export async function generateReport(
  reportType: string,
  format: ReportFormat,
  filters?: Record<string, any>,
): Promise<Blob> {
  return await httpBlob(`/api/projects/reports/generate/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_type: reportType, format, filters: filters || {} }),
  });
}

export async function downloadGeneratedReport(downloadUrl: string): Promise<Blob> {
  return await httpBlob(downloadUrl);
}

export async function fetchSystemAuditLogs(params?: {
  actor?: string;
  actorRole?: string;
  action?: string;
  module?: string;
  dateFrom?: string;
  dateTo?: string;
  recordId?: string;
}): Promise<AuditLog[]> {
  const query = new URLSearchParams();
  if (params?.actor) query.set("actor", params.actor);
  if (params?.actorRole) query.set("actor_role", params.actorRole);
  if (params?.action) query.set("action", params.action);
  if (params?.module) query.set("module", params.module);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  if (params?.recordId) query.set("record_id", params.recordId);
  const url = query.toString() ? `/api/projects/audit-logs/?${query.toString()}` : `/api/projects/audit-logs/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapAuditLogFromApi);
}

export async function exportSystemAuditLogs(
  format: "csv" | "pdf",
  params?: {
    actor?: string;
    actorRole?: string;
    action?: string;
    module?: string;
    dateFrom?: string;
    dateTo?: string;
    recordId?: string;
  },
): Promise<Blob> {
  const query = new URLSearchParams();
  if (params?.actor) query.set("actor", params.actor);
  if (params?.actorRole) query.set("actor_role", params.actorRole);
  if (params?.action) query.set("action", params.action);
  if (params?.module) query.set("module", params.module);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  if (params?.recordId) query.set("record_id", params.recordId);
  const base = format === "csv" ? "/api/projects/audit-logs/export-csv/" : "/api/projects/audit-logs/export-pdf/";
  const url = query.toString() ? `${base}?${query.toString()}` : base;
  return await httpBlob(url);
}

export async function fetchSmartMeterReadings(projectId?: string): Promise<SmartMeterReading[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/smart-meter-readings/${query}`);
  return unwrapListResponse<any>(data).map(mapSmartMeterReadingFromApi);
}

export async function fetchAnomalyFlags(params?: {
  projectId?: string;
  isResolved?: boolean;
}): Promise<AnomalyFlag[]> {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project", params.projectId);
  if (params?.isResolved !== undefined) query.set("is_resolved", String(params.isResolved));
  const q = query.toString() ? `?${query.toString()}` : "";
  const data = await http<any>(`/api/projects/anomaly-flags/${q}`);
  return unwrapListResponse<any>(data).map(mapAnomalyFlagFromApi);
}

export async function resolveAnomalyFlag(id: string): Promise<AnomalyFlag> {
  const data = await http<any>(`/api/projects/anomaly-flags/${id}/resolve/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapAnomalyFlagFromApi(data);
}

export async function fetchProspectSyncLogs(params?: {
  status?: string;
  pageSize?: number;
}): Promise<ProspectSyncLog[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const url = query.toString() ? `/api/projects/prospect-sync-logs/?${query.toString()}` : `/api/projects/prospect-sync-logs/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapProspectSyncLogFromApi);
}

export async function fetchProspectSyncSummary(): Promise<{
  failedJobs: number;
  lastSyncAt?: string;
  rows: Array<{
    dataType: string;
    ourCount: number;
    prospectCount: number;
    match: boolean;
    lastSync?: string;
    note?: string;
  }>;
}> {
  const data = await http<any>(`/api/projects/prospect-sync-logs/summary/`);
  return {
    failedJobs: Number(data.failed_jobs ?? 0),
    lastSyncAt: data.last_sync_at ?? undefined,
    rows: Array.isArray(data.rows)
      ? data.rows.map((row: any) => ({
          dataType: row.data_type ?? "",
          ourCount: Number(row.our_count ?? 0),
          prospectCount: Number(row.prospect_count ?? 0),
          match: Boolean(row.match),
          lastSync: row.last_sync ?? undefined,
          note: row.note ?? undefined,
        }))
      : [],
  };
}

export async function checkProspectConnection(): Promise<{ readTokenOk: boolean; writeTokenOk: boolean; baseUrl?: string }> {
  const data = await http<any>(`/api/projects/prospect-sync-logs/check-connection/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    readTokenOk: Boolean(data.read_token_ok),
    writeTokenOk: Boolean(data.write_token_ok),
    baseUrl: data.base_url ?? undefined,
  };
}

export async function retryProspectSyncJob(id: string): Promise<void> {
  await http<any>(`/api/projects/prospect-sync-logs/${id}/retry/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function retryAllFailedProspectSyncJobs(): Promise<{ count: number }> {
  const data = await http<any>(`/api/projects/prospect-sync-logs/retry-failed/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return { count: Number(data.count ?? 0) };
}

export async function refreshProspectSyncPanel(payload?: {
  projectId?: string;
  size?: number;
  page?: number;
  country?: string;
  program?: string;
  externalId?: string;
}): Promise<{ status: string; queued_methods: string[]; filters: Record<string, string | number> }> {
  const body: Record<string, string | number> = {};
  if (payload?.projectId) body.project_id = payload.projectId;
  if (payload?.size != null) body.size = payload.size;
  if (payload?.page != null) body.page = payload.page;
  if (payload?.country) body.country = payload.country;
  if (payload?.program) body.program = payload.program;
  if (payload?.externalId) body.external_id = payload.externalId;
  return await http<{ status: string; queued_methods: string[]; filters: Record<string, string | number> }>(`/api/projects/prospect-sync-logs/refresh-panel/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function requestProjectSetupChange(projectId: string, message: string): Promise<{ status: string; message: string }> {
  return await http<{ status: string; message: string }>(`/api/projects/${projectId}/setup/request-change/`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function uploadProjectMeterCsv(projectId: string, file: File): Promise<{ status: string; rows_ingested: number; uploaded_at: string }> {
  const form = new FormData();
  form.append("file", file);
  return await http<{ status: string; rows_ingested: number; uploaded_at: string }>(`/api/projects/${projectId}/meter-csv-upload/`, {
    method: "POST",
    body: form,
  });
}

export async function flagProjectIssue(
  projectId: string,
  payload: { category?: string; details: string }
): Promise<{ status: string; title: string; details: string }> {
  return await http(`/api/projects/${projectId}/flag_issue/`, {
    method: "POST",
    body: JSON.stringify({
      category: payload.category ?? "general",
      details: payload.details,
    }),
  });
}

export async function loginUser(username: string, password: string): Promise<{ user: User; access: string; refresh: string }> {
  const normalizedUsername = (username || "").trim();
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

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

  if (typeof window !== "undefined") {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh);
  }

  const user = await fetchCurrentUser();

  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  return { user, access: data.access, refresh: data.refresh };
}

export function logoutUser(sessionExpiredReason?: string) {
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (sessionExpiredReason) {
      localStorage.setItem(SESSION_EXPIRED_KEY, sessionExpiredReason);
    } else {
      localStorage.removeItem(SESSION_EXPIRED_KEY);
    }
  }
}

export function getSessionExpiredMessage(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(SESSION_EXPIRED_KEY);
}

export function clearSessionExpiredMessage() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(SESSION_EXPIRED_KEY);
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

export async function changeOwnPassword(newPassword: string, currentPassword = ""): Promise<User> {
  const data = await http<any>(`/api/users/auth/change-password/`, {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  const user = mapUserFromApi(data);
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  return user;
}

export async function fetchAdminManagedUsers(params?: {
  role?: string;
  district?: string;
  status?: "active" | "inactive";
}): Promise<User[]> {
  const query = new URLSearchParams();
  if (params?.role) query.set("role", params.role);
  if (params?.district) query.set("district", params.district);
  if (params?.status) query.set("status", params.status);
  const url = query.toString() ? `/api/users/?${query.toString()}` : `/api/users/`;
  const data = await http<any>(url);
  return unwrapListResponse<any>(data).map(mapUserFromApi);
}

export async function fetchAdminUserDetail(userId: string): Promise<User> {
  const data = await http<any>(`/api/users/${userId}/`);
  return mapUserFromApi(data);
}

export async function fetchUserManagementMeta(): Promise<{ roles: Array<{ label: string; value: string }> }> {
  return await http<{ roles: Array<{ label: string; value: string }> }>(`/api/users/management/meta/`);
}

export async function createAdminManagedUser(payload: {
  fullName: string;
  email: string;
  gender: "Male" | "Female" | "Other";
  role: string;
  district?: string;
  districts?: string[];
}): Promise<{ user: User; initialPassword?: string; emailError?: string }> {
  const body: Record<string, any> = {
    full_name: payload.fullName,
    email: payload.email,
    gender: payload.gender,
    role: payload.role,
  };
  if (payload.districts && payload.districts.length > 0) {
    body.districts = payload.districts;
    body.verification_zone = payload.districts[0];
    body.region = payload.districts[0];
  } else if (payload.district) {
    body.region = payload.district;
    body.verification_zone = payload.district;
  }
  const data = await http<any>(`/api/users/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return {
    user: mapUserFromApi(data),
    initialPassword: data?.initial_password ?? undefined,
    emailError: data?.email_error ?? undefined,
  };
}

export async function updateAdminManagedUser(userId: string, payload: {
  fullName?: string;
  email?: string;
  gender?: "Male" | "Female" | "Other";
  role?: string;
  district?: string;
  districts?: string[];
  isActive?: boolean;
}): Promise<User> {
  const body: Record<string, any> = {};
  if (payload.fullName !== undefined) body.full_name = payload.fullName;
  if (payload.email !== undefined) body.email = payload.email;
  if (payload.gender !== undefined) body.gender = payload.gender;
  if (payload.role !== undefined) body.role = payload.role;
  if (payload.isActive !== undefined) body.is_active = payload.isActive;
  if (payload.districts && payload.districts.length > 0) {
    body.districts = payload.districts;
    body.verification_zone = payload.districts[0];
    body.region = payload.districts[0];
  } else if (payload.district !== undefined) {
    body.region = payload.district;
    body.verification_zone = payload.district;
  }
  const data = await http<any>(`/api/users/${userId}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return mapUserFromApi(data);
}

export async function deactivateAdminManagedUser(userId: string): Promise<User> {
  const data = await http<any>(`/api/users/${userId}/deactivate/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapUserFromApi(data);
}

export async function resetAdminManagedUserPassword(userId: string): Promise<{ temporaryPassword?: string; emailError?: string }> {
  const data = await http<any>(`/api/users/${userId}/reset-password/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    temporaryPassword: data?.temporary_password ?? undefined,
    emailError: data?.email_error ?? undefined,
  };
}

export async function requestPasswordReset(identifier: string): Promise<{ resetUrl?: string; emailError?: string }> {
  const data = await http<any>(`/api/users/request-password-reset/`, {
    method: "POST",
    body: JSON.stringify({ username_or_email: identifier }),
  });
  return {
    resetUrl: data?.reset_url ?? undefined,
    emailError: data?.email_error ?? undefined,
  };
}

export async function confirmResetPassword(token: string, newPassword: string): Promise<void> {
  await http<any>(`/api/users/reset-password-confirm/`, {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function fetchSuperAdminDashboardSummary(): Promise<SuperAdminDashboardSummary> {
  const data = await http<any>(`/api/users/admin/dashboard/`);
  return mapSuperAdminDashboardSummaryFromApi(data);
}

export async function fetchOrganizations(): Promise<Organization[]> {
  const data = await http<any>(`/api/users/organizations/`);
  return unwrapListResponse<any>(data).map(mapOrganizationFromApi);
}

export async function createOrganization(payload: {
  name: string;
  type: "Government" | "International" | "NGO";
  contactPerson?: string;
  email?: string;
  phone?: string;
  address?: string;
}): Promise<Organization> {
  const data = await http<any>(`/api/users/organizations/`, {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      type: payload.type,
      contact_person: payload.contactPerson ?? "",
      email: payload.email ?? "",
      phone: payload.phone ?? "",
      address: payload.address ?? "",
    }),
  });
  return mapOrganizationFromApi(data);
}

export async function updateOrganization(id: string, payload: {
  name: string;
  type: "Government" | "International" | "NGO";
  contactPerson?: string;
  email?: string;
  phone?: string;
  address?: string;
}): Promise<Organization> {
  const data = await http<any>(`/api/users/organizations/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({
      name: payload.name,
      type: payload.type,
      contact_person: payload.contactPerson ?? "",
      email: payload.email ?? "",
      phone: payload.phone ?? "",
      address: payload.address ?? "",
    }),
  });
  return mapOrganizationFromApi(data);
}

export async function deleteOrganization(id: string): Promise<void> {
  await http<void>(`/api/users/organizations/${id}/`, {
    method: "DELETE",
  });
}

export async function fetchPlatformConfiguration(): Promise<PlatformConfiguration> {
  const data = await http<any>(`/api/users/platform-configuration/`);
  return mapPlatformConfigurationFromApi(data);
}

export async function updatePlatformConfiguration(payload: Partial<PlatformConfiguration>): Promise<PlatformConfiguration> {
  const data = await http<any>(`/api/users/platform-configuration/`, {
    method: "PATCH",
    body: JSON.stringify({
      national_main_program_budget: payload.nationalMainProgramBudget,
      female_target_minimum: payload.femaleTargetMinimum,
      vulnerable_target_minimum: payload.vulnerableTargetMinimum,
      low_income_target_minimum: payload.lowIncomeTargetMinimum,
      uptime_target: payload.uptimeTarget,
      anomaly_deviation_threshold: payload.anomalyDeviationThreshold,
      gps_duplicate_radius_m: payload.gpsDuplicateRadiusM,
      gps_verification_max_distance_m: payload.gpsVerificationMaxDistanceM,
      m2_verification_required_pct: payload.m2VerificationRequiredPct,
      m3_verification_required_pct: payload.m3VerificationRequiredPct,
      email_notifications_enabled: payload.emailNotificationsEnabled,
      sms_notifications_enabled: payload.smsNotificationsEnabled,
      email_host: payload.emailHost,
      email_port: payload.emailPort,
      email_use_tls: payload.emailUseTls,
      email_host_user: payload.emailHostUser,
      default_from_email: payload.defaultFromEmail,
      ...(payload.emailHostPassword ? { email_host_password: payload.emailHostPassword } : {}),
      max_file_size_mb: payload.maxFileSizeMb,
      allowed_file_types: payload.allowedFileTypes,
    }),
  });
  return mapPlatformConfigurationFromApi(data);
}

export async function refreshBoundaryFile(): Promise<void> {
  await http<void>(`/api/users/platform-configuration/refresh-boundary/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function uploadBoundaryFile(file: File): Promise<void> {
  const formData = new FormData();
  formData.append("file", file);
  await http<any>(`/api/users/platform-configuration/upload-boundary/`, {
    method: "POST",
    body: formData,
  });
}

export async function fetchSystemHealth(): Promise<SystemHealthPayload> {
  const data = await http<any>(`/api/users/system-health/`);
  return mapSystemHealthFromApi(data);
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
  associatedEntities?: string[];
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
    associated_entities: payload.associatedEntities ?? [],
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

function mapConcernFromApi(api: any): Concern {
  return {
    id: String(api.id ?? ""),
    raisedBy: String(api.raised_by ?? ""),
    raisedByUsername: api.raised_by_username ?? undefined,
    raisedByRole: api.raised_by_role ?? "doe",
    raisedByRegion: api.raised_by_region ?? undefined,
    concernType: api.concern_type ?? ConcernType.OTHER,
    severity: api.severity ?? ConcernSeverity.LOW,
    linkedProject: api.linked_project ?? undefined,
    linkedProjectName: api.linked_project_ref ?? api.linked_project_name ?? undefined,
    linkedProjectVendor: api.linked_project_vendor ?? undefined,
    linkedProjectDistrict: api.linked_project_district ?? undefined,
    linkedInstallation: api.linked_installation ?? undefined,
    linkedClaim: api.linked_claim ?? undefined,
    description: api.description ?? "",
    evidenceFiles: Array.isArray(api.evidence_files) ? api.evidence_files : undefined,
    status: api.status ?? ConcernStatus.OPEN,
    createdAt: api.created_at ?? "",
    updatedAt: api.updated_at ?? undefined,
    notifyRmt: api.notify_rmt,
    notifyPsc: api.notify_psc,
    responses: Array.isArray(api.responses) ? api.responses.map(mapConcernResponseFromApi) : undefined,
  };
}

function mapConcernResponseFromApi(api: any): ConcernResponse {
  return {
    id: String(api.id ?? ""),
    concernId: String(api.concern ?? ""),
    respondedBy: String(api.responded_by ?? ""),
    respondedByUsername: api.responded_by_username ?? undefined,
    respondedByRole: api.responded_by_role ?? undefined,
    responseText: api.response_text ?? "",
    actionTaken: api.action_taken ?? "under_investigation",
    evidenceFiles: Array.isArray(api.evidence_files) ? api.evidence_files : undefined,
    createdAt: api.created_at ?? "",
  };
}

function mapAuditFindingFromApi(api: any): AuditFinding {
  return {
    id: String(api.id ?? ""),
    findingReference: api.finding_reference ?? undefined,
    raisedBy: String(api.raised_by ?? ""),
    raisedByUsername: api.raised_by_username ?? undefined,
    raisedByRole: api.raised_by_role ?? undefined,
    raisedByRegion: api.raised_by_region ?? undefined,
    findingCategory: api.finding_category ?? FindingCategory.OTHER_COMPLIANCE,
    riskLevel: api.risk_level ?? RiskLevel.OBSERVATION,
    linkedProject: api.linked_project ?? undefined,
    linkedProjectName: api.linked_project_ref ?? api.linked_project_name ?? undefined,
    linkedProjectVendor: api.linked_project_vendor ?? undefined,
    linkedProjectDistrict: api.linked_project_district ?? undefined,
    linkedClaim: api.linked_claim ?? undefined,
    linkedInstallation: api.linked_installation ?? undefined,
    linkedAuditLog: api.linked_audit_log ?? undefined,
    description: api.description ?? "",
    recommendedAction: api.recommended_action ?? undefined,
    evidenceFiles: Array.isArray(api.evidence_files) ? api.evidence_files : undefined,
    status: api.status ?? ConcernStatus.OPEN,
    rmtResponse: api.rmt_response ?? undefined,
    rmtActionTaken: api.rmt_action_taken ?? undefined,
    rmtRespondedAt: api.rmt_responded_at ?? undefined,
    pscComment: api.psc_comment ?? undefined,
    pscCommentedAt: api.psc_commented_at ?? undefined,
    pscNotified: Boolean(api.psc_notified || api.notify_psc),
    superAdminNotified: Boolean(api.super_admin_notified),
    createdAt: api.created_at ?? "",
    updatedAt: api.updated_at ?? undefined,
  };
}

export async function fetchConcerns(): Promise<Concern[]> {
  const data = await http<any>(`/api/projects/concerns/`);
  const items = unwrapListResponse<any>(data);
  return items.map(mapConcernFromApi);
}

export async function createConcern(concern: {
  concern_type: ConcernType;
  severity: ConcernSeverity;
  linked_project?: string;
  linked_installation?: string;
  description: string;
  evidence_files?: string[];
  notify_rmt?: boolean;
  notify_psc?: boolean;
}): Promise<Concern> {
  const data = await http<any>(`/api/projects/concerns/`, {
    method: "POST",
    body: JSON.stringify(concern),
  });
  return mapConcernFromApi(data);
}

export async function updateConcern(concernId: string, data: {
  status?: string;
  notify_psc?: boolean;
  notify_rmt?: boolean;
}): Promise<Concern> {
  const result = await http<any>(`/api/projects/concerns/${concernId}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
  return mapConcernFromApi(result);
}

export async function fetchConcernResponses(concernId: string): Promise<ConcernResponse[]> {
  const data = await http<any>(`/api/projects/concern-responses/?concern=${concernId}`);
  const items = unwrapListResponse<any>(data);
  return items.map(mapConcernResponseFromApi);
}

export async function createConcernResponse(concernId: string, response: {
  response_text: string;
  action_taken?: string;
  evidence_files?: string[];
  responded_by?: string | number;
}): Promise<ConcernResponse> {
  const data = await http<any>(`/api/projects/concern-responses/`, {
    method: "POST",
    body: JSON.stringify({ concern: concernId, responded_by: response.responded_by, response_text: response.response_text, action_taken: response.action_taken, evidence_files: response.evidence_files }),
  });
  return mapConcernResponseFromApi(data);
}

export async function fetchAuditFindings(): Promise<AuditFinding[]> {
  const data = await http<any>(`/api/projects/audit-findings/`);
  const items = unwrapListResponse<any>(data);
  return items.map(mapAuditFindingFromApi);
}

export async function createAuditFinding(finding: {
  finding_category: FindingCategory;
  risk_level: RiskLevel;
  linked_project?: string;
  linked_claim?: string;
  linked_installation?: string;
  description: string;
  recommended_action?: string;
  evidence_files?: string[];
  rised_to_rmt?: boolean;
  rised_to_psc?: boolean;
  rised_to_super_admin?: boolean;
}): Promise<AuditFinding> {
  const data = await http<any>(`/api/projects/audit-findings/`, {
    method: "POST",
    body: JSON.stringify(finding),
  });
  return mapAuditFindingFromApi(data);
}

export async function updateAuditFinding(findingId: string, data: {
  status?: string;
}): Promise<AuditFinding> {
  const result = await http<any>(`/api/projects/audit-findings/${findingId}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
  return mapAuditFindingFromApi(result);
}

export async function respondAuditFinding(findingId: string, response: {
  response: string;
  action_taken: string;
}): Promise<any> {
  const data = await http<any>(`/api/projects/audit-findings/${findingId}/respond/`, {
    method: "POST",
    body: JSON.stringify(response),
  });
  return data;
}

// ======================== NOTICE API FUNCTIONS ========================

function mapNoticeFromApi(data: any): Notice {
  const attachments: NoticeAttachment[] = (data.attachments || []).map((a: any) => ({
    id: a.id,
    name: a.name || a.file_name || 'Document',
    url: a.file || a.url,
    size: a.size,
    type: a.type || a.content_type,
  }));

  return {
    id: data.id,
    notice_id: data.notice_id,
    title: data.title,
    category: data.category as NoticeCategory,
    summary: data.summary,
    content: data.content,
    linked_tender: data.linked_tender || null,
    tender_reference: data.tender_reference || null,
    tender_name: data.tender_name || null,
    is_pinned: data.is_pinned || false,
    send_email_notification: data.send_email_notification || false,
    show_countdown: data.show_countdown || false,
    countdown_date: data.countdown_date || null,
    attachments: attachments,
    status: data.status as NoticeStatus,
    published_at: data.published_at || null,
    publish_date: data.publish_date || null,
    schedule_publish: data.schedule_publish || false,
    created_at: data.created_at,
    updated_at: data.updated_at,
  };
}

function mapNoticeToApi(notice: Partial<Notice>): any {
  const data: any = {};
  if (notice.title !== undefined) data.title = notice.title;
  if (notice.category !== undefined) data.category = notice.category;
  if (notice.summary !== undefined) data.summary = notice.summary;
  if (notice.content !== undefined) data.content = notice.content;
  if (notice.linked_tender !== undefined) data.linked_tender = notice.linked_tender;
  if (notice.is_pinned !== undefined) data.is_pinned = notice.is_pinned;
  if (notice.send_email_notification !== undefined) data.send_email_notification = notice.send_email_notification;
  if (notice.show_countdown !== undefined) data.show_countdown = notice.show_countdown;
  if (notice.countdown_date !== undefined && notice.countdown_date !== null) data.countdown_date = notice.countdown_date;
  if (notice.status !== undefined) data.status = notice.status;
  if (notice.published_at !== undefined) data.published_at = notice.published_at;
  if (notice.publish_date !== undefined) data.publish_date = notice.publish_date;
  if (notice.schedule_publish !== undefined) data.schedule_publish = notice.schedule_publish;
  if (notice.tender_reference !== undefined) data.tender_reference = notice.tender_reference;
  if (notice.tender_name !== undefined) data.tender_name = notice.tender_name;
  if (notice.attachments !== undefined) data.attachments = notice.attachments;
  return data;
}

export async function fetchNotices(params?: {
  status?: string;
  category?: string;
}): Promise<Notice[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.category) query.set("category", params.category);
  const url = query.toString() ? `/api/notices/?${query.toString()}` : `/api/notices/`;
  const data = await http<any>(url);
  const items = unwrapListResponse<any>(data);
  return items.map(mapNoticeFromApi);
}

export async function fetchNotice(noticeId: string): Promise<Notice> {
  const data = await http<any>(`/api/notices/${noticeId}/`);
  return mapNoticeFromApi(data);
}

export async function createNotice(notice: Partial<Notice>, attachments?: File[]): Promise<Notice> {
  const mapped = mapNoticeToApi(notice);
  if (attachments && attachments.length > 0) {
    const form = new FormData();
    
    // Append mapped fields
    Object.keys(mapped).forEach(key => {
      if (key !== 'attachments' && mapped[key] !== undefined && mapped[key] !== null) {
        form.append(key, String(mapped[key]));
      } else if (mapped[key] === null) {
        form.append(key, ""); // Send empty string for null to be handled by backend
      }
    });
    
    attachments.forEach((file, idx) => {
      form.append(`attachments-${idx}`, file);
    });
    
    const data = await http<any>(`/api/notices/`, {
      method: "POST",
      body: form,
    });
    return mapNoticeFromApi(data);
  } else {
    const data = await http<any>(`/api/notices/`, {
      method: "POST",
      body: JSON.stringify(mapped),
    });
    return mapNoticeFromApi(data);
  }
}

export async function updateNotice(noticeId: string, notice: Partial<Notice>, attachments?: File[]): Promise<Notice> {
  const mapped = mapNoticeToApi(notice);
  if (attachments && attachments.length > 0) {
    const form = new FormData();
    
    // Append mapped fields
    Object.keys(mapped).forEach(key => {
      if (key !== 'attachments' && mapped[key] !== undefined && mapped[key] !== null) {
        form.append(key, String(mapped[key]));
      } else if (mapped[key] === null) {
        form.append(key, ""); // Send empty string for null
      }
    });
    
    attachments.forEach((file, idx) => {
      form.append(`attachments-${idx}`, file);
    });
    
    const data = await http<any>(`/api/notices/${noticeId}/`, {
      method: "PATCH",
      body: form,
    });
    return mapNoticeFromApi(data);
  } else {
    const data = await http<any>(`/api/notices/${noticeId}/`, {
      method: "PATCH",
      body: JSON.stringify(mapped),
    });
    return mapNoticeFromApi(data);
  }
}

export async function deleteNotice(noticeId: string): Promise<void> {
  await http<any>(`/api/notices/${noticeId}/`, {
    method: "DELETE",
  });
}

export async function publishNotice(noticeId: string): Promise<Notice> {
  const data = await http<any>(`/api/notices/${noticeId}/publish/`, {
    method: "POST",
  });
  return mapNoticeFromApi(data);
}

export async function unpublishNotice(noticeId: string): Promise<Notice> {
  const data = await http<any>(`/api/notices/${noticeId}/unpublish/`, {
    method: "POST",
  });
  return mapNoticeFromApi(data);
}
