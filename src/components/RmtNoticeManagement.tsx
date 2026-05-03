import React, { useEffect, useMemo, useState } from "react";
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
  PinOff,
  Calendar,
  FileText,
  Download,
  ExternalLink,
  X,
  Save,
  Send,
  AlertCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  FileDown,
} from "lucide-react";
import {
  fetchNotices,
  fetchNotice,
  createNotice,
  updateNotice,
  deleteNotice,
  publishNotice,
  unpublishNotice,
  fetchTenders,
} from "../api";
import { Notice, NoticeCategory, NoticeStatus, Tender } from "../types";

const categoryConfig: Record<NoticeCategory, { label: string; color: string; bgColor: string; borderColor: string }> = {
  [NoticeCategory.TENDER]: { label: "Tender", color: "text-blue-700", bgColor: "bg-blue-50", borderColor: "border-blue-200" },
  [NoticeCategory.DEADLINE]: { label: "Deadline", color: "text-orange-700", bgColor: "bg-orange-50", borderColor: "border-orange-200" },
  [NoticeCategory.AWARD]: { label: "Award", color: "text-emerald-700", bgColor: "bg-emerald-50", borderColor: "border-emerald-200" },
  [NoticeCategory.CLARIFICATION]: { label: "Clarif.", color: "text-yellow-700", bgColor: "bg-yellow-50", borderColor: "border-yellow-200" },
  [NoticeCategory.TRAINING]: { label: "Training", color: "text-purple-700", bgColor: "bg-purple-50", borderColor: "border-purple-200" },
  [NoticeCategory.GENERAL]: { label: "General", color: "text-slate-700", bgColor: "bg-slate-50", borderColor: "border-slate-200" },
};

