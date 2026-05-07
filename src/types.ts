/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export enum UserRole {
  RBF_OFFICIAL = "RBF Management Team",
  TAC = "TAC Member",
  DOE_OFFICER = "DoE Officer",
  FIELD_VERIFIER = "Field Verifier",
  VENDOR = "Vendor",
  ADMIN = "Platform Administrator (Super Admin)",
  UNDP_DONOR = "Project Steering Committee",
  AUDITOR = "Auditor",
}

export type ReportFormat = "csv" | "pdf" | "excel";

export interface ReportTemplate {
  id: string;
  title: string;
  description: string;
  formats: ReportFormat[];
  category?: string;
  quick?: boolean;
}

export interface ReportHistoryItem {
  id: string;
  reportType: string;
  format: ReportFormat;
  generatedAt: string;
  notes?: string;
  project?: string;
  generatedBy?: string;
  downloadUrl?: string;
}

export enum TenderStatus {
  DRAFT = "Draft",
  PUBLISHED = "Published",
  EVALUATION = "Evaluation",
  AWARDED = "Awarded",
  CLOSED = "Closed",
}

export enum BidStatus {
  DRAFT = "Draft",
  SUBMITTED = "Submitted",
  SHORTLISTED = "Shortlisted",
  UNDER_REVIEW = "Under Review",
  REVISION_REQUIRED = "Revision Required",
  AWARDED = "Awarded",
  NOT_AWARDED = "Not Awarded",
  ACCEPTED = "Accepted",
  REJECTED = "Rejected",
  WITHDRAWN = "Withdrawn",
}

export enum BidStage1Status {
  DRAFT = "Draft",
  SUBMITTED = "Submitted",
  SHORTLISTED = "Shortlisted",
  REJECTED = "Rejected",
}

export enum BidStage2Status {
  DRAFT = "Draft",
  SUBMITTED = "Submitted",
  EVALUATED = "Evaluated",
  AWARDED = "Awarded",
  NOT_AWARDED = "Not Awarded",
}

export enum ProjectStatus {
  SETUP_PENDING = "setup_pending",
  ACTIVE = "active",
  PRE_QUALIFICATION = "Pre-Qualification",
  SITE_SPECIFIC = "Site-Specific Proposal",
  CONTRACTING = "Contracting",
  INSTALLATION = "Installation",
  VERIFICATION = "Field Verification",
  DISBURSEMENT = "Disbursement",
  HALTED = "Halted",
  COMPLETED = "Completed",
}

export type UserStatus = 
  | "Active" 
  | "Pending" 
  | "Inactive" 
  | "Registered" 
  | "Suspended" 
  | "Blacklisted"
  | "Reinstated" 
  | "Requalified"
  // Pre-qualification statuses
  | "Prequalification Rejected"
  | "Prequalification Under Review"
  // Blacklist statuses (mapped from backend)
  | "Initiated"
  | "Under Review"
  | "Expired";

export interface BlacklistSummary {
  case_id: string;
  status: string;
  reason: string;
  expiry_date?: string | null;
  cooling_off_until?: string | null;
  is_permanent?: boolean;
  banner: string;
  appeal_allowed?: boolean;
}

export interface VendorBlacklistCase {
  id: string;
  vendor: string;
  vendorUsername?: string;
  reason: string;
  description?: string;
  justificationDocument?: string;
  status: string;
  initiatedBy?: string;
  initiatedByUsername?: string;
  initiatedAt?: string;
  noticeSentAt?: string;
  coolingOffUntil?: string | null;
  reviewedBy?: string;
  reviewedByUsername?: string;
  reviewedAt?: string;
  reviewNotes?: string;
  confirmedBy?: string;
  confirmedByUsername?: string;
  confirmedAt?: string;
  finalDecisionNotes?: string;
  isPermanent?: boolean;
  expiryDate?: string | null;
  reinstatedAt?: string | null;
  reinstatedBy?: string;
  reinstatedByUsername?: string;
}

export interface BlacklistAppeal {
  id: string;
  case: string;
  vendor: string;
  vendorUsername?: string;
  rebuttalText?: string;
  rebuttalDocument?: string;
  status: string;
  submittedAt?: string;
  reviewedBy?: string;
  reviewedByUsername?: string;
  reviewedAt?: string;
  resolutionNotes?: string;
}

