/**
 * Results Framework (Super Admin): the programme's indicators with baselines and targets.
 * The Programme Results report and the PSC Briefing measure actuals against these.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus, Target, X } from "lucide-react";
import { fetchResultsIndicators, fetchResultsMeasures, saveResultsIndicator } from "../api";
import { ResultsIndicator } from "../types";
import { apiErrorMessage, ErrorCard, LoadingCard, PageHeader } from "./OversightShared";

const EMPTY: Partial<ResultsIndicator> = {
  code: "", name: "", unit: "", measure: "verified_installations", technology: "", baseline: null, target: null,
  targetDate: null, manualActual: null, manualActualAsOf: null, sourceNote: "", position: 0,
};

const numberOrNull = (value: string) => (value.trim() === "" ? null : Number(value));

function IndicatorForm({
  initial,
  measures,
  onCancel,
  onSaved,
}: {
  initial: Partial<ResultsIndicator>;
  measures: { value: string; label: string }[];
  onCancel: () => void;
  onSaved: (saved: ResultsIndicator) => void;
}) {
  const [form, setForm] = useState<Partial<ResultsIndicator>>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof ResultsIndicator>(key: K, value: ResultsIndicator[K] | null) => setForm((prev) => ({ ...prev, [key]: value }));
  const manual = form.measure === "manual";

  const submit = async () => {
    if (!form.code?.trim() || !form.name?.trim()) return setError("Enter a code and a name.");
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveResultsIndicator(form));
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to save the indicator."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card space-y-4 border-emerald-200 p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-900">{form.id ? `Edit ${form.code}` : "New indicator"}</h3>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
      </div>
      <div className="grid gap-4 md:grid-cols-[160px_1fr_160px]">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Code *</span>
          <input className="input-field" value={form.code || ""} onChange={(e) => set("code", e.target.value)} placeholder="OUT1.1" />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Indicator *</span>
          <input className="input-field" value={form.name || ""} onChange={(e) => set("name", e.target.value)} placeholder="Households connected to mini-grids" />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Unit</span>
          <input className="input-field" value={form.unit || ""} onChange={(e) => set("unit", e.target.value)} placeholder="households" />
        </label>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">How the actual is obtained *</span>
          <select className="input-field" value={form.measure} onChange={(e) => set("measure", e.target.value)}>
            {measures.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        {!manual && (
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Only this technology</span>
            <input className="input-field" value={form.technology || ""} onChange={(e) => set("technology", e.target.value)} placeholder="All technologies" />
          </label>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Baseline</span>
          <input className="input-field" type="number" value={form.baseline ?? ""} onChange={(e) => set("baseline", numberOrNull(e.target.value))} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Target</span>
          <input className="input-field" type="number" value={form.target ?? ""} onChange={(e) => set("target", numberOrNull(e.target.value))} />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-900">Target date</span>
          <input className="input-field" type="date" value={form.targetDate || ""} onChange={(e) => set("targetDate", e.target.value || null)} />
        </label>
      </div>
      {manual && (
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Current actual</span>
            <input className="input-field" type="number" value={form.manualActual ?? ""} onChange={(e) => set("manualActual", numberOrNull(e.target.value))} />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Actual as of</span>
            <input className="input-field" type="date" value={form.manualActualAsOf || ""} onChange={(e) => set("manualActualAsOf", e.target.value || null)} />
          </label>
        </div>
      )}
      <label className="block">
        <span className="mb-1 block text-sm font-semibold text-slate-900">Source of the target</span>
        <input className="input-field" value={form.sourceNote || ""} onChange={(e) => set("sourceNote", e.target.value)} placeholder="EU Action Document, Renewable Lesotho logframe" />
      </label>
      {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} className="btn-secondary" disabled={saving}>Cancel</button>
        <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
          {saving && <Loader2 size={16} className="animate-spin" />} Save Indicator
        </button>
      </div>
    </div>
  );
}

export function ResultsFramework() {
  const [indicators, setIndicators] = useState<ResultsIndicator[]>([]);
  const [measures, setMeasures] = useState<{ value: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<ResultsIndicator> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rows, choices] = await Promise.all([fetchResultsIndicators(), fetchResultsMeasures()]);
      setIndicators(rows);
      setMeasures(choices);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load the results framework."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingCard label="Loading the results framework..." />;
  if (error) return <ErrorCard message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Results Framework"
        description="The programme indicators, baselines and targets that the Programme Results report and PSC Briefing measure against. Changes are recorded in the audit log."
        onRefresh={() => void load()}
      >
        <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setEditing({ ...EMPTY, position: indicators.length })}>
          <Plus size={16} /> Add Indicator
        </button>
      </PageHeader>
      {editing && (
        <IndicatorForm
          initial={editing}
          measures={measures}
          onCancel={() => setEditing(null)}
          onSaved={(saved) => {
            setIndicators((prev) => [...prev.filter((i) => i.id !== saved.id), saved].sort((a, b) => a.position - b.position || a.code.localeCompare(b.code)));
            setEditing(null);
          }}
        />
      )}
      {indicators.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">
          <Target size={24} className="mx-auto mb-2 text-slate-400" />
          No indicators yet. Add the programme's logframe indicators with their baselines and targets. Until then, reports list the platform's measures without targets.
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Code</th>
                <th className="px-4 py-3 text-left font-semibold">Indicator</th>
                <th className="px-4 py-3 text-left font-semibold">Actual from</th>
                <th className="px-4 py-3 text-right font-semibold">Baseline</th>
                <th className="px-4 py-3 text-right font-semibold">Target</th>
                <th className="px-4 py-3 text-left font-semibold">By</th>
                <th className="px-4 py-3 text-left font-semibold">Last changed</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {indicators.map((i) => (
                <tr key={i.id} className="border-t border-slate-100 align-top">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{i.code}</td>
                  <td className="px-4 py-3 text-slate-900">{i.name}{i.unit && <span className="text-slate-500"> ({i.unit})</span>}{i.sourceNote && <p className="text-xs text-slate-500">{i.sourceNote}</p>}</td>
                  <td className="px-4 py-3 text-slate-600">{i.measureDisplay}{i.technology && ` · ${i.technology}`}{i.measure === "manual" && i.manualActual !== null && <p className="text-xs">Current: {i.manualActual.toLocaleString()}</p>}</td>
                  <td className="px-4 py-3 text-right text-slate-700">{i.baseline !== null ? i.baseline.toLocaleString() : "-"}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-900">{i.target !== null ? i.target.toLocaleString() : "-"}</td>
                  <td className="px-4 py-3 text-slate-600">{i.targetDate || "-"}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{i.updatedByName || "-"}{i.updatedAt && <p>{new Date(i.updatedAt).toLocaleDateString("en-GB")}</p>}</td>
                  <td className="px-4 py-3 text-right">
                    <button type="button" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs" onClick={() => setEditing(i)}><Pencil size={14} /> Edit</button>
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
