import { getInclusionTargets } from "./inclusionTargets";
import { MilestoneConditionThresholds } from "./types";

// Condition keys from the KPI milestone_eligibility summary keep their legacy
// names (e.g. installations_80_pct); the configured percentages behind them are
// reported separately in `thresholds` and used for the label when present.
export function formatMilestoneConditionLabel(conditionKey: string, thresholds?: MilestoneConditionThresholds) {
  const installationsPct = thresholds?.installations_pct;
  const labels: Record<string, string> = {
    contract_approved: "Contract approved",
    setup_complete: "Project setup completed",
    installations_80_pct: `At least ${installationsPct ?? 80}% of target installations verified`,
    female_pct_50: `Female-headed households at or above ${thresholds?.female_pct ?? getInclusionTargets().female}%`,
    no_blocking_anomaly_flags: "No unresolved blocking anomaly flags",
    meter_data_present: "Meter data received within the last 30 days",
    installations_100_pct: `${installationsPct != null && installationsPct < 100 ? `At least ${installationsPct}%` : "100%"} of target installations verified`,
    vulnerable_pct_30: `Vulnerable households at or above ${thresholds?.vulnerable_pct ?? getInclusionTargets().vulnerable}%`,
    low_income_pct_60: `Low-income households at or above ${thresholds?.low_income_pct ?? getInclusionTargets().lowIncome}%`,
    all_anomaly_flags_resolved: "All anomaly flags resolved",
    milestone_2_paid: "Milestone 2 fully paid",
    milestone_1_verified: "Milestone 1 verified by RBF / Super Admin to proceed",
    milestone_2_verified: "Milestone 2 verified by RBF / Super Admin to proceed",
  };
  return labels[conditionKey] || conditionKey.replace(/_/g, " ");
}