export interface Tender {
  id: string;
  referenceNumber: string;
  name: string;
  department: string;
  category: string;
  status: TenderStatus;
  deadline: string;
  budget?: number;
  applicationType?: "Access Window" | "Application Window";
  stageType?: "Stage 1: Concept" | "Stage 2: Detailed" | "Pre-Qualification" | "Site-Specific";
  procurementMethod?: string;
  addressForDocument?: string;
  addressForSecurity?: string;
  placeForOpening?: string;
  biddersEligibility?: string;
  timeForCompletion?: string;
  invitedBy?: string;
  biddingCurrency?: string;
  instruction?: string;
  lastDateSecurity?: string;
  lastDateSubmission?: string;
  dateOpening?: string;
  preTenderMeetingInfo?: string;
  biddersSchedulePurchase?: boolean;
  tenderSecurityRequired?: boolean;
  contactDetails?: string;
  technologyTypes?: string[];
  targetDistricts?: string[];
  targetSiteType?: "Household" | "Business" | "School" | "Clinic";
  isVerified?: boolean;
  fundingSource?: string;
  minimumServiceTier?: string;
  approximateInstallationTarget?: number;
  technicalWeight?: number;
  financialWeight?: number;
  technicalThreshold?: number;
  coolingOffDays?: number;
  scheduleFile?: string;
  rfpDocumentsFile?: string;
  milestonePaymentScheduleFile?: string;
  intentToAwardBidId?: string;
  intentToAwardAt?: string;
  coolingOffUntil?: string;
  createdAt?: string;
  updatedAt?: string;
  publishedAt?: string;
  verifiedAt?: string;
  awardedAt?: string;
  closedAt?: string;
  awardedVendorName?: string;
  awardedVendorId?: string;
  bidCount?: number;
}

export interface TenderBidSite {
  id?: string;
  siteName: string;
  district?: string;
  villageSubDistrict?: string;
  latitude?: number;
  longitude?: number;
  estimatedHouseholds?: number;
  numberOfHouseholds?: number;
  targetTechnology?: string;
  targetBeneficiaryType?: "female_headed" | "vulnerable" | "low_income" | "standard";
  estimatedEnergyDemandKwhMonth?: number;
  roadAccessAvailable?: boolean;
  notes?: string;
}

export interface TenderBid {
  id: string;
  tender: string;
  tender_reference?: string;
  tender_name?: string;
  tender_status?: TenderStatus | string;
  tender_intent_to_award_at?: string;
  tender_intent_to_award_bid_id?: string;
  tender_awarded_at?: string;
  tender_awarded_vendor_id?: string;
  tender_awarded_vendor_name?: string;
  vendor_id: string;
  vendor_name: string;
  vendor_email?: string;
  preferred_district?: string;
  technology_types?: string[];
  bid_amount?: number;
  subsidy_requested?: number;
  stage?: string;
  stage_key?: string;
  stage_badge?: string;
  technology_type?: string;
  tender_technology_types?: string[];
  device_brand?: string;
  device_model?: string;
  co_financing_amount?: number;
  concept_note?: string;
  technical_proposal?: string;
  financial_proposal?: string;
  device_brand_model?: string;
  tech_tier?: "Tier 1" | "Tier 2" | "Tier 3" | "Tier 4" | "Tier 5";
  energy_target_kwh_month?: number;
  energy_target?: number;
  system_configuration?: {
    technology_type?: string;
    co_financing_amount_lsl?: number;
    device_brand?: string;
    device_model?: string;
    system_capacity?: number;
    system_capacity_unit?: string;
    rated_power_w?: number;
    battery_capacity_wh?: number;
    pv_panel_size_w?: number;
    inverter_type?: string;
  };
  boq_details?: Array<{
    item_number?: number;
    description: string;
    qty: number;
    unit: string;
    unit_price: number;
    total?: number;
  }>;
  boq_items?: Array<{
    item_number?: number;
    description: string;
    qty: number;
    unit: string;
    unit_price: number;
    total?: number;
  }>;
  technical_proposal_file?: string;
  financial_proposal_file?: string;
  boq_file?: string;
  gender_action_plan_file?: string;
  implementation_plan_file?: string;
  om_plan_file?: string;
  om_plan_document?: string;
  reporting_templates_file?: string;
  distribution_map_file?: string;
  tender_security_file?: string;
  female_target_pct?: number;
  gender_inclusion_target?: number;
  vulnerable_target_pct?: number;
  vulnerable_group_target?: number;
  low_income_target_pct?: number;
  low_income_target?: number;
  inclusion_commitment_confirmed?: boolean;
  om_strategy_summary?: string;
  local_technicians_to_be_trained?: number;
  warranty_period_months?: number;
  warranty_period?: number;
  offer_paygo?: boolean;
  paygo_platform?: string;
  daily_payment_amount_lsl?: number;
  collection_method?: string;
  technical_summary?: string;
  financial_summary?: string;
  aftersales_description?: string;
  service_tier?: "Tier 1" | "Tier 2" | "Tier 3" | "Tier 4" | "Tier 5";
  stage_two_unlocked?: boolean;
  stage_two_unlocked_at?: string;
  stage_two_source_bid?: string;
  stage_two_ready?: boolean;
  document_requirements?: Array<{ field: string; required: boolean; uploaded: boolean }>;
  document_counts?: { uploaded: number; required: number };
  deadline?: string;
  deadline_passed?: boolean;
  deadline_countdown_seconds?: number;
  is_locked?: boolean;
  evaluation_status?: "pending" | "technical_scored" | "evaluated";
  technical_score_total?: number;
  financial_score_total?: number;
  version_history?: Array<{
    id: string;
    version_number: number;
    status: BidStatus;
    updated_at?: string;
    submitted_at?: string;
  }>;
  status: BidStatus;
  version_number: number;
  submitted_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
  rejection_reason?: string;
  created_at?: string;
  updated_at?: string;
  sites?: TenderBidSite[];
}

