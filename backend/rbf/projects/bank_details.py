from functools import lru_cache

from django.db import connection

from rbf.users.models import PrequalificationStatus, User, VendorPrequalification


@lru_cache(maxsize=1)
def _vendor_preq_columns() -> set[str]:
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                VendorPrequalification._meta.db_table,
            )
        }


def get_vendor_bank_snapshot(vendor: User) -> dict[str, str]:
    snapshot = {
        'bank_name': getattr(vendor, 'bank_name', '') or '',
        'bank_branch': getattr(vendor, 'bank_branch', '') or '',
        'bank_swift_code': getattr(vendor, 'bank_swift_code', '') or '',
        'bank_sort_code': getattr(vendor, 'bank_sort_code', '') or '',
        'bank_account_name': getattr(vendor, 'bank_account_name', '') or '',
        'bank_account_number': getattr(vendor, 'bank_account_number', '') or '',
    }
    available_columns = _vendor_preq_columns()
    selectable_fields = [
        field
        for field in snapshot.keys()
        if field in available_columns
    ]
    if not selectable_fields:
        return snapshot

    approved = (
        VendorPrequalification.objects
        .filter(vendor=vendor, status=PrequalificationStatus.APPROVED)
        .order_by('-reviewed_at', '-submitted_at')
        .values(*selectable_fields)
        .first()
    )
    latest = approved or (
        VendorPrequalification.objects
        .filter(vendor=vendor)
        .order_by('-submitted_at')
        .values(*selectable_fields)
        .first()
    )
    if not latest:
        return snapshot

    for field in selectable_fields:
        snapshot[field] = latest.get(field) or snapshot[field]
    return snapshot
