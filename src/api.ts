import {
  Tender,
  Project,
  Notification,
  User,
  UserRole,
  Milestone,
  VendorPrequalification,
  VendorPrequalificationSubmission,
  PaymentClaim,
  PaymentClaimSubmission,
  Disbursement,
  AuditLog,
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
        if (Array.isArray(value) && value.length) return String(value[0]);
        if (typeof value === "string") return value;
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
    organizationName: api.organization_name ?? undefined,
    organizationType: api.organization_type ?? undefined,
    technologyTypes: Array.isArray(api.technology_types) ? api.technology_types : undefined,
    status: api.status ?? "Active",
    mustChangePassword: api.must_change_password ?? false,
  };
}

function randomRef(): string {
  const n = Math.floor(100000 + Math.random() * 900000);
  return `REF-${n}`;
}

function mapTenderToApi(ui: Partial<Tender>): any {
  return {
    reference_number: ui.referenceNumber || randomRef(),
    name: ui.name ?? "",
    department: ui.department ?? "",
    category: ui.category ?? "",
    status: ui.status ?? "Draft",
    deadline: ui.deadline ?? new Date().toISOString(),
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
    last_date_submission: ui.lastDateSubmission ?? null,
    date_opening: ui.dateOpening ?? null,
    pre_tender_meeting_info: ui.preTenderMeetingInfo ?? "",
    bidders_schedule_purchase: ui.biddersSchedulePurchase ?? false,
    tender_security_required: ui.tenderSecurityRequired ?? false,
    contact_details: ui.contactDetails ?? "",
    technology_types: ui.technologyTypes ?? [],
    target_site_type: ui.targetSiteType ?? null,
    is_verified: ui.isVerified ?? false,
    funding_source: ui.fundingSource ?? null,
  };
}

function mapProjectFromApi(api: any): Project {
  return {
    id: String(api.id ?? ""),
    vendorId: api.vendor_id ?? "",
    vendorName: api.vendor_name ?? "",
    techType: api.tech_type ?? "",
    region: api.region ?? "",
    status: api.status ?? "Pre-Qualification",
    progress: Number(api.progress ?? 0),
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
    percentage: Number(api.percentage ?? 0),
    status: api.status ?? "Pending",
    amount: Number(api.amount ?? 0),
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
    techTier: api.tech_tier ?? undefined,
    yearsExperience: Number(api.years_experience ?? 0),
    priorProjects: Number(api.prior_projects ?? 0),
    annualRevenue: api.annual_revenue != null ? Number(api.annual_revenue) : undefined,
    districtsCovered: Number(api.districts_covered ?? 0),
    femaleBeneficiaryTarget: Number(api.female_beneficiary_target ?? 50),
    vulnerableGroupTarget: Number(api.vulnerable_group_target ?? 30),
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

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null;
  const initHeaders = headersInitToObject(init?.headers as HeadersInit | undefined);
  const skipAuth = Boolean(getHeaderValue(initHeaders, "X-Skip-Auth"));
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...initHeaders,
  };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === "x-skip-auth") {
      delete headers[key];
    }
  }
  if (token && !skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const { headers: _ignoredHeaders, ...requestInit } = init ?? {};

  const isAbsolute = /^https?:\/\//i.test(url);
  const requestUrls = isAbsolute
    ? [url]
    : API_BASE_CANDIDATES.map((base) => joinApiUrl(base, url));

  let lastError: Error | null = null;
  for (let i = 0; i < requestUrls.length; i += 1) {
    const requestUrl = requestUrls[i];
    const isLastAttempt = i === requestUrls.length - 1;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), requestTimeoutMs);
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
        lastError = new Error(`Request timed out after ${requestTimeoutMs}ms`);
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

// ============ API functions ============

export async function fetchTenders(): Promise<Tender[]> {
  const data = await http<any>(`/api/tenders/`);
  return unwrapListResponse<any>(data).map(mapTenderFromApi);
}

export async function createTender(payload: Partial<Tender>): Promise<Tender> {
  const body = JSON.stringify(mapTenderToApi(payload));
  const data = await http<any>(`/api/tenders/`, { method: "POST", body });
  return mapTenderFromApi(data);
}

export async function verifyTender(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/verify/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function publishTender(tenderId: string): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/publish/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return mapTenderFromApi(data);
}

export async function awardTender(
  tenderId: string,
  payload: { awardedVendorId?: string; awardedVendorName?: string }
): Promise<Tender> {
  const data = await http<any>(`/api/tenders/${tenderId}/award/`, {
    method: "POST",
    body: JSON.stringify({
      awarded_vendor_id: payload.awardedVendorId ?? "",
      awarded_vendor_name: payload.awardedVendorName ?? "",
    }),
  });
  return mapTenderFromApi(data);
}

export async function fetchProjects(): Promise<Project[]> {
  const data = await http<any>(`/api/projects/`);
  return unwrapListResponse<any>(data).map(mapProjectFromApi);
}

export async function fetchMilestones(projectId?: string): Promise<Milestone[]> {
  const query = projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  const data = await http<any>(`/api/projects/milestones/${query}`);
  return unwrapListResponse<any>(data).map(mapMilestoneFromApi);
}

export async function fetchNotifications(): Promise<Notification[]> {
  const data = await http<any>(`/api/notifications/`);
  return unwrapListResponse<any>(data).map(mapNotificationFromApi);
}

export async function fetchVendorPrequalifications(): Promise<VendorPrequalification[]> {
  const data = await http<any>(`/api/users/prequalifications/`);
  return unwrapListResponse<any>(data).map(mapVendorPrequalificationFromApi);
}

export async function submitVendorPrequalification(
  payload: VendorPrequalificationSubmission
): Promise<VendorPrequalification> {
  const data = await http<any>(`/api/users/prequalifications/`, {
    method: "POST",
    body: JSON.stringify({
      company_name: payload.companyName,
      organization_type: payload.organizationType ?? "",
      tax_id: payload.taxId ?? "",
      hq_address: payload.hqAddress ?? "",
      technology_types: payload.technologyTypes ?? [],
      registration_certificate_name: payload.registrationCertificateName ?? "",
      tech_tier: payload.techTier ?? "",
      years_experience: payload.yearsExperience ?? 0,
      prior_projects: payload.priorProjects ?? 0,
      annual_revenue: payload.annualRevenue ?? 0,
      districts_covered: payload.districtsCovered ?? 0,
      female_beneficiary_target: payload.femaleBeneficiaryTarget ?? 50,
      vulnerable_group_target: payload.vulnerableGroupTarget ?? 30,
      declaration_accepted: payload.declarationAccepted,
    }),
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

export async function registerVendor(payload: {
  username: string;
  password: string;
  fullName: string;
  email: string;
  gender: "Male" | "Female" | "Other";
  organizationName: string;
  organizationType: string;
  technologyTypes: string[];
  region?: string;
}): Promise<User> {
  const body = JSON.stringify({
    username: payload.username,
    password: payload.password,
    full_name: payload.fullName,
    email: payload.email,
    gender: payload.gender,
    role: UserRole.VENDOR,
    organization_name: payload.organizationName,
    organization_type: payload.organizationType,
    technology_types: payload.technologyTypes,
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
