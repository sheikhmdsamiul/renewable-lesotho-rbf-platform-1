import { Tender, TenderStatus } from "../types";

/**
 * One shared reading of "where is this tender, and what has to happen next?" — used by
 * the Tender / Award Management lists, the tender detail page and the award view, so
 * every screen describes a tender's state in the same words.
 */

export type StageTone = "neutral" | "info" | "action" | "success" | "warning" | "danger";

export interface TenderStage {
  /** Index into TENDER_LIFECYCLE of the step the tender is currently on. */
  step: number;
  /** Short status label. */
  label: string;
  /** What has to happen next, in plain language. */
  nextStep: string;
  /** Who is expected to act next. */
  owner: "RBF" | "Super Admin" | "Vendors" | "Evaluation Committee" | "None";
  tone: StageTone;
  /** The deadline/date that matters right now, if any. */
  keyDate?: { label: string; value: string };
}

export const TENDER_LIFECYCLE = [
  "Draft",
  "Verified",
  "Publish approval",
  "Open for bids",
  "Evaluation",
  "Intent to award",
  "Standstill",
  "Awarded",
] as const;

export const EOI_LIFECYCLE = ["Draft", "Open for EOIs", "Shortlisting", "Shortlist finalized"] as const;

export const STAGE_TONE_CLASSES: Record<StageTone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  info: "bg-sky-100 text-sky-700",
  action: "bg-amber-100 text-amber-800",
  success: "bg-emerald-100 text-emerald-700",
  warning: "bg-orange-100 text-orange-700",
  danger: "bg-rose-100 text-rose-700",
};

/** "in 3 days", "in 5 hours", "2 days ago". */
export function relativeTime(iso?: string | null, now = Date.now()): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - now;
  if (Number.isNaN(ms)) return "";
  const abs = Math.abs(ms);
  const minutes = Math.round(abs / 60000);
  const hours = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  const span = minutes < 60 ? `${minutes} min` : hours < 48 ? `${hours} hour${hours === 1 ? "" : "s"}` : `${days} day${days === 1 ? "" : "s"}`;
  return ms >= 0 ? `in ${span}` : `${span} ago`;
}

