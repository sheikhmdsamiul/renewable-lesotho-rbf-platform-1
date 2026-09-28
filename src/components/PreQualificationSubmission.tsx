import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ChevronRight, Clock, Download, HelpCircle, Loader2, XCircle } from "lucide-react";
import { fetchMyProfile, fetchVendorPrequalifications, submitVendorPrequalification } from "../api";
import { VendorPrequalification } from "../types";
import { apiFieldErrors, EMAIL_PATTERN, Field, FieldErrors, FileDrop, inputClass, mobileNumberError } from "./formFields";

export const getLatestPrequalification = (items: VendorPrequalification[]) => {
  if (!items.length) return null;
  const sorted = [...items].sort((a, b) => {
    const aSubmitted = Date.parse(a.submittedAt || "");
    const bSubmitted = Date.parse(b.submittedAt || "");
    if (!Number.isNaN(aSubmitted) || !Number.isNaN(bSubmitted)) {
      return (Number.isNaN(bSubmitted) ? 0 : bSubmitted) - (Number.isNaN(aSubmitted) ? 0 : aSubmitted);
    }
    const aReviewed = Date.parse(a.reviewedAt || "");
    const bReviewed = Date.parse(b.reviewedAt || "");
    if (!Number.isNaN(aReviewed) || !Number.isNaN(bReviewed)) {
      return (Number.isNaN(bReviewed) ? 0 : bReviewed) - (Number.isNaN(aReviewed) ? 0 : aReviewed);
    }
    return (Number(b.id) || 0) - (Number(a.id) || 0);
  });
  return sorted[0] ?? null;
};

const TECH_OPTIONS = [
  { value: "SHS", label: "Solar Home Systems (SHS)" },
  { value: "ICS", label: "Improved Cookstoves (ICS)" },
  { value: "GMG", label: "Green Mini-Grids (GMG)" },
  { value: "SWP", label: "Solar Water Pumping (SWP)" },
  { value: "PUE", label: "Productive Use of Energy (PUE)" },
];
const ORG_TYPES = [
  { value: "Private", label: "Private company" },
  { value: "NGO", label: "NGO / non-profit" },
  { value: "Cooperative", label: "Cooperative" },
  { value: "Public", label: "Public entity" },
];
const TIERS = ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"];
const DOC_TYPES = ["pdf", "docx", "jpg", "jpeg", "png"];
const DOC_MAX_MB = 10;
const SWIFT_PATTERN = /^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$/;

type DocKey = "registrationCertificate" | "tradingLicense" | "taxComplianceCertificate" | "authorizedSignatoryId" | "experienceFinancialProof";
const DOCUMENTS: Array<{ key: DocKey; api: string; label: string; help: string }> = [
  { key: "registrationCertificate", api: "registration_certificate", label: "Company registration certificate", help: "Certificate of incorporation / registration." },
  { key: "tradingLicense", api: "trading_license", label: "Valid trading licence", help: "Must be current." },
  { key: "taxComplianceCertificate", api: "tax_compliance_certificate", label: "Tax clearance certificate", help: "Issued by the Revenue Services Lesotho." },
  { key: "authorizedSignatoryId", api: "authorized_signatory_id", label: "Authorised signatory ID", help: "ID or passport of the person signing contracts." },
  { key: "experienceFinancialProof", api: "experience_financial_proof", label: "Experience & financial proof", help: "E.g. audited accounts, reference letters, past project records." },
];

// Form field keys match the API names so server errors map directly onto fields.
type Form = {
  company_name: string;
  organization_type: string;
  tax_id: string;
  hq_address: string;
  email: string;
  contact_number: string;
  gender_of_focal_person: string;
  technology_types: string[];
  tech_tier: string;
  years_experience: string;
  prior_projects: string;
  annual_revenue: string;
  districts_covered: string;
  female_beneficiary_target: number;
  vulnerable_group_target: number;
  bank_name: string;
  bank_branch: string;
  bank_account_name: string;
  bank_account_number: string;
  bank_swift_code: string;
  bank_sort_code: string;
  declaration_accepted: boolean;
};

const EMPTY_FORM: Form = {
  company_name: "",
  organization_type: "Private",
  tax_id: "",
  hq_address: "",
  email: "",
  contact_number: "",
  gender_of_focal_person: "",
  technology_types: [],
  tech_tier: "",
  years_experience: "",
  prior_projects: "",
  annual_revenue: "",
  districts_covered: "",
  female_beneficiary_target: 50,
  vulnerable_group_target: 30,
  bank_name: "",
  bank_branch: "",
  bank_account_name: "",
  bank_account_number: "",
  bank_swift_code: "",
  bank_sort_code: "",
  declaration_accepted: false,
};

