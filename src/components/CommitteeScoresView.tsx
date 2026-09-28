import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  Search,
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

type BidderSortKey = "vendor" | "lot" | "technical" | "financial" | "combined" | "status";

/** One line of the "Bidder Scores" comparison table. A single-bid tender gets one row
 * per bidder; a lot-wise tender gets one row per bidder PER LOT, because each lot is
 * scored and decided on its own — a blended per-bidder number would hide exactly the
 * thing the reader came to check. */
type ComparisonRow = {
  key: string;
  bid: EvaluationCommitteeScoresBid;
  lot: { lotId: string; lotName: string } | null;
  /** Committee mean technical mark on the rubric's own scale (out of technicalMax). */
  technicalAvg: number | null;
  /** The same committee verdict expressed as a percentage, against which the
   * tender's technical threshold is applied. */
  technicalPct: number | null;
  passedThreshold: boolean;
  quorumMet: boolean;
  /** Committee mean financial mark, already scaled onto the tender's financial weight. */
  financialAvg: number | null;
  combined: number | null;
  financialFinalized: boolean;
  scoredMembers: number;
  /** Lot-wise only: how many of this bidder's lots passed end to end, for the
   * per-bidder progress hint. */
  lotsPassed: number | null;
  lotCount: number | null;
  lotOrder: number;
};

