import React, { useEffect, useState } from "react";

import { fetchPortfolioKpiSummary } from "../api";
import { PortfolioKpiSummary as PortfolioKpiSummaryType } from "../types";

export default function PortfolioKpiSummary({
  onSelectProject,
}: {
  onSelectProject?: (projectId: string) => void;
}) {
  const [summary, setSummary] = useState<PortfolioKpiSummaryType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchPortfolioKpiSummary()
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((err: any) => {
        if (active) setError(String(err?.message || "Unable to load portfolio KPIs."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">Loading portfolio KPI summary...</div>;
  }
  if (error || !summary) {
    return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">{error || "Portfolio KPI summary unavailable."}</div>;
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total Projects</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.total_projects}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Overall Progress</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">{summary.overall_progress_pct}%</p>
        </div>
        <div className={`rounded-2xl border p-5 shadow-sm ${summary.overall_female_met ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-rose-200 bg-rose-50 text-rose-700"}`}>
          <p className="text-xs font-semibold uppercase tracking-wide">Overall Female %</p>
          <p className="mt-2 text-3xl font-semibold">{summary.overall_female_pct}%</p>
        </div>
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-800 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide">Projects At Risk</p>
          <p className="mt-2 text-3xl font-semibold">{summary.projects_at_risk}</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">Project</th>
                <th className="py-2 pr-4">Vendor</th>
                <th className="py-2 pr-4">Technology</th>
                <th className="py-2 pr-4">Progress</th>
                <th className="py-2 pr-4">Female %</th>
                <th className="py-2 pr-4">Uptime</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {summary.projects.map((project) => (
                <tr key={project.project_id} className="border-b border-slate-100">
                  <td className="py-3 pr-4">
                    <button
                      onClick={() => onSelectProject?.(project.project_id)}
                      className="font-medium text-emerald-700 hover:underline"
                    >
                      {project.project_reference}
                    </button>
                  </td>
                  <td className="py-3 pr-4 text-slate-600">{project.vendor_name}</td>
                  <td className="py-3 pr-4 text-slate-600">{project.technology}</td>
                  <td className="py-3 pr-4 text-slate-600">{project.progress_pct}%</td>
                  <td className="py-3 pr-4 text-slate-600">{project.female_pct}%</td>
                  <td className="py-3 pr-4 text-slate-600">{project.uptime_pct}%</td>
                  <td className={`py-3 font-medium ${
                    project.status === "On Track" ? "text-emerald-700"
                      : project.status === "At Risk" ? "text-amber-700"
                        : project.status === "Completed" ? "text-slate-500"
                          : "text-rose-700"
                  }`}>
                    {project.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
