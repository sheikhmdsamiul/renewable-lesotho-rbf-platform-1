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
  Flag,
  Eye,
  X,
  CheckCircle2,
} from "lucide-react";
import { fetchProjects, fetchReportTemplates, fetchReportHistory, fetchConcerns, createConcern } from "../api";
import { Project, ReportHistoryItem, ReportTemplate, User } from "../types";
import { ReportsHub } from "./ReportsHub";
import { GisInstallationsMap } from "./GisInstallationsMap";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

const CONCERN_TYPES = [
  { value: "kpi_issue", label: "KPI Issue", desc: "Female/vulnerable/uptime targets at risk" },
  { value: "gps_issue", label: "GPS / Location Issue", desc: "Suspicious coordinates or location mismatch" },
  { value: "verification_issue", label: "Field Verification Issue", desc: "Verifications not being conducted properly" },
  { value: "vendor_behaviour", label: "Vendor Behaviour", desc: "Vendor not cooperating or acting suspiciously" },
  { value: "installation_quality", label: "Installation Quality", desc: "Systems not working or incorrectly installed" },
  { value: "data_discrepancy", label: "Data Discrepancy", desc: "Data in system does not match field reality" },
  { value: "other", label: "Other", desc: "Other concern" },
];

const SEVERITY_LEVELS = [
  { value: "low", label: "Low", desc: "Informational, monitor only", color: "yellow" },
  { value: "medium", label: "Medium", desc: "Needs attention within 7 days", color: "orange" },
  { value: "high", label: "High", desc: "Urgent, needs immediate action", color: "red" },
];

