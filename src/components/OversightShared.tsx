/**
 * Shared Monitoring & Verification views used by the DoE, PSC, Auditor and RMT portals.
 *
 * Every view reads the same project, verification, KPI, vendor and disbursement records.
 * What a viewer may do is decided by their role (`OversightKind`), never by a separate copy
 * of the data: DoE reviews and requests re-verification, PSC records governance reviews,
 * the Auditor only reads and opens audit cases, and RMT tracks follow-ups.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  Flag,
  Loader2,
  Lock,
  MapPin,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  acknowledgeVerification,
  amendOversightReview,
  AuditCaseInput,
  createOversightReview,
  fetchKpiReviews,
  fetchOversightReviews,
  fetchVendorPerformance,
  fetchVerificationTasks,
  requestReverification,
  updateOversightFollowUp,
} from "../api";
import {
  FieldVerificationRecord,
  KpiReview,
  OversightFollowUpStatus,
  OversightReview,
  OversightReviewStatus,
  OversightSubject,
  UserRole,
  VendorPerformance,
  VerificationTask,
} from "../types";

export type OversightKind = "doe" | "psc" | "auditor" | "rmt";

export type AuditCasePrefill = Partial<AuditCaseInput> & { context?: string };

export const oversightKindForRole = (role?: string): OversightKind => {
  if (role === UserRole.DOE_OFFICER) return "doe";
  if (role === UserRole.UNDP_DONOR) return "psc";
  if (role === UserRole.AUDITOR) return "auditor";
  return "rmt";
};

export const apiErrorMessage = (err: any, fallback: string) => {
  const raw = String(err?.message || "");
  try {
    const parsed = JSON.parse(raw.slice(raw.indexOf("{")));
    if (parsed?.detail) return String(parsed.detail);
    const first = Object.entries(parsed || {})[0];
    if (first) return `${first[0].replace(/_/g, " ")}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
  } catch {
    // Not a JSON error body.
  }
  return raw && raw.length < 200 ? raw : fallback;
};

const formatDate = (value?: string | null) => (value ? new Date(value).toLocaleDateString("en-GB") : "-");
const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString("en-GB") : "-");
const formatMoney = (value: number) => `LSL ${Math.round(value).toLocaleString()}`;

// ---------------------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------------------

export function LoadingCard({ label }: { label: string }) {
  return (
    <div className="card p-10 text-center text-slate-500">
      <Loader2 size={24} className="mx-auto mb-2 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card border-rose-200 bg-rose-50 p-10 text-center text-rose-700">
      <AlertTriangle size={24} className="mx-auto mb-2" />
      {message}
      <button type="button" onClick={onRetry} className="btn-secondary mx-auto mt-4 flex items-center gap-2">
        <RefreshCw size={14} /> Retry
      </button>
    </div>
  );
}

export function PageHeader({ title, description, onRefresh, children }: {
  title: string;
  description: string;
  onRefresh?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        <p className="text-sm text-slate-500">{description}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 self-start">
        {children}
        {onRefresh && (
          <button type="button" onClick={onRefresh} className="btn-secondary inline-flex items-center gap-2">
            <RefreshCw size={16} /> Refresh
          </button>
        )}
      </div>
    </div>
  );
}

export function StatTiles({ tiles }: { tiles: { label: string; value: React.ReactNode; tone?: string }[] }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} className="card p-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">{tile.label}</p>
          <p className={`mt-3 text-3xl font-bold ${tile.tone || "text-slate-900"}`}>{tile.value}</p>
        </div>
      ))}
    </div>
  );
}

/** Tabs over several existing views, so a sidebar entry can group related screens without duplicating them. */
export function TabbedSection({ tabs }: { tabs: { id: string; label: string; render: () => React.ReactNode }[] }) {
  const [active, setActive] = useState(tabs[0]?.id);
  const current = tabs.find((tab) => tab.id === active) || tabs[0];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2 border-b border-slate-200">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActive(tab.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold transition ${
              tab.id === current?.id ? "border-emerald-600 text-emerald-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {current?.render()}
    </div>
  );
}

function ReadOnlyNotice({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <Lock size={14} className="mt-0.5 shrink-0 text-slate-400" />
      <span>{children}</span>
    </p>
  );
}

// ---------------------------------------------------------------------------------------
// Oversight reviews (shared record for DoE / PSC / RMT)
// ---------------------------------------------------------------------------------------

export const REVIEW_STATUS_META: Record<OversightReviewStatus, { label: string; badge: string }> = {
  compliant: { label: "Compliant", badge: "bg-emerald-100 text-emerald-700" },
  delayed: { label: "Delayed", badge: "bg-amber-100 text-amber-700" },
  flagged: { label: "Flagged", badge: "bg-rose-100 text-rose-700" },
  comment: { label: "Comment", badge: "bg-slate-100 text-slate-700" },
  acknowledged: { label: "Acknowledged", badge: "bg-blue-100 text-blue-700" },
  reverification_requested: { label: "Re-verification Requested", badge: "bg-violet-100 text-violet-700" },
};

const FOLLOW_UP_META: Record<OversightFollowUpStatus, { label: string; badge: string }> = {
  none: { label: "No follow-up", badge: "bg-slate-100 text-slate-500" },
  open: { label: "Open", badge: "bg-amber-100 text-amber-700" },
  in_progress: { label: "In progress", badge: "bg-blue-100 text-blue-700" },
  resolved: { label: "Resolved", badge: "bg-emerald-100 text-emerald-700" },
};

const SUBJECT_LABELS: Record<OversightSubject, string> = {
  project: "Project",
  verification: "Verification",
  kpi: "KPI",
  vendor: "Vendor performance",
  disbursement: "Disbursement",
  monitoring: "Monitoring",
};

/** Review statuses each role may record directly; acknowledgement and re-verification are workflow actions. */
const ROLE_REVIEW_STATUSES: Record<OversightKind, OversightReviewStatus[]> = {
  psc: ["compliant", "delayed", "flagged", "comment"],
  doe: ["flagged", "comment"],
  rmt: ["flagged", "comment"],
  auditor: [],
};

