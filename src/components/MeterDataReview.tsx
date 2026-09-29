import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, FileText, RefreshCw, ShieldAlert, X } from "lucide-react";
import {
  fetchMeterDataBatch,
  fetchMeterDataBatches,
  initiateVendorBlacklisting,
  MeterDataBatchReviewAction,
  reviewMeterDataBatch,
} from "../api";
import { MeterDataBatch, MeterDataBatchStatus, MeterIntegrityFinding } from "../types";

const STATUS_LABELS: Record<MeterDataBatchStatus, string> = {
  pending_review: "Pending review",
  flagged: "Flagged: failed checks",
  verified: "Verified",
  rejected: "Rejected",
  correction_requested: "Correction requested",
  superseded: "Superseded by new upload",
};

const STATUS_TONES: Record<MeterDataBatchStatus, string> = {
  pending_review: "bg-slate-100 text-slate-700",
  flagged: "bg-rose-100 text-rose-700",
  verified: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-50 text-rose-600 line-through",
  correction_requested: "bg-amber-100 text-amber-700",
  superseded: "bg-slate-100 text-slate-500",
};

const SEVERITY_TONES: Record<MeterIntegrityFinding["severity"], string> = {
  high: "border-rose-200 bg-rose-50 text-rose-800",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-slate-200 bg-slate-50 text-slate-700",
};

const OPEN_STATUSES: MeterDataBatchStatus[] = ["pending_review", "flagged", "verified"];

type ReviewMode = "verify" | "reject" | "request-correction" | "reject-readings" | "restore-readings" | "blacklist";

const MODE_COPY: Record<ReviewMode, { title: string; field: string; placeholder: string; button: string }> = {
  verify: {
    title: "Verify this upload as genuine",
    field: "Verification notes",
    placeholder: "What did you check? e.g. readings match the site visit / meter photos.",
    button: "Verify upload",
  },
  reject: {
    title: "Reject the entire upload",
    field: "Reason (sent to the vendor)",
    placeholder: "Why is this data not genuine?",
    button: "Reject upload",
  },
  "request-correction": {
    title: "Send back to the vendor for correction",
    field: "What must be corrected (sent to the vendor)",
    placeholder: "e.g. Meter IDs are swapped between households; re-export from the meter portal.",
    button: "Request correction",
  },
  "reject-readings": {
    title: "Reject the selected readings",
    field: "Reason (sent to the vendor)",
    placeholder: "Why are these readings not genuine?",
    button: "Reject selected readings",
  },
  "restore-readings": {
    title: "Restore the selected readings",
    field: "Reason for restoring",
    placeholder: "Why were these readings rejected by mistake?",
    button: "Restore selected readings",
  },
  blacklist: {
    title: "Initiate blacklisting for fraudulent reporting",
    field: "Case description",
    placeholder: "",
    button: "Initiate blacklisting case",
  },
};

const SUCCESS_MESSAGES: Record<Exclude<ReviewMode, "blacklist">, string> = {
  verify: "Upload verified. The vendor has been notified.",
  reject: "Upload rejected. Its readings no longer count, and the vendor has been notified.",
  "request-correction": "Correction requested. Milestone claims stay blocked until the vendor uploads corrected data.",
  "reject-readings": "Selected readings rejected. They no longer count toward KPIs or milestones.",
  "restore-readings": "Selected readings restored and counted again.",
};

function friendlyError(err: any, fallback: string): string {
  const raw = String(err?.message || "").replace(/^HTTP \d+ [^:]*:\s*/, "");
  try {
    const parsed = JSON.parse(raw);
    const first = Object.values(parsed)[0];
    if (Array.isArray(first)) return String(first[0]);
    if (first) return String(first);
  } catch {
    // Not JSON: fall through to the raw text.
  }
  return raw || fallback;
}

function formatDateTime(value?: string): string {
  if (!value) return "N/A";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "N/A" : date.toLocaleString();
}

