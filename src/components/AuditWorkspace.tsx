/**
 * Independent audit workspace: audit cases and compliance reviews, their evidence, findings,
 * management responses and corrective actions, plus the system-access audit trail.
 *
 * The Auditor drives every workflow step. Cases only link to the records they examine; the
 * source records are never edited from here. RMT records the management response and
 * corrective-action progress; PSC can read cases once management has been asked to respond.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Download,
  FileText,
  History,
  Link2,
  Loader2,
  Paperclip,
  Plus,
  Search,
  ShieldCheck,
  StickyNote,
  X,
} from "lucide-react";
import {
  addAuditEvidence,
  AuditCaseStep,
  createAuditCase,
  downloadAuditCaseReport,
  exportSystemAuditLogs,
  fetchAllProjects,
  fetchAuditCaseHistory,
  fetchAuditCases,
  fetchAuditLogsForModule,
  fetchPaymentClaims,
  runAuditCaseStep,
  updateAuditCase,
} from "../api";
import {
  AuditArea,
  AuditCase,
  AuditCaseStatus,
  AuditCaseType,
  AuditEvidence,
  AuditFindingType,
  AuditLog,
  AuditRiskLevel,
  CorrectiveActionStatus,
  PaymentClaim,
  Project,
  UserRole,
} from "../types";
import { apiErrorMessage, AuditCasePrefill, ErrorCard, LoadingCard, PageHeader, StatTiles } from "./OversightShared";

const formatDate = (value?: string | null) => (value ? new Date(value).toLocaleDateString("en-GB") : "-");
const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString("en-GB") : "-");

const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

export const AUDIT_AREAS: { value: AuditArea; label: string }[] = [
  { value: "procurement", label: "Procurement" },
  { value: "vendor", label: "Vendor" },
  { value: "contract", label: "Contract" },
  { value: "verification", label: "Verification / GPS Evidence" },
  { value: "kpi", label: "KPI" },
  { value: "disbursement", label: "Disbursement" },
  { value: "system_access", label: "System Access" },
  { value: "other", label: "Other" },
];

const WORKFLOW: { status: AuditCaseStatus; label: string }[] = [
  { status: "draft", label: "Draft" },
  { status: "under_review", label: "Under Review" },
  { status: "evidence_collected", label: "Evidence Collected" },
  { status: "finding_recorded", label: "Finding Recorded" },
  { status: "management_response", label: "Management Response" },
  { status: "finalized", label: "Finalized" },
  { status: "closed", label: "Closed" },
];

const STATUS_TONE: Record<AuditCaseStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  under_review: "bg-blue-100 text-blue-700",
  evidence_collected: "bg-indigo-100 text-indigo-700",
  finding_recorded: "bg-amber-100 text-amber-700",
  management_response: "bg-violet-100 text-violet-700",
  finalized: "bg-emerald-100 text-emerald-700",
  closed: "bg-slate-200 text-slate-600",
};

const FINDING_TYPES: { value: AuditFindingType; label: string }[] = [
  { value: "compliant", label: "No exception (compliant)" },
  { value: "observation", label: "Observation" },
  { value: "exception", label: "Exception" },
  { value: "non_compliance", label: "Non-compliance" },
];

const RISK_LEVELS: { value: AuditRiskLevel; label: string; tone: string }[] = [
  { value: "observation", label: "Observation", tone: "bg-slate-100 text-slate-700" },
  { value: "minor", label: "Minor", tone: "bg-blue-100 text-blue-700" },
  { value: "major", label: "Major", tone: "bg-amber-100 text-amber-700" },
  { value: "critical", label: "Critical", tone: "bg-rose-100 text-rose-700" },
];

const CORRECTIVE_LABELS: Record<CorrectiveActionStatus, string> = {
  not_required: "Not required",
  open: "Open",
  in_progress: "In progress",
  implemented: "Implemented (awaiting auditor)",
  verified: "Verified by Auditor",
};

const riskTone = (risk: string) => RISK_LEVELS.find((r) => r.value === risk)?.tone || "bg-slate-100 text-slate-500";
const findingLabel = (value: string) => FINDING_TYPES.find((f) => f.value === value)?.label || "-";

// ---------------------------------------------------------------------------------------
// New case
// ---------------------------------------------------------------------------------------

function NewAuditCaseModal({
  prefill,
  defaultCaseType,
  onClose,
  onCreated,
}: {
  prefill?: AuditCasePrefill | null;
  defaultCaseType: AuditCaseType;
  onClose: () => void;
  onCreated: (created: AuditCase) => void;
}) {
  const [caseType, setCaseType] = useState<AuditCaseType>(prefill?.caseType || defaultCaseType);
  const [auditArea, setAuditArea] = useState<AuditArea>(prefill?.auditArea || "disbursement");
  const [title, setTitle] = useState(prefill?.title || "");
  const [scope, setScope] = useState(prefill?.scope || "");
  const [criteria, setCriteria] = useState(prefill?.criteria || "");
  const [projectId, setProjectId] = useState(prefill?.projectId || "");
  const [claimId, setClaimId] = useState(prefill?.paymentClaimId || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAllProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => {
    if (!projectId) {
      setClaims([]);
      return;
    }
    fetchPaymentClaims({ projectId }).then(setClaims).catch(() => setClaims([]));
  }, [projectId]);

  const fixedLinks = [
    prefill?.context && `Subject: ${prefill.context}`,
    prefill?.tenderId && `Tender #${prefill.tenderId}`,
    prefill?.contractId && `Contract #${prefill.contractId}`,
    prefill?.verificationTaskId && `Verification task #${prefill.verificationTaskId}`,
    prefill?.vendorId && `Vendor account #${prefill.vendorId}`,
  ].filter(Boolean) as string[];

  const submit = async () => {
    if (title.trim().length < 5) return setError("Give the case a title (at least 5 characters).");
    if (scope.trim().length < 10) return setError("Describe the scope (at least 10 characters).");
    setSaving(true);
    setError(null);
    try {
      const created = await createAuditCase({
        caseType,
        auditArea,
        title: title.trim(),
        scope: scope.trim(),
        criteria: criteria.trim(),
        projectId: projectId || undefined,
        paymentClaimId: claimId || undefined,
        tenderId: prefill?.tenderId,
        contractId: prefill?.contractId,
        verificationTaskId: prefill?.verificationTaskId,
        vendorId: prefill?.vendorId,
      });
      onCreated(created);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to open the case."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Open Audit Case</h3>
            <p className="text-sm text-slate-500">The case links to the records under audit. It never changes them.</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
        </div>
        {fixedLinks.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {fixedLinks.map((label) => (
              <span key={label} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"><Link2 size={12} /> {label}</span>
            ))}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Type *</span>
            <select className="input-field" value={caseType} onChange={(e) => setCaseType(e.target.value as AuditCaseType)}>
              <option value="audit">Audit case</option>
              <option value="compliance_review">Compliance review</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Audit area *</span>
            <select className="input-field" value={auditArea} onChange={(e) => setAuditArea(e.target.value as AuditArea)}>
              {AUDIT_AREAS.map((area) => <option key={area.value} value={area.value}>{area.label}</option>)}
            </select>
          </label>
        </div>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Title *</span>
          <input className="input-field" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Scope *</span>
          <textarea className="input-field min-h-[90px]" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="Which records, which period, what is being tested?" />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Criteria</span>
          <textarea className="input-field min-h-[60px]" value={criteria} onChange={(e) => setCriteria(e.target.value)} placeholder="Rule, SRS requirement or policy tested against" />
        </label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Project</span>
            <select className="input-field" value={projectId} onChange={(e) => { setProjectId(e.target.value); setClaimId(""); }}>
              <option value="">Not project-specific</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.projectReference || p.id} - {p.vendorName}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Payment claim</span>
            <select className="input-field" value={claimId} onChange={(e) => setClaimId(e.target.value)} disabled={!projectId}>
              <option value="">None</option>
              {claims.map((c) => <option key={c.id} value={c.id}>#{c.id} - {c.status} - LSL {Math.round(c.claimAmount).toLocaleString()}</option>)}
            </select>
          </label>
        </div>
        {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>Cancel</button>
          <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
            {saving && <Loader2 size={16} className="animate-spin" />} Open Case
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Case detail
// ---------------------------------------------------------------------------------------

function WorkflowStepper({ status }: { status: AuditCaseStatus }) {
  const index = WORKFLOW.findIndex((step) => step.status === status);
  return (
    <ol className="flex flex-wrap items-center gap-2">
      {WORKFLOW.map((step, i) => (
        <li key={step.status} className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
            i < index ? "bg-emerald-50 text-emerald-700" : i === index ? STATUS_TONE[step.status] + " ring-1 ring-current" : "bg-slate-50 text-slate-400"
          }`}>
            {i < index ? <CheckCircle2 size={12} /> : <Circle size={12} />} {step.label}
          </span>
          {i < WORKFLOW.length - 1 && <span className="text-slate-300">&rsaquo;</span>}
        </li>
      ))}
    </ol>
  );
}

function EvidenceForm({ onAdd, busy }: { onAdd: (payload: { kind: AuditEvidence["kind"]; description: string; sourceType?: string; sourceId?: string; file?: File | null }) => void; busy: boolean }) {
  const [kind, setKind] = useState<AuditEvidence["kind"]>("record");
  const [description, setDescription] = useState("");
  const [sourceType, setSourceType] = useState("PaymentClaim");
  const [sourceId, setSourceId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 p-4">
      <div className="grid gap-3 md:grid-cols-[180px_1fr]">
        <select className="input-field" value={kind} onChange={(e) => setKind(e.target.value as AuditEvidence["kind"])}>
          <option value="record">Source record</option>
          <option value="file">File</option>
          <option value="note">Working note</option>
        </select>
        <input className="input-field" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this evidence show? *" />
      </div>
      {kind === "record" && (
        <div className="grid gap-3 md:grid-cols-2">
          <select className="input-field" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            {["PaymentClaim", "Disbursement", "Project", "Milestone", "InstallationReport", "VerificationTask", "FieldVerification", "KpiReview", "Tender", "TenderBid", "TenderBidEvaluation", "TenderContract", "AuditLog", "User"].map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
          <input className="input-field" value={sourceId} onChange={(e) => setSourceId(e.target.value)} placeholder="Record ID *" />
        </div>
      )}
      {kind === "file" && (
        <input type="file" accept=".pdf,.jpg,.jpeg,.png,.csv,.xlsx,.docx" onChange={(e) => setFile(e.target.files?.[0] || null)} className="block text-sm" />
      )}
      <div className="flex justify-end">
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-2"
          disabled={busy || description.trim().length < 5 || (kind === "record" && !sourceId.trim()) || (kind === "file" && !file)}
          onClick={() => {
            onAdd({ kind, description: description.trim(), sourceType: kind === "record" ? sourceType : undefined, sourceId: kind === "record" ? sourceId.trim() : undefined, file: kind === "file" ? file : null });
            setDescription("");
            setSourceId("");
            setFile(null);
          }}
        >
          <Plus size={16} /> Add Evidence
        </button>
      </div>
    </div>
  );
}

function AuditCaseDetail({
  auditCase,
  isAuditor,
  canRespond,
  onBack,
  onChanged,
}: {
  auditCase: AuditCase;
  isAuditor: boolean;
  canRespond: boolean;
  onBack: () => void;
  onChanged: (updated: AuditCase) => void;
}) {
  const c = auditCase;
  const locked = c.status === "finalized" || c.status === "closed";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AuditLog[]>([]);
  const [editingScope, setEditingScope] = useState(false);
  const [scopeDraft, setScopeDraft] = useState({ title: c.title, scope: c.scope, criteria: c.criteria });
  const [finding, setFinding] = useState({
    findingType: c.findingType || "",
    riskLevel: c.riskLevel || "",
    finding: c.finding,
    criteria: c.criteria,
    recommendation: c.recommendation,
    correctiveAction: c.correctiveAction,
    correctiveActionOwner: c.correctiveActionOwner,
    correctiveActionDue: c.correctiveActionDue || "",
  });
  const [response, setResponse] = useState({ text: "", progress: "" });
  const [conclusion, setConclusion] = useState(c.conclusion);

  const loadHistory = useCallback(() => {
    fetchAuditCaseHistory(c.id).then(setHistory).catch(() => setHistory([]));
  }, [c.id]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory, c.updatedAt]);

  const run = async (fn: () => Promise<AuditCase>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to complete this step."));
    } finally {
      setBusy(false);
    }
  };
  const step = (name: AuditCaseStep, payload: Record<string, any> = {}) => run(() => runAuditCaseStep(c.id, name, payload));

  const linked = [
    c.projectReference && `Project ${c.projectReference}`,
    c.vendorDisplay && `Vendor ${c.vendorDisplay}`,
    c.tenderReference && `Tender ${c.tenderReference}`,
    c.contractReference && `Contract ${c.contractReference}`,
    c.paymentClaimId && `Claim #${c.paymentClaimId}${c.claimStatus ? ` (${c.claimStatus})` : ""}`,
    c.installationSerial && `Installation ${c.installationSerial}`,
  ].filter(Boolean) as string[];

  const canEditFinding = isAuditor && (c.status === "evidence_collected" || c.status === "finding_recorded");
  const needsAction = finding.findingType === "exception" || finding.findingType === "non_compliance";

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm font-semibold text-emerald-700 hover:underline">&larr; Back to cases</button>
      <div className="card space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400">{c.reference} | {c.caseType === "compliance_review" ? "Compliance review" : "Audit case"} | {c.auditAreaDisplay}</p>
            <h2 className="mt-1 text-xl font-bold text-slate-900">{c.title}</h2>
            <p className="text-sm text-slate-500">Auditor {c.auditorName || "-"} | opened {formatDate(c.createdAt)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {c.riskLevel && <span className={`rounded-full px-3 py-1 text-xs font-bold ${riskTone(c.riskLevel)}`}>{RISK_LEVELS.find((r) => r.value === c.riskLevel)?.label} risk</span>}
            <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void downloadAuditCaseReport(c.id).then((blob) => saveBlob(blob, `${c.reference}.pdf`)).catch((err) => setError(apiErrorMessage(err, "Unable to generate the report.")))}>
              <Download size={16} /> Audit Report (PDF)
            </button>
          </div>
        </div>
        <WorkflowStepper status={c.status} />
        {linked.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {linked.map((label) => <span key={label} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"><Link2 size={12} /> {label}</span>)}
          </div>
        )}
        {editingScope ? (
          <div className="space-y-3">
            <input className="input-field" value={scopeDraft.title} onChange={(e) => setScopeDraft({ ...scopeDraft, title: e.target.value })} />
            <textarea className="input-field min-h-[80px]" value={scopeDraft.scope} onChange={(e) => setScopeDraft({ ...scopeDraft, scope: e.target.value })} />
            <textarea className="input-field min-h-[60px]" value={scopeDraft.criteria} onChange={(e) => setScopeDraft({ ...scopeDraft, criteria: e.target.value })} placeholder="Criteria" />
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setEditingScope(false)}>Cancel</button>
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void run(() => updateAuditCase(c.id, scopeDraft)).then(() => setEditingScope(false))}>Save</button>
            </div>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <p className="whitespace-pre-wrap text-slate-700"><span className="font-semibold text-slate-900">Scope:</span> {c.scope}</p>
            {c.criteria && <p className="whitespace-pre-wrap text-slate-700"><span className="font-semibold text-slate-900">Criteria:</span> {c.criteria}</p>}
            {isAuditor && !locked && <button type="button" className="text-xs font-semibold text-emerald-700 hover:underline" onClick={() => setEditingScope(true)}>Edit scope</button>}
          </div>
        )}
        {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        {isAuditor && (
          <div className="flex flex-wrap gap-2">
            {c.status === "draft" && <button type="button" className="btn-primary" disabled={busy} onClick={() => void step("start_review")}>Start Review</button>}
            {c.status === "under_review" && <button type="button" className="btn-primary" disabled={busy || c.evidence.length === 0} onClick={() => void step("evidence_collected")}>Mark Evidence Collected</button>}
            {c.status === "finding_recorded" && c.findingType !== "compliant" && (
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void step("request_response")}>Request Management Response</button>
            )}
            {c.status === "finalized" && c.correctiveActionStatus === "implemented" && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void step("corrective_action_progress", { corrective_action_status: "verified" })}>Verify Corrective Action</button>
            )}
            {c.status === "finalized" && (
              <button type="button" className="btn-primary" disabled={busy || !["not_required", "verified"].includes(c.correctiveActionStatus)} onClick={() => void step("close")}>Close Case</button>
            )}
          </div>
        )}
      </div>

      {/* Evidence */}
      <div className="card space-y-4 p-6">
        <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><Paperclip size={18} /> Evidence ({c.evidence.length})</h3>
        <p className="text-xs text-slate-500">Evidence is append-only. It references source records by ID and never alters them.</p>
        {c.evidence.length === 0 ? <p className="text-sm text-slate-500">No evidence yet.</p> : (
          <ul className="divide-y divide-slate-100">
            {c.evidence.map((item) => (
              <li key={item.id} className="flex flex-wrap items-start gap-3 py-3 text-sm">
                {item.kind === "file" ? <FileText size={16} className="mt-0.5 text-slate-400" /> : item.kind === "record" ? <Link2 size={16} className="mt-0.5 text-slate-400" /> : <StickyNote size={16} className="mt-0.5 text-slate-400" />}
                <div className="flex-1">
                  <p className="text-slate-800">{item.description}</p>
                  <p className="text-xs text-slate-500">
                    {item.kind === "record" && `${item.sourceType} #${item.sourceId} | `}
                    {item.addedByName} | {formatDateTime(item.addedAt)}
                  </p>
                </div>
                {item.fileUrl && <a href={item.fileUrl} target="_blank" rel="noreferrer" className="text-xs font-semibold text-emerald-700 hover:underline">Open file</a>}
              </li>
            ))}
          </ul>
        )}
        {isAuditor && !locked && c.status !== "draft" && (
          <EvidenceForm busy={busy} onAdd={(payload) => void run(() => addAuditEvidence(c.id, payload))} />
        )}
      </div>

      {/* Finding */}
      <div className="card space-y-4 p-6">
        <h3 className="text-lg font-bold text-slate-900">Finding</h3>
        {canEditFinding ? (
          <div className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <select className="input-field" value={finding.findingType} onChange={(e) => setFinding({ ...finding, findingType: e.target.value as AuditFindingType })}>
                <option value="">Finding type *</option>
                {FINDING_TYPES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
              <select className="input-field" value={finding.riskLevel} onChange={(e) => setFinding({ ...finding, riskLevel: e.target.value as AuditRiskLevel })}>
                <option value="">Risk level *</option>
                {RISK_LEVELS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <textarea className="input-field min-h-[100px]" value={finding.finding} onChange={(e) => setFinding({ ...finding, finding: e.target.value })} placeholder="Condition found, with reference to the evidence *" />
            <textarea className="input-field min-h-[60px]" value={finding.recommendation} onChange={(e) => setFinding({ ...finding, recommendation: e.target.value })} placeholder="Recommendation" />
            {(needsAction || finding.correctiveAction) && (
              <div className="grid gap-3 md:grid-cols-[1fr_200px_180px]">
                <input className="input-field" value={finding.correctiveAction} onChange={(e) => setFinding({ ...finding, correctiveAction: e.target.value })} placeholder={`Corrective action${needsAction ? " *" : ""}`} />
                <input className="input-field" value={finding.correctiveActionOwner} onChange={(e) => setFinding({ ...finding, correctiveActionOwner: e.target.value })} placeholder="Owner" />
                <input type="date" className="input-field" value={finding.correctiveActionDue} onChange={(e) => setFinding({ ...finding, correctiveActionDue: e.target.value })} />
              </div>
            )}
            <div className="flex justify-end">
              <button
                type="button"
                className="btn-primary"
                disabled={busy}
                onClick={() => void step("record_finding", {
                  finding_type: finding.findingType,
                  risk_level: finding.riskLevel,
                  finding: finding.finding,
                  recommendation: finding.recommendation,
                  corrective_action: finding.correctiveAction,
                  corrective_action_owner: finding.correctiveActionOwner,
                  corrective_action_due: finding.correctiveActionDue || null,
                })}
              >
                {c.status === "finding_recorded" ? "Update Finding" : "Record Finding"}
              </button>
            </div>
          </div>
        ) : c.findingType ? (
          <dl className="grid gap-3 text-sm md:grid-cols-2">
            <div><dt className="text-xs text-slate-500">Finding type</dt><dd className="font-semibold text-slate-900">{findingLabel(c.findingType)}</dd></div>
            <div><dt className="text-xs text-slate-500">Recorded</dt><dd className="text-slate-900">{formatDateTime(c.findingRecordedAt)}</dd></div>
            <div className="md:col-span-2"><dt className="text-xs text-slate-500">Finding</dt><dd className="whitespace-pre-wrap text-slate-800">{c.finding}</dd></div>
            {c.recommendation && <div className="md:col-span-2"><dt className="text-xs text-slate-500">Recommendation</dt><dd className="whitespace-pre-wrap text-slate-800">{c.recommendation}</dd></div>}
          </dl>
        ) : (
          <p className="text-sm text-slate-500">No finding recorded yet. Findings are recorded after evidence is collected.</p>
        )}
      </div>

      {/* Management response and corrective action */}
      {(c.correctiveActionStatus !== "not_required" || c.status === "management_response" || c.managementResponse) && (
        <div className="card space-y-4 p-6">
          <h3 className="text-lg font-bold text-slate-900">Management Response &amp; Corrective Action</h3>
          {c.correctiveAction && (
            <p className="text-sm text-slate-700">
              <span className="font-semibold">Corrective action:</span> {c.correctiveAction}
              {c.correctiveActionOwner && ` | owner ${c.correctiveActionOwner}`}
              {c.correctiveActionDue && ` | due ${formatDate(c.correctiveActionDue)}`}
            </p>
          )}
          <p className="text-sm"><span className="font-semibold text-slate-900">Status:</span> {CORRECTIVE_LABELS[c.correctiveActionStatus]}</p>
          {c.managementResponse ? (
            <p className="whitespace-pre-wrap rounded-xl bg-violet-50 px-3 py-2 text-sm text-violet-900">
              {c.managementResponse}
              <span className="mt-1 block text-xs text-violet-700">{c.respondedByName} | {formatDateTime(c.respondedAt)}</span>
            </p>
          ) : c.status === "management_response" && <p className="text-sm text-slate-500">Awaiting the RBF Management Team's response.</p>}
          {canRespond && c.status === "management_response" && (
            <div className="space-y-3 rounded-xl border border-slate-200 p-4">
              <textarea className="input-field min-h-[90px]" value={response.text} onChange={(e) => setResponse({ ...response, text: e.target.value })} placeholder="Management response *" />
              {c.correctiveActionStatus !== "not_required" && (
                <select className="input-field md:w-64" value={response.progress} onChange={(e) => setResponse({ ...response, progress: e.target.value })}>
                  <option value="">Corrective action progress (unchanged)</option>
                  <option value="in_progress">In progress</option>
                  <option value="implemented">Implemented</option>
                </select>
              )}
              <div className="flex justify-end">
                <button type="button" className="btn-primary" disabled={busy || response.text.trim().length < 10}
                  onClick={() => void step("respond", { management_response: response.text.trim(), corrective_action_status: response.progress || undefined })}>
                  {c.managementResponse ? "Update Response" : "Submit Response"}
                </button>
              </div>
            </div>
          )}
          {canRespond && c.status === "finalized" && ["open", "in_progress"].includes(c.correctiveActionStatus) && (
            <div className="flex flex-wrap gap-2">
              {c.correctiveActionStatus === "open" && <button type="button" className="btn-secondary" disabled={busy} onClick={() => void step("corrective_action_progress", { corrective_action_status: "in_progress" })}>Mark In Progress</button>}
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void step("corrective_action_progress", { corrective_action_status: "implemented" })}>Mark Implemented</button>
            </div>
          )}
        </div>
      )}

      {/* Conclusion */}
      <div className="card space-y-3 p-6">
        <h3 className="text-lg font-bold text-slate-900">Audit Conclusion</h3>
        {isAuditor && (c.status === "management_response" || (c.status === "finding_recorded" && c.findingType === "compliant")) ? (
          <>
            <textarea className="input-field min-h-[80px]" value={conclusion} onChange={(e) => setConclusion(e.target.value)} placeholder="Overall conclusion *" />
            {c.status === "management_response" && !c.respondedAt && <p className="text-xs text-amber-700">Finalizing is available once management has responded.</p>}
            <div className="flex justify-end">
              <button type="button" className="btn-primary" disabled={busy || conclusion.trim().length < 10 || (c.status === "management_response" && !c.respondedAt)}
                onClick={() => void step("finalize", { conclusion: conclusion.trim() })}>
                Finalize Audit
              </button>
            </div>
          </>
        ) : (
          <p className="whitespace-pre-wrap text-sm text-slate-700">{c.conclusion || "Not yet finalized."}</p>
        )}
        {c.finalizedAt && <p className="text-xs text-slate-500">Finalized {formatDateTime(c.finalizedAt)}{c.closedAt ? ` | closed ${formatDateTime(c.closedAt)}` : ""}</p>}
      </div>

      {/* Trail */}
      <div className="card space-y-3 p-6">
        <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><History size={18} /> Case Trail</h3>
        {history.length === 0 ? <p className="text-sm text-slate-500">No activity yet.</p> : (
          <ul className="space-y-2 text-sm">
            {history.map((log) => (
              <li key={log.id} className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
                <span className="font-semibold text-slate-900">{log.action.replace(/_/g, " ")}</span>
                {log.oldStatus && log.newStatus && <span className="text-slate-500">{log.oldStatus} &rarr; {log.newStatus}</span>}
                <span className="ml-auto text-xs text-slate-400">{log.actorFullName || log.actorUsername || "System"} ({log.actorRole}) | {formatDateTime(log.createdAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Case list (with presets for the Audit / Compliance / Reports sidebar entries)
// ---------------------------------------------------------------------------------------

export type AuditCasePreset = "all" | "compliance" | "exceptions" | "corrective" | "reports" | "evidence" | "responses";

const PRESET_META: Record<AuditCasePreset, { title: string; description: string }> = {
  all: { title: "Audit Cases", description: "Independent audit cases. Open a case, collect evidence, record the finding and follow it to closure." },
  compliance: { title: "Compliance Reviews", description: "Compliance reviews of processes and records against the SRS and programme rules." },
  exceptions: { title: "Exceptions", description: "Findings recorded as exceptions or non-compliance." },
  corrective: { title: "Corrective Actions", description: "Corrective actions agreed with management, and their progress." },
  reports: { title: "Audit Reports", description: "Finalized and closed audits. Download the audit report for each case." },
  evidence: { title: "Evidence Reports", description: "Register of all evidence collected across audit cases." },
  responses: { title: "Audit Findings", description: "Findings on which the Auditor has requested a management response, and their corrective actions." },
};

export function AuditCasesView({
  currentUser,
  preset = "all",
  prefill,
  onPrefillConsumed,
}: {
  currentUser: any;
  preset?: AuditCasePreset;
  prefill?: AuditCasePrefill | null;
  onPrefillConsumed?: () => void;
}) {
  const isAuditor = currentUser?.role === UserRole.AUDITOR;
  const canRespond = currentUser?.role === UserRole.RBF_OFFICIAL || currentUser?.role === UserRole.ADMIN;
  const [cases, setCases] = useState<AuditCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [status, setStatus] = useState("");
  const [area, setArea] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCases(await fetchAuditCases(preset === "compliance" ? { case_type: "compliance_review" } : {}));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load audit cases."));
    } finally {
      setLoading(false);
    }
  }, [preset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (prefill && isAuditor) setShowNew(true);
  }, [prefill, isAuditor]);

  const presetCases = useMemo(() => cases.filter((c) => {
    if (preset === "exceptions") return c.findingType === "exception" || c.findingType === "non_compliance";
    if (preset === "corrective") return c.correctiveActionStatus !== "not_required";
    if (preset === "reports") return c.status === "finalized" || c.status === "closed";
    return true;
  }), [cases, preset]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return presetCases.filter((c) => (!status || c.status === status) && (!area || c.auditArea === area) &&
      (!term || `${c.reference} ${c.title} ${c.projectReference} ${c.vendorDisplay}`.toLowerCase().includes(term)));
  }, [presetCases, status, area, search]);

  if (loading) return <LoadingCard label="Loading audit cases..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const replace = (updated: AuditCase) => setCases((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  const selected = selectedId ? cases.find((c) => c.id === selectedId) : null;
  if (selected) {
    return <AuditCaseDetail auditCase={selected} isAuditor={isAuditor} canRespond={canRespond} onBack={() => setSelectedId(null)} onChanged={replace} />;
  }

  const meta = PRESET_META[preset];
  const newModal = showNew && (
    <NewAuditCaseModal
      prefill={prefill}
      defaultCaseType={preset === "compliance" ? "compliance_review" : "audit"}
      onClose={() => {
        setShowNew(false);
        onPrefillConsumed?.();
      }}
      onCreated={(created) => {
        setCases((prev) => [created, ...prev]);
        setShowNew(false);
        onPrefillConsumed?.();
        setSelectedId(created.id);
      }}
    />
  );

  if (preset === "evidence") {
    const rows = presetCases.flatMap((c) => c.evidence.map((item) => ({ c, item })))
      .filter(({ c, item }) => !search.trim() || `${c.reference} ${item.description} ${item.sourceType} ${item.sourceId}`.toLowerCase().includes(search.trim().toLowerCase()))
      .sort((a, b) => b.item.addedAt.localeCompare(a.item.addedAt));
    return (
      <div className="space-y-6">
        <PageHeader title={meta.title} description={meta.description} onRefresh={() => void load()} />
        <div className="relative md:w-96">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search evidence..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Case</th>
                <th className="px-4 py-3 text-left font-semibold">Kind</th>
                <th className="px-4 py-3 text-left font-semibold">Description</th>
                <th className="px-4 py-3 text-left font-semibold">Source</th>
                <th className="px-4 py-3 text-left font-semibold">Added</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ c, item }) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="px-4 py-3"><button type="button" className="font-semibold text-emerald-700 hover:underline" onClick={() => setSelectedId(c.id)}>{c.reference}</button></td>
                  <td className="px-4 py-3 capitalize text-slate-700">{item.kind}</td>
                  <td className="px-4 py-3 text-slate-700">{item.description}</td>
                  <td className="px-4 py-3 text-slate-700">
                    {item.kind === "record" ? `${item.sourceType} #${item.sourceId}` : item.fileUrl ? <a href={item.fileUrl} target="_blank" rel="noreferrer" className="text-emerald-700 hover:underline">File</a> : "-"}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{item.addedByName} | {formatDate(item.addedAt)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">No evidence recorded.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={meta.title} description={meta.description} onRefresh={() => void load()}>
        {isAuditor && (preset === "all" || preset === "compliance") && (
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setShowNew(true)}>
            <Plus size={16} /> {preset === "compliance" ? "New Compliance Review" : "Open Audit Case"}
          </button>
        )}
      </PageHeader>
      <StatTiles tiles={[
        { label: "Cases", value: presetCases.length },
        { label: "In progress", value: presetCases.filter((c) => !["finalized", "closed"].includes(c.status)).length, tone: "text-blue-700" },
        { label: "Awaiting management", value: presetCases.filter((c) => c.status === "management_response" && !c.respondedAt).length, tone: "text-violet-700" },
        { label: "Major / critical", value: presetCases.filter((c) => c.riskLevel === "major" || c.riskLevel === "critical").length, tone: "text-rose-700" },
      ]} />
      <div className="card flex flex-col gap-3 p-4 md:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search reference, title, project..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input-field md:w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {WORKFLOW.map((s) => <option key={s.status} value={s.status}>{s.label}</option>)}
        </select>
        <select className="input-field md:w-56" value={area} onChange={(e) => setArea(e.target.value)}>
          <option value="">All areas</option>
          {AUDIT_AREAS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Reference</th>
              <th className="px-4 py-3 text-left font-semibold">Title</th>
              <th className="px-4 py-3 text-left font-semibold">Area</th>
              <th className="px-4 py-3 text-left font-semibold">Status</th>
              <th className="px-4 py-3 text-left font-semibold">Finding</th>
              <th className="px-4 py-3 text-left font-semibold">Corrective action</th>
              <th className="px-4 py-3 text-left font-semibold">Updated</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-4 py-3 font-medium text-slate-900">{c.reference}</td>
                <td className="px-4 py-3 text-slate-700">{c.title}<div className="text-xs text-slate-500">{[c.projectReference, c.vendorDisplay].filter(Boolean).join(" | ")}</div></td>
                <td className="px-4 py-3 text-slate-700">{c.auditAreaDisplay}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_TONE[c.status]}`}>{c.statusDisplay}</span></td>
                <td className="px-4 py-3">
                  {c.findingType ? <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${riskTone(c.riskLevel)}`}>{findingLabel(c.findingType)}</span> : <span className="text-slate-400">-</span>}
                </td>
                <td className="px-4 py-3 text-slate-700">{CORRECTIVE_LABELS[c.correctiveActionStatus]}{c.correctiveActionDue && <div className="text-xs text-slate-500">due {formatDate(c.correctiveActionDue)}</div>}</td>
                <td className="px-4 py-3 text-slate-700">{formatDate(c.updatedAt)}</td>
                <td className="px-4 py-3 text-right">
                  <div className="flex justify-end gap-2">
                    {preset === "reports" && (
                      <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => void downloadAuditCaseReport(c.id).then((blob) => saveBlob(blob, `${c.reference}.pdf`)).catch(() => undefined)}>
                        <Download size={14} /> PDF
                      </button>
                    )}
                    <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setSelectedId(c.id)}>
                      <ShieldCheck size={14} /> Open
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500">No cases.</td></tr>}
          </tbody>
        </table>
      </div>
      {newModal}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// System access audit (logins, failed sign-ins, user and role-permission changes)
// ---------------------------------------------------------------------------------------

export function SystemAccessAuditView() {
  const defaultFrom = () => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  };
  const [dateFrom, setDateFrom] = useState(defaultFrom());
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<"" | "logins" | "failed" | "users">("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [access, users] = await Promise.all([fetchAuditLogsForModule("system_access", dateFrom), fetchAuditLogsForModule("users", dateFrom)]);
      setLogs([...access, ...users].sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load the access log."));
    } finally {
      setLoading(false);
    }
  }, [dateFrom]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return logs.filter((log) => {
      if (kind === "logins" && log.action !== "login_succeeded") return false;
      if (kind === "failed" && log.action !== "login_failed") return false;
      if (kind === "users" && log.module !== "users") return false;
      return !term || `${log.action} ${log.actorUsername} ${log.actorFullName} ${log.notes} ${log.details?.identifier || ""}`.toLowerCase().includes(term);
    });
  }, [logs, kind, search]);

  if (loading) return <LoadingCard label="Loading access log..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  const failedByIdentifier = logs.filter((l) => l.action === "login_failed").reduce<Record<string, number>>((acc, l) => {
    const key = String(l.details?.identifier || "unknown");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const repeated = (Object.entries(failedByIdentifier) as [string, number][]).filter(([, n]) => n >= 5).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6">
      <PageHeader title="System Access Audit" description="Sign-ins, failed sign-in attempts, user account changes and role-permission changes. Read-only." onRefresh={() => void load()}>
        <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => void exportSystemAuditLogs("csv", { module: "system_access", dateFrom }).then((blob) => saveBlob(blob, "system_access_audit.csv"))}>
          <Download size={16} /> Export CSV
        </button>
      </PageHeader>
      <StatTiles tiles={[
        { label: "Successful sign-ins", value: logs.filter((l) => l.action === "login_succeeded").length, tone: "text-emerald-700" },
        { label: "Failed sign-ins", value: logs.filter((l) => l.action === "login_failed").length, tone: "text-rose-700" },
        { label: "User account changes", value: logs.filter((l) => l.module === "users" && l.action !== "Updated role permissions").length },
        { label: "Permission changes", value: logs.filter((l) => l.action === "Updated role permissions").length, tone: "text-amber-700" },
      ]} />
      {repeated.length > 0 && (
        <div className="card border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <p className="font-semibold">Repeated failed sign-ins (5 or more):</p>
          <p>{repeated.map(([who, n]) => `${who} (${n})`).join(", ")}</p>
        </div>
      )}
      <div className="card flex flex-col gap-3 p-4 md:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-field pl-9" placeholder="Search user, action, notes..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input-field md:w-56" value={kind} onChange={(e) => setKind(e.target.value as any)}>
          <option value="">All access events</option>
          <option value="logins">Successful sign-ins</option>
          <option value="failed">Failed sign-ins</option>
          <option value="users">User &amp; permission changes</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          From <input type="date" className="input-field" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">When</th>
              <th className="px-4 py-3 text-left font-semibold">Event</th>
              <th className="px-4 py-3 text-left font-semibold">User</th>
              <th className="px-4 py-3 text-left font-semibold">Role</th>
              <th className="px-4 py-3 text-left font-semibold">Details</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((log) => (
              <tr key={log.id} className="border-t border-slate-100">
                <td className="whitespace-nowrap px-4 py-3 text-slate-700">{formatDateTime(log.createdAt)}</td>
                <td className={`px-4 py-3 font-semibold ${log.action === "login_failed" ? "text-rose-700" : "text-slate-900"}`}>{log.action.replace(/_/g, " ")}</td>
                <td className="px-4 py-3 text-slate-700">{log.actorFullName || log.actorUsername || log.details?.identifier || "-"}</td>
                <td className="px-4 py-3 text-slate-700">{log.actorRole || "-"}</td>
                <td className="px-4 py-3 text-slate-600">{log.notes || [log.oldStatus, log.newStatus].filter(Boolean).join(" -> ") || "-"}</td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">No access events in this period.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
