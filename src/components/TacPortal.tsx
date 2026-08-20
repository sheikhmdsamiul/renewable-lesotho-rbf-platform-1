import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock,
  CreditCard,
  FileWarning,
  FolderKanban,
  Loader2,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  fetchBidEvaluations,
  fetchPaymentClaims,
  fetchPortfolioKpiSummary,
  fetchProjects,
  fetchReportHistory,
  fetchReportTemplates,
  fetchTenderBids,
  fetchTenders,
  generateReport,
  downloadGeneratedReport,
} from "../api";
import {
  PortfolioKpiSummary,
  Project,
  ReportFormat,
  ReportHistoryItem,
  ReportTemplate,
  TenderBid,
  TenderBidEvaluation,
  User,
  UserRole,
} from "../types";
import { ReportsHub } from "./ReportsHub";

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

function formatDateTime(value?: string | null) {
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
}

export function TacReports() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">TAC Reports</h1>
          <p className="text-sm text-slate-500">Technical Advisory Committee reports and audit trails.</p>
        </div>
      </div>
      <ReportsHub currentUser={{ role: UserRole.TAC }} />
    </div>
  );
}

export function TacDashboard({ currentUser, onNavigate }: { currentUser: any; onNavigate?: (action: string, id?: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bids, setBids] = useState<TenderBid[]>([]);
  const [evaluations, setEvaluations] = useState<TenderBidEvaluation[]>([]);
  const [claims, setClaims] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
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
      const [bidsData, evalsData, claimsData, projectData, portfolioData] = await Promise.all([
        fetchTenderBids(),
        fetchBidEvaluations(),
        fetchPaymentClaims(),
        fetchProjects(),
        fetchPortfolioKpiSummary(),
      ]);
      setBids(bidsData);
      setEvaluations(evalsData);
      setClaims(claimsData);
      setProjects(projectData);
      setPortfolio(portfolioData);
      setLastSyncedAt(new Date().toISOString());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load TAC dashboard data."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const summary = useMemo(() => {
    const pendingBids = bids.filter(
      (b) => b.status === "Submitted" || b.status === "Under Review",
    );
    const pendingClaims = claims.filter(
      (c: any) => c.status === "RMT Approved" || c.status === "Verified",
    );
    const evaluatedBidIds = new Set(evaluations.map((e) => e.bid));
    const unauditedBids = pendingBids.filter((b) => !evaluatedBidIds.has(b.id));
    return {
      pendingBidCount: unauditedBids.length,
      pendingClaimCount: pendingClaims.length,
      totalProjects: portfolio?.total_projects ?? projects.length,
      overallProgress: portfolio?.overall_progress_pct ?? 0,
      projectsAtRisk: portfolio?.projects_at_risk ?? 0,
      projectsOnTrack: portfolio?.projects_on_track ?? 0,
      pendingBids,
      pendingClaims,
      unauditedBids,
    };
  }, [bids, evaluations, claims, projects, portfolio]);

  const recentEvaluations = useMemo(() => {
    return [...evaluations]
      .sort((a, b) => (b.updated_at || b.created_at || "").localeCompare(a.updated_at || a.created_at || ""))
      .slice(0, 5);
  }, [evaluations]);

  const projectsById = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading TAC dashboard...
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">TAC Overview</h1>
          <p className="text-slate-500">Technical review, bid evaluations, and claim endorsements at a glance.</p>
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <button
          type="button"
          onClick={() => onNavigate?.("evaluations")}
          className="card group p-5 text-left transition hover:border-blue-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Pending Bid Reviews</p>
            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 transition group-hover:bg-blue-200">
              <ClipboardCheck size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.pendingBidCount}</p>
          <p className="mt-1 text-xs text-slate-500">Bids awaiting TAC technical evaluation</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("payments")}
          className="card group p-5 text-left transition hover:border-amber-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Pending Claim Endorsements</p>
            <div className="rounded-lg bg-amber-100 p-2 text-amber-600 transition group-hover:bg-amber-200">
              <CreditCard size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.pendingClaimCount}</p>
          <p className="mt-1 text-xs text-slate-500">Claims requiring TAC technical endorsement</p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate?.("projects")}
          className="card group p-5 text-left transition hover:border-emerald-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Active Projects</p>
            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600 transition group-hover:bg-emerald-200">
              <FolderKanban size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.totalProjects}</p>
          <p className="mt-1 text-xs text-slate-500">{summary.overallProgress}% overall progress</p>
        </button>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Portfolio Health</p>
            <div className={`rounded-lg p-2 transition ${summary.projectsAtRisk > 0 ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600"}`}>
              <ShieldCheck size={18} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <p className="text-3xl font-bold text-slate-900">{summary.projectsOnTrack}</p>
            <span className="text-sm text-slate-400">on track</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {summary.projectsAtRisk > 0 ? (
              <span className="font-semibold text-rose-600">{summary.projectsAtRisk} at risk</span>
            ) : (
              <span className="font-semibold text-emerald-600">No projects at risk</span>
            )}
          </p>
        </div>
      </div>

      {/* Pending Workload — Bids + Claims */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Pending Bid Reviews */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Pending Bid Reviews</h3>
              <p className="text-xs text-slate-500">{summary.unauditedBids.length} bid{summary.unauditedBids.length === 1 ? "" : "s"} awaiting your evaluation</p>
            </div>
            {summary.unauditedBids.length > 0 && (
              <button
                type="button"
                onClick={() => onNavigate?.("evaluations")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700"
              >
                View all <ChevronRight size={14} />
              </button>
            )}
          </div>
          <div className="divide-y divide-slate-100">
            {summary.unauditedBids.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-500" />
                All caught up — no bids awaiting TAC review.
              </div>
            ) : (
              summary.unauditedBids.slice(0, 5).map((bid) => {
                const project = bid.tender_name || bid.tender_reference || "Untitled Tender";
                return (
                  <div key={bid.id} className="flex items-center justify-between px-5 py-3 transition hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-slate-900">{bid.vendor_name}</p>
                      <p className="truncate text-xs text-slate-500">
                        {project}
                        {bid.preferred_district ? ` • ${bid.preferred_district}` : ""}
                        {bid.tech_tier ? ` • ${bid.tech_tier}` : ""}
                      </p>
                    </div>
                    <span className="ml-3 inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-bold text-blue-700">
                      <Clock size={12} /> {bid.status}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Pending Claim Endorsements */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Pending Claim Endorsements</h3>
              <p className="text-xs text-slate-500">{summary.pendingClaims.length} claim{summary.pendingClaims.length === 1 ? "" : "s"} requiring TAC endorsement</p>
            </div>
            {summary.pendingClaims.length > 0 && (
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
            {summary.pendingClaims.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-500" />
                All caught up — no claims awaiting TAC endorsement.
              </div>
            ) : (
              summary.pendingClaims.slice(0, 5).map((claim: any) => {
                const project = projectsById[claim.projectId];
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
                      <Clock size={12} /> {claim.status}
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
              <h3 className="text-lg font-bold text-slate-900">Project Health</h3>
              <p className="text-xs text-slate-500">KPI performance across all active projects</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate?.("projects")}
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

      {/* Quick Actions + Recent Evaluations */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Quick Actions */}
        <div className="card p-5">
          <h3 className="mb-4 text-lg font-bold text-slate-900">Quick Actions</h3>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => onNavigate?.("evaluations")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-blue-200 hover:bg-blue-50"
            >
              <div className="rounded-lg bg-blue-100 p-2 text-blue-600">
                <ClipboardCheck size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Bid Evaluations</p>
                <p className="text-xs text-slate-500">Technical scoring and shortlisting</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.("payments")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-amber-200 hover:bg-amber-50"
            >
              <div className="rounded-lg bg-amber-100 p-2 text-amber-600">
                <CreditCard size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Claim Reviews</p>
                <p className="text-xs text-slate-500">Technical endorsement of payment claims</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.("projects")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-emerald-200 hover:bg-emerald-50"
            >
              <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600">
                <FolderKanban size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Project Hub</p>
                <p className="text-xs text-slate-500">KPI scorecards and project status</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.("blacklisting")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-rose-200 hover:bg-rose-50"
            >
              <div className="rounded-lg bg-rose-100 p-2 text-rose-600">
                <FileWarning size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Blacklisting</p>
                <p className="text-xs text-slate-500">Non-compliance cases and appeals</p>
              </div>
              <ChevronRight size={16} className="text-slate-400" />
            </button>
          </div>
        </div>

        {/* Recent Evaluations */}
        <div className="card p-5 lg:col-span-2">
          <h3 className="mb-4 text-lg font-bold text-slate-900">Recent Evaluations</h3>
          <div className="divide-y divide-slate-100">
            {recentEvaluations.length === 0 ? (
              <div className="py-8 text-center text-sm text-slate-500">
                <ClipboardCheck size={20} className="mx-auto mb-2 text-slate-400" />
                No evaluations submitted yet.
              </div>
            ) : (
              recentEvaluations.map((evaluation) => {
                const bid = bids.find((b) => b.id === evaluation.bid);
                const project = bid ? (bid.tender_name || bid.tender_reference || "Tender") : "Unknown";
                const scores = evaluation.scores || {};
                const hasScores = Object.values(scores).some((v) => v != null && v !== 0);
                const avgScore = hasScores
                  ? Math.round(
                      Object.values(scores)
                        .filter((v): v is number => v != null)
                        .reduce((sum, v, _, arr) => sum + v / arr.length, 0),
                    )
                  : null;
                return (
                  <div key={evaluation.id} className="flex items-center justify-between px-5 py-3 transition hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-slate-900">
                        {bid?.vendor_name || evaluation.bid}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        {project}
                        {evaluation.submitted_at ? ` • ${formatDateTime(evaluation.submitted_at)}` : ""}
                      </p>
                    </div>
                    <div className="ml-3 flex items-center gap-2">
                      {avgScore != null && (
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${
                          avgScore >= 70 ? "bg-emerald-100 text-emerald-700" :
                          avgScore >= 50 ? "bg-amber-100 text-amber-700" :
                          "bg-rose-100 text-rose-700"
                        }`}>
                          {avgScore}%
                        </span>
                      )}
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${
                        evaluation.status === "submitted" ? "bg-blue-100 text-blue-700" :
                        evaluation.status === "draft" ? "bg-slate-100 text-slate-600" :
                        "bg-emerald-100 text-emerald-700"
                      }`}>
                        {evaluation.status || "Draft"}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
