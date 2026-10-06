/**
 * Read-only procurement views for PSC oversight and the Auditor's procurement/contract audit.
 * Tenders, bids, evaluator scores, awards and contracts are shown exactly as recorded by
 * RMT and the Evaluation Committee; nothing here can change them.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Search, ShieldCheck } from "lucide-react";
import {
  fetchAllBidEvaluationsForOversight,
  fetchAllTenderBidsForOversight,
  fetchAllTenderContractsForOversight,
  fetchAllTendersForOversight,
} from "../api";
import { Tender, TenderBid, TenderBidEvaluation, TenderContract, TenderStatus } from "../types";
import { apiErrorMessage, AuditCasePrefill, ErrorCard, LoadingCard, PageHeader, StatTiles } from "./OversightShared";

export type ProcurementView = "active" | "history" | "evaluations" | "rejected_bids" | "contracts";

const VIEW_META: Record<ProcurementView, { label: string; title: string; description: string }> = {
  active: { label: "Active Tenders", title: "Active Tenders", description: "Tenders currently published, under evaluation or in standstill." },
  history: { label: "Tender History", title: "Tender History", description: "Awarded and closed tenders." },
  evaluations: { label: "Bid Evaluations", title: "Bid Evaluations", description: "Evaluator scores per bid, as submitted by the Evaluation Committee." },
  rejected_bids: { label: "Rejected Bids", title: "Rejected Bids", description: "Bids that were rejected or not awarded, with the recorded reason." },
  contracts: { label: "Awards & Contracts", title: "Awards & Contracts", description: "Awarded contracts and their signature and approval status." },
};

const ACTIVE_STATUSES = new Set<string>([
  TenderStatus.PENDING_PUBLISH_APPROVAL, TenderStatus.PUBLISHED, TenderStatus.EVALUATION, TenderStatus.STANDSTILL, TenderStatus.DISPUTED,
]);
const HISTORY_STATUSES = new Set<string>([TenderStatus.AWARDED, TenderStatus.CLOSED]);

const formatDate = (value?: string | null) => (value ? new Date(value).toLocaleDateString("en-GB") : "-");
const money = (value?: number | null) => (value != null ? Math.round(value).toLocaleString() : "-");

const STATUS_TONE: Record<string, string> = {
  Published: "bg-blue-100 text-blue-700",
  Evaluation: "bg-amber-100 text-amber-700",
  Standstill: "bg-violet-100 text-violet-700",
  Disputed: "bg-rose-100 text-rose-700",
  Awarded: "bg-emerald-100 text-emerald-700",
  Closed: "bg-slate-200 text-slate-700",
  Approved: "bg-emerald-100 text-emerald-700",
  Signed: "bg-blue-100 text-blue-700",
  Rejected: "bg-rose-100 text-rose-700",
  "Not Awarded": "bg-slate-200 text-slate-700",
};

const Pill = ({ value }: { value?: string }) => (
  <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_TONE[value || ""] || "bg-slate-100 text-slate-700"}`}>{value || "-"}</span>
);

export function ProcurementOversightView({
  views,
  title,
  description,
  onOpenAuditCase,
}: {
  /** One view hides the tab bar (PSC sidebar entries); several show tabs (Auditor procurement audit). */
  views: ProcurementView[];
  title?: string;
  description?: string;
  onOpenAuditCase?: (prefill: AuditCasePrefill) => void;
}) {
  const [view, setView] = useState<ProcurementView>(views[0]);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [bids, setBids] = useState<TenderBid[]>([]);
  const [evaluations, setEvaluations] = useState<TenderBidEvaluation[]>([]);
  const [contracts, setContracts] = useState<TenderContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tenderFilter, setTenderFilter] = useState("");

  const needs = useMemo(() => new Set(views), [views]);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tenderList, bidList, evaluationList, contractList] = await Promise.all([
        fetchAllTendersForOversight(),
        needs.has("evaluations") || needs.has("rejected_bids") ? fetchAllTenderBidsForOversight() : Promise.resolve([]),
        needs.has("evaluations") ? fetchAllBidEvaluationsForOversight() : Promise.resolve([]),
        needs.has("contracts") ? fetchAllTenderContractsForOversight() : Promise.resolve([]),
      ]);
      setTenders(tenderList);
      setBids(bidList);
      setEvaluations(evaluationList);
      setContracts(contractList);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load procurement records."));
    } finally {
      setLoading(false);
    }
  }, [needs]);

  useEffect(() => {
    void load();
  }, [load]);

  const tenderById = useMemo(() => new Map(tenders.map((tender) => [tender.id, tender])), [tenders]);
  const bidById = useMemo(() => new Map(bids.map((bid) => [bid.id, bid])), [bids]);
  const term = search.trim().toLowerCase();
  const matches = (...values: (string | undefined | null)[]) => !term || values.some((value) => String(value || "").toLowerCase().includes(term));

  if (loading) return <LoadingCard label="Loading procurement records..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const meta = VIEW_META[view];
  const auditButton = (prefill: AuditCasePrefill) => onOpenAuditCase && (
    <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => onOpenAuditCase(prefill)}>
      <ShieldCheck size={14} /> Audit
    </button>
  );

  const tenderRows = tenders.filter((tender) => (view === "active" ? ACTIVE_STATUSES : HISTORY_STATUSES).has(tender.status) &&
    matches(tender.referenceNumber, tender.name, tender.department));

  const evaluationRows = evaluations
    .map((evaluation) => ({ evaluation, bid: bidById.get(evaluation.bid) }))
    .filter(({ bid, evaluation }) => (!tenderFilter || bid?.tender === tenderFilter) &&
      matches(bid?.vendor_name, bid?.tender_reference, bid?.tender_name, evaluation.evaluatorUsername));

  const rejectedRows = bids.filter((bid) => ["Rejected", "Not Awarded"].includes(String(bid.status)) &&
    (!tenderFilter || bid.tender === tenderFilter) && matches(bid.vendor_name, bid.tender_reference, bid.tender_name, bid.rejection_reason));

  const contractRows = contracts.filter((contract) => matches(contract.referenceNumber, contract.vendorName, tenderById.get(contract.tender)?.name));

  const tenderSelect = (
    <select className="input-field md:w-72" value={tenderFilter} onChange={(e) => setTenderFilter(e.target.value)}>
      <option value="">All tenders</option>
      {tenders.map((tender) => <option key={tender.id} value={tender.id}>{tender.referenceNumber} - {tender.name}</option>)}
    </select>
  );

  return (
    <div className="space-y-6">
      <PageHeader title={title || meta.title} description={description || `${meta.description} Read-only.`} onRefresh={() => void load()} />
      {views.length > 1 && (
        <div className="flex flex-wrap gap-2 border-b border-slate-200">
          {views.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setView(id)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${id === view ? "border-emerald-600 text-emerald-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}
            >
              {VIEW_META[id].label}
            </button>
          ))}
        </div>
      )}
      {(view === "active" || view === "history") && (
        <StatTiles tiles={[
          { label: "Tenders", value: tenderRows.length },
          { label: "Under evaluation", value: tenderRows.filter((t) => t.status === TenderStatus.EVALUATION).length, tone: "text-amber-700" },
          { label: "Awarded", value: tenderRows.filter((t) => t.status === TenderStatus.AWARDED).length, tone: "text-emerald-700" },
          { label: "Disputed", value: tenderRows.filter((t) => t.status === TenderStatus.DISPUTED).length, tone: "text-rose-700" },
        ]} />
      )}
      <div className="card flex flex-col gap-3 p-4 md:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search reference, name, vendor..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {(view === "evaluations" || view === "rejected_bids") && tenderSelect}
      </div>

      <div className="card overflow-x-auto">
        {(view === "active" || view === "history") && (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Reference</th>
                <th className="px-4 py-3 text-left font-semibold">Tender</th>
                <th className="px-4 py-3 text-left font-semibold">Method</th>
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                <th className="px-4 py-3 text-left font-semibold">Deadline</th>
                <th className="px-4 py-3 text-right font-semibold">Budget</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {tenderRows.map((tender) => (
                <tr key={tender.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">{tender.referenceNumber}</td>
                  <td className="px-4 py-3 text-slate-700">{tender.name}<div className="text-xs text-slate-500">{tender.department}</div></td>
                  <td className="px-4 py-3 text-slate-700">{tender.procurementMethod || "-"}</td>
                  <td className="px-4 py-3">
                    <Pill value={tender.status} />
                    {(tender.lotStatuses || []).length > 0 && (
                      <ul className="mt-2 space-y-1 text-xs">
                        {(tender.lotStatuses || []).map((lot) => (
                          <li key={lot.id} className="flex items-center justify-between gap-2">
                            <span className="truncate text-slate-500" title={lot.name}>{lot.name}</span>
                            <Pill value={lot.status} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{formatDate(tender.deadline)}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{money(tender.budget)}</td>
                  <td className="px-4 py-3 text-right">{auditButton({ auditArea: "procurement", tenderId: tender.id, title: `Procurement audit: ${tender.referenceNumber}`, context: tender.name })}</td>
                </tr>
              ))}
              {tenderRows.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-500">No tenders.</td></tr>}
            </tbody>
          </table>
        )}

        {view === "evaluations" && (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Tender</th>
                <th className="px-4 py-3 text-left font-semibold">Bidder</th>
                <th className="px-4 py-3 text-left font-semibold">Stage</th>
                <th className="px-4 py-3 text-left font-semibold">Evaluator</th>
                <th className="px-4 py-3 text-right font-semibold">Technical</th>
                <th className="px-4 py-3 text-right font-semibold">Financial</th>
                <th className="px-4 py-3 text-right font-semibold">Total</th>
                <th className="px-4 py-3 text-left font-semibold">Submission</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {evaluationRows.map(({ evaluation, bid }) => (
                <tr key={evaluation.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-700">{bid?.tender_reference || "-"}<div className="text-xs text-slate-500">{bid?.tender_name}</div></td>
                  <td className="px-4 py-3 font-medium text-slate-900">{bid?.vendor_name || evaluation.bid}</td>
                  <td className="px-4 py-3 capitalize text-slate-700">{evaluation.stage}</td>
                  <td className="px-4 py-3 text-slate-700">{evaluation.evaluatorUsername || "-"}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{evaluation.technicalScore}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{evaluation.financialScore}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-900">{evaluation.totalScore}</td>
                  <td className="px-4 py-3 text-slate-700">{evaluation.submissionStatus === "submitted" ? `Submitted ${formatDate(evaluation.submittedAt)}` : "Draft"}</td>
                  <td className="px-4 py-3 text-right">{bid && auditButton({ auditArea: "procurement", tenderId: bid.tender, title: `Bid evaluation audit: ${bid.tender_reference || bid.tender} - ${bid.vendor_name}`, context: bid.vendor_name })}</td>
                </tr>
              ))}
              {evaluationRows.length === 0 && <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-500">No evaluations.</td></tr>}
            </tbody>
          </table>
        )}

        {view === "rejected_bids" && (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Tender</th>
                <th className="px-4 py-3 text-left font-semibold">Bidder</th>
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                <th className="px-4 py-3 text-left font-semibold">Reason</th>
                <th className="px-4 py-3 text-left font-semibold">Submitted</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {rejectedRows.map((bid) => (
                <tr key={bid.id} className="border-t border-slate-100 align-top">
                  <td className="px-4 py-3 text-slate-700">{bid.tender_reference || "-"}<div className="text-xs text-slate-500">{bid.tender_name}</div></td>
                  <td className="px-4 py-3 font-medium text-slate-900">{bid.vendor_name}</td>
                  <td className="px-4 py-3"><Pill value={String(bid.status)} /></td>
                  <td className="max-w-md px-4 py-3 text-slate-700">{bid.rejection_reason || "-"}</td>
                  <td className="px-4 py-3 text-slate-700">{formatDate(bid.submitted_at)}</td>
                  <td className="px-4 py-3 text-right">{auditButton({ auditArea: "procurement", tenderId: bid.tender, title: `Rejected bid audit: ${bid.vendor_name}`, context: bid.vendor_name })}</td>
                </tr>
              ))}
              {rejectedRows.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500">No rejected bids.</td></tr>}
            </tbody>
          </table>
        )}

        {view === "contracts" && (
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Contract</th>
                <th className="px-4 py-3 text-left font-semibold">Tender</th>
                <th className="px-4 py-3 text-left font-semibold">Vendor</th>
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                <th className="px-4 py-3 text-left font-semibold">Signed</th>
                <th className="px-4 py-3 text-left font-semibold">Approved</th>
                <th className="px-4 py-3 text-left font-semibold">Document</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {contractRows.map((contract) => {
                const tender = tenderById.get(contract.tender);
                const file = contract.signedFile || contract.generatedFile;
                return (
                  <tr key={contract.id} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">{contract.referenceNumber}{contract.lotName && <div className="text-xs text-slate-500">{contract.lotName}</div>}</td>
                    <td className="px-4 py-3 text-slate-700">{tender?.referenceNumber || contract.tender}<div className="text-xs text-slate-500">{tender?.name}</div></td>
                    <td className="px-4 py-3 text-slate-700">{contract.vendorName}</td>
                    <td className="px-4 py-3"><Pill value={contract.status} /></td>
                    <td className="px-4 py-3 text-slate-700">{formatDate(contract.signedAt)}</td>
                    <td className="px-4 py-3 text-slate-700">{formatDate(contract.approvedAt)}</td>
                    <td className="px-4 py-3">
                      {file ? <a href={file} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-700 hover:underline"><FileText size={14} /> View</a> : "-"}
                    </td>
                    <td className="px-4 py-3 text-right">{auditButton({ auditArea: "contract", contractId: contract.id, tenderId: contract.tender, title: `Contract audit: ${contract.referenceNumber}`, context: contract.vendorName })}</td>
                  </tr>
                );
              })}
              {contractRows.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500">No contracts.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
