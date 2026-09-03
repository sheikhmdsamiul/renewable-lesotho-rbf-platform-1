import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Clock,
  Download,
  FileText,
  Filter,
  FolderKanban,
  History,
  Loader2,
  Map,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
  AlertCircle,
  XCircle,
  FileSearch,
  CreditCard,
  Building2,
  X,
  TrendingUp,
  Shield,
  Paperclip,
  Users,
  Calendar,
  BarChart3,
  Banknote,
} from "lucide-react";
import {
  fetchProjects,
  fetchSystemAuditLogs,
  fetchAnomalyFlags,
  fetchAuditLogs,
  fetchProspectSyncLogs,
  fetchPaymentClaims,
  fetchProjectsSummary,
  fetchProspectSyncSummary,
  exportSystemAuditLogs,
  API_BASE,
  fetchAuditFindings,
  createAuditFinding,
  fetchPortfolioKpiSummary,
  fetchProjectKpiSummary,
  fetchConcerns,
} from "../api";
import {
  AuditLog,
  AnomalyFlag,
  Project,
  ProjectKpiSummary,
  PaymentClaim,
  ProspectSyncLog,
  UserRole,
  FindingCategory,
  RiskLevel,
  PortfolioKpiSummary,
  AuditFinding,
  Concern,
} from "../types";
import KpiDashboard from "./KpiDashboard";

const FINDING_CATEGORIES = [
  { value: "payment_compliance", label: "Payment Compliance", desc: "Payment made without required KPI conditions" },
  { value: "approval_chain_violation", label: "Approval Chain Violation", desc: "Payment approved without full chain" },
  { value: "data_integrity", label: "Data Integrity", desc: "Data mismatch between system and Prospect" },
  { value: "gps_fraud", label: "GPS / Location Fraud", desc: "Suspicious GPS patterns or location fraud" },
  { value: "kpi_manipulation", label: "KPI Manipulation", desc: "KPI data appears manipulated or fabricated" },
  { value: "document_irregularity", label: "Document Irregularity", desc: "Missing, forged, or inconsistent documents" },
  { value: "process_violation", label: "Process Violation", desc: "System process was bypassed or overridden" },
  { value: "conflict_of_interest", label: "Conflict of Interest", desc: "Potential conflict between actors" },
  { value: "other", label: "Other Compliance Issue", desc: "Other compliance issue" },
];

const RISK_LEVELS = [
  { value: "observation", label: "Observation", desc: "Minor issue, note for record", color: "yellow" },
  { value: "minor", label: "Minor Finding", desc: "Issue found, corrective action needed", color: "orange" },
  { value: "major", label: "Major Finding", desc: "Serious breach, immediate action required", color: "red" },
  { value: "critical", label: "Critical", desc: "Fraud suspected, escalate immediately", color: "rose" },
];

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

const formatRelativeTime = (value?: string | null) => {
  if (!value) return "Never";
  const delta = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(delta)) return "Unknown";
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
};

const saveBlob = (blob: Blob, filename: string) => {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
};

