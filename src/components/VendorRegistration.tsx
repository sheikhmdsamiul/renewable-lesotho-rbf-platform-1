import React, { useEffect, useState } from "react";
import { motion } from "motion/react";
import { CheckCircle2, ChevronRight, Circle, Eye, EyeOff, Loader2 } from "lucide-react";
import {
  registerVendor,
  requestRegistrationOtp,
  validateVendorRegistration,
  verifyRegistrationOtp,
  VendorRegistrationPayload,
} from "../api";
import { apiFieldErrors, EMAIL_PATTERN, Field, FieldErrors, FileDrop, inputClass, mobileNumberError } from "./formFields";

const TECH_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "SHS", label: "Solar Home Systems (SHS)" },
  { value: "ICS", label: "Improved Cookstoves (ICS)" },
  { value: "GMG", label: "Green Mini-Grids (GMG)" },
  { value: "SWP", label: "Solar Water Pumping (SWP)" },
  { value: "PUE", label: "Productive Use of Energy (PUE)" },
];
const DISTRICTS = ["Maseru", "Leribe", "Berea", "Mafeteng", "Mohale's Hoek", "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Butha-Buthe"];
const ORG_TYPES = [
  { value: "Private", label: "Private company" },
  { value: "NGO", label: "NGO / non-profit" },
  { value: "Cooperative", label: "Cooperative" },
  { value: "Public", label: "Public entity" },
];
const CERT_TYPES = ["pdf", "jpg", "jpeg", "png"];
const CERT_MAX_MB = 10;
const RESEND_SECONDS = 60;

// Which step each server field lives on, so a server error sends the user back there.
const STEP_ONE_FIELDS = new Set(["full_name", "username", "email", "password", "confirm_password", "mobile_number", "gender", "national_id"]);

// Client field keys use the API's snake_case names so server errors map 1:1.
type Form = {
  full_name: string;
  username: string;
  email: string;
  password: string;
  confirm_password: string;
  mobile_number: string;
  gender: "Male" | "Female" | "Other";
  national_id: string;
  organization_name: string;
  organization_type: string;
  company_registration_number: string;
  tax_id: string;
  address: string;
  region: string;
  associated_entities: string;
  technology_types: string[];
  device_id: string;
};

const EMPTY_FORM: Form = {
  full_name: "",
  username: "",
  email: "",
  password: "",
  confirm_password: "",
  mobile_number: "",
  gender: "Female",
  national_id: "",
  organization_name: "",
  organization_type: "Private",
  company_registration_number: "",
  tax_id: "",
  address: "",
  region: "Maseru",
  associated_entities: "",
  technology_types: [],
  device_id: "",
};

function passwordChecks(form: Form) {
  const pw = form.password;
  const lower = pw.toLowerCase();
  const personal = [form.username, form.email.split("@")[0], ...form.full_name.split(/\s+/)]
    .map((part) => part.trim().toLowerCase())
    .filter((part) => part.length >= 4);
  return [
    { label: "At least 8 characters", ok: pw.length >= 8 },
    { label: "Not only numbers", ok: pw.length > 0 && !/^\d+$/.test(pw) },
    { label: "Does not contain your name, username or email", ok: pw.length > 0 && !personal.some((part) => lower.includes(part)) },
  ];
}

