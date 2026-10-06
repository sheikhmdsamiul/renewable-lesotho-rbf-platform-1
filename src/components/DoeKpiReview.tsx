import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, ClipboardCheck, ExternalLink, Loader2, Pencil, Plus, RefreshCw, X } from "lucide-react";
import {
  createKpiReview,
  fetchKpiReviews,
  fetchProjectKpiSummary,
  fetchProjects,
  KpiReviewInput,
  updateKpiReview,
} from "../api";
import { KpiReview, KpiReviewRating, Project, ProjectKpiSummary } from "../types";
import KpiDashboard from "./KpiDashboard";

const RATINGS: { value: KpiReviewRating; label: string; desc: string; badge: string; selected: string }[] = [
  { value: "on_track", label: "On Track", desc: "KPIs meet or are close to target", badge: "bg-emerald-100 text-emerald-700", selected: "border-emerald-500 bg-emerald-50" },
  { value: "needs_attention", label: "Needs Attention", desc: "Some KPIs are slipping", badge: "bg-amber-100 text-amber-700", selected: "border-amber-500 bg-amber-50" },
  { value: "at_risk", label: "At Risk", desc: "Targets likely to be missed — RMT is notified", badge: "bg-rose-100 text-rose-700", selected: "border-rose-500 bg-rose-50" },
];

const ratingMeta = (rating: KpiReviewRating) => RATINGS.find((option) => option.value === rating) || RATINGS[0];

const currentPeriod = () => new Date().toISOString().slice(0, 7);

const formatPeriod = (period: string) => {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month) return period;
  return new Date(year, month - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
};

