import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Loader2,
  X,
  FileText,
  MessageSquare,
  Calendar,
  User,
  Building2,
  Send,
  Shield,
  ExternalLink,
} from "lucide-react";
import { fetchConcerns, fetchAuditFindings, fetchProjects, fetchPaymentClaims, updateConcern, updateAuditFinding, createConcernResponse, respondAuditFinding } from "../api";
import { MacroKpiPortal } from "./RoleBasedKpiPanels";
import { Project, PaymentClaim } from "../types";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");
const formatDate = (value?: string | null) => {
  if (!value) return "N/A";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const getSeverityIcon = (severity: string | undefined) => {
  if (severity === "critical") return "⛔";
  if (severity === "high" || severity === "major") return "🔴";
  if (severity === "medium" || severity === "minor") return "🟠";
  return "🟡";
};

const getSeverityLabel = (severity: string | undefined) => {
  if (severity === "critical") return "CRITICAL";
  if (severity === "high" || severity === "major") return "MAJOR";
  if (severity === "medium" || severity === "minor") return "MINOR";
  return "OBSERVATION";
};

const getSeverityBadgeColor = (severity: string | undefined) => {
  if (severity === "critical") return "bg-rose-600 text-white";
  if (severity === "high" || severity === "major") return "bg-rose-500 text-white";
  if (severity === "medium" || severity === "minor") return "bg-orange-500 text-white";
  return "bg-amber-400 text-amber-900";
};

export default function PscIssuesView({ currentUser }: { currentUser?: any }) {
  const [loading, setLoading] = useState(true);
  const [concerns, setConcerns] = useState<any[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [pscComment, setPscComment] = useState("");
  const [submittingComment, setSubmittingComment] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [concernsData, findingsData, projList, claimsData] = await Promise.all([
        fetchConcerns(),
        fetchAuditFindings(),
        fetchProjects(),
        fetchPaymentClaims(),
      ]);
      setConcerns(concernsData);
      setFindings(findingsData);
      setProjects(projList);
      setClaims(claimsData);
    } catch (err) {
      console.error("Failed to load PSC issues:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const projectMap = useMemo(() => {
    const map: Record<string, any> = {};
    projects.forEach((p: Project) => { map[p.id] = p; });
    return map;
  }, [projects]);

  const escalatedConcerns = useMemo(() => {
    return concerns.filter((c: any) => c.notifyPsc || c.notify_psc || c.status === "escalated_to_psc");
  }, [concerns]);

  const escalatedFindings = useMemo(() => {
    return findings;
  }, [findings]);

  const handleAddPscComment = async () => {
    if (!pscComment.trim() || !selectedItem) return;
    setSubmittingComment(true);
    try {
      console.log("=== PSC ADDING COMMENT ===");
      console.log("Type:", selectedItem.type);
      console.log("ID:", selectedItem.id);
      console.log("Comment:", pscComment);
      
      if (selectedItem.type === "DoE Concern") {
        console.log("Calling createConcernResponse...");
        const result = await createConcernResponse(selectedItem.id, {
          response_text: pscComment,
          action_taken: "psc_directive",
          responded_by: currentUser?.id || currentUser?.pk || currentUser?.user_id || currentUser?.sub,
        });
        console.log("Concern response created:", result);
      } else if (selectedItem.type === "Audit Finding") {
        console.log("Calling respondAuditFinding...");
        const result = await respondAuditFinding(selectedItem.id, {
          response: pscComment,
          action_taken: "psc_directive",
        });
        console.log("Audit finding response created:", result);
      }
      alert("PSC comment added successfully! RMT has been notified.");
      setPscComment("");
      setSelectedItem(null);
      void loadData();
      window.dispatchEvent(new CustomEvent("rbf-notifications-refresh"));
    } catch (err) {
      console.error("Failed to add PSC comment:", err);
      alert("Failed to add comment. Please try again.");
    } finally {
      setSubmittingComment(false);
    }
  };

  const handleResolve = async () => {
    if (!selectedItem) return;
    setSubmittingComment(true);
    try {
      if (selectedItem.type === "DoE Concern") {
        await updateConcern(selectedItem.id, { status: "resolved" });
      } else if (selectedItem.type === "Audit Finding") {
        await updateAuditFinding(selectedItem.id, { status: "resolved" });
      }
      alert("Issue has been marked as RESOLVED by PSC!");
      setSelectedItem(null);
      void loadData();
    } catch (err) {
      console.error("Failed to resolve:", err);
      alert("Failed to resolve. Please try again.");
    } finally {
      setSubmittingComment(false);
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading PSC issues...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">⚠ Items Requiring Your Attention</h1>
          <p className="text-sm text-slate-500">Audit findings and escalated concerns requiring PSC oversight</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div className="rounded-xl bg-amber-50 p-4 border border-amber-200">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Audit Findings (Raised to PSC)</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{escalatedFindings.length}</p>
        </div>
        <div className="rounded-xl bg-rose-50 p-4 border border-rose-200">
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">DoE Concerns (Escalated)</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">{escalatedConcerns.length}</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-4 border border-slate-200">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Total Requiring Action</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{escalatedFindings.length + escalatedConcerns.length}</p>
        </div>
      </div>

      {escalatedFindings.length === 0 && escalatedConcerns.length === 0 ? (
        <div className="card p-10 text-center text-slate-500">
          <CheckCircle2 size={48} className="mx-auto mb-4 text-emerald-500" />
          No issues require your attention at this time.
        </div>
      ) : (
        <div className="space-y-6">
          {escalatedFindings.length > 0 && (
            <div className="card p-6 border-l-4 border-amber-500">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <FileText size={20} className="text-amber-600" />
                Audit Findings (Raised to PSC)
              </h3>
              <div className="space-y-3">
                {escalatedFindings.map((finding: any) => (
                  <div key={finding.id} className="p-4 rounded-xl border border-amber-200 bg-amber-50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-amber-900">{finding.id}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${getSeverityBadgeColor(finding.risk_level)}`}>
                          {getSeverityIcon(finding.risk_level)} {getSeverityLabel(finding.risk_level)}
                        </span>
                        {finding.linked_project && (
                          <span className="text-xs text-slate-500">— PRJ-{finding.linked_project}</span>
                        )}
                      </div>
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${finding.status === "resolved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {finding.status?.replace(/_/g, " ") || "Open"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2 line-clamp-2">{finding.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                      <span>Raised by: Auditor</span>
                      <span>{formatDateTime(finding.created_at)}</span>
                    </div>
                    <button
                      onClick={() => setSelectedItem({ ...finding, type: "Audit Finding", category: finding.finding_category, severity: finding.risk_level, project: finding.linked_project ? projectMap[finding.linked_project] : null })}
                      className="btn-secondary text-xs"
                    >
                      View Full Finding
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {escalatedConcerns.length > 0 && (
            <div className="card p-6 border-l-4 border-rose-500">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <AlertTriangle size={20} className="text-rose-600" />
                DoE Concerns Escalated to PSC
              </h3>
              <div className="space-y-3">
                {escalatedConcerns.map((concern: any) => (
                  <div key={concern.id} className="p-4 rounded-xl border border-rose-200 bg-rose-50">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-rose-900">{concern.id}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${getSeverityBadgeColor(concern.severity)}`}>
                          {getSeverityIcon(concern.severity)} {getSeverityLabel(concern.severity)}
                        </span>
                        {concern.linked_project && (
                          <span className="text-xs text-slate-500">— PRJ-{concern.linked_project}</span>
                        )}
                      </div>
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${concern.status === "resolved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                        {concern.status?.replace(/_/g, " ") || "Open"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2 line-clamp-2">{concern.description}</p>
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                      <span>Raised by: {concern.raised_by_username || "DoE"}</span>
                      <span>{formatDateTime(concern.created_at)}</span>
                    </div>
                    <button
                      onClick={() => setSelectedItem({ ...concern, type: "DoE Concern", project: concern.linked_project ? projectMap[concern.linked_project] : null })}
                      className="btn-secondary text-xs"
                    >
                      View Full Detail
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {selectedItem && (
        <PscIssueDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          pscComment={pscComment}
          setPscComment={setPscComment}
          onAddComment={handleAddPscComment}
          onResolve={handleResolve}
          submitting={submittingComment}
        />
      )}
    </div>
  );
}

function PscIssueDetailModal({ item, onClose, pscComment, setPscComment, onAddComment, onResolve, submitting }: {
  item: any;
  onClose: () => void;
  pscComment: string;
  setPscComment: (v: string) => void;
  onAddComment: () => void;
  onResolve: () => void;
  submitting: boolean;
}) {
  const isAuditFinding = item.type === "Audit Finding";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl shadow-xl max-h-[90vh] flex flex-col">
        <div className={`text-white px-6 py-4 rounded-t-2xl flex-shrink-0 ${isAuditFinding ? "bg-amber-600" : "bg-rose-600"}`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold flex items-center gap-2">
                {isAuditFinding ? "AUDIT FINDING" : "CONCERN DETAIL"} — {item.id}
              </h3>
              <p className="text-white/80 text-sm mt-1">
                {isAuditFinding ? item.category : item.concern_type?.replace(/_/g, " ") || "DoE Concern"}
              </p>
            </div>
            <button onClick={onClose} className="text-white/80 hover:text-white">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">{isAuditFinding ? "FINDING" : "CONCERN"} INFORMATION</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Finding ID" : "Concern ID"}</p>
                <p className="font-medium">{item.id}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Risk Level" : "Severity"}</p>
                <p className={`font-medium px-2 py-0.5 rounded inline-flex items-center gap-1 ${getSeverityBadgeColor(item.severity)}`}>
                  {getSeverityIcon(item.severity)} {getSeverityLabel(item.severity)}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Status</p>
                <p className="font-medium">{item.status?.replace(/_/g, " ") || "Open"}</p>
              </div>
              {item.project && (
                <div>
                  <p className="text-slate-500 text-xs">Linked Project</p>
                  <p className="font-medium flex items-center gap-1">
                    <Building2 size={14} />
                    {item.project.projectReference || `PRJ-${item.linked_project}`} — {item.project.vendorName || "Vendor"}
                  </p>
                </div>
              )}
              <div>
                <p className="text-slate-500 text-xs">Raised By</p>
                <p className="font-medium flex items-center gap-1">
                  <User size={14} />
                  {isAuditFinding ? "Auditor" : (item.raised_by_username || "DoE")}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Date Raised</p>
                <p className="font-medium flex items-center gap-1">
                  <Calendar size={14} />
                  {formatDate(item.date || item.created_at)}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">{isAuditFinding ? "FINDING DESCRIPTION" : "DESCRIPTION"}</h4>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.description}"</p>
          </div>

          {isAuditFinding && item.recommended_action && (
            <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
              <h4 className="text-xs font-bold uppercase text-amber-700 mb-3">RECOMMENDED ACTION (by Auditor)</h4>
              <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.recommended_action}"</p>
            </div>
          )}

          {(item.responses && item.responses.length > 0) ? (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">RMT INVESTIGATION RESPONSE</h4>
              <div className="space-y-3">
                {item.responses.map((resp: any, idx: number) => (
                  <div key={idx} className="bg-white rounded-lg p-3 border border-slate-200">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">RMT Response</span>
                      <span className="text-xs text-slate-500">{formatDateTime(resp.created_at)}</span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2">{resp.response_text || resp.response}</p>
                    <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">
                      Action: {resp.action_taken?.replace(/_/g, " ") || "N/A"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
              <p className="text-sm text-amber-700">
                ⏳ RMT Response pending. You can request an update from RMT.
              </p>
            </div>
          )}

          <div className="bg-purple-50 rounded-xl p-4 border border-purple-200">
            <h4 className="text-xs font-bold uppercase text-purple-700 mb-3 flex items-center gap-2">
              <Shield size={14} /> PSC CAN:
            </h4>
            <ul className="text-sm text-slate-600 space-y-1">
              <li>✅ View finding details</li>
              <li>✅ View RMT investigation response</li>
              <li>✅ Add PSC comment/directive below</li>
              <li>✅ Request RMT provide update by deadline</li>
              <li>✅ Resolve escalated concerns (this one!)</li>
              <li className="text-slate-400">❌ Close audit findings (only Auditor can close)</li>
            </ul>
          </div>

          <div className="border-t pt-4">
            <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
              <MessageSquare size={16} />
              Add PSC Comment / Directive
            </h4>
            <textarea
              className="input-field min-h-[100px]"
              placeholder="Enter your directive, comment, or request for RMT update..."
              value={pscComment}
              onChange={(e) => setPscComment(e.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-between items-center px-6 py-4 border-t bg-slate-50 flex-shrink-0">
          <p className="text-xs text-slate-500">
            {isAuditFinding ? "Note: PSC can resolve escalated audit findings." : "Note: PSC can resolve escalated DoE concerns."}
          </p>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-secondary">Close</button>
            {item.status !== "resolved" && (
              <button
                onClick={onResolve}
                className="btn-primary flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700"
                disabled={submitting}
              >
                {submitting ? <RefreshCw size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                Mark as Resolved
              </button>
            )}
            <button
              onClick={onAddComment}
              className="btn-primary flex items-center gap-2"
              disabled={submitting || !pscComment.trim()}
            >
              {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              Add PSC Comment
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PscDashboard({ currentUser }: { currentUser?: any }) {
  return (
    <MacroKpiPortal
      title="Project Steering Committee"
      description="Macro portfolio monitoring for national progress, inclusion compliance, payment pacing, and system alerts."
    />
  );
}

export function PscReports({ currentUser }: { currentUser?: any }) {
  return <PscIssuesView currentUser={currentUser} />;
}