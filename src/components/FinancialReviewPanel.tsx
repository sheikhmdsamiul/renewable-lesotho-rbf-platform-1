import React, { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Info,
  Lock,
  StickyNote,
} from "lucide-react";
import { FinancialEvaluationRow, FinancialScoringFormula, TenderBid } from "../types";
import { getMissingDocumentLabels, getBidDocumentItems } from "./SubmittedBidModal";

interface FinancialReviewPanelProps {
  bid: TenderBid;
  row: FinancialEvaluationRow;
  lotId?: string;
  securityRequired: boolean;
  displayCurrency: string;
  baseCurrency: string;
  referenceLowest: number;
  isThisLowest: boolean;
  budget?: number;
  lotCoverage?: { total: number; priced: number };
  locked: boolean;
  lockedAt?: string;
  finalizing: boolean;
  financialFormula: FinancialScoringFormula;
  onFinalize: (payload: { justifications: Record<string, string>; comments: string }) => void;
  onCancel: () => void;
}

type ManualCheck = {
  id: string;
  label: string;
  autoPass: boolean;
  autoDetail?: string;
};

export function FinancialReviewPanel({
  bid,
  row,
  lotId,
  securityRequired,
  displayCurrency,
  baseCurrency,
  referenceLowest,
  isThisLowest,
  budget,
  lotCoverage,
  locked,
  lockedAt,
  finalizing,
  financialFormula,
  onFinalize,
  onCancel,
}: FinancialReviewPanelProps) {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [notes, setNotes] = useState("");

  const isLotWise = lotId != null;

  const currentOffer = isLotWise ? (bid.lot_offers || []).find((o) => String(o.lot) === String(lotId)) : undefined;
  const totalProjectCost = useMemo(
    () => (isLotWise ? Number(currentOffer?.bid_amount || 0) : Number(bid.bid_amount || 0)),
    [currentOffer?.bid_amount, bid.bid_amount, isLotWise],
  );
  const subsidyRequested = useMemo(
    () => (isLotWise ? Number(currentOffer?.subsidy_requested || 0) : Number(bid.subsidy_requested || 0)),
    [currentOffer?.subsidy_requested, bid.subsidy_requested, isLotWise],
  );
  const coFinancing = Math.max(0, totalProjectCost - subsidyRequested);
  const householdTotal = (bid.sites || []).reduce((sum, s) => sum + Number(s.numberOfHouseholds || 0), 0);

  const financialProposalPresent = Boolean(bid.financial_proposal_file);
  const securityPresent = !securityRequired || Boolean(bid.tender_security_file);
  const missingDocs = getMissingDocumentLabels(bid, securityRequired);
  const missingRequiredDocs = missingDocs.filter((label) => label !== "Financial Proposal" || !financialProposalPresent);
  const uploadedDocs = getBidDocumentItems(bid, securityRequired);

  const sites = bid.sites || [];
  const incompleteSites = sites.filter(
    (s) =>
      !String(s.siteName || "").trim() ||
      s.latitude == null ||
      s.longitude == null ||
      Number(s.numberOfHouseholds || 0) <= 0,
  );
  const sitesComplete = sites.length > 0 && incompleteSites.length === 0;

  const subsidyWithinBudget = budget != null ? subsidyRequested <= budget : true;
  const coFinancingPositive = totalProjectCost > 0 && subsidyRequested <= totalProjectCost;
  const subsidySane = subsidyWithinBudget && coFinancingPositive;

  const lotOffers = bid.lot_offers || [];
  const pricedOffers = lotOffers.filter((o) => Number(o.bid_amount || 0) > 0);
  const lotsPriced =
    lotCoverage != null
      ? lotCoverage.priced > 0 && lotCoverage.priced === lotCoverage.total
      : lotOffers.length === 0 || pricedOffers.length === lotOffers.length;

  const checksInfo: ManualCheck[] = useMemo(() => {
    const list: ManualCheck[] = [
      {
        id: "amount",
        label: `The bid amount of ${displayCurrency} ${Number(row.bidAmount || 0).toLocaleString()} matches the figures in the submitted financial proposal.`,
        autoPass: financialProposalPresent && coFinancingPositive,
        autoDetail: financialProposalPresent ? undefined : "No financial proposal document uploaded — confirm the figure from the document separately.",
      },
    ];
    if (securityRequired) {
      list.push({
        id: "security",
        label: "Tender security has been uploaded and is valid.",
        autoPass: securityPresent,
        autoDetail: securityPresent ? undefined : "No tender security document uploaded.",
      });
    }
    list.push({
      id: "documents",
      label: "All required documents are uploaded and legible.",
      autoPass: missingRequiredDocs.length === 0,
      autoDetail: missingRequiredDocs.length > 0 ? `Missing: ${missingRequiredDocs.join(", ")}.` : undefined,
    });
    list.push({
      id: "subsidy",
      label: `The subsidy request of ${displayCurrency} ${subsidyRequested.toLocaleString()} is within budget and the co-financing commitment is real.`,
      autoPass: subsidySane,
      autoDetail: !subsidyWithinBudget && budget != null
        ? `Requested subsidy exceeds the RBF budget of ${displayCurrency} ${budget.toLocaleString()}.`
        : !coFinancingPositive
        ? `Co-financing is negative — requested subsidy exceeds the total project cost.`
        : undefined,
    });
    list.push({
      id: "coverage",
      label: isLotWise
        ? `Every lot this bidder declared is priced (${lotCoverage?.priced ?? 0} of ${lotCoverage?.total ?? 0}) and every site row is complete.`
        : "Every site row is complete (village, district, GPS, household count).",
      autoPass: lotsPriced && sitesComplete,
      autoDetail: !lotsPriced
        ? "One or more lots have no positive offer amount."
        : !sitesComplete
        ? `${incompleteSites.length} of ${sites.length} site row${incompleteSites.length === 1 ? "" : "s"} missing GPS, village, or household counts.`
        : undefined,
    });
    return list;
  }, [
    row.bidAmount,
    displayCurrency,
    financialProposalPresent,
    coFinancingPositive,
    securityRequired,
    securityPresent,
    missingRequiredDocs,
    subsidyRequested,
    subsidySane,
    subsidyWithinBudget,
    coFinancingPositive,
    budget,
    isLotWise,
    lotCoverage?.priced,
    lotCoverage?.total,
    lotsPriced,
    sitesComplete,
    incompleteSites.length,
    sites.length,
  ]);

  const allPass = checksInfo.some((c) => !c.autoPass) === false;
  const pendingCheckCount = checksInfo.filter((c) => !checks[c.id]).length;
  const readyToFinalize = !locked && pendingCheckCount === 0;

  const handleToggle = (id: string) => {
    if (locked) return;
    setChecks((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleFinalize = () => {
    const justifications: Record<string, string> = {};
    const confirmedAt = new Date().toLocaleString();
    for (const check of checksInfo) {
      if (checks[check.id]) {
        justifications[check.label] = `Confirmed by the reviewing committee member at ${confirmedAt}.`;
      }
    }
    onFinalize({ justifications, comments: notes.trim() });
  };

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-emerald-200 bg-emerald-50/60 px-6 py-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-700">System-Calculated Financial Score</p>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="text-4xl font-bold text-emerald-800">{row.computedFinancialScore.toFixed(1)}</span>
              <span className="text-lg font-bold text-emerald-700">/ 100</span>
            </p>
            <p className="mt-1 text-sm text-emerald-900">
              {financialFormula === "linear_deviation_100"
                ? "Lowest qualifying price scores 100; every other bid loses its percentage deviation above the lowest, floored at 0."
                : "Lowest qualifying price scores 100; every other bid is scored proportionally against it."}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            {locked && (
              <span className="inline-flex items-center gap-1.5 badge bg-emerald-600 text-white">
                <Lock size={12} /> Finalized & locked
                {lockedAt && <span className="font-normal">on {new Date(lockedAt).toLocaleString()}</span>}
              </span>
            )}
            {isThisLowest ? (
              <span className="badge bg-emerald-100 text-emerald-700">Lowest qualifying bid — scores automatically</span>
            ) : (
              <span className="badge bg-slate-100 text-slate-600">
                Scored against lowest qualifying bid of {baseCurrency} {referenceLowest.toLocaleString()}
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-2xl border border-emerald-100 bg-white px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Bid Amount</p>
            <p className="mt-1 text-sm font-bold text-slate-900">{displayCurrency} {Number(row.bidAmount || 0).toLocaleString()}</p>
            {row.bidCurrency && row.bidCurrency !== displayCurrency && row.bidAmountBaseCurrency != null && (
              <p className="text-[11px] text-slate-400">≈ {displayCurrency} {row.bidAmountBaseCurrency.toLocaleString()}</p>
            )}
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-white px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Subsidy Requested</p>
            <p className="mt-1 text-sm font-bold text-slate-900">{displayCurrency} {subsidyRequested.toLocaleString()}</p>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-white px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Co-financing</p>
            <p className="mt-1 text-sm font-bold text-slate-900">{displayCurrency} {Math.max(0, totalProjectCost - subsidyRequested).toLocaleString()}</p>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-white px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Households</p>
            <p className="mt-1 text-sm font-bold text-slate-900">{householdTotal.toLocaleString()}</p>
            <p className="text-[11px] text-slate-400">across {(bid.sites || []).length} site row{(bid.sites || []).length === 1 ? "" : "s"}</p>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-6 py-3.5 flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
            <ClipboardCheck size={15} /> Verification Checklist
          </h3>
          <span className={`badge ${allPass ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            {allPass ? "All compliance checks pass" : "Review flagged items below"}
          </span>
        </div>
        <div className="p-5 space-y-3">
          {checksInfo.map((check) => {
            const autoIcon = check.autoPass ? (
              <CheckCircle2 size={14} className="text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
            );
            return (
              <div key={check.id} className="rounded-2xl border border-slate-100 bg-slate-50/60 px-4 py-3 flex gap-3">
                <div className="pt-0.5">{autoIcon}</div>
                <div className="min-w-0 flex-1">
                  <label
                    className={`flex items-start gap-3 text-sm cursor-pointer ${locked ? "cursor-default" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={locked || Boolean(checks[check.id])}
                      onChange={() => handleToggle(check.id)}
                      disabled={locked}
                      className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span className={`text-slate-700 ${locked && checks[check.id] ? "text-slate-500" : ""}`}>{check.label}</span>
                  </label>
                  {check.autoDetail && (
                    <p className="mt-1 pl-9 text-xs text-amber-700">{check.autoDetail}</p>
                  )}
                </div>
              </div>
            );
          })}
          {locked && (
            <p className="flex items-center gap-1.5 text-xs text-emerald-700">
              <CheckCircle2 size={13} /> This record is locked after your finalize — the confirmation above was recorded when it was submitted.
            </p>
          )}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-6 py-3.5">
          <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
            <StickyNote size={15} /> Verification Notes
          </h3>
        </div>
        <div className="p-5">
          <textarea
            className="input-field w-full min-h-[84px]"
            placeholder="Optional: note anything checked against the paper record — e.g. 'Amounts match including VAT', 'Bid security validity date confirmed'."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={locked}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 pt-5">
        {!locked && pendingCheckCount > 0 && (
          <p className="mr-auto flex items-center gap-1.5 text-xs text-slate-500">
            <Info size={13} />
            {allPass
              ? `Confirm ${pendingCheckCount} checklist item${pendingCheckCount === 1 ? "" : "s"} to enable the Finalize button.`
              : "Resolve the flagged items and confirm each checklist box before finalizing."}
          </p>
        )}
        <button onClick={onCancel} className="btn-secondary">Cancel</button>
        <button
          onClick={handleFinalize}
          disabled={!readyToFinalize || finalizing}
          className="btn-primary px-5 disabled:opacity-50"
        >
          {finalizing ? "Saving..." : locked ? "Finalized & locked" : "Verify & Finalize"}
        </button>
      </div>
    </div>
  );
}