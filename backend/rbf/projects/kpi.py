import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, Min, Q, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.tenders.models import ContractStatus, TenderContract
from rbf.users.models import User, UserRole

from .audit import log_audit
from .models import (
    AnomalyFlag,
    InstallationReport,
    InstallationStatus,
    Milestone,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectUpdate,
    ProjectStatus,
    SmartMeterReading,
)


KPI_SUMMARY_CACHE_KEY = "kpi_summary_{project_id}"
KPI_SUMMARY_CACHE_TIMEOUT = 60 * 15


def _round(value: float | int | None, digits: int = 1) -> float:
    if value in (None, ""):
        return 0.0
    return round(float(value), digits)


def _project_duration_days(project: Project) -> int:
    if project.start_date and project.end_date and project.end_date >= project.start_date:
        return max(1, (project.end_date - project.start_date).days)
    months = project.project_duration_months or 0
    if months > 0:
        return max(1, int(round(months * 30.4)))
    return 365


def _project_start(project: Project):
    return project.start_date or timezone.localdate()


def _expected_progress_pct(project: Project) -> float:
    start_date = _project_start(project)
    elapsed_days = max(0, (timezone.localdate() - start_date).days)
    duration_days = _project_duration_days(project)
    return min(100.0, (elapsed_days / duration_days) * 100.0)


def _ordered_milestones(project: Project) -> list[Milestone]:
    return list(project.milestones.all().order_by("milestone_number", "created_at", "id"))


def _milestone_by_number(project: Project, milestone_number: int) -> Milestone | None:
    milestones = _ordered_milestones(project)
    index = milestone_number - 1
    if index < 0 or index >= len(milestones):
        return None
    return milestones[index]


def invalidate_kpi_cache(project_id: str):
    cache.delete(KPI_SUMMARY_CACHE_KEY.format(project_id=project_id))


@dataclass
class MilestoneEligibilityResult:
    summary: dict[str, Any]
    newly_claimable: list[int]


