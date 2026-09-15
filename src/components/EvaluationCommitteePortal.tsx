import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  CreditCard,
  FolderKanban,
  Loader2,
  RefreshCw,
  Scale,
} from "lucide-react";
import {
  createBidEvaluation,
  fetchBidEvaluations,
  fetchFinancialEvaluation,
  fetchEvaluationScoringConfig,
  fetchTenderBids,
  fetchTenders,
} from "../api";
import { FinancialEvaluationLot, FinancialEvaluationRow, FinancialScoringFormula, Tender, TenderBid, TenderBidEvaluation } from "../types";
import { SubmittedBidModal } from "./SubmittedBidModal";
import { FinancialReviewPanel } from "./FinancialReviewPanel";

function formatDeadline(value?: string | null) {
  if (!value) return "No deadline set";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "No deadline set";
  return parsed.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function EvaluationCommitteeDashboard({ onNavigate }: { onNavigate?: (action: string, id?: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [bids, setBids] = useState<TenderBid[]>([]);
  const [evaluations, setEvaluations] = useState<TenderBidEvaluation[]>([]);

  const loadData = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const [tenderRows, bidRows, evalRows] = await Promise.all([
        fetchTenders(),
        fetchTenderBids(),
        fetchBidEvaluations(),
      ]);
      setTenders(tenderRows);
      setBids(bidRows.filter((b) => b.status !== "Draft"));
      setEvaluations(evalRows);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load your Evaluation Committee dashboard."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  useEffect(() => {
    const handler = () => void loadData(true);
    window.addEventListener("rbf-bid-updated", handler);
    return () => window.removeEventListener("rbf-bid-updated", handler);
  }, [loadData]);

  const bidsByTender = useMemo(() => {
    const map = new Map<string, TenderBid[]>();
    bids.forEach((b) => {
      const list = map.get(b.tender) || [];
      list.push(b);
      map.set(b.tender, list);
    });
    return map;
  }, [bids]);

  const summary = useMemo(() => {
    const detailedBids = bids.filter((b) => b.stage_key === "technical" || b.stage_key === "combined");
    const evaluatedByMeTechnical = new Set(
      evaluations.filter((e) => e.stage === "technical").map((e) => e.bid),
    );
    const evaluatedByMeFinancial = new Set(
      evaluations.filter((e) => e.stage === "financial").map((e) => e.bid),
    );
    const pendingTechnical = detailedBids.filter((b) => !evaluatedByMeTechnical.has(b.id));
    const readyForFinancial = detailedBids.filter(
      (b) => (b.evaluation_status === "technical_scored" || b.evaluation_status === "evaluated")
        && !evaluatedByMeFinancial.has(b.id),
    );
    return {
      assignedTenders: tenders.length,
      pendingTechnicalCount: pendingTechnical.length,
      readyForFinancialCount: readyForFinancial.length,
      finalizedByMeCount: evaluatedByMeFinancial.size,
    };
  }, [bids, evaluations, tenders]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading Evaluation Committee dashboard...
      </div>
    );
  }

  if (error) {
    return (
      <div className="card border-rose-200 bg-rose-50 p-10 text-center text-rose-700">
        <AlertTriangle size={24} className="mx-auto mb-2" />
        {error}
        <button onClick={() => void loadData()} className="btn-secondary mx-auto mt-4 flex items-center gap-2">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Evaluation Committee Overview</h1>
          <p className="text-slate-500">Bids awaiting your technical and financial evaluation, across every tender you're assigned to.</p>
        </div>
        <button
          type="button"
          onClick={() => void loadData(true)}
          disabled={refreshing}
          className="btn-secondary inline-flex items-center gap-2 self-start"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Assigned Tenders</p>
            <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
              <FolderKanban size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.assignedTenders}</p>
          <p className="mt-1 text-xs text-slate-500">Tenders whose committee you sit on</p>
        </div>

        <button
          type="button"
          onClick={() => onNavigate?.("evaluations")}
          className="card group p-5 text-left transition hover:border-blue-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Pending Technical Reviews</p>
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 transition group-hover:bg-blue-200">
              <ClipboardCheck size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.pendingTechnicalCount}</p>
          <p className="mt-1 text-xs text-slate-500">Bids you haven't scored yet</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("evaluations")}
          className="card group p-5 text-left transition hover:border-amber-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Ready for Financial</p>
            <div className="rounded-lg bg-amber-100 p-2 text-amber-600 transition group-hover:bg-amber-200">
              <Scale size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.readyForFinancialCount}</p>
          <p className="mt-1 text-xs text-slate-500">Cleared technical, awaiting your verification</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("evaluations")}
          className="card group p-5 text-left transition hover:border-emerald-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Finalized by Me</p>
            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600 transition group-hover:bg-emerald-200">
              <CheckCircle2 size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.finalizedByMeCount}</p>
          <p className="mt-1 text-xs text-slate-500">Financial scores you've verified</p>
        </button>
      </div>

      <div className="card">
        <div className="border-b border-slate-100 p-6">
          <h3 className="text-lg font-bold text-slate-900">Your Committees</h3>
          <p className="text-sm text-slate-500">Every tender you've been assigned to evaluate.</p>
        </div>
        <div className="divide-y divide-slate-100">
          {tenders.length === 0 && (
            <p className="p-6 text-sm text-slate-500">You haven't been assigned to any tender's Evaluation Committee yet. Contact your Super Admin.</p>
          )}
          {tenders.map((t) => {
            const tenderBids = bidsByTender.get(t.id) || [];
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onNavigate?.("evaluations")}
                className="flex w-full flex-col gap-1 p-6 text-left transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-bold text-slate-900">{t.name}</p>
                  <p className="text-xs text-slate-500">Ref: {t.referenceNumber} • Deadline: {formatDeadline(t.deadline)}</p>
                </div>
                <span className="badge bg-slate-100 text-slate-700 shrink-0">{tenderBids.length} bid{tenderBids.length === 1 ? "" : "s"}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function FinancialEvaluationView() {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [selectedTenderId, setSelectedTenderId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<{ isLotWise: boolean; rows?: FinancialEvaluationRow[]; lots?: FinancialEvaluationLot[] } | null>(null);
  const [bids, setBids] = useState<TenderBid[]>([]);
  const [finalizingKey, setFinalizingKey] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ row: FinancialEvaluationRow; lotId?: string } | null>(null);
  const [financialFormula, setFinancialFormula] = useState<FinancialScoringFormula>("lowest_price_100");
  const [rowsPage, setRowsPage] = useState<Record<string, number>>({});
  const ROWS_PAGE_SIZE = 10;
  const showNotification = (msg: string) => { setNotification(msg); setTimeout(() => setNotification(null), 3500); };

  const loadTenders = useCallback(async () => {
    try {
      const rows = await fetchTenders();
      setTenders(rows);
      setSelectedTenderId((prev) => prev || rows[0]?.id || "");
    } catch {
      setTenders([]);
    }
  }, []);

  useEffect(() => { void loadTenders(); }, [loadTenders]);
  useEffect(() => {
    fetchEvaluationScoringConfig().then((config) => setFinancialFormula(config.financialScoringFormula)).catch(() => {});
  }, []);

  const loadFinancialData = useCallback(async (tenderId: string) => {
    if (!tenderId) { setData(null); setBids([]); return null; }
    setLoading(true);
    try {
      const [result, bidRows] = await Promise.all([
        fetchFinancialEvaluation(tenderId),
        fetchTenderBids(tenderId),
      ]);
      setData(result);
      setBids(bidRows);
      return result;
    } catch (err: any) {
      setData(null);
      setBids([]);
      showNotification(String(err?.message || "Failed to load financial evaluation."));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadFinancialData(selectedTenderId); }, [selectedTenderId, loadFinancialData]);
  useEffect(() => { setRowsPage({}); }, [selectedTenderId]);

  const finalize = async (
    bidId: string,
    lotId: string | undefined,
    payload: { justifications: Record<string, string>; comments: string },
  ) => {
    const key = bidId + (lotId || "");
    setFinalizingKey(key);
    try {
      await createBidEvaluation({
        bid: bidId,
        stage: "financial",
        lot: lotId || undefined,
        submissionStatus: "submitted",
        justifications: payload.justifications,
        comments: payload.comments,
      });
      showNotification("Financial score verified, finalized, and locked.");
      const refreshed = await loadFinancialData(selectedTenderId);
      window.dispatchEvent(new Event("rbf-bid-updated"));
      const refreshedRows = refreshed ? (refreshed.isLotWise ? (refreshed.lots || []).flatMap((lot) => lot.rows) : refreshed.rows || []) : [];
      const refreshedRow = refreshedRows.find((r) => r.bidId === bidId);
      setViewing((prev) => (prev && prev.row.bidId === bidId ? (refreshedRow ? { row: refreshedRow, lotId } : null) : prev));
    } catch (err: any) {
      showNotification(String(err?.message || "Failed to finalize score."));
    } finally {
      setFinalizingKey(null);
    }
  };

  const selectedTender = tenders.find((t) => t.id === selectedTenderId);
  const viewingBid = viewing ? bids.find((b) => b.id === viewing.row.bidId) : undefined;
  const viewingLotNameById: Record<string, string> = viewing?.lotId
    ? Object.fromEntries((data?.isLotWise ? data.lots || [] : []).map((lot) => [lot.lotId, lot.lotName]))
    : {};

  const referenceRows = useMemo(() => {
    if (!data || !viewing) return [];
    if (data.isLotWise) {
      const lot = (data.lots || []).find((l) => l.lotId === viewing.lotId);
      return lot ? lot.rows : [];
    }
    return data.rows || [];
  }, [data, viewing]);

  const referenceLowest = referenceRows.length
    ? Math.min(...referenceRows.map((r) => r.bidAmountBaseCurrency ?? r.bidAmount))
    : 0;
  const lotCoverage = data?.isLotWise
    ? {
        total: (data.lots || []).length,
        priced: (viewingBid?.lot_offers || []).filter((o) => Number(o.bid_amount || 0) > 0).length,
      }
    : undefined;
  const isThisLowest = viewing && (viewing.row.bidAmountBaseCurrency ?? viewing.row.bidAmount) === referenceLowest;
  const lockedBidKey = viewing ? viewing.row.bidId + (viewing.lotId || "") : null;

  const allRows: FinancialEvaluationRow[] = useMemo(() => {
    if (!data) return [];
    return data.isLotWise ? (data.lots || []).flatMap((lot) => lot.rows) : (data.rows || []);
  }, [data]);

  const readyCount = allRows.length;
  const verifiedCount = allRows.filter((r) => r.finalized).length;
  const awaitingOthersCount = allRows.filter((r) => r.finalized && !r.finalizedByMe).length;

  const sortedRows = (rows: FinancialEvaluationRow[]) =>
    [...rows].sort((a, b) => (a.bidAmountBaseCurrency ?? a.bidAmount) - (b.bidAmountBaseCurrency ?? b.bidAmount));

  const renderRows = (rows: FinancialEvaluationRow[], lotId?: string) => {
    const pageKey = lotId || "all";
    const sorted = sortedRows(rows);
    const page = rowsPage[pageKey] || 1;
    const totalPages = Math.max(1, Math.ceil(sorted.length / ROWS_PAGE_SIZE));
    const pageRows = sorted.slice((page - 1) * ROWS_PAGE_SIZE, page * ROWS_PAGE_SIZE);
    const lowestBidId = sorted[0]?.bidId;
    return (
      <div className="space-y-3">
        <div className="overflow-x-auto rounded-2xl border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                {["Vendor", "Bid Amount", "Subsidy Requested", "Financial Score", "Status", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <tr
                  key={row.bidId}
                  className="border-t border-slate-100 cursor-pointer hover:bg-slate-50"
                  onClick={() => setViewing({ row, lotId })}
                >
                  <td className="px-4 py-3 font-semibold text-slate-900">
                    {row.vendorName}
                    {row.bidId === lowestBidId && sorted.length > 1 && (
                      <span className="ml-2 badge bg-blue-50 text-blue-700">Lowest price</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {row.bidCurrency || selectedTender?.biddingCurrency || "LSL"} {row.bidAmount.toLocaleString()}
                    {row.bidCurrency && row.bidCurrency !== selectedTender?.biddingCurrency && row.bidAmountBaseCurrency != null && (
                      <span className="text-slate-400"> (≈ {selectedTender?.biddingCurrency} {row.bidAmountBaseCurrency.toLocaleString()})</span>
                    )}
                  </td>
                  <td className="px-4 py-3">{row.subsidyRequested != null ? `${row.bidCurrency || selectedTender?.biddingCurrency || "LSL"} ${row.subsidyRequested.toLocaleString()}` : "N/A"}</td>
                  <td className="px-4 py-3 font-bold text-emerald-700">{row.computedFinancialScore.toFixed(1)} / 100</td>
                  <td className="px-4 py-3">
                    {row.submissionStatus === "submitted" ? (
                      <span className="badge bg-emerald-100 text-emerald-700">
                        {row.finalized ? "Finalized" : "Locked"}
                        {row.finalizedByMe ? " by you" : ""}
                      </span>
                    ) : row.finalized ? (
                      <span className="badge bg-emerald-100 text-emerald-700">Finalized{row.finalizedByMe ? " by you" : ""}</span>
                    ) : (
                      <span className="badge bg-amber-100 text-amber-700">Pending verification</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); setViewing({ row, lotId }); }}
                      className="btn-secondary text-xs px-3 py-1.5"
                    >
                      Review Bid
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-500">No bids have cleared technical evaluation yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-slate-500">
              Showing {(page - 1) * ROWS_PAGE_SIZE + 1}-{Math.min(page * ROWS_PAGE_SIZE, sorted.length)} of {sorted.length} bid{sorted.length !== 1 ? "s" : ""}
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setRowsPage((p) => ({ ...p, [pageKey]: Math.max(1, page - 1) }))}
                disabled={page === 1}
                className="btn-secondary text-xs py-1 px-3 disabled:opacity-50"
              >
                Previous
              </button>
              <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
              <button
                onClick={() => setRowsPage((p) => ({ ...p, [pageKey]: Math.min(totalPages, page + 1) }))}
                disabled={page === totalPages}
                className="btn-secondary text-xs py-1 px-3 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {notification && (
        <div className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl">{notification}</div>
      )}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Financial Evaluation</h1>
        <p className="text-sm text-slate-500">Every bidder who cleared technical evaluation, with the financial score computed automatically from price. Verify each bid for compliance and finalize to submit the committee's financial score.</p>
      </div>

      <div className="rounded-2xl border border-blue-100 bg-blue-50/60 px-5 py-4 text-sm text-blue-900">
        <span className="font-bold">How this is calculated:</span>{" "}
        {financialFormula === "linear_deviation_100"
          ? "the lowest qualifying price scores 100 — every other bid is scored 100 minus its percentage deviation above the lowest, floored at 0 (100 − (this bid's price − lowest) ÷ lowest × 100)."
          : "the lowest qualifying price scores 100 — every other bid is scored proportionally against it (100 × lowest ÷ this bid's price)."}{" "}
        Nothing here is manually typed. Set by Super Admin in System Configuration.
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Bids Ready to Verify</p>
          <p className="mt-3 text-3xl font-bold text-slate-900">{readyCount}</p>
        </div>
        <div className="card p-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Verified</p>
          <p className="mt-3 text-3xl font-bold text-emerald-700">{verifiedCount}</p>
        </div>
        <div className="card p-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Awaiting Other Members</p>
          <p className="mt-3 text-3xl font-bold text-amber-700">{awaitingOthersCount}</p>
        </div>
      </div>

      <div className="card p-4">
        <label className="text-sm font-bold text-slate-700 mb-2 block">Tender</label>
        <select className="input-field" value={selectedTenderId} onChange={(e) => setSelectedTenderId(e.target.value)}>
          {tenders.length === 0 && <option value="">No tenders assigned to you yet</option>}
          {tenders.map((t) => <option key={t.id} value={t.id}>{t.referenceNumber} — {t.name}</option>)}
        </select>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : !data ? (
        <p className="text-sm text-slate-500">Select a tender to view its financial evaluation.</p>
      ) : data.isLotWise ? (
        <div className="space-y-6">
          {(data.lots || []).map((lot) => {
            const lotVerified = lot.rows.filter((r) => r.finalized).length;
            return (
              <div key={lot.lotId} className="card p-6 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-lg font-bold text-slate-900">{lot.lotName}</h3>
                  <span className="badge bg-slate-100 text-slate-700">{lotVerified} of {lot.rows.length} verified</span>
                </div>
                {renderRows(lot.rows, lot.lotId)}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card p-6 space-y-3">
          {renderRows(data.rows || [])}
        </div>
      )}

      {viewing && viewingBid && (
        <SubmittedBidModal
          bid={viewingBid}
          lotNameById={viewingLotNameById}
          securityRequired={selectedTender?.tenderSecurityRequired || false}
          onClose={() => setViewing(null)}
        >
          <FinancialReviewPanel
            bid={viewingBid}
            row={viewing.row}
            lotId={viewing.lotId}
            securityRequired={selectedTender?.tenderSecurityRequired || false}
            displayCurrency={viewing.row.bidCurrency || selectedTender?.biddingCurrency || "LSL"}
            baseCurrency={selectedTender?.biddingCurrency || "LSL"}
            referenceLowest={referenceLowest}
            isThisLowest={Boolean(isThisLowest)}
            budget={selectedTender?.budget}
            lotCoverage={lotCoverage}
            locked={viewing.row.submissionStatus === "submitted"}
            lockedAt={viewing.row.submittedAt}
            finalizing={finalizingKey === lockedBidKey}
            financialFormula={financialFormula}
            onFinalize={(payload) => finalize(viewing.row.bidId, viewing.lotId, payload)}
            onCancel={() => setViewing(null)}
          />
        </SubmittedBidModal>
      )}
    </div>
  );
}
