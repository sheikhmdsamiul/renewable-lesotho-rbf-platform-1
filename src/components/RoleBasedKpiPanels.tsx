import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  CreditCard,
  FileText,
  FolderKanban,
  Gauge,
  MapPinned,
  RadioTower,
  ShieldAlert,
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
  Wallet,
  Zap,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchAnomalyFlags,
  fetchMapInstallations,
  fetchPortfolioKpiSummary,
  fetchProjectKpiSummary,
  fetchProjects,
  fetchSmartMeterReadings,
  fetchTenders,
} from "../api";
import {
  AnomalyFlag,
  InstallationReport,
  MapInstallationRecord,
  PortfolioKpiSummary,
  Project,
  ProjectKpiSummary,
  SmartMeterReading,
  Tender,
  VerificationTask,
} from "../types";

function formatNumber(value: number, digits = 0) {
  return Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value: number, digits = 0) {
  return `${formatNumber(value, digits)}%`;
}

function formatCurrency(value: number) {
  return `M ${formatNumber(value, 2)}`;
}

function formatShortDate(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatMonthKey(monthKey: string) {
  const parsed = new Date(`${monthKey}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return monthKey;
  return parsed.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function parseDate(value?: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function daysBetween(now: Date, other: Date) {
  return Math.floor((now.getTime() - other.getTime()) / 86400000);
}

function hoursBetween(start: Date, end: Date) {
  return (end.getTime() - start.getTime()) / 3600000;
}

function statusTone(ok: boolean, warn = false) {
  if (ok) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (warn) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

function titleCase(value: string) {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function isCompletedTask(status: string) {
  return status === "Verified" || status === "Flagged" || status === "Partial";
}

function compareMonthKeys(a: string, b: string) {
  return a.localeCompare(b);
}

function getProjectReference(projectId: string, projectsById: Map<string, Project>, summariesById?: Map<string, ProjectKpiSummary>) {
  const summary = summariesById?.get(projectId);
  if (summary?.project.project_reference) return summary.project.project_reference;
  const project = projectsById.get(projectId);
  return project?.projectReference || `Project ${projectId}`;
}

function DashboardFrame({
  title,
  description,
  loading,
  error,
  refreshedAt,
  children,
}: {
  title: string;
  description: string;
  loading: boolean;
  error: string | null;
  refreshedAt?: string | null;
  children: React.ReactNode;
}) {
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
            <p className="text-slate-500">{description}</p>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading KPI dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
            <p className="text-slate-500">{description}</p>
          </div>
        </div>
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="text-slate-500">{description}</p>
        </div>
        {refreshedAt && (
          <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Refreshed {formatShortDate(refreshedAt)}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "slate",
  status,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ElementType;
  tone?: "slate" | "emerald" | "amber" | "rose" | "blue";
  status?: string;
}) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-900",
    emerald: "border-emerald-200 bg-emerald-50/80 text-emerald-900",
    amber: "border-amber-200 bg-amber-50/80 text-amber-900",
    rose: "border-rose-200 bg-rose-50/80 text-rose-900",
    blue: "border-blue-200 bg-blue-50/80 text-blue-900",
  } as const;

  return (
    <div className={`rounded-2xl border p-5 shadow-sm ${tones[tone]}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{label}</p>
          <p className="mt-2 text-3xl font-semibold">{value}</p>
          <p className="mt-2 text-sm opacity-80">{hint}</p>
          {status && <p className="mt-3 text-xs font-semibold uppercase tracking-wide opacity-75">{status}</p>}
        </div>
        <div className="rounded-xl bg-white/80 p-3 shadow-sm">
          <Icon size={22} />
        </div>
      </div>
    </div>
  );
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        {description && <p className="text-sm text-slate-500">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function ProgressMetric({
  label,
  value,
  targetLabel,
  percent,
  color,
  ok,
}: {
  label: string;
  value: string;
  targetLabel: string;
  percent: number;
  color: string;
  ok: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-900">{label}</p>
          <p className="text-xs text-slate-500">{targetLabel}</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone(ok, !ok)}`}>{value}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
      {message}
    </div>
  );
}

export function MacroKpiPortal({
  title,
  description,
  portalType,
}: {
  title: string;
  description: string;
  portalType?: "rbf" | "psc";
}) {
  const [portfolio, setPortfolio] = useState<PortfolioKpiSummary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [installations, setInstallations] = useState<MapInstallationRecord[]>([]);
  const [meterReadings, setMeterReadings] = useState<SmartMeterReading[]>([]);
  const [projectSummaries, setProjectSummaries] = useState<ProjectKpiSummary[]>([]);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [activeTendersPage, setActiveTendersPage] = useState(1);
  const activeTendersPerPage = 5;
  const [systemAlertsPage, setSystemAlertsPage] = useState(1);
  const systemAlertsPerPage = 8;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMacroDashboard = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    if (showLoader) setError(null);
    try {
      const results = await Promise.all([
        fetchPortfolioKpiSummary(),
        fetchProjects(),
        fetchMapInstallations(),
        fetchSmartMeterReadings(),
        ...(portalType === "rbf" ? [fetchTenders()] : []),
      ]);
      const [portfolioSummary, projectRows, mapData, readings] = results;
      setPortfolio(portfolioSummary);
      setProjects(projectRows);
      setInstallations(mapData.installations);
      setMeterReadings(readings);

      if (portalType === "rbf" && results.length > 4) {
        const tenderData = results[4] as Tender[];
        setTenders(tenderData);
      }

      const summaries = await Promise.all(projectRows.map((project) => fetchProjectKpiSummary(project.id).catch(() => null)));
      setProjectSummaries(summaries.filter(Boolean) as ProjectKpiSummary[]);
    } catch (err: any) {
      if (showLoader) setError(String(err?.message || "Unable to load macro KPI dashboard."));
    } finally {
      if (showLoader) setLoading(false);
    }
  }, [portalType]);

  useEffect(() => {
    void loadMacroDashboard(true);
  }, [loadMacroDashboard]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      void loadMacroDashboard(false);
    }, 20000);
    return () => clearInterval(intervalId);
  }, [loadMacroDashboard]);

  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const summariesById = useMemo(() => new Map(projectSummaries.map((summary) => [summary.project.id, summary])), [projectSummaries]);
  const refreshedAt = useMemo(
    () => projectSummaries.map((item) => item.generated_at).sort().slice(-1)[0] || null,
    [projectSummaries]
  );

  const districtRows = useMemo(() => {
    const byDistrict = new Map<string, { district: string; verified: number; pending: number; flagged: number; total: number }>();
    installations.forEach((row) => {
      const district = row.district || "Unassigned";
      const entry = byDistrict.get(district) || { district, verified: 0, pending: 0, flagged: 0, total: 0 };
      entry.total += 1;
      if (row.gisStatus === "green") entry.verified += 1;
      else if (row.gisStatus === "red") entry.flagged += 1;
      else entry.pending += 1;
      byDistrict.set(district, entry);
    });

    return Array.from(byDistrict.values())
      .map((entry) => ({
        ...entry,
        score: entry.total ? (entry.verified / entry.total) * 100 : 0,
        backlogPct: entry.total ? ((entry.pending + entry.flagged) / entry.total) * 100 : 0,
      }))
      .sort((a, b) => a.district.localeCompare(b.district));
  }, [installations]);

  const inclusion = useMemo(() => {
    const totalVerified = projectSummaries.reduce((sum, item) => sum + item.gender_kpi.total_verified, 0);
    const femaleCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.female_headed.count || 0), 0);
    const vulnerableCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.vulnerable.count || 0), 0);
    const lowIncomeCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.low_income.count || 0), 0);

    const femalePct = totalVerified ? (femaleCount / totalVerified) * 100 : 0;
    const vulnerablePct = totalVerified ? (vulnerableCount / totalVerified) * 100 : 0;
    const lowIncomePct = totalVerified ? (lowIncomeCount / totalVerified) * 100 : 0;

    return {
      totalVerified,
      femalePct,
      vulnerablePct,
      lowIncomePct,
      metCount: Number(femalePct >= 50) + Number(vulnerablePct >= 30) + Number(lowIncomePct >= 60),
    };
  }, [projectSummaries]);

  const budgetSummary = useMemo(() => {
    const totalBudget = projects.reduce((sum, project) => sum + Number(project.budget || project.contractValue || project.milestoneTotalAmount || 0), 0);
    const paidFromPortfolio = Number(portfolio?.total_paid_amount || 0);
    const paidFromSummaries = projectSummaries.reduce((sum, summary) => sum + Number(summary.payments_data?.summary?.total_disbursed || 0), 0);
    const paidAmount = paidFromPortfolio > 0 ? paidFromPortfolio : paidFromSummaries;
    const progressPct = Number(portfolio?.overall_progress_pct || 0);
    const paidPct = totalBudget > 0 ? (paidAmount / totalBudget) * 100 : 0;
    const pendingFromSummaries = projectSummaries.reduce((sum, summary) => sum + Number(summary.payments_data?.summary?.total_pending || 0), 0);
    const pendingAmount = pendingFromSummaries > 0 ? pendingFromSummaries : Math.max(0, totalBudget - paidAmount);
    const configuredProgramBudget = Number(portfolio?.national_main_program_budget || 0);
    const totalContracted = configuredProgramBudget > 0 ? configuredProgramBudget : totalBudget;
    const pendingCount = projectSummaries.reduce((count, summary) => {
      const claims = summary.payments_data?.claims || [];
      return count + claims.filter((claim) => !["Completed", "Paid", "Rejected"].includes(claim.status)).length;
    }, 0);
    return {
      totalBudget,
      paidAmount,
      progressPct,
      paidPct,
      gapPct: Number((progressPct - paidPct).toFixed(1)),
      totalContracted,
      pendingAmount,
      pendingCount,
      chartRows: [
        { name: "Work Completed", value: Number(progressPct.toFixed(1)), fill: "#1D9E75" },
        { name: "Budget Paid", value: Number(paidPct.toFixed(1)), fill: "#1d4ed8" },
      ],
    };
  }, [portfolio, projectSummaries, projects]);

  const latestMeterByProject = useMemo(() => {
    const latest = new Map<string, Date>();
    meterReadings.forEach((reading) => {
      const parsed = parseDate(reading.recordedAt || reading.createdAt);
      if (!parsed) return;
      const current = latest.get(reading.projectId);
      if (!current || parsed > current) latest.set(reading.projectId, parsed);
    });
    return latest;
  }, [meterReadings]);

  const redFlags = useMemo(() => {
    const now = new Date();
    return projects
      .map((project) => {
        const latest = latestMeterByProject.get(project.id) || null;
        const daysSince = latest ? daysBetween(now, latest) : null;
        const summary = summariesById.get(project.id);
        const unresolvedFlags = Number(project.unresolvedFlagCount || 0);
        const reasons = [
          daysSince == null ? "No meter feed yet" : daysSince >= 30 ? `${daysSince} days since last meter reading` : null,
          unresolvedFlags > 0 ? `${unresolvedFlags} unresolved anomaly flag${unresolvedFlags === 1 ? "" : "s"}` : null,
          summary && !summary.installation_progress.on_track ? "Installation progress below plan" : null,
        ].filter(Boolean) as string[];
        return {
          id: project.id,
          projectReference: project.projectReference || `Project ${project.id}`,
          vendorName: project.vendorName,
          district: project.district || project.region || "N/A",
          reasons,
          daysSince,
        };
      })
      .filter((item) => item.reasons.length > 0 && (item.daysSince == null || item.daysSince >= 30 || item.reasons.length > 1))
      .sort((a, b) => (b.daysSince || 9999) - (a.daysSince || 9999));
  }, [latestMeterByProject, projects, summariesById]);

  const watchlist = useMemo(() => {
    return projects
      .map((project) => {
        const summary = summariesById.get(project.id);
        const backlog = summary ? summary.installation_progress.pending + summary.installation_progress.flagged : 0;
        const unresolvedFlags = Number(project.unresolvedFlagCount || 0);
        const readinessScore = [
          summary?.installation_progress.on_track ? 1 : 0,
          (summary?.uptime_kpi.met ?? false) ? 1 : 0,
          (summary?.gender_kpi.all_gender_kpis_met ?? false) ? 1 : 0,
          unresolvedFlags === 0 ? 1 : 0,
        ].reduce((sum, value) => sum + value, 0);
        return {
          id: project.id,
          projectReference: project.projectReference || `Project ${project.id}`,
          district: project.district || project.region || "N/A",
          vendorName: project.vendorName,
          progressPct: summary?.installation_progress.progress_pct ?? project.progress ?? 0,
          backlog,
          unresolvedFlags,
          readinessScore,
        };
      })
      .sort((a, b) => a.readinessScore - b.readinessScore || b.backlog - a.backlog)
      .slice(0, 5);
  }, [projects, summariesById]);

  const laggingDistrictCount = districtRows.filter((item) => item.score < 40).length;

  const tenderStats = useMemo(() => {
    const published = tenders.filter(t => t.status === "Published");
    const closingSoon = published.filter(t => {
      const deadline = Date.parse(t.lastDateSubmission || t.deadline || "");
      if (Number.isNaN(deadline)) return false;
      const days = Math.ceil((deadline - Date.now()) / (1000 * 60 * 60 * 24));
      return days >= 0 && days <= 7;
    });
    const newest = [...published].sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime());
    return { published: published.length, closingSoon: closingSoon.length, total: tenders.length, newest };
  }, [tenders]);

  return (
    <DashboardFrame title={title} description={description} loading={loading} error={error} refreshedAt={refreshedAt}>
      {portfolio && (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <KpiCard
              label="National Progress"
              value={`${portfolio.total_verified}/${portfolio.total_installations_target}`}
              hint={`${formatPercent(portfolio.overall_progress_pct, 1)} of the national verified-installation goal`}
              icon={Target}
              tone="emerald"
              status={portfolio.projects_on_track >= portfolio.projects_at_risk ? "Portfolio broadly on track" : "Recovery action needed"}
            />
            <KpiCard
              label="Total Projects"
              value={String(projects.length)}
              hint={`${projectSummaries.length} with KPI data loaded`}
              icon={FolderKanban}
              tone="emerald"
              status={portfolio?.projects_on_track && portfolio?.projects_at_risk ? `${portfolio.projects_on_track} on track, ${portfolio.projects_at_risk} at risk` : "Loading..."}
            />
            <KpiCard
              label="Total Paid Out"
              value={formatCurrency(budgetSummary.paidAmount)}
              hint="Across all projects"
              icon={Wallet}
              tone="blue"
              status={`${formatPercent(budgetSummary.totalContracted > 0 ? (budgetSummary.paidAmount / budgetSummary.totalContracted) * 100 : 0, 1)} of contracted value`}
            />
            <KpiCard
              label="Disbursement Tracker"
              value={`${formatCurrency(budgetSummary.totalContracted)}`}
              hint={`Paid: ${formatCurrency(budgetSummary.paidAmount)} | Pending: ${formatCurrency(budgetSummary.pendingAmount)}`}
              icon={CreditCard}
              tone={budgetSummary.pendingAmount > 0 ? "amber" : "emerald"}
              status={budgetSummary.pendingAmount > 0 ? `${budgetSummary.pendingCount} approvals pending` : "All up to date"}
            />
            {portalType === "rbf" && (
              <KpiCard
                label="Tenders"
                value={String(tenderStats.published)}
                hint={`${tenderStats.closingSoon} closing soon`}
                icon={FileText}
                tone="blue"
                status={`${tenderStats.total} total, ${tenderStats.published} active`}
              />
            )}
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <SectionCard
              title="Global Progress Bar"
              description="Verified installations compared with the national delivery target and current portfolio completion pace."
            >
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-900">Verified installations</p>
                    <p className="text-xs text-slate-500">Scope: {portfolio.scope_label || "National portfolio"}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-semibold text-slate-900">
                      {portfolio.total_verified} / {portfolio.total_installations_target}
                    </p>
                    <p className="text-xs text-slate-500">{formatPercent(portfolio.overall_progress_pct, 1)} complete</p>
                  </div>
                </div>
                <div className="mt-5 h-4 overflow-hidden rounded-full bg-white">
                  <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-emerald-400 to-blue-600" style={{ width: `${Math.max(0, Math.min(100, portfolio.overall_progress_pct))}%` }} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Projects</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{portfolio.total_projects}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">On Track</p>
                    <p className="mt-1 text-lg font-semibold text-emerald-700">{portfolio.projects_on_track}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">At Risk</p>
                    <p className="mt-1 text-lg font-semibold text-amber-700">{portfolio.projects_at_risk}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">Completed</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{portfolio.projects_completed}</p>
                  </div>
                </div>
              </div>
            </SectionCard>

            <SectionCard
              title="Target Compliance"
              description="National inclusion performance against live program thresholds."
            >
              <div className="space-y-5">
                <ProgressMetric
                  label="Gender"
                  value={formatPercent(inclusion.femalePct, 1)}
                  targetLabel="Target: at least 50% female-headed households"
                  percent={inclusion.femalePct}
                  color="bg-emerald-500"
                  ok={inclusion.femalePct >= 50}
                />
                <ProgressMetric
                  label="Vulnerable Groups"
                  value={formatPercent(inclusion.vulnerablePct, 1)}
                  targetLabel="Target: at least 30% vulnerable households"
                  percent={inclusion.vulnerablePct}
                  color="bg-amber-500"
                  ok={inclusion.vulnerablePct >= 30}
                />
                <ProgressMetric
                  label="Low-Income"
                  value={formatPercent(inclusion.lowIncomePct, 1)}
                  targetLabel="Target: at least 60% low-income households"
                  percent={inclusion.lowIncomePct}
                  color="bg-blue-600"
                  ok={inclusion.lowIncomePct >= 60}
                />
              </div>
            </SectionCard>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.05fr_0.95fr]">
            <SectionCard
              title="Geographic KPI Map"
              description="District heat tiles showing where verified delivery is strongest and where backlog is accumulating."
            >
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {districtRows.map((district) => {
                  const tone =
                    district.score >= 70 ? "border-emerald-200 bg-emerald-50 text-emerald-900" :
                    district.score >= 40 ? "border-amber-200 bg-amber-50 text-amber-900" :
                    "border-rose-200 bg-rose-50 text-rose-900";
                  return (
                    <div key={district.district} className={`rounded-2xl border p-4 ${tone}`}>
                      <div className="flex items-center justify-between gap-4">
                        <p className="font-semibold">{district.district}</p>
                        <span className="text-xs font-semibold">{formatPercent(district.score, 0)}</span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/80">
                        <div className="h-full rounded-full bg-current opacity-75" style={{ width: `${district.score}%` }} />
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <p className="opacity-70">Green</p>
                          <p className="font-semibold">{district.verified}</p>
                        </div>
                        <div>
                          <p className="opacity-70">Yellow</p>
                          <p className="font-semibold">{district.pending}</p>
                        </div>
                        <div>
                          <p className="opacity-70">Red</p>
                          <p className="font-semibold">{district.flagged}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {districtRows.length === 0 && <EmptyState message="District performance tiles will appear once mapped installations are available." />}
              </div>
            </SectionCard>

            <SectionCard
              title="Budget vs. Performance"
              description="Compares verified work completed with milestone funds already paid."
            >
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={budgetSummary.chartRows}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} />
                    <YAxis axisLine={false} tickLine={false} unit="%" />
                    <Tooltip formatter={(value: number) => `${value}%`} />
                    <Bar dataKey="value" radius={[10, 10, 0, 0]}>
                      {budgetSummary.chartRows.map((entry) => (
                        <Cell key={entry.name} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Contract Value</p>
                  <p className="mt-1 text-lg font-semibold text-slate-900">{formatCurrency(budgetSummary.totalBudget)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Paid To Date</p>
                  <p className="mt-1 text-lg font-semibold text-blue-700">{formatCurrency(budgetSummary.paidAmount)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">Pacing Gap</p>
                  <p className={`mt-1 text-lg font-semibold ${budgetSummary.gapPct >= 0 ? "text-emerald-700" : "text-amber-700"}`}>
                    {budgetSummary.gapPct >= 0 ? "+" : ""}{formatPercent(budgetSummary.gapPct, 1)}
                  </p>
                </div>
              </div>
            </SectionCard>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <SectionCard
              title="Project Watchlist"
              description="The lowest-readiness projects based on progress, unresolved flags, and KPI compliance."
            >
              <div className="space-y-3">
                {watchlist.map((item) => (
                  <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="font-semibold text-slate-900">{item.projectReference}</p>
                        <p className="text-sm text-slate-500">{item.vendorName} • {item.district}</p>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(item.readinessScore >= 3, item.readinessScore === 2)}`}>
                        Readiness score {item.readinessScore}/4
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                      <div>
                        <p className="text-slate-500">Progress</p>
                        <p className="font-semibold text-slate-900">{formatPercent(item.progressPct, 1)}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Backlog</p>
                        <p className="font-semibold text-slate-900">{item.backlog}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Flags</p>
                        <p className="font-semibold text-slate-900">{item.unresolvedFlags}</p>
                      </div>
                    </div>
                  </div>
                ))}
                {watchlist.length === 0 && <EmptyState message="No projects currently need escalation attention." />}
              </div>
            </SectionCard>

            {(() => {
              const systemAlertsTotalPages = Math.max(1, Math.ceil(redFlags.length / systemAlertsPerPage));
              const systemAlertsSafePage = Math.min(Math.max(1, systemAlertsPage), systemAlertsTotalPages);
              const paginatedRedFlags = redFlags.slice(
                (systemAlertsSafePage - 1) * systemAlertsPerPage,
                systemAlertsSafePage * systemAlertsPerPage,
              );
              return (
                <SectionCard
                  title="System Alert"
                  description="Projects where meter data has not arrived within 30 days or multiple operational risks are stacking up."
                >
                  <div className="space-y-3">
                    {paginatedRedFlags.map((item) => (
                      <div key={item.id} className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                          <div>
                            <p className="font-semibold text-rose-900">{item.projectReference}</p>
                            <p className="text-sm text-rose-700">{item.vendorName} • {item.district}</p>
                          </div>
                          <span className="rounded-full border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-700">
                            {item.daysSince == null ? "No meter feed" : `${item.daysSince} days stale`}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.reasons.map((reason) => (
                            <span key={reason} className="rounded-full border border-rose-200 bg-white px-2.5 py-1 text-xs text-rose-800">
                              {reason}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                    {redFlags.length === 0 && <EmptyState message="No projects are currently breaching the live red-flag threshold." />}
                  </div>
                  {redFlags.length > systemAlertsPerPage && (
                    <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500">
                        Showing <span className="font-semibold text-slate-700">{((systemAlertsSafePage - 1) * systemAlertsPerPage) + 1}</span>
                        {"–"}
                        <span className="font-semibold text-slate-700">{Math.min(systemAlertsSafePage * systemAlertsPerPage, redFlags.length)}</span>
                        {" of "}
                        <span className="font-semibold text-slate-700">{redFlags.length}</span>
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setSystemAlertsPage((p) => Math.max(1, p - 1))}
                          disabled={systemAlertsSafePage <= 1}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-rose-300 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                        >
                          <ChevronLeft size={14} /> Previous
                        </button>
                        <span className="text-xs font-bold text-slate-600">
                          Page {systemAlertsSafePage} of {systemAlertsTotalPages}
                        </span>
                        <button
                          type="button"
                          onClick={() => setSystemAlertsPage((p) => Math.min(systemAlertsTotalPages, p + 1))}
                          disabled={systemAlertsSafePage >= systemAlertsTotalPages}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-rose-300 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                        >
                          Next <ChevronRight size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                </SectionCard>
              );
            })()}
          </div>

          {portalType === "rbf" && (() => {
            const activeTendersTotalPages = Math.max(1, Math.ceil(tenderStats.newest.length / activeTendersPerPage));
            const activeTendersSafePage = Math.min(Math.max(1, activeTendersPage), activeTendersTotalPages);
            const paginatedActiveTenders = tenderStats.newest.slice(
              (activeTendersSafePage - 1) * activeTendersPerPage,
              activeTendersSafePage * activeTendersPerPage,
            );
            return (
              <div className="grid grid-cols-1 gap-6">
                <SectionCard
                  title="Active Tenders Overview"
                  description="Current open tenders, upcoming deadlines, and procurement activity."
                >
                  {tenderStats.published === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
                      <FileText size={32} className="mx-auto mb-3 text-slate-300" />
                      <p className="text-sm font-medium text-slate-600">No active tenders</p>
                      <p className="mt-1 text-xs text-slate-400">Published tenders will appear here.</p>
                    </div>
                  ) : (
                    <>
                      <div className="space-y-3">
                        {paginatedActiveTenders.map((t) => {
                          const deadline = t.lastDateSubmission || t.deadline;
                          const deadlineMs = deadline ? Date.parse(deadline) : NaN;
                          const daysLeft = Number.isNaN(deadlineMs) ? null : Math.ceil((deadlineMs - Date.now()) / (1000 * 60 * 60 * 24));
                          const isClosingSoon = daysLeft !== null && daysLeft >= 0 && daysLeft <= 7;
                          const isExpired = daysLeft !== null && daysLeft < 0;
                          const deadlineLabel = daysLeft === null ? "N/A" : isExpired ? "Closed" : daysLeft === 0 ? "Today" : daysLeft === 1 ? "Tomorrow" : `${daysLeft}d left`;
                          const deadlineColor = isExpired ? "text-rose-600" : isClosingSoon ? "text-amber-600" : "text-emerald-600";
                          const deadlineBg = isExpired ? "border-rose-100 bg-rose-50" : isClosingSoon ? "border-amber-100 bg-amber-50" : "border-emerald-100 bg-emerald-50";

                          return (
                            <div key={t.id} className="rounded-xl border border-slate-100 bg-white p-4 transition-all hover:border-emerald-200 hover:shadow-sm">
                              <div className="mb-2 flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <div className="mb-1 flex items-center gap-2">
                                    <span className="text-[10px] font-mono text-slate-400">{t.referenceNumber}</span>
                                    <span className="rounded border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700">Published</span>
                                    {isClosingSoon && (
                                      <span className="rounded border border-amber-100 bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700">Urgent</span>
                                    )}
                                  </div>
                                  <p className="truncate text-sm font-bold text-slate-900">{t.name}</p>
                                  <p className="mt-0.5 text-xs text-slate-500">{t.department}</p>
                                </div>
                                <div className={`flex-shrink-0 rounded-lg border px-3 py-2 text-center ${deadlineBg}`}>
                                  <p className={`text-xs font-black ${deadlineColor}`}>{deadlineLabel}</p>
                                </div>
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {(t.technologyTypes || []).slice(0, 3).map((tech) => (
                                  <span key={tech} className="rounded border border-slate-100 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-500">{tech}</span>
                                ))}
                                <span className="rounded border border-blue-100 bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase text-blue-600">{t.category}</span>
                              </div>
                              {t.budget != null && (
                                <p className="mt-2 text-xs text-slate-500">Est. Budget: <span className="font-bold text-slate-900">M {t.budget.toLocaleString()}</span></p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
                        <p className="text-xs text-slate-500">
                          Showing <span className="font-semibold text-slate-700">{((activeTendersSafePage - 1) * activeTendersPerPage) + 1}</span>
                          {"–"}
                          <span className="font-semibold text-slate-700">{Math.min(activeTendersSafePage * activeTendersPerPage, tenderStats.newest.length)}</span>
                          {" of "}
                          <span className="font-semibold text-slate-700">{tenderStats.newest.length}</span>
                          <span className="ml-2 text-slate-400">· {tenderStats.closingSoon} closing soon</span>
                        </p>
                        {tenderStats.newest.length > activeTendersPerPage && (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => setActiveTendersPage((p) => Math.max(1, p - 1))}
                              disabled={activeTendersSafePage <= 1}
                              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                            >
                              <ChevronLeft size={14} /> Previous
                            </button>
                            <span className="text-xs font-bold text-slate-600">
                              Page {activeTendersSafePage} of {activeTendersTotalPages}
                            </span>
                            <button
                              type="button"
                              onClick={() => setActiveTendersPage((p) => Math.min(activeTendersTotalPages, p + 1))}
                              disabled={activeTendersSafePage >= activeTendersTotalPages}
                              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                            >
                              Next <ChevronRight size={14} />
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </SectionCard>
              </div>
            );
          })()}
        </>
      )}
    </DashboardFrame>
  );
}

export function VendorKpiPanel({
  projects,
  installationReports,
}: {
  projects: Project[];
  installationReports: InstallationReport[];
}) {
  const [projectSummaries, setProjectSummaries] = useState<ProjectKpiSummary[]>([]);
  const [meterReadings, setMeterReadings] = useState<SmartMeterReading[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [milestonePage, setMilestonePage] = useState(1);
  const milestonePerPage = 4;

  useEffect(() => {
    let active = true;
    const projectIds = projects.map((project) => project.id);

    if (projectIds.length === 0) {
      setProjectSummaries([]);
      setMeterReadings([]);
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    setError(null);

    Promise.all([
      Promise.all(projectIds.map((projectId) => fetchProjectKpiSummary(projectId).catch(() => null))),
      fetchSmartMeterReadings().catch(() => [] as SmartMeterReading[]),
    ])
      .then(([summaries, readings]) => {
        if (!active) return;
        setProjectSummaries(summaries.filter(Boolean) as ProjectKpiSummary[]);
        setMeterReadings(readings.filter((reading) => projectIds.includes(reading.projectId)));
      })
      .catch((err: any) => {
        if (active) setError(String(err?.message || "Unable to load vendor KPI summary."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [projects]);

  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const refreshedAt = useMemo(
    () => projectSummaries.map((item) => item.generated_at).sort().slice(-1)[0] || null,
    [projectSummaries]
  );

  const aggregatedProgress = useMemo(() => {
    return projectSummaries.reduce(
      (acc, summary) => {
        acc.verified += summary.installation_progress.verified;
        acc.pending += summary.installation_progress.pending;
        acc.flagged += summary.installation_progress.flagged;
        acc.target += summary.installation_progress.target;
        return acc;
      },
      { verified: 0, pending: 0, flagged: 0, target: 0 }
    );
  }, [projectSummaries]);

  const milestoneReadiness = useMemo(() => {
    return projectSummaries
      .map((summary) => {
        const milestone2 = summary.milestone_eligibility.milestone_2 || { eligible: false, status: "PENDING", conditions: {} };
        const conditions = Object.entries(milestone2.conditions || {});
        const metConditions = conditions.filter(([, met]) => met).length;
        const readinessPct = conditions.length ? (metConditions / conditions.length) * 100 : 0;
        const blockers = conditions.filter(([, met]) => !met).map(([key]) => titleCase(key));
        const verifiedPct = summary.installation_progress.target
          ? (summary.installation_progress.verified / summary.installation_progress.target) * 100
          : 0;

        return {
          projectId: summary.project.id,
          projectReference: summary.project.project_reference || `Project ${summary.project.id}`,
          verified: summary.installation_progress.verified,
          target: summary.installation_progress.target,
          verifiedPct,
          milestoneEligible: Boolean(milestone2.eligible),
          readinessPct,
          blockers,
          pending: summary.installation_progress.pending,
          flagged: summary.installation_progress.flagged,
        };
      })
      .sort((a, b) => Number(b.milestoneEligible) - Number(a.milestoneEligible) || b.verifiedPct - a.verifiedPct);
  }, [projectSummaries]);

  const milestoneReadinessTotalPages = Math.max(1, Math.ceil(milestoneReadiness.length / milestonePerPage));
  const milestoneReadinessSafePage = Math.min(Math.max(1, milestonePage), milestoneReadinessTotalPages);
  const paginatedMilestoneReadiness = useMemo(() => {
    const start = (milestoneReadinessSafePage - 1) * milestonePerPage;
    return milestoneReadiness.slice(start, start + milestonePerPage);
  }, [milestoneReadiness, milestoneReadinessSafePage]);

  const inclusion = useMemo(() => {
    const totalVerified = projectSummaries.reduce((sum, item) => sum + item.gender_kpi.total_verified, 0);
    const femaleCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.female_headed.count || 0), 0);
    const vulnerableCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.vulnerable.count || 0), 0);
    const lowIncomeCount = projectSummaries.reduce((sum, item) => sum + (item.gender_kpi.low_income.count || 0), 0);

    const femalePct = totalVerified ? (femaleCount / totalVerified) * 100 : 0;
    const vulnerablePct = totalVerified ? (vulnerableCount / totalVerified) * 100 : 0;
    const lowIncomePct = totalVerified ? (lowIncomeCount / totalVerified) * 100 : 0;

    return {
      totalVerified,
      femalePct,
      vulnerablePct,
      lowIncomePct,
      metCount: Number(femalePct >= 50) + Number(vulnerablePct >= 30) + Number(lowIncomePct >= 60),
    };
  }, [projectSummaries]);

  const quality = useMemo(() => {
    const verified = installationReports.filter((report) => report.status === "Verified").length;
    const flagged = installationReports.filter((report) => report.status === "Flagged").length;
    const submitted = installationReports.filter((report) => report.status === "Submitted").length;
    const resolved = verified + flagged;
    return {
      verified,
      flagged,
      submitted,
      resolved,
      passRate: resolved ? (verified / resolved) * 100 : 0,
      discrepancyRate: resolved ? (flagged / resolved) * 100 : 0,
      chartRows: [
        { name: "Verified", value: verified, fill: "#1D9E75" },
        { name: "Flagged", value: flagged, fill: "#BE123C" },
        { name: "Pending", value: submitted, fill: "#BA7517" },
      ],
    };
  }, [installationReports]);

  const energy = useMemo(() => {
    const monthly = new Map<string, { sortKey: string; month: string; actual: number; target: number }>();
    projectSummaries.forEach((summary) => {
      summary.energy_kpi.monthly_data.forEach((row) => {
        const current = monthly.get(row.month) || {
          sortKey: row.month,
          month: formatMonthKey(row.month),
          actual: 0,
          target: 0,
        };
        current.actual += Number(row.total_kwh || 0);
        current.target += Number(row.target_kwh || 0);
        monthly.set(row.month, current);
      });
    });

    const rows = Array.from(monthly.values())
      .sort((a, b) => compareMonthKeys(a.sortKey, b.sortKey))
      .slice(-6)
      .map((row) => ({
        month: row.month,
        actual: Number(row.actual.toFixed(1)),
        target: Number(row.target.toFixed(1)),
      }));

    const currentActual = projectSummaries.reduce((sum, summary) => sum + Number(summary.energy_kpi.current_month_kwh || 0), 0);
    const currentTarget = projectSummaries.reduce((sum, summary) => sum + Number(summary.energy_kpi.current_month_target || 0), 0);

    return {
      rows,
      currentActual,
      currentTarget,
      currentPct: currentTarget > 0 ? (currentActual / currentTarget) * 100 : 0,
    };
  }, [projectSummaries]);

  const latestMeterByProject = useMemo(() => {
    const latest = new Map<string, Date>();
    meterReadings.forEach((reading) => {
      const parsed = parseDate(reading.recordedAt || reading.createdAt);
      if (!parsed) return;
      const current = latest.get(reading.projectId);
      if (!current || parsed > current) latest.set(reading.projectId, parsed);
    });
    return latest;
  }, [meterReadings]);

  const actionItems = useMemo(() => {
    const now = new Date();
    return milestoneReadiness
      .map((item) => {
        const project = projectsById.get(item.projectId);
        const latestMeter = latestMeterByProject.get(item.projectId) || null;
        const staleDays = latestMeter ? daysBetween(now, latestMeter) : null;
        const needsMeterAttention = staleDays == null || staleDays >= 30;
        const reasons = [
          item.verifiedPct < 80 ? `Only ${formatPercent(item.verifiedPct, 1)} verified toward Milestone 2` : null,
          item.flagged > 0 ? `${item.flagged} flagged installation${item.flagged === 1 ? "" : "s"} need correction` : null,
          needsMeterAttention ? (staleDays == null ? "No meter data received yet" : `${staleDays} days since last meter reading`) : null,
          Number(project?.unresolvedFlagCount || 0) > 0 ? `${project?.unresolvedFlagCount} unresolved anomaly flag${project?.unresolvedFlagCount === 1 ? "" : "s"}` : null,
        ].filter(Boolean) as string[];

        return {
          ...item,
          reasons,
        };
      })
      .filter((item) => item.reasons.length > 0)
      .sort((a, b) => b.reasons.length - a.reasons.length || a.verifiedPct - b.verifiedPct)
      .slice(0, 6);
  }, [latestMeterByProject, milestoneReadiness, projectsById]);

  const verifiedAgainstThreshold = aggregatedProgress.target ? (aggregatedProgress.verified / (aggregatedProgress.target * 0.8)) * 100 : 0;

  return (
    <DashboardFrame
      title="Vendor KPI Dashboard"
      description="Production-ready self-monitoring for payment readiness, quality control, inclusion compliance, and energy delivery."
      loading={loading}
      error={error}
      refreshedAt={refreshedAt}
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label="Milestone 2 Readiness"
          value={formatPercent(Math.min(100, verifiedAgainstThreshold), 1)}
          hint={`${aggregatedProgress.verified} verified against the 80% threshold needed for payment unlock`}
          icon={Target}
          tone={verifiedAgainstThreshold >= 100 ? "emerald" : "amber"}
          status={verifiedAgainstThreshold >= 100 ? "Milestone threshold reached" : "More verified installations needed"}
        />
        <KpiCard
          label="Quality Pass Rate"
          value={formatPercent(quality.passRate, 1)}
          hint={`${quality.verified} verified vs ${quality.flagged} flagged resolved installations`}
          icon={ShieldCheck}
          tone={quality.passRate >= 90 ? "emerald" : quality.passRate >= 75 ? "amber" : "rose"}
          status={quality.passRate >= 90 ? "Field quality is strong" : "Installation quality needs attention"}
        />
        <KpiCard
          label="Inclusion Compliance"
          value={`${inclusion.metCount}/3`}
          hint={`${formatPercent(inclusion.femalePct, 1)} gender, ${formatPercent(inclusion.vulnerablePct, 1)} vulnerable, ${formatPercent(inclusion.lowIncomePct, 1)} low-income`}
          icon={Users}
          tone={inclusion.metCount === 3 ? "emerald" : "amber"}
          status={inclusion.metCount === 3 ? "All verified inclusion targets met" : "Outreach mix should be rebalanced"}
        />
        <KpiCard
          label="Current Energy Attainment"
          value={formatPercent(energy.currentPct, 1)}
          hint={`${formatNumber(energy.currentActual, 1)} kWh generated against ${formatNumber(energy.currentTarget, 1)} kWh target this month`}
          icon={Zap}
          tone={energy.currentPct >= 95 ? "emerald" : "amber"}
          status={energy.currentPct >= 95 ? "Generation is on target" : "Metered output is below target"}
        />
        <KpiCard
          label="Immediate Actions"
          value={String(actionItems.length)}
          hint={`${aggregatedProgress.pending} pending and ${aggregatedProgress.flagged} flagged installation records still affect readiness`}
          icon={AlertTriangle}
          tone={actionItems.length > 0 ? "rose" : "slate"}
          status={actionItems.length > 0 ? "Operational follow-up required" : "No active readiness blockers"}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionCard
          title="Milestone Progress"
          description="Project-by-project payment readiness against Milestone 2 conditions and the 80% verification threshold."
        >
          <div className="space-y-4">
            {paginatedMilestoneReadiness.map((item) => (
              <div key={item.projectId} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="font-semibold text-slate-900">{item.projectReference}</p>
                    <p className="text-sm text-slate-500">{item.verified} verified of {item.target} target installations</p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(item.milestoneEligible, !item.milestoneEligible)}`}>
                    {item.milestoneEligible ? "Milestone 2 unlocked" : `${formatPercent(item.readinessPct, 0)} conditions met`}
                  </span>
                </div>
                <div className="mt-4 h-3 overflow-hidden rounded-full bg-white">
                  <div className={`h-full rounded-full ${item.verifiedPct >= 80 ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${Math.max(0, Math.min(100, item.verifiedPct / 0.8))}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                  <span>{formatPercent(item.verifiedPct, 1)} of total target</span>
                  <span>{item.pending} pending</span>
                  <span>{item.flagged} flagged</span>
                </div>
                {!item.milestoneEligible && item.blockers.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.blockers.map((blocker) => (
                      <span key={blocker} className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
                        {blocker}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {milestoneReadiness.length === 0 && <EmptyState message="Milestone readiness will appear once your project KPI summaries are available." />}
          </div>
          {milestoneReadiness.length > milestonePerPage && (
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-500">
                Showing <span className="font-semibold text-slate-700">{((milestoneReadinessSafePage - 1) * milestonePerPage) + 1}</span>
                {"–"}
                <span className="font-semibold text-slate-700">{Math.min(milestoneReadinessSafePage * milestonePerPage, milestoneReadiness.length)}</span>
                {" of "}
                <span className="font-semibold text-slate-700">{milestoneReadiness.length}</span>
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setMilestonePage((p) => Math.max(1, p - 1))}
                  disabled={milestoneReadinessSafePage <= 1}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <span className="text-xs font-bold text-slate-600">
                  Page {milestoneReadinessSafePage} of {milestoneReadinessTotalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setMilestonePage((p) => Math.min(milestoneReadinessTotalPages, p + 1))}
                  disabled={milestoneReadinessSafePage >= milestoneReadinessTotalPages}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:bg-white"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </SectionCard>

        <div className="space-y-6">
          <SectionCard
            title="Discrepancy Rate"
            description="Operational quality split between verified, flagged, and still-pending installation records."
          >
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={quality.chartRows}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip formatter={(value: number) => `${value} installations`} />
                  <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                    {quality.chartRows.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-[11px] uppercase tracking-wide text-slate-500">Discrepancy Rate</p>
                <p className="mt-1 text-lg font-semibold text-rose-700">{formatPercent(quality.discrepancyRate, 1)}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-[11px] uppercase tracking-wide text-slate-500">Pending Resolution</p>
                <p className="mt-1 text-lg font-semibold text-amber-700">{quality.submitted}</p>
              </div>
            </div>
            </SectionCard>

            <SectionCard
            title="Inclusion Tracker"
            description="Verified-beneficiary mix so your next deployment cycle can target the right households."
          >
            <div className="space-y-5">
              <ProgressMetric
                label="Gender"
                value={formatPercent(inclusion.femalePct, 1)}
                targetLabel="Target: at least 50% female-headed households"
                percent={inclusion.femalePct}
                color="bg-emerald-500"
                ok={inclusion.femalePct >= 50}
              />
              <ProgressMetric
                label="Vulnerable Groups"
                value={formatPercent(inclusion.vulnerablePct, 1)}
                targetLabel="Target: at least 30% vulnerable households"
                percent={inclusion.vulnerablePct}
                color="bg-amber-500"
                ok={inclusion.vulnerablePct >= 30}
              />
              <ProgressMetric
                label="Low-Income"
                value={formatPercent(inclusion.lowIncomePct, 1)}
                targetLabel="Target: at least 60% low-income households"
                percent={inclusion.lowIncomePct}
                color="bg-blue-600"
                ok={inclusion.lowIncomePct >= 60}
              />
            </div>
          </SectionCard>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard
          title="Immediate Actions Before Next Claim"
          description="Projects with blockers that will delay payment eligibility if they are not addressed soon."
        >
          <div className="space-y-3">
            {actionItems.map((item) => (
              <div key={item.projectId} className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="font-semibold text-rose-900">{item.projectReference}</p>
                    <p className="text-sm text-rose-700">{formatPercent(item.verifiedPct, 1)} verified toward milestone unlock</p>
                  </div>
                  <span className="rounded-full border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-700">
                    {item.reasons.length} blocker{item.reasons.length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.reasons.map((reason) => (
                    <span key={reason} className="rounded-full border border-rose-200 bg-white px-2.5 py-1 text-xs text-rose-800">
                      {reason}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {actionItems.length === 0 && <EmptyState message="No immediate payment-readiness blockers are active right now." />}
          </div>
        </SectionCard>

        <SectionCard
          title="Energy Generation"
          description="Measured monthly generation compared with the contracted meter target."
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={energy.rows}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="month" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip formatter={(value: number) => `${formatNumber(value, 1)} kWh`} />
                <Legend />
                <Bar dataKey="actual" name="Actual kWh" fill="#1D9E75" radius={[8, 8, 0, 0]} />
                <Line type="monotone" dataKey="target" name="Target kWh" stroke="#1d4ed8" strokeWidth={2.5} dot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {energy.rows.length === 0 && <EmptyState message="Monthly generation data will appear once smart meter readings are flowing." />}
        </SectionCard>
      </div>
    </DashboardFrame>
  );
}

export function FieldOperationalKpiPanel({
  tasks,
  reports,
  projects,
  assignedDistrict,
  assignedDistricts,
}: {
  tasks: VerificationTask[];
  reports: InstallationReport[];
  projects: Project[];
  assignedDistrict: string;
  assignedDistricts?: string[];
}) {
  const [anomalyFlags, setAnomalyFlags] = useState<AnomalyFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchAnomalyFlags()
      .then((rows) => {
        if (active) setAnomalyFlags(rows);
      })
      .catch((err: any) => {
        if (active) setError(String(err?.message || "Unable to load data quality metrics."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const reportsById = useMemo(() => new Map(reports.map((report) => [report.id, report])), [reports]);
  const projectsById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);

  const completedTasks = tasks.filter((task) => isCompletedTask(task.status));
  const pendingTasks = tasks.filter((task) => !isCompletedTask(task.status));
  const verifiedCount = tasks.filter((task) => task.status === "Verified").length;
  const flaggedCount = tasks.filter((task) => task.status === "Flagged" || task.status === "Partial").length;
  const completionRate = tasks.length ? (completedTasks.length / tasks.length) * 100 : 0;
  const firstPassRate = completedTasks.length ? (verifiedCount / completedTasks.length) * 100 : 0;

  const averageVerificationHours = useMemo(() => {
    const durations = completedTasks
      .map((task) => {
        const report = reportsById.get(task.report);
        const submittedAt = parseDate(report?.submittedAt || task.createdAt);
        const completedAt = parseDate(task.updatedAt || task.createdAt);
        if (!submittedAt || !completedAt) return null;
        return hoursBetween(submittedAt, completedAt);
      })
      .filter((value): value is number => value != null && value >= 0);

    if (!durations.length) return 0;
    return durations.reduce((sum, value) => sum + value, 0) / durations.length;
  }, [completedTasks, reportsById]);

  const overduePending = useMemo(() => {
    const now = new Date();
    return pendingTasks.filter((task) => {
      const report = reportsById.get(task.report);
      const submittedAt = parseDate(report?.submittedAt || task.createdAt);
      if (!submittedAt) return false;
      return hoursBetween(submittedAt, now) > 72;
    });
  }, [pendingTasks, reportsById]);

  const gpsMismatchCount = useMemo(
    () => tasks.filter((task) => task.distanceMeters != null && task.distanceMeters > 50).length,
    [tasks]
  );

  const oldestPending = useMemo(() => {
    const now = new Date();
    return pendingTasks
      .map((task) => {
        const report = reportsById.get(task.report);
        const project = report ? projectsById.get(report.projectId) : undefined;
        const submittedAt = parseDate(report?.submittedAt || task.createdAt);
        const ageHours = submittedAt ? hoursBetween(submittedAt, now) : 0;
        return {
          id: task.id,
          projectReference: project?.projectReference || project?.projectTitle || `Project ${report?.projectId || task.report}`,
          beneficiary: report?.beneficiaryName || report?.beneficiaryId || "Beneficiary not named",
          district: project?.district || project?.region || assignedDistrict,
          ageHours,
        };
      })
      .sort((a, b) => b.ageHours - a.ageHours)
      .slice(0, 6);
  }, [assignedDistrict, pendingTasks, projectsById, reportsById]);

  const reasonRows = useMemo(() => {
    const projectIds = new Set(projects.map((project) => project.id));
    const counts = new Map<string, number>();

    anomalyFlags
      .filter((flag) => projectIds.size === 0 || projectIds.has(flag.project))
      .forEach((flag) => {
        const key = titleCase(flag.flagType || "unknown");
        counts.set(key, (counts.get(key) || 0) + 1);
      });

    return Array.from(counts.entries())
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [anomalyFlags, projects]);

  const queueByDistrict = useMemo(() => {
    const counts = new Map<string, { district: string; total: number; completed: number; pending: number }>();
    tasks.forEach((task) => {
      const report = reportsById.get(task.report);
      const project = report ? projectsById.get(report.projectId) : undefined;
      const district = project?.district || project?.region || assignedDistrict;
      const entry = counts.get(district) || { district, total: 0, completed: 0, pending: 0 };
      entry.total += 1;
      if (isCompletedTask(task.status)) entry.completed += 1;
      else entry.pending += 1;
      counts.set(district, entry);
    });

    return Array.from(counts.values())
      .map((row) => ({
        ...row,
        coveragePct: row.total ? (row.completed / row.total) * 100 : 0,
      }))
      .sort((a, b) => b.coveragePct - a.coveragePct);
  }, [assignedDistrict, projectsById, reportsById, tasks]);

  return (
    <DashboardFrame
      title="Field Officer KPI Dashboard"
      description={`Operational verification performance, queue health, and data quality signals for ${assignedDistrict}.`}
      loading={false}
      error={null}
      refreshedAt={new Date().toISOString()}
    >
      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label="Verification Speed"
          value={`${formatNumber(averageVerificationHours, 1)} hrs`}
          hint="Average turnaround from vendor submission to completed field decision"
          icon={Clock3}
          tone={averageVerificationHours <= 72 ? "emerald" : "amber"}
          status={averageVerificationHours <= 72 ? "Within 72-hour SLA" : "SLA recovery required"}
        />
        <KpiCard
          label="District Coverage"
          value={formatPercent(completionRate, 1)}
          hint={`${completedTasks.length} of ${tasks.length} assigned tasks already converted from yellow pins`}
          icon={MapPinned}
          tone={completionRate >= 80 ? "emerald" : "amber"}
          status={completionRate >= 80 ? "Strong coverage" : "Coverage still building"}
        />
        <KpiCard
          label="Overdue Visits"
          value={String(overduePending.length)}
          hint="Pending verification tasks older than 72 hours"
          icon={AlertTriangle}
          tone={overduePending.length === 0 ? "emerald" : overduePending.length <= 3 ? "amber" : "rose"}
          status={overduePending.length === 0 ? "Queue is within SLA" : "Old tasks need attention"}
        />
        <KpiCard
          label="GPS Mismatch Alerts"
          value={String(gpsMismatchCount)}
          hint="Tasks with more than 50 meters between vendor and verifier coordinates"
          icon={Gauge}
          tone={gpsMismatchCount === 0 ? "emerald" : gpsMismatchCount <= 3 ? "amber" : "rose"}
          status={gpsMismatchCount === 0 ? "Location integrity is clean" : "Coordinate review recommended"}
        />
        <KpiCard
          label="First-Pass Verification"
          value={formatPercent(firstPassRate, 1)}
          hint={`${verifiedCount} verified vs ${flaggedCount} flagged or partial outcomes`}
          icon={ShieldCheck}
          tone={firstPassRate >= 85 ? "emerald" : firstPassRate >= 70 ? "amber" : "rose"}
          status={firstPassRate >= 85 ? "Most sites pass on first visit" : "Rework rate is high"}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard
          title="District Coverage"
          description="How much of the current queue has been turned from yellow pins into final green or red outcomes."
        >
          <div className="space-y-4">
            {queueByDistrict.map((row) => (
              <div key={row.district} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900">{row.district}</p>
                    <p className="text-sm text-slate-500">{row.completed} completed, {row.pending} still pending</p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(row.coveragePct >= 80, row.coveragePct >= 60)}`}>
                    {formatPercent(row.coveragePct, 1)}
                  </span>
                </div>
                <div className="mt-3 h-3 overflow-hidden rounded-full bg-white">
                  <div className={`h-full rounded-full ${row.coveragePct >= 80 ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${row.coveragePct}%` }} />
                </div>
              </div>
            ))}
            {queueByDistrict.length === 0 && <EmptyState message="District coverage will appear once field assignments are synced." />}
          </div>
        </SectionCard>

        <SectionCard
          title="Data Quality"
          description="The most common rejection and anomaly reasons showing up in your current assignment scope."
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={reasonRows} layout="vertical" margin={{ left: 12, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                <XAxis type="number" axisLine={false} tickLine={false} allowDecimals={false} />
                <YAxis dataKey="reason" type="category" axisLine={false} tickLine={false} width={130} />
                <Tooltip formatter={(value: number) => `${value} cases`} />
                <Legend />
                <Bar dataKey="count" name="Cases" fill="#BA7517" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {reasonRows.length === 0 && <EmptyState message="No anomaly or rejection reason data is available yet for this field scope." />}
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard
          title="Oldest Pending Visits"
          description="The assignments most likely to become SLA breaches if they stay in the queue."
        >
          <div className="space-y-3">
            {oldestPending.map((item) => (
              <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="font-semibold text-slate-900">{item.projectReference}</p>
                    <p className="text-sm text-slate-500">{item.beneficiary} • {item.district}</p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(item.ageHours <= 72, item.ageHours <= 96)}`}>
                    {item.ageHours >= 24 ? `${formatNumber(item.ageHours / 24, 1)} days old` : `${formatNumber(item.ageHours, 1)} hours old`}
                  </span>
                </div>
              </div>
            ))}
            {oldestPending.length === 0 && <EmptyState message="There are no pending visits waiting in the queue right now." />}
          </div>
        </SectionCard>

        <SectionCard
          title="Queue Outcome Mix"
          description="A quick operational split across verified, flagged, and still-pending field decisions."
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  { name: "Verified", value: verifiedCount, fill: "#1D9E75" },
                  { name: "Flagged / Partial", value: flaggedCount, fill: "#BE123C" },
                  { name: "Pending", value: pendingTasks.length, fill: "#BA7517" },
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip formatter={(value: number) => `${value} tasks`} />
                <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                  {[
                    { name: "Verified", fill: "#1D9E75" },
                    { name: "Flagged / Partial", fill: "#BE123C" },
                    { name: "Pending", fill: "#BA7517" },
                  ].map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Assigned Projects</p>
              <p className="mt-1 text-lg font-semibold text-slate-900">{new Set(tasks.map((task) => reportsById.get(task.report)?.projectId).filter(Boolean)).size}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Verified</p>
              <p className="mt-1 text-lg font-semibold text-emerald-700">{verifiedCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Flagged</p>
              <p className="mt-1 text-lg font-semibold text-rose-700">{flaggedCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Pending</p>
              <p className="mt-1 text-lg font-semibold text-amber-700">{pendingTasks.length}</p>
            </div>
          </div>
        </SectionCard>
      </div>
    </DashboardFrame>
  );
}