const STEP_FIELDS: Record<number, string[]> = {
  1: ["company_name", "organization_type", "tax_id", "hq_address", "email", "contact_number", "gender_of_focal_person", ...DOCUMENTS.map((doc) => doc.api)],
  2: ["technology_types", "tech_tier", "years_experience", "prior_projects", "annual_revenue", "districts_covered"],
  3: ["bank_name", "bank_branch", "bank_account_name", "bank_account_number", "bank_swift_code", "bank_sort_code"],
  4: ["female_beneficiary_target", "vulnerable_group_target", "declaration_accepted"],
};
const STEP_TITLES = ["Company & documents", "Technical & financial capacity", "Payment details", "Inclusion targets & declaration"];
// Bank account details are never written to the browser draft.
const DRAFT_EXCLUDED: Array<keyof Form> = ["bank_account_number", "declaration_accepted"];

function intInRange(value: string, label: string, min: number, max: number, required: boolean): string {
  if (value.trim() === "") return required ? `${label} is required.` : "";
  const number = Number(value);
  if (!Number.isInteger(number)) return `${label} must be a whole number.`;
  if (number < min || number > max) return `${label} must be between ${min} and ${max}.`;
  return "";
}

function validateStep(step: number, form: Form, docs: Record<DocKey, File | null>, existing: VendorPrequalification | null): FieldErrors {
  const errors: FieldErrors = {};
  const need = (key: keyof Form, message: string) => {
    if (!String(form[key] ?? "").trim()) errors[key] = message;
  };
  if (step === 1) {
    need("company_name", "Enter the registered company name.");
    need("tax_id", "Enter the Tax ID (TIN).");
    need("hq_address", "Enter the head office address.");
    if (!form.email.trim()) errors.email = "Enter a contact email.";
    else if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = "Enter a valid email address.";
    const mobile = mobileNumberError(form.contact_number);
    if (mobile) errors.contact_number = mobile;
    need("gender_of_focal_person", "Select the gender of the focal person.");
    for (const doc of DOCUMENTS) {
      if (!docs[doc.key] && !(existing && existing[doc.key])) errors[doc.api] = `Upload the ${doc.label.toLowerCase()}.`;
    }
  }
  if (step === 2) {
    if (form.technology_types.length === 0) errors.technology_types = "Select at least one technology.";
    need("tech_tier", "Select the highest technology tier you deliver.");
    const checks: Array<[keyof Form, string, number, number, boolean]> = [
      ["years_experience", "Years of experience", 0, 100, true],
      ["prior_projects", "Prior projects", 0, 100000, true],
      ["districts_covered", "Districts covered", 1, 10, true],
    ];
    for (const [key, label, min, max, required] of checks) {
      const message = intInRange(String(form[key]), label, min, max, required);
      if (message) errors[key] = message;
    }
    if (form.annual_revenue.trim() && !(Number(form.annual_revenue) >= 0)) errors.annual_revenue = "Enter revenue as a positive amount.";
  }
  if (step === 3) {
    need("bank_name", "Enter the bank name.");
    need("bank_branch", "Enter the branch.");
    need("bank_account_name", "Enter the account holder name.");
    const account = form.bank_account_number.replace(/[\s-]/g, "");
    if (!account) errors.bank_account_number = "Enter the account number.";
    else if (!/^\d{5,20}$/.test(account)) errors.bank_account_number = "Account number must be 5-20 digits.";
    const swift = form.bank_swift_code.trim().toUpperCase().replace(/\s/g, "");
    if (swift && !SWIFT_PATTERN.test(swift)) errors.bank_swift_code = "SWIFT/BIC is 8 or 11 letters/digits, e.g. FIRNLSMX.";
    if (form.bank_sort_code.trim() && !/^[0-9-]{4,12}$/.test(form.bank_sort_code.trim())) errors.bank_sort_code = "Use digits and dashes only.";
  }
  if (step === 4 && !form.declaration_accepted) errors.declaration_accepted = "You must accept the declaration to submit.";
  return errors;
}

