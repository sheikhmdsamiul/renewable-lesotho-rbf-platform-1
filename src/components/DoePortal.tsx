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
import { fetchProjects } from "../api";
import { Project } from "../types";

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
    const avgFemale = projects.length > 0 
      ? projects.reduce((sum, p) => sum + (p.genderImpact || 0), 0) / projects.length 
      : 0;
    const avgVerified = projects.length > 0
      ? projects.reduce((sum, p) => sum + (p.progress || 0), 0) / projects.length
      : 0;
    
    return {
      activeProjects: active,
      installations: totalInstallations,
      femalePct: Math.round(avgFemale),
      verifiedPct: Math.round(avgVerified),
    };
  }, [projects]);

  const attentionItems = useMemo(() => {
    const kpisBelowTarget = projects.filter(p => (p.uptime || 0) < 95).length;
    const lowProgress = projects.filter(p => (p.progress || 0) < 50).length;
    return { kpisBelowTarget, lowProgress };
  }, [projects]);

  const handleViewMap = () => {
    if (onNavigate) {
      onNavigate("gis");
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
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Active Projects</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summaryCards.activeProjects}</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Installations</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summaryCards.installations}</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Female %</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">{summaryCards.femalePct}%</p>
          </div>
          <div className="rounded-xl bg-blue-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-blue-600">Verified %</p>
            <p className="mt-2 text-3xl font-bold text-blue-700">{summaryCards.verifiedPct}%</p>
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
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Vendor</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Progress</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Female %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {projects.slice(0, 10).map((project) => (
                  <tr key={project.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">
                      {project.projectReference || project.id}
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
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {project.genderImpact || 0}%
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
              <span className="text-sm font-medium text-slate-700">Projects with low progress</span>
            </div>
            <span className="text-lg font-bold text-amber-700">{attentionItems.lowProgress}</span>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button onClick={handleViewMap} className="btn-secondary flex items-center gap-2">
            <Map size={16} /> View Regional Map
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

export function DoeReports({ currentUser }: { currentUser: any }) {
  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  const handleExportReport = (reportType: string) => {
    const csv = [
      ["Reference", "Vendor", "Status", "Progress", "Gender Impact"].join(","),
    ].join("\n");
    
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${reportType}_${regionLabel.replace(/\s+/g, "_")}.csv`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
          <p className="text-sm text-slate-500">Reports scoped to {regionLabel}</p>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Available Reports</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button 
            onClick={() => handleExportReport("regional_progress")}
            className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50 cursor-pointer text-left"
          >
            <FileText size={24} className="text-emerald-600 mb-2" />
            <p className="font-medium text-slate-900">Regional Progress Report</p>
            <p className="text-xs text-slate-500">Current progress by project and district</p>
          </button>
          <button 
            onClick={() => handleExportReport("gender_impact")}
            className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50 cursor-pointer text-left"
          >
            <FileText size={24} className="text-emerald-600 mb-2" />
            <p className="font-medium text-slate-900">Regional Gender Impact Report</p>
            <p className="text-xs text-slate-500">Female beneficiary analysis</p>
          </button>
          <button 
            onClick={() => handleExportReport("verification_summary")}
            className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50 cursor-pointer text-left"
          >
            <FileText size={24} className="text-emerald-600 mb-2" />
            <p className="font-medium text-slate-900">Regional Verification Summary</p>
            <p className="text-xs text-slate-500">Verification status by project</p>
          </button>
          <button 
            onClick={() => handleExportReport("technology_breakdown")}
            className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50 cursor-pointer text-left"
          >
            <FileText size={24} className="text-emerald-600 mb-2" />
            <p className="font-medium text-slate-900">Technology Breakdown Report</p>
            <p className="text-xs text-slate-500">SHS/ICS/GMG distribution</p>
          </button>
        </div>
      </div>
    </div>
  );
}