import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  CreditCard,
  FileText,
  FolderKanban,
  Loader2,
  MessageSquare,
  RefreshCw,
  Send,
  Shield,
  ShieldCheck,
  TrendingUp,
  Users,
  X,
  Building2,
  Calendar,
  User,
  ExternalLink,
} from "lucide-react";
import {
  fetchConcerns,
  fetchAuditFindings,
  fetchProjects,
  fetchPaymentClaims,
  fetchPortfolioKpiSummary,
  updateConcern,
  updateAuditFinding,
  createConcernResponse,
  respondAuditFinding,
} from "../api";
import {
  Concern,
  PaymentClaim,
  PortfolioKpiSummary,
  Project,
} from "../types";
import { MacroKpiPortal } from "./RoleBasedKpiPanels";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");
const formatDate = (value?: string | null) => {
  if (!value) return "N/A";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const getSeverityIcon = (severity: string | undefined) => {
  if (severity === "critical") return <AlertCircle size={14} className="text-rose-600" />;
  if (severity === "high" || severity === "major") return <AlertTriangle size={14} className="text-rose-500" />;
  if (severity === "medium" || severity === "minor") return <AlertTriangle size={14} className="text-orange-500" />;
  return <AlertCircle size={14} className="text-amber-500" />;
};

const getSeverityLabel = (severity: string | undefined) => {
  if (severity === "critical") return "CRITICAL";
  if (severity === "high" || severity === "major") return "MAJOR";
  if (severity === "medium" || severity === "minor") return "MINOR";
  return "OBSERVATION";
};

const getSeverityBadgeColor = (severity: string | undefined) => {
  if (severity === "critical") return "bg-rose-600 text-white";
  if (severity === "high" || severity === "major") return "bg-rose-500 text-white";
  if (severity === "medium" || severity === "minor") return "bg-orange-500 text-white";
  return "bg-amber-400 text-amber-900";
};

export function PscDashboard({ currentUser, onNavigate }: { currentUser?: any; onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [concerns, setConcerns] = useState<Concern[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
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
      const [projectData, claimsData, concernsData, findingsData, portfolioData] = await Promise.all([
        fetchProjects(),
        fetchPaymentClaims(),
        fetchConcerns(),
        fetchAuditFindings(),
        fetchPortfolioKpiSummary(),
      ]);
      setProjects(projectData);
      setClaims(claimsData);
      setConcerns(concernsData);
      setFindings(findingsData);
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
    const escalatedConcerns = concerns.filter(
      (c) => (c as any).notifyPsc || (c as any).notify_psc || c.status === "escalated_to_psc",
    );
    const openFindings = findings.filter((f) => f.status !== "resolved");
    const totalPaid = claims
      .filter((c) => c.status === "Completed" || c.status === "Paid")
      .reduce((sum, c) => sum + (c.claimAmount || 0), 0);
    const openIssuesCount = escalatedConcerns.length + openFindings.length;
    return {
      totalProjects: portfolio?.total_projects ?? projects.length,
      pendingApprovalsCount: pendingApprovals.length,
      pendingApprovals,
      openIssuesCount,
      escalatedConcerns,
      openFindings,
      totalPaid,
      overallProgress: portfolio?.overall_progress_pct ?? 0,
      projectsAtRisk: portfolio?.projects_at_risk ?? 0,
      projectsOnTrack: portfolio?.projects_on_track ?? 0,
    };
  }, [projects, claims, concerns, findings, portfolio]);

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
          <p className="text-slate-500">National oversight — portfolio health, financial approvals, and escalated issues.</p>
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

        <button
          type="button"
          onClick={() => onNavigate?.("issues")}
          className="card group p-5 text-left transition hover:border-rose-300 hover:shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Open Issues</p>
            <div className={`rounded-lg p-2 transition ${summary.openIssuesCount > 0 ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600"}`}>
              <AlertTriangle size={18} />
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold text-slate-900">{summary.openIssuesCount}</p>
          <p className="mt-1 text-xs text-slate-500">
            {summary.escalatedConcerns.length} concerns + {summary.openFindings.length} findings
          </p>
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

      {/* Pending Approvals + Active Issues */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
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

        {/* Active Issues */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-slate-100 p-5">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Active Issues</h3>
              <p className="text-xs text-slate-500">{summary.openIssuesCount} issue{summary.openIssuesCount === 1 ? "" : "s"} requiring PSC attention</p>
            </div>
            {summary.openIssuesCount > 0 && (
              <button
                type="button"
                onClick={() => onNavigate?.("issues")}
                className="inline-flex items-center gap-1 text-xs font-semibold text-rose-600 hover:text-rose-700"
              >
                View all <ChevronRight size={14} />
              </button>
            )}
          </div>
          <div className="divide-y divide-slate-100">
            {summary.openIssuesCount === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-500">
                <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-500" />
                No active issues requiring PSC attention.
              </div>
            ) : (
              <>
                {summary.openFindings.slice(0, 3).map((finding: any) => (
                  <div key={finding.id} className="flex items-center justify-between px-5 py-3 transition hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-slate-900">Audit Finding</p>
                        <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold ${getSeverityBadgeColor(finding.risk_level)}`}>
                          {getSeverityIcon(finding.risk_level)} {getSeverityLabel(finding.risk_level)}
                        </span>
                      </div>
                      <p className="mt-0.5 max-w-md truncate text-xs text-slate-500">{finding.description}</p>
                    </div>
                    <span className="ml-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-700">
                      {finding.status?.replace(/_/g, " ") || "Open"}
                    </span>
                  </div>
                ))}
                {summary.escalatedConcerns.slice(0, 3).map((concern: any) => (
                  <div key={concern.id} className="flex items-center justify-between px-5 py-3 transition hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-slate-900">DoE Concern</p>
                        <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold ${getSeverityBadgeColor(concern.severity)}`}>
                          {getSeverityIcon(concern.severity)} {getSeverityLabel(concern.severity)}
                        </span>
                      </div>
                      <p className="mt-0.5 max-w-md truncate text-xs text-slate-500">{concern.description}</p>
                    </div>
                    <span className="ml-3 inline-flex rounded-full bg-rose-100 px-2.5 py-1 text-[11px] font-bold text-rose-700">
                      {concern.status?.replace(/_/g, " ") || "Open"}
                    </span>
                  </div>
                ))}
              </>
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
              onClick={() => onNavigate?.("issues")}
              className="flex w-full items-center gap-3 rounded-xl border border-slate-100 px-4 py-3 text-left transition hover:border-rose-200 hover:bg-rose-50"
            >
              <div className="rounded-lg bg-rose-100 p-2 text-rose-600">
                <AlertTriangle size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Issues & Concerns</p>
                <p className="text-xs text-slate-500">Escalated concerns and audit findings</p>
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

export default function PscIssuesView({ currentUser }: { currentUser?: any }) {
  const [loading, setLoading] = useState(true);
  const [concerns, setConcerns] = useState<any[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [pscComment, setPscComment] = useState("");
  const [submittingComment, setSubmittingComment] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [concernsData, findingsData, projList, claimsData] = await Promise.all([
        fetchConcerns(),
        fetchAuditFindings(),
        fetchProjects(),
        fetchPaymentClaims(),
      ]);
      setConcerns(concernsData);
      setFindings(findingsData);
      setProjects(projList);
      setClaims(claimsData);
    } catch (err) {
      console.error("Failed to load PSC issues:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const projectMap = useMemo(() => {
    const map: Record<string, any> = {};
    projects.forEach((p: Project) => { map[p.id] = p; });
    return map;
  }, [projects]);

  const escalatedConcerns = useMemo(() => {
    return concerns.filter((c: any) => c.notifyPsc || c.notify_psc || c.status === "escalated_to_psc");
  }, [concerns]);

  const escalatedFindings = useMemo(() => {
    return findings;
  }, [findings]);

  const handleAddPscComment = async () => {
    if (!pscComment.trim() || !selectedItem) return;
    setSubmittingComment(true);
    try {
      if (selectedItem.type === "DoE Concern") {
        await createConcernResponse(selectedItem.id, {
          response_text: pscComment,
          action_taken: "psc_directive",
          responded_by: currentUser?.id || currentUser?.pk || currentUser?.user_id || currentUser?.sub,
        });
      } else if (selectedItem.type === "Audit Finding") {
        await respondAuditFinding(selectedItem.id, {
          response: pscComment,
          action_taken: "psc_directive",
        });
      }
      alert("PSC comment added successfully! RMT has been notified.");
      setPscComment("");
      setSelectedItem(null);
      void loadData();
      window.dispatchEvent(new CustomEvent("rbf-notifications-refresh"));
    } catch (err) {
      console.error("Failed to add PSC comment:", err);
      alert("Failed to add comment. Please try again.");
    } finally {
      setSubmittingComment(false);
    }
  };

  const handleResolve = async () => {
    if (!selectedItem) return;
    setSubmittingComment(true);
    try {
      if (selectedItem.type === "DoE Concern") {
        await updateConcern(selectedItem.id, { status: "resolved" });
      } else if (selectedItem.type === "Audit Finding") {
        await updateAuditFinding(selectedItem.id, { status: "resolved" });
      }
      alert("Issue has been marked as RESOLVED by PSC!");
      setSelectedItem(null);
      void loadData();
    } catch (err) {
      console.error("Failed to resolve:", err);
      alert("Failed to resolve. Please try again.");
    } finally {
      setSubmittingComment(false);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading PSC issues...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><AlertTriangle size={20} className="text-amber-500" /> Items Requiring Your Attention</h1>
          <p className="text-sm text-slate-500">Audit findings and escalated concerns requiring PSC oversight</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div className="rounded-xl bg-amber-50 p-4 border border-amber-200">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Audit Findings (Raised to PSC)</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{escalatedFindings.length}</p>
        </div>
        <div className="rounded-xl bg-rose-50 p-4 border border-rose-200">
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">DoE Concerns (Escalated)</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">{escalatedConcerns.length}</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-4 border border-slate-200">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Requiring Action</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{escalatedFindings.length + escalatedConcerns.length}</p>
        </div>
      </div>

      {escalatedFindings.length === 0 && escalatedConcerns.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">
          <CheckCircle2 size={48} className="mx-auto mb-4 text-emerald-500" />
          No issues require your attention at this time.
        </div>
      ) : (
        <div className="space-y-6">
          {escalatedFindings.length > 0 && (
            <div className="card p-6 border-l-4 border-amber-500">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <FileText size={20} className="text-amber-600" />
                Audit Findings (Raised to PSC)
              </h3>
              <div className="space-y-3">
                {escalatedFindings.map((finding: any) => (
                  <div key={finding.id} className="p-4 rounded-xl border border-amber-200 bg-amber-50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-amber-900">{finding.id}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${getSeverityBadgeColor(finding.risk_level)}`}>
                          {getSeverityIcon(finding.risk_level)} {getSeverityLabel(finding.risk_level)}
                        </span>
                        {finding.linked_project && (
                          <span className="text-xs text-slate-500">— PRJ-{finding.linked_project}</span>
                        )}
                      </div>
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${finding.status === "resolved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {finding.status?.replace(/_/g, " ") || "Open"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2 line-clamp-2">{finding.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                      <span>Raised by: Auditor</span>
                      <span>{formatDateTime(finding.created_at)}</span>
                    </div>
                    <button
                      onClick={() => setSelectedItem({ ...finding, type: "Audit Finding", category: finding.finding_category, severity: finding.risk_level, project: finding.linked_project ? projectMap[finding.linked_project] : null })}
                      className="btn-secondary text-xs"
                    >
                      View Full Finding
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {escalatedConcerns.length > 0 && (
            <div className="card p-6 border-l-4 border-rose-500">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <AlertTriangle size={20} className="text-rose-600" />
                DoE Concerns Escalated to PSC
              </h3>
              <div className="space-y-3">
                {escalatedConcerns.map((concern: any) => (
                  <div key={concern.id} className="p-4 rounded-xl border border-rose-200 bg-rose-50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-rose-900">{concern.id}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${getSeverityBadgeColor(concern.severity)}`}>
                          {getSeverityIcon(concern.severity)} {getSeverityLabel(concern.severity)}
                        </span>
                        {concern.linked_project && (
                          <span className="text-xs text-slate-500">— PRJ-{concern.linked_project}</span>
                        )}
                      </div>
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${concern.status === "resolved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {concern.status?.replace(/_/g, " ") || "Open"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2 line-clamp-2">{concern.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                      <span>Raised by: {concern.raised_by_username || "DoE"}</span>
                      <span>{formatDateTime(concern.created_at)}</span>
                    </div>
                    <button
                      onClick={() => setSelectedItem({ ...concern, type: "DoE Concern", project: concern.linked_project ? projectMap[concern.linked_project] : null })}
                      className="btn-secondary text-xs"
                    >
                      View Full Detail
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {selectedItem && (
        <PscIssueDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          pscComment={pscComment}
          setPscComment={setPscComment}
          onAddComment={handleAddPscComment}
          onResolve={handleResolve}
          submitting={submittingComment}
        />
      )}
    </div>
  );
}

function PscIssueDetailModal({ item, onClose, pscComment, setPscComment, onAddComment, onResolve, submitting }: {
  item: any;
  onClose: () => void;
  pscComment: string;
  setPscComment: (v: string) => void;
  onAddComment: () => void;
  onResolve: () => void;
  submitting: boolean;
}) {
  const isAuditFinding = item.type === "Audit Finding";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl shadow-xl max-h-[90vh] flex flex-col">
        <div className={`text-white px-6 py-4 rounded-t-2xl flex-shrink-0 ${isAuditFinding ? "bg-amber-600" : "bg-rose-600"}`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold flex items-center gap-2">
                {isAuditFinding ? "AUDIT FINDING" : "CONCERN DETAIL"} — {item.id}
              </h3>
              <p className="text-white/80 text-sm mt-1">
                {isAuditFinding ? item.category : item.concern_type?.replace(/_/g, " ") || "DoE Concern"}
              </p>
            </div>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">{isAuditFinding ? "FINDING" : "CONCERN"} INFORMATION</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Finding ID" : "Concern ID"}</p>
                <p className="font-medium">{item.id}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Risk Level" : "Severity"}</p>
                <p className={`font-medium px-2 py-0.5 rounded inline-flex items-center gap-1 ${getSeverityBadgeColor(item.severity)}`}>
                  {getSeverityIcon(item.severity)} {getSeverityLabel(item.severity)}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Status</p>
                <p className="font-medium">{item.status?.replace(/_/g, " ") || "Open"}</p>
              </div>
              {item.project && (
                <div>
                  <p className="text-slate-500 text-xs">Linked Project</p>
                  <p className="font-medium flex items-center gap-1">
                    <Building2 size={14} />
                    {item.project.projectReference || `PRJ-${item.linked_project}`} — {item.project.vendorName || "Vendor"}
                  </p>
                </div>
              )}
              <div>
                <p className="text-slate-500 text-xs">Raised By</p>
                <p className="font-medium flex items-center gap-1">
                  <User size={14} />
                  {isAuditFinding ? "Auditor" : (item.raised_by_username || "DoE")}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Date Raised</p>
                <p className="font-medium flex items-center gap-1">
                  <Calendar size={14} />
                  {formatDate(item.date || item.created_at)}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">{isAuditFinding ? "FINDING DESCRIPTION" : "DESCRIPTION"}</h4>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.description}"</p>
          </div>

          {isAuditFinding && item.recommended_action && (
            <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
              <h4 className="text-xs font-bold uppercase text-amber-700 mb-3">RECOMMENDED ACTION (by Auditor)</h4>
              <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.recommended_action}"</p>
            </div>
          )}

          {(item.responses && item.responses.length > 0) ? (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">RMT INVESTIGATION RESPONSE</h4>
              <div className="space-y-3">
                {item.responses.map((resp: any, idx: number) => (
                  <div key={idx} className="bg-white rounded-lg p-3 border border-slate-200">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">RMT Response</span>
                      <span className="text-xs text-slate-500">{formatDateTime(resp.created_at)}</span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2">{resp.response_text || resp.response}</p>
                    <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">
                      Action: {resp.action_taken?.replace(/_/g, " ") || "N/A"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
              <p className="text-sm text-amber-700">
                ⏳ RMT Response pending. You can request an update from RMT.
              </p>
            </div>
          )}

          <div className="bg-purple-50 rounded-xl p-4 border border-purple-200">
            <h4 className="text-xs font-bold uppercase text-purple-700 mb-3 flex items-center gap-2">
              <Shield size={14} /> PSC CAN:
            </h4>
            <ul className="text-sm text-slate-600 space-y-1">
              <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-600" /> View finding details</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-600" /> View RMT investigation response</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-600" /> Add PSC comment/directive below</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-600" /> Request RMT provide update by deadline</li>
              <li className="flex items-center gap-2"><CheckCircle2 size={14} className="text-emerald-600" /> Resolve escalated concerns (this one!)</li>
              <li className="flex items-center gap-2 text-slate-400"><X size={14} className="text-slate-400" /> Close audit findings (only Auditor can close)</li>
            </ul>
          </div>

          <div className="border-t pt-4">
            <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
              <MessageSquare size={16} />
              Add PSC Comment / Directive
            </h4>
            <textarea
              className="input-field min-h-[100px]"
              placeholder="Enter your directive, comment, or request for RMT update..."
              value={pscComment}
              onChange={(e) => setPscComment(e.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-between items-center px-6 py-4 border-t bg-slate-50 flex-shrink-0">
          <p className="text-xs text-slate-500">
            {isAuditFinding ? "Note: PSC can resolve escalated audit findings." : "Note: PSC can resolve escalated DoE concerns."}
          </p>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-secondary">Close</button>
            {item.status !== "resolved" && (
              <button
                onClick={onResolve}
                className="btn-primary flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700"
                disabled={submitting}
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                Mark as Resolved
              </button>
            )}
            <button
              onClick={onAddComment}
              className="btn-primary flex items-center gap-2"
              disabled={submitting || !pscComment.trim()}
            >
              {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              Add PSC Comment
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PscReports({ currentUser }: { currentUser?: any }) {
  return <PscIssuesView currentUser={currentUser} />;
}