function validateStep(step: number, form: Form, certificate: File | null, consent: boolean): FieldErrors {
  const errors: FieldErrors = {};
  if (step === 1) {
    if (!form.full_name.trim()) errors.full_name = "Enter the focal person's full name.";
    const username = form.username.trim();
    if (!username) errors.username = "Choose a username.";
    else if (username.length < 3) errors.username = "Username must be at least 3 characters.";
    else if (!/^[\w.@+-]+$/.test(username)) errors.username = "Use only letters, numbers and @ . + - _";
    if (!form.email.trim()) errors.email = "Email is required.";
    else if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = "Enter a valid email address.";
    const failed = passwordChecks(form).find((check) => !check.ok);
    if (!form.password) errors.password = "Create a password.";
    else if (failed) errors.password = `Password: ${failed.label.toLowerCase()}.`;
    if (form.confirm_password !== form.password) errors.confirm_password = "Passwords do not match.";
    const mobile = mobileNumberError(form.mobile_number);
    if (mobile) errors.mobile_number = mobile;
    if (!form.national_id.trim()) errors.national_id = "National ID or passport number is required.";
  }
  if (step === 2) {
    if (!form.organization_name.trim()) errors.organization_name = "Enter the registered name of the organisation.";
    if (!form.company_registration_number.trim()) errors.company_registration_number = "Enter the company registration number.";
    if (!form.tax_id.trim()) errors.tax_id = "Enter the Tax ID (TIN).";
    if (!form.address.trim()) errors.address = "Enter the physical address of the head office.";
    if (form.technology_types.length === 0) errors.technology_types = "Select at least one technology.";
    if (!certificate) errors.registration_certificate = "Upload the company registration certificate.";
    if (!consent) errors.consent_accepted = "You must confirm this declaration to register.";
  }
  return errors;
}

