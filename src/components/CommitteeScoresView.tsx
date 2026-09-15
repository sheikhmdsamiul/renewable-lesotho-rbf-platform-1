import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  History,
  Layers,
  Loader2,
  Lock,
  MessageSquareText,
  RefreshCw,
  Save,
  Users,
} from "lucide-react";
import {
  fetchEvaluationCommitteeScores,
  fetchTenderEvaluationComment,
  fetchTenders,
  saveTenderEvaluationComment,
} from "../api";
import { EvaluationCommitteeScores, EvaluationCommitteeScoresBid, EvaluationCommitteeScoresMemberEvaluation, Tender, TenderEvaluationComment } from "../types";

function ScoreBadge({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</span>
      <span className="inline-flex min-w-[2.5rem] justify-center rounded-md bg-slate-100 px-1.5 py-0.5 text-xs font-bold text-slate-700">
        {value}
        <span className="font-medium text-slate-400">/{max}</span>
      </span>
    </div>
  );
}

const TECHNICAL_CRITERION_LABELS: Record<string, string> = {
  technical_score: "Technical",
  feasibility_score: "Feasibility",
  kpi_score: "KPI",
  gender_score: "Gender",
  environmental_score: "Environmental",
  om_score: "O&M",
  inclusivity_score: "Inclusivity",
};

function SubmissionPill({ submissionStatus }: { submissionStatus?: "draft" | "submitted" }) {
  if (submissionStatus === "submitted") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
        <Lock size={10} /> Submitted & locked
      </span>
    );
  }
  if (submissionStatus === "draft") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
        Draft
      </span>
    );
  }
  return null;
}

