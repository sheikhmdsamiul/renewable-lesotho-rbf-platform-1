/**
 * Report Schedules (Super Admin): reports generated automatically each month or quarter for the
 * period just ended, and shared with their recipients. Formal reports go through review and
 * approval first and are shared only once approved.
 */
import React, { useCallback, useEffect, useState } from "react";
import { CalendarClock, Loader2, Pause, Pencil, Play, Plus, X, Zap } from "lucide-react";
import { fetchReportScheduleOptions, fetchReportSchedules, runReportScheduleNow, saveReportSchedule } from "../api";
import { ReportFormat, ReportSchedule, ReportScheduleOptions } from "../types";
import { apiErrorMessage, ErrorCard, LoadingCard, PageHeader } from "./OversightShared";

const EMPTY: Partial<ReportSchedule> = {
  name: "", reportType: "", format: "pdf", frequency: "monthly", runDay: 5, filters: {}, preparedBy: "",
  recipientRoles: [], recipientUsers: [], active: true,
};

const FORMAT_LABEL: Record<ReportFormat, string> = { pdf: "PDF", excel: "Excel", csv: "CSV", geojson: "GeoJSON", xml: "IATI XML", zip: "ZIP package" };

const when = (value?: string | null) => (value ? new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "-");

function ScheduleForm({
  initial,
  options,
  onCancel,
  onSaved,
}: {
  initial: Partial<ReportSchedule>;
  options: ReportScheduleOptions;
  onCancel: () => void;
  onSaved: (saved: ReportSchedule) => void;
}) {
  const [form, setForm] = useState<Partial<ReportSchedule>>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof ReportSchedule>(key: K, value: ReportSchedule[K]) => setForm((prev) => ({ ...prev, [key]: value }));
  const report = options.reports.find((r) => r.id === form.reportType);
  // Only people whose role can generate the chosen report may prepare it.
  const preparers = options.preparers.filter((p) => !report || report.roles.includes(p.role) || p.role === "Platform Administrator (Super Admin)");

  const chooseReport = (id: string) => {
    const next = options.reports.find((r) => r.id === id);
    setForm((prev) => ({
      ...prev,
      reportType: id,
      name: prev.name || next?.title || "",
      format: next && !next.formats.includes(prev.format as ReportFormat) ? next.formats[0] : prev.format,
    }));
  };

  const submit = async () => {
    if (!form.reportType) return setError("Choose a report.");
    if (!form.name?.trim()) return setError("Give the schedule a name.");
    if (!form.preparedBy) return setError("Choose who the report is prepared as.");
    if (!form.recipientRoles?.length) return setError("Choose at least one recipient role.");
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveReportSchedule(form));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to save the schedule."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card space-y-4 border-emerald-200 p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-900">{form.id ? `Edit ${initial.name}` : "New schedule"}</h3>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Report *</span>
          <select className="input-field" value={form.reportType || ""} onChange={(e) => chooseReport(e.target.value)}>
            <option value="">Choose a report</option>
            {options.reports.map((r) => <option key={r.id} value={r.id}>{r.title}{r.formal ? " (needs approval)" : ""}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Schedule name *</span>
          <input className="input-field" value={form.name || ""} onChange={(e) => set("name", e.target.value)} placeholder="Monthly PSC briefing" />
        </label>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Frequency</span>
          <select className="input-field" value={form.frequency} onChange={(e) => set("frequency", e.target.value as ReportSchedule["frequency"])}>
            <option value="monthly">Monthly (covers the previous month)</option>
            <option value="quarterly">Quarterly (covers the previous quarter)</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Run on day</span>
          <input className="input-field" type="number" min={1} max={28} value={form.runDay ?? 5} onChange={(e) => set("runDay", Number(e.target.value))} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Format</span>
          <select className="input-field" value={form.format} onChange={(e) => set("format", e.target.value as ReportFormat)}>
            {(report?.formats || ["pdf", "excel", "csv"]).map((f) => <option key={f} value={f}>{FORMAT_LABEL[f as ReportFormat]}</option>)}
          </select>
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold text-slate-900">Prepared as *</span>
        <select className="input-field" value={form.preparedBy || ""} onChange={(e) => set("preparedBy", e.target.value)}>
          <option value="">Choose a person</option>
          {preparers.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.role})</option>)}
        </select>
        <span className="mt-1 block text-xs text-slate-500">The report is generated with this person's data access and they are recorded as its preparer. A formal report is sent to someone else for review.</span>
      </label>
      <div>
        <span className="mb-1 block text-sm font-semibold text-slate-900">Recipients *</span>
        <div className="grid gap-2 sm:grid-cols-2">
          {options.roles.map((r) => (
            <label key={r.value} className="flex items-center gap-2 text-sm text-slate-800">
              <input
                type="checkbox"
                checked={form.recipientRoles?.includes(r.value) || false}
                onChange={(e) => set("recipientRoles", e.target.checked ? [...(form.recipientRoles || []), r.value] : (form.recipientRoles || []).filter((x) => x !== r.value))}
              />
              {r.label}
            </label>
          ))}
        </div>
        <span className="mt-1 block text-xs text-slate-500">Recipients get an in-app notice and an email with a link. The file is never attached to the email.</span>
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-800">
        <input type="checkbox" checked={form.active ?? true} onChange={(e) => set("active", e.target.checked)} /> Active
      </label>
      {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} className="btn-secondary" disabled={saving}>Cancel</button>
        <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
          {saving && <Loader2 size={16} className="animate-spin" />} Save Schedule
        </button>
      </div>
    </div>
  );
}

