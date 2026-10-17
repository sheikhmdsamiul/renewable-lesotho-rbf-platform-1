import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  ArchiveRestore,
  Bell,
  BellOff,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Copy,
  CreditCard,
  ExternalLink,
  FileText,
  FolderKanban,
  Gavel,
  Info,
  Loader2,
  Mail,
  MailOpen,
  Megaphone,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import {
  archiveNotification,
  bulkNotificationAction,
  deleteNotification,
  fetchNotificationPage,
  markAllNotificationsRead,
  markNotificationRead,
  markNotificationUnread,
  unarchiveNotification,
} from "../api";
import { Notification, NotificationCategory, UserRole } from "../types";

// ---------------------------------------------------------------------------------------------
// Where a notification leads, per role
// ---------------------------------------------------------------------------------------------

export interface NotificationTarget {
  /** Sidebar tab to open. */
  tab: string;
  /** Button label, e.g. "Open Payment Claims". */
  label: string;
  projectId?: string;
  /** Tab inside the project page. */
  projectTab?: string;
  /** Open this tender's detail page (staff tender screens). */
  tenderId?: string;
}

type ProjectArea = "overview" | "payments" | "milestones" | "installations" | "anomalies" | "readings";

const PROJECT_HUB_TAB: Partial<Record<UserRole, string>> = {
  [UserRole.VENDOR]: "projects_hub",
  [UserRole.RBF_OFFICIAL]: "rbf_projects",
  [UserRole.ADMIN]: "rbf_projects",
  [UserRole.UNDP_DONOR]: "portfolio",
  [UserRole.DOE_OFFICER]: "projects",
  [UserRole.TAC]: "projects",
  [UserRole.AUDITOR]: "projects",
};

// Each role sees a different set of tabs on a project page (see ProjectsHub in App.tsx).
function projectTabFor(role: UserRole, area: ProjectArea): string {
  if (role === UserRole.VENDOR) {
    return { overview: "overview", payments: "payments", milestones: "milestones", installations: "fieldwork", anomalies: "anomaly_flags", readings: "device_readings" }[area];
  }
  if (role === UserRole.UNDP_DONOR) {
    return { overview: "summary", payments: "milestone_payments", milestones: "milestone_payments", installations: "summary", anomalies: "summary", readings: "device_readings" }[area];
  }
  const hasPayments = role === UserRole.RBF_OFFICIAL || role === UserRole.ADMIN || role === UserRole.AUDITOR;
  return {
    overview: "overview",
    payments: hasPayments ? "payments" : "overview",
    milestones: "milestones",
    installations: "installations",
    anomalies: "anomaly_flags",
    readings: "device_readings",
  }[area];
}

const PROJECT_AREA_LABEL: Record<ProjectArea, string> = {
  overview: "",
  payments: " → Payments",
  milestones: " → Milestones",
  installations: " → Installations",
  anomalies: " → Anomaly Flags",
  readings: " → Device Readings",
};

/**
 * The screen a notification should open for the given role, or null when nothing more useful
 * than the message itself exists. `canOpen(tab)` says whether the user may open a sidebar tab.
 */
