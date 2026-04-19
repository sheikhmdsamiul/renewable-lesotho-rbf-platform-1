import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronRight,
  Download,
  Eye,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  UserCog,
  Users,
} from "lucide-react";
import {
  checkProspectConnection,
  createAdminManagedUser,
  createOrganization,
  deactivateAdminManagedUser,
  deleteOrganization,
  exportSystemAuditLogs,
  fetchAdminManagedUsers,
  fetchAdminUserDetail,
  fetchOrganizations,
  fetchPlatformConfiguration,
  fetchProspectSyncLogs,
  fetchProspectSyncSummary,
  fetchSuperAdminDashboardSummary,
  fetchSystemAuditLogs,
  fetchSystemHealth,
  fetchUserManagementMeta,
  refreshBoundaryFile,
  resetAdminManagedUserPassword,
  retryAllFailedProspectSyncJobs,
  retryProspectSyncJob,
  updateAdminManagedUser,
  updateOrganization,
  updatePlatformConfiguration,
} from "../api";
import {
  AuditLog,
  Notification,
  Organization,
  PlatformConfiguration,
  ProspectSyncLog,
  SuperAdminDashboardSummary,
  SystemHealthPayload,
  User,
  UserRole,
} from "../types";

const DISTRICTS = [
  "Maseru",
  "Leribe",
  "Berea",
  "Mafeteng",
  "Mohale's Hoek",
  "Quthing",
  "Qacha's Nek",
  "Mokhotlong",
  "Thaba-Tseka",
  "Butha-Buthe",
];

const emptyUserForm = {
  fullName: "",
  email: "",
  role: "",
  gender: "Male" as "Male" | "Female" | "Other",
  district: "",
  isActive: true,
};

const emptyOrganizationForm = {
  id: "",
  name: "",
  type: "Government" as "Government" | "International" | "NGO",
  contactPerson: "",
  email: "",
  phone: "",
  address: "",
};

const statusPill = (ok: boolean) =>
  ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

const formatRelativeTime = (value?: string | null) => {
  if (!value) return "Never";
  const delta = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(delta)) return "Unknown";
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
};