export function AuditorDashboard({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
  const [anomalyFlags, setAnomalyFlags] = useState<AnomalyFlag[]>([]);
  const [syncLogs, setSyncLogs] = useState<ProspectSyncLog[]>([]);
  const [kpiSummary, setKpiSummary] = useState<PortfolioKpiSummary | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projList, findingsData, anomalyData, syncData, kpi] = await Promise.all([
        fetchProjects(),
        fetchAuditFindings(),
        fetchAnomalyFlags({}),
        fetchProspectSyncLogs({ pageSize: 100 }),
        fetchPortfolioKpiSummary(),
      ]);
      setProjects(projList);
      setFindings(findingsData);
      setAnomalyFlags(anomalyData);
      setSyncLogs(syncData);
      setKpiSummary(kpi);
    } catch (err) {
      console.error("Failed to load auditor dashboard:", err);
      setError("Failed to load dashboard data. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const summary = useMemo(() => {
    const totalProjects = projects.length;
    const projectsWithFlags = projects.filter(p => (p.unresolvedFlagCount || 0) > 0).length;

    const unresolvedAnomalies = anomalyFlags.filter(a => !a.isResolved).length;
    const resolvedAnomalies = anomalyFlags.filter(a => a.isResolved).length;

    const openFindings = findings.filter((f: any) => f.status === "open").length;
    const criticalFindings = findings.filter((f: any) => f.riskLevel === "critical").length;

    const syncSuccess = syncLogs.filter(l => l.status === "Success").length;
    const syncFailed = syncLogs.filter(l => l.status === "Failed").length;
    const syncTotal = syncLogs.length;
    const syncSuccessRate = syncTotal > 0 ? Math.round((syncSuccess / syncTotal) * 100) : 0;

    return {
      totalProjects,
      projectsWithFlags,
      unresolvedAnomalies,
      resolvedAnomalies,
      openFindings,
      criticalFindings,
      syncSuccess,
      syncFailed,
      syncTotal,
      syncSuccessRate,
    };
  }, [projects, anomalyFlags, findings, syncLogs]);

  const flaggedProjects = useMemo(() => {
    return projects
      .filter(p => (p.unresolvedFlagCount || 0) > 0)
      .sort((a, b) => (b.unresolvedFlagCount || 0) - (a.unresolvedFlagCount || 0))
      .slice(0, 8);
  }, [projects]);

  const recentFindings = useMemo(() => {
    return [...findings]
      .sort((a: any, b: any) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime())
      .slice(0, 6);
  }, [findings]);

  const getSeverityIcon = (severity: string | undefined) => {
    if (severity === "critical") return <AlertCircle size={14} className="text-rose-600" />;
    if (severity === "major") return <AlertTriangle size={14} className="text-rose-500" />;
    if (severity === "minor") return <AlertTriangle size={14} className="text-orange-500" />;
    return <AlertCircle size={14} className="text-amber-500" />;
  };

  const getSeverityBadge = (severity: string | undefined) => {
    if (severity === "critical") return "bg-rose-600 text-white";
    if (severity === "major") return "bg-rose-500 text-white";
    if (severity === "minor") return "bg-orange-500 text-white";
    return "bg-amber-400 text-amber-900";
  };

  const getStatusBadge = (status: string | undefined) => {
    if (status === "resolved") return "bg-emerald-100 text-emerald-700";
    if (status === "open") return "bg-amber-100 text-amber-700";
    return "bg-slate-100 text-slate-600";
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Auditor Portal</h1>
            <p className="text-sm text-slate-500">Audit Oversight Dashboard</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="rounded-xl bg-slate-50 p-4 animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-24 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-16" />
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-slate-50 p-6 animate-pulse">
          <div className="h-4 bg-slate-200 rounded w-48 mb-4" />
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="h-12 bg-slate-200 rounded" />)}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-10 text-center">
        <AlertCircle size={40} className="mx-auto text-rose-400 mb-3" />
        <p className="text-slate-700 font-medium mb-1">{error}</p>
        <button onClick={() => void loadData()} className="btn-secondary mt-3 flex items-center gap-2 mx-auto">
          <RefreshCw size={16} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Auditor Portal</h1>
          <p className="text-sm text-slate-500">Audit Oversight Dashboard — compliance monitoring, anomaly tracking, and finding management</p>
        </div>
        <button onClick={() => void handleRefresh()} className="btn-secondary flex items-center gap-2" disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <button
          onClick={() => onNavigate?.("projects")}
          className="rounded-xl bg-slate-50 p-4 border border-slate-200 hover:border-slate-300 hover:bg-slate-100 transition-all text-left"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Projects</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{summary.totalProjects}</p>
          <p className="text-xs text-slate-400 mt-1">{summary.projectsWithFlags} with flags</p>
        </button>
        <button
          onClick={() => onNavigate?.("anomaly_report")}
          className="rounded-xl bg-rose-50 p-4 border border-rose-200 hover:border-rose-300 hover:bg-rose-100 transition-all text-left"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Unresolved Anomalies</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">{summary.unresolvedAnomalies}</p>
          <p className="text-xs text-slate-400 mt-1">{summary.resolvedAnomalies} resolved</p>
        </button>
        <button
          onClick={() => onNavigate?.("audit_findings")}
          className="rounded-xl bg-amber-50 p-4 border border-amber-200 hover:border-amber-300 hover:bg-amber-100 transition-all text-left"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Open Audit Findings</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{summary.openFindings}</p>
          <p className="text-xs text-rose-500 mt-1">{summary.criticalFindings} critical</p>
        </button>
        <button
          onClick={() => onNavigate?.("projects")}
          className="rounded-xl bg-purple-50 p-4 border border-purple-200 hover:border-purple-300 hover:bg-purple-100 transition-all text-left"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-purple-600">Projects with Flags</p>
          <p className="mt-2 text-3xl font-bold text-purple-700">{summary.projectsWithFlags}</p>
          <p className="text-xs text-slate-400 mt-1">of {summary.totalProjects} total</p>
        </button>
        <button
          onClick={() => onNavigate?.("prospect_sync")}
          className="rounded-xl bg-emerald-50 p-4 border border-emerald-200 hover:border-emerald-300 hover:bg-emerald-100 transition-all text-left"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Prospect Sync Rate</p>
          <p className="mt-2 text-3xl font-bold text-emerald-700">{summary.syncSuccessRate}%</p>
          <p className="text-xs text-rose-500 mt-1">{summary.syncFailed} failed</p>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <ShieldCheck size={18} className="text-purple-600" /> Project Health
            </h3>
            <button onClick={() => onNavigate?.("projects")} className="text-sm text-purple-600 hover:text-purple-700 flex items-center gap-1 font-medium">
              View all <ChevronRight size={14} />
            </button>
          </div>
          {flaggedProjects.length === 0 ? (
            <div className="bg-emerald-50 rounded-xl p-6 text-center border border-emerald-200">
              <CheckCircle2 size={32} className="mx-auto text-emerald-500 mb-2" />
              <p className="font-medium text-emerald-700">No projects with unresolved flags</p>
              <p className="text-sm text-emerald-600">All projects are within compliance thresholds</p>
            </div>
          ) : (
            <div className="space-y-3">
              {flaggedProjects.map((project) => {
                const progress = project.totalMilestones
                  ? Math.round(((project.completedMilestones || 0) / project.totalMilestones) * 100)
                  : 0;
                return (
                  <div key={project.id} className="rounded-xl border border-slate-200 p-3 hover:bg-slate-50 transition-colors">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <span className="font-medium text-slate-900 text-sm">{project.projectReference || `PRJ-${project.id}`}</span>
                        <span className="text-xs text-slate-500 ml-2">{project.vendorName || "—"}</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700">
                        {project.unresolvedFlagCount || 0} flag{(project.unresolvedFlagCount || 0) !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-500">
                      <span>{project.assignedDistrict || project.region || "—"}</span>
                      <span>{project.techType || "—"}</span>
                      <div className="flex-1">
                        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-purple-500 rounded-full" style={{ width: `${Math.min(progress, 100)}%` }} />
                        </div>
                      </div>
                      <span className="text-slate-400">{progress}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <FileText size={18} className="text-amber-600" /> Recent Audit Findings
            </h3>
            <button onClick={() => onNavigate?.("audit_findings")} className="text-sm text-amber-600 hover:text-amber-700 flex items-center gap-1 font-medium">
              View all <ChevronRight size={14} />
            </button>
          </div>
          {recentFindings.length === 0 ? (
            <div className="bg-slate-50 rounded-xl p-6 text-center border border-slate-200">
              <FileText size={32} className="mx-auto text-slate-300 mb-2" />
              <p className="font-medium text-slate-500">No audit findings raised yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {recentFindings.map((finding: any) => (
                <div key={finding.id} className="rounded-xl border border-slate-200 p-3 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      {getSeverityIcon(finding.riskLevel)}
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${getSeverityBadge(finding.riskLevel)}`}>
                        {finding.riskLevel?.toUpperCase()}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${getStatusBadge(finding.status)}`}>
                        {finding.status?.replace(/_/g, " ")}
                      </span>
                    </div>
                    <span className="text-xs text-slate-400">{formatRelativeTime(finding.createdAt)}</span>
                  </div>
                  <p className="text-sm text-slate-700 line-clamp-2 mt-1">{finding.description}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span>{finding.findingCategory?.replace(/_/g, " ")}</span>
                    {finding.linkedProject && <span>PRJ-{finding.linkedProject}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="card p-6">
          <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Activity size={18} className="text-blue-600" /> Anomaly Breakdown
          </h3>
          {anomalyFlags.length === 0 ? (
            <p className="text-sm text-slate-500">No anomaly flags in system.</p>
          ) : (
            <div className="space-y-3">
              {(() => {
                const byType: Record<string, { total: number; unresolved: number }> = anomalyFlags.reduce((acc, f) => {
                  const t = f.flagType || "Unknown";
                  if (!acc[t]) acc[t] = { total: 0, unresolved: 0 };
                  acc[t].total++;
                  if (!f.isResolved) acc[t].unresolved++;
                  return acc;
                }, {} as Record<string, { total: number; unresolved: number }>);
                return Object.entries(byType)
                  .sort(([, a], [, b]) => b.unresolved - a.unresolved)
                  .slice(0, 6)
                  .map(([type, stats]) => (
                    <div key={type} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                      <div>
                        <p className="text-sm font-medium text-slate-900">{type}</p>
                        <p className="text-xs text-slate-500">{stats.total} total</p>
                      </div>
                      {stats.unresolved > 0 ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700">{stats.unresolved} open</span>
                      ) : (
                        <CheckCircle2 size={14} className="text-emerald-500" />
                      )}
                    </div>
                  ));
              })()}
            </div>
          )}
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
            <History size={18} className="text-teal-600" /> Prospect Sync Status
          </h3>
          {syncLogs.length === 0 ? (
            <p className="text-sm text-slate-500">No sync logs recorded.</p>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg bg-emerald-50 p-3 text-center">
                  <p className="text-lg font-bold text-emerald-700">{summary.syncSuccess}</p>
                  <p className="text-[10px] font-bold uppercase text-emerald-600">Success</p>
                </div>
                <div className="rounded-lg bg-rose-50 p-3 text-center">
                  <p className="text-lg font-bold text-rose-700">{summary.syncFailed}</p>
                  <p className="text-[10px] font-bold uppercase text-rose-600">Failed</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-3 text-center">
                  <p className="text-lg font-bold text-slate-700">{summary.syncTotal}</p>
                  <p className="text-[10px] font-bold uppercase text-slate-600">Total</p>
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-slate-600">Success rate</span>
                  <span className="font-bold text-slate-900">{summary.syncSuccessRate}%</span>
                </div>
                <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${summary.syncSuccessRate >= 95 ? "bg-emerald-500" : summary.syncSuccessRate >= 80 ? "bg-amber-500" : "bg-rose-500"}`}
                    style={{ width: `${summary.syncSuccessRate}%` }}
                  />
                </div>
              </div>
              <button onClick={() => onNavigate?.("prospect_sync")} className="w-full text-sm text-teal-600 hover:text-teal-700 flex items-center justify-center gap-1 font-medium py-2 rounded-lg hover:bg-teal-50 transition-colors">
                View full sync log <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
            <FolderKanban size={18} className="text-indigo-600" /> Quick Actions
          </h3>
          <div className="space-y-2">
            <button onClick={() => onNavigate?.("audit_logs")} className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50 hover:border-slate-300 transition-all text-left">
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                <FileText size={18} className="text-blue-600" />
              </div>
              <div>
                <p className="font-medium text-slate-900 text-sm">Audit Logs</p>
                <p className="text-xs text-slate-500">Full system audit trail</p>
              </div>
              <ChevronRight size={14} className="text-slate-400 ml-auto" />
            </button>
            <button onClick={() => onNavigate?.("anomaly_report")} className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50 hover:border-slate-300 transition-all text-left">
              <div className="w-10 h-10 rounded-lg bg-rose-50 flex items-center justify-center">
                <AlertTriangle size={18} className="text-rose-600" />
              </div>
              <div>
                <p className="font-medium text-slate-900 text-sm">Anomaly Report</p>
                <p className="text-xs text-slate-500">All anomaly flags across projects</p>
              </div>
              <ChevronRight size={14} className="text-slate-400 ml-auto" />
            </button>
            <button onClick={() => onNavigate?.("audit_findings")} className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50 hover:border-slate-300 transition-all text-left">
              <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
                <Shield size={18} className="text-amber-600" />
              </div>
              <div>
                <p className="font-medium text-slate-900 text-sm">Audit Findings</p>
                <p className="text-xs text-slate-500">Raise and manage findings</p>
              </div>
              <ChevronRight size={14} className="text-slate-400 ml-auto" />
            </button>
            <button onClick={() => onNavigate?.("claims_audit")} className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 hover:bg-slate-50 hover:border-slate-300 transition-all text-left">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                <CreditCard size={18} className="text-emerald-600" />
              </div>
              <div>
                <p className="font-medium text-slate-900 text-sm">Claims Audit</p>
                <p className="text-xs text-slate-500">Payment chain audit trail</p>
              </div>
              <ChevronRight size={14} className="text-slate-400 ml-auto" />
            </button>
          </div>
        </div>
      </div>

      {kpiSummary && (
        <div className="card p-6">
          <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-emerald-600" /> Portfolio KPI Summary
          </h3>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <p className="text-xs font-bold uppercase text-slate-500">Total Projects</p>
              <p className="text-xl font-bold text-slate-900 mt-1">{kpiSummary.total_projects}</p>
            </div>
            <div className="rounded-xl bg-emerald-50 p-3 text-center">
              <p className="text-xs font-bold uppercase text-emerald-600">Installations Verified</p>
              <p className="text-xl font-bold text-emerald-700 mt-1">{kpiSummary.total_verified}</p>
            </div>
            <div className="rounded-xl bg-blue-50 p-3 text-center">
              <p className="text-xs font-bold uppercase text-blue-600">On Track</p>
              <p className="text-xl font-bold text-blue-700 mt-1">{kpiSummary.projects_on_track}</p>
            </div>
            <div className="rounded-xl bg-amber-50 p-3 text-center">
              <p className="text-xs font-bold uppercase text-amber-600">Total Disbursed (LSL)</p>
              <p className="text-xl font-bold text-amber-700 mt-1">{(kpiSummary.total_paid_amount ?? 0).toLocaleString()}</p>
            </div>
            <div className="rounded-xl bg-purple-50 p-3 text-center">
              <p className="text-xs font-bold uppercase text-purple-600">Progress</p>
              <p className="text-xl font-bold text-purple-700 mt-1">{kpiSummary.overall_progress_pct}%</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function AuditorGisMap() {
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const list = await fetchProjects();
      setProjects(list);
    } catch (err) {
      console.error("Failed to load projects:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredProjects = useMemo(() => {
    if (!showFlaggedOnly) return projects;
    return projects.filter(p => (p.unresolvedFlagCount || 0) > 0);
  }, [projects, showFlaggedOnly]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading GIS data...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Auditor GIS Map</h1>
          <p className="text-sm text-slate-500">Full system GIS map (read-only)</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showFlaggedOnly}
              onChange={(e) => setShowFlaggedOnly(e.target.checked)}
              className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-600"
            />
            <span className="text-sm font-medium text-slate-700">Show only flagged installations</span>
          </label>
        </div>
      </div>

      <div className="card p-6">
        <p className="text-sm text-slate-500 mb-4">
          Full system GIS map view. Same as RMT map view but read-only. Use the filter above for targeted audit sampling.
        </p>
        <div className="bg-slate-100 rounded-xl p-8 text-center">
          <Map size={48} className="mx-auto text-slate-400 mb-2" />
          <p className="text-slate-500">Map view shows {filteredProjects.length} projects</p>
          {showFlaggedOnly && (
            <p className="text-sm text-rose-600 mt-2">
              Showing only {filteredProjects.length} projects with flags
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function AuditorKpiDashboard() {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectSummaries, setProjectSummaries] = useState<Record<string, ProjectKpiSummary>>({});
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProjectKpi, setSelectedProjectKpi] = useState<ProjectKpiSummary | null>(null);
  const [loadingKpi, setLoadingKpi] = useState(false);
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterTech, setFilterTech] = useState("all");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const projList = await fetchProjects();
      setProjects(projList);

      const summaries: Record<string, ProjectKpiSummary> = {};
      const results = await Promise.allSettled(
        projList.map(p => fetchProjectKpiSummary(p.id))
      );
      results.forEach((result, idx) => {
        if (result.status === "fulfilled" && result.value) {
          summaries[projList[idx].id] = result.value;
        }
      });
      setProjectSummaries(summaries);
    } catch (err) {
      console.error("Failed to load KPI data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSelectProject = async (projectId: string) => {
    setSelectedProjectId(projectId);
    setLoadingKpi(true);
    try {
      const existing = projectSummaries[projectId];
      if (existing) {
        setSelectedProjectKpi(existing);
      } else {
        const kpi = await fetchProjectKpiSummary(projectId);
        setSelectedProjectKpi(kpi);
      }
    } catch (err) {
      console.error("Failed to load project KPI:", err);
    } finally {
      setLoadingKpi(false);
    }
  };

  const portfolioSummary = useMemo(() => {
    const summaries: ProjectKpiSummary[] = Object.values(projectSummaries);
    if (summaries.length === 0) return null;

    const totalProjects = summaries.length;
    const onTrack = summaries.filter(s => s.installation_progress.on_track).length;
    const behindTarget = totalProjects - onTrack;

    const totalTarget = summaries.reduce((acc, s) => acc + (s.installation_progress.target || 0), 0);
    const totalVerified = summaries.reduce((acc, s) => acc + (s.installation_progress.verified || 0), 0);
    const overallProgress = totalTarget > 0 ? Math.round((totalVerified / totalTarget) * 100) : 0;

    const genderMet = summaries.filter(s => s.gender_kpi.all_gender_kpis_met).length;
    const energyMet = summaries.filter(s => s.energy_kpi.on_track).length;
    const uptimeMet = summaries.filter(s => s.uptime_kpi.met).length;

    const totalMilestoneEligible = summaries.filter(s =>
      Object.values(s.milestone_eligibility).some(m => m.eligible)
    ).length;

    return {
      totalProjects,
      onTrack,
      behindTarget,
      overallProgress,
      genderMet,
      energyMet,
      uptimeMet,
      totalMilestoneEligible,
    };
  }, [projectSummaries]);

  const filteredProjects = useMemo(() => {
    let result = projects;
    if (filterStatus !== "all") {
      result = result.filter(p => p.status === filterStatus);
    }
    if (filterTech !== "all") {
      result = result.filter(p => p.techType === filterTech);
    }
    return result;
  }, [projects, filterStatus, filterTech]);

  const techTypes = useMemo(() => {
    const types = new Set(projects.map(p => p.techType).filter(Boolean));
    return Array.from(types);
  }, [projects]);

  const statuses = useMemo(() => {
    const s = new Set(projects.map(p => p.status).filter(Boolean));
    return Array.from(s);
  }, [projects]);

  if (selectedProjectId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setSelectedProjectId(null); setSelectedProjectKpi(null); }}
            className="btn-secondary flex items-center gap-2"
          >
            <ArrowLeft size={16} /> Back to Portfolio
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              KPI Verification — {selectedProjectKpi?.project?.project_reference || `PRJ-${selectedProjectId}`}
            </h1>
            <p className="text-sm text-slate-500">
              {selectedProjectKpi?.project?.vendor_name} | {selectedProjectKpi?.project?.technology_type} | {selectedProjectKpi?.project?.district}
            </p>
          </div>
        </div>
        {loadingKpi ? (
          <div className="card p-10 text-center text-slate-500">
            <Loader2 size={24} className="animate-spin mx-auto mb-2" />
            Loading project KPI data...
          </div>
        ) : selectedProjectKpi ? (
          <KpiDashboard projectId={selectedProjectId} projectKpi={selectedProjectKpi} />
        ) : (
          <div className="card p-10 text-center text-slate-500">
            <AlertCircle size={24} className="mx-auto text-rose-400 mb-2" />
            Failed to load KPI data for this project.
          </div>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">KPI Dashboard</h1>
            <p className="text-sm text-slate-500">Loading KPI data...</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="rounded-xl bg-slate-50 p-4 animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-24 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-16" />
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-slate-50 p-6 animate-pulse">
          <div className="h-4 bg-slate-200 rounded w-48 mb-4" />
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map(i => <div key={i} className="h-12 bg-slate-200 rounded" />)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">KPI Dashboard</h1>
          <p className="text-sm text-slate-500">Portfolio KPI verification for milestone payment eligibility assessment</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {portfolioSummary && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-4 border border-slate-200">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Overall Progress</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{portfolioSummary.overallProgress}%</p>
            <p className="text-xs text-slate-400 mt-1">{portfolioSummary.totalProjects} projects</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4 border border-emerald-200">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">On Track</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">{portfolioSummary.onTrack}</p>
            <p className="text-xs text-slate-400 mt-1">{portfolioSummary.behindTarget} behind target</p>
          </div>
          <div className="rounded-xl bg-blue-50 p-4 border border-blue-200">
            <p className="text-xs font-bold uppercase tracking-widest text-blue-600">Gender KPI Met</p>
            <p className="mt-2 text-3xl font-bold text-blue-700">{portfolioSummary.genderMet}</p>
            <p className="text-xs text-slate-400 mt-1">{portfolioSummary.totalProjects - portfolioSummary.genderMet} below target</p>
          </div>
          <div className="rounded-xl bg-amber-50 p-4 border border-amber-200">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Milestone Eligible</p>
            <p className="mt-2 text-3xl font-bold text-amber-700">{portfolioSummary.totalMilestoneEligible}</p>
            <p className="text-xs text-slate-400 mt-1">of {portfolioSummary.totalProjects} projects</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {portfolioSummary && (
          <>
            <div className="rounded-xl bg-purple-50 p-3 border border-purple-200 text-center">
              <p className="text-xs font-bold uppercase text-purple-600">Energy On Track</p>
              <p className="text-xl font-bold text-purple-700 mt-1">{portfolioSummary.energyMet}/{portfolioSummary.totalProjects}</p>
            </div>
            <div className="rounded-xl bg-teal-50 p-3 border border-teal-200 text-center">
              <p className="text-xs font-bold uppercase text-teal-600">Uptime Met</p>
              <p className="text-xl font-bold text-teal-700 mt-1">{portfolioSummary.uptimeMet}/{portfolioSummary.totalProjects}</p>
            </div>
          </>
        )}
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <select
            className="input-field"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="all">All Statuses</option>
            {statuses.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            className="input-field"
            value={filterTech}
            onChange={(e) => setFilterTech(e.target.value)}
          >
            <option value="all">All Technologies</option>
            {techTypes.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <div className="flex-1" />
          <span className="text-sm text-slate-500 self-center">
            {filteredProjects.length} project{filteredProjects.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Vendor</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Tech / District</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Progress</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Gender</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Energy</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Uptime</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Milestone</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredProjects.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center">
                  <Activity size={32} className="mx-auto text-slate-300 mb-2" />
                  <p className="text-slate-500 font-medium">No projects found</p>
                </td>
              </tr>
            )}
            {filteredProjects.map((project) => {
              const kpi = projectSummaries[project.id];
              const progress = kpi?.installation_progress;
              const gender = kpi?.gender_kpi;
              const energy = kpi?.energy_kpi;
              const uptime = kpi?.uptime_kpi;
              const milestones = kpi?.milestone_eligibility;
              const hasMilestoneEligible = milestones ? Object.values(milestones as Record<string, { eligible: boolean }>).some(m => m.eligible) : false;

              const progressPct = progress?.progress_pct ?? 0;
              const isOnTrack = progress?.on_track ?? false;

              return (
                <tr
                  key={project.id}
                  className="hover:bg-slate-50 cursor-pointer"
                  onClick={() => void handleSelectProject(project.id)}
                >
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-900 text-sm">{project.projectReference || `PRJ-${project.id}`}</span>
                    <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold ${
                      isOnTrack ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                    }`}>
                      {isOnTrack ? "On Track" : "Behind"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-600">{project.vendorName || "—"}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">
                    <span>{project.techType || "—"}</span>
                    <span className="text-slate-400 mx-1">/</span>
                    <span>{project.assignedDistrict || project.region || "—"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden min-w-[60px]">
                        <div
                          className={`h-full rounded-full ${progressPct >= 70 ? "bg-emerald-500" : progressPct >= 40 ? "bg-amber-500" : "bg-rose-500"}`}
                          style={{ width: `${Math.min(progressPct, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-slate-600 w-10 text-right">{progressPct}%</span>
                    </div>
                    {progress && (
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        {progress.verified}/{progress.target} verified
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {gender ? (
                      <div>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          gender.all_gender_kpis_met ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                        }`}>
                          {gender.all_gender_kpis_met ? "Met" : "Below"}
                        </span>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          F: {gender.female_headed?.percentage ?? 0}% | V: {gender.vulnerable?.percentage ?? 0}%
                        </p>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {energy ? (
                      <div>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          energy.on_track ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                        }`}>
                          {energy.on_track ? "On Track" : "Below"}
                        </span>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          {energy.current_month_kwh?.toLocaleString() ?? 0} / {energy.current_month_target?.toLocaleString() ?? 0} kWh
                        </p>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {uptime ? (
                      <div>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          uptime.met ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                        }`}>
                          {uptime.average_uptime_pct ?? 0}%
                        </span>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          target: {uptime.target_uptime_pct ?? 0}%
                        </p>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {milestones ? (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        hasMilestoneEligible ? "bg-sky-100 text-sky-700" : "bg-slate-100 text-slate-600"
                      }`}>
                        {hasMilestoneEligible ? "Eligible" : "Not Yet"}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
        <h4 className="text-sm font-bold text-blue-800 mb-1 flex items-center gap-2">
          <ShieldCheck size={14} /> Auditor Verification Guide
        </h4>
        <ul className="text-xs text-blue-700 space-y-0.5">
          <li>Click any project row to view detailed KPI data (energy trends, uptime distribution, milestone conditions, gender breakdown).</li>
          <li><strong>Gender targets:</strong> Female-headed households ≥ 50%, Vulnerable groups ≥ 30%, Low-income ≥ 60% (per SRS contractual requirements).</li>
          <li><strong>Milestone eligibility:</strong> A project becomes eligible when installation progress, gender KPIs, uptime, and anomaly flags all meet thresholds.</li>
          <li><strong>Payment workflow:</strong> KPI verification is required before RMT → TAC → PSC approval chain can proceed to disbursement.</li>
        </ul>
      </div>
    </div>
  );
}

export function AuditorAuditLogs() {
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [filters, setFilters] = useState({
    actor: "",
    action: "",
    dateFrom: "",
    dateTo: "",
  });
  const [searchQuery, setSearchQuery] = useState("");

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchSystemAuditLogs(filters);
      setLogs(data);
    } catch (err) {
      console.error("Failed to load audit logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [filters]);

  const filteredLogs = useMemo(() => {
    if (!searchQuery) return logs;
    const q = searchQuery.toLowerCase();
    return logs.filter(l => 
      l.action?.toLowerCase().includes(q) ||
      l.actor?.toLowerCase().includes(q) ||
      l.entityType?.toLowerCase().includes(q)
    );
  }, [logs, searchQuery]);

  const handleExport = async (format: "csv" | "pdf") => {
    try {
      const blob = await exportSystemAuditLogs(format, filters);
      saveBlob(blob, format === "csv" ? "audit_logs.csv" : "audit_logs.pdf");
    } catch (err) {
      console.error("Failed to export:", err);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading audit logs...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Audit Logs</h1>
          <p className="text-sm text-slate-500">Full system audit trail</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => handleExport("csv")} className="btn-secondary flex items-center gap-2 text-sm">
            <Download size={16} /> Export CSV
          </button>
          <button onClick={() => handleExport("pdf")} className="btn-secondary flex items-center gap-2 text-sm">
            <Download size={16} /> Export PDF
          </button>
        </div>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input
              className="input-field pl-9"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <input
            type="date"
            className="input-field"
            value={filters.dateFrom}
            onChange={(e) => setFilters(f => ({ ...f, dateFrom: e.target.value }))}
            placeholder="From date"
          />
          <input
            type="date"
            className="input-field"
            value={filters.dateTo}
            onChange={(e) => setFilters(f => ({ ...f, dateTo: e.target.value }))}
            placeholder="To date"
          />
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Timestamp</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Actor</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Action</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Entity</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredLogs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No audit logs found.
                </td>
              </tr>
            )}
            {filteredLogs.map((log) => (
              <tr key={log.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm text-slate-600">
                  {formatDateTime(log.createdAt)}
                </td>
                <td className="px-4 py-3 text-sm text-slate-900">
                  {log.actor || "—"}
                </td>
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {log.action}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  {log.entityType} #{log.entityId}
                </td>
                <td className="px-4 py-3 text-sm text-slate-500">
                  {log.module || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const FLAG_TYPE_META: Record<string, { label: string; description: string; severity: "critical" | "high" | "medium" | "low"; riskContext: string }> = {
  zero_uptime: {
    label: "Zero Uptime",
    description: "Installation reports zero uptime — system is offline or not generating energy.",
    severity: "critical",
    riskContext: "Indicates total system failure or tampering. Payment claims for this installation should be frozen pending investigation.",
  },
  output_deviation: {
    label: "Output Deviation",
    description: "Energy output deviates significantly from contracted/expected levels.",
    severity: "high",
    riskContext: "May indicate underperformance, equipment degradation, or data manipulation. Cross-check with meter readings and field verification.",
  },
  no_data: {
    label: "No Data",
    description: "No telemetry data received from installation for an extended period.",
    severity: "high",
    riskContext: "Could mean device is offline, SIM/network failure, or deliberate data suppression. Request vendor explanation within 7 days.",
  },
  duplicate_gps: {
    label: "Duplicate GPS",
    description: "Multiple installations share identical GPS coordinates — potential fraudulent duplication.",
    severity: "critical",
    riskContext: "Strong indicator of ghost installations. Cross-reference with field verification photos, customer IDs, and serial numbers. Escalate to RMT.",
  },
  location_mismatch: {
    label: "Location Mismatch",
    description: "Installation GPS coordinates do not match the documented/documented project site location.",
    severity: "high",
    riskContext: "Installation may be outside the contracted tender zone. Verify against tender boundaries and GIS overlays.",
  },
  verification_distance: {
    label: "Verification Distance",
    description: "Field verification was conducted at an unusual distance from the vendor-pinned installation site.",
    severity: "medium",
    riskContext: "May indicate verification was done remotely or the installation was moved. Request clarification from field officer.",
  },
};

const FLAG_SEVERITY_STYLES: Record<string, { bg: string; text: string; icon: string }> = {
  critical: { bg: "bg-rose-50 border-rose-200", text: "text-rose-700", icon: "text-rose-600" },
  high: { bg: "bg-orange-50 border-orange-200", text: "text-orange-700", icon: "text-orange-600" },
  medium: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", icon: "text-amber-600" },
  low: { bg: "bg-slate-50 border-slate-200", text: "text-slate-700", icon: "text-slate-600" },
};

export function AuditorAnomalyReport() {
  const [loading, setLoading] = useState(true);
  const [flags, setFlags] = useState<AnomalyFlag[]>([]);
  const [filterResolved, setFilterResolved] = useState<"all" | "resolved" | "unresolved">("all");
  const [filterType, setFilterType] = useState("all");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [expandedFlag, setExpandedFlag] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const isResolved = filterResolved === "resolved" ? true : filterResolved === "unresolved" ? false : undefined;
      const data = await fetchAnomalyFlags({ isResolved });
      setFlags(data);
    } catch (err) {
      console.error("Failed to load anomaly flags:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [filterResolved]);

  const getFlagSeverity = (flagType: string): "critical" | "high" | "medium" | "low" => {
    return FLAG_TYPE_META[flagType]?.severity ?? "low";
  };

  const filteredFlags = useMemo(() => {
    let result = flags;
    if (filterType !== "all") {
      result = result.filter(f => f.flagType === filterType);
    }
    if (filterSeverity !== "all") {
      result = result.filter(f => getFlagSeverity(f.flagType) === filterSeverity);
    }
    return result;
  }, [flags, filterType, filterSeverity]);

  const summary = useMemo(() => {
    const total = flags.length;
    const resolved = flags.filter(f => f.isResolved).length;
    const unresolved = total - resolved;
    const resolutionRate = total > 0 ? Math.round((resolved / total) * 100) : 0;

    const byType: Record<string, { total: number; resolved: number; unresolved: number }> = {};
    for (const f of flags) {
      const t = f.flagType || "Unknown";
      if (!byType[t]) byType[t] = { total: 0, resolved: 0, unresolved: 0 };
      byType[t].total++;
      if (f.isResolved) byType[t].resolved++;
      else byType[t].unresolved++;
    }

    const criticalCount = flags.filter(f => getFlagSeverity(f.flagType) === "critical" && !f.isResolved).length;
    const highCount = flags.filter(f => getFlagSeverity(f.flagType) === "high" && !f.isResolved).length;

    const unresolvedAges = flags
      .filter(f => !f.isResolved && f.createdAt)
      .map(f => {
        const days = Math.floor((Date.now() - new Date(f.createdAt).getTime()) / 86400000);
        return days;
      });
    const avgAgeDays = unresolvedAges.length > 0
      ? Math.round(unresolvedAges.reduce((a, b) => a + b, 0) / unresolvedAges.length)
      : 0;
    const oldestAgeDays = unresolvedAges.length > 0 ? Math.max(...unresolvedAges) : 0;

    return { total, resolved, unresolved, resolutionRate, byType, criticalCount, highCount, avgAgeDays, oldestAgeDays };
  }, [flags]);

  const handleExport = () => {
    const csv = [
      ["ID", "Installation", "Project", "Flag Type", "Severity", "Description", "Risk Context", "Status", "Age (Days)", "Created At", "Resolved At"].join(","),
      ...filteredFlags.map(f => {
        const meta = FLAG_TYPE_META[f.flagType];
        const age = f.createdAt ? Math.floor((Date.now() - new Date(f.createdAt).getTime()) / 86400000) : "";
        return [
          f.id,
          f.installation,
          f.project,
          f.flagType,
          meta?.severity ?? "low",
          `"${(f.description || meta?.description || "").replace(/"/g, '""')}"`,
          `"${(meta?.riskContext || "").replace(/"/g, '""')}"`,
          f.isResolved ? "Resolved" : "Unresolved",
          age,
          f.createdAt || "",
          f.resolvedAt || "",
        ].join(",");
      })
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, `anomaly_report_${new Date().toISOString().slice(0, 10)}.csv`);
  };

  const getAgeLabel = (createdAt?: string) => {
    if (!createdAt) return "—";
    const days = Math.floor((Date.now() - new Date(createdAt).getTime()) / 86400000);
    if (days === 0) return "Today";
    if (days === 1) return "1 day";
    return `${days} days`;
  };

  const getAgeColor = (createdAt?: string, isResolved?: boolean) => {
    if (isResolved) return "text-emerald-600";
    if (!createdAt) return "text-slate-400";
    const days = Math.floor((Date.now() - new Date(createdAt).getTime()) / 86400000);
    if (days <= 3) return "text-slate-600";
    if (days <= 7) return "text-amber-600";
    return "text-rose-600";
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Anomaly Report</h1>
            <p className="text-sm text-slate-500">Loading anomaly flags...</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="rounded-xl bg-slate-50 p-4 animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-24 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-16" />
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-slate-50 p-6 animate-pulse">
          <div className="h-4 bg-slate-200 rounded w-48 mb-4" />
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="h-16 bg-slate-200 rounded" />)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Anomaly Report</h1>
          <p className="text-sm text-slate-500">System-generated anomaly flags for compliance review and risk assessment</p>
        </div>
        <button onClick={handleExport} className="btn-secondary flex items-center gap-2">
          <Download size={16} /> Export CSV
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl bg-slate-50 p-4 border border-slate-200">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Flags</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{summary.total}</p>
          <p className="text-xs text-slate-400 mt-1">{summary.resolutionRate}% resolved</p>
        </div>
        <div className="rounded-xl bg-rose-50 p-4 border border-rose-200">
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Critical (Unresolved)</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">{summary.criticalCount}</p>
          <p className="text-xs text-slate-400 mt-1">duplicate GPS, zero uptime</p>
        </div>
        <div className="rounded-xl bg-orange-50 p-4 border border-orange-200">
          <p className="text-xs font-bold uppercase tracking-widest text-orange-600">High Risk (Unresolved)</p>
          <p className="mt-2 text-3xl font-bold text-orange-700">{summary.highCount}</p>
          <p className="text-xs text-slate-400 mt-1">output deviation, no data, location mismatch</p>
        </div>
        <div className="rounded-xl bg-amber-50 p-4 border border-amber-200">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Avg. Age (Open)</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{summary.avgAgeDays}d</p>
          <p className="text-xs text-rose-500 mt-1">oldest: {summary.oldestAgeDays}d</p>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-sm font-bold uppercase text-slate-500 mb-4">Flag Type Breakdown</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(FLAG_TYPE_META).map(([key, meta]) => {
            const stats = summary.byType[key];
            const count = stats?.total ?? 0;
            const unresolvedCount = stats?.unresolved ?? 0;
            const sev = FLAG_SEVERITY_STYLES[meta.severity];
            return (
              <div key={key} className={`rounded-xl border p-4 ${sev.bg}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-sm font-bold ${sev.text}`}>{meta.label}</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                    meta.severity === "critical" ? "bg-rose-100 text-rose-700" :
                    meta.severity === "high" ? "bg-orange-100 text-orange-700" :
                    meta.severity === "medium" ? "bg-amber-100 text-amber-700" :
                    "bg-slate-100 text-slate-600"
                  }`}>
                    {meta.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-600 mb-2">{meta.description}</p>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">{count} total</span>
                  {unresolvedCount > 0 ? (
                    <span className="font-bold text-rose-600">{unresolvedCount} unresolved</span>
                  ) : count > 0 ? (
                    <span className="text-emerald-600">All resolved</span>
                  ) : (
                    <span className="text-slate-400">None detected</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <select
            className="input-field"
            value={filterResolved}
            onChange={(e) => setFilterResolved(e.target.value as any)}
          >
            <option value="all">All Status</option>
            <option value="unresolved">Unresolved</option>
            <option value="resolved">Resolved</option>
          </select>
          <select
            className="input-field"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="all">All Types</option>
            {Object.entries(FLAG_TYPE_META).map(([key, meta]) => (
              <option key={key} value={key}>{meta.label}</option>
            ))}
          </select>
          <select
            className="input-field"
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <div className="flex-1" />
          <span className="text-sm text-slate-500 self-center">
            Showing {filteredFlags.length} of {flags.length} flags
          </span>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Type</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Installation</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Description</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Age</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredFlags.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center">
                  <CheckCircle2 size={32} className="mx-auto text-emerald-400 mb-2" />
                  <p className="text-slate-500 font-medium">No anomaly flags found</p>
                  <p className="text-sm text-slate-400">
                    {filterResolved === "all" && filterType === "all" && filterSeverity === "all"
                      ? "No anomalies have been detected in the system."
                      : "Try adjusting your filters to see more results."}
                  </p>
                </td>
              </tr>
            )}
            {filteredFlags.map((flag) => {
              const meta = FLAG_TYPE_META[flag.flagType];
              const severity = meta?.severity ?? "low";
              const sev = FLAG_SEVERITY_STYLES[severity];
              const isExpanded = expandedFlag === flag.id;
              return (
                <React.Fragment key={flag.id}>
                  <tr
                    className="hover:bg-slate-50 cursor-pointer"
                    onClick={() => setExpandedFlag(isExpanded ? null : flag.id)}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {severity === "critical" ? (
                          <AlertCircle size={14} className={sev.icon} />
                        ) : severity === "high" ? (
                          <AlertTriangle size={14} className={sev.icon} />
                        ) : severity === "medium" ? (
                          <AlertTriangle size={14} className={sev.icon} />
                        ) : (
                          <AlertCircle size={14} className={sev.icon} />
                        )}
                        <div>
                          <p className={`text-sm font-medium ${sev.text}`}>{meta?.label ?? flag.flagType}</p>
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            severity === "critical" ? "bg-rose-100 text-rose-700" :
                            severity === "high" ? "bg-orange-100 text-orange-700" :
                            severity === "medium" ? "bg-amber-100 text-amber-700" :
                            "bg-slate-100 text-slate-600"
                          }`}>
                            {severity}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm font-mono text-slate-600">
                      INS-{flag.installation}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">
                      PRJ-{flag.project}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600 max-w-xs truncate">
                      {flag.description || meta?.description || "—"}
                    </td>
                    <td className="px-4 py-3">
                      {flag.isResolved ? (
                        <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 flex items-center gap-1 w-fit">
                          <CheckCircle2 size={10} /> Resolved
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700 flex items-center gap-1 w-fit">
                          <AlertCircle size={10} /> Open
                        </span>
                      )}
                    </td>
                    <td className={`px-4 py-3 text-sm font-medium ${getAgeColor(flag.createdAt, flag.isResolved)}`}>
                      {getAgeLabel(flag.createdAt)}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">
                      {formatDateTime(flag.createdAt)}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={7} className="px-4 py-0">
                        <div className="bg-slate-50 rounded-xl p-4 my-2 border border-slate-200">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <div>
                              <h4 className="text-xs font-bold uppercase text-slate-500 mb-2">Risk Assessment</h4>
                              <p className="text-sm text-slate-700">{meta?.riskContext || "No risk context available for this flag type."}</p>
                            </div>
                            <div>
                              <h4 className="text-xs font-bold uppercase text-slate-500 mb-2">Flag Details</h4>
                              <div className="space-y-1 text-sm">
                                <p className="text-slate-600">
                                  <span className="font-medium text-slate-900">Flag ID:</span> {flag.id}
                                </p>
                                <p className="text-slate-600">
                                  <span className="font-medium text-slate-900">Installation:</span> INS-{flag.installation}
                                </p>
                                <p className="text-slate-600">
                                  <span className="font-medium text-slate-900">Project:</span> PRJ-{flag.project}
                                </p>
                                <p className="text-slate-600">
                                  <span className="font-medium text-slate-900">Created:</span> {formatDateTime(flag.createdAt)}
                                </p>
                                {flag.resolvedAt && (
                                  <p className="text-slate-600">
                                    <span className="font-medium text-slate-900">Resolved:</span> {formatDateTime(flag.resolvedAt)}
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                          {flag.description && (
                            <div className="mt-3 pt-3 border-t border-slate-200">
                              <h4 className="text-xs font-bold uppercase text-slate-500 mb-1">System Description</h4>
                              <p className="text-sm text-slate-700">{flag.description}</p>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {flags.length > 0 && (
        <div className="card p-6">
          <h3 className="text-sm font-bold uppercase text-slate-500 mb-4">Unresolved Flags by Type (Severity排序)</h3>
          <div className="space-y-2">
            {Object.entries(FLAG_TYPE_META)
              .filter(([key]) => (summary.byType[key]?.unresolved ?? 0) > 0)
              .sort(([, a], [, b]) => {
                const order = { critical: 0, high: 1, medium: 2, low: 3 };
                return order[a.severity] - order[b.severity];
              })
              .map(([key, meta]) => {
                const stats = summary.byType[key];
                if (!stats || stats.unresolved === 0) return null;
                const sev = FLAG_SEVERITY_STYLES[meta.severity];
                return (
                  <div key={key} className={`rounded-xl border p-3 ${sev.bg}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {meta.severity === "critical" ? (
                          <AlertCircle size={16} className={sev.icon} />
                        ) : (
                          <AlertTriangle size={16} className={sev.icon} />
                        )}
                        <div>
                          <span className={`text-sm font-bold ${sev.text}`}>{meta.label}</span>
                          <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            meta.severity === "critical" ? "bg-rose-100 text-rose-700" :
                            meta.severity === "high" ? "bg-orange-100 text-orange-700" :
                            meta.severity === "medium" ? "bg-amber-100 text-amber-700" :
                            "bg-slate-100 text-slate-600"
                          }`}>{meta.severity}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-slate-500">{stats.unresolved} open</span>
                        <span className="text-slate-400">{stats.resolved} resolved</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            {Object.entries(FLAG_TYPE_META).filter(([key]) => (summary.byType[key]?.unresolved ?? 0) > 0).length === 0 && (
              <div className="bg-emerald-50 rounded-xl p-4 text-center border border-emerald-200">
                <CheckCircle2 size={24} className="mx-auto text-emerald-500 mb-1" />
                <p className="text-sm font-medium text-emerald-700">All anomaly flags have been resolved</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function AuditorClaimsAudit() {
  const [loading, setLoading] = useState(true);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyFlag[]>([]);
  const [auditFindings, setAuditFindings] = useState<AuditFinding[]>([]);
  const [selectedClaim, setSelectedClaim] = useState<PaymentClaim | null>(null);
  const [filterProject, setFilterProject] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 10;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [claimsData, projectsData, anomalyData, findingsData] = await Promise.allSettled([
        fetchPaymentClaims({ pageSize: 500 }),
        fetchProjects(),
        fetchAnomalyFlags(),
        fetchAuditFindings(),
      ]);
      if (claimsData.status === "fulfilled") setClaims(claimsData.value);
      if (projectsData.status === "fulfilled") setProjects(projectsData.value);
      if (anomalyData.status === "fulfilled") setAnomalies(anomalyData.value);
      if (findingsData.status === "fulfilled") setAuditFindings(findingsData.value);
    } catch (err) {
      console.error("Failed to load claims audit data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const projectMap = useMemo(() => {
    const map: Record<string, Project> = {};
    projects.forEach(p => { map[p.id] = p; });
    return map;
  }, [projects]);

  const anomalyCountByProject = useMemo(() => {
    const counts: Record<string, number> = {};
    anomalies.forEach(a => { counts[a.project] = (counts[a.project] || 0) + 1; });
    return counts;
  }, [anomalies]);

  const findingsByClaim = useMemo(() => {
    const map: Record<string, AuditFinding[]> = {};
    auditFindings.forEach(f => {
      if (f.linkedClaim) {
        if (!map[f.linkedClaim]) map[f.linkedClaim] = [];
        map[f.linkedClaim].push(f);
      }
    });
    return map;
  }, [auditFindings]);

  const filteredClaims = useMemo(() => {
    let result = claims;
    if (filterProject) result = result.filter(c => c.projectId === filterProject);
    if (filterStatus !== "all") result = result.filter(c => c.status === filterStatus);
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      result = result.filter(c =>
        c.id.toLowerCase().includes(term) ||
        (c.vendorUsername || "").toLowerCase().includes(term) ||
        c.projectId.toLowerCase().includes(term) ||
        (c.milestone_details?.name || "").toLowerCase().includes(term) ||
        (c.vendorLegalName || "").toLowerCase().includes(term)
      );
    }
    return result;
  }, [claims, filterProject, filterStatus, searchTerm]);

  const totalPages = Math.ceil(filteredClaims.length / perPage);
  const safePage = Math.min(Math.max(1, page), totalPages || 1);
  const paginatedClaims = filteredClaims.slice((safePage - 1) * perPage, safePage * perPage);

  const summary = useMemo(() => {
    const totalClaims = claims.length;
    const pendingReview = claims.filter(c => c.status === "Submitted").length;
    const inPipeline = claims.filter(c => ["RMT Approved", "TAC Endorsed", "PSC Approved"].includes(c.status)).length;
    const paid = claims.filter(c => c.status === "Paid").length;
    const totalClaimed = claims.reduce((acc, c) => acc + (c.claimAmount || 0), 0);
    const totalPaid = claims.filter(c => c.status === "Paid").reduce((acc, c) => acc + (c.claimAmount || 0), 0);
    const flaggedCount = claims.filter(c => (anomalyCountByProject[c.projectId] || 0) > 0).length;
    const withFindings = Object.keys(findingsByClaim).length;
    return { totalClaims, pendingReview, inPipeline, paid, totalClaimed, totalPaid, flaggedCount, withFindings };
  }, [claims, anomalyCountByProject, findingsByClaim]);

  const handleExportCsv = () => {
    const rows = [
      ["Claim ID", "Project", "Vendor", "Milestone", "Slab %", "Amount (LSL)", "Status", "Submitted", "RMT Verified", "TAC Endorsed", "PSC Approved", "Paid", "Beneficiaries", "Female Beneficiaries", "Evidence Files", "Anomalies", "Findings"].join(","),
      ...filteredClaims.map(c => [
        c.id,
        c.projectId,
        c.vendorUsername || c.vendorLegalName || "",
        c.milestone_details?.name || "",
        c.milestone_details?.disbursementPct || "",
        c.claimAmount || 0,
        c.status,
        c.submittedAt || "",
        c.verifiedAt || "",
        c.approvedAt || "",
        c.paidAt || "",
        c.paidAt || "",
        c.actualBeneficiaries || 0,
        c.actualFemaleBeneficiaries || 0,
        (c.evidenceFiles || []).length,
        anomalyCountByProject[c.projectId] || 0,
        (findingsByClaim[c.id] || []).length,
      ].join(","))
    ].join("\n");
    const blob = new Blob([rows], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, "claims_audit.csv");
  };

  const daysSince = (date?: string) => {
    if (!date) return "\u2014";
    const diff = Math.floor((Date.now() - new Date(date).getTime()) / (1000 * 60 * 60 * 24));
    return `${diff}d`;
  };

  const getSlabLabel = (pct?: number) => {
    if (!pct) return "\u2014";
    if (pct <= 20) return `${pct}% \u2014 Mobilization`;
    if (pct <= 50) return `${pct}% \u2014 Installation`;
    return `${pct}% \u2014 Final`;
  };

  const statusColor = (status: string) => {
    switch (status) {
      case "Paid": return "bg-emerald-100 text-emerald-700 border-emerald-200";
      case "PSC Approved": return "bg-indigo-100 text-indigo-700 border-indigo-200";
      case "TAC Endorsed": return "bg-violet-100 text-violet-700 border-violet-200";
      case "RMT Approved": return "bg-amber-100 text-amber-700 border-amber-200";
      case "Submitted": return "bg-blue-100 text-blue-700 border-blue-200";
      case "Rejected": return "bg-red-100 text-red-700 border-red-200";
      default: return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  const approvalSteps = ["Submitted", "RMT Approved", "TAC Endorsed", "PSC Approved", "Paid"];
  const getApprovalStepIndex = (status: string) => {
    const idx = approvalSteps.indexOf(status);
    return idx >= 0 ? idx : 0;
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading claims audit data...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {selectedClaim && (
        <ClaimDetailPanel
          claim={selectedClaim}
          project={projectMap[selectedClaim.projectId]}
          anomalies={anomalies.filter(a => a.project === selectedClaim.projectId)}
          findings={findingsByClaim[selectedClaim.id] || []}
          approvalSteps={approvalSteps}
          getSlabLabel={getSlabLabel}
          onClose={() => setSelectedClaim(null)}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Claims Audit</h1>
          <p className="text-sm text-slate-500">Verify milestone claims, cross-reference KPIs, review evidence &amp; disbursement chain</p>
        </div>
        <button onClick={handleExportCsv} className="btn-primary flex items-center gap-2">
          <Download size={16} /> Export Audit CSV
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <button onClick={() => setFilterStatus("all")} className="card p-4 text-left hover:border-blue-300 transition-all">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Total Claims</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{summary.totalClaims}</p>
          <p className="mt-1 text-xs text-slate-500">LSL {(summary.totalClaimed / 1000).toFixed(0)}K claimed</p>
        </button>
        <button onClick={() => setFilterStatus("Submitted")} className="card p-4 text-left hover:border-blue-300 transition-all">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Pending Review</p>
          <p className="mt-2 text-3xl font-bold text-blue-700">{summary.pendingReview}</p>
          <p className="mt-1 text-xs text-slate-500">Awaiting auditor verification</p>
        </button>
        <button onClick={() => setFilterStatus("all")} className="card p-4 text-left hover:border-blue-300 transition-all border-red-200 bg-red-50/30">
          <p className="text-xs font-bold uppercase tracking-widest text-red-400">With Anomalies</p>
          <p className="mt-2 text-3xl font-bold text-red-700">{summary.flaggedCount}</p>
          <p className="mt-1 text-xs text-red-500">{summary.withFindings} with audit findings</p>
        </button>
        <button onClick={() => setFilterStatus("Paid")} className="card p-4 text-left hover:border-blue-300 transition-all">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Paid</p>
          <p className="mt-2 text-3xl font-bold text-emerald-700">{summary.paid}</p>
          <p className="mt-1 text-xs text-slate-500">LSL {(summary.totalPaid / 1000).toFixed(0)}K disbursed</p>
        </button>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input-field pl-8 w-full"
              placeholder="Search claim ID, vendor, project..."
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
            />
          </div>
          <select
            className="input-field min-w-[160px]"
            value={filterProject}
            onChange={(e) => { setFilterProject(e.target.value); setPage(1); }}
          >
            <option value="">All Projects</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.reference || p.id}</option>
            ))}
          </select>
          <select
            className="input-field min-w-[140px]"
            value={filterStatus}
            onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
          >
            <option value="all">All Statuses</option>
            <option value="Submitted">Submitted</option>
            <option value="RMT Approved">RMT Approved</option>
            <option value="TAC Endorsed">TAC Endorsed</option>
            <option value="PSC Approved">PSC Approved</option>
            <option value="Paid">Paid</option>
            <option value="Rejected">Rejected</option>
          </select>
          {(filterProject || filterStatus !== "all" || searchTerm) && (
            <button
              onClick={() => { setFilterProject(""); setFilterStatus("all"); setSearchTerm(""); setPage(1); }}
              className="text-xs text-blue-600 hover:underline flex items-center gap-1"
            >
              <X size={12} /> Clear
            </button>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Claim</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project / Vendor</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Milestone / Slab</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500 text-right">Amount</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500 text-center">Approvals</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500 text-center">Days</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500 text-center">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {paginatedClaims.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                  <FileSearch size={32} className="mx-auto mb-2 text-slate-300" />
                  <p className="font-medium">No claims found</p>
                  <p className="text-xs mt-1">Try adjusting filters or search terms</p>
                </td>
              </tr>
            )}
            {paginatedClaims.map((claim) => {
              const proj = projectMap[claim.projectId];
              const anomalyCount = anomalyCountByProject[claim.projectId] || 0;
              const claimFindings = findingsByClaim[claim.id] || [];
              const stepIdx = getApprovalStepIndex(claim.status);
              const hasFlags = anomalyCount > 0 || claimFindings.length > 0;
              const slabPct = claim.milestone_details?.disbursementPct;

              return (
                <tr
                  key={claim.id}
                  className={`hover:bg-slate-50 cursor-pointer ${hasFlags ? "bg-red-50/30" : ""}`}
                  onClick={() => setSelectedClaim(claim)}
                >
                  <td className="px-4 py-3">
                    <span className="text-sm font-mono font-medium text-slate-900">{claim.id.slice(0, 8)}</span>
                    {claim.evidenceFiles && claim.evidenceFiles.length > 0 && (
                      <div className="flex items-center gap-1 mt-1 text-[10px] text-slate-400">
                        <Paperclip size={10} /> {claim.evidenceFiles.length} files
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-slate-900">{proj?.projectReference || claim.projectId.slice(0, 8)}</div>
                    <div className="text-xs text-slate-500">{claim.vendorUsername || claim.vendorLegalName || "\u2014"}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm text-slate-900">{claim.milestone_details?.name || "\u2014"}</div>
                    {slabPct && (
                      <div className={`text-xs mt-0.5 font-medium ${slabPct <= 20 ? "text-emerald-600" : slabPct <= 50 ? "text-amber-600" : "text-indigo-600"}`}>
                        {getSlabLabel(slabPct)}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-sm font-semibold text-slate-900">
                      {claim.claimAmount ? `LSL ${claim.claimAmount.toLocaleString()}` : "\u2014"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-[10px] font-bold border ${statusColor(claim.status)}`}>
                      {claim.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-0.5">
                      {approvalSteps.map((step, idx) => (
                        <div
                          key={step}
                          className={`w-6 h-1.5 rounded-full ${
                            idx <= stepIdx
                              ? idx === stepIdx ? "bg-blue-500" : "bg-emerald-400"
                              : "bg-slate-200"
                          }`}
                          title={`${step}${idx <= stepIdx ? " done" : ""}`}
                        />
                      ))}
                    </div>
                    <div className="text-[10px] text-slate-400 text-center mt-1">
                      {stepIdx + 1}/{approvalSteps.length}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-xs text-slate-600">{daysSince(claim.submittedAt)}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {anomalyCount > 0 && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">
                          {anomalyCount} <AlertCircle size={8} className="inline" />
                        </span>
                      )}
                      {claimFindings.length > 0 && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700">
                          {claimFindings.length} <FileText size={8} className="inline" />
                        </span>
                      )}
                      {!hasFlags && <span className="text-[10px] text-slate-300">\u2014</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filteredClaims.length > perPage && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50/50">
            <p className="text-xs text-slate-500">
              Showing {((safePage - 1) * perPage) + 1}\u2013{Math.min(safePage * perPage, filteredClaims.length)} of {filteredClaims.length}
            </p>
            <div className="flex items-center gap-2">
              <button
                disabled={safePage <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                className="px-3 py-1 text-xs rounded-lg border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
              >
                <ChevronLeft size={12} /> Previous
              </button>
              <span className="text-xs text-slate-500">Page {safePage} of {totalPages}</span>
              <button
                disabled={safePage >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                className="px-3 py-1 text-xs rounded-lg border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
              >
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="card p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
          <ShieldCheck size={16} /> SRS Verification Guide
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-600">
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="font-bold text-slate-700 mb-1">Payment Slabs (SRS 4.3)</p>
            <ul className="space-y-0.5">
              <li><span className="font-medium text-emerald-600">20%</span> \u2014 Mobilization / contract signing</li>
              <li><span className="font-medium text-amber-600">50%</span> \u2014 Installation verification</li>
              <li><span className="font-medium text-indigo-600">30%</span> \u2014 Final validation / audit</li>
            </ul>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="font-bold text-slate-700 mb-1">Auditor Checklist (SRS 5.3)</p>
            <ul className="space-y-0.5">
              <li>\u2713 Verify smart meter / API data matches claim</li>
              <li>\u2713 Check GPS &amp; installation photos</li>
              <li>\u2713 Validate beneficiary counts &amp; gender targets</li>
              <li>\u2713 Flag data deviations &gt;5%</li>
              <li>\u2713 Review anomaly flags &amp; audit findings</li>
            </ul>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="font-bold text-slate-700 mb-1">Non-Conforming Triggers (SRS 5.4)</p>
            <ul className="space-y-0.5">
              <li>Zero uptime on smart meter data</li>
              <li>Output deviation &gt;5% from declared</li>
              <li>GPS mismatch / duplicate coordinates</li>
              <li>Missing data windows (&gt;7 days)</li>
              <li>All held back from disbursement</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

interface ClaimDetailPanelProps {
  claim: PaymentClaim;
  project?: Project;
  anomalies: AnomalyFlag[];
  findings: AuditFinding[];
  approvalSteps: string[];
  getSlabLabel: (pct?: number) => string;
  onClose: () => void;
}

function ClaimDetailPanel({ claim, project, anomalies, findings, approvalSteps, getSlabLabel, onClose }: ClaimDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "evidence" | "flags" | "timeline">("overview");
  const stepIdx = approvalSteps.indexOf(claim.status);

  const timeline = useMemo(() => {
    const events: { label: string; date?: string; done: boolean }[] = [
      { label: "Claim Submitted", date: claim.submittedAt, done: true },
      { label: "RMT Verified", date: claim.verifiedAt, done: !!claim.verifiedAt },
      { label: "TAC Endorsed", date: claim.approvedAt, done: !!claim.approvedAt && stepIdx >= 2 },
      { label: "PSC Approved", date: claim.paidAt, done: !!claim.paidAt && stepIdx >= 3 },
      { label: "Disbursed", date: claim.paidAt, done: claim.status === "Paid" },
    ];
    return events;
  }, [claim, stepIdx]);

  return (
    <div className="card border-2 border-blue-200 bg-blue-50/20 overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-blue-100">
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-blue-100 transition-colors">
            <ArrowLeft size={18} className="text-blue-600" />
          </button>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Claim {claim.id.slice(0, 12)}</h2>
            <p className="text-xs text-slate-500">{project?.projectReference || claim.projectId} \u2014 {claim.milestone_details?.name || "Milestone"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
            claim.status === "Paid" ? "bg-emerald-100 text-emerald-700 border-emerald-200" :
            claim.status === "Submitted" ? "bg-blue-100 text-blue-700 border-blue-200" :
            "bg-amber-100 text-amber-700 border-amber-200"
          }`}>
            {claim.status}
          </span>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100">
            <X size={16} className="text-slate-400" />
          </button>
        </div>
      </div>

      <div className="flex border-b border-slate-200 bg-white">
        {(["overview", "evidence", "flags", "timeline"] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              activeTab === tab ? "text-blue-600 border-b-2 border-blue-600" : "text-slate-400 hover:text-slate-600"
            }`}
          >
            {tab === "overview" && <FileText size={12} className="inline mr-1" />}
            {tab === "evidence" && <Paperclip size={12} className="inline mr-1" />}
            {tab === "flags" && <AlertCircle size={12} className="inline mr-1" />}
            {tab === "timeline" && <History size={12} className="inline mr-1" />}
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {tab === "flags" && (anomalies.length + findings.length) > 0 && (
              <span className="ml-1 px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 text-[9px]">
                {anomalies.length + findings.length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="p-6">
        {activeTab === "overview" && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Claim Amount</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{claim.claimAmount ? `LSL ${claim.claimAmount.toLocaleString()}` : "\u2014"}</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Milestone Slab</p>
                <p className="mt-1 text-sm font-bold text-slate-900">{getSlabLabel(claim.milestone_details?.disbursementPct)}</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Beneficiaries</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{claim.actualBeneficiaries || 0}</p>
                <p className="text-[10px] text-slate-500">Female: {claim.actualFemaleBeneficiaries || 0} ({claim.actualBeneficiaries ? Math.round((claim.actualFemaleBeneficiaries / claim.actualBeneficiaries) * 100) : 0}%)</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Evidence Files</p>
                <p className="mt-1 text-xl font-bold text-slate-900">{(claim.evidenceFiles || []).length}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3 flex items-center gap-1">
                  <Building2 size={12} /> Vendor Details
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-slate-500">Legal Name</span><span className="font-medium text-slate-900">{claim.vendorLegalName || "\u2014"}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Username</span><span className="font-medium text-slate-900">{claim.vendorUsername || "\u2014"}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Bank</span><span className="font-medium text-slate-900">{claim.vendorBankName || "\u2014"}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Branch</span><span className="font-medium text-slate-900">{claim.vendorBankBranch || "\u2014"}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Account</span><span className="font-mono text-xs text-slate-900">{claim.vendorAccountNumber || "\u2014"}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Holder</span><span className="font-medium text-slate-900">{claim.vendorAccountHolderName || "\u2014"}</span></div>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3 flex items-center gap-1">
                  <Banknote size={12} /> Disbursement Info
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-slate-500">Status</span><span className="font-medium text-slate-900">{claim.status}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Payment Ref</span><span className="font-mono text-xs text-slate-900">{claim.paymentReference || "\u2014"}</span></div>
                  {claim.disbursement && (
                    <>
                      <div className="flex justify-between"><span className="text-slate-500">Disbursement ID</span><span className="font-mono text-xs text-slate-900">{claim.disbursement.id.slice(0, 8)}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Disbursement Status</span><span className="font-medium text-slate-900">{claim.disbursement.status}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Processed By</span><span className="font-medium text-slate-900">{claim.disbursement.processedByUsername || "\u2014"}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">Processed At</span><span className="text-xs text-slate-900">{formatDateTime(claim.disbursement.processedAt)}</span></div>
                    </>
                  )}
                  {claim.paymentLocked && (
                    <div className="mt-2 p-2 bg-red-50 rounded-lg border border-red-200">
                      <p className="text-xs font-bold text-red-700 flex items-center gap-1"><AlertCircle size={12} /> Payment Locked</p>
                      <p className="text-xs text-red-600 mt-0.5">{claim.paymentLockReason || "Locked by system"}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {claim.implementationNotes && (
              <div className="bg-slate-50 rounded-xl p-4">
                <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Implementation Notes</h4>
                <p className="text-sm text-slate-700">{claim.implementationNotes}</p>
              </div>
            )}
            {claim.remarks && (
              <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
                <h4 className="text-xs font-bold uppercase tracking-widest text-amber-500 mb-2">Reviewer Remarks</h4>
                <p className="text-sm text-amber-800">{claim.remarks}</p>
              </div>
            )}
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="space-y-4">
            {(claim.evidenceFiles || []).length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <Paperclip size={32} className="mx-auto mb-2" />
                <p className="font-medium">No evidence files uploaded</p>
                <p className="text-xs mt-1">Vendor has not attached any evidence to this claim</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {claim.evidenceFiles.map((file, idx) => (
                  <div key={idx} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <FileText size={20} className="text-slate-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 truncate">{file}</p>
                      <p className="text-[10px] text-slate-400">Evidence file {idx + 1}</p>
                    </div>
                    <a
                      href={file.startsWith("http") ? file : `${API_BASE}${file}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline shrink-0"
                    >
                      View
                    </a>
                  </div>
                ))}
              </div>
            )}
            <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
              <h4 className="text-xs font-bold text-blue-700 mb-2 flex items-center gap-1">
                <ShieldCheck size={12} /> Auditor Evidence Checklist (SRS 5.3)
              </h4>
              <ul className="space-y-1 text-xs text-blue-800">
                <li>\u2713 Customer details (ID, address, phone, NID)</li>
                <li>\u2713 GPS coordinates matching installation site</li>
                <li>\u2713 Proof of sale / payment receipts</li>
                <li>\u2713 Product information (brand, serial, type)</li>
                <li>\u2713 Power supply duration &ge;30 days stable</li>
                <li>\u2713 Smart meter data / API verification</li>
                <li>\u2713 Installation photos with timestamps</li>
              </ul>
            </div>
          </div>
        )}

        {activeTab === "flags" && (
          <div className="space-y-5">
            {anomalies.length === 0 && findings.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-400" />
                <p className="font-medium text-emerald-600">No flags or findings</p>
                <p className="text-xs mt-1">This claim has no linked anomaly flags or audit findings</p>
              </div>
            ) : (
              <>
                {anomalies.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-widest text-red-500 mb-3 flex items-center gap-1">
                      <AlertCircle size={12} /> Anomaly Flags ({anomalies.length})
                    </h4>
                    <div className="space-y-2">
                      {anomalies.map(flag => (
                        <div key={flag.id} className="p-3 bg-red-50 rounded-lg border border-red-200">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-red-700">{flag.flagType.replace(/_/g, " ").toUpperCase()}</span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${flag.isResolved ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                              {flag.isResolved ? "Resolved" : "Open"}
                            </span>
                          </div>
                          {flag.description && <p className="text-xs text-red-600 mt-1">{flag.description}</p>}
                          <p className="text-[10px] text-red-400 mt-1">Created: {formatDateTime(flag.createdAt)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {findings.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-widest text-amber-500 mb-3 flex items-center gap-1">
                      <FileText size={12} /> Audit Findings ({findings.length})
                    </h4>
                    <div className="space-y-2">
                      {findings.map(finding => (
                        <div key={finding.id} className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-amber-700">{finding.findingCategory.replace(/_/g, " ").toUpperCase()}</span>
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                                finding.riskLevel === RiskLevel.CRITICAL || finding.riskLevel === RiskLevel.MAJOR_FINDING
                                  ? "bg-red-100 text-red-700"
                                  : "bg-amber-100 text-amber-700"
                              }`}>
                                {finding.riskLevel}
                              </span>
                              <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${finding.status === "resolved" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"}`}>
                                {finding.status}
                              </span>
                            </div>
                          </div>
                          <p className="text-xs text-amber-800 mt-1">{finding.description}</p>
                          {finding.recommendedAction && (
                            <p className="text-[10px] text-amber-600 mt-1 font-medium">Action: {finding.recommendedAction}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {activeTab === "timeline" && (
          <div className="space-y-0">
            {timeline.map((event, idx) => (
              <div key={idx} className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className={`w-3 h-3 rounded-full border-2 ${event.done ? "bg-emerald-500 border-emerald-500" : "bg-white border-slate-300"}`} />
                  {idx < timeline.length - 1 && (
                    <div className={`w-0.5 h-8 ${event.done ? "bg-emerald-300" : "bg-slate-200"}`} />
                  )}
                </div>
                <div className="pb-6">
                  <p className={`text-sm font-medium ${event.done ? "text-slate-900" : "text-slate-400"}`}>{event.label}</p>
                  <p className="text-xs text-slate-500">{event.date ? formatDateTime(event.date) : "Pending"}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function AuditorProspectSyncLog() {
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<ProspectSyncLog[]>([]);
  const [operationFilter, setOperationFilter] = useState<"all" | "post" | "get">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "success" | "failed">("all");

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchProspectSyncLogs({ pageSize: 100 });
      setLogs(data);
    } catch (err) {
      console.error("Failed to load prospect logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredLogs = useMemo(() => {
    let result = logs;
    if (operationFilter !== "all") {
      result = result.filter(l => 
        (operationFilter === "post" && l.methodName.startsWith("post")) ||
        (operationFilter === "get" && l.methodName.startsWith("get"))
      );
    }
    if (statusFilter !== "all") {
      result = result.filter(l => l.status.toLowerCase() === statusFilter);
    }
    return result;
  }, [logs, operationFilter, statusFilter]);

  const summary = useMemo(() => {
    const total = logs.length;
    const success = logs.filter(l => l.status === "Success").length;
    const failed = logs.filter(l => l.status === "Failed").length;
    const pending = total - success - failed;
    return { total, success, failed, pending };
  }, [logs]);

  const handleExport = () => {
    const csv = [
      ["ID", "Method", "Status", "Attempts", "Record ID", "Created At", "Error"].join(","),
      ...filteredLogs.map(l => [
        l.id,
        l.methodName,
        l.status,
        l.attempts,
        l.recordId || "",
        l.createdAt || "",
        l.errorMessage || "",
      ].join(","))
    ].join("\n");
    
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, "prospect_sync_log.csv");
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading prospect sync logs...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Prospect Sync Log</h1>
          <p className="text-sm text-slate-500">Full prospect_sync_log table (read-only)</p>
        </div>
        <button onClick={handleExport} className="btn-secondary flex items-center gap-2">
          <Download size={16} /> Export
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-slate-500">Total</p>
          <p className="text-2xl font-bold text-slate-900">{summary.total}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-emerald-600">Success</p>
          <p className="text-2xl font-bold text-emerald-700">{summary.success}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-amber-600">Pending</p>
          <p className="text-2xl font-bold text-amber-700">{summary.pending}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-rose-600">Failed</p>
          <p className="text-2xl font-bold text-rose-700">{summary.failed}</p>
        </div>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <select
            className="input-field"
            value={operationFilter}
            onChange={(e) => setOperationFilter(e.target.value as any)}
          >
            <option value="all">All Operations</option>
            <option value="post">POST Only</option>
            <option value="get">GET Only</option>
          </select>
          <select
            className="input-field"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Operation</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Attempts</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Record</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredLogs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No sync logs found.
                </td>
              </tr>
            )}
            {filteredLogs.map((log) => (
              <tr key={log.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {log.methodName}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                    log.status === "Success" ? "bg-emerald-100 text-emerald-700" :
                    log.status === "Failed" ? "bg-rose-100 text-rose-700" :
                    "bg-amber-100 text-amber-700"
                  }`}>
                    {log.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">{log.attempts}</td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  {log.recordType} #{log.recordId}
                </td>
                <td className="px-4 py-3 text-sm text-slate-500">
                  {formatDateTime(log.createdAt)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AuditorAuditFindings({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [findings, setFindings] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [showFindingModal, setShowFindingModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [findingCategory, setFindingCategory] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [linkedProject, setLinkedProject] = useState("");
  const [linkedClaim, setLinkedClaim] = useState("");
  const [description, setDescription] = useState("");
  const [recommendedAction, setRecommendedAction] = useState("");
  const [notifyRmt, setNotifyRmt] = useState(true);
  const [notifyPsc, setNotifyPsc] = useState(true);
  const [notifySuperAdmin, setNotifySuperAdmin] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [findingsData, projList, claimsData] = await Promise.all([
        fetchAuditFindings(),
        fetchProjects(),
        fetchPaymentClaims(),
      ]);
      setFindings(findingsData);
      setProjects(projList);
      setClaims(claimsData);
    } catch (err) {
      console.error("Failed to load audit findings:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const openFindings = findings.filter((f: any) => f.status === "open");
  const resolvedFindings = findings.filter((f: any) => f.status === "resolved");

  const handleSubmitFinding = async () => {
    if (!findingCategory || !riskLevel || !description.trim()) {
      alert("Please fill in all required fields.");
      return;
    }
    setSubmitting(true);
    try {
      await createAuditFinding({
        finding_category: findingCategory as FindingCategory,
        risk_level: riskLevel as RiskLevel,
        linked_project: linkedProject || undefined,
        linked_claim: linkedClaim || undefined,
        description: description,
        recommended_action: recommendedAction,
        rised_to_rmt: notifyRmt,
        rised_to_psc: notifyPsc,
        rised_to_super_admin: notifySuperAdmin,
      });
      alert("Audit finding submitted successfully!");
      setShowFindingModal(false);
      resetForm();
      void loadData();
    } catch (err) {
      console.error("Failed to submit finding:", err);
      alert("Failed to submit finding. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setFindingCategory("");
    setRiskLevel("");
    setLinkedProject("");
    setLinkedClaim("");
    setDescription("");
    setRecommendedAction("");
    setNotifyRmt(true);
    setNotifyPsc(true);
    setNotifySuperAdmin(false);
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading audit findings...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {showFindingModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto">
          <div className="bg-white rounded-2xl p-6 max-w-3xl w-full mx-4 my-8 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <FileText size={20} className="text-amber-600" />
                Raise Audit Finding
              </h3>
              <button onClick={() => setShowFindingModal(false)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Finding Category *</label>
              <div className="grid grid-cols-2 gap-2">
                {FINDING_CATEGORIES.map((cat) => (
                  <button
                    key={cat.value}
                    onClick={() => setFindingCategory(cat.value)}
                    className={`p-3 rounded-xl text-left border transition-all ${
                      findingCategory === cat.value
                        ? "border-amber-500 bg-amber-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <p className="font-medium text-slate-900 text-sm">{cat.label}</p>
                    <p className="text-xs text-slate-500">{cat.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Risk Level *</label>
              <div className="flex gap-2">
                {RISK_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => setRiskLevel(level.value)}
                    className={`flex-1 p-3 rounded-xl text-center border transition-all ${
                      riskLevel === level.value
                        ? level.color === "rose" ? "border-rose-500 bg-rose-50"
                          : level.color === "red" ? "border-red-500 bg-red-50"
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

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="text-sm font-bold text-slate-900 mb-2 block">Linked Project</label>
                <select
                  className="input-field"
                  value={linkedProject}
                  onChange={(e) => { setLinkedProject(e.target.value); setLinkedClaim(""); }}
                >
                  <option value="">Select project...</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.projectReference || `PRJ-${p.id}`} | {p.vendorName || p.vendorId || "Vendor"} | {p.techType || "Tech"} | {p.district || p.region || "Region"} | {p.status}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-bold text-slate-900 mb-2 block">
                  Linked Payment Claim
                  {!linkedProject && <span className="text-slate-400 text-xs ml-2">(select project first)</span>}
                </label>
                <select
                  className="input-field"
                  value={linkedClaim}
                  onChange={(e) => setLinkedClaim(e.target.value)}
                  disabled={!linkedProject}
                >
                  <option value="">{linkedProject ? "Select claim..." : "Select a project first"}</option>
                  {claims.filter(c => !linkedProject || String(c.projectId) === linkedProject).map((c) => (
                    <option key={c.id} value={c.id}>
                      CLM-{c.id} | {c.milestoneId ? `M${c.milestoneId}` : "Milestone"} | ${c.claimAmount?.toLocaleString() || "0"} | {c.status}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Finding Description *</label>
              <textarea
                className="input-field min-h-[150px]"
                placeholder="Describe the audit finding in detail..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Recommended Action</label>
              <textarea
                className="input-field min-h-[100px]"
                placeholder="What action do you recommend be taken?"
                value={recommendedAction}
                onChange={(e) => setRecommendedAction(e.target.value)}
              />
            </div>

            <div className="mb-4">
              <label className="text-sm font-bold text-slate-900 mb-2 block">Notify *</label>
              <div className="space-y-2">
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyRmt}
                    onChange={(e) => setNotifyRmt(e.target.checked)}
                    className="rounded border-slate-300 text-amber-600"
                  />
                  <span className="text-sm font-medium text-slate-700">RMT (always notified)</span>
                </label>
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifyPsc}
                    onChange={(e) => setNotifyPsc(e.target.checked)}
                    className="rounded border-slate-300 text-amber-600"
                  />
                  <span className="text-sm font-medium text-slate-700">PSC (always notified for audit findings)</span>
                </label>
                <label className="flex items-center gap-2 p-3 bg-slate-50 rounded-xl">
                  <input
                    type="checkbox"
                    checked={notifySuperAdmin}
                    onChange={(e) => setNotifySuperAdmin(e.target.checked)}
                    className="rounded border-slate-300 text-amber-600"
                  />
                  <span className="text-sm font-medium text-slate-700">Super Admin (notify for system-level issues)</span>
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => { setShowFindingModal(false); resetForm(); }}
                className="btn-secondary"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitFinding}
                className="btn-primary flex items-center gap-2"
                disabled={submitting || !findingCategory || !riskLevel || !description.trim()}
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
                Submit Finding
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Audit Findings</h1>
          <p className="text-sm text-slate-500">Raise and manage formal audit findings</p>
        </div>
        <button onClick={() => setShowFindingModal(true)} className="btn-primary flex items-center gap-2">
          <FileText size={16} /> Raise Audit Finding
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl bg-slate-50 p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Findings</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{findings.length}</p>
        </div>
        <div className="rounded-xl bg-amber-50 p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Open</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{openFindings.length}</p>
        </div>
        <div className="rounded-xl bg-emerald-50 p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Resolved</p>
          <p className="mt-2 text-3xl font-bold text-emerald-700">{resolvedFindings.length}</p>
        </div>
        <div className="rounded-xl bg-rose-50 p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Critical</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">
            {findings.filter((f: any) => f.riskLevel === "critical").length}
          </p>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">My Audit Findings</h3>
        {findings.length === 0 ? (
          <p className="text-slate-500">No audit findings raised yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">ID</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Category</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Risk Level</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {findings.map((finding: any) => (
                  <tr key={finding.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">{finding.id}</td>
                    <td className="px-4 py-3 text-sm text-slate-600">{finding.findingCategory}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        finding.riskLevel === "critical" ? "bg-rose-600 text-white" :
                        finding.riskLevel === "major" ? "bg-red-500 text-white" :
                        finding.riskLevel === "minor" ? "bg-orange-500 text-white" :
                        "bg-yellow-500 text-white"
                      }`}>
                        {finding.riskLevel?.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">{finding.linkedProject || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        finding.status === "resolved" ? "bg-emerald-100 text-emerald-700" :
                        finding.status === "under_investigation" ? "bg-amber-100 text-amber-700" :
                        "bg-amber-100 text-amber-700"
                      }`}>
                        {finding.status?.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">{formatDateTime(finding.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}