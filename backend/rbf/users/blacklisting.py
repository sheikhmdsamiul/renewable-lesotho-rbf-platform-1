from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus
from rbf.projects.audit import log_audit
from rbf.projects.models import (
    Disbursement,
    DisbursementStatus,
    PaymentClaim,
    PaymentClaimStatus,
    Project,
    ProjectStatus,
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
        'normalized_organization_name': normalize_identifier(vendor.organization_name),
        'normalized_tax_id': normalize_identifier(vendor.tax_id),
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
    log_audit(actor, 'vendor_blacklisting_initiated', case, {'vendor_id': str(vendor.id), 'reason': case.reason})


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