export interface Project {
  id: string;
  tenderId?: string;
  projectTitle?: string;
  projectReference?: string;
  tenderReferenceNumber?: string;
  tenderName?: string;
  tenderBudget?: number;
  tenderDeadline?: string;
  tenderAwardedAt?: string;
  tenderStatus?: string;
  contractReference?: string;
  contractStatus?: string;
  contractSignedFile?: string;
  milestoneTotalAmount?: number;
  milestoneCount?: number;
  milestonePlanId?: string;
  vendorId: string;
  vendorName: string;
  techType: string;
  region: string;
  district?: string;
  status: ProjectStatus;
  progress: number;
  startDate?: string;
  endDate?: string;
  budget?: number;
  targetInstallations?: number;
  targetFemalePct?: number;
  targetVulnerablePct?: number;
  targetLowIncomePct?: number;
  targetBeneficiaries?: number;
  projectDurationMonths?: number;
  verificationMethod?: string;
  deploymentTeamRoster?: string;
  deploymentEquipmentPlan?: string;
  deploymentSiteStatus?: string;
  deploymentWorkSchedule?: string;
  deploymentPermitsStatus?: string;
  deviceBrand?: string;
  deviceModel?: string;
  deviceTechTier?: string;
  verificationMethodConfirmed?: boolean;
  setupCompletedAt?: string;
  projectSetup?: ProjectSetup;
  claimCount?: number;
  unresolvedFlagCount?: number;
  latestAuditEntry?: AuditLog;
contractValue?: number;
  awardedBidDeviceInfo?: {
    device_brand?: string;
    device_model?: string;
  };
  energyOutput: number; // kWh
  uptime: number; // %
  genderImpact: number; // % female beneficiaries
}

export type ProjectSetupSiteStatus = "ready" | "in_progress" | "not_started";