function CommitteeScoresTable({ data }: { data: EvaluationCommitteeScores }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const criteria = Object.keys(data.scoreLimits).length
    ? Object.keys(data.scoreLimits)
    : ["technical_score", "feasibility_score", "kpi_score", "gender_score", "environmental_score", "om_score"];
  const colSpan = criteria.length + 5;
  const lots = data.lots || [];
  const lotNameById = Object.fromEntries(lots.map((lot) => [lot.lotId, lot.lotName]));
  // A lot-wise tender is scored lot by lot, so the table is grouped by lot. A tender
  // with no lots is scored once for the whole bid, and gets a single flat list — no
  // lot headers, no per-lot roll-ups, nothing that implies a lot breakdown exists.
  const isLotWise = data.isLotWise && lots.length > 0;
  const thresholdPct = data.technicalThreshold;
  const technicalMax = data.technicalScoreTotal;
  const financialMax = data.financialWeight;
  const combinedMax = technicalMax + financialMax;

  const lotLabelFor = (ev: EvaluationCommitteeScoresMemberEvaluation) =>
    ev.lotName ?? (ev.lot ? lotNameById[ev.lot] || ev.lot : undefined);

  const hasDetails = (ev: EvaluationCommitteeScoresMemberEvaluation) =>
    (ev.justifications && Object.keys(ev.justifications).length > 0) || (ev.revisions?.length ?? 0) > 0;

  // The marks live on two different scales: technical is a raw sum over the configured
  // rubric (technicalMax, 70 by default) and financial is a 0-100 price score
  // auto-calculated server-side. Report each on its own scale, and only add them once
  // both exist, so a single "Total" column can never mean two different things.
  const criterionValue = (ev: EvaluationCommitteeScoresMemberEvaluation, key: string) =>
    ({
      technical_score: ev.technicalScore,
      feasibility_score: ev.feasibilityScore,
      kpi_score: ev.kpiScore,
      gender_score: ev.genderScore,
      environmental_score: ev.environmentalScore,
      om_score: ev.omScore,
      inclusivity_score: ev.inclusivityScore,
    } as Record<string, number>)[key] ?? 0;

  const technicalRaw = (ev: EvaluationCommitteeScoresMemberEvaluation) =>
    criteria.reduce((sum, key) => sum + Number(criterionValue(ev, key) || 0), 0);

  // An auto-calculated financial score is 0-100 and has to be scaled onto the tender's
  // financial weight; a legacy manually-typed row is already out of that weight.
  const financialMark = (ev: EvaluationCommitteeScoresMemberEvaluation) =>
    ev.financialScoreAutoCalculated ? (Number(ev.financialScore || 0) * financialMax) / 100 : Number(ev.financialScore || 0);

  // Mean of the committee's financial marks in a given scope (a whole bid, or one lot of
  // it), on the same out-of-financialWeight scale. Null until someone has marked it.
  const averageFinancialMark = (evals: EvaluationCommitteeScoresMemberEvaluation[]) => {
    const marked = evals.filter((ev) => ev.stage === "financial" && Number(ev.financialScore || 0) > 0);
    if (marked.length === 0) return null;
    return marked.reduce((sum, ev) => sum + financialMark(ev), 0) / marked.length;
  };

  type ScopePair = { technical?: EvaluationCommitteeScoresMemberEvaluation; financial?: EvaluationCommitteeScoresMemberEvaluation };
  type ScopeMap = Map<string, ScopePair>;

  // One member's technical and financial rows pair up by (evaluator, lot) — the two
  // stages of the same person's mark on the same unit of the bid.
  const buildScopeMap = (bid: EvaluationCommitteeScoresBid): ScopeMap => {
    const map: ScopeMap = new Map();
    for (const ev of bid.evaluations) {
      const key = `${ev.evaluator}|${ev.lot ?? ""}`;
      const slot: ScopePair = map.get(key) ?? {};
      if (ev.stage === "financial") slot.financial = ev;
      else slot.technical = ev;
      map.set(key, slot);
    }
    return map;
  };

  const scopePair = (scopeMap: ScopeMap, ev: EvaluationCommitteeScoresMemberEvaluation): ScopePair =>
    scopeMap.get(`${ev.evaluator}|${ev.lot ?? ""}`) ?? {};

  const MarkCell = ({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) => (
    <td className={`px-2 py-2.5 text-center text-sm ${muted ? "text-slate-300" : "font-bold text-slate-800"}`}>{children}</td>
  );

  const renderMemberCell = (ev: EvaluationCommitteeScoresMemberEvaluation) => {
    const expandable = hasDetails(ev);
    const isExpanded = expandedId === ev.evaluationId;
    return (
      <button
        type="button"
        onClick={() => setExpandedId(isExpanded ? null : ev.evaluationId)}
        className="inline-flex items-center gap-1.5 text-left hover:underline disabled:opacity-40"
        disabled={!expandable}
        title={expandable ? "Show justifications and revision history" : "No justifications recorded"}
      >
        {expandable ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-[14px]" />}
        {ev.evaluatorName}
      </button>
    );
  };

  const renderTechnicalRow = (
    ev: EvaluationCommitteeScoresMemberEvaluation,
    { lotTone = false, showLot = false, scopeMap }: { lotTone?: boolean; showLot?: boolean; scopeMap: ScopeMap },
  ) => {
    const lotLabel = showLot ? lotLabelFor(ev) : undefined;
    const paired = scopePair(scopeMap, ev).financial;
    const combined = paired ? technicalRaw(ev) + financialMark(paired) : null;
    return (
      <React.Fragment key={ev.evaluationId}>
        <tr className={`border-t border-slate-100 ${lotTone ? "bg-emerald-50/40" : ""}`}>
          <td className="px-4 py-2.5 font-medium text-slate-900">{renderMemberCell(ev)}</td>
          <td className="px-4 py-2.5">
            <div className="flex flex-col items-start gap-1">
              <span className="badge bg-blue-100 text-blue-700">
                Technical{lotLabel ? " · " : ""}
                {lotLabel ?? ""}
              </span>
              <SubmissionPill submissionStatus={ev.submissionStatus} />
            </div>
          </td>
          {criteria.map((key) => (
            <td key={key} className="px-2 py-2.5">
              <ScoreBadge label="" value={criterionValue(ev, key)} max={data.scoreLimits[key] ?? 0} />
            </td>
          ))}
          <MarkCell>{technicalRaw(ev)}<span className="text-xs font-medium text-slate-400">/{technicalMax}</span></MarkCell>
          <MarkCell muted>—</MarkCell>
          <MarkCell muted={combined === null}>{combined === null ? "—" : `${combined.toFixed(1)}/${combinedMax}`}</MarkCell>
          <td className="max-w-[12rem] px-4 py-2.5 text-xs text-slate-500">{ev.comments || <span className="text-slate-300">—</span>}</td>
        </tr>
        {expandedId === ev.evaluationId && <EvaluationDetailsRow evaluation={ev} colSpan={colSpan} criteria={criteria} />}
      </React.Fragment>
    );
  };

  const renderFinancialRow = (
    ev: EvaluationCommitteeScoresMemberEvaluation,
    { lotTone = false, showLot = false, scopeMap }: { lotTone?: boolean; showLot?: boolean; scopeMap: ScopeMap },
  ) => {
    const lotLabel = showLot ? lotLabelFor(ev) : undefined;
    const paired = scopePair(scopeMap, ev).technical;
    const combined = paired ? technicalRaw(paired) + financialMark(ev) : null;
    return (
      <React.Fragment key={ev.evaluationId}>
        <tr className={`border-t border-slate-100 ${lotTone ? "bg-emerald-50/40" : ""}`}>
          <td className="px-4 py-2.5 font-medium text-slate-900">{renderMemberCell(ev)}</td>
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
          <MarkCell muted>{paired ? `${technicalRaw(paired)}/${technicalMax}` : "—"}</MarkCell>
          <MarkCell>{financialMark(ev).toFixed(1)}<span className="text-xs font-medium text-slate-400">/{financialMax}</span></MarkCell>
          <MarkCell muted={combined === null}>{combined === null ? "—" : `${combined.toFixed(1)}/${combinedMax}`}</MarkCell>
          <td className="max-w-[12rem] px-4 py-2.5 text-xs text-slate-500">{ev.comments || <span className="text-slate-300">—</span>}</td>
        </tr>
        {expandedId === ev.evaluationId && <EvaluationDetailsRow evaluation={ev} colSpan={colSpan} criteria={criteria} />}
      </React.Fragment>
    );
  };

  const renderEmptyRow = (message: string) => (
    <tr className="border-t border-slate-100">
      <td colSpan={colSpan} className="px-4 py-2.5 text-center text-xs text-slate-400">{message}</td>
    </tr>
  );

  const renderSectionLabel = (label: string, right?: React.ReactNode) => (
    <tr className="border-t border-slate-200 bg-slate-50/80">
      <td colSpan={colSpan} className="px-4 py-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</span>
          {right}
        </div>
      </td>
    </tr>
  );

  // One lot of a lot-wise tender: its own technical quorum/average/threshold verdict
  // and its own financial rows, so a bid that was marked per lot is never shown as one
  // blended score.
  const renderLotSection = (
    bid: EvaluationCommitteeScoresBid,
    lot: { lotId: string; lotName: string },
    scopeMap: ScopeMap,
  ) => {
    const lotEvals = bid.evaluations.filter((ev) => String(ev.lot ?? "") === lot.lotId);
    const technicalEvals = lotEvals.filter((ev) => ev.stage === "technical");
    const financialEvals = lotEvals.filter((ev) => ev.stage === "financial");
    const technical = bid.lotTechnicalSummary?.[lot.lotId];
    const financialFinalized = bid.lotFinancialFinalized?.[lot.lotId] === true;
    return (
      <React.Fragment key={lot.lotId}>
        <tr className="border-t-2 border-slate-200 bg-slate-100/70">
          <td colSpan={colSpan} className="px-4 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-sm font-bold text-slate-700">
                <Layers size={14} className="text-slate-500" /> Lot · {lot.lotName}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`badge ${technical?.quorumMet ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                  {technical?.quorumMet
                    ? `Technical quorum met (${technical.memberCount}/${data.quorum} members)`
                    : `${technical?.memberCount ?? 0} technical score(s) — awaiting quorum`}
                </span>
                <span className={`badge ${technical?.passedThreshold ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                  {technical?.passedThreshold ? "Above threshold" : "Below threshold"}
                </span>
                <span className={`badge ${financialFinalized ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                  {financialFinalized ? "Financial finalized" : financialEvals.length > 0 ? "Financial pending" : "No financial scores yet"}
                </span>
              </div>
            </div>
          </td>
        </tr>
        {technical?.averageScore != null && (
          <tr className="border-t border-slate-100 bg-slate-50/60">
            <td colSpan={colSpan} className="px-4 py-2">
              <div className="flex flex-wrap gap-6 text-sm">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Committee Average</p>
                  <p className="text-lg font-bold text-emerald-700">{Number(technical.averageScore).toFixed(1)} / 100</p>
                </div>
                {technical.rawAverage != null && (
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Raw Average</p>
                    <p className="text-lg font-bold text-slate-700">{Number(technical.rawAverage).toFixed(1)} / {data.technicalScoreTotal}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Threshold</p>
                  <p className="text-lg font-bold text-slate-800">{thresholdPct}%</p>
                </div>
              </div>
            </td>
          </tr>
        )}
        {renderSectionLabel(`Technical — ${technicalEvals.length} member score(s)`)}
        {technicalEvals.length > 0
          ? technicalEvals.map((ev) => renderTechnicalRow(ev, { lotTone: true, scopeMap }))
          : renderEmptyRow("No committee technical marks submitted yet for this lot.")}
        {renderSectionLabel(`Financial — ${financialEvals.length} member score(s)`)}
        {financialEvals.length > 0
          ? financialEvals.map((ev) => renderFinancialRow(ev, { lotTone: true, scopeMap }))
          : renderEmptyRow("No committee financial marks submitted yet for this lot.")}
      </React.Fragment>
    );
  };

  // A tender can carry dozens of bidders and every one has a full member-by-member
  // table, so the view is built around a single scannable comparison table: one row per
  // bidder, sortable and filterable, with the heavy per-member tables rendered only for
  // the bidders actually opened. Rendering every table up front made the page unusable
  // past a handful of bidders.
  const [openBidIds, setOpenBidIds] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<BidderSortKey>("vendor");
  const [sortAsc, setSortAsc] = useState(true);

  const toggleBid = (bidId: string) =>
    setOpenBidIds((prev) => (prev.includes(bidId) ? prev.filter((id) => id !== bidId) : [...prev, bidId]));

  // Distinct evaluators with a technical row for a given lot (or for the whole bid on a
  // non-lot-wise tender) — the committee's progress on this unit.
  const scoredMemberCountFor = (bid: EvaluationCommitteeScoresBid, lotId: string | null) =>
    new Set(
      bid.evaluations
        .filter((ev) => ev.stage === "technical" && (ev.lot ?? null) === lotId)
        .map((ev) => ev.evaluator),
    ).size;

  const rows = useMemo<ComparisonRow[]>(
    () =>
      data.bids.flatMap((bid) => {
        if (isLotWise) {
          const lotRows = lots.map((lot, lotOrder) => {
            const technical = bid.lotTechnicalSummary?.[lot.lotId];
            const financialAvg = averageFinancialMark(bid.evaluations.filter((ev) => ev.lot === lot.lotId));
            const technicalAvg = technical?.rawAverage != null ? Number(technical.rawAverage) : null;
            return {
              key: `${bid.bidId}:${lot.lotId}`,
              bid,
              lot,
              technicalAvg,
              technicalPct: technical?.averageScore != null ? Number(technical.averageScore) : null,
              passedThreshold: technical?.passedThreshold === true,
              quorumMet: technical?.quorumMet === true,
              financialAvg,
              combined: technicalAvg != null && financialAvg != null ? technicalAvg + financialAvg : null,
              financialFinalized: bid.lotFinancialFinalized?.[lot.lotId] === true,
              scoredMembers: scoredMemberCountFor(bid, lot.lotId),
              lotsPassed: lots.filter((l) => bid.lotTechnicalSummary?.[l.lotId]?.passedThreshold && bid.lotFinancialFinalized?.[l.lotId]).length,
              lotCount: lots.length,
              lotOrder,
            };
          });
          return lotRows;
        }
        const technicalAvg = bid.technicalRawAverage != null ? Number(bid.technicalRawAverage) : null;
        const financialAvg = averageFinancialMark(bid.evaluations);
        return [{
          key: bid.bidId,
          bid,
          lot: null,
          technicalAvg,
          technicalPct: bid.technicalAverageScore != null ? Number(bid.technicalAverageScore) : null,
          passedThreshold: bid.passedTechnicalThreshold,
          quorumMet: bid.technicalQuorumMet,
          financialAvg,
          combined: technicalAvg != null && financialAvg != null ? technicalAvg + financialAvg : null,
          financialFinalized: bid.financialFinalized,
          scoredMembers: scoredMemberCountFor(bid, null),
          lotsPassed: null,
          lotCount: null,
          lotOrder: 0,
        }];
      }),
    // averageFinancialMark / scoredMemberCountFor read `bid` plus the scale constants,
    // which all come from `data`, `isLotWise` or `lots` — all three are listed.
    [data, isLotWise, lots],
  );

  const rowStatusLabel = (r: ComparisonRow) =>
    r.scoredMembers === 0 ? "Not scored"
    : !r.quorumMet ? "In progress"
    : r.financialFinalized ? "Finalized"
    : !r.passedThreshold ? "Below threshold"
    : "Technical only";

  const rowStatusTone = (r: ComparisonRow) =>
    r.scoredMembers === 0 ? "bg-slate-100 text-slate-500"
    : !r.quorumMet ? "bg-amber-100 text-amber-700"
    : r.financialFinalized ? "bg-emerald-100 text-emerald-700"
    : r.passedThreshold ? "bg-sky-100 text-sky-700"
    : "bg-rose-100 text-rose-700";

  const visibleRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = needle
      ? rows.filter((r) =>
          r.bid.vendorName.toLowerCase().includes(needle) ||
          r.bid.status.toLowerCase().includes(needle) ||
          (r.lot?.lotName.toLowerCase().includes(needle) ?? false),
        )
      : rows;
    const value = (r: ComparisonRow) =>
      sortKey === "vendor" ? r.bid.vendorName.toLowerCase()
      : sortKey === "lot" ? r.lotOrder
      : sortKey === "technical" ? r.technicalAvg
      : sortKey === "financial" ? r.financialAvg
      : sortKey === "status" ? rowStatusLabel(r)
      : r.combined;
    return [...matches].sort((a, b) => {
      // Default ordering groups a bidder's lots together and keeps bidders in name order.
      if (sortKey === "vendor") {
        const byName = a.bid.vendorName.localeCompare(b.bid.vendorName);
        return (sortAsc ? byName : -byName) || a.lotOrder - b.lotOrder;
      }
      const av = value(a);
      const bv = value(b);
      // Rows with nothing scored yet always sink to the bottom, in either direction — an
      // unevaluated lot is not "lowest scoring", it is simply unranked.
      if (av == null && bv == null) return a.key.localeCompare(b.key);
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortAsc ? cmp : -cmp;
    });
  }, [rows, query, sortKey, sortAsc]);

  const SortHeader = ({ label, value, align = "right" }: { label: string; value: BidderSortKey; align?: "left" | "right" }) => (
    <th className={`px-3 py-2 ${align === "left" ? "text-left" : "text-right"}`}>
      <button
        type="button"
        onClick={() => {
          if (sortKey === value) setSortAsc((prev) => !prev);
          else { setSortKey(value); setSortAsc(value === "vendor" || value === "lot"); }
        }}
        className={`inline-flex items-center gap-1 font-semibold hover:text-slate-800 ${sortKey === value ? "text-slate-900" : ""}`}
      >
        {label}
        {sortKey === value && (sortAsc ? <ChevronDown size={12} className="rotate-180" /> : <ChevronDown size={12} />)}
      </button>
    </th>
  );

  return (
    <div className="space-y-6">
      {data.bids.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
            <div>
              <p className="font-bold text-slate-900">Bidder Scores</p>
              <p className="text-xs text-slate-500">
                {data.bids.length} bidder{data.bids.length === 1 ? "" : "s"}
                {isLotWise ? ` · ${lots.length} lot${lots.length === 1 ? "" : "s"} each` : ""} ·{" "}
                {rows.filter((r) => r.technicalAvg != null).length} scored ·{" "}
                {rows.filter((r) => r.financialFinalized).length} finalized
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  className="input-field w-56 pl-8 text-sm"
                  placeholder="Filter by bidder..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              {openBidIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setOpenBidIds([])}
                  className="btn-secondary py-1.5 px-3 text-xs"
                >
                  Collapse all
                </button>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <SortHeader label="Bidder" value="vendor" align="left" />
                  {isLotWise && <SortHeader label="Lot" value="lot" align="left" />}
                  <SortHeader label={`Technical / ${data.technicalScoreTotal}`} value="technical" />
                  <SortHeader label={`Financial / ${data.financialWeight}`} value="financial" />
                  <SortHeader label={`Combined / ${data.technicalScoreTotal + data.financialWeight}`} value="combined" />
                  <th className="px-3 py-2 text-right font-semibold">
                    Scored By
                    <span className="block text-[10px] font-normal text-slate-400">quorum {data.quorum || "—"}</span>
                  </th>
                  <SortHeader label="Status" value="status" align="left" />
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((r, index) => {
                  const open = openBidIds.includes(r.bid.bidId);
                  // Only the first row of a bidder carries the name, chevron and bid-level
                  // progress, so a bidder's lots read as one indented block. Recomputed
                  // per render so it stays correct under any sort order.
                  const firstOfBidder = index === 0 || visibleRows[index - 1].bid.bidId !== r.bid.bidId;
                  return (
                    <tr
                      key={r.key}
                      className={`cursor-pointer border-t border-slate-100 transition-colors hover:bg-slate-50 ${open ? "bg-emerald-50/40" : ""}`}
                      onClick={() => toggleBid(r.bid.bidId)}
                    >
                      <td className={`px-3 py-2.5 align-top ${firstOfBidder ? "" : "pl-9"}`}>
                        {firstOfBidder ? (
                          <>
                            <span className="flex items-center gap-1.5 font-semibold text-slate-900">
                              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                              {r.bid.vendorName}
                            </span>
                            <span className="ml-5 block text-[11px] text-slate-400">
                              {r.bid.bidStage} · {r.bid.status}
                              {isLotWise && r.lotsPassed != null && r.lotsPassed < (r.lotCount ?? 0)
                                ? ` · ${r.lotsPassed}/${r.lotCount} lots passed`
                                : ""}
                            </span>
                          </>
                        ) : null}
                      </td>
                      {isLotWise && (
                        <td className="px-3 py-2.5 align-top text-slate-700">
                          {r.lot?.lotName ?? "—"}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-right align-top">
                        <span className="font-bold text-slate-900">{r.technicalAvg != null ? r.technicalAvg.toFixed(1) : "—"}</span>
                        {r.technicalPct != null && (
                          <span className={`block text-[11px] ${r.passedThreshold ? "text-emerald-600" : "text-rose-500"}`}>
                            {r.technicalPct.toFixed(1)}% vs {thresholdPct}% threshold
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right align-top font-bold text-slate-900">
                        {r.financialAvg != null ? r.financialAvg.toFixed(1) : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right align-top font-bold text-emerald-700">
                        {r.combined != null ? r.combined.toFixed(1) : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right align-top text-slate-600">
                        {r.scoredMembers > 0 ? r.scoredMembers : "—"}
                      </td>
                      <td className="px-3 py-2.5 align-top">
                        <span className={`badge ${rowStatusTone(r)}`}>{rowStatusLabel(r)}</span>
                      </td>
                    </tr>
                  );
                })}
                {visibleRows.length === 0 && (
                  <tr>
                    <td colSpan={isLotWise ? 7 : 6} className="px-4 py-6 text-center text-sm text-slate-400">
                      No {isLotWise ? "bidder or lot" : "bidder"} matches “{query}”.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.bids.length > 1 && (
        <p className="text-xs text-slate-500">
          Select a bidder to see the individual marks each Evaluation Committee member gave{isLotWise ? ", lot by lot" : ""}.
        </p>
      )}

      {/* Driven by `data.bids`, not the filtered rows: typing in the filter box should
          not silently throw away a bidder's expanded member-by-member marks. */}
      {data.bids.map((bid) => {
        if (!openBidIds.includes(bid.bidId)) return null;
        const technicalEvals = bid.evaluations.filter((e) => e.stage === "technical");
        const financialEvals = bid.evaluations.filter((e) => e.stage === "financial");
        // Legacy lot-wise data can hold lot=NULL rows; on a lot-wise tender those are
        // the only marks those members have, so they get their own trailing section
        // rather than being silently dropped.
        const lotlessEvals = bid.evaluations.filter((e) => !e.lot);
        const scopeMap = buildScopeMap(bid);
        const bidFinancialAvg = averageFinancialMark(bid.evaluations);
        // Distinct people, not rows — on a lot-wise tender one member holds a row per lot.
        const scoredMemberCount = new Set(technicalEvals.map((e) => e.evaluator)).size;
        // On a lot-wise tender the bid-level flags are a roll-up across lots; the
        // authoritative verdict is per lot, so say so rather than presenting one blended
        // technical number as the bid's outcome.
        const rollUpPrefix = isLotWise ? "All lots — " : "";

        return (
          <div key={bid.bidId} id={`bidder-${bid.bidId}`} className="space-y-3 scroll-mt-24">
            <div className="rounded-2xl border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
                <div>
                  <p className="flex items-center gap-1.5 font-bold text-slate-900">
                    <button
                      type="button"
                      onClick={() => toggleBid(bid.bidId)}
                      className="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-0.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                    >
                      <ChevronDown size={14} /> Hide
                    </button>
                    {bid.vendorName}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {bid.bidStage} · {bid.status} ·{" "}
                    {isLotWise
                      ? `${lots.length} lot${lots.length === 1 ? "" : "s"} · ${scoredMemberCount} member technical score(s)`
                      : `${scoredMemberCount} member technical score(s)`}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`badge ${bid.technicalQuorumMet ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {bid.technicalQuorumMet ? `${rollUpPrefix}technical quorum met` : "Awaiting quorum"}
                  </span>
                  <span className={`badge ${bid.passedTechnicalThreshold ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                    {bid.passedTechnicalThreshold ? `${rollUpPrefix}above threshold` : "Below threshold"}
                  </span>
                  <span className={`badge ${bid.financialFinalized ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {bid.financialFinalized ? `${rollUpPrefix}financial finalized` : "Financial pending"}
                  </span>
                </div>
              </div>

              {isLotWise && (
                <div className="grid grid-cols-1 gap-2 border-b border-slate-100 bg-slate-50/60 px-5 py-3 sm:grid-cols-2 lg:grid-cols-3">
                  {lots.map((lot) => {
                    const technical = bid.lotTechnicalSummary?.[lot.lotId];
                    const finalised = bid.lotFinancialFinalized?.[lot.lotId] === true;
                    const financialAvg = averageFinancialMark(bid.evaluations.filter((ev) => ev.lot === lot.lotId));
                    return (
                      <div key={lot.lotId} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                        <p className="flex items-center gap-1.5 text-xs font-bold text-slate-700">
                          <Layers size={12} className="text-slate-400" /> {lot.lotName}
                        </p>
                        <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1">
                          <p className="text-sm font-bold text-slate-900">
                            {technical?.rawAverage != null ? `${Number(technical.rawAverage).toFixed(1)}/${technicalMax}` : "—"}
                            <span className="ml-1 text-[11px] font-medium text-slate-400">technical</span>
                          </p>
                          <p className="text-sm font-bold text-slate-900">
                            {financialAvg != null ? `${financialAvg.toFixed(1)}/${financialMax}` : "—"}
                            <span className="ml-1 text-[11px] font-medium text-slate-400">financial</span>
                          </p>
                        </div>
                        {technical?.averageScore != null && (
                          <p className="text-[11px] font-medium text-slate-500">
                            Committee average {Number(technical.averageScore).toFixed(1)}% · threshold {data.technicalThreshold}%
                          </p>
                        )}
                        <div className="mt-1 flex flex-wrap gap-1">
                          <span className={`badge ${technical?.quorumMet ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                            {technical?.quorumMet ? "Quorum met" : `${technical?.memberCount ?? 0} score(s)`}
                          </span>
                          <span className={`badge ${technical?.passedThreshold ? "bg-emerald-100 text-emerald-700" : technical?.quorumMet ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-500"}`}>
                            {technical?.passedThreshold ? "Above threshold" : technical?.quorumMet ? "Below threshold" : "Awaiting quorum"}
                          </span>
                          <span className={`badge ${finalised ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                            {finalised ? "Financial final" : "Financial pending"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {!isLotWise && (
                <div className="flex flex-wrap gap-6 bg-slate-50/60 px-5 py-3 text-sm">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Technical Average</p>
                    <p className="text-xl font-bold text-emerald-700">
                      {bid.technicalRawAverage != null ? `${Number(bid.technicalRawAverage).toFixed(1)} / ${data.technicalScoreTotal}` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Financial Average</p>
                    <p className="text-xl font-bold text-emerald-700">
                      {bidFinancialAvg != null ? `${bidFinancialAvg.toFixed(1)} / ${data.financialWeight}` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Committee Average</p>
                    <p className="text-xl font-bold text-emerald-700">
                      {bid.technicalAverageScore != null ? `${Number(bid.technicalAverageScore).toFixed(1)} %` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Threshold</p>
                    <p className="text-xl font-bold text-slate-800">{data.technicalThreshold}%</p>
                  </div>
                  {bid.technicalRawAverage != null && bidFinancialAvg != null && (
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Combined</p>
                      <p className="text-xl font-bold text-slate-900">
                        {(Number(bid.technicalRawAverage) + bidFinancialAvg).toFixed(1)} / {data.technicalScoreTotal + data.financialWeight}
                      </p>
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
                      <th className="px-2 py-2.5 text-center font-semibold">
                        Technical
                        <span className="block text-[10px] font-normal text-slate-400">out of {data.technicalScoreTotal}</span>
                      </th>
                      <th className="px-2 py-2.5 text-center font-semibold">
                        Financial
                        <span className="block text-[10px] font-normal text-slate-400">out of {data.financialWeight}</span>
                      </th>
                      <th className="px-2 py-2.5 text-center font-semibold">
                        Combined
                        <span className="block text-[10px] font-normal text-slate-400">out of {data.technicalScoreTotal + data.financialWeight}</span>
                      </th>
                      <th className="px-2 py-2.5 text-left font-semibold">Comments</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLotWise ? (
                      <>
                        {lots.map((lot) => renderLotSection(bid, lot, scopeMap))}
                        {lotlessEvals.length > 0 && renderSectionLabel(
                          `Not tied to a lot — ${lotlessEvals.length} score(s)`,
                          <span className="text-[11px] text-slate-400">Scored before this tender was split into lots</span>,
                        )}
                        {lotlessEvals.map((ev) =>
                          ev.stage === "technical"
                            ? renderTechnicalRow(ev, { showLot: true, scopeMap })
                            : renderFinancialRow(ev, { showLot: true, scopeMap }),
                        )}
                      </>
                    ) : (
                      <>
                        {renderSectionLabel(`Technical — ${technicalEvals.length} member score(s)`)}
                        {technicalEvals.length > 0
                          ? technicalEvals.map((ev) => renderTechnicalRow(ev, { scopeMap }))
                          : renderEmptyRow("No committee technical marks submitted yet for this bid.")}
                        {renderSectionLabel(`Financial — ${financialEvals.length} member score(s)`)}
                        {financialEvals.length > 0
                          ? financialEvals.map((ev) => renderFinancialRow(ev, { lotTone: true, scopeMap }))
                          : renderEmptyRow("No committee financial marks submitted yet for this bid.")}
                      </>
                    )}
                    {bid.evaluations.length === 0 && (
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
