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
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
  ExternalLink,
} from "lucide-react";
import {
  fetchProjects,
  fetchPaymentClaims,
  fetchPortfolioKpiSummary,
} from "../api";
import {
  PaymentClaim,
  PortfolioKpiSummary,
  Project,
} from "../types";
import { MacroKpiPortal } from "./RoleBasedKpiPanels";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

export function PscDashboard({ currentUser, onNavigate }: { currentUser?: any; onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioKpiSummary | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  const loadData = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const [projectData, claimsData, portfolioData] = await Promise.all([
        fetchProjects(),
        fetchPaymentClaims(),
        fetchPortfolioKpiSummary(),
      ]);
      setProjects(projectData);
      setClaims(claimsData);
      setPortfolio(portfolioData);
      setLastSyncedAt(new Date().toISOString());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load PSC dashboard data."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const summary = useMemo(() => {
    const pendingApprovals = claims.filter((c) => c.status === "TAC Endorsed");
    const totalPaid = claims
      .filter((c) => c.status === "Completed" || c.status === "Paid")
      .reduce((sum, c) => sum + (c.claimAmount || 0), 0);
    return {
      totalProjects: portfolio?.total_projects ?? projects.length,
      pendingApprovalsCount: pendingApprovals.length,
      pendingApprovals,
      totalPaid,
      overallProgress: portfolio?.overall_progress_pct ?? 0,
      projectsAtRisk: portfolio?.projects_at_risk ?? 0,
      projectsOnTrack: portfolio?.projects_on_track ?? 0,
    };
  }, [projects, claims, portfolio]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading PSC dashboard...
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
          <h1 className="text-2xl font-bold text-slate-900">PSC Dashboard</h1>
          <p className="text-slate-500">National oversight — portfolio health and financial approvals.</p>
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
          onClick={() => onNavigate?.("portfolio")}
          className="card group p-5 text-left transition hover:border-blue-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Projects</p>
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 transition group-hover:bg-blue-200">
              <FolderKanban size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.totalProjects}</p>
          <p className="mt-1 text-xs text-slate-500">{summary.overallProgress}% overall progress</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("payments")}
          className="card group p-5 text-left transition hover:border-amber-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Pending Approvals</p>
            <div className="rounded-lg bg-amber-100 p-2 text-amber-600 transition group-hover:bg-amber-200">
              <CreditCard size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.pendingApprovalsCount}</p>
          <p className="mt-1 text-xs text-slate-500">Claims awaiting PSC financial authorization</p>
        </button>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Disbursed</p>
            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600">
              <TrendingUp size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">M {summary.totalPaid.toLocaleString()}</p>
          <p className="mt-1 text-xs text-slate-500">
            {summary.projectsAtRisk > 0 ? (
              <span className="font-semibold text-rose-600">{summary.projectsAtRisk} projects at risk</span>
            ) : (
              <span className="font-semibold text-emerald-600">All projects on track</span>
            )}
          </p>
        </div>
      </div>

      {/* Pending Approvals */}
      <div className="grid grid-cols-1 gap-6">
        {/* Pending PSC Approvals */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Pending PSC Approvals</h3>
              <p className="text-xs text-slate-500">{summary.pendingApprovalsCount} claim{summary.pendingApprovalsCount === 1 ? "" : "s"} awaiting financial authorization</p>
            </div>
            {summary.pendingApprovalsCount > 0 && (
              <button
                type="button"
                onClick={() => onNavigate?.("payments")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600 hover:text-amber-700"
              >
                View all <ChevronRight size={14} />
              </button>
            )}
          </div>
          <div className="divide-y divide-slate-100">
            {summary.pendingApprovals.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-500" />
                No claims awaiting PSC approval.
              </div>
            ) : (
              summary.pendingApprovals.slice(0, 5).map((claim) => {
                const project = projects.find((p) => p.id === claim.projectId);
                const projectName = project?.projectTitle || project?.projectReference || claim.projectId;
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
                      <Clock size={12} /> TAC Endorsed
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Project Health Overview */}
      {portfolio && portfolio.projects.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Portfolio Health</h3>
              <p className="text-xs text-slate-500">KPI performance across all national projects</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate?.("portfolio")}
              className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
            >
              View all <ChevronRight size={14} />
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-semibold">Project</th>
                  <th className="px-5 py-3 text-left font-semibold">Vendor</th>
                  <th className="px-5 py-3 text-left font-semibold">District</th>
                  <th className="px-5 py-3 text-left font-semibold">Progress</th>
                  <th className="px-5 py-3 text-left font-semibold">Female %</th>
                  <th className="px-5 py-3 text-left font-semibold">Uptime</th>
                  <th className="px-5 py-3 text-left font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {portfolio.projects.slice(0, 8).map((project) => (
                  <tr key={project.project_id} className="transition hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <p className="font-semibold text-slate-900">{project.project_reference}</p>
                      <p className="max-w-[200px] truncate text-xs text-slate-500">{project.project_title}</p>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{project.vendor_name}</td>
                    <td className="px-5 py-3 text-slate-600">{project.district || "N/A"}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${project.progress_pct >= 70 ? "bg-emerald-500" : project.progress_pct >= 40 ? "bg-amber-500" : "bg-rose-500"}`}
                            style={{ width: `${Math.min(100, project.progress_pct)}%` }}
                          />
                        </div>
                        <span className="text-xs font-semibold text-slate-600">{project.progress_pct}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{project.female_pct}%</td>
                    <td className="px-5 py-3 text-slate-600">{project.uptime_pct}%</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${
                        project.status === "On Track" ? "bg-emerald-100 text-emerald-700" :
                        project.status === "At Risk" ? "bg-rose-100 text-rose-700" :
                        "bg-slate-100 text-slate-600"
                      }`}>
                        {project.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {portfolio.projects.length > 8 && (
            <div className="border-t border-slate-100 px-5 py-3 text-center text-xs text-slate-500">
              Showing 8 of {portfolio.projects.length} projects
            </div>
          )}
        </div>
      )}

      {/* Quick Actions + Macro KPI Portal */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Quick Actions */}
        <div className="card p-5">
          <h3 className="mb-4 text-lg font-bold text-slate-900">Quick Actions</h3>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => onNavigate?.("payments")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-amber-200 hover:bg-amber-50"
            >
              <div className="rounded-lg bg-amber-100 p-2 text-amber-600">
                <CreditCard size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Disbursements</p>
                <p className="text-xs text-slate-500">Financial authorization of claims</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.("portfolio")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-blue-200 hover:bg-blue-50"
            >
              <div className="rounded-lg bg-blue-100 p-2 text-blue-600">
                <FolderKanban size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Portfolio Overview</p>
                <p className="text-xs text-slate-500">Project details and compliance</p>
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
                <p className="text-sm font-semibold text-slate-900">Vendor Directory</p>
                <p className="text-xs text-slate-500">All vendors and profiles</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
          </div>
        </div>

        {/* Macro KPI Portal */}
        <div className="lg:col-span-2">
          <MacroKpiPortal
            title="National KPI Summary"
            description="Macro portfolio monitoring for national progress, inclusion compliance, and system alerts."
          />
        </div>
      </div>
    </div>
  );
}

