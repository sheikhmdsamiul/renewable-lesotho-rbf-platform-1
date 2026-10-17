import React, { useState } from "react";
import { X } from "lucide-react";
import { resubmitInstallationReport } from "../api";
import { InstallationReport } from "../types";

type Props = {
  report: InstallationReport;
  onClose: () => void;
  onResubmitted: (updated: InstallationReport) => void;
};

// The API answers validation failures as {errors: {field: [messages]}} or {detail: "..."}.
function describeError(err: any): string {
  const payload = err?.detailPayload;
  if (payload?.errors && typeof payload.errors === "object") {
    return Object.values(payload.errors).flat().join(" ");
  }
  if (typeof payload?.detail === "string") return payload.detail;
  if (payload && typeof payload === "object") {
    const messages = Object.values(payload).flat().filter((v) => typeof v === "string");
    if (messages.length) return messages.join(" ");
  }
  return "Could not resubmit the installation. Please try again.";
}

// Vendor fixes a flagged installation and sends it back for another field-verification round.
// Only changed fields are sent; blank inputs keep the current value.
export default function InstallationCorrectionModal({ report, onClose, onResubmitted }: Props) {
  const [note, setNote] = useState("");
  const [serialNumber, setSerialNumber] = useState(report.serialNumber || "");
  const [beneficiaryId, setBeneficiaryId] = useState(report.beneficiaryId || "");
  const [beneficiaryName, setBeneficiaryName] = useState(report.beneficiaryName || "");
  const [beneficiaryPhone, setBeneficiaryPhone] = useState(report.beneficiaryPhone || "");
  const [meterId, setMeterId] = useState(report.meterId || "");
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [gpsStatus, setGpsStatus] = useState<string | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changed = (value: string, original?: string) => (value.trim() !== (original || "").trim() ? value : undefined);

  const captureGps = () => {
    if (!navigator.geolocation) {
      setGpsStatus("This device cannot capture GPS.");
      return;
    }
    setGpsStatus("Capturing location…");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGps({ lat: Number(position.coords.latitude.toFixed(6)), lng: Number(position.coords.longitude.toFixed(6)) });
        setGpsStatus(`Captured (accuracy ±${Math.round(position.coords.accuracy)} m). Capture it at the installation site.`);
      },
      () => setGpsStatus("Could not capture the location. Allow location access and try again."),
      { enableHighAccuracy: true, timeout: 20000 }
    );
  };

  const submit = async () => {
    if (note.trim().length < 10) {
      setError("Describe what you corrected (at least 10 characters).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await resubmitInstallationReport(report.id, {
        correctionNote: note.trim(),
        serialNumber: changed(serialNumber, report.serialNumber),
        beneficiaryId: changed(beneficiaryId, report.beneficiaryId),
        beneficiaryName: changed(beneficiaryName, report.beneficiaryName),
        beneficiaryPhone: changed(beneficiaryPhone, report.beneficiaryPhone),
        meterId: changed(meterId, report.meterId),
        gpsLat: gps?.lat,
        gpsLng: gps?.lng,
        photoFiles: photos,
      });
      onResubmitted(updated);
    } catch (err: any) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Correct and resubmit installation #{report.id}</h2>
            <p className="text-xs text-slate-500">
              {report.resubmissionsLeft} resubmission(s) left. A field verifier will visit again after you resubmit.
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-5 p-6">
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
            <p className="text-xs font-bold uppercase text-rose-700">Why it was flagged</p>
            <p className="mt-1">{report.latestFlagReason || "The field verifier did not record a reason. Contact the RBF Management Team if unclear."}</p>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="font-semibold text-slate-800">What did you correct? *</span>
            <textarea
              className="input-field min-h-[90px]"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="E.g. the serial number was mistyped; replaced the faulty battery and added new photos."
            />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              ["Serial number", serialNumber, setSerialNumber],
              ["Beneficiary ID", beneficiaryId, setBeneficiaryId],
              ["Beneficiary name", beneficiaryName, setBeneficiaryName],
              ["Beneficiary phone", beneficiaryPhone, setBeneficiaryPhone],
              ["Meter ID", meterId, setMeterId],
            ].map(([label, value, setter]) => (
              <label key={label as string} className="block space-y-1 text-sm">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label as string}</span>
                <input
                  className="input-field"
                  value={value as string}
                  onChange={(e) => (setter as React.Dispatch<React.SetStateAction<string>>)(e.target.value)}
                />
              </label>
            ))}
          </div>

          <div className="space-y-2 rounded-xl border border-slate-200 p-4 text-sm">
            <p className="font-semibold text-slate-800">Location (only if the recorded GPS was wrong)</p>
            <p className="text-xs text-slate-500">
              Current: {report.gpsLat.toFixed(6)}, {report.gpsLng.toFixed(6)}
              {gps ? ` → new: ${gps.lat}, ${gps.lng}` : ""}
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={captureGps} className="btn-secondary text-xs">Capture current location</button>
              {gps && (
                <button type="button" onClick={() => { setGps(null); setGpsStatus(null); }} className="btn-secondary text-xs">
                  Keep original location
                </button>
              )}
            </div>
            {gpsStatus && <p className="text-xs text-slate-600">{gpsStatus}</p>}
          </div>

          <label className="block space-y-1 text-sm">
            <span className="font-semibold text-slate-800">Additional photos (added to the existing ones)</span>
            <input type="file" accept="image/*" multiple onChange={(e) => setPhotos(Array.from(e.target.files || []))} />
            {photos.length > 0 && <span className="block text-xs text-slate-500">{photos.length} photo(s) selected</span>}
          </label>

          {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

          <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
            <button onClick={onClose} className="btn-secondary text-sm" disabled={submitting}>Cancel</button>
            <button onClick={() => void submit()} className="btn-primary text-sm" disabled={submitting}>
              {submitting ? "Resubmitting..." : "Resubmit for verification"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
