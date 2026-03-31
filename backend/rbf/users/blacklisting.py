from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.projects.audit import log_audit
from rbf.projects.models import (
    Disbursement,
    DisbursementStatus,
    InstallationReport,
    InstallationStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
    VerificationStatus,
    VerificationTask,
)

from .models import (
    BlacklistedIdentifier,
    BlacklistCaseStatus,
    User,
    UserRole,
    UserStatus,
    VendorBlacklistCase,
)


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def pause_vendor_field_verification(vendor: User, actor: User | None = None) -> dict[str, int]:
    paused_report_ids = list(
        InstallationReport.objects.filter(
            vendor=vendor,
            status=InstallationStatus.SUBMITTED,
        ).values_list('id', flat=True)
    )
    paused_task_ids = list(
        VerificationTask.objects.filter(
            report__vendor=vendor,
            status=VerificationStatus.PENDING,
        ).values_list('id', flat=True)
    )
    if paused_report_ids:
        InstallationReport.objects.filter(id__in=paused_report_ids).update(status=InstallationStatus.PAUSED)
    if paused_task_ids:
        VerificationTask.objects.filter(id__in=paused_task_ids).update(status=VerificationStatus.PAUSED)
    summary = {
        'paused_report_count': len(paused_report_ids),
        'paused_verification_task_count': len(paused_task_ids),
    }
    if any(summary.values()):
        log_audit(actor, 'vendor_field_verification_paused', vendor, summary)
    return summary


def terminate_vendor_field_verification(vendor: User, actor: User | None = None) -> dict[str, int]:
    terminated_report_ids = list(
        InstallationReport.objects.filter(
            vendor=vendor,
            status__in=[InstallationStatus.SUBMITTED, InstallationStatus.PAUSED],
        ).values_list('id', flat=True)
    )
    terminated_task_ids = list(
        VerificationTask.objects.filter(
            report__vendor=vendor,
            status__in=[VerificationStatus.PENDING, VerificationStatus.PAUSED],
        ).values_list('id', flat=True)
    )
    if terminated_report_ids:
        InstallationReport.objects.filter(id__in=terminated_report_ids).update(status=InstallationStatus.TERMINATED)
    if terminated_task_ids:
        VerificationTask.objects.filter(id__in=terminated_task_ids).update(status=VerificationStatus.TERMINATED)
    summary = {
        'terminated_report_count': len(terminated_report_ids),
        'terminated_verification_task_count': len(terminated_task_ids),
    }
    if any(summary.values()):
        log_audit(actor, 'vendor_field_verification_terminated', vendor, summary)
    return summary


def normalize_identifier_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        raw_items = re.split(r"[\n,;]+", values)
    else:
        raw_items = list(values)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        key = normalize_identifier(str(item))
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def audit_related_vendor_activity(vendor: User, actor: User | None = None) -> dict[str, int]:
    linked_reports = InstallationReport.objects.filter(vendor=vendor)
    serials = [value for value in linked_reports.values_list('serial_number', flat=True) if value]
    beneficiaries = [value for value in linked_reports.values_list('beneficiary_id', flat=True) if value]

    related_reports = InstallationReport.objects.filter(
        Q(serial_number__in=serials) | Q(beneficiary_id__in=beneficiaries)
    ).exclude(vendor=vendor)
    related_project_ids = list(
        related_reports.exclude(project__status=ProjectStatus.COMPLETED)
        .values_list('project_id', flat=True)
        .distinct()
    )
    related_claim_ids = list(
        PaymentClaim.objects.filter(
            project_id__in=related_project_ids,
            status__in=[PaymentClaimStatus.PENDING, PaymentClaimStatus.VERIFIED, PaymentClaimStatus.APPROVED],
        ).values_list('id', flat=True)
    )
    related_task_ids = list(
        VerificationTask.objects.filter(report__in=related_reports).values_list('id', flat=True)
    )
    related_report_ids = list(related_reports.values_list('id', flat=True))

    if related_project_ids:
        Project.objects.filter(id__in=related_project_ids).exclude(status=ProjectStatus.COMPLETED).update(status=ProjectStatus.HALTED)
    if related_claim_ids:
        PaymentClaim.objects.filter(id__in=related_claim_ids).update(status=PaymentClaimStatus.HELD_AUDIT)
        Disbursement.objects.filter(claim_id__in=related_claim_ids).update(status=DisbursementStatus.HELD_AUDIT)
    if related_report_ids:
        InstallationReport.objects.filter(id__in=related_report_ids).update(status=InstallationStatus.FLAGGED)
    if related_task_ids:
        VerificationTask.objects.filter(id__in=related_task_ids).update(
            anomaly_flag=True,
            status=VerificationStatus.FLAGGED,
        )

    summary = {
        'related_project_count': len(related_project_ids),
        'related_claim_count': len(related_claim_ids),
        'related_report_count': len(related_report_ids),
        'related_verification_task_count': len(related_task_ids),
    }
    if any(summary.values()):
        log_audit(actor, 'vendor_blacklist_related_activity_flagged', vendor, summary)
    return summary


def get_active_blacklist_case(user: User | None) -> VendorBlacklistCase | None:
    if not user or user.role != UserRole.VENDOR:
        return None
    return (
        user.blacklist_cases.filter(
            status__in=[BlacklistCaseStatus.INITIATED, BlacklistCaseStatus.UNDER_REVIEW, BlacklistCaseStatus.BLACKLISTED]
        )
        .order_by('-initiated_at')
        .first()
    )


