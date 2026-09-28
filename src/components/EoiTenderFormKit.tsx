/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

// Shared building blocks for the EOI Invite and Tender creation forms — styled to
// match the rest of the platform's existing design system (Inter font, slate/emerald
// Tailwind palette, the same .card/.input-field/.btn-primary/.badge classes used
// everywhere else), not the standalone mockup's custom look.

import React from "react";
import { Lock, Info, Upload, ChevronLeft } from "lucide-react";

// Kept as named exports (not literal Tailwind classes) so every call site that
// already does style={{ color: TEAL }} / style={{ background: AMBER }} keeps working
// unchanged — only the values below changed, to the system's real palette.
export const TEAL = "#059669"; // emerald-600 — the platform's one primary action color, used for Tender forms
export const TEAL_SOFT = "#ecfdf5"; // emerald-50
export const AMBER = "#4f46e5"; // indigo-600 — matches the existing "EOI Invite" badge color used elsewhere in the app
export const AMBER_SOFT = "#eef2ff"; // indigo-50
export const INK = "#0f172a"; // slate-900
export const INK_SUB = "#475569"; // slate-600
export const INK_FAINT = "#94a3b8"; // slate-400
export const LINE = "#e2e8f0"; // slate-200
export const BG = "#f8fafc"; // slate-50
export const SURFACE = "#ffffff";
export const LOCK_BG = "#f1f5f9"; // slate-100

export function FormKitShell({ children }: { children: React.ReactNode }) {
  return <div className="space-y-6 max-w-[90rem] mx-auto">{children}</div>;
}

export function Field({
  label,
  required,
  accent,
  badge,
  help,
  children,
}: {
  label: string;
  required?: boolean;
  accent: string;
  badge?: React.ReactNode;
  help?: { text: string; tone?: "legacy" };
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 mb-4">
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-sm font-bold text-slate-700">
          {label}
          {required && <span style={{ color: accent }}> *</span>}
        </label>
        {badge}
      </div>
      {children}
      {help && (
        <p className="text-xs" style={{ color: help.tone === "legacy" ? AMBER : "#94a3b8" }}>
          {help.text}
        </p>
      )}
    </div>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return <input {...rest} className={`input-field ${className || ""}`} />;
}
export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className, ...rest } = props;
  return <select {...rest} className={`input-field ${className || ""}`} />;
}
export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className, ...rest } = props;
  return <textarea rows={3} {...rest} className={`input-field ${className || ""}`} />;
}

// A real controlled multi-select, styled like every other technology/district
// checkbox-chip picker already used throughout the tender form.
export function Chips({
  items,
  selected,
  onToggle,
  accent,
}: {
  items: string[];
  selected: string[];
  onToggle: (item: string) => void;
  accent: string;
}) {
  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {items.map((item) => {
        const active = selected.includes(item);
        return (
          <label
            key={item}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-lg border border-slate-200 cursor-pointer hover:bg-slate-100"
          >
            <input
              type="checkbox"
              className="w-4 h-4 rounded"
              style={{ accentColor: accent }}
              checked={active}
              onChange={() => onToggle(item)}
            />
            <span className="text-sm font-medium">{item}</span>
          </label>
        );
      })}
    </div>
  );
}

export function UploadZone({
  label,
  fileName,
  onFileSelect,
  accept,
}: {
  label: string;
  fileName?: string | null;
  onFileSelect?: (file: File | null) => void;
  accept?: string;
}) {
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  return (
    <div
      className={`flex items-center gap-2 rounded-lg border border-dashed px-3 py-3 text-sm cursor-pointer hover:bg-slate-50 ${fileName ? "border-slate-300 text-slate-700" : "border-slate-300 text-slate-400"}`}
      onClick={() => inputRef.current?.click()}
    >
      <Upload size={14} />
      {fileName || label}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFileSelect?.(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

export function ToggleRow({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  id: string;
}) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        id={id}
        className="w-4 h-4 rounded text-emerald-600"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-sm font-medium text-slate-700">{label}</span>
    </label>
  );
}

export function Badge({ children, tone = "locked" }: { children: React.ReactNode; tone?: "locked" | "legacy" }) {
  const classes = tone === "locked" ? "bg-slate-100 text-slate-500" : "bg-indigo-50 text-indigo-700";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${classes}`}>
      {tone === "locked" && <Lock size={10} />}
      {children}
    </span>
  );
}

export function InfoBanner({ color, bg, children }: { color: string; bg: string; children: React.ReactNode }) {
  // color/bg still accepted (hex) for backward-compat with call sites, but rendered
  // via the system's existing banner pattern (rounded-xl, soft border, small icon).
  return (
    <div className="flex items-start gap-2 rounded-xl border px-4 py-3 mb-6 text-sm" style={{ background: bg, borderColor: bg, color }}>
      <Info size={16} className="mt-0.5 shrink-0" />
      <p>{children}</p>
    </div>
  );
}

export function Crumb({ onBack, trail }: { onBack: () => void; trail: string }) {
  return (
    <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-slate-500 hover:text-slate-900 mb-4 transition-colors">
      <ChevronLeft size={16} /> {trail}
    </button>
  );
}

export function StatusChip({ children, color, bg }: { children: React.ReactNode; color: string; bg: string }) {
  return (
    <span className="badge" style={{ color, background: bg }}>
      {children}
    </span>
  );
}
