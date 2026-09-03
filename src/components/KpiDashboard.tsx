import React, { useEffect, useMemo, useRef, useState } from "react";

import { downloadProjectKpiPdf, fetchProjectKpiSummary } from "../api";
import { ProjectKpiSummary } from "../types";

declare global {
  interface Window {
    Chart?: any;
  }
}

const CHART_JS_ID = "chartjs-cdn-script";

function ensureChartJs(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window !== "undefined" && window.Chart) {
      resolve();
      return;
    }
    const existing = document.getElementById(CHART_JS_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Failed to load Chart.js.")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.id = CHART_JS_ID;
    script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Chart.js."));
    document.head.appendChild(script);
  });
}

function formatMonthLabel(value: string): string {
  if (!value) return "";
  const parsed = new Date(`${value}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function statusTone(met: boolean) {
  return met ? "text-emerald-700 bg-emerald-50 border-emerald-200" : "text-rose-700 bg-rose-50 border-rose-200";
}

function milestoneStatusTone(status?: string) {
  if (status === "PAID") return "bg-emerald-100 text-emerald-700";
  if (status === "CLAIMABLE") return "bg-sky-100 text-sky-700";
  if (status === "PENDING") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

function formatMilestoneConditionLabel(conditionKey: string) {
  const labels: Record<string, string> = {
    contract_approved: "Contract approved",
    setup_complete: "Project setup completed",
    installations_80_pct: "At least 80% of target installations verified",
    female_pct_50: "Female-headed households at or above 50%",
    no_blocking_anomaly_flags: "No unresolved blocking anomaly flags",
    meter_data_present: "Meter data received within the last 30 days",
    installations_100_pct: "100% of target installations verified",
    vulnerable_pct_30: "Vulnerable households at or above 30%",
    low_income_pct_60: "Low-income households at or above 60%",
    all_anomaly_flags_resolved: "All anomaly flags resolved",
    milestone_2_paid: "Milestone 2 fully paid",
  };
  return labels[conditionKey] || conditionKey.replace(/_/g, " ");
}

function formatMilestoneStatusLabel(status?: string) {
  if (!status) return "Pending";
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

function metricStatusLabel(ok: boolean, fallback?: "track") {
  if (ok) return fallback === "track" ? "On track" : "Met";
  return fallback === "track" ? "Behind target" : "Below target";
}

function displayMetricValue(value: number, hasData: boolean, suffix = "") {
  if (!hasData) return "—";
  return `${value}${suffix}`;
}

export default function KpiDashboard({ projectId, projectKpi }: { projectId?: string; projectKpi?: ProjectKpiSummary | null }) {
  const [chartReady, setChartReady] = useState(false);
  const [summary, setSummary] = useState<ProjectKpiSummary | null>(projectKpi || null);
  const [loading, setLoading] = useState(!projectKpi);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const doughnutRef = useRef<HTMLCanvasElement | null>(null);
  const progressRef = useRef<HTMLCanvasElement | null>(null);
  const energyRef = useRef<HTMLCanvasElement | null>(null);
  const uptimeRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstancesRef = useRef<any[]>([]);

  useEffect(() => {
    let active = true;
    ensureChartJs()
      .then(() => {
        if (active) setChartReady(true);
      })
      .catch((err) => {
        if (active) setError(String(err?.message || "Could not load chart assets."));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (projectKpi) {
      setSummary(projectKpi);
      setLoading(false);
      return;
    }
    if (!projectId) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    fetchProjectKpiSummary(projectId)
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((err: any) => {
        if (active) setError(String(err?.message || "Unable to load KPI dashboard."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, projectKpi]);

  const kpiRows = useMemo(() => {
    if (!summary) return [];
    const hasVerifiedInstallations = summary.gender_kpi.total_verified > 0;
    const hasUptimeData = summary.uptime_kpi.total_devices_monitored > 0;
    const hasEnergyData = summary.energy_kpi.monthly_data.length > 0;
    return [
      {
        label: "Female-headed HH",
        target: `>=${summary.gender_kpi.female_headed.target}%`,
        current: hasVerifiedInstallations ? `${summary.gender_kpi.female_headed.percentage}%` : "No data",
        ok: summary.gender_kpi.female_headed.met,
        status: hasVerifiedInstallations ? metricStatusLabel(summary.gender_kpi.female_headed.met) : "No data",
      },
      {
        label: "Vulnerable groups",
        target: `>=${summary.gender_kpi.vulnerable.target}%`,
        current: hasVerifiedInstallations ? `${summary.gender_kpi.vulnerable.percentage}%` : "No data",
        ok: summary.gender_kpi.vulnerable.met,
        status: hasVerifiedInstallations ? metricStatusLabel(summary.gender_kpi.vulnerable.met) : "No data",
      },
      {
        label: "Low-income HH",
        target: `>=${summary.gender_kpi.low_income.target}%`,
        current: hasVerifiedInstallations ? `${summary.gender_kpi.low_income.percentage}%` : "No data",
        ok: summary.gender_kpi.low_income.met,
        status: hasVerifiedInstallations ? metricStatusLabel(summary.gender_kpi.low_income.met) : "No data",
      },
      {
        label: "System uptime",
        target: `>=${summary.uptime_kpi.target_uptime_pct}%`,
        current: hasUptimeData ? `${summary.uptime_kpi.average_uptime_pct}%` : "No data",
        ok: summary.uptime_kpi.met,
        status: hasUptimeData ? metricStatusLabel(summary.uptime_kpi.met) : "No data",
      },
      {
        label: "Installation progress",
        target: String(summary.installation_progress.target),
        current: String(summary.installation_progress.verified),
        ok: summary.installation_progress.on_track,
        status: metricStatusLabel(summary.installation_progress.on_track, "track"),
      },
      {
        label: "Energy output",
        target: `${summary.energy_kpi.current_month_target.toLocaleString()} kWh`,
        current: hasEnergyData ? `${summary.energy_kpi.current_month_kwh.toLocaleString()} kWh` : "No data",
        ok: summary.energy_kpi.current_month_pct >= 95,
        status: hasEnergyData ? metricStatusLabel(summary.energy_kpi.current_month_pct >= 95, "track") : "No data",
      },
    ];
  }, [summary]);

  useEffect(() => {
    if (!chartReady || !summary) return;
    chartInstancesRef.current.forEach((chart) => chart?.destroy?.());
    chartInstancesRef.current = [];
    const Chart = window.Chart;
    if (!Chart) return;

    const doughnut = doughnutRef.current?.getContext("2d");
    if (doughnut) {
      const centerTextPlugin = {
        id: "centerText",
        afterDraw(chart: any) {
          const meta = chart.getDatasetMeta(0);
          if (!meta?.data?.[0]) return;
          const x = meta.data[0].x;
          const y = meta.data[0].y;
          const ctx = chart.ctx;
          ctx.save();
          ctx.textAlign = "center";
          ctx.fillStyle = "#0f172a";
          ctx.font = "600 15px Arial";
          ctx.fillText(`Total: ${summary.gender_kpi.total_verified}`, x, y);
          ctx.restore();
        },
      };
      chartInstancesRef.current.push(
        new Chart(doughnut, {
          type: "doughnut",
          data: {
            labels: ["Female-headed", "Vulnerable", "Low-income", "Standard"],
            datasets: [
              {
                data: [
                  summary.gender_kpi.female_headed.count || 0,
                  summary.gender_kpi.vulnerable.count || 0,
                  summary.gender_kpi.low_income.count || 0,
                  summary.gender_kpi.standard.count || 0,
                ],
                backgroundColor: ["#1D9E75", "#BA7517", "#185FA5", "#5F5E5A"],
                borderWidth: 0,
              },
            ],
          },
          options: {
            maintainAspectRatio: false,
            plugins: {
              legend: { position: "bottom" },
            },
          },
          plugins: [centerTextPlugin],
        })
      );
    }

    const progress = progressRef.current?.getContext("2d");
    if (progress) {
      chartInstancesRef.current.push(
        new Chart(progress, {
          type: "line",
          data: {
            labels: summary.installation_trend.weeks.map((row) =>
              new Date(`${row.week_start}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })
            ),
            datasets: [
              {
                label: "Cumulative Verified",
                data: summary.installation_trend.weeks.map((row) => row.cumulative_verified),
                borderColor: "#1D9E75",
                backgroundColor: "rgba(29,158,117,0.15)",
                tension: 0.25,
              },
              {
                label: "Target Trajectory",
                data: summary.installation_trend.weeks.map((row) => row.target_at_this_week),
                borderColor: "#64748b",
                borderDash: [6, 4],
                tension: 0,
              },
            ],
          },
          options: {
            maintainAspectRatio: false,
            plugins: {
              tooltip: {
                callbacks: {
                  label(context: any) {
                    const row = summary.installation_trend.weeks[context.dataIndex];
                    if (context.datasetIndex === 0) {
                      return `Week of ${row.week_start}: ${row.cumulative_verified} verified (target: ${row.target_at_this_week})`;
                    }
                    return `Target: ${row.target_at_this_week}`;
                  },
                },
              },
            },
          },
        })
      );
    }

    const energy = energyRef.current?.getContext("2d");
    if (energy) {
      chartInstancesRef.current.push(
        new Chart(energy, {
          data: {
            labels: summary.energy_kpi.monthly_data.map((row) => formatMonthLabel(row.month)),
            datasets: [
              {
                type: "bar",
                label: "Actual kWh",
                data: summary.energy_kpi.monthly_data.map((row) => row.total_kwh),
                backgroundColor: summary.energy_kpi.monthly_data.map((row) =>
                  row.achievement_pct < 80 ? "#b91c1c" : "#1D9E75"
                ),
              },
              {
                type: "line",
                label: "Target kWh",
                data: summary.energy_kpi.monthly_data.map((row) => row.target_kwh),
                borderColor: "#64748b",
                borderDash: [6, 4],
              },
            ],
          },
          options: {
            maintainAspectRatio: false,
            plugins: {
              tooltip: {
                callbacks: {
                  label(context: any) {
                    const row = summary.energy_kpi.monthly_data[context.dataIndex];
                    if (context.dataset.type === "bar") {
                      return `${formatMonthLabel(row.month)}: ${row.total_kwh.toLocaleString()} kWh (${row.achievement_pct}% of target)`;
                    }
                    return `Target: ${row.target_kwh.toLocaleString()} kWh`;
                  },
                },
              },
            },
          },
        })
      );
    }

    const uptime = uptimeRef.current?.getContext("2d");
    if (uptime) {
      const labels = ["95-100%", "90-94%", "80-89%", "Below 80%", "Offline"];
      chartInstancesRef.current.push(
        new Chart(uptime, {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: "Devices",
                data: labels.map((label) => summary.uptime_kpi.distribution[label] || 0),
                backgroundColor: ["#1D9E75", "#BA7517", "#c97316", "#b91c1c", "#7f1d1d"],
              },
            ],
          },
          options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
          },
        })
      );
    }

    return () => {
      chartInstancesRef.current.forEach((chart) => chart?.destroy?.());
      chartInstancesRef.current = [];
    };
  }, [chartReady, summary]);

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading KPI dashboard...</div>;
  }

  if (error || !summary) {
    return <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">{error || "Unable to load KPI data."}</div>;
  }

  const warningCount = kpiRows.filter((row) => !row.ok).length;
  const progressGap = summary.installation_progress.progress_pct - summary.installation_progress.expected_progress_pct;
  const progressTone = progressGap < -10 ? "bg-rose-500" : summary.installation_progress.on_track ? "bg-emerald-500" : "bg-amber-500";
  const hasVerifiedInstallations = summary.gender_kpi.total_verified > 0;
  const hasUptimeData = summary.uptime_kpi.total_devices_monitored > 0;
  const hasEnergyData = summary.energy_kpi.monthly_data.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-lg font-semibold text-slate-900">KPI Dashboard</h4>
          <p className="text-sm text-slate-500">Verified installations, meter data, and milestone readiness for this project.</p>
        </div>
        <button
          onClick={async () => {
            setExporting(true);
            try {
              await downloadProjectKpiPdf(projectId);
            } finally {
              setExporting(false);
            }
          }}
          className="btn-secondary text-xs"
          disabled={exporting}
        >
          {exporting ? "Exporting..." : "Export KPI Report PDF"}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Installation Progress</p>
          <p className="mt-2 text-3xl font-semibold text-slate-900">
            {summary.installation_progress.verified}/{summary.installation_progress.target}
          </p>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full rounded-full ${progressTone}`} style={{ width: `${Math.min(100, summary.installation_progress.progress_pct)}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">{summary.installation_progress.progress_pct}% complete</p>
        </div>
        <div className={`rounded-2xl border p-5 shadow-sm ${statusTone(summary.gender_kpi.female_headed.met)}`}>
          <p className="text-xs font-semibold uppercase tracking-wide">Female Beneficiary %</p>
          <p className="mt-2 text-3xl font-semibold">{displayMetricValue(summary.gender_kpi.female_headed.percentage, hasVerifiedInstallations, "%")}</p>
          <p className="mt-2 text-xs">Target: {"\u2265"} {summary.gender_kpi.female_headed.target}%</p>
          <p className="mt-1 text-xs">{hasVerifiedInstallations ? `${summary.gender_kpi.female_trending_up ? "↑" : "↓"} vs last week` : "No verified installations yet"}</p>
        </div>
        <div className={`rounded-2xl border p-5 shadow-sm ${statusTone(summary.uptime_kpi.met)}`}>
          <p className="text-xs font-semibold uppercase tracking-wide">Average Uptime</p>
          <p className="mt-2 text-3xl font-semibold">{displayMetricValue(summary.uptime_kpi.average_uptime_pct, hasUptimeData, "%")}</p>
          <p className="mt-2 text-xs">Target: {"\u2265"} {summary.uptime_kpi.target_uptime_pct}%</p>
          <p className="mt-1 text-xs">{hasUptimeData ? `${summary.uptime_kpi.devices_offline} devices offline` : "No meter data yet"}</p>
        </div>
        <div className={`rounded-2xl border p-5 shadow-sm ${
          summary.energy_kpi.current_month_pct >= 95 ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : summary.energy_kpi.current_month_pct >= 80 ? "border-amber-200 bg-amber-50 text-amber-700"
              : "border-rose-200 bg-rose-50 text-rose-700"
        }`}>
          <p className="text-xs font-semibold uppercase tracking-wide">Energy Output</p>
          <p className="mt-2 text-3xl font-semibold">{hasEnergyData ? `${summary.energy_kpi.current_month_kwh.toLocaleString()} kWh` : "—"}</p>
          <p className="mt-2 text-xs">Target: {summary.energy_kpi.current_month_target.toLocaleString()} kWh</p>
          <p className="mt-1 text-xs">{hasEnergyData ? `${summary.energy_kpi.current_month_pct}% of target` : "No data yet"}</p>
        </div>
      </div>

      {!hasVerifiedInstallations && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          No installations verified yet. Submit and verify installations to see KPI data.
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {warningCount > 0 && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {warningCount} KPI{warningCount === 1 ? "" : "s"} need attention before the next milestone claim.
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">KPI</th>
                <th className="py-2 pr-4">Target</th>
                <th className="py-2 pr-4">Current</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {kpiRows.map((row) => (
                <tr key={row.label} className="border-b border-slate-100">
                  <td className="py-3 pr-4 font-medium text-slate-900">{row.label}</td>
                  <td className="py-3 pr-4 text-slate-600">{row.target}</td>
                  <td className="py-3 pr-4 text-slate-600">{row.current}</td>
                  <td className={`py-3 font-medium ${
                    row.status === "No data" ? "text-slate-500" :
                    row.ok ? "text-emerald-700" :
                    row.status.includes("Behind") ? "text-amber-700" :
                    "text-rose-700"
                  }`}>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="text-sm font-semibold text-slate-900">Household Type Breakdown</h5>
          <div className="mt-4 h-80">
            <canvas ref={doughnutRef} />
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="text-sm font-semibold text-slate-900">Installation Progress Over Time</h5>
          <div className="mt-4 h-80">
            <canvas ref={progressRef} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="text-sm font-semibold text-slate-900">Monthly Energy Output</h5>
          <div className="mt-4 h-80">
            <canvas ref={energyRef} />
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h5 className="text-sm font-semibold text-slate-900">Device Uptime Distribution (last 30 days)</h5>
          <div className="mt-4 h-80">
            <canvas ref={uptimeRef} />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h5 className="text-sm font-semibold text-slate-900">Milestone Readiness</h5>
        <div className="mt-4 space-y-4">
          {Object.entries(summary.milestone_eligibility).map(([key, value], index) => {
            const eligibility = value as { eligible: boolean; status?: string; conditions: Record<string, boolean> };
            return (
            <div key={key} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-slate-900">Milestone {index + 1}</p>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${milestoneStatusTone(eligibility.status)}`}>
                  {formatMilestoneStatusLabel(eligibility.status)}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                {Object.entries(eligibility.conditions).map(([condition, met]) => (
                  <div
                    key={condition}
                    className={`rounded-xl border px-3 py-2 text-sm ${
                      met
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    <div className="font-medium">{formatMilestoneConditionLabel(condition)}</div>
                    <div className="mt-1 text-xs uppercase tracking-wide">{met ? "Met" : "Pending"}</div>
                  </div>
                ))}
              </div>
            </div>
          )})}
        </div>
      </div>
    </div>
  );
}