function EvaluationDetailsRow({
  evaluation,
  colSpan,
  criteria,
}: {
  evaluation: EvaluationCommitteeScoresMemberEvaluation;
  colSpan: number;
  criteria: string[];
}) {
  const justifications = evaluation.justifications ? Object.entries(evaluation.justifications) : [];
  const revisions = evaluation.revisions ?? [];
  const hasContent = justifications.length > 0 || revisions.length > 0;

  return (
    <tr>
      <td colSpan={colSpan} className="bg-slate-50/70 px-4 py-3">
        <div className="space-y-3 text-xs text-slate-600">
          {evaluation.submittedAt && (
            <p className="text-[11px] text-slate-400">
              Submitted {new Date(evaluation.submittedAt).toLocaleString()}
            </p>
          )}
          {justifications.length > 0 && (
            <div>
              <p className="mb-1 font-bold text-slate-700">Score Justifications</p>
              <ul className="space-y-1">
                {justifications.map(([key, val]) => (
                  <li key={key} className="flex gap-2">
                    <span className="shrink-0 font-semibold text-slate-500">
                      {TECHNICAL_CRITERION_LABELS[key] ?? key}:
                    </span>
                    <span>{val || <em className="text-slate-400">not provided</em>}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {revisions.length > 0 && (
            <div>
              <p className="mb-1 flex items-center gap-1.5 font-bold text-slate-700">
                <History size={12} /> Revision History
              </p>
              <ul className="space-y-1.5">
                {revisions.map((rev, i) => (
                  <li key={i} className="border-l-2 border-slate-200 pl-2">
                    <span className="font-semibold text-slate-600">{rev.action}</span>
                    {" · "}
                    <span className="text-slate-500">{rev.changedBy}</span>
                    {rev.changedAt && <span className="text-slate-400"> · {new Date(rev.changedAt).toLocaleString()}</span>}
                    {rev.reason && <span className="block text-slate-500">Reason: {rev.reason}</span>}
                    {rev.changes.length > 0 && (
                      <ul className="mt-0.5 list-disc pl-4 text-slate-500">
                        {rev.changes.map((ch, j) => (
                          <li key={j}>
                            {ch.field}: {String(ch.before ?? "—")} → {String(ch.after ?? "—")}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!hasContent && <p className="text-slate-400">No justifications or revisions recorded.</p>}
        </div>
      </td>
    </tr>
  );
}

function CommitteeScoresTable({ data }: { data: EvaluationCommitteeScores }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const criteria = Object.keys(data.scoreLimits).length
    ? Object.keys(data.scoreLimits)
    : ["technical_score", "feasibility_score", "kpi_score", "gender_score", "environmental_score", "om_score"];
  const colSpan = criteria.length + 5;
  const lotNameById = Object.fromEntries((data.lots || []).map((lot) => [lot.lotId, lot.lotName]));
  const isLotWise = data.isLotWise && (data.lots || []).length > 0;

  const renderFinancialRow = (
    ev: EvaluationCommitteeScoresMemberEvaluation,
    { lotTone = false }: { lotTone?: boolean } = {},
  ) => {
    const hasDetails = (ev.justifications && Object.keys(ev.justifications).length > 0) || (ev.revisions?.length ?? 0) > 0;
    const isExpanded = expandedId === ev.evaluationId;
    const lotLabel = ev.lotName ?? (ev.lot ? lotNameById[ev.lot] || ev.lot : undefined);
    return (
      <React.Fragment key={ev.evaluationId}>
        <tr className={`border-t border-slate-100 ${lotTone ? "bg-emerald-50/40" : ""}`}>
          <td className="px-4 py-2.5 font-medium text-slate-900">
            <button
              type="button"
              onClick={() => setExpandedId(isExpanded ? null : ev.evaluationId)}
              className="inline-flex items-center gap-1.5 text-left hover:underline disabled:opacity-40"
              disabled={!hasDetails}
              title={hasDetails ? "Show justifications and revision history" : "No justifications recorded"}
            >
              {hasDetails ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-[14px]" />}
              {ev.evaluatorName}
            </button>
          </td>
          <td className="px-4 py-2.5">
            <div className="flex flex-col items-start gap-1">
              <span className="badge bg-emerald-100 text-emerald-700">
                Financial{lotLabel ? " · " : ""}
                {lotLabel ?? ""}
              </span>
              <SubmissionPill submissionStatus={ev.submissionStatus} />
            </div>
          </td>
          {criteria.map((key) => (
            <td key={key} className="px-2 py-2.5 text-center text-slate-300">—</td>
          ))}
          <td className="px-2 py-2.5">
            <ScoreBadge label="" value={ev.financialScore} max={100} />
          </td>
          <td className="px-2 py-2.5 text-center font-bold text-slate-800">{ev.financialScore}</td>
          <td className="max-w-[12rem] px-4 py-2.5 text-xs text-slate-500">{ev.comments || <span className="text-slate-300">—</span>}</td>
        </tr>
        {isExpanded && <EvaluationDetailsRow evaluation={ev} colSpan={colSpan} criteria={criteria} />}
      </React.Fragment>
    );
  };

  const renderLotFinancialSection = (bid: EvaluationCommitteeScoresBid, financialEvals: EvaluationCommitteeScoresMemberEvaluation[]) => (
    (data.lots || []).map((lot) => {
      const lotEvals = financialEvals.filter((ev) => String(ev.lot ?? "") === String(lot.lotId));
      const finalized = bid.lotFinancialFinalized?.[lot.lotId];
      return (
        <React.Fragment key={lot.lotId}>
          <tr className="border-t border-slate-200 bg-slate-100/70">
            <td colSpan={colSpan} className="px-4 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-sm font-bold text-slate-700">
                  <Layers size={14} className="text-slate-500" /> Lot · {lot.lotName}
                </span>
                <span className={`badge ${finalized ? "bg-emerald-100 text-emerald-700" : lotEvals.length > 0 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}>
                  {finalized ? "Financial finalized" : lotEvals.length > 0 ? `${lotEvals.length} financial score(s) — awaiting quorum` : "No financial scores yet"}
                </span>
              </div>
            </td>
          </tr>
          {lotEvals.length > 0 ? (
            lotEvals.map((ev) => renderFinancialRow(ev, { lotTone: true }))
          ) : (
            <tr className="border-t border-slate-100">
              <td colSpan={colSpan} className="px-4 py-2.5 text-center text-xs text-slate-400">
                No committee financial marks submitted yet for this lot.
              </td>
            </tr>
          )}
        </React.Fragment>
      );
    })
  );

  return (
    <div className="space-y-8">
      {data.bids.map((bid) => {
        const technicalEvals = bid.evaluations.filter((e) => e.stage === "technical");
        const financialEvals = bid.evaluations.filter((e) => e.stage === "financial");

        return (
          <div key={bid.bidId} className="space-y-3">
            <div className="rounded-2xl border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
                <div>
                  <p className="font-bold text-slate-900">{bid.vendorName}</p>
                  <p className="text-xs text-slate-500">
                    {bid.bidStage} · {bid.status} · {technicalEvals.length} member technical score(s)
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`badge ${bid.technicalQuorumMet ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {bid.technicalQuorumMet ? "Technical quorum met" : "Awaiting quorum"}
                  </span>
                  <span className={`badge ${bid.passedTechnicalThreshold ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                    {bid.passedTechnicalThreshold ? "Above threshold" : "Below threshold"}
                  </span>
                  <span className={`badge ${bid.financialFinalized ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {bid.financialFinalized ? "Financial finalized" : "Financial pending"}
                  </span>
                </div>
              </div>

              {isLotWise && (
                <div className="flex flex-wrap gap-2 border-b border-slate-100 bg-white px-5 py-3">
                  {(data.lots || []).map((lot) => {
                    const finalized = bid.lotFinancialFinalized?.[lot.lotId];
                    const hasMarks = financialEvals.some((ev) => String(ev.lot ?? "") === String(lot.lotId));
                    return (
                      <span
                        key={lot.lotId}
                        className={`badge ${finalized ? "bg-emerald-100 text-emerald-700" : hasMarks ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}
                      >
                        {lot.lotName} — {finalized ? "Finalized" : hasMarks ? "In progress" : "No marks yet"}
                      </span>
                    );
                  })}
                </div>
              )}

              {bid.technicalQuorumMet && bid.technicalAverageScore != null && (
                <div className="flex flex-wrap gap-6 bg-slate-50/60 px-5 py-3 text-sm">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Committee Average</p>
                    <p className="text-xl font-bold text-emerald-700">{Number(bid.technicalAverageScore).toFixed(1)} / 100</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Threshold</p>
                    <p className="text-xl font-bold text-slate-800">{data.technicalThreshold}%</p>
                  </div>
                  {bid.technicalRawAverage != null && (
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Raw Average</p>
                      <p className="text-xl font-bold text-slate-700">{Number(bid.technicalRawAverage).toFixed(1)} / {data.technicalScoreTotal}</p>
                    </div>
                  )}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-4 py-2.5 text-left font-semibold">Committee Member</th>
                      <th className="px-4 py-2.5 text-left font-semibold">Stage</th>
                      {criteria.map((key) => (
                        <th key={key} className="px-2 py-2.5 text-center font-semibold">
                          {TECHNICAL_CRITERION_LABELS[key] ?? key}
                          <span className="block text-[10px] font-normal text-slate-400">max {data.scoreLimits[key] ?? 0}</span>
                        </th>
                      ))}
                      <th className="px-2 py-2.5 text-center font-semibold">Financial</th>
                      <th className="px-2 py-2.5 text-center font-semibold">Total</th>
                      <th className="px-2 py-2.5 text-left font-semibold">Comments</th>
                    </tr>
                  </thead>
                  <tbody>
                    {technicalEvals.map((ev) => {
                      const hasDetails = (ev.justifications && Object.keys(ev.justifications).length > 0) || (ev.revisions?.length ?? 0) > 0;
                      const isExpanded = expandedId === ev.evaluationId;
                      return (
                        <React.Fragment key={ev.evaluationId}>
                          <tr className="border-t border-slate-100">
                            <td className="px-4 py-2.5 font-medium text-slate-900">
                              <button
                                type="button"
                                onClick={() => setExpandedId(isExpanded ? null : ev.evaluationId)}
                                className="inline-flex items-center gap-1.5 text-left hover:underline disabled:opacity-40"
                                disabled={!hasDetails}
                                title={hasDetails ? "Show justifications and revision history" : "No justifications recorded"}
                              >
                                {hasDetails ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-[14px]" />}
                                {ev.evaluatorName}
                              </button>
                            </td>
                            <td className="px-4 py-2.5">
                              <div className="flex flex-col items-start gap-1">
                                <span className="badge bg-blue-100 text-blue-700">Technical</span>
                                <SubmissionPill submissionStatus={ev.submissionStatus} />
                              </div>
                            </td>
                            {criteria.map((key) => {
                              const scoreField = ({
                                technical_score: ev.technicalScore,
                                feasibility_score: ev.feasibilityScore,
                                kpi_score: ev.kpiScore,
                                gender_score: ev.genderScore,
                                environmental_score: ev.environmentalScore,
                                om_score: ev.omScore,
                                inclusivity_score: ev.inclusivityScore,
                              } as Record<string, number>)[key];
                              return (
                                <td key={key} className="px-2 py-2.5">
                                  <ScoreBadge label="" value={scoreField ?? 0} max={data.scoreLimits[key] ?? 0} />
                                </td>
                              );
                            })}
                            <td className="px-2 py-2.5 text-center text-slate-400">—</td>
                            <td className="px-2 py-2.5 text-center font-bold text-slate-800">{ev.totalScore}</td>
                            <td className="max-w-[12rem] px-4 py-2.5 text-xs text-slate-500">{ev.comments || <span className="text-slate-300">—</span>}</td>
                          </tr>
                          {isExpanded && <EvaluationDetailsRow evaluation={ev} colSpan={colSpan} criteria={criteria} />}
                        </React.Fragment>
                      );
                    })}
                    {isLotWise ? renderLotFinancialSection(bid, financialEvals) : financialEvals.map((ev) => renderFinancialRow(ev, { lotTone: true }))}
                    {technicalEvals.length === 0 && financialEvals.length === 0 && (
                      <tr className="border-t border-slate-100">
                        <td colSpan={colSpan} className="px-4 py-4 text-center text-slate-400">
                          No committee scores submitted yet for this bid.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        );
      })}
      {data.bids.length === 0 && (
        <p className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">
          No bids have entered the committee's detailed evaluation yet.
        </p>
      )}
    </div>
  );
}

export function CommitteeScoresView({ tenderId }: { tenderId?: string }) {
  const embedded = Boolean(tenderId);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [selectedTenderId, setSelectedTenderId] = useState(tenderId ?? "");
  const [scores, setScores] = useState<EvaluationCommitteeScores | null>(null);
  const [comment, setComment] = useState<TenderEvaluationComment | null>(null);
  const [commentText, setCommentText] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savingError, setSavingError] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

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

  useEffect(() => {
    if (tenderId != null && tenderId !== selectedTenderId) setSelectedTenderId(tenderId);
  }, [tenderId, selectedTenderId]);

  useEffect(() => { if (!embedded) void loadTenders(); }, [loadTenders, embedded]);

  const loadData = useCallback(async (tenderId: string) => {
    if (!tenderId) { setScores(null); setComment(null); return; }
    setLoading(true);
    setSavingError(null);
    try {
      const [scoresData, commentData] = await Promise.all([
        fetchEvaluationCommitteeScores(tenderId),
        fetchTenderEvaluationComment(tenderId),
      ]);
      setScores(scoresData);
      setComment(commentData);
      setCommentText(commentData.comment);
    } catch (err: any) {
      setScores(null);
      setComment(null);
      setSavingError(String(err?.message || "Failed to load committee scores."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(selectedTenderId); }, [selectedTenderId, loadData]);

  useEffect(() => {
    const handler = () => void loadData(selectedTenderId);
    window.addEventListener("rbf-bid-updated", handler);
    return () => window.removeEventListener("rbf-bid-updated", handler);
  }, [selectedTenderId, loadData]);

  const saveComment = async () => {
    if (!selectedTenderId) return;
    setSaving(true);
    setSavingError(null);
    try {
      const result = await saveTenderEvaluationComment(selectedTenderId, commentText);
      setComment(result);
      showNotification(result.comment ? "RBF Official comment saved." : "RBF Official comment cleared.");
    } catch (err: any) {
      setSavingError(String(err?.message || "Failed to save comment."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {notification && (
        <div className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl">{notification}</div>
      )}
      {!embedded && (
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Evaluation Committee Scores</h1>
          <p className="text-sm text-slate-500">
            Each mark every Evaluation Committee member gave, per bid — grouped lot by lot when a tender has been split. Review
            the committee's scoring and, once the whole evaluation is complete, add the RBF Official's comment.
          </p>
        </div>
      )}

      {!embedded && (
        <div className="card p-4">
          <label className="text-sm font-bold text-slate-700 mb-2 block">Tender</label>
          <select className="input-field" value={selectedTenderId} onChange={(e) => setSelectedTenderId(e.target.value)}>
            {tenders.length === 0 && <option value="">No tenders available</option>}
            {tenders.map((t) => <option key={t.id} value={t.id}>{t.referenceNumber} — {t.name}</option>)}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Committee Size</p>
            <Users size={18} className="text-slate-400" />
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{scores?.committeeSize ?? "—"}</p>
          <p className="mt-1 text-xs text-slate-500">Quorum: {scores?.quorum ?? "—"} members</p>
        </div>
        <div className="card p-5">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Bids in Evaluation</p>
          <p className="mt-3 text-3xl font-bold text-slate-900">{scores?.bids.length ?? "—"}</p>
          <p className="mt-1 text-xs text-slate-500">Committee-quorum threshold</p>
        </div>
        <div className={`card p-5 ${comment?.evaluationComplete ? "border-emerald-200 bg-emerald-50/40" : ""}`}>
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Evaluation Status</p>
            {comment?.evaluationComplete
              ? <CheckCircle2 size={18} className="text-emerald-600" />
              : <Clock size={18} className="text-amber-500" />}
          </div>
          <p className={`mt-3 text-sm font-bold ${comment?.evaluationComplete ? "text-emerald-700" : "text-amber-700"}`}>
            {comment?.evaluationComplete ? "Complete" : "In Progress"}
          </p>
          {comment && !comment.evaluationComplete && comment.incompleteReasons.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-xs text-slate-500 space-y-0.5">
              {comment.incompleteReasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500 flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Loading committee scores...</p>
      ) : !selectedTenderId ? (
        <p className="text-sm text-slate-500">Select a tender to view its committee scores.</p>
      ) : scores ? (
        <CommitteeScoresTable data={scores} />
      ) : (
        <div className="card border-rose-200 bg-rose-50 p-8 text-center text-rose-700 flex flex-col items-center gap-3">
          <AlertTriangle size={24} />
          {savingError || "Unable to load committee scores."}
          <button onClick={() => void loadData(selectedTenderId)} className="btn-secondary mt-1 flex items-center gap-2">
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {scores && (
        <div className="card p-6 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-blue-100 p-2.5 text-blue-700"><MessageSquareText size={18} /></div>
              <div>
                <h3 className="text-lg font-bold text-slate-900">RBF Official Evaluation Comment</h3>
                <p className="text-sm text-slate-500">
                  A single comment on this tender's evaluation. Written once the whole committee evaluation is complete.
                </p>
              </div>
            </div>
            <span className={`badge shrink-0 ${comment?.evaluationComplete ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
              {comment?.evaluationComplete ? "Can save comment" : "Evaluation not complete"}
            </span>
          </div>

          {comment?.author && (
            <p className="text-xs text-slate-400">
              Last edited by {comment.author}{comment.updatedAt ? ` on ${new Date(comment.updatedAt).toLocaleString()}` : ""}
            </p>
          )}

          <textarea
            className="input-field w-full min-h-[110px]"
            placeholder="Add the RBF Official's comment on the completed evaluation..."
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            disabled={!comment?.evaluationComplete}
          />

          {savingError && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {savingError}
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void saveComment()}
              disabled={saving || !comment?.evaluationComplete}
              className="btn-primary inline-flex items-center gap-2 disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {saving ? "Saving..." : commentText.trim() ? "Save Comment" : "Clear Comment"}
            </button>
          </div>
          {!comment?.evaluationComplete && (
            <p className="text-xs text-amber-700">
              The comment becomes editable once every bid has a quorum technical score and every threshold-passing bid has a
              finalized financial score.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
