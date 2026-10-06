/**
 * Report Center: one screen per portal over the shared report engine.
 *
 * The viewer picks a reporting period and optional district / technology / vendor / tender
 * filters, then generates any report in their role's catalogue. Reports are generated in
 * the background; this screen follows each job and downloads the file when it is ready.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarRange, CheckCircle2, Download, FileText, Inbox, Info, Loader2, RefreshCw, Search, Send, Share2, ShieldCheck, X, XCircle } from "lucide-react";
import {
  downloadGeneratedReport,
  fetchReportFilterOptions,
  fetchReportHistory,
  fetchReportInbox,
  fetchReportJob,
  fetchReportTemplates,
  queueReport,
  ReportStep,
  runReportStep,
} from "../api";
import { ReportFilterOptions, ReportFormat, ReportHistoryItem, ReportTemplate, User, UserRole } from "../types";
import { apiErrorMessage } from "./OversightShared";

function saveBlob(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

const FORMAT_LABELS: Partial<Record<ReportFormat, string>> = { excel: "Excel", geojson: "GeoJSON", xml: "IATI XML", zip: "ZIP package" };
const formatLabel = (format: ReportFormat) => FORMAT_LABELS[format] || format.toUpperCase();
const filenameFor = (title: string, format: ReportFormat) => `${title.replace(/[^a-z0-9_-]+/gi, "_")}.${format === "excel" ? "xlsx" : format}`;
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const PAGE_TITLE: Partial<Record<UserRole, { title: string; note: string }>> = {
  [UserRole.DOE_OFFICER]: { title: "Monitoring Reports", note: "Reports cover the districts assigned to you." },
  [UserRole.UNDP_DONOR]: { title: "Monitoring Reports", note: "Reports cover the national portfolio." },
  [UserRole.AUDITOR]: { title: "Compliance Reports", note: "Reports cover the whole platform, read-only." },
  [UserRole.FIELD_VERIFIER]: { title: "My Reports", note: "Reports cover your own verification work." },
  [UserRole.TAC]: { title: "Reports", note: "Technical, verification and inclusion reports for TAC review." },
  [UserRole.RBF_OFFICIAL]: { title: "Reports", note: "Programme reports generated from live platform data." },
  [UserRole.ADMIN]: { title: "Reports", note: "Every report in the platform catalogue." },
  [UserRole.VENDOR]: { title: "My Reports", note: "Reports on your own projects, claims and installations." },
};

type PeriodPreset = "all" | "this_month" | "last_month" | "this_quarter" | "last_quarter" | "this_fy" | "custom";

const PERIOD_LABELS: Record<PeriodPreset, string> = {
  all: "Programme to date",
  this_month: "This month",
  last_month: "Last month",
  this_quarter: "This quarter",
  last_quarter: "Last quarter",
  this_fy: "This financial year (Apr–Mar)",
  custom: "Custom dates",
};

function presetRange(preset: PeriodPreset, today = new Date()): { from: string; to: string } {
  const y = today.getFullYear();
  const m = today.getMonth();
  switch (preset) {
    case "this_month":
      return { from: iso(new Date(y, m, 1)), to: iso(today) };
    case "last_month":
      return { from: iso(new Date(y, m - 1, 1)), to: iso(new Date(y, m, 0)) };
    case "this_quarter": {
      const q = Math.floor(m / 3) * 3;
      return { from: iso(new Date(y, q, 1)), to: iso(today) };
    }
    case "last_quarter": {
      const q = Math.floor(m / 3) * 3 - 3;
      return { from: iso(new Date(y, q, 1)), to: iso(new Date(y, q + 3, 0)) };
    }
    case "this_fy": {
      // Government of Lesotho financial year runs 1 April to 31 March.
      const start = m >= 3 ? new Date(y, 3, 1) : new Date(y - 1, 3, 1);
      return { from: iso(start), to: iso(today) };
    }
    default:
      return { from: "", to: "" };
  }
}

const FILTER_NAMES: Record<string, string> = { period: "Period", district: "District", technology: "Technology", vendor: "Vendor", tender: "Tender", reason: "Stated reason" };

const STATUS_PILL: Record<string, string> = {
  queued: "bg-slate-100 text-slate-600",
  running: "bg-blue-100 text-blue-700",
  ready: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
};
const STATUS_LABEL: Record<string, string> = { queued: "Queued", running: "Generating", ready: "Ready", failed: "Failed" };

const APPROVAL_LABEL: Record<string, string> = {
  draft: "Draft",
  in_review: "In review",
  reviewed: "Reviewed",
  approved: "Approved",
  returned: "Returned",
};
const APPROVAL_PILL: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  in_review: "bg-amber-100 text-amber-800",
  reviewed: "bg-sky-100 text-sky-800",
  approved: "bg-emerald-100 text-emerald-800",
  returned: "bg-rose-100 text-rose-800",
};

// Who a report can be shared with. Vendors never receive programme reports.
const SHARE_ROLES = [
  UserRole.UNDP_DONOR,
  UserRole.RBF_OFFICIAL,
  UserRole.TAC,
  UserRole.DOE_OFFICER,
  UserRole.AUDITOR,
  UserRole.ADMIN,
];

// Provisional: the RBF Management Team and Super Admin review, approve and share reports.
const SIGNERS = new Set<UserRole>([UserRole.RBF_OFFICIAL, UserRole.ADMIN]);

type Dialog = { item: ReportHistoryItem; step: "review" | "approve" | "distribute" };

function StepDialog({
  dialog,
  busy,
  onClose,
  onRun,
}: {
  dialog: Dialog;
  busy: boolean;
  onClose: () => void;
  onRun: (step: ReportStep, payload: Record<string, any>) => void;
}) {
  const [notes, setNotes] = useState("");
  const [roles, setRoles] = useState<string[]>([UserRole.UNDP_DONOR]);
  const { item, step } = dialog;
  const heading = step === "review" ? "Review report" : step === "approve" ? "Approve report" : "Share report";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="card w-full max-w-lg space-y-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{heading}</h3>
            <p className="text-sm text-slate-500">{item.title}{item.version && item.version > 1 ? ` · version ${item.version}` : ""} · {item.period}</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
        </div>
        {step === "distribute" ? (
          <div className="space-y-2">
            <p className="text-sm text-slate-600">Everyone active in the chosen roles gets an in-app notice and an email with a link to sign in and download. The file itself is not emailed.</p>
            {SHARE_ROLES.map((r) => (
              <label key={r} className="flex items-center gap-2 text-sm text-slate-800">
                <input type="checkbox" checked={roles.includes(r)} onChange={(e) => setRoles((prev) => (e.target.checked ? [...prev, r] : prev.filter((x) => x !== r)))} />
                {r}
              </label>
            ))}
          </div>
        ) : (
          <>
            {item.reviewNotes && <p className="whitespace-pre-line rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">{item.reviewNotes}</p>}
            <p className="text-sm text-slate-600">Download and read the report before deciding. To return it, explain what the preparer should change.</p>
            <textarea className="input-field min-h-[96px]" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (required when returning)" />
          </>
        )}
        <div className="flex flex-wrap justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          {step === "distribute" ? (
            <button type="button" className="btn-primary inline-flex items-center gap-2" disabled={busy || roles.length === 0} onClick={() => onRun("distribute", { roles })}>
              {busy && <Loader2 size={16} className="animate-spin" />} Share
            </button>
          ) : (
            <>
              <button type="button" className="btn-secondary text-rose-700" disabled={busy || !notes.trim()} onClick={() => onRun(step, { decision: "return", notes })}>
                Return to preparer
              </button>
              <button type="button" className="btn-primary inline-flex items-center gap-2" disabled={busy} onClick={() => onRun(step, { notes })}>
                {busy && <Loader2 size={16} className="animate-spin" />} {step === "review" ? "Mark reviewed" : "Approve"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function ReportsHub({ currentUser }: { currentUser: User | { role: UserRole } }) {
  const role = currentUser.role as UserRole;
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [options, setOptions] = useState<ReportFilterOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [category, setCategory] = useState("All");
  const [preset, setPreset] = useState<PeriodPreset>("all");
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [district, setDistrict] = useState("");
  const [technology, setTechnology] = useState("");
  const [vendor, setVendor] = useState("");
  const [tender, setTender] = useState("");
  const [projectByTemplate, setProjectByTemplate] = useState<Record<string, string>>({});
  const [tenderByTemplate, setTenderByTemplate] = useState<Record<string, string>>({});
  const [reasonByTemplate, setReasonByTemplate] = useState<Record<string, string>>({});
  const [openMethod, setOpenMethod] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ReportHistoryItem[]>([]);
  const [history, setHistory] = useState<ReportHistoryItem[]>([]);
  const [historyCount, setHistoryCount] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historySearch, setHistorySearch] = useState("");
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [inbox, setInbox] = useState<{ shared: ReportHistoryItem[]; awaiting: ReportHistoryItem[] }>({ shared: [], awaiting: [] });
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [stepping, setStepping] = useState<string | null>(null);
  const myId = "id" in currentUser ? String(currentUser.id) : "";
  const signer = SIGNERS.has(role);
  const autoDownload = useRef<Set<string>>(new Set());

  const period = preset === "custom" ? custom : presetRange(preset);

  const loadHistory = useCallback(async (page = historyPage, search = historySearch) => {
    const result = await fetchReportHistory({ page, search });
    setHistory(result.results);
    setHistoryCount(result.count);
  }, [historyPage, historySearch]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tpls, opts, active] = await Promise.all([
        fetchReportTemplates(),
        fetchReportFilterOptions(),
        fetchReportHistory({ active: true }),
      ]);
      setTemplates(tpls);
      setOptions(opts);
      setJobs(active.results);
      setInbox(await fetchReportInbox().catch(() => ({ shared: [], awaiting: [] })));
      await loadHistory(1, "");
      setHistoryPage(1);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load reports."));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Follow queued and running jobs until they finish, then download the file automatically.
  const activeIds = jobs.filter((j) => j.status === "queued" || j.status === "running").map((j) => j.id).join(",");
  useEffect(() => {
    if (!activeIds) return;
    const timer = window.setInterval(async () => {
      const ids = activeIds.split(",");
      const updated = await Promise.all(ids.map((id) => fetchReportJob(id).catch(() => null)));
      setJobs((prev) => prev.map((job) => updated.find((u) => u?.id === job.id) || job));
      for (const job of updated) {
        if (!job) continue;
        if (job.status === "ready" && job.downloadUrl && autoDownload.current.has(job.id)) {
          autoDownload.current.delete(job.id);
          downloadGeneratedReport(job.downloadUrl)
            .then((blob) => saveBlob(blob, filenameFor(job.title || job.reportType, job.format)))
            .catch(() => undefined);
          setNotice(`${job.title} is ready and has been downloaded.`);
        }
        if (job.status === "failed" && autoDownload.current.has(job.id)) {
          autoDownload.current.delete(job.id);
          setError(`${job.title} could not be generated: ${job.error || "unknown error"}`);
        }
      }
      if (updated.some((u) => u && (u.status === "ready" || u.status === "failed"))) {
        void loadHistory();
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeIds, loadHistory]);

  const usedFilters = useMemo(() => new Set(templates.flatMap((t) => t.filters)), [templates]);
  const categories = useMemo(() => ["All", ...Array.from(new Set(templates.map((t) => t.category || "Reports"))).sort()], [templates]);
  const visible = useMemo(
    () => templates.filter((t) => category === "All" || (t.category || "Reports") === category).sort((a, b) => a.title.localeCompare(b.title)),
    [templates, category],
  );

  const generate = async (tpl: ReportTemplate, format: ReportFormat) => {
    const projectId = projectByTemplate[tpl.id] || "";
    if (tpl.requiresProject && !projectId) {
      setError(`Choose a project for "${tpl.title}".`);
      return;
    }
    const tenderId = tenderByTemplate[tpl.id] || tender;
    if (tpl.requiresTender && !tenderId) {
      setError(`Choose a tender for "${tpl.title}".`);
      return;
    }
    const reason = (reasonByTemplate[tpl.id] || "").trim();
    if (tpl.requiresReason && reason.length < 10) {
      setError(`State why you need the data in "${tpl.title}" (at least 10 characters). The reason is recorded in the audit log.`);
      return;
    }
    if (preset === "custom" && custom.from && custom.to && custom.from > custom.to) {
      setError("The start date is after the end date.");
      return;
    }
    const uses = new Set(tpl.filters);
    const filters: Record<string, string> = {};
    if (projectId) filters.project_id = projectId;
    if (uses.has("period")) {
      if (period.from) filters.from = period.from;
      if (period.to) filters.to = period.to;
    }
    if (uses.has("district") && district) filters.district = district;
    if (uses.has("technology") && technology) filters.technology = technology;
    if (uses.has("vendor") && vendor) filters.vendor = vendor;
    if (uses.has("tender") && tenderId) filters.tender = tenderId;
    if (uses.has("reason")) filters.reason = reason;
    setSubmitting(`${tpl.id}:${format}`);
    setError(null);
    setNotice(null);
    try {
      const job = await queueReport(tpl.id, format, filters);
      autoDownload.current.add(job.id);
      setJobs((prev) => [job, ...prev]);
    } catch (err) {
      setError(apiErrorMessage(err, `Unable to generate "${tpl.title}".`));
    } finally {
      setSubmitting(null);
    }
  };

  const download = async (item: ReportHistoryItem) => {
    if (!item.downloadUrl) return;
    try {
      saveBlob(await downloadGeneratedReport(item.downloadUrl), filenameFor(item.title || item.reportType, item.format));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to download the report."));
    }
  };

  const runStep = async (item: ReportHistoryItem, step: ReportStep, payload: Record<string, any> = {}) => {
    setStepping(item.id);
    setError(null);
    setNotice(null);
    try {
      const result: any = await runReportStep(item.id, step, payload);
      if (step === "new-version") {
        setJobs((prev) => [result, ...prev]);
        setNotice(`Version ${result.version} of ${item.title} is being generated from today's data.`);
      } else if (step === "distribute") {
        setNotice(`${item.title} was shared with ${result.recipients ?? "the chosen"} recipient${result.recipients === 1 ? "" : "s"}.`);
      } else {
        setNotice(`${item.title} is now ${(APPROVAL_LABEL[result.approvalStatus] || result.approvalStatus).toLowerCase()}.`);
      }
      setDialog(null);
      const [box] = await Promise.all([fetchReportInbox(), loadHistory()]);
      setInbox(box);
    } catch (err) {
      setError(apiErrorMessage(err, "That step could not be completed."));
    } finally {
      setStepping(null);
    }
  };

  // The sign-off and sharing controls a report offers to the current user.
  const signOff = (item: ReportHistoryItem) => {
    const approval = item.approvalStatus || "not_required";
    const mine = !!myId && item.generatedById === myId;
    const busy = stepping === item.id;
    const buttons: React.ReactNode[] = [];
    const small = "btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs";
    if (item.status === "ready") {
      if (approval === "draft" && mine) {
        buttons.push(<button key="submit" type="button" className={small} disabled={busy} onClick={() => void runStep(item, "submit")}><Send size={14} /> Submit for review</button>);
      }
      if (approval === "in_review" && signer && !mine) {
        buttons.push(<button key="review" type="button" className={small} disabled={busy} onClick={() => setDialog({ item, step: "review" })}><ShieldCheck size={14} /> Review</button>);
      }
      if (approval === "reviewed" && signer && !mine && item.reviewedById !== myId) {
        buttons.push(<button key="approve" type="button" className={small} disabled={busy} onClick={() => setDialog({ item, step: "approve" })}><ShieldCheck size={14} /> Approve</button>);
      }
      if ((approval === "not_required" || approval === "approved") && signer) {
        buttons.push(<button key="share" type="button" className={small} disabled={busy} onClick={() => setDialog({ item, step: "distribute" })}><Share2 size={14} /> Share</button>);
      }
    }
    if (approval === "returned" && mine) {
      buttons.push(<button key="redo" type="button" className={small} disabled={busy} onClick={() => void runStep(item, "new-version")}><RefreshCw size={14} /> New version</button>);
    }
    return buttons;
  };

  const approvalBadge = (item: ReportHistoryItem) => {
    const approval = item.approvalStatus || "not_required";
    if (approval === "not_required") return null;
    return (
      <div className="mt-1 space-y-0.5">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${APPROVAL_PILL[approval]}`}>
          {APPROVAL_LABEL[approval]}{item.version && item.version > 1 ? ` · v${item.version}` : ""}
        </span>
        {item.reviewedBy && <p className="text-[11px] text-slate-500">Reviewed by {item.reviewedBy}</p>}
        {item.approvedBy && <p className="text-[11px] text-slate-500">Approved by {item.approvedBy}{item.approvedAt ? `, ${new Date(item.approvedAt).toLocaleDateString("en-GB")}` : ""}</p>}
        {approval === "returned" && item.reviewNotes && <p className="max-w-xs whitespace-pre-line text-[11px] text-rose-700">{item.reviewNotes}</p>}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="mx-auto mb-2 animate-spin" />
        Loading reports...
      </div>
    );
  }

  const heading = PAGE_TITLE[role] || { title: "Reports", note: "Reports for your role, generated from live platform data." };
  const activeFilters = [district && `District: ${district}`, technology && `Technology: ${technology}`,
    vendor && `Vendor: ${options?.vendors.find((v) => v.id === vendor)?.name || vendor}`,
    tender && `Tender: ${options?.tenders.find((t) => t.id === tender)?.reference || tender}`].filter(Boolean);
  const runningJobs = jobs.filter((j) => j.status === "queued" || j.status === "running" || autoDownload.current.has(j.id));
  const pages = Math.max(1, Math.ceil(historyCount / 25));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{heading.title}</h1>
          <p className="text-sm text-slate-500">{heading.note}</p>
        </div>
        <button type="button" onClick={() => void load()} className="btn-secondary inline-flex items-center gap-2 self-start">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {notice && <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}

      {templates.length > 0 && (
        <div className="card space-y-4 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <CalendarRange size={18} className="text-emerald-600" /> Reporting period and filters
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="text-xs font-bold uppercase tracking-widest text-slate-500">Period</span>
              <select className="input-field mt-1" value={preset} onChange={(e) => setPreset(e.target.value as PeriodPreset)}>
                {(Object.keys(PERIOD_LABELS) as PeriodPreset[]).map((key) => <option key={key} value={key}>{PERIOD_LABELS[key]}</option>)}
              </select>
            </label>
            {preset === "custom" ? (
              <>
                <label className="block">
                  <span className="text-xs font-bold uppercase tracking-widest text-slate-500">From</span>
                  <input className="input-field mt-1" type="date" value={custom.from} max={custom.to || undefined} onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
                </label>
                <label className="block">
                  <span className="text-xs font-bold uppercase tracking-widest text-slate-500">To</span>
                  <input className="input-field mt-1" type="date" value={custom.to} min={custom.from || undefined} onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
                </label>
              </>
            ) : (
              <p className="self-end pb-2 text-xs text-slate-500 md:col-span-1">
                {period.from ? `${period.from} to ${period.to}` : "All activity to date"}
              </p>
            )}
            {usedFilters.has("district") && (options?.districts.length || 0) > 1 && (
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-500">District</span>
                <select className="input-field mt-1" value={district} onChange={(e) => setDistrict(e.target.value)}>
                  <option value="">All districts</option>
                  {options?.districts.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            )}
            {usedFilters.has("technology") && (options?.technologies.length || 0) > 1 && (
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-500">Technology</span>
                <select className="input-field mt-1" value={technology} onChange={(e) => setTechnology(e.target.value)}>
                  <option value="">All technologies</option>
                  {options?.technologies.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            )}
            {usedFilters.has("vendor") && (options?.vendors.length || 0) > 1 && (
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-500">Vendor</span>
                <select className="input-field mt-1" value={vendor} onChange={(e) => setVendor(e.target.value)}>
                  <option value="">All vendors</option>
                  {options?.vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </label>
            )}
            {usedFilters.has("tender") && (options?.tenders.length || 0) > 0 && (
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-500">Tender</span>
                <select className="input-field mt-1" value={tender} onChange={(e) => setTender(e.target.value)}>
                  <option value="">All tenders</option>
                  {options?.tenders.map((t) => <option key={t.id} value={t.id}>{t.reference} - {t.name}</option>)}
                </select>
              </label>
            )}
          </div>
          <p className="text-xs text-slate-500">
            {activeFilters.length ? `Applied where a report supports it: ${activeFilters.join(" · ")}.` : "Each report lists the filters it uses."}
          </p>
        </div>
      )}

      {runningJobs.length > 0 && (
        <div className="card space-y-2 p-5">
          <h3 className="text-sm font-bold text-slate-900">Reports being prepared</h3>
          {runningJobs.map((job) => (
            <div key={job.id} className="flex flex-wrap items-center gap-3 text-sm">
              {job.status === "ready" ? <CheckCircle2 size={16} className="text-emerald-600" /> : job.status === "failed" ? <XCircle size={16} className="text-rose-600" /> : <Loader2 size={16} className="animate-spin text-blue-600" />}
              <span className="font-medium text-slate-800">{job.title}</span>
              <span className="text-slate-500">{formatLabel(job.format)} · {job.period}</span>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${STATUS_PILL[job.status]}`}>{STATUS_LABEL[job.status]}</span>
              {job.status === "ready" && job.downloadUrl && (
                <button type="button" className="text-xs font-semibold text-emerald-700 hover:underline" onClick={() => void download(job)}>Download again</button>
              )}
            </div>
          ))}
        </div>
      )}

      {templates.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">No reports are available for your role yet.</div>
      ) : (
        <div className="card space-y-5 p-6">
          {categories.length > 2 && (
            <div className="flex flex-wrap gap-2">
              {categories.map((cat) => (
                <button key={cat} type="button" onClick={() => setCategory(cat)} className={cat === category ? "btn-primary text-sm" : "btn-secondary text-sm"}>
                  {cat}
                </button>
              ))}
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {visible.map((tpl) => (
              <div key={tpl.id} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-emerald-50 p-2.5"><FileText size={18} className="text-emerald-700" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-slate-900">{tpl.title}</p>
                    <p className="mt-1 text-xs text-slate-500">{tpl.description}</p>
                    <p className="mt-2 text-[11px] text-slate-500">
                      <span className="font-semibold">Uses:</span>{" "}
                      {tpl.filters.length ? tpl.filters.map((f) => FILTER_NAMES[f] || f).join(", ") : tpl.requiresProject ? "Project only" : "No filters"}
                      {tpl.requiresTender && " · one tender"}
                      {!tpl.filters.includes("period") && " · current position, not period-based"}
                    </p>
                  </div>
                  {tpl.method && (
                    <button type="button" aria-label={`How ${tpl.title} is calculated`} className="text-slate-400 hover:text-slate-600" onClick={() => setOpenMethod(openMethod === tpl.id ? null : tpl.id)}>
                      <Info size={16} />
                    </button>
                  )}
                </div>
                {openMethod === tpl.id && <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">{tpl.method}</p>}
                {tpl.requiresProject && (
                  <select
                    className="input-field"
                    value={projectByTemplate[tpl.id] || ""}
                    onChange={(e) => setProjectByTemplate((prev) => ({ ...prev, [tpl.id]: e.target.value }))}
                    aria-label={`Project for ${tpl.title}`}
                  >
                    <option value="">Choose a project *</option>
                    {options?.projects.map((p) => <option key={p.id} value={p.id}>{p.reference}{p.vendor ? ` - ${p.vendor}` : ""}</option>)}
                  </select>
                )}
                {tpl.requiresTender && (
                  <select
                    className="input-field"
                    value={tenderByTemplate[tpl.id] || tender}
                    onChange={(e) => setTenderByTemplate((prev) => ({ ...prev, [tpl.id]: e.target.value }))}
                    aria-label={`Tender for ${tpl.title}`}
                  >
                    <option value="">Choose a tender *</option>
                    {options?.tenders.map((t) => <option key={t.id} value={t.id}>{t.reference} - {t.name}</option>)}
                  </select>
                )}
                {tpl.requiresReason && (
                  <textarea
                    className="input-field min-h-[64px] text-sm"
                    value={reasonByTemplate[tpl.id] || ""}
                    onChange={(e) => setReasonByTemplate((prev) => ({ ...prev, [tpl.id]: e.target.value }))}
                    placeholder="Why do you need this personal data? *"
                    aria-label={`Reason for ${tpl.title}`}
                    maxLength={500}
                  />
                )}
                <div className="mt-auto flex flex-wrap gap-2">
                  {tpl.formats.map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => void generate(tpl, f)}
                      className="btn-secondary inline-flex items-center gap-2 text-xs"
                      disabled={submitting !== null}
                    >
                      {submitting === `${tpl.id}:${f}` ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} {formatLabel(f)}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {dialog && (
        <StepDialog
          dialog={dialog}
          busy={stepping === dialog.item.id}
          onClose={() => setDialog(null)}
          onRun={(step, payload) => void runStep(dialog.item, step, payload)}
        />
      )}

      {(inbox.awaiting.length > 0 || inbox.shared.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {inbox.awaiting.length > 0 && (
            <div className="card space-y-3 border-amber-200 p-6">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-amber-600" />
                <h3 className="text-lg font-bold text-slate-900">Awaiting your sign-off</h3>
              </div>
              <p className="text-xs text-slate-500">Formal reports someone else prepared. You cannot review your own report, or approve one you reviewed.</p>
              <ul className="divide-y divide-slate-100">
                {inbox.awaiting.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <div>
                      <p className="font-medium text-slate-900">{item.title}{item.version && item.version > 1 ? ` · v${item.version}` : ""}</p>
                      <p className="text-xs text-slate-500">{item.period} · prepared by {item.generatedBy || "—"} · {APPROVAL_LABEL[item.approvalStatus || ""] || ""}</p>
                    </div>
                    <div className="flex gap-2">
                      {item.downloadUrl && (
                        <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => void download(item)}><Download size={14} /> Read</button>
                      )}
                      {signOff(item)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {inbox.shared.length > 0 && (
            <div className="card space-y-3 p-6">
              <div className="flex items-center gap-2">
                <Inbox size={18} className="text-emerald-600" />
                <h3 className="text-lg font-bold text-slate-900">Shared with you</h3>
              </div>
              <ul className="divide-y divide-slate-100">
                {inbox.shared.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <div>
                      <p className="font-medium text-slate-900">{item.title}{item.version && item.version > 1 ? ` · v${item.version}` : ""}</p>
                      <p className="text-xs text-slate-500">
                        {item.period}{item.distributedAt ? ` · shared ${new Date(item.distributedAt).toLocaleDateString("en-GB")}` : ""}
                        {item.approvedBy ? ` · approved by ${item.approvedBy}` : ""}
                      </p>
                    </div>
                    {item.downloadUrl && (
                      <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => void download(item)}><Download size={14} /> Download</button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="card space-y-4 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Generated reports</h3>
            <p className="text-xs text-slate-500">
              {role === UserRole.ADMIN || role === UserRole.AUDITOR ? "Every generated report on the platform." : "Reports you generated."} Generation and downloads are recorded in the audit log.
            </p>
          </div>
          <form
            className="relative sm:w-72"
            onSubmit={(e) => {
              e.preventDefault();
              setHistoryPage(1);
              void loadHistory(1, historySearch);
            }}
          >
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input-field pl-9" placeholder="Search by report or person" value={historySearch} onChange={(e) => setHistorySearch(e.target.value)} />
          </form>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-widest text-slate-500">
              <tr>
                <th className="px-4 py-3">Report</th>
                <th className="px-4 py-3">Period and filters</th>
                <th className="px-4 py-3">Generated by</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {history.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No generated reports{historySearch ? " match your search" : " yet"}.</td></tr>
              ) : (
                history.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{item.title || item.reportType}</p>
                      <p className="text-xs text-slate-500">{formatLabel(item.format)}{item.rowCount ? ` · ${item.rowCount.toLocaleString()} rows` : ""}{item.project ? ` · ${item.project}` : ""}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.period}
                      {item.filters && <p className="text-xs text-slate-500">{item.filters}</p>}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{item.generatedBy || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{item.generatedAt ? new Date(item.generatedAt).toLocaleString() : "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${STATUS_PILL[item.status]}`}>{STATUS_LABEL[item.status]}</span>
                      {item.status === "failed" && item.error && <p className="mt-1 max-w-xs text-xs text-rose-700">{item.error}</p>}
                      {approvalBadge(item)}
                      {item.scheduleName && <p className="mt-1 text-[11px] text-slate-500">Scheduled: {item.scheduleName}</p>}
                      {item.distributedAt && <p className="text-[11px] text-slate-500">Shared {new Date(item.distributedAt).toLocaleDateString("en-GB")}</p>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        {item.downloadUrl && (
                          <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={() => void download(item)}>
                            <Download size={14} /> Download
                          </button>
                        )}
                        {signOff(item)}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {pages > 1 && (
          <div className="flex items-center justify-end gap-2 text-sm">
            <button type="button" className="btn-secondary text-xs" disabled={historyPage <= 1} onClick={() => { const p = historyPage - 1; setHistoryPage(p); void loadHistory(p); }}>Previous</button>
            <span className="text-slate-500">Page {historyPage} of {pages}</span>
            <button type="button" className="btn-secondary text-xs" disabled={historyPage >= pages} onClick={() => { const p = historyPage + 1; setHistoryPage(p); void loadHistory(p); }}>Next</button>
          </div>
        )}
      </div>
    </div>
  );
}
