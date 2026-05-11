import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  Bell,
  Plus,
  Search,
  Filter,
  Edit,
  Trash2,
  Eye,
  EyeOff,
  Pin,
  Calendar,
  FileText,
  Download,
  ExternalLink,
  X,
  Save,
  Send,
  CheckCircle2,
  Clock,
  RefreshCw,
  FileDown,
  AlertTriangle,
  ChevronRight,
  Link2,
  Mail,
  Timer,
} from "lucide-react";
import {
  fetchNotices,
  createNotice,
  updateNotice,
  deleteNotice,
  publishNotice,
  unpublishNotice,
  fetchTenders,
} from "../api";
import { Notice, NoticeCategory, NoticeStatus, Tender } from "../types";

const categoryConfig: Record<NoticeCategory, { label: string; color: string; bgColor: string; borderColor: string; textColor: string }> = {
  [NoticeCategory.TENDER]: { label: "Tender", color: "bg-blue-100 text-blue-700", bgColor: "bg-blue-50", borderColor: "border-blue-200", textColor: "text-blue-700" },
  [NoticeCategory.DEADLINE]: { label: "Deadline", color: "bg-orange-100 text-orange-700", bgColor: "bg-orange-50", borderColor: "border-orange-200", textColor: "text-orange-700" },
  [NoticeCategory.AWARD]: { label: "Award", color: "bg-emerald-100 text-emerald-700", bgColor: "bg-emerald-50", borderColor: "border-emerald-200", textColor: "text-emerald-700" },
  [NoticeCategory.CLARIFICATION]: { label: "Clarification", color: "bg-yellow-100 text-yellow-700", bgColor: "bg-yellow-50", borderColor: "border-yellow-200", textColor: "text-yellow-700" },
  [NoticeCategory.TRAINING]: { label: "Training", color: "bg-purple-100 text-purple-700", bgColor: "bg-purple-50", borderColor: "border-purple-200", textColor: "text-purple-700" },
  [NoticeCategory.GENERAL]: { label: "General", color: "bg-slate-100 text-slate-700", bgColor: "bg-slate-50", borderColor: "border-slate-200", textColor: "text-slate-700" },
};

type ViewMode = "list" | "create" | "edit" | "preview" | "detail";