class KpiService:
    GENDER_TARGETS = {
        "female_headed": 50,
        "vulnerable": 30,
        "low_income": 60,
    }

    def __init__(self, project_id: str):
        self.project = Project.objects.get(id=project_id)

    @classmethod
    def for_project(cls, project_id: str) -> "KpiService":
        return cls(project_id)

    @staticmethod
    def invalidate(project_id: str):
        invalidate_kpi_cache(project_id)

    def _verified_installations(self):
        return InstallationReport.objects.filter(
            project=self.project,
            status=InstallationStatus.VERIFIED,
        ).distinct()

    def _readings_queryset(self):
        verified_installations = self._verified_installations()
        meter_ids = [meter_id for meter_id in verified_installations.values_list("meter_id", flat=True) if meter_id]
        return SmartMeterReading.objects.filter(
            Q(installation__in=verified_installations)
            | Q(installation__isnull=True, project=self.project, meter_id__in=meter_ids)
        ).distinct()

    def getInstallationProgress(self) -> dict[str, Any]:
        aggregates = InstallationReport.objects.filter(project=self.project).aggregate(
            total_submitted=Count("id"),
            total_verified=Count("id", filter=Q(status=InstallationStatus.VERIFIED)),
            total_pending=Count("id", filter=Q(status=InstallationStatus.SUBMITTED)),
            total_flagged=Count("id", filter=Q(status=InstallationStatus.FLAGGED)),
        )
        target = int(self.project.target_installations or self.project.installation_target or 0)
        verified = int(aggregates["total_verified"] or 0)
        progress_pct = (verified / target * 100.0) if target > 0 else 0.0
        expected_pct = _expected_progress_pct(self.project)
        return {
            "submitted": int(aggregates["total_submitted"] or 0),
            "verified": verified,
            "pending": int(aggregates["total_pending"] or 0),
            "flagged": int(aggregates["total_flagged"] or 0),
            "target": target,
            "progress_pct": _round(progress_pct, 1),
            "expected_progress_pct": _round(expected_pct, 1),
            "on_track": progress_pct >= max(0.0, expected_pct - 10.0),
        }

    def getGenderKpi(self) -> dict[str, Any]:
        verified = self._verified_installations()
        total = verified.count()
        grouped = verified.aggregate(
            female_count=Count("id", filter=Q(household_type__iexact="female_headed")),
            vulnerable_count=Count("id", filter=Q(household_type__iexact="vulnerable")),
            low_income_count=Count("id", filter=Q(household_type__iexact="low_income")),
            standard_count=Count("id", filter=Q(household_type__iexact="standard")),
        )

        last_week = timezone.now() - timedelta(days=7)
        previous_week = timezone.now() - timedelta(days=14)
        recent_female = verified.filter(submitted_at__gte=last_week, household_type__iexact="female_headed").count()
        recent_total = verified.filter(submitted_at__gte=last_week).count()
        prior_female = verified.filter(
            submitted_at__gte=previous_week,
            submitted_at__lt=last_week,
            household_type__iexact="female_headed",
        ).count()
        prior_total = verified.filter(submitted_at__gte=previous_week, submitted_at__lt=last_week).count()
        recent_pct = (recent_female / recent_total * 100.0) if recent_total else 0.0
        prior_pct = (prior_female / prior_total * 100.0) if prior_total else 0.0

        def build(count: int, target: int):
            percentage = (count / total * 100.0) if total else 0.0
            return {
                "count": int(count),
                "percentage": _round(percentage, 1),
                "target": int(target),
                "met": percentage >= float(target),
            }

        female = build(int(grouped["female_count"] or 0), self.GENDER_TARGETS["female_headed"])
        vulnerable = build(int(grouped["vulnerable_count"] or 0), self.GENDER_TARGETS["vulnerable"])
        low_income = build(int(grouped["low_income_count"] or 0), self.GENDER_TARGETS["low_income"])

        return {
            "total_verified": total,
            "female_headed": female,
            "vulnerable": vulnerable,
            "low_income": low_income,
            "standard": {
                "count": int(grouped["standard_count"] or 0),
                "percentage": _round(((grouped["standard_count"] or 0) / total * 100.0) if total else 0.0, 1),
            },
            "female_trend_pct_vs_last_week": _round(recent_pct - prior_pct, 1),
            "female_trending_up": recent_pct >= prior_pct,
            "all_gender_kpis_met": female["met"] and vulnerable["met"] and low_income["met"],
            "all_kpis_met": female["met"] and vulnerable["met"] and low_income["met"],
        }

    def getEnergyKpi(self, months_back: int = 3) -> dict[str, Any]:
        start_at = timezone.now() - timedelta(days=max(1, months_back) * 31)
        monthly_rows = (
            self._readings_queryset()
            .filter(recorded_at__gte=start_at)
            .annotate(month=TruncMonth("recorded_at"))
            .values("month")
            .annotate(
                total_kwh=Sum("kwh"),
                active_devices=Count("meter_id", distinct=True),
            )
            .order_by("month")
        )

        target_kwh = float(self.project.energy_output_target_kwh or self.project.energy_output or 0)
        monthly_data = []
        for row in monthly_rows:
            total_kwh = float(row["total_kwh"] or 0)
            achievement_pct = (total_kwh / target_kwh * 100.0) if target_kwh > 0 else 0.0
            monthly_data.append(
                {
                    "month": row["month"].strftime("%Y-%m") if row["month"] else "",
                    "total_kwh": _round(total_kwh, 1),
                    "target_kwh": _round(target_kwh, 1),
                    "achievement_pct": _round(achievement_pct, 1),
                    "active_devices": int(row["active_devices"] or 0),
                }
            )

        current = monthly_data[-1] if monthly_data else {
            "total_kwh": 0.0,
            "target_kwh": _round(target_kwh, 1),
            "achievement_pct": 0.0,
        }
        return {
            "monthly_data": monthly_data,
            "current_month_kwh": current["total_kwh"],
            "current_month_target": current["target_kwh"],
            "current_month_pct": current["achievement_pct"],
            "on_track": current["achievement_pct"] >= 95.0 if target_kwh > 0 else True,
        }

    def getUptimeKpi(self) -> dict[str, Any]:
        cutoff = timezone.now() - timedelta(days=30)
        per_device = list(
            self._readings_queryset()
            .filter(recorded_at__gte=cutoff)
            .values("meter_id")
            .annotate(
                avg_uptime=Avg("uptime_pct"),
                min_uptime=Min("uptime_pct"),
                reading_count=Count("id"),
            )
        )
        target = 99.0
        average = sum(float(row["avg_uptime"] or 0) for row in per_device) / len(per_device) if per_device else 0.0
        devices_above = sum(1 for row in per_device if float(row["avg_uptime"] or 0) >= target)
        devices_below = sum(1 for row in per_device if 0 < float(row["avg_uptime"] or 0) < target)
        devices_offline = sum(1 for row in per_device if float(row["avg_uptime"] or 0) <= 0)

        buckets = Counter()
        for row in per_device:
            uptime = float(row["avg_uptime"] or 0)
            if uptime <= 0:
                buckets["Offline"] += 1
            elif uptime >= 95:
                buckets["95-100%"] += 1
            elif uptime >= 90:
                buckets["90-94%"] += 1
            elif uptime >= 80:
                buckets["80-89%"] += 1
            else:
                buckets["Below 80%"] += 1

        return {
            "average_uptime_pct": _round(average, 1),
            "target_uptime_pct": _round(target, 1),
            "met": average >= target if per_device else False,
            "devices_above_target": devices_above,
            "devices_below_target": devices_below,
            "devices_offline": devices_offline,
            "total_devices_monitored": len(per_device),
            "distribution": {
                "95-100%": buckets.get("95-100%", 0),
                "90-94%": buckets.get("90-94%", 0),
                "80-89%": buckets.get("80-89%", 0),
                "Below 80%": buckets.get("Below 80%", 0),
                "Offline": buckets.get("Offline", 0),
            },
        }

    def getInstallationTrend(self) -> dict[str, Any]:
        verified = list(
            self._verified_installations()
            .annotate(week=TruncWeek("submitted_at"))
            .values("week")
            .annotate(weekly_verified=Count("id"))
            .order_by("week")
        )
        target = int(self.project.target_installations or self.project.installation_target or 0)
        duration_weeks = max(1.0, (_project_duration_days(self.project) / 7.0))
        target_per_week = target / duration_weeks if duration_weeks > 0 else 0.0
        cumulative = 0
        weeks = []
        target_line = []
        for index, row in enumerate(verified, start=1):
            cumulative += int(row["weekly_verified"] or 0)
            target_value = _round(target_per_week * index, 1)
            weeks.append(
                {
                    "week_start": row["week"].date().isoformat() if row["week"] else "",
                    "cumulative_verified": cumulative,
                    "weekly_new": int(row["weekly_verified"] or 0),
                    "target_at_this_week": target_value,
                }
            )
            target_line.append(target_value)
        return {
            "weeks": weeks,
            "target_line": target_line,
            "total_verified": cumulative,
            "target": target,
        }

    def getMilestoneEligibility(self) -> dict[str, Any]:
        result = self._get_milestone_eligibility()
        return result.summary

    def _is_unlockable_status(self, status_value: str | None) -> bool:
        normalized = str(status_value or "").strip().lower()
        return normalized in {"locked", "pending"}

    def _unlock_milestone_if_eligible(
        self,
        *,
        milestone: Milestone | None,
        milestone_number: int,
        eligible: bool,
        reason_notes: str,
    ) -> bool:
        if milestone is None or not eligible or not self._is_unlockable_status(milestone.status):
            return False

        with transaction.atomic():
            milestone.status = "claimable"
            if not milestone.unlocked_at:
                milestone.unlocked_at = timezone.now()
                milestone.save(update_fields=["status", "unlocked_at", "updated_at"])
            else:
                milestone.save(update_fields=["status", "updated_at"])
            Notification.objects.create(
                recipient_id=str(self.project.vendor_id),
                recipient_name=self.project.vendor_name,
                type=NotificationChannel.IN_APP,
                event="milestone_claimable",
                title=f"Milestone {milestone_number} Claimable",
                body=f"Milestone {milestone_number} for Project {self.project.id} is now claimable. Log in to submit your claim.",
                status=NotificationStatus.SENT,
                linked_entity_id=str(self.project.id),
            )
            log_audit(
                None,
                "milestone_claimable_auto_detected",
                milestone,
                {
                    "project_id": str(self.project.id),
                    "milestone_number": milestone_number,
                    "notes": reason_notes,
                },
            )
            create_project_activity_update(
                self.project,
                None,
                f"Milestone {milestone_number} Claimable",
                reason_notes,
            )
        return True

    def _get_milestone_eligibility(self) -> MilestoneEligibilityResult:
        installation = self.getInstallationProgress()
        gender = self.getGenderKpi()
        readings_cutoff = timezone.now() - timedelta(days=30)
        blocking_flags = AnomalyFlag.objects.filter(
            project=self.project,
            is_resolved=False,
            flag_type__in=['zero_uptime', 'output_deviation'],
        ).count()
        all_flags = AnomalyFlag.objects.filter(project=self.project, is_resolved=False).count()
        meter_present = self._readings_queryset().filter(recorded_at__gte=readings_cutoff).exists()

        contract_approved = TenderContract.objects.filter(
            project_id=str(self.project.id),
            status=ContractStatus.APPROVED,
        ).exists()
        setup = getattr(self.project, 'project_setup', None)
        setup_complete = bool((setup and setup.setup_completed_at) or self.project.setup_completed_at)
        verified_ratio = (installation["verified"] / installation["target"]) if installation["target"] else 0.0
        milestone_two = _milestone_by_number(self.project, 2)
        milestone_two_paid = bool(
            milestone_two
            and (
                milestone_two.status == "Paid"
                or PaymentClaim.objects.filter(
                    project=self.project,
                    milestone=milestone_two,
                    status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID},
                ).exists()
            )
        )

        milestone_one = _milestone_by_number(self.project, 1)
        milestone_one_paid = bool(
            milestone_one
            and (
                milestone_one.status in {"paid", "Paid"}
                or PaymentClaim.objects.filter(
                    project=self.project,
                    milestone=milestone_one,
                    status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID},
                ).exists()
            )
        )
        milestone_one_claimable = bool(milestone_one and str(milestone_one.status).strip().lower() in {"claimable", "claimed", "paid"})
        milestone_two_claimable = bool(milestone_two and str(milestone_two.status).strip().lower() in {"claimable", "claimed", "paid"})
        milestone_three = _milestone_by_number(self.project, 3)
        milestone_three_paid = bool(
            milestone_three
            and (
                milestone_three.status in {"paid", "Paid"}
                or PaymentClaim.objects.filter(
                    project=self.project,
                    milestone=milestone_three,
                    status__in={PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID},
                ).exists()
            )
        )
        milestone_three_claimable = bool(milestone_three and str(milestone_three.status).strip().lower() in {"claimable", "claimed", "paid"})
        female_pct_met = bool(gender["female_headed"]["met"])
        vulnerable_pct_met = bool(gender["vulnerable"]["met"])
        low_income_pct_met = bool(gender["low_income"]["met"])
        summary = {
            "milestone_1": {
                "eligible": contract_approved and setup_complete,
                "status": "PAID" if milestone_one_paid else "CLAIMABLE" if (contract_approved and setup_complete or milestone_one_claimable) else "Pending",
                "conditions": {
                    "contract_approved": contract_approved,
                    "setup_complete": setup_complete,
                },
            },
            "milestone_2": {
                "eligible": (
                    verified_ratio >= 0.8
                    and gender["female_headed"]["met"]
                    and blocking_flags == 0
                    and meter_present
                ),
                "status": "PAID" if milestone_two_paid else "CLAIMABLE" if (
                    verified_ratio >= 0.8
                    and female_pct_met
                    and blocking_flags == 0
                    and meter_present
                ) or milestone_two_claimable else "Pending",
                "conditions": {
                    "installations_80_pct": verified_ratio >= 0.8,
                    "female_pct_50": female_pct_met,
                    "no_blocking_anomaly_flags": blocking_flags == 0,
                    "meter_data_present": meter_present,
                },
            },
            "milestone_3": {
                "eligible": (
                    verified_ratio >= 1.0
                    and female_pct_met
                    and vulnerable_pct_met
                    and low_income_pct_met
                    and all_flags == 0
                    and milestone_two_paid
                ),
                "status": "PAID" if milestone_three_paid else "CLAIMABLE" if (
                    verified_ratio >= 1.0
                    and female_pct_met
                    and vulnerable_pct_met
                    and low_income_pct_met
                    and all_flags == 0
                    and milestone_two_paid
                ) or milestone_three_claimable else "Pending",
                "conditions": {
                    "installations_100_pct": verified_ratio >= 1.0,
                    "female_pct_50": female_pct_met,
                    "vulnerable_pct_30": vulnerable_pct_met,
                    "low_income_pct_60": low_income_pct_met,
                    "all_anomaly_flags_resolved": all_flags == 0,
                    "milestone_2_paid": milestone_two_paid,
                },
            },
        }

        newly_claimable: list[int] = []
        if self._unlock_milestone_if_eligible(
            milestone=milestone_one,
            milestone_number=1,
            eligible=summary["milestone_1"]["eligible"],
            reason_notes="M1 conditions met automatically: contract approved and project setup complete.",
        ):
            newly_claimable.append(1)
        if self._unlock_milestone_if_eligible(
            milestone=milestone_two,
            milestone_number=2,
            eligible=summary["milestone_2"]["eligible"],
            reason_notes=(
                f"M2 conditions met automatically: verified={installation['verified']}/{installation['target']}, "
                f"female={gender['female_headed']['percentage']}%."
            ),
        ):
            newly_claimable.append(2)
        if self._unlock_milestone_if_eligible(
            milestone=milestone_three,
            milestone_number=3,
            eligible=summary["milestone_3"]["eligible"],
            reason_notes="M3 conditions met automatically: 100% verified, all KPIs met, all anomaly flags resolved, and M2 paid.",
        ):
            newly_claimable.append(3)
        return MilestoneEligibilityResult(summary=summary, newly_claimable=newly_claimable)

    def getFullKpiSummary(self) -> dict[str, Any]:
        cache_key = KPI_SUMMARY_CACHE_KEY.format(project_id=self.project.id)
        cached = cache.get(cache_key)
        if cached:
            return cached

        installation = self.getInstallationProgress()
        gender = self.getGenderKpi()
        energy = self.getEnergyKpi(months_back=6)
        uptime = self.getUptimeKpi()
        trend = self.getInstallationTrend()
        milestone = self._get_milestone_eligibility().summary
        summary = {
            "project": {
                "id": str(self.project.id),
                "project_reference": self.project.project_reference,
                "project_title": self.project.project_title,
                "vendor_name": self.project.vendor_name,
                "technology_type": self.project.tech_type,
                "district": self.project.district,
                "status": self.project.status,
                "start_date": self.project.start_date.isoformat() if self.project.start_date else None,
                "end_date": self.project.end_date.isoformat() if self.project.end_date else None,
                "target_installations": self.project.target_installations,
            },
            "installation_progress": installation,
            "gender_kpi": gender,
            "energy_kpi": energy,
            "uptime_kpi": uptime,
            "installation_trend": trend,
            "milestone_eligibility": milestone,
            "generated_at": timezone.now().isoformat(),
        }
        self._sync_project_snapshot(summary)
        cache.set(cache_key, summary, KPI_SUMMARY_CACHE_TIMEOUT)
        return summary

    def _sync_project_snapshot(self, summary: dict[str, Any]):
        installation = summary["installation_progress"]
        gender = summary["gender_kpi"]
        energy = summary["energy_kpi"]
        uptime = summary["uptime_kpi"]
        verified_target = int(installation["target"] or 0)
        progress_pct = float(installation["progress_pct"] or 0)
        update_fields: list[str] = []

        normalized_progress = int(round(progress_pct))
        if self.project.progress != normalized_progress:
            self.project.progress = normalized_progress
            update_fields.append("progress")

        normalized_gender = float(gender["female_headed"]["percentage"] or 0)
        if float(self.project.gender_impact or 0) != normalized_gender:
            self.project.gender_impact = normalized_gender
            update_fields.append("gender_impact")

        normalized_uptime = float(uptime["average_uptime_pct"] or 0)
        if float(self.project.uptime or 0) != normalized_uptime:
            self.project.uptime = normalized_uptime
            update_fields.append("uptime")

        normalized_energy = float(energy["current_month_kwh"] or 0)
        if float(self.project.energy_output or 0) != normalized_energy:
            self.project.energy_output = normalized_energy
            update_fields.append("energy_output")

        if verified_target and self.project.target_installations != verified_target:
            self.project.target_installations = verified_target
            update_fields.append("target_installations")

        if update_fields:
            self.project.save(update_fields=update_fields + ["updated_at"])

    @classmethod
    def getPortfolioSummary(cls, user: User | None = None) -> dict[str, Any]:
        projects = Project.objects.exclude(status=ProjectStatus.HALTED)
        scope_label = "National Portfolio"

        if user is not None and user.role == UserRole.DOE_OFFICER:
            region = (user.region or "").strip()
            if region:
                projects = projects.filter(Q(region__iexact=region) | Q(district__iexact=region))
                scope_label = f"Regional Portfolio - {region}"
            else:
                projects = projects.none()
                scope_label = "Regional Portfolio"
        elif user is not None and user.role == UserRole.AUDITOR:
            scope_label = "Audit Portfolio"
        elif user is not None and user.role == UserRole.UNDP_DONOR:
            scope_label = "PSC Portfolio"
        elif user is not None and user.role == UserRole.TAC:
            scope_label = "TAC Portfolio"
        elif user is not None and user.role in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            scope_label = "RMT Portfolio"

        projects = projects.order_by("project_reference", "id")
        rows = []
        total_target = 0
        total_verified = 0
        female_numerator = 0
        female_denominator = 0
        uptime_weighted = 0.0
        uptime_devices = 0
        projects_at_risk = 0
        projects_on_track = 0
        projects_completed = 0
        total_paid_amount = 0.0
        pending_claims = 0

        for project in projects:
            service = cls(str(project.id))
            summary = service.getFullKpiSummary()
            installation = summary["installation_progress"]
            gender = summary["gender_kpi"]
            uptime = summary["uptime_kpi"]
            energy = summary["energy_kpi"]
            status_label = (
                "Completed" if project.status == ProjectStatus.COMPLETED
                else "At Risk" if not installation["on_track"]
                else "On Track"
            )
            if project.status == ProjectStatus.COMPLETED:
                projects_completed += 1
            elif status_label == "At Risk":
                projects_at_risk += 1
            else:
                projects_on_track += 1

            total_target += int(installation["target"])
            total_verified += int(installation["verified"])
            female_numerator += int(gender["female_headed"]["count"])
            female_denominator += int(gender["total_verified"])
            uptime_weighted += float(uptime["average_uptime_pct"]) * max(1, int(uptime["total_devices_monitored"] or 0))
            uptime_devices += max(1, int(uptime["total_devices_monitored"] or 0))
            total_paid_amount += sum(
                float(claim.claim_amount or 0)
                for claim in project.payment_claims.filter(status__in=[PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID])
            )
            pending_claims += project.payment_claims.exclude(
                status__in=[PaymentClaimStatus.COMPLETED, PaymentClaimStatus.LEGACY_PAID, PaymentClaimStatus.REJECTED]
            ).count()
            rows.append(
                {
                    "project_id": str(project.id),
                    "project_reference": project.project_reference or f"PRJ-{project.id}",
                    "project_title": project.project_title or f"Project {project.id}",
                    "vendor_name": project.vendor_name,
                    "technology": project.tech_type,
                    "district": project.district or project.region,
                    "progress_pct": installation["progress_pct"],
                    "female_pct": gender["female_headed"]["percentage"],
                    "uptime_pct": uptime["average_uptime_pct"],
                    "energy_kwh": energy["current_month_kwh"],
                    "status": status_label,
                }
            )

        overall_progress_pct = (total_verified / total_target * 100.0) if total_target else 0.0
        overall_female_pct = (female_numerator / female_denominator * 100.0) if female_denominator else 0.0
        return {
            "scope_label": scope_label,
            "total_projects": len(rows),
            "total_installations_target": total_target,
            "total_verified": total_verified,
            "overall_progress_pct": _round(overall_progress_pct, 1),
            "overall_female_pct": _round(overall_female_pct, 1),
            "overall_female_met": overall_female_pct >= 50.0 if female_denominator else False,
            "overall_uptime_pct": _round((uptime_weighted / uptime_devices) if uptime_devices else 0.0, 1),
            "projects_at_risk": projects_at_risk,
            "projects_on_track": projects_on_track,
            "projects_completed": projects_completed,
            "total_paid_amount": _round(total_paid_amount, 2),
            "pending_claims": pending_claims,
            "projects": rows,
        }

    @classmethod
    def getPublicPortfolioSummary(cls) -> dict[str, Any]:
        projects = Project.objects.exclude(status=ProjectStatus.HALTED)
        
        total_projects = projects.count()
        total_target = 0
        total_verified = 0
        female_numerator = 0
        female_denominator = 0
        total_energy_kwh = 0
        
        for project in projects:
            service = cls(str(project.id))
            summary = service.getFullKpiSummary()
            installation = summary["installation_progress"]
            gender = summary["gender_kpi"]
            energy = summary.get("energy_kpi", {})
            
            target = installation.get("target_installations", 0)
            verified = installation.get("verified_installations", 0)
            total_target += target
            total_verified += verified
            
            female_denominator += verified
            female_numerator += int(verified * (gender.get("female_pct", 0) / 100))
            
            total_energy_kwh += energy.get("total_energy_kwh", 0)
        
        overall_female_pct = (female_numerator / female_denominator * 100) if female_denominator else 0
        
        return {
            "total_projects": total_projects,
            "total_installations_target": total_target,
            "total_verified": total_verified,
            "overall_female_pct": round(overall_female_pct, 1),
            "total_energy_kwh_monthly": total_energy_kwh,
        }


