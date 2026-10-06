/**
 * The archive of a completed project: its whole lifecycle from tender creation to completion
 * and contract closure, as recorded when the project was archived. Read-only for everyone;
 * only the Super Admin can restore the project for corrections.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Download, Loader2, Lock, RotateCcw } from "lucide-react";
import { downloadProjectArchiveDossier, fetchProjectArchive, restoreArchivedProject } from "../api";
import { Project, ProjectArchiveRecord, UserRole } from "../types";
import { apiErrorMessage } from "./OversightShared";

const PHASE_TONE: Record<string, string> = {
  Procurement: "bg-sky-100 text-sky-700",
  Award: "bg-violet-100 text-violet-700",
  Contract: "bg-indigo-100 text-indigo-700",
  Delivery: "bg-emerald-100 text-emerald-700",
  Payment: "bg-amber-100 text-amber-700",
  Completion: "bg-slate-800 text-white",
};

const when = (value?: string | null) => (value ? new Date(value).toLocaleString("en-GB") : "-");
const day = (value?: string | null) => (value ? new Date(value).toLocaleDateString("en-GB") : "-");
const money = (value?: number | null) => (value != null ? `LSL ${Number(value).toLocaleString()}` : "-");

const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

/** Banner shown at the top of an archived project. */
export function ArchivedProjectBanner({ project }: { project: Project }) {
  if (!project.archivedAt) return null;
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-slate-300 bg-slate-100 px-4 py-3 text-sm text-slate-700">
      <Lock size={18} className="mt-0.5 shrink-0 text-slate-500" />
      <div>
        <p className="font-semibold text-slate-900">Completed and archived on {day(project.archivedAt)}</p>
        <p>This project, its contract and every record from tender creation to completion are read-only. See the Lifecycle Archive tab for the full record.</p>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-bold uppercase tracking-widest text-slate-500">{title}</h4>
      {children}
    </div>
  );
}