const errorMessage = (err: any, fallback: string) => {
  const raw = String(err?.message || "");
  try {
    const parsed = JSON.parse(raw.slice(raw.indexOf("{")));
    if (parsed?.detail) return String(parsed.detail);
    const first = Object.entries(parsed || {})[0];
    if (first) return `${first[0].replace(/_/g, " ")}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
  } catch {
    // Not a JSON error body.
  }
  return fallback;
};

const snapshotFromSummary = (summary: ProjectKpiSummary | null): Record<string, any> => {
  if (!summary) return {};
  return {
    installation_progress_pct: summary.installation_progress?.progress_pct,
    expected_progress_pct: summary.installation_progress?.expected_progress_pct,
    verified_installations: summary.installation_progress?.verified,
    female_headed_pct: summary.gender_kpi?.female_headed?.percentage,
    vulnerable_pct: summary.gender_kpi?.vulnerable?.percentage,
    average_uptime_pct: summary.uptime_kpi?.average_uptime_pct,
    energy_achievement_pct: summary.energy_kpi?.current_month_pct,
    generated_at: summary.generated_at,
  };
};

const emptyReview = (projectId: string): KpiReviewInput => ({
  projectId,
  reviewPeriod: currentPeriod(),
  rating: "on_track",
  uptimeComment: "",
  beneficiaryComment: "",
  genderInclusionComment: "",
  summary: "",
  recommendations: "",
});

function KpiReviewForm({
  initial,
  existing,
  summary,
  onCancel,
  onSaved,
}: {
  initial: KpiReviewInput;
  existing?: KpiReview;
  summary: ProjectKpiSummary | null;
  onCancel: () => void;
  onSaved: (review: KpiReview) => void;
}) {
  const [form, setForm] = useState<KpiReviewInput>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof KpiReviewInput>(key: K, value: KpiReviewInput[K]) => setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(form.reviewPeriod)) return setError("Choose the month this review covers.");
    if (form.summary.trim().length < 10) return setError("Write a short summary (at least 10 characters).");
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form, summary: form.summary.trim(), kpiSnapshot: snapshotFromSummary(summary) };
      const saved = existing ? await updateKpiReview(existing.id, payload) : await createKpiReview(payload);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, "Unable to save the review."));
    } finally {
      setSaving(false);
    }
  };

  const commentField = (key: "uptimeComment" | "beneficiaryComment" | "genderInclusionComment", label: string, placeholder: string) => (
    <label className="block">
      <span className="mb-1 block text-sm font-semibold text-slate-900">{label}</span>
      <textarea className="input-field min-h-[70px]" placeholder={placeholder} value={form[key]} onChange={(e) => set(key, e.target.value)} />
    </label>
  );

  return (
    <div className="card space-y-4 border-emerald-200 p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900">
          <ClipboardCheck size={18} className="text-emerald-600" /> {existing ? "Edit KPI Review" : "New KPI Review"}
        </h3>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X size={18} /></button>
      </div>

      <label className="block md:w-64">
        <span className="mb-1 block text-sm font-semibold text-slate-900">Review month *</span>
        <input type="month" className="input-field" value={form.reviewPeriod} max={currentPeriod()} onChange={(e) => set("reviewPeriod", e.target.value)} />
      </label>

      <div>
        <p className="mb-2 text-sm font-semibold text-slate-900">Overall rating *</p>
        <div className="grid gap-2 md:grid-cols-3">
          {RATINGS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => set("rating", option.value)}
              className={`rounded-xl border p-3 text-left transition ${form.rating === option.value ? option.selected : "border-slate-200 hover:border-slate-300"}`}
            >
              <p className="text-sm font-semibold text-slate-900">{option.label}</p>
              <p className="text-xs text-slate-500">{option.desc}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {commentField("uptimeComment", "Uptime & energy", "System uptime and energy output")}
        {commentField("beneficiaryComment", "Installations & beneficiaries", "Progress against installation targets")}
        {commentField("genderInclusionComment", "Gender & inclusion", "Female-headed and vulnerable households")}
      </div>

      <label className="block">
        <span className="mb-1 block text-sm font-semibold text-slate-900">Summary *</span>
        <textarea className="input-field min-h-[90px]" placeholder="Your overall assessment of the project's KPI performance this month" value={form.summary} onChange={(e) => set("summary", e.target.value)} />
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold text-slate-900">Recommendations</span>
        <textarea className="input-field min-h-[70px]" placeholder="Actions you recommend to RMT or the vendor" value={form.recommendations} onChange={(e) => set("recommendations", e.target.value)} />
      </label>

      <p className="text-xs text-slate-500">The KPI figures shown above are saved with the review, so readers can see what you assessed.</p>
      {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} className="btn-secondary" disabled={saving}>Cancel</button>
        <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
          {saving && <Loader2 size={16} className="animate-spin" />} {existing ? "Save Changes" : "Submit Review"}
        </button>
      </div>
    </div>
  );
}

function ProjectReviewDetail({
  project,
  reviews,
  currentUserId,
  onBack,
  onSaved,
  onOpenProject,
}: {
  project: Project;
  reviews: KpiReview[];
  currentUserId: string;
  onBack: () => void;
  onSaved: (review: KpiReview) => void;
  onOpenProject?: (projectId: string) => void;
}) {
  const [summary, setSummary] = useState<ProjectKpiSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [editing, setEditing] = useState<{ initial: KpiReviewInput; existing?: KpiReview } | null>(null);

  useEffect(() => {
    let active = true;
    setSummaryLoading(true);
    fetchProjectKpiSummary(project.id)
      .then((data) => { if (active) setSummary(data); })
      .catch(() => { if (active) setSummary(null); })
      .finally(() => { if (active) setSummaryLoading(false); });
    return () => { active = false; };
  }, [project.id]);

  const ownThisMonth = reviews.find((review) => review.reviewer === currentUserId && review.reviewPeriod === currentPeriod());

  const startNew = () => setEditing({ initial: emptyReview(project.id) });
  const startEdit = (review: KpiReview) => setEditing({
    existing: review,
    initial: {
      projectId: review.projectId,
      reviewPeriod: review.reviewPeriod,
      rating: review.rating,
      uptimeComment: review.uptimeComment,
      beneficiaryComment: review.beneficiaryComment,
      genderInclusionComment: review.genderInclusionComment,
      summary: review.summary,
      recommendations: review.recommendations,
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button type="button" onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-sm font-semibold text-slate-500 hover:text-slate-700">
            <ArrowLeft size={16} /> All regional projects
          </button>
          <h1 className="text-2xl font-bold text-slate-900">{project.projectReference || `PRJ-${project.id}`}</h1>
          <p className="text-sm text-slate-500">{project.projectTitle || project.vendorName} • {project.district || project.region}</p>
        </div>
        <div className="flex gap-2">
          {onOpenProject && (
            <button type="button" onClick={() => onOpenProject(project.id)} className="btn-secondary inline-flex items-center gap-2">
              <ExternalLink size={16} /> Open Project
            </button>
          )}
          {!editing && (
            ownThisMonth ? (
              <button type="button" onClick={() => startEdit(ownThisMonth)} className="btn-primary inline-flex items-center gap-2">
                <Pencil size={16} /> Edit This Month's Review
              </button>
            ) : (
              <button type="button" onClick={startNew} className="btn-primary inline-flex items-center gap-2">
                <Plus size={16} /> New Review
              </button>
            )
          )}
        </div>
      </div>

      {editing && (
        <KpiReviewForm
          initial={editing.initial}
          existing={editing.existing}
          summary={summary}
          onCancel={() => setEditing(null)}
          onSaved={(review) => { setEditing(null); onSaved(review); }}
        />
      )}

      <div className="card">
        <div className="border-b border-slate-100 p-5">
          <h3 className="text-lg font-bold text-slate-900">Review History</h3>
          <p className="text-xs text-slate-500">One review per officer per month. You can edit the reviews you wrote.</p>
        </div>
        {reviews.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">This project has not been reviewed yet.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {reviews.map((review) => {
              const meta = ratingMeta(review.rating);
              const own = review.reviewer === currentUserId;
              return (
                <div key={review.id} className="space-y-2 px-5 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-slate-900">{formatPeriod(review.reviewPeriod)}</p>
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${meta.badge}`}>{meta.label}</span>
                      <span className="text-xs text-slate-400">by {own ? "you" : review.reviewerName || review.reviewerUsername || "DoE Officer"}</span>
                    </div>
                    {own && !editing && (
                      <button type="button" onClick={() => startEdit(review)} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800">
                        <Pencil size={12} /> Edit
                      </button>
                    )}
                  </div>
                  <p className="whitespace-pre-line text-sm text-slate-700">{review.summary}</p>
                  {(review.uptimeComment || review.beneficiaryComment || review.genderInclusionComment) && (
                    <div className="grid gap-2 text-xs text-slate-600 md:grid-cols-3">
                      {review.uptimeComment && <p><span className="font-semibold text-slate-700">Uptime & energy:</span> {review.uptimeComment}</p>}
                      {review.beneficiaryComment && <p><span className="font-semibold text-slate-700">Installations:</span> {review.beneficiaryComment}</p>}
                      {review.genderInclusionComment && <p><span className="font-semibold text-slate-700">Gender & inclusion:</span> {review.genderInclusionComment}</p>}
                    </div>
                  )}
                  {review.recommendations && (
                    <p className="text-xs text-slate-600"><span className="font-semibold text-slate-700">Recommendations:</span> {review.recommendations}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="card p-5">
        <h3 className="mb-4 text-lg font-bold text-slate-900">Current KPIs</h3>
        {summaryLoading ? (
          <div className="py-8 text-center text-slate-500"><Loader2 size={20} className="mx-auto animate-spin" /></div>
        ) : (
          <KpiDashboard projectId={project.id} projectKpi={summary} />
        )}
      </div>
    </div>
  );
}

export function DoeKpiReview({ currentUser, onOpenProject }: { currentUser: any; onOpenProject?: (projectId: string) => void }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [reviews, setReviews] = useState<KpiReview[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const currentUserId = currentUser?.id ? String(currentUser.id) : "";

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectList, reviewList] = await Promise.all([fetchProjects(), fetchKpiReviews()]);
      setProjects(projectList);
      setReviews(reviewList);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load KPI review data."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const reviewsByProject = useMemo(() => {
    const map: Record<string, KpiReview[]> = {};
    reviews.forEach((review) => {
      (map[review.projectId] ||= []).push(review);
    });
    Object.values(map).forEach((list) => list.sort((a, b) => b.reviewPeriod.localeCompare(a.reviewPeriod) || b.updatedAt.localeCompare(a.updatedAt)));
    return map;
  }, [reviews]);

  const stats = useMemo(() => {
    const period = currentPeriod();
    const reviewedThisMonth = new Set(reviews.filter((review) => review.reviewPeriod === period).map((review) => review.projectId));
    const latest = projects.map((project) => reviewsByProject[project.id]?.[0]).filter(Boolean) as KpiReview[];
    return {
      reviewedThisMonth: reviewedThisMonth.size,
      dueThisMonth: projects.filter((project) => !reviewedThisMonth.has(project.id)).length,
      atRisk: latest.filter((review) => review.rating === "at_risk").length,
      needsAttention: latest.filter((review) => review.rating === "needs_attention").length,
    };
  }, [projects, reviews, reviewsByProject]);

  const handleSaved = (saved: KpiReview) => {
    setReviews((prev) => [saved, ...prev.filter((review) => review.id !== saved.id)]);
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="mx-auto mb-2 animate-spin" />
        Loading KPI review...
      </div>
    );
  }

  if (error) {
    return (
      <div className="card border-rose-200 bg-rose-50 p-10 text-center text-rose-700">
        <AlertTriangle size={24} className="mx-auto mb-2" />
        {error}
        <button type="button" onClick={() => void loadData()} className="btn-secondary mx-auto mt-4 flex items-center gap-2">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  const selectedProject = selectedProjectId ? projects.find((project) => project.id === selectedProjectId) : null;
  if (selectedProject) {
    return (
      <ProjectReviewDetail
        project={selectedProject}
        reviews={reviewsByProject[selectedProject.id] || []}
        currentUserId={currentUserId}
        onBack={() => setSelectedProjectId(null)}
        onSaved={handleSaved}
        onOpenProject={onOpenProject}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">KPI Review</h1>
          <p className="text-sm text-slate-500">Review the KPI performance of projects in {currentUser?.region || "your region"} each month.</p>
        </div>
        <button type="button" onClick={() => void loadData()} className="btn-secondary inline-flex items-center gap-2 self-start">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: `Reviewed in ${formatPeriod(currentPeriod())}`, value: stats.reviewedThisMonth, tone: "text-emerald-700" },
          { label: "Awaiting review this month", value: stats.dueThisMonth, tone: stats.dueThisMonth ? "text-amber-700" : "text-emerald-700" },
          { label: "Latest rating: needs attention", value: stats.needsAttention, tone: "text-amber-700" },
          { label: "Latest rating: at risk", value: stats.atRisk, tone: stats.atRisk ? "text-rose-700" : "text-slate-900" },
        ].map((card) => (
          <div key={card.label} className="card p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">{card.label}</p>
            <p className={`mt-3 text-3xl font-bold ${card.tone}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="border-b border-slate-100 p-5">
          <h3 className="text-lg font-bold text-slate-900">Regional Projects</h3>
          <p className="text-xs text-slate-500">Open a project to see its KPIs and add or update your review.</p>
        </div>
        {projects.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">No projects are currently assigned to this regional scope.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-semibold">Project</th>
                  <th className="px-5 py-3 text-left font-semibold">Vendor</th>
                  <th className="px-5 py-3 text-left font-semibold">Progress</th>
                  <th className="px-5 py-3 text-left font-semibold">Uptime</th>
                  <th className="px-5 py-3 text-left font-semibold">Latest review</th>
                  <th className="px-5 py-3 text-left font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {projects.map((project) => {
                  const latest = reviewsByProject[project.id]?.[0];
                  const reviewedThisMonth = (reviewsByProject[project.id] || []).some((review) => review.reviewPeriod === currentPeriod());
                  return (
                    <tr key={project.id} className="hover:bg-slate-50">
                      <td className="px-5 py-3">
                        <p className="font-semibold text-slate-900">{project.projectReference || `PRJ-${project.id}`}</p>
                        <p className="text-xs text-slate-500">{project.district || project.region}</p>
                      </td>
                      <td className="px-5 py-3 text-slate-600">{project.vendorName || "—"}</td>
                      <td className="px-5 py-3 text-slate-600">{project.progress || 0}%</td>
                      <td className={`px-5 py-3 ${(project.uptime || 0) < 95 ? "font-semibold text-rose-600" : "text-slate-600"}`}>{project.uptime || 0}%</td>
                      <td className="px-5 py-3">
                        {latest ? (
                          <div className="flex flex-col gap-1">
                            <span className={`inline-flex w-fit rounded-full px-2.5 py-1 text-[11px] font-bold ${ratingMeta(latest.rating).badge}`}>{ratingMeta(latest.rating).label}</span>
                            <span className="text-xs text-slate-400">{formatPeriod(latest.reviewPeriod)}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">Not reviewed</span>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <button type="button" onClick={() => setSelectedProjectId(project.id)} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800">
                          <ClipboardCheck size={12} /> {reviewedThisMonth ? "View Reviews" : "Review"}
                        </button>
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
  );
}