def build_svg_bar_chart(title: str, labels: list[str], values: list[float], line_values: list[float] | None = None) -> str:
    width = 720
    height = 260
    chart_height = 160
    left = 50
    bottom = 210
    max_value = max(values + (line_values or []) + [1.0])
    bar_width = max(24, int(520 / max(1, len(labels) * 1.7)))
    gap = bar_width // 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="28" font-size="18" font-family="Arial" fill="#0f172a">{title}</text>',
        f'<line x1="{left}" y1="40" x2="{left}" y2="{bottom}" stroke="#cbd5e1"/>',
        f'<line x1="{left}" y1="{bottom}" x2="680" y2="{bottom}" stroke="#cbd5e1"/>',
    ]
    line_points = []
    for idx, (label, value) in enumerate(zip(labels, values)):
        x = left + 20 + idx * (bar_width + gap)
        bar_height = int((value / max_value) * chart_height)
        y = bottom - bar_height
        color = "#1d9e75" if (line_values or [max_value])[idx] == 0 or value >= 0.8 * (line_values or [max_value])[idx] else "#b91c1c"
        parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="{color}" rx="4"/>')
        parts.append(f'<text x="{x + bar_width/2}" y="{bottom + 18}" text-anchor="middle" font-size="11" font-family="Arial" fill="#475569">{label}</text>')
        if line_values:
            line_height = int((line_values[idx] / max_value) * chart_height)
            line_y = bottom - line_height
            line_points.append(f"{x + bar_width/2},{line_y}")
    if line_points:
        parts.append(f'<polyline fill="none" stroke="#64748b" stroke-width="3" stroke-dasharray="6 4" points="{" ".join(line_points)}"/>')
    parts.append("</svg>")
    return "".join(parts)


