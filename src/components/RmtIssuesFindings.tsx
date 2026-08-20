import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  AlertCircle,
  Flag,
  FileText,
  Clock,
  User,
  MessageSquare,
  X,
  Download,
  ExternalLink,
  Paperclip,
  Send,
  Building2,
  MapPin,
  Calendar,
  Shield,
} from "lucide-react";
import { fetchConcerns, fetchAuditFindings, fetchProjects, fetchPaymentClaims, createConcernResponse, updateConcern, updateAuditFinding, respondAuditFinding } from "../api";
import { Project, PaymentClaim } from "../types";

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "N/A");

const formatDate = (value?: string | null) => {
  if (!value) return "N/A";
  const d = new Date(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const getSeverityIcon = (severity: string | undefined) => {
  if (severity === "critical") return <AlertCircle size={14} className="text-rose-600" />;
  if (severity === "high") return <AlertTriangle size={14} className="text-rose-500" />;
  if (severity === "medium") return <AlertTriangle size={14} className="text-orange-500" />;
  return <AlertCircle size={14} className="text-amber-500" />;
};

const getSeverityLabel = (severity: string | undefined) => {
  if (severity === "critical") return "CRITICAL";
  if (severity === "high") return "HIGH";
  if (severity === "medium") return "MEDIUM";
  return "LOW";
};

const getSeverityBadgeColor = (severity: string | undefined) => {
  if (severity === "critical") return "bg-rose-600 text-white";
  if (severity === "high") return "bg-rose-500 text-white";
  if (severity === "medium") return "bg-orange-500 text-white";
  return "bg-amber-400 text-amber-900";
};

export default function RmtIssuesFindings({ currentUser }: { currentUser?: any }) {
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [concerns, setConcerns] = useState<any[]>([]);
  const [findings, setFindings] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [filterType, setFilterType] = useState("all");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [filterProject, setFilterProject] = useState("all");
  const [filterStatus, setFilterStatus] = useState("all");
  const [activeTab, setActiveTab] = useState("open");
  const [selectedItem, setSelectedItem] = useState<any>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const timestamp = Date.now();
      const [concernsData, findingsData, projList, claimsData] = await Promise.all([
        fetchConcerns(),
        fetchAuditFindings(),
        fetchProjects(),
        fetchPaymentClaims(),
      ]);
      console.log("Load completed at:", timestamp);
      console.log("Fetched concerns after refresh:", concernsData);
      console.log("Concern statuses:", concernsData.map((c: any) => ({ id: c.id, status: c.status })));
      setConcerns(concernsData);
      console.log("Concern data loaded, first concern responses:", concernsData[0]?.responses);
      setFindings(findingsData);
      setProjects(projList);
      setClaims(claimsData);
    } catch (err) {
      console.error("Failed to load issues and findings:", err);
    } finally {
      setLoading(false);
      setRefreshKey(k => k + 1);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const allItems = useMemo(() => {
    const mappedConcerns = concerns.map((c: any) => ({
      id: c.id,
      type: "DoE Concern",
      category: c.concernType || c.concern_type,
      severity: c.severity,
      status: c.status,
      linked_project: c.linkedProject || c.linked_project,
      linked_project_ref: c.linkedProjectName || c.linked_project_ref,
      linked_project_vendor: c.linkedProjectVendor || c.linked_project_vendor,
      linked_project_district: c.linkedProjectDistrict || c.linked_project_district,
      linked_claim: c.linkedClaim || c.linked_claim,
      linked_installation: c.linkedInstallation || c.linked_installation,
      raised_by: c.raisedByUsername || c.raised_by_username,
      raised_by_name: c.raisedByUsername || c.raised_by_username,
      raised_by_role: c.raisedByRole || c.raised_by_role,
      raised_by_region: c.raisedByRegion || c.raised_by_region,
      date: c.createdAt || c.created_at,
      description: c.description,
      evidence_files: c.evidenceFiles || c.evidence_files || [],
      notify_rmt: c.notify_rmt,
      notify_psc: c.notify_psc,
      responses: c.responses || [],
    }));

const mappedFindings = findings.map((f: any) => {
      const responses = f.responses || [];
      
      if (f.rmtResponse || f.rmt_response) {
        responses.push({
          respondedByUsername: f.rmtRespondedByUsername || f.rmt_responded_by_username || "RMT",
          respondedByRole: "RBF Official",
          response_text: f.rmtResponse || f.rmt_response,
          action_taken: f.rmtActionTaken || f.rmt_action_taken || "under_investigation",
          created_at: f.rmtRespondedAt || f.rmt_responded_at,
        });
      }
      
      if (f.pscComment || f.psc_comment) {
        responses.push({
          respondedByUsername: "PSC",
          respondedByRole: "Project Steering Committee",
          response_text: f.pscComment || f.psc_comment,
          action_taken: "psc_directive",
          created_at: f.pscCommentedAt || f.psc_commented_at,
        });
      }
      
      return {
        id: f.id,
        type: "Audit Finding",
        category: f.findingCategory || f.finding_category,
        severity: f.riskLevel || f.risk_level,
        status: f.status,
        linked_project: f.linkedProject || f.linked_project,
        linked_project_ref: f.linkedProjectName || f.linked_project_ref,
        linked_project_vendor: f.linkedProjectVendor || f.linked_project_vendor,
        linked_project_district: f.linkedProjectDistrict || f.linked_project_district,
        linked_claim: f.linkedClaim || f.linked_claim,
        linked_installation: f.linkedInstallation || f.linked_installation,
        raised_by: f.raisedByUsername || f.raised_by_username,
        raised_by_name: f.raisedByUsername || f.raised_by_username,
        raised_by_role: f.raisedByRole || f.raised_by_role,
        raised_by_region: f.raisedByRegion || f.raised_by_region,
        date: f.createdAt || f.created_at,
        description: f.description,
        recommended_action: f.recommendedAction || f.recommended_action,
        evidence_files: f.evidenceFiles || f.evidence_files || [],
        responses: responses,
        also_notified_psc: f.pscNotified || f.notify_psc,
      };
    });

    return [...mappedConcerns, ...mappedFindings];
  }, [concerns, findings]);

  const filteredItems = useMemo(() => {
    let items = allItems;
    
    if (activeTab === "doe") items = items.filter((i: any) => i.type === "DoE Concern");
    else if (activeTab === "audit") items = items.filter((i: any) => i.type === "Audit Finding");
    else if (activeTab === "resolved") items = items.filter((i: any) => i.status === "resolved");
    else if (activeTab === "open") items = items.filter((i: any) => i.status !== "resolved");
    // "all" shows everything

    console.log("Filtering:", { activeTab, totalItems: allItems.length, filteredCount: items.length, statuses: items.map((i: any) => i.status) });

    if (filterType !== "all") {
      items = items.filter((item: any) => {
        if (filterType === "doe") return item.type === "DoE Concern";
        if (filterType === "audit") return item.type === "Audit Finding";
        return true;
      });
    }
    if (filterSeverity !== "all") {
      items = items.filter((item: any) => item.severity === filterSeverity);
    }
    if (filterProject !== "all") {
      items = items.filter((item: any) => item.linked_project === parseInt(filterProject));
    }
    if (filterStatus !== "all") {
      items = items.filter((item: any) => item.status === filterStatus);
    }
    return items;
  }, [allItems, activeTab, filterType, filterSeverity, filterProject, filterStatus]);

  const openItems = allItems.filter((i: any) => i.status !== "resolved");
  const resolvedThisWeek = allItems.filter((i: any) => {
    if (i.status !== "resolved") return false;
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    return new Date(i.date) > weekAgo;
  });
  const urgentItems = allItems.filter((i: any) => i.status !== "resolved" && (i.severity === "critical" || i.severity === "high"));

  const projectMap = useMemo(() => {
    const map: Record<string, any> = {};
    projects.forEach((p: Project) => {
      map[p.id] = p;
    });
    return map;
  }, [projects]);

  const claimMap = useMemo(() => {
    const map: Record<string, any> = {};
    claims.forEach((c: PaymentClaim) => {
      map[c.id] = c;
    });
    return map;
  }, [claims]);

  const getProjectDisplay = (item: any) => {
    if (!item.linked_project) return "—";
    const proj = projectMap[item.linked_project];
    return proj ? `${proj.projectReference} — ${proj.vendor?.name || "Vendor"}` : `PRJ-${item.linked_project}`;
  };

  const handleRespond = async (item: any, response: string, action: string) => {
    try {
      let newStatus = item.status;
      let escalationMessage = "";
      let resolutionMessage = "";
      
      const concernResolvedActions = ["resolved", "dismissed", "action_initiated"];
      const auditFindingResolvedActions = [
        "evidence_reviewed_no_issue", 
        "issue_confirmed_corrective",
        "issue_confirmed_suspend",
        "issue_confirmed_blacklist",
        "referred_legal"
      ];
      
      if (item.type === "DoE Concern") {
        console.log("=== HANDLING CONCERN ===");
        console.log("Item ID:", item.id, "Item status:", item.status);
        console.log("Action selected:", action);
        console.log("Creating concern response for:", item.id, "action:", action);
        
        await createConcernResponse(item.id, {
          response_text: response,
          action_taken: action,
          responded_by: currentUser?.id || currentUser?.pk || currentUser?.user_id || currentUser?.sub,
        });
        console.log("Concern response created, now updating status...");
        
        if (concernResolvedActions.includes(action)) {
          newStatus = "resolved";
          if (action === "resolved") {
            resolutionMessage = " Concern has been marked as RESOLVED.";
          } else if (action === "dismissed") {
            resolutionMessage = " Concern has been DISMISSED.";
          } else if (action === "action_initiated") {
            resolutionMessage = " Concern - Action Initiated.";
          }
        } else if (action === "under_investigation") {
          newStatus = "under_investigation";
          resolutionMessage = " Concern is now under investigation.";
        } else if (action === "escalated_to_psc") {
          newStatus = "escalated_to_psc";
          escalationMessage = " Concern has been escalated to PSC.";
        }
        
        console.log("PATCH concern with status:", newStatus, "item.notify_psc:", item.notify_psc);
        
        try {
          const result = await updateConcern(item.id, {
            status: newStatus,
            notify_psc: action === "escalated_to_psc" ? true : item.notify_psc
          });
          console.log("PATCH succeeded, new status from API:", result.status);
        } catch (err: any) {
          console.error("PATCH failed:", err?.message || err);
        }
      } else {
        await respondAuditFinding(item.id, { response, action_taken: action });
        
        if (auditFindingResolvedActions.includes(action)) {
          await updateAuditFinding(item.id, { status: "resolved" });
          if (action === "evidence_reviewed_no_issue") {
            resolutionMessage = " Finding - Evidence Reviewed, No Issue Found.";
          } else if (action === "issue_confirmed_corrective") {
            resolutionMessage = " Finding - Issue Confirmed, Corrective Action Initiated.";
          } else if (action === "issue_confirmed_suspend") {
            resolutionMessage = " Finding - Issue Confirmed, Payment Suspended.";
          } else if (action === "issue_confirmed_blacklist") {
            resolutionMessage = " Finding - Issue Confirmed, Blacklist Initiated.";
          } else if (action === "referred_legal") {
            resolutionMessage = " Finding has been referred to Legal/External Authority.";
          }
        } else if (action === "escalated_to_psc") {
          escalationMessage = " Finding has been escalated to PSC.";
        }
      }
      
      let successMessage = "Response submitted successfully!";
      if (resolutionMessage) {
        successMessage = resolutionMessage;
      } else if (escalationMessage) {
        successMessage += escalationMessage;
      }
      
      alert(successMessage);
      console.log("Submit complete, now refreshing data...");
      setSelectedItem(null);
      void loadData().then(() => console.log("Data refresh complete"));
    } catch (err) {
      console.error("Failed to submit response:", err);
      alert("Failed to submit response. Please try again.");
    }
  };

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <RefreshCw size={24} className="animate-spin mx-auto mb-2" />
        Loading issues and findings...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Issues & Findings</h1>
          <p className="text-sm text-slate-500">Central management for all raised concerns and audit findings</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl bg-slate-800 p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Open Total</p>
          <p className="mt-2 text-3xl font-bold text-white">{openItems.length}</p>
        </div>
        <div className="rounded-xl bg-rose-50 p-4 border border-rose-200">
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600">DoE Concerns</p>
          <p className="mt-2 text-3xl font-bold text-rose-700">{concerns.filter(c => c.status !== "resolved").length}</p>
        </div>
        <div className="rounded-xl bg-amber-50 p-4 border border-amber-200">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Audit Findings</p>
          <p className="mt-2 text-3xl font-bold text-amber-700">{findings.filter(f => f.status !== "resolved").length}</p>
        </div>
        <div className="rounded-xl bg-emerald-50 p-4 border border-emerald-200">
          <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Resolved This Week</p>
          <p className="mt-2 text-3xl font-bold text-emerald-700">{resolvedThisWeek.length}</p>
        </div>
      </div>

      {urgentItems.length > 0 && (
        <div className="card p-6 border-2 border-rose-500 bg-rose-50/50">
          <h3 className="text-lg font-bold text-rose-700 mb-4 flex items-center gap-2">
            <AlertTriangle size={20} />
            URGENT ITEMS (High + Critical)
          </h3>
          <div className="space-y-3">
            {urgentItems.map((item: any) => (
              <div key={item.id} className="flex items-start gap-4 p-4 bg-white rounded-xl border border-rose-200">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-50">{getSeverityIcon(item.severity)}</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-rose-900">{item.id}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${getSeverityBadgeColor(item.severity)}`}>
                      {getSeverityLabel(item.severity)}
                    </span>
                    <span className="text-slate-500 text-sm">{item.linked_project ? `— PRJ-${item.linked_project}` : ""}</span>
                  </div>
                  <p className="text-sm text-slate-700">
                    {item.type === "Audit Finding" ? item.recommended_action || item.description : item.description}
                  </p>
                  <p className="text-xs text-slate-500 mt-2">
                    Raised by: {item.raised_by_name || item.raised_by} — {formatDate(item.date)}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedItem(item)}
                  className="btn-secondary text-sm whitespace-nowrap"
                >
                  View & Respond
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveTab("open")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            activeTab === "open" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          Open ({openItems.length})
        </button>
        <button
          onClick={() => setActiveTab("all")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            activeTab === "all" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          All
        </button>
        <button
          onClick={() => setActiveTab("doe")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            activeTab === "doe" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          DoE Concerns ({concerns.filter(c => c.status !== "resolved").length})
        </button>
        <button
          onClick={() => setActiveTab("audit")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            activeTab === "audit" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          Audit Findings ({findings.filter(f => f.status !== "resolved").length})
        </button>
        <button
          onClick={() => setActiveTab("resolved")}
          className={`px-4 py-2 rounded-xl text-sm font-medium ${
            activeTab === "resolved" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          Resolved ({allItems.filter(i => i.status === "resolved").length})
        </button>
      </div>

      <div className="card p-6" key={refreshKey}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 bg-slate-100 rounded-lg px-3 py-2">
              <Search size={16} className="text-slate-500" />
              <input
                type="text"
                className="bg-transparent outline-none text-sm placeholder-slate-500"
                placeholder="Search by ID or project..."
              />
            </div>
            <select
              className="bg-slate-100 rounded-lg px-3 py-2 text-sm outline-none"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="all">Type: All</option>
              <option value="doe">DoE Concerns</option>
              <option value="audit">Audit Findings</option>
            </select>
            <select
              className="bg-slate-100 rounded-lg px-3 py-2 text-sm outline-none"
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
            >
              <option value="all">Severity: All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select
              className="bg-slate-100 rounded-lg px-3 py-2 text-sm outline-none"
              value={filterProject}
              onChange={(e) => setFilterProject(e.target.value)}
            >
              <option value="all">Project: All</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.projectReference}</option>
              ))}
            </select>
            <select
              className="bg-slate-100 rounded-lg px-3 py-2 text-sm outline-none"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="all">Status: All</option>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="escalated_to_psc">Escalated to PSC</option>
            </select>
          </div>
          <button className="btn-secondary flex items-center gap-2 text-sm">
            <FileText size={16} /> Export Issues Report
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">ID</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Type</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Project</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Raised By</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Severity</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Status</th>
                <th className="px-4 py-3 text-xs font-bold uppercase text-slate-500">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    No issues or findings found.
                  </td>
                </tr>
              ) : (
                filteredItems.map((item: any) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">{item.id}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        item.type === "Audit Finding" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"
                      }`}>
                        {item.type === "Audit Finding" ? "Audit" : "DoE"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {item.linked_project ? getProjectDisplay(item) : "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {item.raised_by_name || item.raised_by}
                      {item.type === "Audit Finding" && " (Auditor)"}
                      {item.type === "DoE Concern" && " (DoE)"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold flex items-center gap-1 w-fit ${
                        item.severity === "critical" ? "bg-rose-600 text-white" :
                        item.severity === "high" ? "bg-rose-500 text-white" :
                        item.severity === "medium" ? "bg-orange-500 text-white" :
                        "bg-amber-400 text-amber-900"
                      }`}>
                        <span>{getSeverityIcon(item.severity)}</span>
                        {getSeverityLabel(item.severity)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                        item.status === "resolved" ? "bg-emerald-100 text-emerald-700" :
                        item.status === "escalated_to_psc" ? "bg-purple-100 text-purple-700" :
                        "bg-amber-100 text-amber-700"
                      }`}>
                        {item.status === "open" ? "Open" : item.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setSelectedItem(item)}
                        className="text-emerald-600 hover:text-emerald-700 text-xs font-medium"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedItem && (
        <RmtIssueDetail
          item={selectedItem}
          project={selectedItem.linked_project ? projectMap[selectedItem.linked_project] : null}
          claim={selectedItem.linked_claim ? claimMap[selectedItem.linked_claim] : null}
          onClose={() => setSelectedItem(null)}
          onRespond={(response, action) => handleRespond(selectedItem, response, action)}
        />
      )}
    </div>
  );
}

function RmtIssueDetail({ item, project, claim, onClose, onRespond }: { item: any; project: any; claim: any; onClose: () => void; onRespond: (response: string, action: string) => void }) {
  const [responseText, setResponseText] = useState("");
  const [actionTaken, setActionTaken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  console.log("RmtIssueDetail received item:", item);

  const isAuditFinding = item.type === "Audit Finding";

  const handleSubmit = async () => {
    if (!responseText.trim() || !actionTaken) {
      alert("Please provide a response and select an action.");
      return;
    }
    setSubmitting(true);
    try {
      await onRespond(responseText, actionTaken);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl shadow-xl max-h-[90vh] flex flex-col">
        <div className="bg-slate-800 text-white px-6 py-4 rounded-t-2xl flex-shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold flex items-center gap-2">
                {isAuditFinding ? "AUDIT FINDING" : "CONCERN DETAIL"} — {item.id}
              </h3>
              <p className="text-slate-300 text-sm mt-1">
                {isAuditFinding ? item.category : item.category || "DoE Concern"}
              </p>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-white">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">{isAuditFinding ? "FINDING INFORMATION" : "CONCERN INFORMATION"}</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Finding ID" : "Concern ID"}</p>
                <p className="font-medium">{item.id}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Type</p>
                <p className="font-medium">{isAuditFinding ? "Audit Finding" : "DoE Concern"}</p>
              </div>
              {!isAuditFinding && (
                <div>
                  <p className="text-slate-500 text-xs">Category</p>
                  <p className="font-medium">{item.category?.replace(/_/g, " ") || "—"}</p>
                </div>
              )}
              <div>
                <p className="text-slate-500 text-xs">{isAuditFinding ? "Risk Level" : "Severity"}</p>
                <p className={`font-medium px-2 py-0.5 rounded inline-flex items-center gap-1 ${
                  item.severity === "critical" ? "bg-rose-600 text-white" :
                  item.severity === "high" ? "bg-rose-500 text-white" :
                  item.severity === "medium" ? "bg-orange-500 text-white" :
                  "bg-amber-400 text-amber-900"
                }`}>
                  {getSeverityIcon(item.severity)} {getSeverityLabel(item.severity)}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Status</p>
                <p className="font-medium">{item.status === "open" ? "Open" : item.status.replace(/_/g, " ")}</p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Linked Project</p>
                <p className="font-medium">
                  {item.linked_project_ref ? (
                    <span className="flex items-center gap-1">
                      <Building2 size={14} />
                      {item.linked_project_ref}
                      {item.linked_project_vendor && ` — ${item.linked_project_vendor}`}
                      {item.linked_project_district && ` — ${item.linked_project_district}`}
                    </span>
                  ) : item.linked_project ? `PRJ-${item.linked_project}` : "—"}
                </p>
              </div>
              {claim && (
                <div>
                  <p className="text-slate-500 text-xs">Linked Claim</p>
                  <p className="font-medium">CLM-{claim.id}</p>
                </div>
              )}
              <div>
                <p className="text-slate-500 text-xs">Raised By</p>
                <p className="font-medium flex items-center gap-1">
                  <User size={14} />
                  {item.raised_by_name || item.raised_by}
                  {item.raised_by_role && ` (${item.raised_by_role}${item.raised_by_region ? ` — ${item.raised_by_region}` : ""})`}
                </p>
              </div>
              <div>
                <p className="text-slate-500 text-xs">Date Raised</p>
                <p className="font-medium flex items-center gap-1">
                  <Calendar size={14} />
                  {formatDate(item.date)}
                </p>
              </div>
              {!isAuditFinding && (
                <div>
                  <p className="text-slate-500 text-xs">Notified</p>
                  <p className="font-medium flex items-center gap-1">
                    {item.notify_rmt && <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 size={12} /> RMT</span>}
                    {item.notify_psc && <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 size={12} /> PSC</span>}
                    {!item.notify_rmt && !item.notify_psc && <span className="text-slate-400">—</span>}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4">
            <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">Description</h4>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.description}"</p>
          </div>

          {item.evidence_files && item.evidence_files.length > 0 && (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">Evidence Attached</h4>
              <div className="flex flex-wrap gap-2">
                {item.evidence_files.map((file: any, idx: number) => (
                  <button key={idx} className="flex items-center gap-2 px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                    <Download size={14} className="text-slate-500" />
                    {typeof file === 'string' ? file : file.name || `File ${idx + 1}`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {isAuditFinding && item.recommended_action && (
            <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
              <h4 className="text-xs font-bold uppercase text-amber-700 mb-3">Recommended Action (by Auditor)</h4>
              <p className="text-sm text-slate-700 whitespace-pre-wrap">"{item.recommended_action}"</p>
            </div>
          )}

          {(item.linked_project || item.linked_project_ref || claim) && (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">Linked Records</h4>
              <div className="flex flex-wrap gap-2">
                {item.linked_project && (
                  <>
                    <button 
                      onClick={() => {
                        const url = new URL(window.location.href);
                        url.searchParams.set("tab", "rbf_projects");
                        url.searchParams.set("projectId", String(item.linked_project));
                        url.searchParams.set("projectTab", "kpis");
                        window.location.href = url.toString();
                      }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50"
                    >
                      <ExternalLink size={14} /> View {item.linked_project_ref || `PRJ-${item.linked_project}`} KPI Dashboard
                    </button>
                    <button 
                      onClick={() => {
                        const url = new URL(window.location.href);
                        url.searchParams.set("tab", "gis");
                        url.searchParams.set("projectId", String(item.linked_project));
                        window.location.href = url.toString();
                      }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50"
                    >
                      <MapPin size={14} /> View on GIS Map
                    </button>
                    <button 
                      onClick={() => {
                        const url = new URL(window.location.href);
                        url.searchParams.set("tab", "rbf_projects");
                        url.searchParams.set("projectId", String(item.linked_project));
                        url.searchParams.set("projectTab", "installations");
                        window.location.href = url.toString();
                      }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50"
                    >
                      <FileText size={14} /> View Installation List
                    </button>
                  </>
                )}
                {claim && (
                  <button className="flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                    <FileText size={14} /> View Claim Details
                  </button>
                )}
              </div>
            </div>
          )}

          {item.responses && item.responses.length > 0 && (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-3">Response History</h4>
              <div className="space-y-3">
                {item.responses.map((resp: any, idx: number) => (
                  <div key={idx} className={`bg-white rounded-lg p-3 border ${
                    resp.action_taken === 'psc_directive' ? 'border-purple-300 bg-purple-50' : 'border-slate-200'
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">
                        {resp.respondedByUsername || resp.responder_name || "Unknown"}
                        {resp.respondedByRole && <span className="text-xs text-slate-500 ml-1">({resp.respondedByRole})</span>}
                        {resp.action_taken === 'psc_directive' && <span className="ml-2 px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">PSC</span>}
                      </span>
                      <span className="text-xs text-slate-500">{formatDateTime(resp.created_at)}</span>
                    </div>
                    <p className="text-sm text-slate-700 mb-2">{resp.response_text}</p>
                    {resp.action_taken && resp.action_taken !== 'psc_directive' && (
                      <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">
                        Action: {resp.action_taken?.replace(/_/g, " ")}
                      </span>
                    )}
                    {resp.action_taken === 'psc_directive' && (
                      <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                        PSC Directive
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="border-t pt-6">
            <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
              <MessageSquare size={16} />
              RMT Response {isAuditFinding && <span className="text-rose-500 text-xs">(Required)</span>}
            </h4>
            <textarea
              className="input-field min-h-[120px]"
              placeholder={isAuditFinding 
                ? "Provide your investigation findings and response..." 
                : "Type your response here..."}
              value={responseText}
              onChange={(e) => setResponseText(e.target.value)}
            />
          </div>

          <div className="mb-4">
            <h4 className="text-sm font-bold text-slate-900 mb-2">
              Action Taken {isAuditFinding && <span className="text-rose-500">*</span>}
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {isAuditFinding ? (
                <>
                  {["under_investigation", "evidence_reviewed_no_issue", "issue_confirmed_corrective", "issue_confirmed_suspend", "issue_confirmed_blacklist", "escalated_to_psc", "referred_legal"].map((action) => (
                    <button
                      key={action}
                      onClick={() => setActionTaken(action)}
                      className={`p-2 rounded-xl text-left border transition-all text-xs ${
                        actionTaken === action
                          ? "border-emerald-500 bg-emerald-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      {action === "under_investigation" && "○ Under Investigation"}
                      {action === "evidence_reviewed_no_issue" && "○ Evidence Reviewed — No Issue Found"}
                      {action === "issue_confirmed_corrective" && "○ Issue Confirmed — Corrective Action Initiated"}
                      {action === "issue_confirmed_suspend" && "○ Issue Confirmed — Payment Suspended"}
                      {action === "issue_confirmed_blacklist" && "○ Issue Confirmed — Blacklist Initiated"}
                      {action === "escalated_to_psc" && "○ Escalated to PSC for Decision"}
                      {action === "referred_legal" && "○ Referred to Legal / External Authority"}
                    </button>
                  ))}
                </>
              ) : (
                <>
                  {["under_investigation", "action_initiated", "resolved", "escalated_to_psc", "dismissed"].map((action) => (
                    <button
                      key={action}
                      onClick={() => setActionTaken(action)}
                      className={`p-2 rounded-xl text-left border transition-all text-xs ${
                        actionTaken === action
                          ? "border-emerald-500 bg-emerald-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      {action === "under_investigation" && "○ Under Investigation — still looking into it"}
                      {action === "action_initiated" && "○ Action Initiated — contacting vendor / FO"}
                      {action === "resolved" && "○ Resolved — issue has been addressed"}
                      {action === "escalated_to_psc" && "○ Escalated to PSC — requires PSC attention"}
                      {action === "dismissed" && "○ Dismissed — not a valid concern"}
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>

          {isAuditFinding && (
            <div className="bg-slate-50 rounded-xl p-4">
              <h4 className="text-xs font-bold uppercase text-slate-500 mb-2">Supporting Evidence (attach your investigation)</h4>
              <button className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-800">
                <Paperclip size={16} /> + Attach File
              </button>
              <p className="text-xs text-slate-400 mt-2">
                Note: Audit findings and RMT responses are permanently recorded and visible to Auditor.
              </p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t flex-shrink-0 bg-white">
            <button onClick={onClose} className="btn-secondary" disabled={submitting}>Cancel</button>
            <button
              onClick={handleSubmit}
              className="btn-primary flex items-center gap-2"
              disabled={submitting || !responseText.trim() || !actionTaken}
            >
              {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              Submit Response
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}