function SimpleTable({ headers, rows, empty = "None recorded." }: { headers: string[]; rows: React.ReactNode[][]; empty?: string }) {
  if (rows.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>{headers.map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-slate-100">
              {row.map((cell, j) => <td key={j} className="px-3 py-2 align-top text-slate-700">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProjectLifecycleArchive({
  project,
  currentUser,
  onRestored,
}: {
  project: Project;
  currentUser: any;
  onRestored?: (project: Project) => void;
}) {
  const [records, setRecords] = useState<ProjectArchiveRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState("");
  const [restoreReason, setRestoreReason] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser?.role === UserRole.ADMIN;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchProjectArchive(project.id);
      setRecords(rows);
      setSelectedId(rows[0]?.id ?? null);
    } catch (err) {
      setError(apiErrorMessage(err, "This project has no archive record yet."));
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const record = records.find((r) => r.id === selectedId) || records[0];
  const timeline = useMemo(() => (record?.timeline || []).filter((e) => !phase || e.phase === phase), [record, phase]);

  if (loading) {
    return <div className="card p-8 text-center text-slate-500"><Loader2 size={20} className="mx-auto mb-2 animate-spin" />Loading the lifecycle archive...</div>;
  }
  if (error || !record) {
    return <div className="card p-8 text-center text-slate-500">{error || "This project has no archive record yet."}</div>;
  }

  const snap = record.snapshot || {};
  const tender = snap.tender || {};
  const contract = snap.contract || {};
  const phases = Array.from(new Set((record.timeline || []).map((e) => e.phase)));

  return (
    <div className="space-y-6">
      <div className="card space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400"><Archive size={14} /> Lifecycle archive</p>
            <h3 className="mt-1 text-lg font-bold text-slate-900">
              Tender {record.tenderReference || "-"} to contract {record.contractReference || "-"} closure
            </h3>
            <p className="text-sm text-slate-500">
              {day(record.lifecycleStartedAt)} (tender created) to {day(record.lifecycleEndedAt)} (completed). Archived {when(record.archivedAt)}
              {record.archivedBy ? ` by ${record.archivedBy}` : ""}. {record.reason}
            </p>
            {record.supersededAt && <p className="mt-1 text-xs font-semibold text-amber-700">Superseded on {when(record.supersededAt)}: the project was restored for correction.</p>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {records.length > 1 && (
              <select className="input-field" value={record.id} onChange={(e) => setSelectedId(e.target.value)}>
                {records.map((r) => <option key={r.id} value={r.id}>Archived {day(r.archivedAt)}{r.supersededAt ? " (superseded)" : ""}</option>)}
              </select>
            )}
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-2"
              onClick={() => void downloadProjectArchiveDossier(project.id, record.id)
                .then((blob) => saveBlob(blob, `${project.projectReference || project.id}_lifecycle_archive.pdf`))
                .catch((err) => setError(apiErrorMessage(err, "The dossier could not be generated.")))}
            >
              <Download size={16} /> Archive Dossier (PDF)
            </button>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Tender", `${tender.reference || "-"}`, tender.name],
            ["Bids received", String((snap.bids || []).length), `${(snap.evaluations || []).length} evaluation score(s)`],
            ["Contract", contract.reference || "-", contract.closed_at ? `Closed ${day(contract.closed_at)}` : contract.status],
            ["Paid", money((snap.payment_claims || []).filter((c: any) => c.paid_at).reduce((sum: number, c: any) => sum + (c.amount || 0), 0)),
              `${(snap.payment_claims || []).length} claim(s), ${snap.installations?.total ?? 0} installation(s)`],
          ].map(([label, value, sub]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{label}</p>
              <p className="text-sm font-bold text-slate-900">{value}</p>
              <p className="truncate text-xs text-slate-500" title={sub || ""}>{sub}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-bold text-slate-900">Lifecycle timeline</h3>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setPhase("")} className={`rounded-full px-3 py-1 text-xs font-bold ${!phase ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>All</button>
            {phases.map((p) => (
              <button key={p} type="button" onClick={() => setPhase(p)} className={`rounded-full px-3 py-1 text-xs font-bold ${phase === p ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>{p}</button>
            ))}
          </div>
        </div>
        <ol className="relative space-y-3 border-l border-slate-200 pl-5">
          {timeline.map((event, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[27px] top-1.5 h-3 w-3 rounded-full border-2 border-white bg-slate-400" />
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${PHASE_TONE[event.phase] || "bg-slate-100 text-slate-600"}`}>{event.phase}</span>
                <span className="text-sm font-semibold text-slate-900">{event.title}</span>
                <span className="text-xs text-slate-400">{when(event.at)}{event.actor ? ` | ${event.actor}` : ""}</span>
              </div>
              {event.detail && <p className="text-xs text-slate-600">{event.detail}</p>}
            </li>
          ))}
        </ol>
      </div>

      <div className="card space-y-6 p-6">
        <h3 className="text-lg font-bold text-slate-900">Archived records</h3>
        <Section title="Bids">
          <SimpleTable headers={["Vendor", "Stage", "Status", "Amount", "Submitted", "Rejection reason"]}
            rows={(snap.bids || []).map((b: any) => [b.vendor_name, b.stage, b.status, money(b.bid_amount), day(b.submitted_at), b.rejection_reason || "-"])} />
        </Section>
        <Section title="Evaluation scores">
          <SimpleTable headers={["Bidder", "Stage", "Evaluator", "Technical", "Financial", "Total"]}
            rows={(snap.evaluations || []).map((v: any) => [v.vendor_name, v.stage, v.evaluator, v.technical_score, v.financial_score, v.total_score])} />
        </Section>
        <Section title="Intent to award and challenges">
          <SimpleTable headers={["Proposed vendor", "Status", "Requested by", "Reviewed by", "Reviewed"]}
            rows={(snap.intent_to_award_requests || []).map((r: any) => [r.proposed_vendor_name, r.status, r.requested_by, r.reviewed_by || "-", day(r.reviewed_at)])} />
          <SimpleTable headers={["Filed by", "Category", "Status", "Filed", "Resolved"]} empty="No challenges filed."
            rows={(snap.challenges || []).map((c: any) => [c.filed_by, c.category, c.status, day(c.filed_at), day(c.resolved_at)])} />
        </Section>
        <Section title="Milestones">
          <SimpleTable headers={["#", "Milestone", "Share", "Amount", "Status", "Completed"]}
            rows={(snap.milestones || []).map((m: any) => [m.number, m.name, `${m.disbursement_pct}%`, money(m.amount), m.status, m.completed_date || "-"])} />
        </Section>
        <Section title="Payment claims and disbursements">
          <SimpleTable headers={["Claim", "Milestone", "Amount", "Status", "Approved", "Paid", "Reference"]}
            rows={(snap.payment_claims || []).map((c: any) => [`#${c.id}`, c.milestone ?? "-", money(c.amount), c.status, day(c.approved_at), day(c.paid_at), c.payment_reference || "-"])} />
        </Section>
        <Section title="Delivery and oversight">
          <SimpleTable headers={["Installations", "Verification visits", "Re-verified", "GPS mismatches", "Meter readings", "Anomalies (open)", "Oversight reviews", "Audit cases"]}
            rows={[[
              snap.installations?.total ?? 0,
              snap.field_verification?.visits ?? 0,
              snap.field_verification?.reverified_installations ?? 0,
              snap.field_verification?.location_mismatches ?? 0,
              snap.meter_data?.readings ?? 0,
              `${snap.anomalies?.total ?? 0} (${snap.anomalies?.unresolved ?? 0})`,
              snap.oversight_reviews?.total ?? 0,
              (snap.audit_cases || []).map((a: any) => a.reference).join(", ") || "None",
            ]]} />
        </Section>
        <Section title={`Audit trail (${(snap.audit_trail || []).length} entries)`}>
          <SimpleTable headers={["When", "Action", "Record", "By"]}
            rows={(snap.audit_trail || []).slice(-200).reverse().map((a: any) => [when(a.at), a.action, a.entity, `${a.actor}${a.role ? ` (${a.role})` : ""}`])} />
        </Section>
      </div>

      {isAdmin && project.archivedAt && (
        <div className="card space-y-3 border-amber-200 p-6">
          <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><RotateCcw size={18} /> Restore for correction</h3>
          <p className="text-sm text-slate-600">Restoring reopens the project and its contract for editing. This archive record is kept as superseded, and a new one is written when the project is archived again.</p>
          <textarea className="input-field min-h-[70px]" value={restoreReason} onChange={(e) => setRestoreReason(e.target.value)} placeholder="Why does this project need to be reopened? *" />
          <div className="flex justify-end">
            <button
              type="button"
              className="btn-primary"
              disabled={busy || restoreReason.trim().length < 10}
              onClick={() => {
                setBusy(true);
                restoreArchivedProject(project.id, restoreReason.trim())
                  .then((restored) => onRestored?.(restored))
                  .catch((err) => setError(apiErrorMessage(err, "Unable to restore the project.")))
                  .finally(() => setBusy(false));
              }}
            >
              Restore Project
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
