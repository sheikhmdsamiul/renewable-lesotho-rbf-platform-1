import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  RefreshCw,
  TrendingUp,
} from "lucide-react";
import { fetchTenderBids, fetchPaymentClaims } from "../api";

export function TacDashboard({ currentUser }: { currentUser: any }) {
  const [loading, setLoading] = useState(true);
  const [bids, setBids] = useState<any[]>([]);
  const [claims, setClaims] = useState<any[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [bidsData, claimsData] = await Promise.all([
        fetchTenderBids(),
        fetchPaymentClaims(),
      ]);
      setBids(bidsData);
      setClaims(claimsData);
    } catch (err) {
      console.error("Failed to load TAC data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const summary = useMemo(() => {
    const pendingBids = bids.filter(b => b.status === "Submitted" || b.status === "Under Review").length;
    const pendingClaims = claims.filter(c => c.status === "RMT Approved" || c.status === "Verified").length;
    return {
      pendingBids,
      pendingClaims,
      projectsReviewed: 5,
    };
  }, [bids, claims]);

  const pendingItems = useMemo(() => {
    const bidItems = bids
      .filter(b => b.status === "Submitted" || b.status === "Under Review")
      .slice(0, 2)
      .map(b => ({ type: "Bid" as const, id: b.tender_reference || b.id, ref: b.tender_name || "Stage 2" }));
    
    const claimItems = claims
      .filter(c => c.status === "RMT Approved" || c.status === "Verified")
      .slice(0, 1)
      .map(c => ({ type: "Claim" as const, id: c.projectId, ref: `M${c.milestone_details?.milestoneNumber || 2}` }));
    
    return [...bidItems, ...claimItems];
  }, [bids, claims]);

  const recentActivity = useMemo(() => {
    return [
      { action: "Reviewed bid TND-000024 Stage 2", time: "2 hours ago" },
      { action: "Endorsed claim PRJ-001 M2", time: "5 hours ago" },
      { action: "Technical scoring complete", time: "1 day ago" },
    ];
  }, []);

  if (loading) {
    return (
      <div className="card p-10 text-center text-slate-500">
        <Loader2 size={24} className="animate-spin mx-auto mb-2" />
        Loading TAC dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">TAC Overview</h1>
          <p className="text-sm text-slate-500">Dashboard</p>
        </div>
        <button onClick={() => void loadData()} className="btn-secondary flex items-center gap-2">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Summary</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Bids awaiting TAC review</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{summary.pendingBids}</p>
          </div>
          <div className="rounded-xl bg-amber-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600">Claims awaiting TAC endorsement</p>
            <p className="mt-2 text-3xl font-bold text-amber-700">{summary.pendingClaims}</p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Projects reviewed this month</p>
            <p className="mt-2 text-3xl font-bold text-emerald-700">{summary.projectsReviewed}</p>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Pending Items</h3>
        <div className="space-y-3">
          {pendingItems.length === 0 && (
            <p className="text-slate-500">No pending items.</p>
          )}
          {pendingItems.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
              <div className="flex items-center gap-3">
                <FileText size={18} className="text-slate-400" />
                <span className="text-sm font-medium text-slate-700">
                  {item.type}: {item.id} {item.ref}
                </span>
              </div>
              <button className="btn-secondary text-xs">
                Review
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-900 mb-4">Recent Activity</h3>
        <div className="space-y-3">
          {recentActivity.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
              <div className="flex items-center gap-3">
                <CheckCircle2 size={18} className="text-emerald-500" />
                <span className="text-sm text-slate-700">{item.action}</span>
              </div>
              <span className="text-xs text-slate-400">{item.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}