import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Flag, Loader2, Send, XCircle } from "lucide-react";
import {
  createBlacklistRecommendation,
  fetchBlacklistRecommendations,
  fetchProjects,
  fetchVendorDirectory,
  respondToBlacklistRecommendation,
} from "../api";
import { BlacklistRecommendation, Project, VendorDirectoryEntry } from "../types";

const REASONS = ["Fraudulent Reporting", "Integrity Breach", "Persistent Non-Performance", "External Legal Action"];

const STATUS_BADGE: Record<string, string> = {
  Submitted: "bg-amber-100 text-amber-700",
  Accepted: "bg-rose-100 text-rose-700",
  Declined: "bg-slate-100 text-slate-600",
};

const errorMessage = (err: any, fallback: string) => {
  const raw = String(err?.message || "");
  try {
    const parsed = JSON.parse(raw.slice(raw.indexOf("{")));
    if (parsed?.detail) return String(parsed.detail);
    const first = Object.entries(parsed || {})[0];
    if (first) return `${first[0].replace(/_/g, " ")}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
  } catch {
    // Not a JSON error body.
  }
  return fallback;
};

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "—");

async function fetchAllRegionalVendors(): Promise<VendorDirectoryEntry[]> {
  const first = await fetchVendorDirectory(1);
  const rest = await Promise.all(
    Array.from({ length: Math.min(first.totalPages, 10) - 1 }, (_, index) => fetchVendorDirectory(index + 2)),
  );
  return [...first.vendors, ...rest.flatMap((page) => page.vendors)];
}

function RecommendationRow({ item, children }: { item: BlacklistRecommendation; children?: React.ReactNode }) {
  return (
    <div className="space-y-2 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-slate-900">{item.vendorName || item.vendorUsername}</p>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">{item.reason}</span>
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_BADGE[item.status] || STATUS_BADGE.Declined}`}>{item.status}</span>
        </div>
        <span className="text-xs text-slate-400">{formatDateTime(item.createdAt)}</span>
      </div>
      <p className="whitespace-pre-line text-sm text-slate-700">{item.justification}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>By {item.recommendedByUsername || "DoE Officer"}{item.recommendedByRegion ? ` (${item.recommendedByRegion})` : ""}</span>
        {item.projectReference && <span>Project {item.projectReference}</span>}
        {item.evidenceDocument && (
          <a href={item.evidenceDocument} target="_blank" rel="noreferrer" className="text-emerald-700 underline">Evidence</a>
        )}
      </div>
      {item.status !== "Submitted" && (
        <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <span className="font-semibold">RMT response</span>
          {item.respondedByUsername ? ` (${item.respondedByUsername}, ${formatDateTime(item.respondedAt)})` : ""}: {item.responseNotes || (item.status === "Accepted" ? "A blacklisting case was opened." : "Declined.")}
        </p>
      )}
      {children}
    </div>
  );
}

