import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarCheck,
  Camera,
  CheckCircle2,
  ClipboardList,
  Eye,
  Loader2,
  LocateFixed,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import {
  createSiteMonitoringVisit,
  fetchInstallationReports,
  fetchProjects,
  fetchSiteMonitoringVisits,
  removeSiteMonitoringPhoto,
  SiteMonitoringVisitInput,
  updateSiteMonitoringVisit,
} from "../api";
import { InstallationReport, Project, SiteMonitoringVisit, SiteVisitFollowUpStatus } from "../types";
import { GisInstallationsMap } from "./GisInstallationsMap";

const FOLLOW_UP_OPTIONS: { value: SiteVisitFollowUpStatus; label: string; badge: string }[] = [
  { value: "none", label: "No follow-up needed", badge: "bg-slate-100 text-slate-600" },
  { value: "open", label: "Open", badge: "bg-amber-100 text-amber-700" },
  { value: "in_progress", label: "In progress", badge: "bg-blue-100 text-blue-700" },
  { value: "closed", label: "Closed", badge: "bg-emerald-100 text-emerald-700" },
];

const followUpMeta = (status: SiteVisitFollowUpStatus) =>
  FOLLOW_UP_OPTIONS.find((option) => option.value === status) || FOLLOW_UP_OPTIONS[0];

const triStateLabel = (value: boolean | null) => (value === null ? "Not checked" : value ? "Yes" : "No");