const statusTone: Record<string, string> = {
  Approved: "bg-emerald-100 text-emerald-700 border-emerald-300",
  "Under Review": "bg-blue-100 text-blue-700 border-blue-300",
  Pending: "bg-amber-100 text-amber-700 border-amber-300",
  "Partial (Resubmit)": "bg-orange-100 text-orange-700 border-orange-300",
  Rejected: "bg-rose-100 text-rose-700 border-rose-300",
};
const statusLabel = (status: string) => (status === "Partial (Resubmit)" ? "Changes requested" : status);
const statusIcon = (status: string) => {
  switch (status) {
    case "Approved": return <CheckCircle2 className="text-emerald-600" size={32} />;
    case "Under Review": return <Clock className="text-blue-600" size={32} />;
    case "Pending": return <Clock className="text-amber-600" size={32} />;
    case "Partial (Resubmit)": return <AlertCircle className="text-orange-600" size={32} />;
    case "Rejected": return <XCircle className="text-rose-600" size={32} />;
    default: return <HelpCircle className="text-slate-600" size={32} />;
  }
};

function formFromPrequal(prequal: VendorPrequalification): Form {
  return {
    company_name: prequal.companyName ?? "",
    organization_type: prequal.organizationType || "Private",
    tax_id: prequal.taxId ?? "",
    hq_address: prequal.hqAddress ?? "",
    email: prequal.email ?? "",
    contact_number: prequal.contactNumber ?? "",
    gender_of_focal_person: prequal.genderOfFocalPerson ?? "",
    technology_types: prequal.technologyTypes ?? [],
    tech_tier: prequal.techTier ?? "",
    years_experience: prequal.yearsExperience != null ? String(prequal.yearsExperience) : "",
    prior_projects: prequal.priorProjects != null ? String(prequal.priorProjects) : "",
    annual_revenue: prequal.annualRevenue != null ? String(prequal.annualRevenue) : "",
    districts_covered: prequal.districtsCovered ? String(prequal.districtsCovered) : "",
    female_beneficiary_target: prequal.femaleBeneficiaryTarget ?? 50,
    vulnerable_group_target: prequal.vulnerableGroupTarget ?? 30,
    bank_name: prequal.bankName ?? "",
    bank_branch: prequal.bankBranch ?? "",
    bank_account_name: prequal.bankAccountName ?? "",
    bank_account_number: prequal.bankAccountNumber ?? "",
    bank_swift_code: prequal.bankSwiftCode ?? "",
    bank_sort_code: prequal.bankSortCode ?? "",
    declaration_accepted: false,
  };
}

const EMPTY_DOCS: Record<DocKey, File | null> = {
  registrationCertificate: null,
  tradingLicense: null,
  taxComplianceCertificate: null,
  authorizedSignatoryId: null,
  experienceFinancialProof: null,
};

