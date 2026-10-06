"""Personal data in reports (Lesotho Data Protection Act 2011).

Beneficiary identifiers (names, phone numbers, IDs) and exact household coordinates are
shown in full only to roles that need them to verify, pay or audit. Everyone else gets them
masked: identifiers keep their last two characters, coordinates are rounded to about 1 km.

PROVISIONAL: these defaults are conservative and await sign-off by the RBF Management Team.
Change BENEFICIARY_IDENTITY_ROLES / EXACT_GPS_ROLES once the policy is approved.
"""
from rbf.users.models import UserRole as R

BENEFICIARY_IDENTITY_ROLES = frozenset({R.RBF_OFFICIAL, R.ADMIN, R.AUDITOR, R.FIELD_VERIFIER})
EXACT_GPS_ROLES = frozenset({R.RBF_OFFICIAL, R.ADMIN, R.AUDITOR, R.FIELD_VERIFIER})
MASKED_GPS_DECIMALS = 2  # about 1.1 km

POLICY_SUMMARY = (
    'Beneficiary identifiers are shown in full to RBF Management Team, Super Admin, Auditor and Field '
    'Verifier, and masked for other roles. Household coordinates are exact for those roles and rounded '
    'to about 1 km for others.'
)


def mask_identity(value) -> str:
    text = str(value or '')
    if len(text) <= 2:
        return '*' * len(text)
    return '*' * (len(text) - 2) + text[-2:]


def mask_gps(value):
    try:
        return round(float(value), MASKED_GPS_DECIMALS)
    except (TypeError, ValueError):
        return ''


def masker_for(role, kind: str):
    """A function applied to each value of a personal-data column, or None to show it as-is."""
    if kind == 'identity' and role not in BENEFICIARY_IDENTITY_ROLES:
        return mask_identity
    if kind == 'gps' and role not in EXACT_GPS_ROLES:
        return mask_gps
    return None


def is_masked_for(role, kinds) -> bool:
    return any(masker_for(role, kind) for kind in kinds)