interface ToastMessage {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

const formatDate = (value?: string | null) => {
  if (!value) return "—";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const formatDateTime = (value?: string | null) => {
  if (!value) return "—";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

const getNextNoticeId = (notices: Notice[]) => {
  const maxNum = notices.reduce((max, n) => {
    const match = n.notice_id.match(/NTC-(\d+)/);
    if (match) return Math.max(max, parseInt(match[1]));
    return max;
  }, 0);
  return `NTC-${String(maxNum + 1).padStart(4, "0")}`;
};

export default function RmtNoticeManagement({ currentUser }: { currentUser?: any }) {
  const [loading, setLoading] = useState(true);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [selectedNotice, setSelectedNotice] = useState<Notice | null>(null);
  const [filterStatus, setFilterStatus] = useState<"all" | NoticeStatus>("all");
  const [filterCategory, setFilterCategory] = useState<"all" | NoticeCategory>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [existingAttachments, setExistingAttachments] = useState<any[]>([]);

  const [formData, setFormData] = useState({
    title: "",
    category: NoticeCategory.TENDER,
    summary: "",
    content: "",
    linked_tender: "" as string | null,
    is_pinned: false,
    send_email_notification: false,
    show_countdown: false,
    countdown_date: "" as string,
    publish_date: "" as string,
    schedule_publish: false,
  });

  const addToast = useCallback((type: ToastMessage["type"], message: string) => {
    const id = Date.now().toString();
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [noticesData, tendersData] = await Promise.all([
        fetchNotices(),
        fetchTenders(),
      ]);
      setNotices(noticesData);
      setTenders(tendersData);
    } catch (err) {
      addToast("error", "Failed to load notices. Please refresh the page.");
      console.error("Failed to load notices:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (formData.linked_tender && viewMode === "create") {
      const selectedTender = tenders.find((t) => t.id === formData.linked_tender);
      if (selectedTender?.deadline) {
        const tenderDeadline = new Date(selectedTender.deadline);
        if (!formData.countdown_date || new Date(formData.countdown_date) < tenderDeadline) {
          handleInputChange("countdown_date", selectedTender.deadline.split("T")[0]);
        }
        if (!formData.show_countdown) {
          handleInputChange("show_countdown", true);
        }
      }
    }
  }, [formData.linked_tender]);

  const filteredNotices = useMemo(() => {
    let filtered = notices;
    if (filterStatus !== "all") {
      filtered = filtered.filter((n) => n.status === filterStatus);
    }
    if (filterCategory !== "all") {
      filtered = filtered.filter((n) => n.category === filterCategory);
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (n) =>
          n.title.toLowerCase().includes(term) ||
          n.notice_id.toLowerCase().includes(term) ||
          n.summary.toLowerCase().includes(term)
      );
    }
    return filtered.sort((a, b) => {
      if (a.is_pinned && !b.is_pinned) return -1;
      if (!a.is_pinned && b.is_pinned) return 1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [notices, filterStatus, filterCategory, searchTerm]);

  const handleInputChange = (field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const resetForm = () => {
    setFormData({
      title: "",
      category: NoticeCategory.TENDER,
      summary: "",
      content: "",
      linked_tender: null,
      is_pinned: false,
      send_email_notification: false,
      show_countdown: false,
      countdown_date: "",
      publish_date: "",
      schedule_publish: false,
    });
    setAttachments([]);
    setExistingAttachments([]);
  };

  const handleCreateNew = () => {
    resetForm();
    setViewMode("create");
  };

  const handleEdit = (notice: Notice) => {
    setSelectedNotice(notice);
    setFormData({
      title: notice.title || "",
      category: notice.category || NoticeCategory.TENDER,
      summary: notice.summary || "",
      content: notice.content || "",
      linked_tender: notice.linked_tender || null,
      is_pinned: notice.is_pinned || false,
      send_email_notification: notice.send_email_notification || false,
      show_countdown: notice.show_countdown || false,
      countdown_date: notice.countdown_date ? new Date(notice.countdown_date).toISOString().slice(0, 16) : "",
      publish_date: notice.publish_date ? new Date(notice.publish_date).toISOString().slice(0, 16) : "",
      schedule_publish: notice.schedule_publish || false,
    });
    setViewMode("edit");
  };

  const handlePreview = (notice?: Notice) => {
    if (notice) {
      setSelectedNotice(notice);
    } else {
      setSelectedNotice({
        id: "",
        notice_id: getNextNoticeId(notices),
        title: formData.title,
        category: formData.category,
        summary: formData.summary,
        content: formData.content,
        linked_tender: formData.linked_tender,
        is_pinned: formData.is_pinned,
        show_countdown: formData.show_countdown,
        countdown_date: formData.countdown_date || null,
        status: NoticeStatus.DRAFT,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Notice);
    }
    setViewMode("preview");
  };

  const handleSubmit = async (publishImmediately: boolean) => {
    if (!formData.title.trim()) {
      addToast("error", "Notice title is required.");
      return;
    }
    if (!formData.summary.trim()) {
      addToast("error", "Summary is required.");
      return;
    }
    if (!formData.content.trim()) {
      addToast("error", "Full content is required.");
      return;
    }

    setSubmitting(true);
    try {
      const payload: any = {
        title: formData.title.trim(),
        category: formData.category,
        summary: formData.summary.trim(),
        content: formData.content.trim(),
        linked_tender: formData.linked_tender || null,
        is_pinned: formData.is_pinned,
        send_email_notification: formData.send_email_notification,
        show_countdown: formData.show_countdown,
        countdown_date: formData.show_countdown && formData.countdown_date ? new Date(formData.countdown_date).toISOString() : null,
        status: publishImmediately ? NoticeStatus.PUBLISHED : NoticeStatus.DRAFT,
      };

      if (formData.linked_tender) {
        const linkedTender = tenders.find(t => t.id === formData.linked_tender);
        if (linkedTender) {
          payload.tender_reference = linkedTender.referenceNumber;
          payload.tender_name = linkedTender.name;
          if (linkedTender.deadline && !formData.countdown_date) {
            payload.countdown_date = new Date(linkedTender.deadline).toISOString();
          }
        }
      }

      if (formData.schedule_publish && formData.publish_date) {
        payload.status = NoticeStatus.SCHEDULED;
        payload.publish_date = new Date(formData.publish_date).toISOString();
      }

      if (publishImmediately) {
        payload.published_at = new Date().toISOString();
      }

      let result: Notice;
      if (viewMode === "create") {
        result = await createNotice(payload);
        setNotices((prev) => [result, ...prev]);
        addToast("success", "Notice created successfully.");
      } else if (viewMode === "edit" && selectedNotice) {
        result = await updateNotice(selectedNotice.id, payload);
        setNotices((prev) => prev.map((n) => (n.id === result.id ? result : n)));
        addToast("success", "Notice updated successfully.");
      }

      setViewMode("list");
      resetForm();
    } catch (err: any) {
      const errorMsg = err?.message || "Failed to save notice. Please try again.";
      addToast("error", errorMsg);
      console.error("Failed to save notice:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (noticeId: string) => {
    setConfirmDelete(null);
    setActionLoading(noticeId);
    try {
      await deleteNotice(noticeId);
      setNotices((prev) => prev.filter((n) => n.id !== noticeId));
      addToast("success", "Notice deleted successfully.");
    } catch (err) {
      addToast("error", "Failed to delete notice. Please try again.");
      console.error("Failed to delete notice:", err);
    } finally {
      setActionLoading(null);
    }
  };

  const handlePublish = async (notice: Notice) => {
    setActionLoading(notice.id);
    try {
      const updated = await publishNotice(notice.id);
      setNotices((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      addToast("success", "Notice published successfully.");
    } catch (err) {
      addToast("error", "Failed to publish notice. Please try again.");
      console.error("Failed to publish notice:", err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUnpublish = async (notice: Notice) => {
    setActionLoading(notice.id);
    try {
      const updated = await unpublishNotice(notice.id);
      setNotices((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      addToast("success", "Notice unpublished successfully.");
    } catch (err) {
      addToast("error", "Failed to unpublish notice. Please try again.");
      console.error("Failed to unpublish notice:", err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleExport = () => {
    const headers = ["Ref", "Title", "Category", "Status", "Pinned", "Published Date", "Created Date"];
    const rows = notices.map((n) => [
      n.notice_id,
      `"${n.title.replace(/"/g, '""')}"`,
      n.category,
      n.status,
      n.is_pinned ? "Yes" : "No",
      n.published_at || "",
      n.created_at,
    ]);

    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `notice-archive-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addToast("success", "Notice archive exported successfully.");
  };

  const handleAttachmentChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const validFiles = files.filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      if (!["pdf", "docx", "xlsx"].includes(ext || "")) {
        addToast("error", `${f.name} is not a supported file type.`);
        return false;
      }
      if (f.size > 10 * 1024 * 1024) {
        addToast("error", `${f.name} exceeds 10MB size limit.`);
        return false;
      }
      return true;
    });
    setAttachments((prev) => [...prev, ...validFiles]);
  };

  const removeAttachment = (index: number, type: 'new' | 'existing' = 'new') => {
    if (type === 'existing') {
      setExistingAttachments(prev => prev.filter((_, i) => i !== index));
    } else {
      setAttachments(prev => prev.filter((_, i) => i !== index));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="animate-spin text-emerald-600 mx-auto mb-3" size={32} />
          <p className="text-slate-500">Loading notices...</p>
        </div>
      </div>
    );
  }

  if (viewMode === "preview") {
    const notice = selectedNotice!;
    const catConfig = categoryConfig[notice.category] || categoryConfig[NoticeCategory.GENERAL];

    return (
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="bg-slate-50 px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setViewMode(viewMode === "preview" && formData.title ? "create" : "list")}
              className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
            >
              <ChevronRight className="rotate-180" size={16} />
              Back
            </button>
            <span className="text-slate-300">|</span>
            <span className="text-sm font-medium text-slate-700">Preview Mode</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-3 py-1 rounded-full text-xs font-bold ${catConfig.color}`}>
              {catConfig.label.toUpperCase()}
            </span>
            {notice.is_pinned && (
              <span className="px-3 py-1 rounded-full bg-amber-100 text-amber-700 text-xs font-bold">
                PINNED
              </span>
            )}
          </div>
        </div>

        <div className="p-6 md:p-8">
          <div className="mb-6">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              {notice.notice_id || "DRAFT"} | {formatDate(notice.published_at || notice.created_at)}
            </p>
            <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mb-3">{notice.title}</h1>
            <p className="text-slate-600 text-lg whitespace-pre-wrap break-words">{notice.summary}</p>
          </div>

          {(notice.linked_tender || notice.tender_reference) && (
            <div className="flex items-center gap-2 p-4 bg-blue-50 rounded-xl border border-blue-200 mb-6">
              <Link2 size={18} className="text-blue-600" />
              <div>
                <p className="text-xs font-medium text-blue-600 uppercase">Linked Tender</p>
                <p className="text-sm font-semibold text-blue-700">{notice.tender_reference || notice.linked_tender}</p>
              </div>
            </div>
          )}

          <div className="border-t border-b border-slate-200 py-6 mb-6">
            <div className="text-slate-700 whitespace-pre-wrap break-words leading-relaxed">{notice.content}</div>
          </div>

          {notice.show_countdown && notice.countdown_date && (
            <div className="flex items-center gap-3 p-4 bg-rose-50 rounded-xl border border-rose-200 mb-6">
              <Timer size={20} className="text-rose-600" />
              <div>
                <p className="text-xs font-semibold text-rose-600 uppercase">Countdown Deadline</p>
                <p className="text-sm font-bold text-rose-700">{formatDateTime(notice.countdown_date)}</p>
              </div>
            </div>
          )}

          {notice.send_email_notification && (
            <div className="flex items-center gap-2 p-4 bg-slate-50 rounded-xl border border-slate-200 mb-6">
              <Mail size={18} className="text-slate-600" />
              <p className="text-sm text-slate-600">Email notification will be sent to all registered vendors</p>
            </div>
          )}

          {(existingAttachments.length > 0 || attachments.length > 0) && (
            <div className="mb-6">
              <h4 className="text-sm font-semibold text-slate-700 mb-3">Attachments</h4>
              <div className="space-y-2">
                {existingAttachments.map((att: any, i: number) => (
                  <div key={`existing-${i}`} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <FileText size={18} className="text-emerald-600" />
                    <span className="text-sm text-slate-700 flex-1">{att.name}</span>
                    {att.url && (
                      <a href={att.url} target="_blank" rel="noopener noreferrer" className="text-xs text-emerald-600 font-medium hover:underline">Download</a>
                    )}
                  </div>
                ))}
                {attachments.map((file, i) => (
                  <div key={`new-${i}`} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <FileText size={18} className="text-emerald-600" />
                    <span className="text-sm text-slate-700 flex-1">{file.name}</span>
                    <span className="text-xs text-slate-400">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-200">
            <button
              onClick={() => setViewMode(viewMode === "preview" && formData.title ? "create" : "list")}
              className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium"
            >
              Cancel
            </button>
            <div className="flex items-center gap-3">
              <button
                onClick={() => handleSubmit(false)}
                disabled={submitting}
                className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                Save Draft
              </button>
              <button
                onClick={() => handleSubmit(true)}
                disabled={submitting}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
                Publish Notice
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (viewMode === "create" || viewMode === "edit") {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="bg-slate-50 px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setViewMode("list");
                resetForm();
              }}
              className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
            >
              <ChevronRight className="rotate-180" size={16} />
              Back to Notices
            </button>
            <span className="text-slate-300">|</span>
            <span className="text-sm font-medium text-slate-700">
              {viewMode === "create" ? "Create New Notice" : "Edit Notice"}
            </span>
          </div>
          <span className="text-sm text-slate-500">
            {viewMode === "create" ? `Ref: ${getNextNoticeId(notices)}` : `Ref: ${selectedNotice?.notice_id}`}
          </span>
        </div>

        <div className="p-6 md:p-8 space-y-8">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-6">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">
                  Notice Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => handleInputChange("title", e.target.value)}
                  placeholder="e.g. New Tender Open — TND-000027"
                  className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition"
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-3">
                  Category <span className="text-rose-500">*</span>
                </label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {Object.entries(categoryConfig).map(([key, config]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => handleInputChange("category", key as NoticeCategory)}
                      className={`p-3 rounded-xl border-2 text-left transition-all ${
                        formData.category === key
                          ? `border-emerald-500 ${config.bgColor}`
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${config.color}`}>
                        {config.label.toUpperCase()}
                      </span>
                      <p className="text-xs text-slate-500 mt-1">
                        {key === NoticeCategory.TENDER && "New tender announcement"}
                        {key === NoticeCategory.DEADLINE && "Deadline reminder"}
                        {key === NoticeCategory.AWARD && "Contract award"}
                        {key === NoticeCategory.CLARIFICATION && "Addendum or Q&A"}
                        {key === NoticeCategory.TRAINING && "Workshop notice"}
                        {key === NoticeCategory.GENERAL && "Programme update"}
                      </p>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">
                  Linked Tender (optional)
                </label>
                <select
                  value={formData.linked_tender || ""}
                  onChange={(e) => handleInputChange("linked_tender", e.target.value || null)}
                  className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition bg-white"
                >
                  <option value="">Select a tender...</option>
                  {tenders.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.referenceNumber} — {t.name}{t.deadline ? ` (Deadline: ${new Date(t.deadline).toLocaleDateString()})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">
                  Summary <span className="text-rose-500">*</span>
                </label>
                <textarea
                  value={formData.summary}
                  onChange={(e) => handleInputChange("summary", e.target.value)}
                  placeholder="Brief description shown in the notice board list"
                  maxLength={200}
                  rows={2}
                  className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition resize-none"
                />
                <p className="text-xs text-slate-500 mt-1 text-right">{formData.summary.length}/200</p>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">
                  Full Content <span className="text-rose-500">*</span>
                </label>
                <textarea
                  value={formData.content}
                  onChange={(e) => handleInputChange("content", e.target.value)}
                  placeholder="Enter the full notice content here. You can use multiple paragraphs."
                  rows={10}
                  className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-2">
                  Attachments
                </label>
                <div className="border-2 border-dashed border-slate-300 rounded-xl p-6">
                  <input
                    type="file"
                    id="notice-attachments"
                    multiple
                    accept=".pdf,.docx,.xlsx"
                    onChange={handleAttachmentChange}
                    className="hidden"
                  />
                  <label
                    htmlFor="notice-attachments"
                    className="cursor-pointer flex flex-col items-center"
                  >
                    <Plus size={24} className="text-slate-400 mb-2" />
                    <span className="text-sm font-medium text-slate-600">Click to upload</span>
                    <span className="text-xs text-slate-400 mt-1">PDF, DOCX, XLSX — max 10MB per file</span>
                  </label>
                </div>
                {attachments.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {existingAttachments.map((att: any, i: number) => (
                      <div key={`existing-${i}`} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                        <FileText size={18} className="text-emerald-600" />
                        <span className="text-sm text-slate-700 flex-1">{att.name}</span>
                        <a href={att.url} target="_blank" rel="noopener noreferrer" className="text-xs text-emerald-600 font-medium">View</a>
                      </div>
                    ))}
                    {attachments.map((file, i) => (
                      <div key={i} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                        <FileText size={18} className="text-emerald-600" />
                        <span className="text-sm text-slate-700 flex-1 truncate">{file.name}</span>
                        <span className="text-xs text-slate-400">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                        <button onClick={() => removeAttachment(i, 'existing')} className="text-slate-400 hover:text-rose-600">
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    {attachments.map((file, i) => (
                      <div key={`new-${i}`} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                        <FileText size={18} className="text-emerald-600" />
                        <span className="text-sm text-slate-700 flex-1 truncate">{file.name}</span>
                        <span className="text-xs text-slate-400">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                        <button onClick={() => removeAttachment(i, 'new')} className="text-slate-400 hover:text-rose-600">
                          <X size={16} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-6">
              <div className="bg-slate-50 rounded-xl p-5 space-y-4">
                <h4 className="font-bold text-slate-700">Publishing Options</h4>

                <div>
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_pinned}
                      onChange={(e) => handleInputChange("is_pinned", e.target.checked)}
                      className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-slate-700">Pin to top</span>
                      <p className="text-xs text-slate-500">Important notices only</p>
                    </div>
                  </label>
                </div>

                <div>
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.send_email_notification}
                      onChange={(e) => handleInputChange("send_email_notification", e.target.checked)}
                      className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-slate-700">Email vendors</span>
                      <p className="text-xs text-slate-500">Notify all registered vendors</p>
                    </div>
                  </label>
                </div>

                <div>
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.show_countdown}
                      onChange={(e) => handleInputChange("show_countdown", e.target.checked)}
                      className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-slate-700">Show countdown</span>
                      <p className="text-xs text-slate-500">Display days remaining</p>
                    </div>
                  </label>
                  {formData.show_countdown && (
                    <div className="mt-2 ml-7">
                      <input
                        type="datetime-local"
                        value={formData.countdown_date}
                        onChange={(e) => handleInputChange("countdown_date", e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-emerald-500 outline-none"
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-slate-50 rounded-xl p-5 space-y-4">
                <h4 className="font-bold text-slate-700">Schedule</h4>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="schedule"
                    checked={!formData.schedule_publish}
                    onChange={() => handleInputChange("schedule_publish", false)}
                    className="w-4 h-4 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">Publish immediately</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="schedule"
                    checked={formData.schedule_publish}
                    onChange={() => handleInputChange("schedule_publish", true)}
                    className="w-4 h-4 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">Schedule for later</span>
                </label>

                {formData.schedule_publish && (
                  <div className="ml-7 space-y-2">
                    <input
                      type="date"
                      value={formData.publish_date ? formData.publish_date.split("T")[0] : ""}
                      onChange={(e) => handleInputChange("publish_date", e.target.value + "T" + (formData.publish_date?.split("T")[1] || "09:00"))}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-emerald-500 outline-none"
                    />
                    <input
                      type="time"
                      value={formData.publish_date ? formData.publish_date.split("T")[1]?.substring(0, 5) : "09:00"}
                      onChange={(e) => handleInputChange("publish_date", (formData.publish_date?.split("T")[0] || new Date().toISOString().split("T")[0]) + "T" + e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-emerald-500 outline-none"
                    />
                  </div>
                )}
              </div>

              <button
                onClick={() => handlePreview()}
                disabled={!formData.title || !formData.summary}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <Eye size={18} />
                Preview Notice
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between pt-6 border-t border-slate-200">
            <button
              onClick={() => {
                setViewMode("list");
                resetForm();
              }}
              className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium"
            >
              Cancel
            </button>
            <div className="flex items-center gap-3">
              <button
                onClick={() => handleSubmit(false)}
                disabled={submitting}
                className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                Save Draft
              </button>
              <button
                onClick={() => handleSubmit(true)}
                disabled={submitting}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
                Publish Notice
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`fixed top-20 right-6 z-50 px-5 py-3 rounded-xl shadow-lg flex items-center gap-3 animate-slide-in ${
            toast.type === "success" ? "bg-emerald-600 text-white" : toast.type === "error" ? "bg-rose-600 text-white" : "bg-slate-800 text-white"
          }`}
        >
          {toast.type === "success" && <CheckCircle2 size={20} />}
          {toast.type === "error" && <AlertTriangle size={20} />}
          <span className="font-medium">{toast.message}</span>
        </div>
      ))}

      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center">
            <Bell className="text-white" size={20} />
          </div>
          <div>
            <h3 className="text-xl md:text-2xl font-bold text-slate-900">Notice Board</h3>
            <p className="text-sm text-slate-500">{filteredNotices.length} notices</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium text-sm"
          >
            <FileDown size={18} />
            Export
          </button>
          <button
            onClick={handleCreateNew}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition font-medium text-sm"
          >
            <Plus size={18} />
            New Notice
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search notices..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-slate-400" />
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as any)}
              className="px-3 py-2.5 rounded-xl border border-slate-300 text-sm focus:border-emerald-500 outline-none bg-white"
            >
              <option value="all">All Status</option>
              <option value={NoticeStatus.PUBLISHED}>Published</option>
              <option value={NoticeStatus.DRAFT}>Draft</option>
              <option value={NoticeStatus.SCHEDULED}>Scheduled</option>
            </select>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value as any)}
              className="px-3 py-2.5 rounded-xl border border-slate-300 text-sm focus:border-emerald-500 outline-none bg-white"
            >
              <option value="all">All Categories</option>
              {Object.entries(categoryConfig).map(([key, config]) => (
                <option key={key} value={key}>{config.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {filteredNotices.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-16 text-center">
          <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <Bell className="text-slate-400" size={32} />
          </div>
          <p className="font-semibold text-slate-700 text-lg">No notices found</p>
          <p className="text-slate-500 mt-1">
            {searchTerm || filterStatus !== "all" || filterCategory !== "all"
              ? "Try adjusting your filters to see more results"
              : "Get started by creating your first notice"}
          </p>
          {(searchTerm || filterStatus !== "all" || filterCategory !== "all") && (
            <button
              onClick={() => { setSearchTerm(""); setFilterStatus("all"); setFilterCategory("all"); }}
              className="mt-4 text-emerald-600 font-medium hover:underline"
            >
              Clear all filters
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredNotices.map((notice) => {
            const catConfig = categoryConfig[notice.category] || categoryConfig[NoticeCategory.GENERAL];
            return (
              <div
                key={notice.id}
                className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-lg hover:border-slate-300 transition-all group"
              >
                <div className="p-5">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <span className={`px-2.5 py-1 rounded-lg text-xs font-bold ${catConfig.color}`}>
                      {catConfig.label.toUpperCase()}
                    </span>
                    {notice.is_pinned && (
                      <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-bold uppercase tracking-wider">
                        PINNED
                      </span>
                    )}
                  </div>

                  <p className="text-xs font-mono text-slate-400 mb-2">{notice.notice_id}</p>
                  <h4 className="font-bold text-slate-900 mb-2 line-clamp-2">{notice.title}</h4>
                  <p className="text-sm text-slate-500 line-clamp-2 mb-4">{notice.summary}</p>

                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">
                      {formatDate(notice.published_at || notice.created_at)}
                    </span>
                    {notice.status === NoticeStatus.PUBLISHED ? (
                      <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase">
                        LIVE
                      </span>
                    ) : notice.status === NoticeStatus.SCHEDULED ? (
                      <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-bold uppercase">
                        SCHEDULED
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-bold uppercase">
                        DRAFT
                      </span>
                    )}
                  </div>
                </div>

                <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handlePreview(notice)}
                      className="p-2 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition"
                      title="Preview"
                    >
                      <Eye size={16} />
                    </button>
                    <button
                      onClick={() => handleEdit(notice)}
                      className="p-2 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition"
                      title="Edit"
                    >
                      <Edit size={16} />
                    </button>
                    {notice.status === NoticeStatus.DRAFT ? (
                      <button
                        onClick={() => handlePublish(notice)}
                        disabled={actionLoading === notice.id}
                        className="p-2 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition disabled:opacity-50"
                        title="Publish"
                      >
                        {actionLoading === notice.id ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
                      </button>
                    ) : (
                      <button
                        onClick={() => handleUnpublish(notice)}
                        disabled={actionLoading === notice.id}
                        className="p-2 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition disabled:opacity-50"
                        title="Unpublish"
                      >
                        <EyeOff size={16} />
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => setConfirmDelete(notice.id)}
                    className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition"
                    title="Delete"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-rose-100 flex items-center justify-center">
                <AlertTriangle className="text-rose-600" size={24} />
              </div>
              <div>
                <h4 className="text-lg font-bold text-slate-900">Delete Notice</h4>
                <p className="text-sm text-slate-500">This action cannot be undone.</p>
              </div>
            </div>
            <p className="text-slate-600 mb-6">
              Are you sure you want to delete this notice? This will permanently remove it from the system.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(confirmDelete)}
                className="px-5 py-2.5 rounded-xl bg-rose-600 text-white hover:bg-rose-700 transition font-medium flex items-center gap-2"
              >
                <Trash2 size={16} />
                Delete Notice
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
