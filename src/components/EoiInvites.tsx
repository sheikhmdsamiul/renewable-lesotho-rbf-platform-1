/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

// EOI Invites tab: its own list, create, and edit screens — completely separate from
// the Tender Management UI. (The detail/shortlist view lives in App.tsx as
// `EoiInviteDetail`, co-located with `TACView`, which it reuses directly — keeping
// that reuse in the same file avoids a circular import between this file and App.tsx.)

import React, { useEffect, useMemo, useState } from "react";
import { Plus, ArrowRight, Users } from "lucide-react";
import { Tender, TenderStatus } from "../types";
import { fetchTenders, createTender, updateTender, fetchTender, publishTender, fetchCurrenciesConfig } from "../api";
import {
  FormKitShell,
  Field,
  TextInput,
  Select,
  TextArea,
  Chips,
  UploadZone,
  Crumb,
  StatusChip,
  AMBER,
  AMBER_SOFT,
  INK_SUB,
  LOCK_BG,
} from "./EoiTenderFormKit";

const DISTRICTS = ["Berea", "Butha-Buthe", "Leribe", "Mafeteng", "Maseru", "Mohale's Hoek", "Mokhotlong", "Qacha's Nek", "Quthing", "Thaba-Tseka"];
const TECH_TYPES = ["SHS", "ICS", "GMG", "SWP", "PUE"];
const CHANNELS = ["Platform Notice Board", "National Gazette", "Local Newspaper", "UNGM"];
// Kept in sync with TARGET_SITE_TYPE_HELP in App.tsx — duplicated rather than imported
// to avoid a circular import between this file and App.tsx (see note above).
const TARGET_SITE_TYPE_HELP: Record<string, string> = {
  Household: "Systems installed at individual homes — the most common target for SHS and mini-grid connections.",
  Business: "Commercial premises such as shops or small enterprises.",
  School: "Educational institutions — typically lighting, ICT, or refrigeration loads.",
  Clinic: "Healthcare facilities — often prioritized for vaccine refrigeration and medical equipment.",
};

interface EoiFormData {
  id?: string;
  referenceNumber?: string;
  status?: string;
  name: string;
  department: string;
  targetSiteType: string;
  technologyTypes: string[];
  targetDistricts: string[];
  approximateInstallationTarget?: number;
  timeForCompletion: string;
  purposeAndScope: string;
  eoiDeadline: string;
  maxVendorsToShortlist?: number;
  advertisementChannels: string[];
  contactDetails: string;
}

const defaultEoiFormData: EoiFormData = {
  name: "",
  department: "",
  targetSiteType: "Household",
  technologyTypes: [],
  targetDistricts: [],
  approximateInstallationTarget: undefined,
  timeForCompletion: "",
  purposeAndScope: "",
  eoiDeadline: "",
  maxVendorsToShortlist: undefined,
  advertisementChannels: [],
  contactDetails: "",
};

function toEoiFormData(tender: Tender): EoiFormData {
  return {
    id: tender.id,
    referenceNumber: tender.referenceNumber,
    status: tender.status,
    name: tender.name ?? "",
    department: tender.department ?? "",
    targetSiteType: tender.targetSiteType || "Household",
    technologyTypes: tender.technologyTypes ?? [],
    targetDistricts: tender.targetDistricts ?? [],
    approximateInstallationTarget: tender.approximateInstallationTarget ?? undefined,
    timeForCompletion: tender.timeForCompletion ?? "",
    // instruction and biddersEligibility are always mirrored from the same "Purpose &
    // Scope" text on this form (see the save handler) — either is a faithful source
    // to read back from.
    purposeAndScope: tender.instruction ?? tender.biddersEligibility ?? "",
    eoiDeadline: tender.eoiDeadline ? tender.eoiDeadline.slice(0, 16) : "",
    maxVendorsToShortlist: tender.maxVendorsToShortlist ?? undefined,
    advertisementChannels: tender.advertisementChannels ?? [],
    contactDetails: tender.contactDetails ?? "",
  };
}