/** DoE officers flag a vendor to RMT with a blacklisting recommendation; they cannot open or change cases. */
export function DoeBlacklistRecommendationPanel() {
  const [vendors, setVendors] = useState<VendorDirectoryEntry[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [mine, setMine] = useState<BlacklistRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ vendorId: "", projectId: "", reason: REASONS[0], justification: "" });
  const [evidence, setEvidence] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [vendorRows, projectRows, recommendationRows] = await Promise.all([
        fetchAllRegionalVendors(),
        fetchProjects(),
        fetchBlacklistRecommendations(),
      ]);
      setVendors(vendorRows);
      setProjects(projectRows);
      setMine(recommendationRows);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err, "Unable to load recommendation data.") });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const vendorProjects = projects.filter((project) => !form.vendorId || project.vendorId === form.vendorId);

  const submit = async () => {
    if (!form.vendorId) return setMessage({ tone: "error", text: "Select the vendor you are recommending." });
    if (form.justification.trim().length < 30) {
      return setMessage({ tone: "error", text: "Explain what you found (at least 30 characters)." });
    }
    setSaving(true);
    setMessage(null);
    try {
      const created = await createBlacklistRecommendation({
        vendorId: form.vendorId,
        projectId: form.projectId || undefined,
        reason: form.reason,
        justification: form.justification.trim(),
        evidenceDocument: evidence,
      });
      setMine((prev) => [created, ...prev]);
      setForm({ vendorId: "", projectId: "", reason: REASONS[0], justification: "" });
      setEvidence(null);
      setMessage({ tone: "ok", text: "Recommendation sent to the RBF Management Team." });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err, "Unable to submit the recommendation.") });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card space-y-4 p-6">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-bold"><Flag size={18} className="text-amber-600" /> Recommend Vendor for Blacklisting</h3>
          <p className="text-sm text-slate-500">
            Flag a vendor in your region to RMT. RMT decides whether to open a blacklisting case; you can follow the outcome below.
          </p>
        </div>
        {loading ? (
          <div className="py-4 text-center text-slate-500"><Loader2 size={18} className="mx-auto animate-spin" /></div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <label className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-slate-400">Vendor *</span>
                <select
                  className="input-field py-2 text-sm"
                  value={form.vendorId}
                  onChange={(e) => setForm((prev) => ({ ...prev, vendorId: e.target.value, projectId: "" }))}
                >
                  <option value="">Select vendor</option>
                  {vendors.map((vendor) => (
                    <option key={vendor.id} value={vendor.id}>
                      {vendor.organizationName || vendor.fullName}
                      {vendor.username && vendor.username !== (vendor.organizationName || vendor.fullName) ? ` (${vendor.username})` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-slate-400">Related project</span>
                <select
                  className="input-field py-2 text-sm"
                  value={form.projectId}
                  onChange={(e) => setForm((prev) => ({ ...prev, projectId: e.target.value }))}
                >
                  <option value="">Not specific to one project</option>
                  {vendorProjects.map((project) => (
                    <option key={project.id} value={project.id}>{project.projectReference || `PRJ-${project.id}`}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-slate-400">Reason *</span>
                <select className="input-field py-2 text-sm" value={form.reason} onChange={(e) => setForm((prev) => ({ ...prev, reason: e.target.value }))}>
                  {REASONS.map((reason) => <option key={reason}>{reason}</option>)}
                </select>
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-[10px] font-bold uppercase text-slate-400">What did you find? *</span>
              <textarea
                className="input-field min-h-[100px] text-sm"
                placeholder="Describe the evidence: what you observed, where and when."
                value={form.justification}
                onChange={(e) => setForm((prev) => ({ ...prev, justification: e.target.value }))}
              />
            </label>
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <label className="space-y-1">
                <span className="text-[10px] font-bold uppercase text-slate-400">Evidence (PDF, JPG, PNG)</span>
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setEvidence(e.target.files?.[0] ?? null)} className="block text-sm text-slate-600" />
              </label>
              <button type="button" onClick={() => void submit()} disabled={saving} className="btn-primary inline-flex items-center gap-2 self-start">
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Send Recommendation
              </button>
            </div>
            {vendors.length === 0 && <p className="text-xs text-slate-500">No vendors are registered in your region.</p>}
          </>
        )}
        {message && (
          <p className={`rounded-xl px-3 py-2 text-sm ${message.tone === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{message.text}</p>
        )}
      </div>

      <div className="card">
        <div className="border-b border-slate-100 p-5">
          <h3 className="text-lg font-bold text-slate-900">My Recommendations</h3>
          <p className="text-xs text-slate-500">Recommendations are a permanent record and cannot be edited or deleted after sending.</p>
        </div>
        {mine.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">You have not recommended any vendors.</p>
        ) : (
          <div className="divide-y divide-slate-100">{mine.map((item) => <React.Fragment key={item.id}><RecommendationRow item={item} /></React.Fragment>)}</div>
        )}
      </div>
    </div>
  );
}

/** RMT queue of DoE recommendations: accept opens a four-eyes blacklisting case, decline closes it with a reason. */
export function RmtBlacklistRecommendationsPanel({ canAct, onCaseOpened }: { canAct: boolean; onCaseOpened: () => void }) {
  const [items, setItems] = useState<BlacklistRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetchBlacklistRecommendations()
      .then(setItems)
      .catch((err) => setError(errorMessage(err, "Unable to load DoE recommendations.")))
      .finally(() => setLoading(false));
  }, []);

  const respond = async (item: BlacklistRecommendation, decision: "accept" | "decline") => {
    const note = (notes[item.id] || "").trim();
    if (decision === "decline" && !note) {
      setError("Add a note explaining why the recommendation is declined.");
      return;
    }
    if (decision === "accept" && !window.confirm(`Open a blacklisting case for ${item.vendorName || item.vendorUsername}? The vendor is suspended during cooling-off.`)) {
      return;
    }
    setBusyId(item.id);
    setError(null);
    try {
      const updated = await respondToBlacklistRecommendation(item.id, decision, note);
      setItems((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      if (decision === "accept") onCaseOpened();
    } catch (err) {
      setError(errorMessage(err, `Unable to ${decision} the recommendation.`));
    } finally {
      setBusyId(null);
    }
  };

  const pending = items.filter((item) => item.status === "Submitted");
  const history = items.filter((item) => item.status !== "Submitted");

  if (loading) return null;
  if (items.length === 0 && !error) return null;

  return (
    <div className="card">
      <div className="flex flex-col gap-2 border-b border-slate-100 p-5 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><Flag size={18} className="text-amber-600" /> DoE Recommendations</h3>
          <p className="text-xs text-slate-500">
            {pending.length} awaiting a decision. Accepting opens a blacklisting case with you as the initiator.
          </p>
        </div>
        {history.length > 0 && (
          <button type="button" onClick={() => setShowHistory((value) => !value)} className="text-xs font-semibold text-slate-500 hover:text-slate-700">
            {showHistory ? "Hide" : "Show"} actioned ({history.length})
          </button>
        )}
      </div>
      {error && <p className="mx-5 mt-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="divide-y divide-slate-100">
        {pending.length === 0 && <p className="px-5 py-6 text-center text-sm text-slate-500">No recommendations awaiting a decision.</p>}
        {pending.map((item) => (
          <React.Fragment key={item.id}>
          <RecommendationRow item={item}>
            {canAct && (
              <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <input
                  className="input-field flex-1 py-2 text-sm"
                  placeholder="Response note (required to decline)"
                  value={notes[item.id] || ""}
                  onChange={(e) => setNotes((prev) => ({ ...prev, [item.id]: e.target.value }))}
                />
                <div className="flex gap-2">
                  <button type="button" disabled={busyId === item.id} onClick={() => void respond(item, "decline")} className="btn-secondary inline-flex items-center gap-1 text-xs">
                    <XCircle size={14} /> Decline
                  </button>
                  <button type="button" disabled={busyId === item.id} onClick={() => void respond(item, "accept")} className="btn-primary inline-flex items-center gap-1 text-xs">
                    {busyId === item.id ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Accept & Open Case
                  </button>
                </div>
              </div>
            )}
          </RecommendationRow>
          </React.Fragment>
        ))}
        {showHistory && history.map((item) => <React.Fragment key={item.id}><RecommendationRow item={item} /></React.Fragment>)}
      </div>
    </div>
  );
}
