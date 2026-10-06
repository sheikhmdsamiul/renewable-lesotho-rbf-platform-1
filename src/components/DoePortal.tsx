import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  CreditCard,
  FolderKanban,
  Loader2,
  Map,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  fetchPaymentClaims,
  fetchPortfolioKpiSummary,
  fetchProjects,
} from "../api";
import {
  PortfolioKpiSummary,
  Project,
  User,
} from "../types";

const formatDateTime = (value?: string | null) => {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

export function DoeDashboard({ currentUser, onNavigate }: { currentUser: any; onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioKpiSummary | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  const userDistricts = useMemo(() => {
    const districts = currentUser?.district || currentUser?.region || "";
    return districts.split(",").map((d: string) => d.trim()).filter(Boolean);
  }, [currentUser]);

  const regionLabel = userDistricts.length > 0 ? userDistricts.join(" + ") : "All Regions";

  const loadData = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const [projectList, claimsData, portfolioData] = await Promise.all([
        fetchProjects(),
        fetchPaymentClaims(),
        fetchPortfolioKpiSummary(),
      ]);
      const filtered = projectList.filter((p: Project) => {
        if (userDistricts.length === 0) return true;
        const projectDistrict = p.district || p.region || "";
        return userDistricts.some((d) => projectDistrict.toLowerCase().includes(d.toLowerCase()));
      });
      setProjects(filtered);
      setClaims(claimsData);
      setPortfolio(portfolioData);
      setLastSyncedAt(new Date().toISOString());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load regional dashboard data."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userDistricts]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const summary = useMemo(() => {
    const activeProjects = projects.filter((p) => p.status === "active").length;
    const completedProjects = projects.filter((p) => p.status === "completed").length;
    const totalInstallations = projects.reduce((sum, p) => sum + (p.progress || 0), 0);
    const kpisBelowTarget = projects.filter((p) => (p.uptime || 0) < 95).length;
    const pendingClaims = claims.filter(
      (c: any) => c.status === "Submitted" || c.status === "RMT Approved" || c.status === "Verified",
    );
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const unverifiedOld = projects.filter((p) => {
      if (p.status !== "completed") return false;
      const created = p.createdAt ? new Date(p.createdAt) : null;
      return created && created < sevenDaysAgo;
    }).length;
    return {
      activeProjects,
      completedProjects,
      totalInstallations,
      kpisBelowTarget,
      pendingClaimsCount: pendingClaims.length,
      pendingClaims,
      unverifiedOld,
      overallProgress: portfolio?.overall_progress_pct ?? 0,
      projectsAtRisk: portfolio?.projects_at_risk ?? 0,
      projectsOnTrack: portfolio?.projects_on_track ?? 0,
    };
  }, [projects, claims, portfolio]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading regional dashboard...
      </div>
    );
  }

  if (error) {
    return (
      <div className="card border-rose-200 bg-rose-50 p-10 text-center text-rose-700">
        <AlertTriangle size={24} className="mx-auto mb-2" />
        {error}
        <button onClick={() => void loadData()} className="btn-secondary mx-auto mt-4 flex items-center gap-2">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regional Overview</h1>
          <p className="text-slate-500">Districts: {regionLabel}</p>
          {lastSyncedAt && (
            <p className="mt-1 text-xs text-slate-400">Last synced {formatDateTime(lastSyncedAt)}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void loadData(true)}
          disabled={refreshing}
          className="btn-secondary inline-flex items-center gap-2 self-start"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <button
          type="button"
          onClick={() => onNavigate?.("projects")}
          className="card group p-5 text-left transition hover:border-blue-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Active Projects</p>
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 transition group-hover:bg-blue-200">
              <FolderKanban size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.activeProjects}</p>
          <p className="mt-1 text-xs text-slate-500">
            {summary.completedProjects} completed • {summary.overallProgress}% avg progress
          </p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("kpis")}
          className="card group p-5 text-left transition hover:border-emerald-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Installations</p>
            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600 transition group-hover:bg-emerald-200">
              <TrendingUp size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.totalInstallations}</p>
          <p className="mt-1 text-xs text-slate-500">Across {summary.activeProjects} active projects</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("kpis")}
          className="card group p-5 text-left transition hover:border-amber-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Pending Claims</p>
            <div className="rounded-lg bg-amber-100 p-2 text-amber-600 transition group-hover:bg-amber-200">
              <CreditCard size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.pendingClaimsCount}</p>
          <p className="mt-1 text-xs text-slate-500">Claims requiring regional review</p>
        </button>
      </div>

      {/* Project Health Table */}
      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-100 p-5">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Project Health</h3>
            <p className="text-xs text-slate-500">KPI performance across projects in your region</p>
          </div>
          {projects.length > 8 && (
            <button
              type="button"
              onClick={() => onNavigate?.("projects")}
              className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
            >
              View all <ChevronRight size={14} />
            </button>
          )}
        </div>
        {projects.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-slate-500">
            No projects are currently assigned to this regional scope.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-semibold">Project</th>
                  <th className="px-5 py-3 text-left font-semibold">District</th>
                  <th className="px-5 py-3 text-left font-semibold">Vendor</th>
                  <th className="px-5 py-3 text-left font-semibold">Progress</th>
                  <th className="px-5 py-3 text-left font-semibold">Uptime</th>
                  <th className="px-5 py-3 text-left font-semibold">Status</th>
                  <th className="px-5 py-3 text-left font-semibold">KPI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {projects.slice(0, 10).map((project) => (
                  <tr key={project.id} className="transition hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <p className="font-semibold text-slate-900">{project.projectReference || project.id}</p>
                      <p className="max-w-[200px] truncate text-xs text-slate-500">{project.projectTitle || project.tenderName}</p>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{project.district || project.region || "—"}</td>
                    <td className="px-5 py-3 text-slate-600">{project.vendorName || "—"}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${(project.progress || 0) >= 70 ? "bg-emerald-500" : (project.progress || 0) >= 40 ? "bg-amber-500" : "bg-rose-500"}`}
                            style={{ width: `${Math.min(100, project.progress || 0)}%` }}
                          />
                        </div>
                        <span className="text-xs font-semibold text-slate-600">{project.progress || 0}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{project.uptime || 0}%</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${
                        project.status === "active" ? "bg-emerald-100 text-emerald-700" :
                        project.status === "completed" ? "bg-blue-100 text-blue-700" :
                        "bg-slate-100 text-slate-600"
                      }`}>
                        {project.status}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {(project.uptime || 0) >= 95 ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">
                          <CheckCircle2 size={12} /> OK
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-1 text-[11px] font-bold text-rose-700">
                          <AlertTriangle size={12} /> LOW
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {projects.length > 10 && (
          <div className="border-t border-slate-100 px-5 py-3 text-center text-xs text-slate-500">
            Showing 10 of {projects.length} projects
          </div>
        )}
      </div>

      {/* Attention Items + Pending Claims */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Attention Items */}
        <div className="card p-5">
          <h3 className="mb-4 text-lg font-bold text-slate-900">Attention Items</h3>
          <div className="space-y-3">
            <div className={`flex items-center justify-between rounded-xl border px-4 py-3 transition ${
              summary.kpisBelowTarget > 0 ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-slate-50"
            }`}>
              <div className="flex items-center gap-3">
                <div className={`rounded-lg p-2 ${summary.kpisBelowTarget > 0 ? "bg-rose-100 text-rose-600" : "bg-slate-100 text-slate-500"}`}>
                  <AlertTriangle size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">KPIs Below Target</p>
                  <p className="text-xs text-slate-500">Projects with uptime below 95%</p>
                </div>
              </div>
              <span className={`text-lg font-bold ${summary.kpisBelowTarget > 0 ? "text-rose-700" : "text-slate-500"}`}>
                {summary.kpisBelowTarget}
              </span>
            </div>

            <div className={`flex items-center justify-between rounded-xl border px-4 py-3 transition ${
              summary.unverifiedOld > 0 ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"
            }`}>
              <div className="flex items-center gap-3">
                <div className={`rounded-lg p-2 ${summary.unverifiedOld > 0 ? "bg-amber-100 text-amber-600" : "bg-slate-100 text-slate-500"}`}>
                  <Clock size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">Unverified &gt; 7 Days</p>
                  <p className="text-xs text-slate-500">Completed installations awaiting verification</p>
                </div>
              </div>
              <span className={`text-lg font-bold ${summary.unverifiedOld > 0 ? "text-amber-700" : "text-slate-500"}`}>
                {summary.unverifiedOld}
              </span>
            </div>

            <div className={`flex items-center justify-between rounded-xl border px-4 py-3 transition ${
              summary.projectsAtRisk > 0 ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-slate-50"
            }`}>
              <div className="flex items-center gap-3">
                <div className={`rounded-lg p-2 ${summary.projectsAtRisk > 0 ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600"}`}>
                  <ShieldCheck size={18} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">Projects At Risk</p>
                  <p className="text-xs text-slate-500">Requiring immediate attention</p>
                </div>
              </div>
              <span className={`text-lg font-bold ${summary.projectsAtRisk > 0 ? "text-rose-700" : "text-emerald-600"}`}>
                {summary.projectsAtRisk}
              </span>
            </div>
          </div>
        </div>

        {/* Pending Claims */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Pending Claims</h3>
              <p className="text-xs text-slate-500">{summary.pendingClaimsCount} claim{summary.pendingClaimsCount === 1 ? "" : "s"} requiring review</p>
            </div>
            {summary.pendingClaimsCount > 0 && (
              <button
                type="button"
                onClick={() => onNavigate?.("kpis")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600 hover:text-amber-700"
              >
                View all <ChevronRight size={14} />
              </button>
            )}
          </div>
          <div className="divide-y divide-slate-100">
            {summary.pendingClaims.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-500" />
                No pending claims in your region.
              </div>
            ) : (
              summary.pendingClaims.slice(0, 5).map((claim: any) => {
                const projectName = claim.projectId || "Unknown Project";
                const milestoneNum = claim.milestone_details?.milestoneNumber;
                return (
                  <div key={claim.id} className="flex items-center justify-between px-5 py-3 transition hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-slate-900">{projectName}</p>
                      <p className="truncate text-xs text-slate-500">
                        {milestoneNum ? `Milestone ${milestoneNum}` : "Claim"}
                        {claim.vendorLegalName ? ` • ${claim.vendorLegalName}` : ""}
                        {claim.claimAmount ? ` • M {claim.claimAmount.toLocaleString()}` : ""}
                      </p>
                    </div>
                    <span className="ml-3 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-bold text-amber-700">
                      <Clock size={12} /> {claim.status}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card p-5">
        <h3 className="mb-4 text-lg font-bold text-slate-900">Quick Actions</h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <button
            type="button"
            onClick={() => onNavigate?.("regional")}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-blue-200 hover:bg-blue-50"
          >
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600">
              <Map size={18} />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-900">Regional Map</p>
              <p className="text-xs text-slate-500">GIS view of installations</p>
            </div>
            <ChevronRight size={16} className="text-slate-400" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate?.("kpis")}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-emerald-200 hover:bg-emerald-50"
          >
            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600">
              <BarChart3 size={18} />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-900">KPI Review</p>
              <p className="text-xs text-slate-500">Regional KPI performance</p>
            </div>
            <ChevronRight size={16} className="text-slate-400" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate?.("projects")}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-amber-200 hover:bg-amber-50"
          >
            <div className="rounded-lg bg-amber-100 p-2 text-amber-600">
              <FolderKanban size={18} />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-900">Regional Projects</p>
              <p className="text-xs text-slate-500">Project details and documents</p>
            </div>
            <ChevronRight size={16} className="text-slate-400" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate?.("all_vendors")}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-slate-200 hover:bg-slate-50"
          >
            <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
              <Users size={18} />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-900">Regional Vendors</p>
              <p className="text-xs text-slate-500">Vendor directory and profiles</p>
            </div>
            <ChevronRight size={16} className="text-slate-400" />
          </button>
        </div>
      </div>
    </div>
  );
}

