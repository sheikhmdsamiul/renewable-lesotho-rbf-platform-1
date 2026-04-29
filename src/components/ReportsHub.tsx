import React, { useEffect, useMemo, useState } from "react";
import { BarChart3, Download, Loader2, RefreshCw } from "lucide-react";
import { downloadGeneratedReport, fetchProjects, fetchReportHistory, fetchReportTemplates, generateReport } from "../api";
import { Project, ReportFormat, ReportHistoryItem, ReportTemplate, User, UserRole } from "../types";

function saveBlob(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

function formatFormat(format: ReportFormat) {
  if (format === "excel") return "Excel";
  return format.toUpperCase();
}

function filenameFor(reportType: string, format: ReportFormat) {
  const safe = reportType.replace(/[^a-z0-9_-]+/gi, "_");
  const ext = format === "excel" ? "xlsx" : format;
  return `${safe}.${ext}`;
}

function isPerProjectTemplate(templateId: string) {
  return [
    "rmt_kpi_project",
    "rmt_verification_project",
    "doe_regional_progress",
    "doe_verification_summary",
  ].includes(templateId);
}

const roleLabel = (role: UserRole) => {
  if (role === UserRole.RBF_OFFICIAL) return "RMT";
  if (role === UserRole.UNDP_DONOR) return "PSC";
  if (role === UserRole.DOE_OFFICER) return "DoE";
  if (role === UserRole.FIELD_VERIFIER) return "Field Officer";
  if (role === UserRole.AUDITOR) return "Auditor";
  if (role === UserRole.TAC) return "TAC";
  return role;
};

export function ReportsHub({ currentUser }: { currentUser: User }) {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [history, setHistory] = useState<ReportHistoryItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("All");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [generatingKey, setGeneratingKey] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [projectByTemplate, setProjectByTemplate] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [tpls, hist, proj] = await Promise.all([
        fetchReportTemplates(),
        fetchReportHistory(),
        fetchProjects().catch(() => [] as Project[]),
      ]);
      setTemplates(tpls);
      setHistory(hist);
      setProjects(proj);
      if (!selectedTemplateId && tpls.length) setSelectedTemplateId(tpls[0].id);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load reports."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const categories = useMemo(() => {
    const uniq = new Set<string>();
    templates.forEach((t) => uniq.add(t.category || "Reports"));
    return ["All", ...Array.from(uniq).sort((a, b) => a.localeCompare(b))];
  }, [templates]);

  const grouped = useMemo(() => {
    const result = new Map<string, ReportTemplate[]>();
    templates.forEach((tpl) => {
      const cat = tpl.category || "Reports";
      if (!result.has(cat)) result.set(cat, []);
      result.get(cat)!.push(tpl);
    });
    result.forEach((rows) => rows.sort((a, b) => a.title.localeCompare(b.title)));
    return result;
  }, [templates]);

  const quick = useMemo(() => templates.filter((t) => t.quick).slice(0, 6), [templates]);

  const visibleTemplates = useMemo(() => {
    if (activeCategory === "All") return templates;
    return templates.filter((t) => (t.category || "Reports") === activeCategory);
  }, [templates, activeCategory]);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) || null,
    [templates, selectedTemplateId],
  );

  const canPickProject = useMemo(() => {
    if (!selectedTemplate) return false;
    return isPerProjectTemplate(selectedTemplate.id);
  }, [selectedTemplate]);

  const handleGenerate = async (templateId: string, chosenFormat: ReportFormat, projectId?: string) => {
    const key = `${templateId}:${chosenFormat}:${projectId || ""}`;
    setGeneratingKey(key);
    try {
      const filters: Record<string, any> = {};
      if (projectId) filters.project_id = projectId;
      if (dateFrom) filters.from = dateFrom;
      if (dateTo) filters.to = dateTo;
      const blob = await generateReport(templateId, chosenFormat, filters);
      saveBlob(blob, filenameFor(templateId, chosenFormat));
      await load();
    } catch (err: any) {
      setError(String(err?.message || "Unable to generate report."));
    } finally {
      setGeneratingKey(null);
    }
  };

  const handleDownloadHistory = async (item: ReportHistoryItem) => {
    if (!item.downloadUrl) return;
    const key = `download:${item.id}`;
    setGeneratingKey(key);
    try {
      const blob = await downloadGeneratedReport(item.downloadUrl);
      saveBlob(blob, filenameFor(item.reportType, item.format));
    } catch (err: any) {
      setError(String(err?.message || "Unable to download report."));
    } finally {
      setGeneratingKey(null);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading reports...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {currentUser.role === UserRole.DOE_OFFICER ? "REPORTS — Regional Scope" : "REPORTS"}
          </h1>
          <p className="text-sm text-slate-500">
            {currentUser.role === UserRole.DOE_OFFICER
              ? "All reports are scoped to your assigned region."
              : `${roleLabel(currentUser.role)} reports, export-ready and auditable.`}
          </p>
        </div>
        <button onClick={() => void load()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Quick Generate (most used)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {quick.map((tpl) => (
            <div key={tpl.id} className="rounded-2xl border border-slate-200 p-5 bg-white">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-emerald-50 p-3">
                  <BarChart3 size={20} className="text-emerald-700" />
                </div>
                <div className="flex-1">
                  <p className="font-bold text-slate-900">{tpl.title}</p>
                  <p className="text-xs text-slate-500 mt-1">{tpl.description}</p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {(tpl.formats || []).slice(0, 3).map((f) => (
                  <button
                    key={f}
                    onClick={() => {
                      const projectId = isPerProjectTemplate(tpl.id) ? (projectByTemplate[tpl.id] || "") : "";
                      if (isPerProjectTemplate(tpl.id) && !projectId) {
                        setSelectedTemplateId(tpl.id);
                        return;
                      }
                      void handleGenerate(tpl.id, f, projectId || undefined);
                    }}
                    className="btn-secondary flex items-center gap-2 text-sm"
                    disabled={generatingKey === `${tpl.id}:${f}:`}
                  >
                    <Download size={16} /> {formatFormat(f)}
                  </button>
                ))}
              </div>
              {isPerProjectTemplate(tpl.id) && (
                <div className="mt-3">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Project</label>
                  <select
                    className="input-field mt-2"
                    value={projectByTemplate[tpl.id] || ""}
                    onChange={(e) => setProjectByTemplate((prev) => ({ ...prev, [tpl.id]: e.target.value }))}
                  >
                    <option value="">Select a project…</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.projectReference || p.projectTitle || p.id}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          ))}
          {quick.length === 0 && <p className="text-sm text-slate-500">No quick reports available for your role.</p>}
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Report Categories</h3>
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={cat === activeCategory ? "btn-primary text-sm" : "btn-secondary text-sm"}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          {visibleTemplates.map((tpl) => (
            <div key={tpl.id} className="rounded-2xl border border-slate-200 p-5 bg-white">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-900">{tpl.title}</p>
                  <p className="text-xs text-slate-500 mt-1">{tpl.description}</p>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mt-2">{tpl.category || "Reports"}</p>
                </div>
                <div className="flex flex-wrap gap-2 justify-end">
                  {(tpl.formats || []).map((f) => (
                    <button
                      key={f}
                      onClick={() => {
                        const projectId = isPerProjectTemplate(tpl.id) ? (projectByTemplate[tpl.id] || "") : "";
                        if (isPerProjectTemplate(tpl.id) && !projectId) {
                          setSelectedTemplateId(tpl.id);
                          return;
                        }
                        void handleGenerate(tpl.id, f, projectId || undefined);
                      }}
                      className="btn-secondary flex items-center gap-2 text-xs"
                      disabled={generatingKey === `${tpl.id}:${f}:`}
                    >
                      <Download size={14} /> {formatFormat(f)}
                    </button>
                  ))}
                </div>
              </div>
              {isPerProjectTemplate(tpl.id) && (
                <div className="mt-4">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Project</label>
                  <select
                    className="input-field mt-2"
                    value={projectByTemplate[tpl.id] || ""}
                    onChange={(e) => setProjectByTemplate((prev) => ({ ...prev, [tpl.id]: e.target.value }))}
                  >
                    <option value="">Select a project…</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.projectReference || p.projectTitle || p.id}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          ))}
          {visibleTemplates.length === 0 && <p className="text-sm text-slate-500">No reports in this category.</p>}
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Generate Report (Universal)</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-slate-500">Report Type</label>
            <select
              className="input-field mt-2"
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
            >
              {Array.from(grouped.entries())
                .sort(([a], [b]) => a.localeCompare(b))
                .flatMap(([cat, rows]) => [
                  <option key={`__cat_${cat}`} disabled value={`__cat_${cat}`}>
                    {cat.toUpperCase()}
                  </option>,
                  ...rows.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.title}
                    </option>
                  )),
                ])}
            </select>
          </div>

          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-slate-500">Format</label>
            <select className="input-field mt-2" value={format} onChange={(e) => setFormat(e.target.value as ReportFormat)}>
              <option value="pdf">PDF</option>
              <option value="excel">Excel</option>
              <option value="csv">CSV</option>
            </select>
          </div>

          {canPickProject && (
            <div className="lg:col-span-2">
              <label className="text-xs font-bold uppercase tracking-widest text-slate-500">Project (optional)</label>
              <select className="input-field mt-2" value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)}>
                <option value="">All / Default</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.projectReference || p.projectTitle || p.id}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-slate-500">From</label>
            <input className="input-field mt-2" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-slate-500">To</label>
            <input className="input-field mt-2" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>

          <div className="lg:col-span-2 flex justify-end">
            <button
              className="btn-primary flex items-center gap-2"
              disabled={!selectedTemplate || (selectedTemplate?.formats || []).length === 0 || generatingKey === `form`}
              onClick={() => {
                if (!selectedTemplate) return;
                void handleGenerate(selectedTemplate.id, format, selectedProjectId || undefined);
              }}
            >
              <Download size={16} /> Generate Report
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Generated reports are saved to history (last 20) and can be downloaded again anytime.
        </p>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Generated Reports History (last 20)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs tracking-widest">
              <tr>
                <th className="px-4 py-3">Report Type</th>
                <th className="px-4 py-3">Project</th>
                <th className="px-4 py-3">Generated By</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Download</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {history.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                    No generated reports yet.
                  </td>
                </tr>
              ) : (
                history.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-900">{item.reportType}</td>
                    <td className="px-4 py-3 text-slate-600">{item.project || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{item.generatedBy || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{item.generatedAt ? new Date(item.generatedAt).toLocaleString() : "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{formatFormat(item.format)}</td>
                    <td className="px-4 py-3">
                      <button
                        className="btn-secondary flex items-center gap-2 text-xs"
                        onClick={() => void handleDownloadHistory(item)}
                        disabled={!item.downloadUrl || generatingKey === `download:${item.id}`}
                      >
                        <Download size={14} /> Download
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