const ISSUE_CATEGORIES = [
  "Payment delay",
  "Contract inconsistency",
  "Excessive rejections",
  "Verification quality",
  "GPS / location mismatch",
  "KPI shortfall",
  "Gender & inclusion",
  "Vendor performance",
  "Other",
];

export interface OversightLinks {
  projectId?: string;
  milestoneId?: string;
  verificationTaskId?: string;
  paymentClaimId?: string;
  vendorId?: string;
  kpiReviewId?: string;
  monitoringVisitId?: string;
}

export function OversightReviewModal({
  kind,
  subjectType,
  heading,
  subjectLabel,
  links,
  projectOptions,
  onClose,
  onSaved,
}: {
  kind: OversightKind;
  subjectType: OversightSubject;
  heading: string;
  subjectLabel: string;
  links: OversightLinks;
  /** When the subject is a vendor, the viewer may pick one of its projects to anchor the review. */
  projectOptions?: { id: string; reference: string }[];
  onClose: () => void;
  onSaved: (review: OversightReview) => void;
}) {
  const statuses = ROLE_REVIEW_STATUSES[kind];
  const [reviewStatus, setReviewStatus] = useState<OversightReviewStatus>(statuses.includes("flagged") ? "flagged" : statuses[0]);
  const [comment, setComment] = useState("");
  const [issueCategory, setIssueCategory] = useState("");
  const [actionRequired, setActionRequired] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [projectId, setProjectId] = useState(links.projectId || (projectOptions?.length === 1 ? projectOptions[0].id : ""));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const projectRequired = kind === "doe" && subjectType === "vendor";
  const maxComment = kind === "psc" ? 500 : 2000;

  const submit = async () => {
    if (comment.trim().length < 5) return setError("Write a comment (at least 5 characters).");
    if (projectRequired && !projectId) return setError("Choose the regional project this concerns.");
    setSaving(true);
    setError(null);
    try {
      const saved = await createOversightReview({
        subjectType,
        reviewStatus,
        comment: comment.trim(),
        issueCategory,
        actionRequired: actionRequired.trim(),
        followUpDate,
        ...links,
        projectId: projectId || links.projectId,
      });
      onSaved(saved);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to record the review."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="max-h-[90vh] w-full max-w-xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{heading}</h3>
            <p className="text-sm text-slate-500">{SUBJECT_LABELS[subjectType]}: {subjectLabel}</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
        </div>

        <ReadOnlyNotice>Your review is stored alongside the record. The record itself, its field evidence and its calculated values are not changed.</ReadOnlyNotice>

        <div>
          <p className="mb-2 text-sm font-semibold text-slate-900">Review status *</p>
          <div className="flex flex-wrap gap-2">
            {statuses.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setReviewStatus(value)}
                className={`rounded-full px-3 py-1.5 text-xs font-bold ring-1 transition ${
                  reviewStatus === value ? `${REVIEW_STATUS_META[value].badge} ring-current` : "bg-white text-slate-500 ring-slate-200"
                }`}
              >
                {REVIEW_STATUS_META[value].label}
              </button>
            ))}
          </div>
        </div>

        {projectOptions && projectOptions.length > 0 && (
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Project {projectRequired ? "*" : "(optional)"}</span>
            <select className="input-field" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">{projectRequired ? "Choose a project" : "Not project-specific"}</option>
              {projectOptions.map((option) => <option key={option.id} value={option.id}>{option.reference}</option>)}
            </select>
          </label>
        )}

        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Comment *</span>
          <textarea className="input-field min-h-[100px]" maxLength={maxComment} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What did you find, and why does it matter?" />
          <span className="mt-1 block text-right text-xs text-slate-400">{comment.length}/{maxComment}</span>
        </label>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Issue category</span>
            <select className="input-field" value={issueCategory} onChange={(e) => setIssueCategory(e.target.value)}>
              <option value="">None</option>
              {ISSUE_CATEGORIES.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Follow-up by</span>
            <input type="date" className="input-field" value={followUpDate} onChange={(e) => setFollowUpDate(e.target.value)} />
          </label>
        </div>

        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Action required</span>
          <textarea className="input-field min-h-[70px]" value={actionRequired} onChange={(e) => setActionRequired(e.target.value)} placeholder="What should RMT or the vendor do?" />
        </label>

        {(reviewStatus === "flagged" || reviewStatus === "delayed") && (
          <p className="text-xs text-amber-700">Flagged and delayed reviews open a follow-up for the RBF Management Team and notify RMT and PSC.</p>
        )}
        {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>Cancel</button>
          <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
            {saving && <Loader2 size={16} className="animate-spin" />} Record Review
          </button>
        </div>
      </div>
    </div>
  );
}

