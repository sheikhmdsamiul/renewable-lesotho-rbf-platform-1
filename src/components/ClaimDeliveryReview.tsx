import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { ClaimAssessment, ClaimDeficiency, PaymentBlocker, PaymentClaim } from "../types";

// RMT's choice when verifying a submitted claim. "return" sends it back to the vendor.
export type RmtReviewChoice = "full" | "partial" | "return";

const money = (value: number) => `M ${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export function emptyDeficiency(): ClaimDeficiency {
  return { description: "", requiredAction: "", installationIds: [] };
}

export function filledDeficiencies(items: ClaimDeficiency[]): ClaimDeficiency[] {
  return items
    .map((d) => ({ ...d, description: d.description.trim(), requiredAction: (d.requiredAction || "").trim() }))
    .filter((d) => d.description);
}

// One-line summary of what was paid vs claimed, for list rows and TAC / PSC / vendor views.
export function describeClaimPayout(claim: PaymentClaim): string | null {
  if (claim.isPartial && claim.approvedAmount != null) {
    return `Partial: ${claim.completionPct ?? "?"}% delivered — ${money(claim.approvedAmount)} of ${money(claim.claimAmount)}`;
  }
  if (claim.carryInAmount > 0) {
    return `Includes ${money(claim.carryInAmount)} carried over from an earlier milestone`;
  }
  return null;
}

export function DeficiencyList({ items, title }: { items: ClaimDeficiency[]; title: string }) {
  if (!items.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-bold uppercase text-slate-500">{title}</p>
      <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-800">
        {items.map((d, index) => (
          <li key={index}>
            <span className="font-semibold">{d.description}</span>
            {d.requiredAction ? <span className="block text-slate-600">Action: {d.requiredAction}</span> : null}
            {d.installationIds && d.installationIds.length > 0 ? (
              <span className="block text-xs text-slate-500">Installations: {d.installationIds.join(", ")}</span>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

// Banner shown to TAC, PSC and the vendor when a claim was partly approved or carries a shortfall.
export function ClaimPayoutNotice({ claim }: { claim: PaymentClaim }) {
  const summary = describeClaimPayout(claim);
  if (!summary && claim.status !== "Returned") return null;
  if (claim.status === "Returned") {
    return (
      <div className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
        <p className="font-semibold">Returned for completion{claim.returnedAt ? ` on ${new Date(claim.returnedAt).toLocaleDateString()}` : ""}</p>
        {claim.expectedUnits ? (
          <p>Verified at review: {claim.verifiedUnits ?? 0} of {claim.expectedUnits} units.</p>
        ) : null}
        <DeficiencyList items={claim.deficiencies} title="Complete before resubmitting" />
      </div>
    );
  }
  return (
    <div className={`space-y-3 rounded-2xl border px-4 py-4 text-sm ${claim.isPartial ? "border-amber-200 bg-amber-50 text-amber-900" : "border-sky-200 bg-sky-50 text-sky-900"}`}>
      <p className="font-semibold">{summary}</p>
      {claim.isPartial ? (
        <p>
          The remaining {money(claim.shortfallAmount)} is added to the next milestone claim once the missing items are delivered and verified.
          {claim.carryOver ? ` Carry-over to Milestone ${claim.carryOver.toMilestoneNumber}: ${claim.carryOver.status}.` : ""}
        </p>
      ) : null}
      {claim.isPartial ? <DeficiencyList items={claim.deficiencies} title="Still owed" /> : null}
    </div>
  );
}

const BLOCKER_SOURCE_LABEL: Record<PaymentBlocker["source"], string> = {
  anomaly: "Anomaly flag",
  oversight: "Oversight flag",
  audit: "Audit",
  site_visit: "Site visit",
};

const BLOCKER_OWNER_LABEL: Record<PaymentBlocker["owner"], string> = {
  vendor: "waiting on the vendor",
  rmt: "waiting on the RMT",
  auditor: "waiting on the Auditor",
};

// Open findings that stop this claim from being approved or paid. `null` while loading.
export function PaymentHoldNotice({ blockers }: { blockers: PaymentBlocker[] | null }) {
  if (!blockers || blockers.length === 0) return null;
  return (
    <div className="space-y-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-900">
      <p className="font-semibold">Payment on hold: {blockers.length} open finding{blockers.length === 1 ? "" : "s"}</p>
      <p className="text-xs text-rose-800">
        The claim cannot be approved or paid until these are resolved through their own workflows. You can still return or reject it.
      </p>
      <ul className="space-y-1.5">
        {blockers.map((b) => (
          <li key={`${b.source}-${b.id}`} className="rounded-lg bg-white/70 px-3 py-2">
            <span className="text-xs font-bold uppercase text-rose-700">{BLOCKER_SOURCE_LABEL[b.source] ?? b.source}</span>{" "}
            {b.title}
            <span className="block text-xs text-rose-700">
              {BLOCKER_OWNER_LABEL[b.owner] ?? ""}
              {b.dueDate ? ` · due ${new Date(b.dueDate).toLocaleDateString()}` : ""}
              {b.overdue ? " · OVERDUE" : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Props = {
  claim: PaymentClaim;
  assessment: ClaimAssessment | null;
  loading: boolean;
  choice: RmtReviewChoice;
  onChoiceChange: (choice: RmtReviewChoice) => void;
  assessedPct: string;
  onAssessedPctChange: (value: string) => void;
  deficiencies: ClaimDeficiency[];
  onDeficienciesChange: (items: ClaimDeficiency[]) => void;
};

// RMT verification of a submitted milestone claim: approve in full, approve the verified
// share (at least the configured minimum, carrying the rest to the next milestone), or
// return it to the vendor with what must be completed.
export default function ClaimDeliveryReview({
  claim,
  assessment,
  loading,
  choice,
  onChoiceChange,
  assessedPct,
  onAssessedPctChange,
  deficiencies,
  onDeficienciesChange,
}: Props) {
  const unitBased = assessment != null && assessment.completionPct != null;
  const pct = unitBased ? assessment!.completionPct! : assessedPct === "" ? null : Number(assessedPct);
  const effectivePct = unitBased && assessedPct !== "" ? Math.min(Number(assessedPct), assessment!.completionPct!) : pct;
  const minimum = assessment?.partialPaymentMinPct ?? 70;
  const partialBlockedReason = !assessment
    ? null
    : assessment.isFinalMilestone
      ? "The final milestone cannot be paid partially; return it for completion instead."
      : effectivePct != null && effectivePct < minimum
        ? `Only ${effectivePct}% delivered; partial payment needs at least ${minimum}%.`
        : effectivePct != null && effectivePct >= 100
          ? "Fully delivered; approve in full."
          : null;
  const partialAmount = effectivePct != null ? Math.round(claim.claimAmount * effectivePct) / 100 : null;

  const updateDeficiency = (index: number, patch: Partial<ClaimDeficiency>) => {
    onDeficienciesChange(deficiencies.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };

  const options: { value: RmtReviewChoice; label: string; hint: string; disabled?: boolean }[] = [
    { value: "full", label: "Approve in full", hint: money(claim.claimAmount) },
    {
      value: "partial",
      label: "Approve partially",
      hint: partialBlockedReason || (partialAmount != null ? `${money(partialAmount)} now, rest carried over` : "Enter the assessed %"),
      disabled: Boolean(partialBlockedReason),
    },
    { value: "return", label: "Return for completion", hint: "Vendor fixes and resubmits" },
  ];

  return (
    <div className="space-y-4 border-b border-slate-200 pb-6">
      <h3 className="text-sm font-bold uppercase text-slate-900">Delivery verification</h3>
      {loading ? (
        <p className="text-sm text-slate-500">Checking verified installations…</p>
      ) : assessment ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Verified / expected units</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">
              {unitBased ? `${assessment.verifiedUnits} / ${assessment.expectedUnits}` : "No installation target"}
            </p>
            {assessment.carryInUnits > 0 ? (
              <p className="mt-1 text-xs text-slate-600">Includes {assessment.carryInUnits} carried-over units</p>
            ) : null}
          </div>
          <div className={`rounded-xl border p-3 ${pct != null && pct >= 100 ? "border-emerald-200 bg-emerald-50" : pct != null && pct >= minimum ? "border-amber-200 bg-amber-50" : "border-rose-200 bg-rose-50"}`}>
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Delivered</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{pct != null ? `${pct}%` : "Assess below"}</p>
            <p className="mt-1 text-xs text-slate-600">Partial payment minimum: {minimum}%</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Claimed</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{money(claim.claimAmount)}</p>
            {assessment.carryInAmount > 0 ? (
              <p className="mt-1 text-xs text-slate-600">Includes {money(assessment.carryInAmount)} carried over</p>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-500">Delivery figures are unavailable; you can still return or approve the claim.</p>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={option.disabled}
            onClick={() => onChoiceChange(option.value)}
            className={`rounded-xl border px-3 py-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${choice === option.value ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200" : "border-slate-200 bg-white hover:bg-slate-50"}`}
          >
            <span className="block text-sm font-semibold text-slate-900">{option.label}</span>
            <span className="mt-1 block text-xs text-slate-600">{option.hint}</span>
          </button>
        ))}
      </div>

      {choice === "partial" ? (
        <label className="block space-y-1 text-sm">
          <span className="font-semibold text-slate-800">
            {unitBased ? "Assessed completion % (optional, cannot exceed verified delivery)" : "Assessed completion %"}
          </span>
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={assessedPct}
            onChange={(e) => onAssessedPctChange(e.target.value)}
            placeholder={unitBased ? String(assessment!.completionPct) : `At least ${minimum}`}
            className="w-40 rounded-lg border border-slate-200 p-2"
          />
        </label>
      ) : null}

      {choice !== "full" ? (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-slate-800">
            {choice === "return" ? "What the vendor must complete before resubmitting" : "What is still owed with the next milestone"}
          </p>
          {deficiencies.map((d, index) => (
            <div key={index} className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 p-3 sm:grid-cols-[1fr_1fr_auto]">
              <input
                value={d.description}
                onChange={(e) => updateDeficiency(index, { description: e.target.value })}
                placeholder="What is missing (e.g. 12 households not installed)"
                className="rounded-lg border border-slate-200 p-2 text-sm"
              />
              <input
                value={d.requiredAction || ""}
                onChange={(e) => updateDeficiency(index, { requiredAction: e.target.value })}
                placeholder="Required action"
                className="rounded-lg border border-slate-200 p-2 text-sm"
              />
              <button
                type="button"
                onClick={() => onDeficienciesChange(deficiencies.filter((_, i) => i !== index))}
                className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
                aria-label="Remove item"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => onDeficienciesChange([...deficiencies, emptyDeficiency()])}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            <Plus size={14} /> Add item
          </button>
        </div>
      ) : null}
    </div>
  );
}