export interface ProjectSetup {
  id?: string;
  projectId?: string;
  vendorId?: string;
  teamRosterFile?: string;
  teamRosterFileUrl?: string;
  equipmentPlanFile?: string;
  equipmentPlanFileUrl?: string;
  siteStatus?: ProjectSetupSiteStatus;
  workScheduleStart?: string;
  workScheduleEnd?: string;
  complianceDocsFile?: string;
  complianceDocsFileUrl?: string;
  insuranceCertificateFile?: string;
  insuranceCertificateFileUrl?: string;
  deviceModel?: string;
  deviceBrand?: string;
  techTier?: number;
  meterApiEndpoint?: string;
  hasMeterApiToken?: boolean;
  manualVerificationConfirmed?: boolean;
  checklistTeamReady?: boolean;
  checklistEquipmentReady?: boolean;
  checklistSiteReady?: boolean;
  checklistSafetyReady?: boolean;
  checklistLogisticsReady?: boolean;
  setupCompletedAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface KpiMetricStatus {
  count?: number;
  percentage: number;
  target: number;
  met: boolean;
}

export interface ProjectKpiSummary {
  project: {
    id: string;
    project_reference?: string;
    project_title?: string;
    vendor_name: string;
    technology_type: string;
    district?: string;
    status: string;
    start_date?: string | null;
    end_date?: string | null;
    target_installations: number;
  };
  installation_progress: {
    submitted: number;
    verified: number;
    pending: number;
    flagged: number;
    target: number;
    progress_pct: number;
    expected_progress_pct: number;
    on_track: boolean;
  };
  gender_kpi: {
    total_verified: number;
    female_headed: KpiMetricStatus;
    vulnerable: KpiMetricStatus;
    low_income: KpiMetricStatus;
    standard: { count: number; percentage: number };
    female_trend_pct_vs_last_week: number;
    female_trending_up: boolean;
    all_gender_kpis_met: boolean;
    all_kpis_met?: boolean;
  };
  energy_kpi: {
    monthly_data: Array<{
      month: string;
      total_kwh: number;
      target_kwh: number;
      achievement_pct: number;
      active_devices: number;
    }>;
    current_month_kwh: number;
    current_month_target: number;
    current_month_pct: number;
    on_track: boolean;
  };
  uptime_kpi: {
    average_uptime_pct: number;
    target_uptime_pct: number;
    met: boolean;
    devices_above_target: number;
    devices_below_target: number;
    devices_offline: number;
    total_devices_monitored: number;
    distribution: Record<string, number>;
  };
  installation_trend: {
    weeks: Array<{
      week_start: string;
      cumulative_verified: number;
      weekly_new: number;
      target_at_this_week: number;
    }>;
    target_line?: number[];
    total_verified: number;
    target: number;
  };
  milestone_eligibility: Record<string, { eligible: boolean; status?: string; conditions: Record<string, boolean> }>;
  generated_at: string;
}

export interface PortfolioKpiSummary {
  scope_label?: string;
  total_projects: number;
  total_installations_target: number;
  total_verified: number;
  overall_progress_pct: number;
  overall_female_pct: number;
  overall_female_met: boolean;
  overall_uptime_pct: number;
  projects_at_risk: number;
  projects_on_track: number;
  projects_completed: number;
  total_paid_amount?: number;
  pending_claims?: number;
  national_main_program_budget?: number;
  projects: Array<{
    project_id: string;
    project_reference: string;
    project_title: string;
    vendor_name: string;
    technology: string;
    district?: string;
    progress_pct: number;
    female_pct: number;
    uptime_pct: number;
    energy_kwh?: number;
    status: string;
  }>;
}

export interface User {
  id: string;
  username?: string;
  fullName: string;
  email: string;
  role: UserRole;
  gender: "Male" | "Female" | "Other";
  region?: string;
  district?: string;
  districts?: string[];
  mobileNumber?: string;
  nationalId?: string;
  address?: string;
  organizationName?: string;
  organizationType?: string;
  associatedEntities?: string[];
  technologyTypes?: string[];
  registrationCertificateName?: string;
  taxId?: string;
  deviceId?: string;
  tierAssignment?: string;
  verificationZone?: string;
  status: UserStatus;
  isActive?: boolean;
  mustChangePassword?: boolean;
  roleLabel?: string;
  lastLogin?: string;
  recentAuditLogs?: Array<{
    id: string;
    action: string;
    module?: string;
    recordId?: string | number;
    recordType?: string;
    createdAt?: string;
  }>;
  prospectSyncStatus?: ProspectSyncLog[];
  vendorTag?: string | null;
  blacklistSummary?: BlacklistSummary | null;
}

export interface Organization {
  id: string;
  name: string;
  type: "Government" | "International" | "NGO";
  contactPerson?: string;
  email?: string;
  phone?: string;
  address?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface PlatformConfiguration {
  id?: string;
  platformName: string;
  countryCode: string;
  countryName: string;
  defaultCurrency: string;
  nationalMainProgramBudget: number;
  timezone: string;
  femaleTargetMinimum: number;
  vulnerableTargetMinimum: number;
  lowIncomeTargetMinimum: number;
  uptimeTarget: number;
  anomalyDeviationThreshold: number;
  gpsDuplicateRadiusM: number;
  gpsVerificationMaxDistanceM: number;
  m2VerificationRequiredPct: number;
  m3VerificationRequiredPct: number;
  emailNotificationsEnabled: boolean;
  smsNotificationsEnabled: boolean;
  maxFileSizeMb: number;
  allowedFileTypes: string[];
  lesothoBoundary?: {
    path: string;
    exists: boolean;
    lastModified?: string | null;
  };
}

export interface SystemHealthPayload {
  database: {
    status: string;
    error?: string | null;
    slowQueriesLast24h: number;
    tableSizes: Record<string, number>;
  };
  queue: {
    workerStatus: string;
    pendingJobsCount: number;
    failedJobsCount: number;
    processingRateLast24h: number;
  };
  scheduler: {
    status: string;
    lastMonthlyReportSync?: string | null;
  };
  prospectApi: {
    status: string;
  };
  storage: {
    totalBytes: number;
    usedBytes: number;
    freeBytes: number;
    filesUploadedToday: number;
  };
  errors: Array<{
    id: string;
    methodName: string;
    errorMessage?: string;
    updatedAt?: string;
  }>;
}

export interface SuperAdminDashboardSummary {
  stats: {
    totalUsers: number;
    activeProjects: number;
    totalVendors: number;
    pendingPrequalifications: number;
  };
  systemHealth: SystemHealthPayload;
  recentActivity: Array<{
    id: string;
    timestamp?: string;
    actor: string;
    role?: string;
    action: string;
    module?: string;
    record?: string;
    notes?: string;
    oldStatus?: string;
    newStatus?: string;
  }>;
  prospectSyncSummary: {
    failedJobs: number;
    lastSyncAt?: string | null;
  };
}

export interface ProspectSyncLog {
  id: string;
  methodName: string;
  status: string;
  attempts: number;
  payload?: unknown;
  errorMessage?: string;
  createdAt?: string;
  updatedAt?: string;
  recordId?: string;
  recordType?: string;
}

export interface TenderBidEvaluation {
  id: string;
  bid: string;
  evaluator?: string;
  evaluatorUsername?: string;
  evaluatorRole?: UserRole;
  status: "Pending" | "Scored";
  technicalScore: number;
  financialScore: number;
  feasibilityScore: number;
  kpiScore: number;
  genderScore: number;
  environmentalScore: number;
  omScore: number;
  inclusivityScore: number;
  totalScore: number;
  comments?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface TenderAwardRankingRow {
  rank: number;
  bid_id: string;
  vendor_id: string;
  vendor_name: string;
  bid_amount: number;
  technical_score?: number | null;
  financial_score?: number | null;
  combined_score?: number | null;
  gender_score?: number | null;
  female_headed_household_target?: number;
  passed_technical_threshold: boolean;
  financial_opened: boolean;
  is_recommended_winner: boolean;
  disqualification_reason?: string;
}

export interface TenderContract {
  id: string;
  tender: string;
  bid?: string;
  vendorId: string;
  vendorName: string;
  vendorEmail?: string;
  referenceNumber: string;
  templateName?: string;
  status: "Generated" | "Submitted" | "Signed" | "Approved" | "Rejected";
  signatureStatus?: "awaiting" | "uploaded" | "approved";
  generatedFile?: string;
  signedFile?: string;
  annexAFile?: string;
  annexBFile?: string;
  annexCFile?: string;
  annexDFile?: string;
  annexEFile?: string;
  signedAt?: string;
  approvedAt?: string;
  approvedBy?: string;
  rejectionReason?: string;
  milestonePlanId?: string;
  projectId?: string;
  generatedAt?: string;
  updatedAt?: string;
}

export interface Milestone {
  id: string;
  projectId: string;
  milestoneNumber?: number;
  disbursementPct?: number;
  name: string;
  description?: string;
  percentage: number;
  status: "locked" | "pending" | "claimable" | "claimed" | "paid" | "Pending" | "Submitted" | "Verified" | "Paid";
  amount: number;
  progressPercentage: number;
  targetDate?: string;
  completedDate?: string;
  unlockedAt?: string;
  amountLsl?: number;
}

export interface ProjectUpdate {
  id: string;
  projectId: string;
  title?: string;
  body: string;
  author?: string;
  authorUsername?: string;
  createdAt: string;
}

export interface ProjectDocument {
  id: string;
  projectId: string;
  title?: string;
  file: string;
  uploadedBy?: string;
  uploadedByUsername?: string;
  uploadedAt: string;
}

export type InstallationStatus = "Submitted" | "Verified" | "Flagged";
export type VerificationStatus = "Pending" | "Paused" | "Partial" | "Verified" | "Flagged" | "Terminated";

export interface InstallationReport {
  id: string;
  projectId: string;
  vendorId: string;
  vendorUsername?: string;
  milestoneId?: string;
  gpsLat: number;
  gpsLng: number;
  serialNumber: string;
  beneficiaryId: string;
  receiptFile?: string;
  receiptFileUrl?: string;
  photoFiles: string[];
  meterId?: string;
  kwhReading?: number;
  status: InstallationStatus;
  submittedAt: string;
  beneficiaryName?: string;
  householdType?: string;
  verificationStatus?: string;
  verifiedBy?: string;
  gisStatus?: "green" | "yellow" | "red";
}

export interface SmartMeterReading {
  id: string;
  projectId: string;
  installationId?: string;
  meterId: string;
  kwh: number;
  uptimePct?: number;
  recordedAt: string;
  createdAt: string;
}

export interface VerificationTask {
  id: string;
  report: string;
  assignedVerifier?: string;
  assignedVerifierUsername?: string;
  vendorLat: number;
  vendorLng: number;
  verifierLat?: number;
  verifierLng?: number;
  distanceMeters?: number;
  anomalyFlag: boolean;
  status: VerificationStatus;
  createdAt: string;
  updatedAt: string;
  concernMessage?: string;
}

export interface MapInstallationRecord {
  id: string;
  projectId: string;
  latitude: number;
  longitude: number;
  gisStatus: "green" | "yellow" | "red";
  verificationStatus: string;
  technologyType: string;
  householdType?: string;
  vendorName: string;
  beneficiaryName: string;
  serialNumber?: string;
  district: string;
  installationDate?: string;
  uptimePct?: number;
}

export interface MapInstallationSummary {
  total: number;
  verified: number;
  pending: number;
  flagged: number;
}

export interface MapInstallationsResponse {
  installations: MapInstallationRecord[];
  summary: MapInstallationSummary;
  truncated?: boolean;
}

export enum NotificationChannel {
  EMAIL = "Email",
  SMS = "SMS",
  IN_APP = "In-App",
}

export enum NotificationStatus {
  SENT = "Sent",
  DELIVERED = "Delivered",
  READ = "Read",
  FAILED = "Failed",
}

export interface Notification {
  id: string;
  recipientId: string;
  recipientName: string;
  type: NotificationChannel;
  event: string;
  title: string;
  body: string;
  status: NotificationStatus;
   timestamp: string;
   linkedEntityId?: string; // Tender ID, Bid ID, etc.
}

export enum NoticeCategory {
  TENDER = "tender",
  DEADLINE = "deadline",
  AWARD = "award",
  CLARIFICATION = "clarification",
  TRAINING = "training",
  GENERAL = "general",
}

export enum NoticeStatus {
  DRAFT = "draft",
  PUBLISHED = "published",
}

export interface Notice {
  id: string;
  notice_id: string;
  title: string;
  category: NoticeCategory;
  summary: string;
  content: string;
  linked_tender?: string | null;
  tender_reference?: string | null;
  tender_name?: string | null;
  is_pinned: boolean;
  show_countdown: boolean;
  countdown_date?: string | null;
  status: NoticeStatus;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type PrequalificationStatus =
  | "Pending"
  | "Under Review"
  | "Approved"
  | "Partial (Resubmit)"
  | "Rejected";

export interface VendorPrequalification {
  id: string;
  vendorId?: string;
  vendorUsername?: string;
  companyName: string;
  organizationType?: string;
  taxId?: string;
  hqAddress?: string;
  technologyTypes: string[];
  registrationCertificateName?: string;
  tradingLicense?: string; // File URL
  registrationCertificate?: string; // File URL
  taxComplianceCertificate?: string; // File URL
  authorizedSignatoryId?: string; // File URL
  experienceFinancialProof?: string; // File URL
  techTier?: string;
  yearsExperience: number;
  priorProjects: number;
  annualRevenue?: number;
  districtsCovered: number;
  femaleBeneficiaryTarget: number;
  vulnerableGroupTarget: number;
  bankName?: string;
  bankBranch?: string;
  bankSwiftCode?: string;
  bankSortCode?: string;
  bankAccountName?: string;
  bankAccountNumber?: string;
  contactNumber?: string;
  email?: string;
  genderOfFocalPerson?: string;
  declarationAccepted: boolean;
  reviewerComments?: string;
  status: PrequalificationStatus;
  submittedAt: string;
  reviewedAt?: string;
  reviewedBy?: string;
  reviewedByUsername?: string;
}

export interface VendorBankDetails {
  vendorLegalName?: string;
  vendorBankName?: string;
  vendorBankBranch?: string;
  vendorBankSwiftCode?: string;
  vendorBankSortCode?: string;
  vendorAccountHolderName?: string;
  vendorAccountNumber?: string;
}

export interface DisbursementSheet extends VendorBankDetails {
  claimId?: string;
  projectId?: string;
  claimStatus?: PaymentClaimStatus;
  totalApprovedAmount?: number;
}

export interface VendorPrequalificationSubmission {
  companyName: string;
  organizationType?: string;
  taxId?: string;
  hqAddress?: string;
  technologyTypes: string[];
  registrationCertificateName?: string;
  tradingLicense?: File;
  techTier?: string;
  yearsExperience?: number;
  priorProjects?: number;
  annualRevenue?: number;
  districtsCovered?: number;
  femaleBeneficiaryTarget?: number;
  vulnerableGroupTarget?: number;
  bankName?: string;
  bankBranch?: string;
  bankSwiftCode?: string;
  bankSortCode?: string;
  bankAccountName?: string;
  bankAccountNumber?: string;
  contactNumber?: string;
  email?: string;
  genderOfFocalPerson?: string;
  declarationAccepted: boolean;
  registrationCertificate?: File;
  taxComplianceCertificate?: File;
  authorizedSignatoryId?: File;
  experienceFinancialProof?: File;
}

export interface VendorProfile {
  id: string;
  username: string;
  email: string;
  full_name: string;
  gender: string;
  role: string;
  mobile_number: string;
  national_id?: string;
  address?: string;
  organization_name?: string;
  organization_type?: string;
  technology_types: string[];
  registration_certificate_name?: string;
  tax_id?: string;
  bank_name?: string;
  bank_branch?: string;
  bank_swift_code?: string;
  bank_sort_code?: string;
  bank_account_name?: string;
  bank_account_number?: string;
  tier_assignment?: string;
  verification_zone?: string;
  region?: string;
  status: string;
  date_joined: string;
  last_login?: string;
  prequalification?: {
    status: string;
    approved_at?: string;
    submitted_at?: string;
    company_name?: string;
    organization_type?: string;
    tax_id?: string;
    hq_address?: string;
    tech_tier?: string;
    technology_types: string[];
    female_beneficiary_target: number;
    vulnerable_group_target: number;
    years_experience: number;
    prior_projects: number;
    annual_revenue?: number;
    districts_covered: number;
    contact_number?: string;
    email?: string;
    gender_of_focal_person?: string;
    bank_name?: string;
    bank_branch?: string;
    bank_swift_code?: string;
    bank_sort_code?: string;
    bank_account_name?: string;
    bank_account_number?: string;
    trading_license?: string;
    registration_certificate?: string;
    tax_compliance_certificate?: string;
    authorized_signatory_id?: string;
    experience_financial_proof?: string;
  };
  blacklist_status: {
    status: string;
    reason?: string;
    description?: string;
    expiry_date?: string;
    is_permanent?: boolean;
    initiated_at?: string;
    reviewed_at?: string;
    confirmed_at?: string;
    reinstated_at?: string;
  };
  bid_count: number;
  project_count: number;
  total_contract_value: number;
  documents?: {
    prequalification_documents: Array<{
      label: string;
      category: string;
      url: string;
      uploaded_at?: string;
    }>;
    project_documents: Array<{
      id: string;
      project_id: string;
      project_reference?: string;
      title: string;
      url: string;
      uploaded_at?: string;
      uploaded_by?: string;
    }>;
    contract_documents: Array<{
      contract_id: string;
      reference_number?: string;
      title: string;
      url: string;
      uploaded_at?: string;
    }>;
  };
  bids_data?: {
    summary: {
      total_bids: number;
      awarded: number;
      accepted: number;
      rejected: number;
      pending: number;
      win_rate_pct: number;
    };
    bids: TenderBid[];
    evaluations: TenderBidEvaluation[];
    contracts: TenderContract[];
  } | null;
  projects_data?: {
    projects: Project[];
    recent_updates: Array<{
      id: string;
      project_id: string;
      project_reference?: string;
      title?: string;
      body: string;
      created_at: string;
      author_name?: string;
    }>;
    recent_documents: Array<{
      id: string;
      project_id: string;
      project_reference?: string;
      title: string;
      url: string;
      uploaded_at?: string;
    }>;
  };
  performance_data?: {
    kpi_rows: Array<{
      label: string;
      target: string;
      achieved: string;
      status: string;
    }>;
    installation_summary: {
      submitted: number;
      verified: number;
      flagged: number;
      paused: number;
      terminated: number;
      verification_rate_pct: number;
    };
    anomaly_summary: {
      total: number;
      resolved: number;
      unresolved: number;
      by_type: Array<{
        flag_type: string;
        count: number;
        resolved: number;
        unresolved: number;
      }>;
    };
    meter_summary: {
      average_uptime_pct: number;
      total_energy_kwh: number;
      target_energy_kwh: number;
      reading_count: number;
    };
    performance_notes: Array<{
      id: string;
      created_at: string;
      author_name?: string;
      author_role?: string;
      title?: string;
      body: string;
    }>;
  };
  payments_data?: {
    summary: {
      total_contracted_value: number;
      total_disbursed: number;
      total_pending: number;
    };
    claims: PaymentClaim[];
  } | null;
  audit_trail?: {
    limited: boolean;
    entries: AuditLog[];
  } | null;
  prospect_sync_logs?: ProspectSyncLog[];
}

export interface VendorDirectoryEntry {
  id: string;
  username: string;
  fullName: string;
  email: string;
  organizationName?: string;
  organizationType?: string;
  technologyTypes: string[];
  region?: string;
  status: string;
  vendorTag?: string;
  lastLogin?: string;
  prequalificationStatus?: string;
  prequalificationApprovedAt?: string;
  blacklistStatus?: string;
  operationalStanding: "Active" | "Suspended" | "Blacklisted" | "Reinstated";
  projectCount: number;
  bidCount: number;
}

export type PaymentClaimStatus =
  | "Submitted"
  | "RMT Approved"
  | "TAC Endorsed"
  | "PSC Approved"
  | "Completed"
  | "Pending"
  | "Verified"
  | "Approved"
  | "Paid"
  | "Rejected";
export type DisbursementStatus = "Initiated" | "Completed" | "Failed";

export interface Disbursement {
  id: string;
  claimId: string;
  amount: number;
  status: DisbursementStatus;
  reference?: string;
  notes?: string;
  processedBy?: string;
  processedByUsername?: string;
  processedAt?: string;
}

export interface PaymentClaim {
  id: string;
  projectId: string;
  vendorId: string;
  milestoneId?: string;
  milestone_details?: Milestone;
  completionDate?: string;
  claimAmount: number;
  actualBeneficiaries: number;
  actualFemaleBeneficiaries: number;
  implementationNotes?: string;
  evidenceFiles: string[];
  declarationAccepted: boolean;
  status: PaymentClaimStatus;
  submittedAt: string;
  verifiedAt?: string;
  approvedAt?: string;
  paidAt?: string;
  paymentReference?: string;
  remarks?: string;
  reviewedBy?: string;
  reviewedByUsername?: string;
  vendorUsername?: string;
  vendorLegalName?: string;
  vendorBankName?: string;
  vendorBankBranch?: string;
  vendorBankSwiftCode?: string;
  vendorBankSortCode?: string;
  vendorAccountHolderName?: string;
  vendorAccountNumber?: string;
  disbursement?: Disbursement;
  paymentLocked?: boolean;
  paymentLockReason?: string;
}

export interface PaymentClaimSubmission {
  projectId: string;
  milestoneId?: string;
  completionDate?: string;
  claimAmount: number;
  actualBeneficiaries: number;
  actualFemaleBeneficiaries: number;
  implementationNotes?: string;
  evidenceFiles?: string[];
  declarationAccepted: boolean;
}

export interface AuditLog {
  id: string;
  action: string;
  entityType: string;
  entityId: string;
  details: Record<string, any>;
  actor?: string;
  actorUsername?: string;
  createdAt: string;
  notes?: string;
  recordId?: string;
  recordType?: string;
  actorRole?: string;
  module?: string;
  oldStatus?: string;
  newStatus?: string;
}

export interface AnomalyFlag {
  id: string;
  installation: string;
  project: string;
  flagType: string;
  description?: string;
  isResolved: boolean;
  createdAt: string;
  resolvedAt?: string;
}

export enum ConcernType {
  KPI_ISSUE = "kpi_issue",
  GPS_ISSUE = "gps_issue",
  VERIFICATION_ISSUE = "verification_issue",
  VENDOR_BEHAVIOUR = "vendor_behaviour",
  INSTALLATION_QUALITY = "installation_quality",
  DATA_DISCREPANCY = "data_discrepancy",
  OTHER = "other",
}

export enum ConcernSeverity {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  CRITICAL = "critical",
}

export enum ConcernStatus {
  OPEN = "open",
  UNDER_INVESTIGATION = "under_investigation",
  RESOLVED = "resolved",
  DISMISSED = "dismissed",
  ESCALATED_TO_PSC = "escalated_to_psc",
}

export interface Concern {
  id: string;
  raisedBy: string;
  raisedByUsername?: string;
  raisedByRole: "doe" | "auditor";
  raisedByRegion?: string;
  concernType: ConcernType;
  severity: ConcernSeverity;
  linkedProject?: string;
  linkedProjectName?: string;
  linkedProjectVendor?: string;
  linkedProjectDistrict?: string;
  linkedInstallation?: string;
  linkedClaim?: string;
  description: string;
  evidenceFiles?: Array<{ url: string; name: string }>;
  status: ConcernStatus;
  createdAt: string;
  updatedAt?: string;
  notifyRmt?: boolean;
  notifyPsc?: boolean;
  responses?: ConcernResponse[];
}

export interface ConcernResponse {
  id: string;
  concernId: string;
  respondedBy: string;
  respondedByUsername?: string;
  respondedByRole?: string;
  responseText: string;
  actionTaken: "under_investigation" | "action_initiated" | "resolved" | "escalated_to_psc" | "dismissed" | "issue_confirmed" | "payment_suspended" | "blacklist_initiated";
  evidenceFiles?: Array<{ url: string; name: string }>;
  createdAt: string;
}

export enum FindingCategory {
  PAYMENT_COMPLIANCE = "payment_compliance",
  APPROVAL_CHAIN_VIOLATION = "approval_chain_violation",
  DATA_INTEGRITY = "data_integrity",
  GPS_LOCATION_FRAUD = "gps_location_fraud",
  KPI_MANIPULATION = "kpi_manipulation",
  DOCUMENT_IRREGULARITY = "document_irregularity",
  PROCESS_VIOLATION = "process_violation",
  CONFLICT_OF_INTEREST = "conflict_of_interest",
  OTHER_COMPLIANCE = "other_compliance",
}

export enum RiskLevel {
  OBSERVATION = "observation",
  MINOR_FINDING = "minor_finding",
  MAJOR_FINDING = "major_finding",
  CRITICAL = "critical",
}

export interface AuditFinding {
  id: string;
  findingReference?: string;
  raisedBy: string;
  raisedByUsername?: string;
  raisedByRole?: string;
  raisedByRegion?: string;
  findingCategory: FindingCategory;
  riskLevel: RiskLevel;
  linkedProject?: string;
  linkedProjectName?: string;
  linkedProjectVendor?: string;
  linkedProjectDistrict?: string;
  linkedClaim?: string;
  linkedInstallation?: string;
  linkedAuditLog?: string;
  description: string;
  recommendedAction?: string;
  evidenceFiles?: Array<{ url: string; name: string }>;
  status: ConcernStatus;
  rmtResponse?: string;
  rmtActionTaken?: string;
  rmtRespondedAt?: string;
  pscComment?: string;
  pscCommentedAt?: string;
  pscNotified?: boolean;
  superAdminNotified?: boolean;
  createdAt: string;
  updatedAt?: string;
}