def build_svg_line_chart(title: str, labels: list[str], values: list[float], target_values: list[float]) -> str:
    width = 720
    height = 260
    chart_height = 160
    left = 50
    bottom = 210
    max_value = max(values + target_values + [1.0])
    span = max(1, len(labels) - 1)
    value_points = []
    target_points = []
    labels_svg = []
    for idx, label in enumerate(labels):
        x = left + 20 + (580 * idx / span)
        value_y = bottom - int((values[idx] / max_value) * chart_height)
        target_y = bottom - int((target_values[idx] / max_value) * chart_height)
        value_points.append(f"{x},{value_y}")
        target_points.append(f"{x},{target_y}")
        labels_svg.append(
            f'<text x="{x}" y="{bottom + 18}" text-anchor="middle" font-size="11" font-family="Arial" fill="#475569">{label}</text>'
        )
    return "".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            f'<text x="24" y="28" font-size="18" font-family="Arial" fill="#0f172a">{title}</text>',
            f'<line x1="{left}" y1="40" x2="{left}" y2="{bottom}" stroke="#cbd5e1"/>',
            f'<line x1="{left}" y1="{bottom}" x2="680" y2="{bottom}" stroke="#cbd5e1"/>',
            f'<polyline fill="none" stroke="#1d9e75" stroke-width="4" points="{" ".join(value_points)}"/>',
            f'<polyline fill="none" stroke="#64748b" stroke-width="3" stroke-dasharray="6 4" points="{" ".join(target_points)}"/>',
            "".join(labels_svg),
            "</svg>",
        ]
    )


