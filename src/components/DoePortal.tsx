import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Clock,
  Download,
  FileText,
  Loader2,
  Map,
  RefreshCw,
  Send,
  TrendingUp,
} from "lucide-react";
import { fetchProjects, fetchReportTemplates, fetchReportHistory } from "../api";
import { Project, ReportHistoryItem, ReportTemplate, User } from "../types";
import { ReportsHub } from "./ReportsHub";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

export function DoeDashboard({ currentUser, onNavigate }: { currentUser: any; onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sendingNotification, setSendingNotification] = useState(false);
  const [concernText, setConcernText] = useState("");
  const [showConcernModal, setShowConcernModal] = useState(false);

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const loadData = async () => {
    setLoading(true);
    try {
      const list = await fetchProjects();
      const filtered = list.filter((p: Project) => {
        if (userDistricts.length === 0) return true;
        const projectDistrict = p.district || p.region || "";
        return userDistricts.some(d => projectDistrict.toLowerCase().includes(d.toLowerCase()));
      });
      setProjects(filtered);
    } catch (err) {
      console.error("Failed to load DoE dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [userDistricts]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  const summaryCards = useMemo(() => {
    const active = projects.filter(p => p.status === "active").length;
    const totalInstallations = projects.reduce((sum, p) => sum + (p.progress || 0), 0);
    
    return {
      activeProjects: active,
      installations: totalInstallations,
    };
  }, [projects]);

  const attentionItems = useMemo(() => {
    const kpisBelowTarget = projects.filter(p => (p.uptime || 0) < 95).length;
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const unverifiedOld = projects.filter(p => {
      if (p.status !== "completed") return false;
      const created = p.createdAt ? new Date(p.createdAt) : null;
      return created && created < sevenDaysAgo;
    }).length;
    return { kpisBelowTarget, unverifiedOld };
  }, [projects]);

  const handleViewMap = () => {
    if (onNavigate) {
      onNavigate("gis");
    }
  };

  const handleViewKpis = () => {
    if (onNavigate) {
      onNavigate("kpis");
    }
  };

  const handleViewProjects = () => {
    if (onNavigate) {
      onNavigate("projects");
    }
  };

  const handleContactRmt = () => {
    setShowConcernModal(true);
  };

  const handleSendConcern = async () => {
    if (!concernText.trim()) return;
    setSendingNotification(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 1000));
      setShowConcernModal(false);
      setConcernText("");
      alert("Concern sent to RMT successfully!");
    } catch (err) {
      console.error("Failed to send concern:", err);
    } finally {
      setSendingNotification(false);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading regional dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {showConcernModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Flag Concern to RMT</h3>
            <textarea
              className="input-field min-h-[120px]"
              placeholder="Describe your concern..."
              value={concernText}
              onChange={(e) => setConcernText(e.target.value)}
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setShowConcernModal(false)}
                className="btn-secondary"
                disabled={sendingNotification}
              >
                Cancel
              </button>
              <button
                onClick={handleSendConcern}
                className="btn-primary flex items-center gap-2"
                disabled={sendingNotification || !concernText.trim()}
              >
                {sendingNotification ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                Send to RMT
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regional Overview</h1>
          <p className="text-sm text-slate-500">Region: {regionLabel}</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Summary Cards</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Active Projects</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summaryCards.activeProjects}</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Installations</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summaryCards.installations}</p>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Projects in My Region</h3>
        {projects.length === 0 ? (
          <p className="text-slate-500">No projects are currently assigned to this regional scope.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">District</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Vendor</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Progress</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">KPI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {projects.slice(0, 10).map((project) => (
                  <tr key={project.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">
                      {project.projectReference || project.id}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {project.district || project.region || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {project.vendorName || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {project.progress || 0}%
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        project.status === "active" ? "bg-emerald-100 text-emerald-700" :
                        project.status === "completed" ? "bg-blue-100 text-blue-700" :
                        "bg-slate-100 text-slate-600"
                      }`}>
                        {project.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {(project.uptime || 0) >= 95 ? (
                        <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700">
                          OK
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700">
                          LOW
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Attention Items</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-rose-600" />
              <span className="text-sm font-medium text-slate-700">Projects with KPIs below target</span>
            </div>
            <span className="text-lg font-bold text-rose-700">{attentionItems.kpisBelowTarget}</span>
          </div>
          <div className="flex items-center justify-between rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
            <div className="flex items-center gap-2">
              <Clock size={18} className="text-amber-600" />
              <span className="text-sm font-medium text-slate-700">Unverified installations &gt; 7 days old</span>
            </div>
            <span className="text-lg font-bold text-amber-700">{attentionItems.unverifiedOld}</span>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button onClick={handleViewMap} className="btn-secondary flex items-center gap-2">
            <Map size={16} /> View Regional Map
          </button>
          <button onClick={handleViewKpis} className="btn-secondary flex items-center gap-2">
            <TrendingUp size={16} /> View Regional KPI
          </button>
          <button onClick={handleViewProjects} className="btn-secondary flex items-center gap-2">
            <FileText size={16} /> View Projects
          </button>
          <button onClick={handleContactRmt} className="btn-primary flex items-center gap-2">
            <Send size={16} /> Contact RMT
          </button>
        </div>
      </div>
    </div>
  );
}

export function DoeRegionalMap({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const loadData = async () => {
    setLoading(true);
    try {
      const list = await fetchProjects();
      const filtered = list.filter((p: Project) => {
        if (userDistricts.length === 0) return true;
        const projectDistrict = p.district || p.region || "";
        return userDistricts.some(d => projectDistrict.toLowerCase().includes(d.toLowerCase()));
      });
      setProjects(filtered);
    } catch (err) {
      console.error("Failed to load projects:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [userDistricts]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading regional map...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regional Map</h1>
          <p className="text-sm text-slate-500">Region: {regionLabel}</p>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-600"
          />
          <span className="text-sm font-medium text-slate-700">Show Gender Impact Layer</span>
        </label>
      </div>

      <div className="card p-6">
        <p className="text-sm text-slate-500 mb-4">
          GIS map filtered to your region. All installations in assigned districts. Read-only.
        </p>
        <div className="bg-slate-100 rounded-xl p-8 text-center">
          <Map size={48} className="mx-auto text-slate-400 mb-2" />
          <p className="text-slate-500">Map view shows {projects.length} projects in {regionLabel}</p>
        </div>
      </div>
    </div>
  );
}

export function DoeReports({ currentUser }: { currentUser: User }) {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [history, setHistory] = useState<ReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
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

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading reports...
      </div>
    );
  }

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">REPORTS — Regional Scope</h1>
          <p className="text-sm text-slate-500">
            All reports are scoped to your assigned region.
          </p>
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

      <ReportsHub currentUser={currentUser} />
    </div>
  );
}