const formatBytes = (value?: number) => {
  const bytes = Number(value ?? 0);
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const normalized = bytes / 1024 ** index;
  return `${normalized.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
};

const formatJsonBlock = (value: unknown) => {
  if (value == null) return "No payload captured.";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const saveBlob = (blob: Blob, filename: string) => {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
};

const toneForNotification = (status: Notification["status"]) => {
  if (status === "Delivered") return "bg-emerald-100 text-emerald-700";
  if (status === "Read") return "bg-blue-100 text-blue-700";
  if (status === "Failed") return "bg-rose-100 text-rose-700";
  return "bg-slate-100 text-slate-600";
};

type AdminSection =
  | "dashboard"
  | "users"
  | "organizations"
  | "system_configuration"
  | "prospect_sync"
  | "audit_logs"
  | "notifications"
  | "system_health";

type Props = {
  section: AdminSection;
  notifications: Notification[];
  onNotificationSelect?: (note: Notification) => void;
};

export default function SuperAdminPortal({ section, notifications, onNotificationSelect }: Props) {
  const [banner, setBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<SuperAdminDashboardSummary | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);

  const [users, setUsers] = useState<User[]>([]);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [userView, setUserView] = useState<"list" | "create" | "edit" | "detail">("list");
  const [roleOptions, setRoleOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [userFilters, setUserFilters] = useState({ role: "", district: "", status: "" });
  const [userSearch, setUserSearch] = useState("");
  const [userForm, setUserForm] = useState(emptyUserForm);
  const [usersLoading, setUsersLoading] = useState(false);
  const [userSubmitting, setUserSubmitting] = useState(false);

  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationForm, setOrganizationForm] = useState(emptyOrganizationForm);
  const [organizationsLoading, setOrganizationsLoading] = useState(false);
  const [organizationSubmitting, setOrganizationSubmitting] = useState(false);

  const [configuration, setConfiguration] = useState<PlatformConfiguration | null>(null);
  const [configurationLoading, setConfigurationLoading] = useState(false);
  const [configurationSubmitting, setConfigurationSubmitting] = useState(false);

  const [connectionStatus, setConnectionStatus] = useState<{ readTokenOk: boolean; writeTokenOk: boolean; baseUrl?: string } | null>(null);
  const [prospectSummary, setProspectSummary] = useState<Awaited<ReturnType<typeof fetchProspectSyncSummary>> | null>(null);
  const [prospectLogs, setProspectLogs] = useState<ProspectSyncLog[]>([]);
  const [prospectLoading, setProspectLoading] = useState(false);
  const [expandedPayloadLogId, setExpandedPayloadLogId] = useState<string | null>(null);

  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditFilters, setAuditFilters] = useState({
    actor: "",
    actorRole: "",
    action: "",
    module: "",
    dateFrom: "",
    dateTo: "",
    recordId: "",
  });

  const [health, setHealth] = useState<SystemHealthPayload | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const clearFlash = () => {
    setBanner(null);
    setError(null);
  };

  const loadUsers = async () => {
    setUsersLoading(true);
    try {
      const [list, meta] = await Promise.all([
        fetchAdminManagedUsers({
          role: userFilters.role || undefined,
          district: userFilters.district || undefined,
          status: userFilters.status ? (userFilters.status as "active" | "inactive") : undefined,
        }),
        fetchUserManagementMeta(),
      ]);
      setUsers(list);
      setRoleOptions(meta.roles ?? []);
      setUserForm((prev) => ({ ...prev, role: prev.role || meta.roles?.[0]?.value || "" }));
    } catch (err: any) {
      setError(String(err?.message || "Unable to load users."));
    } finally {
      setUsersLoading(false);
    }
  };

  const loadDashboard = async () => {
    setDashboardLoading(true);
    try {
      setDashboard(await fetchSuperAdminDashboardSummary());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load dashboard."));
    } finally {
      setDashboardLoading(false);
    }
  };

  const loadOrganizations = async () => {
    setOrganizationsLoading(true);
    try {
      setOrganizations(await fetchOrganizations());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load organizations."));
    } finally {
      setOrganizationsLoading(false);
    }
  };

  const loadConfiguration = async () => {
    setConfigurationLoading(true);
    try {
      setConfiguration(await fetchPlatformConfiguration());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load configuration."));
    } finally {
      setConfigurationLoading(false);
    }
  };

  const loadProspect = async () => {
    setProspectLoading(true);
    try {
      const [summary, logs, connection] = await Promise.all([
        fetchProspectSyncSummary(),
        fetchProspectSyncLogs({ pageSize: 50 }),
        checkProspectConnection(),
      ]);
      setProspectSummary(summary);
      setProspectLogs(logs);
      setConnectionStatus(connection);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load Prospect sync data."));
    } finally {
      setProspectLoading(false);
    }
  };

  const loadAudit = async () => {
    setAuditLoading(true);
    try {
      setAuditLogs(await fetchSystemAuditLogs(auditFilters));
    } catch (err: any) {
      setError(String(err?.message || "Unable to load audit logs."));
    } finally {
      setAuditLoading(false);
    }
  };

  const loadHealth = async () => {
    setHealthLoading(true);
    try {
      setHealth(await fetchSystemHealth());
    } catch (err: any) {
      setError(String(err?.message || "Unable to load system health."));
    } finally {
      setHealthLoading(false);
    }
  };

  useEffect(() => {
    clearFlash();
    if (section === "dashboard") void loadDashboard();
    if (section === "users") void loadUsers();
    if (section === "organizations") void loadOrganizations();
    if (section === "system_configuration") void loadConfiguration();
    if (section === "prospect_sync") void loadProspect();
    if (section === "audit_logs") void loadAudit();
    if (section === "system_health") void loadHealth();
  }, [section]);

  useEffect(() => {
    if (section === "users") void loadUsers();
  }, [userFilters.role, userFilters.district, userFilters.status]);

  const visibleUsers = useMemo(() => {
    const query = userSearch.trim().toLowerCase();
    if (!query) return users;
    return users.filter((user) =>
      `${user.fullName} ${user.email} ${user.roleLabel || user.role} ${user.district || user.region || ""}`
        .toLowerCase()
        .includes(query),
    );
  }, [userSearch, users]);

  const visibleNotifications = useMemo(() => {
    return notifications.slice().sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  }, [notifications]);

  const resetUserForm = () => {
    setUserForm({ ...emptyUserForm, role: roleOptions[0]?.value || "" });
    setSelectedUser(null);
  };

  const openUserCreate = () => {
    resetUserForm();
    setUserView("create");
  };

  const openUserDetail = async (userId: string, nextView: "detail" | "edit") => {
    setUsersLoading(true);
    try {
      const detail = await fetchAdminUserDetail(userId);
      setSelectedUser(detail);
      setUserForm({
        fullName: detail.fullName || "",
        email: detail.email || "",
        role: detail.role || roleOptions[0]?.value || "",
        gender: detail.gender || "Male",
        district: detail.district || detail.region || detail.verificationZone || "",
        isActive: detail.isActive ?? detail.status === "Active",
      });
      setUserView(nextView);
    } catch (err: any) {
      setError(String(err?.message || "Unable to load user detail."));
    } finally {
      setUsersLoading(false);
    }
  };

  const saveUser = async (event: React.FormEvent) => {
    event.preventDefault();
    clearFlash();
    const requiresDistrict = [UserRole.FIELD_VERIFIER, UserRole.DOE_OFFICER].includes(userForm.role as UserRole);
    if (!userForm.fullName.trim() || !userForm.email.trim() || !userForm.role || !userForm.gender) {
      setError("Full name, email, role, and gender are required.");
      return;
    }
    if (requiresDistrict && !userForm.district.trim()) {
      setError("Assigned district is required for Field Officer and DoE roles.");
      return;
    }
    setUserSubmitting(true);
    try {
      if (userView === "create") {
        const result = await createAdminManagedUser({
          fullName: userForm.fullName.trim(),
          email: userForm.email.trim(),
          role: userForm.role,
          gender: userForm.gender,
          district: userForm.district.trim() || undefined,
        });
        setBanner(
          result.initialPassword
            ? `User created. Temporary password: ${result.initialPassword}`
            : result.emailError
              ? `User created, but email delivery failed: ${result.emailError}`
              : "User created and credentials email sent.",
        );
      } else if (selectedUser) {
        const updated = await updateAdminManagedUser(selectedUser.id, {
          fullName: userForm.fullName.trim(),
          email: userForm.email.trim(),
          role: userForm.role,
          gender: userForm.gender,
          district: userForm.district.trim() || undefined,
          isActive: userForm.isActive,
        });
        setSelectedUser(updated);
        setBanner("User updated successfully.");
      }
      setUserView("list");
      await loadUsers();
    } catch (err: any) {
      setError(String(err?.message || "Unable to save user."));
    } finally {
      setUserSubmitting(false);
    }
  };

  const deactivateUser = async (id: string) => {
    if (!window.confirm("Deactivate this user immediately?")) return;
    setUserSubmitting(true);
    try {
      await deactivateAdminManagedUser(id);
      setBanner("User deactivated.");
      await loadUsers();
      if (selectedUser?.id === id) {
        setSelectedUser(await fetchAdminUserDetail(id));
      }
    } catch (err: any) {
      setError(String(err?.message || "Unable to deactivate user."));
    } finally {
      setUserSubmitting(false);
    }
  };

  const resetPassword = async (id: string) => {
    setUserSubmitting(true);
    try {
      const result = await resetAdminManagedUserPassword(id);
      setBanner(
        result.temporaryPassword
          ? `Temporary password reset: ${result.temporaryPassword}`
          : result.emailError
            ? `Password reset completed, but email delivery failed: ${result.emailError}`
            : "Password reset email sent.",
      );
      if (selectedUser?.id === id) {
        setSelectedUser(await fetchAdminUserDetail(id));
      }
    } catch (err: any) {
      setError(String(err?.message || "Unable to reset password."));
    } finally {
      setUserSubmitting(false);
    }
  };

  const saveOrganization = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!organizationForm.name.trim()) {
      setError("Organization name is required.");
      return;
    }
    setOrganizationSubmitting(true);
    try {
      if (organizationForm.id) {
        await updateOrganization(organizationForm.id, organizationForm);
        setBanner("Organization updated.");
      } else {
        await createOrganization(organizationForm);
        setBanner("Organization created.");
      }
      setOrganizationForm(emptyOrganizationForm);
      await loadOrganizations();
    } catch (err: any) {
      setError(String(err?.message || "Unable to save organization."));
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  const removeOrganization = async (id: string) => {
    if (!window.confirm("Delete this organization?")) return;
    setOrganizationSubmitting(true);
    try {
      await deleteOrganization(id);
      setBanner("Organization deleted.");
      await loadOrganizations();
      if (organizationForm.id === id) setOrganizationForm(emptyOrganizationForm);
    } catch (err: any) {
      setError(String(err?.message || "Unable to delete organization."));
    } finally {
      setOrganizationSubmitting(false);
    }
  };

  const saveConfiguration = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!configuration) return;
    setConfigurationSubmitting(true);
    try {
      const updated = await updatePlatformConfiguration(configuration);
      setConfiguration(updated);
      setBanner("System configuration updated.");
    } catch (err: any) {
      setError(String(err?.message || "Unable to update configuration."));
    } finally {
      setConfigurationSubmitting(false);
    }
  };

  const redownloadBoundary = async () => {
    setConfigurationSubmitting(true);
    try {
      await refreshBoundaryFile();
      setBanner("Lesotho boundary file re-downloaded.");
      setConfiguration(await fetchPlatformConfiguration());
    } catch (err: any) {
      setError(String(err?.message || "Unable to refresh boundary file."));
    } finally {
      setConfigurationSubmitting(false);
    }
  };

  const retryFailedJobs = async () => {
    try {
      const result = await retryAllFailedProspectSyncJobs();
      setBanner(`Queued ${result.count} failed Prospect sync job(s).`);
      await loadProspect();
      if (section === "dashboard") await loadDashboard();
    } catch (err: any) {
      setError(String(err?.message || "Unable to retry Prospect sync jobs."));
    }
  };

  const retryJob = async (id: string) => {
    try {
      await retryProspectSyncJob(id);
      setBanner("Prospect retry queued.");
      await loadProspect();
    } catch (err: any) {
      setError(String(err?.message || "Unable to retry this job."));
    }
  };

  const exportAudit = async (format: "csv" | "pdf") => {
    try {
      const blob = await exportSystemAuditLogs(format, auditFilters);
      saveBlob(blob, format === "csv" ? "audit_logs.csv" : "audit_logs.pdf");
    } catch (err: any) {
      setError(String(err?.message || `Unable to export ${format.toUpperCase()}.`));
    }
  };

  const sectionHeader = {
    dashboard: ["System Overview", "Live operational summary across the full Super Admin portal."],
    users: ["User Management", "Create, edit, deactivate, and audit all non-vendor accounts."],
    organizations: ["Organizations", "Manage stakeholder organizations and their points of contact."],
    system_configuration: ["System Configuration", "Control thresholds, notification behavior, and boundary assets."],
    prospect_sync: ["Prospect Sync", "Monitor connectivity, failed jobs, and recent sync activity."],
    audit_logs: ["Audit Logs", "Filter the full platform audit trail and export reports."],
    notifications: ["Notifications", "Review delivery history and open linked workflow items."],
    system_health: ["System Health", "Check database, queue, storage, and recent errors."],
  }[section];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{sectionHeader[0]}</h1>
          <p className="text-sm text-slate-500">{sectionHeader[1]}</p>
        </div>
        <button
          onClick={() => {
            if (section === "dashboard") void loadDashboard();
            if (section === "users") void loadUsers();
            if (section === "organizations") void loadOrganizations();
            if (section === "system_configuration") void loadConfiguration();
            if (section === "prospect_sync") void loadProspect();
            if (section === "audit_logs") void loadAudit();
            if (section === "system_health") void loadHealth();
          }}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {banner && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{banner}</div>}
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      {section === "dashboard" && (
        <div className="space-y-6">
          {dashboardLoading || !dashboard ? (
            <div className="card p-10 text-center text-slate-500">Loading dashboard summary...</div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Total Users", dashboard.stats.totalUsers, Users],
                  ["Active Projects", dashboard.stats.activeProjects, Activity],
                  ["Total Vendors", dashboard.stats.totalVendors, UserCog],
                  ["Pending Prequalifications", dashboard.stats.pendingPrequalifications, AlertTriangle],
                ].map(([label, value, Icon]: any) => (
                  <div key={label} className="card p-5">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">{label}</p>
                        <p className="mt-3 text-3xl font-bold text-slate-900">{value}</p>
                      </div>
                      <div className="rounded-xl bg-emerald-50 p-3 text-emerald-600">
                        <Icon size={20} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                <div className="card p-6 xl:col-span-1">
                  <h3 className="text-lg font-bold text-slate-900">System Health</h3>
                  <div className="mt-4 space-y-3 text-sm">
                    {[
                      ["Database", dashboard.systemHealth.database.status === "Connected", dashboard.systemHealth.database.status],
                      ["Queue Worker", dashboard.systemHealth.queue.workerStatus === "Running", dashboard.systemHealth.queue.workerStatus],
                      ["Scheduler", dashboard.systemHealth.scheduler.status === "Running", dashboard.systemHealth.scheduler.status],
                      ["Prospect API", dashboard.systemHealth.prospectApi.status === "Connected", dashboard.systemHealth.prospectApi.status],
                      ["Storage", dashboard.systemHealth.storage.freeBytes > 0, `${formatBytes(dashboard.systemHealth.storage.freeBytes)} free`],
                    ].map(([label, ok, value]) => (
                      <div key={String(label)} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
                        <span className="text-slate-600">{label}</span>
                        <span className={`rounded-full px-2 py-1 text-xs font-bold ${statusPill(Boolean(ok))}`}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card p-6 xl:col-span-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold text-slate-900">Prospect Sync Summary</h3>
                    <button onClick={() => void retryFailedJobs()} className="btn-secondary text-xs">
                      Retry All Failed
                    </button>
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-2xl bg-rose-50 p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-rose-500">Failed Jobs</p>
                      <p className="mt-3 text-3xl font-bold text-rose-700">{dashboard.prospectSyncSummary.failedJobs}</p>
                    </div>
                    <div className="rounded-2xl bg-blue-50 p-5">
                      <p className="text-xs font-bold uppercase tracking-widest text-blue-500">Last Sync</p>
                      <p className="mt-3 text-lg font-bold text-slate-900">{formatRelativeTime(dashboard.prospectSyncSummary.lastSyncAt)}</p>
                      <p className="text-xs text-slate-500">{formatDateTime(dashboard.prospectSyncSummary.lastSyncAt)}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="card p-6">
                <h3 className="text-lg font-bold text-slate-900">Recent Activity</h3>
                <div className="mt-4 space-y-3">
                  {dashboard.recentActivity.map((item) => (
                    <div key={item.id} className="rounded-xl border border-slate-100 px-4 py-3">
                      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                          <p className="font-semibold text-slate-900">{item.action}</p>
                          <p className="text-xs text-slate-500">
                            {item.actor} {item.role ? `• ${item.role}` : ""} {item.module ? `• ${item.module}` : ""} {item.record ? `• ${item.record}` : ""}
                          </p>
                        </div>
                        <span className="text-xs text-slate-400">{formatDateTime(item.timestamp)}</span>
                      </div>
                      {(item.notes || item.oldStatus || item.newStatus) && (
                        <p className="mt-2 text-xs text-slate-600">
                          {[item.oldStatus && `Old: ${item.oldStatus}`, item.newStatus && `New: ${item.newStatus}`, item.notes].filter(Boolean).join(" • ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {section === "users" && (
        <div className="space-y-6">
          {(userView === "create" || userView === "edit") && (
            <div className="card p-6">
              <div className="mb-5 flex items-center gap-3">
                <button onClick={() => setUserView("list")} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                  <ChevronRight className="rotate-180" size={18} />
                </button>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">{userView === "create" ? "Create User" : "Edit User"}</h3>
                  <p className="text-sm text-slate-500">Temp password, credentials email, Prospect sync, and audit logging are handled server-side.</p>
                </div>
              </div>
              <form onSubmit={saveUser} className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <input className="input-field" placeholder="Full Name *" value={userForm.fullName} onChange={(e) => setUserForm((prev) => ({ ...prev, fullName: e.target.value }))} />
                <input className="input-field" placeholder="Email *" type="email" value={userForm.email} onChange={(e) => setUserForm((prev) => ({ ...prev, email: e.target.value }))} />
                <select className="input-field" value={userForm.role} onChange={(e) => setUserForm((prev) => ({ ...prev, role: e.target.value }))}>
                  {roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <select className="input-field" value={userForm.gender} onChange={(e) => setUserForm((prev) => ({ ...prev, gender: e.target.value as "Male" | "Female" | "Other" }))}>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
                <select className="input-field" value={userForm.district} onChange={(e) => setUserForm((prev) => ({ ...prev, district: e.target.value }))}>
                  <option value="">Assigned District</option>
                  {DISTRICTS.map((district) => <option key={district} value={district}>{district}</option>)}
                </select>
                {userView === "edit" && (
                  <select className="input-field" value={userForm.isActive ? "active" : "inactive"} onChange={(e) => setUserForm((prev) => ({ ...prev, isActive: e.target.value === "active" }))}>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                )}
                <div className="md:col-span-2 flex gap-3">
                  <button type="button" onClick={() => setUserView("list")} className="btn-secondary">Cancel</button>
                  <button type="submit" disabled={userSubmitting} className="btn-primary flex items-center gap-2">
                    {userSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    {userView === "create" ? "Create User" : "Save Changes"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {userView === "detail" && selectedUser && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
              <div className="card p-6">
                <div className="mb-4 flex items-center gap-3">
                  <button onClick={() => setUserView("list")} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                    <ChevronRight className="rotate-180" size={18} />
                  </button>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900">{selectedUser.fullName}</h3>
                    <p className="text-sm text-slate-500">{selectedUser.email}</p>
                  </div>
                </div>
                <div className="space-y-2 text-sm text-slate-600">
                  <p><strong>Role:</strong> {selectedUser.roleLabel || selectedUser.role}</p>
                  <p><strong>District:</strong> {selectedUser.district || "—"}</p>
                  <p><strong>Status:</strong> {selectedUser.status}</p>
                  <p><strong>Last Login:</strong> {formatDateTime(selectedUser.lastLogin)}</p>
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  <button onClick={() => setUserView("edit")} className="btn-primary text-xs">Edit</button>
                  <button onClick={() => void resetPassword(selectedUser.id)} className="btn-secondary text-xs">Reset Password</button>
                  {(selectedUser.isActive !== false && selectedUser.status !== "Inactive") && (
                    <button onClick={() => void deactivateUser(selectedUser.id)} className="btn-secondary text-xs text-rose-700">Deactivate</button>
                  )}
                </div>
              </div>
              <div className="card p-6 xl:col-span-2">
                <h3 className="text-lg font-bold text-slate-900">Recent Audit Trail</h3>
                <div className="mt-4 space-y-3">
                  {(selectedUser.recentAuditLogs || []).map((log) => (
                    <div key={String(log.id)} className="rounded-xl border border-slate-100 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-slate-900">{log.action}</span>
                        <span className="text-xs text-slate-400">{formatDateTime(log.createdAt)}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{log.module || "users"} • {log.recordType || "user"} #{log.recordId ?? "—"}</p>
                    </div>
                  ))}
                </div>
                <h3 className="mt-6 text-lg font-bold text-slate-900">Prospect Sync Status</h3>
                <div className="mt-4 space-y-3">
                  {(selectedUser.prospectSyncStatus || []).map((log) => (
                    <div key={log.id} className="rounded-xl border border-slate-100 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-slate-900">{log.methodName}</span>
                        <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${log.status === "success" ? "bg-emerald-100 text-emerald-700" : log.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{log.status}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">Attempts: {log.attempts} • {formatDateTime(log.createdAt)}</p>
                      {log.errorMessage && <p className="mt-2 text-xs text-rose-600">{log.errorMessage}</p>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {userView === "list" && (
            <>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="card p-5"><p className="text-xs font-bold uppercase tracking-widest text-slate-400">Total Users</p><p className="mt-3 text-3xl font-bold text-slate-900">{users.length}</p></div>
                <div className="card p-5"><p className="text-xs font-bold uppercase tracking-widest text-slate-400">Active</p><p className="mt-3 text-3xl font-bold text-slate-900">{users.filter((user) => user.isActive !== false && user.status !== "Inactive").length}</p></div>
                <div className="card p-5"><p className="text-xs font-bold uppercase tracking-widest text-slate-400">Inactive</p><p className="mt-3 text-3xl font-bold text-slate-900">{users.filter((user) => user.isActive === false || user.status === "Inactive").length}</p></div>
                <div className="card p-5"><p className="text-xs font-bold uppercase tracking-widest text-slate-400">Roles Covered</p><p className="mt-3 text-3xl font-bold text-slate-900">{new Set(users.map((user) => user.role)).size}</p></div>
              </div>

              <div className="card">
                <div className="flex flex-col gap-4 border-b border-slate-100 p-6 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="text-lg font-bold">All Non-Vendor Accounts</h3>
                    <p className="text-sm text-slate-500">Columns match the Super Admin directory and link to detailed activity.</p>
                  </div>
                  <button onClick={openUserCreate} className="btn-primary flex items-center gap-2">
                    <Plus size={16} /> Create User
                  </button>
                </div>
                <div className="flex flex-col gap-3 border-b border-slate-100 p-6 lg:flex-row">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input className="input-field pl-9" placeholder="Search name, email, role, district..." value={userSearch} onChange={(e) => setUserSearch(e.target.value)} />
                  </div>
                  <select className="input-field lg:w-48" value={userFilters.role} onChange={(e) => setUserFilters((prev) => ({ ...prev, role: e.target.value }))}>
                    <option value="">All Roles</option>
                    {roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                  <select className="input-field lg:w-48" value={userFilters.district} onChange={(e) => setUserFilters((prev) => ({ ...prev, district: e.target.value }))}>
                    <option value="">All Districts</option>
                    {DISTRICTS.map((district) => <option key={district} value={district}>{district}</option>)}
                  </select>
                  <select className="input-field lg:w-40" value={userFilters.status} onChange={(e) => setUserFilters((prev) => ({ ...prev, status: e.target.value }))}>
                    <option value="">All Status</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="bg-slate-50">
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Name</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Email</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Role</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">District</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Status</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Last Login</th>
                        <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {usersLoading && (
                        <tr><td colSpan={7} className="px-6 py-10 text-center text-slate-500">Loading users...</td></tr>
                      )}
                      {!usersLoading && visibleUsers.length === 0 && (
                        <tr><td colSpan={7} className="px-6 py-10 text-center text-slate-500">No users matched the selected filters.</td></tr>
                      )}
                      {!usersLoading && visibleUsers.map((user) => (
                        <tr key={user.id} className="hover:bg-slate-50">
                          <td className="px-6 py-4 font-semibold text-slate-900">{user.fullName}</td>
                          <td className="px-6 py-4 text-sm text-slate-600">{user.email}</td>
                          <td className="px-6 py-4 text-sm text-slate-600">{user.roleLabel || user.role}</td>
                          <td className="px-6 py-4 text-sm text-slate-600">{user.district || user.region || "—"}</td>
                          <td className="px-6 py-4"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${(user.isActive !== false && user.status !== "Inactive") ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{(user.isActive !== false && user.status !== "Inactive") ? "Active" : "Inactive"}</span></td>
                          <td className="px-6 py-4 text-sm text-slate-500">{formatDateTime(user.lastLogin)}</td>
                          <td className="px-6 py-4">
                            <div className="flex justify-end gap-3 text-xs font-semibold">
                              <button onClick={() => void openUserDetail(user.id, "detail")} className="text-emerald-700">View</button>
                              <button onClick={() => void openUserDetail(user.id, "edit")} className="text-slate-700">Edit</button>
                              <button onClick={() => void resetPassword(user.id)} className="text-blue-700">Reset Password</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {section === "organizations" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr,0.9fr]">
          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 p-6">
              <h3 className="text-lg font-bold text-slate-900">Stakeholder Organizations</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Organization</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Type</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Contact</th>
                    <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {organizationsLoading && <tr><td colSpan={4} className="px-6 py-10 text-center text-slate-500">Loading organizations...</td></tr>}
                  {!organizationsLoading && organizations.map((org) => (
                    <tr key={org.id} className="hover:bg-slate-50">
                      <td className="px-6 py-4">
                        <p className="font-semibold text-slate-900">{org.name}</p>
                        <p className="text-xs text-slate-500">{org.address || "No address"}</p>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-600">{org.type}</td>
                      <td className="px-6 py-4 text-sm text-slate-600">
                        {org.contactPerson || "—"}
                        <div className="text-xs text-slate-400">{org.email || org.phone || "No contact details"}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex justify-end gap-3 text-xs font-semibold">
                          <button onClick={() => setOrganizationForm({
                            id: org.id,
                            name: org.name,
                            type: org.type,
                            contactPerson: org.contactPerson || "",
                            email: org.email || "",
                            phone: org.phone || "",
                            address: org.address || "",
                          })} className="text-slate-700">Edit</button>
                          <button onClick={() => void removeOrganization(org.id)} className="text-rose-700">Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-bold text-slate-900">{organizationForm.id ? "Edit Organization" : "Create Organization"}</h3>
            <form onSubmit={saveOrganization} className="mt-4 space-y-4">
              <input className="input-field" placeholder="Organization Name" value={organizationForm.name} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, name: e.target.value }))} />
              <select className="input-field" value={organizationForm.type} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, type: e.target.value as Organization["type"] }))}>
                <option value="Government">Government</option>
                <option value="International">International</option>
                <option value="NGO">NGO</option>
              </select>
              <input className="input-field" placeholder="Contact Person" value={organizationForm.contactPerson} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, contactPerson: e.target.value }))} />
              <input className="input-field" placeholder="Email" type="email" value={organizationForm.email} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, email: e.target.value }))} />
              <input className="input-field" placeholder="Phone" value={organizationForm.phone} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, phone: e.target.value }))} />
              <textarea className="input-field min-h-[120px]" placeholder="Address" value={organizationForm.address} onChange={(e) => setOrganizationForm((prev) => ({ ...prev, address: e.target.value }))} />
              <div className="flex gap-3">
                {organizationForm.id && <button type="button" onClick={() => setOrganizationForm(emptyOrganizationForm)} className="btn-secondary">Cancel</button>}
                <button type="submit" disabled={organizationSubmitting} className="btn-primary flex items-center gap-2">
                  {organizationSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                  {organizationForm.id ? "Save Organization" : "Create Organization"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {section === "system_configuration" && configuration && (
        <form onSubmit={saveConfiguration} className="space-y-6">
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <div className="card p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-900">General Settings</h3>
              <input className="input-field" value={configuration.platformName} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, platformName: e.target.value } : prev)} placeholder="Platform Name" />
              <div className="grid grid-cols-2 gap-4">
                <input className="input-field" value={configuration.countryName} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, countryName: e.target.value } : prev)} placeholder="Country" />
                <input className="input-field" value={configuration.countryCode} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, countryCode: e.target.value } : prev)} placeholder="Country Code" />
                <input className="input-field" value={configuration.defaultCurrency} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, defaultCurrency: e.target.value } : prev)} placeholder="Currency" />
                <input className="input-field" value={configuration.timezone} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, timezone: e.target.value } : prev)} placeholder="Timezone" />
              </div>
            </div>

            <div className="card p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-900">Notification Settings</h3>
              <label className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
                <span>Email notifications</span>
                <input type="checkbox" checked={configuration.emailNotificationsEnabled} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, emailNotificationsEnabled: e.target.checked } : prev)} />
              </label>
              <label className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
                <span>SMS notifications</span>
                <input type="checkbox" checked={configuration.smsNotificationsEnabled} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, smsNotificationsEnabled: e.target.checked } : prev)} />
              </label>
              <div className="grid grid-cols-2 gap-4">
                <input className="input-field" type="number" value={configuration.maxFileSizeMb} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, maxFileSizeMb: Number(e.target.value || 0) } : prev)} placeholder="Max file size" />
                <input className="input-field" value={configuration.allowedFileTypes.join("/")} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, allowedFileTypes: e.target.value.split("/").map((item) => item.trim().toUpperCase()).filter(Boolean) } : prev)} placeholder="Allowed types" />
              </div>
              <div className="rounded-xl border border-slate-100 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900">Lesotho Boundary</p>
                    <p className="text-xs text-slate-500">{configuration.lesothoBoundary?.exists ? "GeoJSON file available" : "GeoJSON file missing"}</p>
                    <p className="text-xs text-slate-400">{configuration.lesothoBoundary?.lastModified ? formatDateTime(configuration.lesothoBoundary.lastModified) : "No timestamp"}</p>
                  </div>
                  <button type="button" onClick={() => void redownloadBoundary()} className="btn-secondary text-xs">Re-download Boundary File</button>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <div className="card p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-900">KPI Thresholds</h3>
              <div className="grid grid-cols-2 gap-4">
                <input className="input-field" type="number" value={configuration.femaleTargetMinimum} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, femaleTargetMinimum: Number(e.target.value || 0) } : prev)} placeholder="Female target" />
                <input className="input-field" type="number" value={configuration.vulnerableTargetMinimum} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, vulnerableTargetMinimum: Number(e.target.value || 0) } : prev)} placeholder="Vulnerable target" />
                <input className="input-field" type="number" value={configuration.lowIncomeTargetMinimum} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, lowIncomeTargetMinimum: Number(e.target.value || 0) } : prev)} placeholder="Low income target" />
                <input className="input-field" type="number" value={configuration.uptimeTarget} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, uptimeTarget: Number(e.target.value || 0) } : prev)} placeholder="Uptime target" />
                <input className="input-field" type="number" value={configuration.anomalyDeviationThreshold} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, anomalyDeviationThreshold: Number(e.target.value || 0) } : prev)} placeholder="Anomaly deviation" />
                <input className="input-field" type="number" value={configuration.gpsDuplicateRadiusM} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, gpsDuplicateRadiusM: Number(e.target.value || 0) } : prev)} placeholder="GPS duplicate radius" />
                <input className="input-field" type="number" value={configuration.gpsVerificationMaxDistanceM} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, gpsVerificationMaxDistanceM: Number(e.target.value || 0) } : prev)} placeholder="GPS verification max distance" />
              </div>
            </div>

            <div className="card p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-900">Milestone Thresholds</h3>
              <div className="grid grid-cols-2 gap-4">
                <input className="input-field" type="number" value={configuration.m2VerificationRequiredPct} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, m2VerificationRequiredPct: Number(e.target.value || 0) } : prev)} placeholder="M2 verification required" />
                <input className="input-field" type="number" value={configuration.m3VerificationRequiredPct} onChange={(e) => setConfiguration((prev) => prev ? { ...prev, m3VerificationRequiredPct: Number(e.target.value || 0) } : prev)} placeholder="M3 verification required" />
              </div>
            </div>
          </div>

          <button type="submit" disabled={configurationSubmitting || configurationLoading} className="btn-primary flex items-center gap-2">
            {configurationSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Configuration
          </button>
        </form>
      )}

      {section === "prospect_sync" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <div className="card p-6 xl:col-span-1">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900">Connection Status</h3>
                <button onClick={() => void loadProspect()} className="btn-secondary text-xs">Check Connection</button>
              </div>
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
                  <span>Read token</span>
                  <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusPill(Boolean(connectionStatus?.readTokenOk))}`}>{connectionStatus?.readTokenOk ? "Working" : "Unavailable"}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
                  <span>Write token</span>
                  <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusPill(Boolean(connectionStatus?.writeTokenOk))}`}>{connectionStatus?.writeTokenOk ? "Working" : "Unavailable"}</span>
                </div>
                <p className="text-xs text-slate-500">{connectionStatus?.baseUrl || "No Prospect base URL configured."}</p>
              </div>
            </div>

            <div className="card p-6 xl:col-span-2">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900">Sync Summary</h3>
                <button onClick={() => void retryFailedJobs()} className="btn-secondary text-xs">Retry All Failed</button>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-2xl bg-rose-50 p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-rose-500">Failed Jobs</p>
                  <p className="mt-3 text-3xl font-bold text-rose-700">{prospectSummary?.failedJobs ?? 0}</p>
                </div>
                <div className="rounded-2xl bg-blue-50 p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-blue-500">Last Sync</p>
                  <p className="mt-3 text-lg font-bold text-slate-900">{formatRelativeTime(prospectSummary?.lastSyncAt)}</p>
                  <p className="text-xs text-slate-500">{formatDateTime(prospectSummary?.lastSyncAt)}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 p-6"><h3 className="text-lg font-bold text-slate-900">Counts Comparison</h3></div>
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Data Type</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Our Count</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Prospect Count</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Match</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Last Sync</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(prospectSummary?.rows || []).map((row) => (
                  <tr key={row.dataType}>
                    <td className="px-6 py-4 font-semibold text-slate-900">{row.dataType}<div className="text-xs text-slate-500">{row.note}</div></td>
                    <td className="px-6 py-4 text-sm text-slate-600">{row.ourCount}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{row.prospectCount}</td>
                    <td className="px-6 py-4"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${row.match ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{row.match ? "Match" : "Mismatch"}</span></td>
                    <td className="px-6 py-4 text-sm text-slate-500">{formatDateTime(row.lastSync)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card overflow-hidden">
            <div className="border-b border-slate-100 p-6"><h3 className="text-lg font-bold text-slate-900">Failed Jobs and Recent Sync Logs</h3></div>
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Method</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Record</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Attempts</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Status</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Error</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {prospectLoading && <tr><td colSpan={6} className="px-6 py-10 text-center text-slate-500">Loading sync logs...</td></tr>}
                {!prospectLoading && prospectLogs.map((log) => {
                  const isExpanded = expandedPayloadLogId === log.id;
                  return (
                    <React.Fragment key={log.id}>
                      <tr>
                        <td className="px-6 py-4 font-semibold text-slate-900">{log.methodName}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{log.recordType || "—"} {log.recordId || ""}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{log.attempts}</td>
                        <td className="px-6 py-4"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${log.status === "success" ? "bg-emerald-100 text-emerald-700" : log.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{log.status}</span></td>
                        <td className="px-6 py-4 text-xs text-slate-500">{log.errorMessage || "—"}</td>
                        <td className="px-6 py-4">
                          <div className="flex justify-end gap-3">
                            <button
                              onClick={() => setExpandedPayloadLogId((current) => current === log.id ? null : log.id)}
                              className="inline-flex items-center gap-2 text-xs font-semibold text-emerald-700"
                            >
                              <Eye size={14} />
                              {isExpanded ? "Hide payload" : "View payload"}
                            </button>
                            {log.status === "failed" && <button onClick={() => void retryJob(log.id)} className="text-xs font-semibold text-emerald-700">Retry</button>}
                          </div>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-slate-50/70">
                          <td colSpan={6} className="px-6 pb-6 pt-1">
                            <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                              <div className="border-b border-slate-100 px-4 py-3">
                                <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Sent/Post Data Structure</p>
                                <p className="mt-1 text-xs text-slate-500">{log.methodName} payload captured for this sync job.</p>
                              </div>
                              <pre className="max-h-[32rem] overflow-auto rounded-b-2xl bg-slate-950/95 p-5 text-[12px] leading-6 text-slate-100 whitespace-pre-wrap break-words">
                                {formatJsonBlock(log.payload)}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {section === "audit_logs" && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <input className="input-field" placeholder="Actor" value={auditFilters.actor} onChange={(e) => setAuditFilters((prev) => ({ ...prev, actor: e.target.value }))} />
              <input className="input-field" placeholder="Role" value={auditFilters.actorRole} onChange={(e) => setAuditFilters((prev) => ({ ...prev, actorRole: e.target.value }))} />
              <input className="input-field" placeholder="Action" value={auditFilters.action} onChange={(e) => setAuditFilters((prev) => ({ ...prev, action: e.target.value }))} />
              <input className="input-field" placeholder="Module" value={auditFilters.module} onChange={(e) => setAuditFilters((prev) => ({ ...prev, module: e.target.value }))} />
              <input className="input-field" type="date" value={auditFilters.dateFrom} onChange={(e) => setAuditFilters((prev) => ({ ...prev, dateFrom: e.target.value }))} />
              <input className="input-field" type="date" value={auditFilters.dateTo} onChange={(e) => setAuditFilters((prev) => ({ ...prev, dateTo: e.target.value }))} />
              <input className="input-field" placeholder="Record ID" value={auditFilters.recordId} onChange={(e) => setAuditFilters((prev) => ({ ...prev, recordId: e.target.value }))} />
              <div className="flex gap-3">
                <button onClick={() => void loadAudit()} className="btn-primary flex-1">Apply</button>
                <button onClick={() => void exportAudit("csv")} className="btn-secondary flex items-center gap-2"><Download size={14} /> CSV</button>
                <button onClick={() => void exportAudit("pdf")} className="btn-secondary flex items-center gap-2"><Download size={14} /> PDF</button>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Timestamp</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Actor</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Role</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Action</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Module</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Record</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Old Status</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">New Status</th>
                  <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {auditLoading && <tr><td colSpan={9} className="px-6 py-10 text-center text-slate-500">Loading audit logs...</td></tr>}
                {!auditLoading && auditLogs.map((log) => (
                  <tr key={log.id}>
                    <td className="px-6 py-4 text-sm text-slate-500">{formatDateTime(log.createdAt)}</td>
                    <td className="px-6 py-4 text-sm text-slate-700">{log.actor || "System"}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.actorRole || "—"}</td>
                    <td className="px-6 py-4 font-semibold text-slate-900">{log.action}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.module || "—"}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.entityId || log.recordId || "—"}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.oldStatus || "—"}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.newStatus || "—"}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">{log.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {section === "notifications" && (
        <div className="card overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Recipient</th>
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Channel</th>
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Event</th>
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Status</th>
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500">Timestamp</th>
                <th className="px-6 py-4 text-xs font-bold uppercase text-slate-500 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visibleNotifications.map((note) => (
                <tr key={note.id} className="hover:bg-slate-50">
                  <td className="px-6 py-4">
                    <p className="font-semibold text-slate-900">{note.recipientName}</p>
                    <p className="text-xs text-slate-400">{note.recipientId}</p>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-600">{note.type}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{note.event}</td>
                  <td className="px-6 py-4"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${toneForNotification(note.status)}`}>{note.status}</span></td>
                  <td className="px-6 py-4 text-sm text-slate-500">{formatDateTime(note.timestamp)}</td>
                  <td className="px-6 py-4">
                    <div className="flex justify-end">
                      <button onClick={() => onNotificationSelect?.(note)} className="text-xs font-semibold text-emerald-700">Open Linked Item</button>
                    </div>
                  </td>
                </tr>
              ))}
              {visibleNotifications.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-10 text-center text-slate-500">No notifications available.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {section === "system_health" && (
        <div className="space-y-6">
          {healthLoading || !health ? (
            <div className="card p-10 text-center text-slate-500">Loading system health...</div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                <div className="card p-6">
                  <h3 className="text-lg font-bold text-slate-900">Database</h3>
                  <div className="mt-4 space-y-3 text-sm text-slate-600">
                    <div className="flex items-center justify-between"><span>Connection status</span><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusPill(health.database.status === "Connected")}`}>{health.database.status}</span></div>
                    <div className="flex items-center justify-between"><span>Slow queries (24h)</span><span>{health.database.slowQueriesLast24h}</span></div>
                    {Object.entries(health.database.tableSizes).map(([name, size]) => (
                      <div key={name} className="flex items-center justify-between"><span>{name}</span><span>{size}</span></div>
                    ))}
                  </div>
                </div>

                <div className="card p-6">
                  <h3 className="text-lg font-bold text-slate-900">Queue</h3>
                  <div className="mt-4 space-y-3 text-sm text-slate-600">
                    <div className="flex items-center justify-between"><span>Worker status</span><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusPill(health.queue.workerStatus === "Running")}`}>{health.queue.workerStatus}</span></div>
                    <div className="flex items-center justify-between"><span>Pending jobs</span><span>{health.queue.pendingJobsCount}</span></div>
                    <div className="flex items-center justify-between"><span>Failed jobs</span><span>{health.queue.failedJobsCount}</span></div>
                    <div className="flex items-center justify-between"><span>Processing rate</span><span>{health.queue.processingRateLast24h}/24h</span></div>
                  </div>
                </div>

                <div className="card p-6">
                  <h3 className="text-lg font-bold text-slate-900">Storage</h3>
                  <div className="mt-4 space-y-3 text-sm text-slate-600">
                    <div className="flex items-center justify-between"><span>Total</span><span>{formatBytes(health.storage.totalBytes)}</span></div>
                    <div className="flex items-center justify-between"><span>Used</span><span>{formatBytes(health.storage.usedBytes)}</span></div>
                    <div className="flex items-center justify-between"><span>Available</span><span>{formatBytes(health.storage.freeBytes)}</span></div>
                    <div className="flex items-center justify-between"><span>Files uploaded today</span><span>{health.storage.filesUploadedToday}</span></div>
                  </div>
                </div>
              </div>

              <div className="card p-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-bold text-slate-900">Recent Application Errors</h3>
                  <span className="text-xs text-slate-400">Latest failed Prospect-related events</span>
                </div>
                <div className="mt-4 space-y-3">
                  {health.errors.map((item) => (
                    <div key={item.id} className="rounded-xl border border-slate-100 px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-semibold text-slate-900">{item.methodName}</p>
                        <span className="text-xs text-slate-400">{formatDateTime(item.updatedAt)}</span>
                      </div>
                      <p className="mt-2 text-xs text-rose-600">{item.errorMessage || "Unknown error"}</p>
                    </div>
                  ))}
                  {health.errors.length === 0 && <p className="text-sm text-slate-500">No recent errors logged.</p>}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