export function ReportSchedules() {
  const [schedules, setSchedules] = useState<ReportSchedule[]>([]);
  const [options, setOptions] = useState<ReportScheduleOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<ReportSchedule> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rows, opts] = await Promise.all([fetchReportSchedules(), fetchReportScheduleOptions()]);
      setSchedules(rows);
      setOptions(opts);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load report schedules."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (saved: ReportSchedule) =>
    setSchedules((prev) => [...prev.filter((s) => s.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));

  const toggle = async (schedule: ReportSchedule) => {
    setBusy(schedule.id);
    setNotice(null);
    try {
      replace(await saveReportSchedule({ ...schedule, active: !schedule.active }));
    } catch (err) {
      setNotice(apiErrorMessage(err, "Unable to update the schedule."));
    } finally {
      setBusy(null);
    }
  };

  const runNow = async (schedule: ReportSchedule) => {
    setBusy(schedule.id);
    setNotice(null);
    try {
      const job = await runReportScheduleNow(schedule.id);
      setNotice(`${job.title} for ${job.period} is being generated. It appears in the Report Center when ready${job.approvalStatus && job.approvalStatus !== "not_required" ? " and is sent for review" : " and is shared with the recipients"}.`);
      await load();
    } catch (err) {
      setNotice(apiErrorMessage(err, "Unable to run the schedule."));
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <LoadingCard label="Loading report schedules..." />;
  if (error || !options) return <ErrorCard message={error || "Unable to load report schedules."} onRetry={() => void load()} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Report Schedules"
        description="Reports generated automatically for the month or quarter just ended and shared with their recipients. Formal reports are reviewed and approved before anyone receives them."
        onRefresh={() => void load()}
      >
        <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setEditing({ ...EMPTY })}>
          <Plus size={16} /> Add Schedule
        </button>
      </PageHeader>
      {notice && <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{notice}</p>}
      {editing && (
        <ScheduleForm
          initial={editing}
          options={options}
          onCancel={() => setEditing(null)}
          onSaved={(saved) => {
            replace(saved);
            setEditing(null);
          }}
        />
      )}
      {schedules.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">
          <CalendarClock size={24} className="mx-auto mb-2 text-slate-400" />
          No schedules yet. A common start is a monthly PSC Briefing for the Project Steering Committee.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Schedule</th>
                <th className="px-4 py-3 text-left font-semibold">Runs</th>
                <th className="px-4 py-3 text-left font-semibold">Prepared as</th>
                <th className="px-4 py-3 text-left font-semibold">Recipients</th>
                <th className="px-4 py-3 text-left font-semibold">Next run</th>
                <th className="px-4 py-3 text-left font-semibold">Last run</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => (
                <tr key={s.id} className={`border-t border-slate-100 align-top ${s.active ? "" : "opacity-60"}`}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-slate-900">{s.name}</p>
                    <p className="text-xs text-slate-500">{s.reportTitle} · {FORMAT_LABEL[s.format]}</p>
                    {!s.active && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">Paused</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{s.frequency === "monthly" ? "Monthly" : "Quarterly"}, day {s.runDay}</td>
                  <td className="px-4 py-3 text-slate-600">{s.preparedByName || "-"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{s.recipientRoles.join(", ") || "-"}{s.recipientUsers.length > 0 && ` + ${s.recipientUsers.length} named`}</td>
                  <td className="px-4 py-3 text-slate-600">{s.active ? when(s.nextRunAt) : "-"}</td>
                  <td className="px-4 py-3 text-slate-600">{when(s.lastRunAt)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" disabled={busy === s.id} onClick={() => void runNow(s)}><Zap size={14} /> Run now</button>
                      <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" disabled={busy === s.id} onClick={() => void toggle(s)}>
                        {s.active ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
                      </button>
                      <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setEditing(s)}><Pencil size={14} /> Edit</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