function ReviewCard({
  review,
  currentUserId,
  kind,
  onChanged,
}: {
  review: OversightReview;
  currentUserId: string;
  kind: OversightKind;
  onChanged: (review: OversightReview) => void;
}) {
  const [mode, setMode] = useState<"view" | "amend" | "follow">("view");
  const [comment, setComment] = useState(review.comment);
  const [status, setStatus] = useState<OversightFollowUpStatus>(review.followUpStatus === "open" ? "in_progress" : "resolved");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isOwner = Boolean(review.reviewer && review.reviewer === currentUserId);
  const isWorkflowRecord = review.reviewStatus === "acknowledged" || review.reviewStatus === "reverification_requested";
  const canAmend = isOwner && !isWorkflowRecord && review.followUpStatus !== "resolved";
  const canFollowUp = (kind === "rmt" || isOwner) && (review.followUpStatus === "open" || review.followUpStatus === "in_progress");

  const run = async (fn: () => Promise<OversightReview>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
      setMode("view");
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to save."));
    } finally {
      setBusy(false);
    }
  };

  const target = [
    review.projectReference,
    review.installationSerial && `Installation ${review.installationSerial}${review.verificationRound ? ` (round ${review.verificationRound})` : ""}`,
    review.paymentClaimId && `Claim #${review.paymentClaimId}${review.claimStatus ? ` (${review.claimStatus})` : ""}`,
    review.subjectType === "vendor" && review.vendorDisplay,
  ].filter(Boolean).join(" | ");

  return (
    <div className="card space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${REVIEW_STATUS_META[review.reviewStatus]?.badge}`}>{REVIEW_STATUS_META[review.reviewStatus]?.label}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">{SUBJECT_LABELS[review.subjectType]}</span>
        {review.issueCategory && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{review.issueCategory}</span>}
        {review.followUpStatus !== "none" && (
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${FOLLOW_UP_META[review.followUpStatus].badge}`}>Follow-up: {FOLLOW_UP_META[review.followUpStatus].label}</span>
        )}
        <span className="ml-auto text-xs text-slate-400">{formatDateTime(review.createdAt)}</span>
      </div>
      {target && <p className="text-sm font-semibold text-slate-900">{target}</p>}
      {mode === "amend" ? (
        <textarea className="input-field min-h-[80px]" value={comment} onChange={(e) => setComment(e.target.value)} />
      ) : (
        <p className="whitespace-pre-wrap text-sm text-slate-700">{review.comment}</p>
      )}
      {review.actionRequired && <p className="text-sm text-slate-600"><span className="font-semibold">Action required:</span> {review.actionRequired}</p>}
      <p className="text-xs text-slate-500">
        {review.reviewerName || review.reviewerUsername || "Unknown"} ({review.reviewerRole})
        {review.followUpDate && ` | follow-up by ${formatDate(review.followUpDate)}`}
      </p>
      {review.resolutionNote && (
        <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {review.followUpStatus === "resolved" ? "Resolved" : "Update"}{review.resolvedByUsername ? ` by ${review.resolvedByUsername}` : ""}: {review.resolutionNote}
        </p>
      )}
      {mode === "follow" && (
        <div className="grid gap-3 md:grid-cols-[200px_1fr]">
          <select className="input-field" value={status} onChange={(e) => setStatus(e.target.value as OversightFollowUpStatus)}>
            <option value="in_progress">In progress</option>
            <option value="resolved">Resolved</option>
          </select>
          <input className="input-field" value={note} onChange={(e) => setNote(e.target.value)} placeholder={status === "resolved" ? "How was it resolved? *" : "Progress note"} />
        </div>
      )}
      {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        {mode !== "view" && <button type="button" className="btn-secondary" disabled={busy} onClick={() => setMode("view")}>Cancel</button>}
        {mode === "amend" && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void run(() => amendOversightReview(review.id, { comment: comment.trim() }))}>Save</button>
        )}
        {mode === "follow" && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void run(() => updateOversightFollowUp(review.id, status, note.trim()))}>Update Follow-up</button>
        )}
        {mode === "view" && canAmend && <button type="button" className="btn-secondary" onClick={() => setMode("amend")}>Amend</button>}
        {mode === "view" && canFollowUp && <button type="button" className="btn-secondary" onClick={() => setMode("follow")}>Update Follow-up</button>}
      </div>
    </div>
  );
}

export type ReviewListPreset = "all" | "open" | "mine" | "mine_flagged" | "flagged";

/** Lists the shared oversight reviews; DoE sees its region, PSC/RMT/Auditor see everything. */
export function OversightReviewsView({
  currentUser,
  title,
  description,
  preset = "all",
  reviewerRole,
}: {
  currentUser: any;
  title: string;
  description: string;
  preset?: ReviewListPreset;
  /** Limit to reviews recorded by one role (e.g. PSC review history). */
  reviewerRole?: string;
}) {
  const kind = oversightKindForRole(currentUser?.role);
  const currentUserId = currentUser?.id ? String(currentUser.id) : "";
  const [reviews, setReviews] = useState<OversightReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState<"" | OversightSubject>("");
  const [followUp, setFollowUp] = useState<"" | OversightFollowUpStatus>("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReviews(await fetchOversightReviews({
        mine: preset === "mine" || preset === "mine_flagged" ? "1" : undefined,
        open: preset === "open" ? "1" : undefined,
        reviewer_role: reviewerRole,
      }));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load reviews."));
    } finally {
      setLoading(false);
    }
  }, [preset, reviewerRole]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return reviews.filter((review) => {
      if ((preset === "flagged" || preset === "mine_flagged") && !["flagged", "delayed"].includes(review.reviewStatus)) return false;
      if (subject && review.subjectType !== subject) return false;
      if (followUp && review.followUpStatus !== followUp) return false;
      if (!term) return true;
      return [review.comment, review.projectReference, review.vendorDisplay, review.installationSerial, review.issueCategory]
        .some((value) => String(value || "").toLowerCase().includes(term));
    });
  }, [reviews, preset, subject, followUp, search]);

  const counts = useMemo(() => ({
    open: reviews.filter((r) => r.followUpStatus === "open" || r.followUpStatus === "in_progress").length,
    flagged: reviews.filter((r) => r.reviewStatus === "flagged").length,
    delayed: reviews.filter((r) => r.reviewStatus === "delayed").length,
    resolved: reviews.filter((r) => r.followUpStatus === "resolved").length,
  }), [reviews]);

  const replace = (updated: OversightReview) => setReviews((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));

  if (loading) return <LoadingCard label="Loading reviews..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-6">
      <PageHeader title={title} description={description} onRefresh={() => void load()} />
      <StatTiles tiles={[
        { label: "Open follow-ups", value: counts.open, tone: counts.open ? "text-amber-700" : "text-emerald-700" },
        { label: "Flagged", value: counts.flagged, tone: counts.flagged ? "text-rose-700" : "text-slate-900" },
        { label: "Delayed", value: counts.delayed, tone: "text-amber-700" },
        { label: "Resolved", value: counts.resolved, tone: "text-emerald-700" },
      ]} />
      <div className="card flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search comment, project, vendor..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input-field md:w-48" value={subject} onChange={(e) => setSubject(e.target.value as any)}>
          <option value="">All subjects</option>
          {Object.entries(SUBJECT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select className="input-field md:w-48" value={followUp} onChange={(e) => setFollowUp(e.target.value as any)}>
          <option value="">Any follow-up</option>
          {Object.entries(FOLLOW_UP_META).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
        </select>
      </div>
      {visible.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">No reviews match.</div>
      ) : (
        <div className="space-y-3">
          {visible.map((review) => (
            <React.Fragment key={review.id}>
              <ReviewCard review={review} currentUserId={currentUserId} kind={kind} onChanged={replace} />
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Field verification review (DoE acts; PSC reviews summaries; Auditor reads)
// ---------------------------------------------------------------------------------------

const VERIFICATION_TONE: Record<string, string> = {
  Verified: "bg-emerald-100 text-emerald-700",
  Flagged: "bg-rose-100 text-rose-700",
  Partial: "bg-amber-100 text-amber-700",
  Pending: "bg-slate-100 text-slate-700",
  "Reverification Required": "bg-violet-100 text-violet-700",
  Paused: "bg-slate-200 text-slate-700",
  Terminated: "bg-slate-200 text-slate-700",
};

const yesNo = (value: boolean) => (value ? "Yes" : "No");

function EvidenceRound({ record, vendorLat, vendorLng }: { record: FieldVerificationRecord; vendorLat: number; vendorLng: number }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-bold text-white">Round {record.verificationRound || 1}</span>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${VERIFICATION_TONE[record.verificationStatus.charAt(0).toUpperCase() + record.verificationStatus.slice(1)] || "bg-slate-100 text-slate-700"}`}>
          {record.verificationStatus}
        </span>
        <span className="text-xs text-slate-500">{record.fieldOfficerName || record.fieldOfficerUsername} | {formatDateTime(record.verifiedAt)}</span>
        <span className="ml-auto inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400"><Lock size={12} /> Submitted evidence</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
        <div><dt className="text-xs text-slate-500">Verifier GPS</dt><dd className="font-medium text-slate-900">{record.officerLatitude.toFixed(5)}, {record.officerLongitude.toFixed(5)}</dd></div>
        <div><dt className="text-xs text-slate-500">Vendor GPS</dt><dd className="font-medium text-slate-900">{vendorLat.toFixed(5)}, {vendorLng.toFixed(5)}</dd></div>
        <div><dt className="text-xs text-slate-500">Distance</dt><dd className={`font-medium ${record.locationMatch ? "text-emerald-700" : "text-rose-700"}`}>{record.locationDistanceMeters.toFixed(1)} m {record.locationMatch ? "(match)" : "(mismatch)"}</dd></div>
        <div><dt className="text-xs text-slate-500">Beneficiary present</dt><dd className="font-medium text-slate-900">{yesNo(record.beneficiaryPresent)} ({record.beneficiaryGender})</dd></div>
        <div><dt className="text-xs text-slate-500">System working</dt><dd className="font-medium text-slate-900">{yesNo(record.systemWorking)}</dd></div>
        <div><dt className="text-xs text-slate-500">Serial visible</dt><dd className="font-medium text-slate-900">{yesNo(record.serialVisible)}</dd></div>
      </dl>
      {record.observationNotes && <p className="mt-3 text-sm text-slate-700"><span className="font-semibold">Notes:</span> {record.observationNotes}</p>}
      {record.flagReason && <p className="mt-1 text-sm text-rose-700"><span className="font-semibold">Flag reason:</span> {record.flagReason}</p>}
      {record.sitePhotos.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {record.sitePhotos.map((url) => (
            <a key={url} href={url} target="_blank" rel="noreferrer">
              <img src={url} alt="Site evidence" className="h-24 w-24 rounded-lg border border-slate-200 object-cover" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function VerificationDetail({
  task,
  kind,
  reviews,
  currentUserId,
  onBack,
  onTaskChanged,
  onReviewAdded,
  onOpenAuditCase,
}: {
  task: VerificationTask;
  kind: OversightKind;
  reviews: OversightReview[];
  currentUserId: string;
  onBack: () => void;
  onTaskChanged: (task: VerificationTask) => void;
  onReviewAdded: (review: OversightReview) => void;
  onOpenAuditCase?: (prefill: AuditCasePrefill) => void;
}) {
  const [mode, setMode] = useState<"none" | "ack" | "reverify" | "review">("none");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const installation = task.installation;
  const completed = ["Verified", "Flagged", "Partial"].includes(task.status);
  const canDecide = kind === "doe" || kind === "rmt";
  const alreadyAcknowledged = reviews.some(
    (r) => r.reviewStatus === "acknowledged" && r.reviewer === currentUserId && (r.verificationRound ?? 1) === task.verificationRound,
  );
  const history = task.fieldVerifications || (task.fieldVerification ? [task.fieldVerification] : []);

  const run = async (fn: () => Promise<VerificationTask>) => {
    setBusy(true);
    setError(null);
    try {
      onTaskChanged(await fn());
      setMode("none");
      setText("");
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to complete the action."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm font-semibold text-emerald-700 hover:underline">&larr; Back to verifications</button>
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Installation {installation?.serialNumber || task.report}</p>
            <h2 className="mt-1 text-xl font-bold text-slate-900">{installation?.projectReference || "Project"} - {installation?.vendorName || "Vendor"}</h2>
            <p className="text-sm text-slate-500">{installation?.district || "-"} | Reported {formatDate(installation?.submittedAt)} | Verifier {task.assignedVerifierUsername || "unassigned"}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${VERIFICATION_TONE[task.status] || "bg-slate-100"}`}>{task.status}</span>
            <span className="text-xs text-slate-500">Round {task.verificationRound}</span>
          </div>
        </div>
        {task.status === "Reverification Required" && task.reverificationReason && (
          <p className="mt-4 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-800">
            Re-verification requested by {task.reverificationRequestedByUsername || "a reviewer"} on {formatDate(task.reverificationRequestedAt)}: {task.reverificationReason}
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {canDecide && completed && !alreadyAcknowledged && (
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setMode("ack")}><CheckCircle2 size={16} /> Accept / Acknowledge</button>
          )}
          {canDecide && completed && (
            <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => setMode("reverify")}><RotateCcw size={16} /> Request Re-verification</button>
          )}
          {(kind === "doe" || kind === "psc" || kind === "rmt") && (
            <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => setMode("review")}>
              <Flag size={16} /> {kind === "psc" ? "Record PSC Review" : "Flag Issue / Comment"}
            </button>
          )}
          {kind === "auditor" && onOpenAuditCase && (
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-2"
              onClick={() => onOpenAuditCase({
                auditArea: "verification",
                verificationTaskId: task.id,
                projectId: installation?.projectId,
                title: `Verification evidence: installation ${installation?.serialNumber || task.report}`,
                context: `Installation ${installation?.serialNumber || task.report}`,
              })}
            >
              <ShieldCheck size={16} /> Open Audit Case
            </button>
          )}
          {alreadyAcknowledged && <span className="inline-flex items-center gap-1 text-sm font-semibold text-blue-700"><CheckCircle2 size={16} /> You acknowledged round {task.verificationRound}</span>}
        </div>
        {(mode === "ack" || mode === "reverify") && (
          <div className="mt-4 space-y-3 rounded-xl border border-slate-200 p-4">
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-slate-900">{mode === "ack" ? "Comment (optional)" : "Reason for re-verification *"}</span>
              <textarea className="input-field min-h-[80px]" value={text} onChange={(e) => setText(e.target.value)}
                placeholder={mode === "ack" ? "Evidence reviewed and accepted." : "What must the field verifier check again?"} />
            </label>
            {mode === "reverify" && <p className="text-xs text-slate-500">The submitted evidence stays on record. The verifier is notified and a new round is opened.</p>}
            {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => setMode("none")}>Cancel</button>
              <button
                type="button"
                className="btn-primary"
                disabled={busy || (mode === "reverify" && text.trim().length < 10)}
                onClick={() => void run(() => (mode === "ack" ? acknowledgeVerification(task.id, text.trim()) : requestReverification(task.id, text.trim())))}
              >
                {mode === "ack" ? "Acknowledge" : "Request Re-verification"}
              </button>
            </div>
          </div>
        )}
      </div>

      {mode === "review" && (
        <OversightReviewModal
          kind={kind}
          subjectType="verification"
          heading={kind === "psc" ? "PSC review of verification" : "Flag a verification issue"}
          subjectLabel={`Installation ${installation?.serialNumber || task.report} (round ${task.verificationRound})`}
          links={{ verificationTaskId: task.id, projectId: installation?.projectId }}
          onClose={() => setMode("none")}
          onSaved={(review) => {
            onReviewAdded(review);
            setMode("none");
          }}
        />
      )}

      <div className="card space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-900">Field evidence</h3>
          <span className="inline-flex items-center gap-1 text-xs text-slate-500"><MapPin size={14} /> Vendor-reported GPS {installation ? `${installation.gpsLat.toFixed(5)}, ${installation.gpsLng.toFixed(5)}` : "-"}</span>
        </div>
        <ReadOnlyNotice>Field evidence (GPS, photographs and survey answers) is locked once submitted. Reviewers can acknowledge it, flag it or request a new verification round, but cannot edit or delete it.</ReadOnlyNotice>
        {installation && installation.photoUrls.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-400">Vendor installation photos</p>
            <div className="flex flex-wrap gap-2">
              {installation.photoUrls.map((url) => (
                <a key={url} href={url} target="_blank" rel="noreferrer">
                  <img src={url} alt="Installation" className="h-24 w-24 rounded-lg border border-slate-200 object-cover" />
                </a>
              ))}
            </div>
          </div>
        )}
        {history.length === 0 ? (
          <p className="text-sm text-slate-500">No field verification has been submitted yet.</p>
        ) : (
          history.map((record) => (
            <React.Fragment key={record.id}>
              <EvidenceRound record={record} vendorLat={task.vendorLat} vendorLng={task.vendorLng} />
            </React.Fragment>
          ))
        )}
      </div>

      <div className="card space-y-3 p-6">
        <h3 className="text-lg font-bold text-slate-900">Reviews of this verification</h3>
        {reviews.length === 0 ? (
          <p className="text-sm text-slate-500">No reviews yet.</p>
        ) : (
          reviews.map((review) => (
            <div key={review.id} className="flex flex-wrap items-start gap-2 border-t border-slate-100 pt-3 text-sm">
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${REVIEW_STATUS_META[review.reviewStatus].badge}`}>{REVIEW_STATUS_META[review.reviewStatus].label}</span>
              <span className="text-slate-700">{review.comment}</span>
              <span className="ml-auto text-xs text-slate-400">{review.reviewerName || review.reviewerUsername} ({review.reviewerRole}) | round {review.verificationRound ?? "-"} | {formatDate(review.createdAt)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

type VerificationFilter = "awaiting" | "reverification" | "flagged" | "pending" | "all";

export function VerificationReviewView({
  currentUser,
  title,
  description,
  onOpenAuditCase,
}: {
  currentUser: any;
  title?: string;
  description?: string;
  onOpenAuditCase?: (prefill: AuditCasePrefill) => void;
}) {
  const kind = oversightKindForRole(currentUser?.role);
  const currentUserId = currentUser?.id ? String(currentUser.id) : "";
  const [tasks, setTasks] = useState<VerificationTask[]>([]);
  const [reviews, setReviews] = useState<OversightReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<VerificationFilter>(kind === "doe" ? "awaiting" : "all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskList, reviewList] = await Promise.all([
        fetchVerificationTasks(),
        fetchOversightReviews({ subject_type: "verification" }),
      ]);
      setTasks(taskList);
      setReviews(reviewList);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load verifications."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reviewsByTask = useMemo(() => {
    const map: Record<string, OversightReview[]> = {};
    reviews.forEach((review) => {
      if (review.verificationTaskId) (map[review.verificationTaskId] ||= []).push(review);
    });
    return map;
  }, [reviews]);

  const acknowledgedCurrentRound = useCallback((task: VerificationTask) => (reviewsByTask[task.id] || []).some(
    (r) => r.reviewStatus === "acknowledged" && (r.verificationRound ?? 1) === task.verificationRound,
  ), [reviewsByTask]);

  const completed = (task: VerificationTask) => ["Verified", "Flagged", "Partial"].includes(task.status);
  const stats = useMemo(() => ({
    awaiting: tasks.filter((t) => completed(t) && !acknowledgedCurrentRound(t)).length,
    reverification: tasks.filter((t) => t.status === "Reverification Required").length,
    flagged: tasks.filter((t) => t.status === "Flagged" || t.status === "Partial").length,
    verified: tasks.filter((t) => t.status === "Verified").length,
    pending: tasks.filter((t) => t.status === "Pending").length,
  }), [tasks, acknowledgedCurrentRound]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return tasks.filter((task) => {
      if (filter === "awaiting" && !(completed(task) && !acknowledgedCurrentRound(task))) return false;
      if (filter === "reverification" && task.status !== "Reverification Required") return false;
      if (filter === "flagged" && !(task.status === "Flagged" || task.status === "Partial")) return false;
      if (filter === "pending" && task.status !== "Pending") return false;
      if (!term) return true;
      const inst = task.installation;
      return [inst?.serialNumber, inst?.projectReference, inst?.vendorName, inst?.district, task.assignedVerifierUsername]
        .some((value) => String(value || "").toLowerCase().includes(term));
    });
  }, [tasks, filter, search, acknowledgedCurrentRound]);

  if (loading) return <LoadingCard label="Loading verifications..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const selected = selectedId ? tasks.find((task) => task.id === selectedId) : null;
  if (selected) {
    return (
      <VerificationDetail
        task={selected}
        kind={kind}
        reviews={reviewsByTask[selected.id] || []}
        currentUserId={currentUserId}
        onBack={() => setSelectedId(null)}
        onTaskChanged={(updated) => {
          setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
          void fetchOversightReviews({ subject_type: "verification" }).then(setReviews).catch(() => undefined);
        }}
        onReviewAdded={(review) => setReviews((prev) => [review, ...prev])}
        onOpenAuditCase={onOpenAuditCase}
      />
    );
  }

  const defaultDescription = {
    doe: `Review submitted field verifications for ${currentUser?.region || "your region"}: accept them, flag issues or request re-verification.`,
    psc: "Summary of field verification outcomes across the portfolio. Record a PSC review where governance attention is needed.",
    auditor: "Read-only verification records, GPS evidence and every verification round, for independent audit.",
    rmt: "Field verification outcomes and reviews.",
  }[kind];

  const filters: { id: VerificationFilter; label: string; count?: number }[] = [
    { id: "awaiting", label: "Awaiting review", count: stats.awaiting },
    { id: "reverification", label: "Re-verification required", count: stats.reverification },
    { id: "flagged", label: "Flagged / partial", count: stats.flagged },
    { id: "pending", label: "Not yet verified", count: stats.pending },
    { id: "all", label: "All", count: tasks.length },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title={title || (kind === "psc" ? "Verification Summary" : kind === "auditor" ? "Verification Audit" : "Field Verification")} description={description || defaultDescription} onRefresh={() => void load()} />
      <StatTiles tiles={[
        { label: "Verified", value: stats.verified, tone: "text-emerald-700" },
        { label: "Flagged / partial", value: stats.flagged, tone: stats.flagged ? "text-rose-700" : "text-slate-900" },
        { label: "Re-verification required", value: stats.reverification, tone: "text-violet-700" },
        { label: "Awaiting DoE/RMT review", value: stats.awaiting, tone: stats.awaiting ? "text-amber-700" : "text-emerald-700" },
      ]} />
      <div className="card flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
        <div className="flex flex-wrap gap-2">
          {filters.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setFilter(option.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${filter === option.id ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            >
              {option.label}{option.count != null ? ` (${option.count})` : ""}
            </button>
          ))}
        </div>
        <div className="relative lg:ml-auto lg:w-72">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Serial, project, vendor..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Installation</th>
              <th className="px-4 py-3 text-left font-semibold">Project / Vendor</th>
              <th className="px-4 py-3 text-left font-semibold">District</th>
              <th className="px-4 py-3 text-left font-semibold">Status</th>
              <th className="px-4 py-3 text-left font-semibold">Round</th>
              <th className="px-4 py-3 text-left font-semibold">GPS check</th>
              <th className="px-4 py-3 text-left font-semibold">Reviewed</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {visible.map((task) => (
              <tr key={task.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-900">{task.installation?.serialNumber || task.report}</td>
                <td className="px-4 py-3 text-slate-700">
                  <div>{task.installation?.projectReference || "-"}</div>
                  <div className="text-xs text-slate-500">{task.installation?.vendorName}</div>
                </td>
                <td className="px-4 py-3 text-slate-700">{task.installation?.district || "-"}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${VERIFICATION_TONE[task.status] || "bg-slate-100"}`}>{task.status}</span></td>
                <td className="px-4 py-3 text-slate-700">{task.verificationRound}</td>
                <td className="px-4 py-3 text-slate-700">
                  {task.distanceMeters != null ? <span className={task.distanceMeters <= 50 ? "text-emerald-700" : "text-rose-700"}>{task.distanceMeters.toFixed(1)} m</span> : "-"}
                </td>
                <td className="px-4 py-3 text-slate-700">{acknowledgedCurrentRound(task) ? <CheckCircle2 size={16} className="text-blue-600" /> : "-"}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setSelectedId(task.id)}>
                    <Eye size={14} /> {kind === "doe" ? "Review" : "View Evidence"}
                  </button>
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500">No verifications match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Vendor performance (read-only metrics computed from the shared records)
// ---------------------------------------------------------------------------------------

export function VendorPerformanceView({
  currentUser,
  title,
  onOpenAuditCase,
}: {
  currentUser: any;
  title?: string;
  onOpenAuditCase?: (prefill: AuditCasePrefill) => void;
}) {
  const kind = oversightKindForRole(currentUser?.role);
  const [rows, setRows] = useState<VendorPerformance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [reviewing, setReviewing] = useState<VendorPerformance | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchVendorPerformance());
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load vendor performance."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return term ? rows.filter((row) => `${row.vendorName} ${row.districts.join(" ")}`.toLowerCase().includes(term)) : rows;
  }, [rows, search]);

  if (loading) return <LoadingCard label="Loading vendor performance..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const totals = rows.reduce((acc, row) => ({
    installations: acc.installations + row.installations,
    verified: acc.verified + row.verified,
    flagged: acc.flagged + row.flagged,
    issues: acc.issues + row.openIssues,
  }), { installations: 0, verified: 0, flagged: 0, issues: 0 });

  const description = {
    doe: `Performance of vendors with projects in ${currentUser?.region || "your region"}, calculated from verification, KPI and claim records.`,
    psc: "Portfolio-wide vendor performance from the shared verification, KPI and disbursement records.",
    auditor: "Read-only vendor performance for audit sampling. Open an audit case on any vendor.",
    rmt: "Vendor performance across the portfolio.",
  }[kind];

  return (
    <div className="space-y-6">
      <PageHeader title={title || "Vendor Performance"} description={description} onRefresh={() => void load()} />
      <StatTiles tiles={[
        { label: "Vendors", value: rows.length },
        { label: "Installations verified", value: `${totals.verified}/${totals.installations}`, tone: "text-emerald-700" },
        { label: "Flagged installations", value: totals.flagged, tone: totals.flagged ? "text-rose-700" : "text-slate-900" },
        { label: "Open oversight issues", value: totals.issues, tone: totals.issues ? "text-amber-700" : "text-slate-900" },
      ]} />
      <ReadOnlyNotice>Figures are calculated from source records and cannot be edited here.{kind === "doe" || kind === "psc" ? " Use Record Review to add a comment or flag." : ""}</ReadOnlyNotice>
      {notice && <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p>}
      <div className="relative md:w-80">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input-field pl-9" placeholder="Search vendor or district..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Vendor</th>
              <th className="px-4 py-3 text-right font-semibold">Projects</th>
              <th className="px-4 py-3 text-right font-semibold">Installations</th>
              <th className="px-4 py-3 text-right font-semibold">Verified %</th>
              <th className="px-4 py-3 text-right font-semibold">Flagged</th>
              <th className="px-4 py-3 text-right font-semibold">Re-verified</th>
              <th className="px-4 py-3 text-left font-semibold">Latest KPI ratings</th>
              <th className="px-4 py-3 text-right font-semibold">Claimed / Paid</th>
              <th className="px-4 py-3 text-right font-semibold">Open issues</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.vendorId} className="border-t border-slate-100 align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-900">{row.vendorName}</div>
                  <div className="text-xs text-slate-500">{row.districts.join(", ") || "-"}</div>
                  {row.vendorStatus && row.vendorStatus !== "Active" && (
                    <span className="mt-1 inline-block rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700">{row.vendorStatus}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-slate-700">{row.projects}<div className="text-xs text-slate-400">{row.activeProjects} active</div></td>
                <td className="px-4 py-3 text-right text-slate-700">{row.installations}<div className="text-xs text-slate-400">{row.pendingVerification} pending</div></td>
                <td className="px-4 py-3 text-right font-semibold text-slate-900">{row.verificationRate != null ? `${row.verificationRate}%` : "-"}</td>
                <td className={`px-4 py-3 text-right ${row.flagged ? "font-semibold text-rose-700" : "text-slate-700"}`}>{row.flagged}</td>
                <td className="px-4 py-3 text-right text-slate-700">{row.reverifications}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {row.kpiOnTrack > 0 && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700">{row.kpiOnTrack} on track</span>}
                    {row.kpiNeedsAttention > 0 && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">{row.kpiNeedsAttention} attention</span>}
                    {row.kpiAtRisk > 0 && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-700">{row.kpiAtRisk} at risk</span>}
                    {row.kpiOnTrack + row.kpiNeedsAttention + row.kpiAtRisk === 0 && <span className="text-xs text-slate-400">Not reviewed</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-slate-700">
                  {formatMoney(row.claimedAmount)}<div className="text-xs text-slate-400">{formatMoney(row.paidAmount)} paid{row.heldClaims ? `, ${row.heldClaims} held` : ""}</div>
                </td>
                <td className={`px-4 py-3 text-right ${row.openIssues ? "font-semibold text-amber-700" : "text-slate-700"}`}>{row.openIssues}</td>
                <td className="px-4 py-3 text-right">
                  {(kind === "doe" || kind === "psc") && (
                    <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setReviewing(row)}>
                      <MessageSquare size={14} /> Record Review
                    </button>
                  )}
                  {kind === "auditor" && onOpenAuditCase && (
                    <button
                      type="button"
                      className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs"
                      onClick={() => onOpenAuditCase({
                        auditArea: "vendor",
                        vendorId: /^\d+$/.test(row.vendorId) ? row.vendorId : undefined,
                        projectId: row.projectRefs.length === 1 ? row.projectRefs[0].id : undefined,
                        title: `Vendor audit: ${row.vendorName}`,
                        context: row.vendorName,
                      })}
                    >
                      <ShieldCheck size={14} /> Audit
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={10} className="px-4 py-10 text-center text-slate-500">No vendors found.</td></tr>}
          </tbody>
        </table>
      </div>
      {reviewing && (
        <OversightReviewModal
          kind={kind}
          subjectType="vendor"
          heading={kind === "psc" ? "PSC vendor performance review" : "Vendor performance comment"}
          subjectLabel={reviewing.vendorName}
          links={{ vendorId: /^\d+$/.test(reviewing.vendorId) ? reviewing.vendorId : undefined }}
          projectOptions={reviewing.projectRefs}
          onClose={() => setReviewing(null)}
          onSaved={() => {
            setReviewing(null);
            setNotice("Review recorded.");
            void load();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// KPI oversight (DoE KPI reviews read by PSC / Auditor; calculated KPIs stay read-only)
// ---------------------------------------------------------------------------------------

const KPI_RATING_META: Record<string, { label: string; badge: string }> = {
  on_track: { label: "On Track", badge: "bg-emerald-100 text-emerald-700" },
  needs_attention: { label: "Needs Attention", badge: "bg-amber-100 text-amber-700" },
  at_risk: { label: "At Risk", badge: "bg-rose-100 text-rose-700" },
};

const SNAPSHOT_LABELS: Record<string, string> = {
  installation_progress_pct: "Installation progress %",
  expected_progress_pct: "Expected progress %",
  verified_installations: "Verified installations",
  female_headed_pct: "Female-headed %",
  vulnerable_pct: "Vulnerable %",
  average_uptime_pct: "Average uptime %",
  energy_achievement_pct: "Energy achievement %",
};

export function KpiOversightView({
  currentUser,
  title,
  onOpenAuditCase,
}: {
  currentUser: any;
  title?: string;
  onOpenAuditCase?: (prefill: AuditCasePrefill) => void;
}) {
  const kind = oversightKindForRole(currentUser?.role);
  const [reviews, setReviews] = useState<KpiReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rating, setRating] = useState("");
  const [search, setSearch] = useState("");
  const [reviewing, setReviewing] = useState<KpiReview | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReviews(await fetchKpiReviews());
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load KPI reviews."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return reviews.filter((review) => (!rating || review.rating === rating) &&
      (!term || `${review.projectReference} ${review.projectTitle} ${review.summary}`.toLowerCase().includes(term)));
  }, [reviews, rating, search]);

  if (loading) return <LoadingCard label="Loading KPI reviews..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const latestByProject = new Map<string, KpiReview>();
  reviews.forEach((review) => {
    const current = latestByProject.get(review.projectId);
    if (!current || review.reviewPeriod > current.reviewPeriod) latestByProject.set(review.projectId, review);
  });
  const latest = [...latestByProject.values()];

  return (
    <div className="space-y-6">
      <PageHeader
        title={title || "KPI Review"}
        description={kind === "auditor"
          ? "DoE KPI assessments with the KPI figures they were based on, for audit."
          : "DoE regional KPI assessments with the figures they were based on. Record a PSC review where needed."}
        onRefresh={() => void load()}
      />
      <StatTiles tiles={[
        { label: "Projects reviewed", value: latest.length },
        { label: "Latest: on track", value: latest.filter((r) => r.rating === "on_track").length, tone: "text-emerald-700" },
        { label: "Latest: needs attention", value: latest.filter((r) => r.rating === "needs_attention").length, tone: "text-amber-700" },
        { label: "Latest: at risk", value: latest.filter((r) => r.rating === "at_risk").length, tone: "text-rose-700" },
      ]} />
      <ReadOnlyNotice>Calculated KPI values and DoE assessments are read-only. {kind === "psc" ? "PSC comments are stored as separate oversight reviews." : ""}</ReadOnlyNotice>
      {notice && <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p>}
      <div className="card flex flex-col gap-3 p-4 md:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search project or summary..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input-field md:w-56" value={rating} onChange={(e) => setRating(e.target.value)}>
          <option value="">All ratings</option>
          {Object.entries(KPI_RATING_META).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
        </select>
      </div>
      <div className="space-y-3">
        {visible.map((review) => (
          <div key={review.id} className="card space-y-3 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${KPI_RATING_META[review.rating]?.badge}`}>{KPI_RATING_META[review.rating]?.label}</span>
              <span className="font-semibold text-slate-900">{review.projectReference || review.projectId}</span>
              <span className="text-sm text-slate-500">{review.projectTitle}</span>
              <span className="ml-auto text-xs text-slate-400">{review.reviewPeriod} | {review.reviewerName || review.reviewerUsername} (DoE)</span>
            </div>
            <p className="text-sm text-slate-700">{review.summary}</p>
            {review.recommendations && <p className="text-sm text-slate-600"><span className="font-semibold">Recommendations:</span> {review.recommendations}</p>}
            {Object.keys(review.kpiSnapshot || {}).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(SNAPSHOT_LABELS).map(([key, label]) => (
                  review.kpiSnapshot[key] != null ? (
                    <span key={key} className="rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-600 ring-1 ring-slate-200">{label}: <b>{String(review.kpiSnapshot[key])}</b></span>
                  ) : null
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2">
              {kind === "psc" && (
                <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setReviewing(review)}>
                  <ClipboardCheck size={14} /> Record PSC Review
                </button>
              )}
              {kind === "auditor" && onOpenAuditCase && (
                <button
                  type="button"
                  className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs"
                  onClick={() => onOpenAuditCase({
                    auditArea: "kpi",
                    projectId: review.projectId,
                    title: `KPI audit: ${review.projectReference || review.projectId} ${review.reviewPeriod}`,
                    context: `${review.projectReference} ${review.reviewPeriod}`,
                  })}
                >
                  <ShieldCheck size={14} /> Open Audit Case
                </button>
              )}
            </div>
          </div>
        ))}
        {visible.length === 0 && <div className="card p-10 text-center text-slate-500">No KPI reviews match.</div>}
      </div>
      {reviewing && (
        <OversightReviewModal
          kind={kind}
          subjectType="kpi"
          heading="PSC review of KPI results"
          subjectLabel={`${reviewing.projectReference || reviewing.projectId} (${reviewing.reviewPeriod})`}
          links={{ kpiReviewId: reviewing.id, projectId: reviewing.projectId }}
          onClose={() => setReviewing(null)}
          onSaved={() => {
            setReviewing(null);
            setNotice("PSC review recorded.");
          }}
        />
      )}
    </div>
  );
}
