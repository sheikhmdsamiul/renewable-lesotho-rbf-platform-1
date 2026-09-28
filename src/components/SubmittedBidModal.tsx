import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, History, X } from "lucide-react";
import { TenderBid } from "../types";
import { fetchTenderBids } from "../api";

export interface BidDocumentItem {
  label: string;
  key: keyof TenderBid;
  security?: boolean;
}

export const BID_DOCUMENT_ITEMS: BidDocumentItem[] = [
  { label: "Technical Proposal", key: "technical_proposal_file" },
  { label: "Financial Proposal", key: "financial_proposal_file" },
  { label: "Bill of Quantities", key: "boq_file" },
  { label: "Implementation Plan", key: "implementation_plan_file" },
  { label: "O&M Plan", key: "om_plan_file" },
  { label: "Gender Action Plan", key: "gender_action_plan_file" },
  { label: "Reporting Templates", key: "reporting_templates_file" },
  { label: "Distribution Map", key: "distribution_map_file" },
  { label: "Tender Security", key: "tender_security_file", security: true },
];

export function getBidDocumentItems(bid: TenderBid, securityRequired: boolean): BidDocumentItem[] {
  return BID_DOCUMENT_ITEMS.filter((doc) => !doc.security || securityRequired).filter((doc) => Boolean(bid[doc.key]));
}

export function getMissingDocumentLabels(bid: TenderBid, securityRequired: boolean): string[] {
  return BID_DOCUMENT_ITEMS.filter((doc) => !doc.security || securityRequired)
    .filter((doc) => !bid[doc.key])
    .map((doc) => doc.label);
}

function isPastEoiStage(bid: TenderBid): boolean {
  return bid.stage_key === "technical" || bid.stage_key === "financial" || bid.stage_key === "combined";
}

/**
 * Read-only view of everything a vendor submitted for a bid — financial proposal,
 * technical specification, sites, social inclusion targets, narrative, and documents.
 * Shared by Technical Evaluation and Financial Evaluation so both stages "verify by
 * seeing the overall bid" the same way.
 */