const formatDate = (value?: string | null) => {
  if (!value) return "Draft";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const getNextNoticeId = (notices: Notice[]) => {
  const maxNum = notices.reduce((max, n) => {
    const match = n.notice_id.match(/NTC-(\d+)/);
    if (match) return Math.max(max, parseInt(match[1]));
    return max;
  }, 0);
  return `NTC-${String(maxNum + 1).padStart(4, "0")}`;
};

type ViewMode = "list" | "create" | "edit" | "preview";

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

  const [formData, setFormData] = useState<Partial<Notice>>({
    title: "",
    category: NoticeCategory.TENDER,
    summary: "",
    content: "",
    linked_tender: null,
    is_pinned: false,
    show_countdown: false,
    countdown_date: null,
    status: NoticeStatus.DRAFT,
  });

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
      console.error("Failed to load notices:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

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
    return filtered;
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
      show_countdown: false,
      countdown_date: null,
      status: NoticeStatus.DRAFT,
    });
  };

  const handleCreateNew = () => {
    resetForm();
    setViewMode("create");
  };

  const handleEdit = (notice: Notice) => {
    setSelectedNotice(notice);
    setFormData({
      title: notice.title,
      category: notice.category,
      summary: notice.summary,
      content: notice.content,
      linked_tender: notice.linked_tender || null,
      is_pinned: notice.is_pinned,
      show_countdown: notice.show_countdown,
      countdown_date: notice.countdown_date || null,
      status: notice.status,
    });
    setViewMode("edit");
  };

  const handlePreview = (notice: Notice) => {
    setSelectedNotice(notice);
    setViewMode("preview");
  };

  const handleSubmit = async (publishImmediately: boolean) => {
    setSubmitting(true);
    try {
      const payload = {
        ...formData,
        status: publishImmediately ? NoticeStatus.PUBLISHED : NoticeStatus.DRAFT,
        published_at: publishImmediately ? new Date().toISOString() : null,
      };

      if (viewMode === "create") {
        const newNotice = await createNotice(payload);
        setNotices((prev) => [newNotice, ...prev]);
      } else if (viewMode === "edit" && selectedNotice) {
        const updated = await updateNotice(selectedNotice.id, payload);
        setNotices((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      }

      setViewMode("list");
      resetForm();
    } catch (err) {
      console.error("Failed to save notice:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (noticeId: string) => {
    if (!confirm("Are you sure you want to delete this notice?")) return;
    try {
      await deleteNotice(noticeId);
      setNotices((prev) => prev.filter((n) => n.id !== noticeId));
    } catch (err) {
      console.error("Failed to delete notice:", err);
    }
  };

  const handlePublish = async (notice: Notice) => {
    try {
      const updated = await publishNotice(notice.id);
      setNotices((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
    } catch (err) {
      console.error("Failed to publish notice:", err);
    }
  };

  const handleUnpublish = async (notice: Notice) => {
    try {
      const updated = await unpublishNotice(notice.id);
      setNotices((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
    } catch (err) {
      console.error("Failed to unpublish notice:", err);
    }
  };

  const handleExport = () => {
    const csv = [
      ["Ref", "Title", "Category", "Published", "Status"].join(","),
      ...notices.map((n) =>
        [n.notice_id, `"${n.title}"`, n.category, n.published_at || "Draft", n.status].join(",")
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "notice-archive.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-emerald-600" size={32} />
      </div>
    );
  }

  if (viewMode === "create" || viewMode === "edit") {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => setViewMode("list")}
            className="text-sm text-emerald-600 hover:text-emerald-700"
          >
            ← Back to All Notices
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-6 md:p-8">
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center">
                <Bell className="text-white" size={20} />
              </div>
              <div>
                <h3 className="text-2xl font-bold text-slate-900">
                  {viewMode === "create" ? "New Notice" : "Edit Notice"}
                </h3>
                <p className="text-sm text-slate-500">
                  {viewMode === "create"
                    ? `Notice Reference: ${getNextNoticeId(notices)} (auto-generated)`
                    : `Notice Reference: ${selectedNotice?.notice_id}`}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {/* Notice Title */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">
                Notice Title <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                value={formData.title || ""}
                onChange={(e) => handleInputChange("title", e.target.value)}
                placeholder="e.g. New Tender Open — TND-000027"
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition"
              />
            </div>

            {/* Category */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-3">
                Category <span className="text-rose-500">*</span>
              </label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(categoryConfig).map(([key, config]) => (
                  <label
                    key={key}
                    className={`flex items-start gap-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                      formData.category === key
                        ? `border-emerald-500 ${config.bgColor}`
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <input
                      type="radio"
                      name="category"
                      value={key}
                      checked={formData.category === key}
                      onChange={(e) => handleInputChange("category", e.target.value)}
                      className="mt-1"
                    />
                    <div>
                      <div className={`font-medium text-sm ${config.color}`}>{config.label}</div>
                      <div className="text-xs text-slate-500 mt-1">
                        {key === NoticeCategory.TENDER && "New tender announcement"}
                        {key === NoticeCategory.DEADLINE && "Deadline reminder or extension"}
                        {key === NoticeCategory.AWARD && "Contract award notification"}
                        {key === NoticeCategory.CLARIFICATION && "Addendum or Q&A response"}
                        {key === NoticeCategory.TRAINING && "Workshop or meeting notice"}
                        {key === NoticeCategory.GENERAL && "Programme update or other"}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Link to Tender */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">
                Link to Tender (optional)
              </label>
              <select
                value={formData.linked_tender || ""}
                onChange={(e) => handleInputChange("linked_tender", e.target.value || null)}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition bg-white"
              >
                <option value="">No linked tender</option>
                {tenders.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.referenceNumber} - {t.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">
                Links this notice to a specific tender. Will show [View Tender] button on notice.
              </p>
            </div>

            {/* Summary */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">
                Summary (shown on notice board list) <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={formData.summary || ""}
                onChange={(e) => handleInputChange("summary", e.target.value)}
                placeholder="Short description shown in the notice list (max 200 characters)"
                maxLength={200}
                rows={2}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition resize-none"
              />
              <p className="text-xs text-slate-500 mt-1">
                {(formData.summary || "").length}/200 characters
              </p>
            </div>

            {/* Full Content */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">
                Full Content <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={formData.content || ""}
                onChange={(e) => handleInputChange("content", e.target.value)}
                placeholder="Full notice content goes here. Supports plain text formatting."
                rows={8}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition resize-none font-mono text-sm"
              />
              <p className="text-xs text-slate-500 mt-1">
                Full notice content. You can use plain text formatting.
              </p>
            </div>

            {/* Attachments */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">
                Attachments (optional)
              </label>
              <div className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center">
                <input
                  type="file"
                  id="notice-attachments"
                  multiple
                  accept=".pdf,.docx,.xlsx"
                  className="hidden"
                />
                <label
                  htmlFor="notice-attachments"
                  className="cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 transition"
                >
                  <Plus size={16} />
                  Add File
                </label>
                <p className="text-xs text-slate-500 mt-2">
                  PDF/DOCX/XLSX — max 10MB per file
                </p>
              </div>
            </div>

            {/* Options */}
            <div className="space-y-4 bg-slate-50 rounded-xl p-6">
              <h4 className="font-semibold text-slate-700">Options</h4>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_pinned || false}
                  onChange={(e) => handleInputChange("is_pinned", e.target.checked)}
                  className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                <div>
                  <span className="text-sm font-medium text-slate-700">Pin this notice to the top of the board</span>
                  <p className="text-xs text-slate-500">Use for urgent or important notices only</p>
                </div>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.show_countdown || false}
                  onChange={(e) => handleInputChange("show_countdown", e.target.checked)}
                  className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                <div>
                  <span className="text-sm font-medium text-slate-700">Show countdown timer</span>
                  <p className="text-xs text-slate-500">For deadline notices — shows days remaining</p>
                </div>
              </label>

              {formData.show_countdown && (
                <div className="ml-8">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Deadline Date</label>
                  <input
                    type="datetime-local"
                    value={formData.countdown_date || ""}
                    onChange={(e) => handleInputChange("countdown_date", e.target.value || null)}
                    className="px-4 py-2 rounded-lg border border-slate-300 focus:border-emerald-500 outline-none"
                  />
                </div>
              )}
            </div>

            {/* Publish Options */}
            <div className="bg-slate-50 rounded-xl p-6">
              <h4 className="font-semibold text-slate-700 mb-4">Publish Date</h4>
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="publishOption"
                    checked={formData.status !== NoticeStatus.PUBLISHED}
                    onChange={() => handleInputChange("status", NoticeStatus.DRAFT)}
                    className="w-5 h-5 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">Publish immediately</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="publishOption"
                    checked={formData.status === NoticeStatus.PUBLISHED}
                    onChange={() => handleInputChange("status", NoticeStatus.PUBLISHED)}
                    className="w-5 h-5 text-emerald-600"
                  />
                  <span className="text-sm font-medium text-slate-700">Schedule for later</span>
                </label>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-6 border-t border-slate-200">
              <button
                onClick={() => {
                  setViewMode("list");
                  resetForm();
                }}
                className="px-6 py-3 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium"
              >
                Cancel
              </button>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleSubmit(false)}
                  disabled={submitting}
                  className="px-6 py-3 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium flex items-center gap-2"
                >
                  <Save size={18} />
                  Save as Draft
                </button>

                <button
                  onClick={() => handleSubmit(true)}
                  disabled={submitting}
                  className="px-6 py-3 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition font-medium flex items-center gap-2"
                >
                  {submitting ? (
                    <RefreshCw size={18} className="animate-spin" />
                  ) : (
                    <Send size={18} />
                  )}
                  Publish Notice
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (viewMode === "preview" && selectedNotice) {
    const catConfig = categoryConfig[selectedNotice.category];
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => setViewMode("list")}
            className="text-sm text-emerald-600 hover:text-emerald-700"
          >
            ← Back to All Notices
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-3xl mx-auto">
          <div className="mb-6">
            <div className={`inline-flex items-center gap-2 rounded-lg border ${catConfig.borderColor} ${catConfig.bgColor} px-3 py-1.5 mb-4`}>
              <span className="text-xs">{catConfig.label === "Tender" ? "🔵" : catConfig.label === "Award" ? "🟢" : catConfig.label === "Clarification" ? "🟡" : catConfig.label === "Training" ? "🟣" : "⚪"}</span>
              <span className={`text-xs font-bold ${catConfig.color} uppercase tracking-wider`}>{catConfig.label}</span>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">{selectedNotice.title}</h2>
            <p className="text-sm text-slate-500">
              Published: {formatDate(selectedNotice.published_at)} | Ref: {selectedNotice.notice_id}
            </p>
          </div>

          <div className="prose prose-slate max-w-none">
            <p className="text-slate-600 leading-relaxed">{selectedNotice.summary}</p>
            <div className="mt-4 pt-4 border-t border-slate-200">
              <p className="text-slate-700 whitespace-pre-wrap">{selectedNotice.content}</p>
            </div>
          </div>

          {selectedNotice.linked_tender && (
            <div className="mt-6 pt-6 border-t border-slate-200">
              <a
                href="#"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition text-sm font-medium"
              >
                <ExternalLink size={16} />
                View Tender
              </a>
            </div>
          )}

          {selectedNotice.is_pinned && (
            <div className="mt-4">
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium">
                <Pin size={12} /> Pinned
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center">
            <Bell className="text-white" size={20} />
          </div>
          <div>
            <h3 className="text-2xl font-bold text-slate-900">Notice Board Management</h3>
            <p className="text-sm text-slate-500">Manage notices for the RBF programme</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition font-medium"
          >
            <FileDown size={18} />
            Export Notice Archive
          </button>
          <button
            onClick={handleCreateNew}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition font-medium"
          >
            <Plus size={18} />
            New Notice
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 mb-6">
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

          <div className="flex items-center gap-3">
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
              </select>
            </div>

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

      {/* Notices Table */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Ref</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Title</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Category</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Published</th>
                <th className="text-left px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
                <th className="text-right px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredNotices.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400">
                    <Bell className="mx-auto mb-3 text-slate-300" size={48} />
                    <p className="font-medium">No notices found</p>
                    <p className="text-sm">Create your first notice to get started</p>
                  </td>
                </tr>
              ) : (
                filteredNotices.map((notice) => {
                  const catConfig = categoryConfig[notice.category];
                  return (
                    <tr key={notice.id} className="hover:bg-slate-50 transition">
                      <td className="px-6 py-4">
                        <span className="font-mono text-sm font-medium text-slate-700">{notice.notice_id}</span>
                      </td>
                      <td className="px-6 py-4">
                        <div>
                          <p className="font-medium text-slate-900">{notice.title}</p>
                          {notice.is_pinned && (
                            <span className="inline-flex items-center gap-1 text-xs text-amber-600 mt-1">
                              <Pin size={12} /> Pinned
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium ${catConfig.bgColor} ${catConfig.color} ${catConfig.borderColor} border`}>
                          {catConfig.label === "Tender" ? "🔵" : catConfig.label === "Award" ? "🟢" : catConfig.label === "Clarification" ? "🟡" : catConfig.label === "Training" ? "🟣" : "⚪"} {catConfig.label}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm text-slate-600">{formatDate(notice.published_at)}</span>
                      </td>
                      <td className="px-6 py-4">
                        {notice.status === NoticeStatus.PUBLISHED ? (
                          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle2 size={14} /> Live
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                            <Clock size={14} /> Draft
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handlePreview(notice)}
                            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
                            title="Preview"
                          >
                            <Eye size={18} />
                          </button>
                          <button
                            onClick={() => handleEdit(notice)}
                            className="p-2 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition"
                            title="Edit"
                          >
                            <Edit size={18} />
                          </button>
                          {notice.status === NoticeStatus.DRAFT ? (
                            <button
                              onClick={() => handlePublish(notice)}
                              className="p-2 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition"
                              title="Publish"
                            >
                              <Send size={18} />
                            </button>
                          ) : (
                            <button
                              onClick={() => handleUnpublish(notice)}
                              className="p-2 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition"
                              title="Unpublish"
                            >
                              <EyeOff size={18} />
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(notice.id)}
                            className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition"
                            title="Delete"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
