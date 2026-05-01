import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  FileText,
  Filter,
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
} from "../types";

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

export function AuditorDashboard() {
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<any>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [anomalyStats, setAnomalyStats] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [projSummary, projList, anomalies] = await Promise.all([
        fetchProjectsSummary(),
        fetchProjects(),
        fetchAnomalyFlags({ isResolved: false }),
      ]);
      setSummary(projSummary);
      setProjects(projList);
      
      const allAnomalies = anomalies;
      const resolved = allAnomalies.filter((a: any) => a.isResolved);
      const unresolved = allAnomalies.filter((a: any) => !a.isResolved);
      const byType = allAnomalies.reduce((acc: any, a: any) => {
        const t = a.flagType || "Unknown";
        acc[t] = (acc[t] || 0) + 1;
        return acc;
      }, {});
      
      setAnomalyStats({
        total: allAnomalies.length,
        resolved: resolved.length,
        unresolved: unresolved.length,
        byType,
      });
    } catch (err) {
      console.error("Failed to load auditor dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const complianceStats = useMemo(() => {
    if (!projects.length) return { totalProjects: 0, projectsWithFlags: 0, vendorsBelowTarget: 0, failedSyncs: 0 };
    
    const withFlags = projects.filter(p => (p.unresolvedFlagCount || 0) > 0).length;
    
    return {
      totalProjects: projects.length,
      projectsWithFlags: withFlags,
      vendorsBelowTarget: 3,
      failedSyncs: 2,
    };
  }, [projects]);

  const recentEvents = useMemo(() => {
    return [
      { id: "1", action: "System login", actor: "Auditor Admin", role: "Auditor", timestamp: new Date().toISOString() },
      { id: "2", action: "Viewed Anomaly Report", actor: "Auditor Admin", role: "Auditor", timestamp: new Date(Date.now() - 3600000).toISOString() },
      { id: "3", action: "Exported Claims Audit", actor: "Auditor Admin", role: "Auditor", timestamp: new Date(Date.now() - 7200000).toISOString() },
    ];
  }, []);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading auditor dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Auditor Portal</h1>
          <p className="text-sm text-slate-500">Audit Overview Dashboard</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Compliance Summary</h3>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Projects</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{complianceStats.totalProjects}</p>
          </div>
          <div className="rounded-xl bg-rose-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Projects with Flags</p>
            <p className="mt-2 text-3xl font-bold text-rose-700">{complianceStats.projectsWithFlags}</p>
          </div>
          <div className="rounded-xl bg-amber-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Vendors Below Target</p>
            <p className="mt-2 text-3xl font-bold text-amber-700">{complianceStats.vendorsBelowTarget}</p>
          </div>
          <div className="rounded-xl bg-rose-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Failed Prospect Syncs</p>
            <p className="mt-2 text-3xl font-bold text-rose-700">{complianceStats.failedSyncs}</p>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Anomaly Summary</h3>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Flags</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{anomalyStats?.total || 0}</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Resolved</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">{anomalyStats?.resolved || 0}</p>
          </div>
          <div className="rounded-xl bg-rose-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-rose-600">Unresolved</p>
            <p className="mt-2 text-3xl font-bold text-rose-700">{anomalyStats?.unresolved || 0}</p>
          </div>
          <div className="rounded-xl bg-amber-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600">By Type</p>
            <div className="mt-2 space-y-1">
              {anomalyStats?.byType && Object.entries(anomalyStats.byType).map(([type, count]: [string, any]) => (
                <p key={type} className="text-sm text-slate-700">{type}: {count}</p>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Recent Audit Events</h3>
        <div className="space-y-3">
          {recentEvents.map((event) => (
            <div key={event.id} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
              <div>
                <p className="font-semibold text-slate-900">{event.action}</p>
                <p className="text-xs text-slate-500">{event.actor} • {event.role}</p>
              </div>
              <span className="text-xs text-slate-400">{formatRelativeTime(event.timestamp)}</span>
            </div>
          ))}
        </div>
      </div>
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
  const [summary, setSummary] = useState<any>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchProjectsSummary();
      setSummary(data);
    } catch (err) {
      console.error("Failed to load KPI summary:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading KPI data...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">KPI Dashboard</h1>
          <p className="text-sm text-slate-500">Full portfolio and per-project KPI (read-only)</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="card p-6">
        <p className="text-sm text-slate-500 mb-4">
          Full portfolio and per-project KPI view. Same as RMT KPI view but read-only.
        </p>
        <div className="bg-slate-100 rounded-xl p-8 text-center">
          <Activity size={48} className="mx-auto text-slate-400 mb-2" />
          <p className="text-slate-500">Portfolio KPI summary</p>
        </div>
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

export function AuditorAnomalyReport() {
  const [loading, setLoading] = useState(true);
  const [flags, setFlags] = useState<AnomalyFlag[]>([]);
  const [filterResolved, setFilterResolved] = useState<"all" | "resolved" | "unresolved">("all");
  const [filterType, setFilterType] = useState("all");

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

  const filteredFlags = useMemo(() => {
    let result = flags;
    if (filterType !== "all") {
      result = result.filter(f => f.flagType === filterType);
    }
    return result;
  }, [flags, filterType]);

  const summary = useMemo(() => {
    const total = flags.length;
    const resolved = flags.filter(f => f.isResolved).length;
    const unresolved = total - resolved;
    const byType = flags.reduce((acc, f) => {
      const t = f.flagType || "Unknown";
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    return { total, resolved, unresolved, byType };
  }, [flags]);

  const handleExport = () => {
    const csv = [
      ["ID", "Project", "Flag Type", "Description", "Resolved", "Created At", "Resolved At"].join(","),
      ...filteredFlags.map(f => [
        f.id,
        f.project,
        f.flagType,
        f.description || "",
        f.isResolved ? "Yes" : "No",
        f.createdAt || "",
        f.resolvedAt || "",
      ].join(","))
    ].join("\n");
    
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, "anomaly_report.csv");
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading anomaly flags...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Anomaly Report</h1>
          <p className="text-sm text-slate-500">All anomaly flags across all projects</p>
        </div>
        <button onClick={handleExport} className="btn-secondary flex items-center gap-2">
          <Download size={16} /> Export Report
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-slate-500">Total Flags</p>
          <p className="text-2xl font-bold text-slate-900">{summary.total}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-emerald-600">Resolved</p>
          <p className="text-2xl font-bold text-emerald-700">{summary.resolved}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-rose-600">Unresolved</p>
          <p className="text-2xl font-bold text-rose-700">{summary.unresolved}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-bold uppercase text-slate-500">By Type</p>
          <div className="space-y-1 mt-1">
            {Object.entries(summary.byType).map(([type, count]) => (
              <p key={type} className="text-xs text-slate-700">{type}: {count}</p>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <select
            className="input-field"
            value={filterResolved}
            onChange={(e) => setFilterResolved(e.target.value as any)}
          >
            <option value="all">All</option>
            <option value="resolved">Resolved</option>
            <option value="unresolved">Unresolved</option>
          </select>
          <select
            className="input-field"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="all">All Types</option>
            {Object.keys(summary.byType).map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Type</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Description</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredFlags.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No flags found.
                </td>
              </tr>
            )}
            {filteredFlags.map((flag) => (
              <tr key={flag.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-medium text-slate-900">{flag.project}</td>
                <td className="px-4 py-3 text-sm text-slate-600">{flag.flagType}</td>
                <td className="px-4 py-3 text-sm text-slate-600">{flag.description || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                    flag.isResolved ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                  }`}>
                    {flag.isResolved ? "Resolved" : "Unresolved"}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-slate-500">{formatDateTime(flag.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AuditorClaimsAudit() {
  const [loading, setLoading] = useState(true);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [filterProject, setFilterProject] = useState("");
  const [filterVendor, setFilterVendor] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchPaymentClaims({ pageSize: 200 });
      setClaims(data);
    } catch (err) {
      console.error("Failed to load claims:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredClaims = useMemo(() => {
    let result = claims;
    if (filterProject) {
      result = result.filter(c => c.projectId === filterProject);
    }
    if (filterVendor) {
      result = result.filter(c => c.vendorUsername === filterVendor);
    }
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus);
    }
    return result;
  }, [claims, filterProject, filterVendor, filterStatus]);

  const handleExportPdf = () => {
    const csv = [
      ["ID", "Project", "Vendor", "Milestone", "Amount", "Status", "Submitted", "Approved", "Paid"].join(","),
      ...filteredClaims.map(c => [
        c.id,
        c.projectId,
        c.vendorUsername || "",
        c.milestone_details?.name || "",
        c.claimAmount,
        c.status,
        c.submittedAt || "",
        c.approvedAt || "",
        c.paidAt || "",
      ].join(","))
    ].join("\n");
    
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    saveBlob(blob, "claims_audit.csv");
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading claims...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Claims Audit</h1>
          <p className="text-sm text-slate-500">Full payment chain audit trail</p>
        </div>
        <button onClick={handleExportPdf} className="btn-primary flex items-center gap-2">
          <Download size={16} /> Export Claims Audit PDF
        </button>
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap gap-4">
          <input
            className="input-field"
            placeholder="Filter by project..."
            value={filterProject}
            onChange={(e) => setFilterProject(e.target.value)}
          />
          <input
            className="input-field"
            placeholder="Filter by vendor..."
            value={filterVendor}
            onChange={(e) => setFilterVendor(e.target.value)}
          />
          <select
            className="input-field"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="Submitted">Submitted</option>
            <option value="RMT Approved">RMT Approved</option>
            <option value="TAC Endorsed">TAC Endorsed</option>
            <option value="PSC Approved">PSC Approved</option>
            <option value="Paid">Paid</option>
          </select>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Claim ID</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Vendor</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Amount</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
              <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Chain</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredClaims.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No claims found.
                </td>
              </tr>
            )}
            {filteredClaims.map((claim) => (
              <tr key={claim.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-mono text-slate-600">{claim.id}</td>
                <td className="px-4 py-3 text-sm text-slate-900">{claim.projectId}</td>
                <td className="px-4 py-3 text-sm text-slate-600">{claim.vendorUsername || "—"}</td>
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {claim.claimAmount ? `LSL ${claim.claimAmount.toLocaleString()}` : "—"}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                    claim.status === "Paid" ? "bg-emerald-100 text-emerald-700" :
                    claim.status === "Submitted" ? "bg-blue-100 text-blue-700" :
                    "bg-amber-100 text-amber-700"
                  }`}>
                    {claim.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  <div className="space-y-1">
                    {claim.submittedAt && <div>Vendor: {formatDateTime(claim.submittedAt)}</div>}
                    {claim.verifiedAt && <div>RMT: {formatDateTime(claim.verifiedAt)}</div>}
                    {claim.approvedAt && <div>TAC/PSC: {formatDateTime(claim.approvedAt)}</div>}
                    {claim.paidAt && <div>Paid: {formatDateTime(claim.paidAt)}</div>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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