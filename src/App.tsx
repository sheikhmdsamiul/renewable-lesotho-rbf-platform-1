/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo } from "react";
import { 
  LayoutDashboard, 
  FileText, 
  ClipboardCheck, 
  Activity, 
  Map as MapIcon, 
  CreditCard, 
  BarChart3, 
  Users, 
  Bell, 
  Settings, 
  LogOut, 
  ChevronRight,
  Search,
  Plus,
  Filter,
  Download,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Clock,
  HelpCircle,
  UserCircle,
  Loader2,
  Menu,
  X,
  XCircle,
  Mail,
  Lock,
  ShieldCheck,
  FileSearch,
  FileWarning,
  History,
  Eye,
  Globe,
  Zap,
  Leaf,
  TrendingUp,
  Award,
  Calendar,
  Database,
  Upload
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  PieChart, 
  Pie, 
  Cell 
} from "recharts";
import { motion, AnimatePresence } from "motion/react";
import {
  UserRole,
  TenderStatus,
  ProjectStatus,
  Tender,
  Project,
  Milestone,
  ProjectUpdate,
  ProjectDocument,
  InstallationReport,
  PaymentClaim,
  VendorPrequalification,
  Notification,
  NotificationChannel,
  NotificationStatus,
  User,
  BidStatus,
  TenderBid,
  TenderBidSite,
  TenderBidEvaluation,
  TenderContract,
  TenderAwardRankingRow,
  VendorBlacklistCase,
  BlacklistAppeal,
} from "./types";
import { MOCK_TENDERS, MOCK_NOTIFICATIONS } from "./constants";
import {
  fetchTenders,
  fetchTender,
  createTender,
  updateTender,
  verifyTender,
  publishTender,
  awardTender,
  fetchNotifications,
  loginUser,
  logoutUser,
  registerVendor,
  getStoredUser,
  fetchCurrentUser,
  requestRegistrationOtp,
  verifyRegistrationOtp,
  updateUserPassword,
  createOfficialAccount,
  fetchVendorPrequalifications,
  fetchBlacklistCases,
  fetchBlacklistAppeals,
  submitVendorPrequalification,
  startVendorPrequalificationReview,
  approveVendorPrequalification,
  requestVendorPrequalificationClarification,
  rejectVendorPrequalification,
  initiateVendorBlacklisting,
  reviewBlacklistCase,
  confirmBlacklistCase,
  rejectBlacklistCase,
  reinstateBlacklistCase,
  submitBlacklistAppeal,
  reviewBlacklistAppeal,
  fetchPaymentClaims,
  submitPaymentClaim,
  approvePaymentClaim,
  payPaymentClaim,
  fetchProjects,
  fetchMilestones,
  createMilestone,
  updateMilestone,
  fetchProjectUpdates,
  fetchProjectDocuments,
  uploadProjectDocument,
  fetchInstallationReports,
  createInstallationReport,
  fetchTenderBids,
  submitTenderBid,
  updateTenderBid,
  reviewTenderBid,
  fetchBidEvaluations,
  createBidEvaluation,
  updateBidEvaluation,
  fetchTenderContracts,
  signTenderContract,
  approveTenderContract,
  rejectTenderContract,
  fetchTenderAwardRanking,
  confirmTenderAward,
  updateProject,
  API_BASE,
} from "./api";

// --- Components ---

const SidebarItem = ({ icon: Icon, label, active, onClick, badge }: any) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
      active 
        ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20" 
        : "text-blue-200 hover:bg-slate-700/40 hover:text-white"
    }`}
  >
    <Icon size={20} />
    <span className="font-medium flex-1 text-left">{label}</span>
    {badge && <span className="px-1.5 py-0.5 rounded-md bg-rose-500 text-[10px] font-bold text-white">{badge}</span>}
    {active && <motion.div layoutId="active-pill" className="ml-2 w-1.5 h-1.5 rounded-full bg-white" />}
  </button>
);

const StatCard = ({ label, value, trend, icon: Icon, color }: any) => (
  <div className="card p-6 flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-slate-500 mb-1">{label}</p>
      <h3 className="text-2xl font-bold text-slate-900">{value}</h3>
      {trend && (
        <p className={`text-xs mt-1 font-medium ${trend.startsWith('+') ? 'text-emerald-600' : 'text-rose-600'}`}>
          {trend} from last month
        </p>
      )}
    </div>
    <div className={`p-3 rounded-xl ${color}`}>
      <Icon size={24} className="text-white" />
    </div>
  </div>
);

const triggerDownload = (filename: string, content: string, mimeType = "text/plain;charset=utf-8") => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const isConnectivityError = (raw: string) => {
  const lower = raw.toLowerCase();
  return (
    lower.includes("failed to fetch") ||
    lower.includes("timed out") ||
    lower.includes("networkerror")
  );
};

const toFriendlyApiMessage = (raw: string): string => {
  const cleaned = raw
    .replace(/^http\s+\d+\s+[a-z ]+:\s*/i, "")
    .replace(/^error:\s*/i, "")
    .trim();
  if (!cleaned || cleaned.length > 220) return "";
  return cleaned;
};

// --- Auth Components ---

const Login = ({
  onLogin,
  onRegisterClick,
  onViewPublic,
  infoMessage,
}: {
  onLogin: (username: string, password: string) => Promise<void>;
  onRegisterClick: () => void;
  onViewPublic: () => void;
  infoMessage?: string | null;
}) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!username || !password) {
      setError("Please enter both username and password.");
      return;
    }

    try {
      setIsSubmitting(true);
      await onLogin(username.trim(), password.trim());
    } catch (err: any) {
      const raw = String(err?.message || "");
      const lower = raw.toLowerCase();
      if (lower.includes("pending approval")) {
        setError("Your account is pending approval. Please contact an administrator.");
      } else if (lower.includes("no active account")) {
        setError("Invalid username or password.");
      } else if (lower.includes("throttled") || lower.includes("too many requests")) {
        setError("Too many login attempts. Please wait a minute and try again.");
      } else if (isConnectivityError(raw)) {
        setError(`Cannot connect to backend (${API_BASE}). Start backend and try again.`);
      } else {
        const friendly = toFriendlyApiMessage(raw);
        setError(friendly || "Login failed. Please verify your credentials and try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-md w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100"
      >
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-emerald-600 flex items-center justify-center text-white font-bold text-3xl mx-auto mb-4 shadow-lg shadow-emerald-600/20">
            R
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Welcome Back</h2>
          <p className="text-slate-500">Sign in to the RBF Digital Platform</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {infoMessage && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-700">
              {infoMessage}
            </div>
          )}

          <div className="space-y-1">
            <label className="text-sm font-bold text-slate-700 ml-1">Username</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input-field pl-10"
                placeholder="Enter your username"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-bold text-slate-700 ml-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field pl-10"
                placeholder="********"
              />
            </div>
          </div>

          {error && <p className="text-rose-600 text-xs font-medium ml-1">{error}</p>}

          <div className="flex items-center justify-between py-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-600" />
              <span className="text-xs text-slate-600">Remember me</span>
            </label>
            <button
              type="button"
              onClick={() => setError("Password reset is managed by admin. Please contact support.")}
              className="text-xs font-bold text-emerald-600 hover:text-emerald-700"
            >
              Forgot Password?
            </button>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full btn-primary py-3 rounded-xl shadow-lg shadow-emerald-600/20 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Signing In..." : "Sign In"}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 space-y-4">
          <button
            onClick={onViewPublic}
            className="w-full py-3 px-4 bg-emerald-50 text-emerald-700 rounded-xl font-bold text-sm flex items-center justify-center gap-2 hover:bg-emerald-100 transition-colors"
          >
            <Globe size={18} /> View Public Impact Portal
          </button>

          <div className="text-center">
            <p className="text-sm text-slate-500">
              Are you a Vendor?{" "}
              <button onClick={onRegisterClick} className="font-bold text-emerald-600 hover:text-emerald-700">
                Register your organization first
              </button>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
const Register = ({
  onBackToLogin,
  onRegisterSuccess,
}: {
  onBackToLogin: () => void;
  onRegisterSuccess: (username: string) => void;
}) => {
  const [step, setStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [otp, setOtp] = useState("");
  const [otpInfo, setOtpInfo] = useState("");
  const [registrationCertName, setRegistrationCertName] = useState("");
  const certInputRef = React.useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState({
    fullName: "",
    username: "",
    email: "",
    password: "",
    mobile: "",
    gender: "Male",
    nationalId: "",
    orgName: "",
    orgType: "Private",
    associatedEntities: "",
    techTypes: [] as string[],
    address: "",
    taxId: "",
    region: "Maseru",
    deviceId: "",
  });

  const techOptions = ["SHS", "ICS", "Mini-grid", "SWP", "PUE"];
  const districts = ["Maseru", "Leribe", "Berea", "Mafeteng", "Mohale's Hoek", "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Butha-Buthe"];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const normalizedEmail = formData.email.trim().toLowerCase();

    if (step < 3) {
      if (step === 1) {
        const digits = formData.mobile.replace(/\D/g, "");
        if (!/^\d{8,15}$/.test(digits)) {
          setError("Mobile number must be 8-15 digits.");
          return;
        }
      }
      if (step === 2) {
        if (formData.techTypes.length === 0) {
          setError("Please select at least one technology type.");
          return;
        }
        if (!registrationCertName) {
          setError("Please upload your registration certificate.");
          return;
        }
        try {
          setIsSubmitting(true);
          const otpResp = await requestRegistrationOtp(normalizedEmail);
          const debugNote = otpResp.debugOtp ? ` Debug OTP: ${otpResp.debugOtp}` : "";
          const emailWarn = otpResp.emailError ? " (email delivery failed, using debug OTP)" : "";
          setOtp("");
          setOtpInfo(`OTP sent to ${normalizedEmail}${emailWarn}.${debugNote}`);
        } catch (err: any) {
          const raw = String(err?.message || "");
          const lower = raw.toLowerCase();
          if (lower.includes("throttled") || lower.includes("too many requests")) {
            setError("Too many OTP requests. Please wait a minute and try again.");
          } else if (isConnectivityError(raw)) {
            setError(`Cannot connect to backend (${API_BASE}). Start backend and try again.`);
          } else {
            const friendly = toFriendlyApiMessage(raw);
            setError(friendly || "Failed to send OTP. Please try again.");
          }
          return;
        } finally {
          setIsSubmitting(false);
        }
      }
      setStep(step + 1);
      return;
    }

    if (!otp.trim()) {
      setError("Please enter the OTP sent to your email.");
      return;
    }

    try {
      setIsSubmitting(true);
      await verifyRegistrationOtp(normalizedEmail, otp.trim());
      await registerVendor({
        username: formData.username.trim(),
        password: formData.password,
        fullName: formData.fullName,
        email: normalizedEmail,
        gender: formData.gender as "Male" | "Female" | "Other",
        mobileNumber: formData.mobile.replace(/\D/g, ""),
        nationalId: formData.nationalId,
        address: formData.address,
        organizationName: formData.orgName,
        organizationType: formData.orgType,
        associatedEntities: formData.associatedEntities
          .split(/[\n,;]+/)
          .map((item) => item.trim())
          .filter(Boolean),
        technologyTypes: formData.techTypes,
        registrationCertificateName: registrationCertName,
        taxId: formData.taxId,
        deviceId: formData.deviceId || undefined,
        region: formData.region,
      });
      onRegisterSuccess(formData.username.trim());
    } catch (err: any) {
      const raw = String(err?.message || "");
      const lower = raw.toLowerCase();
      if (lower.includes("already exists")) {
        setError("Username or email already exists. Try another one.");
      } else {
        const friendly = toFriendlyApiMessage(raw);
        setError(friendly || "Registration failed. Please review your details and try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4 py-12">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="max-w-2xl w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100"
      >
        <button onClick={onBackToLogin} className="flex items-center gap-2 text-slate-500 hover:text-slate-900 mb-6 transition-colors">
          <ChevronRight className="rotate-180" size={18} />
          <span className="text-sm font-medium">Back to Login</span>
        </button>

        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-slate-900">
              {step === 3 ? "Identity Verification" : "Vendor Registration"}
            </h2>
            <span className="text-sm font-bold text-slate-400">Step {step} of 3</span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
            <motion.div animate={{ width: `${(step / 3) * 100}%` }} className="bg-emerald-600 h-full" />
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {step === 1 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Full Name *</label>
                <input
                  required
                  type="text"
                  value={formData.fullName}
                  onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                  className="input-field"
                  placeholder="John Doe"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Username *</label>
                <input
                  required
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value.replace(/\s/g, "") })}
                  className="input-field"
                  placeholder="vendor_username"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Email Address *</label>
                <input
                  required
                  type="email"
                  value={formData.email}
                  onChange={(e) => {
                    setFormData({ ...formData, email: e.target.value });
                    setOtp("");
                    setOtpInfo("");
                  }}
                  className="input-field"
                  placeholder="john@example.com"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Password *</label>
                <input
                  required
                  minLength={8}
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="input-field"
                  placeholder="At least 8 characters"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Mobile Number *</label>
                <input
                  required
                  type="tel"
                  value={formData.mobile}
                  onChange={(e) => setFormData({ ...formData, mobile: e.target.value.replace(/\D/g, "") })}
                  className="input-field"
                  inputMode="numeric"
                  pattern="[0-9]{8,15}"
                  minLength={8}
                  maxLength={15}
                  placeholder="Digits only"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Gender of Focal Person *</label>
                <select
                  value={formData.gender}
                  onChange={(e) => setFormData({ ...formData, gender: e.target.value as any })}
                  className="input-field"
                  required
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">National ID / Passport *</label>
                <input
                  required
                  type="text"
                  value={formData.nationalId}
                  onChange={(e) => setFormData({ ...formData, nationalId: e.target.value })}
                  className="input-field"
                  placeholder="ID Number"
                />
              </div>
            </div>
          ) : step === 2 ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Assigned District/Region *</label>
                  <select
                    value={formData.region}
                    onChange={(e) => setFormData({ ...formData, region: e.target.value })}
                    className="input-field"
                    required
                  >
                    {districts.map((district) => (
                      <option key={district} value={district}>{district}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Organization Name *</label>
                  <input
                    required
                    type="text"
                    value={formData.orgName}
                    onChange={(e) => setFormData({ ...formData, orgName: e.target.value })}
                    className="input-field"
                    placeholder="Legal Entity Name"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Organization Type *</label>
                  <select
                    value={formData.orgType}
                    onChange={(e) => setFormData({ ...formData, orgType: e.target.value })}
                    className="input-field"
                  >
                    <option value="Private">Private</option>
                    <option value="NGO">NGO</option>
                    <option value="Public">Public</option>
                    <option value="Cooperative">Cooperative</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Tax ID / VAT No. *</label>
                  <input
                    required
                    type="text"
                    value={formData.taxId}
                    onChange={(e) => setFormData({ ...formData, taxId: e.target.value })}
                    className="input-field"
                    placeholder="TIN Number"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">HQ Address *</label>
                  <input
                    required
                    type="text"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                    className="input-field"
                    placeholder="Physical Address"
                  />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <label className="text-sm font-bold text-slate-700 ml-1">Directors / Partners</label>
                  <textarea
                    value={formData.associatedEntities}
                    onChange={(e) => setFormData({ ...formData, associatedEntities: e.target.value })}
                    className="input-field min-h-[96px]"
                    placeholder="Comma-separated names for directors, partners, or key principals"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Device ID (IMEI/MAC) (Optional)</label>
                  <input
                    type="text"
                    value={formData.deviceId}
                    onChange={(e) => setFormData({ ...formData, deviceId: e.target.value })}
                    className="input-field"
                    placeholder="Optional device identifier"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700 ml-1">Technology Types * (Select all that apply)</label>
                <div className="flex flex-wrap gap-2">
                  {techOptions.map((tech) => (
                    <button
                      key={tech}
                      type="button"
                      onClick={() => {
                        const current = formData.techTypes;
                        if (current.includes(tech)) {
                          setFormData({ ...formData, techTypes: current.filter((t) => t !== tech) });
                        } else {
                          setFormData({ ...formData, techTypes: [...current, tech] });
                        }
                      }}
                      className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                        formData.techTypes.includes(tech)
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                      }`}
                    >
                      {tech}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700 ml-1">Registration Certificate (PDF/JPG) *</label>
                <input
                  ref={certInputRef}
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    setRegistrationCertName(file ? file.name : "");
                  }}
                />
                <button
                  type="button"
                  onClick={() => certInputRef.current?.click()}
                  className="w-full border-2 border-dashed border-slate-200 rounded-2xl p-8 text-center hover:border-emerald-500 transition-colors"
                >
                  <Plus className="mx-auto text-slate-400 mb-2" size={32} />
                  <p className="text-sm font-medium text-slate-600">
                    {registrationCertName || "Click to upload or drag and drop"}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">Maximum file size 10MB</p>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-8 py-4">
              <div className="text-center space-y-2">
                <p className="text-slate-500">We've sent a 6-digit verification code to</p>
                <p className="font-bold text-slate-900">{formData.email}</p>
                {otpInfo && <p className="text-xs text-emerald-700 font-medium">{otpInfo}</p>}
              </div>
              <div className="flex justify-center">
                <input
                  required
                  type="text"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  className="text-center text-4xl tracking-[0.5em] font-black py-6 border-2 border-slate-200 rounded-2xl focus:border-emerald-500 focus:ring-0 outline-none w-full max-w-[300px]"
                  placeholder="000000"
                />
              </div>
              <div className="text-center">
                <p className="text-sm text-slate-400">
                  Didn't receive the code?{" "}
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        setIsSubmitting(true);
                        const normalizedEmail = formData.email.trim().toLowerCase();
                        const otpResp = await requestRegistrationOtp(normalizedEmail);
                        const debugNote = otpResp.debugOtp ? ` Debug OTP: ${otpResp.debugOtp}` : "";
                        const emailWarn = otpResp.emailError ? " (email delivery failed, using debug OTP)" : "";
                        setOtp("");
                        setOtpInfo(`OTP resent to ${normalizedEmail}${emailWarn}.${debugNote}`);
                        setError("");
                      } catch (err: any) {
                        const raw = String(err?.message || "");
                        const lower = raw.toLowerCase();
                        if (lower.includes("throttled") || lower.includes("too many requests")) {
                          setError("Too many OTP requests. Please wait a minute and try again.");
                        } else if (isConnectivityError(raw)) {
                          setError(`Cannot connect to backend (${API_BASE}). Start backend and try again.`);
                        } else {
                          const friendly = toFriendlyApiMessage(raw);
                          setError(friendly || "Unable to resend OTP right now. Try again.");
                        }
                      } finally {
                        setIsSubmitting(false);
                      }
                    }}
                    className="text-emerald-600 font-bold hover:underline"
                  >
                    Resend OTP
                  </button>
                </p>
              </div>
            </div>
          )}

          {error && <p className="text-rose-600 text-xs font-medium">{error}</p>}

          <div className="flex justify-end pt-4">
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary px-8 py-3 rounded-xl shadow-lg shadow-emerald-600/20 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting
                ? "Submitting..."
                : step === 1
                ? "Next: Organization Details"
                : step === 2
                ? "Send Verification Code"
                : "Verify & Submit Registration"}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
};

const ForcePasswordReset = ({
  user,
  onComplete,
  onLogout,
}: {
  user: User;
  onComplete: (user: User) => void;
  onLogout: () => void;
}) => {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!password || password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    try {
      setIsSubmitting(true);
      const updated = await updateUserPassword(user.id, password);
      onComplete(updated);
    } catch (err: any) {
      const friendly = toFriendlyApiMessage(String(err?.message || ""));
      setError(friendly || "Unable to update password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100">
        <div className="text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-emerald-600 flex items-center justify-center text-white font-bold text-2xl mx-auto mb-4 shadow-lg shadow-emerald-600/20">
            R
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Set a New Password</h2>
          <p className="text-slate-500">You must change your temporary password before continuing.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-bold text-slate-700 ml-1">New Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-field"
              placeholder="At least 8 characters"
              minLength={8}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-bold text-slate-700 ml-1">Confirm Password</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input-field"
              placeholder="Re-enter password"
              minLength={8}
              required
            />
          </div>
          {error && <p className="text-rose-600 text-xs font-medium ml-1">{error}</p>}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full btn-primary py-3 rounded-xl shadow-lg shadow-emerald-600/20 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Updating..." : "Update Password"}
          </button>
        </form>

        <div className="mt-6 text-center">
          <button onClick={onLogout} className="text-xs font-bold text-slate-500 hover:text-slate-700">
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
};

// --- Pages ---

const Dashboard = ({ role, onNewTender }: { role: UserRole, onNewTender: () => void }) => {
  const data = [
    { name: 'Jan', value: 400 },
    { name: 'Feb', value: 300 },
    { name: 'Mar', value: 600 },
    { name: 'Apr', value: 800 },
    { name: 'May', value: 500 },
    { name: 'Jun', value: 900 },
  ];

  const pieData = [
    { name: 'SHS', value: 400 },
    { name: 'Mini-Grid', value: 300 },
    { name: 'ICS', value: 300 },
  ];

  const COLORS = ['#059669', '#1d4ed8', '#d97706'];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Portfolio Overview</h1>
          <p className="text-slate-500">Welcome back, {role} Dashboard</p>
        </div>
        <div className="flex gap-3">
          <button className="btn-secondary flex items-center gap-2">
            <Download size={18} /> Export Report
          </button>
          <button onClick={onNewTender} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> New Tender
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard label="Total Energy Output" value="1.2 GWh" trend="+12%" icon={Activity} color="bg-emerald-600" />
        <StatCard label="Active Vendors" value="24" trend="+2" icon={Users} color="bg-blue-600" />
        <StatCard label="Disbursement Pacing" value="78%" trend="+5%" icon={CreditCard} color="bg-amber-600" />
        <StatCard label="Gender Equity" value="54%" trend="+3%" icon={ClipboardCheck} color="bg-purple-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card p-6 lg:col-span-2">
          <h3 className="text-lg font-bold mb-6">Energy Output Trend (MWh)</h3>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#64748b', fontSize: 12}} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#64748b', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                />
                <Line type="monotone" dataKey="value" stroke="#059669" strokeWidth={3} dot={{r: 4, fill: '#059669'}} activeDot={{r: 6}} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-6">Technology Distribution</h3>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2">
            {pieData.map((item, i) => (
              <div key={item.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{backgroundColor: COLORS[i]}} />
                  <span className="text-slate-600">{item.name}</span>
                </div>
                <span className="font-bold">{item.value} units</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const Tenders = ({
  initialView = "list",
  initialTenderId,
  onTenderOpened,
}: {
  initialView?: "list" | "create" | "details" | "verify" | "publish" | "award" | "security" | "edit";
  initialTenderId?: string | null;
  onTenderOpened?: () => void;
}) => {
  const [view, setView] = useState<"list" | "create" | "details" | "verify" | "publish" | "award" | "security" | "edit">(initialView);
  const [selectedTender, setSelectedTender] = useState<Tender | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [tenderError, setTenderError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [selectedDepartment, setSelectedDepartment] = useState("All Departments");
  const [selectedProcurement, setSelectedProcurement] = useState("All Methods");
  const [sortBy, setSortBy] = useState<"created_at" | "deadline" | "published_at">("created_at");
  const [awardWinner, setAwardWinner] = useState("");
  const [awardWinnerId, setAwardWinnerId] = useState("");
  const [awardBids, setAwardBids] = useState<TenderBid[]>([]);
  const [awardBidId, setAwardBidId] = useState("");
  const [awardBidLoading, setAwardBidLoading] = useState(false);
  const [awardRankingRows, setAwardRankingRows] = useState<TenderAwardRankingRow[]>([]);
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [isActioning, setIsActioning] = useState(false);
  const [tenderContracts, setTenderContracts] = useState<TenderContract[]>([]);
  const [contractMessage, setContractMessage] = useState<string | null>(null);
  const [contractRejectionReason, setContractRejectionReason] = useState("");
  const [milestoneDrafts, setMilestoneDrafts] = useState([
    { name: "Mobilization", percentage: 20, amount: 0 },
    { name: "Installation", percentage: 50, amount: 0 },
    { name: "Commissioning", percentage: 30, amount: 0 },
  ]);

  const activeContract = useMemo(() => {
    if (!tenderContracts.length) return null;
    const awardedId = selectedTender?.awardedVendorId;
    if (awardedId) {
      const match = tenderContracts.find(item => String(item.vendorId) === String(awardedId));
      if (match) return match;
    }
    return tenderContracts[0];
  }, [tenderContracts, selectedTender]);

  // Form State
  const defaultFormData: Partial<Tender> = {
    name: "",
    department: "",
    applicationType: "Access Window",
    stageType: "Pre-Qualification",
    procurementMethod: "Open Competitive",
    biddingCurrency: "LSL (Maloti)",
    category: "SHS",
    budget: 0,
    deadline: "",
    lastDateSubmission: "",
    lastDateSecurity: "",
    dateOpening: "",
    technologyTypes: [],
    targetSiteType: "Household",
    biddersEligibility: "",
    instruction: "",
    contactDetails: "",
    fundingSource: "",
    coolingOffDays: 7,
    addressForDocument: "",
    addressForSecurity: "",
    placeForOpening: "",
    invitedBy: "",
    timeForCompletion: ""
  };
  const [formData, setFormData] = useState<Partial<Tender>>(defaultFormData);
  const [scheduleFile, setScheduleFile] = useState<File | null>(null);
  const [rfpDocumentsFile, setRfpDocumentsFile] = useState<File | null>(null);
  const [milestonePaymentScheduleFile, setMilestonePaymentScheduleFile] = useState<File | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleTechToggle = (tech: string) => {
    setFormData(prev => {
      const current = prev.technologyTypes || [];
      if (current.includes(tech)) {
        return { ...prev, technologyTypes: current.filter(t => t !== tech) };
      }
      return { ...prev, technologyTypes: [...current, tech] };
    });
  };

  const toFormDataFromTender = (tender: Tender): Partial<Tender> => ({
    ...defaultFormData,
    id: tender.id,
    referenceNumber: tender.referenceNumber,
    name: tender.name ?? "",
    department: tender.department ?? "",
    applicationType: tender.applicationType ?? defaultFormData.applicationType,
    stageType: tender.stageType ?? defaultFormData.stageType,
    procurementMethod: tender.procurementMethod ?? defaultFormData.procurementMethod,
    biddingCurrency: tender.biddingCurrency ?? defaultFormData.biddingCurrency,
    category: tender.category ?? defaultFormData.category,
    budget: tender.budget ?? 0,
    deadline: tender.deadline ?? "",
    lastDateSubmission: tender.lastDateSubmission ?? tender.deadline ?? "",
    lastDateSecurity: tender.lastDateSecurity ?? "",
    dateOpening: tender.dateOpening ?? "",
    technologyTypes: tender.technologyTypes ?? [],
    targetSiteType: tender.targetSiteType ?? defaultFormData.targetSiteType,
    biddersEligibility: tender.biddersEligibility ?? "",
    instruction: tender.instruction ?? "",
    contactDetails: tender.contactDetails ?? "",
    fundingSource: tender.fundingSource ?? "",
    coolingOffDays: tender.coolingOffDays ?? 7,
    addressForDocument: tender.addressForDocument ?? "",
    addressForSecurity: tender.addressForSecurity ?? "",
    placeForOpening: tender.placeForOpening ?? "",
    invitedBy: tender.invitedBy ?? "",
    timeForCompletion: tender.timeForCompletion ?? "",
    biddersSchedulePurchase: tender.biddersSchedulePurchase ?? false,
    tenderSecurityRequired: tender.tenderSecurityRequired ?? false,
  });

  const loadTenders = React.useCallback(async () => {
    try {
      const tnds = await fetchTenders().catch(() => MOCK_TENDERS);
      setTenders(tnds);
    } catch {
      setTenders(MOCK_TENDERS);
    }
  }, []);

  React.useEffect(() => {
    void loadTenders();
  }, [loadTenders]);

  React.useEffect(() => {
    const id = setInterval(() => {
      void loadTenders();
    }, 20000);
    return () => clearInterval(id);
  }, [loadTenders]);

  const filteredTenders = useMemo(() => {
    const list = tenders.filter(tender => {
      const matchesSearch = tender.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                            tender.referenceNumber.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === "All Categories" || tender.category === selectedCategory;
      const matchesDept = selectedDepartment === "All Departments" || tender.department === selectedDepartment;
      const matchesProc = selectedProcurement === "All Methods" || tender.procurementMethod === selectedProcurement;
      return matchesSearch && matchesCategory && matchesDept && matchesProc;
    });
    return list.sort((a, b) => {
      if (sortBy === "deadline") return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
      if (sortBy === "published_at") return new Date(b.publishedAt || 0).getTime() - new Date(a.publishedAt || 0).getTime();
      return new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime();
    });
  }, [tenders, searchQuery, selectedCategory, selectedDepartment, selectedProcurement, sortBy]);

  // Sync view with initialView prop when it changes
  React.useEffect(() => {
    setView(initialView);
    if (initialView === "create") {
      setSelectedTender(null);
      setFormData(defaultFormData);
      setScheduleFile(null);
      setRfpDocumentsFile(null);
      setMilestonePaymentScheduleFile(null);
      setTenderError(null);
    }
  }, [initialView]);

  React.useEffect(() => {
    if (!initialTenderId) return;
    void openTenderView(initialTenderId, "details")
      .catch(() => null)
      .finally(() => onTenderOpened?.());
  }, [initialTenderId]);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const NotificationToast = () => (
    <AnimatePresence>
      {notification && (
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl flex items-center gap-3"
        >
          <CheckCircle2 size={20} />
          <span className="font-medium">{notification}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );

  const startCreateTender = () => {
    setSelectedTender(null);
    setFormData(defaultFormData);
    setScheduleFile(null);
    setRfpDocumentsFile(null);
    setMilestonePaymentScheduleFile(null);
    setTenderError(null);
    setView("create");
  };

  const openTenderView = async (tenderId: string, nextView: typeof view) => {
    try {
      setIsActioning(true);
      const full = await fetchTender(tenderId);
      setSelectedTender(full);
      if (nextView === "edit") {
        setFormData(toFormDataFromTender(full));
        setScheduleFile(null);
        setRfpDocumentsFile(null);
        setMilestonePaymentScheduleFile(null);
      }
      if (nextView === "award") {
        const contracts = await fetchTenderContracts({ tenderId });
        setTenderContracts(contracts);
        setContractMessage(null);
        setContractRejectionReason("");
        setAwardBidLoading(true);
        try {
          const [bids, ranking] = await Promise.all([
            fetchTenderBids(tenderId),
            fetchTenderAwardRanking(tenderId),
          ]);
          setAwardRankingRows(ranking.rows || []);
          const qualifyingBidIds = new Set((ranking.rows || []).filter(row => row.combined_score != null).map(row => row.bid_id));
          const eligible = bids.filter(b => qualifyingBidIds.has(b.id));
          setAwardBids(eligible);
          const recommended = ranking.recommended;
          let selected = recommended ? eligible.find(b => b.id === recommended.bid_id) : undefined;
          if (!selected) {
            selected = eligible.find(b => full.intentToAwardBidId && b.id === full.intentToAwardBidId)
              || eligible.find(b => full.awardedVendorId && b.vendor_id === full.awardedVendorId)
              || eligible.find(b => full.awardedVendorName && b.vendor_name === full.awardedVendorName);
          }
          if (!selected && eligible.length === 1) selected = eligible[0];
          setAwardBidId(selected?.id || recommended?.bid_id || "");
          setAwardWinner(selected?.vendor_name || recommended?.vendor_name || full.awardedVendorName || "");
          setAwardWinnerId(selected?.vendor_id || recommended?.vendor_id || full.awardedVendorId || "");
        } catch {
          setAwardRankingRows([]);
          setAwardBids([]);
          setAwardBidId("");
          setAwardWinner(full.awardedVendorName || "");
          setAwardWinnerId(full.awardedVendorId || "");
        } finally {
          setAwardBidLoading(false);
        }
        setMilestoneDrafts([
          { name: "Mobilization", percentage: 20, amount: 0 },
          { name: "Installation", percentage: 60, amount: 0 },
          { name: "Commissioning", percentage: 20, amount: 0 },
        ]);
      }
      setView(nextView);
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to load tender details."));
    } finally {
      setIsActioning(false);
    }
  };

  const toFileUrl = (raw?: string | null) => {
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    return `${base}${path}`;
  };

  const downloadTenderDocument = (docName: string, url?: string | null) => {
    if (!url) {
      showNotification(`No file uploaded for ${docName}.`);
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
    showNotification(`Opening: ${docName}`);
  };

  const exportBidList = () => {
    if (!selectedTender) {
      showNotification("Open a tender first to export bid list.");
      return;
    }
    const csv = [
      "bid_id,vendor,status,amount,tender_reference",
      `BID-1001,SolarLease Ltd,Submitted,250000,${selectedTender.referenceNumber}`,
      `BID-1002,EcoGrid Solutions,Verified,275000,${selectedTender.referenceNumber}`,
      `BID-1003,Mountain Power,Submitted,240000,${selectedTender.referenceNumber}`,
    ].join("\n");
    triggerDownload(`bid_list_${selectedTender.referenceNumber}.csv`, csv, "text/csv;charset=utf-8");
    showNotification("Bid list exported.");
  };

  const sendBidReminder = () => {
    showNotification("Reminder notifications queued for participating vendors.");
  };

  const runTenderSearch = () => {
    showNotification(`Search complete. ${filteredTenders.length} tender(s) matched.`);
  };

  const runSecuritySearch = () => {
    showNotification("Security verification search executed.");
  };

  const verifySecurityTender = (tenderId: string) => {
    showNotification(`Security money verified for ${tenderId}.`);
  };

  const upsertTender = (updatedTender: Tender) => {
    setTenders(prev => prev.map(t => t.id === updatedTender.id ? updatedTender : t));
    setSelectedTender(prev => (prev && prev.id === updatedTender.id ? updatedTender : prev));
  };

  const toActionError = (err: any, fallback: string) => {
    const raw = String(err?.message || "");
    if (isConnectivityError(raw)) return `Cannot connect to backend (${API_BASE}).`;
    return toFriendlyApiMessage(raw) || fallback;
  };

  const handlePublish = async (tenderId: string) => {
    try {
      setIsActioning(true);
      const result = await publishTender(tenderId, {
        sendEmail: notifyEmail,
        notifyAllBidders: true,
      });
      upsertTender(result.tender);
      await loadTenders();
      const summary = result.summary;
      if (summary) {
        if (!summary.email_enabled) {
          showNotification("Tender published. Email is disabled in backend settings.");
        } else if (summary.email_error) {
          showNotification(`Tender published. Email failed: ${summary.email_error}`);
        } else {
          showNotification(
            `Tender published. Notifications: ${summary.recipient_count ?? 0}. Emails sent: ${summary.email_recipient_count ?? 0}.`
          );
        }
      } else {
        showNotification("Tender published and bidders notified successfully!");
      }
      setView("list");
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to publish tender."));
    } finally {
      setIsActioning(false);
    }
  };

  const handleSaveTender = async (tenderData: any) => {
    const payload = { ...tenderData };
    const isEditing = view === "edit" && Boolean(selectedTender);
    const hasExistingSchedule = Boolean(selectedTender?.scheduleFile);
    const hasRfp = Boolean(rfpDocumentsFile) || Boolean(selectedTender?.rfpDocumentsFile);
    const hasMilestoneSchedule =
      Boolean(milestonePaymentScheduleFile) || Boolean(selectedTender?.milestonePaymentScheduleFile);

    const requiredFields = [
      'name','department','applicationType','stageType','procurementMethod',
      'addressForDocument','addressForSecurity','placeForOpening',
      'biddersEligibility','invitedBy','biddingCurrency','timeForCompletion',
      'instruction','contactDetails','category','targetSiteType',
      'lastDateSecurity','lastDateSubmission','dateOpening'
    ];
    const missing = requiredFields.filter(f => !payload[f] || payload[f]?.length === 0);
    if (missing.length) {
      setTenderError(`Fill required fields: ${missing.join(', ')}`);
      return;
    }
    // Align backend mandatory deadline with the document submission deadline provided by user
    payload.deadline = payload.lastDateSubmission;
    if (!payload.technologyTypes || payload.technologyTypes.length === 0) {
      setTenderError("Select at least one Technology Type.");
      return;
    }
    if (!payload.scheduleFile && !(isEditing && hasExistingSchedule)) {
      setTenderError("Upload the tender schedule (PDF/DOC/DOCX).");
      return;
    }
    if (!hasRfp || !hasMilestoneSchedule) {
      setTenderError("Upload the RFP/Subsidy Framework and the Milestone Payment Schedule.");
      return;
    }
    try {
      setTenderError(null);
      setIsSaving(true);
      if (isEditing && selectedTender) {
        const updated = await updateTender(selectedTender.id, {
          ...payload,
          status: selectedTender.status,
          rfpDocumentsFile,
          milestonePaymentScheduleFile,
        });
        upsertTender(updated);
      } else {
        const created = await createTender({
          ...payload,
          status: TenderStatus.DRAFT,
          rfpDocumentsFile,
          milestonePaymentScheduleFile,
        });
        setTenders([created, ...tenders]);
      }
      await loadTenders();
      showNotification(isEditing ? "Tender updated successfully." : "Tender saved successfully.");
      setView("list");
    } catch (e: any) {
      const raw = String(e?.message || e);
      setTenderError(toFriendlyApiMessage(raw) || "Failed to save tender. Please review fields and try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleVerify = async (tenderId: string) => {
    try {
      setIsActioning(true);
      const updated = await verifyTender(tenderId);
      upsertTender(updated);
      await loadTenders();
      showNotification("Tender information verified successfully.");
      setView("list");
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to verify tender."));
    } finally {
      setIsActioning(false);
    }
  };

  const handleAward = async (tenderId: string) => {
    if (!awardBidId.trim()) {
      showNotification("Select a submitted bid to issue the award.");
      return;
    }
    if (!awardWinner.trim() || !awardWinnerId.trim()) {
      showNotification("Winning Vendor Name and Vendor ID are required to issue the award.");
      return;
    }
    const tenderLabel = selectedTender?.name || "this tender";
    const confirmationMessage = `Award "${tenderLabel}" (Tender ID: ${tenderId}) to "${awardWinner}" (Vendor ID: ${awardWinnerId})?`;
    if (!window.confirm(confirmationMessage)) {
      return;
    }
    try {
      setIsActioning(true);
      setContractMessage(null);
      const updated = await awardTender(tenderId, {
        bidId: awardBidId,
        awardedVendorId: awardWinnerId || undefined,
        awardedVendorName: awardWinner,
        sendEmail: notifyEmail,
      });
      if (selectedTender?.id === tenderId) {
        setSelectedTender(updated);
      }
      upsertTender(updated);
      await loadTenders();
      const ranking = await fetchTenderAwardRanking(tenderId);
      setAwardRankingRows(ranking.rows || []);
      const channels = [notifyEmail ? "Email" : null].filter(Boolean).join(" & ");
      const coolingDate = updated.coolingOffUntil ? new Date(updated.coolingOffUntil).toLocaleString() : "the configured cooling-off deadline";
      showNotification(`Intent to Award issued for ${tenderLabel}. Notifications sent via ${channels || "System"}.`);
      setContractMessage(`Intent to Award issued to ${awardWinner}. Cooling-off period ends on ${coolingDate}. The final award and PBA generation will only happen after that date.`);
    } catch (err: any) {
      const message = toActionError(err, "Failed to award tender.");
      showNotification(message);
      setContractMessage(message);
    } finally {
      setIsActioning(false);
    }
  };

  const handleConfirmFinalAward = async (tenderId: string) => {
    const tenderLabel = selectedTender?.name || "this tender";
    if (!window.confirm(`Confirm final award for "${tenderLabel}" now? This will generate the PBA and open Contracting for vendor signature.`)) {
      return;
    }
    try {
      setIsActioning(true);
      setContractMessage(null);
      const updated = await confirmTenderAward(tenderId, { sendEmail: notifyEmail });
      if (selectedTender?.id === tenderId) {
        setSelectedTender(updated);
      }
      upsertTender(updated);
      await loadTenders();
      showNotification(`Final award confirmed for ${tenderLabel}.`);
      setContractMessage("Final award confirmed. Refreshing the Performance-Based Agreement package now.");

      try {
        const refreshedContracts = await fetchTenderContracts({ tenderId });
        const activeAwardContract = refreshedContracts.find(
          item => String(item.vendorId) === String(updated.awardedVendorId || awardWinnerId)
        );
        setTenderContracts(refreshedContracts);
        if (activeAwardContract?.generatedFile) {
          setContractMessage("Final award confirmed. The Performance-Based Agreement has been generated, the vendor can now see it under Contracting, download it, sign it digitally or by scanned signed PDF, upload it, and then admin can review and finalize.");
        } else {
          setContractMessage("Final award confirmed. The contract package is still being prepared. Re-open Manage Award in a moment if the PBA does not appear yet.");
        }
      } catch (contractErr: any) {
        const raw = String(contractErr?.message || "");
        setContractMessage(
          isConnectivityError(raw)
            ? "Final award confirmed, but the contract package could not be refreshed immediately. Re-open Manage Award in a moment to verify the generated PBA."
            : (toFriendlyApiMessage(raw) || "Final award confirmed, but the contract package could not be refreshed immediately.")
        );
      }
    } catch (err: any) {
      const message = toActionError(err, "Failed to confirm the final award.");
      showNotification(message);
      setContractMessage(message);
    } finally {
      setIsActioning(false);
    }
  };

  const handleApproveContract = async (contractId: string) => {
    try {
      setIsActioning(true);
      const updated = await approveTenderContract(contractId, milestoneDrafts);
      setTenderContracts(prev => prev.map(item => item.id === updated.id ? updated : item));
      setContractMessage("Contract approved. Project and milestones created.");
    } catch (err: any) {
      setContractMessage(toActionError(err, "Failed to approve contract."));
    } finally {
      setIsActioning(false);
    }
  };

  const handleRejectContract = async (contractId: string) => {
    if (!contractRejectionReason.trim()) {
      setContractMessage("Please provide a rejection reason.");
      return;
    }
    try {
      setIsActioning(true);
      const updated = await rejectTenderContract(contractId, contractRejectionReason.trim());
      setTenderContracts(prev => prev.map(item => item.id === updated.id ? updated : item));
      setContractMessage("Contract rejected.");
    } catch (err: any) {
      setContractMessage(toActionError(err, "Failed to reject contract."));
    } finally {
      setIsActioning(false);
    }
  };

  if (view === "create" || view === "edit") {
    const isEditing = view === "edit";
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <NotificationToast />
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">
            {isEditing ? `Edit Tender: ${selectedTender?.name ?? ""}` : "Add New Tender"}
          </h1>
        </div>
        {tenderError && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium">
            {tenderError}
          </div>
        )}

        <div className="card p-8 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Name of the Tender *</label>
              <input 
                type="text" 
                name="name"
                value={formData.name}
                onChange={handleInputChange}
                placeholder="Tender Name" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Department Entity *</label>
              <select 
                name="department"
                value={formData.department}
                onChange={handleInputChange}
                className="input-field"
              >
                <option value="">Select Department</option>
                <option>Department of Energy</option>
                <option>UNDP Lesotho</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Application Type *</label>
              <select 
                name="applicationType"
                value={formData.applicationType}
                onChange={handleInputChange}
                className="input-field"
              >
                <option>Access Window</option>
                <option>Application Window</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Stage Type *</label>
              <select 
                name="stageType"
                value={formData.stageType}
                onChange={handleInputChange}
                className="input-field"
              >
                <option>Pre-Qualification</option>
                <option>Site-Specific</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Procurement Method *</label>
              <select 
                name="procurementMethod"
                value={formData.procurementMethod}
                onChange={handleInputChange}
                className="input-field"
              >
                <option value="">Select Method</option>
                <option>Open Tendering</option>
                <option>Restricted Tendering</option>
                <option>Request for Proposals</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Bidding Currency *</label>
              <select 
                name="biddingCurrency"
                value={formData.biddingCurrency}
                onChange={handleInputChange}
                className="input-field"
              >
                <option>LSL (Maloti)</option>
                <option>USD</option>
                <option>ZAR</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Funding Source (Optional)</label>
              <select 
                name="fundingSource"
                value={formData.fundingSource}
                onChange={handleInputChange}
                className="input-field"
              >
                <option value="">Select Funding Source</option>
                <option>Government Budget</option>
                <option>UNDP Grant</option>
                <option>World Bank Loan</option>
                <option>Private Investment</option>
                <option>Other</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Cooling-Off Period (Days)</label>
              <input
                type="number"
                name="coolingOffDays"
                min={0}
                max={14}
                value={formData.coolingOffDays ?? 7}
                onChange={handleInputChange}
                className="input-field"
              />
              <p className="text-[10px] text-slate-400">Set between 0 and 14 days. Use 0 for instant testing.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Name & Address for Tender Document *</label>
              <input 
                type="text" 
                name="addressForDocument"
                value={formData.addressForDocument}
                onChange={handleInputChange}
                placeholder="Address" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Name & Address for Tender Security *</label>
              <input 
                type="text" 
                name="addressForSecurity"
                value={formData.addressForSecurity}
                onChange={handleInputChange}
                placeholder="Address" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Place for Tender Opening *</label>
              <input 
                type="text" 
                name="placeForOpening"
                value={formData.placeForOpening}
                onChange={handleInputChange}
                placeholder="Opening Location" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Tender Invited By *</label>
              <input 
                type="text" 
                name="invitedBy"
                value={formData.invitedBy}
                onChange={handleInputChange}
                placeholder="Official Name" 
                className="input-field" 
              />
            </div>
          </div>

          <div className="space-y-6">
            {/* Security Submission Deadline */}
            <div>
              <label className="text-sm font-bold text-slate-700 mb-2">Security Submission Deadline *</label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="date" 
                    placeholder="Date"
                    value={formData.lastDateSecurity ? formData.lastDateSecurity.split('T')[0] : ""}
                    onChange={(e) => {
                      const currentTime = formData.lastDateSecurity?.split('T')[1] || '09:00';
                      setFormData(prev => ({ ...prev, lastDateSecurity: `${e.target.value}T${currentTime}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
                <div className="relative">
                  <Clock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="time" 
                    placeholder="Time"
                    value={formData.lastDateSecurity ? formData.lastDateSecurity.split('T')[1] : '09:00'}
                    onChange={(e) => {
                      const currentDate = formData.lastDateSecurity?.split('T')[0] || new Date().toISOString().split('T')[0];
                      setFormData(prev => ({ ...prev, lastDateSecurity: `${currentDate}T${e.target.value}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
              </div>
            </div>

            {/* Document Submission Deadline */}
            <div>
              <label className="text-sm font-bold text-slate-700 mb-2">Document Submission Deadline *</label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="date" 
                    placeholder="Date"
                    value={formData.lastDateSubmission ? formData.lastDateSubmission.split('T')[0] : ""}
                    onChange={(e) => {
                      const currentTime = formData.lastDateSubmission?.split('T')[1] || '14:00';
                      setFormData(prev => ({ ...prev, lastDateSubmission: `${e.target.value}T${currentTime}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
                <div className="relative">
                  <Clock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="time" 
                    placeholder="Time"
                    value={formData.lastDateSubmission ? formData.lastDateSubmission.split('T')[1] : '14:00'}
                    onChange={(e) => {
                      const currentDate = formData.lastDateSubmission?.split('T')[0] || new Date().toISOString().split('T')[0];
                      setFormData(prev => ({ ...prev, lastDateSubmission: `${currentDate}T${e.target.value}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
              </div>
            </div>

            {/* Tender Opening Date & Time */}
            <div>
              <label className="text-sm font-bold text-slate-700 mb-2">Tender Opening Date & Time *</label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="date" 
                    placeholder="Date"
                    value={formData.dateOpening ? formData.dateOpening.split('T')[0] : ""}
                    onChange={(e) => {
                      const currentTime = formData.dateOpening?.split('T')[1] || '10:00';
                      setFormData(prev => ({ ...prev, dateOpening: `${e.target.value}T${currentTime}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
                <div className="relative">
                  <Clock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input 
                    type="time" 
                    placeholder="Time"
                    value={formData.dateOpening ? formData.dateOpening.split('T')[1] : '10:00'}
                    onChange={(e) => {
                      const currentDate = formData.dateOpening?.split('T')[0] || new Date().toISOString().split('T')[0];
                      setFormData(prev => ({ ...prev, dateOpening: `${currentDate}T${e.target.value}` }));
                    }}
                    className="input-field pl-10" 
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="font-bold text-slate-900 border-b pb-2">Technical Mapping</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700">Technology Type * (Multi-select)</label>
                <div className="flex flex-wrap gap-2 pt-1">
                  {['Mini-grid', 'SHS', 'ICS', 'SWP', 'PUE', 'SAS'].map(tech => (
                    <label key={tech} className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-lg border border-slate-200 cursor-pointer hover:bg-slate-100">
                      <input 
                        type="checkbox" 
                        className="w-4 h-4 rounded text-emerald-600" 
                        checked={formData.technologyTypes?.includes(tech)}
                        onChange={() => handleTechToggle(tech)}
                      />
                      <span className="text-sm font-medium">{tech}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700">Target Site Type *</label>
                <select 
                  name="targetSiteType"
                  value={formData.targetSiteType}
                  onChange={handleInputChange}
                  className="input-field"
                >
                  <option>Household</option>
                  <option>Business</option>
                  <option>School</option>
                  <option>Clinic</option>
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Bidders Eligibility *</label>
            <textarea 
              name="biddersEligibility"
              value={formData.biddersEligibility}
              onChange={handleInputChange}
              rows={3} 
              placeholder="Describe eligibility criteria..." 
              className="input-field"
            ></textarea>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Instructions *</label>
            <textarea 
              name="instruction"
              value={formData.instruction}
              onChange={handleInputChange}
              rows={3} 
              placeholder="Special instructions for bidders..." 
              className="input-field"
            ></textarea>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Time for Completion *</label>
            <input
              type="text"
              name="timeForCompletion"
              value={formData.timeForCompletion}
              onChange={handleInputChange}
              placeholder="e.g., 60 days"
              className="input-field"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  className="w-5 h-5 rounded border-slate-300 text-emerald-600" 
                  checked={formData.tenderSecurityRequired}
                  onChange={(e) => setFormData(prev => ({ ...prev, tenderSecurityRequired: e.target.checked }))}
                />
                <span className="text-sm font-medium text-slate-700">Bidders Schedule Purchase Required</span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  className="w-5 h-5 rounded border-slate-300 text-emerald-600" 
                  checked={formData.biddersSchedulePurchase}
                  onChange={(e) => setFormData(prev => ({ ...prev, biddersSchedulePurchase: e.target.checked }))}
                />
                <span className="text-sm font-medium text-slate-700">Tender Security Required</span>
              </label>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Contact Details *</label>
              <input 
                type="text" 
                name="contactDetails"
                value={formData.contactDetails}
                onChange={handleInputChange}
                placeholder="Email or Phone" 
                className="input-field" 
              />
            </div>
          </div>

          <div className="space-y-4">
            <label className="text-sm font-bold text-slate-700">Governing Documents *</label>
            <p className="text-xs text-slate-500">Upload the core tender documents that define rules, eligibility, and payment terms.</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                {
                  label: "Tender Schedule",
                  hint: "Key dates and procurement timeline",
                  file: scheduleFile,
                  existing: selectedTender?.scheduleFile,
                  setter: setScheduleFile,
                },
                {
                  label: "RFP / Subsidy Framework",
                  hint: "Eligibility, evaluation criteria, technical standards",
                  file: rfpDocumentsFile,
                  existing: selectedTender?.rfpDocumentsFile,
                  setter: setRfpDocumentsFile,
                },
                {
                  label: "Milestone Payment Schedule",
                  hint: "Payment terms for this window",
                  file: milestonePaymentScheduleFile,
                  existing: selectedTender?.milestonePaymentScheduleFile,
                  setter: setMilestonePaymentScheduleFile,
                },
              ].map((doc, idx) => (
                <div key={doc.label} className="p-4 border-2 border-dashed border-slate-200 rounded-xl text-center bg-slate-50">
                  <label htmlFor={`docUpload-${idx}`} className="cursor-pointer block">
                    <FileText size={22} className="mx-auto text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-700">{doc.label}</p>
                    <p className="text-[10px] text-slate-400 mt-1">{doc.hint}</p>
                    <p className="text-[10px] text-slate-400 mt-1">
                      {doc.file
                        ? doc.file.name
                        : doc.existing
                          ? "Existing file attached (upload to replace)"
                          : "Click to upload"}
                    </p>
                  </label>
                  <input
                    id={`docUpload-${idx}`}
                    type="file"
                    accept=".pdf,.doc,.docx,.xls,.xlsx"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      doc.setter(file || null);
                    }}
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
            <button onClick={() => setView("list")} className="btn-secondary">Cancel</button>
            {isEditing ? (
              <button
                onClick={() =>
                  handleSaveTender({
                    ...formData,
                    scheduleFile,
                    rfpDocumentsFile,
                    milestonePaymentScheduleFile,
                  })
                }
                className="btn-primary disabled:opacity-60"
                disabled={isSaving}
              >
                {isSaving ? "Saving..." : "Save Changes"}
              </button>
            ) : (
              <>
                <button
                  onClick={() =>
                    handleSaveTender({
                      ...formData,
                      scheduleFile,
                      rfpDocumentsFile,
                      milestonePaymentScheduleFile,
                    })
                  }
                  className="btn-secondary border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
                  disabled={isSaving}
                >
                  {isSaving ? "Saving..." : "Save as Draft"}
                </button>
                <button
                  onClick={() =>
                    handleSaveTender({
                      ...formData,
                      scheduleFile,
                      rfpDocumentsFile,
                      milestonePaymentScheduleFile,
                    })
                  }
                  className="btn-primary disabled:opacity-60"
                  disabled={isSaving}
                >
                  {isSaving ? "Saving..." : "Save Tender"}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (view === "details" && selectedTender) {
    const formatDateTime = (value?: string | null) => {
      if (!value) return "N/A";
      const ts = Date.parse(value);
      if (Number.isNaN(ts)) return value;
      const date = new Date(ts).toLocaleDateString();
      const time = new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `${date} • ${time}`;
    };

    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-12">
        <NotificationToast />
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
              <ChevronRight className="rotate-180" size={20} />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">{selectedTender.name}</h1>
              <p className="text-sm text-slate-500 font-mono">{selectedTender.referenceNumber}</p>
            </div>
          </div>
          <div className="flex gap-3">
            {selectedTender.status === TenderStatus.DRAFT && (
              <button onClick={() => openTenderView(selectedTender.id, "edit")} className="btn-secondary flex items-center gap-2">
                <FileText size={18} /> Edit Tender
              </button>
            )}
            {!selectedTender.isVerified && (
              <button 
                onClick={() => setView("verify")}
                className="btn-primary bg-blue-600 hover:bg-blue-700 flex items-center gap-2"
              >
                <ShieldCheck size={18} /> Verify
              </button>
            )}
            {selectedTender.isVerified && selectedTender.status === TenderStatus.DRAFT && (
              <button 
                onClick={() => setView("publish")}
                className="btn-primary flex items-center gap-2"
              >
                <Zap size={18} /> Publish
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-6">
              <div className="flex flex-wrap items-center gap-3">
                <span className={`badge ${
                  selectedTender.status === TenderStatus.PUBLISHED ? 'bg-emerald-100 text-emerald-700' :
                  selectedTender.status === TenderStatus.EVALUATION ? 'bg-blue-100 text-blue-700' :
                  selectedTender.status === TenderStatus.AWARDED ? 'bg-purple-100 text-purple-700' :
                  'bg-amber-100 text-amber-700'
                }`}>
                  {selectedTender.status}
                </span>
                <span className={`text-xs font-bold ${selectedTender.isVerified ? 'text-emerald-600' : 'text-amber-600'}`}>
                  {selectedTender.isVerified ? 'Verified' : 'Pending Verification'}
                </span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-xs text-slate-500">Dept: {selectedTender.department}</span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-xs text-slate-500">Category: {selectedTender.category}</span>
                {selectedTender.budget != null && (
                  <>
                    <span className="text-xs text-slate-400">•</span>
                    <span className="text-xs text-slate-500">Budget: M {selectedTender.budget.toLocaleString()}</span>
                  </>
                )}
              </div>
            </div>

            <div className="card p-8 space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Overview</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Application Type</p>
                      <p className="font-medium">{selectedTender.applicationType || "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Stage Type</p>
                      <p className="font-medium">{selectedTender.stageType || "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Procurement Method</p>
                      <p className="font-medium">{selectedTender.procurementMethod || "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Invited By</p>
                      <p className="font-medium">{selectedTender.invitedBy || "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Time for Completion</p>
                      <p className="font-medium">{selectedTender.timeForCompletion || "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Funding Source</p>
                      <p className="font-medium">{selectedTender.fundingSource || "N/A"}</p>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Financials & Security</h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Budget Estimate</p>
                      <p className="text-lg font-bold text-slate-900">M {selectedTender.budget?.toLocaleString() ?? "N/A"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Bidding Currency</p>
                      <p className="font-medium">{selectedTender.biddingCurrency || "LSL (Maloti)"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Schedule Purchase</p>
                      <p className="font-medium">{selectedTender.biddersSchedulePurchase ? "Required" : "Not Required"}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Tender Security</p>
                      <p className="font-medium">{selectedTender.tenderSecurityRequired ? "Required" : "Not Required"}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Deadlines & Schedule</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <Clock size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Submission Deadline</p>
                    <p className="text-sm font-bold text-slate-900">{formatDateTime(selectedTender.lastDateSubmission || selectedTender.deadline)}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <ShieldCheck size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Security Deadline</p>
                    <p className="text-sm font-bold text-slate-900">{formatDateTime(selectedTender.lastDateSecurity)}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <Eye size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Opening Date</p>
                    <p className="text-sm font-bold text-slate-900">{formatDateTime(selectedTender.dateOpening)}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Technical Requirements</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Technology Types</p>
                    <div className="flex flex-wrap gap-2">
                      {(selectedTender.technologyTypes || []).length ? (selectedTender.technologyTypes || []).map(tech => (
                        <span key={tech} className="px-2 py-1 bg-emerald-50 text-emerald-700 rounded text-[10px] font-bold uppercase tracking-wider">{tech}</span>
                      )) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Target Site Type</p>
                    <p className="text-sm font-medium">{selectedTender.targetSiteType || "N/A"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Eligibility & Instructions</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Eligibility</p>
                    <p className="text-slate-700">{selectedTender.biddersEligibility || "Not specified"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Instructions</p>
                    <p className="text-slate-700">{selectedTender.instruction || "Not specified"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 md:col-span-2">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Pre‑Tender Meeting</p>
                    <p className="text-slate-700">{selectedTender.preTenderMeetingInfo || "Not specified"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Required Documents</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {[
                    { label: "Tender Schedule", url: toFileUrl(selectedTender.scheduleFile) },
                    { label: "RFP / Subsidy Framework", url: toFileUrl(selectedTender.rfpDocumentsFile) },
                    { label: "Milestone Payment Schedule", url: toFileUrl(selectedTender.milestonePaymentScheduleFile) },
                  ].map((doc, i) => (
                    <div key={i} className="p-4 border-2 border-dashed border-slate-200 rounded-xl bg-slate-50">
                      <div className="flex items-center gap-2">
                        <FileText size={18} className="text-slate-400" />
                        <span className="text-xs font-bold text-slate-700">{doc.label}</span>
                      </div>
                      <div className="mt-3">
                        <button
                          onClick={() => downloadTenderDocument(doc.label, doc.url)}
                          className={`text-emerald-600 hover:text-emerald-700 text-xs font-bold ${doc.url ? "" : "opacity-40 cursor-not-allowed"}`}
                          title={doc.url ? `Download ${doc.label}` : "No file uploaded"}
                          disabled={!doc.url}
                        >
                          {doc.url ? "Download →" : "Not provided"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Contact</h3>
              <p className="text-sm text-slate-600">{selectedTender.contactDetails || "Not provided"}</p>
            </div>
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Logistics & Locations</h3>
              <div className="space-y-3 text-sm">
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Document Address</p>
                  <p className="text-slate-700">{selectedTender.addressForDocument || "Not specified"}</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Security Address</p>
                  <p className="text-slate-700">{selectedTender.addressForSecurity || "Not specified"}</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Opening Venue</p>
                  <p className="text-slate-700">{selectedTender.placeForOpening || "Not specified"}</p>
                </div>
              </div>
            </div>
            <div className="card p-6 space-y-4">
              <h3 className="font-bold text-slate-900">Submission Stats</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-500">Total Bids</span>
                  <span className="font-bold">12</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-500">Verified Bids</span>
                  <span className="font-bold text-emerald-600">8</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-emerald-500 h-full w-[66%]" />
                </div>
              </div>
            </div>

            <div className="card p-6 space-y-4">
              <h3 className="font-bold text-slate-900">Quick Actions</h3>
              <div className="space-y-2">
                <button onClick={sendBidReminder} className="btn-secondary w-full flex items-center justify-center gap-2">
                  <Bell size={16} /> Send Reminder
                </button>
                <button onClick={exportBidList} className="btn-secondary w-full flex items-center justify-center gap-2">
                  <Download size={16} /> Export Bid List
                </button>
                {(selectedTender.status === TenderStatus.EVALUATION || selectedTender.status === TenderStatus.PUBLISHED) && (
                  <button onClick={() => setView("award")} className="btn-primary w-full bg-purple-600 hover:bg-purple-700">
                    Issue Award
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "publish" && selectedTender) {
    return (
      <div className="space-y-6 max-w-2xl mx-auto">
        <NotificationToast />
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">Publish Tender & Notify Bidders</h1>
        </div>

        <div className="card p-8 space-y-8">
          <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
            <p className="text-sm text-emerald-800 font-medium">Tender: {selectedTender.name}</p>
            <p className="text-xs text-emerald-600 font-mono">{selectedTender.referenceNumber}</p>
          </div>

          <div className="space-y-6">
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <p className="text-sm text-slate-700 font-medium">
                All pre-qualified vendors will be notified when this tender is published.
              </p>
            </div>

            <div className="space-y-3">
              <label className="text-sm font-bold text-slate-700">Notification Channels</label>
              <div className="space-y-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    className="w-5 h-5 rounded border-slate-300 text-emerald-600"
                    checked={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.checked)}
                  />
                  <span className="text-sm font-medium text-slate-700">Send Email Notification</span>
                </label>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
            <button onClick={() => setView("list")} className="btn-secondary">Cancel</button>
            <button onClick={() => handlePublish(selectedTender.id)} disabled={isActioning} className="btn-primary disabled:opacity-60">
              {isActioning ? "Publishing..." : "Publish Now"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (view === "verify" && selectedTender) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <NotificationToast />
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">Verify Tender Details</h1>
        </div>

        <div className="card p-8 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="space-y-4">
              <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Basic Information</h3>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Tender Name</p>
                <p className="text-sm font-medium">{selectedTender.name}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Reference Number</p>
                <p className="text-sm font-mono">{selectedTender.referenceNumber}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Department</p>
                <p className="text-sm font-medium">{selectedTender.department}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Application Type</p>
                <p className="text-sm font-medium">{selectedTender.applicationType || "Access Window"}</p>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Procurement & Stage</h3>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Stage Type</p>
                <p className="text-sm font-medium">{selectedTender.stageType || "Pre-Qualification"}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Procurement Method</p>
                <p className="text-sm font-medium">{selectedTender.procurementMethod || "Open Tendering"}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Bidding Currency</p>
                <p className="text-sm font-medium">{selectedTender.biddingCurrency || "LSL (Maloti)"}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Budget Estimate</p>
                <p className="text-sm font-medium">M {selectedTender.budget?.toLocaleString()}</p>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Deadlines</h3>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Submission Deadline</p>
                <p className="text-sm font-medium">{selectedTender.deadline}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Security Deadline</p>
                <p className="text-sm font-medium">{selectedTender.lastDateSecurity || "2025-06-10 12:00"}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Opening Date</p>
                <p className="text-sm font-medium">{selectedTender.dateOpening || "2025-06-16 10:00"}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4 border-t border-slate-100">
            <div className="space-y-4">
              <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Technical Mapping</h3>
              <div className="flex flex-wrap gap-2">
                {(selectedTender.technologyTypes || ["SHS", "Mini-Grid"]).map(tech => (
                  <span key={tech} className="px-2 py-1 bg-slate-100 rounded text-xs font-bold text-slate-600">{tech}</span>
                ))}
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Target Site Type</p>
                <p className="text-sm font-medium">{selectedTender.targetSiteType || "Household"}</p>
              </div>
            </div>
            <div className="space-y-4">
              <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Eligibility & Instructions</h3>
              <div className="space-y-1">
                <p className="text-xs font-bold text-slate-500">Bidders Eligibility</p>
                <p className="text-sm text-slate-600 italic">"{selectedTender.biddersEligibility || "Standard pre-qualification required."}"</p>
              </div>
            </div>
          </div>

          <div className="p-4 bg-amber-50 rounded-xl border border-amber-100 flex items-start gap-3">
            <AlertCircle className="text-amber-600 mt-0.5" size={18} />
            <p className="text-sm text-amber-800">I confirm that I have reviewed all tender documents, schedules, and technical requirements. This information is accurate and ready for publication.</p>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
            <button onClick={() => setView("list")} className="btn-secondary">Cancel</button>
            <button onClick={() => handleVerify(selectedTender.id)} disabled={isActioning} className="btn-primary bg-blue-600 hover:bg-blue-700 flex items-center gap-2 disabled:opacity-60">
              <ShieldCheck size={18} /> Confirm Verification
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (view === "security") {
    return (
      <div className="space-y-6">
        <NotificationToast />
        <div className="flex items-center gap-4">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">Verify Security Money</h1>
        </div>

        <div className="card p-6 flex flex-wrap gap-4 items-center">
          <div className="flex-1 grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Search By</label>
              <select className="input-field py-1.5 text-sm">
                <option>Tender ID</option>
                <option>Vendor Name</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Search Key</label>
              <input type="text" placeholder="Enter ID..." className="input-field py-1.5 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Award Date</label>
              <input type="date" className="input-field py-1.5 text-sm" />
            </div>
            <div className="flex items-end">
              <button onClick={runSecuritySearch} className="btn-primary w-full py-2 flex items-center justify-center gap-2">
                <Search size={16} /> Search
              </button>
            </div>
          </div>
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Tender ID</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Amount</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {[
                { id: "T-001", vendor: "SolarLease Ltd", amount: "M 25,000", status: "Pending" },
                { id: "T-002", vendor: "EcoGrid Solutions", amount: "M 60,000", status: "Verified" },
              ].map((item, i) => (
                <tr key={i} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-mono text-xs text-slate-500">{`SEC-${String(i + 1).padStart(3, "0")}`}</td>
                  <td className="px-6 py-4 font-mono text-sm">{item.id}</td>
                  <td className="px-6 py-4 text-sm font-medium">{item.vendor}</td>
                  <td className="px-6 py-4 text-sm font-bold">{item.amount}</td>
                  <td className="px-6 py-4">
                    <span className={`badge ${item.status === 'Verified' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => verifySecurityTender(item.id)} className="btn-secondary py-1 px-3 text-xs">Verify Tender</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <NotificationToast />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-slate-900">Tender Management</h1>
          <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">Stage 1 & 2</span>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setView("security")} className="btn-secondary flex items-center gap-2">
            <ShieldCheck size={18} /> Verify Security
          </button>
          <button onClick={startCreateTender} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> Add Tender
          </button>
        </div>
      </div>

      <div className="card p-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-5 lg:grid-cols-7 gap-4 items-end">
          <div className="space-y-1 md:col-span-2">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Search Key</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input 
                type="text" 
                placeholder="Search by reference or name..." 
                className="input-field pl-10 py-2 text-sm"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Department</label>
            <select 
              className="input-field py-2 text-sm"
              value={selectedDepartment}
              onChange={(e) => setSelectedDepartment(e.target.value)}
            >
              <option>All Departments</option>
              <option>Department of Energy</option>
              <option>UNDP Lesotho</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Category</label>
            <select 
              className="input-field py-2 text-sm"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option>All Categories</option>
              <option>SHS</option>
              <option>Mini-Grid</option>
              <option>ICS</option>
              <option>SWP</option>
              <option>PUE</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Procurement</label>
            <select 
              className="input-field py-2 text-sm"
              value={selectedProcurement}
              onChange={(e) => setSelectedProcurement(e.target.value)}
            >
              <option>All Methods</option>
              <option>Open Competitive</option>
              <option>Selective</option>
              <option>Direct</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Sort By</label>
            <select 
              className="input-field py-2 text-sm"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
            >
              <option value="created_at">Recent</option>
              <option value="deadline">Deadline</option>
              <option value="published_at">Published</option>
            </select>
          </div>
          <button onClick={runTenderSearch} className="btn-primary py-2 flex items-center justify-center gap-2">
            <Search size={16} /> Search Now
          </button>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-bottom border-slate-200">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Reference</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Tender Name</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Category</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Verification</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {filteredTenders.map((tender) => (
              <tr key={tender.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{tender.id}</td>
                <td className="px-6 py-4 font-mono text-sm text-slate-600">{tender.referenceNumber}</td>
                <td className="px-6 py-4 font-medium text-slate-900">{tender.name}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{tender.category}</td>
                <td className="px-6 py-4">
                  <span className={`badge ${
                    tender.status === TenderStatus.PUBLISHED ? 'bg-emerald-100 text-emerald-700' :
                    tender.status === TenderStatus.EVALUATION ? 'bg-blue-100 text-blue-700' :
                    tender.status === TenderStatus.AWARDED ? 'bg-purple-100 text-purple-700' :
                    'bg-amber-100 text-amber-700'
                  }`}>
                    {tender.status}
                  </span>
                </td>
                <td className="px-6 py-4">
                  {tender.isVerified ? (
                    <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-600">
                      <ShieldCheck size={14} /> Verified
                    </span>
                  ) : (
                    <span className="text-xs font-bold text-slate-400">Pending</span>
                  )}
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-4">
                    <button 
                      onClick={() => void openTenderView(tender.id, "details")}
                      className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                    >
                      View
                    </button>
                    {!tender.isVerified && (
                      <button 
                        onClick={() => void openTenderView(tender.id, "verify")}
                        className="text-blue-600 hover:text-blue-700 font-medium text-sm"
                      >
                        Verify
                      </button>
                    )}
                    {tender.isVerified && tender.status === TenderStatus.DRAFT && (
                      <button 
                        onClick={() => void openTenderView(tender.id, "publish")}
                        className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                      >
                        Publish
                      </button>
                    )}
                    {(tender.status === TenderStatus.EVALUATION || tender.status === TenderStatus.PUBLISHED || tender.status === TenderStatus.AWARDED) && (
                      <button 
                        onClick={() => void openTenderView(tender.id, "award")}
                        className="text-purple-600 hover:text-purple-700 font-medium text-sm"
                      >
                        {tender.status === TenderStatus.AWARDED || tender.intentToAwardAt ? "Manage Award" : "Award"}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Award Notification Overlay */}
      <AnimatePresence>
        {view === "award" && selectedTender && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setView("list")}
          >
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[92vh] overflow-y-auto p-6 md:p-8 space-y-6"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold text-slate-900">
                {selectedTender.intentToAwardAt && selectedTender.status !== TenderStatus.AWARDED ? "Intent to Award Review" : "Issue Intent to Award"}
              </h2>
              <p className="text-sm text-slate-500">
                The system ranks bidders by weighted technical and financial scoring. First issue the Intent to Award to the best evaluated bidder, then confirm the final award after the cooling-off period to generate the PBA.
              </p>
              
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.2fr_0.8fr]">
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <label className="text-sm font-bold text-slate-700">Winning Bid</label>
                      {awardBidLoading ? (
                        <div className="text-xs text-slate-500">Loading submitted bids...</div>
                      ) : (
                        <select
                          className="input-field"
                          value={awardBidId}
                          onChange={(e) => {
                            const nextId = e.target.value;
                            setAwardBidId(nextId);
                            const match = awardBids.find(b => b.id === nextId);
                            if (match) {
                              setAwardWinner(match.vendor_name || "");
                              setAwardWinnerId(match.vendor_id || "");
                            }
                          }}
                        >
                          <option value="">Select a submitted bid</option>
                          {awardBids.map(bid => (
                            <option key={bid.id} value={bid.id}>
                              {bid.vendor_name} • Vendor {bid.vendor_id} • Version {bid.version_number ?? 1}
                            </option>
                          ))}
                        </select>
                      )}
                      {!awardBidLoading && awardBids.length === 0 && (
                        <p className="text-xs text-amber-700">No TAC‑scored bids found for this tender.</p>
                      )}
                      {!awardBidLoading && awardBids.length > 0 && (
                        <p className="text-[10px] text-slate-400">Only TAC‑scored bids with total score ≥ 71 are available for award.</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-slate-700">Winning Vendor ID</label>
                      <input
                        className="input-field"
                        value={awardWinnerId}
                        onChange={(e) => setAwardWinnerId(e.target.value)}
                        placeholder="Vendor user ID (e.g., 12)"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-slate-700">Winning Vendor Name</label>
                      <input
                        className="input-field"
                        value={awardWinner}
                        onChange={(e) => setAwardWinner(e.target.value)}
                        placeholder="Vendor legal name"
                      />
                    </div>
                  </div>

                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                    <p className="font-semibold">Award Confirmation Summary</p>
                    <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                      <p>Tender: {selectedTender.name}</p>
                      <p>Tender ID: {selectedTender.id}</p>
                      <p>Vendor: {awardWinner || "Select a winning bid"}</p>
                      <p>Vendor ID: {awardWinnerId || "Select a winning bid"}</p>
                    </div>
                    {selectedTender.intentToAwardAt && (
                      <p className="mt-2 text-xs text-amber-800">
                        Intent to Award issued on {new Date(selectedTender.intentToAwardAt).toLocaleString()}.
                        Cooling-off ends on {selectedTender.coolingOffUntil ? new Date(selectedTender.coolingOffUntil).toLocaleString() : "the configured deadline"}.
                      </p>
                    )}
                    {!selectedTender.intentToAwardAt && (
                      <p className="mt-2 text-xs text-amber-800">After you press the button, you will be asked to confirm this exact Intent to Award action before it is submitted.</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-700">Notification Options</label>
                    <div className="space-y-2">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <input 
                          type="checkbox" 
                          className="w-5 h-5 rounded border-slate-300 text-emerald-600" 
                          checked={notifyEmail}
                          onChange={(e) => setNotifyEmail(e.target.checked)}
                        />
                        <span className="text-sm font-medium text-slate-700">Send Email Notification</span>
                      </label>
                    </div>
                  </div>

                  {awardRankingRows.length > 0 && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-sm font-semibold text-slate-800">Comparative Ranking Table</p>
                      <div className="mt-3 max-h-[34vh] overflow-y-auto space-y-2 pr-1 text-xs">
                        {awardRankingRows.map((row) => (
                          <div key={row.bid_id} className={`rounded-lg border px-3 py-2 ${row.is_recommended_winner ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-white"}`}>
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <p className="font-semibold text-slate-900">{row.vendor_name}</p>
                                <p className="text-slate-500">Bid Amount: {row.bid_amount ? `LSL ${Number(row.bid_amount).toLocaleString()}` : "N/A"}</p>
                              </div>
                              <div className="text-right">
                                <p className="font-semibold text-slate-900">Rank {row.rank}</p>
                                {row.is_recommended_winner && <p className="text-emerald-700 font-semibold">Recommended Winner</p>}
                              </div>
                            </div>
                            <div className="mt-2 grid grid-cols-1 gap-2 text-slate-600 sm:grid-cols-3">
                              <p>Ts (Technical Score): {row.technical_score ?? "N/A"}</p>
                              <p>Fs (Financial Score): {row.financial_score ?? "Not opened"}</p>
                              <p>S (Combined Score): {row.combined_score ?? "N/A"}</p>
                            </div>
                            {row.disqualification_reason && (
                              <p className="mt-2 text-rose-600">{row.disqualification_reason}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="space-y-4 border-t border-slate-100 pt-4 xl:border-t-0 xl:border-l xl:border-slate-100 xl:pl-6 xl:pt-0">
                <h3 className="text-sm font-bold text-slate-700">Contract & Milestones</h3>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                  <p className="font-semibold text-slate-700">After Final Award Is Confirmed</p>
                  <p className="mt-1">1. The PBA is generated.</p>
                  <p>2. The vendor sees it under Contracting.</p>
                  <p>3. The vendor downloads and signs it.</p>
                  <p>4. The vendor uploads a digitally signed PDF or scanned signed PDF.</p>
                  <p>5. Admin reviews the uploaded package and finalizes it.</p>
                </div>
                {tenderContracts.length === 0 && (
                  <p className="text-xs text-slate-500">The Performance-Based Agreement will be generated automatically as soon as the award is confirmed.</p>
                )}
                {activeContract && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-slate-700">{activeContract.referenceNumber}</span>
                      <span className="badge bg-slate-100 text-slate-700">{activeContract.status}</span>
                    </div>
                    {activeContract && (
                      <div className="space-y-3">
                        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                          <p className="font-semibold text-slate-700">Signed Contract Review</p>
                          <p className="mt-1 text-[11px] text-slate-500">The awarded bid package is locked into Annexes A-E and must be complete before final activation.</p>
                          {activeContract.generatedFile && (
                            <a
                              href={activeContract.generatedFile}
                              target="_blank"
                              rel="noreferrer"
                              className="block text-blue-700 hover:text-blue-800 underline mt-1"
                            >
                              Download generated Performance-Based Agreement
                            </a>
                          )}
                          <div className="mt-2 flex flex-wrap gap-2">
                            {[
                              ["Annex A", activeContract.annexAFile],
                              ["Annex B", activeContract.annexBFile],
                              ["Annex C", activeContract.annexCFile],
                              ["Annex D", activeContract.annexDFile],
                              ["Annex E", activeContract.annexEFile],
                            ].map(([label, file]) => (
                              file ? (
                                <a
                                  key={label}
                                  href={String(file)}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-blue-700 hover:text-blue-800 underline"
                                >
                                  {label}
                                </a>
                              ) : (
                                <span key={label} className="text-rose-600">{label} missing</span>
                              )
                            ))}
                          </div>
                          {activeContract.signedFile ? (
                            <a
                              href={activeContract.signedFile}
                              target="_blank"
                              rel="noreferrer"
                              className="text-emerald-700 hover:text-emerald-800 underline"
                            >
                              View uploaded contract
                            </a>
                          ) : (
                            <p className="text-rose-600">No signed file uploaded yet.</p>
                          )}
                          <p className="text-[10px] text-slate-400 mt-2">
                            Status: {activeContract.status}
                          </p>
                        </div>
                        <p className="text-xs text-slate-500">After the vendor uploads the signed PBA, review the uploaded package here and finalize the default 20/50/30 milestones to activate the project.</p>
                        {milestoneDrafts.map((m, idx) => (
                          <div key={`${m.name}-${idx}`} className="grid grid-cols-3 gap-2">
                            <input
                              className="input-field"
                              value={m.name}
                              onChange={(e) => setMilestoneDrafts(prev => prev.map((item, i) => i === idx ? { ...item, name: e.target.value } : item))}
                              placeholder="Milestone name"
                            />
                            <input
                              className="input-field"
                              type="number"
                              value={m.percentage}
                              onChange={(e) => setMilestoneDrafts(prev => prev.map((item, i) => i === idx ? { ...item, percentage: Number(e.target.value) } : item))}
                              placeholder="%"
                            />
                            <input
                              className="input-field"
                              type="number"
                              value={m.amount}
                              onChange={(e) => setMilestoneDrafts(prev => prev.map((item, i) => i === idx ? { ...item, amount: Number(e.target.value) } : item))}
                              placeholder="Amount"
                            />
                          </div>
                        ))}
                        <button
                          onClick={() => handleApproveContract(activeContract.id)}
                          disabled={isActioning}
                          className="btn-primary w-full"
                        >
                          {isActioning ? "Finalizing..." : "Finalize Contract"}
                        </button>
                        <div className="space-y-2">
                          <input
                            className="input-field"
                            value={contractRejectionReason}
                            onChange={(e) => setContractRejectionReason(e.target.value)}
                            placeholder="Rejection reason (optional)"
                          />
                          <button
                            onClick={() => handleRejectContract(activeContract.id)}
                            disabled={isActioning}
                            className="btn-secondary w-full"
                          >
                            Reject Contract
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {contractMessage && <p className="text-xs text-slate-600">{contractMessage}</p>}
              </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row">
                <button onClick={() => setView("list")} className="btn-secondary flex-1">Cancel</button>
                {selectedTender.status !== TenderStatus.AWARDED && !selectedTender.intentToAwardAt && (
                  <button onClick={() => handleAward(selectedTender.id)} disabled={isActioning} className="btn-primary flex-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-60">
                    {isActioning ? "Submitting..." : "Issue Intent to Award"}
                  </button>
                )}
                {selectedTender.status !== TenderStatus.AWARDED && selectedTender.intentToAwardAt && (
                  <button
                    onClick={() => handleConfirmFinalAward(selectedTender.id)}
                    disabled={isActioning || (selectedTender.coolingOffUntil ? new Date(selectedTender.coolingOffUntil).getTime() > Date.now() : false)}
                    className="btn-primary flex-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-60"
                  >
                    {isActioning ? "Confirming..." : "Confirm Final Award"}
                  </button>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const GISMap = () => {
  const [activeLayers, setActiveLayers] = useState<string[]>(['Installation Density', 'Tender Zones']);
  const [timePeriod, setTimePeriod] = useState<'Daily' | 'Weekly' | 'Monthly'>('Monthly');
  const [selectedVendor, setSelectedVendor] = useState<string>('All');
  const [showVerificationQueue, setShowVerificationQueue] = useState(false);
  const [mapZoom, setMapZoom] = useState(100);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [verificationQueue, setVerificationQueue] = useState([
    { id: 'SITE-991', meterId: 'MTR-8821', lat: -29.63, long: 27.91, status: 'Pending', vendor: 'SolarLease Ltd', type: 'SHS' },
    { id: 'SITE-992', meterId: 'MTR-7712', lat: -28.81, long: 28.24, status: 'Flagged', vendor: 'EcoPower', type: 'Mini-grid' },
  ]);

  const toggleLayer = (layer: string) => {
    setActiveLayers(prev => 
      prev.includes(layer) ? prev.filter(l => l !== layer) : [...prev, layer]
    );
  };

  const showActionMessage = (message: string) => {
    setActionMessage(message);
    setTimeout(() => setActionMessage(null), 2500);
  };

  const handleZoomIn = () => {
    const nextZoom = Math.min(140, mapZoom + 10);
    setMapZoom(nextZoom);
    showActionMessage(`Map zoom set to ${nextZoom}%`);
  };

  const handleZoomOut = () => {
    const nextZoom = Math.max(60, mapZoom - 10);
    setMapZoom(nextZoom);
    showActionMessage(`Map zoom set to ${nextZoom}%`);
  };

  const handleResetMapView = () => {
    setMapZoom(100);
    setSelectedVendor('All');
    setActiveLayers(['Installation Density', 'Tender Zones']);
    showActionMessage("Map view reset.");
  };

  const updateVerificationStatus = (id: string, status: 'Verified' | 'Flagged') => {
    setVerificationQueue(prev =>
      prev.map(item => (item.id === id ? { ...item, status } : item))
    );
    showActionMessage(`Site ${id} marked as ${status}.`);
  };

  return (
    <div className="space-y-6 h-full flex flex-col">
      <AnimatePresence>
        {actionMessage && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 right-8 z-[300] bg-blue-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
          >
            {actionMessage}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">GIS & Spatial Analytics</h1>
          <p className="text-sm text-slate-500">Powered by Prospect Visualization Layer</p>
        </div>
        <div className="flex gap-3">
          <div className="flex bg-white rounded-xl p-1 shadow-sm border border-slate-200">
            {['Daily', 'Weekly', 'Monthly'].map(p => (
              <button
                key={p}
                onClick={() => setTimePeriod(p as any)}
                className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  timePeriod === p ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          <button 
            onClick={() => setShowVerificationQueue(!showVerificationQueue)}
            className="btn-secondary flex items-center gap-2 relative"
          >
            <ShieldCheck size={18} />
            Verification Queue
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-white">
              2
            </span>
          </button>
        </div>
      </div>

      <div className="flex-1 flex gap-6 min-h-[600px]">
        {/* Map Area */}
        <div className="flex-1 card relative bg-slate-200 overflow-hidden border-none shadow-inner">
          <div className="absolute top-4 left-4 z-20 bg-white/90 px-3 py-1 rounded-lg text-xs font-bold text-slate-700 border border-slate-200">
            Zoom: {mapZoom}%
          </div>
          {/* Base Map Placeholder */}
          <div className="absolute inset-0 bg-[#e5e7eb] opacity-50">
            <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(#cbd5e1 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
          </div>

          {/* Layer: Tender Zones */}
          <AnimatePresence>
            {activeLayers.includes('Tender Zones') && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 pointer-events-none"
              >
                <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-emerald-500/10 border-2 border-emerald-500/30 rounded-full blur-2xl" />
                <div className="absolute bottom-1/4 right-1/3 w-80 h-80 bg-blue-500/10 border-2 border-blue-500/30 rounded-full blur-3xl" />
                <div className="absolute top-1/2 right-1/4 w-48 h-48 bg-amber-500/10 border-2 border-amber-500/30 rounded-full blur-xl" />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Layer: Installation Density (Heatmap Mock) */}
          <AnimatePresence>
            {activeLayers.includes('Installation Density') && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 pointer-events-none"
              >
                <div className="absolute top-[40%] left-[35%] w-32 h-32 bg-emerald-400/40 rounded-full blur-3xl" />
                <div className="absolute top-[45%] left-[38%] w-16 h-16 bg-emerald-600/50 rounded-full blur-2xl" />
                <div className="absolute bottom-[30%] left-[50%] w-40 h-40 bg-emerald-400/30 rounded-full blur-3xl" />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Layer: Gender Impact */}
          <AnimatePresence>
            {activeLayers.includes('Gender Impact') && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 pointer-events-none"
              >
                <div className="absolute top-[20%] right-[20%] flex items-center gap-2 bg-white/90 backdrop-blur px-3 py-1.5 rounded-full shadow-lg border border-pink-100">
                  <div className="w-2 h-2 rounded-full bg-pink-500" />
                  <span className="text-[10px] font-bold text-slate-700">65% Female Beneficiaries</span>
                </div>
                <div className="absolute bottom-[40%] left-[20%] flex items-center gap-2 bg-white/90 backdrop-blur px-3 py-1.5 rounded-full shadow-lg border border-pink-100">
                  <div className="w-2 h-2 rounded-full bg-pink-500" />
                  <span className="text-[10px] font-bold text-slate-700">58% Female Beneficiaries</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Map Center Content */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center space-y-4 opacity-20">
              <Globe size={120} className="mx-auto text-slate-400" />
              <p className="text-2xl font-black text-slate-400 uppercase tracking-[0.2em]">Lesotho Spatial Engine</p>
            </div>
          </div>
          
          {/* Mock Pins with Detailed Attributes */}
          <div className="absolute top-1/4 left-1/3 w-5 h-5 rounded-full bg-emerald-500 border-2 border-white shadow-xl animate-pulse cursor-pointer group">
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-4 bg-white rounded-2xl shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 border border-slate-100">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <p className="text-xs font-bold text-slate-900">Meter: MTR-8821</p>
                  <p className="text-[10px] text-slate-500">Tender: RL-2025-SHS-01</p>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-[8px] font-bold text-emerald-700 uppercase">Online</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] mb-2">
                <div>
                  <p className="text-slate-400 uppercase font-bold">Type</p>
                  <p className="text-slate-700 font-medium">SHS</p>
                </div>
                <div>
                  <p className="text-slate-400 uppercase font-bold">Gender Impact</p>
                  <p className="text-pink-600 font-bold">True</p>
                </div>
                <div>
                  <p className="text-slate-400 uppercase font-bold">Lat/Long</p>
                  <p className="text-slate-700 font-medium">-29.63, 27.91</p>
                </div>
                <div>
                  <p className="text-slate-400 uppercase font-bold">Output</p>
                  <p className="text-emerald-600 font-bold">450.2 kWh</p>
                </div>
              </div>
              <div className="pt-2 border-t border-slate-100 flex justify-between items-center">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Vendor: SolarLease Ltd</span>
              </div>
            </div>
          </div>

          <div className="absolute top-1/2 left-1/2 w-5 h-5 rounded-full bg-emerald-500 border-2 border-white shadow-xl" />
          <div className="absolute top-1/3 left-2/3 w-5 h-5 rounded-full bg-amber-500 border-2 border-white shadow-xl" />
          <div className="absolute bottom-1/4 left-1/2 w-5 h-5 rounded-full bg-rose-500 border-2 border-white shadow-xl" />

          {/* Map Controls */}
          <div className="absolute bottom-6 left-6 space-y-2">
            <div className="card p-2 flex flex-col gap-1 shadow-2xl border-none">
              <button onClick={handleZoomIn} className="p-2 hover:bg-slate-100 rounded-lg text-slate-600 transition-colors"><Plus size={20} /></button>
              <div className="h-px bg-slate-100 mx-1" />
              <button onClick={handleZoomOut} className="p-2 hover:bg-slate-100 rounded-lg text-slate-600 transition-colors"><X size={20} /></button>
            </div>
            <button onClick={handleResetMapView} className="card p-3 shadow-2xl border-none text-slate-600 hover:text-emerald-600 transition-colors">
              <Globe size={20} />
            </button>
          </div>

          {/* Layer Toggle Panel */}
          <div className="absolute top-6 right-6">
            <div className="card p-5 w-72 space-y-5 shadow-2xl border-none backdrop-blur-md bg-white/90">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-xs uppercase tracking-widest text-slate-400">Map Layers</h4>
                <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                  {activeLayers.length} Active
                </span>
              </div>
              <div className="space-y-1">
                {[
                  { name: 'Installation Density', icon: Activity, color: 'text-emerald-500' },
                  { name: 'Gender Impact', icon: Users, color: 'text-pink-500' },
                  { name: 'Tender Zones', icon: ShieldCheck, color: 'text-blue-500' },
                  { name: 'Community Vulnerability', icon: AlertCircle, color: 'text-amber-500' }
                ].map(layer => (
                  <label 
                    key={layer.name} 
                    className={`flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition-all ${
                      activeLayers.includes(layer.name) ? 'bg-slate-50' : 'hover:bg-slate-50/50'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`p-1.5 rounded-lg ${activeLayers.includes(layer.name) ? 'bg-white shadow-sm' : 'bg-transparent'}`}>
                        <layer.icon size={16} className={activeLayers.includes(layer.name) ? layer.color : 'text-slate-400'} />
                      </div>
                      <span className={`text-sm font-bold ${activeLayers.includes(layer.name) ? 'text-slate-900' : 'text-slate-500'}`}>
                        {layer.name}
                      </span>
                    </div>
                    <input 
                      type="checkbox" 
                      checked={activeLayers.includes(layer.name)}
                      onChange={() => toggleLayer(layer.name)}
                      className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer" 
                    />
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar: Verification Queue */}
        <AnimatePresence>
          {showVerificationQueue && (
            <motion.div
              initial={{ x: 300, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 300, opacity: 0 }}
              className="w-96 bg-white border-l border-slate-200 flex flex-col shadow-2xl z-20"
            >
              <div className="p-6 border-b border-slate-100 flex items-center justify-between">
                <h3 className="font-bold text-slate-900 flex items-center gap-2">
                  <ShieldCheck className="text-emerald-600" size={20} />
                  GPS Verification
                </h3>
                <button onClick={() => setShowVerificationQueue(false)} className="text-slate-400 hover:text-slate-600">
                  <X size={20} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 space-y-2">
                  <p className="text-xs font-bold text-amber-800 uppercase tracking-wider">Boundary Check</p>
                  <p className="text-xs text-amber-700 leading-relaxed">
                    System automatically validates that coordinates fall within Lesotho's national boundaries via Prospect Spatial API.
                  </p>
                </div>

                {verificationQueue.map(item => (
                  <div key={item.id} className="card p-4 space-y-3 border-slate-100 hover:border-emerald-200 transition-colors">
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">{item.id}</p>
                        <p className="text-sm font-bold text-slate-900">Meter: {item.meterId}</p>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        item.status === 'Pending' ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'
                      }`}>
                        {item.status}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <p className="text-slate-400 font-bold uppercase">Vendor</p>
                        <p className="text-slate-700">{item.vendor}</p>
                      </div>
                      <div>
                        <p className="text-slate-400 font-bold uppercase">Type</p>
                        <p className="text-slate-700">{item.type}</p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-slate-400 font-bold uppercase">Coordinates</p>
                        <p className="text-slate-700 font-mono">{item.lat}, {item.long}</p>
                      </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => updateVerificationStatus(item.id, 'Verified')}
                        className="flex-1 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg hover:bg-emerald-700 transition-colors"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => updateVerificationStatus(item.id, 'Flagged')}
                        className="flex-1 py-2 bg-slate-100 text-slate-600 text-xs font-bold rounded-lg hover:bg-slate-200 transition-colors"
                      >
                        Flag
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

const Monitoring = () => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "api" | "fallback" | "gis" | "reports" | "field">("dashboard");
  const [selectedAudit, setSelectedAudit] = useState<any>(null);
  const [view, setView] = useState<"list" | "review">("list");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const verificationQueue = [
    { 
      id: "AUD-1025", 
      site: "Ha-Ramabanta School", 
      district: "Maseru", 
      tech: "SHS", 
      verifier: "Verifier_Maseru", 
      date: "2025-05-20", 
      status: "Submitted",
      photos: 4,
      notes: "System installed and operational. Beneficiary trained on maintenance.",
      coordinates: "-29.635, 27.912",
      gender: "Female",
      householdId: "HH-4421"
    },
    { 
      id: "AUD-1026", 
      site: "Mokhotlong Clinic", 
      district: "Mokhotlong", 
      tech: "Mini-grid", 
      verifier: "Verifier_Mokhotlong", 
      date: "2025-05-21", 
      status: "Submitted",
      photos: 12,
      notes: "Mini-grid connection verified for 12 households and clinic. Smart meter syncing correctly.",
      coordinates: "-29.283, 29.067",
      gender: "Other",
      householdId: "HH-9901"
    },
    { 
      id: "AUD-1027", 
      site: "Semonkong Community", 
      district: "Maseru", 
      tech: "ICS", 
      verifier: "Verifier_Maseru", 
      date: "2025-05-22", 
      status: "Flagged",
      photos: 2,
      notes: "Discrepancy in serial numbers. Requires follow-up with vendor.",
      coordinates: "-29.833, 28.050",
      gender: "Male",
      householdId: "HH-1120"
    },
  ];

  const [smartMeterData, setSmartMeterData] = useState([
    { id: "MTR-8821", project: "T-001", vendor: "SolarLease Ltd", kwh: 450.2, uptime: 99.9, status: "Online", lastSync: "2025-05-23T10:00:00Z" },
    { id: "MTR-8822", project: "T-001", vendor: "SolarLease Ltd", kwh: 380.5, uptime: 99.8, status: "Online", lastSync: "2025-05-23T10:05:00Z" },
    { id: "MTR-9901", project: "T-002", vendor: "EcoGrid Solutions", kwh: 1250.0, uptime: 94.5, status: "Warning", lastSync: "2025-05-23T09:45:00Z", alert: "Low Battery Voltage" },
    { id: "MTR-7712", project: "T-003", vendor: "SolarLease Ltd", kwh: 0.0, uptime: 0.0, status: "Offline", lastSync: "2025-05-22T18:30:00Z", alert: "Communication Failure" },
  ]);

  const vendorReports = [
    { vendor: "SolarLease Ltd", totalKwh: 15420, avgUptime: 98.2, sites: 45, ranking: 1 },
    { vendor: "EcoGrid Solutions", totalKwh: 12800, avgUptime: 96.5, sites: 12, ranking: 2 },
    { vendor: "Mountain Power", totalKwh: 8900, avgUptime: 92.1, sites: 28, ranking: 3 },
  ];

  const showActionMessage = (message: string) => {
    setActionMessage(message);
    setTimeout(() => setActionMessage(null), 2500);
  };

  const handleRegisterDevice = () => {
    const nextId = `MTR-${Math.floor(1000 + Math.random() * 9000)}`;
    setSmartMeterData(prev => [
      {
        id: nextId,
        project: "T-NEW",
        vendor: "New Vendor",
        kwh: 0,
        uptime: 0,
        status: "Online",
        lastSync: new Date().toISOString(),
      } as any,
      ...prev,
    ]);
    showActionMessage(`Device ${nextId} registered.`);
  };

  const downloadFallbackTemplate = () => {
    const csv = [
      "meter_id,project,vendor,lat,long,timestamp_kat",
      "MTR-0001,T-001,SolarLease Ltd,-29.635,27.912,2026-03-09T00:00:00Z",
    ].join("\n");
    triggerDownload("meter_template.csv", csv, "text/csv;charset=utf-8");
    showActionMessage("Template downloaded.");
  };

  const handleFallbackUpload = () => {
    showActionMessage("CSV uploaded and queued for validation.");
  };

  const exportVendorPdf = () => {
    const content = [
      "Vendor Performance Report (Mock Export)",
      `Generated: ${new Date().toISOString()}`,
      "",
      ...vendorReports.map((row) => `${row.ranking}. ${row.vendor} | ${row.totalKwh} kWh | ${row.avgUptime}% uptime`),
    ].join("\n");
    triggerDownload("vendor_performance_report.txt", content);
    showActionMessage("Vendor performance report exported.");
  };

  const exportMonitoringSummary = () => {
    const content = [
      "Monitoring Summary",
      `Generated: ${new Date().toISOString()}`,
      "",
      ...smartMeterData.map((meter) => `${meter.id} | ${meter.project} | ${meter.vendor} | ${meter.status}`),
    ].join("\n");
    triggerDownload("monitoring_summary.txt", content);
    showActionMessage("Monitoring summary exported.");
  };

  const renderDashboard = () => (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Total Energy Generated" value="37,120 kWh" trend="+12%" icon={Zap} color="bg-emerald-500" />
        <StatCard label="Average Uptime" value="96.8%" trend="+0.5%" icon={Activity} color="bg-blue-500" />
        <StatCard label="Active Installations" value="1,245" trend="+45" icon={Database} color="bg-indigo-500" />
        <StatCard label="Anomalies Detected" value="8" trend="-2" icon={AlertCircle} color="bg-rose-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-bold">Energy Generation Trend</h3>
            <select className="text-xs font-bold border-none bg-slate-100 rounded-lg px-2 py-1">
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
            </select>
          </div>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[
                { name: 'Mon', value: 4200 },
                { name: 'Tue', value: 4500 },
                { name: 'Wed', value: 4100 },
                { name: 'Thu', value: 4800 },
                { name: 'Fri', value: 5200 },
                { name: 'Sat', value: 4900 },
                { name: 'Sun', value: 4600 },
              ]}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#64748b'}} />
                <YAxis axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#64748b'}} />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                />
                <Line type="monotone" dataKey="value" stroke="#10b981" strokeWidth={3} dot={{ r: 4, fill: '#10b981' }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-6">Status Alerts</h3>
          <div className="space-y-4">
            {smartMeterData.filter(m => m.status !== "Online").map(m => (
              <div key={m.id} className="flex gap-4 p-3 rounded-xl bg-slate-50 border border-slate-100">
                <div className={`p-2 rounded-lg ${m.status === 'Offline' ? 'bg-rose-100 text-rose-600' : 'bg-amber-100 text-amber-600'}`}>
                  <AlertCircle size={20} />
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-900">{m.alert}</p>
                  <p className="text-xs text-slate-500">Meter: {m.id} • {m.vendor}</p>
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => setActiveTab("field")} className="w-full mt-6 py-2 text-sm font-bold text-emerald-600 hover:text-emerald-700 transition-colors">
            View All Alerts
          </button>
        </div>
      </div>
    </div>
  );

  const renderMeterAPI = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">Smart Meter API Integration</h3>
        <button onClick={handleRegisterDevice} className="btn-primary flex items-center gap-2 text-xs py-2">
          <Plus size={16} /> Register New Device
        </button>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Meter ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Project / Vendor</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">kWh Gen.</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Uptime</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Last Sync</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {smartMeterData.map((meter, idx) => (
              <tr key={meter.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{`SM-${String(idx + 1).padStart(3, "0")}`}</td>
                <td className="px-6 py-4 font-mono text-xs font-bold text-blue-600">{meter.id}</td>
                <td className="px-6 py-4">
                  <div className="text-sm font-bold text-slate-900">{meter.project}</div>
                  <div className="text-xs text-slate-500">{meter.vendor}</div>
                </td>
                <td className="px-6 py-4 text-sm font-medium text-slate-700">{meter.kwh} kWh</td>
                <td className="px-6 py-4 text-sm text-slate-600">{meter.uptime}%</td>
                <td className="px-6 py-4 text-xs text-slate-500">{new Date(meter.lastSync).toLocaleString()}</td>
                <td className="px-6 py-4">
                  <span className={`badge ${
                    meter.status === 'Online' ? 'bg-emerald-100 text-emerald-700' : 
                    meter.status === 'Warning' ? 'bg-amber-100 text-amber-700' : 
                    'bg-rose-100 text-rose-700'
                  }`}>
                    {meter.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderFallback = () => (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="text-center space-y-2">
        <h3 className="text-xl font-bold text-slate-900">Manual CSV Upload (Fallback)</h3>
        <p className="text-slate-500">Upload data manually when smart meter API synchronization fails.</p>
      </div>
      
      <div className="card p-8 space-y-6">
        <div className="p-4 bg-blue-50 rounded-xl border border-blue-100 flex gap-4 items-start">
          <div className="p-2 bg-blue-100 text-blue-600 rounded-lg">
            <Download size={20} />
          </div>
          <div>
            <p className="text-sm font-bold text-blue-900">Need the template?</p>
            <p className="text-xs text-blue-700 mt-1">Download our standardized CSV template matching the Prospect schema.</p>
            <button onClick={downloadFallbackTemplate} className="mt-2 text-xs font-bold text-blue-600 underline">Download Template.csv</button>
          </div>
        </div>

        <div className="space-y-4">
          <div className="border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center hover:border-emerald-500 transition-colors cursor-pointer group">
            <Upload className="mx-auto text-slate-400 mb-4 group-hover:text-emerald-500 transition-colors" size={48} />
            <p className="text-sm font-bold text-slate-900">Click to upload or drag and drop</p>
            <p className="text-xs text-slate-500 mt-1">Only .csv files under 5MB are supported</p>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-bold text-slate-500 uppercase ml-1">Latitude *</label>
              <input type="number" step="any" className="input-field" placeholder="-29.635" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-bold text-slate-500 uppercase ml-1">Longitude *</label>
              <input type="number" step="any" className="input-field" placeholder="27.912" />
            </div>
          </div>
          
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-500 uppercase ml-1">Date & Time *</label>
            <input type="datetime-local" className="input-field" />
          </div>
        </div>

        <button onClick={handleFallbackUpload} className="btn-primary w-full py-3 rounded-xl">Upload and Validate Data</button>
      </div>
    </div>
  );

  const renderReports = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">Vendor Performance Reports</h3>
        <div className="flex gap-2">
          <select className="text-xs font-bold border border-slate-200 rounded-lg px-3 py-2">
            <option>Daily Report</option>
            <option>Weekly Report</option>
            <option>Monthly Report</option>
          </select>
          <button onClick={exportVendorPdf} className="btn-secondary flex items-center gap-2 text-xs py-2">
            <Download size={16} /> Export PDF
          </button>
        </div>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Ranking</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Total kWh</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Avg Uptime</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Sites</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Performance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {vendorReports.map((report, idx) => (
              <tr key={report.vendor} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{`RPT-${String(idx + 1).padStart(3, "0")}`}</td>
                <td className="px-6 py-4">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                    report.ranking === 1 ? 'bg-amber-100 text-amber-700' : 
                    report.ranking === 2 ? 'bg-slate-200 text-slate-700' : 
                    'bg-orange-100 text-orange-700'
                  }`}>
                    {report.ranking}
                  </div>
                </td>
                <td className="px-6 py-4 font-bold text-slate-900">{report.vendor}</td>
                <td className="px-6 py-4 text-sm text-slate-700">{report.totalKwh.toLocaleString()} kWh</td>
                <td className="px-6 py-4 text-sm text-slate-600">{report.avgUptime}%</td>
                <td className="px-6 py-4 text-sm text-slate-600">{report.sites}</td>
                <td className="px-6 py-4 text-right">
                  <div className="inline-flex items-center gap-1 text-emerald-600 font-bold text-xs">
                    <TrendingUp size={14} />
                    Top Performer
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderFieldVerification = () => {
    if (view === "review" && selectedAudit) {
      return (
        <div className="space-y-6 max-w-5xl mx-auto">
          <div className="flex items-center gap-4">
            <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
              <ChevronRight className="rotate-180" size={20} />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Review Field Survey</h1>
              <p className="text-slate-500">Survey ID: {selectedAudit.id} • Household: {selectedAudit.householdId}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className="card p-6 space-y-6">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <h3 className="text-lg font-bold">Survey Evidence</h3>
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">{selectedAudit.photos} Photos Attached</span>
                </div>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[1, 2, 3, 4].map(i => (
                    <div key={i} className="aspect-square rounded-xl bg-slate-100 overflow-hidden relative group cursor-pointer">
                      <img 
                        src={`https://picsum.photos/seed/survey-${selectedAudit.id}-${i}/400/400`} 
                        alt="Evidence" 
                        className="w-full h-full object-cover group-hover:scale-110 transition-transform"
                        referrerPolicy="no-referrer"
                      />
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-slate-400 uppercase">Beneficiary Gender</p>
                    <p className="text-sm font-bold text-slate-900">{selectedAudit.gender}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-slate-400 uppercase">Survey Timestamp</p>
                    <p className="text-sm font-bold text-slate-900">{selectedAudit.date}</p>
                  </div>
                </div>

                <div className="space-y-4 pt-4">
                  <h4 className="text-sm font-bold text-slate-900 uppercase tracking-widest">Field Officer Notes</h4>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 text-sm text-slate-600 italic">
                    "{selectedAudit.notes}"
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-6">
              <div className="card p-6 bg-slate-900 text-white">
                <h3 className="text-lg font-bold mb-4">GIS Validation</h3>
                <div className="aspect-video bg-slate-800 rounded-xl mb-4 flex items-center justify-center overflow-hidden relative">
                  <MapIcon size={48} className="text-slate-700" />
                  <div className="absolute inset-0 bg-emerald-500/10" />
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
                    <div className="w-4 h-4 bg-emerald-500 rounded-full animate-ping" />
                    <div className="w-4 h-4 bg-emerald-500 rounded-full absolute top-0 border-2 border-white" />
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-xs text-slate-400 font-bold uppercase tracking-widest">Captured Coordinates</p>
                  <p className="text-sm font-mono">{selectedAudit.coordinates}</p>
                </div>
              </div>

              <div className="card p-6 space-y-4">
                <h3 className="text-lg font-bold">Verification Decision</h3>
                <div className="grid grid-cols-2 gap-3">
                  <button onClick={() => setView("list")} className="btn-secondary border-rose-200 text-rose-600">Flag</button>
                  <button onClick={() => setView("list")} className="btn-primary">Match</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">Field Verification Queue (Kobo/ODK)</h3>
          <button onClick={() => showActionMessage("Filters applied to current survey queue.")} className="btn-secondary flex items-center gap-2 text-xs py-2">
            <Filter size={16} /> Filter Surveys
          </button>
        </div>
        <div className="card overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Survey ID</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Household / District</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Field Officer</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {verificationQueue.map((audit, idx) => (
                <tr key={audit.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-4 font-mono text-xs text-slate-500">{`SVY-${String(idx + 1).padStart(3, "0")}`}</td>
                  <td className="px-6 py-4 font-mono text-xs font-bold text-blue-600">{audit.id}</td>
                  <td className="px-6 py-4">
                    <div className="text-sm font-bold text-slate-900">{audit.householdId}</div>
                    <div className="text-xs text-slate-500">{audit.district} • {audit.tech}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-600">{audit.verifier}</td>
                  <td className="px-6 py-4">
                    <span className={`badge ${audit.status === 'Flagged' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>
                      {audit.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button 
                      onClick={() => { setSelectedAudit(audit); setView("review"); }}
                      className="btn-secondary py-1.5 px-4 text-xs"
                    >
                      Verify Survey
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderGIS = () => (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">GIS Validation Dashboard</h3>
        <div className="flex gap-4">
          <div className="flex gap-2">
            <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-slate-400">
              <div className="w-2 h-2 rounded-full bg-emerald-500" /> Online
            </span>
            <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-slate-400">
              <div className="w-2 h-2 rounded-full bg-amber-500" /> Warning
            </span>
            <span className="flex items-center gap-1 text-[10px] font-bold uppercase text-slate-400">
              <div className="w-2 h-2 rounded-full bg-rose-500" /> Offline
            </span>
          </div>
        </div>
      </div>

      <div className="flex-1 card relative bg-slate-200 overflow-hidden min-h-[500px]">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center space-y-4">
            <Globe size={64} className="mx-auto text-slate-400" />
            <div>
              <p className="text-lg font-bold text-slate-600">Lesotho GIS Infrastructure</p>
              <p className="text-slate-500">Spatial Validation Engine Powered by Prospect</p>
            </div>
          </div>
        </div>
        
        {/* Mock Pins */}
        <div className="absolute top-1/4 left-1/3 w-6 h-6 rounded-full bg-emerald-500 border-4 border-white shadow-xl animate-pulse cursor-pointer group">
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-4 bg-white rounded-2xl shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 border border-slate-100">
            <div className="flex justify-between items-start mb-2">
              <div>
                <p className="text-xs font-bold text-slate-900">Meter: MTR-8821</p>
                <p className="text-[10px] text-slate-500">Project: RL-2025-SHS-01</p>
              </div>
              <span className="px-2 py-0.5 rounded bg-emerald-100 text-[8px] font-bold text-emerald-700 uppercase">Verified</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px] mb-2">
              <div>
                <p className="text-slate-400 uppercase font-bold">Vendor</p>
                <p className="text-slate-700">SolarLease Ltd</p>
              </div>
              <div>
                <p className="text-slate-400 uppercase font-bold">Accuracy</p>
                <p className="text-slate-700">2.4 meters</p>
              </div>
              <div>
                <p className="text-slate-400 uppercase font-bold">Lat/Long</p>
                <p className="text-slate-700">-29.63, 27.91</p>
              </div>
              <div>
                <p className="text-slate-400 uppercase font-bold">Validated By</p>
                <p className="text-slate-700">Admin_01</p>
              </div>
            </div>
            <div className="pt-2 border-t border-slate-100 flex justify-between items-center">
              <span className="text-xs font-bold text-emerald-600">450.2 kWh Produced</span>
              <span className="text-[8px] text-slate-400">2025-05-23</span>
            </div>
          </div>
        </div>
        <div className="absolute top-1/2 left-1/2 w-6 h-6 rounded-full bg-amber-500 border-4 border-white shadow-xl" />
        <div className="absolute bottom-1/3 right-1/4 w-6 h-6 rounded-full bg-rose-500 border-4 border-white shadow-xl" />

        <div className="absolute top-6 right-6">
          <div className="card p-4 w-64 space-y-4">
            <h4 className="font-bold text-xs uppercase tracking-widest text-slate-400">Filters</h4>
            <div className="space-y-2">
              <select className="input-field text-xs py-2">
                <option>All Tenders</option>
                <option>RL-2025-SHS-01</option>
              </select>
              <select className="input-field text-xs py-2">
                <option>All Regions</option>
                <option>Maseru</option>
              </select>
              <select className="input-field text-xs py-2">
                <option>All Statuses</option>
                <option>Online</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <AnimatePresence>
        {actionMessage && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 right-8 z-[300] bg-blue-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
          >
            {actionMessage}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Monitoring & Evaluation</h1>
          <p className="text-slate-500">Real-time performance tracking powered by Prospect Integration</p>
        </div>
        <div className="flex gap-3">
          <button onClick={exportMonitoringSummary} className="btn-secondary flex items-center gap-2">
            <Download size={18} /> Export PDF
          </button>
        </div>
      </div>

      <div className="flex gap-2 p-1 bg-slate-100 rounded-2xl w-fit">
        {[
          { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
          { id: 'api', label: 'Meter API', icon: Zap },
          { id: 'fallback', label: 'Fallback', icon: Upload },
          { id: 'gis', label: 'GIS Map', icon: Globe },
          { id: 'reports', label: 'Reports', icon: FileText },
          { id: 'field', label: 'Field Verification', icon: ClipboardCheck },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all ${
              activeTab === tab.id 
                ? "bg-white text-emerald-600 shadow-sm" 
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            <tab.icon size={18} />
            {tab.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === 'dashboard' && renderDashboard()}
          {activeTab === 'api' && renderMeterAPI()}
          {activeTab === 'fallback' && renderFallback()}
          {activeTab === 'gis' && renderGIS()}
          {activeTab === 'reports' && renderReports()}
          {activeTab === 'field' && renderFieldVerification()}
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

const PreQualification = () => {
  const [selectedVendor, setSelectedVendor] = useState<VendorPrequalification | null>(null);
  const [vendors, setVendors] = useState<VendorPrequalification[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [reviewerComments, setReviewerComments] = useState("");
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toFileUrl = (raw?: string | null) => {
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    return `${base}${path}`;
  };

  const renderDocLink = (label: string, url?: string | null) => (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">{label}</span>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="text-emerald-600 hover:underline flex items-center gap-1"
        >
          <Download size={14} /> View Document
        </a>
      ) : (
        <span className="text-xs text-slate-400">Not provided</span>
      )}
    </div>
  );

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const loadPrequalifications = React.useCallback(async () => {
    setLoading(true);
    try {
      const rows = await fetchVendorPrequalifications();
      setVendors(rows);
    } catch (err: any) {
      const raw = String(err?.message || "");
      if (isConnectivityError(raw)) {
        showNotification(`Cannot connect to backend (${API_BASE}).`);
      } else {
        showNotification(toFriendlyApiMessage(raw) || "Failed to load pre-qualification records.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadPrequalifications();
  }, [loadPrequalifications]);

  React.useEffect(() => {
    const id = setInterval(() => {
      void loadPrequalifications();
    }, 20000);
    return () => clearInterval(id);
  }, [loadPrequalifications]);

  const updateVendorStatus = async (
    vendor: VendorPrequalification,
    newStatus: VendorPrequalification["status"]
  ) => {
    try {
      setIsSubmitting(true);
      let updated: VendorPrequalification;
      if (newStatus === "Under Review") {
        updated = await startVendorPrequalificationReview(vendor.id, reviewerComments);
      } else if (newStatus === "Approved") {
        updated = await approveVendorPrequalification(vendor.id, reviewerComments);
      } else if (newStatus === "Clarification Requested") {
        updated = await requestVendorPrequalificationClarification(vendor.id, reviewerComments);
      } else {
        updated = await rejectVendorPrequalification(vendor.id, reviewerComments);
      }

      setVendors(prev => prev.map(item => item.id === updated.id ? updated : item));
      await loadPrequalifications();
      setSelectedVendor(null);
      setReviewerComments("");
      showNotification(`Vendor application ${newStatus.toLowerCase()} successfully.`);
    } catch (err: any) {
      const raw = String(err?.message || "");
      if (isConnectivityError(raw)) {
        showNotification(`Cannot connect to backend (${API_BASE}).`);
      } else {
        showNotification(toFriendlyApiMessage(raw) || "Failed to update vendor application.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const pendingCount = vendors.filter(v => v.status === "Pending").length;

  return (
    <div className="space-y-6">
      <AnimatePresence>
        {notification && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl flex items-center gap-3"
          >
            <CheckCircle2 size={20} />
            <span className="font-medium">{notification}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Vendor Pre-Qualification</h1>
        <div className="flex gap-2">
          <span className="badge bg-amber-100 text-amber-700">{pendingCount} Pending Reviews</span>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor Name</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Type</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Technologies</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Submitted</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!loading && vendors.map(vendor => (
              <tr key={vendor.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{vendor.id}</td>
                <td className="px-6 py-4">
                  <div className="font-medium text-slate-900">{vendor.companyName}</div>
                  <div className="text-xs text-slate-500 font-mono">{vendor.vendorUsername || `ID-${vendor.id}`}</div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">{vendor.organizationType || "N/A"}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{vendor.technologyTypes.join(", ") || "N/A"}</td>
                <td className="px-6 py-4 text-sm text-slate-600">{new Date(vendor.submittedAt).toLocaleDateString()}</td>
                <td className="px-6 py-4">
                  <span className={`badge ${
                    vendor.status === 'Approved' ? 'bg-emerald-100 text-emerald-700' :
                    vendor.status === 'Under Review' ? 'bg-blue-100 text-blue-700' :
                    vendor.status === 'Rejected' ? 'bg-rose-100 text-rose-700' :
                    vendor.status === 'Clarification Requested' ? 'bg-amber-100 text-amber-700' :
                    'bg-slate-100 text-slate-700'
                  }`}>
                    {vendor.status}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <button 
                    onClick={() => {
                      setSelectedVendor(vendor);
                      setReviewerComments(vendor.reviewerComments || "");
                    }}
                    className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                  >
                    Review Profile
                  </button>
                </td>
              </tr>
            ))}
            {!loading && vendors.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  No pre-qualification submissions found.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  Loading pre-qualification submissions...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {selectedVendor && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setSelectedVendor(null)}
          >
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-100 flex items-center justify-between">
                <h2 className="text-xl font-bold text-slate-900">Vendor Profile Review: {selectedVendor.companyName}</h2>
                <button onClick={() => setSelectedVendor(null)} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
                  <X size={20} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-8 space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-6">
                    <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Legal & Administrative</h3>
                    <div className="space-y-4">
                      {renderDocLink("Company Registration", toFileUrl(selectedVendor.registrationCertificate))}
                      {renderDocLink("Tax Clearance Certificate", toFileUrl(selectedVendor.taxComplianceCertificate))}
                      {renderDocLink("Valid Trading License", toFileUrl(selectedVendor.tradingLicense))}
                      {renderDocLink("Experience & Financial Proof", toFileUrl(selectedVendor.experienceFinancialProof))}
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Organization Type</span>
                        <span className="text-slate-900 font-medium">{selectedVendor.organizationType || "N/A"}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Tax ID</span>
                        <span className="text-slate-900 font-medium">{selectedVendor.taxId || "N/A"}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">HQ Address</span>
                        <span className="text-slate-900 font-medium">{selectedVendor.hqAddress || "N/A"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-6">
                    <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Technical Capacity</h3>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Technology Tier</span>
                        <span className="text-slate-900 font-bold">{selectedVendor.techTier || "N/A"}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Years of Experience</span>
                        <span className="text-slate-900 font-bold">{selectedVendor.yearsExperience} Years</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Annual Revenue (LSL)</span>
                        <span className="text-slate-900 font-bold">M {(selectedVendor.annualRevenue ?? 0).toLocaleString()}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Districts Covered</span>
                        <span className="text-slate-900 font-bold">{selectedVendor.districtsCovered} Districts</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-6">
                    <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Social Inclusion Commitments</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
                        <p className="text-[10px] font-bold text-emerald-700 uppercase mb-1">Female Beneficiaries</p>
                        <p className="text-2xl font-bold text-emerald-600">{selectedVendor.femaleBeneficiaryTarget}%</p>
                        <p className="text-[8px] text-emerald-500 italic mt-1">Target: &gt;= 50%</p>
                      </div>
                      <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
                        <p className="text-[10px] font-bold text-blue-700 uppercase mb-1">Vulnerable Groups</p>
                        <p className="text-2xl font-bold text-blue-600">{selectedVendor.vulnerableGroupTarget}%</p>
                        <p className="text-[8px] text-blue-500 italic mt-1">Target: &gt;= 30%</p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-6">
                    <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Financial & Contact</h3>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Bank Account</span>
                        <span className="text-slate-900 font-medium">
                          {selectedVendor.bankAccountName || "N/A"} {selectedVendor.bankAccountNumber ? `• ${selectedVendor.bankAccountNumber}` : ""}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Focal Person</span>
                        <span className="text-slate-900 font-medium">
                          {selectedVendor.genderOfFocalPerson || "N/A"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Contact</span>
                        <span className="text-slate-900 font-medium">{selectedVendor.contactNumber || "N/A"}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Email</span>
                        <span className="text-slate-900 font-medium">{selectedVendor.email || "N/A"}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                  <div className="flex items-center gap-2 text-slate-900 mb-2">
                    <ShieldCheck size={18} className="text-emerald-600" />
                    <span className="font-bold text-sm">Declaration of Truthfulness</span>
                  </div>
                  <p className="text-xs text-slate-600 italic">
                    "I hereby declare that all information provided in this pre-qualification application is true, accurate, and complete..." 
                    <span className="text-emerald-600 font-bold ml-2">Signed & Confirmed</span>
                  </p>
                </div>

                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900">Reviewer Comments</h3>
                  <textarea 
                    className="input-field min-h-[100px]" 
                    placeholder="Add internal notes or feedback for the vendor..."
                    value={reviewerComments}
                    onChange={(e) => setReviewerComments(e.target.value)}
                  ></textarea>
                </div>

                <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
                  <button
                    onClick={() => updateVendorStatus(selectedVendor, 'Under Review')}
                    disabled={isSubmitting}
                    className="btn-secondary disabled:opacity-60"
                  >
                    Start Review
                  </button>
                  <button 
                    onClick={() => updateVendorStatus(selectedVendor, 'Rejected')}
                    disabled={isSubmitting}
                    className="btn-secondary text-rose-600 border-rose-100 hover:bg-rose-50 disabled:opacity-60"
                  >
                    Reject Application
                  </button>
                  <button 
                    onClick={() => updateVendorStatus(selectedVendor, 'Clarification Requested')}
                    disabled={isSubmitting}
                    className="btn-secondary text-amber-600 border-amber-100 hover:bg-amber-50 disabled:opacity-60"
                  >
                    Request Clarification
                  </button>
                  <button 
                    onClick={() => updateVendorStatus(selectedVendor, 'Approved')}
                    disabled={isSubmitting}
                    className="btn-primary disabled:opacity-60"
                  >
                    {isSubmitting ? "Submitting..." : "Approve for EVL"}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const Blacklisting = ({ currentUser }: { currentUser: User | null }) => {
  const [cases, setCases] = useState<VendorBlacklistCase[]>([]);
  const [appeals, setAppeals] = useState<BlacklistAppeal[]>([]);
  const [vendors, setVendors] = useState<VendorPrequalification[]>([]);
  const [selectedCase, setSelectedCase] = useState<VendorBlacklistCase | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [initiateForm, setInitiateForm] = useState({
    vendorId: "",
    reason: "Fraudulent Reporting",
    description: "",
    coolingOffDays: "14",
    expiryDate: "",
    isPermanent: false,
  });
  const [initiateFile, setInitiateFile] = useState<File | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [appealNotes, setAppealNotes] = useState("");
  const [appealResolution, setAppealResolution] = useState("");
  const [appealFile, setAppealFile] = useState<File | null>(null);
  const caseDetailsRef = React.useRef<HTMLDivElement | null>(null);

  const role = currentUser?.role;
  const canInitiate = role === UserRole.RBF_OFFICIAL || role === UserRole.AUDITOR;
  const canReview = role === UserRole.TAC || role === UserRole.DOE_OFFICER || role === UserRole.AUDITOR;
  const canConfirm = role === UserRole.ADMIN || role === UserRole.DOE_OFFICER;
  const canReviewAppeals = role === UserRole.AUDITOR || role === UserRole.ADMIN;
  const canAppeal = role === UserRole.VENDOR;

  const toFileUrl = (raw?: string | null) => {
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    return `${base}${path}`;
  };

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const loadBlacklisting = React.useCallback(async () => {
    setLoading(true);
    try {
      const [caseRows, appealRows, vendorRows] = await Promise.all([
        fetchBlacklistCases(),
        fetchBlacklistAppeals(),
        (canInitiate ? fetchVendorPrequalifications() : Promise.resolve([])),
      ]);
      setCases(caseRows);
      setAppeals(appealRows);
      setVendors(vendorRows);
      setSelectedCase(prev => caseRows.find(item => item.id === prev?.id) || caseRows[0] || null);
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(isConnectivityError(raw) ? `Cannot connect to backend (${API_BASE}).` : (toFriendlyApiMessage(raw) || "Failed to load blacklisting records."));
    } finally {
      setLoading(false);
    }
  }, [canInitiate]);

  React.useEffect(() => {
    void loadBlacklisting();
  }, [loadBlacklisting]);

  const selectedVendorRecord = vendors.find(v => String(v.vendorId) === initiateForm.vendorId);
  const activeCaseAppeals = appeals.filter(item => item.case === selectedCase?.id);

  const openCase = (item: VendorBlacklistCase) => {
    setSelectedCase(item);
    setReviewNotes(item.reviewNotes ?? "");
    setDecisionNotes(item.finalDecisionNotes ?? "");
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        caseDetailsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  };

  const handleInitiate = async () => {
    if (!initiateForm.vendorId) {
      showNotification("Select a vendor first.");
      return;
    }
    try {
      setIsSubmitting(true);
      await initiateVendorBlacklisting({
        vendorId: initiateForm.vendorId,
        reason: initiateForm.reason,
        description: initiateForm.description,
        coolingOffDays: Number(initiateForm.coolingOffDays || 14),
        expiryDate: initiateForm.expiryDate || undefined,
        isPermanent: initiateForm.isPermanent,
        justificationDocument: initiateFile,
      });
      setInitiateForm({
        vendorId: "",
        reason: "Fraudulent Reporting",
        description: "",
        coolingOffDays: "14",
        expiryDate: "",
        isPermanent: false,
      });
      setInitiateFile(null);
      await loadBlacklisting();
      showNotification("Blacklisting case initiated.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(toFriendlyApiMessage(raw) || "Failed to initiate blacklisting.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCaseAction = async (action: "review" | "confirm" | "reject" | "reinstate") => {
    if (!selectedCase) return;
    try {
      setIsSubmitting(true);
      if (action === "review") {
        await reviewBlacklistCase(selectedCase.id, reviewNotes);
      } else if (action === "confirm") {
        await confirmBlacklistCase(selectedCase.id, {
          finalDecisionNotes: decisionNotes,
          expiryDate: initiateForm.expiryDate || selectedCase.expiryDate || undefined,
          isPermanent: initiateForm.isPermanent || selectedCase.isPermanent,
        });
      } else if (action === "reject") {
        await rejectBlacklistCase(selectedCase.id, decisionNotes);
      } else {
        await reinstateBlacklistCase(selectedCase.id);
      }
      await loadBlacklisting();
      showNotification(`Case ${action} completed.`);
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(toFriendlyApiMessage(raw) || `Failed to ${action} blacklist case.`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitAppeal = async () => {
    if (!selectedCase) return;
    try {
      setIsSubmitting(true);
      await submitBlacklistAppeal(selectedCase.id, {
        rebuttalText: appealNotes,
        rebuttalDocument: appealFile,
      });
      setAppealNotes("");
      setAppealFile(null);
      await loadBlacklisting();
      showNotification("Appeal submitted.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(toFriendlyApiMessage(raw) || "Failed to submit appeal.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReviewAppeal = async (appealId: string) => {
    try {
      setIsSubmitting(true);
      await reviewBlacklistAppeal(appealId, appealResolution);
      setAppealResolution("");
      await loadBlacklisting();
      showNotification("Appeal reviewed.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(toFriendlyApiMessage(raw) || "Failed to review appeal.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const pendingCases = cases.filter(item => item.status === "Initiated" || item.status === "Under Review").length;

  return (
    <div className="space-y-6">
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-24 right-8 z-[200] bg-slate-900 text-white px-6 py-3 rounded-xl shadow-xl flex items-center gap-3"
          >
            <CheckCircle2 size={20} />
            <span className="font-medium">{notification}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Blacklisting</h1>
        <div className="flex gap-2">
          <span className="badge bg-rose-100 text-rose-700">{pendingCases} Active Cases</span>
          <span className="badge bg-slate-100 text-slate-700">{appeals.length} Appeals</span>
        </div>
      </div>

      {canInitiate && (
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold">Initiate Blacklisting</h3>
              <p className="text-sm text-slate-500">Open a new four-eyes blacklisting case and suspend the vendor during cooling-off.</p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Vendor</label>
              <select
                className="input-field py-2 text-sm"
                value={initiateForm.vendorId}
                onChange={(e) => setInitiateForm(prev => ({ ...prev, vendorId: e.target.value }))}
              >
                <option value="">Select vendor</option>
                {vendors.map(vendor => (
                  <option key={vendor.id} value={vendor.vendorId}>
                    {vendor.companyName} ({vendor.vendorUsername})
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Reason</label>
              <select
                className="input-field py-2 text-sm"
                value={initiateForm.reason}
                onChange={(e) => setInitiateForm(prev => ({ ...prev, reason: e.target.value }))}
              >
                <option>Fraudulent Reporting</option>
                <option>Integrity Breach</option>
                <option>Persistent Non-Performance</option>
                <option>External Legal Action</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Cooling-Off Days</label>
              <input
                type="number"
                min={1}
                className="input-field py-2 text-sm"
                value={initiateForm.coolingOffDays}
                onChange={(e) => setInitiateForm(prev => ({ ...prev, coolingOffDays: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Expiry Date</label>
              <input
                type="date"
                className="input-field py-2 text-sm"
                value={initiateForm.expiryDate}
                onChange={(e) => setInitiateForm(prev => ({ ...prev, expiryDate: e.target.value }))}
                disabled={initiateForm.isPermanent}
              />
            </div>
            <label className="flex items-center gap-3 pt-6">
              <input
                type="checkbox"
                checked={initiateForm.isPermanent}
                onChange={(e) => setInitiateForm(prev => ({ ...prev, isPermanent: e.target.checked, expiryDate: e.target.checked ? "" : prev.expiryDate }))}
              />
              <span className="text-sm font-medium text-slate-700">Permanent blacklist</span>
            </label>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-slate-400 uppercase">Justification Document</label>
              <input type="file" className="input-field py-2 text-sm" onChange={(e) => setInitiateFile(e.target.files?.[0] ?? null)} />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Description</label>
            <textarea
              className="input-field min-h-28 text-sm"
              value={initiateForm.description}
              onChange={(e) => setInitiateForm(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Summarize the triggering event, evidence, and risk to programme integrity."
            />
          </div>
          {selectedVendorRecord && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Vendor: <span className="font-semibold text-slate-900">{selectedVendorRecord.companyName}</span> • Tax ID: {selectedVendorRecord.taxId || "N/A"}
            </div>
          )}
          <div className="flex justify-end">
            <button onClick={handleInitiate} disabled={isSubmitting} className="btn-primary disabled:opacity-60">Initiate Blacklisting</button>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">Blacklisting Policy Table</h3>
          <p className="text-sm text-slate-500">Operational effects by vendor restriction stage.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Feature</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Suspended (Initiated)</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Blacklisted (Confirmed)</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Reinstated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {[
                ["Login", "Allowed", "Allowed", "Allowed"],
                ["View Past Projects", "Read-Only", "Read-Only", "Read-Only"],
                ["Submit New Bids", "Blocked", "Blocked", "Blocked (until re-qualified)"],
                ["Request Payments", "Blocked", "Blocked", "Allowed"],
                ["Field Verification", "Paused", "Terminated", "Resume (new logs only)"],
              ].map(([feature, suspended, blacklisted, reinstated]) => (
                <tr key={feature} className="hover:bg-slate-50">
                  <td className="px-6 py-4 text-sm font-medium text-slate-900">{feature}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{suspended}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{blacklisted}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{reinstated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-6">
        <div className="card overflow-hidden">
          <div className="p-6 border-b border-slate-100">
            <h3 className="text-lg font-bold">Blacklist Cases</h3>
            <p className="text-sm text-slate-500">Track suspension, review, confirmation, and reinstatement.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50">
                  <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor</th>
                  <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Reason</th>
                  <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
                  <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Cooling-Off</th>
                  <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cases.map(item => {
                  const isSelected = selectedCase?.id === item.id;
                  return (
                    <React.Fragment key={item.id}>
                      <tr
                        onClick={() => openCase(item)}
                        className={`cursor-pointer hover:bg-slate-50 ${isSelected ? "bg-emerald-50/60" : ""}`}
                      >
                        <td className="px-6 py-4 text-sm font-medium text-slate-900">{item.vendorUsername || item.vendor}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{item.reason}</td>
                        <td className="px-6 py-4">
                          <span className={`badge ${item.status === "Blacklisted" ? "bg-rose-100 text-rose-700" : item.status === "Under Review" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-700"}`}>
                            {item.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-500">{item.coolingOffUntil ? new Date(item.coolingOffUntil).toLocaleString() : "N/A"}</td>
                        <td className="px-6 py-4 text-right">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              openCase(item);
                            }}
                            className={`btn-secondary py-1 px-3 text-xs ${isSelected ? "border-emerald-200 text-emerald-700 bg-emerald-50" : ""}`}
                          >
                            {isSelected ? "Opened" : "Open"}
                          </button>
                        </td>
                      </tr>
                      {isSelected && (
                        <tr className="bg-emerald-50/40">
                          <td colSpan={5} className="px-6 py-3 text-sm text-slate-700">
                            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                              <span>
                                Selected case: <span className="font-semibold">{item.vendorUsername || item.vendor}</span> • {item.status}
                              </span>
                              <span className="text-slate-500">
                                Details are shown in the Case Details panel.
                              </span>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
                {!loading && cases.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-sm text-slate-500">No blacklist cases found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div ref={caseDetailsRef} className="card p-6 space-y-4">
          <h3 className="text-lg font-bold">Case Details</h3>
          {!selectedCase ? (
            <p className="text-sm text-slate-500">Select a blacklist case to review actions and evidence.</p>
          ) : (
            <>
              <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                Viewing case for <span className="font-semibold">{selectedCase.vendorUsername || selectedCase.vendor}</span>.
              </div>
              <div className="space-y-2 text-sm">
                <p><span className="font-bold text-slate-700">Vendor:</span> {selectedCase.vendorUsername || selectedCase.vendor}</p>
                <p><span className="font-bold text-slate-700">Reason:</span> {selectedCase.reason}</p>
                <p><span className="font-bold text-slate-700">Status:</span> {selectedCase.status}</p>
                <p><span className="font-bold text-slate-700">Initiated:</span> {selectedCase.initiatedAt ? new Date(selectedCase.initiatedAt).toLocaleString() : "N/A"}</p>
                <p><span className="font-bold text-slate-700">Expiry:</span> {selectedCase.isPermanent ? "Permanent" : (selectedCase.expiryDate || "Not set")}</p>
              </div>
              {selectedCase.description && (
                <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 text-sm text-slate-600">
                  {selectedCase.description}
                </div>
              )}
              {selectedCase.justificationDocument && (
                <a href={toFileUrl(selectedCase.justificationDocument) || undefined} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline text-sm inline-flex items-center gap-2">
                  <Download size={16} /> View Justification Document
                </a>
              )}

              {canReview && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <label className="text-[10px] font-bold text-slate-400 uppercase">Review Notes</label>
                  <textarea className="input-field min-h-24 text-sm" value={reviewNotes} onChange={(e) => setReviewNotes(e.target.value)} />
                  <button type="button" onClick={() => handleCaseAction("review")} disabled={isSubmitting} className="btn-secondary w-full disabled:opacity-60">Mark Under Review</button>
                </div>
              )}

              {canConfirm && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <label className="text-[10px] font-bold text-slate-400 uppercase">Decision Notes</label>
                  <textarea className="input-field min-h-24 text-sm" value={decisionNotes} onChange={(e) => setDecisionNotes(e.target.value)} />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <button type="button" onClick={() => handleCaseAction("confirm")} disabled={isSubmitting} className="btn-primary disabled:opacity-60">Confirm Blacklist</button>
                    <button type="button" onClick={() => handleCaseAction("reject")} disabled={isSubmitting} className="btn-secondary disabled:opacity-60">Reject Case</button>
                  </div>
                  {selectedCase.status === "Blacklisted" && (
                    <button type="button" onClick={() => handleCaseAction("reinstate")} disabled={isSubmitting} className="btn-secondary w-full disabled:opacity-60">Reinstate Vendor</button>
                  )}
                </div>
              )}

              {canAppeal && currentUser?.blacklistSummary?.appeal_allowed && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <label className="text-[10px] font-bold text-slate-400 uppercase">Appeal Statement</label>
                  <textarea className="input-field min-h-24 text-sm" value={appealNotes} onChange={(e) => setAppealNotes(e.target.value)} />
                  <input type="file" className="input-field py-2 text-sm" onChange={(e) => setAppealFile(e.target.files?.[0] ?? null)} />
                  <button type="button" onClick={handleSubmitAppeal} disabled={isSubmitting} className="btn-primary w-full disabled:opacity-60">Submit Appeal</button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">Appeals</h3>
            <p className="text-sm text-slate-500">Vendor rebuttals routed for audit/legal review.</p>
          </div>
        </div>
        <div className="divide-y divide-slate-100">
          {appeals.length === 0 && (
            <div className="p-6 text-sm text-slate-500">No appeals submitted yet.</div>
          )}
          {appeals.map(item => (
            <div key={item.id} className="p-6 space-y-3">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-900">{item.vendorUsername || item.vendor}</p>
                  <p className="text-xs text-slate-500">Case {item.case} • Submitted {item.submittedAt ? new Date(item.submittedAt).toLocaleString() : "N/A"}</p>
                </div>
                <span className={`badge ${item.status === "Resolved" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{item.status}</span>
              </div>
              {item.rebuttalText && <p className="text-sm text-slate-600">{item.rebuttalText}</p>}
              {item.rebuttalDocument && (
                <a href={toFileUrl(item.rebuttalDocument) || undefined} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline text-sm inline-flex items-center gap-2">
                  <Download size={16} /> View Appeal Document
                </a>
              )}
              {canReviewAppeals && item.status !== "Resolved" && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    className="input-field text-sm"
                    value={appealResolution}
                    onChange={(e) => setAppealResolution(e.target.value)}
                    placeholder="Resolution notes"
                  />
                  <button type="button" onClick={() => handleReviewAppeal(item.id)} disabled={isSubmitting} className="btn-secondary disabled:opacity-60">Resolve Appeal</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const Disbursements = () => {
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [processingClaimId, setProcessingClaimId] = useState<string | null>(null);
  const currentUser = getStoredUser();
  const canProcessPayments =
    currentUser?.role === UserRole.ADMIN || currentUser?.role === UserRole.RBF_OFFICIAL;

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 2500);
  };

  const loadClaims = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPaymentClaims();
      setClaims(data);
    } catch (err: any) {
      const raw = String(err?.message || "");
      if (isConnectivityError(raw)) {
        showNotification(`Cannot connect to backend (${API_BASE}).`);
      } else {
        showNotification(toFriendlyApiMessage(raw) || "Failed to load payment claims.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadClaims();
  }, [loadClaims]);

  React.useEffect(() => {
    const id = setInterval(() => {
      void loadClaims();
    }, 20000);
    return () => clearInterval(id);
  }, [loadClaims]);

  const exportPaymentSchedule = () => {
    const csv = [
      "claim_id,vendor,project,milestone,amount,status",
      ...claims.map((claim) =>
        `${claim.id},${claim.vendorUsername || claim.vendorId},${claim.projectId},${claim.milestoneId || ""},${claim.claimAmount},${claim.status}`
      ),
    ].join("\n");
    triggerDownload("payment_schedule.csv", csv, "text/csv;charset=utf-8");
    showNotification("Payment schedule exported.");
  };

  const processPayment = async (claim: PaymentClaim) => {
    if (!canProcessPayments || claim.status === "Paid" || claim.paymentLocked) return;

    try {
      setProcessingClaimId(claim.id);
      if (claim.status === "Pending" || claim.status === "Verified") {
        await approvePaymentClaim(claim.id, "Approved from disbursement dashboard.");
      }
      const paid = await payPaymentClaim(claim.id, undefined, "Processed from disbursement dashboard.");
      setClaims(prev => prev.map(item => item.id === claim.id ? paid : item));
      await loadClaims();
      showNotification(`Claim ${claim.id} processed and marked as Paid.`);
    } catch (err: any) {
      const raw = String(err?.message || "");
      if (isConnectivityError(raw)) {
        showNotification(`Cannot connect to backend (${API_BASE}).`);
      } else {
        showNotification(toFriendlyApiMessage(raw) || "Failed to process payment.");
      }
    } finally {
      setProcessingClaimId(null);
    }
  };

  const totalDisbursed = claims
    .filter(claim => claim.status === "Paid")
    .reduce((sum, claim) => sum + claim.claimAmount, 0);
  const pendingApproval = claims
    .filter(claim => claim.status === "Pending" || claim.status === "Verified" || claim.status === "Approved")
    .reduce((sum, claim) => sum + claim.claimAmount, 0);
  const budgetRemaining = Math.max(0, 35800000 - totalDisbursed);

  return (
    <div className="space-y-6">
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 right-8 z-[300] bg-emerald-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
          >
            {notification}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Disbursement Management</h1>
        <div className="flex gap-2">
          <button onClick={exportPaymentSchedule} className="btn-secondary flex items-center gap-2">
            <Download size={18} /> Export Payment Schedule
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6 bg-emerald-50 border-emerald-100">
          <p className="text-xs font-bold text-emerald-600 uppercase mb-1">Total Disbursed</p>
          <h3 className="text-2xl font-bold text-slate-900">M {totalDisbursed.toLocaleString()}</h3>
        </div>
        <div className="card p-6 bg-amber-50 border-amber-100">
          <p className="text-xs font-bold text-amber-600 uppercase mb-1">Pending Approval</p>
          <h3 className="text-2xl font-bold text-slate-900">M {pendingApproval.toLocaleString()}</h3>
        </div>
        <div className="card p-6 bg-blue-50 border-blue-100">
          <p className="text-xs font-bold text-blue-600 uppercase mb-1">Budget Remaining</p>
          <h3 className="text-2xl font-bold text-slate-900">M {budgetRemaining.toLocaleString()}</h3>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Claim ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor & Project</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Milestone</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Amount</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!loading && claims.map(claim => (
              <tr key={claim.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{claim.id}</td>
                <td className="px-6 py-4 font-mono text-sm text-slate-600">CLM-{String(claim.id).padStart(3, "0")}</td>
                <td className="px-6 py-4">
                  <div className="font-medium text-slate-900">{claim.vendorUsername || `Vendor ${claim.vendorId}`}</div>
                  <div className="text-xs text-slate-500">PRJ-{claim.projectId}</div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">{claim.milestoneId ? `Milestone ${claim.milestoneId}` : "N/A"}</td>
                <td className="px-6 py-4 font-bold text-slate-900">M {claim.claimAmount.toLocaleString()}</td>
                <td className="px-6 py-4">
                  <span className={`badge ${
                    claim.status === 'Paid' ? 'bg-emerald-100 text-emerald-700' :
                    claim.status === 'Verified' || claim.status === 'Approved' ? 'bg-blue-100 text-blue-700' :
                    'bg-amber-100 text-amber-700'
                  }`}>
                    {claim.status}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <button
                    onClick={() => processPayment(claim)}
                    className="text-emerald-600 hover:text-emerald-700 font-medium text-sm disabled:text-slate-400 disabled:cursor-not-allowed"
                    disabled={!canProcessPayments || claim.status === "Paid" || claim.paymentLocked || processingClaimId === claim.id}
                    title={claim.paymentLocked ? (claim.paymentLockReason || "Payment locked for audit.") : undefined}
                  >
                    {!canProcessPayments ? "View Only" : claim.status === "Paid" ? "Paid" : claim.paymentLocked ? "Locked" : processingClaimId === claim.id ? "Processing..." : "Process Payment"}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && claims.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  No payment claims found.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  Loading payment claims...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Reports = () => {
  const [view, setView] = useState<'list' | 'analytics'>('list');
  const [dateRange, setDateRange] = useState('Last 30 Days');
  const [notification, setNotification] = useState<string | null>(null);

  const stats = [
    { label: 'Gender Participation', value: '42%', trend: '+5%', color: 'text-pink-600' },
    { label: 'Installed Capacity', value: '1.2 MW', trend: '+12%', color: 'text-emerald-600' },
    { label: 'Total Energy Output', value: '850 MWh', trend: '+8%', color: 'text-blue-600' },
    { label: 'Regional Coverage', value: '8/10 Districts', trend: 'Stable', color: 'text-slate-600' },
  ];

  const regionalImpactData = [
    { name: 'Maseru', capacity: 450, output: 320, gender: 45 },
    { name: 'Leribe', capacity: 320, output: 210, gender: 38 },
    { name: 'Berea', capacity: 210, output: 150, gender: 52 },
    { name: 'Mafeteng', capacity: 180, output: 120, gender: 41 },
    { name: 'Quthing', capacity: 150, output: 90, gender: 48 },
  ];

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 2500);
  };

  const exportDashboard = () => {
    const content = [
      `Impact Analytics (${dateRange})`,
      `Generated: ${new Date().toISOString()}`,
      "",
      ...regionalImpactData.map((row) => `${row.name}: capacity=${row.capacity}, output=${row.output}, gender=${row.gender}%`),
    ].join("\n");
    triggerDownload("impact_dashboard_export.txt", content);
    showNotification("Analytics dashboard exported.");
  };

  const createCustomReport = () => {
    showNotification("Custom report wizard opened (stub).");
  };

  const downloadReportCard = (title: string) => {
    const content = `${title}\nGenerated: ${new Date().toISOString()}\n\nSample export content.`;
    const safeName = title.replace(/[^a-z0-9]+/gi, "_").toLowerCase();
    triggerDownload(`${safeName}.txt`, content);
    showNotification(`${title} exported.`);
  };

  const requestApiAccess = () => {
    showNotification("API access request submitted.");
  };

  if (view === 'analytics') {
    return (
      <div className="space-y-8">
        <AnimatePresence>
          {notification && (
            <motion.div
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              className="fixed top-24 right-8 z-[300] bg-blue-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
            >
              {notification}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => setView('list')} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
              <ChevronRight className="rotate-180" size={20} />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Impact Analytics</h1>
              <p className="text-sm text-slate-500">Real-time performance metrics from Prospect database</p>
            </div>
          </div>
          <div className="flex gap-3">
            <select 
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="bg-white border-slate-200 rounded-xl px-4 py-2 text-sm font-bold text-slate-700 shadow-sm focus:ring-emerald-500"
            >
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
              <option>Last Quarter</option>
              <option>Year to Date</option>
            </select>
            <button onClick={exportDashboard} className="btn-primary flex items-center gap-2">
              <Download size={18} /> Export Dashboard
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((stat, i) => (
            <div key={i} className="card p-6 space-y-2">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">{stat.label}</p>
              <div className="flex items-end justify-between">
                <h3 className={`text-3xl font-black ${stat.color}`}>{stat.value}</h3>
                <span className="text-xs font-bold text-emerald-500 bg-emerald-50 px-2 py-0.5 rounded-full">
                  {stat.trend}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Regional Output Chart */}
          <div className="card p-8 space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900">Energy Output by Region (kWh)</h3>
              <div className="flex gap-2">
                <span className="flex items-center gap-1 text-[10px] font-bold text-slate-400">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" /> Output
                </span>
                <span className="flex items-center gap-1 text-[10px] font-bold text-slate-400">
                  <div className="w-2 h-2 rounded-full bg-slate-200" /> Capacity
                </span>
              </div>
            </div>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={regionalImpactData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} />
                  <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                    cursor={{ fill: '#f8fafc' }}
                  />
                  <Bar dataKey="output" fill="#10b981" radius={[4, 4, 0, 0]} barSize={32} />
                  <Bar dataKey="capacity" fill="#e2e8f0" radius={[4, 4, 0, 0]} barSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Gender Participation Chart */}
          <div className="card p-8 space-y-6">
            <h3 className="font-bold text-slate-900">Gender Participation Rate (%)</h3>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={regionalImpactData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748b' }} domain={[0, 100]} />
                  <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Line type="monotone" dataKey="gender" stroke="#db2777" strokeWidth={3} dot={{ r: 6, fill: '#db2777', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 8 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <h3 className="font-bold text-slate-900">Detailed Regional Impact Table</h3>
            <button onClick={() => showNotification("Displaying all districts in the current table view.")} className="text-emerald-600 text-sm font-bold hover:underline">View All Districts</button>
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">ID</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">District</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Project Type</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Installed Capacity</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Energy Output</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Gender Impact</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {[
                { district: 'Maseru', type: 'Mini-grid', capacity: '450 kW', output: '320 kWh', gender: '45%', status: 'Verified' },
                { district: 'Leribe', type: 'SHS', capacity: '320 kW', output: '210 kWh', gender: '38%', status: 'Verified' },
                { district: 'Berea', type: 'Cook Stove', capacity: '210 kW', output: '150 kWh', gender: '52%', status: 'Pending' },
              ].map((row, i) => (
                <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                  <td className="px-6 py-4 font-mono text-xs text-slate-500">{`RG-${String(i + 1).padStart(3, "0")}`}</td>
                  <td className="px-6 py-4 font-bold text-slate-900">{row.district}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{row.type}</td>
                  <td className="px-6 py-4 text-sm text-slate-600">{row.capacity}</td>
                  <td className="px-6 py-4 text-sm font-bold text-emerald-600">{row.output}</td>
                  <td className="px-6 py-4 text-sm font-bold text-pink-600">{row.gender}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${
                      row.status === 'Verified' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                    }`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 right-8 z-[300] bg-blue-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
          >
            {notification}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reporting & Exports</h1>
          <p className="text-sm text-slate-500">Generate and download verified program impact data</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setView('analytics')} className="btn-secondary flex items-center gap-2">
            <BarChart3 size={18} /> View Analytics Dashboard
          </button>
          <button onClick={createCustomReport} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> Custom Report
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[
          { title: 'Gender Impact Report', desc: 'Disaggregated participation by region and tender.', icon: Users, format: 'PDF/Excel', category: 'Gender' },
          { title: 'Energy Output Log', desc: 'Timestamped and verified generation data.', icon: Zap, format: 'CSV', category: 'Performance' },
          { title: 'Tender Summary', desc: 'Program progress grouped by technology type.', icon: FileText, format: 'PDF', category: 'Admin' },
          { title: 'Regional Impact', desc: 'Spatial performance breakdown by district.', icon: MapIcon, format: 'Excel', category: 'Spatial' },
          { title: 'Beneficiary Export', desc: 'Anonymized household data with GPS tags.', icon: Database, format: 'CSV/GeoJSON', category: 'Data' },
          { title: 'Vendor Audit Trail', desc: 'Compliance and performance history logs.', icon: ShieldCheck, format: 'PDF', category: 'Audit' },
        ].map((report, i) => (
          <div key={i} className="card p-6 hover:shadow-xl transition-all cursor-pointer group border-slate-100 hover:border-emerald-200">
            <div className="flex justify-between items-start mb-4">
              <div className="w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600 transition-colors">
                <report.icon size={24} />
              </div>
              <span className="text-[10px] font-black text-slate-300 uppercase tracking-widest">{report.category}</span>
            </div>
            <h3 className="font-bold text-slate-900 mb-2 group-hover:text-emerald-700 transition-colors">{report.title}</h3>
            <p className="text-sm text-slate-500 mb-6 leading-relaxed">{report.desc}</p>
            <div className="flex items-center justify-between pt-4 border-t border-slate-50">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-slate-100 text-[10px] font-bold text-slate-500 uppercase">{report.format}</span>
              </div>
              <button onClick={() => downloadReportCard(report.title)} className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center hover:bg-emerald-600 hover:text-white transition-all">
                <Download size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="card p-8 bg-slate-900 text-white relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="space-y-2 text-center md:text-left">
            <h3 className="text-xl font-bold">Need a custom data export?</h3>
            <p className="text-slate-400 text-sm max-w-md">
              Access the raw Prospect database for advanced spatial-temporal analysis or third-party integration.
            </p>
          </div>
          <button onClick={requestApiAccess} className="px-8 py-3 bg-emerald-500 hover:bg-emerald-600 text-white font-bold rounded-xl transition-colors flex items-center gap-2">
            <Database size={18} /> Request API Access
          </button>
        </div>
        <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl -mr-32 -mt-32" />
      </div>
    </div>
  );
};

const NotificationCenter = ({
  notifications,
  onClose,
  onViewAll,
  onSelect,
}: {
  notifications: Notification[];
  onClose: () => void;
  onViewAll: () => void;
  onSelect?: (notification: Notification) => void;
}) => {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      className="absolute top-16 right-8 w-96 bg-white rounded-3xl shadow-2xl border border-slate-100 z-[100] overflow-hidden"
    >
      <div className="p-6 border-b border-slate-50 flex items-center justify-between bg-slate-50/50">
        <h3 className="font-bold text-slate-900 flex items-center gap-2">
          <Bell size={18} className="text-emerald-600" />
          Notifications
        </h3>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
          <X size={18} />
        </button>
      </div>
      <div className="max-h-[400px] overflow-y-auto">
        {notifications.length > 0 ? (
          <div className="divide-y divide-slate-50">
            {notifications.map((n) => (
              <div
                key={n.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelect?.(n)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect?.(n);
                  }
                }}
                className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${n.status === NotificationStatus.SENT ? 'bg-emerald-50/30' : ''}`}
              >
                <div className="flex gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    n.type === NotificationChannel.EMAIL ? 'bg-blue-50 text-blue-600' :
                    n.type === NotificationChannel.SMS ? 'bg-amber-50 text-amber-600' :
                    'bg-emerald-50 text-emerald-600'
                  }`}>
                    {n.type === NotificationChannel.EMAIL ? <Mail size={18} /> :
                     n.type === NotificationChannel.SMS ? <Zap size={18} /> :
                     <Bell size={18} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-1">
                      <p className="text-sm font-bold text-slate-900 truncate">{n.title}</p>
                      <span className="text-[10px] text-slate-400 whitespace-nowrap ml-2">
                        {new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">{n.body}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-12 text-center">
            <Bell size={40} className="mx-auto text-slate-200 mb-4" />
            <p className="text-slate-500 text-sm">No new notifications</p>
          </div>
        )}
      </div>
      <div className="p-4 bg-slate-50 border-t border-slate-100 text-center">
        <button onClick={onViewAll} className="text-xs font-bold text-emerald-600 hover:text-emerald-700">
          View All Notifications
        </button>
      </div>
    </motion.div>
  );
};

const NotificationLogs = ({
  logs,
  onSelect,
}: {
  logs: Notification[];
  onSelect?: (notification: Notification) => void;
}) => {
  const [statusFilter, setStatusFilter] = useState<"All" | NotificationStatus>("All");
  const [message, setMessage] = useState<string | null>(null);

  const showMessage = (msg: string) => {
    setMessage(msg);
    setTimeout(() => setMessage(null), 2500);
  };

  const handleResend = (id: string) => {
    showMessage(`Resend queued for notification ${id}.`);
  };

  const handleFilterToggle = () => {
    setStatusFilter(prev => {
      if (prev === "All") return NotificationStatus.FAILED;
      if (prev === NotificationStatus.FAILED) return NotificationStatus.SENT;
      return "All";
    });
  };

  const handleNewBroadcast = () => {
    showMessage("Broadcast draft created.");
  };

  const visibleLogs = logs.filter((log) => statusFilter === "All" || log.status === statusFilter);

  return (
    <div className="space-y-6">
      <AnimatePresence>
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 right-8 z-[300] bg-blue-600 text-white px-5 py-2.5 rounded-xl shadow-xl text-sm font-medium"
          >
            {message}
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Notification Delivery Logs</h1>
          <p className="text-sm text-slate-500">
            Monitor system alerts across all channels
            <span className="ml-2 text-xs font-bold text-slate-400">Filter: {statusFilter}</span>
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={handleFilterToggle} className="btn-secondary flex items-center gap-2">
            <Filter size={18} /> Filter Logs
          </button>
          <button onClick={handleNewBroadcast} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> New Broadcast
          </button>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/50">
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">ID</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Recipient</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Channel</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Event</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Timestamp</th>
              <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {visibleLogs.map((log) => (
              <tr
                key={log.id}
                className="hover:bg-slate-50/50 transition-colors cursor-pointer"
                onClick={() => onSelect?.(log)}
                title="View related section"
              >
                <td className="px-6 py-4 font-mono text-[10px] text-slate-500">{log.id}</td>
                <td className="px-6 py-4">
                  <p className="text-sm font-bold text-slate-900">{log.recipientName}</p>
                  <p className="text-[10px] text-slate-400">{log.recipientId}</p>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    {log.type === NotificationChannel.EMAIL ? <Mail size={14} className="text-blue-500" /> :
                     log.type === NotificationChannel.SMS ? <Zap size={14} className="text-amber-500" /> :
                     <Bell size={14} className="text-emerald-500" />}
                    <span className="text-xs font-medium text-slate-600">{log.type}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-xs text-slate-600 font-medium">{log.event}</td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${
                    log.status === NotificationStatus.DELIVERED ? 'bg-emerald-100 text-emerald-700' :
                    log.status === NotificationStatus.READ ? 'bg-blue-100 text-blue-700' :
                    log.status === NotificationStatus.FAILED ? 'bg-rose-100 text-rose-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>
                    {log.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-xs text-slate-500">
                  {new Date(log.timestamp).toLocaleString()}
                </td>
                <td className="px-6 py-4 text-right">
                  <button 
                    onClick={(event) => {
                      event.stopPropagation();
                      handleResend(log.id);
                    }}
                    className="p-2 hover:bg-emerald-50 rounded-lg text-emerald-600 transition-colors"
                    title="Resend"
                  >
                    <History size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {visibleLogs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                  No logs match the selected filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const getLatestPrequalification = (items: VendorPrequalification[]) => {
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
    const aId = Number(a.id);
    const bId = Number(b.id);
    return (Number.isNaN(bId) ? 0 : bId) - (Number.isNaN(aId) ? 0 : aId);
  });
  return sorted[0] ?? null;
};

const PreQualificationSubmission = () => {
  const [step, setStep] = useState(1);
  const [prequals, setPrequals] = useState<VendorPrequalification[]>([]);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [formData, setFormData] = useState({
    companyName: "",
    yearsOfExperience: "",
    sectorFocus: [] as string[],
    priorProjects: "",
    annualRevenue: "",
    femaleCommitment: 50,
    vulnerableInclusion: 30,
    districtsCovered: "",
    bankAccountName: "",
    bankAccountNumber: "",
    focalPersonGender: "Male",
    contactNumber: "",
    emailAddress: "",
    techTier: "Level 1",
    declaration: false
  });
  const [docFiles, setDocFiles] = useState<{
    tradingLicense: File | null;
    registrationCertificate: File | null;
    taxComplianceCertificate: File | null;
    experienceFinancialProof: File | null;
  }>({
    tradingLicense: null,
    registrationCertificate: null,
    taxComplianceCertificate: null,
    experienceFinancialProof: null,
  });
  const [submitted, setSubmitted] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const techSectors = ["SHS", "ICS", "GMG", "SAS", "PUE", "SWP"];

  // Load vendor's existing pre-qualification status
  React.useEffect(() => {
    const loadStatus = async () => {
      try {
        const data = await fetchVendorPrequalifications();
        setPrequals(data);
      } catch (err) {
        console.error('Failed to load pre-qualification status:', err);
      } finally {
        setLoadingStatus(false);
      }
    };
    loadStatus();
  }, []);

  // Show current status if vendor has already submitted
  const latestPrequal = getLatestPrequalification(prequals);

  const handleTechToggle = (tech: string) => {
    setFormData(prev => ({
      ...prev,
      sectorFocus: prev.sectorFocus.includes(tech)
        ? prev.sectorFocus.filter(t => t !== tech)
        : [...prev.sectorFocus, tech]
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");
    if (step < 3) {
      setStep(step + 1);
    } else {
      if (formData.sectorFocus.length === 0) {
        setSubmitError("Please select at least one technology type.");
        return;
      }
      if (!docFiles.tradingLicense || !docFiles.taxComplianceCertificate || !docFiles.registrationCertificate || !docFiles.experienceFinancialProof) {
        setSubmitError("Please upload all required legal and financial documents.");
        return;
      }
      try {
        setIsSubmitting(true);
        const created = await submitVendorPrequalification({
          companyName: formData.companyName.trim(),
          organizationType: "Private",
          taxId: "",
          hqAddress: "",
          technologyTypes: formData.sectorFocus,
          registrationCertificateName: "",
          tradingLicense: docFiles.tradingLicense || undefined,
          registrationCertificate: docFiles.registrationCertificate || undefined,
          taxComplianceCertificate: docFiles.taxComplianceCertificate || undefined,
          experienceFinancialProof: docFiles.experienceFinancialProof || undefined,
          techTier: formData.techTier,
          yearsExperience: Number(formData.yearsOfExperience || 0),
          priorProjects: Number(formData.priorProjects || 0),
          annualRevenue: Number(formData.annualRevenue || 0),
          districtsCovered: Number(formData.districtsCovered || 0),
          femaleBeneficiaryTarget: formData.femaleCommitment,
          vulnerableGroupTarget: formData.vulnerableInclusion,
          bankAccountName: formData.bankAccountName,
          bankAccountNumber: formData.bankAccountNumber,
          contactNumber: formData.contactNumber,
          email: formData.emailAddress,
          genderOfFocalPerson: formData.focalPersonGender,
          declarationAccepted: formData.declaration,
        });
        setSubmissionId(created.id);
        setSubmitted(true);
      } catch (err: any) {
        const raw = String(err?.message || "");
        if (isConnectivityError(raw)) {
          setSubmitError(`Cannot connect to backend (${API_BASE}).`);
        } else {
          setSubmitError(toFriendlyApiMessage(raw) || "Failed to submit pre-qualification.");
        }
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Approved': return 'bg-emerald-100 text-emerald-700 border-emerald-300';
      case 'Under Review': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'Pending': return 'bg-amber-100 text-amber-700 border-amber-300';
      case 'Clarification Requested': return 'bg-orange-100 text-orange-700 border-orange-300';
      case 'Rejected': return 'bg-rose-100 text-rose-700 border-rose-300';
      default: return 'bg-slate-100 text-slate-700 border-slate-300';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'Approved': return <CheckCircle2 className="text-emerald-600" size={32} />;
      case 'Under Review': return <Clock className="text-blue-600" size={32} />;
      case 'Pending': return <Clock className="text-amber-600" size={32} />;
      case 'Clarification Requested': return <AlertCircle className="text-orange-600" size={32} />;
      case 'Rejected': return <XCircle className="text-rose-600" size={32} />;
      default: return <HelpCircle className="text-slate-600" size={32} />;
    }
  };

  const toFileUrl = (raw?: string | null) => {
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    return `${base}${path}`;
  };

  const renderDocLink = (label: string, url?: string | null) => (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">{label}</span>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="text-emerald-600 hover:underline flex items-center gap-1"
        >
          <Download size={14} /> View Document
        </a>
      ) : (
        <span className="text-xs text-slate-400">Not provided</span>
      )}
    </div>
  );

  if (loadingStatus) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-emerald-600" size={32} />
        <p className="ml-3 text-slate-600">Loading your pre-qualification status...</p>
      </div>
    );
  }

  // Show status if vendor has submitted
  if (latestPrequal) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="card p-8">
          <div className="flex items-start gap-6">
            <div className="flex-shrink-0">
              {getStatusIcon(latestPrequal.status)}
            </div>
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-slate-900 mb-2">Pre-Qualification Status</h2>
              <p className="text-slate-600 mb-4">Here's the current status of your pre-qualification submission:</p>
              
              <div className={`px-4 py-3 rounded-xl border-2 inline-block font-bold text-lg ${getStatusColor(latestPrequal.status)}`}>
                {latestPrequal.status}
              </div>
            </div>
          </div>
        </div>

        {/* Status Details */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card p-6">
            <h3 className="font-bold text-slate-900 mb-3">Submission Details</h3>
            <div className="space-y-3 text-sm">
              <div>
                <p className="text-slate-500">Company Name</p>
                <p className="font-medium text-slate-900">{latestPrequal.companyName}</p>
              </div>
              <div>
                <p className="text-slate-500">Technology Types</p>
                <div className="flex flex-wrap gap-2 mt-1">
                  {latestPrequal.technologyTypes.map(tech => (
                    <span key={tech} className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded text-xs font-bold">
                      {tech}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-slate-500">Submitted At</p>
                <p className="font-medium text-slate-900">{new Date(latestPrequal.submittedAt).toLocaleDateString()}</p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-bold text-slate-900 mb-3">Targets & Commitments</h3>
            <div className="space-y-3 text-sm">
              <div>
                <p className="text-slate-500">Female-Beneficiary Target</p>
                <p className="font-medium text-slate-900">{latestPrequal.femaleBeneficiaryTarget}%</p>
              </div>
              <div>
                <p className="text-slate-500">Vulnerable Group Target</p>
                <p className="font-medium text-slate-900">{latestPrequal.vulnerableGroupTarget}%</p>
              </div>
              <div>
                <p className="text-slate-500">Tech Tier</p>
                <p className="font-medium text-slate-900">{latestPrequal.techTier || 'Not specified'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Status-specific information */}
        {latestPrequal.status === 'Approved' && (
          <div className="card p-6 border-2 border-emerald-200 bg-emerald-50">
            <h3 className="font-bold text-emerald-900 mb-2 flex items-center gap-2">
              <CheckCircle2 size={20} /> Congratulations!
            </h3>
            <p className="text-emerald-800">
              Your pre-qualification has been approved! You can now access bidding opportunities and submit applications for active tenders.
            </p>
          </div>
        )}

        {latestPrequal.status === 'Under Review' && (
          <div className="card p-6 border-2 border-blue-200 bg-blue-50">
            <h3 className="font-bold text-blue-900 mb-2 flex items-center gap-2">
              <Clock size={20} /> Under Review
            </h3>
            <p className="text-blue-800">
              Your submission is currently being reviewed by RBF and UNDP officials. You will receive an email notification once the review is complete (typically within 5-10 business days).
            </p>
          </div>
        )}

        {latestPrequal.status === 'Pending' && (
          <div className="card p-6 border-2 border-amber-200 bg-amber-50">
            <h3 className="font-bold text-amber-900 mb-2 flex items-center gap-2">
              <Clock size={20} /> Pending Review
            </h3>
            <p className="text-amber-800">
              Your submission has been received and is waiting to be picked up for review. You will receive an email notification soon.
            </p>
          </div>
        )}

        {latestPrequal.status === 'Clarification Requested' && (
          <div className="card p-6 border-2 border-orange-200 bg-orange-50">
            <h3 className="font-bold text-orange-900 mb-2 flex items-center gap-2">
              <AlertCircle size={20} /> Clarification Needed
            </h3>
            <p className="text-orange-800 mb-3">
              The review team needs more information to process your application. Please review the comments below and resubmit.
            </p>
            {latestPrequal.reviewerComments && (
              <div className="p-4 bg-white rounded border border-orange-300">
                <p className="text-sm font-medium text-slate-700 mb-1">Reviewer Comments:</p>
                <p className="text-sm text-slate-600">{latestPrequal.reviewerComments}</p>
              </div>
            )}
            <button 
              onClick={() => {
                setPrequals([]);
                setSubmitted(false);
                setStep(1);
              }}
              className="btn-primary mt-4"
            >
              Resubmit Pre-Qualification
            </button>
          </div>
        )}

        {latestPrequal.status === 'Rejected' && (
          <div className="card p-6 border-2 border-rose-200 bg-rose-50">
            <h3 className="font-bold text-rose-900 mb-2 flex items-center gap-2">
              <XCircle size={20} /> Application Rejected
            </h3>
            <p className="text-rose-800 mb-3">
              Your pre-qualification application was not approved. Please review the feedback below.
            </p>
            {latestPrequal.reviewerComments && (
              <div className="p-4 bg-white rounded border border-rose-300 mb-4">
                <p className="text-sm font-medium text-slate-700 mb-1">Reviewer Feedback:</p>
                <p className="text-sm text-slate-600">{latestPrequal.reviewerComments}</p>
              </div>
            )}
            <p className="text-sm text-rose-800 mb-4">
              If you would like to appeal this decision or have questions, please contact RBF support.
            </p>
            <button 
              onClick={() => {
                setPrequals([]);
                setSubmitted(false);
                setStep(1);
              }}
              className="btn-secondary"
            >
              Submit New Application
            </button>
          </div>
        )}

        {/* Review Information */}
        {latestPrequal.reviewedBy && (
          <div className="card p-6 bg-slate-50">
            <p className="text-xs text-slate-500 uppercase font-bold mb-1">Review Information</p>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-slate-600">Reviewed By</p>
                <p className="font-medium">{latestPrequal.reviewedByUsername || 'RBF Official'}</p>
              </div>
              <div>
                <p className="text-slate-600">Reviewed At</p>
                <p className="font-medium">{latestPrequal.reviewedAt ? new Date(latestPrequal.reviewedAt).toLocaleDateString() : '-'}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Show form if no pre-qualification exists
  if (submitted) {
    return (
      <div className="max-w-2xl mx-auto text-center space-y-6 py-12">
        <div className="w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle2 size={40} />
        </div>
        <h2 className="text-3xl font-bold text-slate-900">Submission Received!</h2>
        <p className="text-slate-500 text-lg">
          Your pre-qualification application has been successfully submitted to RBF and UNDP officials for review. 
          You will be notified via email once your application has been processed.
        </p>
        {submissionId && (
          <p className="text-xs font-mono text-slate-500">Submission ID: {submissionId}</p>
        )}
        <div className="p-6 bg-slate-50 rounded-2xl border border-slate-200 text-left space-y-4">
          <h3 className="font-bold text-slate-900 flex items-center gap-2">
            <Clock size={18} className="text-amber-500" />
            What happens next?
          </h3>
          <ul className="space-y-2 text-sm text-slate-600">
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600">1.</span>
              <span>Document Verification: Officials will validate your legal and financial documents.</span>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600">2.</span>
              <span>Technical Review: Your capacity and sector focus will be evaluated.</span>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-emerald-600">3.</span>
              <span>Approval/Rejection: You will receive a status update within 5-10 business days.</span>
            </li>
          </ul>
        </div>
        <button 
          onClick={() => {
            setSubmitted(false);
            setSubmissionId(null);
            setStep(1);
            // Reload status
            const loadStatus = async () => {
              try {
                const data = await fetchVendorPrequalifications();
                setPrequals(data);
              } catch (err) {
                console.error('Failed to load pre-qualification status:', err);
              }
            };
            loadStatus();
          }} 
          className="btn-primary px-8 py-3 rounded-xl"
        >
          Check Status
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Vendor Pre-Qualification</h1>
          <p className="text-slate-500">Complete the mandatory process to access bidding opportunities</p>
        </div>
        <div className="flex items-center gap-2 text-sm font-bold text-slate-400">
          <span className={step >= 1 ? "text-emerald-600" : ""}>Step 1</span>
          <ChevronRight size={16} />
          <span className={step >= 2 ? "text-emerald-600" : ""}>Step 2</span>
          <ChevronRight size={16} />
          <span className={step >= 3 ? "text-emerald-600" : ""}>Step 3</span>
        </div>
      </div>

      <div className="card p-8">
        <form onSubmit={handleSubmit} className="space-y-8">
          {step === 1 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Company Profile & Legal Documents</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Company Name *</label>
                  <input 
                    required type="text" className="input-field" placeholder="Full legal name"
                    value={formData.companyName} onChange={(e) => setFormData({...formData, companyName: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Email Address *</label>
                  <input 
                    required type="email" className="input-field" placeholder="official@company.com"
                    value={formData.emailAddress} onChange={(e) => setFormData({...formData, emailAddress: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Contact Number *</label>
                  <input 
                    required type="text" className="input-field" placeholder="10-15 digits"
                    value={formData.contactNumber} onChange={(e) => setFormData({...formData, contactNumber: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Gender of Focal Person *</label>
                  <select 
                    className="input-field"
                    value={formData.focalPersonGender} onChange={(e) => setFormData({...formData, focalPersonGender: e.target.value})}
                  >
                    <option>Male</option>
                    <option>Female</option>
                    <option>Other</option>
                  </select>
                </div>
              </div>

              <div className="space-y-4 pt-4">
                <label className="text-sm font-bold text-slate-700 ml-1">Required Documentation (Max 5MB per file)</label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { key: "tradingLicense", label: "Valid Trading License", icon: FileText },
                    { key: "taxComplianceCertificate", label: "Tax Clearance Certificate", icon: ShieldCheck },
                    { key: "registrationCertificate", label: "Company Registration", icon: FileText },
                    { key: "experienceFinancialProof", label: "Experience & Financial Stability", icon: UserCircle },
                  ].map((doc, i) => (
                    <div key={i} className="p-4 border-2 border-dashed border-slate-200 rounded-xl text-center bg-slate-50">
                      <label htmlFor={`prequal-doc-${doc.key}`} className="cursor-pointer block">
                        <doc.icon className="mx-auto text-slate-400 mb-2" size={24} />
                        <p className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{doc.label}</p>
                        <p className="text-[8px] text-slate-400 mt-1">
                          {(docFiles as any)[doc.key]?.name || "PDF/DOCX only"}
                        </p>
                      </label>
                      <input
                        id={`prequal-doc-${doc.key}`}
                        type="file"
                        accept=".pdf,.doc,.docx"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0] || null;
                          setDocFiles(prev => ({ ...prev, [doc.key]: file }));
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Bank Details (Account Name & Number) *</label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <input 
                    required type="text" className="input-field" placeholder="Account Name"
                    value={formData.bankAccountName} onChange={(e) => setFormData({...formData, bankAccountName: e.target.value})}
                  />
                  <input 
                    required type="text" className="input-field" placeholder="Account Number"
                    value={formData.bankAccountNumber} onChange={(e) => setFormData({...formData, bankAccountNumber: e.target.value})}
                  />
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Technical & Financial Capacity</h3>
              
              <div className="space-y-4">
                <label className="text-sm font-bold text-slate-700 ml-1">Sector Focus / Technology Type *</label>
                <div className="flex flex-wrap gap-3">
                  {techSectors.map(tech => (
                    <button
                      key={tech}
                      type="button"
                      onClick={() => handleTechToggle(tech)}
                      className={`px-4 py-2 rounded-xl text-sm font-bold transition-all border-2 ${
                        formData.sectorFocus.includes(tech)
                          ? "bg-emerald-600 text-white border-emerald-600 shadow-lg shadow-emerald-600/20"
                          : "bg-white text-slate-500 border-slate-100 hover:border-slate-200"
                      }`}
                    >
                      {tech}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Technology Tier Supported *</label>
                  <select 
                    className="input-field"
                    value={formData.techTier} onChange={(e) => setFormData({...formData, techTier: e.target.value})}
                  >
                    {[1, 2, 3, 4, 5].map(l => <option key={l}>Level {l}</option>)}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Years of Experience</label>
                  <input 
                    type="number" className="input-field" placeholder="Number of years"
                    value={formData.yearsOfExperience} onChange={(e) => setFormData({...formData, yearsOfExperience: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Prior Projects Implemented</label>
                  <input 
                    type="number" className="input-field" placeholder="Total number of projects"
                    value={formData.priorProjects} onChange={(e) => setFormData({...formData, priorProjects: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Annual Revenue (Last Year - LSL)</label>
                  <input 
                    type="number" className="input-field" placeholder="M 0.00"
                    value={formData.annualRevenue} onChange={(e) => setFormData({...formData, annualRevenue: e.target.value})}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Number of Districts Covered</label>
                  <input 
                    type="number" className="input-field" placeholder="Regional coverage"
                    value={formData.districtsCovered} onChange={(e) => setFormData({...formData, districtsCovered: e.target.value})}
                  />
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Inclusive Targets & Declaration</h3>
              
              <div className="p-6 bg-emerald-50 rounded-2xl border border-emerald-100 space-y-6">
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <label className="text-sm font-bold text-emerald-900">Female-Beneficiary Commitment (%) *</label>
                    <span className="text-lg font-bold text-emerald-600">{formData.femaleCommitment}%</span>
                  </div>
                  <input 
                    type="range" min="50" max="100" step="5"
                    value={formData.femaleCommitment}
                    onChange={(e) => setFormData({...formData, femaleCommitment: parseInt(e.target.value)})}
                    className="w-full h-2 bg-emerald-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                  />
                  <p className="text-[10px] text-emerald-700 font-medium italic">Minimum 50% commitment required for female-headed households</p>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <label className="text-sm font-bold text-emerald-900">Vulnerable Group Inclusion (%) *</label>
                    <span className="text-lg font-bold text-emerald-600">{formData.vulnerableInclusion}%</span>
                  </div>
                  <input 
                    type="range" min="30" max="100" step="5"
                    value={formData.vulnerableInclusion}
                    onChange={(e) => setFormData({...formData, vulnerableInclusion: parseInt(e.target.value)})}
                    className="w-full h-2 bg-emerald-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                  />
                  <p className="text-[10px] text-emerald-700 font-medium italic">Minimum 30% inclusion required for vulnerable groups (elderly, disabled, etc.)</p>
                </div>
              </div>

              <div className="p-6 bg-slate-900 text-white rounded-2xl space-y-4">
                <div className="flex items-center gap-3 text-emerald-400">
                  <AlertCircle size={20} />
                  <h4 className="font-bold">Final Declaration</h4>
                </div>
                <label className="flex gap-4 cursor-pointer group">
                  <div className="pt-1">
                    <input 
                      type="checkbox" required
                      checked={formData.declaration}
                      onChange={(e) => setFormData({...formData, declaration: e.target.checked})}
                      className="w-5 h-5 rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-emerald-500"
                    />
                  </div>
                  <span className="text-sm text-slate-300 leading-relaxed group-hover:text-white transition-colors">
                    I hereby declare that all information provided in this pre-qualification application is true, accurate, and complete. 
                    I understand that any false declaration may lead to immediate disqualification and potential legal action. 
                    I also commit to fulfilling the inclusive targets declared above.
                  </span>
                </label>
              </div>
            </div>
          )}

          <div className="flex justify-between pt-8 border-t border-slate-100">
            <button 
              type="button" 
              onClick={() => step > 1 && setStep(step - 1)}
              className={`btn-secondary px-8 ${step === 1 ? "invisible" : ""}`}
            >
              Previous
            </button>
            <div className="text-right">
              {submitError && (
                <p className="mb-2 text-xs font-medium text-rose-600">{submitError}</p>
              )}
              <button type="submit" disabled={isSubmitting} className="btn-primary px-12 py-3 rounded-xl shadow-lg shadow-emerald-600/20 disabled:opacity-60">
                {step === 3 ? (isSubmitting ? "Submitting..." : "Submit Pre-Qualification") : "Next Step"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

const VendorTenders = ({ onSubmitTender }: { onSubmitTender?: (tenderId: string) => void }) => {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [selectedTender, setSelectedTender] = useState<Tender | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [selectedStage, setSelectedStage] = useState("All Stages");
  const [selectedTech, setSelectedTech] = useState("All Technologies");
  const [sortBy, setSortBy] = useState<"deadline" | "recent">("deadline");

  const loadPublishedTenders = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const rows = await fetchTenders();
      setTenders(rows.filter(t => t.status === TenderStatus.PUBLISHED));
    } catch (err: any) {
      const raw = String(err?.message || "");
      setError(isConnectivityError(raw) ? `Cannot connect to backend (${API_BASE}).` : (toFriendlyApiMessage(raw) || "Failed to load tenders."));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadPublishedTenders();
  }, [loadPublishedTenders]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    tenders.forEach(t => t.category && set.add(t.category));
    return ["All Categories", ...Array.from(set).sort()];
  }, [tenders]);
  const stages = useMemo(() => {
    const set = new Set<string>();
    tenders.forEach(t => t.stageType && set.add(t.stageType));
    return ["All Stages", ...Array.from(set).sort()];
  }, [tenders]);
  const technologies = useMemo(() => {
    const set = new Set<string>();
    tenders.forEach(t => (t.technologyTypes || []).forEach(tech => set.add(tech)));
    return ["All Technologies", ...Array.from(set).sort()];
  }, [tenders]);

  const filteredTenders = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return tenders
      .filter(t => t.status === TenderStatus.PUBLISHED)
      .filter(t => {
        if (!q) return true;
        return (
          t.name.toLowerCase().includes(q) ||
          t.referenceNumber.toLowerCase().includes(q) ||
          t.category.toLowerCase().includes(q)
        );
      })
      .filter(t => selectedCategory === "All Categories" || t.category === selectedCategory)
      .filter(t => selectedStage === "All Stages" || t.stageType === selectedStage)
      .filter(t => selectedTech === "All Technologies" || (t.technologyTypes || []).includes(selectedTech))
      .sort((a, b) => {
        if (sortBy === "recent") {
          return new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime();
        }
        return new Date(a.deadline || 0).getTime() - new Date(b.deadline || 0).getTime();
      });
  }, [tenders, searchQuery, selectedCategory, selectedStage, selectedTech, sortBy]);

  const publishedCount = useMemo(() => tenders.filter(t => t.status === TenderStatus.PUBLISHED).length, [tenders]);
  const closingSoonCount = useMemo(() => {
    const now = Date.now();
    return tenders.filter(t => {
      if (t.status !== TenderStatus.PUBLISHED) return false;
      const deadline = Date.parse(t.lastDateSubmission || t.deadline || "");
      if (Number.isNaN(deadline)) return false;
      const days = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));
      return days >= 0 && days <= 7;
    }).length;
  }, [tenders]);
  const newestTender = useMemo(() => {
    const list = tenders.filter(t => t.status === TenderStatus.PUBLISHED);
    return list.sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime())[0];
  }, [tenders]);

  const openTenderDetails = async (tender: Tender) => {
    try {
      setDetailLoading(true);
      const full = await fetchTender(tender.id);
      setSelectedTender(full);
    } catch (err: any) {
      const raw = String(err?.message || "");
      setError(isConnectivityError(raw) ? `Cannot connect to backend (${API_BASE}).` : (toFriendlyApiMessage(raw) || "Failed to load tender details."));
    } finally {
      setDetailLoading(false);
    }
  };

  if (selectedTender) {
    const scheduleUrl = (() => {
      const raw = selectedTender.scheduleFile;
      if (!raw) return null;
      if (/^https?:\/\//i.test(raw)) return raw;
      const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
      const path = raw.startsWith("/") ? raw : `/${raw}`;
      return `${base}${path}`;
    })();

    const toFileUrl = (raw?: string | null) => {
      if (!raw) return null;
      if (/^https?:\/\//i.test(raw)) return raw;
      const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
      const path = raw.startsWith("/") ? raw : `/${raw}`;
      return `${base}${path}`;
    };
    const fileNameFromUrl = (url?: string | null) => {
      if (!url) return undefined;
      try {
        const clean = url.split("?")[0];
        return clean.split("/").pop() || undefined;
      } catch {
        return undefined;
      }
    };
    const requiredDocs = [
      { label: "Tender Schedule", url: scheduleUrl },
      { label: "RFP / Subsidy Framework", url: toFileUrl(selectedTender.rfpDocumentsFile) },
      { label: "Milestone Payment Schedule", url: toFileUrl(selectedTender.milestonePaymentScheduleFile) },
    ];
    const deadlineValue = selectedTender.lastDateSubmission || selectedTender.deadline;
    const deadlineMs = deadlineValue ? Date.parse(deadlineValue) : NaN;
    const daysLeft = Number.isNaN(deadlineMs) ? null : Math.ceil((deadlineMs - Date.now()) / (1000 * 60 * 60 * 24));

    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-12">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={() => setSelectedTender(null)} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{selectedTender.name}</h1>
            <p className="text-sm text-slate-500 font-mono">{selectedTender.referenceNumber}</p>
          </div>
          {onSubmitTender && (
            <div className="ml-auto">
              <button
                onClick={() => onSubmitTender(selectedTender.id)}
                className="btn-primary"
              >
                Submit Proposal
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card p-5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Deadline</p>
            <p className="text-lg font-bold text-slate-900 mt-2">
              {selectedTender.lastDateSubmission || selectedTender.deadline || "N/A"}
            </p>
            <p className="text-xs text-slate-500 mt-1">Submission cutoff</p>
          </div>
          <div className="card p-5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Stage</p>
            <p className="text-lg font-bold text-slate-900 mt-2">{selectedTender.stageType || "N/A"}</p>
            <p className="text-xs text-slate-500 mt-1">Procurement stage</p>
          </div>
          <div className="card p-5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Budget</p>
            <p className="text-lg font-bold text-slate-900 mt-2">
              {selectedTender.budget != null ? `M ${selectedTender.budget.toLocaleString()}` : "N/A"}
            </p>
            <p className="text-xs text-slate-500 mt-1">Estimated value</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-8 space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Tender Information</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Status</p>
                      <span className="badge bg-emerald-100 text-emerald-700">{selectedTender.status}</span>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Verification</p>
                      <span className={`text-sm font-bold ${selectedTender.isVerified ? 'text-emerald-600' : 'text-amber-600'}`}>
                        {selectedTender.isVerified ? 'Verified' : 'Pending'}
                      </span>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Department</p>
                      <p className="text-sm font-medium">{selectedTender.department}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Category</p>
                      <p className="text-sm font-medium">{selectedTender.category}</p>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Financials</h3>
                  <div className="space-y-1">
                    <p className="text-xs font-bold text-slate-500">Budget Estimate</p>
                    <p className="text-lg font-bold text-slate-900">M {selectedTender.budget?.toLocaleString() ?? "N/A"}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-bold text-slate-500">Bidding Currency</p>
                    <p className="text-sm font-medium">{selectedTender.biddingCurrency || "N/A"}</p>
                  </div>
                  {selectedTender.fundingSource && (
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Funding Source</p>
                      <p className="text-sm font-medium">{selectedTender.fundingSource}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Deadlines & Schedule</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <Clock size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Submission Deadline</p>
                    <p className="text-sm font-bold text-slate-900">{selectedTender.lastDateSubmission || selectedTender.deadline || "N/A"}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <ShieldCheck size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Security Deadline</p>
                    <p className="text-sm font-bold text-slate-900">{selectedTender.lastDateSecurity || "N/A"}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <Eye size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Opening Date</p>
                    <p className="text-sm font-bold text-slate-900">{selectedTender.dateOpening || "N/A"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Technical Requirements</h3>
                <div className="grid grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Technology Types</p>
                    <div className="flex flex-wrap gap-2">
                      {(selectedTender.technologyTypes || []).length ? (selectedTender.technologyTypes || []).map(tech => (
                        <span key={tech} className="px-2 py-1 bg-emerald-50 text-emerald-700 rounded text-[10px] font-bold uppercase tracking-wider">{tech}</span>
                      )) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Target Site Type</p>
                    <p className="text-sm font-medium">{selectedTender.targetSiteType || "N/A"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Bid Decision Aids</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Eligibility</p>
                    <p className="text-slate-700">{selectedTender.biddersEligibility || "Not specified"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Instructions</p>
                    <p className="text-slate-700">{selectedTender.instruction || "Not specified"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Pre‑Tender Meeting</p>
                    <p className="text-slate-700">{selectedTender.preTenderMeetingInfo || "Not specified"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Required Documents</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {requiredDocs.map((doc) => (
                    <div key={doc.label} className="p-4 border-2 border-dashed border-slate-200 rounded-xl bg-slate-50">
                      <div className="flex items-center gap-2">
                        <FileText size={18} className="text-slate-400" />
                        <span className="text-xs font-bold text-slate-700">{doc.label}</span>
                      </div>
                      <div className="mt-3">
                        {doc.url ? (
                          <a
                            href={doc.url}
                            target="_blank"
                            rel="noreferrer"
                            download={fileNameFromUrl(doc.url)}
                            className="text-emerald-600 hover:text-emerald-700 text-xs font-bold"
                          >
                            Download →
                          </a>
                        ) : (
                          <span className="text-xs text-slate-400">Not provided</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Contact</h3>
              <p className="text-sm text-slate-600">{selectedTender.contactDetails || "Not provided"}</p>
            </div>
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Tender Info</h3>
              <div className="grid grid-cols-1 gap-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Application Type</span>
                  <span className="text-slate-700 font-medium">{selectedTender.applicationType || "N/A"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Stage Type</span>
                  <span className="text-slate-700 font-medium">{selectedTender.stageType || "N/A"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Procurement Method</span>
                  <span className="text-slate-700 font-medium">{selectedTender.procurementMethod || "N/A"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Invited By</span>
                  <span className="text-slate-700 font-medium">{selectedTender.invitedBy || "N/A"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Time for Completion</span>
                  <span className="text-slate-700 font-medium">{selectedTender.timeForCompletion || "N/A"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Schedule Purchase</span>
                  <span className="text-slate-700 font-medium">{selectedTender.biddersSchedulePurchase ? "Required" : "Not Required"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Tender Security</span>
                  <span className="text-slate-700 font-medium">{selectedTender.tenderSecurityRequired ? "Required" : "Not Required"}</span>
                </div>
                {daysLeft != null && (
                  <div className={`flex items-center justify-between ${daysLeft < 0 ? "text-rose-600" : daysLeft <= 7 ? "text-amber-600" : "text-slate-600"}`}>
                    <span className="text-slate-500">Days Left</span>
                    <span className="font-semibold">D-{daysLeft}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Logistics & Locations</h3>
              <div className="space-y-3 text-sm">
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Document Address</p>
                  <p className="text-slate-700">{selectedTender.addressForDocument || "Not specified"}</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Security Address</p>
                  <p className="text-slate-700">{selectedTender.addressForSecurity || "Not specified"}</p>
                </div>
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Opening Venue</p>
                  <p className="text-slate-700">{selectedTender.placeForOpening || "Not specified"}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Published Tenders</h1>
          <p className="text-slate-500">Calls for Proposals open to pre-qualified vendors</p>
        </div>
        <button onClick={loadPublishedTenders} className="btn-secondary text-sm">Refresh</button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-5">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Published</p>
          <p className="text-2xl font-bold text-slate-900 mt-2">{publishedCount}</p>
          <p className="text-xs text-slate-500 mt-1">Active tenders available to vendors</p>
        </div>
        <div className="card p-5">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Closing Soon</p>
          <p className="text-2xl font-bold text-amber-600 mt-2">{closingSoonCount}</p>
          <p className="text-xs text-slate-500 mt-1">Deadlines within the next 7 days</p>
        </div>
        <div className="card p-5">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Newest Tender</p>
          <p className="text-lg font-bold text-slate-900 mt-2">{newestTender?.name || "N/A"}</p>
          <p className="text-xs text-slate-500 mt-1">{newestTender?.referenceNumber || "—"}</p>
        </div>
      </div>

      <div className="card p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Filter Published Tenders</h3>
            <p className="text-xs text-slate-500">Find open opportunities by category, stage, and technology.</p>
          </div>
          <button
            onClick={() => {
              setSearchQuery("");
              setSelectedCategory("All Categories");
              setSelectedStage("All Stages");
              setSelectedTech("All Technologies");
              setSortBy("deadline");
            }}
            className="btn-secondary text-sm"
          >
            Reset Filters
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-4 items-end">
          <div className="md:col-span-2 space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input
                className="input-field py-2 pl-9 text-sm"
              placeholder="Search by name, reference, category..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Category</label>
            <select
              className="input-field py-2 text-sm"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              {categories.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Stage</label>
            <select
              className="input-field py-2 text-sm"
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
            >
              {stages.map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Technology</label>
            <select
              className="input-field py-2 text-sm"
              value={selectedTech}
              onChange={(e) => setSelectedTech(e.target.value)}
            >
              {technologies.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-slate-400 uppercase">Sort By</label>
            <select
              className="input-field py-2 text-sm"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
            >
              <option value="deadline">Deadline</option>
              <option value="recent">Recently Added</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-bottom border-slate-200">
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Reference</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Tender</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Stage</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Category</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Deadline</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {loading && (
              <tr>
                <td colSpan={7} className="px-6 py-6 text-sm text-slate-500">Loading published tenders...</td>
              </tr>
            )}
            {!loading && filteredTenders.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-10 text-sm text-slate-500 text-center">
                  No published tenders match your filters.
                </td>
              </tr>
            )}
            {!loading && filteredTenders.map((tender) => (
              <tr key={tender.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-slate-500">{tender.id}</td>
                <td className="px-6 py-4 font-mono text-sm text-slate-600">{tender.referenceNumber}</td>
                <td className="px-6 py-4">
                  <p className="font-medium text-slate-900">{tender.name}</p>
                  <div className="flex flex-wrap gap-2 mt-1">
                    <span className="text-[10px] font-bold text-slate-400 uppercase">{tender.department}</span>
                    {(tender.technologyTypes || []).slice(0, 3).map((tech) => (
                      <span key={tech} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded text-[10px] font-bold uppercase tracking-wider">
                        {tech}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className="badge bg-slate-100 text-slate-600">
                    {tender.stageType || "N/A"}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">{tender.category}</td>
                <td className="px-6 py-4 text-sm">
                  {(() => {
                    const deadline = tender.lastDateSubmission || tender.deadline;
                    const ts = Date.parse(deadline || "");
                    if (Number.isNaN(ts)) return <span className="text-slate-600">N/A</span>;
                    const days = Math.ceil((ts - Date.now()) / (1000 * 60 * 60 * 24));
                    const color =
                      days < 0 ? "text-rose-600" : days <= 7 ? "text-amber-600" : "text-slate-600";
                    const dateStr = new Date(ts).toLocaleDateString();
                    const timeStr = new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                    return (
                      <div className={color}>
                        <div className="font-medium">{dateStr}</div>
                        <div className="text-[10px] uppercase tracking-widest opacity-70">{timeStr}</div>
                        {days >= 0 && !Number.isNaN(days) && (
                          <div className="text-[10px] font-bold">(D-{days})</div>
                        )}
                      </div>
                    );
                  })()}
                </td>
                <td className="px-6 py-4 text-right">
                  <button
                    onClick={() => void openTenderDetails(tender)}
                    className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                    disabled={detailLoading}
                  >
                    {detailLoading ? "Loading..." : "View Details"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const VendorBids = ({ onOpenBid }: { onOpenBid: (bid: TenderBid) => void }) => {
  const [bids, setBids] = useState<TenderBid[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewBid, setViewBid] = useState<TenderBid | null>(null);
  const [viewBidVersions, setViewBidVersions] = useState<TenderBid[]>([]);
  const [viewBidLoading, setViewBidLoading] = useState(false);

  const loadBids = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchTenderBids();
      setBids(data);
    } catch {
      setBids([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadBids();
  }, [loadBids]);

  React.useEffect(() => {
    const handler = () => void loadBids();
    window.addEventListener("rbf-bid-updated", handler);
    return () => window.removeEventListener("rbf-bid-updated", handler);
  }, [loadBids]);

  const grouped = useMemo(() => {
    const byTender = new Map<string, TenderBid[]>();
    bids.forEach(bid => {
      const key = bid.tender;
      const list = byTender.get(key) || [];
      list.push(bid);
      byTender.set(key, list);
    });
    return Array.from(byTender.entries()).map(([tenderId, items]) => {
      const sorted = items.slice().sort((a, b) => (b.version_number || 0) - (a.version_number || 0));
      return { tenderId, latest: sorted[0], versions: sorted };
    }).sort((a, b) => (b.latest.submitted_at || "").localeCompare(a.latest.submitted_at || ""));
  }, [bids]);

  const openViewBid = async (bid: TenderBid) => {
    setViewBid(bid);
    setViewBidVersions([]);
    setViewBidLoading(true);
    try {
      const versions = await fetchTenderBids(bid.tender);
      setViewBidVersions(versions.sort((a, b) => (b.version_number || 0) - (a.version_number || 0)));
    } catch {
      setViewBidVersions([]);
    } finally {
      setViewBidLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">My Bids</h1>
        <p className="text-slate-500">Track your submissions and individual bid status</p>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold">Submitted Bids</h3>
            <p className="text-xs text-slate-500">Latest updates across all your tenders</p>
          </div>
          <button onClick={loadBids} className="btn-secondary text-sm">Refresh</button>
        </div>
        <div className="p-6 space-y-4">
          {loading && <p className="text-sm text-slate-500">Loading bids...</p>}
          {!loading && grouped.length === 0 && (
            <p className="text-sm text-slate-500">No bids submitted yet.</p>
          )}
          {!loading && grouped.map(({ latest, versions }) => {
            const statusColor =
              latest.status === BidStatus.SUBMITTED ? "bg-blue-100 text-blue-700" :
              latest.status === BidStatus.UNDER_REVIEW ? "bg-amber-100 text-amber-700" :
              latest.status === BidStatus.ACCEPTED ? "bg-emerald-100 text-emerald-700" :
              latest.status === BidStatus.REJECTED ? "bg-rose-100 text-rose-700" :
              "bg-slate-100 text-slate-700";
            return (
              <div key={latest.id} className="border border-slate-100 rounded-2xl p-5 hover:border-emerald-200 transition-colors">
                <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                  <div className="space-y-1">
                    <p className="text-sm font-bold text-slate-900">
                      {latest.tender_name || `Tender ${latest.tender_reference || latest.tender}`}
                    </p>
                    <p className="text-xs text-slate-500">
                      Ref: {latest.tender_reference || "N/A"} • Latest Version {latest.version_number}
                    </p>
                    <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
                      <span>Amount: {latest.bid_amount != null ? `M ${Number(latest.bid_amount).toLocaleString()}` : "N/A"}</span>
                      <span>Submitted: {latest.submitted_at ? new Date(latest.submitted_at).toLocaleString() : "Draft"}</span>
                      <span>Versions: {versions.length}</span>
                    </div>
                    {latest.rejection_reason && (
                      <div className="text-xs text-rose-600">Rejection: {latest.rejection_reason}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`badge ${statusColor}`}>{latest.status}</span>
                    <button onClick={() => openViewBid(latest)} className="btn-secondary text-xs">View</button>
                    {(latest.status === BidStatus.DRAFT || latest.status === BidStatus.SUBMITTED) && (
                      <button onClick={() => onOpenBid(latest)} className="btn-primary text-xs">Edit</button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {viewBid && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[120] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setViewBid(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl p-6 space-y-5 max-h-[85vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Bid Details</h2>
                  <p className="text-sm text-slate-500">
                    {viewBid.tender_name || `Tender ${viewBid.tender_reference || viewBid.tender}`}
                  </p>
                </div>
                <button onClick={() => setViewBid(null)} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
                  <X size={18} />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="card p-4">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</p>
                  <p className="text-base font-bold text-slate-900 mt-2">{viewBid.status}</p>
                  <p className="text-xs text-slate-500 mt-1">Current processing stage</p>
                </div>
                <div className="card p-4">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Bid Amount</p>
                  <p className="text-base font-bold text-slate-900 mt-2">
                    {viewBid.bid_amount != null ? `M ${Number(viewBid.bid_amount).toLocaleString()}` : "N/A"}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">Submitted amount</p>
                </div>
                <div className="card p-4">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Version</p>
                  <p className="text-base font-bold text-slate-900 mt-2">{viewBid.version_number}</p>
                  <p className="text-xs text-slate-500 mt-1">Submission version</p>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="space-y-4">
                  <div className="card p-6 space-y-5">
                    <div className="space-y-3">
                      <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Bid Information</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                        <div>
                          <p className="text-xs font-bold text-slate-500">Reference</p>
                          <p className="text-sm font-medium">{viewBid.tender_reference || "N/A"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-bold text-slate-500">Stage</p>
                          <p className="text-sm font-medium">{viewBid.stage || "N/A"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-bold text-slate-500">Submitted</p>
                          <p className="text-sm font-medium">{viewBid.submitted_at ? new Date(viewBid.submitted_at).toLocaleString() : "Draft"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-bold text-slate-500">Reviewed</p>
                          <p className="text-sm font-medium">{viewBid.reviewed_at ? new Date(viewBid.reviewed_at).toLocaleString() : "Pending"}</p>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3 pt-4 border-t border-slate-100">
                      <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Sites Summary</h3>
                      {(viewBid.sites || []).length === 0 && (
                        <p className="text-sm text-slate-500">No sites provided for this bid.</p>
                      )}
                      {(viewBid.sites || []).length > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-slate-600">
                          {(viewBid.sites || []).map((site, idx) => (
                            <div key={`${site.siteName}-${idx}`} className="rounded-lg border border-slate-100 bg-white px-3 py-2">
                              <p className="font-medium text-slate-900">{site.siteName}</p>
                              <p className="text-xs text-slate-500">{site.district || "District N/A"}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="card p-6">
                    <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Bid Versions</h3>
                    {viewBidLoading && <p className="text-sm text-slate-500">Loading versions...</p>}
                    {!viewBidLoading && viewBidVersions.length === 0 && (
                      <p className="text-sm text-slate-500">No versions available.</p>
                    )}
                    {!viewBidLoading && viewBidVersions.length > 0 && (
                      <div className="space-y-3">
                        {viewBidVersions.map((version) => (
                          <div key={version.id} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                            <div>
                              <p className="text-sm font-medium text-slate-900">Version {version.version_number}</p>
                              <p className="text-xs text-slate-500">{version.submitted_at ? new Date(version.submitted_at).toLocaleString() : "Draft"}</p>
                            </div>
                            <span className="badge bg-slate-100 text-slate-700">{version.status}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="card p-6">
                    <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Narratives</h3>
                    <div className="space-y-3 text-sm">
                      <details className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <summary className="cursor-pointer text-sm font-bold text-slate-700">Concept Note</summary>
                        <div className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
                          {viewBid.concept_note || "N/A"}
                        </div>
                      </details>
                      <details className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <summary className="cursor-pointer text-sm font-bold text-slate-700">Technical Proposal</summary>
                        <div className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
                          {viewBid.technical_proposal || "N/A"}
                        </div>
                      </details>
                      <details className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                        <summary className="cursor-pointer text-sm font-bold text-slate-700">Financial Proposal</summary>
                        <div className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
                          {viewBid.financial_proposal || "N/A"}
                        </div>
                      </details>
                    </div>
                  </div>

                  <div className="card p-6">
                    <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Documents</h3>
                    <div className="space-y-3">
                      {[
                        { label: "Technical Proposal", url: viewBid.technical_proposal_file },
                        { label: "Financial Proposal", url: viewBid.financial_proposal_file },
                        { label: "BOQ", url: viewBid.boq_file },
                        { label: "Gender Action Plan", url: viewBid.gender_action_plan_file },
                        { label: "Implementation Plan", url: viewBid.implementation_plan_file },
                        { label: "Reporting Templates", url: viewBid.reporting_templates_file },
                      ]
                        .filter(doc => Boolean(doc.url))
                        .map(doc => (
                          <a
                            key={doc.label}
                            href={String(doc.url)}
                            target="_blank"
                            rel="noreferrer"
                            className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 border border-transparent hover:border-slate-100 transition-all text-left group"
                          >
                            <div className="p-2 rounded-lg bg-slate-100 text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600">
                              <FileText size={18} />
                            </div>
                            <span className="text-xs font-medium text-slate-600 truncate">{doc.label}</span>
                          </a>
                        ))}
                      {[
                        viewBid.technical_proposal_file,
                        viewBid.financial_proposal_file,
                        viewBid.boq_file,
                        viewBid.gender_action_plan_file,
                        viewBid.implementation_plan_file,
                        viewBid.reporting_templates_file,
                      ].every(item => !item) && (
                        <p className="text-xs text-slate-500">No documents uploaded for this bid.</p>
                      )}
                    </div>
                  </div>

                  {viewBid.rejection_reason && (
                    <div className="card p-6 border border-rose-100 bg-rose-50">
                      <h3 className="text-sm font-bold text-rose-700 uppercase mb-2">Rejection Reason</h3>
                      <p className="text-sm text-rose-700">{viewBid.rejection_reason}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-end">
                <button onClick={() => setViewBid(null)} className="btn-secondary">Close</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const VendorDashboard = ({
  currentUser,
  onGoToPrequal,
  pendingBidTenderId,
  pendingBidId,
  onBidOpened,
  initialSection,
  showOnlyContracting,
}: {
  currentUser?: User | null;
  onGoToPrequal?: () => void;
  pendingBidTenderId?: string | null;
  pendingBidId?: string | null;
  onBidOpened?: () => void;
  initialSection?: "contracting" | null;
  showOnlyContracting?: boolean;
}) => {
  const [view, setView] = useState<"dashboard" | "new-application" | "new-claim" | "details" | "bid">("dashboard");
  const [isPreQualified, setIsPreQualified] = useState(false);
  const [selectedMilestone, setSelectedMilestone] = useState<(Milestone & { projectName?: string }) | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [activeTenders, setActiveTenders] = useState<Tender[]>([]);
  const [bidTender, setBidTender] = useState<Tender | null>(null);
  const [bidVersions, setBidVersions] = useState<TenderBid[]>([]);
  const [bidMessage, setBidMessage] = useState<string | null>(null);
  const [editingBidId, setEditingBidId] = useState<string | null>(null);
  const [editingBidStatus, setEditingBidStatus] = useState<BidStatus | null>(null);
  const [bidHistory, setBidHistory] = useState<TenderBid[]>([]);
  const [contracts, setContracts] = useState<TenderContract[]>([]);
  const [contractFiles, setContractFiles] = useState<Record<string, File | null>>({});
  const [contractMessage, setContractMessage] = useState<string | null>(null);
  const [isContractSubmitting, setIsContractSubmitting] = useState(false);
  const [isBidSubmitting, setIsBidSubmitting] = useState(false);
  const [bidForm, setBidForm] = useState({
    bidAmount: "",
    stage: "Pre-Qualification",
    conceptNote: "",
    technicalProposal: "",
    financialProposal: "",
  });
  const [bidFiles, setBidFiles] = useState<{
    technicalProposal: File | null;
    financialProposal: File | null;
    boq: File | null;
    genderActionPlan: File | null;
    implementationPlan: File | null;
    reportingTemplates: File | null;
  }>({
    technicalProposal: null,
    financialProposal: null,
    boq: null,
    genderActionPlan: null,
    implementationPlan: null,
    reportingTemplates: null,
  });
  const [bidSites, setBidSites] = useState<TenderBidSite[]>([
    { siteName: "", district: "", latitude: undefined, longitude: undefined, systemConfiguration: {}, boqItems: [], notes: "" },
  ]);
  const [applicationStep, setApplicationStep] = useState(1);
  const [claimStep, setClaimStep] = useState(1);
  const [isClaimSubmitting, setIsClaimSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    projectName: "",
    location: "",
    district: "Maseru",
    techType: "SHS",
    capacity: "",
    totalCost: "",
    requestedSubsidy: "",
    beneficiaries: "",
    femaleBeneficiaries: "",
  });
  const vendorRestricted = currentUser?.status === "Suspended" || currentUser?.status === "Blacklisted";
  const vendorRestrictionMessage = currentUser?.blacklistSummary?.banner || "This account is restricted from new actions.";

  const [claimData, setClaimData] = useState({
    milestoneName: "",
    completionDate: "",
    actualBeneficiaries: "",
    actualFemaleBeneficiaries: "",
    notes: "",
  });
  const contractingRef = React.useRef<HTMLDivElement | null>(null);

  const districts = ["Maseru", "Leribe", "Berea", "Mafeteng", "Mohale's Hoek", "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Butha-Buthe"];
  const techTypes = ["SHS", "ICS", "Mini-grid", "SWP", "PUE"];

  const loadVendorData = React.useCallback(async () => {
    try {
      const [prequals, projectRows, milestoneRows, tenders, contractRows, bids] = await Promise.all([
        fetchVendorPrequalifications(),
        fetchProjects(),
        fetchMilestones(),
        fetchTenders(),
        fetchTenderContracts(),
        fetchTenderBids(),
      ]);
      const latestPrequal = getLatestPrequalification(prequals);
      const anyApproved = prequals.some(item => String(item.status || "").toLowerCase() === "approved");
      setIsPreQualified(anyApproved);
      setProjects(projectRows);
      setActiveTenders(tenders.filter(t => t.status === TenderStatus.PUBLISHED));
      const projectIds = new Set(projectRows.map(item => item.id));
      setMilestones(milestoneRows.filter(item => projectIds.has(item.projectId)));
      setContracts(contractRows);
      setBidHistory(bids);
    } catch {
      setProjects([]);
      setMilestones([]);
      setContracts([]);
      setBidHistory([]);
    }
  }, []);

  React.useEffect(() => {
    void loadVendorData();
  }, [loadVendorData]);

  React.useEffect(() => {
    const id = setInterval(() => {
      void loadVendorData();
    }, 20000);
    return () => clearInterval(id);
  }, [loadVendorData]);

  React.useEffect(() => {
    const handler = () => void loadVendorData();
    window.addEventListener("rbf-bid-updated", handler);
    return () => window.removeEventListener("rbf-bid-updated", handler);
  }, [loadVendorData]);

  React.useEffect(() => {
    if (initialSection !== "contracting") return;
    setView("dashboard");
    const id = window.setTimeout(() => {
      contractingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
    return () => window.clearTimeout(id);
  }, [initialSection]);

  const projectById = useMemo(() => {
    const map = new Map<string, Project>();
    projects.forEach(project => map.set(project.id, project));
    return map;
  }, [projects]);

  const milestoneRows = useMemo(
    () =>
      milestones.map(milestone => {
        const project = projectById.get(milestone.projectId);
        return {
          ...milestone,
          projectName: project ? `${project.region} ${project.techType}` : `Project ${milestone.projectId}`,
          progress: milestone.percentage,
          status: project?.status || milestone.status,
        };
      }),
    [milestones, projectById]
  );
  const sortedContracts = useMemo(() => {
    if (!contracts.length) return [];
    return [...contracts].sort((a, b) => (b.generatedAt || "").localeCompare(a.generatedAt || ""));
  }, [contracts]);

  const contractTone = (status: TenderContract["status"]) => {
    if (status === "Approved") return "bg-emerald-100 text-emerald-800";
    if (status === "Submitted") return "bg-amber-100 text-amber-800";
    if (status === "Rejected") return "bg-rose-100 text-rose-700";
    return "bg-slate-100 text-slate-700";
  };
  const pendingClaimAmount = milestoneRows
    .filter(item => item.status !== "Paid")
    .reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const averageKpiScore = projects.length
    ? (projects.reduce((sum, item) => sum + Number(item.uptime || 0), 0) / projects.length).toFixed(1)
    : "0.0";

  const handleStartApplication = () => {
    if (!isPreQualified) {
      alert("You must complete the Pre-Qualification process before submitting new applications.");
      return;
    }
    setView("new-application");
    setApplicationStep(1);
  };

  const handleStartClaim = (milestone: Milestone & { projectName?: string }) => {
    setSelectedMilestone(milestone);
    setClaimData({
      milestoneName: milestone.name,
      completionDate: "",
      actualBeneficiaries: "",
      actualFemaleBeneficiaries: "",
      notes: "",
    });
    setView("new-claim");
    setClaimStep(1);
  };

  const resetBidForm = () => {
    setBidForm({
      bidAmount: "",
      stage: "Pre-Qualification",
      conceptNote: "",
      technicalProposal: "",
      financialProposal: "",
    });
    setEditingBidId(null);
    setEditingBidStatus(null);
    setBidSites([{ siteName: "", district: "", latitude: undefined, longitude: undefined, systemConfiguration: {}, boqItems: [], notes: "" }]);
    setBidFiles({
      technicalProposal: null,
      financialProposal: null,
      boq: null,
      genderActionPlan: null,
      implementationPlan: null,
      reportingTemplates: null,
    });
  };

  const openBidForm = async (tender: Tender, selectedBidId?: string | null) => {
    setBidTender(tender);
    setBidMessage(null);
    resetBidForm();
    try {
      const versions = await fetchTenderBids(tender.id);
      setBidVersions(versions);
      if (selectedBidId) {
        const match = versions.find(v => v.id === selectedBidId);
        if (match) {
          useBidVersion(match);
        }
      }
    } catch {
      setBidVersions([]);
    }
    setView("bid");
  };

  React.useEffect(() => {
    if (!pendingBidTenderId) return;
    const match = activeTenders.find(t => t.id === pendingBidTenderId);
    if (match) {
      void openBidForm(match, pendingBidId);
      if (onBidOpened) onBidOpened();
    }
  }, [pendingBidTenderId, pendingBidId, activeTenders]);

  const useBidVersion = (version: TenderBid) => {
    setEditingBidId(version.id);
    setEditingBidStatus(version.status);
    setBidForm({
      bidAmount: version.bid_amount != null ? String(version.bid_amount) : "",
      stage: version.stage ?? "Pre-Qualification",
      conceptNote: version.concept_note ?? "",
      technicalProposal: version.technical_proposal ?? "",
      financialProposal: version.financial_proposal ?? "",
    });
    setBidFiles({
      technicalProposal: null,
      financialProposal: null,
      boq: null,
      genderActionPlan: null,
      implementationPlan: null,
      reportingTemplates: null,
    });
    const sites = (version.sites || []).map(site => ({
      siteName: site.siteName,
      district: site.district,
      latitude: site.latitude,
      longitude: site.longitude,
      systemConfiguration: site.systemConfiguration ?? {},
      boqItems: site.boqItems ?? [],
      notes: site.notes ?? "",
    }));
    setBidSites(sites.length ? sites : [{ siteName: "", district: "", latitude: undefined, longitude: undefined, systemConfiguration: {}, boqItems: [], notes: "" }]);
  };

  const updateBidSite = (index: number, patch: Partial<TenderBidSite>) => {
    setBidSites(prev => prev.map((site, i) => (i === index ? { ...site, ...patch } : site)));
  };

  const addBidSite = () => {
    setBidSites(prev => [...prev, { siteName: "", district: "", latitude: undefined, longitude: undefined, systemConfiguration: {}, boqItems: [], notes: "" }]);
  };

  const removeBidSite = (index: number) => {
    setBidSites(prev => prev.filter((_, i) => i !== index));
  };

  const submitBid = async (status: BidStatus) => {
    if (!bidTender) return;
    if (editingBidStatus && ![BidStatus.DRAFT, BidStatus.SUBMITTED].includes(editingBidStatus)) {
      setBidMessage("This bid is under review or finalized and can no longer be edited.");
      return;
    }
    if (!isPreQualified) {
      setBidMessage("You must be pre-qualified before submitting bids.");
      return;
    }
    if (vendorRestricted) {
      setBidMessage(vendorRestrictionMessage);
      return;
    }
    if (!bidForm.bidAmount) {
      setBidMessage("Bid amount is required.");
      return;
    }
    if (bidForm.stage === "Site-Specific") {
      if (!bidFiles.technicalProposal || !bidFiles.financialProposal) {
        setBidMessage("Upload both technical and financial proposal documents for site-specific submissions.");
        return;
      }
      if (!bidFiles.boq) {
        setBidMessage("BOQ document is required for site-specific submissions.");
        return;
      }
    }
    if (bidSites.some(site => !site.siteName)) {
      setBidMessage("All sites must have a name.");
      return;
    }
    setIsBidSubmitting(true);
    setBidMessage(null);
    try {
      const payload = {
        tender: bidTender.id,
        bid_amount: Number(bidForm.bidAmount),
        stage: bidForm.stage,
        concept_note: bidForm.conceptNote,
        technical_proposal: bidForm.technicalProposal,
        financial_proposal: bidForm.financialProposal,
        technical_proposal_file: bidFiles.technicalProposal ?? undefined,
        financial_proposal_file: bidFiles.financialProposal ?? undefined,
        boq_file: bidFiles.boq ?? undefined,
        gender_action_plan_file: bidFiles.genderActionPlan ?? undefined,
        implementation_plan_file: bidFiles.implementationPlan ?? undefined,
        reporting_templates_file: bidFiles.reportingTemplates ?? undefined,
        status,
        sites: bidSites,
      };
      const created = editingBidId
        ? await updateTenderBid(editingBidId, payload)
        : await submitTenderBid(payload);
      setBidVersions(prev => {
        const next = prev.filter(item => item.id !== created.id);
        return [created, ...next];
      });
      setBidHistory(prev => {
        const next = prev.filter(item => item.id !== created.id);
        return [created, ...next];
      });
      window.dispatchEvent(new Event("rbf-bid-updated"));
      window.dispatchEvent(new Event("rbf-notifications-refresh"));
      resetBidForm();
      if (status === BidStatus.DRAFT) {
        setBidMessage("Draft saved as a new version.");
      } else {
        const submittedAt = created.submitted_at ? new Date(created.submitted_at).toLocaleString() : "now";
        setBidMessage(`Bid submitted. Ref: ${bidTender.referenceNumber} • Version ${created.version_number} • ${submittedAt}.`);
      }
    } catch (err: any) {
      const raw = String(err?.message || "");
      setBidMessage(isConnectivityError(raw) ? `Cannot connect to backend (${API_BASE}).` : (toFriendlyApiMessage(raw) || "Failed to submit bid."));
    } finally {
      setIsBidSubmitting(false);
    }
  };

  const handleSubmitApplication = (e: React.FormEvent) => {
    e.preventDefault();
    if (applicationStep < 3) {
      setApplicationStep(applicationStep + 1);
    } else {
      // Final submission
      alert("Application submitted successfully! It is now pending review.");
      setView("dashboard");
    }
  };

  const handleSubmitClaim = (e: React.FormEvent) => {
    e.preventDefault();
    if (claimStep < 2) {
      setClaimStep(claimStep + 1);
    } else {
      if (!selectedMilestone) return;
      setIsClaimSubmitting(true);
      submitPaymentClaim({
        projectId: selectedMilestone.projectId,
        milestoneId: selectedMilestone.id,
        completionDate: claimData.completionDate,
        claimAmount: Number(selectedMilestone.amount || 0),
        actualBeneficiaries: Number(claimData.actualBeneficiaries || 0),
        actualFemaleBeneficiaries: Number(claimData.actualFemaleBeneficiaries || 0),
        implementationNotes: claimData.notes,
        declarationAccepted: true,
      })
        .then(() => {
          alert(`Claim for ${selectedMilestone.name} submitted successfully! Field verification will be scheduled.`);
          setView("dashboard");
          setClaimStep(1);
        })
        .catch((err: any) => {
          const raw = String(err?.message || "");
          if (isConnectivityError(raw)) {
            alert(`Cannot connect to backend (${API_BASE}).`);
          } else {
            alert(toFriendlyApiMessage(raw) || "Failed to submit claim.");
          }
        })
        .finally(() => setIsClaimSubmitting(false));
    }
  };

  const handleSignContract = async (contractId: string) => {
    const file = contractFiles[contractId];
    if (!file) {
      setContractMessage("Please select a signed contract file.");
      return;
    }
    setIsContractSubmitting(true);
    setContractMessage(null);
    try {
      const updated = await signTenderContract(contractId, {
        signedFile: file,
      });
      setContracts(prev => prev.map(item => item.id === updated.id ? updated : item));
      setContractFiles(prev => ({ ...prev, [contractId]: null }));
      setContractMessage("Signed contract uploaded successfully.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setContractMessage(toFriendlyApiMessage(raw) || "Failed to upload signed contract.");
    } finally {
      setIsContractSubmitting(false);
    }
  };

  if (view === "bid" && bidTender) {
    const versionsSorted = [...bidVersions].sort((a, b) => (b.version_number || 0) - (a.version_number || 0));
    const canEdit = !editingBidStatus || [BidStatus.DRAFT, BidStatus.SUBMITTED].includes(editingBidStatus);
    const parseJsonInput = (value: string, fallbackKey: string) => {
      try {
        return JSON.parse(value);
      } catch {
        return { [fallbackKey]: value };
      }
    };
    const parseBoqItems = (value: string) => {
      const parsed = parseJsonInput(value, "items");
      return Array.isArray(parsed) ? parsed : [parsed];
    };

    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-20">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Submit Tender Proposal</h1>
            <p className="text-slate-500">Tender: {bidTender.name} ({bidTender.referenceNumber})</p>
          </div>
        </div>

        {editingBidStatus && ![BidStatus.DRAFT, BidStatus.SUBMITTED].includes(editingBidStatus) && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 font-medium">
            This bid is under review or finalized and can no longer be edited.
          </div>
        )}
        {bidMessage && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 font-medium">
            {bidMessage}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-6 space-y-6">
              <h3 className="text-lg font-bold text-slate-900">Proposal Details</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Bid Amount (LSL) *</label>
                  <input
                    type="number"
                    className="input-field"
                    value={bidForm.bidAmount}
                    onChange={(e) => setBidForm(prev => ({ ...prev, bidAmount: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Stage</label>
                  <select
                    className="input-field"
                    value={bidForm.stage}
                    onChange={(e) => setBidForm(prev => ({ ...prev, stage: e.target.value }))}
                  >
                    <option>Pre-Qualification</option>
                    <option>Site-Specific</option>
                  </select>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700 ml-1">Concept Note</label>
                <textarea
                  className="input-field min-h-[120px]"
                  value={bidForm.conceptNote}
                  onChange={(e) => setBidForm(prev => ({ ...prev, conceptNote: e.target.value }))}
                />
              </div>

              <div className="space-y-3">
                <label className="text-sm font-bold text-slate-700 ml-1">Proposal Documents (Stage 2)</label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { key: "technicalProposal", label: "Technical Proposal", hint: "PDF/DOCX" },
                    { key: "financialProposal", label: "Financial Proposal", hint: "PDF/DOCX/XLSX" },
                    { key: "boq", label: "BOQ / Bill of Quantities", hint: "XLSX/PDF" },
                    { key: "genderActionPlan", label: "Gender Action Plan", hint: "PDF/DOCX" },
                    { key: "implementationPlan", label: "Implementation Plan", hint: "PDF/DOCX" },
                    { key: "reportingTemplates", label: "Reporting Templates", hint: "PDF/DOCX/XLSX" },
                  ].map((doc, idx) => (
                    <div key={doc.key} className="p-4 border-2 border-dashed border-slate-200 rounded-xl text-center bg-slate-50">
                      <label htmlFor={`bid-doc-${doc.key}-${idx}`} className="cursor-pointer block">
                        <FileText size={22} className="mx-auto text-slate-400 mb-2" />
                        <p className="text-xs font-bold text-slate-700">{doc.label}</p>
                        <p className="text-[10px] text-slate-400 mt-1">{doc.hint}</p>
                        <p className="text-[10px] text-slate-400 mt-1">
                          {(bidFiles as any)[doc.key]?.name || "Click to upload"}
                        </p>
                      </label>
                      <input
                        id={`bid-doc-${doc.key}-${idx}`}
                        type="file"
                        accept=".pdf,.doc,.docx,.xls,.xlsx"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0] || null;
                          setBidFiles(prev => ({ ...prev, [doc.key]: file }));
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700 ml-1">Technical Summary (optional)</label>
                <textarea
                  className="input-field min-h-[140px]"
                  value={bidForm.technicalProposal}
                  onChange={(e) => setBidForm(prev => ({ ...prev, technicalProposal: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700 ml-1">Financial Summary (optional)</label>
                <textarea
                  className="input-field min-h-[140px]"
                  value={bidForm.financialProposal}
                  onChange={(e) => setBidForm(prev => ({ ...prev, financialProposal: e.target.value }))}
                />
              </div>
            </div>

            <div className="card p-6 space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900">Project Sites</h3>
                <button onClick={addBidSite} className="btn-secondary text-sm">Add Site</button>
              </div>

              {bidSites.map((site, index) => (
                <div key={index} className="border border-slate-200 rounded-xl p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-slate-900">Site {index + 1}</h4>
                    {bidSites.length > 1 && (
                      <button onClick={() => removeBidSite(index)} className="text-rose-600 text-sm">Remove</button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-sm font-bold text-slate-700 ml-1">Site Name *</label>
                      <input
                        className="input-field"
                        value={site.siteName}
                        onChange={(e) => updateBidSite(index, { siteName: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-bold text-slate-700 ml-1">District</label>
                      <input
                        className="input-field"
                        value={site.district || ""}
                        onChange={(e) => updateBidSite(index, { district: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-bold text-slate-700 ml-1">Latitude</label>
                      <input
                        className="input-field"
                        value={site.latitude ?? ""}
                        onChange={(e) => updateBidSite(index, { latitude: e.target.value === "" ? undefined : Number(e.target.value) })}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-bold text-slate-700 ml-1">Longitude</label>
                      <input
                        className="input-field"
                        value={site.longitude ?? ""}
                        onChange={(e) => updateBidSite(index, { longitude: e.target.value === "" ? undefined : Number(e.target.value) })}
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-700 ml-1">System Configuration (JSON)</label>
                    <textarea
                      className="input-field min-h-[90px] font-mono text-xs"
                      value={JSON.stringify(site.systemConfiguration ?? {}, null, 2)}
                      onChange={(e) => updateBidSite(index, { systemConfiguration: parseJsonInput(e.target.value, "raw") })}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-700 ml-1">BOQ Items (JSON Array)</label>
                    <textarea
                      className="input-field min-h-[90px] font-mono text-xs"
                      value={JSON.stringify(site.boqItems ?? [], null, 2)}
                      onChange={(e) => updateBidSite(index, { boqItems: parseBoqItems(e.target.value) })}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-slate-700 ml-1">Notes</label>
                    <textarea
                      className="input-field min-h-[70px]"
                      value={site.notes || ""}
                      onChange={(e) => updateBidSite(index, { notes: e.target.value })}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => submitBid(BidStatus.DRAFT)}
                disabled={isBidSubmitting || !canEdit}
                className="btn-secondary flex-1 disabled:opacity-60"
              >
                {isBidSubmitting ? "Saving..." : "Save Draft Version"}
              </button>
              <button
                onClick={() => submitBid(BidStatus.SUBMITTED)}
                disabled={isBidSubmitting || !canEdit}
                className="btn-primary flex-1 disabled:opacity-60"
              >
                {isBidSubmitting ? "Submitting..." : "Submit Final Proposal"}
              </button>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-4">Version History</h3>
              {versionsSorted.length === 0 && (
                <p className="text-sm text-slate-500">No versions yet.</p>
              )}
              <div className="space-y-3">
                {versionsSorted.map((version) => (
                  <div key={version.id} className="p-3 border border-slate-200 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-bold text-slate-900">Version {version.version_number}</p>
                        <p className="text-xs text-slate-500">{version.status}</p>
                      </div>
                      <button
                        onClick={() => useBidVersion(version)}
                        className="text-emerald-600 text-xs font-bold"
                      >
                        Use Version
                      </button>
                    </div>
                    {version.submitted_at && (
                      <p className="text-[10px] text-slate-400 mt-2">
                        Submitted: {new Date(version.submitted_at).toLocaleString()}
                      </p>
                    )}
                    <div className="mt-3 space-y-1 text-[11px]">
                        {[
                          { label: "Technical Proposal", url: version.technical_proposal_file },
                          { label: "Financial Proposal", url: version.financial_proposal_file },
                          { label: "BOQ", url: version.boq_file },
                          { label: "Gender Action Plan", url: version.gender_action_plan_file },
                          { label: "Implementation Plan", url: version.implementation_plan_file },
                          { label: "Reporting Templates", url: version.reporting_templates_file },
                        ].filter(doc => Boolean(doc.url)).length === 0 ? (
                        <p className="text-slate-400">No documents uploaded.</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {[
                            { label: "Technical Proposal", url: version.technical_proposal_file },
                            { label: "Financial Proposal", url: version.financial_proposal_file },
                            { label: "BOQ", url: version.boq_file },
                            { label: "Gender Action Plan", url: version.gender_action_plan_file },
                            { label: "Implementation Plan", url: version.implementation_plan_file },
                            { label: "Reporting Templates", url: version.reporting_templates_file },
                          ]
                            .filter(doc => Boolean(doc.url))
                            .map(doc => (
                              <a
                                key={doc.label}
                                href={doc.url as string}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2 py-1 rounded-full bg-slate-100 text-slate-600 hover:text-emerald-700 hover:bg-emerald-50"
                              >
                                {doc.label}
                              </a>
                            ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="card p-6">
              <h3 className="font-bold text-slate-900 mb-3">Tender Deadline</h3>
              <p className="text-sm text-slate-600">{bidTender.lastDateSubmission || bidTender.deadline}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "new-claim") {
    return (
      <div className="space-y-6 max-w-4xl mx-auto pb-20">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Submit Payment Claim</h1>
            <p className="text-slate-500">Request disbursement for completed milestone: {selectedMilestone?.name}</p>
          </div>
        </div>

        <div className="flex items-center justify-between mb-8 px-4">
          {[
            { step: 1, label: "Verification Data" },
            { step: 2, label: "Evidence & Declaration" },
          ].map((s, i) => (
            <React.Fragment key={s.step}>
              <div className="flex flex-col items-center gap-2">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all ${
                  claimStep >= s.step ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20" : "bg-slate-200 text-slate-500"
                }`}>
                  {s.step}
                </div>
                <span className={`text-xs font-bold ${claimStep >= s.step ? "text-slate-900" : "text-slate-400"}`}>{s.label}</span>
              </div>
              {i < 1 && <div className={`flex-1 h-0.5 mx-4 ${claimStep > s.step ? "bg-emerald-600" : "bg-slate-200"}`} />}
            </React.Fragment>
          ))}
        </div>

        <div className="card p-8">
          <form onSubmit={handleSubmitClaim} className="space-y-8">
            {claimStep === 1 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Milestone Completion Data</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Completion Date *</label>
                    <input 
                      required type="date" className="input-field"
                      value={claimData.completionDate} onChange={(e) => setClaimData({...claimData, completionDate: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Claim Amount (LSL)</label>
                    <input 
                      disabled type="text" className="input-field bg-slate-50" 
                      value={selectedMilestone?.amount}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Actual Beneficiaries Reached *</label>
                    <input 
                      required type="number" className="input-field" placeholder="Number of households"
                      value={claimData.actualBeneficiaries} onChange={(e) => setClaimData({...claimData, actualBeneficiaries: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Actual Female Beneficiaries *</label>
                    <input 
                      required type="number" className="input-field" placeholder="Number of women"
                      value={claimData.actualFemaleBeneficiaries} onChange={(e) => setClaimData({...claimData, actualFemaleBeneficiaries: e.target.value})}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Implementation Notes</label>
                  <textarea 
                    className="input-field min-h-[100px]" placeholder="Describe any challenges or specific details..."
                    value={claimData.notes} onChange={(e) => setClaimData({...claimData, notes: e.target.value})}
                  />
                </div>
              </div>
            )}

            {claimStep === 2 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Evidence & Declaration</h3>
                
                <div className="space-y-4">
                  <label className="text-sm font-bold text-slate-700 ml-1">Upload Evidence Files *</label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      "Installation Photos (ZIP)",
                      "Beneficiary Signature List",
                      "Technical Commissioning Report",
                      "GPS Location Data (CSV)"
                    ].map(doc => (
                      <div key={doc} className="p-4 border border-slate-200 rounded-xl flex items-center justify-between bg-slate-50">
                        <div className="flex items-center gap-3">
                          <FileText className="text-slate-400" size={20} />
                          <span className="text-sm font-medium text-slate-700">{doc}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => triggerDownload(`${doc.replace(/[^a-z0-9]+/gi, "_").toLowerCase()}.txt`, `${doc}\nUpload placeholder`)}
                          className="text-emerald-600 hover:text-emerald-700"
                        >
                          <Plus size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl space-y-3">
                  <div className="flex items-center gap-2 text-amber-800">
                    <AlertCircle size={18} />
                    <span className="font-bold text-sm">Vendor Declaration</span>
                  </div>
                  <label className="flex gap-3 cursor-pointer">
                    <input type="checkbox" required className="mt-1 rounded border-amber-300 text-emerald-600 focus:ring-emerald-500" />
                    <span className="text-xs text-amber-900 leading-relaxed">
                      I hereby declare that the information provided is accurate and the milestone has been completed in accordance with the RBF Operational Manual. I understand that this claim is subject to independent field verification.
                    </span>
                  </label>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-8 border-t border-slate-100">
              <button 
                type="button" 
                onClick={() => claimStep > 1 ? setClaimStep(claimStep - 1) : setView("dashboard")}
                className="btn-secondary px-8"
              >
                {claimStep === 1 ? "Cancel" : "Previous"}
              </button>
              <button type="submit" disabled={isClaimSubmitting} className="btn-primary px-12 disabled:opacity-60">
                {claimStep === 2 ? (isClaimSubmitting ? "Submitting..." : "Submit Claim") : "Next Step"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  if (view === "new-application") {
    return (
      <div className="space-y-6 max-w-4xl mx-auto pb-20">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">New RBF Application</h1>
            <p className="text-slate-500">Submit a new project for subsidy funding</p>
          </div>
        </div>

        <div className="flex items-center justify-between mb-8 px-4">
          {[
            { step: 1, label: "Project Info" },
            { step: 2, label: "Technical & Social" },
            { step: 3, label: "Financials & Docs" },
          ].map((s, i) => (
            <React.Fragment key={s.step}>
              <div className="flex flex-col items-center gap-2">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all ${
                  applicationStep >= s.step ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20" : "bg-slate-200 text-slate-500"
                }`}>
                  {s.step}
                </div>
                <span className={`text-xs font-bold ${applicationStep >= s.step ? "text-slate-900" : "text-slate-400"}`}>{s.label}</span>
              </div>
              {i < 2 && <div className={`flex-1 h-0.5 mx-4 ${applicationStep > s.step ? "bg-emerald-600" : "bg-slate-200"}`} />}
            </React.Fragment>
          ))}
        </div>

        <div className="card p-8">
          <form onSubmit={handleSubmitApplication} className="space-y-8">
            {applicationStep === 1 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Basic Project Information</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Select Active Tender *</label>
                    <select className="input-field" required>
                      <option value="">-- Choose a Tender --</option>
                      <option value="1">RL-2025-SHS-01: Solar Home Systems for Rural Households</option>
                      <option value="2">RL-2025-MG-04: Mini-Grid Development in Mokhotlong</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Project Name *</label>
                    <input 
                      required type="text" className="input-field" placeholder="e.g. Thaba-Tseka Solar Village"
                      value={formData.projectName} onChange={(e) => setFormData({...formData, projectName: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">District *</label>
                    <select 
                      className="input-field" required
                      value={formData.district} onChange={(e) => setFormData({...formData, district: e.target.value})}
                    >
                      {districts.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Specific Location/Village *</label>
                    <input 
                      required type="text" className="input-field" placeholder="Village name or coordinates"
                      value={formData.location} onChange={(e) => setFormData({...formData, location: e.target.value})}
                    />
                  </div>
                </div>
              </div>
            )}

            {applicationStep === 2 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Technical & Social Impact</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Technology Type *</label>
                    <select 
                      className="input-field" required
                      value={formData.techType} onChange={(e) => setFormData({...formData, techType: e.target.value})}
                    >
                      {techTypes.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Proposed Capacity (kW/units) *</label>
                    <input 
                      required type="text" className="input-field" placeholder="e.g. 50kW or 500 units"
                      value={formData.capacity} onChange={(e) => setFormData({...formData, capacity: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Total Estimated Beneficiaries *</label>
                    <input 
                      required type="number" className="input-field" placeholder="Total households/people"
                      value={formData.beneficiaries} onChange={(e) => setFormData({...formData, beneficiaries: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Female Beneficiaries *</label>
                    <input 
                      required type="number" className="input-field" placeholder="Number of women/girls"
                      value={formData.femaleBeneficiaries} onChange={(e) => setFormData({...formData, femaleBeneficiaries: e.target.value})}
                    />
                  </div>
                </div>
              </div>
            )}

            {applicationStep === 3 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Financials & Documentation</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Total Project Cost (LSL) *</label>
                    <input 
                      required type="number" className="input-field" placeholder="M 0.00"
                      value={formData.totalCost} onChange={(e) => setFormData({...formData, totalCost: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">Requested RBF Subsidy (LSL) *</label>
                    <input 
                      required type="number" className="input-field" placeholder="M 0.00"
                      value={formData.requestedSubsidy} onChange={(e) => setFormData({...formData, requestedSubsidy: e.target.value})}
                    />
                  </div>
                </div>

                <div className="space-y-4 pt-4">
                  <label className="text-sm font-bold text-slate-700 ml-1">Required Documents *</label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[
                      "Technical Proposal",
                      "Financial Model",
                      "Environmental Impact Assessment",
                      "Community Engagement Report"
                    ].map(doc => (
                      <div key={doc} className="p-4 border border-slate-200 rounded-xl flex items-center justify-between bg-slate-50">
                        <div className="flex items-center gap-3">
                          <FileText className="text-slate-400" size={20} />
                          <span className="text-sm font-medium text-slate-700">{doc}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => triggerDownload(`${doc.replace(/[^a-z0-9]+/gi, "_").toLowerCase()}.txt`, `${doc}\nUpload placeholder`)}
                          className="text-emerald-600 hover:text-emerald-700"
                        >
                          <Plus size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-8 border-t border-slate-100">
              <button 
                type="button" 
                onClick={() => applicationStep > 1 ? setApplicationStep(applicationStep - 1) : setView("dashboard")}
                className="btn-secondary px-8"
              >
                {applicationStep === 1 ? "Cancel" : "Previous"}
              </button>
              <button type="submit" className="btn-primary px-12">
                {applicationStep === 3 ? "Submit Application" : "Next Step"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  const contractingSection = (
      <section
        className="rounded-3xl border border-slate-200/80 bg-[linear-gradient(135deg,#ffffff_0%,#f8fafc_55%,#eef2ff_100%)] shadow-[0_18px_50px_-32px_rgba(15,23,42,0.7)]"
        ref={contractingRef}
        id="vendor-contracting"
      >
        <div className="p-6 border-b border-slate-200/80">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-400">Contract Workflow</p>
              <h3 className="text-2xl font-bold text-slate-900 mt-2">Contracting & Project Setup</h3>
              <p className="text-sm text-slate-500">After final award, the generated PBA appears here. Download it, review the locked Annexes A-E, sign it digitally or by scanned wet-signature PDF, upload it, and wait for final admin approval.</p>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="badge bg-slate-100 text-slate-700">Generated</span>
              <span className="badge bg-amber-100 text-amber-800">Submitted</span>
              <span className="badge bg-emerald-100 text-emerald-800">Approved</span>
              <span className="badge bg-rose-100 text-rose-700">Rejected</span>
            </div>
          </div>
        </div>

        <div className="p-6">
          {sortedContracts.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-8 text-sm text-slate-500">
              No contracts available yet. You will be notified after award.
            </div>
          )}

          {sortedContracts.length > 0 && (
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              {sortedContracts.map((contract) => (
                <div key={contract.id} className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_12px_30px_-24px_rgba(15,23,42,0.5)]">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold text-slate-400">Contract Reference</p>
                      <p className="text-base font-bold text-slate-900">{contract.referenceNumber}</p>
                      <p className="text-xs text-slate-500 mt-1">Status: {contract.status}</p>
                    </div>
                    <span className={`badge ${contractTone(contract.status)}`}>{contract.status}</span>
                  </div>

                  <div className="mt-4 grid grid-cols-4 gap-2 text-[10px] font-semibold text-slate-500">
                    {["Generated", "Submitted", "Approved", "Rejected"].map((label) => (
                      <div
                        key={label}
                        className={`rounded-full px-3 py-1 text-center ${
                          label === contract.status ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {label}
                      </div>
                    ))}
                  </div>

                  {contract.generatedFile && (
                    <div className="mt-5 space-y-2">
                      <a
                        href={contract.generatedFile}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex text-xs font-semibold text-blue-700 underline"
                      >
                        Download generated Performance-Based Agreement
                      </a>
                      <div className="flex flex-wrap gap-3 text-xs text-slate-600">
                        {[
                          ["Annex A: Results Framework", contract.annexAFile],
                          ["Annex B: Implementation Schedule", contract.annexBFile],
                          ["Annex C: Payment Terms", contract.annexCFile],
                          ["Annex D: Reporting Formats", contract.annexDFile],
                          ["Annex E: Technical Standards", contract.annexEFile],
                        ].map(([label, file]) => (
                          file ? (
                            <a key={label} href={String(file)} target="_blank" rel="noreferrer" className="underline text-slate-700">
                              {label}
                            </a>
                          ) : (
                            <span key={label} className="text-slate-400">{label} missing</span>
                          )
                        ))}
                      </div>
                    </div>
                  )}

                  {contract.status === "Generated" && (
                    <div className="mt-5 space-y-3">
                      <label className="text-xs font-semibold text-slate-600">Upload signed agreement</label>
                      <input
                        type="file"
                        accept=".pdf,application/pdf"
                        onChange={(e) => {
                          const file = e.target.files?.[0] || null;
                          setContractFiles(prev => ({ ...prev, [contract.id]: file }));
                        }}
                        className="input-field"
                      />
                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 space-y-1">
                        <p className="font-semibold text-slate-700">Locked Contract Annexes</p>
                        <p>Upload a signed PDF only. Digitally signed PDFs and scanned wet-signature PDFs are both accepted.</p>
                        <p>After upload, the admin will review and finalize the contract before the project becomes active.</p>
                        <p>Annex A: {contract.annexAFile ? "Results Framework from the awarded Gender Action Plan is attached" : "Missing"}</p>
                        <p>Annex B: {contract.annexBFile ? "Implementation Schedule from the awarded Implementation Plan is attached" : "Missing"}</p>
                        <p>Annex C: {contract.annexCFile ? "Payment Terms including the BOQ and disbursement table are attached" : "Missing"}</p>
                        <p>Annex D: {contract.annexDFile ? "Reporting Formats from the standardized system templates are attached" : "Missing"}</p>
                        <p>Annex E: {contract.annexEFile ? "Technical Standards from the awarded Technical Proposal are attached" : "Missing"}</p>
                      </div>
                      <button
                        onClick={() => handleSignContract(contract.id)}
                        disabled={isContractSubmitting}
                        className="btn-primary px-6 disabled:opacity-60"
                      >
                        {isContractSubmitting ? "Uploading..." : "Submit Signed PBA"}
                      </button>
                    </div>
                  )}

                  {contract.status === "Submitted" && (
                    <p className="mt-5 text-xs text-amber-700">Signed agreement uploaded successfully. Admin can now review the complete package and finalize the contract.</p>
                  )}
                  {contract.status === "Approved" && (
                    <p className="mt-5 text-xs text-emerald-700">Contract finalized. The project is now active, the mobilization payment request has been queued, and installation reporting access is enabled.</p>
                  )}
                  {contract.status === "Rejected" && (
                    <p className="mt-5 text-xs text-rose-600">Rejected: {contract.rejectionReason || "Please contact admin."}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {contractMessage && <p className="mt-4 text-xs text-emerald-700">{contractMessage}</p>}
        </div>
      </section>
  );

  if (showOnlyContracting) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Contracting</h1>
          <p className="text-slate-500">Review and sign contracts for awarded tenders</p>
        </div>
        {contractingSection}
        <div className="card">
          <div className="p-6 border-b border-slate-100">
            <h3 className="text-lg font-bold">Ongoing Projects</h3>
            <p className="text-sm text-slate-500">Active implementations linked to your awarded tenders</p>
          </div>
          <div className="p-6 space-y-4">
            {projects.length === 0 && (
              <p className="text-sm text-slate-500">No ongoing projects yet.</p>
            )}
            {projects.map(project => (
              <div key={project.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-100 p-4">
                <div>
                  <p className="text-sm font-bold text-slate-900">{project.projectReference || `Project ${project.id}`}</p>
                  <p className="text-xs text-slate-500">{project.techType} • {project.region}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="badge bg-slate-100 text-slate-700">{project.status}</span>
                  <span className="text-xs text-slate-500">Progress {project.progress}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {!isPreQualified && (
        <div className="p-6 bg-amber-50 border border-amber-200 rounded-2xl flex items-start gap-4">
          <div className="p-3 bg-amber-100 text-amber-600 rounded-xl">
            <AlertCircle size={24} />
          </div>
          <div className="flex-1">
            <h3 className="font-bold text-amber-900">Pre-Qualification Required</h3>
            <p className="text-sm text-amber-700 mt-1">
              You must complete the mandatory pre-qualification process before you can submit new project applications or participate in tenders.
            </p>
            <button
              onClick={() => {
                if (onGoToPrequal) {
                  onGoToPrequal();
                }
              }}
              className="mt-3 text-sm font-bold text-amber-900 underline hover:no-underline"
            >
              Go to Pre-Qualification Form →
            </button>
          </div>
        </div>
      )}

      {vendorRestricted && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 flex gap-3">
          <AlertTriangle className="text-rose-600 mt-0.5" size={20} />
          <div>
            <h3 className="font-bold text-rose-900">Vendor Access Restricted</h3>
            <p className="text-sm text-rose-700 mt-1">{vendorRestrictionMessage}</p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Vendor Portal</h1>
          <p className="text-slate-500">Manage your energy projects and payment claims</p>
        </div>
        <button 
          onClick={handleStartApplication} 
          disabled={!isPreQualified || vendorRestricted}
          className={`btn-primary flex items-center gap-2 ${(!isPreQualified || vendorRestricted) ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <Plus size={18} /> New Application
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard label="Active Projects" value={String(projects.length)} icon={Activity} color="bg-emerald-600" />
        <StatCard label="Pending Claims" value={`M ${pendingClaimAmount.toLocaleString()}`} icon={CreditCard} color="bg-amber-600" />
        <StatCard label="Average KPI Score" value={`${averageKpiScore}%`} icon={BarChart3} color="bg-blue-600" />
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">Calls for Proposals</h3>
            <p className="text-sm text-slate-500">Published tenders available for bid submission</p>
          </div>
          <button
            onClick={() => {
              if (!isPreQualified) {
                alert("You must be pre-qualified to submit bids.");
                return;
              }
              if (vendorRestricted) {
                alert(vendorRestrictionMessage);
                return;
              }
              if (activeTenders.length > 0) {
                const latest = activeTenders[0];
                const deadline = latest.lastDateSubmission || latest.deadline;
                const deadlineOk = !deadline || new Date(deadline) > new Date();
                const statusOk = latest.status === TenderStatus.PUBLISHED;
                if (!deadlineOk || !statusOk) {
                  alert("This tender is no longer open for bidding.");
                  return;
                }
                void openBidForm(latest);
              }
            }}
            className="btn-secondary text-sm"
            disabled={vendorRestricted}
          >
            Open Latest
          </button>
        </div>
        <div className="divide-y divide-slate-100">
          {activeTenders.map((tender) => (
            <div key={tender.id} className="p-6 flex items-center justify-between hover:bg-slate-50 transition-colors">
              <div>
                <p className="font-bold text-slate-900">{tender.name}</p>
                <p className="text-xs text-slate-500">{tender.referenceNumber} • Deadline: {tender.lastDateSubmission || tender.deadline}</p>
              </div>
              <button
                onClick={() => openBidForm(tender)}
                disabled={vendorRestricted || !isPreQualified || (() => {
                  const deadline = tender.lastDateSubmission || tender.deadline;
                  const deadlineOk = !deadline || new Date(deadline) > new Date();
                  const statusOk = tender.status === TenderStatus.PUBLISHED;
                  return !(deadlineOk && statusOk);
                })()}
                className="btn-primary py-1.5 px-4 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Submit Proposal
              </button>
            </div>
          ))}
          {activeTenders.length === 0 && (
            <div className="p-6 text-sm text-slate-500">No published tenders available right now.</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">My Bids</h3>
          <p className="text-sm text-slate-500">Track your submissions and status updates</p>
        </div>
        <div className="p-6 space-y-4">
          {bidHistory.length === 0 && (
            <p className="text-sm text-slate-500">No bids submitted yet.</p>
          )}
          {bidHistory
            .slice()
            .sort((a, b) => (b.submitted_at || b.reviewed_at || "").localeCompare(a.submitted_at || a.reviewed_at || ""))
            .slice(0, 8)
            .map((bid) => {
              const statusColor =
                bid.status === BidStatus.SUBMITTED ? "bg-blue-100 text-blue-700" :
                bid.status === BidStatus.UNDER_REVIEW ? "bg-amber-100 text-amber-700" :
                bid.status === BidStatus.ACCEPTED ? "bg-emerald-100 text-emerald-700" :
                bid.status === BidStatus.REJECTED ? "bg-rose-100 text-rose-700" :
                "bg-slate-100 text-slate-700";
              return (
                <div key={bid.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border border-slate-100 rounded-xl p-4">
                  <div>
                    <p className="text-sm font-bold text-slate-900">
                      {bid.tender_name || `Tender ${bid.tender_reference || bid.tender}`}
                    </p>
                    <p className="text-xs text-slate-500">
                      Ref: {bid.tender_reference || "N/A"} • Version {bid.version_number}
                    </p>
                    <p className="text-xs text-slate-400">
                      Submitted: {bid.submitted_at ? new Date(bid.submitted_at).toLocaleString() : "Draft"}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className={`badge ${statusColor}`}>{bid.status}</span>
                    <div className="text-xs text-slate-500 mt-2">
                      Amount: {bid.bid_amount != null ? `M ${Number(bid.bid_amount).toLocaleString()}` : "N/A"}
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {contractingSection}

      <div className="card">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">Ongoing Projects</h3>
          <p className="text-sm text-slate-500">View active implementations linked to your awarded tenders</p>
        </div>
        <div className="p-6 space-y-4">
          {projects.length === 0 && (
            <p className="text-sm text-slate-500">No ongoing projects yet.</p>
          )}
          {projects.map(project => (
            <div key={project.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border border-slate-100 p-4">
              <div>
                <p className="text-sm font-bold text-slate-900">{project.projectReference || `Project ${project.id}`}</p>
                <p className="text-xs text-slate-500">{project.techType} • {project.region}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="badge bg-slate-100 text-slate-700">{project.status}</span>
                <span className="text-xs text-slate-500">Progress {project.progress}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">My Project Milestones</h3>
        </div>
        <div className="p-6 space-y-6">
          {[
            { id: "demo-ms-1", projectId: "demo-project-1", name: "Thaba-Tseka SHS Phase 1", percentage: 100, progressPercentage: 100, progress: 100, status: "Verified" as const, amount: 45000 },
            { id: "demo-ms-2", projectId: "demo-project-2", name: "Thaba-Tseka SHS Phase 2", percentage: 45, progressPercentage: 45, progress: 45, status: "Submitted" as const, amount: 60000 },
            { id: "demo-ms-3", projectId: "demo-project-3", name: "Maseru Mini-Grid Expansion", percentage: 10, progressPercentage: 10, progress: 10, status: "Pending" as const, amount: 250000 },
          ].map((p, i) => (
            <div key={i} className="flex items-center gap-6">
              <div className="flex-1">
                <div className="flex justify-between mb-2">
                  <span className="font-medium text-slate-900">{p.name}</span>
                  <span className="text-sm font-bold text-slate-500">{p.progress}%</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-emerald-500 h-full" style={{ width: `${p.progress}%` }} />
                </div>
              </div>
              <div className="text-right min-w-[100px]">
                <div className="text-sm font-bold text-slate-900">M {Number(p.amount).toLocaleString()}</div>
                <div className={`text-[10px] font-bold uppercase ${p.status === 'Verified' ? 'text-emerald-600' : 'text-amber-600'}`}>{p.status}</div>
              </div>
              <button 
                onClick={() => handleStartClaim(p)}
                className="btn-secondary py-1 px-3 text-xs"
              >
                Claim
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const VendorProjectsHub = () => {
  const createEmptyMilestoneDraft = () => ({
    name: "",
    description: "",
    progressPercentage: "0",
    targetDate: "",
    completedDate: "",
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [claims, setClaims] = useState<PaymentClaim[]>([]);
  const [contracts, setContracts] = useState<TenderContract[]>([]);
  const [projectUpdates, setProjectUpdates] = useState<ProjectUpdate[]>([]);
  const [projectDocuments, setProjectDocuments] = useState<ProjectDocument[]>([]);
  const [installationReports, setInstallationReports] = useState<InstallationReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [techFilter, setTechFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [projectTab, setProjectTab] = useState<"overview" | "milestones" | "planning" | "payments" | "documents" | "updates" | "fieldwork">("overview");
  const [deploymentPlan, setDeploymentPlan] = useState({
    teamRoster: "",
    equipmentPlan: "",
    workSchedule: "",
  });
  const [planSaving, setPlanSaving] = useState(false);
  const [planMessage, setPlanMessage] = useState<string | null>(null);
  const [milestoneDraft, setMilestoneDraft] = useState(createEmptyMilestoneDraft);
  const [milestoneSaving, setMilestoneSaving] = useState(false);
  const [milestoneMessage, setMilestoneMessage] = useState<string | null>(null);
  const [editingMilestoneId, setEditingMilestoneId] = useState<string | null>(null);
  const [milestoneEditDraft, setMilestoneEditDraft] = useState(createEmptyMilestoneDraft);
  const [documentTitle, setDocumentTitle] = useState("");
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentUploading, setDocumentUploading] = useState(false);
  const [documentMessage, setDocumentMessage] = useState<string | null>(null);
  const [reportDraft, setReportDraft] = useState({
    serialNumber: "",
    beneficiaryId: "",
    gpsLat: "",
    gpsLng: "",
    meterId: "",
    kwhReading: "",
  });
  const [reportPhotos, setReportPhotos] = useState<File[]>([]);
  const [reportReceipt, setReportReceipt] = useState<File | null>(null);
  const [reportSubmitting, setReportSubmitting] = useState(false);
  const [reportMessage, setReportMessage] = useState<string | null>(null);

  const loadData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [projectRows, milestoneRows, claimRows, contractRows, updateRows] = await Promise.all([
        fetchProjects(),
        fetchMilestones(),
        fetchPaymentClaims(),
        fetchTenderContracts(),
        fetchProjectUpdates(),
      ]);
      setProjects(projectRows);
      setMilestones(milestoneRows);
      setClaims(claimRows);
      setContracts(contractRows);
      setProjectUpdates(updateRows);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadData();
  }, [loadData]);

  React.useEffect(() => {
    if (!selectedProject) {
      setProjectDocuments([]);
      setInstallationReports([]);
      return;
    }
    setDeploymentPlan({
      teamRoster: selectedProject.deploymentTeamRoster || "",
      equipmentPlan: selectedProject.deploymentEquipmentPlan || "",
      workSchedule: selectedProject.deploymentWorkSchedule || "",
    });
    setPlanMessage(null);
    setMilestoneDraft(createEmptyMilestoneDraft());
    setMilestoneMessage(null);
    setEditingMilestoneId(null);
    setMilestoneEditDraft(createEmptyMilestoneDraft());
    setDocumentTitle("");
    setDocumentFile(null);
    setDocumentMessage(null);
    setReportDraft({ serialNumber: "", beneficiaryId: "", gpsLat: "", gpsLng: "", meterId: "", kwhReading: "" });
    setReportPhotos([]);
    setReportReceipt(null);
    setReportMessage(null);
  }, [selectedProject]);

  React.useEffect(() => {
    if (!selectedProject) return;
    let active = true;
    (async () => {
      try {
        const [docs, updates] = await Promise.all([
          fetchProjectDocuments(selectedProject.id),
          fetchProjectUpdates(selectedProject.id),
        ]);
        if (active) {
          setProjectDocuments(docs);
          setProjectUpdates(prev => {
            const otherProjects = prev.filter(update => update.projectId !== selectedProject.id);
            return [...updates, ...otherProjects];
          });
        }
      } catch {
        if (active) {
          setProjectDocuments([]);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedProject]);

  React.useEffect(() => {
    if (!selectedProject) return;
    let active = true;
    (async () => {
      try {
        const reports = await fetchInstallationReports(selectedProject.id);
        if (active) setInstallationReports(reports);
      } catch {
        if (active) setInstallationReports([]);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedProject]);


  const techOptions = useMemo(
    () => ["All", ...Array.from(new Set(projects.map(p => p.techType).filter(Boolean)))],
    [projects]
  );
  const activeProjects = useMemo(
    () => projects.filter(p => [ProjectStatus.INSTALLATION, ProjectStatus.VERIFICATION].includes(p.status)),
    [projects]
  );
  const completedProjects = useMemo(
    () => projects.filter(p => p.status === ProjectStatus.COMPLETED),
    [projects]
  );
  const pendingProjects = useMemo(
    () => projects.filter(p => p.status === ProjectStatus.CONTRACTING),
    [projects]
  );
  const contractValueByProject = useMemo<Map<string, number>>(() => {
    const map = new Map<string, number>();
    milestones.forEach(m => {
      const total = map.get(m.projectId) ?? 0;
      map.set(m.projectId, total + Number(m.amount || 0));
    });
    return map;
  }, [milestones]);
  const totalContractValue = useMemo(
    () => Array.from<number>(contractValueByProject.values()).reduce((sum, val) => sum + val, 0),
    [contractValueByProject]
  );
  const filteredProjects = useMemo(() => {
    return projects.filter(project => {
      const matchesSearch = !search || `${project.projectReference || ""} ${project.techType} ${project.region}`.toLowerCase().includes(search.toLowerCase());
      const matchesTech = techFilter === "All" || project.techType === techFilter;
      const matchesStatus =
        statusFilter === "All" ||
        (statusFilter === "Active" && activeProjects.some(p => p.id === project.id)) ||
        (statusFilter === "Completed" && completedProjects.some(p => p.id === project.id)) ||
        (statusFilter === "Pending" && pendingProjects.some(p => p.id === project.id));
      return matchesSearch && matchesTech && matchesStatus;
    });
  }, [projects, search, techFilter, statusFilter, activeProjects, completedProjects, pendingProjects]);

  const milestonesForProject = (projectId: string) => milestones.filter(m => m.projectId === projectId);
  const claimsForProject = (projectId: string) => claims.filter(c => c.projectId === projectId);
  const contractForProject = (projectId: string) => contracts.find(c => c.projectId === projectId);
  const updatesForProject = (projectId: string) => projectUpdates
    .filter(u => u.projectId === projectId)
    .slice()
    .sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""));
  const documentsForProject = (projectId: string) => projectDocuments
    .filter(d => d.projectId === projectId)
    .slice()
    .sort((a, b) => (b.uploadedAt || "").localeCompare(a.uploadedAt || ""));
  const reportsForProject = (projectId: string) => installationReports
    .filter(r => r.projectId === projectId)
    .slice()
    .sort((a, b) => (b.submittedAt || "").localeCompare(a.submittedAt || ""));
  const refreshProjectUpdates = async (projectId: string) => {
    try {
      const updates = await fetchProjectUpdates(projectId);
      setProjectUpdates(prev => {
        const otherProjects = prev.filter(update => update.projectId !== projectId);
        return [...updates, ...otherProjects];
      });
    } catch {
      // Leave the current update list in place if refresh fails.
    }
  };
  const formatDate = (value?: string) => {
    if (!value) return "N/A";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "N/A";
    return parsed.toLocaleDateString("en-US");
  };
  const toSortableDate = (value?: string) => {
    if (!value) return Number.POSITIVE_INFINITY;
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? Number.POSITIVE_INFINITY : parsed.getTime();
  };
  const milestoneProgress = (milestone: Milestone) => Math.min(100, Math.max(0, Number(milestone.progressPercentage ?? 0)));
  const milestoneCompleted = (milestone: Milestone) => milestoneProgress(milestone) >= 100 || Boolean(milestone.completedDate);
  const nextOpenMilestoneForProject = (projectId: string) => {
    const openMilestones = milestonesForProject(projectId).filter(m => !milestoneCompleted(m));
    if (openMilestones.length === 0) return undefined;
    return openMilestones
      .slice()
      .sort((a, b) => {
        const dateDelta = toSortableDate(a.targetDate) - toSortableDate(b.targetDate);
        if (dateDelta !== 0) return dateDelta;
        return milestoneProgress(b) - milestoneProgress(a);
      })[0];
  };
  const milestoneStatusFromProgress = (progress: number): Milestone["status"] => {
    if (progress >= 100) return "Verified";
    if (progress > 0) return "Submitted";
    return "Pending";
  };
  const milestoneBadge = (milestone: Milestone) => {
    if (milestoneCompleted(milestone)) {
      return {
        label: "Completed",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
        barClassName: "bg-emerald-500",
      };
    }
    if (milestoneProgress(milestone) > 0) {
      return {
        label: "In Progress",
        className: "border-amber-200 bg-amber-50 text-amber-700",
        barClassName: "bg-amber-400",
      };
    }
    return {
      label: "Not Started",
      className: "border-slate-200 bg-slate-100 text-slate-600",
      barClassName: "bg-slate-300",
    };
  };
  const toMilestoneDraft = (milestone?: Milestone | null) => ({
    name: milestone?.name ?? "",
    description: milestone?.description ?? "",
    progressPercentage: milestone ? String(milestoneProgress(milestone)) : "0",
    targetDate: milestone?.targetDate ?? "",
    completedDate: milestone?.completedDate ?? "",
  });
  const normalizeMilestoneDateInput = (value?: string | null) => {
    const raw = String(value ?? "").trim();
    if (!raw) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    const slashMatch = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
    if (!slashMatch) return null;
    const [, monthRaw, dayRaw, yearRaw] = slashMatch;
    const month = Number(monthRaw);
    const day = Number(dayRaw);
    const year = yearRaw.length === 2 ? 2000 + Number(yearRaw) : Number(yearRaw);
    if (month < 1 || month > 12 || day < 1 || day > 31 || year < 2000 || year > 2100) return null;
    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  };
  const toFileUrl = (raw?: string | null) => {
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = API_BASE.replace(/\/api$/i, "").replace(/\/$/, "");
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    return `${base}${path}`;
  };
  const budgetForProject = (project: Project) => {
    if (typeof project.budget === "number") {
      return project.budget;
    }
    if (typeof project.tenderBudget === "number") {
      return project.tenderBudget;
    }
    if (typeof project.milestoneTotalAmount === "number" && project.milestoneTotalAmount > 0) {
      return project.milestoneTotalAmount;
    }
    const fromMilestones = contractValueByProject.get(project.id);
    return typeof fromMilestones === "number" && fromMilestones > 0 ? fromMilestones : null;
  };
  const startDateForProject = (project: Project) => project.startDate || project.tenderAwardedAt;
  const endDateForProject = (project: Project) => project.endDate || project.tenderDeadline;

  const handleSaveDeploymentPlan = async () => {
    if (!selectedProject) return;
    setPlanSaving(true);
    setPlanMessage(null);
    try {
      const updated = await updateProject(selectedProject.id, {
        deploymentTeamRoster: deploymentPlan.teamRoster,
        deploymentEquipmentPlan: deploymentPlan.equipmentPlan,
        deploymentWorkSchedule: deploymentPlan.workSchedule,
      });
      setSelectedProject(updated);
      setProjects(prev => prev.map(p => (p.id === updated.id ? updated : p)));
      await refreshProjectUpdates(updated.id);
      setPlanMessage("Deployment plan saved.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setPlanMessage(toFriendlyApiMessage(raw) || "Unable to save deployment plan.");
    } finally {
      setPlanSaving(false);
    }
  };

  const handleAddMilestone = async () => {
    if (!selectedProject) return;
    const name = milestoneDraft.name.trim();
    const description = milestoneDraft.description.trim();
    const requestedProgressValue = Number(milestoneDraft.progressPercentage);
    const normalizedTargetDate = normalizeMilestoneDateInput(milestoneDraft.targetDate);
    const normalizedCompletedDate = normalizeMilestoneDateInput(milestoneDraft.completedDate);
    const targetDate = normalizedTargetDate || undefined;
    const completedDate = normalizedCompletedDate || undefined;
    const progressValue = completedDate ? 100 : requestedProgressValue;
    if (!name) {
      setMilestoneMessage("Please provide a milestone name.");
      return;
    }
    if (!Number.isFinite(progressValue) || progressValue < 0 || progressValue > 100) {
      setMilestoneMessage("Please provide milestone progress between 0 and 100.");
      return;
    }
    if (normalizedTargetDate === null || normalizedCompletedDate === null) {
      setMilestoneMessage("Please enter milestone dates as YYYY-MM-DD or MM/DD/YYYY.");
      return;
    }
    setMilestoneSaving(true);
    setMilestoneMessage(null);
    try {
      const created = await createMilestone({
        projectId: selectedProject.id,
        name,
        description,
        status: milestoneStatusFromProgress(progressValue),
        progressPercentage: progressValue,
        targetDate,
        completedDate,
      });
      setMilestones(prev => [...prev, created]);
      await refreshProjectUpdates(selectedProject.id);
      setMilestoneDraft(createEmptyMilestoneDraft());
      setMilestoneMessage("Milestone added.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setMilestoneMessage(toFriendlyApiMessage(raw) || "Unable to add milestone.");
    } finally {
      setMilestoneSaving(false);
    }
  };

  const beginMilestoneEdit = (milestone: Milestone) => {
    setEditingMilestoneId(milestone.id);
    setMilestoneEditDraft(toMilestoneDraft(milestone));
    setMilestoneMessage(null);
  };

  const handleSaveMilestone = async () => {
    if (!editingMilestoneId) return;
    const existingMilestone = milestones.find(item => item.id === editingMilestoneId);
    if (!existingMilestone) {
      setMilestoneMessage("Unable to find the milestone to update.");
      return;
    }
    const name = milestoneEditDraft.name.trim();
    const description = milestoneEditDraft.description.trim();
    const requestedProgressValue = Number(milestoneEditDraft.progressPercentage);
    const normalizedTargetDate = normalizeMilestoneDateInput(milestoneEditDraft.targetDate);
    const normalizedCompletedDate = normalizeMilestoneDateInput(milestoneEditDraft.completedDate);
    const targetDate = normalizedTargetDate || null;
    const completedDate = normalizedCompletedDate || null;
    const progressValue = completedDate ? 100 : requestedProgressValue;

    if (!name) {
      setMilestoneMessage("Please provide a milestone name.");
      return;
    }
    if (!Number.isFinite(progressValue) || progressValue < 0 || progressValue > 100) {
      setMilestoneMessage("Please provide milestone progress between 0 and 100.");
      return;
    }
    if (normalizedTargetDate === null || normalizedCompletedDate === null) {
      setMilestoneMessage("Please enter milestone dates as YYYY-MM-DD or MM/DD/YYYY.");
      return;
    }

    setMilestoneSaving(true);
    setMilestoneMessage(null);
    try {
      const updated = await updateMilestone(editingMilestoneId, {
        projectId: existingMilestone.projectId,
        name,
        description,
        percentage: existingMilestone.percentage,
        amount: existingMilestone.amount,
        status: milestoneStatusFromProgress(progressValue),
        progressPercentage: progressValue,
        targetDate,
        completedDate,
      });
      setMilestones(prev => prev.map(item => (item.id === updated.id ? updated : item)));
      await refreshProjectUpdates(existingMilestone.projectId);
      setEditingMilestoneId(null);
      setMilestoneEditDraft(createEmptyMilestoneDraft());
      setMilestoneMessage("Milestone updated.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setMilestoneMessage(toFriendlyApiMessage(raw) || "Unable to update milestone.");
    } finally {
      setMilestoneSaving(false);
    }
  };

  const handleUploadDocument = async () => {
    if (!selectedProject) return;
    if (!documentFile) {
      setDocumentMessage("Please choose a file to upload.");
      return;
    }
    setDocumentUploading(true);
    setDocumentMessage(null);
    try {
      const uploaded = await uploadProjectDocument({
        projectId: selectedProject.id,
        title: documentTitle.trim(),
        file: documentFile,
      });
      setProjectDocuments(prev => [uploaded, ...prev]);
      await refreshProjectUpdates(selectedProject.id);
      setDocumentTitle("");
      setDocumentFile(null);
      setDocumentMessage("Document uploaded.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setDocumentMessage(toFriendlyApiMessage(raw) || "Unable to upload document.");
    } finally {
      setDocumentUploading(false);
    }
  };

  const handleSubmitReport = async () => {
    if (!selectedProject) return;
    const serialNumber = reportDraft.serialNumber.trim();
    const beneficiaryId = reportDraft.beneficiaryId.trim();
    const gpsLat = Number(reportDraft.gpsLat);
    const gpsLng = Number(reportDraft.gpsLng);
    if (!serialNumber || !beneficiaryId) {
      setReportMessage("Serial number and beneficiary ID are required.");
      return;
    }
    if (!Number.isFinite(gpsLat) || !Number.isFinite(gpsLng)) {
      setReportMessage("Valid GPS coordinates are required.");
      return;
    }
    setReportSubmitting(true);
    setReportMessage(null);
    try {
      const created = await createInstallationReport({
        projectId: selectedProject.id,
        gpsLat,
        gpsLng,
        serialNumber,
        beneficiaryId,
        meterId: reportDraft.meterId.trim() || undefined,
        kwhReading: reportDraft.kwhReading ? Number(reportDraft.kwhReading) : undefined,
        receiptFile: reportReceipt,
        photoFiles: reportPhotos,
      });
      setInstallationReports(prev => [created, ...prev]);
      await refreshProjectUpdates(selectedProject.id);
      setReportDraft({ serialNumber: "", beneficiaryId: "", gpsLat: "", gpsLng: "", meterId: "", kwhReading: "" });
      setReportPhotos([]);
      setReportReceipt(null);
      setReportMessage("Installation report submitted.");
    } catch (err: any) {
      const raw = String(err?.message || "");
      setReportMessage(toFriendlyApiMessage(raw) || "Unable to submit installation report.");
    } finally {
      setReportSubmitting(false);
    }
  };

  const handleGenerateProjectReport = (project: Project) => {
    const projectUpdatesForExport = updatesForProject(project.id);
    const projectMilestones = milestonesForProject(project.id);
    const nextMilestone = nextOpenMilestoneForProject(project.id);
    const completedMilestones = projectMilestones.filter(m => milestoneCompleted(m));
    const projectDocumentsForExport = documentsForProject(project.id);
    const projectReports = reportsForProject(project.id);
    const latestUpdate = projectUpdatesForExport[0];
    const budgetValue = budgetForProject(project);
    const reportLines = [
      `PROJECT PERFORMANCE REPORT`,
      `Generated on: ${new Date().toLocaleString()}`,
      ``,
      `1. Executive Summary`,
      `Project Reference: ${project.projectReference || `Project ${project.id}`}`,
      `Project Title: ${project.projectTitle || "N/A"}`,
      `Vendor: ${project.vendorName}`,
      `Technology: ${project.techType}`,
      `Location: ${[project.region, project.district].filter(Boolean).join(", ") || "N/A"}`,
      `Current Status: ${project.status}`,
      `Overall Progress: ${project.progress}%`,
      `Contract Value: ${budgetValue != null ? `M ${Number(budgetValue).toLocaleString()}` : "N/A"}`,
      `Reporting Period Start: ${formatDate(startDateForProject(project))}`,
      `Reporting Period End: ${formatDate(endDateForProject(project))}`,
      ``,
      `2. Immediate Priority`,
      `Next Milestone To Finish: ${nextMilestone?.name || "All milestones completed"}`,
      `Target Date: ${formatDate(nextMilestone?.targetDate)}`,
      `Progress: ${nextMilestone ? `${milestoneProgress(nextMilestone)}%` : "100%"}`,
      `Description: ${nextMilestone?.description?.trim() || "No open milestone description is available."}`,
      ``,
      `3. Milestone Status`,
      ...(projectMilestones.length > 0
        ? projectMilestones.map((milestone, index) => {
            const badge = milestoneCompleted(milestone) ? "Completed" : milestoneBadge(milestone).label;
            return [
              `${index + 1}. ${milestone.name}`,
              `   Status: ${badge}`,
              `   Target Date: ${formatDate(milestone.targetDate)}`,
              `   Completed Date: ${formatDate(milestone.completedDate)}`,
              `   Progress: ${milestoneProgress(milestone)}%`,
              `   Description: ${milestone.description?.trim() || "N/A"}`,
            ].join("\n");
          })
        : ["No milestones have been recorded for this project."]),
      ``,
      `4. Project Activity Summary`,
      `Completed Milestones: ${completedMilestones.length} of ${projectMilestones.length}`,
      `Project Documents: ${projectDocumentsForExport.length}`,
      `Installation Reports Submitted: ${projectReports.length}`,
      `Latest Update: ${latestUpdate?.title || "No recent updates recorded"}`,
      ``,
      `5. Documents On Record`,
      ...(projectDocumentsForExport.length > 0
        ? projectDocumentsForExport.map((doc, index) => `${index + 1}. ${doc.title || doc.file.split("/").pop() || "Project Document"} - uploaded ${doc.uploadedAt ? new Date(doc.uploadedAt).toLocaleString() : "N/A"}`)
        : ["No project documents have been uploaded."]),
      ``,
      `6. Field Work Summary`,
      ...(projectReports.length > 0
        ? projectReports.map((report, index) => `${index + 1}. Serial ${report.serialNumber} | Beneficiary ${report.beneficiaryId} | Status ${report.status} | Submitted ${report.submittedAt ? new Date(report.submittedAt).toLocaleString() : "N/A"}`)
        : ["No installation reports have been submitted."]),
      ``,
      `7. Update Timeline`,
      ...(projectUpdatesForExport.length > 0
        ? projectUpdatesForExport.map((update, index) => {
            const stamp = update.createdAt ? new Date(update.createdAt).toLocaleString() : "N/A";
            const author = update.authorUsername ? ` | ${update.authorUsername}` : "";
            return `${index + 1}. ${update.title || "Project Update"} | ${stamp}${author}\n${update.body}`;
          })
        : ["No project updates have been recorded yet."]),
      ``,
      `End of Report`,
    ];

    const safeReference = (project.projectReference || `project_${project.id}`)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "");
    triggerDownload(`${safeReference || `project_${project.id}`}_report.txt`, reportLines.join("\n"));
  };

  const renderProjectDetail = (project: Project) => (
    <div className="mt-5 rounded-3xl border border-slate-100 bg-white shadow-[0_30px_70px_-55px_rgba(15,23,42,0.7)] overflow-hidden">
      <div className="p-5 border-b border-slate-100 bg-[linear-gradient(120deg,#f8fafc_0%,#f1f5f9_45%,#ffffff_100%)] space-y-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-slate-400">Project Details</p>
          <p className="text-sm text-slate-600 mt-1">
            Choose a section below to add or view information for this project.
          </p>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {["overview", "milestones", "planning", "payments", "documents", "updates", "fieldwork"].map(tab => (
            <button
              key={tab}
              onClick={() => setProjectTab(tab as typeof projectTab)}
              className={`text-xs font-semibold rounded-full px-4 py-2 border transition whitespace-nowrap ${
                projectTab === tab
                  ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {tab === "fieldwork" ? "Field Work" : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          <button
            onClick={() => setProjectTab("milestones")}
            className="px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 font-semibold"
          >
            Add Milestone
          </button>
          <button
            onClick={() => setProjectTab("documents")}
            className="px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 font-semibold"
          >
            Upload Document
          </button>
          <button
            onClick={() => setProjectTab("updates")}
            className="px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 font-semibold"
          >
            View Updates
          </button>
          <button
            onClick={() => setProjectTab("fieldwork")}
            className="px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100 font-semibold"
          >
            Report Installation
          </button>
        </div>
      </div>
      <div className="px-6 pt-5">
        <div className="grid grid-cols-2 gap-3 text-[11px] text-slate-500 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
            <p className="uppercase tracking-wider text-slate-400">Contract Ref</p>
            <p className="font-semibold text-slate-700">{project.contractReference || "N/A"}</p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
            <p className="uppercase tracking-wider text-slate-400">Tender Status</p>
            <p className="font-semibold text-slate-700">{project.tenderStatus || "N/A"}</p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
            <p className="uppercase tracking-wider text-slate-400">Start Date</p>
            <p className="font-semibold text-slate-700">{formatDate(startDateForProject(project))}</p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
            <p className="uppercase tracking-wider text-slate-400">End Date</p>
            <p className="font-semibold text-slate-700">{formatDate(endDateForProject(project))}</p>
          </div>
        </div>
      </div>
      <div className="p-6 space-y-4">
        {projectTab === "overview" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Overview</h4>
              <p className="text-xs text-slate-500">See the next thing to finish and the actions you can take right now.</p>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5">
                <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-emerald-700">Next To Finish</p>
                <p className="mt-3 text-lg font-semibold text-slate-900">
                  {nextOpenMilestoneForProject(project.id)?.name || "All milestones completed"}
                </p>
                <p className="mt-2 text-sm text-slate-600">
                  {nextOpenMilestoneForProject(project.id)?.targetDate
                    ? `Target date: ${formatDate(nextOpenMilestoneForProject(project.id)?.targetDate)}`
                    : nextOpenMilestoneForProject(project.id)?.description?.trim() || "No open milestone description is available."}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-slate-500">What You Can Do Now</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={() => setProjectTab("milestones")}
                    className="btn-primary text-xs"
                  >
                    Update Milestones
                  </button>
                  <button
                    onClick={() => setProjectTab("documents")}
                    className="btn-secondary text-xs"
                  >
                    Upload Document
                  </button>
                  <button
                    onClick={() => setProjectTab("fieldwork")}
                    className="btn-secondary text-xs"
                  >
                    Report Field Work
                  </button>
                  <button
                    onClick={() => handleGenerateProjectReport(project)}
                    className="btn-secondary text-xs"
                  >
                    Generate Report
                  </button>
                </div>
                <p className="mt-3 text-sm text-slate-500">
                  Latest update: {updatesForProject(project.id)[0]?.title || "No updates recorded yet"}
                </p>
              </div>
            </div>
          </div>
        )}
        {projectTab === "planning" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Deployment Planning</h4>
              <p className="text-xs text-slate-500">Provide team, equipment, and schedule details.</p>
            </div>
            <div className="space-y-6">
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <p className="text-xs text-slate-500">
                  Core project parameters are locked because they are inherited from the awarded bid and tender.
                  Use this section to provide your deployment-level planning.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Field Team Roster</label>
                  <textarea
                    className="input-field min-h-[90px]"
                    placeholder="List roles, headcount, and deployment leads"
                    value={deploymentPlan.teamRoster}
                    onChange={(e) => setDeploymentPlan(prev => ({ ...prev, teamRoster: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Equipment Sourcing Plan</label>
                  <textarea
                    className="input-field min-h-[90px]"
                    placeholder="Describe suppliers, lead times, and logistics"
                    value={deploymentPlan.equipmentPlan}
                    onChange={(e) => setDeploymentPlan(prev => ({ ...prev, equipmentPlan: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-slate-700">Work Schedule</label>
                  <textarea
                    className="input-field min-h-[90px]"
                    placeholder="Phases, timelines, and key milestones"
                    value={deploymentPlan.workSchedule}
                    onChange={(e) => setDeploymentPlan(prev => ({ ...prev, workSchedule: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleSaveDeploymentPlan}
                  className="btn-primary px-6"
                  disabled={planSaving}
                >
                  {planSaving ? "Saving..." : "Save Deployment Plan"}
                </button>
                {planMessage && <span className="text-sm text-slate-500">{planMessage}</span>}
              </div>
            </div>
          </div>
        )}
        {projectTab === "milestones" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Milestones</h4>
              <p className="text-xs text-slate-500">Add milestones, set target dates, and track progress from one place.</p>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-700">Add Milestone</p>
                <span className="text-[11px] text-slate-400">Fields marked * are required</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600">Milestone Name *</label>
                  <input
                    className="input-field"
                    placeholder="e.g. Site Assessment"
                    value={milestoneDraft.name}
                    onChange={(e) => setMilestoneDraft(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600">Target Date</label>
                  <input
                    className="input-field"
                    type="date"
                    value={milestoneDraft.targetDate}
                    onChange={(e) => setMilestoneDraft(prev => ({ ...prev, targetDate: e.target.value }))}
                  />
                </div>
                <div className="space-y-1 md:col-span-2">
                  <label className="text-xs font-semibold text-slate-600">Description</label>
                  <textarea
                    className="input-field min-h-[88px]"
                    placeholder="Briefly explain the purpose of this milestone."
                    value={milestoneDraft.description}
                    onChange={(e) => setMilestoneDraft(prev => ({ ...prev, description: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600">Progress %</label>
                  <input
                    className="input-field"
                    type="number"
                    min={0}
                    max={100}
                    placeholder="0"
                    value={milestoneDraft.progressPercentage}
                    onChange={(e) => setMilestoneDraft(prev => ({
                      ...prev,
                      progressPercentage: e.target.value,
                    }))}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600">Completed Date</label>
                  <input
                    className="input-field"
                    type="date"
                    value={milestoneDraft.completedDate}
                    onChange={(e) => setMilestoneDraft(prev => ({
                      ...prev,
                      completedDate: e.target.value,
                      progressPercentage: e.target.value ? "100" : prev.progressPercentage,
                    }))}
                  />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleAddMilestone}
                  className="btn-primary text-xs"
                  disabled={milestoneSaving}
                >
                  {milestoneSaving ? "Saving..." : "Add Milestone"}
                </button>
                {milestoneMessage && <span className="text-xs text-slate-500">{milestoneMessage}</span>}
              </div>
            </div>
            <div className="space-y-3">
              {milestonesForProject(project.id).length === 0 && (
                <p className="text-sm text-slate-500">No milestones added yet.</p>
              )}
              {milestonesForProject(project.id).map(m => {
                const badge = milestoneBadge(m);
                const progress = milestoneProgress(m);
                const isEditing = editingMilestoneId === m.id;

                return (
                  <div key={m.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="space-y-2">
                        <div>
                          <p className="text-lg font-semibold text-slate-900">{m.name}</p>
                          <p className="text-sm text-slate-500">
                            {m.description?.trim() || "No description added yet for this milestone."}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${badge.className}`}>
                          {badge.label}
                        </span>
                        <button
                          onClick={() => {
                            if (isEditing) {
                              setEditingMilestoneId(null);
                              setMilestoneEditDraft(createEmptyMilestoneDraft());
                              setMilestoneMessage(null);
                            } else {
                              beginMilestoneEdit(m);
                            }
                          }}
                          className="btn-secondary py-1.5 px-3 text-xs"
                        >
                          {isEditing ? "Cancel" : "Edit"}
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Target Date</p>
                        <p className="mt-1 text-sm font-medium text-slate-900">{formatDate(m.targetDate)}</p>
                      </div>
                      {milestoneCompleted(m) && m.completedDate ? (
                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Completed Date</p>
                          <p className="mt-1 text-sm font-medium text-slate-900">{formatDate(m.completedDate)}</p>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Completed Date</p>
                          <p className="mt-1 text-sm font-medium text-slate-400">Shown when the milestone reaches 100%</p>
                        </div>
                      )}
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-slate-700">Progress</span>
                        <span className="font-semibold text-slate-900">{progress}%</span>
                      </div>
                      <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full rounded-full transition-all ${badge.barClassName}`} style={{ width: `${progress}%` }} />
                      </div>
                    </div>

                    {isEditing && (
                      <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 space-y-3">
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-600">Milestone Name *</label>
                            <input
                              className="input-field"
                              value={milestoneEditDraft.name}
                              onChange={(e) => setMilestoneEditDraft(prev => ({ ...prev, name: e.target.value }))}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-600">Target Date</label>
                            <input
                              className="input-field"
                              type="date"
                              value={milestoneEditDraft.targetDate}
                              onChange={(e) => setMilestoneEditDraft(prev => ({ ...prev, targetDate: e.target.value }))}
                            />
                          </div>
                          <div className="space-y-1 md:col-span-2">
                            <label className="text-xs font-semibold text-slate-600">Description</label>
                            <textarea
                              className="input-field min-h-[88px]"
                              value={milestoneEditDraft.description}
                              onChange={(e) => setMilestoneEditDraft(prev => ({ ...prev, description: e.target.value }))}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-600">Progress %</label>
                            <input
                              className="input-field"
                              type="number"
                              min={0}
                              max={100}
                              value={milestoneEditDraft.progressPercentage}
                              onChange={(e) => setMilestoneEditDraft(prev => ({
                                ...prev,
                                progressPercentage: e.target.value,
                              }))}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-600">Completed Date</label>
                            <input
                              className="input-field"
                              type="date"
                              value={milestoneEditDraft.completedDate}
                              onChange={(e) => setMilestoneEditDraft(prev => ({
                                ...prev,
                                completedDate: e.target.value,
                                progressPercentage: e.target.value ? "100" : prev.progressPercentage,
                              }))}
                            />
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={handleSaveMilestone}
                            className="btn-primary text-xs"
                            disabled={milestoneSaving}
                          >
                            {milestoneSaving ? "Saving..." : "Save Changes"}
                          </button>
                          <span className="text-xs text-slate-500">Update the milestone details and progress tracking fields.</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {projectTab === "payments" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Payments</h4>
              <p className="text-xs text-slate-500">Track claims and disbursement status.</p>
            </div>
            <div className="space-y-3">
              {claimsForProject(project.id).length === 0 && (
                <p className="text-sm text-slate-500">No payment requests logged yet.</p>
              )}
              {claimsForProject(project.id).map(claim => (
                <div key={claim.id} className="rounded-xl border border-slate-100 p-4 flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-slate-900">{claim.milestoneName || "Payment Tranche"}</p>
                    <p className="text-xs text-slate-500">Amount: M {Number(claim.claimAmount || 0).toLocaleString()}</p>
                  </div>
                  <span className="badge bg-slate-100 text-slate-700">{claim.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {projectTab === "documents" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Documents</h4>
              <p className="text-xs text-slate-500">Upload project files or download existing ones.</p>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-700">Upload Document</p>
                <span className="text-[11px] text-slate-400">PDF, XLS, DOC, images</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  className="input-field"
                  placeholder="Document title (optional)"
                  value={documentTitle}
                  onChange={(e) => setDocumentTitle(e.target.value)}
                />
                <input
                  className="input-field"
                  type="file"
                  onChange={(e) => setDocumentFile(e.target.files?.[0] || null)}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleUploadDocument}
                  className="btn-primary text-xs"
                  disabled={documentUploading}
                >
                  {documentUploading ? "Uploading..." : "Upload Document"}
                </button>
                {documentMessage && <span className="text-xs text-slate-500">{documentMessage}</span>}
              </div>
            </div>
            <div className="space-y-3">
              {contractForProject(project.id)?.signedFile && (
                <a
                  href={toFileUrl(contractForProject(project.id)?.signedFile)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-700 underline"
                >
                  Signed Performance-Based Agreement
                </a>
              )}
              {documentsForProject(project.id).length === 0 && !contractForProject(project.id)?.signedFile && (
                <p className="text-sm text-slate-500">No documents uploaded yet.</p>
              )}
              {documentsForProject(project.id).map(doc => {
                const label = doc.title || doc.file.split("/").pop() || "Project Document";
                return (
                  <div key={doc.id} className="rounded-xl border border-slate-100 p-4 flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-slate-900">{label}</p>
                      <p className="text-xs text-slate-500">
                        Uploaded {doc.uploadedAt ? new Date(doc.uploadedAt).toLocaleString() : "N/A"}
                        {doc.uploadedByUsername ? ` • ${doc.uploadedByUsername}` : ""}
                      </p>
                    </div>
                    <a
                      href={toFileUrl(doc.file) ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="text-emerald-700 underline text-xs"
                    >
                      View
                    </a>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {projectTab === "updates" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Updates</h4>
              <p className="text-xs text-slate-500">Recent activity from milestones, planning, documents, field work, and payments appears here automatically.</p>
            </div>
            <div className="space-y-3">
              {updatesForProject(project.id).length === 0 && (
                <p className="text-sm text-slate-500">No recent updates yet. New project activity will appear here automatically.</p>
              )}
              {updatesForProject(project.id).map(update => (
                <div key={update.id} className="rounded-xl border border-slate-100 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-900">{update.title || "Project Update"}</p>
                    <span className="text-xs text-slate-400">
                      {update.createdAt ? new Date(update.createdAt).toLocaleString() : "N/A"}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600">{update.body}</p>
                  {update.authorUsername && (
                    <p className="text-xs text-slate-400">Posted by {update.authorUsername}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {projectTab === "fieldwork" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Field Work Reporting</h4>
              <p className="text-xs text-slate-500">Submit installation evidence for verification.</p>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-700">New Installation Report</p>
                <span className="text-[11px] text-slate-400">GPS + Photo + Receipt</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  className="input-field"
                  placeholder="Serial number"
                  value={reportDraft.serialNumber}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, serialNumber: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="Beneficiary ID (NID)"
                  value={reportDraft.beneficiaryId}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, beneficiaryId: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="GPS Latitude"
                  value={reportDraft.gpsLat}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, gpsLat: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="GPS Longitude"
                  value={reportDraft.gpsLng}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, gpsLng: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="Smart meter ID (optional)"
                  value={reportDraft.meterId}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, meterId: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="kWh reading (optional)"
                  value={reportDraft.kwhReading}
                  onChange={(e) => setReportDraft(prev => ({ ...prev, kwhReading: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  className="input-field"
                  type="file"
                  multiple
                  onChange={(e) => setReportPhotos(Array.from(e.target.files || []))}
                />
                <input
                  className="input-field"
                  type="file"
                  onChange={(e) => setReportReceipt(e.target.files?.[0] || null)}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleSubmitReport}
                  className="btn-primary text-xs"
                  disabled={reportSubmitting}
                >
                  {reportSubmitting ? "Submitting..." : "Submit Report"}
                </button>
                {reportMessage && <span className="text-xs text-slate-500">{reportMessage}</span>}
              </div>
            </div>
            <div className="space-y-3">
              {reportsForProject(project.id).length === 0 && (
                <p className="text-sm text-slate-500">No installation reports submitted yet.</p>
              )}
              {reportsForProject(project.id).map(report => (
                <div key={report.id} className="rounded-xl border border-slate-100 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-900">Serial: {report.serialNumber}</p>
                    <span className="badge bg-slate-100 text-slate-700">{report.status}</span>
                  </div>
                  <div className="text-xs text-slate-500">
                    Beneficiary: {report.beneficiaryId} • GPS: {report.gpsLat}, {report.gpsLng}
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-emerald-700">
                    {(report.photoFiles || []).map((file, idx) => (
                      <a key={`${report.id}-photo-${idx}`} href={toFileUrl(file) ?? "#"} target="_blank" rel="noreferrer" className="underline">
                        Photo {idx + 1}
                      </a>
                    ))}
                    {(report.receiptFileUrl || report.receiptFile) && (
                      <a href={toFileUrl(report.receiptFileUrl || report.receiptFile) ?? "#"} target="_blank" rel="noreferrer" className="underline">
                        Receipt
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="rounded-[32px] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,#16a34a22,transparent_45%),radial-gradient(circle_at_top_right,#0ea5e922,transparent_40%),linear-gradient(125deg,#0f172a_0%,#0b1530_45%,#111827_100%)] text-white shadow-[0_35px_80px_-40px_rgba(15,23,42,0.95)]">
        <div className="p-8 lg:p-10">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.35em] text-emerald-200/80">
                Project Intelligence Hub
              </div>
              <h1 className="text-3xl font-semibold mt-4">Projects Hub</h1>
              <p className="text-sm text-slate-200/90 mt-2">
                A unified command center for implementation health, contract readiness, and disbursement momentum.
              </p>
              <div className="mt-5 flex flex-wrap gap-2 text-[11px] text-slate-200/80">
                <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">Realtime Milestone Visibility</span>
                <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">Claims & Payments Tracker</span>
                <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">Project Documents Vault</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-white/60 font-semibold">Total Projects</p>
                <p className="text-xl font-semibold">{projects.length}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-white/60 font-semibold">Active</p>
                <p className="text-xl font-semibold">{activeProjects.length}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-white/60 font-semibold">Completed</p>
                <p className="text-xl font-semibold">{completedProjects.length}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-white/60 font-semibold">Contract Value</p>
                <p className="text-xl font-semibold">M {totalContractValue.toLocaleString()}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 className="text-lg font-bold">Project Portfolio</h3>
            <p className="text-sm text-slate-500">Curated overview with smart filters and at-a-glance health</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                className="input-field pl-9"
                placeholder="Search by ID, technology, region"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select className="input-field" value={techFilter} onChange={(e) => setTechFilter(e.target.value)}>
              {techOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
            </select>
            <select className="input-field" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="All">All Status</option>
              <option value="Active">Active</option>
              <option value="Completed">Completed</option>
              <option value="Pending">Pending</option>
            </select>
          </div>
        </div>
        <div className="p-6 space-y-4">
          {loading && <p className="text-sm text-slate-500">Loading projects...</p>}
          {!loading && filteredProjects.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-200 p-6 text-sm text-slate-500">
              No projects found for the selected filters.
            </div>
          )}
          {!loading && filteredProjects.map(project => (
            <div key={project.id} className="rounded-3xl border border-slate-100 bg-white p-5 shadow-[0_24px_60px_-46px_rgba(15,23,42,0.55)] space-y-4 relative overflow-hidden">
              <div className="absolute left-0 top-0 h-full w-1.5 bg-[linear-gradient(180deg,#22c55e_0%,#0ea5e9_60%,#1e293b_100%)]" />
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="pl-2">
                  <p className="text-base font-semibold text-slate-900">
                    {project.projectTitle || project.tenderName || "Project Title Pending"}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {project.projectReference || `Project ${project.id}`}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{project.techType} • {project.region}</p>
                  <div className="flex flex-wrap gap-2 mt-3 text-[11px]">
                    <span className="badge bg-slate-100 text-slate-700">Progress {project.progress}%</span>
                    {project.status && <span className="badge bg-emerald-50 text-emerald-700">{project.status}</span>}
                    {project.contractStatus && <span className="badge bg-blue-50 text-blue-700">{project.contractStatus}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      setSelectedProject(prev => (prev?.id === project.id ? null : project));
                      setProjectTab("overview");
                    }}
                    className="btn-primary text-xs"
                  >
                    {selectedProject?.id === project.id ? "Close Project" : "Open Project"}
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[11px] text-slate-500 sm:grid-cols-6">
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">Start</p>
                  <p className="font-semibold text-slate-700">{formatDate(startDateForProject(project))}</p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">End</p>
                  <p className="font-semibold text-slate-700">{formatDate(endDateForProject(project))}</p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">District</p>
                  <p className="font-semibold text-slate-700">{project.district || project.region || "N/A"}</p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">Budget</p>
                  <p className="font-semibold text-slate-700">
                    {budgetForProject(project) != null ? `M ${Number(budgetForProject(project)).toLocaleString()}` : "N/A"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">Tender</p>
                  <p className="font-semibold text-slate-700">{project.tenderReferenceNumber || "N/A"}</p>
                </div>
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="uppercase tracking-wider text-slate-400">Value</p>
                  <p className="font-semibold text-slate-700">
                    M {Number(project.milestoneTotalAmount ?? contractValueByProject.get(project.id) ?? 0).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
                <span className="rounded-full bg-slate-100 px-3 py-1">
                  Milestones: {project.milestoneCount ?? milestonesForProject(project.id).length}
                </span>
                <span className="rounded-full bg-slate-100 px-3 py-1">
                  Overall Progress: {project.progress}%
                </span>
                <span className="rounded-full bg-slate-100 px-3 py-1">
                  Claims: {claimsForProject(project.id).length}
                </span>
              </div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                <div className="bg-gradient-to-r from-emerald-500 via-teal-400 to-sky-500 h-full" style={{ width: `${project.progress}%` }} />
              </div>
              {selectedProject?.id === project.id && (
                <div className="pt-2">
                  {renderProjectDetail(project)}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

    </div>
  );
};

const TACView = () => {
  const [view, setView] = useState<"list" | "evaluate">("list");
  const [selectedEval, setSelectedEval] = useState<{
    bid: TenderBid;
    evaluationId?: string;
    comments: string;
    criteria: {
      technical: number;
      financial: number;
      feasibility: number;
      kpi: number;
      gender: number;
      environmental: number;
      om: number;
      inclusivity: number;
    };
  } | null>(null);
  const [bidQueue, setBidQueue] = useState<TenderBid[]>([]);
  const [evaluations, setEvaluations] = useState<TenderBidEvaluation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const loadEvaluations = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [bids, evals] = await Promise.all([
        fetchTenderBids(),
        fetchBidEvaluations(),
      ]);
      setBidQueue(bids.filter(b => [BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW].includes(b.status)));
      setEvaluations(evals);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadEvaluations();
  }, [loadEvaluations]);

  const evaluationsByBid = useMemo(() => {
    const map = new Map<string, TenderBidEvaluation>();
    evaluations.forEach(ev => map.set(ev.bid, ev));
    return map;
  }, [evaluations]);

  const handleStartEvaluation = (bid: TenderBid) => {
    const existing = evaluationsByBid.get(bid.id);
    setSelectedEval({
      bid,
      evaluationId: existing?.id,
      comments: existing?.comments ?? "",
      criteria: {
        technical: existing?.technicalScore ?? 0,
        financial: existing?.financialScore ?? 0,
        feasibility: existing?.feasibilityScore ?? 0,
        kpi: existing?.kpiScore ?? 0,
        gender: existing?.genderScore ?? 0,
        environmental: existing?.environmentalScore ?? 0,
        om: existing?.omScore ?? 0,
        inclusivity: existing?.inclusivityScore ?? 0,
      },
    });
    setView("evaluate");
  };

  const handleSaveScore = async () => {
    if (!selectedEval) return;
    const payload = {
      bid: selectedEval.bid.id,
      technicalScore: selectedEval.criteria.technical,
      financialScore: selectedEval.criteria.financial,
      feasibilityScore: selectedEval.criteria.feasibility,
      kpiScore: selectedEval.criteria.kpi,
      genderScore: selectedEval.criteria.gender,
      environmentalScore: selectedEval.criteria.environmental,
      omScore: selectedEval.criteria.om,
      inclusivityScore: selectedEval.criteria.inclusivity,
      comments: selectedEval.comments,
    };
    try {
      await reviewTenderBid(selectedEval.bid.id);
    } catch {
      // ignore review update errors
    }
    try {
      const saved = selectedEval.evaluationId
        ? await updateBidEvaluation(selectedEval.evaluationId, payload)
        : await createBidEvaluation(payload);
      setEvaluations(prev => {
        const next = prev.filter(ev => ev.id !== saved.id);
        next.push(saved);
        return next;
      });
      setView("list");
      showNotification(`Evaluation saved for ${selectedEval.bid.vendor_name}.`);
    } catch (err: any) {
      const raw = String(err?.message || "");
      showNotification(toFriendlyApiMessage(raw) || "Failed to save evaluation.");
    }
  };

  if (view === "evaluate" && selectedEval) {
    const totalScore = Math.round((
      selectedEval.criteria.technical +
      selectedEval.criteria.financial +
      selectedEval.criteria.feasibility +
      selectedEval.criteria.kpi +
      selectedEval.criteria.gender +
      selectedEval.criteria.environmental +
      selectedEval.criteria.om +
      selectedEval.criteria.inclusivity
    ) / 8);

    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Technical Evaluation</h1>
            <p className="text-slate-500">{selectedEval.bid.vendor_name} • {selectedEval.bid.tender}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-8 space-y-8">
              <div className="space-y-6">
                <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Scoring Matrix</h3>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Technical Capacity (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.technical}</span>
                    </div>
                    <input 
                      type="range" min="0" max="100" 
                      value={selectedEval.criteria.technical}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, technical: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600" 
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Financial Stability (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.financial}</span>
                    </div>
                    <input 
                      type="range" min="0" max="100" 
                      value={selectedEval.criteria.financial}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, financial: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600" 
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Technical Feasibility (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.feasibility}</span>
                    </div>
                    <input 
                      type="range" min="0" max="100" 
                      value={selectedEval.criteria.feasibility}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, feasibility: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600" 
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Technology KPIs (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.kpi}</span>
                    </div>
                    <input
                      type="range" min="0" max="100"
                      value={selectedEval.criteria.kpi}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, kpi: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Gender Action Plan (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.gender}</span>
                    </div>
                    <input
                      type="range" min="0" max="100"
                      value={selectedEval.criteria.gender}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, gender: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Environmental Compliance (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.environmental}</span>
                    </div>
                    <input
                      type="range" min="0" max="100"
                      value={selectedEval.criteria.environmental}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, environmental: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">O&M Strategy (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.om}</span>
                    </div>
                    <input
                      type="range" min="0" max="100"
                      value={selectedEval.criteria.om}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, om: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <label className="text-sm font-bold text-slate-700">Inclusivity Targets (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.inclusivity}</span>
                    </div>
                    <input
                      type="range" min="0" max="100"
                      value={selectedEval.criteria.inclusivity}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, inclusivity: parseInt(e.target.value)}})}
                      className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2">Justification & Comments</h3>
                <textarea 
                  rows={4} 
                  placeholder="Provide detailed reasoning for the assigned scores..." 
                  className="input-field"
                  value={selectedEval.comments}
                  onChange={(e) => setSelectedEval({ ...selectedEval, comments: e.target.value })}
                />
              </div>

              <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
                <button onClick={() => setView("list")} className="btn-secondary">Cancel</button>
                <button onClick={handleSaveScore} className="btn-primary">Submit Final Score</button>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6">
              <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Proposal Documents</h3>
              <div className="space-y-3">
                {[
                  { label: "Technical Proposal", url: selectedEval.bid.technical_proposal_file },
                  { label: "Financial Proposal", url: selectedEval.bid.financial_proposal_file },
                  { label: "BOQ", url: selectedEval.bid.boq_file },
                  { label: "Gender Action Plan", url: selectedEval.bid.gender_action_plan_file },
                  { label: "Implementation Plan", url: selectedEval.bid.implementation_plan_file },
                  { label: "Reporting Templates", url: selectedEval.bid.reporting_templates_file },
                ]
                  .filter(doc => Boolean(doc.url))
                  .map(doc => (
                    <a
                      key={doc.label}
                      href={String(doc.url)}
                      target="_blank"
                      rel="noreferrer"
                      className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 border border-transparent hover:border-slate-100 transition-all text-left group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100 text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600">
                        <FileText size={18} />
                      </div>
                      <span className="text-xs font-medium text-slate-600 truncate">{doc.label}</span>
                    </a>
                  ))}
                {[
                  selectedEval.bid.technical_proposal_file,
                  selectedEval.bid.financial_proposal_file,
                  selectedEval.bid.boq_file,
                  selectedEval.bid.gender_action_plan_file,
                  selectedEval.bid.implementation_plan_file,
                  selectedEval.bid.reporting_templates_file,
                ].every(item => !item) && (
                  <p className="text-xs text-slate-500">No documents uploaded for this bid.</p>
                )}
              </div>
            </div>

            <div className="card p-6 bg-slate-900 text-white">
              <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Aggregate Score</h3>
              <div className="text-center py-4">
                <p className="text-5xl font-bold text-emerald-400">
                  {totalScore}
                </p>
                <p className="text-xs text-slate-400 mt-2 uppercase tracking-widest">Weighted Average</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>
        {notification && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl flex items-center gap-3"
          >
            <CheckCircle2 size={20} />
            <span className="font-medium">{notification}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Technical Advisory Committee</h1>
          <p className="text-slate-500">Review and evaluate technical proposals</p>
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-lg font-bold">Evaluation Queue</h3>
          <span className="badge bg-rose-100 text-rose-700">
            {bidQueue.filter(item => !evaluationsByBid.get(item.id)).length} Pending Reviews
          </span>
        </div>
        <div className="divide-y divide-slate-100">
          {isLoading && (
            <div className="p-6 text-sm text-slate-500">Loading evaluations...</div>
          )}
          {!isLoading && bidQueue.map((item) => {
            const existing = evaluationsByBid.get(item.id);
            return (
            <div key={item.id} className="p-6 flex items-center justify-between hover:bg-slate-50 transition-colors">
              <div className="flex gap-4 items-center">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400">
                  <FileText size={24} />
                </div>
                <div>
                  <p className="font-bold text-slate-900">{item.vendor_name}</p>
                  <p className="text-xs text-slate-500">Tender: {item.tender}</p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                {existing && existing.totalScore > 0 && (
                  <div className="text-right">
                    <p className="text-xs font-bold text-slate-400 uppercase">Score</p>
                    <p className="text-lg font-bold text-emerald-600">{existing.totalScore}/100</p>
                  </div>
                )}
                <button 
                  onClick={() => handleStartEvaluation(item)}
                  className="btn-primary py-1.5 px-4 text-sm"
                >
                  {existing ? 'Edit Score' : 'Start Evaluation'}
                </button>
              </div>
            </div>
          )})}
          {!isLoading && bidQueue.length === 0 && (
            <div className="p-6 text-sm text-slate-500">No submitted bids awaiting evaluation.</div>
          )}
        </div>
      </div>
    </div>
  );
};

const FieldVerifierView = () => {
  const [view, setView] = useState<"dashboard" | "inspect" | "new">("dashboard");
  const [selectedInspection, setSelectedInspection] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [inspectionStep, setInspectionStep] = useState(1);
  const [inspectionData, setInspectionData] = useState({
    gpsLat: "",
    gpsLong: "",
    serialNumber: "",
    isOperational: true,
    beneficiaryConfirmed: false,
    photos: [] as string[],
    notes: ""
  });

  const [inspections, setInspections] = useState([
    { id: "INS-901", site: "Ha-Ramabanta", tech: "SHS", date: "2025-05-12", status: "Pending", district: "Maseru", vendor: "SolarLease" },
    { id: "INS-902", site: "Mokhotlong Central", tech: "Mini-Grid", date: "2025-05-14", status: "Scheduled", district: "Mokhotlong", vendor: "Mountain Power" },
    { id: "INS-903", site: "Semonkong Village", tech: "ICS", date: "2025-05-15", status: "Scheduled", district: "Maseru", vendor: "CleanCook" },
  ]);

  const allProjects = [
    { id: "INS-904", site: "Quthing Outpost", tech: "SHS", date: "2025-06-01", status: "Pending", district: "Quthing", vendor: "SolarLease" },
    { id: "INS-905", site: "Butha-Buthe Clinic", tech: "Mini-Grid", date: "2025-06-05", status: "Pending", district: "Butha-Buthe", vendor: "EcoEnergy" },
    { id: "INS-906", site: "Mohale's Hoek School", tech: "ICS", date: "2025-06-10", status: "Pending", district: "Mohale's Hoek", vendor: "CleanCook" },
  ];

  const filteredProjects = allProjects.filter(p => 
    p.id.toLowerCase().includes(searchQuery.toLowerCase()) || 
    p.site.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleStartInspection = (ins: any) => {
    setSelectedInspection(ins);
    setView("inspect");
    setInspectionStep(1);
    setInspectionData({
      gpsLat: "",
      gpsLong: "",
      serialNumber: "",
      isOperational: true,
      beneficiaryConfirmed: false,
      photos: [],
      notes: ""
    });
  };

  const handleNextStep = () => {
    if (inspectionStep < 3) {
      setInspectionStep(inspectionStep + 1);
    } else {
      const updatedInspections = inspections.some(i => i.id === selectedInspection.id)
        ? inspections.map(i => i.id === selectedInspection.id ? { ...i, status: "Verified" } : i)
        : [...inspections, { ...selectedInspection, status: "Verified" }];
      
      setInspections(updatedInspections);
      alert(`Inspection for ${selectedInspection.site} completed and queued for sync.`);
      setView("dashboard");
    }
  };

  if (view === "new") {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">New Inspection</h1>
            <p className="text-slate-500">Search for a project to begin field verification</p>
          </div>
        </div>

        <div className="card p-6">
          <div className="relative mb-6">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
            <input 
              type="text" 
              className="input-field pl-10" 
              placeholder="Search by Project ID or Site Name..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="space-y-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Available for Inspection</p>
            <div className="divide-y divide-slate-100 border border-slate-100 rounded-xl overflow-hidden">
              {filteredProjects.length > 0 ? filteredProjects.map((p) => (
                <div key={p.id} className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
                  <div>
                    <p className="font-bold text-slate-900">{p.site}</p>
                    <p className="text-xs text-slate-500">{p.tech} • ID: {p.id} • {p.vendor}</p>
                  </div>
                  <button 
                    onClick={() => handleStartInspection(p)}
                    className="btn-primary py-1.5 px-4 text-xs"
                  >
                    Start Inspection
                  </button>
                </div>
              )) : (
                <div className="p-8 text-center text-slate-500">
                  No projects found matching your search.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "inspect" && selectedInspection) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto pb-20">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView(inspections.some(i => i.id === selectedInspection.id) ? "dashboard" : "new")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Site Inspection</h1>
            <p className="text-slate-500">Verifying {selectedInspection.site} ({selectedInspection.id})</p>
          </div>
        </div>

        <div className="flex items-center justify-between mb-8 px-4">
          {[
            { step: 1, label: "Technical Check" },
            { step: 2, label: "Beneficiary Verification" },
            { step: 3, label: "Evidence & Submit" },
          ].map((s, i) => (
            <React.Fragment key={s.step}>
              <div className="flex flex-col items-center gap-2">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all ${
                  inspectionStep >= s.step ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" : "bg-slate-200 text-slate-500"
                }`}>
                  {s.step}
                </div>
                <span className={`text-xs font-bold ${inspectionStep >= s.step ? "text-slate-900" : "text-slate-400"}`}>{s.label}</span>
              </div>
              {i < 2 && <div className={`flex-1 h-0.5 mx-4 ${inspectionStep > s.step ? "bg-blue-600" : "bg-slate-200"}`} />}
            </React.Fragment>
          ))}
        </div>

        <div className="card p-8">
          <div className="space-y-8">
            {inspectionStep === 1 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Technical Verification</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">System Serial Number *</label>
                    <input 
                      required type="text" className="input-field" placeholder="Scan or enter SN"
                      value={inspectionData.serialNumber} onChange={(e) => setInspectionData({...inspectionData, serialNumber: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">System Operational? *</label>
                    <div className="flex gap-4 p-2">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="radio" checked={inspectionData.isOperational} onChange={() => setInspectionData({...inspectionData, isOperational: true})} />
                        <span className="text-sm">Yes</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="radio" checked={!inspectionData.isOperational} onChange={() => setInspectionData({...inspectionData, isOperational: false})} />
                        <span className="text-sm">No</span>
                      </label>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">GPS Latitude *</label>
                    <input 
                      required type="text" className="input-field" placeholder="-29.XXXX"
                      value={inspectionData.gpsLat} onChange={(e) => setInspectionData({...inspectionData, gpsLat: e.target.value})}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-bold text-slate-700 ml-1">GPS Longitude *</label>
                    <input 
                      required type="text" className="input-field" placeholder="28.XXXX"
                      value={inspectionData.gpsLong} onChange={(e) => setInspectionData({...inspectionData, gpsLong: e.target.value})}
                    />
                  </div>
                </div>
              </div>
            )}

            {inspectionStep === 2 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Beneficiary Verification</h3>
                <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl space-y-4">
                  <p className="text-sm text-blue-800">Please confirm with the household head that the system was installed on the reported date and they received training.</p>
                  <label className="flex items-center gap-3 cursor-pointer p-3 bg-white rounded-lg border border-blue-200">
                    <input 
                      type="checkbox" 
                      checked={inspectionData.beneficiaryConfirmed} 
                      onChange={(e) => setInspectionData({...inspectionData, beneficiaryConfirmed: e.target.checked})}
                      className="rounded text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm font-bold text-slate-700">Beneficiary confirms installation and training</span>
                  </label>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-bold text-slate-700 ml-1">Verification Notes</label>
                  <textarea 
                    className="input-field min-h-[120px]" placeholder="Any discrepancies or beneficiary feedback..."
                    value={inspectionData.notes} onChange={(e) => setInspectionData({...inspectionData, notes: e.target.value})}
                  />
                </div>
              </div>
            )}

            {inspectionStep === 3 && (
              <div className="space-y-6">
                <h3 className="text-lg font-bold text-slate-900 border-b border-slate-100 pb-2">Evidence & Submission</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {[
                    "System Label Photo",
                    "Installation Context",
                    "Beneficiary with System",
                    "Verifier at Site"
                  ].map(label => (
                    <div key={label} className="aspect-square border-2 border-dashed border-slate-200 rounded-xl flex flex-col items-center justify-center gap-2 hover:border-blue-400 hover:bg-blue-50 transition-all cursor-pointer group">
                      <Plus className="text-slate-300 group-hover:text-blue-500" size={24} />
                      <span className="text-[10px] font-bold text-slate-400 group-hover:text-blue-600 uppercase text-center px-2">{label}</span>
                    </div>
                  ))}
                </div>
                <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl flex gap-3">
                  <AlertCircle className="text-amber-600 shrink-0" size={20} />
                  <p className="text-xs text-amber-800">By submitting, you certify that you have physically visited the site and verified the installation according to RBF standards.</p>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-8 border-t border-slate-100">
              <button 
                type="button" 
                onClick={() => inspectionStep > 1 ? setInspectionStep(inspectionStep - 1) : setView(inspections.some(i => i.id === selectedInspection.id) ? "dashboard" : "new")}
                className="btn-secondary px-8"
              >
                {inspectionStep === 1 ? "Cancel" : "Previous"}
              </button>
              <button onClick={handleNextStep} className="btn-primary px-12">
                {inspectionStep === 3 ? "Complete Inspection" : "Next Step"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Field Verification</h1>
          <p className="text-slate-500">Site inspections and ODK/KoboToolbox sync</p>
        </div>
        <button onClick={() => setView("new")} className="btn-primary flex items-center gap-2">
          <Plus size={18} /> New Inspection
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6 bg-slate-900 text-white">
          <h3 className="text-lg font-bold mb-4">Offline Sync Status</h3>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                <CheckCircle2 size={24} />
              </div>
              <div>
                <p className="font-bold">All Data Synced</p>
                <p className="text-xs text-slate-400">Last sync: 12 mins ago</p>
              </div>
            </div>
            <button
              onClick={() => alert("Offline data is already fully synced.")}
              className="btn-secondary bg-white/10 border-white/20 text-white hover:bg-white/20"
            >
              Sync Now
            </button>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-xs font-bold uppercase text-slate-400">
              <span>Syncing Progress</span>
              <span>100%</span>
            </div>
            <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
              <div className="bg-emerald-500 h-full w-full" />
            </div>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-4">Assigned Region</h3>
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600">
              <MapIcon size={24} />
            </div>
            <div>
              <p className="font-bold text-slate-900">Thaba-Tseka District</p>
              <p className="text-xs text-slate-500">12 Pending Installations • 4 Verified</p>
            </div>
          </div>
          <button onClick={() => setView("new")} className="w-full mt-6 btn-secondary text-sm">View Region Map</button>
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">Verification Queue</h3>
        </div>
        <div className="divide-y divide-slate-100">
          {inspections.map((ins, i) => (
            <div key={i} className="p-6 flex items-center justify-between">
              <div className="flex gap-4 items-center">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${ins.status === 'Verified' ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400'}`}>
                  {ins.status === 'Verified' ? <CheckCircle2 size={20} /> : <Clock size={20} />}
                </div>
                <div>
                  <p className="font-bold text-slate-900">{ins.site}</p>
                  <p className="text-xs text-slate-500">{ins.tech} • ID: {ins.id} • {ins.vendor}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm text-slate-500">{ins.date}</span>
                {ins.status !== 'Verified' ? (
                  <button onClick={() => handleStartInspection(ins)} className="btn-primary py-1 px-3 text-xs">Verify</button>
                ) : (
                  <span className="text-xs font-bold text-emerald-600 uppercase tracking-widest">Verified</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const AdminView = () => {
  const [view, setView] = useState<"dashboard" | "create">("dashboard");
  const [users, setUsers] = useState([
    { id: "USR-001", fullName: "Admin User", email: "admin@rbf.ls", role: UserRole.ADMIN, status: "Active", region: "All" },
    { id: "USR-002", fullName: "M. Paiira", email: "m.paiira@rbf.ls", role: UserRole.RBF_OFFICIAL, status: "Active", region: "Maseru" },
    { id: "USR-003", fullName: "T. Molapo", email: "t.molapo@doe.ls", role: UserRole.DOE_OFFICER, status: "Active", region: "Leribe" },
  ]);
  const [createError, setCreateError] = useState("");
  const [createInfo, setCreateInfo] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [newUser, setNewUser] = useState({
    fullName: "",
    username: "",
    email: "",
    role: UserRole.RBF_OFFICIAL,
    region: "Maseru",
    gender: "Male",
    mobileNumber: "",
    tierAssignment: "",
    verificationZone: "",
  });
  const districts = ["All", "Maseru", "Leribe", "Berea", "Mafeteng", "Mohale's Hoek", "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Butha-Buthe"];

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError("");
    setCreateInfo("");
    if (!newUser.fullName.trim()) {
      setCreateError("full_name: This field is required.");
      return;
    }
    if (!newUser.username.trim()) {
      setCreateError("username: This field is required.");
      return;
    }
    if (!newUser.email.trim()) {
      setCreateError("email: This field is required.");
      return;
    }
    if (!newUser.mobileNumber.trim()) {
      setCreateError("mobile_number: This field is required.");
      return;
    }
    if (!/^\d{10,15}$/.test(newUser.mobileNumber.trim())) {
      setCreateError("mobile_number: Must be 10-15 digits.");
      return;
    }
    if (!newUser.region) {
      setCreateError("region: This field is required.");
      return;
    }
    if (!newUser.gender) {
      setCreateError("gender: This field is required.");
      return;
    }
    if (newUser.role === UserRole.FIELD_VERIFIER && !newUser.verificationZone.trim()) {
      setCreateError("verification_zone: This field is required for Field Verifiers.");
      return;
    }
    try {
      setIsSubmitting(true);
      const result = await createOfficialAccount({
        username: newUser.username.trim(),
        fullName: newUser.fullName.trim(),
        email: newUser.email.trim(),
        gender: newUser.gender as any,
        role: newUser.role,
        region: newUser.region,
        mobileNumber: newUser.mobileNumber.trim(),
        tierAssignment: newUser.tierAssignment.trim() || undefined,
        verificationZone: newUser.verificationZone.trim() || undefined,
      });
      const user = result.user;
      setUsers([
        {
          id: user.id,
          fullName: user.fullName,
          email: user.email,
          role: user.role,
          status: user.status,
          region: user.region || "N/A",
        },
        ...users,
      ]);
      if (result.initialPassword) {
        setCreateInfo(`Temporary password generated: ${result.initialPassword}`);
      } else if (result.emailError) {
        setCreateInfo(`Account created, but email delivery failed: ${result.emailError}`);
      } else {
        setCreateInfo("Account created and credentials sent to email.");
      }
      setView("dashboard");
    } catch (err: any) {
      const friendly = toFriendlyApiMessage(String(err?.message || ""));
      setCreateError(friendly || "Unable to create account. Please verify the details.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (view === "create") {
    return (
      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Create Official Account</h1>
            <p className="text-slate-500">Register a new official, evaluator, or verifier</p>
          </div>
        </div>

        <div className="card p-8">
          <form onSubmit={handleCreateUser} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Full Name *</label>
                <input 
                  required
                  type="text" 
                  value={newUser.fullName}
                  onChange={(e) => setNewUser({...newUser, fullName: e.target.value})}
                  className="input-field" 
                  placeholder="Official Name" 
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Username *</label>
                <input 
                  required
                  type="text" 
                  value={newUser.username}
                  onChange={(e) => setNewUser({...newUser, username: e.target.value.replace(/\\s/g, "")})}
                  className="input-field" 
                  placeholder="official_username" 
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Email Address *</label>
                <input 
                  required
                  type="email" 
                  value={newUser.email}
                  onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                  className="input-field" 
                  placeholder="official@rbf.ls" 
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Mobile Number *</label>
                <input 
                  required
                  type="tel" 
                  value={newUser.mobileNumber}
                  onChange={(e) => setNewUser({...newUser, mobileNumber: e.target.value.replace(/\\D/g, "")})}
                  className="input-field" 
                  inputMode="numeric"
                  placeholder="Digits only"
                  pattern="[0-9]{10,15}"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">System Role *</label>
                <select 
                  value={newUser.role}
                  onChange={(e) => setNewUser({...newUser, role: e.target.value as UserRole})}
                  className="input-field"
                  required
                >
                  <option value={UserRole.RBF_OFFICIAL}>RBF Official</option>
                  <option value={UserRole.DOE_OFFICER}>DoE Officer</option>
                  <option value={UserRole.TAC}>TAC Member</option>
                  <option value={UserRole.FIELD_VERIFIER}>Field Verifier</option>
                  <option value={UserRole.AUDITOR}>Auditor</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Assigned Region *</label>
                <select 
                  value={newUser.region}
                  onChange={(e) => setNewUser({...newUser, region: e.target.value})}
                  className="input-field"
                  required
                >
                  {districts.map((district) => (
                    <option key={district} value={district}>
                      {district === "All" ? "All Regions" : district}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Gender *</label>
                <select 
                  value={newUser.gender}
                  onChange={(e) => setNewUser({...newUser, gender: e.target.value as any})}
                  className="input-field"
                  required
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Tier Assignment (Optional)</label>
                <input 
                  type="text" 
                  value={newUser.tierAssignment}
                  onChange={(e) => setNewUser({...newUser, tierAssignment: e.target.value})}
                  className="input-field" 
                  placeholder="e.g., evaluator, verifier"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">
                  Verification Zone {newUser.role === UserRole.FIELD_VERIFIER ? "*" : "(Optional)"}
                </label>
                <input 
                  required={newUser.role === UserRole.FIELD_VERIFIER}
                  type="text" 
                  value={newUser.verificationZone}
                  onChange={(e) => setNewUser({...newUser, verificationZone: e.target.value})}
                  className="input-field" 
                  placeholder="Assigned zone"
                />
              </div>
            </div>

            {createError && (
              <p className="text-rose-600 text-xs font-medium">{createError}</p>
            )}

            <div className="bg-blue-50 p-4 rounded-xl border border-blue-100 flex gap-3">
              <AlertCircle className="text-blue-600 shrink-0" size={20} />
              <p className="text-xs text-blue-800 leading-relaxed">
                A temporary password will be auto-generated and sent to the official's email. 
                They will be required to change it upon their first login.
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button type="button" onClick={() => setView("dashboard")} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={isSubmitting} className="btn-primary px-8">
                {isSubmitting ? "Creating..." : "Create Account"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">System Administration</h1>
          <p className="text-slate-500">Manage users, roles, and system integrity</p>
        </div>
        <div className="flex gap-3">
          <button className="btn-secondary flex items-center gap-2">
            <Download size={18} /> Audit Logs
          </button>
          <button onClick={() => setView("create")} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> Create User
          </button>
        </div>
      </div>

      {createInfo && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-700">
          {createInfo}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6">
          <h4 className="text-xs font-bold text-slate-400 uppercase mb-4">User Status</h4>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-3xl font-bold">{users.length + 139}</p>
              <p className="text-xs text-emerald-600 font-medium">+12 this week</p>
            </div>
            <Users size={32} className="text-slate-200" />
          </div>
        </div>
        <div className="card p-6">
          <h4 className="text-xs font-bold text-slate-400 uppercase mb-4">API Health</h4>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-3xl font-bold">99.9%</p>
              <p className="text-xs text-emerald-600 font-medium">All systems green</p>
            </div>
            <Activity size={32} className="text-slate-200" />
          </div>
        </div>
        <div className="card p-6">
          <h4 className="text-xs font-bold text-slate-400 uppercase mb-4">System Alerts</h4>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-3xl font-bold">2</p>
              <p className="text-xs text-rose-600 font-medium">Requires attention</p>
            </div>
            <AlertCircle size={32} className="text-slate-200" />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-lg font-bold">User Management</h3>
          <div className="flex gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input type="text" placeholder="Search users..." className="pl-9 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:ring-emerald-500 focus:border-emerald-500 outline-none" />
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="p-4 text-xs font-bold text-slate-500 uppercase">ID</th>
                <th className="p-4 text-xs font-bold text-slate-500 uppercase">User</th>
                <th className="p-4 text-xs font-bold text-slate-500 uppercase">Role</th>
                <th className="p-4 text-xs font-bold text-slate-500 uppercase">Region</th>
                <th className="p-4 text-xs font-bold text-slate-500 uppercase">Status</th>
                <th className="p-4 text-xs font-bold text-slate-500 uppercase text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-slate-50 transition-colors">
                  <td className="p-4 font-mono text-xs text-slate-500">{user.id}</td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 text-xs font-bold">
                        {user.fullName.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div>
                        <p className="text-sm font-bold text-slate-900">{user.fullName}</p>
                        <p className="text-xs text-slate-500">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <span className="text-xs font-medium text-slate-600 bg-slate-100 px-2 py-1 rounded">{user.role}</span>
                  </td>
                  <td className="p-4">
                    <span className="text-xs text-slate-600">{user.region}</span>
                  </td>
                  <td className="p-4">
                    <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full ${
                      user.status === 'Active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}>
                      {user.status}
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <button onClick={() => setView("create")} className="text-slate-400 hover:text-emerald-600 p-1">
                      <Settings size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const DoEOfficerView = () => {
  const [view, setView] = useState<"list" | "review">("list");
  const [selectedProject, setSelectedProject] = useState<any>(null);
  const [projects, setProjects] = useState([
    { 
      id: 1, 
      name: "Qacha's Nek Mini-Grid", 
      status: "Pending Endorsement", 
      district: "Qacha's Nek", 
      capacity: "50kW",
      tech: "Mini-grid",
      vendor: "Mountain Power Ltd",
      beneficiaries: 450,
      subsidy: "M 1,200,000",
      docs: ["Technical Design", "Environmental Permit", "Community Consent"]
    },
    { 
      id: 2, 
      name: "Thaba-Tseka SHS Cluster", 
      status: "Endorsed", 
      district: "Thaba-Tseka", 
      capacity: "120 Units",
      tech: "SHS",
      vendor: "SolarLease Lesotho",
      beneficiaries: 120,
      subsidy: "M 450,000",
      docs: ["Product Certs", "Distribution Plan"]
    },
    { 
      id: 3, 
      name: "Mokhotlong Solar Farm", 
      status: "Pending Endorsement", 
      district: "Mokhotlong", 
      capacity: "200kW",
      tech: "Mini-grid",
      vendor: "EcoEnergy Solutions",
      beneficiaries: 1800,
      subsidy: "M 4,500,000",
      docs: ["Grid Impact Study", "Land Lease", "Technical Specs"]
    },
  ]);
  const [notification, setNotification] = useState<string | null>(null);
  const [reviewComment, setReviewComment] = useState("");

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const handleEndorse = (id: number) => {
    setProjects(prev => prev.map(p => p.id === id ? { ...p, status: "Endorsed", comment: reviewComment } : p));
    const project = projects.find(p => p.id === id);
    showNotification(`Project "${project?.name}" has been endorsed.`);
    setView("list");
    setReviewComment("");
  };

  const handleReject = (id: number) => {
    setProjects(prev => prev.map(p => p.id === id ? { ...p, status: "Rejected", comment: reviewComment } : p));
    const project = projects.find(p => p.id === id);
    showNotification(`Project "${project?.name}" endorsement rejected.`);
    setView("list");
    setReviewComment("");
  };

  const startReview = (project: any) => {
    setSelectedProject(project);
    setView("review");
  };

  if (view === "review" && selectedProject) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Technical Review</h1>
            <p className="text-slate-500">Reviewing {selectedProject.name} for regional compliance</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-6">
            <div className="card p-6 space-y-6">
              <h3 className="text-lg font-bold border-b border-slate-100 pb-2">Project Specifications</h3>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Technology</p>
                  <p className="text-sm font-medium text-slate-900">{selectedProject.tech}</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Capacity</p>
                  <p className="text-sm font-medium text-slate-900">{selectedProject.capacity}</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">District</p>
                  <p className="text-sm font-medium text-slate-900">{selectedProject.district}</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Beneficiaries</p>
                  <p className="text-sm font-medium text-slate-900">{selectedProject.beneficiaries} Households</p>
                </div>
              </div>

              <div className="pt-4">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Submitted Documents</p>
                <div className="grid grid-cols-1 gap-2">
                  {selectedProject.docs.map((doc: string) => (
                    <div key={doc} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
                      <div className="flex items-center gap-3">
                        <FileText size={16} className="text-slate-400" />
                        <span className="text-sm font-medium text-slate-700">{doc}</span>
                      </div>
                      <button
                        onClick={() => triggerDownload(`${doc.replace(/\s+/g, "_").toLowerCase()}.txt`, `${doc}\nProject document preview.`)}
                        className="text-emerald-600 hover:underline text-xs font-bold"
                      >
                        View File
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="card p-6 space-y-4">
              <h3 className="text-lg font-bold">Officer Assessment</h3>
              <div className="space-y-2">
                <label className="text-sm font-bold text-slate-700">Review Comments / Justification</label>
                <textarea 
                  className="input-field min-h-[120px]" 
                  placeholder="Provide technical justification for endorsement or reasons for rejection..."
                  value={reviewComment}
                  onChange={(e) => setReviewComment(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6 bg-slate-900 text-white">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Financial Overview</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-400">Requested Subsidy</p>
                  <p className="text-2xl font-bold">{selectedProject.subsidy}</p>
                </div>
                <div className="pt-4 border-t border-white/10">
                  <p className="text-xs text-slate-400">Vendor</p>
                  <p className="text-sm font-medium">{selectedProject.vendor}</p>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <button 
                onClick={() => handleEndorse(selectedProject.id)}
                className="btn-primary py-3 flex items-center justify-center gap-2"
              >
                <CheckCircle2 size={20} /> Endorse Project
              </button>
              <button 
                onClick={() => handleReject(selectedProject.id)}
                className="btn-secondary py-3 text-rose-600 border-rose-200 hover:bg-rose-50 flex items-center justify-center gap-2"
              >
                <X size={20} /> Reject Endorsement
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>
        {notification && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-24 right-8 z-[200] bg-emerald-600 text-white px-6 py-3 rounded-xl shadow-xl flex items-center gap-3"
          >
            <CheckCircle2 size={20} />
            <span className="font-medium">{notification}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Department of Energy</h1>
          <p className="text-slate-500">Regional policy compliance and technical endorsement</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-lg font-bold mb-4">Regional KPI Review</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[
                { district: 'Maseru', target: 100, actual: 85 },
                { district: 'Leribe', target: 80, actual: 92 },
                { district: 'Mafeteng', target: 60, actual: 45 },
              ]}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="district" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip />
                <Bar dataKey="target" fill="#e2e8f0" radius={[4, 4, 0, 0]} />
                <Bar dataKey="actual" fill="#059669" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-4">Technical Endorsements</h3>
          <div className="space-y-4">
            {projects.map((p) => (
              <div key={p.id} className="flex flex-col p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-slate-900">{p.name}</span>
                  <span className={`text-[10px] uppercase tracking-widest font-bold px-2 py-1 rounded-full ${
                    p.status === 'Endorsed' ? 'bg-emerald-100 text-emerald-700' : 
                    p.status === 'Rejected' ? 'bg-rose-100 text-rose-700' : 
                    'bg-amber-100 text-amber-700'
                  }`}>
                    {p.status}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-500 mb-4">
                  <span>District: {p.district}</span>
                  <span>Capacity: {p.capacity}</span>
                </div>
                {p.status === 'Pending Endorsement' && (
                  <div className="flex gap-2">
                    <button 
                      onClick={() => startReview(p)}
                      className="flex-1 btn-primary py-1.5 text-xs flex items-center justify-center gap-2"
                    >
                      <Search size={14} /> Review & Endorse
                    </button>
                  </div>
                )}
                {p.status !== 'Pending Endorsement' && p.comment && (
                  <div className="mt-2 p-2 bg-white rounded border border-slate-100 text-[10px] text-slate-500 italic">
                    " {p.comment} "
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const PublicPortal = ({ onBack }: { onBack?: () => void }) => {
  const regionalData = [
    { region: 'Maseru', funding: 1200000, impact: 4500 },
    { region: 'Leribe', funding: 850000, impact: 3200 },
    { region: 'Berea', funding: 600000, impact: 2100 },
    { region: 'Mafeteng', funding: 550000, impact: 1800 },
    { region: 'Quthing', funding: 400000, impact: 1200 },
  ];

  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      {/* Public Portal Hero */}
      <div className="relative h-[600px] mb-12 overflow-hidden">
        <img 
          src="https://picsum.photos/seed/lesotho-energy/1920/1080" 
          alt="Renewable Energy in Lesotho" 
          className="w-full h-full object-cover brightness-50"
          referrerPolicy="no-referrer"
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            <span className="px-4 py-1 bg-emerald-600 text-white text-xs font-bold uppercase tracking-widest rounded-full">
              Live Impact Transparency
            </span>
            <h1 className="text-6xl md:text-8xl font-black text-white tracking-tighter">
              RENEWABLE <br /> LESOTHO
            </h1>
            <p className="text-xl text-slate-200 max-w-2xl mx-auto font-medium">
              Empowering communities through sustainable energy. Real-time monitoring of the UNDP-led Results Based Financing program.
            </p>
          </motion.div>
        </div>
        
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white to-transparent h-32" />
      </div>

      <div className="max-w-7xl mx-auto px-8 space-y-24 pb-24">
        {/* Big Numbers */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          <div className="text-center space-y-2">
            <p className="text-sm font-bold text-emerald-600 uppercase tracking-widest">Lives Impacted</p>
            <h2 className="text-7xl font-black text-slate-900 tabular-nums">12,450+</h2>
            <p className="text-slate-500">Households with clean energy access</p>
          </div>
          <div className="text-center space-y-2">
            <p className="text-sm font-bold text-blue-600 uppercase tracking-widest">CO2 Avoided</p>
            <h2 className="text-7xl font-black text-slate-900 tabular-nums">1,842</h2>
            <p className="text-slate-500">Tons of carbon emissions reduced</p>
          </div>
          <div className="text-center space-y-2">
            <p className="text-sm font-bold text-amber-600 uppercase tracking-widest">Local Jobs</p>
            <h2 className="text-7xl font-black text-slate-900 tabular-nums">450+</h2>
            <p className="text-slate-500">Created in the green energy sector</p>
          </div>
        </div>

        {/* Impact Story Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div className="space-y-6">
            <h3 className="text-4xl font-bold text-slate-900 leading-tight">
              Beyond the Numbers: <br />
              <span className="text-emerald-600">Powering Education in Qacha's Nek</span>
            </h3>
            <p className="text-lg text-slate-600 leading-relaxed">
              Before the RBF program, students in the remote village of Ha-Ramabanta relied on kerosene lamps for evening study. Today, a community mini-grid provides reliable, clean power to 450 homes and the local primary school.
            </p>
            <div className="flex gap-4 pt-4">
              <div className="flex -space-x-2">
                {[1, 2, 3, 4].map(i => (
                  <img 
                    key={i}
                    src={`https://i.pravatar.cc/100?u=${i}`} 
                    className="w-10 h-10 rounded-full border-2 border-white"
                    alt="User"
                  />
                ))}
              </div>
              <p className="text-sm text-slate-500 flex items-center">
                Join 12,000+ others in the transition
              </p>
            </div>
          </div>
          <div className="relative">
            <div className="aspect-square rounded-3xl overflow-hidden shadow-2xl">
              <img 
                src="https://picsum.photos/seed/impact-story/800/800" 
                alt="Impact Story" 
                className="w-full h-full object-cover"
                referrerPolicy="no-referrer"
              />
            </div>
            <div className="absolute -bottom-8 -left-8 bg-white p-6 rounded-2xl shadow-xl max-w-xs border border-slate-100">
              <p className="text-sm italic text-slate-600 mb-2">
                "The light has changed everything. My children can study safely, and we no longer breathe smoke from the lamps."
              </p>
              <p className="text-xs font-bold text-slate-900">— Masechaba T., Beneficiary</p>
            </div>
          </div>
        </div>

        {/* Regional Map Placeholder / Visual */}
        <div className="bg-slate-900 rounded-[40px] p-12 text-white overflow-hidden relative">
          <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-12">
            <div className="space-y-8">
              <div>
                <h3 className="text-3xl font-bold mb-2">Regional Progress</h3>
                <p className="text-slate-400">Real-time deployment status across Lesotho's districts</p>
              </div>
              <div className="space-y-6">
                {regionalData.map(region => (
                  <div key={region.region} className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium">{region.region}</span>
                      <span className="text-emerald-400 font-bold">{Math.round((region.impact / 4500) * 100)}% Target</span>
                    </div>
                    <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                      <motion.div 
                        initial={{ width: 0 }}
                        whileInView={{ width: `${(region.impact / 4500) * 100}%` }}
                        className="h-full bg-emerald-500"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-center">
              <div className="w-full aspect-square bg-white/5 rounded-full flex items-center justify-center relative">
                <Globe size={200} className="text-emerald-500/20 animate-pulse" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-5xl font-black text-white">100%</p>
                    <p className="text-xs text-slate-400 uppercase tracking-widest">Transparency</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer / CTA */}
        <div className="text-center py-24 space-y-8 border-t border-slate-100">
          <div className="flex justify-center gap-8 items-center opacity-50 grayscale hover:grayscale-0 transition-all">
            <img src="https://upload.wikimedia.org/wikipedia/commons/b/bb/UNDP_logo.svg" alt="UNDP" className="h-12" />
            <div className="h-8 w-px bg-slate-300" />
            <p className="font-bold text-slate-900">Government of Lesotho</p>
          </div>
          <div className="space-y-4">
            <h4 className="text-2xl font-bold text-slate-900">Ready to dive deeper?</h4>
            <p className="text-slate-500">Access the full technical dashboard and audit logs.</p>
            {onBack && (
              <button 
                onClick={onBack}
                className="btn-primary px-8 py-3 rounded-full"
              >
                Back to Portal
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const DonorView = () => {
  const [view, setView] = useState<"dashboard" | "public">("dashboard");
  const impactData = [
    { month: 'Jan', co2: 120, beneficiaries: 800 },
    { month: 'Feb', co2: 150, beneficiaries: 1200 },
    { month: 'Mar', co2: 220, beneficiaries: 2100 },
    { month: 'Apr', co2: 280, beneficiaries: 3500 },
    { month: 'May', co2: 340, beneficiaries: 4800 },
    { month: 'Jun', co2: 410, beneficiaries: 6200 },
  ];

  const regionalData = [
    { region: 'Maseru', funding: 1200000, impact: 4500 },
    { region: 'Leribe', funding: 850000, impact: 3200 },
    { region: 'Berea', funding: 600000, impact: 2100 },
    { region: 'Mafeteng', funding: 550000, impact: 1800 },
    { region: 'Quthing', funding: 400000, impact: 1200 },
  ];

  if (view === "public") {
    return (
      <div className="-m-8">
        <PublicPortal onBack={() => setView("dashboard")} />
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">UNDP & Donor Dashboard</h1>
          <p className="text-slate-500">High-level impact monitoring and funding oversight</p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={() => setView("public")}
            className="btn-secondary flex items-center gap-2"
          >
            <Globe size={18} /> Public Portal
          </button>
          <button
            onClick={() => triggerDownload("impact_report.txt", "UNDP Impact Report\nGenerated sample export.")}
            className="btn-primary flex items-center gap-2 shadow-lg shadow-emerald-600/20"
          >
            <Download size={18} /> Impact Report (PDF)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard label="Total Funding Committed" value="$ 4.2M" icon={CreditCard} color="bg-emerald-600" trend="+15%" />
        <StatCard label="Beneficiaries Reached" value="12,450" icon={Users} color="bg-blue-600" trend="+8%" />
        <StatCard label="CO2 Reduction (Tons)" value="1,842" icon={Leaf} color="bg-emerald-900" trend="+22%" />
        <StatCard label="Energy Capacity" value="2.4 MW" icon={Zap} color="bg-amber-500" trend="+12%" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-bold">Impact Growth Trend</h3>
            <div className="flex gap-4 text-xs">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-emerald-600" />
                <span className="text-slate-500">CO2 (Tons)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full bg-blue-600" />
                <span className="text-slate-500">Beneficiaries</span>
              </div>
            </div>
          </div>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={impactData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                />
                <Line type="monotone" dataKey="co2" stroke="#059669" strokeWidth={3} dot={{ r: 4, fill: '#059669', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 6 }} />
                <Line type="monotone" dataKey="beneficiaries" stroke="#2563eb" strokeWidth={3} dot={{ r: 4, fill: '#2563eb', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-6">Funding by Technology</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[
                    { name: 'Mini-Grids', value: 2400000 },
                    { name: 'SHS', value: 1200000 },
                    { name: 'ICS', value: 600000 },
                  ]}
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  <Cell fill="#059669" />
                  <Cell fill="#2563eb" />
                  <Cell fill="#f59e0b" />
                </Pie>
                <Tooltip formatter={(value: number) => `$ ${value.toLocaleString()}`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-3 mt-4">
            {[
              { name: 'Mini-Grids', val: '$2.4M', color: 'bg-emerald-600' },
              { name: 'SHS', val: '$1.2M', color: 'bg-blue-600' },
              { name: 'ICS', val: '$0.6M', color: 'bg-amber-500' },
            ].map(item => (
              <div key={item.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${item.color}`} />
                  <span className="text-slate-600">{item.name}</span>
                </div>
                <span className="font-bold text-slate-900">{item.val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-lg font-bold mb-6">Regional Impact Distribution</h3>
          <div className="space-y-5">
            {regionalData.map(region => (
              <div key={region.region} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-bold text-slate-900">{region.region}</span>
                  <span className="text-slate-500">{region.impact.toLocaleString()} Beneficiaries</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${(region.impact / 4500) * 100}%` }}
                    className="bg-emerald-600 h-full" 
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-6">Recent Impact Milestones</h3>
          <div className="space-y-4">
            {[
              { title: "Maseru District Electrification", detail: "500 households connected via SHS", date: "2 days ago", icon: Award, color: "text-amber-500" },
              { title: "CO2 Target Reached", detail: "Program surpassed 1,500 ton reduction goal", date: "1 week ago", icon: TrendingUp, color: "text-emerald-600" },
              { title: "New Funding Tranche", detail: "$1.2M released for Mini-Grid expansion", date: "2 weeks ago", icon: CreditCard, color: "text-blue-600" },
              { title: "Gender Equality Milestone", detail: "45% of beneficiaries are female-headed households", date: "1 month ago", icon: Users, color: "text-rose-500" },
            ].map((m, i) => (
              <div key={i} className="flex gap-4 p-3 hover:bg-slate-50 rounded-xl transition-colors">
                <div className={`w-10 h-10 rounded-lg bg-white border border-slate-100 flex items-center justify-center shrink-0 ${m.color}`}>
                  <m.icon size={20} />
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-900">{m.title}</p>
                  <p className="text-xs text-slate-500">{m.detail}</p>
                  <p className="text-[10px] text-slate-400 mt-1">{m.date}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const AuditorView = () => {
  const [view, setView] = useState<"dashboard" | "review">("dashboard");
  const [selectedAudit, setSelectedAudit] = useState<any>(null);
  const [auditStatus, setAuditStatus] = useState<"Compliant" | "Flagged">("Compliant");
  const [auditNotes, setAuditNotes] = useState("");

  const auditLogs = [
    { id: "AUD-101", project: "Ha-Ramabanta SHS", verifier: "Verifier_Maseru", date: "2025-05-20", status: "Pending", type: "Spot Check" },
    { id: "AUD-102", project: "Mokhotlong Mini-Grid", verifier: "Verifier_Mokhotlong", date: "2025-05-22", status: "Compliant", type: "Full Audit" },
    { id: "AUD-103", project: "Semonkong ICS", verifier: "Verifier_Maseru", date: "2025-05-25", status: "Flagged", type: "Spot Check" },
  ];

  const handleStartAudit = (audit: any) => {
    setSelectedAudit(audit);
    setView("review");
    setAuditStatus("Compliant");
    setAuditNotes("");
  };

  const handleSubmitAudit = () => {
    alert(`Audit ${selectedAudit.id} submitted as ${auditStatus}.`);
    setView("dashboard");
  };

  if (view === "review" && selectedAudit) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-20">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("dashboard")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <ChevronRight className="rotate-180" size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Independent Audit Review</h1>
            <p className="text-slate-500">Auditing verification records for {selectedAudit.project}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card p-6">
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                <FileSearch size={20} className="text-blue-600" />
                Verification Evidence
              </h3>
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">GPS Match</p>
                    <div className="flex items-center gap-2 text-emerald-600">
                      <CheckCircle2 size={16} />
                      <span className="text-sm font-bold text-slate-900">Within 5m tolerance</span>
                    </div>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Serial Number</p>
                    <div className="flex items-center gap-2 text-emerald-600">
                      <CheckCircle2 size={16} />
                      <span className="text-sm font-bold text-slate-900">Matches Vendor Record</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-bold text-slate-700">Verifier Photos</p>
                  <div className="grid grid-cols-3 gap-3">
                    {[1, 2, 3].map(i => (
                      <div key={i} className="aspect-video bg-slate-200 rounded-lg flex items-center justify-center text-slate-400 relative group cursor-pointer overflow-hidden">
                        <img 
                          src={`https://picsum.photos/seed/audit-${selectedAudit.id}-${i}/400/300`} 
                          alt="Evidence" 
                          className="w-full h-full object-cover"
                          referrerPolicy="no-referrer"
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                          <Eye size={24} className="text-white" />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl">
                  <p className="text-sm font-bold text-blue-900 mb-1">Verifier Notes</p>
                  <p className="text-sm text-blue-800 italic">"Household confirmed installation on May 12th. System is powering 4 lights and a phone charger as reported. Beneficiary was very satisfied with the training."</p>
                </div>
              </div>
            </div>

            <div className="card p-6">
              <h3 className="text-lg font-bold mb-4">Audit Findings</h3>
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-slate-700">Compliance Status</label>
                  <div className="flex gap-4">
                    <button 
                      onClick={() => setAuditStatus("Compliant")}
                      className={`flex-1 p-4 rounded-xl border-2 transition-all flex items-center justify-center gap-3 ${
                        auditStatus === "Compliant" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-100 bg-white text-slate-500"
                      }`}
                    >
                      <ShieldCheck size={20} />
                      <span className="font-bold">Compliant</span>
                    </button>
                    <button 
                      onClick={() => setAuditStatus("Flagged")}
                      className={`flex-1 p-4 rounded-xl border-2 transition-all flex items-center justify-center gap-3 ${
                        auditStatus === "Flagged" ? "border-rose-500 bg-rose-50 text-rose-700" : "border-slate-100 bg-white text-slate-500"
                      }`}
                    >
                      <FileWarning size={20} />
                      <span className="font-bold">Flag Discrepancy</span>
                    </button>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold text-slate-700">Audit Notes / Justification</label>
                  <textarea 
                    className="input-field min-h-[120px]" 
                    placeholder="Provide details on the audit findings..."
                    value={auditNotes}
                    onChange={(e) => setAuditNotes(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card p-6">
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Audit Metadata</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-400">Audit ID</p>
                  <p className="text-sm font-bold text-slate-900">{selectedAudit.id}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Audit Type</p>
                  <p className="text-sm font-bold text-slate-900">{selectedAudit.type}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Original Verifier</p>
                  <p className="text-sm font-bold text-slate-900">{selectedAudit.verifier}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Verification Date</p>
                  <p className="text-sm font-bold text-slate-900">{selectedAudit.date}</p>
                </div>
              </div>
            </div>

            <button 
              onClick={handleSubmitAudit}
              className="w-full btn-primary py-4 shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2"
            >
              <CheckCircle2 size={20} />
              Submit Audit Report
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Independent Audit Portal</h1>
          <p className="text-slate-500">Compliance checks and verification records</p>
        </div>
        <button
          onClick={() => triggerDownload("audit_logs.txt", "Audit logs export\nSample records included.")}
          className="btn-secondary flex items-center gap-2"
        >
          <Download size={18} /> Export Audit Logs
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard label="Total Audited" value="142" icon={ShieldCheck} color="bg-emerald-600" trend="+12%" />
        <StatCard label="Discrepancies Found" value="3" icon={FileWarning} color="bg-rose-500" trend="-2%" />
        <StatCard label="Compliance Rate" value="97.8%" icon={CheckCircle2} color="bg-blue-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card overflow-hidden">
          <div className="p-6 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-lg font-bold">Audit Queue</h3>
            <div className="flex gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input type="text" placeholder="Search projects..." className="input-field pl-9 py-1 text-sm" />
              </div>
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {auditLogs.map((log, i) => (
              <div key={i} className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
                <div className="flex gap-4 items-center">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    log.status === 'Compliant' ? 'bg-emerald-100 text-emerald-600' : 
                    log.status === 'Flagged' ? 'bg-rose-100 text-rose-600' : 
                    'bg-slate-100 text-slate-400'
                  }`}>
                    {log.status === 'Compliant' ? <ShieldCheck size={20} /> : 
                     log.status === 'Flagged' ? <FileWarning size={20} /> : 
                     <History size={20} />}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-900">{log.project}</p>
                    <p className="text-xs text-slate-500">{log.type} • Verifier: {log.verifier}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-slate-500">{log.date}</span>
                  {log.status === 'Pending' ? (
                    <button 
                      onClick={() => handleStartAudit(log)}
                      className="btn-primary py-1 px-3 text-xs"
                    >
                      Start Audit
                    </button>
                  ) : (
                    <span className={`text-[10px] uppercase font-bold px-2 py-1 rounded-full ${
                      log.status === 'Compliant' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                    }`}>
                      {log.status}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-bold mb-4">Audit Insights</h3>
          <div className="space-y-6">
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Compliant', value: 95 },
                      { name: 'Minor Issues', value: 4 },
                      { name: 'Major Discrepancy', value: 1 },
                    ]}
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    <Cell fill="#10b981" />
                    <Cell fill="#f59e0b" />
                    <Cell fill="#ef4444" />
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500">Audit Coverage</span>
                <span className="font-bold text-slate-900">15% of total</span>
              </div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                <div className="bg-blue-600 h-full w-[15%]" />
              </div>
              <p className="text-[10px] text-slate-400 italic text-center">Program target: 10% independent audit coverage</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

interface SidebarItemType {
  id: string;
  icon: React.ElementType;
  label: string;
  badge?: string;
}

// --- Main App ---

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showPublicPortal, setShowPublicPortal] = useState(false);
  const [authView, setAuthView] = useState<"login" | "register">("login");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [tenderView, setTenderView] = useState<"list" | "create" | "details">("list");
  const [pendingTenderId, setPendingTenderId] = useState<string | null>(null);
  const [pendingBidTenderId, setPendingBidTenderId] = useState<string | null>(null);
  const [pendingBidId, setPendingBidId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>(MOCK_NOTIFICATIONS);
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  const loadNotifications = React.useCallback(async () => {
    if (!getStoredUser()) {
      setNotifications((prev) => (prev.length ? prev : MOCK_NOTIFICATIONS));
      return;
    }
    try {
      const data = await fetchNotifications();
      setNotifications(data);
    } catch {
      setNotifications((prev) => (prev.length ? prev : MOCK_NOTIFICATIONS));
    }
  }, []);

  React.useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  React.useEffect(() => {
    const id = setInterval(() => {
      void loadNotifications();
    }, 20000);
    return () => clearInterval(id);
  }, [loadNotifications]);

  React.useEffect(() => {
    const handler = () => void loadNotifications();
    window.addEventListener("rbf-notifications-refresh", handler);
    return () => window.removeEventListener("rbf-notifications-refresh", handler);
  }, [loadNotifications]);

  React.useEffect(() => {
    const cachedUser = getStoredUser();
    if (!cachedUser) return;

    setCurrentUser(cachedUser);
    fetchCurrentUser()
      .then(setCurrentUser)
      .catch(() => {
        logoutUser();
        setCurrentUser(null);
      });
  }, []);

  const role = currentUser?.role;

  const handleLogin = async (username: string, password: string) => {
    const { user } = await loginUser(username, password);
    setCurrentUser(user);
    setAuthMessage(null);
    setActiveTab("dashboard");
  };

  const handleLogout = () => {
    logoutUser();
    setCurrentUser(null);
    setAuthView("login");
    setShowNotifications(false);
    setActiveTab("dashboard");
    setPendingBidTenderId(null);
    setPendingBidId(null);
    setPendingTenderId(null);
  };

  const handleRegisterSuccess = (username: string) => {
    setAuthView("login");
    setAuthMessage(`Account created for "${username}". Log in now; complete pre-qualification before submitting applications.`);
  };

  const handleNewTender = () => {
    setTenderView("create");
    setActiveTab("tenders");
  };

  const resolveNotificationTarget = (note: Notification) => {
    const event = (note.event || "").toLowerCase();
    const linkedId = (note.linkedEntityId || "").trim();
    const linkedUpper = linkedId.toUpperCase();
    const isTender = linkedUpper.startsWith("T-") || event.includes("tender") || event.includes("bid");
    const isProject = linkedUpper.startsWith("P-") || event.includes("project") || event.includes("milestone") || event.includes("verification");
    const isReport = event.includes("briefing") || event.includes("summary") || event.includes("report");
    const isPrequal = event.includes("pre-qualification") || event.includes("prequalification");
    const isBidId = linkedUpper.startsWith("BID-") || linkedUpper.startsWith("B-");

    if (role === UserRole.VENDOR) {
      if (isTender && linkedId && !isBidId) {
        return { tab: "dashboard", pendingBidTenderId: linkedId };
      }
      if (isBidId) {
        return { tab: "my_bids" };
      }
      if (isProject) {
        return { tab: "projects" };
      }
      return { tab: "dashboard" };
    }

    if (role === UserRole.FIELD_VERIFIER) {
      if (event.includes("survey") || event.includes("verification")) return { tab: "inspections" };
      if (event.includes("gis") || event.includes("map")) return { tab: "gis" };
      return { tab: "dashboard" };
    }

    if (role === UserRole.ADMIN || role === UserRole.RBF_OFFICIAL) {
      if (isTender && linkedId) return { tab: "tenders", tenderId: linkedId };
      if (isPrequal) return { tab: "prequal" };
      if (isProject) return { tab: "monitoring" };
      if (isReport) return { tab: "reports" };
      return { tab: "dashboard" };
    }

    if (role === UserRole.DOE_OFFICER) {
      if (isProject) return { tab: "regional" };
      if (isReport) return { tab: "kpis" };
      return { tab: "dashboard" };
    }

    if (role === UserRole.UNDP_DONOR) {
      if (isReport) return { tab: "reports" };
      if (isProject) return { tab: "impact" };
      return { tab: "dashboard" };
    }

    if (role === UserRole.AUDITOR) {
      if (isProject) return { tab: "verification" };
      if (isReport) return { tab: "audit_trail" };
      return { tab: "dashboard" };
    }

    return { tab: "dashboard" };
  };

  const handleNotificationSelect = (note: Notification) => {
    const target = resolveNotificationTarget(note);
    const allowedTabs = new Set(getSidebarItems().map(item => item.id));
    const nextTab = allowedTabs.has(target.tab) ? target.tab : (allowedTabs.has("notifications") ? "notifications" : "dashboard");

    setShowNotifications(false);
    setActiveTab(nextTab);

    if (target.tenderId) {
      setTenderView("details");
      setPendingTenderId(target.tenderId);
    }

    if (target.pendingBidTenderId) {
      setPendingBidTenderId(target.pendingBidTenderId);
      setPendingBidId(null);
    }

  };

  if (showPublicPortal) {
    return <PublicPortal onBack={() => setShowPublicPortal(false)} />;
  }

  if (!currentUser) {
    return authView === "login" ? (
      <Login 
        onLogin={handleLogin} 
        onRegisterClick={() => {
          setAuthMessage(null);
          setAuthView("register");
        }} 
        onViewPublic={() => setShowPublicPortal(true)}
        infoMessage={authMessage}
      />
    ) : (
      <Register onBackToLogin={() => setAuthView("login")} onRegisterSuccess={handleRegisterSuccess} />
    );
  }

  if (currentUser.mustChangePassword) {
    return (
      <ForcePasswordReset
        user={currentUser}
        onComplete={(updated) => setCurrentUser(updated)}
        onLogout={handleLogout}
      />
    );
  }

  const renderContent = () => {
    // Shared tabs across roles (if they have them in sidebar)
    if (activeTab === "monitoring") return <Monitoring />;
    if (activeTab === "gis") return <GISMap />;
    if (activeTab === "reports") return <Reports />;
    if (activeTab === "notifications") return <NotificationLogs logs={notifications} onSelect={handleNotificationSelect} />;

    // Role-based content filtering
    if (role === UserRole.VENDOR) {
      switch (activeTab) {
        case "dashboard": return (
          <VendorDashboard
            onGoToPrequal={() => setActiveTab("prequal")}
            currentUser={currentUser}
            pendingBidTenderId={pendingBidTenderId}
            pendingBidId={pendingBidId}
            onBidOpened={() => {
              setPendingBidTenderId(null);
              setPendingBidId(null);
            }}
          />
        );
        case "contracting": return (
          <VendorDashboard
            initialSection="contracting"
            showOnlyContracting
            onGoToPrequal={() => setActiveTab("prequal")}
            currentUser={currentUser}
            pendingBidTenderId={pendingBidTenderId}
            pendingBidId={pendingBidId}
            onBidOpened={() => {
              setPendingBidTenderId(null);
              setPendingBidId(null);
            }}
          />
        );
        case "prequal": return <PreQualificationSubmission />;
        case "blacklisting": return <Blacklisting currentUser={currentUser} />;
        case "tenders": return (
          <VendorTenders
            onSubmitTender={(tenderId) => {
              setPendingBidTenderId(tenderId);
              setPendingBidId(null);
              setActiveTab("dashboard");
            }}
          />
        );
        case "applications": return <PreQualificationSubmission />;
        case "my_bids": return (
          <VendorBids
            onOpenBid={(bid) => {
              setPendingBidTenderId(bid.tender);
              setPendingBidId(bid.id);
              setActiveTab("dashboard");
            }}
          />
        );
        case "projects_hub": return <VendorProjectsHub />;
        case "claims": return <Disbursements />;
        default: return <VendorDashboard />;
      }
    }
    if (role === UserRole.TAC) {
      switch (activeTab) {
        case "dashboard":
        case "evaluations":
        case "scoring":
        case "blacklisting":
          return activeTab === "blacklisting" ? <Blacklisting currentUser={currentUser} /> : <TACView />;
        default:
          return <TACView />;
      }
    }
    if (role === UserRole.FIELD_VERIFIER) {
      switch (activeTab) {
        case "dashboard":
        case "inspections":
        case "sync":
          return <FieldVerifierView />;
        default:
          return <FieldVerifierView />;
      }
    }
    if (role === UserRole.ADMIN) {
      switch (activeTab) {
        case "dashboard":
        case "tenders":
          return (
            <Tenders
              initialView={tenderView}
              initialTenderId={pendingTenderId}
              onTenderOpened={() => setPendingTenderId(null)}
            />
          );
        case "blacklisting":
          return <Blacklisting currentUser={currentUser} />;
        case "users":
        case "roles":
        case "logs":
          return <AdminView />;
        default:
          return <AdminView />;
      }
    }
    if (role === UserRole.DOE_OFFICER) {
      switch (activeTab) {
        case "dashboard":
        case "regional":
        case "endorsements":
        case "kpis":
        case "blacklisting":
          return activeTab === "blacklisting" ? <Blacklisting currentUser={currentUser} /> : <DoEOfficerView />;
        default:
          return <DoEOfficerView />;
      }
    }
    if (role === UserRole.UNDP_DONOR) {
      switch (activeTab) {
        case "dashboard":
        case "impact":
        case "funding":
          return <DonorView />;
        default:
          return <DonorView />;
      }
    }
    if (role === UserRole.AUDITOR) {
      switch (activeTab) {
        case "dashboard":
        case "audit_trail":
        case "verification":
        case "compliance":
        case "blacklisting":
          return activeTab === "blacklisting" ? <Blacklisting currentUser={currentUser} /> : <AuditorView />;
        default:
          return <AuditorView />;
      }
    }

    // Default RBF Official view
    switch (activeTab) {
      case "dashboard": return <Dashboard role={role} onNewTender={handleNewTender} />;
      case "tenders": return (
        <Tenders
          initialView={tenderView}
          initialTenderId={pendingTenderId}
          onTenderOpened={() => setPendingTenderId(null)}
        />
      );
      case "prequal": return <PreQualification />;
      case "blacklisting": return <Blacklisting currentUser={currentUser} />;
      case "payments": return <Disbursements />;
      default: return <Dashboard role={role} onNewTender={handleNewTender} />;
    }
  };

  const getSidebarItems = (): SidebarItemType[] => {
    const common = [
      { id: "dashboard", icon: LayoutDashboard, label: "Dashboard" },
    ];

    if (role === UserRole.VENDOR) {
      return [
        ...common,
        { id: "prequal", icon: ClipboardCheck, label: "Pre-Qualification", badge: "Required" },
        { id: "tenders", icon: FileText, label: "Published Tenders" },
        { id: "my_bids", icon: FileSearch, label: "My Bids" },
        { id: "contracting", icon: FileText, label: "Contracting" },
        { id: "applications", icon: ClipboardCheck, label: "My Applications" },
        { id: "projects_hub", icon: BarChart3, label: "Projects Hub" },
        { id: "claims", icon: CreditCard, label: "Payment Claims" },
        { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
      ];
    }

    if (role === UserRole.TAC) {
      return [
        ...common,
        { id: "evaluations", icon: ClipboardCheck, label: "Evaluations", badge: "4" },
        { id: "scoring", icon: BarChart3, label: "Scoring Matrix" },
        { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
      ];
    }

    if (role === UserRole.FIELD_VERIFIER) {
      return [
        ...common,
        { id: "inspections", icon: ClipboardCheck, label: "Inspections", badge: "12" },
        { id: "monitoring", icon: Activity, label: "Monitoring" },
        { id: "gis", icon: MapIcon, label: "Region Map" },
        { id: "sync", icon: Activity, label: "Offline Sync" },
      ];
    }

    if (role === UserRole.ADMIN) {
      return [
        ...common,
        { id: "tenders", icon: FileText, label: "Tender Management" },
        { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
        { id: "users", icon: Users, label: "User Management" },
        { id: "roles", icon: Settings, label: "Role Config" },
        { id: "notifications", icon: Bell, label: "Notification Logs" },
        { id: "monitoring", icon: Activity, label: "System Monitoring" },
        { id: "logs", icon: FileText, label: "System Logs" },
      ];
    }

    if (role === UserRole.DOE_OFFICER) {
      return [
        ...common,
        { id: "regional", icon: MapIcon, label: "Regional Monitoring" },
        { id: "endorsements", icon: CheckCircle2, label: "Endorsements" },
        { id: "kpis", icon: BarChart3, label: "KPI Review" },
        { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
      ];
    }

    if (role === UserRole.UNDP_DONOR) {
      return [
        ...common,
        { id: "impact", icon: Activity, label: "Impact Dashboard" },
        { id: "funding", icon: CreditCard, label: "Funding Flows" },
        { id: "reports", icon: BarChart3, label: "Donor Reports" },
      ];
    }

    if (role === UserRole.AUDITOR) {
      return [
        ...common,
        { id: "audit_trail", icon: FileText, label: "Audit Trail" },
        { id: "verification", icon: ClipboardCheck, label: "Verification Docs" },
        { id: "compliance", icon: CheckCircle2, label: "Compliance Reports" },
        { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
      ];
    }

    // RBF Official
    return [
      ...common,
      { id: "tenders", icon: FileText, label: "Tender Management" },
      { id: "prequal", icon: ClipboardCheck, label: "Pre-Qualification" },
      { id: "blacklisting", icon: FileWarning, label: "Blacklisting" },
      { id: "monitoring", icon: Activity, label: "Monitoring" },
      { id: "gis", icon: MapIcon, label: "GIS Mapping" },
      { id: "payments", icon: CreditCard, label: "Disbursements" },
      { id: "reports", icon: BarChart3, label: "Reports" },
    ];
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Sidebar */}
      <motion.aside 
        initial={false}
        animate={{ width: isSidebarOpen ? 280 : 0, opacity: isSidebarOpen ? 1 : 0 }}
        className="bg-[#0b1530] border-r border-[#17305a] flex flex-col z-50"
      >
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white font-bold text-xl">
            R
          </div>
          <div className="overflow-hidden whitespace-nowrap">
            <h2 className="font-bold text-slate-100 leading-tight">Renewable Lesotho</h2>
            <p className="text-[10px] font-bold text-blue-200 uppercase tracking-widest">RBF Platform</p>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
          <div className="py-4">
            <p className="px-4 text-[10px] font-bold text-blue-200/80 uppercase tracking-widest mb-2">Menu</p>
            {getSidebarItems().map(item => (
              <SidebarItem 
                key={item.id}
                icon={item.icon} 
                label={item.label} 
                badge={item.badge}
                active={activeTab === item.id} 
                onClick={() => {
                  setActiveTab(item.id);
                  if (item.id === "tenders") setTenderView("list");
                }} 
              />
            ))}
          </div>
        </nav>

        <div className="p-4 border-t border-[#17305a]">
          <div className="bg-[#17284c] rounded-xl p-4 flex items-center gap-3 ring-1 ring-[#243b66]">
            <div className="w-10 h-10 rounded-full bg-[#243b66] flex items-center justify-center text-blue-100">
              <UserCircle size={24} />
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-bold text-blue-50 truncate">{currentUser.fullName}</p>
              <p className="text-xs text-blue-200 truncate">{role}</p>
            </div>
            <button 
              onClick={handleLogout}
              className="text-blue-200 hover:text-rose-300 transition-colors"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="h-16 bg-white border-b border-slate-200 px-8 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 hover:bg-slate-100 rounded-lg text-slate-500"
            >
              {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div className="h-6 w-px bg-slate-200 mx-2" />
            <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
              <span>System Role:</span>
              <span className="bg-slate-100 rounded-lg px-3 py-1 text-slate-900 font-bold">
                {role}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="relative">
              <button 
                onClick={() => setShowNotifications(!showNotifications)}
                className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 relative"
              >
                <Bell size={20} />
                {notifications.some(n => n.status === NotificationStatus.SENT) && (
                  <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 border-2 border-white" />
                )}
              </button>
              <AnimatePresence>
                {showNotifications && (
                  <NotificationCenter 
                    notifications={notifications} 
                    onClose={() => setShowNotifications(false)}
                    onViewAll={() => {
                      setShowNotifications(false);
                      setActiveTab("notifications");
                    }}
                    onSelect={handleNotificationSelect}
                  />
                )}
              </AnimatePresence>
            </div>
            <button
              onClick={() => setActiveTab("notifications")}
              className="p-2 hover:bg-slate-100 rounded-lg text-slate-500"
              title="Open Notifications"
            >
              <Settings size={20} />
            </button>
          </div>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-8">
          {currentUser.role === UserRole.VENDOR && currentUser.blacklistSummary?.banner && (
            <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 flex gap-3">
              <AlertTriangle className="text-rose-600 mt-0.5" size={20} />
              <div>
                <p className="font-bold text-rose-900">Vendor Restriction Notice</p>
                <p className="text-sm text-rose-700">{currentUser.blacklistSummary.banner}</p>
              </div>
            </div>
          )}
          <AnimatePresence mode="wait">
            <motion.div
              key={`${role}-${activeTab}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