type Props = {
  projectId: string;
  vendorId?: string;
  vendorName?: string;
  /** RBF Official / Super Admin: can verify, reject and request corrections. */
  canReview: boolean;
  /** RBF Official only: may open a blacklisting case (the Super Admin confirms cases instead). */
  canInitiateBlacklisting?: boolean;
  /** Called after any review decision so the page can refresh readings and KPIs. */
  onChanged?: () => void | Promise<void>;
};

export default function MeterDataReview({ projectId, vendorId, vendorName, canReview, canInitiateBlacklisting, onChanged }: Props) {
  const [batches, setBatches] = useState<MeterDataBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openBatch, setOpenBatch] = useState<MeterDataBatch | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [selectedReadingIds, setSelectedReadingIds] = useState<string[]>([]);
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);
  const [mode, setMode] = useState<ReviewMode | null>(null);
  const [text, setText] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setBatches(await fetchMeterDataBatches(projectId));
    } catch (err: any) {
      setError(friendlyError(err, "Unable to load meter data uploads."));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => ({
    flagged: batches.filter((batch) => batch.status === "flagged").length,
    pending: batches.filter((batch) => batch.status === "pending_review").length,
    correction: batches.filter((batch) => batch.status === "correction_requested").length,
    rejected: batches.filter((batch) => batch.status === "rejected").length,
  }), [batches]);

  const openDetail = async (batchId: string) => {
    setBatchLoading(true);
    setSelectedReadingIds([]);
    setShowFlaggedOnly(false);
    setMode(null);
    setMessage(null);
    setActionError(null);
    try {
      setOpenBatch(await fetchMeterDataBatch(batchId));
    } catch (err: any) {
      setError(friendlyError(err, "Unable to load this upload."));
    } finally {
      setBatchLoading(false);
    }
  };

  const startMode = (next: ReviewMode) => {
    setMode(next);
    setActionError(null);
    setDueDate("");
    if (next === "blacklist" && openBatch) {
      const high = openBatch.integrityFindings.filter((finding) => finding.severity === "high");
      setText(
        `Meter data upload #${openBatch.id} (${openBatch.fileName || "CSV"}) for project ${openBatch.projectReference || projectId}, ` +
        `uploaded ${formatDateTime(openBatch.createdAt)}, is suspected to be fabricated.` +
        (high.length ? ` Failed checks: ${high.map((finding) => finding.message).join(" ")}` : "") +
        (openBatch.reviewNotes ? ` Reviewer notes: ${openBatch.reviewNotes}` : ""),
      );
    } else {
      setText("");
    }
  };

  const submit = async () => {
    if (!openBatch || !mode) return;
    const value = text.trim();
    const needsText = mode !== "verify" || openBatch.status === "flagged";
    if (needsText && !value) {
      setActionError(`${MODE_COPY[mode].field} is required.`);
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      if (mode === "blacklist") {
        if (!vendorId) throw new Error("The vendor for this project could not be identified.");
        await initiateVendorBlacklisting({ vendorId, reason: "Fraudulent Reporting", description: value });
        setMessage("Blacklisting case opened. The vendor is suspended while the case is reviewed.");
      } else {
        let review: MeterDataBatchReviewAction;
        if (mode === "verify") review = { action: "verify", notes: value };
        else if (mode === "reject") review = { action: "reject", reason: value };
        else if (mode === "request-correction") review = { action: "request-correction", reason: value, dueDate: dueDate || undefined };
        else if (mode === "reject-readings") review = { action: "reject-readings", readingIds: selectedReadingIds, reason: value };
        else review = { action: "restore-readings", readingIds: selectedReadingIds, notes: value };
        const updated = await reviewMeterDataBatch(openBatch.id, review);
        setOpenBatch(updated);
        setBatches((current) => current.map((batch) => (batch.id === updated.id ? { ...updated, readings: undefined } : batch)));
        setSelectedReadingIds([]);
        setMessage(SUCCESS_MESSAGES[mode]);
        await onChanged?.();
      }
      setMode(null);
      setText("");
    } catch (err: any) {
      setActionError(friendlyError(err, "The review action failed."));
    } finally {
      setSubmitting(false);
    }
  };

  const isOpen = openBatch ? OPEN_STATUSES.includes(openBatch.status) : false;
  const readings = (openBatch?.readings || []).filter((reading) => !showFlaggedOnly || reading.integrityFlags.length > 0);
  const selectedAccepted = (openBatch?.readings || []).filter((reading) => selectedReadingIds.includes(reading.id) && reading.reviewStatus === "accepted").length;
  const selectedRejected = (openBatch?.readings || []).filter((reading) => selectedReadingIds.includes(reading.id) && reading.reviewStatus === "rejected").length;
  const toggleReading = (id: string) =>
    setSelectedReadingIds((current) => (current.includes(id) ? current.filter((value) => value !== id) : [...current, id]));

  return (
    <div className="card">
      <div className="p-5 border-b border-slate-100 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Meter Data Authenticity Review</h3>
          <p className="text-sm text-slate-500">
            {canReview
              ? "Every vendor upload is checked automatically. Review each upload, and reject or send back data that is not genuine: rejected readings stop counting toward KPIs and milestones."
              : "Each meter upload is checked automatically and reviewed by RBF. Rejected readings do not count toward KPIs or milestones."}
          </p>
        </div>
        <button type="button" onClick={() => void load()} className="btn-secondary inline-flex items-center gap-2 self-start">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {(counts.flagged > 0 || counts.correction > 0) && (
        <div className="mx-5 mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            {counts.flagged > 0 && `${counts.flagged} upload(s) failed integrity checks and await review. `}
            {counts.correction > 0 && `${counts.correction} upload(s) were sent back for correction. `}
            Milestone claims for this project are blocked until these are cleared.
          </span>
        </div>
      )}

      {error && <p className="mx-5 mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

      <div className="p-5 overflow-x-auto">
        {loading ? (
          <p className="text-sm text-slate-500">Loading meter uploads...</p>
        ) : batches.length === 0 ? (
          <p className="text-sm text-slate-500">No meter data uploads yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-slate-400">
                <th className="py-2 pr-4">Uploaded</th>
                <th className="py-2 pr-4">By</th>
                <th className="py-2 pr-4">Rows</th>
                <th className="py-2 pr-4">kWh</th>
                <th className="py-2 pr-4">Checks</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {batches.map((batch) => {
                const high = batch.integrityFindings.filter((finding) => finding.severity === "high").length;
                const medium = batch.integrityFindings.filter((finding) => finding.severity === "medium").length;
                return (
                  <tr key={batch.id}>
                    <td className="py-3 pr-4">
                      <p className="font-semibold text-slate-900">{formatDateTime(batch.createdAt)}</p>
                      <p className="text-xs text-slate-500">#{batch.id} · {batch.fileName || "CSV"}</p>
                    </td>
                    <td className="py-3 pr-4 text-slate-700">{batch.uploadedByName || batch.uploadedByUsername || "Unknown"}</td>
                    <td className="py-3 pr-4 text-slate-700">
                      {batch.rowsIngested}
                      {batch.readingsRejected > 0 && <span className="text-rose-600"> ({batch.readingsRejected} rejected)</span>}
                    </td>
                    <td className="py-3 pr-4 text-slate-700">{batch.totalKwh.toFixed(2)}</td>
                    <td className="py-3 pr-4">
                      {high === 0 && medium === 0 ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><CheckCircle2 size={13} /> Passed</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {high > 0 && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-700">{high} high</span>}
                          {medium > 0 && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700">{medium} medium</span>}
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_TONES[batch.status]}`}>{STATUS_LABELS[batch.status]}</span>
                    </td>
                    <td className="py-3 text-right">
                      <button type="button" onClick={() => void openDetail(batch.id)} className="btn-secondary text-xs" disabled={batchLoading}>
                        {canReview && (batch.status === "flagged" || batch.status === "pending_review") ? "Review" : "View"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {openBatch && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-100 bg-white px-6 py-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Meter upload #{openBatch.id}</h3>
                <p className="text-sm text-slate-500">
                  {openBatch.uploadedByName || openBatch.uploadedByUsername || "Unknown uploader"} · {formatDateTime(openBatch.createdAt)} ·{" "}
                  {openBatch.rowsIngested} rows ingested{openBatch.rowsRejectedOnUpload > 0 ? `, ${openBatch.rowsRejectedOnUpload} invalid rows dropped at upload` : ""}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_TONES[openBatch.status]}`}>{STATUS_LABELS[openBatch.status]}</span>
                <button type="button" onClick={() => setOpenBatch(null)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Close">
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="space-y-6 p-6">
              {openBatch.sourceFileUrl && (
                <a href={openBatch.sourceFileUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm font-semibold text-blue-600 hover:text-blue-700">
                  <FileText size={14} /> Open the original CSV the vendor uploaded <ExternalLink size={12} />
                </a>
              )}

              {openBatch.reviewNotes && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    RBF review{openBatch.reviewedByUsername ? ` by ${openBatch.reviewedByUsername}` : ""} · {formatDateTime(openBatch.reviewedAt)}
                  </p>
                  <p className="mt-1">{openBatch.reviewNotes}</p>
                  {openBatch.correctionDueDate && <p className="mt-1 font-semibold">Corrected data due by {openBatch.correctionDueDate}.</p>}
                </div>
              )}

              <div>
                <h4 className="text-sm font-bold uppercase tracking-wide text-slate-900">Integrity checks</h4>
                {openBatch.integrityFindings.length === 0 ? (
                  <p className="mt-2 inline-flex items-center gap-2 text-sm text-emerald-700">
                    <CheckCircle2 size={15} /> All automated checks passed: no duplicates, future dates, location mismatches or implausible values.
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {openBatch.integrityFindings.map((finding) => (
                      <li key={`${finding.code}-${finding.meterId}`} className={`rounded-xl border px-4 py-2.5 text-sm ${SEVERITY_TONES[finding.severity]}`}>
                        <span className="mr-2 text-[10px] font-bold uppercase tracking-widest">{finding.severity}</span>
                        <span className="font-semibold">{finding.label}:</span> {finding.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-bold uppercase tracking-wide text-slate-900">Readings</h4>
                  <label className="inline-flex items-center gap-2 text-xs text-slate-600">
                    <input type="checkbox" checked={showFlaggedOnly} onChange={(e) => setShowFlaggedOnly(e.target.checked)} />
                    Show only readings that tripped a check
                  </label>
                </div>
                <div className="mt-2 max-h-80 overflow-auto rounded-xl border border-slate-200">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-slate-50">
                      <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400">
                        {canReview && isOpen && <th className="px-3 py-2" />}
                        <th className="px-3 py-2">Meter</th>
                        <th className="px-3 py-2">Recorded</th>
                        <th className="px-3 py-2">kWh</th>
                        <th className="px-3 py-2">Uptime</th>
                        <th className="px-3 py-2">Power (W)</th>
                        <th className="px-3 py-2">GPS</th>
                        <th className="px-3 py-2">Checks</th>
                        <th className="px-3 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {readings.map((reading) => (
                        <tr key={reading.id} className={reading.reviewStatus === "rejected" ? "bg-rose-50/60 text-slate-400" : ""}>
                          {canReview && isOpen && (
                            <td className="px-3 py-2">
                              <input
                                type="checkbox"
                                checked={selectedReadingIds.includes(reading.id)}
                                onChange={() => toggleReading(reading.id)}
                                aria-label={`Select reading ${reading.id}`}
                              />
                            </td>
                          )}
                          <td className="px-3 py-2 font-semibold">{reading.meterId}</td>
                          <td className="px-3 py-2">{formatDateTime(reading.recordedAt)}</td>
                          <td className="px-3 py-2">{reading.kwh.toFixed(2)}</td>
                          <td className="px-3 py-2">{reading.uptimePct != null ? `${reading.uptimePct}%` : "—"}</td>
                          <td className="px-3 py-2">{reading.outputPowerW != null ? reading.outputPowerW : "—"}</td>
                          <td className="px-3 py-2">{reading.latitude != null && reading.longitude != null ? `${reading.latitude.toFixed(4)}, ${reading.longitude.toFixed(4)}` : "—"}</td>
                          <td className="px-3 py-2">
                            {reading.integrityFlags.length === 0 ? (
                              <span className="text-emerald-600">OK</span>
                            ) : (
                              <div className="flex flex-wrap gap-1">
                                {reading.integrityFlags.map((code) => (
                                  <span key={code} className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">{code.replace(/_/g, " ")}</span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {reading.reviewStatus === "rejected" ? (
                              <span className="text-rose-600" title={reading.rejectionReason}>Rejected</span>
                            ) : (
                              <span className="text-slate-600">Counted</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {message && <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}

              {canReview && (isOpen || canInitiateBlacklisting) && (
                <div className="rounded-2xl border border-slate-200 p-4 space-y-3">
                  <h4 className="text-sm font-bold uppercase tracking-wide text-slate-900">Take action</h4>
                  <div className="flex flex-wrap gap-2">
                    {(openBatch.status === "pending_review" || openBatch.status === "flagged") && (
                      <button type="button" className="btn-primary text-sm" onClick={() => startMode("verify")}>Verify as genuine</button>
                    )}
                    {isOpen && (
                      <>
                        <button type="button" className="btn-secondary text-sm" disabled={selectedAccepted === 0} onClick={() => startMode("reject-readings")}>
                          Reject selected ({selectedAccepted})
                        </button>
                        <button type="button" className="btn-secondary text-sm" disabled={selectedRejected === 0} onClick={() => startMode("restore-readings")}>
                          Restore selected ({selectedRejected})
                        </button>
                        <button type="button" className="btn-secondary text-sm" onClick={() => startMode("request-correction")}>Request correction</button>
                        <button type="button" className="btn-secondary text-sm text-rose-700" onClick={() => startMode("reject")}>Reject entire upload</button>
                      </>
                    )}
                    {canInitiateBlacklisting && vendorId && (
                      <button type="button" className="btn-secondary text-sm text-rose-700 inline-flex items-center gap-1" onClick={() => startMode("blacklist")}>
                        <ShieldAlert size={14} /> Initiate blacklisting
                      </button>
                    )}
                  </div>

                  {mode && (
                    <div className="space-y-2 rounded-xl bg-slate-50 p-4">
                      <p className="text-sm font-bold text-slate-900">{MODE_COPY[mode].title}</p>
                      {mode === "blacklist" && (
                        <p className="text-xs text-slate-600">
                          Opens a case against {vendorName || "the vendor"} with reason "Fraudulent Reporting". The vendor is suspended immediately and
                          their pending field verification pauses; the case then goes through review and confirmation on the Blacklisting page.
                        </p>
                      )}
                      {mode === "request-correction" && (
                        <p className="text-xs text-slate-600">All readings in this upload stop counting, and milestone claims stay blocked until the vendor uploads a new file.</p>
                      )}
                      {mode === "reject" && <p className="text-xs text-slate-600">All {openBatch.rowsIngested} readings stop counting toward KPIs and milestones.</p>}
                      <label className="block text-xs font-semibold text-slate-700">
                        {MODE_COPY[mode].field}
                        {mode === "verify" && openBatch.status !== "flagged" ? " (optional)" : ""}
                      </label>
                      <textarea className="input-field min-h-[90px]" value={text} placeholder={MODE_COPY[mode].placeholder} onChange={(e) => setText(e.target.value)} />
                      {mode === "request-correction" && (
                        <label className="block text-xs font-semibold text-slate-700">
                          Corrected data due by (optional)
                          <input type="date" className="input-field mt-1" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                        </label>
                      )}
                      {actionError && <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{actionError}</p>}
                      <div className="flex gap-2">
                        <button type="button" className="btn-primary text-sm disabled:opacity-60" disabled={submitting} onClick={() => void submit()}>
                          {submitting ? "Saving..." : MODE_COPY[mode].button}
                        </button>
                        <button type="button" className="btn-secondary text-sm" onClick={() => setMode(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {!canReview && openBatch.status === "correction_requested" && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  RBF has asked for corrected data. Upload a corrected CSV from the Field Work tab to clear the hold on milestone claims.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