export function DoeDashboard({ currentUser, onNavigate }: { currentUser: any; onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [concerns, setConcerns] = useState<any[]>([]);
  const [showConcernModal, setShowConcernModal] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [concernType, setConcernType] = useState("");
  const [severity, setSeverity] = useState("");
  const [description, setDescription] = useState("");
  const [notifyRmt, setNotifyRmt] = useState(true);
  const [notifyPsc, setNotifyPsc] = useState(false);

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [list, concernsData] = await Promise.all([
        fetchProjects(),
        fetchConcerns(),
      ]);
      const filtered = list.filter((p: Project) => {
        if (userDistricts.length === 0) return true;
        const projectDistrict = p.district || p.region || "";
        return userDistricts.some(d => projectDistrict.toLowerCase().includes(d.toLowerCase()));
      });
      setProjects(filtered);
      setConcerns(concernsData);
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

  const handleRaiseConcern = (project: Project) => {
    setSelectedProject(project);
    setShowConcernModal(true);
  };

  const handleSubmitConcern = async () => {
    if (!concernType || !severity || !description.trim() || description.length < 50) {
      alert("Please fill in all required fields. Description must be at least 50 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await createConcern({
        concern_type: concernType,
        severity: severity,
        linked_project: selectedProject?.id,
        description: description,
        notify_rmt: notifyRmt,
        notify_psc: notifyPsc,
      });
      alert("Concern submitted successfully!");
      setShowConcernModal(false);
      setSelectedProject(null);
      setConcernType("");
      setSeverity("");
      setDescription("");
      setNotifyRmt(true);
      setNotifyPsc(false);
      void loadData();
    } catch (err) {
      console.error("Failed to submit concern:", err);
      alert("Failed to submit concern. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const myConcerns = concerns.filter((c: any) => c.raised_by_username === currentUser?.username);

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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999] overflow-y-auto">
          <div className="bg-white rounded-2xl p-6 max-w-2xl w-full mx-4 my-8 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Flag size={20} className="text-amber-600" />
                Raise Concern
              </h3>
              <button onClick={() => setShowConcernModal(false)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>

            {selectedProject && (
              <div className="bg-slate-50 rounded-xl p-3 mb-4 text-sm">
                <p className="font-medium text-slate-900">
                  Linked to: {selectedProject.projectReference || selectedProject.id}
                </p>
                <p className="text-slate-500">
                  {selectedProject.vendorName} — {selectedProject.district || selectedProject.region}
                </p>
              </div>
            )}

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Concern Type *</label>
              <div className="grid grid-cols-2 gap-2">
                {CONCERN_TYPES.map((type) => (
                  <button
                    key={type.value}
                    onClick={() => setConcernType(type.value)}
                    className={`p-3 rounded-xl text-left border transition-all ${
                      concernType === type.value
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <p className="font-medium text-slate-900 text-sm">{type.label}</p>
                    <p className="text-xs text-slate-500">{type.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Severity *</label>
              <div className="flex gap-2">
                {SEVERITY_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => setSeverity(level.value)}
                    className={`flex-1 p-3 rounded-xl text-center border transition-all ${
                      severity === level.value
                        ? level.color === "red" ? "border-rose-500 bg-rose-50"
                          : level.color === "orange" ? "border-orange-500 bg-orange-50"
                          : "border-yellow-500 bg-yellow-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <p className="font-medium text-slate-900 text-sm">{level.label}</p>
                    <p className="text-xs text-slate-500">{level.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Description *</label>
              <textarea
                className="input-field min-h-[120px]"
                placeholder="Describe your concern in detail (minimum 50 characters)..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <p className="text-xs text-slate-500 mt-1">{description.length}/50 minimum characters</p>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Send To *</label>
              <div className="space-y-2">
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyRmt}
                    onChange={(e) => setNotifyRmt(e.target.checked)}
                    className="rounded border-slate-300 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">RMT (Required — always notified)</span>
                </label>
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyPsc}
                    onChange={(e) => setNotifyPsc(e.target.checked)}
                    className="rounded border-slate-300 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">PSC (tick if concern is serious enough for PSC)</span>
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowConcernModal(false)}
                className="btn-secondary"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitConcern}
                className="btn-primary flex items-center gap-2"
                disabled={submitting || !concernType || !severity || description.length < 50}
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                Submit Concern
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
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Action</th>
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
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleRaiseConcern(project)}
                        className="text-amber-600 hover:text-amber-700 text-xs font-medium flex items-center gap-1"
                      >
                        <Flag size={12} />
                        Raise Concern
                      </button>
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
        <h3 className="text-lg font-bold text-slate-900 mb-4">My Concerns ({myConcerns.length})</h3>
        {myConcerns.length === 0 ? (
          <p className="text-slate-500">No concerns raised yet.</p>
        ) : (
          <div className="space-y-2">
            {myConcerns.slice(0, 5).map((concern: any) => (
              <div key={concern.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                <div>
                  <span className="font-medium text-slate-900 text-sm">{concern.id}</span>
                  <span className={`ml-2 px-2 py-0.5 rounded text-[10px] font-bold ${
                    concern.severity === "high" ? "bg-rose-100 text-rose-700" :
                    concern.severity === "medium" ? "bg-orange-100 text-orange-700" :
                    "bg-yellow-100 text-yellow-700"
                  }`}>
                    {concern.severity.toUpperCase()}
                  </span>
                  <p className="text-xs text-slate-500 mt-1">{concern.description?.slice(0, 80)}...</p>
                </div>
                <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                  concern.status === "resolved" ? "bg-emerald-100 text-emerald-700" :
                  "bg-amber-100 text-amber-700"
                }`}>
                  {concern.status}
                </span>
              </div>
            ))}
          </div>
        )}
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
        </div>
      </div>
    </div>
  );
}

export function DoeRegionalMap({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [showConcernModal, setShowConcernModal] = useState(false);
  const [selectedInstallation, setSelectedInstallation] = useState<any>(null);
  const [concernType, setConcernType] = useState("");
  const [severity, setSeverity] = useState("");
  const [description, setDescription] = useState("");
  const [notifyRmt, setNotifyRmt] = useState(true);
  const [notifyPsc, setNotifyPsc] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map(d => d.trim()).filter(Boolean);
  }, [currentUser]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  const loadData = async () => {
    setLoading(true);
    try {
      console.log("DoeRegionalMap: Loading projects...");
      const list = await fetchProjects();
      console.log("DoeRegionalMap: Got projects:", list.length);
      const filtered = list.filter((p: Project) => {
        if (userDistricts.length === 0) return true;
        const projectDistrict = p.district || p.region || "";
        return userDistricts.some(d => projectDistrict.toLowerCase().includes(d.toLowerCase()));
      });
      console.log("DoeRegionalMap: Filtered projects:", filtered.length, "for districts:", userDistricts);
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

  const handleFlagInstallation = (installation: any) => {
    console.log("Flag installation clicked:", installation);
    console.log("Installation ID:", installation?.id);
    console.log("Project ID:", installation?.projectId);
    setSelectedInstallation(installation);
    setShowConcernModal(true);
  };

  const handleSubmitConcern = async () => {
    if (!concernType || !severity || !description.trim() || description.length < 50) {
      alert("Please fill in all required fields. Description must be at least 50 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await createConcern({
        concern_type: concernType,
        severity: severity,
        linked_project: selectedInstallation?.projectId,
        linked_installation: selectedInstallation?.id,
        description: description,
        notify_rmt: notifyRmt,
        notify_psc: notifyPsc,
      });
      alert("Concern submitted successfully!");
      setShowConcernModal(false);
      setSelectedInstallation(null);
      setConcernType("");
      setSeverity("");
      setDescription("");
      setNotifyRmt(true);
      setNotifyPsc(false);
      void loadData();
    } catch (err) {
      console.error("Failed to submit concern:", err);
      alert("Failed to submit concern. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

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
      {showConcernModal && selectedInstallation && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999] overflow-y-auto">
          <div className="bg-white rounded-2xl p-6 max-w-2xl w-full mx-4 my-8 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Flag size={20} className="text-amber-600" />
                Flag This Installation
              </h3>
              <button onClick={() => setShowConcernModal(false)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>

            <div className="bg-slate-50 rounded-xl p-3 mb-4 text-sm">
              <p className="font-medium text-slate-900">
                Installation: {selectedInstallation.id}
              </p>
              <p className="text-slate-500">
                Project: {selectedInstallation.projectId} — {selectedInstallation.vendorName} — {selectedInstallation.district}
              </p>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Concern Type *</label>
              <div className="grid grid-cols-2 gap-2">
                {CONCERN_TYPES.map((type) => (
                  <button
                    key={type.value}
                    onClick={() => setConcernType(type.value)}
                    className={`p-3 rounded-xl text-left border transition-all ${
                      concernType === type.value
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <p className="font-medium text-slate-900 text-sm">{type.label}</p>
                    <p className="text-xs text-slate-500">{type.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Severity *</label>
              <div className="flex gap-2">
                {SEVERITY_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => setSeverity(level.value)}
                    className={`flex-1 p-3 rounded-xl text-center border transition-all ${
                      severity === level.value
                        ? level.color === "red" ? "border-rose-500 bg-rose-50"
                          : level.color === "orange" ? "border-orange-500 bg-orange-50"
                          : "border-yellow-500 bg-yellow-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <p className="font-medium text-slate-900 text-sm">{level.label}</p>
                    <p className="text-xs text-slate-500">{level.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Description *</label>
              <textarea
                className="input-field min-h-[120px]"
                placeholder="Describe your concern in detail (minimum 50 characters)..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <p className="text-xs text-slate-500 mt-1">{description.length}/50 minimum characters</p>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Send To *</label>
              <div className="space-y-2">
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyRmt}
                    onChange={(e) => setNotifyRmt(e.target.checked)}
                    className="rounded border-slate-300 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">RMT (Required — always notified)</span>
                </label>
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyPsc}
                    onChange={(e) => setNotifyPsc(e.target.checked)}
                    className="rounded border-slate-300 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">PSC (tick if concern is serious enough for PSC)</span>
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowConcernModal(false)}
                className="btn-secondary"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitConcern}
                className="btn-primary flex items-center gap-2"
                disabled={submitting || !concernType || !severity || description.length < 50}
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                Submit Concern
              </button>
            </div>
          </div>
        </div>
      )}

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
          GIS map filtered to your region. All installations in assigned districts. Click on any installation marker to see details or flag concerns.
        </p>
        <GisInstallationsMap
          height="600px"
          onFlagInstallation={handleFlagInstallation}
        />
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