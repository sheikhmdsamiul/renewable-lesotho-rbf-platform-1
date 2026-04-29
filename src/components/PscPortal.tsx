import React, { useEffect, useMemo, useState } from "react";
import {
  CreditCard,
  DollarSign,
  FolderKanban,
  Loader2,
  RefreshCw,
  TrendingUp,
  AlertTriangle,
  Download,
  FileText,
} from "lucide-react";
import {
  fetchProjects,
  fetchPaymentClaims,
  fetchPortfolioKpiSummary,
  fetchReportTemplates,
  fetchReportHistory,
  generateReport,
} from "../api";
import { ReportTemplate, ReportHistoryItem } from "../types";

export function PscDashboard({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<any[]>([]);
  const [claims, setClaims] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [projectsData, claimsData, portfolioData] = await Promise.all([
        fetchProjects(),
        fetchPaymentClaims(),
        fetchPortfolioKpiSummary(),
      ]);
      setProjects(projectsData);
      setClaims(claimsData);
      setPortfolio(portfolioData);
    } catch (err) {
      console.error("Failed to load PSC data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const pendingClaims = useMemo(() => {
    return claims.filter(c => c.status === "PSC Approved" || c.status === "Approved").length;
  }, [claims]);

  const summary = useMemo(() => {
    const totalProjects = projects.length;
    const projectsOnTrack = projects.filter(p => p.progress > 50).length;
    const totalPaid = claims.filter(c => c.status === "Paid").reduce((sum, c) => sum + (c.claimAmount || 0), 0);
    const totalProgress = projects.length > 0
      ? projects.reduce((sum, p) => sum + (p.progress || 0), 0) / projects.length
      : 0;

    return {
      totalProjects,
      projectsOnTrack,
      totalPaid,
      overallProgress: Math.round(totalProgress),
    };
  }, [projects, claims]);

  const disbursement = useMemo(() => {
    const totalContracted = 5400000;
    const paidOut = claims.filter(c => c.status === "Paid").reduce((sum, c) => sum + (c.claimAmount || 0), 0);
    const pendingApprovals = 225000;

    return {
      totalContracted,
      paidOut,
      pendingApprovals,
    };
  }, [claims]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading PSC dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Portfolio Summary</h1>
          <p className="text-sm text-slate-500">Dashboard</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {pendingClaims > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle size={20} className="text-amber-600" />
            <span className="text-sm font-medium text-amber-800">
              {pendingClaims} claims awaiting your final approval
            </span>
          </div>
          <button className="btn-primary text-sm">Review Claims</button>
        </div>
      )}

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Portfolio Summary</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Projects</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summary.totalProjects}</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Total Paid Out</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">LSL {(disbursement.paidOut / 1000000).toFixed(1)}M</p>
          </div>
          <div className="rounded-xl bg-blue-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-blue-600">Overall Progress</p>
            <p className="mt-2 text-3xl font-bold text-blue-700">{summary.overallProgress}%</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Projects On Track</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">{summary.projectsOnTrack}</p>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Disbursement Tracker</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total contracted</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">LSL {(disbursement.totalContracted / 1000000).toFixed(1)}M</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Paid out</p>
            <p className="mt-2 text-2xl font-bold text-emerald-700">LSL {(disbursement.paidOut / 1000000).toFixed(1)}M</p>
          </div>
          <div className="rounded-xl bg-amber-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Pending approvals</p>
            <p className="mt-2 text-2xl font-bold text-amber-700">LSL {(disbursement.pendingApprovals / 1000).toFixed(0)}K</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PscReports() {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [history, setHistory] = useState<ReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadContents = async () => {
    setLoading(true);
    setError(null);

    try {
      const [reportTemplates, reportHistory] = await Promise.all([
        fetchReportTemplates(),
        fetchReportHistory(),
      ]);

      setTemplates(reportTemplates);
      setHistory(reportHistory);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load reports."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadContents();
  }, []);

  const handleExport = async (reportType: string, format: "csv" | "pdf") => {
    setExporting(`${reportType}:${format}`);

    try {
      const blob = await generateReport(reportType, format);
      const filename = `${reportType}_${format}`;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      await loadContents();
    } catch (err) {
      console.error("Failed to export PSC report:", err);
      setError("Unable to generate the report.");
    } finally {
      setExporting(null);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading report library...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">PSC Reports</h1>
          <p className="text-sm text-slate-500">Disbursement and vendor payment export tools.</p>
        </div>
        <button onClick={() => void loadContents()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {templates.map((template) => (
          <div key={template.id} className="card p-5 border border-slate-200 rounded-3xl">
            <div className="flex items-start gap-4">
              <div className="rounded-2xl bg-emerald-50 p-3">
                <FileText size={24} className="text-emerald-700" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-slate-900">{template.title}</h2>
                <p className="text-sm text-slate-500 mt-1">{template.description}</p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              {template.formats.map((format) => (
                <button
                  key={format}
                  onClick={() => void handleExport(template.id, format)}
                  className="btn-secondary flex items-center gap-2 text-sm"
                  disabled={exporting === `${template.id}:${format}`}
                >
                  <Download size={16} /> {format.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Recent Exports</h3>
            <p className="text-sm text-slate-500">Most recent PSC report generation events.</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 uppercase text-xs tracking-widest">
              <tr>
                <th className="px-4 py-3">Report</th>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Generated At</th>
                <th className="px-4 py-3">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {history.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">No recent exports available.</td>
                </tr>
              ) : (
                history.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-900">{item.reportType}</td>
                    <td className="px-4 py-3 uppercase text-slate-600">{item.format}</td>
                    <td className="px-4 py-3 text-slate-600">{new Date(item.generatedAt).toLocaleString()}</td>
                    <td className="px-4 py-3 text-slate-500">{item.notes || "—"}</td>
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