const errorMessage = (err: any, fallback: string) => {
  const raw = String(err?.message || "");
  const json = raw.slice(raw.indexOf("{"));
  try {
    const parsed = JSON.parse(json);
    if (parsed?.detail) return String(parsed.detail);
    const first = Object.entries(parsed || {})[0];
    if (first) return `${first[0].replace(/_/g, " ")}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
  } catch {
    // Not a JSON error body.
  }
  return fallback;
};

const todayIso = () => new Date().toISOString().slice(0, 10);

const projectLabel = (project?: Pick<Project, "projectReference" | "projectTitle" | "id">) =>
  project ? `${project.projectReference || `PRJ-${project.id}`}${project.projectTitle ? ` — ${project.projectTitle}` : ""}` : "";

type VisitFormState = SiteMonitoringVisitInput & { id?: string };

const emptyForm = (projectId = ""): VisitFormState => ({
  projectId,
  installationId: "",
  visitDate: todayIso(),
  systemWorking: null,
  beneficiaryPresent: null,
  observations: "",
  followUpAction: "",
  followUpStatus: "none",
  latitude: null,
  longitude: null,
  photos: [],
});

function TriStateField({ label, value, onChange, disabled }: {
  label: string;
  value: boolean | null;
  onChange: (value: boolean | null) => void;
  disabled?: boolean;
}) {
  const options: { label: string; value: boolean | null }[] = [
    { label: "Yes", value: true },
    { label: "No", value: false },
    { label: "Not checked", value: null },
  ];
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-slate-900">{label}</p>
      <div className="flex gap-2">
        {options.map((option) => (
          <button
            key={option.label}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`flex-1 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
              value === option.value ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-600 hover:border-slate-300"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function SiteVisitModal({
  projects,
  initial,
  existingVisit,
  readOnly,
  onClose,
  onSaved,
}: {
  projects: Project[];
  initial: VisitFormState;
  existingVisit?: SiteMonitoringVisit;
  readOnly: boolean;
  onClose: () => void;
  onSaved: (visit: SiteMonitoringVisit) => void;
}) {
  const [form, setForm] = useState<VisitFormState>(initial);
  const [installations, setInstallations] = useState<InstallationReport[]>([]);
  const [loadingInstallations, setLoadingInstallations] = useState(false);
  const [existingPhotos, setExistingPhotos] = useState(existingVisit?.photos || []);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = Boolean(existingVisit);

  const set = <K extends keyof VisitFormState>(key: K, value: VisitFormState[K]) => setForm((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    if (!form.projectId) {
      setInstallations([]);
      return;
    }
    let active = true;
    setLoadingInstallations(true);
    fetchInstallationReports(form.projectId)
      .then((rows) => { if (active) setInstallations(rows); })
      .catch(() => { if (active) setInstallations([]); })
      .finally(() => { if (active) setLoadingInstallations(false); });
    return () => { active = false; };
  }, [form.projectId]);

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setError("This browser cannot share its location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setForm((prev) => ({
          ...prev,
          latitude: Number(position.coords.latitude.toFixed(6)),
          longitude: Number(position.coords.longitude.toFixed(6)),
        }));
        setLocating(false);
      },
      () => {
        setError("Could not read your location. Check the browser's location permission.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  const removeExistingPhoto = async (photoId: string) => {
    if (!existingVisit || !window.confirm("Remove this photo?")) return;
    try {
      const updated = await removeSiteMonitoringPhoto(existingVisit.id, photoId);
      setExistingPhotos(updated.photos);
    } catch (err) {
      setError(errorMessage(err, "Unable to remove the photo."));
    }
  };

  const submit = async () => {
    if (!form.projectId) return setError("Select the project you visited.");
    if (!form.visitDate) return setError("Enter the visit date.");
    if (form.observations.trim().length < 10) return setError("Describe what you observed (at least 10 characters).");
    if ((form.followUpStatus === "open" || form.followUpStatus === "in_progress") && !form.followUpAction.trim()) {
      return setError("Describe the follow-up action needed.");
    }
    const photoCount = existingPhotos.length + (form.photos?.length || 0);
    if (photoCount > 10) return setError("A visit can have at most 10 photos.");
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form, observations: form.observations.trim(), followUpAction: form.followUpAction.trim() };
      const saved = isEdit && existingVisit
        ? await updateSiteMonitoringVisit(existingVisit.id, payload)
        : await createSiteMonitoringVisit(payload);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, "Unable to save the visit."));
    } finally {
      setSaving(false);
    }
  };

  const title = readOnly ? "Site Visit" : isEdit ? "Edit Site Visit" : "Log Site Visit";

  return (
    <div className="fixed inset-0 z-[9999] flex items-start justify-center overflow-y-auto bg-black/50 p-4">
      <div className="my-8 w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <ClipboardList size={20} className="text-emerald-600" /> {title}
          </h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        {readOnly && existingVisit && (
          <p className="mb-4 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
            Logged by {existingVisit.visitedByName || existingVisit.visitedByUsername || "a DoE officer"}. Only the officer who logged a visit can edit it.
          </p>
        )}

        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-slate-900">Project *</span>
              <select
                className="input-field"
                value={form.projectId}
                disabled={readOnly || isEdit}
                onChange={(e) => setForm((prev) => ({ ...prev, projectId: e.target.value, installationId: "" }))}
              >
                <option value="">Select a project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{projectLabel(project)}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-slate-900">Visit date *</span>
              <input
                type="date"
                className="input-field"
                value={form.visitDate}
                max={todayIso()}
                disabled={readOnly}
                onChange={(e) => set("visitDate", e.target.value)}
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Installation (optional)</span>
            <select
              className="input-field"
              value={form.installationId || ""}
              disabled={readOnly || !form.projectId || loadingInstallations}
              onChange={(e) => set("installationId", e.target.value)}
            >
              <option value="">{loadingInstallations ? "Loading installations..." : "Whole project / not a single installation"}</option>
              {installations.map((installation) => (
                <option key={installation.id} value={installation.id}>
                  {installation.serialNumber || `INS-${installation.id}`}{installation.district ? ` — ${installation.district}` : ""}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <TriStateField label="System working?" value={form.systemWorking} disabled={readOnly} onChange={(value) => set("systemWorking", value)} />
            <TriStateField label="Beneficiary present?" value={form.beneficiaryPresent} disabled={readOnly} onChange={(value) => set("beneficiaryPresent", value)} />
          </div>

          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-slate-900">Observations *</span>
            <textarea
              className="input-field min-h-[110px]"
              placeholder="What did you see on site? Condition of the system, community feedback, issues found..."
              value={form.observations}
              disabled={readOnly}
              onChange={(e) => set("observations", e.target.value)}
            />
          </label>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-slate-900">Follow-up</span>
              <select
                className="input-field"
                value={form.followUpStatus}
                disabled={readOnly}
                onChange={(e) => set("followUpStatus", e.target.value as SiteVisitFollowUpStatus)}
              >
                {FOLLOW_UP_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="block md:col-span-2">
              <span className="mb-1 block text-sm font-semibold text-slate-900">
                Follow-up action{form.followUpStatus === "open" || form.followUpStatus === "in_progress" ? " *" : ""}
              </span>
              <input
                className="input-field"
                placeholder="e.g. Vendor to replace faulty charge controller"
                value={form.followUpAction}
                disabled={readOnly}
                onChange={(e) => set("followUpAction", e.target.value)}
              />
            </label>
          </div>
          {!readOnly && (form.followUpStatus === "open" || form.followUpStatus === "in_progress") && !isEdit && (
            <p className="text-xs text-amber-700">RMT is notified when a visit is logged with an open follow-up.</p>
          )}

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-900">GPS location (optional)</span>
              {!readOnly && (
                <button type="button" onClick={useCurrentLocation} disabled={locating} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800">
                  {locating ? <Loader2 size={12} className="animate-spin" /> : <LocateFixed size={12} />} Use my location
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input
                type="number"
                step="any"
                className="input-field"
                placeholder="Latitude"
                value={form.latitude ?? ""}
                disabled={readOnly}
                onChange={(e) => set("latitude", e.target.value === "" ? null : Number(e.target.value))}
              />
              <input
                type="number"
                step="any"
                className="input-field"
                placeholder="Longitude"
                value={form.longitude ?? ""}
                disabled={readOnly}
                onChange={(e) => set("longitude", e.target.value === "" ? null : Number(e.target.value))}
              />
            </div>
          </div>

          <div>
            <span className="mb-1 block text-sm font-semibold text-slate-900">Site photos</span>
            {existingPhotos.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {existingPhotos.map((photo) => (
                  <div key={photo.id} className="relative">
                    <a href={photo.file} target="_blank" rel="noreferrer">
                      <img src={photo.file} alt="Site visit" className="h-20 w-20 rounded-lg border border-slate-200 object-cover" />
                    </a>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => void removeExistingPhoto(photo.id)}
                        className="absolute -right-1.5 -top-1.5 rounded-full bg-rose-600 p-0.5 text-white"
                        aria-label="Remove photo"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {!readOnly && (
              <>
                <input
                  type="file"
                  accept=".jpg,.jpeg,.png"
                  multiple
                  onChange={(e) => set("photos", Array.from(e.target.files || []))}
                  className="block w-full text-sm text-slate-600"
                />
                <p className="mt-1 text-xs text-slate-500">JPG or PNG, up to 10 photos per visit.</p>
              </>
            )}
            {readOnly && existingPhotos.length === 0 && <p className="text-xs text-slate-500">No photos attached.</p>}
          </div>

          {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>{readOnly ? "Close" : "Cancel"}</button>
          {!readOnly && (
            <button type="button" onClick={() => void submit()} className="btn-primary inline-flex items-center gap-2" disabled={saving}>
              {saving && <Loader2 size={16} className="animate-spin" />}
              {isEdit ? "Save Changes" : "Log Visit"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function DoeRegionalMonitoring({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [visits, setVisits] = useState<SiteMonitoringVisit[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [followUpFilter, setFollowUpFilter] = useState<"" | SiteVisitFollowUpStatus>("");
  const [modal, setModal] = useState<{ initial: VisitFormState; visit?: SiteMonitoringVisit; readOnly: boolean } | null>(null);

  const regionLabel = currentUser?.region || "your region";
  const currentUserId = currentUser?.id ? String(currentUser.id) : "";

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectList, visitList] = await Promise.all([fetchProjects(), fetchSiteMonitoringVisits()]);
      setProjects(projectList);
      setVisits(visitList);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load regional monitoring data."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const projectMap = useMemo(() => Object.fromEntries(projects.map((project) => [project.id, project])), [projects]);

  const filteredVisits = useMemo(
    () => visits.filter((visit) =>
      (!projectFilter || visit.projectId === projectFilter) && (!followUpFilter || visit.followUpStatus === followUpFilter),
    ),
    [visits, projectFilter, followUpFilter],
  );

  const stats = useMemo(() => {
    const monthPrefix = todayIso().slice(0, 7);
    return {
      thisMonth: visits.filter((visit) => visit.visitDate.startsWith(monthPrefix)).length,
      openFollowUps: visits.filter((visit) => visit.followUpStatus === "open" || visit.followUpStatus === "in_progress").length,
      notWorking: visits.filter((visit) => visit.systemWorking === false).length,
      projectsVisited: new Set(visits.map((visit) => visit.projectId)).size,
    };
  }, [visits]);

  const openNew = () => setModal({ initial: emptyForm(projectFilter), readOnly: false });

  const openVisit = (visit: SiteMonitoringVisit) => {
    const own = Boolean(currentUserId) && visit.visitedBy === currentUserId;
    setModal({
      visit,
      readOnly: !own,
      initial: {
        projectId: visit.projectId,
        installationId: visit.installationId || "",
        visitDate: visit.visitDate,
        systemWorking: visit.systemWorking,
        beneficiaryPresent: visit.beneficiaryPresent,
        observations: visit.observations,
        followUpAction: visit.followUpAction,
        followUpStatus: visit.followUpStatus,
        latitude: visit.latitude,
        longitude: visit.longitude,
        photos: [],
      },
    });
  };

  const handleSaved = (saved: SiteMonitoringVisit) => {
    setVisits((prev) => {
      const rest = prev.filter((visit) => visit.id !== saved.id);
      return [saved, ...rest].sort((a, b) => b.visitDate.localeCompare(a.visitDate) || b.createdAt.localeCompare(a.createdAt));
    });
    setModal(null);
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="mx-auto mb-2 animate-spin" />
        Loading regional monitoring...
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

  return (
    <div className="space-y-6">
      {modal && (
        <SiteVisitModal
          projects={projects}
          initial={modal.initial}
          existingVisit={modal.visit}
          readOnly={modal.readOnly}
          onClose={() => setModal(null)}
          onSaved={handleSaved}
        />
      )}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regional Monitoring</h1>
          <p className="text-sm text-slate-500">Site monitoring visits and installations in {regionLabel}.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void loadData()} className="btn-secondary inline-flex items-center gap-2">
            <RefreshCw size={16} /> Refresh
          </button>
          <button type="button" onClick={openNew} disabled={projects.length === 0} className="btn-primary inline-flex items-center gap-2">
            <Plus size={16} /> Log Site Visit
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Visits this month", value: stats.thisMonth, icon: CalendarCheck, tone: "bg-blue-100 text-blue-600" },
          { label: "Open follow-ups", value: stats.openFollowUps, icon: AlertTriangle, tone: stats.openFollowUps ? "bg-amber-100 text-amber-600" : "bg-emerald-100 text-emerald-600" },
          { label: "Systems found not working", value: stats.notWorking, icon: X, tone: stats.notWorking ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600" },
          { label: "Projects visited", value: `${stats.projectsVisited} / ${projects.length}`, icon: MapPin, tone: "bg-emerald-100 text-emerald-600" },
        ].map((card) => (
          <div key={card.label} className="card p-5">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500">{card.label}</p>
              <div className={`rounded-lg p-2 ${card.tone}`}><card.icon size={18} /></div>
            </div>
            <p className="mt-3 text-3xl font-bold text-slate-900">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-5 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Site Visits</h3>
            <p className="text-xs text-slate-500">You can edit the visits you logged. Visits are kept as a permanent record and cannot be deleted.</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select className="input-field sm:w-64" value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}>
              <option value="">All projects</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{projectLabel(project)}</option>
              ))}
            </select>
            <select className="input-field sm:w-44" value={followUpFilter} onChange={(e) => setFollowUpFilter(e.target.value as any)}>
              <option value="">Any follow-up</option>
              {FOLLOW_UP_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
        {filteredVisits.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-slate-500">
            <ClipboardList size={22} className="mx-auto mb-2 text-slate-300" />
            {visits.length === 0 ? "No site visits logged yet. Use “Log Site Visit” after visiting a project." : "No visits match these filters."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-semibold">Date</th>
                  <th className="px-5 py-3 text-left font-semibold">Project</th>
                  <th className="px-5 py-3 text-left font-semibold">System working</th>
                  <th className="px-5 py-3 text-left font-semibold">Observations</th>
                  <th className="px-5 py-3 text-left font-semibold">Follow-up</th>
                  <th className="px-5 py-3 text-left font-semibold">Logged by</th>
                  <th className="px-5 py-3 text-left font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredVisits.map((visit) => {
                  const own = Boolean(currentUserId) && visit.visitedBy === currentUserId;
                  const meta = followUpMeta(visit.followUpStatus);
                  return (
                    <tr key={visit.id} className="hover:bg-slate-50">
                      <td className="whitespace-nowrap px-5 py-3 text-slate-700">{visit.visitDate}</td>
                      <td className="px-5 py-3">
                        <p className="font-semibold text-slate-900">{visit.projectReference || projectLabel(projectMap[visit.projectId]) || `PRJ-${visit.projectId}`}</p>
                        {visit.installationSerial && <p className="text-xs text-slate-500">Installation {visit.installationSerial}</p>}
                      </td>
                      <td className="px-5 py-3">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                          visit.systemWorking === false ? "bg-rose-100 text-rose-700" : visit.systemWorking ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"
                        }`}>
                          {visit.systemWorking ? <CheckCircle2 size={12} /> : null}
                          {triStateLabel(visit.systemWorking)}
                        </span>
                      </td>
                      <td className="max-w-xs px-5 py-3 text-slate-600">
                        <p className="truncate">{visit.observations}</p>
                        {visit.photos.length > 0 && (
                          <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-slate-400"><Camera size={12} /> {visit.photos.length}</p>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${meta.badge}`}>{meta.label}</span>
                      </td>
                      <td className="px-5 py-3 text-slate-600">{own ? "You" : visit.visitedByName || visit.visitedByUsername || "—"}</td>
                      <td className="px-5 py-3">
                        <button type="button" onClick={() => openVisit(visit)} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 hover:text-emerald-800">
                          {own ? <><Pencil size={12} /> Edit</> : <><Eye size={12} /> View</>}
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

      <div className="card p-6">
        <h3 className="mb-1 text-lg font-bold text-slate-900">Regional Map</h3>
        <p className="mb-4 text-sm text-slate-500">All installations in your region. Click a marker to see its details.</p>
        <GisInstallationsMap height="520px" />
      </div>
    </div>
  );
}
