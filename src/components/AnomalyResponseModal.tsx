import React, { useState } from "react";
import { X } from "lucide-react";
import { respondToAnomalyFlag } from "../api";
import { AnomalyFlag } from "../types";

type Props = {
  flag: AnomalyFlag;
  onClose: () => void;
  onResponded: (updated: AnomalyFlag) => void;
};

const MAX_FILE_BYTES = 5 * 1024 * 1024;

// Vendor answers an RMT correction or evidence request. Missing the due date escalates the
// flag and holds the project's milestone payments.
export default function AnomalyResponseModal({ flag, onClose, onResponded }: Props) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const overdue = Boolean(flag.dueDate) && new Date(flag.dueDate as string).getTime() < Date.now();

  const submit = async () => {
    if (text.trim().length < 10) {
      setError("Describe what you did or what the evidence shows (at least 10 characters).");
      return;
    }
    const oversized = files.find((file) => file.size > MAX_FILE_BYTES);
    if (oversized) {
      setError(`"${oversized.name}" is larger than 5 MB.`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      onResponded(await respondToAnomalyFlag(flag.id, text.trim(), files));
    } catch (err: any) {
      const payload = err?.detailPayload;
      setError(payload?.detail || payload?.response || "Could not send the response. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Respond to anomaly #{flag.id}</h2>
            <p className="text-xs text-slate-500">
              {flag.status === "correction_requested" ? "Correction requested" : "Evidence requested"} by the RBF Management Team
              {flag.dueDate ? ` · due ${new Date(flag.dueDate).toLocaleDateString()}` : ""}
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4 p-6 text-sm">
          {overdue && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-red-700">
              This request is past its due date and will be escalated, holding your milestone payments. Respond as soon as possible.
            </p>
          )}
          <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 text-purple-900">
            <p className="text-xs font-bold uppercase text-purple-700">What the RMT asked for</p>
            {flag.correctiveAction && <p className="mt-1"><span className="font-semibold">Action:</span> {flag.correctiveAction}</p>}
            {flag.investigationNotes && <p className="mt-1"><span className="font-semibold">Notes:</span> {flag.investigationNotes}</p>}
            {!flag.correctiveAction && !flag.investigationNotes && <p className="mt-1">{flag.description || "See the flag details."}</p>}
          </div>

          <label className="block space-y-1">
            <span className="font-semibold text-slate-800">Your response *</span>
            <textarea
              className="input-field min-h-[110px]"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="E.g. the meter was offline during a grid outage on 3 May; it was reset on 5 May and the attached photo shows the current reading."
            />
          </label>

          <label className="block space-y-1">
            <span className="font-semibold text-slate-800">Evidence files (jpg, png, webp or pdf, up to 5 MB each)</span>
            <input type="file" accept=".jpg,.jpeg,.png,.webp,.pdf" multiple onChange={(e) => setFiles(Array.from(e.target.files || []))} />
            {files.length > 0 && <span className="block text-xs text-slate-500">{files.length} file(s) selected</span>}
          </label>

          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-rose-700">{error}</p>}

          <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
            <button onClick={onClose} className="btn-secondary text-sm" disabled={submitting}>Cancel</button>
            <button onClick={() => void submit()} className="btn-primary text-sm" disabled={submitting}>
              {submitting ? "Sending..." : "Send to RMT"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