def render_kpi_pdf(project: Project, summary: dict[str, Any]) -> Path:
    from rbf.tenders.pba_pdf import _render_pdf

    gender = summary["gender_kpi"]
    energy = summary["energy_kpi"]
    trend = summary["installation_trend"]
    uptime = summary["uptime_kpi"]
    installation = summary["installation_progress"]
    milestone = summary["milestone_eligibility"]

    energy_svg = build_svg_bar_chart(
        "Monthly Energy Output",
        [row["month"][5:] for row in energy["monthly_data"]],
        [float(row["total_kwh"]) for row in energy["monthly_data"]],
        [float(row["target_kwh"]) for row in energy["monthly_data"]],
    )
    trend_svg = build_svg_line_chart(
        "Installation Progress Over Time",
        [row["week_start"][5:] for row in trend["weeks"]],
        [float(row["cumulative_verified"]) for row in trend["weeks"]],
        [float(row["target_at_this_week"]) for row in trend["weeks"]],
    )
    uptime_svg = build_svg_bar_chart(
        "Uptime Distribution",
        list(uptime["distribution"].keys()),
        [float(v) for v in uptime["distribution"].values()],
    )

    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: Arial, sans-serif; color: #0f172a; margin: 0; padding: 24px; }}
          h1, h2 {{ margin: 0 0 12px; }}
          .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }}
          .card {{ border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
          th, td {{ border-bottom: 1px solid #e2e8f0; padding: 8px; text-align: left; font-size: 12px; }}
          .chart {{ margin: 12px 0 20px; }}
          .small {{ font-size: 12px; color: #475569; }}
        </style>
      </head>
      <body>
        <h1>KPI Report - {project.project_reference or project.id}</h1>
        <p class="small">{project.project_title or f"Project {project.id}"} • {project.vendor_name} • {project.tech_type}</p>
        <div class="grid">
          <div class="card"><strong>Installation Progress</strong><br/>{installation["verified"]} / {installation["target"]} ({installation["progress_pct"]}%)</div>
          <div class="card"><strong>Female Beneficiary</strong><br/>{gender["female_headed"]["percentage"]}% (target {gender["female_headed"]["target"]}%)</div>
          <div class="card"><strong>Average Uptime</strong><br/>{uptime["average_uptime_pct"]}% (target {uptime["target_uptime_pct"]}%)</div>
          <div class="card"><strong>Current Month Energy</strong><br/>{energy["current_month_kwh"]} kWh / {energy["current_month_target"]} kWh</div>
        </div>
        <h2>KPI Status</h2>
        <table>
          <thead><tr><th>KPI</th><th>Target</th><th>Current</th><th>Status</th></tr></thead>
          <tbody>
            <tr><td>Female-headed HH</td><td>&ge;{gender["female_headed"]["target"]}%</td><td>{gender["female_headed"]["percentage"]}%</td><td>{"Met" if gender["female_headed"]["met"] else "Below"}</td></tr>
            <tr><td>Vulnerable groups</td><td>&ge;{gender["vulnerable"]["target"]}%</td><td>{gender["vulnerable"]["percentage"]}%</td><td>{"Met" if gender["vulnerable"]["met"] else "Below"}</td></tr>
            <tr><td>Low-income HH</td><td>&ge;{gender["low_income"]["target"]}%</td><td>{gender["low_income"]["percentage"]}%</td><td>{"Met" if gender["low_income"]["met"] else "Below"}</td></tr>
            <tr><td>System uptime</td><td>&ge;{uptime["target_uptime_pct"]}%</td><td>{uptime["average_uptime_pct"]}%</td><td>{"Met" if uptime["met"] else "Below"}</td></tr>
            <tr><td>Installation progress</td><td>{installation["target"]}</td><td>{installation["verified"]}</td><td>{installation["progress_pct"]}%</td></tr>
            <tr><td>Energy output</td><td>{energy["current_month_target"]} kWh</td><td>{energy["current_month_kwh"]} kWh</td><td>{energy["current_month_pct"]}%</td></tr>
          </tbody>
        </table>
        <div class="chart">{energy_svg}</div>
        <div class="chart">{trend_svg}</div>
        <div class="chart">{uptime_svg}</div>
        <h2>Milestone Readiness</h2>
        <table>
          <thead><tr><th>Milestone</th><th>Eligible</th><th>Conditions</th></tr></thead>
          <tbody>
            {"".join(
                f"<tr><td>{name.replace('_', ' ').title()}</td><td>{'Yes' if data['eligible'] else 'No'}</td><td>{', '.join(f'{key}={value}' for key, value in data['conditions'].items())}</td></tr>"
                for name, data in milestone.items()
            )}
          </tbody>
        </table>
      </body>
    </html>
    """

    tmp_dir = Path(tempfile.mkdtemp(prefix="kpi_pdf_"))
    output_path = tmp_dir / f"KPI_Report_{project.id}_{timezone.localdate().isoformat()}.pdf"
    _render_pdf(html, output_path, project.project_reference or str(project.id))
    return output_path
def create_project_activity_update(project: Project, author, title: str, body: str):
    return ProjectUpdate.objects.create(
        project=project,
        author=author if getattr(author, "is_authenticated", False) else None,
        title=title,
        body=body,
    )
