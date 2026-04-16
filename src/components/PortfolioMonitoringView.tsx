import React, { useEffect, useMemo, useState } from "react";

import { fetchPortfolioKpiSummary, fetchProjects } from "../api";
import { PortfolioKpiSummary, Project } from "../types";
import GisInstallationsMap from "./GisInstallationsMap";
import KpiDashboard from "./KpiDashboard";

function formatNumber(value: number | undefined, digits = 1) {
  if (value == null || Number.isNaN(value)) return "0";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export default function PortfolioMonitoringView({
  title,
  description,
  emptyProjectsMessage,
}: {
  title: string;
  description: string;
  emptyProjectsMessage?: string;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [summary, setSummary] = useState<PortfolioKpiSummary | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([fetchProjects(), fetchPortfolioKpiSummary()])
      .then(([projectRows, portfolio]) => {
        if (!active) return;
        setProjects(projectRows);
        setSummary(portfolio);
        setSelectedProjectId((current) => {
          if (current && projectRows.some((item) => item.id === current)) return current;
          return projectRows[0]?.id || "";
        });
      })
      .catch((err: any) => {
        if (!active) return;
        setError(String(err?.message || "Unable to load the monitoring dashboard."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading dashboard...</div>;
  }

  if (error || !summary) {
    return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">{error || "Unable to load dashboard data."}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="text-slate-500">{description}</p>
        </div>
        {summary.scope_label && (
          <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
            {summary.scope_label}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Projects</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.total_projects}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Overall Progress</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.overall_progress_pct}%</p>
        </div>
        <div className={`rounded-2xl border p-5 shadow-sm ${summary.overall_female_met ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}>
          <p className="text-xs font-semibold uppercase tracking-wide">Female Coverage</p>
          <p className="mt-2 text-3xl font-semibold">{summary.overall_female_pct}%</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Average Uptime</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.overall_uptime_pct}%</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Pending Claims</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.pending_claims ?? 0}</p>
          <p className="mt-2 text-xs text-slate-500">Paid: M {formatNumber(summary.total_paid_amount ?? 0, 2)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-slate-900">Portfolio GIS View</h3>
            <p className="text-sm text-slate-500">Verified installations appear green, pending yellow, and flagged red.</p>
          </div>
          <GisInstallationsMap showFilters height="500px" />
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-slate-900">Project Performance Table</h3>
            <p className="text-sm text-slate-500">Select a project to open its live KPI dashboard and project-only map.</p>
          </div>
          {summary.projects.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
              {emptyProjectsMessage || "No scoped projects are available for this user."}
            </div>
          ) : (
            <div className="max-h-[500px] overflow-auto">
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-slate-200 text-left text-slate-500">
                    <th className="py-2 pr-4">Project</th>
                    <th className="py-2 pr-4">Vendor</th>
                    <th className="py-2 pr-4">District</th>
                    <th className="py-2 pr-4">Progress</th>
                    <th className="py-2 pr-4">Female %</th>
                    <th className="py-2 pr-4">Uptime</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.projects.map((project) => {
                    const selected = selectedProjectId === project.project_id;
                    return (
                      <tr
                        key={project.project_id}
                        className={`cursor-pointer border-b border-slate-100 ${selected ? "bg-emerald-50" : "hover:bg-slate-50"}`}
                        onClick={() => setSelectedProjectId(project.project_id)}
                      >
                        <td className="py-3 pr-4 font-medium text-slate-900">{project.project_reference}</td>
                        <td className="py-3 pr-4 text-slate-600">{project.vendor_name}</td>
                        <td className="py-3 pr-4 text-slate-600">{project.district || "N/A"}</td>
                        <td className="py-3 pr-4 text-slate-600">{project.progress_pct}%</td>
                        <td className="py-3 pr-4 text-slate-600">{project.female_pct}%</td>
                        <td className="py-3 pr-4 text-slate-600">{project.uptime_pct}%</td>
                        <td className={`py-3 font-medium ${
                          project.status === "On Track" ? "text-emerald-700" :
                          project.status === "At Risk" ? "text-rose-700" :
                          "text-slate-600"
                        }`}>
                          {project.status}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selectedProject && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">
              {selectedProject.projectReference || `PRJ-${selectedProject.id}`} - {selectedProject.projectTitle || selectedProject.tenderName || "Project"}
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {selectedProject.vendorName} • {selectedProject.techType || "N/A"} • {selectedProject.district || selectedProject.region || "N/A"}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-slate-900">Project GIS View</h3>
              <p className="text-sm text-slate-500">Project-only installation map with live verified, pending, and flagged markers.</p>
            </div>
            <GisInstallationsMap projectId={selectedProject.id} showFilters height="500px" />
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <KpiDashboard projectId={selectedProject.id} />
          </div>
        </div>
      )}
    </div>
  );
}
