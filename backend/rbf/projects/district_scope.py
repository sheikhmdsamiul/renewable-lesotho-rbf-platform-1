"""District scoping for field verifiers.

A project stores only its PRIMARY district on `district`; `district_zone` holds every
district it covers (a lot-wise project spans all of its lot's districts). Installations
are accepted anywhere in that zone, so each installation records the district it was
actually captured in and verifier queues route on that, not on the project's primary.
"""
import re

from django.db.models import Q

from .gis import GpsValidator


def field_verifier_districts(user) -> list[str]:
    user_districts = getattr(user, 'districts', None) or []
    districts: list[str] = []
    if isinstance(user_districts, list):
        districts = [str(d or '').strip() for d in user_districts if str(d or '').strip()]
    if not districts:
        raw_scope = (
            getattr(user, 'verification_zone', '')
            or getattr(user, 'district', '')
            or getattr(user, 'region', '')
            or ''
        )
        districts = [part.strip() for part in str(raw_scope).split(',') if part.strip()]
    return districts


def _project_matches_district(district: str, project_prefix: str) -> Q:
    # Whole comma-separated tokens: a bare icontains would let "Maseru" match "Maseru Urban".
    zone_token = rf'(^|,\s*){re.escape(district)}\s*(,|$)'
    return (
        Q(**{f'{project_prefix}district__iexact': district})
        | Q(**{f'{project_prefix}region__iexact': district})
        | Q(**{f'{project_prefix}district_zone__iregex': zone_token})
    )


def field_verifier_district_filter(user, project_prefix: str = 'project__') -> Q:
    """Projects covering any of the verifier's districts."""
    query = Q()
    for district in field_verifier_districts(user):
        query |= _project_matches_district(district, project_prefix)
    return query or Q(pk__in=[])


def field_verifier_installation_filter(user, report_prefix: str = '') -> Q:
    """Installations captured in one of the verifier's districts. Reports without a
    recorded district fall back to their project's primary district."""
    project_prefix = f'{report_prefix}project__'
    query = Q()
    for district in field_verifier_districts(user):
        query |= Q(**{f'{report_prefix}district__iexact': district}) | (
            Q(**{f'{report_prefix}district': ''})
            & (
                Q(**{f'{project_prefix}district__iexact': district})
                | Q(**{f'{project_prefix}region__iexact': district})
            )
        )
    return query or Q(pk__in=[])


def field_verifier_task_scope_filter(user, task_prefix: str = '') -> Q:
    return Q(**{f'{task_prefix}assigned_verifier': user}) | field_verifier_installation_filter(
        user,
        report_prefix=f'{task_prefix}report__',
    )


def project_district_list(project) -> list[str]:
    candidates = [getattr(project, 'district', '') or '']
    candidates += str(getattr(project, 'district_zone', '') or '').split(',')
    lot = getattr(project, 'lot', None) if getattr(project, 'lot_id', None) else None
    if lot and isinstance(lot.target_districts, list):
        candidates += [str(d or '') for d in lot.target_districts]
    districts: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        value = value.strip()
        key = GpsValidator._normalize_district_name(value)
        if value and key not in seen:
            seen.add(key)
            districts.append(value)
    return districts


def resolve_installation_district(project, latitude, longitude) -> str:
    """The project district (spelled as the project spells it) containing the point,
    falling back to the project's primary district."""
    districts = project_district_list(project)
    fallback = (getattr(project, 'district', '') or (districts[0] if districts else '')).strip()
    if len(districts) <= 1:
        return fallback
    try:
        resolved = GpsValidator.resolveDistrictName(float(latitude), float(longitude))
    except (FileNotFoundError, TypeError, ValueError):
        return fallback
    if resolved:
        key = GpsValidator._normalize_district_name(resolved)
        for district in districts:
            if GpsValidator._normalize_district_name(district) == key:
                return district
    # Just outside every boundary but within tolerance: take the nearest project district.
    best, best_distance = fallback, None
    for district in districts:
        try:
            distance = GpsValidator.distanceToAssignedDistrict(float(latitude), float(longitude), district)
        except (FileNotFoundError, TypeError, ValueError):
            distance = None
        if distance is not None and (best_distance is None or distance < best_distance):
            best, best_distance = district, distance
    return best