export function SubmittedBidModal({
  bid: initialBid,
  lotNameById,
  securityRequired,
  onClose,
  children,
}: {
  bid: TenderBid;
  lotNameById: Record<string, string>;
  securityRequired: boolean;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  // Every version of this vendor's bid for this tender (EOI/Technical/Financial
  // drafts and resubmissions) — lets the reviewer (RBF Official, Evaluation
  // Committee, or Super Admin) switch between and see the full submission history,
  // not just the single version that happened to be opened.
  const [versions, setVersions] = React.useState<TenderBid[]>([initialBid]);
  const [activeVersionId, setActiveVersionId] = React.useState(initialBid.id);
  React.useEffect(() => {
    setVersions([initialBid]);
    setActiveVersionId(initialBid.id);
    fetchTenderBids(initialBid.tender, undefined, initialBid.vendor_id)
      .then((rows) => { if (rows.length) setVersions(rows); })
      .catch(() => {});
  }, [initialBid.id]);
  const versionsSorted = [...versions].sort((a, b) => (b.version_number || 0) - (a.version_number || 0));
  const bid = versions.find((v) => v.id === activeVersionId) || initialBid;
  const displayCurrency = bid.bid_currency || "LSL";
  const totalProjectCost = Number(bid.bid_amount || 0);
  const subsidyRequested = Number(bid.subsidy_requested || 0);
  const coFinancingAmount = Math.max(
    0,
    Number(bid.system_configuration?.co_financing_amount_lsl ?? (totalProjectCost - subsidyRequested))
  );
  const totalHouseholds = (bid.sites || []).reduce(
    (sum, site) => sum + Number(site.numberOfHouseholds || 0),
    0
  );
  const costPerConnection = subsidyRequested > 0 && totalHouseholds > 0 ? subsidyRequested / totalHouseholds : null;
  const isStageTwoBid = isPastEoiStage(bid);
  const isLotWise = Object.keys(lotNameById).length > 0;
  const allDocuments = getBidDocumentItems(bid, securityRequired);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[220] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.96, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.96, opacity: 0 }}
          className="bg-white rounded-3xl shadow-2xl w-full max-w-6xl max-h-[88vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur px-6 py-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Submitted Bid Review</h2>
              <p className="text-sm text-slate-500">
                {bid.vendor_name} • {bid.tender_name || bid.tender_reference || bid.tender} • {bid.stage_badge || bid.stage || "Bid"}
              </p>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
              <X size={18} />
            </button>
          </div>

          <div className="p-6 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Vendor</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{bid.vendor_name}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Status</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{bid.status}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Version</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{bid.version_number}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Submitted</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{bid.submitted_at ? new Date(bid.submitted_at).toLocaleString() : "Draft"}</p>
              </div>
            </div>

            {versionsSorted.length > 1 && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <History size={15} className="text-slate-400" />
                  <p className="text-xs font-bold uppercase tracking-widest text-slate-500">
                    Version History — {versionsSorted.length} submission{versionsSorted.length === 1 ? "" : "s"} for this vendor on this tender
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {versionsSorted.map((v) => {
                    const isActive = v.id === activeVersionId;
                    return (
                      <button
                        key={v.id}
                        type="button"
                        onClick={() => setActiveVersionId(v.id)}
                        className={`rounded-xl border px-3 py-2 text-left transition ${isActive ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"}`}
                      >
                        <p className="text-xs font-bold">
                          Version {v.version_number} · {v.stage_badge || v.stage || "Bid"}
                        </p>
                        <p className={`text-[11px] ${isActive ? "text-slate-300" : "text-slate-500"}`}>
                          {v.status}{v.submitted_at ? ` — ${new Date(v.submitted_at).toLocaleDateString()}` : ""}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {children}

            <div className="rounded-3xl border border-slate-200 overflow-hidden">
              <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                <h3 className="text-lg font-bold text-slate-900">Section A: Financial Proposal</h3>
              </div>
              {Array.isArray(bid.lot_offers) && bid.lot_offers.length > 0 ? (
                <div className="p-6 space-y-4">
                  <p className="text-sm text-slate-500">This is a lot-wise bid — pricing is set per lot rather than as a single figure.</p>
                  <div className="overflow-x-auto rounded-2xl border border-slate-100">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-slate-50 text-left text-[10px] font-bold uppercase tracking-widest text-slate-400">
                          <th className="px-4 py-3">Lot</th>
                          <th className="px-4 py-3">Bid Amount</th>
                          <th className="px-4 py-3">Subsidy Requested</th>
                          <th className="px-4 py-3">Co-financing</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bid.lot_offers.map((offer, i) => {
                          const offerAmount = Number(offer.bid_amount || 0);
                          const offerSubsidy = Number(offer.subsidy_requested || 0);
                          return (
                            <tr key={offer.lot ?? i} className="border-t border-slate-100">
                              <td className="px-4 py-3 font-semibold text-slate-900">{offer.lot_name || `Lot ${i + 1}`}</td>
                              <td className="px-4 py-3 text-slate-700">{displayCurrency} {offerAmount.toLocaleString()}</td>
                              <td className="px-4 py-3 text-slate-700">{displayCurrency} {offerSubsidy.toLocaleString()}</td>
                              <td className="px-4 py-3 text-slate-700">{displayCurrency} {Math.max(0, offerAmount - offerSubsidy).toLocaleString()}</td>
                            </tr>
                          );
                        })}
                        <tr className="border-t border-slate-200 bg-slate-50 font-bold text-slate-900">
                          <td className="px-4 py-3">Total ({bid.lot_offers.length} lot{bid.lot_offers.length === 1 ? "" : "s"})</td>
                          <td className="px-4 py-3">{displayCurrency} {bid.lot_offers.reduce((sum, o) => sum + Number(o.bid_amount || 0), 0).toLocaleString()}</td>
                          <td className="px-4 py-3">{displayCurrency} {bid.lot_offers.reduce((sum, o) => sum + Number(o.subsidy_requested || 0), 0).toLocaleString()}</td>
                          <td className="px-4 py-3">{displayCurrency} {bid.lot_offers.reduce((sum, o) => sum + Math.max(0, Number(o.bid_amount || 0) - Number(o.subsidy_requested || 0)), 0).toLocaleString()}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Total Project Cost</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{displayCurrency} {totalProjectCost.toLocaleString()}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Subsidy Requested</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{displayCurrency} {subsidyRequested.toLocaleString()}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Co-financing</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{displayCurrency} {coFinancingAmount.toLocaleString()}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Cost Per Connection</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{costPerConnection != null ? `${displayCurrency} ${costPerConnection.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "Not enough data"}</p>
                  </div>
                </div>
              )}
            </div>

            {isStageTwoBid && (
              <div className="rounded-3xl border border-slate-200 overflow-hidden">
                <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                  <h3 className="text-lg font-bold text-slate-900">Section B: Technical Specification</h3>
                </div>
                <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Technology Type</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.system_configuration?.technology_type || bid.technology_type || "Not provided"}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Brand & Model</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.device_brand_model || "Not provided"}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Technology Tier</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.tech_tier || "Not provided"}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Energy Target</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.energy_target || bid.energy_target_kwh_month ? `${bid.energy_target || bid.energy_target_kwh_month} kWh/month` : "Not provided"}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Warranty Period</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.warranty_period || bid.warranty_period_months ? `${bid.warranty_period || bid.warranty_period_months} months` : "Not provided"}</p>
                  </div>
                </div>
              </div>
            )}

            <div className="rounded-3xl border border-slate-200 overflow-hidden">
              <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                <h3 className="text-lg font-bold text-slate-900">Section C: Project Sites & Scope</h3>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Primary District</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{bid.sites?.find(site => site.district)?.district || "Not provided"}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Installation Target</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{totalHouseholds.toLocaleString()} households</p>
                  </div>
                </div>
                <div className="overflow-x-auto rounded-2xl border border-slate-100">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-slate-500">
                      <tr>
                        {[...(isLotWise ? ["Lot"] : []), "Village", "District", "Latitude", "Longitude", "Households", "Target Technology"].map(label => (
                          <th key={label} className="px-4 py-3 text-left font-semibold">{label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(bid.sites || []).map((site, index) => (
                        <tr key={`${site.siteName}-${index}`} className="border-t border-slate-100">
                          {isLotWise && (
                            <td className="px-4 py-3 text-slate-700">{site.lot ? (lotNameById[String(site.lot)] || `Lot ${site.lot}`) : "N/A"}</td>
                          )}
                          <td className="px-4 py-3 text-slate-700">{site.siteName || "N/A"}</td>
                          <td className="px-4 py-3 text-slate-700">{site.district || "N/A"}</td>
                          <td className="px-4 py-3 text-slate-700">{site.latitude != null ? site.latitude : "N/A"}</td>
                          <td className="px-4 py-3 text-slate-700">{site.longitude != null ? site.longitude : "N/A"}</td>
                          <td className="px-4 py-3 text-slate-700">{site.numberOfHouseholds || "N/A"}</td>
                          <td className="px-4 py-3 text-slate-700">{site.targetTechnology || "N/A"}</td>
                        </tr>
                      ))}
                      {(bid.sites || []).length === 0 && (
                        <tr>
                          <td colSpan={isLotWise ? 7 : 6} className="px-4 py-6 text-center text-slate-500">No site rows submitted.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 overflow-hidden">
              <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                <h3 className="text-lg font-bold text-slate-900">Section D: Social Inclusion Commitments</h3>
              </div>
              <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Female-Headed Target</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{bid.female_target_pct ?? 0}%</p>
                </div>
                <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Vulnerable Group Target</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{bid.vulnerable_target_pct ?? 0}%</p>
                </div>
                <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Low-Income Target</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{bid.low_income_target_pct ?? 0}%</p>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 overflow-hidden">
              <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                <h3 className="text-lg font-bold text-slate-900">Section E: Project Narrative</h3>
              </div>
              <div className="p-6">
                <div className="rounded-2xl border border-slate-100 bg-white px-4 py-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Implementation Strategy</p>
                  <p className="mt-3 text-sm text-slate-700 whitespace-pre-wrap">{bid.concept_note || "Not provided"}</p>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 overflow-hidden">
              <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
                <h3 className="text-lg font-bold text-slate-900">Uploaded Documents</h3>
              </div>
              <div className="p-6 space-y-3">
                {allDocuments.map(doc => (
                  <a
                    key={doc.label}
                    href={String(bid[doc.key])}
                    target="_blank"
                    rel="noreferrer"
                    className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 border border-transparent hover:border-slate-100 transition-all text-left group"
                  >
                    <div className="p-2 rounded-lg bg-slate-100 text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600">
                      <FileText size={18} />
                    </div>
                    <span className="text-sm font-medium text-slate-700 truncate">{doc.label}</span>
                  </a>
                ))}
                {allDocuments.length === 0 && (
                  <p className="text-sm text-slate-500">No documents uploaded for this bid.</p>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