export default function PreQualificationSubmission() {
  const [prequals, setPrequals] = useState<VendorPrequalification[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [vendorId, setVendorId] = useState("");
  const [editing, setEditing] = useState<VendorPrequalification | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [docs, setDocs] = useState<Record<DocKey, File | null>>(EMPTY_DOCS);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState<Date | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const draftKey = vendorId ? `rbf-prequal-draft:${vendorId}` : "";

  const load = async () => {
    setLoadState("loading");
    try {
      const [rows, profile] = await Promise.all([fetchVendorPrequalifications(), fetchMyProfile().catch(() => null)]);
      setPrequals(rows);
      if (profile) {
        setVendorId(String(profile.id));
        // Prefill a fresh application from what the vendor gave at registration.
        setForm((prev) => ({
          ...prev,
          company_name: prev.company_name || profile.organization_name || "",
          organization_type: profile.organization_type || prev.organization_type,
          tax_id: prev.tax_id || profile.tax_id || "",
          hq_address: prev.hq_address || profile.address || "",
          email: prev.email || profile.email || "",
          contact_number: prev.contact_number || profile.mobile_number || "",
          gender_of_focal_person: prev.gender_of_focal_person || profile.gender || "",
          technology_types: prev.technology_types.length ? prev.technology_types : profile.technology_types || [],
        }));
      }
      setLoadState("ready");
    } catch {
      setLoadState("error");
    }
  };

  useEffect(() => { void load(); }, []);

  // Restore a saved draft (text fields only) once we know who the vendor is.
  useEffect(() => {
    if (!draftKey) return;
    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) setForm((prev) => ({ ...prev, ...JSON.parse(saved) }));
    } catch { /* storage unavailable */ }
  }, [draftKey]);

  useEffect(() => {
    if (!draftKey || !showForm) return;
    const timer = window.setTimeout(() => {
      try {
        const draft: Partial<Form> = { ...form };
        DRAFT_EXCLUDED.forEach((key) => delete draft[key]);
        localStorage.setItem(draftKey, JSON.stringify(draft));
        setDraftSavedAt(new Date());
      } catch { /* storage unavailable */ }
    }, 800);
    return () => window.clearTimeout(timer);
  }, [form, draftKey, showForm]);

  const latest = useMemo(() => getLatestPrequalification(prequals), [prequals]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key as string];
      return next;
    });
  };

  const goToStep = (next: number) => {
    setStep(next);
    window.requestAnimationFrame(() => headingRef.current?.focus());
  };

  const startResubmission = (prequal: VendorPrequalification) => {
    setForm(formFromPrequal(prequal));
    setDocs(EMPTY_DOCS);
    setEditing(prequal);
    setErrors({});
    setFormError("");
    setShowForm(true);
    goToStep(1);
  };

  const next = (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
    const stepErrors = validateStep(step, form, docs, editing);
    setErrors(stepErrors);
    if (Object.keys(stepErrors).length) {
      setFormError("Please correct the highlighted fields.");
      return;
    }
    if (step < 4) goToStep(step + 1);
    else setConfirmOpen(true);
  };

  const submit = async () => {
    setConfirmOpen(false);
    setSubmitting(true);
    setFormError("");
    try {
      const created = await submitVendorPrequalification({
        companyName: form.company_name.trim(),
        organizationType: form.organization_type,
        taxId: form.tax_id.trim(),
        hqAddress: form.hq_address.trim(),
        technologyTypes: form.technology_types,
        registrationCertificateName: docs.registrationCertificate?.name ?? editing?.registrationCertificateName ?? "",
        registrationCertificate: docs.registrationCertificate || undefined,
        tradingLicense: docs.tradingLicense || undefined,
        taxComplianceCertificate: docs.taxComplianceCertificate || undefined,
        authorizedSignatoryId: docs.authorizedSignatoryId || undefined,
        experienceFinancialProof: docs.experienceFinancialProof || undefined,
        techTier: form.tech_tier,
        yearsExperience: Number(form.years_experience),
        priorProjects: Number(form.prior_projects),
        annualRevenue: form.annual_revenue.trim() === "" ? undefined : Number(form.annual_revenue),
        districtsCovered: Number(form.districts_covered),
        femaleBeneficiaryTarget: form.female_beneficiary_target,
        vulnerableGroupTarget: form.vulnerable_group_target,
        bankName: form.bank_name.trim(),
        bankBranch: form.bank_branch.trim(),
        bankSwiftCode: form.bank_swift_code.trim().toUpperCase().replace(/\s/g, ""),
        bankSortCode: form.bank_sort_code.trim(),
        bankAccountName: form.bank_account_name.trim(),
        bankAccountNumber: form.bank_account_number.replace(/[\s-]/g, ""),
        contactNumber: form.contact_number.replace(/\D/g, ""),
        email: form.email.trim(),
        genderOfFocalPerson: form.gender_of_focal_person,
        declarationAccepted: form.declaration_accepted,
      }, editing?.id);
      setPrequals((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      try { if (draftKey) localStorage.removeItem(draftKey); } catch { /* ignore */ }
      setShowForm(false);
      setEditing(null);
      setJustSubmitted(true);
    } catch (err: any) {
      const { fields, message } = apiFieldErrors(err, "Your application could not be submitted. Please try again.");
      setErrors(fields);
      setFormError(message);
      const firstStep = [1, 2, 3, 4].find((n) => STEP_FIELDS[n].some((key) => key in fields));
      if (firstStep) goToStep(firstStep);
    } finally {
      setSubmitting(false);
    }
  };

  if (loadState === "loading") {
    return (
      <div className="flex items-center justify-center py-12" role="status">
        <Loader2 className="animate-spin text-emerald-600" size={32} />
        <p className="ml-3 text-slate-600">Loading your pre-qualification status...</p>
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
        <p className="font-semibold text-rose-800">We couldn&apos;t load your pre-qualification status.</p>
        <p className="mt-1 text-sm text-rose-700">To avoid a duplicate application, the form is hidden until your status loads.</p>
        <button type="button" onClick={() => void load()} className="btn-primary mt-4">Try again</button>
      </div>
    );
  }

  if (latest && !showForm) {
    const canResubmit = latest.status === "Partial (Resubmit)" || latest.status === "Rejected";
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        {justSubmitted && (
          <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800" role="status">
            <CheckCircle2 className="mt-0.5 shrink-0" size={20} />
            <div>
              <p className="font-semibold">Application submitted</p>
              <p className="text-sm">The RBF Management Team will review it. You&apos;ll get an in-app notification when the status changes.</p>
            </div>
          </div>
        )}
        <div className="card p-6 sm:p-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
            <div className="shrink-0">{statusIcon(latest.status)}</div>
            <div className="flex-1">
              <h2 className="mb-2 text-2xl font-bold text-slate-900">Pre-qualification status</h2>
              <div className={`inline-block rounded-xl border-2 px-4 py-2 text-lg font-bold ${statusTone[latest.status] || "border-slate-300 bg-slate-100 text-slate-700"}`}>
                {statusLabel(latest.status)}
              </div>
              <p className="mt-3 text-sm text-slate-600">
                {latest.status === "Approved" && "You are pre-qualified and can bid on open tenders."}
                {latest.status === "Pending" && "Your application is waiting to be picked up by a reviewer. You cannot edit it while it is in the queue."}
                {latest.status === "Under Review" && "A reviewer is assessing your application. You'll be notified of the outcome."}
                {latest.status === "Partial (Resubmit)" && "The reviewer needs changes before a decision can be made. Update your application and resubmit."}
                {latest.status === "Rejected" && "Your application was not approved. You may correct it and apply again, or contact the RBF Management Team."}
              </p>
            </div>
          </div>
        </div>

        {latest.reviewerComments && (canResubmit || latest.status === "Approved") && (
          <div className={`card border-2 p-6 ${latest.status === "Rejected" ? "border-rose-200 bg-rose-50" : latest.status === "Approved" ? "border-emerald-200 bg-emerald-50" : "border-orange-200 bg-orange-50"}`}>
            <p className="mb-1 text-sm font-semibold text-slate-800">Reviewer comments</p>
            <p className="whitespace-pre-line text-sm text-slate-700">{latest.reviewerComments}</p>
          </div>
        )}
        {canResubmit && (
          <button type="button" onClick={() => startResubmission(latest)} className="btn-primary">
            {latest.status === "Rejected" ? "Correct and apply again" : "Update and resubmit"}
          </button>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="card space-y-3 p-6 text-sm">
            <h3 className="font-bold text-slate-900">Submission</h3>
            <p><span className="text-slate-500">Company:</span> <span className="font-medium text-slate-900">{latest.companyName}</span></p>
            <p><span className="text-slate-500">Submitted:</span> <span className="font-medium text-slate-900">{latest.submittedAt ? new Date(latest.submittedAt).toLocaleString() : "—"}</span></p>
            <p><span className="text-slate-500">Technologies:</span> <span className="font-medium text-slate-900">{latest.technologyTypes.join(", ") || "—"}</span></p>
            <p><span className="text-slate-500">Tier:</span> <span className="font-medium text-slate-900">{latest.techTier || "—"}</span></p>
            <p><span className="text-slate-500">Targets:</span> <span className="font-medium text-slate-900">{latest.femaleBeneficiaryTarget}% female-headed, {latest.vulnerableGroupTarget}% vulnerable</span></p>
            {latest.reviewedAt && <p><span className="text-slate-500">Last reviewed:</span> <span className="font-medium text-slate-900">{new Date(latest.reviewedAt).toLocaleString()}</span></p>}
          </div>
          <div className="card space-y-2 p-6 text-sm">
            <h3 className="font-bold text-slate-900">Documents on record</h3>
            {DOCUMENTS.map((doc) => (
              <div key={doc.key} className="flex items-center justify-between gap-3">
                <span className="text-slate-600">{doc.label}</span>
                {latest[doc.key] ? (
                  <a href={String(latest[doc.key])} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-medium text-emerald-700 hover:underline">
                    <Download size={14} /> View
                  </a>
                ) : <span className="text-xs text-rose-600">Missing</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!showForm) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="card p-6 sm:p-8">
          <h2 className="text-2xl font-bold text-slate-900">Vendor pre-qualification</h2>
          <p className="mt-2 text-slate-600">You must be pre-qualified by the RBF Management Team before you can bid on tenders. The application has four short steps. Have these ready:</p>
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {DOCUMENTS.map((doc) => <li key={doc.key}>{doc.label}</li>)}
            <li>Bank account details for RBF payments</li>
          </ul>
          <p className="mt-3 text-xs text-slate-500">Documents: PDF, DOCX, JPG or PNG, up to {DOC_MAX_MB} MB each. Your progress is saved on this device as you go (except bank account numbers).</p>
          <button type="button" onClick={() => { setShowForm(true); goToStep(1); }} className="btn-primary mt-6">Start application</button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-20">
      {editing?.reviewerComments && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <p className="font-bold text-amber-800">Reviewer comments to address</p>
          <p className="mt-1 whitespace-pre-line text-amber-900">{editing.reviewerComments}</p>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{editing ? "Update your pre-qualification" : "Vendor pre-qualification"}</h1>
          <p className="text-sm text-slate-500">
            Step {step} of 4 · {STEP_TITLES[step - 1]}
            {draftSavedAt && <span className="ml-2 text-xs text-slate-400">Draft saved {draftSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
          </p>
        </div>
        <ol className="flex flex-wrap items-center gap-1 text-xs font-bold text-slate-400" aria-label="Progress">
          {STEP_TITLES.map((title, index) => (
            <li key={title} className="flex items-center gap-1">
              <span className={step >= index + 1 ? "text-emerald-600" : ""} aria-current={step === index + 1 ? "step" : undefined}>{index + 1}. {title}</span>
              {index < STEP_TITLES.length - 1 && <ChevronRight size={14} />}
            </li>
          ))}
        </ol>
      </div>

      <div className="card p-6 sm:p-8">
        <form onSubmit={next} noValidate className="space-y-8">
          <h2 ref={headingRef} tabIndex={-1} className="border-b border-slate-100 pb-2 text-lg font-bold text-slate-900 outline-none">{STEP_TITLES[step - 1]}</h2>

          {step === 1 && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <Field id="pq-company" label="Registered company name" required error={errors.company_name}>
                  {(aria) => <input {...aria} className={inputClass(errors.company_name)} value={form.company_name} onChange={(e) => set("company_name", e.target.value)} />}
                </Field>
                <Field id="pq-org-type" label="Organisation type" required>
                  {(aria) => (
                    <select {...aria} className="input-field" value={form.organization_type} onChange={(e) => set("organization_type", e.target.value)}>
                      {ORG_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                    </select>
                  )}
                </Field>
                <Field id="pq-tax" label="Tax ID (TIN)" required error={errors.tax_id}>
                  {(aria) => <input {...aria} className={inputClass(errors.tax_id)} value={form.tax_id} onChange={(e) => set("tax_id", e.target.value)} />}
                </Field>
                <Field id="pq-address" label="Head office address" required error={errors.hq_address}>
                  {(aria) => <input {...aria} className={inputClass(errors.hq_address)} value={form.hq_address} onChange={(e) => set("hq_address", e.target.value)} />}
                </Field>
                <Field id="pq-email" label="Contact email" required error={errors.email}>
                  {(aria) => <input {...aria} type="email" autoComplete="email" className={inputClass(errors.email)} value={form.email} onChange={(e) => set("email", e.target.value)} />}
                </Field>
                <Field id="pq-phone" label="Contact mobile number" required error={errors.contact_number} help="Lesotho: 8 digits (e.g. 58 123 456). Others: include country code.">
                  {(aria) => <input {...aria} type="tel" inputMode="tel" autoComplete="tel" className={inputClass(errors.contact_number)} value={form.contact_number} onChange={(e) => set("contact_number", e.target.value.replace(/[^\d+\s-]/g, ""))} />}
                </Field>
                <Field id="pq-gender" label="Gender of focal person" required error={errors.gender_of_focal_person}>
                  {(aria) => (
                    <select {...aria} className={inputClass(errors.gender_of_focal_person)} value={form.gender_of_focal_person} onChange={(e) => set("gender_of_focal_person", e.target.value)}>
                      <option value="">Select…</option>
                      <option value="Female">Female</option>
                      <option value="Male">Male</option>
                      <option value="Other">Other / prefer not to say</option>
                    </select>
                  )}
                </Field>
              </div>
              <div>
                <p className="mb-3 text-sm font-bold text-slate-700">Required documents</p>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {DOCUMENTS.map((doc) => (
                    <div key={doc.key}>
                      <FileDrop
                        id={`pq-doc-${doc.key}`}
                        label={doc.label}
                        required
                        accept={DOC_TYPES}
                        maxMb={DOC_MAX_MB}
                        file={docs[doc.key]}
                        existingUrl={editing ? (editing[doc.key] as string | undefined) : undefined}
                        error={errors[doc.api]}
                        onChange={(file, error) => {
                          setDocs((prev) => ({ ...prev, [doc.key]: file }));
                          setErrors((prev) => {
                            const nextErrors = { ...prev };
                            if (error) nextErrors[doc.api] = error;
                            else delete nextErrors[doc.api];
                            return nextErrors;
                          });
                        }}
                      />
                      <p className="ml-1 mt-1 text-xs text-slate-500">{doc.help}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <fieldset className="space-y-2">
                <legend className="ml-1 text-sm font-bold text-slate-700">Technologies you deliver <span className="text-rose-600">*</span></legend>
                <div className="flex flex-wrap gap-2">
                  {TECH_OPTIONS.map((tech) => {
                    const selected = form.technology_types.includes(tech.value);
                    return (
                      <button
                        key={tech.value}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => set("technology_types", selected ? form.technology_types.filter((t) => t !== tech.value) : [...form.technology_types, tech.value])}
                        className={`rounded-xl border-2 px-4 py-2 text-sm font-semibold transition-all ${selected ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}
                      >
                        {tech.label}
                      </button>
                    );
                  })}
                </div>
                {errors.technology_types && <p role="alert" className="ml-1 text-xs text-rose-600">{errors.technology_types}</p>}
              </fieldset>
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <Field id="pq-tier" label="Highest technology tier supported" required error={errors.tech_tier} help="Multi-Tier Framework level of the systems you supply.">
                  {(aria) => (
                    <select {...aria} className={inputClass(errors.tech_tier)} value={form.tech_tier} onChange={(e) => set("tech_tier", e.target.value)}>
                      <option value="">Select…</option>
                      {TIERS.map((tier) => <option key={tier} value={tier}>{tier}</option>)}
                    </select>
                  )}
                </Field>
                <Field id="pq-years" label="Years of experience" required error={errors.years_experience}>
                  {(aria) => <input {...aria} type="number" inputMode="numeric" min={0} max={100} step={1} className={inputClass(errors.years_experience)} value={form.years_experience} onChange={(e) => set("years_experience", e.target.value)} />}
                </Field>
                <Field id="pq-projects" label="Prior projects implemented" required error={errors.prior_projects}>
                  {(aria) => <input {...aria} type="number" inputMode="numeric" min={0} step={1} className={inputClass(errors.prior_projects)} value={form.prior_projects} onChange={(e) => set("prior_projects", e.target.value)} />}
                </Field>
                <Field id="pq-districts" label="Districts covered" required error={errors.districts_covered} help="Out of Lesotho's 10 districts.">
                  {(aria) => <input {...aria} type="number" inputMode="numeric" min={1} max={10} step={1} className={inputClass(errors.districts_covered)} value={form.districts_covered} onChange={(e) => set("districts_covered", e.target.value)} />}
                </Field>
                <Field id="pq-revenue" label="Annual revenue, last financial year (LSL)" error={errors.annual_revenue} help="Optional. Leave blank if not available.">
                  {(aria) => <input {...aria} type="number" inputMode="decimal" min={0} step="0.01" className={inputClass(errors.annual_revenue)} value={form.annual_revenue} onChange={(e) => set("annual_revenue", e.target.value)} />}
                </Field>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <p className="text-sm text-slate-600">RBF payments are made to this account. It must be in the organisation&apos;s registered name.</p>
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <Field id="pq-bank" label="Bank name" required error={errors.bank_name}>
                  {(aria) => <input {...aria} className={inputClass(errors.bank_name)} value={form.bank_name} onChange={(e) => set("bank_name", e.target.value)} />}
                </Field>
                <Field id="pq-branch" label="Branch" required error={errors.bank_branch}>
                  {(aria) => <input {...aria} className={inputClass(errors.bank_branch)} value={form.bank_branch} onChange={(e) => set("bank_branch", e.target.value)} />}
                </Field>
                <Field id="pq-acc-name" label="Account holder name" required error={errors.bank_account_name}>
                  {(aria) => <input {...aria} className={inputClass(errors.bank_account_name)} value={form.bank_account_name} onChange={(e) => set("bank_account_name", e.target.value)} />}
                </Field>
                <Field id="pq-acc-number" label="Account number" required error={errors.bank_account_number}>
                  {(aria) => <input {...aria} inputMode="numeric" autoComplete="off" className={inputClass(errors.bank_account_number)} value={form.bank_account_number} onChange={(e) => set("bank_account_number", e.target.value.replace(/[^\d\s-]/g, ""))} />}
                </Field>
                <Field id="pq-swift" label="SWIFT / BIC code" error={errors.bank_swift_code} help="Optional. 8 or 11 characters.">
                  {(aria) => <input {...aria} className={`${inputClass(errors.bank_swift_code)} uppercase`} value={form.bank_swift_code} onChange={(e) => set("bank_swift_code", e.target.value.toUpperCase())} />}
                </Field>
                <Field id="pq-sort" label="Branch / sort code" error={errors.bank_sort_code} help="Optional.">
                  {(aria) => <input {...aria} className={inputClass(errors.bank_sort_code)} value={form.bank_sort_code} onChange={(e) => set("bank_sort_code", e.target.value)} />}
                </Field>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6">
              <div className="space-y-6 rounded-2xl border border-emerald-100 bg-emerald-50 p-6">
                {([
                  ["female_beneficiary_target", "Female-headed household commitment (%)", 50, "Minimum 50% of beneficiaries must be female-headed households."],
                  ["vulnerable_group_target", "Vulnerable group inclusion (%)", 30, "Minimum 30% of beneficiaries from vulnerable groups (elderly, people with disabilities, etc.)."],
                ] as Array<["female_beneficiary_target" | "vulnerable_group_target", string, number, string]>).map(([key, label, min, help]) => (
                  <div key={key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label htmlFor={`pq-${key}`} className="text-sm font-bold text-emerald-900">{label}</label>
                      <span className="text-lg font-bold text-emerald-700" aria-hidden="true">{form[key]}%</span>
                    </div>
                    <input
                      id={`pq-${key}`}
                      type="range"
                      min={min}
                      max={100}
                      step={5}
                      value={form[key]}
                      aria-valuetext={`${form[key]} percent`}
                      onChange={(e) => set(key, parseInt(e.target.value, 10))}
                      className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-emerald-200 accent-emerald-600"
                    />
                    <p className="text-xs text-emerald-800">{help}</p>
                    {errors[key] && <p role="alert" className="text-xs text-rose-600">{errors[key]}</p>}
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <label className="flex cursor-pointer gap-4 rounded-2xl bg-slate-900 p-6 text-white">
                  <input
                    type="checkbox"
                    checked={form.declaration_accepted}
                    aria-invalid={Boolean(errors.declaration_accepted)}
                    onChange={(e) => set("declaration_accepted", e.target.checked)}
                    className="mt-1 h-5 w-5 shrink-0 accent-emerald-500"
                  />
                  <span className="text-sm leading-relaxed text-slate-200">
                    I declare that the information and documents in this application are true, accurate and complete, and that I am authorised to submit it on
                    behalf of the organisation. I understand that a false declaration may lead to disqualification, blacklisting and legal action, and I commit to
                    the inclusion targets above.
                  </span>
                </label>
                {errors.declaration_accepted && <p role="alert" className="ml-1 text-xs text-rose-600">{errors.declaration_accepted}</p>}
              </div>
            </div>
          )}

          {formError && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{formError}</p>}

          <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-6 sm:flex-row sm:justify-between">
            <div className="flex gap-3">
              {step > 1 && (
                <button type="button" onClick={() => { setErrors({}); setFormError(""); goToStep(step - 1); }} className="btn-secondary px-6">Previous</button>
              )}
              <button type="button" onClick={() => { setShowForm(false); setEditing(null); }} className="px-3 text-sm text-slate-500 underline">
                Save & exit
              </button>
            </div>
            <button type="submit" disabled={submitting} className="btn-primary flex items-center justify-center gap-2 rounded-xl px-10 py-3 shadow-lg shadow-emerald-600/20 disabled:opacity-60">
              {submitting && <Loader2 size={16} className="animate-spin" />}
              {step < 4 ? "Next step" : submitting ? "Submitting..." : editing ? "Resubmit application" : "Submit application"}
            </button>
          </div>
        </form>
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="pq-confirm-title">
          <div className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <h3 id="pq-confirm-title" className="text-lg font-bold text-slate-900">Submit your application?</h3>
            <p className="text-sm text-slate-600">
              You won&apos;t be able to edit it while it is being reviewed. Check that the bank details are correct — payments will be made to{" "}
              <span className="font-semibold">{form.bank_name}</span>, account ending{" "}
              <span className="font-mono font-semibold">{form.bank_account_number.replace(/\D/g, "").slice(-4)}</span>.
            </p>
            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => setConfirmOpen(false)} className="btn-secondary">Go back</button>
              <button type="button" onClick={() => void submit()} className="btn-primary" autoFocus>Submit</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
