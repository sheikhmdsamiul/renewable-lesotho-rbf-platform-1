import React, { useRef, useState } from "react";
import { FileText, Upload, X } from "lucide-react";

// Shared building blocks for the vendor registration and pre-qualification
// forms: labelled fields with linked help/error text, and a validated file drop.

export type FieldErrors = Record<string, string>;

/** Turn an API error (from `http`) into per-field messages plus a summary. */
export function apiFieldErrors(err: any, fallback: string): { fields: FieldErrors; message: string } {
  const payload = err?.detailPayload;
  const fields: FieldErrors = {};
  let message = "";
  if (payload && typeof payload === "object") {
    for (const [key, value] of Object.entries(payload)) {
      const text = Array.isArray(value) ? value.map(String).join(" ") : typeof value === "string" ? value : "";
      if (!text) continue;
      if (key === "detail" || key === "non_field_errors") message = text;
      else fields[key] = text;
    }
  }
  if (!message) {
    const raw = String(err?.message || "").replace(/^HTTP \d+ [^:]*:\s*/, "");
    if (/failed to fetch|networkerror|load failed/i.test(raw)) message = "Cannot reach the server. Check your connection and try again.";
    else if (Object.keys(fields).length) message = "Please correct the highlighted fields.";
    else message = raw && !raw.trim().startsWith("{") && raw.length < 300 ? raw : fallback;
  }
  return { fields, message };
}

type FieldProps = {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  help?: React.ReactNode;
  className?: string;
  children: (aria: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby"?: string;
    "aria-required"?: boolean;
  }) => React.ReactNode;
};

export function Field({ id, label, required, error, help, className = "", children }: FieldProps) {
  const describedBy = [help ? `${id}-help` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`space-y-1 ${className}`}>
      <label htmlFor={id} className="ml-1 text-sm font-bold text-slate-700">
        {label}
        {required && <span className="text-rose-600"> *</span>}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": describedBy, "aria-required": required || undefined })}
      {help && !error && <p id={`${id}-help`} className="ml-1 text-xs text-slate-500">{help}</p>}
      {error && <p id={`${id}-error`} role="alert" className="ml-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}

export const inputClass = (error?: string) =>
  `input-field ${error ? "border-rose-400 focus:border-rose-500 focus:ring-rose-200" : ""}`;

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

type FileDropProps = {
  id: string;
  label: string;
  required?: boolean;
  accept: string[]; // extensions without dot, e.g. ["pdf", "png"]
  maxMb: number;
  file: File | null;
  existingUrl?: string | null;
  error?: string;
  onChange: (file: File | null, error?: string) => void;
};

/** Click or drag-and-drop file picker that checks type and size before upload. */
export function FileDrop({ id, label, required, accept, maxMb, file, existingUrl, error, onChange }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const acceptText = accept.filter((ext) => ext !== "jpeg").map((ext) => ext.toUpperCase()).join(", ");

  const pick = (candidate: File | null | undefined) => {
    if (!candidate) return;
    const extension = candidate.name.includes(".") ? candidate.name.split(".").pop()!.toLowerCase() : "";
    if (!accept.includes(extension)) {
      onChange(null, `${label}: only ${acceptText} files are accepted.`);
      return;
    }
    if (candidate.size > maxMb * 1024 * 1024) {
      onChange(null, `${label}: file is ${formatSize(candidate.size)}; the limit is ${maxMb} MB.`);
      return;
    }
    if (candidate.size === 0) {
      onChange(null, `${label}: the file is empty.`);
      return;
    }
    onChange(candidate);
  };

  return (
    <div className="space-y-1">
      <p id={`${id}-label`} className="ml-1 text-sm font-bold text-slate-700">
        {label}
        {required && <span className="text-rose-600"> *</span>}
      </p>
      <input
        ref={inputRef}
        id={id}
        type="file"
        className="sr-only"
        tabIndex={-1}
        accept={accept.map((ext) => `.${ext}`).join(",")}
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files?.[0]); }}
        className={`rounded-xl border-2 border-dashed p-4 transition-colors ${
          error ? "border-rose-400 bg-rose-50/40" : dragging ? "border-emerald-500 bg-emerald-50" : "border-slate-200 bg-slate-50"
        }`}
      >
        {file ? (
          <div className="flex items-center gap-3">
            <FileText className="shrink-0 text-emerald-600" size={22} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-800">{file.name}</p>
              <p className="text-xs text-slate-500">{formatSize(file.size)}</p>
            </div>
            <button type="button" onClick={() => onChange(null)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200" aria-label={`Remove ${label}`}>
              <X size={16} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            aria-labelledby={`${id}-label`}
            aria-describedby={error ? `${id}-error` : `${id}-hint`}
            className="flex w-full flex-col items-center gap-1 py-2 text-center"
          >
            <Upload className="text-slate-400" size={22} />
            <span className="text-sm font-medium text-slate-700">Choose a file or drag it here</span>
            <span id={`${id}-hint`} className="text-xs text-slate-500">{acceptText} · up to {maxMb} MB</span>
          </button>
        )}
        {!file && existingUrl && (
          <p className="mt-2 text-center text-xs text-slate-600">
            Current file on record:{" "}
            <a href={existingUrl} target="_blank" rel="noreferrer" className="font-semibold text-emerald-700 underline">view</a>
            {" "}— upload a new file only if you need to replace it.
          </p>
        )}
      </div>
      {error && <p id={`${id}-error`} role="alert" className="ml-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}

/** Lesotho-first mobile check mirroring the backend's normalize_mobile_number. */
export function mobileNumberError(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (!digits) return "Mobile number is required.";
  if (digits.length === 8) return /^[56]/.test(digits) ? "" : "A Lesotho mobile number starts with 5 or 6 (or include the country code).";
  if (digits.startsWith("266")) return /^266[56]\d{7}$/.test(digits) ? "" : "A Lesotho number is +266 followed by 8 digits starting with 5 or 6.";
  return digits.length >= 10 && digits.length <= 15 ? "" : "Enter a valid mobile number including the country code.";
}

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