export function formatDateTimeShort(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** The submission deadline that binds vendors right now. */
export function openStageDeadline(t: Tender): string | undefined {
  if (t.isEoiInviteOnly) return t.eoiDeadline || t.deadline;
  return t.technicalDeadline || t.deadline;
}

export function workflowLabel(t: Tender): string {
  if (t.isEoiInviteOnly) return "EOI Invite";
  if (t.procurementWorkflow === "eoi_combined") return t.linkedEoiTenderId ? "EOI → Combined (linked)" : "EOI → Combined";
  if (t.procurementWorkflow === "combined") return "Combined (single stage)";
  if (t.procurementWorkflow === "sequential") return "Sequential (legacy)";
  return t.procurementWorkflow || "—";
}

function eoiStage(t: Tender, now: number): TenderStage {
  const deadline = t.eoiDeadline || t.deadline;
  if (t.status === TenderStatus.DRAFT) {
    return { step: 0, label: "Draft", nextStep: "Publish the EOI Invite to collect Expressions of Interest", owner: "RBF", tone: "neutral" };
  }
  if (t.shortlistFinalizedAt) {
    return {
      step: 3,
      label: "Shortlist finalized",
      nextStep: (t.linkedTenderCount ?? t.linkedTendersSummary?.length ?? 0) > 0
        ? "Tender created from this shortlist"
        : "Create the tender from this shortlist",
      owner: (t.linkedTenderCount ?? t.linkedTendersSummary?.length ?? 0) > 0 ? "None" : "RBF",
      tone: "success",
    };
  }
  if (t.status === TenderStatus.PUBLISHED && deadline && new Date(deadline).getTime() > now) {
    return {
      step: 1,
      label: "Open for EOIs",
      nextStep: `Vendors respond until the deadline (${relativeTime(deadline, now)})`,
      owner: "Vendors",
      tone: "info",
      keyDate: { label: "EOI closes", value: deadline },
    };
  }
  return {
    step: 2,
    label: "Shortlisting",
    nextStep: "Shortlist or reject every response, then finalize the shortlist",
    owner: "RBF",
    tone: "action",
  };
}

export function getTenderStage(t: Tender, now = Date.now()): TenderStage {
  if (t.isEoiInviteOnly) return eoiStage(t, now);

  switch (t.status) {
    case TenderStatus.DRAFT:
      if (!t.isVerified) {
        return { step: 0, label: "Draft", nextStep: "Review the details and verify the tender", owner: "RBF", tone: "neutral" };
      }
      if (t.publishApprovalStatus === "approved") {
        return { step: 2, label: "Approved to publish", nextStep: "Publish the tender to open bidding", owner: "RBF", tone: "action" };
      }
      if (t.publishApprovalStatus === "changes_requested") {
        return { step: 1, label: "Changes requested", nextStep: "Make the Super Admin's requested changes, then request approval again", owner: "RBF", tone: "warning" };
      }
      if (t.publishApprovalStatus === "rejected") {
        return { step: 1, label: "Publish rejected", nextStep: "Revise the tender, then request approval again", owner: "RBF", tone: "danger" };
      }
      return { step: 1, label: "Verified", nextStep: "Request Super Admin approval to publish", owner: "RBF", tone: "action" };

    case TenderStatus.PENDING_PUBLISH_APPROVAL:
      return { step: 2, label: "Awaiting publish approval", nextStep: "Super Admin approves, rejects or requests changes", owner: "Super Admin", tone: "info" };

    case TenderStatus.PUBLISHED: {
      const deadline = openStageDeadline(t);
      if (deadline && new Date(deadline).getTime() > now) {
        return {
          step: 3,
          label: "Open for bids",
          nextStep: `Vendors submit until the deadline (${relativeTime(deadline, now)})`,
          owner: "Vendors",
          tone: "info",
          keyDate: { label: "Submissions close", value: deadline },
        };
      }
      return {
        step: 3,
        label: "Deadline passed",
        nextStep: "Close the tender to stop submissions and start evaluation",
        owner: "RBF",
        tone: "action",
        keyDate: deadline ? { label: "Closed for submissions", value: deadline } : undefined,
      };
    }

    case TenderStatus.CLOSED:
      return {
        step: 4,
        label: "Submissions closed",
        nextStep: "Record the bid opening; the Evaluation Committee then scores the bids",
        owner: "RBF",
        tone: "action",
        keyDate: t.closedAt ? { label: "Closed", value: t.closedAt } : undefined,
      };

    case TenderStatus.EVALUATION:
      if (t.hasPendingIntentAward) {
        return { step: 5, label: "Intent awaiting approval", nextStep: "Super Admin approves or returns the proposed Intent to Award", owner: "Super Admin", tone: "info" };
      }
      return { step: 4, label: "Under evaluation", nextStep: "Committee scores the bids; then the RBF requests an Intent to Award", owner: "Evaluation Committee", tone: "info" };

    case TenderStatus.STANDSTILL: {
      const until = t.coolingOffUntil;
      if (until && new Date(until).getTime() > now) {
        return {
          step: 6,
          label: "Standstill",
          nextStep: `Bidders may challenge until the standstill ends (${relativeTime(until, now)})`,
          owner: "Vendors",
          tone: "info",
          keyDate: { label: "Standstill ends", value: until },
        };
      }
      return { step: 6, label: "Standstill ended", nextStep: "Confirm the final award", owner: "RBF", tone: "action", keyDate: until ? { label: "Standstill ended", value: until } : undefined };
    }

    case TenderStatus.DISPUTED:
      return { step: 6, label: "Award challenged", nextStep: "Review and resolve the bidder's challenge", owner: "RBF", tone: "danger", keyDate: t.disputeStartedAt ? { label: "Challenge filed", value: t.disputeStartedAt } : undefined };

    case TenderStatus.AWARDED: {
      const contracts = t.contractsSummary || [];
      const awardee = t.awardedVendorName ? `Awarded to ${t.awardedVendorName}` : "Awarded";
      if (contracts.length === 0) {
        return { step: 7, label: awardee, nextStep: "Generate the contract", owner: "RBF", tone: "action", keyDate: t.awardedAt ? { label: "Awarded", value: t.awardedAt } : undefined };
      }
      const unsigned = contracts.filter(c => c.status !== "Approved" && c.status !== "Closed");
      if (unsigned.length > 0) {
        return { step: 7, label: awardee, nextStep: `Finalize ${unsigned.length} contract${unsigned.length === 1 ? "" : "s"} (signature and approval)`, owner: "RBF", tone: "action", keyDate: t.awardedAt ? { label: "Awarded", value: t.awardedAt } : undefined };
      }
      const unassigned = contracts.filter(c => !c.hasProject);
      if (unassigned.length > 0) {
        return { step: 7, label: awardee, nextStep: `Assign ${unassigned.length === 1 ? "the project" : `${unassigned.length} projects`} to start delivery`, owner: "RBF", tone: "action", keyDate: t.awardedAt ? { label: "Awarded", value: t.awardedAt } : undefined };
      }
      return { step: 7, label: awardee, nextStep: "Contract approved and project assigned — delivery under way", owner: "None", tone: "success", keyDate: t.awardedAt ? { label: "Awarded", value: t.awardedAt } : undefined };
    }

    default:
      return { step: 0, label: t.status, nextStep: "", owner: "None", tone: "neutral" };
  }
}