def is_vendor_restricted(user: User | None) -> bool:
    return bool(user and user.role == UserRole.VENDOR and user.status in {UserStatus.SUSPENDED, UserStatus.BLACKLISTED})


def ensure_blacklisted_identifiers(case: VendorBlacklistCase):
    vendor = case.vendor
    defaults = {
        'organization_name': vendor.organization_name or '',
        'tax_id': vendor.tax_id or '',
        'national_id': vendor.national_id or '',
        'associated_entities': vendor.associated_entities or [],
        'normalized_organization_name': normalize_identifier(vendor.organization_name),
        'normalized_tax_id': normalize_identifier(vendor.tax_id),
        'normalized_national_id': normalize_identifier(vendor.national_id),
        'normalized_associated_entities': normalize_identifier_list(vendor.associated_entities),
        'active': True,
        'released_at': None,
    }
    BlacklistedIdentifier.objects.update_or_create(case=case, vendor=vendor, defaults=defaults)


@transaction.atomic
def apply_blacklist_initiation(case: VendorBlacklistCase, actor: User | None = None):
    vendor = case.vendor
    vendor.status = UserStatus.SUSPENDED
    vendor.is_active = True
    vendor.save(update_fields=['status', 'is_active'])
    paused_verification_summary = pause_vendor_field_verification(vendor, actor)
    case.status = BlacklistCaseStatus.INITIATED
    if not case.notice_sent_at:
        case.notice_sent_at = timezone.now()
    case.save(update_fields=['status', 'notice_sent_at'])
    Notification.objects.create(
        recipient_id=str(vendor.id),
        recipient_name=vendor.full_name or vendor.username or vendor.email,
        type=NotificationChannel.IN_APP,
        event='vendor_blacklisting_initiated',
        title='Notice of Intent to Blacklist',
        body='Your account has been suspended pending review of a blacklisting case. You may upload an appeal from your profile.',
        status=NotificationStatus.SENT,
        linked_entity_id=str(case.id),
    )
    log_audit(
        actor,
        'vendor_blacklisting_initiated',
        case,
        {'vendor_id': str(vendor.id), 'reason': case.reason, **paused_verification_summary},
    )


@transaction.atomic
def apply_blacklist_confirmation(case: VendorBlacklistCase, actor: User | None = None):
    vendor = case.vendor
    vendor.status = UserStatus.BLACKLISTED
    vendor.is_active = True
    vendor.save(update_fields=['status', 'is_active'])
    ensure_blacklisted_identifiers(case)

    active_projects = Project.objects.filter(vendor_id=str(vendor.id)).exclude(status=ProjectStatus.COMPLETED)
    active_projects.update(status=ProjectStatus.HALTED)

    held_claim_ids = list(
        PaymentClaim.objects.filter(
            vendor=vendor,
            status__in=[PaymentClaimStatus.PENDING, PaymentClaimStatus.VERIFIED, PaymentClaimStatus.APPROVED],
        ).values_list('id', flat=True)
    )
    if held_claim_ids:
        PaymentClaim.objects.filter(id__in=held_claim_ids).update(status=PaymentClaimStatus.HELD_AUDIT)
        Disbursement.objects.filter(claim_id__in=held_claim_ids).update(status=DisbursementStatus.HELD_AUDIT)
    terminated_verification_summary = terminate_vendor_field_verification(vendor, actor)
    related_audit_summary = audit_related_vendor_activity(vendor, actor)

    case.status = BlacklistCaseStatus.BLACKLISTED
    case.confirmed_at = case.confirmed_at or timezone.now()
    case.save(update_fields=['status', 'confirmed_at'])
    Notification.objects.create(
        recipient_id=str(vendor.id),
        recipient_name=vendor.full_name or vendor.username or vendor.email,
        type=NotificationChannel.IN_APP,
        event='vendor_blacklisted',
        title='Vendor Blacklisting Confirmed',
        body='Your account has been blacklisted. New bids, project actions, and payments are now restricted until expiry or formal reinstatement.',
        status=NotificationStatus.SENT,
        linked_entity_id=str(case.id),
    )
    log_audit(
        actor,
        'vendor_blacklisted',
        case,
        {
            'vendor_id': str(vendor.id),
            'halted_project_count': active_projects.count(),
            'held_claim_count': len(held_claim_ids),
            **terminated_verification_summary,
            **related_audit_summary,
        },
    )


@transaction.atomic
def release_blacklist_case(case: VendorBlacklistCase, actor: User | None = None, *, expired: bool = False):
    vendor = case.vendor
    vendor.status = UserStatus.REGISTERED
    vendor.is_active = True
    vendor.save(update_fields=['status', 'is_active'])
    BlacklistedIdentifier.objects.filter(case=case, active=True).update(active=False, released_at=timezone.now())
    case.status = BlacklistCaseStatus.EXPIRED if expired else BlacklistCaseStatus.REINSTATED
    case.reinstated_at = timezone.now()
    if actor:
        case.reinstated_by = actor
    case.save(update_fields=['status', 'reinstated_at', 'reinstated_by'])
    Notification.objects.create(
        recipient_id=str(vendor.id),
        recipient_name=vendor.full_name or vendor.username or vendor.email,
        type=NotificationChannel.IN_APP,
        event='vendor_blacklist_released',
        title='Vendor Blacklisting Released',
        body='Your blacklisting restriction has been lifted. Your account is back in Registered status and may require re-qualification before bidding again.',
        status=NotificationStatus.SENT,
        linked_entity_id=str(case.id),
    )
    log_audit(actor, 'vendor_blacklist_released', case, {'vendor_id': str(vendor.id), 'expired': expired})