export const EoiInvites = ({
  initialView = "list",
  initialTenderId,
  onTenderOpened,
  onNavigate,
}: {
  initialView?: "list" | "create" | "edit";
  initialTenderId?: string | null;
  onTenderOpened?: () => void;
  onNavigate?: (action: string, id?: string) => void;
}) => {
  const [view, setView] = useState<"list" | "create" | "edit">(initialView);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [page, setPage] = useState(1);
  const perPage = 10;
  const [formData, setFormData] = useState<EoiFormData>(defaultEoiFormData);
  const [supportingDocFile, setSupportingDocFile] = useState<File | null>(null);
  const [existingSupportingDocName, setExistingSupportingDocName] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Super-Admin-configurable default currency, silently applied below (this
  // lightweight form has no currency picker of its own) — falls back to the
  // platform's historical default while loading / on failure.
  const [defaultCurrency, setDefaultCurrency] = useState("LSL (Maloti)");
  useEffect(() => {
    fetchCurrenciesConfig()
      .then(({ defaultCurrency: def }) => { if (def) setDefaultCurrency(def); })
      .catch(() => {});
  }, []);

  const navigateView = (newView: typeof view, id?: string | null) => {
    setView(newView);
    onNavigate?.(newView, id ?? undefined);
  };

  const loadTenders = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const all = await fetchTenders();
      setTenders(all.filter((t) => t.isEoiInviteOnly));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTenders();
  }, [loadTenders]);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  useEffect(() => {
    if (view !== "edit" || !initialTenderId) return;
    let cancelled = false;
    (async () => {
      try {
        const tender = await fetchTender(initialTenderId);
        if (cancelled) return;
        setFormData(toEoiFormData(tender));
        setExistingSupportingDocName(
          tender.governingDocuments?.find((d) => d.label === "Supporting Document")?.file_name || null
        );
      } catch {
        // leave the form blank; the save action will surface any real problem
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [view, initialTenderId]);

  const totalPages = Math.ceil(tenders.length / perPage);
  const paginatedTenders = useMemo(() => tenders.slice((page - 1) * perPage, page * perPage), [tenders, page]);

  const startCreate = () => {
    setFormData(defaultEoiFormData);
    setSupportingDocFile(null);
    setExistingSupportingDocName(null);
    setFormError(null);
    navigateView("create");
  };

  const startEdit = (tender: Tender) => {
    onTenderOpened?.();
    navigateView("edit", tender.id);
  };

  const toggleListItem = (key: "technologyTypes" | "targetDistricts" | "advertisementChannels", item: string) => {
    setFormData((prev) => {
      const current = prev[key];
      return {
        ...prev,
        [key]: current.includes(item) ? current.filter((v) => v !== item) : [...current, item],
      };
    });
  };

  const save = async (publish: boolean) => {
    setFormError(null);
    if (!formData.name.trim() || !formData.department.trim() || !formData.targetSiteType) {
      setFormError("Fill in the EOI Title, Department Entity, and Target Site Type.");
      return;
    }
    if (!formData.technologyTypes.length) {
      setFormError("Select at least one Technology Type.");
      return;
    }
    if (!formData.targetDistricts.length) {
      setFormError("Select at least one Target District.");
      return;
    }
    if (!formData.timeForCompletion.trim() || !formData.purposeAndScope.trim()) {
      setFormError("Fill in the Indicative Timeline and Purpose & Scope.");
      return;
    }
    if (!formData.eoiDeadline) {
      setFormError("Provide the Submission Deadline.");
      return;
    }
    if (!formData.contactDetails.trim()) {
      setFormError("Provide Contact Details.");
      return;
    }
    const governingDocuments = existingSupportingDocName || supportingDocFile
      ? [{ label: "Supporting Document", expected_type: "PDF", file_name: supportingDocFile?.name || existingSupportingDocName || undefined }]
      : [];
    // Backend requires a few fields that this lightweight, single-page form doesn't
    // surface — they're not decision-relevant before a real tender exists, so they're
    // silently populated instead of cluttering the EOI screen with paperwork fields:
    // applicationType/procurementMethod/procurementWorkflow/biddingCurrency all only
    // matter once bidding actually starts, and address_for_document/invited_by/
    // bidders_eligibility are mirrored from fields the reviewer already filled in above.
    const payload: any = {
      name: formData.name,
      department: formData.department,
      targetSiteType: formData.targetSiteType,
      technologyTypes: formData.technologyTypes,
      targetDistricts: formData.targetDistricts,
      approximateInstallationTarget: formData.approximateInstallationTarget,
      timeForCompletion: formData.timeForCompletion,
      instruction: formData.purposeAndScope,
      biddersEligibility: formData.purposeAndScope,
      eoiDeadline: formData.eoiDeadline,
      maxVendorsToShortlist: formData.maxVendorsToShortlist,
      advertisementChannels: formData.advertisementChannels,
      contactDetails: formData.contactDetails,
      addressForDocument: formData.contactDetails,
      invitedBy: formData.contactDetails,
      applicationType: "Application Window",
      procurementMethod: "Restricted Tendering",
      procurementWorkflow: "eoi_combined",
      biddingCurrency: defaultCurrency,
      isEoiInviteOnly: true,
      governingDocuments,
      governingDocumentsFiles: [supportingDocFile],
    };
    try {
      setIsSaving(true);
      let savedId = formData.id;
      if (view === "edit" && formData.id) {
        // mapTenderToApi defaults a missing `status` to "Draft" — pass the current
        // status through explicitly so editing an already-published EOI Invite
        // doesn't silently unpublish it.
        await updateTender(formData.id, { ...payload, status: formData.status });
      } else {
        const created = await createTender({ ...payload, status: TenderStatus.DRAFT });
        savedId = created.id;
      }
      if (publish && savedId) {
        await publishTender(savedId);
      }
      await loadTenders();
      navigateView("list");
    } catch (err: any) {
      setFormError(err?.message || "Unable to save this EOI Invite.");
    } finally {
      setIsSaving(false);
    }
  };

  // ---------- LIST ----------
  if (view === "list") {
    return (
      <FormKitShell>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900">EOI Invites</h1>
          <button onClick={startCreate} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> New EOI Invite
          </button>
        </div>

        {isLoading && <p className="text-sm text-slate-500">Loading EOI Invites...</p>}

        {!isLoading && tenders.length === 0 && (
          <div className="card p-6 text-center text-sm text-slate-500">
            No EOI Invites yet. Create one to start collecting Expressions of Interest.
          </div>
        )}

        <div className="space-y-3">
          {paginatedTenders.map((tender) => {
            const statusTone =
              tender.status === TenderStatus.PUBLISHED
                ? { color: AMBER, bg: AMBER_SOFT, label: "Shortlisting" }
                : tender.status === TenderStatus.DRAFT
                ? { color: INK_SUB, bg: LOCK_BG, label: "Draft" }
                : { color: INK_SUB, bg: LOCK_BG, label: tender.status };
            const linkedCount = tender.linkedTenderCount ?? tender.linkedTendersSummary?.length ?? 0;
            const isAlreadyLinked = linkedCount > 0;
            return (
              <button
                key={tender.id}
                onClick={() => onNavigate?.("details", tender.id)}
                disabled={isAlreadyLinked}
                title={isAlreadyLinked ? "This EOI Invite has already been used to create a tender and can no longer be converted or edited." : "Open details"}
                className={`card w-full text-left p-4 transition-colors ${
                  isAlreadyLinked
                    ? "opacity-50 blur-[1px] cursor-not-allowed select-none"
                    : "hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono text-xs text-slate-500">{tender.referenceNumber}</span>
                  <div className="flex items-center gap-2">
                    {isAlreadyLinked && <StatusChip color={INK_SUB} bg={LOCK_BG}>Linked to a tender</StatusChip>}
                    <StatusChip color={statusTone.color} bg={statusTone.bg}>{statusTone.label}</StatusChip>
                  </div>
                </div>
                <p className="font-bold text-slate-900 mb-1">{tender.name}</p>
                <p className="text-xs text-slate-500">
                  {tender.invitedVendorCount ?? 0} shortlisted
                </p>
                {isAlreadyLinked ? (
                  <span className="inline-flex items-center gap-1 mt-2 text-xs font-bold text-slate-400">
                    Used to create {linkedCount} tender{linkedCount > 1 ? "s" : ""} — conversion blocked
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 mt-2 text-xs font-bold" style={{ color: AMBER }}>
                    Review &amp; shortlist <ArrowRight size={12} />
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-secondary text-sm py-1.5 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="btn-secondary text-sm py-1.5 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </FormKitShell>
    );
  }

  // ---------- CREATE / EDIT (single page) ----------
  return (
    <FormKitShell>
      <Crumb onBack={() => navigateView("list")} trail="EOI Invites" />
      <div className="flex items-center gap-2.5 mb-1">
        <h1 className="text-2xl font-bold text-slate-900">{view === "edit" ? "Edit EOI Invite" : "New EOI Invite"}</h1>
        {formData.referenceNumber && (
          <span className="font-mono text-xs text-slate-500 bg-slate-100 rounded px-1.5 py-0.5">
            {formData.referenceNumber}
          </span>
        )}
      </div>
      <p className="text-sm text-slate-500 mb-5">
        A single, lightweight form — no evaluation scoring, security, or envelope rules. Those only apply once this becomes a tender.
      </p>

      <div className="card p-6 md:p-8">
        <p className="text-xs font-bold uppercase tracking-widest mb-4" style={{ color: AMBER }}>Scope</p>
        <Field label="EOI Title" required accent={AMBER}>
          <TextInput
            value={formData.name}
            onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
            placeholder="e.g. Mini-Grid Application Window — Expression of Interest"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Department Entity" required accent={AMBER}>
            <Select value={formData.department} onChange={(e) => setFormData((prev) => ({ ...prev, department: e.target.value }))}>
              <option value="" disabled>Select entity</option>
              <option>Department of Energy</option>
              <option>UNDP Lesotho</option>
            </Select>
          </Field>
          <Field label="Target Site Type" required accent={AMBER} help={{ text: TARGET_SITE_TYPE_HELP[formData.targetSiteType] || TARGET_SITE_TYPE_HELP.Household }}>
            <Select value={formData.targetSiteType} onChange={(e) => setFormData((prev) => ({ ...prev, targetSiteType: e.target.value }))}>
              <option>Household</option>
              <option>Business</option>
              <option>School</option>
              <option>Clinic</option>
            </Select>
          </Field>
        </div>
        <Field label="Technology Type(s)" required accent={AMBER}>
          <Chips items={TECH_TYPES} selected={formData.technologyTypes} onToggle={(item) => toggleListItem("technologyTypes", item)} accent={AMBER} />
        </Field>
        <Field label="Target District(s)" required accent={AMBER}>
          <Chips items={DISTRICTS} selected={formData.targetDistricts} onToggle={(item) => toggleListItem("targetDistricts", item)} accent={AMBER} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Approximate Installation Target" accent={AMBER} help={{ text: "Indicative only — refined once the tender scope is finalized." }}>
            <TextInput
              type="number"
              min={0}
              value={formData.approximateInstallationTarget ?? ""}
              onChange={(e) => setFormData((prev) => ({ ...prev, approximateInstallationTarget: e.target.value === "" ? undefined : Number(e.target.value) }))}
              placeholder="e.g. 1,000 units"
            />
          </Field>
          <Field label="Indicative Timeline" required accent={AMBER} help={{ text: "A rough estimate to help vendors gauge scale — the tender sets the binding completion timeline." }}>
            <TextInput
              value={formData.timeForCompletion}
              onChange={(e) => setFormData((prev) => ({ ...prev, timeForCompletion: e.target.value }))}
              placeholder="e.g. 60 days"
            />
          </Field>
        </div>
        <Field label="Purpose & Scope" required accent={AMBER}>
          <TextArea
            value={formData.purposeAndScope}
            onChange={(e) => setFormData((prev) => ({ ...prev, purposeAndScope: e.target.value }))}
            placeholder="Brief description of the opportunity and what a respondent should demonstrate"
          />
        </Field>

        <p className="text-xs font-bold uppercase tracking-widest mb-4 mt-2" style={{ color: AMBER }}>Interest window</p>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Submission Deadline" required accent={AMBER}>
            <TextInput
              type="datetime-local"
              value={formData.eoiDeadline}
              onChange={(e) => setFormData((prev) => ({ ...prev, eoiDeadline: e.target.value }))}
            />
          </Field>
          <Field label="Max Vendors to Shortlist" accent={AMBER} help={{ text: "Optional cap on how many respondents can be invited into the tender. Advisory only — never enforced." }}>
            <TextInput
              type="number"
              min={1}
              value={formData.maxVendorsToShortlist ?? ""}
              onChange={(e) => setFormData((prev) => ({ ...prev, maxVendorsToShortlist: e.target.value === "" ? undefined : Number(e.target.value) }))}
              placeholder="e.g. 8"
            />
          </Field>
        </div>
        <Field label="Advertisement Channels" accent={AMBER}>
          <Chips items={CHANNELS} selected={formData.advertisementChannels} onToggle={(item) => toggleListItem("advertisementChannels", item)} accent={AMBER} />
        </Field>

        <p className="text-xs font-bold uppercase tracking-widest mb-4 mt-2" style={{ color: AMBER }}>Publish</p>
        <Field label="Contact Details" required accent={AMBER}>
          <TextInput
            value={formData.contactDetails}
            onChange={(e) => setFormData((prev) => ({ ...prev, contactDetails: e.target.value }))}
            placeholder="Name, email, phone"
          />
        </Field>
        <Field label="Supporting Document" accent={AMBER} help={{ text: "Optional concept brief or draft terms of reference, max 10MB." }}>
          <UploadZone
            label="Upload PDF / DOCX — max 10MB"
            fileName={supportingDocFile?.name || existingSupportingDocName}
            onFileSelect={(file) => setSupportingDocFile(file)}
            accept=".pdf,.doc,.docx"
          />
        </Field>

        {formError && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium mb-4">
            {formError}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-4 mt-2 border-t border-slate-100">
          {view === "edit" && formData.status !== TenderStatus.DRAFT ? (
            <button disabled={isSaving} onClick={() => save(false)} className="btn-primary disabled:opacity-50">
              {isSaving ? "Saving..." : "Save Changes"}
            </button>
          ) : (
            <>
              <button disabled={isSaving} onClick={() => save(false)} className="btn-secondary disabled:opacity-50">
                {isSaving ? "Saving..." : "Save Draft"}
              </button>
              <button disabled={isSaving} onClick={() => save(true)} className="btn-primary disabled:opacity-50">
                {isSaving ? "Saving..." : "Publish EOI Invite"}
              </button>
            </>
          )}
        </div>
      </div>
    </FormKitShell>
  );
};

export default EoiInvites;