export default function VendorRegistration({
  onBackToLogin,
  onRegisterSuccess,
}: {
  onBackToLogin: () => void;
  onRegisterSuccess: (username: string) => void;
}) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [certificate, setCertificate] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [otp, setOtp] = useState("");
  const [otpNotice, setOtpNotice] = useState("");
  const [resendIn, setResendIn] = useState(0);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setTimeout(() => setResendIn((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendIn]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key as string];
      return next;
    });
  };

  const payload = (): VendorRegistrationPayload => ({
    username: form.username.trim(),
    password: form.password,
    fullName: form.full_name.trim(),
    email: form.email.trim().toLowerCase(),
    gender: form.gender,
    mobileNumber: form.mobile_number.replace(/\D/g, ""),
    nationalId: form.national_id.trim(),
    address: form.address.trim(),
    organizationName: form.organization_name.trim(),
    organizationType: form.organization_type,
    companyRegistrationNumber: form.company_registration_number.trim(),
    associatedEntities: form.associated_entities.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean),
    technologyTypes: form.technology_types,
    registrationCertificate: certificate,
    taxId: form.tax_id.trim(),
    deviceId: form.device_id.trim() || undefined,
    region: form.region,
    consentAccepted: consent,
  });

  const showServerErrors = (err: any, fallback: string) => {
    const { fields, message } = apiFieldErrors(err, fallback);
    setErrors(fields);
    setFormError(message);
    if (Object.keys(fields).some((key) => STEP_ONE_FIELDS.has(key))) setStep(1);
    else if (Object.keys(fields).length) setStep(2);
  };

  const sendCode = async () => {
    const data = payload();
    const response = await requestRegistrationOtp(data.email);
    setOtp("");
    setResendIn(RESEND_SECONDS);
    setOtpNotice(
      response.debugOtp
        ? `Development mode: email could not be sent. Use code ${response.debugOtp}.`
        : `We sent a 6-digit code to ${data.email}. It expires in 10 minutes.`,
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (step < 3) {
      const stepErrors = validateStep(step, form, certificate, consent);
      setErrors(stepErrors);
      if (Object.keys(stepErrors).length) {
        setFormError("Please correct the highlighted fields.");
        return;
      }
      if (step === 1) {
        setStep(2);
        return;
      }
      setBusy(true);
      try {
        await validateVendorRegistration(payload());
        await sendCode();
        setStep(3);
      } catch (err: any) {
        if (err?.status === 429) {
          setFormError(apiFieldErrors(err, "").message || "Please wait before requesting another code.");
          setStep(3);
        } else {
          showServerErrors(err, "We could not check your details. Please try again.");
        }
      } finally {
        setBusy(false);
      }
      return;
    }

    if (!/^\d{6}$/.test(otp)) {
      setErrors({ otp: "Enter the 6-digit code from the email." });
      return;
    }
    setBusy(true);
    try {
      await verifyRegistrationOtp(form.email.trim().toLowerCase(), otp);
    } catch (err: any) {
      const { message } = apiFieldErrors(err, "That code did not work. Request a new one.");
      setErrors({ otp: message });
      setBusy(false);
      return;
    }
    try {
      await registerVendor(payload());
      onRegisterSuccess(form.username.trim());
    } catch (err: any) {
      showServerErrors(err, "Registration failed. Please review your details and try again.");
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setBusy(true);
    setFormError("");
    try {
      await sendCode();
    } catch (err: any) {
      const retry = Number(err?.detailPayload?.retry_after || 0);
      if (retry) setResendIn(Math.min(retry, 3600));
      setFormError(apiFieldErrors(err, "Could not send a new code. Try again shortly.").message);
    } finally {
      setBusy(false);
    }
  };

  const checks = passwordChecks(form);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 py-12">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-2xl rounded-3xl border border-slate-100 bg-white p-6 shadow-xl sm:p-8"
      >
        <button type="button" onClick={onBackToLogin} className="mb-6 flex items-center gap-2 text-slate-500 transition-colors hover:text-slate-900">
          <ChevronRight className="rotate-180" size={18} />
          <span className="text-sm font-medium">Back to sign in</span>
        </button>

        <div className="mb-8">
          <div className="mb-4 flex items-center justify-between gap-4">
            <h1 className="text-2xl font-bold text-slate-900">
              {step === 1 ? "Register your organisation" : step === 2 ? "Organisation details" : "Verify your email"}
            </h1>
            <span className="shrink-0 text-sm font-bold text-slate-400">Step {step} of 3</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={1} aria-valuemax={3} aria-valuenow={step}>
            <motion.div animate={{ width: `${(step / 3) * 100}%` }} className="h-full bg-emerald-600" />
          </div>
          {step === 1 && (
            <p className="mt-4 text-sm text-slate-500">
              Vendor accounts are for companies delivering RBF projects. After registering you will complete pre-qualification before you can bid.
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-6">
          {step === 1 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Field id="reg-full-name" label="Focal person's full name" required error={errors.full_name}>
                {(aria) => <input {...aria} autoComplete="name" className={inputClass(errors.full_name)} value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />}
              </Field>
              <Field id="reg-username" label="Username" required error={errors.username} help="Used to sign in. Letters, numbers and @ . + - _">
                {(aria) => <input {...aria} autoComplete="username" className={inputClass(errors.username)} value={form.username} onChange={(e) => set("username", e.target.value.replace(/\s/g, ""))} />}
              </Field>
              <Field id="reg-email" label="Work email" required error={errors.email} help="We will send a verification code here.">
                {(aria) => <input {...aria} type="email" autoComplete="email" className={inputClass(errors.email)} value={form.email} onChange={(e) => set("email", e.target.value)} />}
              </Field>
              <Field id="reg-mobile" label="Mobile number" required error={errors.mobile_number} help="Lesotho numbers: 8 digits, e.g. 58 123 456. Others: include country code.">
                {(aria) => (
                  <input {...aria} type="tel" inputMode="tel" autoComplete="tel" className={inputClass(errors.mobile_number)} value={form.mobile_number} onChange={(e) => set("mobile_number", e.target.value.replace(/[^\d+\s-]/g, ""))} />
                )}
              </Field>
              <Field id="reg-password" label="Password" required error={errors.password}>
                {(aria) => (
                  <div className="relative">
                    <input {...aria} type={showPassword ? "text" : "password"} autoComplete="new-password" className={`${inputClass(errors.password)} pr-11`} value={form.password} onChange={(e) => set("password", e.target.value)} />
                    <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-500" aria-label={showPassword ? "Hide password" : "Show password"}>
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                )}
              </Field>
              <Field id="reg-confirm-password" label="Confirm password" required error={errors.confirm_password}>
                {(aria) => <input {...aria} type={showPassword ? "text" : "password"} autoComplete="new-password" className={inputClass(errors.confirm_password)} value={form.confirm_password} onChange={(e) => set("confirm_password", e.target.value)} />}
              </Field>
              <ul className="space-y-1 text-xs md:col-span-2" aria-label="Password requirements">
                {checks.map((check) => (
                  <li key={check.label} className={`flex items-center gap-2 ${check.ok ? "text-emerald-700" : "text-slate-500"}`}>
                    {check.ok ? <CheckCircle2 size={14} /> : <Circle size={14} />} {check.label}
                  </li>
                ))}
                <li className="pl-5 text-slate-400">Very common passwords are rejected.</li>
              </ul>
              <Field id="reg-gender" label="Gender of focal person" required>
                {(aria) => (
                  <select {...aria} className="input-field" value={form.gender} onChange={(e) => set("gender", e.target.value as Form["gender"])}>
                    <option value="Female">Female</option>
                    <option value="Male">Male</option>
                    <option value="Other">Other / prefer not to say</option>
                  </select>
                )}
              </Field>
              <Field id="reg-national-id" label="National ID or passport number" required error={errors.national_id}>
                {(aria) => <input {...aria} className={inputClass(errors.national_id)} value={form.national_id} onChange={(e) => set("national_id", e.target.value)} />}
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field id="reg-org-name" label="Registered organisation name" required error={errors.organization_name} className="md:col-span-2">
                  {(aria) => <input {...aria} autoComplete="organization" className={inputClass(errors.organization_name)} value={form.organization_name} onChange={(e) => set("organization_name", e.target.value)} />}
                </Field>
                <Field id="reg-org-type" label="Organisation type" required>
                  {(aria) => (
                    <select {...aria} className="input-field" value={form.organization_type} onChange={(e) => set("organization_type", e.target.value)}>
                      {ORG_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                    </select>
                  )}
                </Field>
                <Field id="reg-company-number" label="Company registration number" required error={errors.company_registration_number} help="As shown on your registration certificate.">
                  {(aria) => <input {...aria} className={inputClass(errors.company_registration_number)} value={form.company_registration_number} onChange={(e) => set("company_registration_number", e.target.value)} />}
                </Field>
                <Field id="reg-tax-id" label="Tax ID (TIN)" required error={errors.tax_id}>
                  {(aria) => <input {...aria} className={inputClass(errors.tax_id)} value={form.tax_id} onChange={(e) => set("tax_id", e.target.value)} />}
                </Field>
                <Field id="reg-region" label="Head office district" required>
                  {(aria) => (
                    <select {...aria} className="input-field" value={form.region} onChange={(e) => set("region", e.target.value)}>
                      {DISTRICTS.map((district) => <option key={district} value={district}>{district}</option>)}
                    </select>
                  )}
                </Field>
                <Field id="reg-address" label="Head office physical address" required error={errors.address} className="md:col-span-2">
                  {(aria) => <input {...aria} autoComplete="street-address" className={inputClass(errors.address)} value={form.address} onChange={(e) => set("address", e.target.value)} />}
                </Field>
                <Field id="reg-directors" label="Directors / partners" error={errors.associated_entities} help="One name per line or separated by commas. Used for integrity screening." className="md:col-span-2">
                  {(aria) => <textarea {...aria} className="input-field min-h-[80px]" value={form.associated_entities} onChange={(e) => set("associated_entities", e.target.value)} />}
                </Field>
              </div>

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
                        className={`rounded-xl px-4 py-2 text-sm font-semibold transition-all ${selected ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                      >
                        {tech.label}
                      </button>
                    );
                  })}
                </div>
                {errors.technology_types && <p role="alert" className="ml-1 text-xs text-rose-600">{errors.technology_types}</p>}
              </fieldset>

              <FileDrop
                id="reg-certificate"
                label="Company registration certificate"
                required
                accept={CERT_TYPES}
                maxMb={CERT_MAX_MB}
                file={certificate}
                error={errors.registration_certificate}
                onChange={(file, error) => {
                  setCertificate(file);
                  setErrors((prev) => {
                    const next = { ...prev };
                    if (error) next.registration_certificate = error;
                    else delete next.registration_certificate;
                    return next;
                  });
                }}
              />

              <div className="space-y-1">
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0 accent-emerald-600"
                    checked={consent}
                    aria-invalid={Boolean(errors.consent_accepted)}
                    onChange={(e) => {
                      setConsent(e.target.checked);
                      setErrors((prev) => { const next = { ...prev }; delete next.consent_accepted; return next; });
                    }}
                  />
                  <span>
                    I confirm that I am authorised to register this organisation, that the information above is accurate, and I agree that the RBF
                    Management Team may process it for vendor verification, pre-qualification, integrity screening and programme monitoring.
                  </span>
                </label>
                {errors.consent_accepted && <p role="alert" className="ml-1 text-xs text-rose-600">{errors.consent_accepted}</p>}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6 py-2">
              <p className="text-center text-slate-600">
                Enter the 6-digit code sent to <span className="font-semibold text-slate-900">{form.email.trim().toLowerCase()}</span>.
              </p>
              {otpNotice && <p className="text-center text-xs font-medium text-emerald-700" role="status">{otpNotice}</p>}
              <div className="flex flex-col items-center gap-2">
                <label htmlFor="reg-otp" className="sr-only">Verification code</label>
                <input
                  id="reg-otp"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={otp}
                  aria-invalid={Boolean(errors.otp)}
                  aria-describedby={errors.otp ? "reg-otp-error" : undefined}
                  onChange={(e) => { setOtp(e.target.value.replace(/\D/g, "").slice(0, 6)); setErrors({}); }}
                  className={`w-full max-w-[300px] rounded-2xl border-2 py-5 text-center text-4xl font-black tracking-[0.5em] outline-none focus:ring-0 ${errors.otp ? "border-rose-400" : "border-slate-200 focus:border-emerald-500"}`}
                  placeholder="000000"
                />
                {errors.otp && <p id="reg-otp-error" role="alert" className="text-center text-xs text-rose-600">{errors.otp}</p>}
              </div>
              <div className="flex flex-col items-center gap-2 text-sm text-slate-500">
                <p>
                  Didn&apos;t get it? Check your spam folder, or{" "}
                  <button type="button" onClick={resend} disabled={busy || resendIn > 0} className="font-bold text-emerald-700 hover:underline disabled:text-slate-400 disabled:no-underline">
                    {resendIn > 0 ? `resend in ${resendIn}s` : "send a new code"}
                  </button>
                </p>
                <button type="button" onClick={() => { setStep(1); setErrors({}); setFormError(""); }} className="text-xs text-slate-500 underline">
                  Wrong email? Change it
                </button>
              </div>
            </div>
          )}

          {formError && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{formError}</p>}

          <div className="flex items-center justify-between gap-3 pt-2">
            {step > 1 ? (
              <button type="button" onClick={() => { setErrors({}); setFormError(""); setStep(step - 1); }} disabled={busy} className="btn-secondary rounded-xl px-6 py-3 disabled:opacity-60">
                Back
              </button>
            ) : <span />}
            <button type="submit" disabled={busy} className="btn-primary flex items-center gap-2 rounded-xl px-6 py-3 shadow-lg shadow-emerald-600/20 disabled:opacity-60">
              {busy && <Loader2 size={16} className="animate-spin" />}
              {step === 1 ? "Continue" : step === 2 ? (busy ? "Checking details..." : "Send verification code") : busy ? "Creating account..." : "Verify & create account"}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
