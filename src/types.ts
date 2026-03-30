/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export enum UserRole {
  RBF_OFFICIAL = "RBF Official",
  TAC = "TAC Member",
  DOE_OFFICER = "DoE Officer",
  FIELD_VERIFIER = "Field Verifier",
  VENDOR = "Vendor",
  ADMIN = "Digital Admin",
  UNDP_DONOR = "UNDP & Donors",
  AUDITOR = "Auditor",
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
  UNDER_REVIEW = "Under Review",
  AWARDED = "Awarded",
  ACCEPTED = "Accepted",
  REJECTED = "Rejected",
  WITHDRAWN = "Withdrawn",
}

export enum ProjectStatus {
  PRE_QUALIFICATION = "Pre-Qualification",
  SITE_SPECIFIC = "Site-Specific Proposal",
  CONTRACTING = "Contracting",
  INSTALLATION = "Installation",
  VERIFICATION = "Field Verification",
  DISBURSEMENT = "Disbursement",
  COMPLETED = "Completed",
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
  stageType?: "Pre-Qualification" | "Site-Specific";
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
  targetSiteType?: "Household" | "Business" | "School" | "Clinic";
  isVerified?: boolean;
  fundingSource?: string;
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
  latitude?: number;
  longitude?: number;
  systemConfiguration?: Record<string, any>;
  boqItems?: Array<Record<string, any>>;
  notes?: string;
}

export interface TenderBid {
  id: string;
  tender: string;
  tender_reference?: string;
  tender_name?: string;
  vendor_id: string;
  vendor_name: string;
  vendor_email?: string;
  bid_amount?: number;
  stage?: string;
  concept_note?: string;
  technical_proposal?: string;
  financial_proposal?: string;
  technical_proposal_file?: string;
  financial_proposal_file?: string;
  boq_file?: string;
  gender_action_plan_file?: string;
  implementation_plan_file?: string;
  reporting_templates_file?: string;
  status: BidStatus;
  version_number: number;
  submitted_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
  rejection_reason?: string;
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
  targetBeneficiaries?: number;
  deploymentTeamRoster?: string;
  deploymentEquipmentPlan?: string;
  deploymentWorkSchedule?: string;
  energyOutput: number; // kWh
  uptime: number; // %
  genderImpact: number; // % female beneficiaries
}

export interface User {
  id: string;
  fullName: string;
  email: string;
  role: UserRole;
  gender: "Male" | "Female" | "Other";
  region?: string;
  mobileNumber?: string;
  nationalId?: string;
  address?: string;
  organizationName?: string;
  organizationType?: string;
  technologyTypes?: string[];
  registrationCertificateName?: string;
  taxId?: string;
  deviceId?: string;
  tierAssignment?: string;
  verificationZone?: string;
  status: "Active" | "Pending" | "Inactive";
  mustChangePassword?: boolean;
  vendorTag?: string | null;
}

export interface TenderBidEvaluation {
  id: string;
  bid: string;
  evaluator?: string;
  evaluatorUsername?: string;
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
  name: string;
  description?: string;
  percentage: number;
  status: "Pending" | "Submitted" | "Verified" | "Paid";
  amount: number;
  progressPercentage: number;
  targetDate?: string;
  completedDate?: string;
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
export type VerificationStatus = "Pending" | "Verified" | "Flagged";

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

export type PrequalificationStatus =
  | "Pending"
  | "Under Review"
  | "Approved"
  | "Clarification Requested"
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

export interface VendorPrequalificationSubmission {
  companyName: string;
  organizationType?: string;
  taxId?: string;
  hqAddress?: string;
  technologyTypes: string[];
  registrationCertificateName?: string;
  tradingLicense?: File;
  registrationCertificate?: File;
  taxComplianceCertificate?: File;
  authorizedSignatoryId?: File;
  experienceFinancialProof?: File;
  techTier?: string;
  yearsExperience?: number;
  priorProjects?: number;
  annualRevenue?: number;
  districtsCovered?: number;
  femaleBeneficiaryTarget?: number;
  vulnerableGroupTarget?: number;
  bankAccountName?: string;
  bankAccountNumber?: string;
  contactNumber?: string;
  email?: string;
  genderOfFocalPerson?: string;
  declarationAccepted: boolean;
}

export type PaymentClaimStatus = "Pending" | "Verified" | "Approved" | "Paid" | "Rejected";
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
  disbursement?: Disbursement;
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
}
