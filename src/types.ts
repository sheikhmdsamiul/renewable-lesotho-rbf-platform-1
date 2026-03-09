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
}

export interface Project {
  id: string;
  vendorId: string;
  vendorName: string;
  techType: string;
  region: string;
  status: ProjectStatus;
  progress: number;
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
  organizationName?: string;
  organizationType?: string;
  technologyTypes?: string[];
  status: "Active" | "Pending" | "Inactive";
  mustChangePassword?: boolean;
}

export interface Milestone {
  id: string;
  projectId: string;
  name: string;
  percentage: number;
  status: "Pending" | "Submitted" | "Verified" | "Paid";
  amount: number;
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
  techTier?: string;
  yearsExperience: number;
  priorProjects: number;
  annualRevenue?: number;
  districtsCovered: number;
  femaleBeneficiaryTarget: number;
  vulnerableGroupTarget: number;
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
  techTier?: string;
  yearsExperience?: number;
  priorProjects?: number;
  annualRevenue?: number;
  districtsCovered?: number;
  femaleBeneficiaryTarget?: number;
  vulnerableGroupTarget?: number;
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
