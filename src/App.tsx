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
  Clock,
  UserCircle,
  Menu,
  X,
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
  PaymentClaim,
  VendorPrequalification,
  Notification,
  NotificationChannel,
  NotificationStatus,
  User,
} from "./types";
import { MOCK_TENDERS, MOCK_NOTIFICATIONS } from "./constants";
import {
  fetchTenders,
  createTender,
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
  fetchVendorPrequalifications,
  submitVendorPrequalification,
  startVendorPrequalificationReview,
  approveVendorPrequalification,
  requestVendorPrequalificationClarification,
  rejectVendorPrequalification,
  fetchPaymentClaims,
  submitPaymentClaim,
  approvePaymentClaim,
  payPaymentClaim,
  fetchProjects,
  fetchMilestones,
  API_BASE,
} from "./api";

// --- Components ---

const SidebarItem = ({ icon: Icon, label, active, onClick, badge }: any) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
      active 
        ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20" 
        : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
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
    techTypes: [] as string[],
    address: "",
    taxId: "",
  });

  const techOptions = ["SHS", "ICS", "Mini-grid", "SWP", "PUE"];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (step < 3) {
      if (step === 2) {
        try {
          setIsSubmitting(true);
          const otpResp = await requestRegistrationOtp(formData.email.trim());
          const debugNote = otpResp.debugOtp ? ` Debug OTP: ${otpResp.debugOtp}` : "";
          const emailWarn = otpResp.emailError ? " (email delivery failed, using debug OTP)" : "";
          setOtpInfo(`OTP sent to ${formData.email.trim()}${emailWarn}.${debugNote}`);
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
      await verifyRegistrationOtp(formData.email.trim(), otp.trim());
      await registerVendor({
        username: formData.username.trim(),
        password: formData.password,
        fullName: formData.fullName,
        email: formData.email,
        gender: formData.gender as "Male" | "Female" | "Other",
        organizationName: formData.orgName,
        organizationType: formData.orgType,
        technologyTypes: formData.techTypes,
        region: "Maseru",
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
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
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
                  onChange={(e) => setFormData({ ...formData, mobile: e.target.value })}
                  className="input-field"
                  placeholder="+266 ..."
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
                        const otpResp = await requestRegistrationOtp(formData.email.trim());
                        const debugNote = otpResp.debugOtp ? ` Debug OTP: ${otpResp.debugOtp}` : "";
                        const emailWarn = otpResp.emailError ? " (email delivery failed, using debug OTP)" : "";
                        setOtpInfo(`OTP resent to ${formData.email.trim()}${emailWarn}.${debugNote}`);
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

const Tenders = ({ initialView = "list" }: { initialView?: "list" | "create" | "details" | "verify" | "publish" | "award" | "security" | "edit" }) => {
  const [view, setView] = useState<"list" | "create" | "details" | "verify" | "publish" | "award" | "security" | "edit">(initialView);
  const [selectedTender, setSelectedTender] = useState<Tender | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [notification, setNotification] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [awardWinner, setAwardWinner] = useState("SolarLease Ltd");
  const [notifySMS, setNotifySMS] = useState(true);
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [isActioning, setIsActioning] = useState(false);

  // Form State
  const [formData, setFormData] = useState<Partial<Tender>>({
    name: "",
    department: "",
    applicationType: "Access Window",
    stageType: "Pre-Qualification",
    procurementMethod: "",
    biddingCurrency: "LSL (Maloti)",
    category: "SHS",
    budget: 0,
    deadline: "",
    lastDateSecurity: "",
    dateOpening: "",
    technologyTypes: [],
    targetSiteType: "Household",
    biddersEligibility: "",
    instruction: "",
    contactDetails: "",
    fundingSource: ""
  });

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

  React.useEffect(() => {
    // Preload data from API with fallback to mocks
    (async () => {
      try {
        const tnds = await fetchTenders().catch(() => MOCK_TENDERS);
        setTenders(tnds);
      } catch {
        setTenders(MOCK_TENDERS);
      }
    })();
  }, []);

  const filteredTenders = useMemo(() => {
    return tenders.filter(tender => {
      const matchesSearch = tender.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                            tender.referenceNumber.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === "All Categories" || tender.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [tenders, searchQuery, selectedCategory]);

  // Sync view with initialView prop when it changes
  React.useEffect(() => {
    setView(initialView);
  }, [initialView]);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const downloadTenderDocument = (docName: string) => {
    const tenderRef = selectedTender?.referenceNumber ?? "N/A";
    const content = [
      `Document: ${docName}`,
      `Tender: ${tenderRef}`,
      `Generated: ${new Date().toISOString()}`,
      "",
      "This is a generated placeholder document for testing workflow actions.",
    ].join("\n");
    triggerDownload(`${docName.replace(/[^a-z0-9]+/gi, "_").toLowerCase()}.txt`, content);
    showNotification(`Downloaded: ${docName}`);
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
      const updated = await publishTender(tenderId);
      upsertTender(updated);
      showNotification("Tender published and bidders notified successfully!");
      setView("list");
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to publish tender."));
    } finally {
      setIsActioning(false);
    }
  };

  const handleSaveTender = async (tenderData: any) => {
    try {
      const created = await createTender({
        ...tenderData,
        status: TenderStatus.DRAFT,
      });
      setTenders([created, ...tenders]);
      showNotification("Tender saved successfully.");
      setView("list");
    } catch (e) {
      // Fallback to local optimistic add if API fails
      const newTender: Tender = {
        id: "T-" + Math.floor(Math.random() * 10000),
        referenceNumber: "REF-" + Math.floor(Math.random() * 1000000),
        status: TenderStatus.DRAFT,
        ...tenderData
      };
      setTenders([newTender, ...tenders]);
      showNotification("Tender saved locally (offline mode).");
      setView("list");
    }
  };

  const handleVerify = async (tenderId: string) => {
    try {
      setIsActioning(true);
      const updated = await verifyTender(tenderId);
      upsertTender(updated);
      showNotification("Tender information verified successfully.");
      setView("list");
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to verify tender."));
    } finally {
      setIsActioning(false);
    }
  };

  const handleAward = async (tenderId: string) => {
    try {
      setIsActioning(true);
      const updated = await awardTender(tenderId, { awardedVendorName: awardWinner });
      upsertTender(updated);
      const channels = [notifySMS ? "SMS" : null, notifyEmail ? "Email" : null].filter(Boolean).join(" & ");
      showNotification(`Tender awarded to ${awardWinner}. Winner notified via ${channels || "System"}.`);
      setView("list");
    } catch (err: any) {
      showNotification(toActionError(err, "Failed to award tender."));
    } finally {
      setIsActioning(false);
    }
  };

  if (view === "create") {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">Add New Tender</h1>
        </div>

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
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Name & Address for Tender Document *</label>
              <input 
                type="text" 
                placeholder="Address" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Name & Address for Tender Security *</label>
              <input 
                type="text" 
                placeholder="Address" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Place for Tender Opening *</label>
              <input 
                type="text" 
                placeholder="Opening Location" 
                className="input-field" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Tender Invited By *</label>
              <input 
                type="text" 
                placeholder="Official Name" 
                className="input-field" 
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Security Submission Deadline *</label>
              <div className="relative">
                <Clock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input 
                  type="datetime-local" 
                  name="lastDateSecurity"
                  value={formData.lastDateSecurity}
                  onChange={handleInputChange}
                  className="input-field pl-10" 
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Document Submission Deadline *</label>
              <div className="relative">
                <FileText className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input 
                  type="datetime-local" 
                  name="deadline"
                  value={formData.deadline}
                  onChange={handleInputChange}
                  className="input-field pl-10" 
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-slate-700">Tender Opening Date & Time *</label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input 
                  type="datetime-local" 
                  name="dateOpening"
                  value={formData.dateOpening}
                  onChange={handleInputChange}
                  className="input-field pl-10" 
                />
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

          <div className="space-y-2">
            <label className="text-sm font-bold text-slate-700">Upload Schedule * (PDF/DOCX)</label>
            <div className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center hover:border-emerald-500 transition-colors cursor-pointer bg-slate-50">
              <Download size={32} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm text-slate-600 font-medium">Click to upload or drag and drop</p>
              <p className="text-xs text-slate-400 mt-1">Maximum file size: 10MB</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
            <button onClick={() => setView("list")} className="btn-secondary">Cancel</button>
            <button onClick={() => handleSaveTender(formData)} className="btn-secondary border-emerald-200 text-emerald-700 hover:bg-emerald-50">Save as Draft</button>
            <button onClick={() => handleSaveTender(formData)} className="btn-primary">Save Tender</button>
          </div>
        </div>
      </div>
    );
  }

  if (view === "details" && selectedTender) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-12">
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
            <button onClick={() => setView("edit")} className="btn-secondary flex items-center gap-2">
              <FileText size={18} /> Edit Tender
            </button>
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
            <div className="card p-8 space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Tender Information</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <p className="text-xs font-bold text-slate-500">Status</p>
                      <span className={`badge ${
                        selectedTender.status === TenderStatus.PUBLISHED ? 'bg-emerald-100 text-emerald-700' :
                        selectedTender.status === TenderStatus.EVALUATION ? 'bg-blue-100 text-blue-700' :
                        'bg-amber-100 text-amber-700'
                      }`}>
                        {selectedTender.status}
                      </span>
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
                    <p className="text-lg font-bold text-slate-900">M {selectedTender.budget?.toLocaleString()}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-bold text-slate-500">Bidding Currency</p>
                    <p className="text-sm font-medium">{selectedTender.biddingCurrency || "LSL (Maloti)"}</p>
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
                    <p className="text-sm font-bold text-slate-900">{selectedTender.deadline}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <ShieldCheck size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Security Deadline</p>
                    <p className="text-sm font-bold text-slate-900">{selectedTender.lastDateSecurity || "2025-06-10"}</p>
                  </div>
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                    <Eye size={16} className="text-slate-400 mb-2" />
                    <p className="text-xs font-bold text-slate-500">Opening Date</p>
                    <p className="text-sm font-bold text-slate-900">{selectedTender.dateOpening || "2025-06-16"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Technical Requirements</h3>
                <div className="grid grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Technology Types</p>
                    <div className="flex flex-wrap gap-2">
                      {(selectedTender.technologyTypes || ["SHS", "Mini-Grid"]).map(tech => (
                        <span key={tech} className="px-2 py-1 bg-emerald-50 text-emerald-700 rounded text-[10px] font-bold uppercase tracking-wider">{tech}</span>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs font-bold text-slate-500">Target Site Type</p>
                    <p className="text-sm font-medium">{selectedTender.targetSiteType || "Household"}</p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-6 border-t border-slate-100">
                <h3 className="font-bold text-slate-900 uppercase text-[10px] tracking-widest text-slate-400">Required Documents</h3>
                <div className="space-y-3">
                  {[
                    "Tender Schedule (Technical & Financial)",
                    "Valid Trading License",
                    "Tax Clearance Certificate",
                    "Company Registration Documents",
                    "Relevant Experience Portfolio"
                  ].map((doc, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
                      <div className="flex items-center gap-3">
                        <FileText size={18} className="text-slate-400" />
                        <span className="text-sm font-medium text-slate-700">{doc}</span>
                      </div>
                      <button
                        onClick={() => downloadTenderDocument(doc)}
                        className="text-emerald-600 hover:text-emerald-700"
                        title={`Download ${doc}`}
                      >
                        <Download size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
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

  if (view === "edit" && selectedTender) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("details")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={20} />
          </button>
          <h1 className="text-2xl font-bold text-slate-900">Edit Tender: {selectedTender.name}</h1>
        </div>
        <div className="card p-8">
          <p className="text-slate-500 mb-8">Update the tender details below. Some fields may be locked if the tender is already published.</p>
          {/* Reuse create form logic here or similar */}
          <div className="flex justify-end gap-3 pt-6 border-t border-slate-100">
            <button onClick={() => setView("details")} className="btn-secondary">Cancel</button>
            <button onClick={() => { showNotification("Tender updated successfully"); setView("details"); }} className="btn-primary">Save Changes</button>
          </div>
        </div>
      </div>
    );
  }

  if (view === "publish" && selectedTender) {
    return (
      <div className="space-y-6 max-w-2xl mx-auto">
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
            <div className="space-y-3">
              <label className="text-sm font-bold text-slate-700">Target Bidders *</label>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="bidders" className="w-4 h-4 text-emerald-600" defaultChecked />
                  <span className="text-sm font-medium">All Pre-qualified Bidders</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="bidders" className="w-4 h-4 text-emerald-600" />
                  <span className="text-sm font-medium">Category-specific Bidders</span>
                </label>
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-sm font-bold text-slate-700">Notification Channels</label>
              <div className="space-y-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" className="w-5 h-5 rounded border-slate-300 text-emerald-600" defaultChecked />
                  <span className="text-sm font-medium text-slate-700">Send SMS Notification</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" className="w-5 h-5 rounded border-slate-300 text-emerald-600" defaultChecked />
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
        <h1 className="text-2xl font-bold text-slate-900">Tender Management</h1>
        <div className="flex gap-3">
          <button onClick={() => setView("security")} className="btn-secondary flex items-center gap-2">
            <ShieldCheck size={18} /> Verify Security
          </button>
          <button onClick={() => setView("create")} className="btn-primary flex items-center gap-2">
            <Plus size={18} /> Add Tender
          </button>
        </div>
      </div>

      <div className="card p-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-4 items-end">
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
            <select className="input-field py-2 text-sm">
              <option>All Entities</option>
              <option>DoE</option>
              <option>UNDP</option>
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
            <select className="input-field py-2 text-sm">
              <option>All Methods</option>
              <option>Open</option>
              <option>Restricted</option>
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
                      onClick={() => { setSelectedTender(tender); setView("details"); }}
                      className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                    >
                      View
                    </button>
                    {!tender.isVerified && (
                      <button 
                        onClick={() => { setSelectedTender(tender); setView("verify"); }}
                        className="text-blue-600 hover:text-blue-700 font-medium text-sm"
                      >
                        Verify
                      </button>
                    )}
                    {tender.isVerified && tender.status === TenderStatus.DRAFT && (
                      <button 
                        onClick={() => { setSelectedTender(tender); setView("publish"); }}
                        className="text-emerald-600 hover:text-emerald-700 font-medium text-sm"
                      >
                        Publish
                      </button>
                    )}
                    {(tender.status === TenderStatus.EVALUATION || tender.status === TenderStatus.PUBLISHED) && (
                      <button 
                        onClick={() => { setSelectedTender(tender); setView("award"); }}
                        className="text-purple-600 hover:text-purple-700 font-medium text-sm"
                      >
                        Award
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
          >
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8 space-y-6"
            >
              <h2 className="text-xl font-bold text-slate-900">Issue Award Notification</h2>
              <p className="text-sm text-slate-500">Select the winning bidder and notification options for {selectedTender.name}.</p>
              
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-slate-700">Winning Bidder</label>
                  <select 
                    className="input-field"
                    value={awardWinner}
                    onChange={(e) => setAwardWinner(e.target.value)}
                  >
                    <option>SolarLease Ltd</option>
                    <option>EcoGrid Solutions</option>
                    <option>Mountain Power</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-bold text-slate-700">Notification Options</label>
                  <div className="space-y-2">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input 
                        type="checkbox" 
                        className="w-5 h-5 rounded border-slate-300 text-emerald-600" 
                        checked={notifySMS}
                        onChange={(e) => setNotifySMS(e.target.checked)}
                      />
                      <span className="text-sm font-medium text-slate-700">Send SMS Notification</span>
                    </label>
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

              <div className="flex gap-3 pt-4">
                <button onClick={() => setView("list")} className="btn-secondary flex-1">Cancel</button>
                <button onClick={() => handleAward(selectedTender.id)} disabled={isActioning} className="btn-primary flex-1 bg-purple-600 hover:bg-purple-700 disabled:opacity-60">
                  {isActioning ? "Awarding..." : "Confirm Award"}
                </button>
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
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Meter ID</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Project / Vendor</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">kWh Gen.</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Uptime</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Last Sync</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {smartMeterData.map((meter) => (
              <tr key={meter.id} className="hover:bg-slate-50 transition-colors">
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
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Ranking</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Vendor</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Total kWh</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Avg Uptime</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Sites</th>
              <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Performance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {vendorReports.map((report) => (
              <tr key={report.vendor} className="hover:bg-slate-50 transition-colors">
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
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Survey ID</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Household / District</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Field Officer</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Status</th>
                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {verificationQueue.map((audit) => (
                <tr key={audit.id} className="hover:bg-slate-50 transition-colors">
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
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
                  No pre-qualification submissions found.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
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
          >
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
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
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Certificate of Incorporation</span>
                        <button
                          onClick={() => {
                            triggerDownload("certificate_of_incorporation.txt", `Certificate of Incorporation\n${selectedVendor.registrationCertificateName || "No file provided"}`);
                            showNotification("Opened Certificate of Incorporation.");
                          }}
                          className="text-emerald-600 hover:underline flex items-center gap-1"
                        >
                          <Download size={14} /> View Document
                        </button>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Tax Clearance Certificate</span>
                        <button
                          onClick={() => {
                            triggerDownload("tax_clearance_certificate.txt", "Tax Clearance Certificate\nSample document preview.");
                            showNotification("Opened Tax Clearance Certificate.");
                          }}
                          className="text-emerald-600 hover:underline flex items-center gap-1"
                        >
                          <Download size={14} /> View Document
                        </button>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Trade License</span>
                        <button
                          onClick={() => {
                            triggerDownload("trade_license.txt", "Trade License\nSample document preview.");
                            showNotification("Opened Trade License.");
                          }}
                          className="text-emerald-600 hover:underline flex items-center gap-1"
                        >
                          <Download size={14} /> View Document
                        </button>
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
                        <span className="text-slate-900 font-medium">Standard Lesotho Bank</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Focal Person</span>
                        <span className="text-slate-900 font-medium">Jane Doe (Female)</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">Contact</span>
                        <span className="text-slate-900 font-medium">+266 5812 3456</span>
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
    if (!canProcessPayments || claim.status === "Paid") return;

    try {
      setProcessingClaimId(claim.id);
      if (claim.status === "Pending" || claim.status === "Verified") {
        await approvePaymentClaim(claim.id, "Approved from disbursement dashboard.");
      }
      const paid = await payPaymentClaim(claim.id, undefined, "Processed from disbursement dashboard.");
      setClaims(prev => prev.map(item => item.id === claim.id ? paid : item));
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
                    disabled={!canProcessPayments || claim.status === "Paid" || processingClaimId === claim.id}
                  >
                    {!canProcessPayments ? "View Only" : claim.status === "Paid" ? "Paid" : processingClaimId === claim.id ? "Processing..." : "Process Payment"}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && claims.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
                  No payment claims found.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
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
}: {
  notifications: Notification[];
  onClose: () => void;
  onViewAll: () => void;
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
              <div key={n.id} className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer ${n.status === NotificationStatus.SENT ? 'bg-emerald-50/30' : ''}`}>
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

const NotificationLogs = ({ logs }: { logs: Notification[] }) => {
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
              <tr key={log.id} className="hover:bg-slate-50/50 transition-colors">
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
                    onClick={() => handleResend(log.id)}
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
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
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

const PreQualificationSubmission = () => {
  const [step, setStep] = useState(1);
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
  const [submitted, setSubmitted] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const techSectors = ["SHS", "ICS", "GMG", "SAS", "PUE", "SWP"];

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
      try {
        setIsSubmitting(true);
        const created = await submitVendorPrequalification({
          companyName: formData.companyName.trim(),
          organizationType: "Private",
          taxId: "",
          hqAddress: "",
          technologyTypes: formData.sectorFocus,
          registrationCertificateName: "",
          techTier: formData.techTier,
          yearsExperience: Number(formData.yearsOfExperience || 0),
          priorProjects: Number(formData.priorProjects || 0),
          annualRevenue: Number(formData.annualRevenue || 0),
          districtsCovered: Number(formData.districtsCovered || 0),
          femaleBeneficiaryTarget: formData.femaleCommitment,
          vulnerableGroupTarget: formData.vulnerableInclusion,
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
          }} 
          className="btn-primary px-8 py-3 rounded-xl"
        >
          Return to Dashboard
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
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {[
                    { label: "Registration Certificate", icon: FileText },
                    { label: "Tax Compliance Cert", icon: ShieldCheck },
                    { label: "Authorized Signatory ID", icon: UserCircle }
                  ].map((doc, i) => (
                    <div key={i} className="p-4 border-2 border-dashed border-slate-200 rounded-xl text-center hover:border-emerald-500 transition-colors cursor-pointer bg-slate-50">
                      <doc.icon className="mx-auto text-slate-400 mb-2" size={24} />
                      <p className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{doc.label}</p>
                      <p className="text-[8px] text-slate-400 mt-1">PDF/DOCX only</p>
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

const VendorDashboard = ({ onGoToPrequal }: { onGoToPrequal?: () => void }) => {
  const [view, setView] = useState<"dashboard" | "new-application" | "new-claim" | "details">("dashboard");
  const [isPreQualified, setIsPreQualified] = useState(false);
  const [selectedMilestone, setSelectedMilestone] = useState<(Milestone & { projectName?: string }) | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
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

  const [claimData, setClaimData] = useState({
    milestoneName: "",
    completionDate: "",
    actualBeneficiaries: "",
    actualFemaleBeneficiaries: "",
    notes: "",
  });

  const districts = ["Maseru", "Leribe", "Berea", "Mafeteng", "Mohale's Hoek", "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Butha-Buthe"];
  const techTypes = ["SHS", "ICS", "Mini-grid", "SWP", "PUE"];

  React.useEffect(() => {
    (async () => {
      try {
        const [prequals, projectRows, milestoneRows] = await Promise.all([
          fetchVendorPrequalifications(),
          fetchProjects(),
          fetchMilestones(),
        ]);
        setIsPreQualified(prequals.some(item => item.status === "Approved"));
        setProjects(projectRows);
        const projectIds = new Set(projectRows.map(item => item.id));
        setMilestones(milestoneRows.filter(item => projectIds.has(item.projectId)));
      } catch {
        setProjects([]);
        setMilestones([]);
      }
    })();
  }, []);

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

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Vendor Portal</h1>
          <p className="text-slate-500">Manage your energy projects and payment claims</p>
        </div>
        <button 
          onClick={handleStartApplication} 
          className={`btn-primary flex items-center gap-2 ${!isPreQualified ? "opacity-50 cursor-not-allowed" : ""}`}
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
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold">My Project Milestones</h3>
        </div>
        <div className="p-6 space-y-6">
          {milestoneRows.map((p) => (
            <div key={p.id} className="flex items-center gap-6">
              <div className="flex-1">
                <div className="flex justify-between mb-2">
                  <span className="font-medium text-slate-900">{p.name} ({p.projectName})</span>
                  <span className="text-sm font-bold text-slate-500">{p.progress}%</span>
                </div>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-emerald-500 h-full" style={{ width: `${p.progress}%` }} />
                </div>
              </div>
              <div className="text-right min-w-[100px]">
                <div className="text-sm font-bold text-slate-900">M {Number(p.amount || 0).toLocaleString()}</div>
                <div className={`text-[10px] font-bold uppercase ${p.status === 'Verified' ? 'text-emerald-600' : 'text-amber-600'}`}>{p.status}</div>
              </div>
              <button 
                onClick={() => handleStartClaim(p)}
                disabled={!isPreQualified}
                className="btn-secondary py-1 px-3 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Claim
              </button>
            </div>
          ))}
          {milestoneRows.length === 0 && (
            <p className="text-sm text-slate-500">No project milestones available yet.</p>
          )}
        </div>
      </div>
    </div>
  );
};

const TACView = () => {
  const [view, setView] = useState<"list" | "evaluate">("list");
  const [selectedEval, setSelectedEval] = useState<any>(null);
  const [evaluations, setEvaluations] = useState([
    { id: 1, vendor: "SolarLease Ltd", tender: "RL-2025-SHS-01", score: 0, status: "Pending", criteria: { technical: 0, financial: 0, experience: 0 } },
    { id: 2, vendor: "EcoGrid Solutions", tender: "RL-2025-MG-04", score: 88, status: "Scored", criteria: { technical: 90, financial: 85, experience: 90 } },
    { id: 3, vendor: "Basotho Energy", tender: "RL-2025-SHS-01", score: 0, status: "Pending", criteria: { technical: 0, financial: 0, experience: 0 } },
  ]);
  const [notification, setNotification] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const handleStartEvaluation = (item: any) => {
    setSelectedEval({ ...item });
    setView("evaluate");
  };

  const handleSaveScore = () => {
    const totalScore = Math.round((selectedEval.criteria.technical + selectedEval.criteria.financial + selectedEval.criteria.experience) / 3);
    setEvaluations(prev => prev.map(ev => 
      ev.id === selectedEval.id 
        ? { ...selectedEval, score: totalScore, status: "Scored" } 
        : ev
    ));
    setView("list");
    showNotification(`Evaluation for ${selectedEval.vendor} saved successfully!`);
  };

  if (view === "evaluate" && selectedEval) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView("list")} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">
            <X size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Technical Evaluation</h1>
            <p className="text-slate-500">{selectedEval.vendor} • {selectedEval.tender}</p>
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
                      <label className="text-sm font-bold text-slate-700">Experience & Track Record (0-100)</label>
                      <span className="text-sm font-bold text-emerald-600">{selectedEval.criteria.experience}</span>
                    </div>
                    <input 
                      type="range" min="0" max="100" 
                      value={selectedEval.criteria.experience}
                      onChange={(e) => setSelectedEval({...selectedEval, criteria: {...selectedEval.criteria, experience: parseInt(e.target.value)}})}
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
                ></textarea>
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
                {['Technical_Proposal.pdf', 'Financial_Model.xlsx', 'Project_Timeline.pdf'].map(doc => (
                  <button
                    key={doc}
                    onClick={() => {
                      triggerDownload(doc.replace(/\s+/g, "_"), `${doc}\nTechnical document preview.`);
                      showNotification(`Opened ${doc}.`);
                    }}
                    className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 border border-transparent hover:border-slate-100 transition-all text-left group"
                  >
                    <div className="p-2 rounded-lg bg-slate-100 text-slate-400 group-hover:bg-emerald-50 group-hover:text-emerald-600">
                      <FileText size={18} />
                    </div>
                    <span className="text-xs font-medium text-slate-600 truncate">{doc}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="card p-6 bg-slate-900 text-white">
              <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Aggregate Score</h3>
              <div className="text-center py-4">
                <p className="text-5xl font-bold text-emerald-400">
                  {Math.round((selectedEval.criteria.technical + selectedEval.criteria.financial + selectedEval.criteria.experience) / 3)}
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
            {evaluations.filter(e => e.status === 'Pending').length} Pending Reviews
          </span>
        </div>
        <div className="divide-y divide-slate-100">
          {evaluations.map((item) => (
            <div key={item.id} className="p-6 flex items-center justify-between hover:bg-slate-50 transition-colors">
              <div className="flex gap-4 items-center">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400">
                  <FileText size={24} />
                </div>
                <div>
                  <p className="font-bold text-slate-900">{item.vendor}</p>
                  <p className="text-xs text-slate-500">Tender: {item.tender}</p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                {item.score > 0 && (
                  <div className="text-right">
                    <p className="text-xs font-bold text-slate-400 uppercase">Score</p>
                    <p className="text-lg font-bold text-emerald-600">{item.score}/100</p>
                  </div>
                )}
                <button 
                  onClick={() => handleStartEvaluation(item)}
                  className="btn-primary py-1.5 px-4 text-sm"
                >
                  {item.status === 'Pending' ? 'Start Evaluation' : 'Edit Score'}
                </button>
              </div>
            </div>
          ))}
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

  const [newUser, setNewUser] = useState({
    fullName: "",
    email: "",
    role: UserRole.RBF_OFFICIAL,
    region: "Maseru",
    gender: "Male"
  });

  const handleCreateUser = (e: React.FormEvent) => {
    e.preventDefault();
    const user = {
      ...newUser,
      id: "USR-" + Math.floor(Math.random() * 1000).toString().padStart(3, '0'),
      status: "Active"
    };
    setUsers([user, ...users]);
    setView("dashboard");
    // In real app, send email with temp password
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
                <label className="text-sm font-bold text-slate-700 ml-1">System Role *</label>
                <select 
                  value={newUser.role}
                  onChange={(e) => setNewUser({...newUser, role: e.target.value as UserRole})}
                  className="input-field"
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
                >
                  <option value="All">All Regions</option>
                  <option value="Maseru">Maseru</option>
                  <option value="Leribe">Leribe</option>
                  <option value="Mafeteng">Mafeteng</option>
                  <option value="Mokhotlong">Mokhotlong</option>
                  <option value="Qacha's Nek">Qacha's Nek</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-bold text-slate-700 ml-1">Gender *</label>
                <select 
                  value={newUser.gender}
                  onChange={(e) => setNewUser({...newUser, gender: e.target.value as any})}
                  className="input-field"
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>
            </div>

            <div className="bg-blue-50 p-4 rounded-xl border border-blue-100 flex gap-3">
              <AlertCircle className="text-blue-600 shrink-0" size={20} />
              <p className="text-xs text-blue-800 leading-relaxed">
                A temporary password will be auto-generated and sent to the official's email. 
                They will be required to change it upon their first login.
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button type="button" onClick={() => setView("dashboard")} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary px-8">Create Account</button>
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>(MOCK_NOTIFICATIONS);
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  React.useEffect(() => {
    fetchNotifications()
      .then(setNotifications)
      .catch(() => setNotifications(MOCK_NOTIFICATIONS));
  }, []);

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
  };

  const handleRegisterSuccess = (username: string) => {
    setAuthView("login");
    setAuthMessage(`Registration submitted for "${username}". Your account is pending approval.`);
  };

  const handleNewTender = () => {
    setTenderView("create");
    setActiveTab("tenders");
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

  const renderContent = () => {
    // Shared tabs across roles (if they have them in sidebar)
    if (activeTab === "monitoring") return <Monitoring />;
    if (activeTab === "gis") return <GISMap />;
    if (activeTab === "reports") return <Reports />;
    if (activeTab === "notifications") return <NotificationLogs logs={notifications} />;

    // Role-based content filtering
    if (role === UserRole.VENDOR) {
      switch (activeTab) {
        case "dashboard": return <VendorDashboard onGoToPrequal={() => setActiveTab("prequal")} />;
        case "prequal": return <PreQualificationSubmission />;
        case "tenders": return <Tenders initialView="list" />;
        case "applications": return <PreQualificationSubmission />;
        case "projects": return <Monitoring />;
        case "claims": return <Disbursements />;
        default: return <VendorDashboard />;
      }
    }
    if (role === UserRole.TAC) {
      switch (activeTab) {
        case "dashboard":
        case "evaluations":
        case "scoring":
          return <TACView />;
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
          return <DoEOfficerView />;
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
          return <AuditorView />;
        default:
          return <AuditorView />;
      }
    }

    // Default RBF Official view
    switch (activeTab) {
      case "dashboard": return <Dashboard role={role} onNewTender={handleNewTender} />;
      case "tenders": return <Tenders initialView={tenderView} />;
      case "prequal": return <PreQualification />;
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
        { id: "tenders", icon: FileText, label: "Active Tenders" },
        { id: "applications", icon: ClipboardCheck, label: "My Applications" },
        { id: "projects", icon: Activity, label: "My Projects" },
        { id: "claims", icon: CreditCard, label: "Payment Claims" },
      ];
    }

    if (role === UserRole.TAC) {
      return [
        ...common,
        { id: "evaluations", icon: ClipboardCheck, label: "Evaluations", badge: "4" },
        { id: "scoring", icon: BarChart3, label: "Scoring Matrix" },
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
      ];
    }

    // RBF Official
    return [
      ...common,
      { id: "tenders", icon: FileText, label: "Tender Management" },
      { id: "prequal", icon: ClipboardCheck, label: "Pre-Qualification" },
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
        className="bg-white border-r border-slate-200 flex flex-col z-50"
      >
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white font-bold text-xl">
            R
          </div>
          <div className="overflow-hidden whitespace-nowrap">
            <h2 className="font-bold text-slate-900 leading-tight">Renewable Lesotho</h2>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">RBF Platform</p>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
          <div className="py-4">
            <p className="px-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Menu</p>
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

        <div className="p-4 border-t border-slate-100">
          <div className="bg-slate-50 rounded-xl p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center text-slate-500">
              <UserCircle size={24} />
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-bold text-slate-900 truncate">{currentUser.fullName}</p>
              <p className="text-xs text-slate-500 truncate">{role}</p>
            </div>
            <button 
              onClick={handleLogout}
              className="text-slate-400 hover:text-rose-600 transition-colors"
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
          <AnimatePresence mode="wait">
            <motion.div
              key={`${role}-${activeTab}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
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


