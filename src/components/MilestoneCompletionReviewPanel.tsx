import React, { useEffect, useState } from "react";
import { fetchVendorDirectory, submitMilestoneCompletionReview } from "../api";
import { Milestone, MilestoneCompletionReview, MilestoneReviewDecision, VendorDirectoryEntry } from "../types";

const DECISION_LABELS: Record<MilestoneReviewDecision, string> = {
  proceed: "Proceed to next milestone",
  close: "Close project",
  transfer: "Transfer to another vendor",
  complete: "Complete project",
};

const MAX_VENDOR_PAGES = 10;

async function loadAllVendors(): Promise<VendorDirectoryEntry[]> {
  const first = await fetchVendorDirectory(1);
  const vendors = [...first.vendors];
  for (let page = 2; page <= Math.min(first.totalPages, MAX_VENDOR_PAGES); page += 1) {
    vendors.push(...(await fetchVendorDirectory(page)).vendors);
  }
  return vendors;
}

export function describeMilestoneReview(review: MilestoneCompletionReview): string {
  if (review.status === "pending") return "Awaiting RBF / Super Admin verification";
  const decision = review.decision ? DECISION_LABELS[review.decision] : "Decided";
  if (review.decision === "transfer" && review.transferredToVendorName) {
    return `${decision}: ${review.vendorName || "previous vendor"} → ${review.transferredToVendorName}`;
  }
  return decision;
}

type Props = {
  milestone: Milestone;
  isFinalMilestone: boolean;
  canDecide: boolean;
  currentVendorId?: string;
  onDecided: (updated: Milestone) => void | Promise<void>;
};

// Shown on a paid milestone: RBF / Super Admin verify the completed milestone
// and decide whether the vendor proceeds, the project closes, or the remaining
// milestones move to a different vendor.
export default function MilestoneCompletionReviewPanel({ milestone, isFinalMilestone, canDecide, currentVendorId, onDecided }: Props) {
  const review = milestone.completionReview;
  const decisions: MilestoneReviewDecision[] = isFinalMilestone ? ["complete"] : ["proceed", "close", "transfer"];
  const [decision, setDecision] = useState<MilestoneReviewDecision>(decisions[0]);
  const [notes, setNotes] = useState("");
  const [newVendorId, setNewVendorId] = useState("");
  const [vendors, setVendors] = useState<VendorDirectoryEntry[] | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (decision !== "transfer" || vendors !== null) return;
    let cancelled = false;
    loadAllVendors()
      .then((rows) => { if (!cancelled) setVendors(rows); })
      .catch(() => { if (!cancelled) setVendors([]); });
    return () => { cancelled = true; };
  }, [decision, vendors]);

  if (!review) return null;

  if (review.status === "decided") {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
        <p className="font-semibold">Completion verified — {describeMilestoneReview(review)}</p>
        <p className="mt-1 text-emerald-700">
          {review.reviewedByName ? `By ${review.reviewedByName}` : "Recorded"}
          {review.reviewedAt ? ` on ${new Date(review.reviewedAt).toLocaleString()}` : ""}
        </p>
        {review.verificationNotes && <p className="mt-2 whitespace-pre-line text-emerald-900">{review.verificationNotes}</p>}
      </div>
    );
  }

  if (!canDecide) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        <p className="font-semibold">Awaiting completion verification</p>
        <p className="mt-1">RBF / Super Admin will verify this milestone and decide whether the project proceeds to the next milestone.</p>
      </div>
    );
  }

  const transferVendors = (vendors || []).filter((vendor) => vendor.id !== String(currentVendorId || ""));
  const canSubmit = Boolean(notes.trim()) && (decision !== "transfer" || Boolean(newVendorId)) && !submitting;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await submitMilestoneCompletionReview(milestone.id, {
        decision,
        verificationNotes: notes.trim(),
        newVendorId: decision === "transfer" ? newVendorId : undefined,
      });
      await onDecided(updated);
    } catch (err: any) {
      setError(String(err?.message || "").replace(/^HTTP \d+ [^:]*:\s*/, "") || "Failed to record the milestone decision.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 space-y-3 text-sm text-slate-700">
      <div>
        <p className="font-semibold text-amber-900">Completion verification required</p>
        <p className="mt-1 text-amber-800">
          {isFinalMilestone
            ? "This was the final milestone. Verify the work to complete the project."
            : "Verify the completed milestone, then decide how the project continues. The next milestone stays locked until you choose to proceed or transfer."}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {decisions.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setDecision(value)}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
              decision === value
                ? value === "close" ? "border-rose-300 bg-rose-600 text-white" : "border-emerald-300 bg-emerald-600 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {DECISION_LABELS[value]}
          </button>
        ))}
      </div>
      {decision === "transfer" && (
        <div>
          <label className="text-xs font-semibold text-slate-600">New vendor</label>
          <select className="input-field mt-1" value={newVendorId} onChange={(e) => setNewVendorId(e.target.value)} disabled={vendors === null}>
            <option value="">{vendors === null ? "Loading vendors..." : "Select a vendor"}</option>
            {transferVendors.map((vendor) => (
              <option key={vendor.id} value={vendor.id}>
                {vendor.organizationName || vendor.fullName || vendor.username}{vendor.status && vendor.status !== "Active" ? ` (${vendor.status})` : ""}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">The remaining milestones and the project will be reassigned to this vendor.</p>
        </div>
      )}
      {decision === "close" && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          Closing ends the project now. All remaining unpaid milestones will be cancelled and no further claims can be submitted.
        </p>
      )}
      <div>
        <label className="text-xs font-semibold text-slate-600">Verification notes (required)</label>
        <textarea
          className="input-field mt-1 min-h-[80px]"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="What was verified, and the reason for this decision"
        />
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <button type="button" onClick={submit} disabled={!canSubmit} className="btn-primary w-full disabled:opacity-60">
        {submitting ? "Saving..." : `Verify & ${DECISION_LABELS[decision].toLowerCase()}`}
      </button>
    </div>
  );
}