export function resolveNotificationTarget(
  note: Notification,
  role: UserRole | undefined,
  canOpen: (tab: string) => boolean,
): NotificationTarget | null {
  if (!role) return null;
  const event = note.event || "";
  const { projectId, projectLabel, tenderId } = note.related;
  const is = (...prefixes: string[]) => prefixes.some((p) => event.startsWith(p));
  const staff = role === UserRole.RBF_OFFICIAL || role === UserRole.ADMIN;

  const page = (tab: string, label: string): NotificationTarget | null => (canOpen(tab) ? { tab, label } : null);
  const project = (area: ProjectArea): NotificationTarget | null => {
    const hub = PROJECT_HUB_TAB[role];
    if (!projectId || !hub || !canOpen(hub)) return null;
    return {
      tab: hub,
      projectId,
      projectTab: projectTabFor(role, area),
      label: `Open project ${projectLabel || projectId}${PROJECT_AREA_LABEL[area]}`,
    };
  };
  const first = (...options: Array<NotificationTarget | null>) => options.find(Boolean) || null;

  switch (note.category as NotificationCategory) {
    case "payments": {
      if (is("milestone_claimable")) return first(project("payments"));
      if (is("milestone_")) return first(project("milestones"));
      if (role === UserRole.VENDOR) return first(page("claims", "Open Payment Claims"), project("payments"));
      if (staff) return first(page("payments", role === UserRole.ADMIN ? "Open Payments" : "Open Disbursements"), project("payments"));
      if (role === UserRole.TAC) return first(page("payments", "Open Claim Reviews"));
      if (role === UserRole.UNDP_DONOR) return first(page("payments", "Open Disbursements"), project("payments"));
      if (role === UserRole.AUDITOR) return first(page("claims_audit", "Open Disbursement Audit"));
      return first(project("overview"));
    }
    case "verification": {
      if (role === UserRole.FIELD_VERIFIER) return page("inspections", "Open Verifications");
      if (role === UserRole.DOE_OFFICER) return first(page("doe_verification", "Open Field Verification"), project("installations"));
      if (role === UserRole.UNDP_DONOR) return first(page("verification_summary", "Open Verification Summary"));
      if (role === UserRole.AUDITOR) return first(page("verification_audit", "Open Verification Audit"));
      return first(project("installations"));
    }
    case "data": {
      if (is("anomaly_")) {
        if (role === UserRole.AUDITOR) return first(page("anomaly_report", "Open Anomalies"), project("anomalies"));
        return first(project("anomalies"));
      }
      return first(project("readings"));
    }
    case "oversight": {
      if (is("audit_")) {
        if (role === UserRole.AUDITOR) return first(page("audit_cases", "Open Audit Cases"));
        if (role === UserRole.UNDP_DONOR) return first(page("audit_findings", "Open Audit Findings"));
        return first(page("audit_oversight", "Open Audit & Oversight → Audit Findings"), project("overview"));
      }
      if (role === UserRole.DOE_OFFICER) return first(page("oversight_issues", "Open Verification / Monitoring Issues"), project("overview"));
      if (role === UserRole.UNDP_DONOR) return first(page("oversight_flagged", "Open Flagged Issues"), project("overview"));
      return first(page("audit_oversight", "Open Audit & Oversight → Oversight Follow-ups"), project("overview"));
    }
    case "projects":
      return first(project("overview"), PROJECT_HUB_TAB[role] ? page(PROJECT_HUB_TAB[role] as string, "Open Projects") : null);
    case "reports":
      return page("reports", "Open Reports");
    case "procurement": {
      if (role === UserRole.VENDOR) {
        if (is("tender_published")) return page("tenders", "Open Published Tenders");
        if (is("contract_")) return page("contracting", "Open Contracting");
        if (is("eoi_")) return page("eoi_invites", "Open EOI Invites");
        return first(page("my_bids", "Open My Bids"), page("tenders", "Open Published Tenders"));
      }
      if (role === UserRole.ADMIN && is("intent_to_award_approval_requested")) {
        return first(page("intent_award_approvals", "Open Intent to Award Approvals"));
      }
      if (is("evaluation_")) return first(page("evaluations", "Open Evaluations"));
      if (staff) {
        if (tenderId && canOpen("tenders")) return { tab: "tenders", tenderId, label: `Open tender ${note.related.tenderLabel || tenderId}` };
        return page("tenders", "Open Tender Management");
      }
      if (role === UserRole.UNDP_DONOR) {
        return is("contract_") ? page("contracts_oversight", "Open Awards & Contracts") : page("tenders_active", "Open Active Tenders");
      }
      if (role === UserRole.AUDITOR) return page("procurement_audit", "Open Procurement Audit");
      return null;
    }
    case "compliance":
      if (is("prequalification_")) return page("prequal", "Open Pre-Qualification");
      return page("blacklisting", role === UserRole.UNDP_DONOR ? "Open Vendor Compliance" : "Open Blacklisting");
    case "notices":
      return staff ? page("notice_board", "Open Notice Board") : null;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------------------------
// Presentation helpers
// ---------------------------------------------------------------------------------------------

const CATEGORY_META: Record<NotificationCategory, { icon: React.ElementType; tone: string }> = {
  payments: { icon: CreditCard, tone: "bg-emerald-100 text-emerald-700" },
  verification: { icon: ClipboardCheck, tone: "bg-blue-100 text-blue-700" },
  data: { icon: Activity, tone: "bg-amber-100 text-amber-700" },
  oversight: { icon: ShieldCheck, tone: "bg-violet-100 text-violet-700" },
  projects: { icon: FolderKanban, tone: "bg-sky-100 text-sky-700" },
  reports: { icon: FileText, tone: "bg-slate-100 text-slate-700" },
  procurement: { icon: Gavel, tone: "bg-indigo-100 text-indigo-700" },
  compliance: { icon: AlertTriangle, tone: "bg-rose-100 text-rose-700" },
  notices: { icon: Megaphone, tone: "bg-teal-100 text-teal-700" },
  general: { icon: Info, tone: "bg-slate-100 text-slate-600" },
};

export const NOTIFICATION_CATEGORIES: { value: NotificationCategory; label: string }[] = [
  { value: "payments", label: "Payments" },
  { value: "verification", label: "Field verification" },
  { value: "data", label: "Meter data & anomalies" },
  { value: "oversight", label: "Oversight & audit" },
  { value: "projects", label: "Projects" },
  { value: "procurement", label: "Procurement" },
  { value: "compliance", label: "Compliance" },
  { value: "reports", label: "Reports" },
  { value: "notices", label: "Notices" },
  { value: "general", label: "General" },
];

// Two-line preview; set inline because this Tailwind build has no line-clamp utility.
const clamp2: React.CSSProperties = { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" };

export function relativeTime(iso: string, now = Date.now()): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "";
  const seconds = Math.round((now - time) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fullTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function CategoryIcon({ note, size = 16 }: { note: Notification; size?: number }) {
  const meta = CATEGORY_META[note.category] || CATEGORY_META.general;
  const Icon = meta.icon;
  return (
    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${meta.tone}`} aria-hidden="true">
      <Icon size={size} />
    </span>
  );
}

function PriorityBadge({ note }: { note: Notification }) {
  if (note.priority !== "high") return null;
  return <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-rose-700">Action needed</span>;
}

// ---------------------------------------------------------------------------------------------
// Header bell panel
// ---------------------------------------------------------------------------------------------

export function NotificationBellPanel({
  notifications,
  unreadCount,
  highPriorityCount,
  loading,
  error,
  onOpen,
  onMarkAllRead,
  onViewAll,
  onClose,
  browserPushEnabled,
  browserPushSupported,
  onToggleBrowserPush,
}: {
  notifications: Notification[];
  unreadCount: number;
  highPriorityCount: number;
  loading: boolean;
  error: string | null;
  onOpen: (note: Notification) => void;
  onMarkAllRead: () => void;
  onViewAll: () => void;
  onClose: () => void;
  browserPushEnabled: boolean;
  browserPushSupported: boolean;
  onToggleBrowserPush: () => void;
}) {
  const [view, setView] = useState<"all" | "unread">("all");
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointer = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (!panelRef.current || !target) return;
      if (panelRef.current.contains(target) || target.closest("[data-notification-bell]")) return;
      onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [onClose]);

  const shown = (view === "unread" ? notifications.filter((n) => !n.isRead) : notifications).slice(0, 20);

  return (
    <div
      ref={panelRef}
      tabIndex={-1}
      role="dialog"
      aria-label="Notifications"
      className="absolute right-2 top-16 z-[100] w-[min(26rem,calc(100vw-1rem))] overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-2xl outline-none sm:right-8"
    >
      <div className="border-b border-slate-100 px-5 pb-3 pt-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-bold text-slate-900">Notifications</h3>
            <p className="text-xs text-slate-500">
              {unreadCount > 0 ? `${unreadCount} unread` : "You're all caught up"}
              {highPriorityCount > 0 && <span className="font-semibold text-rose-600"> &middot; {highPriorityCount} need action</span>}
            </p>
          </div>
          <div className="flex items-center gap-1">
            {unreadCount > 0 && (
              <button type="button" onClick={onMarkAllRead} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50">
                <CheckCheck size={14} /> Mark all read
              </button>
            )}
            <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close notifications">
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div className="inline-flex rounded-xl bg-slate-100 p-0.5 text-xs font-semibold" role="tablist">
            {(["all", "unread"] as const).map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={view === v}
                onClick={() => setView(v)}
                className={`rounded-lg px-3 py-1 ${view === v ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
              >
                {v === "all" ? "All" : `Unread${unreadCount ? ` (${unreadCount})` : ""}`}
              </button>
            ))}
          </div>
          {browserPushSupported && (
            <button
              type="button"
              onClick={onToggleBrowserPush}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-slate-500 hover:bg-slate-100"
              title="Show desktop alerts while this tab is in the background"
            >
              {browserPushEnabled ? <Bell size={13} /> : <BellOff size={13} />} Desktop alerts {browserPushEnabled ? "on" : "off"}
            </button>
          )}
        </div>
      </div>

      <div className="max-h-[min(28rem,60vh)] overflow-y-auto">
        {error && <p className="m-4 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
        {loading && notifications.length === 0 ? (
          <div className="flex items-center justify-center gap-2 p-8 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Loading&hellip;</div>
        ) : shown.length === 0 ? (
          <div className="p-8 text-center">
            <Bell size={28} className="mx-auto text-slate-300" />
            <p className="mt-2 text-sm font-medium text-slate-600">{view === "unread" ? "No unread notifications" : "No notifications yet"}</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-50">
            {shown.map((note) => (
              <li key={note.id}>
                <button
                  type="button"
                  onClick={() => onOpen(note)}
                  className={`flex w-full gap-3 px-5 py-3 text-left transition hover:bg-slate-50 focus:bg-slate-50 focus:outline-none ${note.isRead ? "" : "bg-emerald-50/40"}`}
                >
                  <CategoryIcon note={note} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-start gap-2">
                      <span style={clamp2} className={`flex-1 text-sm ${note.isRead ? "font-medium text-slate-700" : "font-bold text-slate-900"}`}>{note.title}</span>
                      {!note.isRead && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-emerald-500" aria-label="Unread" />}
                    </span>
                    <span style={clamp2} className="mt-0.5 text-xs text-slate-500">{note.body}</span>
                    <span className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
                      <time dateTime={note.timestamp} title={fullTime(note.timestamp)}>{relativeTime(note.timestamp)}</time>
                      <span>&middot; {note.categoryLabel}</span>
                      <PriorityBadge note={note} />
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-slate-100 bg-slate-50 p-3">
        <button type="button" onClick={onViewAll} className="w-full rounded-xl py-2 text-sm font-semibold text-slate-700 hover:bg-white">
          View all notifications
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Full message window
// ---------------------------------------------------------------------------------------------

export function NotificationDetailModal({
  note,
  target,
  busy,
  error,
  position,
  readOnly = false,
  onClose,
  onOpenTarget,
  onToggleRead,
  onToggleArchive,
  onDelete,
  onPrev,
  onNext,
}: {
  note: Notification;
  target: NotificationTarget | null;
  busy?: boolean;
  error?: string | null;
  position?: { index: number; total: number };
  /** Someone else's notification (administrator delivery log): no state changes. */
  readOnly?: boolean;
  onClose: () => void;
  onOpenTarget: () => void;
  onToggleRead: () => void;
  onToggleArchive: () => void;
  onDelete: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setConfirmDelete(false);
    setCopied(false);
  }, [note.id]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft" && onPrev) onPrev();
      if (event.key === "ArrowRight" && onNext) onNext();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, onPrev, onNext]);

  const copy = async () => {
    const text = `${note.title}\n${fullTime(note.timestamp)}\n\n${note.body}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const related = note.related;
  const showProject = related.projectLabel && !(related.type === "project");

  return (
    <div className="fixed inset-0 z-[1100] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-detail-title"
        className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b border-slate-100 px-6 py-5">
          <CategoryIcon note={note} size={18} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold text-slate-500">{note.categoryLabel}</span>
              <PriorityBadge note={note} />
              {!note.isRead && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700">Unread</span>}
              {note.archivedAt && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-600">Archived</span>}
            </div>
            <h2 id="notification-detail-title" className="mt-1 break-words text-lg font-bold leading-snug text-slate-900">{note.title}</h2>
            <p className="mt-1 text-xs text-slate-500">
              <time dateTime={note.timestamp}>{fullTime(note.timestamp)}</time> ({relativeTime(note.timestamp)})
            </p>
          </div>
          <div className="flex items-center gap-1">
            {position && position.total > 1 && (
              <>
                <button type="button" onClick={onPrev} disabled={!onPrev} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 disabled:opacity-30" aria-label="Previous notification"><ChevronLeft size={18} /></button>
                <span className="text-xs tabular-nums text-slate-400">{position.index + 1}/{position.total}</span>
                <button type="button" onClick={onNext} disabled={!onNext} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 disabled:opacity-30" aria-label="Next notification"><ChevronRight size={18} /></button>
              </>
            )}
            <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-800">{note.body || "No further details."}</p>

          {(related.label || showProject || related.tenderLabel) && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Related record</p>
              <dl className="mt-2 grid gap-1 sm:grid-cols-[8rem_1fr]">
                {related.label && (<><dt className="text-slate-500">Record</dt><dd className="font-medium text-slate-800">{related.label}</dd></>)}
                {showProject && (<><dt className="text-slate-500">Project</dt><dd className="font-medium text-slate-800">{related.projectLabel}</dd></>)}
                {related.tenderLabel && related.type !== "tender" && (<><dt className="text-slate-500">Tender</dt><dd className="font-medium text-slate-800">{related.tenderLabel}</dd></>)}
              </dl>
            </div>
          )}

          {readOnly && (
            <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Sent to {note.recipientName || note.recipientId} &middot; {note.isRead ? `read ${note.readAt ? fullTime(note.readAt) : ""}` : "not yet read"}
            </p>
          )}
          {!target && !readOnly && (
            <p className="flex items-start gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <Info size={14} className="mt-0.5 shrink-0" /> This message has no linked screen for your role; everything you need is above.
            </p>
          )}
          {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        </div>

        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {!readOnly && (<>
            <button type="button" onClick={onToggleRead} disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50">
              {note.isRead ? <><Mail size={14} /> Mark as unread</> : <><MailOpen size={14} /> Mark as read</>}
            </button>
            <button type="button" onClick={onToggleArchive} disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50">
              {note.archivedAt ? <><ArchiveRestore size={14} /> Move to inbox</> : <><Archive size={14} /> Archive</>}
            </button>
            </>)}
            <button type="button" onClick={() => void copy()} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100">
              <Copy size={14} /> {copied ? "Copied" : "Copy text"}
            </button>
            {readOnly ? null : confirmDelete ? (
              <span className="inline-flex items-center gap-1.5 rounded-xl border border-rose-200 bg-white px-2 py-1 text-xs">
                <span className="text-rose-700">Delete permanently?</span>
                <button type="button" onClick={onDelete} disabled={busy} className="rounded-lg bg-rose-600 px-2 py-1 font-semibold text-white hover:bg-rose-700">Delete</button>
                <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-lg px-2 py-1 font-semibold text-slate-600 hover:bg-slate-100">Keep</button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmDelete(true)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50">
                <Trash2 size={14} /> Delete
              </button>
            )}
          </div>
          {target && (
            <button type="button" onClick={onOpenTarget} className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700">
              <ExternalLink size={16} /> {target.label}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Shared state handling for the detail window
// ---------------------------------------------------------------------------------------------

/** Runs one detail-window action against the API and reports the updated (or deleted) row. */
export function useNotificationActions(onChanged: (note: Notification | null, removedId?: string) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (fn: () => Promise<Notification | null>, removedId?: string) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await fn();
      onChanged(updated, removedId);
      return true;
    } catch {
      setError("That didn't work. Check your connection and try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }, [onChanged]);
  return {
    busy,
    error,
    clearError: () => setError(null),
    toggleRead: (note: Notification) => run(() => (note.isRead ? markNotificationUnread(note.id) : markNotificationRead(note.id))),
    toggleArchive: (note: Notification) => run(() => (note.archivedAt ? unarchiveNotification(note.id) : archiveNotification(note.id))),
    remove: (note: Notification) => run(async () => { await deleteNotification(note.id); return null; }, note.id),
    markRead: (note: Notification) => (note.isRead ? Promise.resolve(true) : run(() => markNotificationRead(note.id))),
  };
}

// ---------------------------------------------------------------------------------------------
// Notifications page (every role)
// ---------------------------------------------------------------------------------------------

type Box = "inbox" | "unread" | "archived" | "all_users";

export function NotificationsPage({
  role,
  title = "Notifications",
  resolveTarget,
  onOpenTarget,
  onChanged,
}: {
  role: UserRole | undefined;
  title?: string;
  resolveTarget: (note: Notification) => NotificationTarget | null;
  onOpenTarget: (target: NotificationTarget) => void;
  /** Called after anything that changes read/unread counts, so the header bell can refresh. */
  onChanged: () => void;
}) {
  const isAdmin = role === UserRole.ADMIN;
  const [box, setBox] = useState<Box>("inbox");
  const [category, setCategory] = useState("");
  const [highPriority, setHighPriority] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<Notification[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const readOnly = box === "all_users";

  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(id);
  }, [searchInput]);

  const query = useMemo(() => ({
    unread: box === "unread",
    archived: box === "archived",
    allUsers: box === "all_users",
    category: category || undefined,
    highPriority,
    search,
  }), [box, category, highPriority, search]);

  const load = useCallback(async (nextPage: number) => {
    if (nextPage === 1) setLoading(true); else setLoadingMore(true);
    setError(null);
    try {
      const data = await fetchNotificationPage({ ...query, page: nextPage });
      setRows((prev) => (nextPage === 1 ? data.results : [...prev, ...data.results]));
      setCount(data.count);
      setHasMore(data.hasMore);
      setPage(nextPage);
      if (nextPage === 1) setSelected(new Set());
    } catch {
      setError("Notifications could not be loaded. Check your connection and try again.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [query]);

  useEffect(() => {
    void load(1);
  }, [load]);

  const applyChange = useCallback((updated: Notification | null, removedId?: string) => {
    setRows((prev) => {
      if (removedId) return prev.filter((n) => n.id !== removedId);
      if (!updated) return prev;
      const leavesView =
        (box === "inbox" && Boolean(updated.archivedAt)) ||
        (box === "archived" && !updated.archivedAt);
      return leavesView ? prev.filter((n) => n.id !== updated.id) : prev.map((n) => (n.id === updated.id ? updated : n));
    });
    if (removedId) setCount((c) => Math.max(0, c - 1));
    onChanged();
  }, [box, onChanged]);
  const actions = useNotificationActions(applyChange);

  const openIndex = openId ? rows.findIndex((n) => n.id === openId) : -1;
  const openNote = openIndex >= 0 ? rows[openIndex] : null;
  const openNoteAt = (index: number) => {
    const note = rows[index];
    if (!note) return;
    setOpenId(note.id);
    actions.clearError();
    if (!readOnly && !note.isRead) void actions.markRead(note);
  };

  const toggleSelected = (id: string) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const allSelected = rows.length > 0 && rows.every((n) => selected.has(n.id));

  const runBulk = async (action: "read" | "unread" | "archive" | "unarchive" | "delete") => {
    if (selected.size === 0) return;
    if (action === "delete" && !window.confirm(`Delete ${selected.size} notification(s) permanently?`)) return;
    setBulkBusy(true);
    setError(null);
    try {
      await bulkNotificationAction([...selected], action);
      await load(1);
      onChanged();
    } catch {
      setError("The action could not be completed. Try again.");
    } finally {
      setBulkBusy(false);
    }
  };

  const markAll = async () => {
    setBulkBusy(true);
    try {
      await markAllNotificationsRead();
      await load(1);
      onChanged();
    } catch {
      setError("Could not mark notifications as read. Try again.");
    } finally {
      setBulkBusy(false);
    }
  };

  const boxes: { value: Box; label: string }[] = [
    { value: "inbox", label: "Inbox" },
    { value: "unread", label: "Unread" },
    { value: "archived", label: "Archived" },
    ...(isAdmin ? [{ value: "all_users" as Box, label: "All users (delivery log)" }] : []),
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-500">
            {readOnly
              ? "Every notification the platform has sent, to any user. Read-only."
              : "Messages about your work on the platform. Open one to read it in full and go to the related record."}
          </p>
        </div>
        {!readOnly && (
          <button type="button" onClick={() => void markAll()} disabled={bulkBusy} className="inline-flex items-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            <CheckCheck size={16} /> Mark all as read
          </button>
        )}
      </div>

      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Notification folders">
          {boxes.map((b) => (
            <button
              key={b.value}
              type="button"
              role="tab"
              aria-selected={box === b.value}
              onClick={() => { setBox(b.value); setOpenId(null); }}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold ${box === b.value ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            >
              {b.label}
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <label className="relative flex-1">
            <span className="sr-only">Search notifications</span>
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input-field w-full pl-9"
              placeholder={readOnly ? "Search title, message, event or recipient" : "Search title or message"}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </label>
          <select className="input-field md:w-56" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filter by category">
            <option value="">All categories</option>
            {NOTIFICATION_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <label className="inline-flex items-center gap-2 whitespace-nowrap text-sm text-slate-600">
            <input type="checkbox" checked={highPriority} onChange={(e) => setHighPriority(e.target.checked)} /> Needs action only
          </label>
        </div>
      </div>

      {!readOnly && selected.size > 0 && (
        <div className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm">
          <span className="font-semibold text-emerald-900">{selected.size} selected</span>
          <button type="button" disabled={bulkBusy} onClick={() => void runBulk("read")} className="rounded-lg px-2 py-1 font-semibold text-emerald-800 hover:bg-white">Mark read</button>
          <button type="button" disabled={bulkBusy} onClick={() => void runBulk("unread")} className="rounded-lg px-2 py-1 font-semibold text-emerald-800 hover:bg-white">Mark unread</button>
          {box === "archived"
            ? <button type="button" disabled={bulkBusy} onClick={() => void runBulk("unarchive")} className="rounded-lg px-2 py-1 font-semibold text-emerald-800 hover:bg-white">Move to inbox</button>
            : <button type="button" disabled={bulkBusy} onClick={() => void runBulk("archive")} className="rounded-lg px-2 py-1 font-semibold text-emerald-800 hover:bg-white">Archive</button>}
          <button type="button" disabled={bulkBusy} onClick={() => void runBulk("delete")} className="rounded-lg px-2 py-1 font-semibold text-rose-700 hover:bg-white">Delete</button>
          <button type="button" onClick={() => setSelected(new Set())} className="ml-auto rounded-lg px-2 py-1 text-slate-600 hover:bg-white">Clear</button>
        </div>
      )}

      {error && (
        <div className="flex items-center justify-between rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <span>{error}</span>
          <button type="button" onClick={() => void load(1)} className="font-semibold underline">Retry</button>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {!readOnly && rows.length > 0 && (
          <label className="flex items-center gap-3 border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">
            <input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((n) => n.id)))} aria-label="Select all shown" />
            {count} notification{count === 1 ? "" : "s"}
          </label>
        )}
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-12 text-sm text-slate-500"><Loader2 size={18} className="animate-spin" /> Loading notifications&hellip;</div>
        ) : rows.length === 0 ? (
          <div className="p-12 text-center">
            <Bell size={32} className="mx-auto text-slate-300" />
            <p className="mt-3 font-medium text-slate-700">
              {box === "unread" ? "No unread notifications" : box === "archived" ? "Nothing archived" : search || category || highPriority ? "No notifications match these filters" : "No notifications yet"}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {box === "archived" ? "Archive notifications you have dealt with to keep your inbox short." : "New messages about your projects, claims and reviews will appear here."}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map((note, index) => (
              <li key={note.id} className={`flex items-start gap-3 px-4 py-3 ${note.isRead ? "" : "bg-emerald-50/40"}`}>
                {!readOnly && (
                  <input
                    type="checkbox"
                    className="mt-3"
                    checked={selected.has(note.id)}
                    onChange={() => toggleSelected(note.id)}
                    aria-label={`Select "${note.title}"`}
                  />
                )}
                <button type="button" onClick={() => openNoteAt(index)} className="flex min-w-0 flex-1 gap-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 rounded-xl">
                  <CategoryIcon note={note} />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className={`text-sm ${note.isRead ? "font-medium text-slate-700" : "font-bold text-slate-900"}`}>{note.title}</span>
                      {!note.isRead && <span className="h-2 w-2 rounded-full bg-emerald-500" aria-label="Unread" />}
                      <PriorityBadge note={note} />
                    </span>
                    <span style={clamp2} className="mt-0.5 text-sm text-slate-500">{note.body}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-400">
                      <time dateTime={note.timestamp} title={fullTime(note.timestamp)}>{relativeTime(note.timestamp)}</time>
                      <span>&middot; {note.categoryLabel}</span>
                      {note.related.projectLabel && <span>&middot; {note.related.projectLabel}</span>}
                      {readOnly && <span>&middot; To: {note.recipientName || note.recipientId}</span>}
                      {readOnly && <span>&middot; {note.isRead ? "Read" : "Unread"}</span>}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {hasMore && !loading && (
          <div className="border-t border-slate-100 p-3 text-center">
            <button type="button" onClick={() => void load(page + 1)} disabled={loadingMore} className="rounded-xl px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
              {loadingMore ? "Loading…" : `Load more (${rows.length} of ${count})`}
            </button>
          </div>
        )}
      </div>

      {openNote && (
        <NotificationDetailModal
          note={openNote}
          target={readOnly ? null : resolveTarget(openNote)}
          readOnly={readOnly}
          busy={actions.busy}
          error={actions.error}
          position={{ index: openIndex, total: rows.length }}
          onClose={() => setOpenId(null)}
          onPrev={openIndex > 0 ? () => openNoteAt(openIndex - 1) : undefined}
          onNext={openIndex < rows.length - 1 ? () => openNoteAt(openIndex + 1) : undefined}
          onOpenTarget={() => {
            const target = resolveTarget(openNote);
            if (target) {
              setOpenId(null);
              onOpenTarget(target);
            }
          }}
          onToggleRead={() => void actions.toggleRead(openNote)}
          onToggleArchive={() => void actions.toggleArchive(openNote)}
          onDelete={() => void actions.remove(openNote).then((ok) => { if (ok) setOpenId(null); })}
        />
      )}
    </div>
  );
}
